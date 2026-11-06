# -*- coding: utf-8 -*-
"""v226 - 调拨发货红冲权限

依据: docs/specs/spec-reversal-platform-2026-11-06.md §12 阶段 D5

背景:
- 调拨单此前只有取消（发货前）与收货侧红冲；发货后录错没有入口（G4）。
- D5 通过 ReversalOrchestrator 原地红冲发货事实（库存 / 序列号 / HU / 边 / 行），
  单据进入 `reversed` 终态；不改表结构，仅补动作权限。

动作:
  1. permissions 种子 transfer_order:transfer_order_reverse_shipment，授予 admin / default

回滚:
  删除本迁移种的权限与授权。
"""
from __future__ import annotations

import os
import sqlite3

MIGRATION_NAME = 'v226__transfer_order_reverse'

PERMISSION = (
    'transfer_order:transfer_order_reverse_shipment',
    '调拨发货红冲',
    'transfer_order',
    'reverse_shipment',
)

GRANT_TO_SETS = ('admin', 'default')


def _table_exists(conn, name):
    return bool(conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", [name]
    ).fetchone())


def _columns(conn, table):
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(
        'PRAGMA table_info(%s)' % table).fetchall()}


def _do_permission(conn):
    if not _table_exists(conn, 'permissions'):
        print('  - [SKIP] permissions 表不存在')
        return
    code, name, resource_type, action = PERMISSION
    cur = conn.execute(
        'INSERT OR IGNORE INTO permissions (code, name, resource_type, action) '
        'VALUES (?, ?, ?, ?)', [code, name, resource_type, action])
    if cur.rowcount:
        print('  - [NEW] 权限 %s（%s）' % (code, name))
    else:
        print('  - [SKIP] 权限 %s 已存在' % code)


def _do_grants(conn):
    tables = ('permissions', 'permission_sets', 'permission_set_permissions')
    if not all(_table_exists(conn, name) for name in tables):
        print('  - [SKIP] 权限集相关表缺失，跳过授权')
        return
    cols = _columns(conn, 'permission_set_permissions')
    if 'permission_set_id' in cols:
        id_col = 'permission_set_id'
    elif 'role_id' in cols:
        id_col = 'role_id'
    else:
        print('  - [SKIP] permission_set_permissions 无 permission_set_id/role_id')
        return
    has_code_col = 'permission_code' in cols
    code = PERMISSION[0]
    row = conn.execute('SELECT id FROM permissions WHERE code=?', [code]).fetchone()
    if not row:
        print('  - [SKIP] 权限行缺失，跳过授权')
        return
    permission_id = row[0]
    granted = 0
    for set_code in GRANT_TO_SETS:
        set_row = conn.execute(
            'SELECT id FROM permission_sets WHERE code=? AND is_active=1',
            [set_code]).fetchone()
        if not set_row:
            continue
        permission_set_id = set_row[0]
        params = [permission_set_id, permission_id]
        where = '%s = ? AND permission_id = ?' % id_col
        if has_code_col:
            where += ' AND permission_code = ?'
            params.append(code)
        if conn.execute('SELECT 1 FROM permission_set_permissions WHERE '
                        + where, params).fetchone():
            continue
        insert_cols = [id_col, 'permission_id']
        insert_vals = [permission_set_id, permission_id]
        if has_code_col:
            insert_cols.append('permission_code')
            insert_vals.append(code)
        conn.execute(
            'INSERT INTO permission_set_permissions (%s) VALUES (%s)'
            % (', '.join(insert_cols), ', '.join('?' * len(insert_vals))),
            insert_vals)
        granted += 1
    print('  - [GRANT] %s 授予权限集: +%d' % (code, granted))


def migrate(db_path, skip_backup=False):
    print('[v226] 调拨发货红冲权限')
    if not os.path.exists(db_path):
        print('  - [SKIP] 库不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(db_path)
    try:
        _do_permission(conn)
        _do_grants(conn)
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def verify(db_path):
    if not os.path.exists(db_path):
        return {'ok': False, 'error': 'db not found'}
    conn = sqlite3.connect(db_path)
    try:
        has_permissions = _table_exists(conn, 'permissions')
        permission_ok = True
        if has_permissions:
            permission_ok = bool(conn.execute(
                'SELECT 1 FROM permissions WHERE code=?',
                [PERMISSION[0]]).fetchone())
        return {'ok': permission_ok, 'checks': {'permission': permission_ok}}
    finally:
        conn.close()


def rollback(db_path):
    if not os.path.exists(db_path):
        return False
    conn = sqlite3.connect(db_path)
    try:
        code = PERMISSION[0]
        row = conn.execute(
            'SELECT id FROM permissions WHERE code=?', [code]).fetchone() \
            if _table_exists(conn, 'permissions') else None
        if row and _table_exists(conn, 'permission_set_permissions'):
            conn.execute(
                'DELETE FROM permission_set_permissions WHERE permission_id=?',
                [row[0]])
        if row:
            conn.execute('DELETE FROM permissions WHERE id=?', [row[0]])
        conn.commit()
        print('[v226 rollback] 已删权限与授权')
        return True
    finally:
        conn.close()


downgrade = rollback
