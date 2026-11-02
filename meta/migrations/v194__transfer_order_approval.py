# -*- coding: utf-8 -*-
"""[v194 2026-11-02] 调拨单审批流（TBD-9）

依据:
  docs/specs/tasks-transfer-order-object-model-2026-11-02.md §14 步 24（TBD-9）

范围:
  1. transfer_orders 增列 approval_status VARCHAR(20) NOT NULL
     DEFAULT 'not_required'（与业务状态 status 正交，不新增 submitted 状态）；
  2. permissions 增 4 条审批动作权限（双段式）：
       transfer_order:transfer_order_submit / withdraw / approve / reject；
  3. 授权同步到 admin / default 权限集（表缺失时 SKIP）。

幂等:
  列先查 PRAGMA 再 ALTER；权限 INSERT OR IGNORE；授权先查后用。

回滚:
  删 4 条权限与授权；SQLite 不支持 DROP COLUMN，列 approval_status 保留
  （仅不再被使用）。
"""
import sqlite3
import sys
from pathlib import Path

TO_TABLE = 'transfer_orders'
APPROVAL_COLUMN = 'approval_status'
APPROVAL_DEFAULT = 'not_required'
PERMISSION_TABLE = 'permissions'
PERMISSION_SET_TABLE = 'permission_sets'
PERMISSION_SET_PERMISSION_TABLE = 'permission_set_permissions'

SCOPE_BO = 'transfer_order'

#: (code, name, resource_type, action)
APPROVAL_PERMISSIONS = (
    ('transfer_order:transfer_order_submit', '调拨单提交审批',
     SCOPE_BO, 'submit'),
    ('transfer_order:transfer_order_withdraw', '调拨单撤回审批',
     SCOPE_BO, 'withdraw'),
    ('transfer_order:transfer_order_approve', '调拨单审批通过',
     SCOPE_BO, 'approve'),
    ('transfer_order:transfer_order_reject', '调拨单审批驳回',
     SCOPE_BO, 'reject'),
)

GRANT_TO_SETS = ('admin', 'default')


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set:
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()}


def _do_column(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, TO_TABLE):
        print(f'  - [SKIP] 表 {TO_TABLE} 不存在')
        return
    if APPROVAL_COLUMN in _columns(conn, TO_TABLE):
        print(f'  - [SKIP] 列 {TO_TABLE}.{APPROVAL_COLUMN} 已存在')
        return
    conn.execute(
        "ALTER TABLE %s ADD COLUMN %s VARCHAR(20) NOT NULL DEFAULT '%s'"
        % (TO_TABLE, APPROVAL_COLUMN, APPROVAL_DEFAULT))
    print(f'  - [CREATE] 列 {TO_TABLE}.{APPROVAL_COLUMN}')


def _do_permissions(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, PERMISSION_TABLE):
        print(f'  - [SKIP] 表 {PERMISSION_TABLE} 不存在')
        return
    created = 0
    for code, name, resource_type, action in APPROVAL_PERMISSIONS:
        cur = conn.execute(
            'INSERT OR IGNORE INTO permissions (code, name, resource_type, action) '
            'VALUES (?, ?, ?, ?)',
            (code, name, resource_type, action))
        if cur.rowcount:
            created += 1
            print(f'  - [CREATE] 权限 {code} ({name})')
        else:
            print(f'  - [SKIP] 权限 {code} 已存在')
    print(f'  - [SUMMARY] permissions: +{created} 新增')


