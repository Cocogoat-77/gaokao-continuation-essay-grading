# -*- coding: utf-8 -*-
"""skillpay.bill —— 402 账单下发（AI 按量付费第一项必做控制）。

流程：无有效 `Payment-Proof` → 返回 HTTP 402 + `Payment-Needed` 响应头，
头里是 **Base64URL 编码**的账单 JSON，结构固定为 `protocol` + `method` 两段。

`Payment-Needed.protocol` 必备字段：
  out_trade_no / amount / currency=CNY / resource_id / pay_before /
  seller_signature / seller_sign_type=RSA2 / seller_unique_id
`Payment-Needed.method` 必备字段：
  seller_name / seller_id / seller_app_id / goods_name /
  seller_unique_id_key=seller_id / service_id

商家签名（seller_signature）在**本地**完成，不请求支付宝服务端：
按 key 字典序拼接 `amount / currency / goods_name / out_trade_no / pay_before /
resource_id / seller_id / service_id`，用商家私钥做 RSA2（SHA256 + PKCS#1 v1.5），
再把签名结果做标准 Base64。
"""
import base64
import json
import re
import uuid
from datetime import datetime, timedelta, timezone

SIGN_FIELDS = ("amount", "currency", "goods_name", "out_trade_no",
               "pay_before", "resource_id", "seller_id", "service_id")

# 参与签名但**不放进** Payment-Needed.protocol 的字段
_EXTRA_SIGN_FIELDS = ("seller_id", "service_id")


# ---------------- Base64URL ----------------

def base64url_encode(data):
    """Base64URL 编码，去掉尾部 '=' 填充。"""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def base64url_decode(data):
    """Base64URL 解码，自动补回 '=' 填充。"""
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    data = data.strip()
    pad = 4 - len(data) % 4
    if pad != 4:
        data += "=" * pad
    return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8")


# ---------------- RSA2 签名 ----------------
# 优先用 pycryptodome（支付宝官方示例用的就是它），其次 cryptography。
# 两者都没有时给出明确安装提示，不做静默降级——签名错误会让整条链路失效。

CRYPTO_HINT = ("需要 RSA 签名库。请安装其一：\n"
               "    pip install pycryptodome\n"
               "    pip install cryptography")


def _read_key_bytes(raw):
    """把「裸 base64 / PEM 字符串 / PEM 文件路径」统一成 bytes。"""
    raw = (raw or "").strip()
    if not raw:
        return None
    if raw.startswith("file:"):
        with open(raw[5:], "rb") as f:
            return f.read()
    if "BEGIN" in raw:
        return raw.encode("utf-8")
    return base64.b64decode(re.sub(r"\s+", "", raw), validate=True)


def _import_key(raw, public=False):
    """返回 (backend, key_object)。backend ∈ {'pycryptodome', 'cryptography'}。"""
    data = _read_key_bytes(raw)
    if data is None:
        return None, None

    try:
        from Crypto.PublicKey import RSA
        return "pycryptodome", RSA.import_key(data)
    except ImportError:
        pass
    except Exception:
        # 已经装了就不要再退到另一个后端，否则错误会被掩盖
        raise

    try:
        from cryptography.hazmat.primitives import serialization
        if public:
            return "cryptography", serialization.load_pem_public_key(data)
        if data.startswith(b"-----"):
            return "cryptography", serialization.load_pem_private_key(data, password=None)
        return "cryptography", serialization.load_der_private_key(data, password=None)
    except ImportError:
        raise RuntimeError(CRYPTO_HINT)


def _sign(backend, key, message):
    if backend == "pycryptodome":
        from Crypto.Hash import SHA256
        from Crypto.Signature import pkcs1_15
        return pkcs1_15.new(key).sign(SHA256.new(message))
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    return key.sign(message, padding.PKCS1v15(), hashes.SHA256())


def _verify(backend, key, message, signature):
    try:
        if backend == "pycryptodome":
            from Crypto.Hash import SHA256
            from Crypto.Signature import pkcs1_15
            pkcs1_15.new(key).verify(SHA256.new(message), signature)
            return True
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        key.verify(signature, message, padding.PKCS1v15(), hashes.SHA256())
        return True
    except Exception:
        return False


def _load_private_key(raw):
    backend, key = _import_key(raw, public=False)
    if key is None:
        raise RuntimeError("未配置商户应用私钥（SKILLPAY_MERCHANT_PRIVATE_KEY）")
    return backend, key


def _load_public_key(raw):
    backend, key = _import_key(raw, public=True)
    if key is None:
        raise RuntimeError("未配置支付宝公钥（SKILLPAY_ALIPAY_PUBLIC_KEY）")
    return backend, key


