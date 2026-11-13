# -*- coding: utf-8 -*-
"""[v262 2026-11-13] 采购发票行价格追溯列（W5 遗留②）

依据:
  docs/specs/spec-vendor-invoice-object-model-2026-11-11.md §22.4 / R-VI-27
  docs/superpowers/plans/2026-11-12-vendor-invoice-amount-w2-execution-plan.md §9.2

内容:
  1. vendor_invoice_lines 增列:
       price_source VARCHAR(20)   po / manual / adjustment（可空，服务写入）
       price_trace  TEXT          JSON 快照（可空，不建索引，Spec §22.11）
     幂等: PRAGMA 判列，缺失才 ALTER。
  2. 历史回填（仅 price_source IS NULL，天然幂等）:
       头 document_category = 'adjustment'       → adjustment
       order_line_id IS NOT NULL                 → po
       其余                                       → manual
     price_trace 无法重建，保持 NULL（不伪造快照）。

回滚:
  SQLite 老版本不支持 DROP COLUMN，列保留并清空值（与 v259 / v260 一致）。
"""

import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v262__vendor_invoice_line_price_trace'

LINE_TABLE = 'vendor_invoice_lines'
HEADER_TABLE = 'vendor_invoices'

LINE_COLUMNS = (
    ('price_source', 'VARCHAR(20)'),
    ('price_trace', 'TEXT'),
)

SOURCE_PO = 'po'
SOURCE_MANUAL = 'manual'
SOURCE_ADJUSTMENT = 'adjustment'


def _connect(db_path):
    return sqlite3.connect(str(db_path))


def _table_exists(conn, table):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        [table]).fetchone()
    return row is not None


def _columns(conn, table):
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute('PRAGMA table_info(%s)' % table)}


# ------------------------------------------------------------------ migration

def _do_columns(conn):
    if not _table_exists(conn, LINE_TABLE):
        print('[v262] SKIP: %s 表不存在（未加列）' % LINE_TABLE)
        return 0
    existing = _columns(conn, LINE_TABLE)
    added = 0
    for column, column_type in LINE_COLUMNS:
        if column in existing:
            print('[v262] SKIP: %s.%s 已存在' % (LINE_TABLE, column))
            continue
        conn.execute('ALTER TABLE %s ADD COLUMN %s %s'
                     % (LINE_TABLE, column, column_type))
        added += 1
        print('[v262] ALTER: %s 新增 %s' % (LINE_TABLE, column))
    return added


def _backfill(conn):
    """历史行按锚点近似回填 price_source（仅 IS NULL）。"""
    if not _table_exists(conn, LINE_TABLE):
        return 0
    columns = _columns(conn, LINE_TABLE)
    if 'price_source' not in columns:
        return 0
    has_header = _table_exists(conn, HEADER_TABLE)
    total = 0
    if has_header:
        cursor = conn.execute(
            'UPDATE %s SET price_source = ? WHERE price_source IS NULL '
            'AND invoice_id IN (SELECT id FROM %s WHERE document_category = ?)'
            % (LINE_TABLE, HEADER_TABLE),
            [SOURCE_ADJUSTMENT, 'adjustment'])
        total += cursor.rowcount
        print('[v262] BACKFILL: 调整单行 → %s（%d 行）'
              % (SOURCE_ADJUSTMENT, cursor.rowcount))
    cursor = conn.execute(
        'UPDATE %s SET price_source = ? WHERE price_source IS NULL '
        'AND order_line_id IS NOT NULL' % LINE_TABLE, [SOURCE_PO])
    total += cursor.rowcount
    print('[v262] BACKFILL: PO 锚点行 → %s（%d 行）' % (SOURCE_PO, cursor.rowcount))
    cursor = conn.execute(
        'UPDATE %s SET price_source = ? WHERE price_source IS NULL'
        % LINE_TABLE, [SOURCE_MANUAL])
    total += cursor.rowcount
    print('[v262] BACKFILL: 其余行 → %s（%d 行）' % (SOURCE_MANUAL, cursor.rowcount))
    return total


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    db_path = Path(db_path)
    print('[v262] 开始: 采购发票行价格追溯列（price_source / price_trace）')
    conn = _connect(db_path)
    try:
        _do_columns(conn)
        _backfill(conn)
        conn.commit()
        print('[v262] 完成: 采购发票行价格追溯列')
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
        if not _table_exists(conn, LINE_TABLE):
            problems.append('缺少表 %s' % LINE_TABLE)
        else:
            existing = _columns(conn, LINE_TABLE)
            for column, _type in LINE_COLUMNS:
                if column not in existing:
                    problems.append('缺少列 %s.%s' % (LINE_TABLE, column))
            nullable = {row[1]: row[3] for row in
                        conn.execute('PRAGMA table_info(%s)' % LINE_TABLE)}
            for column, _type in LINE_COLUMNS:
                if column in nullable and int(nullable[column] or 0) != 0:
                    problems.append('列 %s.%s 不应为 NOT NULL'
                                    % (LINE_TABLE, column))
            if 'price_source' in existing:
                left = conn.execute(
                    'SELECT COUNT(*) FROM %s WHERE price_source IS NULL'
                    % LINE_TABLE).fetchone()[0]
                if int(left):
                    problems.append('回填后仍有 %d 行 price_source IS NULL'
                                    % int(left))
    finally:
        conn.close()

    if problems:
        for problem in problems:
            print('[v262] FAIL: %s' % problem)
        return False
    print('[v262] PASS: vendor_invoice_lines.price_source / price_trace 齐备且已回填')
    return True


def rollback(db_path: Path) -> bool:
    db_path = Path(db_path)
    print('[v262] 开始: 回滚采购发票行价格追溯列（清值，列保留）')
    conn = _connect(db_path)
    try:
        if _table_exists(conn, LINE_TABLE):
            existing = _columns(conn, LINE_TABLE)
            for column, _type in LINE_COLUMNS:
                if column in existing:
                    conn.execute('UPDATE %s SET %s = NULL' % (LINE_TABLE, column))
        conn.commit()
        print('[v262] 完成: 两列已清空（SQLite 老版本不支持 DROP COLUMN）')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()