# -*- coding: utf-8 -*-
"""skillpay 包 —— 支付宝 AI 按量付费（402 协议）接入层。

四步编排（与 SkillHub 付费改造要求一致）：
  probe    → 请求资源；未付款时服务端返回 HTTP 402 + `Payment-Needed` 账单头
  pay      → 把账单交给支付宝官方支付能力拉起收银台（Agent 只编排，不代付）
  complete → 付款后携带 `Payment-Proof` 重试；服务端调用 payment.verify 验付并（幂等）履约
  ack      → 交付后调用 fulfillment.confirm 确认履约，失败可重试且保持幂等

完整规范与五项必做控制见 `references/skillpay.md`。
"""
__all__ = ["config", "store", "bill", "proof", "gateway", "service"]
