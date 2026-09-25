# -*- coding: utf-8 -*-
"""skillpay.config —— 支付宝 AI 按量付费的运行配置。

配置来源（后者覆盖前者）：
  1. 代码里的沙箱默认值
  2. 环境变量 SKILLPAY_*
  3. 本地配置文件 <state_dir>/../skillpay.local.json（**不入库**，见 .gitignore）

安全红线（支付宝官方校验清单要求）：
  - 应用私钥只允许来自环境变量或本地非入库配置，**禁止写进仓库、日志或包内**。
  - 生产环境必须把网关切到 https://openapi.alipay.com/gateway.do，
    并把 service_id 换成服务市场返回的真实值（不再用 api_mock_service_id）。
"""
import json
import os

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SANDBOX_GATEWAY = "https://openapi-sandbox.dl.alipaydev.com/gateway.do"
PRODUCTION_GATEWAY = "https://openapi.alipay.com/gateway.do"
SANDBOX_SERVICE_ID = "api_mock_service_id"

# 计费口径：**按报告篇数**计价。
#   账单金额 = unit_price × 本次请求的篇数
#   例：一篇 ¥0.01 → 0.01；一个班 40 篇 → 0.40
RESOURCE_ID = "grade-report"
GOODS_NAME = "高中读后续写自动批改（按篇计费）"
DEFAULT_UNIT_PRICE = "0.01"    # 元/篇；必须与 SkillHub 发布表单里的定价一致
DEFAULT_QUANTITY_CAP = 2500    # 单次调用最多交付多少篇（防误传目录导致天价账单）
                               # 2500 篇 × 0.01 元 = 上限账单 25.00 元
DEFAULT_PAY_WINDOW_MIN = 30    # 账单有效期（分钟）

_FIELDS = (
    "mode", "gateway", "app_id", "seller_id", "seller_name", "service_id",
    "unit_price", "amount", "quantity_cap", "resource_id", "goods_name",
    "merchant_private_key", "alipay_public_key", "state_dir", "pay_window_min",
    "gateway_impl",
)


def _state_dir_default():
    return os.path.join(SKILL_DIR, "state")


def load(local_file=None):
    """读取配置。返回 dict；敏感字段只在内存里，不落日志。"""
    cfg = {
        "mode": "sandbox",
        "gateway": SANDBOX_GATEWAY,
        "app_id": "",
        "seller_id": "",
        "seller_name": "读后续写批改服务",
        "service_id": SANDBOX_SERVICE_ID,
        # 按篇计价：不填 amount 时按 unit_price × 篇数算账
        "unit_price": DEFAULT_UNIT_PRICE,
        "amount": "",                   # 留空＝按篇计价；填了则固定价（一次性打包价）
        "quantity_cap": DEFAULT_QUANTITY_CAP,
        "resource_id": RESOURCE_ID,
        "goods_name": GOODS_NAME,
        "merchant_private_key": "",     # 裸 PKCS#1/PKCS#8 base64，或 PEM
        "alipay_public_key": "",        # 验签用，可选
        "state_dir": _state_dir_default(),
        "pay_window_min": DEFAULT_PAY_WINDOW_MIN,
        "gateway_impl": "alipay",       # alipay | mock（mock 仅供自测）
    }

    # 2) 本地配置文件
    path = local_file or os.path.join(SKILL_DIR, "skillpay.local.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg.update({k: v for k, v in json.load(f).items() if k in _FIELDS})
        except Exception:
            pass

    # 3) 环境变量
    for k in _FIELDS:
        env = os.environ.get("SKILLPAY_" + k.upper())
        if env not in (None, ""):
            cfg[k] = int(env) if k in ("pay_window_min", "quantity_cap") else env

    # 生产/沙箱派生值
    if cfg["mode"] == "production":
        if cfg["gateway"] == SANDBOX_GATEWAY:
            cfg["gateway"] = PRODUCTION_GATEWAY
        if cfg["service_id"] == SANDBOX_SERVICE_ID:
            raise RuntimeError(
                "生产模式不能使用沙箱 service_id。请在 skillpay.local.json 或 "
                "SKILLPAY_SERVICE_ID 中填入服务市场返回的真实 service_id。")
    else:
        cfg["mode"] = "sandbox"
        cfg["gateway"] = SANDBOX_GATEWAY
        cfg["service_id"] = SANDBOX_SERVICE_ID

    cfg["state_dir"] = os.path.abspath(cfg["state_dir"])
    return cfg


def is_sandbox(cfg):
    return cfg["mode"] == "sandbox" and cfg["service_id"] == SANDBOX_SERVICE_ID \
        and cfg["gateway"] == SANDBOX_GATEWAY


class QuantityError(ValueError):
    """篇数不合法（为 0，或超过单次调用上限）。"""


def amount_for(cfg, quantity):
    """按篇计价：账单金额 = 单价 × 篇数。

    返回 `(amount_str, quantity)`；`amount_str` 是 2 位小数定点字符串。
    若配置里显式填了 `amount`，则按固定价结算（打包价场景），篇数仍如实记录。
    用 Decimal 计算，杜绝二进制浮点误差。
    """
    from decimal import Decimal
    qty = int(quantity)
    if qty < 1:
        raise QuantityError("篇数必须 ≥ 1，得到 %s" % quantity)
    cap = int(cfg.get("quantity_cap") or 0)
    if cap and qty > cap:
        raise QuantityError(
            "单次调用最多 %d 篇，本次请求 %d 篇。请分批调用，"
            "或调整配置里的 quantity_cap。" % (cap, qty))

    if cfg.get("amount"):
        total = Decimal(str(cfg["amount"]))
    else:
        total = Decimal(str(cfg["unit_price"])) * qty
    return str(total.quantize(Decimal("0.01"))), qty


def describe(cfg):
    """给人看的配置摘要——**不含任何密钥内容**，只报告"是否已配置"。"""
    cap = cfg.get("quantity_cap") or 0
    return {
        "mode": cfg["mode"],
        "gateway": cfg["gateway"],
        "service_id": cfg["service_id"],
        "app_id": cfg["app_id"] or "(未配置)",
        "seller_id": cfg["seller_id"] or "(未配置)",
        "计费方式": ("固定价 %s 元/次" % cfg["amount"]) if cfg.get("amount")
                    else "按篇计价 %s 元/篇（单次上限 %s 篇）" % (cfg["unit_price"], cap),
        "resource_id": cfg["resource_id"],
        "state_dir": cfg["state_dir"],
        "merchant_private_key": "已配置" if cfg["merchant_private_key"] else "(未配置)",
        "alipay_public_key": "已配置" if cfg["alipay_public_key"] else "(未配置)",
    }
