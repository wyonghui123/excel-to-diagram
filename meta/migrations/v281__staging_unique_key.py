# -*- coding: utf-8 -*-
"""v281 —— staging 唯一键补 `object_type`（多 sheet 导入行号会撞车）。

依据:
  docs/specs/spec-integration-module-2026-11-15.md
    §4.2 import_staging_rows / §6 FR-4 / §11 M3

问题:
  v279 建的 `uq_import_staging_row` 是 `(batch_no, row_no)` 唯一；
  一个工作簿含多个 sheet 时，第 2 行在每个 sheet 都存在 → 唯一键冲突。

修法:
  唯一键改为 `(batch_no, object_type, row_no)`，`row_no` 仍是 Excel 行号
  （表头在第 1 行），前端仍可直接跳行。

幂等: 每次先 DROP IF EXISTS 再 CREATE IF NOT EXISTS。
"""

import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v281__staging_unique_key'

TABLE = 'import_staging_rows'
INDEX_NAME = 'uq_import_staging_row'

CREATE_SQL = (
    'CREATE UNIQUE INDEX IF NOT EXISTS uq_import_staging_row '
    'ON import_staging_rows(batch_no, object_type, row_no)'
)


def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", [table]
    ).fetchone()
    return bool(row)


def _index_columns(conn: sqlite3.Connection, name: str):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name = ?", [name]
    ).fetchone()
    if not row:
        return None
    return [info[2] for info in conn.execute('PRAGMA index_info(%s)' % name)]


def _do_index(conn: sqlite3.Connection) -> None:
    if not _has_table(conn, TABLE):
        print('  - [SKIP] 表 %s 不存在，跳过重建索引' % TABLE)
        return
    columns = _index_columns(conn, INDEX_NAME)
    if columns == ['batch_no', 'object_type', 'row_no']:
        print('  - [OK] 索引 %s 已是 (batch_no, object_type, row_no)' % INDEX_NAME)
        return
    conn.execute('DROP INDEX IF EXISTS %s' % INDEX_NAME)
    conn.execute(CREATE_SQL)
    print('  - [NEW] 索引 %s → (batch_no, object_type, row_no)' % INDEX_NAME)


def migrate(db_path, skip_backup=True) -> bool:
    """migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    path = Path(db_path)
    if not path.exists():
        print('[v281] SKIP: database not found: %s' % path)
        return False

    conn = sqlite3.connect(str(path), timeout=10)
    try:
        print('[v281] 开始: staging 唯一键补 object_type')
        _do_index(conn)
        conn.commit()
        print('[v281] 完成')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


#: 部分历史迁移以 `upgrade()` 命名；保留别名便于手工调用。
upgrade = migrate


def verify(db_path) -> bool:
    path = Path(db_path)
    if not path.exists():
        print('[v281 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        if not _has_table(conn, TABLE):
            print('[v281 verify] SKIP: 表 %s 不存在' % TABLE)
            return True
        columns = _index_columns(conn, INDEX_NAME)
        if columns != ['batch_no', 'object_type', 'row_no']:
            print('[v281 verify] FAIL: 索引列为 %s' % columns)
            return False
        return True
    finally:
        conn.close()