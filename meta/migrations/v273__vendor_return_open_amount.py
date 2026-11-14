# -*- coding: utf-8 -*-
"""[v273 2026-11-14] 退货贷项余量视图（W11-2 / R-VI-51）

依据:
  docs/specs/spec-vendor-invoice-object-model-2026-11-11.md
  §25.4 R-VI-51；§25.6 视图字段

范围:
  退货域无独立 vendor_return 表：退货 = 退货收货单（receipts.document_type_id →
  type_definitions.scope_bo='receipt' AND document_category='return'）。
  收货行不存价（D-RC-9），故 amount_returned = |qty_received| × PO 行单价。

  amount_credited 只统计「已过账」贷项行（status='posted'）：
  贷项被红冲后原单置 reversed，自动退出统计；红字借项单 category=debit_memo 被排除。

回滚:
  DROP VIEW（不动表与数据）。
"""

import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v273__vendor_return_open_amount'

VIEW_NAME = 'v_vendor_return_open_amount'

RETURN_OPEN_DDL = """
CREATE VIEW IF NOT EXISTS v_vendor_return_open_amount AS
SELECT
    rl.id AS return_line_id,
    ABS(COALESCE(rl.qty_received, 0)) AS qty_returned,
    ROUND(ABS(COALESCE(rl.qty_received, 0)) * COALESCE(pol.unit_price, 0), 4)
        AS amount_returned,
    COALESCE(credit.amount_credited, 0) AS amount_credited,
    ROUND(ABS(COALESCE(rl.qty_received, 0)) * COALESCE(pol.unit_price, 0), 4)
        - COALESCE(credit.amount_credited, 0) AS amount_open
FROM receipt_lines rl
JOIN receipts r ON r.id = rl.receipt_id
JOIN type_definitions td ON td.id = r.document_type_id
LEFT JOIN purchase_order_lines pol ON pol.id = rl.order_line_id
LEFT JOIN (
    SELECT vil.return_line_id AS return_line_id,
           SUM(ABS(COALESCE(vil.net_amount, 0))) AS amount_credited
    FROM vendor_invoice_lines vil
    JOIN vendor_invoices vi ON vi.id = vil.invoice_id
    WHERE vil.return_line_id IS NOT NULL
      AND vi.document_category = 'credit_memo'
      AND vi.status = 'posted'
    GROUP BY vil.return_line_id
) credit ON credit.return_line_id = rl.id
WHERE td.scope_bo = 'receipt'
  AND td.document_category = 'return'
  AND r.status = 'posted'
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
    print('[v273] 开始: 退货贷项余量视图')
    conn = _connect(db_path)
    try:
        conn.execute(RETURN_OPEN_DDL)
        print('[v273] CREATE VIEW: %s' % VIEW_NAME)
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    db_path = Path(db_path)
    conn = _connect(db_path)
    try:
        ok = _view_exists(conn, VIEW_NAME)
    finally:
        conn.close()
    if not ok:
        print('[v273] FAIL: 缺少视图 %s' % VIEW_NAME)
        return False
    print('[v273] PASS: %s 齐备' % VIEW_NAME)
    return True


def rollback(db_path: Path) -> bool:
    db_path = Path(db_path)
    print('[v273] 开始回滚: 删除视图')
    conn = _connect(db_path)
    try:
        conn.execute('DROP VIEW IF EXISTS %s' % VIEW_NAME)
        print('[v273] DROP VIEW: %s' % VIEW_NAME)
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