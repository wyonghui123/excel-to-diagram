# -*- coding: utf-8 -*-
"""[v189 2026-11-02] 员工主数据 TBD 收口（v1.18）

依据:
  docs/specs/spec-unified-resource-model-2026-11-01-v1.0.md §FR-015 / §10 TBD-9~13

变更（仅两处，均为增量、可回滚）:
  ① `employees` 增 `supplier_party_id INTEGER`（可空，真外键 REFERENCES parties(id)）
     —— 派遣人员（employment_type=dispatched）必填由服务层校验（TBD-10）；
  ② 工号唯一域从「active 全局」改为「按法人雇主」：
     `uq_employee_active_no(employee_no) WHERE status='active'`
     → `uq_employee_active_org_no(org_id, employee_no) WHERE status='active'`
     —— `org_id` 语义 = legal employer（TBD-12 两层简化）。

口径:
  · TBD-9  `name` 保留为缓存列，真源 person_profile→party，服务层同步；不改表。
  · TBD-11 不建 `employee_org_assignment`、不加矩阵汇报字段；本迁移不涉及。
  · 幂等：列 / 索引先查后用，重复执行打印 [SKIP]。
  · 回滚：删新索引并尝试恢复旧索引（若现有数据跨法人同号则无法恢复，
    打印 [WARN] 并保留列 stub）；**不 DROP COLUMN**（SQLite 旧版本兼容）。
"""
import sqlite3
import sys
from pathlib import Path

EMPLOYEES_TABLE = 'employees'

NEW_COLUMN = ('supplier_party_id', 'INTEGER REFERENCES parties(id)')

OLD_INDEX = 'uq_employee_active_no'
OLD_INDEX_SQL = (
    'CREATE UNIQUE INDEX IF NOT EXISTS uq_employee_active_no '
    "ON employees(employee_no) WHERE status='active'"
)

NEW_INDEX = 'uq_employee_active_org_no'
NEW_INDEX_SQL = (
    'CREATE UNIQUE INDEX IF NOT EXISTS uq_employee_active_org_no '
    "ON employees(org_id, employee_no) WHERE status='active'"
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set:
    return {row[1] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()}


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone() is not None


def _index_sql(conn: sqlite3.Connection, name: str):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone()
    return row[0] if row else None


def _do_column(conn: sqlite3.Connection) -> None:
    column, column_type = NEW_COLUMN
    if column in _columns(conn, EMPLOYEES_TABLE):
        print(f'  - [SKIP] 列 {EMPLOYEES_TABLE}.{column} 已存在')
        return
    conn.execute(
        f'ALTER TABLE {EMPLOYEES_TABLE} ADD COLUMN {column} {column_type}')
    print(f'  - [ADD] 列 {EMPLOYEES_TABLE}.{column}')


def _do_indexes(conn: sqlite3.Connection) -> None:
    if _index_exists(conn, OLD_INDEX):
        conn.execute(f'DROP INDEX IF EXISTS {OLD_INDEX}')
        print(f'  - [DROP] 旧索引 {OLD_INDEX}')
    if _index_exists(conn, NEW_INDEX):
        print(f'  - [SKIP] 索引 {NEW_INDEX} 已存在')
    else:
        conn.execute(NEW_INDEX_SQL)
        print(f'  - [ADD] 索引 {NEW_INDEX}')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print(f'[v189] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v189] 开始: 员工 TBD 收口（supplier_party_id + 按法人工号唯一）')
        if not _table_exists(conn, EMPLOYEES_TABLE):
            print(f'[v189] 表 {EMPLOYEES_TABLE} 不存在（需先执行 v185），跳过')
            return False
        _do_column(conn)
        _do_indexes(conn)
        conn.commit()
        print('[v189] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v189] 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v189 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        if not _table_exists(conn, EMPLOYEES_TABLE):
            print(f'[v189 verify] FAIL: 缺表 {EMPLOYEES_TABLE}')
            return False

        column, _type = NEW_COLUMN
        if column not in _columns(conn, EMPLOYEES_TABLE):
            print(f'[v189 verify] FAIL: 缺列 {EMPLOYEES_TABLE}.{column}')
            ok = False

        if _index_exists(conn, OLD_INDEX):
            print(f'[v189 verify] FAIL: 旧索引 {OLD_INDEX} 仍存在')
            ok = False
        sql = _index_sql(conn, NEW_INDEX) or ''
        if not sql:
            print(f'[v189 verify] FAIL: 缺索引 {NEW_INDEX}')
            ok = False
        else:
            lowered = sql.lower()
            if 'unique' not in lowered or 'where' not in lowered:
                print(f'[v189 verify] FAIL: {NEW_INDEX} 不是部分唯一索引')
                ok = False
            if 'org_id' not in lowered or 'employee_no' not in lowered:
                print(f'[v189 verify] FAIL: {NEW_INDEX} 列不符（应为 org_id, employee_no）')
                ok = False
            if "'active'" not in lowered:
                print(f"[v189 verify] FAIL: {NEW_INDEX} 条件不含 status='active'")
                ok = False

        print('[v189 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print(f'[v189 rollback] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        if not _table_exists(conn, EMPLOYEES_TABLE):
            print(f'[v189 rollback] 表 {EMPLOYEES_TABLE} 不存在，无需回滚')
            return True

        if _index_exists(conn, NEW_INDEX):
            conn.execute(f'DROP INDEX IF EXISTS {NEW_INDEX}')
            print(f'  - [DROP] 索引 {NEW_INDEX}')

        if not _index_exists(conn, OLD_INDEX):
            try:
                conn.execute(OLD_INDEX_SQL)
                print(f'  - [ADD] 旧索引 {OLD_INDEX}')
            except sqlite3.IntegrityError as e:
                print(f'  - [WARN] 旧索引 {OLD_INDEX} 无法恢复（跨法人存在同号在职行）: {e}')

        conn.commit()
        print('[v189 rollback] 完成（supplier_party_id 列保留为 stub）')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v189 rollback] 失败: {e}')
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
