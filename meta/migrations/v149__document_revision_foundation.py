# -*- coding: utf-8 -*-
"""[v149] 文档版本地基（document_revisions / document_revision_changes）

依据:
  docs/superpowers/specs/2026-10-29-m2-document-revision/spec.md（M2 实施层）
  docs/superpowers/specs/2026-10-28-document-change-management-spec.md
    FR-004（修订产生版本：整单快照 + 字段级差异，append-only）
    TR-001（存量单据回填 revision_no = 1）

设计:
  · snapshot 存 TEXT，内容为 JSON 明文（D1：可 SQL 查询优先于压缩）
  · change_set_id 与 audit_logs 同值（D4），M2 阶段 change_request_id 恒 NULL
  · sales_orders 加 revision_no INTEGER NOT NULL DEFAULT 1，存量行回填 1

幂等:
  表 / 索引 / 列先查后用；重复执行打印 [SKIP]，DB 终态一致。

回滚:
  删表 + 尽量删列（SQLite 旧版不支持 DROP COLUMN 时打印 [KEEP]）。
  历史版本数据随表删除而丢失，回滚前先备份。
"""
import sqlite3
import sys
from pathlib import Path

TARGET_TABLE = 'sales_orders'
REVISION_FIELD = 'revision_no'

REVISIONS_TABLE = 'document_revisions'
CHANGES_TABLE = 'document_revision_changes'

REVISIONS_DDL = """
CREATE TABLE IF NOT EXISTS document_revisions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    object_type       TEXT NOT NULL,
    object_id         TEXT NOT NULL,
    revision_no       INTEGER NOT NULL,
    snapshot          TEXT NOT NULL,
    change_request_id INTEGER NULL,
    reason_code       TEXT NULL,
    change_set_id     TEXT NULL,
    created_by        TEXT NULL,
    created_at        TEXT NOT NULL,
    UNIQUE(object_type, object_id, revision_no)
)
"""

CHANGES_DDL = """
CREATE TABLE IF NOT EXISTS document_revision_changes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    revision_id INTEGER NOT NULL,
    line_key    TEXT NULL,
    field_name  TEXT NOT NULL,
    old_value   TEXT NULL,
    new_value   TEXT NULL
)
"""

INDEXES = (
    ('idx_revision_lookup',
     f'CREATE INDEX IF NOT EXISTS idx_revision_lookup ON {REVISIONS_TABLE}(object_type, object_id)'),
    ('idx_revision_change_rev',
     f'CREATE INDEX IF NOT EXISTS idx_revision_change_rev ON {CHANGES_TABLE}(revision_id, line_key)'),
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set:
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> bool:
    if column in _columns(conn, table):
        print(f'  - [SKIP] {table}.{column} 已存在')
        return False
    conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}')
    print(f'  - [ADD] {table}.{column}')
    return True


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用，
    缺少该参数会被静默跳过（v146 的坑）。"""
    if not db_path.exists():
        print(f'[v149] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v149] 开始: 文档版本地基')

        if _table_exists(conn, REVISIONS_TABLE):
            print(f'  - [SKIP] 表 {REVISIONS_TABLE} 已存在')
        else:
            conn.execute(REVISIONS_DDL)
            print(f'  - [ADD] 表 {REVISIONS_TABLE}')

        if _table_exists(conn, CHANGES_TABLE):
            print(f'  - [SKIP] 表 {CHANGES_TABLE} 已存在')
        else:
            conn.execute(CHANGES_DDL)
            print(f'  - [ADD] 表 {CHANGES_TABLE}')

        for index_name, ddl in INDEXES:
            conn.execute(ddl)
            print(f'  - [INDEX] {index_name}')

        if not _table_exists(conn, TARGET_TABLE):
            print(f'[v149] 表不存在: {TARGET_TABLE}（请先 sync_schema --execute 建表）')
            conn.commit()
            return False

        _ensure_column(conn, TARGET_TABLE, REVISION_FIELD,
                       'INTEGER NOT NULL DEFAULT 1')
        # 存量行显式回填 1（ALTER 的 DEFAULT 只对新增行生效的旧 SQLite 版本兜底）
        cursor = conn.execute(
            f'UPDATE {TARGET_TABLE} SET {REVISION_FIELD} = 1 '
            f'WHERE {REVISION_FIELD} IS NULL'
        )
        if cursor.rowcount:
            print(f'  - [BACKFILL] {TARGET_TABLE}.{REVISION_FIELD} ' 
                  f'{cursor.rowcount} 行回填为 1')

        conn.commit()
        print('[v149] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v149] 失败: %s' % e)
        return False
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v149 verify] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        for table in (REVISIONS_TABLE, CHANGES_TABLE):
            if not _table_exists(conn, table):
                print('[v149 verify] FAIL: 缺表 %s' % table)
                ok = False

        if REVISION_FIELD not in _columns(conn, TARGET_TABLE):
            print('[v149 verify] FAIL: %s 缺列 %s' % (TARGET_TABLE, REVISION_FIELD))
            ok = False

        indexes = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        for index_name, _ddl in INDEXES:
            if index_name not in indexes:
                print('[v149 verify] FAIL: 缺索引 %s' % index_name)
                ok = False

        print('[v149 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v149 rollback] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        for index_name, _ddl in INDEXES:
            conn.execute(f'DROP INDEX IF EXISTS {index_name}')
        for table in (CHANGES_TABLE, REVISIONS_TABLE):
            if _table_exists(conn, table):
                conn.execute(f'DROP TABLE {table}')
                print(f'  - [DROP] 表 {table}')
            else:
                print(f'  - [SKIP] 表 {table} 不存在')

        if REVISION_FIELD in _columns(conn, TARGET_TABLE):
            try:
                conn.execute(
                    f'ALTER TABLE {TARGET_TABLE} DROP COLUMN {REVISION_FIELD}'
                )
                print(f'  - [DROP] {TARGET_TABLE}.{REVISION_FIELD}')
            except sqlite3.OperationalError as e:
                print(f'  - [KEEP] {TARGET_TABLE}.{REVISION_FIELD}'
                      f'（当前 SQLite 不支持 DROP COLUMN: {e}）')

        conn.commit()
        print('[v149 rollback] 完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v149 rollback] 失败: %s' % e)
        return False
    finally:
        conn.close()


downgrade = rollback


if __name__ == '__main__':
    _REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from meta.core.db_path import get_meta_db_path

    db = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith('-') \
        else Path(get_meta_db_path())
    print('DB: %s' % db)

    if '--verify' in sys.argv:
        sys.exit(0 if verify(db) else 1)
    elif '--rollback' in sys.argv:
        sys.exit(0 if rollback(db) else 1)
    else:
        if not migrate(db):
            sys.exit(1)
        sys.exit(0 if verify(db) else 1)
