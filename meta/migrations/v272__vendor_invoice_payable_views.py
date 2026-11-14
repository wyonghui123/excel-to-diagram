# -*- coding: utf-8 -*-
"""[v272 2026-11-14] 采购发票应付敞口视图（W11-1）

依据:
  docs/specs/spec-vendor-invoice-object-model-2026-11-11.md
  §25.6 数据模型 / 视图；§25.4 R-VI-49 / R-VI-50

范围:
  1. v_vendor_payable_open：期次表的第一生产读方（逾期 / 账龄 / 付款波次）。
     只读 open|partial；open_amount = amount − amount_applied（付款域落地前
     amount_applied 恒 0，故 open_amount = amount）。
     aging_bucket：未到期与逾期 1-30 天同归 '0-30'（与 Spec §25.6 四档一致）。
  2. v_vendor_invoice_negative_open：负余量告警投影，把 `max(0)` 静默吞掉
     改为可观测（收货行 / PO 计划行两条分支）。
  3. 期次表金额列本无 CHECK(amount >= 0)（见 v271 DDL），负额期次无需放宽约束。

回滚:
  DROP VIEW 两个视图（不动表与数据）。
"""

import sqlite3
from pathlib import Path

from meta.core.doc_flow_schema import POOL_AP_MATCH, POOL_BILLING

MIGRATION_NAME = 'v272__vendor_invoice_payable_views'

PAYABLE_VIEW = 'v_vendor_payable_open'
NEGATIVE_VIEW = 'v_vendor_invoice_negative_open'

PAYABLE_DDL = """
CREATE VIEW IF NOT EXISTS v_vendor_payable_open AS
SELECT
    vi.supplier_account_id AS supplier_account_id,
    s.invoice_id          AS invoice_id,
    vi.invoice_no         AS invoice_no,
    s.schedule_no         AS schedule_no,
    s.due_date            AS due_date,
    s.amount              AS amount,
    s.amount_applied      AS amount_applied,
    s.amount - COALESCE(s.amount_applied, 0) AS open_amount,
    vi.currency_id        AS currency_id,
    CASE
        WHEN julianday('now') - julianday(s.due_date) <= 30 THEN '0-30'
        WHEN julianday('now') - julianday(s.due_date) <= 60 THEN '31-60'
        WHEN julianday('now') - julianday(s.due_date) <= 90 THEN '61-90'
        ELSE '90+'
    END                   AS aging_bucket
FROM vendor_invoice_schedules s
JOIN vendor_invoices vi ON vi.id = s.invoice_id
WHERE s.status IN ('open', 'partial')
"""

NEGATIVE_DDL = f"""
CREATE VIEW IF NOT EXISTS v_vendor_invoice_negative_open AS
SELECT
    'receipt_line' AS source_bo,
    r.id           AS source_id,
    '{POOL_AP_MATCH}'     AS pool,
    (COALESCE(r.qty_received, 0) - COALESCE(r.qty_rejected, 0))
        - COALESCE(c.consumed_qty, 0) AS open_qty
FROM receipt_lines r
LEFT JOIN v_doc_flow_consumed_qty c
    ON c.source_bo = 'receipt_line'
   AND c.source_id = CAST(r.id AS TEXT)
   AND c.pool = '{POOL_AP_MATCH}'
WHERE (COALESCE(r.qty_received, 0) - COALESCE(r.qty_rejected, 0))
        - COALESCE(c.consumed_qty, 0) < -0.000001
UNION ALL
SELECT
    'purchase_order_schedule' AS source_bo,
    s.id                      AS source_id,
    '{POOL_BILLING}'                 AS pool,
    COALESCE(s.promised_qty, 0) - COALESCE(c.consumed_qty, 0) AS open_qty
FROM purchase_order_schedules s
LEFT JOIN v_doc_flow_consumed_qty c
    ON c.source_bo = 'purchase_order_schedule'
   AND c.source_id = CAST(s.id AS TEXT)
   AND c.pool = '{POOL_BILLING}'
WHERE COALESCE(s.promised_qty, 0) - COALESCE(c.consumed_qty, 0) < -0.000001
"""


def _connect(db_path):
    return sqlite3.connect(str(db_path))


def _view_exists(conn, view):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'view' AND name = ?",
        [view]).fetchone()
    return row is not None


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    db_path = Path(db_path)
    print('[v272] 开始: 应付敞口 / 负余量视图')
    conn = _connect(db_path)
    try:
        conn.execute(PAYABLE_DDL)
        print('[v272] CREATE VIEW: %s' % PAYABLE_VIEW)
        conn.execute(NEGATIVE_DDL)
        print('[v272] CREATE VIEW: %s' % NEGATIVE_VIEW)
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    db_path = Path(db_path)
    problems = []
    conn = _connect(db_path)
    try:
        for view in (PAYABLE_VIEW, NEGATIVE_VIEW):
            if not _view_exists(conn, view):
                problems.append('缺少视图 %s' % view)
    finally:
        conn.close()

    if problems:
        for problem in problems:
            print('[v272] FAIL: %s' % problem)
        return False
    print('[v272] PASS: %s / %s 齐备' % (PAYABLE_VIEW, NEGATIVE_VIEW))
    return True


def rollback(db_path: Path) -> bool:
    db_path = Path(db_path)
    print('[v272] 开始回滚: 删除两个视图')
    conn = _connect(db_path)
    try:
        for view in (PAYABLE_VIEW, NEGATIVE_VIEW):
            conn.execute('DROP VIEW IF EXISTS %s' % view)
            print('[v272] DROP VIEW: %s' % view)
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('meta.db')
    migrate(target)
    verify(target)