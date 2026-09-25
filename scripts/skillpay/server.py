# -*- coding: utf-8 -*-
"""skillpay.server —— 本地 HTTP 服务，把付费资源暴露成真正的 402 端点。

协议落在 HTTP 层才完整：未付款时响应 **状态码 402** + `Payment-Needed` 响应头；
付款后携带 `Payment-Proof` 重试同一路径，成功时返回 200 + `Payment-Validation`。

启动：
    python scripts/skillpay/server.py --port 8787
路由：
    POST /v1/grade      付费资源（批改报告生成）—— probe / complete 都打这里
    GET  /v1/pay-info   价格信息（不下单）
    POST /v1/ack        重试履约确认（body: {"trade_no": "..."}）
    GET  /healthz       健康检查
"""
import argparse
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skillpay import config as config_mod          # noqa: E402
from skillpay.service import PayService            # noqa: E402

RESOURCE_PATH = "/v1/grade"
SERVICE = None


class Handler(BaseHTTPRequestHandler):
    server_version = "skillpay/1.0"

    # ---- 工具 ----
    def _send(self, result):
        body = json.dumps(result["body"], ensure_ascii=False).encode("utf-8")
        self.send_response(result["status"])
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (result.get("headers") or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def log_message(self, fmt, *args):        # 静音默认访问日志
        pass

    # ---- 路由 ----
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/healthz":
            return self._send({"status": 200, "headers": {},
                               "body": {"ok": True, "mode": SERVICE.cfg["mode"]}})
        if path == "/v1/pay-info":
            return self._send({"status": 200, "headers": {},
                               "body": SERVICE.pay_info()})
        return self._send({"status": 404, "headers": {},
                           "body": {"code": "NOT_FOUND", "path": path}})

    def do_POST(self):
        path = self.path.split("?")[0]
        body = self._read_json()

        if path == RESOURCE_PATH:
            # ★ 无 Payment-Proof → probe（402 账单下发）
            proof_header = self.headers.get("Payment-Proof") or body.get("payment_proof")
            if not proof_header:
                return self._send(SERVICE.probe(body.get("payload")))
            # ★ 携带 Payment-Proof 重试 → complete（验付 + 履约）
            return self._send(SERVICE.complete(proof_header, body.get("payload")))

        if path == "/v1/ack":
            return self._send(SERVICE.ack(body.get("trade_no")))

        return self._send({"status": 404, "headers": {},
                           "body": {"code": "NOT_FOUND", "path": path}})


def main():
    global SERVICE
    ap = argparse.ArgumentParser(description="skillpay 本地付费资源服务")
    ap.add_argument("--host", default="127.0.0.1", help="默认只监听本机回环地址")
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()

    cfg = config_mod.load()
    cfg.setdefault("resource_id", config_mod.RESOURCE_ID)
    print("付费服务配置：")
    for k, v in config_mod.describe(cfg).items():
        print("  %-22s %s" % (k, v))
    if not cfg.get("merchant_private_key"):
        print("\n[警告] 未配置商户应用私钥，probe 会返回 500（无法签发账单）。")
        print("       自测请用：python scripts/skillpay/selftest.py")

    SERVICE = PayService(cfg)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    addr = "http://%s:%d" % (args.host, args.port)
    print("\n付费资源端点：POST %s%s" % (addr, RESOURCE_PATH))
    print("价格信息：     GET  %s/v1/pay-info" % addr)
    print("履约确认重试： POST %s/v1/ack" % addr)
    print("\n按 Ctrl+C 停止。")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
