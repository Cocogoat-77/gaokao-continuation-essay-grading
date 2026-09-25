# -*- coding: utf-8 -*-
"""skillpay.selftest —— 离线跑通完整付费链路（不需要商户资质、不联网）。

它真实地走一遍：
    402 账单下发 → RSA2 签名可验 → 订单落库 → 携带 Payment-Proof 重试
    → 验付 → 本地订单四项校验 → 幂等履约（资源只生成一次）→ 履约确认
    → 200 + Payment-Validation
并逐一验证失败分支：凭证损坏、验付失败、active=false、金额不符、资源串号、
篇数不符、订单不存在、订单过期、凭证复用、履约确认失败与重试。

用法：
    python scripts/skillpay/selftest.py
退出码 0 = 全部通过。
"""
import base64
import json
import os
import shutil
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skillpay import bill, config as config_mod                     # noqa: E402
from skillpay.gateway import MockGateway                            # noqa: E402
from skillpay.service import PayService                             # noqa: E402
from skillpay.store import OrderStore                               # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print("  %s %s%s" % ("✅" if ok else "❌", name, ("  —— " + detail) if detail else ""))
    return ok


# ---------------------------------------------------------------- 测试脚手架

def make_keypair():
    """生成一对 RSA 密钥（PEM）。用 pycryptodome —— 与 bill.py 的签名后端一致。"""
    from Crypto.PublicKey import RSA
    key = RSA.generate(2048)
    return key.export_key(format="PEM").decode(), key.publickey().export_key(format="PEM").decode()


def make_cfg(state_dir, priv, pub):
    return {
        "mode": "sandbox",
        "gateway": config_mod.SANDBOX_GATEWAY,
        "app_id": "2021000000000000",
        "seller_id": "2088000000000000",
        "seller_name": "读后续写批改服务",
        "service_id": config_mod.SANDBOX_SERVICE_ID,
        "unit_price": "0.01",
        "amount": "",
        "quantity_cap": config_mod.DEFAULT_QUANTITY_CAP,
        "resource_id": config_mod.RESOURCE_ID,
        "goods_name": config_mod.GOODS_NAME,
        "merchant_private_key": priv,
        "alipay_public_key": pub,
        "state_dir": state_dir,
        "pay_window_min": 30,
        "gateway_impl": "mock",
    }


def make_proof(trade_no, payment_proof="pp_" + "x" * 24, client_session=None):
    payload = {"protocol": {"trade_no": trade_no, "payment_proof": payment_proof},
               "method": {}}
    if client_session:
        payload["method"]["client_session"] = client_session
    return bill.base64url_encode(json.dumps(payload, ensure_ascii=False))


def build_service(state_dir, priv, pub, resolver=None, confirm_ok=True, deliver=None):
    cfg = make_cfg(state_dir, priv, pub)
    gw = MockGateway(confirm_ok=confirm_ok, resolver=resolver)
    return PayService(cfg, store=OrderStore(state_dir), gateway=gw, deliver=deliver), gw


def json_dir(parent, n):
    d = os.path.join(parent, "final_%d" % n)
    os.makedirs(d, exist_ok=True)
    for i in range(n):
        with open(os.path.join(d, "s%02d.json" % i), "w", encoding="utf-8") as f:
            f.write("{}")
    return d


# ---------------------------------------------------------------- 主流程

