# -*- coding: utf-8 -*-
"""[v148] 审计日志补变更集与原因码

依据:
  docs/superpowers/specs/2026-10-28-m1-audit-change-set/spec.md（M1）
  docs/superpowers/specs/2026-10-28-document-change-management-spec.md
    FR-001（审计补 change_set_id + reason_code）
    TR-002（audit_logs 加两列，存量行留空）

背景:
  audit_logs 已有字段级流水，但缺少「一次保存 = 一个变更集」的显式归组，
  也没有「为什么改」的原因码。本迁移补两列：
    · change_set_id  —— 一次保存产生的多条审计共享（cs_<uuid16>）
    · reason_code    —— 原因码必填字段被修改时写入

回填策略:
  存量行两列留空（NULL），不回溯补造（上游 Spec TBD-7 决策：回溯成本高、
  价值低）。

幂等:
  列先查后用；重复执行打印 [SKIP]，DB 终态一致。索引 IF NOT EXISTS。

回滚:
  删索引 + 删两列；SQLite 版本不支持 DROP COLUMN 时打印 [KEEP] 并保留。
"""
import sqlite3
import sys
from pathlib import Path

AUDIT_TABLE = 'audit_logs'

CHANGE_SET_COLUMN = 'change_set_id'
REASON_CODE_COLUMN = 'reason_code'

NEW_COLUMNS = (
    (CHANGE_SET_COLUMN, 'TEXT'),
    (REASON_CODE_COLUMN, 'TEXT'),
)

INDEX_NAME = 'idx_audit_change_set'


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set:
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> bool:
    """返回 True = 本次新增。"""
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
        print(f'[v148] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v148] 开始: audit_logs 补变更集/原因码列')
        if not _table_exists(conn, AUDIT_TABLE):
            print(f'[v148] 表不存在: {AUDIT_TABLE}（请先 sync_schema --execute 建表）')
            return False

        for column, ddl in NEW_COLUMNS:
            _ensure_column(conn, AUDIT_TABLE, column, ddl)

        conn.execute(
            f'CREATE INDEX IF NOT EXISTS {INDEX_NAME} '
            f'ON {AUDIT_TABLE}({CHANGE_SET_COLUMN})'
        )
        print(f'  - [INDEX] {INDEX_NAME}')

        conn.commit()
        print('[v148] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v148] 失败: %s' % e)
        return False
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v148 verify] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        cols = _columns(conn, AUDIT_TABLE)
        ok = True
        for column, _ddl in NEW_COLUMNS:
            if column not in cols:
                print('[v148 verify] FAIL: %s 缺列 %s' % (AUDIT_TABLE, column))
                ok = False
        indexes = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=?",
                (AUDIT_TABLE,),
            )
        }
        if INDEX_NAME not in indexes:
            print('[v148 verify] FAIL: 缺索引 %s' % INDEX_NAME)
            ok = False
        print('[v148 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    """删索引 + 删两列（SQLite 不支持 DROP COLUMN 时保留）。"""
    if not db_path.exists():
        print('[v148 rollback] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        conn.execute(f'DROP INDEX IF EXISTS {INDEX_NAME}')
        for column, _ddl in NEW_COLUMNS:
            if column not in _columns(conn, AUDIT_TABLE):
                print(f'  - [SKIP] {AUDIT_TABLE}.{column} 不存在')
                continue
            try:
                conn.execute(f'ALTER TABLE {AUDIT_TABLE} DROP COLUMN {column}')
                print(f'  - [DROP] {AUDIT_TABLE}.{column}')
            except sqlite3.OperationalError as e:
                print(f'  - [KEEP] {AUDIT_TABLE}.{column}（当前 SQLite 不支持 DROP COLUMN: {e}）')
        conn.commit()
        print('[v148 rollback] 完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v148 rollback] 失败: %s' % e)
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
