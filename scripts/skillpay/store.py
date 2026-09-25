# -*- coding: utf-8 -*-
"""skillpay.store —— 订单持久化与幂等（AI 按量付费的第五项必做控制）。

官方契约对订单存储的要求（references/skillpay.md 有完整摘录）：
  - 返回 `Payment-Needed` 前必须持久化 out_trade_no / resource_id / 金额 / 状态 / 过期时间。
  - 付款后携带 `Payment-Proof` 回来时，必须能映射回本地订单。
  - 同一订单重复携带 `Payment-Proof` 时**不得重复发放资源**。
  - 必须提供 create_pending / find_by_out_trade_no / prepare_fulfillment / mark_fulfilled。

本模块用 SQLite 实现，靠两件事保证幂等：
  1. `out_trade_no` 主键 + `trade_no` 唯一索引 —— 同一个平台订单号不可能履约两次；
  2. `prepare_fulfillment` 在 `BEGIN IMMEDIATE` 事务内**原子地**「重读订单 → 校验 → 生成资源 → 落库」，
     资源只可能被生成一次；已经生成过就直接返回历史结果。

状态机（与官方示例一致）：
  order_status   : PENDING_PAYMENT → PAID
  fulfill_status : UNFULFILLED → PENDING_CONFIRM → FULFILLED
"""
import json
import os
import sqlite3
import time
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
  out_trade_no   TEXT PRIMARY KEY,
  resource_id    TEXT NOT NULL,
  quantity       INTEGER NOT NULL DEFAULT 1,
  amount         TEXT NOT NULL,
  currency       TEXT NOT NULL DEFAULT 'CNY',
  goods_name     TEXT NOT NULL DEFAULT '',
  pay_before     TEXT NOT NULL,
  order_status   TEXT NOT NULL,
  fulfill_status TEXT NOT NULL,
  trade_no       TEXT,
  service_result TEXT,
  created_at     TEXT NOT NULL,
  updated_at     TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_trade_no
  ON orders(trade_no) WHERE trade_no IS NOT NULL AND trade_no <> '';
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);
"""

ORDER_STATUS = ("PENDING_PAYMENT", "PAID")
FULFILL_STATUS = ("UNFULFILLED", "PENDING_CONFIRM", "FULFILLED")
IN_PROGRESS = ("PENDING_CONFIRM", "FULFILLED")


def _now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class OrderStore:
    def __init__(self, state_dir):
        self.state_dir = state_dir
        os.makedirs(state_dir, exist_ok=True)
        self.db_path = os.path.join(state_dir, "orders.db")
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self):
        c = sqlite3.connect(self.db_path, timeout=15, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        return c

    # ---------- 1) 建单：返回 Payment-Needed 之前必须调用 ----------
    def create_pending(self, order):
        """持久化一笔待支付订单。out_trade_no 冲突时保持原记录（幂等）。"""
        now = _now_iso()
        with self._conn() as c:
            c.execute(
                """INSERT OR IGNORE INTO orders
                   (out_trade_no, resource_id, quantity, amount, currency,
                    goods_name, pay_before, order_status, fulfill_status,
                    created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (order["out_trade_no"], order["resource_id"],
                 int(order.get("quantity", 1)), order["amount"],
                 order.get("currency", "CNY"), order.get("goods_name", ""),
                 order["pay_before"], order.get("order_status", "PENDING_PAYMENT"),
                 order.get("fulfill_status", "UNFULFILLED"), now, now))
            row = c.execute("SELECT * FROM orders WHERE out_trade_no=?",
                            (order["out_trade_no"],)).fetchone()
        return dict(row)

    # ---------- 2) 按商户订单号回查 ----------
    def find_by_out_trade_no(self, out_trade_no):
        if not out_trade_no:
            return None
        with self._conn() as c:
            row = c.execute("SELECT * FROM orders WHERE out_trade_no=?",
                            (out_trade_no,)).fetchone()
        return dict(row) if row else None

    def find_by_trade_no(self, trade_no):
        if not trade_no:
            return None
        with self._conn() as c:
            row = c.execute("SELECT * FROM orders WHERE trade_no=?",
                            (trade_no,)).fetchone()
        return dict(row) if row else None

    # ---------- 3) 幂等履约：资源只生成一次 ----------
    def prepare_fulfillment(self, out_trade_no, trade_no, expected_amount,
                            expected_resource_id, create_resource,
                            expected_quantity=None):
        """原子地校验订单并**只生成一次**资源。

        返回 {'state': 'PENDING_CONFIRM'|'FULFILLED', 'service_result': <str>}；
        校验不通过返回 None（调用方应改为重新下发 402）。
        """
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")           # 写锁，防并发重复履约
            row = c.execute("SELECT * FROM orders WHERE out_trade_no=?",
                            (out_trade_no,)).fetchone()
            if row is None:
                c.execute("ROLLBACK")
                return None
            order = dict(row)

            # 金额 / 篇数 / 资源 / 状态 / 时效 校验
            if not _amounts_equal(order["amount"], expected_amount):
                c.execute("ROLLBACK")
                return None
            if expected_quantity is not None and int(order["quantity"]) != int(expected_quantity):
                c.execute("ROLLBACK")
                return None
            if order["resource_id"] != expected_resource_id:
                c.execute("ROLLBACK")
                return None
            if order["currency"] != "CNY":
                c.execute("ROLLBACK")
                return None
            if order["order_status"] not in ORDER_STATUS:
                c.execute("ROLLBACK")
                return None
            if order["fulfill_status"] not in FULFILL_STATUS:
                c.execute("ROLLBACK")
                return None
            # 已经进入履约流程的订单，不再看 pay_before（官方明确要求：
            # 不得因为支付截止时间已过就重复生成资源）
            if order["fulfill_status"] == "UNFULFILLED" and not _is_future(order["pay_before"]):
                c.execute("ROLLBACK")
                return None

            # 已履约过：直接返回历史结果，不重新生成
            if order["fulfill_status"] in IN_PROGRESS and order["service_result"]:
                c.execute("ROLLBACK")
                return {"state": order["fulfill_status"],
                        "service_result": order["service_result"],
                        "order": order}

            # 首次履约：生成资源 → 落库（同一事务内，保证只生成一次）
            result = create_resource()
            if isinstance(result, (dict, list)):
                result = json.dumps(result, ensure_ascii=False)
            result = str(result)
            now = _now_iso()
            c.execute(
                """UPDATE orders
                      SET service_result=?, fulfill_status='PENDING_CONFIRM',
                          trade_no=?, order_status='PAID', updated_at=?
                    WHERE out_trade_no=? AND fulfill_status='UNFULFILLED'""",
                (result, trade_no, now, out_trade_no))
            if c.total_changes == 0:     # 被并发抢先，视为已在处理
                c.execute("ROLLBACK")
                again = self.find_by_out_trade_no(out_trade_no)
                if again and again["service_result"]:
                    return {"state": again["fulfill_status"],
                            "service_result": again["service_result"], "order": again}
                return None
            c.execute("COMMIT")
            return {"state": "PENDING_CONFIRM", "service_result": result,
                    "order": self.find_by_out_trade_no(out_trade_no)}
        except Exception:
            try:
                c.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            c.close()

    # ---------- 4) 履约确认成功后落最终状态 ----------
    def mark_fulfilled(self, out_trade_no, trade_no=None):
        with self._conn() as c:
            c.execute(
                """UPDATE orders SET fulfill_status='FULFILLED',
                          order_status='PAID',
                          trade_no=COALESCE(?, trade_no), updated_at=?
                    WHERE out_trade_no=?""",
                (trade_no, _now_iso(), out_trade_no))

    # ---------- 辅助 / 审计 ----------
    def stats(self):
        with self._conn() as c:
            rows = c.execute(
                "SELECT fulfill_status, COUNT(*) n FROM orders GROUP BY fulfill_status"
            ).fetchall()
            total = c.execute("SELECT COUNT(*) n FROM orders").fetchone()["n"]
        return {"total": total, "by_fulfill_status": {r["fulfill_status"]: r["n"] for r in rows}}


def normalize_amount(value):
    """金额一律按 2 位小数定点处理，禁止二进制浮点误差。"""
    text = str(value if value is not None else "").strip()
    if not text:
        return None
    try:
        from decimal import Decimal
        d = Decimal(text)
    except Exception:
        return None
    if d < 0:
        return None
    return "%.2f" % d


def _amounts_equal(left, right):
    a, b = normalize_amount(left), normalize_amount(right)
    return a is not None and b is not None and a == b


def _is_future(value):
    try:
        return datetime.fromisoformat(value).timestamp() > time.time()
    except (TypeError, ValueError):
        return False
