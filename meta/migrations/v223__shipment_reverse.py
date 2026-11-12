# -*- coding: utf-8 -*-
"""v223 - 交货单数据错误冲销：reversed 状态字段与冲销权限

依据: docs/specs/spec-doc-flow-end-to-end-2026-11-05.md §5.1 / §6 阶段 5 / D6

背景:
- 阶段 5 已让发货确认写入库存事务与 DOC_FLOW 边；但 shipped / delivered
  之后没有数据错误冲销入口（cancel 仅 draft / released，R-DN-2）。
- 退货（业务事实）继续走反向交货；本迁移只为「数据错误红冲」补终态与权限。
- 反向能力复用现有原语：InventoryPostingService.reverse_by_source、
  reverse_edges_by_source、SerialNumberService.reverse_serial_event、
  HandlingUnitService.reverse_document、预留 unfulfill_by_demand。

动作:
  1. shipments 补列 reversed_at / reversal_reason（库列可空，幂等先查后用）
  2. permissions 种子 shipment:shipment_reverse（双段式），授予 admin / default

回滚:
  删除本迁移种的权限与授权；新增列保留（YAML 声明，删列需重建表）。

[ALLOW_DESTRUCTIVE] rollback 仅 DELETE 权限/授权行，不改单据数据。
"""
from __future__ import annotations

import os
import sqlite3

MIGRATION_NAME = 'v223__shipment_reverse'

SHIPMENT_TABLE = 'shipments'

#: (列名, DDL 片段)
COLUMNS = (
    ('reversed_at', 'DATETIME NULL'),
    ('reversal_reason', 'VARCHAR(200) NULL'),
)

PERMISSION = (
    'shipment:shipment_reverse', '交货单冲销', 'shipment', 'reverse',
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


def _do_columns(conn):
    if not _table_exists(conn, SHIPMENT_TABLE):
        print('  - [SKIP] 缺表 %s，跳过补列' % SHIPMENT_TABLE)
        return
    have = _columns(conn, SHIPMENT_TABLE)
    for name, ddl in COLUMNS:
        if name in have:
            print('  - [SKIP] 列 %s.%s 已存在' % (SHIPMENT_TABLE, name))
            continue
        conn.execute('ALTER TABLE %s ADD COLUMN %s %s'
                     % (SHIPMENT_TABLE, name, ddl))
        print('  - [ALTER] 列 %s.%s' % (SHIPMENT_TABLE, name))


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


def _do_upgrade(conn):
    _do_columns(conn)
    _do_permission(conn)
    _do_grants(conn)
    return True


def migrate(db_path, skip_backup=False):
    print('[v223] 交货单冲销终态字段与权限')
    if not os.path.exists(db_path):
        print('  - [SKIP] 库不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(db_path)
    try:
        _do_upgrade(conn)
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
        cols = _columns(conn, SHIPMENT_TABLE)
        columns_ok = all(name in cols for name, _ddl in COLUMNS)
        has_permissions = _table_exists(conn, 'permissions')
        permission_ok = True
        if has_permissions:
            permission_ok = bool(conn.execute(
                'SELECT 1 FROM permissions WHERE code=?',
                [PERMISSION[0]]).fetchone())
        checks = {
            'columns': columns_ok,
            'permission': permission_ok,
        }
        return {'ok': all(checks.values()), 'checks': checks}
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
        print('[v223 rollback] 已删权限与授权（列保留：YAML 声明）')
        return True
    finally:
        conn.close()


downgrade = rollback