def main():
    tmp = tempfile.mkdtemp(prefix="skillpay_selftest_")
    priv, pub = make_keypair()
    proof_map = {}          # trade_no -> 验付应返回的字段
    delivered = []          # deliver 被调用的次数记录

    def fake_deliver(payload, order):
        delivered.append(order["out_trade_no"])
        return {"resource_id": order["resource_id"],
                "out_trade_no": order["out_trade_no"],
                "produced": [{"json": "s%02d.json" % i} for i in range(order["quantity"])],
                "quantity": order["quantity"]}

    def resolver(trade_no, payment_proof):
        return proof_map.get(trade_no, {})

    state_a = os.path.join(tmp, "state_a")
    svc, gw = build_service(state_a, priv, pub, resolver=resolver,
                            deliver=fake_deliver)

    try:
        print("\n【一】probe —— 402 账单下发（按篇计价 0.01 元/篇）")
        r = svc.probe({"json": "some/one.json"})
        check("未付款返回 HTTP 402", r["status"] == 402, "status=%s" % r["status"])
        check("带 Payment-Needed 响应头", "Payment-Needed" in r["headers"])
        check("账单金额 = 0.01（1 篇）", r["body"]["amount"] == "0.01",
              "amount=%s" % r["body"]["amount"])
        order_no = r["body"]["out_trade_no"]
        hdr = r["headers"].get("Payment-Needed", "")
        decoded = bill.decode_payment_needed(hdr)
        proto, method = decoded.get("protocol", {}), decoded.get("method", {})
        need_proto = ("out_trade_no", "amount", "currency", "resource_id",
                      "pay_before", "seller_signature", "seller_sign_type",
                      "seller_unique_id")
        need_method = ("seller_name", "seller_id", "seller_app_id", "goods_name",
                       "seller_unique_id_key", "service_id")
        check("protocol 字段齐全", all(k in proto for k in need_proto),
              "缺：" + ",".join(k for k in need_proto if k not in proto))
        check("method 字段齐全", all(k in method for k in need_method),
              "缺：" + ",".join(k for k in need_method if k not in method))
        check("currency=CNY", proto.get("currency") == "CNY")
        check("seller_sign_type=RSA2", proto.get("seller_sign_type") == "RSA2")
        check("seller_unique_id_key=seller_id",
              method.get("seller_unique_id_key") == "seller_id")
        check("沙箱 service_id=api_mock_service_id",
              method.get("service_id") == config_mod.SANDBOX_SERVICE_ID)
        sf = bill.sign_fields_from_payment_needed(decoded)
        check("签名字段可从账单还原（跨 protocol/method）",
              all(sf.get(k) for k in bill.SIGN_FIELDS),
              "缺：" + ",".join(k for k in bill.SIGN_FIELDS if not sf.get(k)))
        check("RSA2 签名可被公钥验证",
              bill.verify_signature(sf, proto.get("seller_signature", ""), pub))
        tampered = dict(sf, amount="0.00")
        check("篡改金额后签名失效",
              not bill.verify_signature(tampered, proto.get("seller_signature", ""), pub))
        tampered2 = dict(sf, service_id="someone_else_service")
        check("篡改 service_id 后签名失效",
              not bill.verify_signature(tampered2, proto.get("seller_signature", ""), pub))
        row = svc.store.find_by_out_trade_no(order_no)
        check("返回账单前已落库（PENDING_PAYMENT/UNFULFILLED）",
              row and row["order_status"] == "PENDING_PAYMENT"
              and row["fulfill_status"] == "UNFULFILLED")
        check("订单记录了篇数与金额", row and row["quantity"] == 1 and row["amount"] == "0.01")

        print("\n【二】按篇计价：5 篇 → 0.05 元；超上限拒绝")
        d5 = json_dir(tmp, 5)
        r5 = svc.probe({"jsondir": d5, "outdir": os.path.join(tmp, "out5")})
        check("5 篇账单金额 = 0.05", r5["body"]["amount"] == "0.05",
              "amount=%s" % r5["body"]["amount"])
        check("账单里写明篇数", r5["body"]["quantity"] == 5)
        check("商品描述含篇数明细", "5 篇" in r5["body"]["goods_name"],
              r5["body"]["goods_name"])
        check("默认单次上限 = 2500 篇",
              config_mod.DEFAULT_QUANTITY_CAP == 2500,
              "DEFAULT_QUANTITY_CAP=%s" % config_mod.DEFAULT_QUANTITY_CAP)
        cap_amount = config_mod.amount_for(svc.cfg, 2500)[0]
        check("2500 篇的账单 = 25.00 元（上限价）", cap_amount == "25.00",
              "amount=%s" % cap_amount)
        # 超上限：用一个上限被调小的服务来验证（避免真造 2501 个文件）
        svc_small = PayService(dict(svc.cfg, quantity_cap=3), store=svc.store,
                               gateway=gw, deliver=fake_deliver)
        r_over = svc_small.probe({"jsondir": json_dir(tmp, 4)})
        check("超过篇数上限返回 400", r_over["status"] == 400
              and r_over["body"]["code"] == "QUANTITY_ERROR",
              "status=%s message=%s" % (r_over["status"],
                                        r_over["body"].get("message", "")))
        check("pay-info 报出单价与篇数",
              svc.pay_info({"json": "x"})["unit_price"] == "0.01")

        print("\n【三】complete —— 携带 Payment-Proof 重试（验付 + 幂等履约）")
        trade_no = "T2026092600000001"
        proof_map[trade_no] = {"out_trade_no": order_no, "amount": "0.01",
                               "resource_id": svc.resource_id}
        proof = make_proof(trade_no, client_session="sess-1")
        ok = svc.complete(proof, {"json": "some/one.json"})
        check("验付通过并交付（HTTP 200）", ok["status"] == 200,
              "status=%s body=%s" % (ok["status"], json.dumps(ok["body"], ensure_ascii=False)[:160]))
        check("返回 Payment-Validation 头", "Payment-Validation" in ok["headers"])
        if "Payment-Validation" in ok["headers"]:
            pv = json.loads(bill.base64url_decode(ok["headers"]["Payment-Validation"]))
            check("Payment-Validation.validated=true", pv.get("validated") is True)
            check("Payment-Validation.resource_id 一致",
                  pv.get("resource_id") == svc.resource_id)
        check("履约确认已调用", gw.confirm_calls == 1, "confirm_calls=%s" % gw.confirm_calls)
        check("client_session 已透传",
              any(c.get("client_session") == "sess-1" for c in gw.calls))
        row = svc.store.find_by_out_trade_no(order_no)
        check("订单最终状态 FULFILLED",
              row and row["fulfill_status"] == "FULFILLED" and row["order_status"] == "PAID")
        check("资源生成了一次", len(delivered) == 1, "delivered=%d" % len(delivered))

        print("\n【四】幂等 —— 同一订单重复携带 Payment-Proof 不重复发放")
        again = svc.complete(proof, {"json": "some/one.json"})
        check("重试返回 200（历史结果）", again["status"] == 200)
        check("already_fulfilled=true", again["body"].get("already_fulfilled") is True)
        check("资源未被重复生成", len(delivered) == 1, "delivered=%d" % len(delivered))
        check("未重复调用履约确认", gw.confirm_calls == 1, "confirm_calls=%s" % gw.confirm_calls)

        print("\n【五】失败分支 —— 一律回到 402，绝不返回资源")

        def case(label, payload=None, proof_header=None, resolver_patch=None,
                 trade="T2026092600000002", expect_402=True, outdir="o1"):
            order = svc.probe({"json": "x/%s.json" % outdir})
            ono = order["body"]["out_trade_no"]
            proof_map[trade] = {"out_trade_no": ono, "amount": order["body"]["amount"],
                                "resource_id": svc.resource_id}
            if resolver_patch:
                proof_map[trade].update(resolver_patch)
            hdr = proof_header if proof_header is not None else make_proof(trade)
            res = svc.complete(hdr, payload if payload is not None
                               else {"json": "x/%s.json" % outdir})
            ok = (res["status"] == 402) if expect_402 else (res["status"] == 200)
            check(label, ok, "status=%s reason=%s" % (
                res["status"], res["body"].get("rejected_reason", "")))
            return res

        case("凭证是乱码 → 402", proof_header="!!!not-base64!!!")
        case("凭证缺 trade_no → 402",
             proof_header=bill.base64url_encode(json.dumps(
                 {"protocol": {"payment_proof": "x"}})))
        # 验付失败：临时把 mock 的返回码改掉
        gw.verify_response = {"code": "40004", "sub_msg": "凭证无效"}
        case("验付返回非 10000 → 402", trade="T2026092600000003")
        gw.verify_response = {}
        gw.verify_response = {"active": False}
        case("active=false → 402", trade="T2026092600000004")
        gw.verify_response = {}
        case("金额不一致 → 402", trade="T2026092600000005",
             resolver_patch={"amount": "9.99"})
        case("资源标识串号 → 402", trade="T2026092600000006",
             resolver_patch={"resource_id": "other-resource"})
        case("本地订单不存在 → 402", trade="T2026092600000007",
             resolver_patch={"out_trade_no": "ORDER_NOT_EXIST"})
        case("篇数不一致（下单 1 篇，重试改 2 篇）→ 402",
             payload={"jsondir": json_dir(tmp, 2)}, trade="T2026092600000008",
             outdir="o8")

        # 订单过期
        r_exp = svc.probe({"json": "x/exp.json"})
        o_exp = r_exp["body"]["out_trade_no"]
        trade_exp = "T2026092600000009"
        proof_map[trade_exp] = {"out_trade_no": o_exp, "amount": r_exp["body"]["amount"],
                                "resource_id": svc.resource_id}
        conn = sqlite3.connect(svc.store.db_path)
        conn.execute("UPDATE orders SET pay_before=? WHERE out_trade_no=?",
                     ("2020-01-01T00:00:00+08:00", o_exp))
        conn.commit()
        conn.close()
        res = svc.complete(make_proof(trade_exp), {"json": "x/exp.json"})
        check("订单已过期 → 402", res["status"] == 402,
              "reason=%s" % res["body"].get("rejected_reason", ""))

        print("\n【六】凭证复用 —— 同一 trade_no 不能履给另一笔订单")
        r_new = svc.probe({"json": "x/reuse.json"})
        o_new = r_new["body"]["out_trade_no"]
        proof_map[trade_no] = {"out_trade_no": o_new, "amount": r_new["body"]["amount"],
                               "resource_id": svc.resource_id}
        res = svc.complete(make_proof(trade_no), {"json": "x/reuse.json"})
        check("该凭证已用于订单 %s → 402" % order_no, res["status"] == 402,
              "reason=%s" % res["body"].get("rejected_reason", ""))

        print("\n【七】履约确认失败 → 502 → 用同一凭证重试可恢复")
        state_b = os.path.join(tmp, "state_b")
        svc_b, gw_b = build_service(state_b, priv, pub, resolver=resolver,
                                    confirm_ok=False, deliver=fake_deliver)
        rb = svc_b.probe({"json": "x/b.json"})
        ob = rb["body"]["out_trade_no"]
        tb = "T2026092600000010"
        proof_map[tb] = {"out_trade_no": ob, "amount": rb["body"]["amount"],
                         "resource_id": svc_b.resource_id}
        res = svc_b.complete(make_proof(tb), {"json": "x/b.json"})
        check("确认失败返回 502", res["status"] == 502,
              "status=%s code=%s" % (res["status"], res["body"].get("code")))
        rowb = svc_b.store.find_by_out_trade_no(ob)
        check("资源已生成但状态为 PENDING_CONFIRM",
              rowb and rowb["fulfill_status"] == "PENDING_CONFIRM")
        gw_b.confirm_ok = True
        ack = svc_b.ack(tb)
        check("ack 重试履约确认成功", ack["status"] == 200, "status=%s" % ack["status"])
        rowb = svc_b.store.find_by_out_trade_no(ob)
        check("ack 后订单变为 FULFILLED", rowb and rowb["fulfill_status"] == "FULFILLED")
        res = svc_b.complete(make_proof(tb), {"json": "x/b.json"})
        check("重试 complete 返回 200 且不重复发放",
              res["status"] == 200 and res["body"].get("already_fulfilled") is True)

        print("\n【八】真实 default_deliver 走一遍（不指定输入 → 交付调用凭据）")
        state_c = os.path.join(tmp, "state_c")
        svc_c, _ = build_service(state_c, priv, pub, resolver=resolver)
        rc = svc_c.probe({})
        oc = rc["body"]["out_trade_no"]
        tc = "T2026092600000011"
        proof_map[tc] = {"out_trade_no": oc, "amount": rc["body"]["amount"],
                         "resource_id": svc_c.resource_id}
        resc = svc_c.complete(make_proof(tc), {})
        check("默认交付器可用", resc["status"] == 200
              and isinstance(resc["body"].get("content"), dict),
              "status=%s" % resc["status"])

        print("\n【九】订单统计")
        print("  %s" % json.dumps(svc.store.stats(), ensure_ascii=False))

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    total = len(RESULTS)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print("\n" + "=" * 62)
    print("自测结果：%d/%d 通过" % (passed, total))
    if passed != total:
        print("\n未通过项：")
        for name, ok, detail in RESULTS:
            if not ok:
                print("  ❌ %s   %s" % (name, detail))
    print("=" * 62)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
