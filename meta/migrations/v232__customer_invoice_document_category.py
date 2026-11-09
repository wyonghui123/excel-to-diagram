# -*- coding: utf-8 -*-
"""v232 —— 销售发票单据类别（document_category）。

背景：
  v231 建表时只靠 document_type_id 间接表达单据语义。Fusion 对标后确认需要
  头级 document_category（invoice / credit_memo / debit_memo / cancellation），
  并一律由 type_definitions.document_category 派生。

内容：
  1. 给 customer_invoices 增加 document_category（NOT NULL DEFAULT 'invoice'）。
  2. 按 document_type_id 回填：standard→invoice / credit_memo→credit_memo /
     debit_memo→debit_memo / 其余→invoice。
  3. verify 校验列存在、无空值、无越界、与类型映射一致。
  4. rollback 删除该列。

幂等：列已存在则跳过 ALTER；回填可重复执行。
"""

import sqlite3
from pathlib import Path

HEADER_TABLE = 'customer_invoices'
TYPE_TABLE = 'type_definitions'
COLUMN = 'document_category'

ALLOWED_CATEGORIES = ('invoice', 'credit_memo', 'debit_memo', 'cancellation')

_CATEGORY_CASE_SQL = """
CASE td.document_category
    WHEN 'standard' THEN 'invoice'
    WHEN 'credit_memo' THEN 'credit_memo'
    WHEN 'debit_memo' THEN 'debit_memo'
    ELSE 'invoice'
END
"""


def _connect(db_path):
    return sqlite3.connect(str(db_path))


def _table_exists(conn, table):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        [table]).fetchone()
    return row is not None


def _column_exists(conn, table, column):
    if not _table_exists(conn, table):
        return False
    rows = conn.execute('PRAGMA table_info(%s)' % table).fetchall()
    return any(row[1] == column for row in rows)


def upgrade(db_path, skip_backup=True):
    path = Path(db_path)
    if not path.exists():
        print('[v232] SKIP: database not found: %s' % path)
        return False

    conn = _connect(path)
    try:
        if not _table_exists(conn, HEADER_TABLE):
            print('[v232] SKIP: table %s not found（请先执行 v231）' % HEADER_TABLE)
            return False

        if not _column_exists(conn, HEADER_TABLE, COLUMN):
            conn.execute(
                "ALTER TABLE %s ADD COLUMN %s VARCHAR(20) NOT NULL DEFAULT 'invoice'"
                % (HEADER_TABLE, COLUMN))
            print('[v232] added column %s.%s' % (HEADER_TABLE, COLUMN))
        else:
            print('[v232] column %s.%s already exists, skip ALTER'
                  % (HEADER_TABLE, COLUMN))

        if _table_exists(conn, TYPE_TABLE):
            conn.execute(
                """
                UPDATE %s
                   SET %s = COALESCE((
                       SELECT %s FROM %s td WHERE td.id = %s.document_type_id
                   ), 'invoice')
                """
                % (HEADER_TABLE, COLUMN, _CATEGORY_CASE_SQL, TYPE_TABLE,
                   HEADER_TABLE))
        else:
            print('[v232] WARN: table %s not found, skip backfill' % TYPE_TABLE)

        conn.commit()
    finally:
        conn.close()

    print('[v232] done')
    return True


def migrate(db_path, skip_backup=True):
    """与 v231 保持同名入口。"""
    return upgrade(db_path, skip_backup=skip_backup)


def verify(db_path) -> bool:
    path = Path(db_path)
    if not path.exists():
        print('[v232] verify FAIL: database not found')
        return False

    conn = _connect(path)
    try:
        if not _table_exists(conn, HEADER_TABLE):
            print('[v232] verify FAIL: table %s missing' % HEADER_TABLE)
            return False
        if not _column_exists(conn, HEADER_TABLE, COLUMN):
            print('[v232] verify FAIL: column %s missing' % COLUMN)
            return False

        placeholders = ','.join(['?'] * len(ALLOWED_CATEGORIES))
        bad = conn.execute(
            'SELECT COUNT(*) FROM %s WHERE %s IS NULL OR %s NOT IN (%s)'
            % (HEADER_TABLE, COLUMN, COLUMN, placeholders),
            list(ALLOWED_CATEGORIES)).fetchone()[0]
        if bad:
            print('[v232] verify FAIL: %s invalid rows' % bad)
            return False

        if _table_exists(conn, TYPE_TABLE):
            mismatch = conn.execute(
                """
                SELECT COUNT(*)
                  FROM %s ci
                  JOIN %s td ON td.id = ci.document_type_id
                 WHERE ci.%s <> %s
                """
                % (HEADER_TABLE, TYPE_TABLE, COLUMN, _CATEGORY_CASE_SQL)
            ).fetchone()[0]
            if mismatch:
                print('[v232] verify FAIL: %s category/type mismatches'
                      % mismatch)
                return False

        print('[v232] verify OK')
        return True
    finally:
        conn.close()


def rollback(db_path) -> bool:
    path = Path(db_path)
    if not path.exists():
        print('[v232] rollback SKIP: database not found')
        return False

    conn = _connect(path)
    try:
        if not _column_exists(conn, HEADER_TABLE, COLUMN):
            print('[v232] rollback SKIP: column missing')
            return True
        try:
            conn.execute(
                'ALTER TABLE %s DROP COLUMN %s' % (HEADER_TABLE, COLUMN))
            conn.commit()
            print('[v232] rollback done')
            return True
        except sqlite3.OperationalError as exc:
            print('[v232] rollback FAIL: %s' % exc)
            return False
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else 'meta/architecture.db'
    upgrade(target)
    verify(target)
