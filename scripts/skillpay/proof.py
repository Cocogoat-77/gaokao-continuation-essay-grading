# -*- coding: utf-8 -*-
"""skillpay.proof —— 解析 Payment-Proof（携带凭证重试的入口）。

用户付款成功后，Agent/SkillHub 在**重试原请求**时通过 `Payment-Proof` 请求头
回传 Base64URL 编码的凭证。本模块把它解出来，取出验付所需的三个值：

| 取值 | 来源 | 必需 |
|---|---|---|
| payment_proof | `protocol.payment_proof` | 是 |
| trade_no      | `protocol.trade_no` | 是 |
| client_session| `method.client_session` | 否 |

任一必需字段缺失／解码失败 → 直接回退到 402（让 Agent 重新支付），
**不得**用「结果不明」为由要求用户重复付款。
"""
from .bill import base64url_decode


class ProofError(ValueError):
    """凭证解析失败——调用方应据此重新下发 402。"""


def parse_payment_proof(header_value):
    """解析 Payment-Proof 头，返回 dict。

    失败抛 ProofError；成功返回：
      {'payment_proof': str, 'trade_no': str, 'client_session': str|None,
       'raw': dict}
    """
    if not header_value or not str(header_value).strip():
        raise ProofError("Payment-Proof 为空")

    try:
        decoded = base64url_decode(header_value)
        data = __import__("json").loads(decoded)
    except Exception as exc:
        raise ProofError("Payment-Proof 解码失败：%s" % exc)

    if not isinstance(data, dict):
        raise ProofError("Payment-Proof 结构不是 JSON 对象")

    protocol = data.get("protocol") or {}
    method = data.get("method") or {}

    payment_proof = (protocol.get("payment_proof") or "").strip()
    trade_no = (protocol.get("trade_no") or "").strip()
    client_session = (method.get("client_session") or "").strip() or None

    if not payment_proof:
        raise ProofError("Payment-Proof 缺少 protocol.payment_proof")
    if not trade_no:
        raise ProofError("Payment-Proof 缺少 protocol.trade_no")

    return {
        "payment_proof": payment_proof,
        "trade_no": trade_no,
        "client_session": client_session,
        "raw": data,
    }
