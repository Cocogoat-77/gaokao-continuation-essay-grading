# -*- coding: utf-8 -*-
"""skillpay.service —— 付费编排核心（probe / pay / complete / ack 四步）。

| 步骤 | 本模块 | 做什么 |
|---|---|---|
| probe    | `probe()`    | 无 `Payment-Proof` → 建单落库 → 返回 **HTTP 402 + Payment-Needed** |
| pay      | `pay_info()` | 只输出商品名与价格，供 Agent 展示；真正的收银由支付宝官方支付能力拉起（本服务不代付） |
| complete | `complete()` | 携带 `Payment-Proof` 重试 → **验付** → 本地订单四项校验 → **幂等履约** → 履约确认 → 200 |
| ack      | `ack()`      | 单独重试履约确认（资源已生成、确认失败时用） |

控制流的两个关键点（官方契约的硬要求）：
  - **先落库再下发账单**：`create_pending` 必须发生在返回 `Payment-Needed` 之前。
  - **任一校验失败一律回到 402**，绝不返回资源；也绝不用「结果不明」为由让用户重复付款。
"""
import json
import os
import time
from datetime import datetime

from . import bill, config as config_mod, proof as proof_mod
from .gateway import get_gateway
from .store import IN_PROGRESS, FULFILL_STATUS, ORDER_STATUS, OrderStore, normalize_amount


class DeliveryError(RuntimeError):
    """交付物生成失败。"""


# ---------------------------------------------------------------- 默认交付物