def build_sign_string(params):
    """按 key 字典序拼 `k=v&k=v`，跳过 None 与空串。"""
    parts = []
    for key in sorted(params.keys()):
        value = params.get(key)
        if value is None or value == "":
            continue
        parts.append("%s=%s" % (key, value))
    return "&".join(parts)


def seller_signature(fields, private_key_raw):
    """生成商家签名（标准 Base64，不是 URL-safe）。"""
    backend, key = _load_private_key(private_key_raw)
    sign_string = build_sign_string({k: fields.get(k) for k in SIGN_FIELDS})
    return base64.b64encode(_sign(backend, key, sign_string.encode("utf-8"))).decode("utf-8")


def verify_signature(fields, signature_b64, public_key_raw):
    """校验签名（自测与排查用）。"""
    backend, key = _load_public_key(public_key_raw)
    sign_string = build_sign_string({k: fields.get(k) for k in SIGN_FIELDS})
    try:
        sig = base64.b64decode(signature_b64)
    except Exception:
        return False
    return _verify(backend, key, sign_string.encode("utf-8"), sig)


# ---------------- 账单组装 ----------------

def new_out_trade_no():
    return "ORDER_%d_%s" % (int(datetime.now().timestamp() * 1000),
                            uuid.uuid4().hex[:12])


def pay_before_iso(minutes):
    """账单有效期截止时间，带时区的 ISO 8601。"""
    return (datetime.now(timezone.utc).astimezone()
            + timedelta(minutes=minutes)).isoformat(timespec="seconds")


def build_payment_needed(cfg, out_trade_no, amount, resource_id, pay_before,
                         goods_name=None, quantity=1):
    """组装 Payment-Needed 头内容，返回 (header_value, order_dict, payload)。

    `goods_name` 可传入本次的实际商品描述（按篇计价时带上「N 篇 × 单价」的明细），
    它参与签名，所以必须在签名之前确定。
    """
    goods_name = cfg.get("goods_name", "") if goods_name is None else goods_name
    seller_id = cfg.get("seller_id", "")
    service_id = cfg.get("service_id", "")

    signature = seller_signature({
        "amount": amount,
        "currency": "CNY",
        "goods_name": goods_name,
        "out_trade_no": out_trade_no,
        "pay_before": pay_before,
        "resource_id": resource_id,
        "seller_id": seller_id,
        "service_id": service_id,
    }, cfg.get("merchant_private_key", ""))

    payload = {
        "protocol": {
            "out_trade_no": out_trade_no,
            "amount": amount,
            "currency": "CNY",
            "resource_id": resource_id,
            "pay_before": pay_before,
            "seller_signature": signature,
            "seller_sign_type": "RSA2",
            "seller_unique_id": seller_id,
        },
        "method": {
            "seller_name": cfg.get("seller_name", ""),
            "seller_id": seller_id,
            "seller_app_id": cfg.get("app_id", ""),
            "goods_name": goods_name,
            "seller_unique_id_key": "seller_id",
            "service_id": service_id,
        },
    }

    order = {
        "out_trade_no": out_trade_no,
        "resource_id": resource_id,
        "quantity": int(quantity),
        "amount": amount,
        "currency": "CNY",
        "goods_name": goods_name,
        "pay_before": pay_before,
        "order_status": "PENDING_PAYMENT",
        "fulfill_status": "UNFULFILLED",
    }
    header = base64url_encode(json.dumps(payload, ensure_ascii=False))
    return header, order, payload


def decode_payment_needed(header_value):
    """把 Payment-Needed 头解回来（自测/排查用）。"""
    return json.loads(base64url_decode(header_value))


def sign_fields_from_payment_needed(decoded):
    """从解开的 Payment-Needed 里还原**参与签名的 8 个字段**。

    签名字段横跨 protocol 与 method 两段（`seller_id` / `service_id` 只在 method 里），
    所以校验签名不能只拿 protocol 段 —— 这个函数负责合并，供排查与第三方校验使用。
    """
    proto = decoded.get("protocol") or {}
    method = decoded.get("method") or {}
    return {
        "amount": proto.get("amount"),
        "currency": proto.get("currency"),
        "goods_name": method.get("goods_name") or proto.get("goods_name"),
        "out_trade_no": proto.get("out_trade_no"),
        "pay_before": proto.get("pay_before"),
        "resource_id": proto.get("resource_id"),
        "seller_id": method.get("seller_id") or proto.get("seller_unique_id"),
        "service_id": method.get("service_id"),
    }


def build_payment_validation(trade_no, out_trade_no, resource_id):
    """交付成功时回给调用方的 `Payment-Validation` 头。"""
    return base64url_encode(json.dumps({
        "trade_no": trade_no,
        "out_trade_no": out_trade_no,
        "validated": True,
        "resource_id": resource_id,
    }, ensure_ascii=False))
