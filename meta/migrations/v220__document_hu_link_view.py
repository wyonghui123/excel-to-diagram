# -*- coding: utf-8 -*-
"""v220：单据 ↔ 容器只读视图 document_hu_link_view。

依据: docs/specs/p6-serial-number-model/spec.md §11.16.2
  · 写模型只有 document_hu_links；本迁移只建读模型（SQL VIEW）。
  · 视图与三张单据头 / 行表强耦合；缺任一基表时 [SKIP]，不建空视图。
  · schema_generator 只发 CREATE VIEW IF NOT EXISTS，定义变更不生效；
    本迁移用 DROP + CREATE 保证重建（与 v219 同口径）。
  · [ALLOW_DESTRUCTIVE] 仅 DROP/CREATE 视图，不动表数据。
"""

import sqlite3
from pathlib import Path

VIEW_NAME = 'document_hu_link_view'

REQUIRED_TABLES = (
    'document_hu_links',
    'handling_units',
    'receipts',
    'receipt_lines',
    'shipments',
    'transfer_orders',
    'transfer_order_lines',
)

VIEW_SQL = """SELECT
  l.id AS id,
  l.hu_id AS hu_id,
  h.hu_no AS hu_no,
  h.status AS hu_status,
  h.hu_type AS hu_type,
  l.doc_type AS doc_type,
  l.doc_id AS doc_id,
  COALESCE(r.receipt_no, s.delivery_no, t.transfer_order_no) AS doc_no,
  COALESCE(r.status, s.status, t.status) AS doc_status,
  COALESCE(r.receipt_date, s.actual_ship_date, s.planned_ship_date,
           t.transfer_date) AS doc_date,
  l.line_id AS line_id,
  COALESCE(rl.line_no, tl.line_no, CAST(l.line_id AS TEXT)) AS line_no,
  l.direction AS direction,
  l.link_type AS link_type,
  l.tentative AS tentative,
  l.qty AS qty,
  l.org_id AS org_id,
  l.created_at AS created_at
FROM document_hu_links l
LEFT JOIN handling_units h ON h.id = l.hu_id
LEFT JOIN receipts r ON l.doc_type = 'receipt' AND r.id = l.doc_id
LEFT JOIN receipt_lines rl ON l.doc_type = 'receipt' AND rl.id = l.line_id
LEFT JOIN shipments s ON l.doc_type = 'shipment' AND s.id = l.doc_id
LEFT JOIN transfer_orders t ON l.doc_type = 'transfer_order' AND t.id = l.doc_id
LEFT JOIN transfer_order_lines tl
       ON l.doc_type = 'transfer_order' AND tl.id = l.line_id"""

EXPECTED_COLUMNS = [
    'id', 'hu_id', 'hu_no', 'hu_status', 'hu_type', 'doc_type', 'doc_id',
    'doc_no', 'doc_status', 'doc_date', 'line_id', 'line_no', 'direction',
    'link_type', 'tentative', 'qty', 'org_id', 'created_at',
]


def _table_exists(conn, name):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,)).fetchone()
    return row is not None


def _view_exists(conn, name):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'view' AND name = ?",
        (name,)).fetchone()
    return row is not None


def _missing_tables(conn):
    return [name for name in REQUIRED_TABLES if not _table_exists(conn, name)]


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    db_path = Path(db_path)
    if not db_path.exists():
        print('[v220] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        missing = _missing_tables(conn)
        if missing:
            print('[v220] [SKIP] 缺基表: %s' % ', '.join(missing))
            return True
        conn.execute('DROP VIEW IF EXISTS %s' % VIEW_NAME)
        conn.execute('CREATE VIEW %s AS\n%s' % (VIEW_NAME, VIEW_SQL))
        conn.commit()
        print('[v220] 视图已重建: %s' % VIEW_NAME)
        return True
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        print('[v220] 失败: %s' % e)
        return False
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    db_path = Path(db_path)
    if not db_path.exists():
        print('[v220 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        missing = _missing_tables(conn)
        if missing:
            print('[v220 verify] [SKIP] 缺基表: %s' % ', '.join(missing))
            return True
        if not _view_exists(conn, VIEW_NAME):
            print('[v220 verify] FAIL: 缺视图 %s' % VIEW_NAME)
            return False
        columns = [row[1] for row in
                   conn.execute('PRAGMA table_info(%s)' % VIEW_NAME).fetchall()]
        if columns != EXPECTED_COLUMNS:
            print('[v220 verify] FAIL: 列不一致 %s' % columns)
            return False
        conn.execute('SELECT doc_no, hu_no, doc_date FROM %s LIMIT 1'
                     % VIEW_NAME).fetchall()
        print('[v220 verify] OK')
        return True
    except Exception as e:  # noqa: BLE001
        print('[v220 verify] FAIL: %s' % e)
        return False
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    db_path = Path(db_path)
    if not db_path.exists():
        print('[v220 rollback] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        conn.execute('DROP VIEW IF EXISTS %s' % VIEW_NAME)
        conn.commit()
        print('[v220 rollback] 视图已删除: %s' % VIEW_NAME)
        return True
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        print('[v220 rollback] 失败: %s' % e)
        return False
    finally:
        conn.close()


downgrade = rollback
