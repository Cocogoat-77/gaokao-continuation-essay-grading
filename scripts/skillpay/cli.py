# -*- coding: utf-8 -*-
"""skillpay.cli —— 命令行入口，把四步编排暴露成四个子命令。

    # 1) probe：请求资源。未付款 → 打印 402 账单并退出码 402
    python scripts/skillpay/cli.py probe --jsondir ./final --outdir ./out

    # 2) pay：把上一步的 Payment-Needed 交给支付宝官方支付能力（由 Agent 编排收银）
    python scripts/skillpay/cli.py pay-info

    # 3) complete：付款后用同一请求 + Payment-Proof 重试
    python scripts/skillpay/cli.py complete --payment-proof "<Base64URL>" \
        --jsondir ./final --outdir ./out

    # 4) ack：资源已生成但履约确认失败时，单独重试确认
    python scripts/skillpay/cli.py ack --trade-no "<trade_no>"

    python scripts/skillpay/cli.py status      # 配置与订单统计
    python scripts/skillpay/cli.py selftest    # 离线跑通完整链路
退出码：200/402 与 HTTP 状态一致（402 = 需要支付），0 = 成功。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skillpay import config as config_mod      # noqa: E402
from skillpay.service import PayService        # noqa: E402


def _payload(args):
    return {
        "json": args.json,
        "jsondir": args.jsondir,
        "outdir": args.outdir,
        "theme": args.theme,
        "marks": args.marks,
    }


def _emit(result, quiet=False):
    """把服务返回打印成 JSON；结构化信息走 stdout，提示走 stderr。"""
    print(json.dumps(result, ensure_ascii=False, indent=2))
    status = result["status"]
    if status == 402:
        sys.stderr.write(
            "\n[probe] 需要支付。请把上面 headers.Payment-Needed 交给支付宝官方支付能力"
            "拉起收银台；付款后用同一请求 + Payment-Proof 重试（complete）。\n"
            "       账单号 out_trade_no = %s，金额 %s 元，请在 pay_before 之前完成支付。\n"
            % (result["body"].get("out_trade_no"), result["body"].get("amount")))
    return 200 if status == 200 else status


def main():
    ap = argparse.ArgumentParser(prog="skillpay", description="支付宝 AI 按量付费四步编排")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_payload_args(p):
        p.add_argument("--json", help="要交付的批改结果 JSON")
        p.add_argument("--jsondir", help="批量：批改结果 JSON 目录")
        p.add_argument("--outdir", default="./out", help="交付物输出目录")
        p.add_argument("--theme", default="default", help="报告皮肤：default / apple")
        p.add_argument("--marks", default="theme", help="修订标记口径：theme / strict")

    p_probe = sub.add_parser("probe", help="第 1 步：请求资源（未付款返回 402）")
    add_payload_args(p_probe)

    p_info = sub.add_parser("pay-info", help="第 2 步：查看商品名与价格（不下单）")

    p_complete = sub.add_parser("complete", help="第 3 步：携带 Payment-Proof 重试（验付+履约）")
    p_complete.add_argument("--payment-proof", required=True, help="Payment-Proof 头原值")
    add_payload_args(p_complete)

    p_ack = sub.add_parser("ack", help="第 4 步：重试履约确认")
    p_ack.add_argument("--trade-no", required=True)

    sub.add_parser("status", help="查看配置与订单统计")
    sub.add_parser("selftest", help="离线跑通完整链路（生成密钥 + mock 网关）")

    args = ap.parse_args()

    if args.cmd == "status":
        cfg = config_mod.load()
        print("配置：")
        for k, v in config_mod.describe(cfg).items():
            print("  %-22s %s" % (k, v))
        svc = PayService(cfg)
        print("\n订单统计：")
        print("  %s" % json.dumps(svc.store.stats(), ensure_ascii=False))
        return 0

    if args.cmd == "selftest":
        here = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, here)
        import selftest
        return selftest.main()

    svc = PayService(config_mod.load())

    if args.cmd == "pay-info":
        print(json.dumps(svc.pay_info(), ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "probe":
        return _emit(svc.probe(_payload(args)))

    if args.cmd == "complete":
        return _emit(svc.complete(args.payment_proof, _payload(args)))

    if args.cmd == "ack":
        return _emit(svc.ack(args.trade_no))

    return 2


if __name__ == "__main__":
    sys.exit(main())