def _do_grants(conn: sqlite3.Connection) -> None:
    if not (_table_exists(conn, PERMISSION_TABLE)
            and _table_exists(conn, PERMISSION_SET_TABLE)
            and _table_exists(conn, PERMISSION_SET_PERMISSION_TABLE)):
        print('  - [SKIP] 权限集相关表缺失，跳过授权')
        return
    cols = _columns(conn, PERMISSION_SET_PERMISSION_TABLE)
    if 'permission_set_id' in cols:
        id_col = 'permission_set_id'
    elif 'role_id' in cols:
        id_col = 'role_id'
    else:
        print('  - [SKIP] permission_set_permissions 无 permission_set_id/role_id')
        return
    has_code_col = 'permission_code' in cols
    has_granted = 'granted' in cols
    granted = 0
    for set_code in GRANT_TO_SETS:
        row = conn.execute(
            'SELECT id FROM permission_sets WHERE code=? AND is_active=1',
            (set_code,)).fetchone()
        if not row:
            continue
        permission_set_id = row[0]
        for code, _name, _rtype, _action in APPROVAL_PERMISSIONS:
            prow = conn.execute(
                'SELECT id FROM permissions WHERE code=?', (code,)).fetchone()
            if not prow:
                continue
            params = [permission_set_id, prow[0]]
            where = f'{id_col} = ? AND permission_id = ?'
            if has_code_col:
                where += ' AND permission_code = ?'
                params.append(code)
            if conn.execute(
                    'SELECT 1 FROM permission_set_permissions WHERE ' + where,
                    params).fetchone():
                continue
            if has_code_col:
                conn.execute(
                    f"INSERT INTO permission_set_permissions "
                    f"({id_col}, permission_code, permission_id, granted, "
                    f"created_at) VALUES (?, ?, ?, 1, datetime('now'))",
                    (permission_set_id, code, prow[0]))
            elif has_granted:
                conn.execute(
                    f"INSERT INTO permission_set_permissions "
                    f"({id_col}, permission_id, granted, created_at) "
                    f"VALUES (?, ?, 1, datetime('now'))",
                    (permission_set_id, prow[0]))
            else:
                conn.execute(
                    f"INSERT INTO permission_set_permissions "
                    f"({id_col}, permission_id, created_at) "
                    f"VALUES (?, ?, datetime('now'))",
                    (permission_set_id, prow[0]))
            granted += 1
    print(f'  - [SUMMARY] permission_set_permissions: +{granted} 授权')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print(f'[v194] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v194] 开始: 调拨单审批流（TBD-9）')
        _do_column(conn)
        _do_permissions(conn)
        _do_grants(conn)
        conn.commit()
        print('[v194] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v194] 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v194 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True

        if not _table_exists(conn, TO_TABLE):
            print(f'[v194 verify] FAIL: 缺表 {TO_TABLE}')
            ok = False
        elif APPROVAL_COLUMN not in _columns(conn, TO_TABLE):
            print(f'[v194 verify] FAIL: 缺列 {TO_TABLE}.{APPROVAL_COLUMN}')
            ok = False

        if not _table_exists(conn, PERMISSION_TABLE):
            print(f'[v194 verify] FAIL: 缺表 {PERMISSION_TABLE}')
            ok = False
        else:
            for code, _name, _rtype, _action in APPROVAL_PERMISSIONS:
                if not conn.execute(
                        'SELECT 1 FROM permissions WHERE code=?', (code,)
                ).fetchone():
                    print(f'[v194 verify] FAIL: 缺权限 {code}')
                    ok = False

        print('[v194 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print(f'[v194 rollback] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        if _table_exists(conn, PERMISSION_SET_PERMISSION_TABLE):
            grant_cols = _columns(conn, PERMISSION_SET_PERMISSION_TABLE)
            for code, _name, _rtype, _action in APPROVAL_PERMISSIONS:
                if 'permission_code' in grant_cols:
                    cur = conn.execute(
                        'DELETE FROM permission_set_permissions '
                        'WHERE permission_code=?', (code,))
                else:
                    prow = conn.execute(
                        'SELECT id FROM permissions WHERE code=?', (code,)
                    ).fetchone() if _table_exists(conn, PERMISSION_TABLE) else None
                    if not prow:
                        continue
                    cur = conn.execute(
                        'DELETE FROM permission_set_permissions '
                        'WHERE permission_id=?', (prow[0],))
                if cur.rowcount:
                    print(f'  - [DROP] 授权 {code}')

        if _table_exists(conn, PERMISSION_TABLE):
            for code, _name, _rtype, _action in APPROVAL_PERMISSIONS:
                cur = conn.execute(
                    'DELETE FROM permissions WHERE code=?', (code,))
                if cur.rowcount:
                    print(f'  - [DROP] 权限 {code}')

        if _table_exists(conn, TO_TABLE):
            print(f'  - [KEEP] 列 {TO_TABLE}.{APPROVAL_COLUMN}'
                  '（SQLite 不支持 DROP COLUMN）')

        conn.commit()
        print('[v194 rollback] 完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v194 rollback] 失败: {e}')
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
