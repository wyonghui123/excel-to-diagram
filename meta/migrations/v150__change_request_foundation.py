# -*- coding: utf-8 -*-
"""[v150] 变更申请地基（change_requests / change_request_lines）

依据:
  docs/superpowers/specs/2026-10-29-m3-change-request/spec.md（M3 实施层）
  docs/superpowers/specs/2026-10-28-document-change-management-spec.md
    FR-007（通用对象 change_request + 行表，不存 JSON blob）
    FR-011（派生字段禁止进入变更申请字段白名单）

设计:
  · change_request_lines 一行一字段（field_name + old/new），与
    document_revision_changes 同口径（TEXT 字符串化），禁止 JSON blob
  · line_key 为 NULL = 头级变更；非空 = 行级变更（行主键字符串）
  · document_revisions.change_request_id 已由 v149 预留，本迁移不动该表

幂等:
  表 / 索引先查后用；重复执行打印 [SKIP]，DB 终态一致。

回滚:
  删索引 + 删表；变更申请数据随表删除而丢失，回滚前先备份。
"""
import sqlite3
import sys
from pathlib import Path

CR_TABLE = 'change_requests'
CRL_TABLE = 'change_request_lines'

CR_DDL = """
CREATE TABLE IF NOT EXISTS change_requests (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    target_object_type  TEXT NOT NULL,
    target_object_id    TEXT NOT NULL,
    target_revision_no  INTEGER NOT NULL,
    status              TEXT NOT NULL DEFAULT 'draft',
    reason_code         TEXT NULL,
    summary             TEXT NULL,
    submitted_by        TEXT NULL,
    submitted_at        TEXT NULL,
    approved_by         TEXT NULL,
    approved_at         TEXT NULL,
    applied_at          TEXT NULL,
    applied_revision_no INTEGER NULL,
    fail_reason         TEXT NULL,
    change_set_id       TEXT NULL,
    created_by          TEXT NULL,
    created_at          TEXT NOT NULL,
    updated_by          TEXT NULL,
    updated_at          TEXT NULL
)
"""

CRL_DDL = """
CREATE TABLE IF NOT EXISTS change_request_lines (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    change_request_id INTEGER NOT NULL,
    line_key          TEXT NULL,
    field_name        TEXT NOT NULL,
    old_value         TEXT NULL,
    new_value         TEXT NULL
)
"""

INDEXES = (
    ('idx_cr_target',
     f'CREATE INDEX IF NOT EXISTS idx_cr_target ON {CR_TABLE}'
     f'(target_object_type, target_object_id, status)'),
    ('idx_cr_status',
     f'CREATE INDEX IF NOT EXISTS idx_cr_status ON {CR_TABLE}(status)'),
    ('uq_crl_cr_line_field',
     f'CREATE UNIQUE INDEX IF NOT EXISTS uq_crl_cr_line_field ON {CRL_TABLE}'
     f'(change_request_id, line_key, field_name)'),
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用，
    缺少该参数会被静默跳过（v146 的坑）。"""
    if not db_path.exists():
        print(f'[v150] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v150] 开始: 变更申请地基')

        if _table_exists(conn, CR_TABLE):
            print(f'  - [SKIP] 表 {CR_TABLE} 已存在')
        else:
            conn.execute(CR_DDL)
            print(f'  - [ADD] 表 {CR_TABLE}')

        if _table_exists(conn, CRL_TABLE):
            print(f'  - [SKIP] 表 {CRL_TABLE} 已存在')
        else:
            conn.execute(CRL_DDL)
            print(f'  - [ADD] 表 {CRL_TABLE}')

        for index_name, ddl in INDEXES:
            conn.execute(ddl)
            print(f'  - [INDEX] {index_name}')

        conn.commit()
        print('[v150] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v150] 失败: %s' % e)
        return False
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v150 verify] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        for table in (CR_TABLE, CRL_TABLE):
            if not _table_exists(conn, table):
                print('[v150 verify] FAIL: 缺表 %s' % table)
                ok = False

        indexes = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        for index_name, _ddl in INDEXES:
            if index_name not in indexes:
                print('[v150 verify] FAIL: 缺索引 %s' % index_name)
                ok = False

        print('[v150 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v150 rollback] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        for index_name, _ddl in INDEXES:
            conn.execute(f'DROP INDEX IF EXISTS {index_name}')
        for table in (CRL_TABLE, CR_TABLE):
            if _table_exists(conn, table):
                conn.execute(f'DROP TABLE {table}')
                print(f'  - [DROP] 表 {table}')
            else:
                print(f'  - [SKIP] 表 {table} 不存在')

        conn.commit()
        print('[v150 rollback] 完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v150 rollback] 失败: %s' % e)
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
