# -*- coding: utf-8 -*-
"""skillpay.gateway —— 调用支付宝两个官方接口。

只做两件事：
  1. `alipay.aipay.agent.payment.verify`        —— 验付（校验 Payment-Proof 真实性）
  2. `alipay.aipay.agent.fulfillment.confirm`   —— 履约确认

均走支付宝网关 `gateway.do`，请求参数按 RSA2 签名（复用 bill.py 的签名实现）。
沙箱与生产只差 `gateway` 与 `service_id`（见 config.py）。

另外提供 `MockGateway`：仅用于**离线自测**，模拟返回验付成功/失败，
让整条链路（402 → 凭证重试 → 验付 → 幂等履约 → 履约确认）在没有商户资质时也能跑通。
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from .bill import build_sign_string, seller_signature

VERIFY = "alipay.aipay.agent.payment.verify"
CONFIRM = "alipay.aipay.agent.fulfillment.confirm"


class GatewayError(RuntimeError):
    """网络或协议层错误。"""


class AlipayGateway:
    def __init__(self, cfg, timeout=20):
        self.cfg = cfg
        self.timeout = timeout

    def _call(self, method, biz):
        if not self.cfg.get("app_id"):
            raise GatewayError("未配置 SKILLPAY_APP_ID，无法调用 %s" % method)
        if not self.cfg.get("merchant_private_key"):
            raise GatewayError("未配置商户应用私钥，无法调用 %s" % method)

        params = {
            "app_id": self.cfg["app_id"],
            "method": method,
            "charset": "utf-8",
            "sign_type": "RSA2",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0",
            "biz_content": json.dumps(biz, ensure_ascii=False, separators=(",", ":")),
        }
        params["sign"] = seller_signature(params, self.cfg["merchant_private_key"])

        body = urllib.parse.urlencode(params).encode("utf-8")
        req = urllib.request.Request(
            self.cfg["gateway"], data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                text = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            raise GatewayError("网关返回 HTTP %s：%s" % (exc.code, exc.read()[:300]))
        except Exception as exc:
            raise GatewayError("调用 %s 失败：%s" % (method, exc))

        try:
            data = json.loads(text)
        except Exception:
            raise GatewayError("网关响应不是 JSON：%s" % text[:300])

        # 失败时支付宝返回 error_response
        if "error_response" in data:
            err = data["error_response"]
            return {"code": err.get("code"), "sub_code": err.get("sub_code"),
                    "sub_msg": err.get("sub_msg") or err.get("msg"), "raw": data}

        # 成功节点名 = method 里的点换成下划线 + _response
        node = method.replace(".", "_") + "_response"
        resp = data.get(node, data)
        # 兼容扁平结构（SDK/网关两种返回形态官方示例都提到过）
        if isinstance(resp, dict):
            resp.setdefault("raw", data)
            return resp
        return {"code": None, "sub_msg": "响应结构无法解析", "raw": data}

    # ---------- 1) 验付 ----------
    def payment_verify(self, trade_no, payment_proof, client_session=None):
        biz = {"trade_no": trade_no, "payment_proof": payment_proof}
        if client_session:
            biz["client_session"] = client_session
        return self._call(VERIFY, biz)

    # ---------- 2) 履约确认 ----------
    def fulfillment_confirm(self, trade_no):
        return self._call(CONFIRM, {"trade_no": trade_no})


class MockGateway:
    """离线自测用。`resolver(trade_no, payment_proof)` 返回本次验付的字段，
    再与 `verify_response` 合并（后者优先，便于构造异常场景）。

    仅覆盖支付宝返回值的形状，**不改变** service.py 里的任何校验逻辑——
    所以自测能真实检验「金额/资源/时效/幂等」这些控制流。
    """

    def __init__(self, verify_response=None, confirm_ok=True, resolver=None):
        self.calls = []
        self.verify_response = verify_response or {}
        self.confirm_ok = confirm_ok
        self.resolver = resolver
        self.confirm_calls = 0

    def payment_verify(self, trade_no, payment_proof, client_session=None):
        self.calls.append({"method": VERIFY, "trade_no": trade_no,
                           "client_session": client_session})
        base = {"code": "10000", "trade_no": trade_no, "active": True}
        if self.resolver:
            extra = self.resolver(trade_no, payment_proof) or {}
            base.update(extra)
        base.update(self.verify_response)
        return base

    def fulfillment_confirm(self, trade_no):
        self.calls.append({"method": CONFIRM, "trade_no": trade_no})
        self.confirm_calls += 1
        if self.confirm_ok:
            return {"code": "10000", "trade_no": trade_no}
        return {"code": "40004", "sub_code": "SYSTEM_ERROR",
                "sub_msg": "模拟的履约确认失败"}


def get_gateway(cfg):
    if cfg.get("gateway_impl") == "mock":
        return MockGateway()
    return AlipayGateway(cfg)