def _load_render():
    """延迟加载 Skill 自带的 render.py（避免与付费层产生循环依赖）。"""
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "render.py")
    spec = importlib.util.spec_from_file_location("skill_render", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def default_deliver(payload, order):
    """付费交付物 = 该次调用要渲染的批改报告。

    payload 形如 {'json': 路径} 或 {'jsondir': 目录, 'outdir': 目录, 'theme': 'default'}。
    **注意**：本函数在 SQLite 写事务内被调用，只能做文件生成，
    不得再去访问订单库（会造成同库写锁自锁）。
    """
    payload = payload or {}
    outdir = payload.get("outdir") or os.path.join(os.getcwd(), "out")
    theme = payload.get("theme") or "default"
    marks = payload.get("marks") or "theme"

    targets = []
    if payload.get("json"):
        targets.append(payload["json"])
    if payload.get("jsondir"):
        d = payload["jsondir"]
        targets += [os.path.join(d, f) for f in sorted(os.listdir(d))
                    if f.endswith(".json")]

    if not targets:
        # 没有给输入时，交付一次可核验的调用凭据（自测/联调用）
        return {
            "resource_id": order["resource_id"],
            "out_trade_no": order["out_trade_no"],
            "delivered_at": datetime.now().isoformat(timespec="seconds"),
            "produced": [],
            "note": "本次调用未指定 --json/--jsondir，仅交付调用凭据",
        }

    render = _load_render()
    render.use_theme(theme)
    render.use_marks(marks)

    produced, errors = [], []
    for src in targets:
        try:
            html_path, pdf_path = render.process(src, outdir)
            produced.append({"json": os.path.basename(src),
                             "html": html_path, "pdf": pdf_path})
        except Exception as exc:
            errors.append({"json": os.path.basename(src), "error": str(exc)})

    if not produced and errors:
        raise DeliveryError("交付失败：%s" % json.dumps(errors, ensure_ascii=False))

    return {
        "resource_id": order["resource_id"],
        "out_trade_no": order["out_trade_no"],
        "delivered_at": datetime.now().isoformat(timespec="seconds"),
        "outdir": outdir,
        "theme": theme,
        "produced": produced,
        "errors": errors,
    }


# ---------------------------------------------------------------- 服务

class PayService:
    def __init__(self, cfg=None, store=None, gateway=None, deliver=None):
        self.cfg = cfg or config_mod.load()
        self.store = store or OrderStore(self.cfg["state_dir"])
        self.gateway = gateway if gateway is not None else get_gateway(self.cfg)
        self.deliver = deliver or default_deliver

    # -------- 工具 --------
    @property
    def resource_id(self):
        return self.cfg["resource_id"]

    @property
    def unit_price(self):
        return normalize_amount(self.cfg.get("unit_price")) or "0.00"

    @staticmethod
    def count_reports(payload):
        """本次请求要交付多少篇报告 —— 决定账单金额。

        - 指定 `--json <一份>`            → 1 篇
        - 指定 `--jsondir <目录>`         → 目录里的 .json 个数
        - 两者都没给（只交付调用凭据）      → 1 篇
        """
        payload = payload or {}
        if payload.get("json"):
            return 1
        d = payload.get("jsondir")
        if d and os.path.isdir(d):
            n = len([f for f in os.listdir(d) if f.endswith(".json")])
            return n if n else 1
        return 1

    def quote(self, payload):
        """返回 (金额, 篇数, 商品描述)，按篇计价并给出明细。"""
        qty = self.count_reports(payload)
        amount, qty = config_mod.amount_for(self.cfg, qty)
        if self.cfg.get("amount"):
            goods = "%s（%d 篇，打包价 %s 元）" % (self.cfg["goods_name"], qty, amount)
        else:
            goods = "%s（%d 篇 × %s 元）" % (self.cfg["goods_name"], qty, self.unit_price)
        return amount, qty, goods

    def _resp(self, status, body, headers=None):
        return {"status": status, "headers": headers or {}, "body": body}

    def _redirect_to_402(self, reason, payload=None):
        """任一校验失败的统一出口：重新下发 402，让 Agent 重新支付。"""
        resp = self.probe(payload)
        resp["body"]["rejected_reason"] = reason
        return resp

    # -------- 价格信息（不下单，供 Agent 展示） --------
    def pay_info(self, payload=None):
        amount, qty, goods = self.quote(payload)
        return {
            "resource_id": self.resource_id,
            "goods_name": goods,
            "unit_price": self.unit_price,
            "quantity": qty,
            "amount": amount,
            "currency": "CNY",
            "mode": self.cfg["mode"],
            "note": "实际扣费以服务返回的 402 + Payment-Needed 账单金额为准，二者必须一致",
        }

    # -------- 第 1 步：probe —— 402 账单下发 --------
    def probe(self, payload=None):
        if not self.cfg.get("merchant_private_key"):
            return self._resp(500, {
                "code": "CONFIG_ERROR",
                "message": "未配置商户应用私钥，无法签发账单。"
                           "请设置 SKILLPAY_MERCHANT_PRIVATE_KEY 或本地 skillpay.local.json",
            })

        try:
            amount, quantity, goods_name = self.quote(payload)
        except config_mod.QuantityError as exc:
            return self._resp(400, {"code": "QUANTITY_ERROR", "message": str(exc)})

        out_trade_no = bill.new_out_trade_no()
        pay_before = bill.pay_before_iso(self.cfg.get("pay_window_min", 30))

        header, order, payload_json = bill.build_payment_needed(
            self.cfg, out_trade_no, amount, self.resource_id, pay_before,
            goods_name=goods_name, quantity=quantity)

        # ★ 必须持久化成功后才返回 Payment-Needed
        self.store.create_pending(order)

        return self._resp(402, {
            "code": "Payment-Needed",
            "message": "需要支付",
            "out_trade_no": out_trade_no,
            "amount": amount,
            "currency": "CNY",
            "quantity": quantity,
            "unit_price": self.unit_price,
            "resource_id": self.resource_id,
            "goods_name": goods_name,
            "pay_before": pay_before,
            "seller_name": self.cfg["seller_name"],
        }, {"Payment-Needed": header})

    # -------- 第 3 步：complete —— 携带凭证重试（验付 + 幂等履约） --------
    def complete(self, payment_proof_header, payload=None):
        # 3.1 解析 Payment-Proof；解析不了直接回到 402
        try:
            prf = proof_mod.parse_payment_proof(payment_proof_header)
        except proof_mod.ProofError as exc:
            return self._redirect_to_402("凭证解析失败：%s" % exc, payload)

        # 3.2 验付调用
        try:
            verify = self.gateway.payment_verify(
                prf["trade_no"], prf["payment_proof"], prf["client_session"])
        except Exception as exc:
            return self._redirect_to_402("验付调用失败：%s" % exc, payload)

        if str(verify.get("code")) != "10000":
            return self._redirect_to_402(
                "验付未通过：%s %s" % (verify.get("sub_code") or verify.get("code") or "",
                                     verify.get("sub_msg") or ""), payload)

        sandbox = config_mod.is_sandbox(self.cfg)
        returned_trade_no = (verify.get("trade_no") or verify.get("tradeNo") or "").strip()
        verify_out_trade_no = (verify.get("out_trade_no")
                               or verify.get("outTradeNo") or "").strip()
        returned_amount = verify.get("amount")
        returned_resource_id = (verify.get("resource_id")
                                or verify.get("resourceId") or "").strip()
        active = verify.get("active")

        # 3.3 凭证有效性：active=true、trade_no 一致、订单号与资源标识非空
        verify_trade_no = returned_trade_no or (prf["trade_no"] if sandbox else "")
        if (active is not True or not verify_trade_no
                or verify_trade_no != prf["trade_no"]
                or not verify_out_trade_no):
            return self._redirect_to_402("支付凭证无效或已过期", payload)

        # 3.4 本地订单匹配
        order = self.store.find_by_out_trade_no(verify_out_trade_no)
        if order is None:
            return self._redirect_to_402("本地订单不存在：%s" % verify_out_trade_no, payload)

        verify_amount = (returned_amount if returned_amount not in (None, "")
                         else (order["amount"] if sandbox else None))
        resource_id_verified = returned_resource_id or (
            order["resource_id"] if sandbox else "")

        if not resource_id_verified:
            return self._redirect_to_402("验付结果缺少 resource_id", payload)

        # 3.5 篇数一致性：本次请求要交付的篇数必须与下单时一致
        #     （按篇计价，篇数变了金额就变了；这里显式再校验一次，防篡改）
        req_quantity = self.count_reports(payload)
        if int(order.get("quantity", 1)) != int(req_quantity):
            return self._redirect_to_402(
                "篇数不一致：下单 %s 篇 / 本次请求 %s 篇。请用同一请求原样重试"
                % (order.get("quantity"), req_quantity), payload)

        # 3.6 金额一致性
        if normalize_amount(order["amount"]) != normalize_amount(verify_amount):
            return self._redirect_to_402(
                "金额不一致：本地 %s / 验付 %s" % (order["amount"], verify_amount), payload)

        # 3.7 资源防串：验付资源 == 本地订单资源 == 本次请求资源
        if (order["resource_id"] != resource_id_verified
                or resource_id_verified != self.resource_id):
            return self._redirect_to_402(
                "资源标识不一致：请求 %s / 本地 %s / 验付 %s"
                % (self.resource_id, order["resource_id"], resource_id_verified), payload)

        # 3.8 本地订单状态与时效
        if order["currency"] != "CNY":
            return self._redirect_to_402("订单币种不是 CNY", payload)
        if order["order_status"] not in ORDER_STATUS:
            return self._redirect_to_402("订单状态异常：%s" % order["order_status"], payload)
        if order["fulfill_status"] not in FULFILL_STATUS:
            return self._redirect_to_402("履约状态异常：%s" % order["fulfill_status"], payload)

        in_progress = order["fulfill_status"] in IN_PROGRESS
        if not in_progress and not _is_future(order["pay_before"]):
            return self._redirect_to_402("订单已过期：%s" % order["pay_before"], payload)

        # 3.9 同一 trade_no 不得履给另一笔订单（trade_no 唯一索引 + 显式检查）
        other = self.store.find_by_trade_no(verify_trade_no)
        if other and other["out_trade_no"] != order["out_trade_no"]:
            return self._redirect_to_402(
                "该支付凭证已用于订单 %s" % other["out_trade_no"], payload)

        # 3.10 幂等履约：资源只生成一次
        try:
            fulfillment = self.store.prepare_fulfillment(
                out_trade_no=order["out_trade_no"],
                trade_no=verify_trade_no,
                expected_amount=order["amount"],
                expected_resource_id=resource_id_verified,
                create_resource=lambda: self.deliver(payload, order),
                expected_quantity=req_quantity,
            )
        except DeliveryError as exc:
            return self._resp(500, {"code": "DELIVERY_ERROR", "message": str(exc)})

        if (not fulfillment or fulfillment.get("state") not in IN_PROGRESS
                or not fulfillment.get("service_result")):
            return self._resp(500, {
                "code": "FULFILLMENT_STATE_ERROR",
                "message": "履约状态异常，未生成可交付结果",
            })

        service_result = fulfillment["service_result"]

        # 3.11 已经履约并确认过 → 直接返回历史结果，不重复发放、不重复扣费
        if fulfillment["state"] == "FULFILLED":
            return self._delivered(order, verify_trade_no, resource_id_verified,
                                   service_result, already_fulfilled=True)

        # 3.12 履约确认（ack）；失败则允许用**同一 Payment-Proof** 重试
        if not self._confirm(verify_trade_no):
            return self._resp(502, {
                "code": "FULFILLMENT_CONFIRM_FAILED",
                "message": "资源已生成但履约确认失败，请稍后使用同一 Payment-Proof 重试",
                "out_trade_no": order["out_trade_no"],
                "trade_no": verify_trade_no,
            })

        self.store.mark_fulfilled(order["out_trade_no"], verify_trade_no)
        return self._delivered(order, verify_trade_no, resource_id_verified,
                               service_result, already_fulfilled=False)

    # -------- 第 4 步：ack —— 单独重试履约确认 --------
    def ack(self, trade_no):
        if not trade_no:
            return self._resp(400, {"code": "BAD_REQUEST", "message": "缺少 trade_no"})
        order = self.store.find_by_trade_no(trade_no)
        if order is None:
            return self._resp(404, {"code": "ORDER_NOT_FOUND",
                                    "message": "找不到该 trade_no 对应的订单"})
        if order["fulfill_status"] == "FULFILLED":
            return self._resp(200, {"code": "ALREADY_FULFILLED",
                                    "out_trade_no": order["out_trade_no"],
                                    "trade_no": trade_no})
        if order["fulfill_status"] != "PENDING_CONFIRM":
            return self._resp(409, {"code": "NOT_READY",
                                    "message": "订单尚未生成资源，无法确认履约",
                                    "fulfill_status": order["fulfill_status"]})
        if not self._confirm(trade_no):
            return self._resp(502, {"code": "FULFILLMENT_CONFIRM_FAILED",
                                    "message": "履约确认失败，可重试"})
        self.store.mark_fulfilled(order["out_trade_no"], trade_no)
        return self._resp(200, {"code": "OK", "out_trade_no": order["out_trade_no"],
                                "trade_no": trade_no})

    # -------- 内部 --------
    def _confirm(self, trade_no):
        try:
            resp = self.gateway.fulfillment_confirm(trade_no)
        except Exception:
            return False
        return str(resp.get("code")) == "10000"

    def _delivered(self, order, trade_no, resource_id, service_result,
                   already_fulfilled):
        try:
            content = json.loads(service_result)
        except Exception:
            content = service_result
        return self._resp(200, {
            "code": "OK",
            "resource_id": resource_id,
            "content": content,
            "trade_no": trade_no,
            "out_trade_no": order["out_trade_no"],
            "already_fulfilled": already_fulfilled,
            "fulfillment_confirmed": True,
        }, {"Payment-Validation": bill.build_payment_validation(
            trade_no, order["out_trade_no"], resource_id)})


def _is_future(value):
    try:
        return datetime.fromisoformat(value).timestamp() > time.time()
    except (TypeError, ValueError):
        return False
