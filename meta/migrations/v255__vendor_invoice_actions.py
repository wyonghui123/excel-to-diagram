# -*- coding: utf-8 -*-
"""[v255 2026-11-11] 采购发票对象模型（W4：权限 / 菜单 / 幽灵元数据退役）

依据:
  docs/specs/spec-vendor-invoice-object-model-2026-11-11.md §7 权限 / §8 菜单 / §13 W4
  .trae/rules/scenarios/5-development/meta-menu-retirement.md

内容:
  1. permissions 单段式权限码（v249 归一后口径）:
       vendor_invoice:       create/read/update/delete/list/submit/post/match/
                             override_match/override_duplicate/cancel/reverse/
                             create_credit_memo/create_debit_memo（14）
       vendor_invoice_line:  create/read/update/delete/list（5）
     授予 admin / default 权限集。
  2. menus 一条「采购发票管理」挂到 procurement 下：
       vendor-invoice-management → /vendor-invoices
     同步 menu_permissions（required_permissions / bo_bindings）。
  3. 退役自动生成菜单 vendor_invoice-list / vendor_invoice_line-list：
     用 is_active=0 而非 DELETE（meta-menu-retirement 铁律），并清理其孤儿
     menu_permissions 行。
  4. 幽灵元数据（应付发票 AP_INVOICE / BO_AP_INV、付款申请 BO_PAYMENT_REQ）
     已从 init_and_seed.py / generate_test_data.py 移除；本迁移对存量库兜底：
     仅当镜像表存在 status 列时置为 inactive（不 DELETE，保留审计痕迹）。
     实测 service_modules / business_objects 无 status 列，此时跳过退役。

幂等: 权限 INSERT OR IGNORE；菜单先查后插再 UPDATE；退役 UPDATE 幂等。
回滚: 删权限与授权；菜单 is_active=0（不物理删除）。
"""

import json
import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v255__vendor_invoice_actions'

PERMISSION_TABLE = 'permissions'
PERMISSION_SET_TABLE = 'permission_sets'
GRANT_TABLE = 'permission_set_permissions'
MENU_TABLE = 'menus'
MENU_PERMISSION_TABLE = 'menu_permissions'
SET_MENU_PERMISSION_TABLE = 'permission_set_menu_permissions'
SERVICE_MODULE_TABLE = 'service_modules'
BUSINESS_OBJECT_TABLE = 'business_objects'

SCOPE_BO = 'vendor_invoice'
SCOPE_LINE_BO = 'vendor_invoice_line'

GRANT_TO_SETS = ('admin', 'default')

HEADER_ACTIONS = (
    ('create', '创建采购发票'),
    ('read', '查看采购发票'),
    ('update', '修改采购发票'),
    ('delete', '删除采购发票'),
    ('list', '查询采购发票'),
    ('submit', '提交采购发票'),
    ('post', '过账采购发票'),
    ('match', '执行发票匹配'),
    ('override_match', '匹配差异例外放行'),
    ('override_duplicate', '重复发票例外放行'),
    ('cancel', '取消采购发票'),
    ('reverse', '冲销采购发票'),
    ('create_credit_memo', '生成采购贷项凭证'),
    ('create_debit_memo', '生成采购借项通知单'),
)

LINE_ACTIONS = (
    ('create', '创建采购发票行'),
    ('read', '查看采购发票行'),
    ('update', '修改采购发票行'),
    ('delete', '删除采购发票行'),
    ('list', '查询采购发票行'),
)

PERMISSIONS = (
    tuple(('%s:%s' % (SCOPE_BO, action), name, SCOPE_BO, action)
          for action, name in HEADER_ACTIONS)
    + tuple(('%s:%s' % (SCOPE_LINE_BO, action), name, SCOPE_LINE_BO, action)
            for action, name in LINE_ACTIONS)
)

PERMISSION_CODES = tuple(item[0] for item in PERMISSIONS)

ROOT_MENU_CODE = 'procurement'
MENU_CODE = 'vendor-invoice-management'
MENU_ACTIONS = tuple(action for action, _name in HEADER_ACTIONS)

RETIRED_MENU_CODES = (
    'vendor_invoice-list',
    'vendor_invoice_line-list',
)

#: 幽灵元数据（存量库兜底退役）
GHOST_SM_CODES = ('AP_INVOICE',)
GHOST_BO_CODES = ('BO_AP_INV', 'BO_PAYMENT_REQ')

MENU_ROW = {
    'menu_code': MENU_CODE,
    'menu_name': '采购发票管理',
    'menu_path': '/vendor-invoices',
    'page_type': 'object_list',
    'primary_object_type': SCOPE_BO,
    'object_types': [SCOPE_BO, SCOPE_LINE_BO],
    'bo_bindings': [
        {'bo_id': SCOPE_BO, 'role': 'primary',
         'include_actions': list(MENU_ACTIONS)},
        {'bo_id': SCOPE_LINE_BO, 'role': 'secondary',
         'include_actions': ['read', 'list', 'create', 'update', 'delete']},
    ],
    'required_permissions': [
        '%s:read' % SCOPE_BO,
        '%s:list' % SCOPE_BO,
    ],
    'parent_menu': ROOT_MENU_CODE,
    'icon': 'Receipt',
    'color': '#f59e0b',
    'description': '采购发票：PO/收货匹配、过账应付、贷项/借项与取消冲销',
    'sort_order': 6,
    'show_in_sidebar': 1,
    'data_permission_hint': {
        'resource_types': [SCOPE_BO],
        'message': '建议按采购组织/会计组织分配采购发票数据权限',
    },
}


# --------------------------------------------------------------------- helpers

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


def _dump(values):
    return json.dumps(values, ensure_ascii=False)


# ------------------------------------------------------------------ permissions

def _do_permissions(conn):
    if not _table_exists(conn, PERMISSION_TABLE):
        print('[v255] SKIP: permissions 表不存在（未写权限）')
        return 0
    created = 0
    for code, name, resource_type, action in PERMISSIONS:
        cur = conn.execute(
            'INSERT OR IGNORE INTO permissions (code, name, resource_type, action) '
            'VALUES (?, ?, ?, ?)', (code, name, resource_type, action))
        if cur.rowcount:
            created += 1
            print('[v255] CREATE: 权限 %s' % code)
    return created


def _do_grants(conn):
    if not (_table_exists(conn, PERMISSION_TABLE)
            and _table_exists(conn, PERMISSION_SET_TABLE)
            and _table_exists(conn, GRANT_TABLE)):
        print('[v255] SKIP: 权限集相关表缺失（未授权）')
        return 0
    cols = _columns(conn, GRANT_TABLE)
    if 'permission_set_id' in cols:
        id_col = 'permission_set_id'
    elif 'role_id' in cols:
        id_col = 'role_id'
    else:
        print('[v255] SKIP: 授权表无 permission_set_id/role_id')
        return 0
    has_code_col = 'permission_code' in cols
    granted = 0
    for set_code in GRANT_TO_SETS:
        row = conn.execute(
            'SELECT id FROM %s WHERE code = ? AND is_active = 1'
            % PERMISSION_SET_TABLE, [set_code]).fetchone()
        if not row:
            continue
        set_id = int(row[0])
        for code in PERMISSION_CODES:
            prow = conn.execute(
                'SELECT id FROM %s WHERE code = ?' % PERMISSION_TABLE,
                [code]).fetchone()
            if not prow:
                continue
            params = [set_id, int(prow[0])]
            where = '%s = ? AND permission_id = ?' % id_col
            if has_code_col:
                where += ' AND permission_code = ?'
                params.append(code)
            if conn.execute('SELECT 1 FROM %s WHERE %s'
                            % (GRANT_TABLE, where), params).fetchone():
                continue
            if has_code_col:
                conn.execute(
                    'INSERT INTO %s (%s, permission_code, permission_id, '
                    "granted, created_at) VALUES (?, ?, ?, 1, datetime('now'))"
                    % (GRANT_TABLE, id_col),
                    [set_id, code, int(prow[0])])
            else:
                conn.execute(
                    'INSERT INTO %s (%s, permission_id, granted, created_at) '
                    "VALUES (?, ?, 1, datetime('now'))" % (GRANT_TABLE, id_col),
                    [set_id, int(prow[0])])
            granted += 1
    return granted


# ----------------------------------------------------------------------- menus

def _do_menu(conn):
    if not _table_exists(conn, MENU_TABLE):
        print('[v255] SKIP: menus 表不存在（未写菜单）')
        return
    available = _columns(conn, MENU_TABLE)
    values = {
        'menu_code': MENU_ROW['menu_code'],
        'menu_name': MENU_ROW['menu_name'],
        'menu_path': MENU_ROW['menu_path'],
        'page_type': MENU_ROW['page_type'],
        'primary_object_type': MENU_ROW['primary_object_type'],
        'object_types': _dump(MENU_ROW['object_types']),
        'bo_bindings': _dump(MENU_ROW['bo_bindings']),
        'required_permissions': _dump(MENU_ROW['required_permissions']),
        'parent_menu': MENU_ROW['parent_menu'],
        'icon': MENU_ROW['icon'],
        'color': MENU_ROW['color'],
        'description': MENU_ROW['description'],
        'sort_order': MENU_ROW['sort_order'],
        'is_active': 1,
        'show_in_sidebar': MENU_ROW['show_in_sidebar'],
        'auto_generated': 0,
    }
    row = {key: value for key, value in values.items() if key in available}
    if 'menu_code' not in row:
        print('[v255] SKIP: menus 表缺 menu_code 列')
        return
    exists = conn.execute(
        'SELECT 1 FROM %s WHERE menu_code = ?' % MENU_TABLE,
        [MENU_CODE]).fetchone()
    if exists:
        update_cols = [key for key in row if key != 'menu_code']
        conn.execute(
            'UPDATE %s SET %s WHERE menu_code = ?'
            % (MENU_TABLE, ', '.join('%s = ?' % key for key in update_cols)),
            [row[key] for key in update_cols] + [MENU_CODE])
        print('[v255] UPDATE: 菜单 %s' % MENU_CODE)
    else:
        columns = list(row)
        conn.execute(
            'INSERT INTO %s (%s) VALUES (%s)'
            % (MENU_TABLE, ', '.join(columns),
               ', '.join('?' for _ in columns)),
            [row[key] for key in columns])
        print('[v255] CREATE: 菜单 %s' % MENU_CODE)
    _sync_menu_permissions(conn)


def _sync_menu_permissions(conn):
    if not _table_exists(conn, MENU_PERMISSION_TABLE):
        return
    available = _columns(conn, MENU_PERMISSION_TABLE)
    values = {
        'menu_code': MENU_CODE,
        'menu_name': MENU_ROW['menu_name'],
        'menu_path': MENU_ROW['menu_path'],
        'required_permissions': _dump(MENU_ROW['required_permissions']),
        'required_any_permission': 0,
        'parent_menu': MENU_ROW['parent_menu'],
        'icon': MENU_ROW['icon'],
        'sort_order': MENU_ROW['sort_order'],
        'is_active': 1,
        'data_permission_hint': _dump(MENU_ROW['data_permission_hint']),
    }
    row = {key: value for key, value in values.items() if key in available}
    if 'menu_code' not in row:
        return
    exists = conn.execute(
        'SELECT 1 FROM %s WHERE menu_code = ?' % MENU_PERMISSION_TABLE,
        [MENU_CODE]).fetchone()
    if exists:
        update_cols = [key for key in row if key != 'menu_code']
        conn.execute(
            'UPDATE %s SET %s WHERE menu_code = ?'
            % (MENU_PERMISSION_TABLE,
               ', '.join('%s = ?' % key for key in update_cols)),
            [row[key] for key in update_cols] + [MENU_CODE])
        print('[v255] UPDATE: menu_permissions %s' % MENU_CODE)
    else:
        columns = list(row)
        conn.execute(
            'INSERT INTO %s (%s) VALUES (%s)'
            % (MENU_PERMISSION_TABLE, ', '.join(columns),
               ', '.join('?' for _ in columns)),
            [row[key] for key in columns])
        print('[v255] CREATE: menu_permissions %s' % MENU_CODE)


def _retire_auto_menus(conn):
    """旧自动菜单退役：is_active=0（不 DELETE），并清孤儿 menu_permissions。"""
    if _table_exists(conn, MENU_TABLE) and 'is_active' in _columns(conn, MENU_TABLE):
        for code in RETIRED_MENU_CODES:
            cur = conn.execute(
                'UPDATE %s SET is_active = 0 WHERE menu_code = ?' % MENU_TABLE,
                [code])
            if cur.rowcount:
                print('[v255] RETIRE: 菜单 %s（is_active=0）' % code)
    _cleanup_orphan_menu_permissions(conn)


def _cleanup_orphan_menu_permissions(conn):
    if not _table_exists(conn, MENU_PERMISSION_TABLE):
        return
    if 'menu_code' not in _columns(conn, MENU_PERMISSION_TABLE):
        return
    placeholders = ', '.join('?' for _ in RETIRED_MENU_CODES)
    if _table_exists(conn, MENU_TABLE) and 'menu_code' in _columns(conn, MENU_TABLE):
        orphan_where = (
            'menu_code IN (%s) AND menu_code NOT IN '
            '(SELECT menu_code FROM %s)' % (placeholders, MENU_TABLE))
        params = list(RETIRED_MENU_CODES)
    else:
        orphan_where = 'menu_code IN (%s)' % placeholders
        params = list(RETIRED_MENU_CODES)
    cur = conn.execute(
        'DELETE FROM %s WHERE %s' % (MENU_PERMISSION_TABLE, orphan_where), params)
    if cur.rowcount:
        print('[v255] CLEAN: menu_permissions 孤儿 %d 行' % cur.rowcount)


# --------------------------------------------------------------- ghost retire

def _retire_ghost_metadata(conn):
    """存量库兜底退役幽灵元数据。

    注意：service_modules / business_objects 是元数据镜像表，实际库中**没有 status 列**
    （列清单见 .runtime/probe_v255.py 探测结果），因此只能在存在 status 列时退役；
    无 status 列时依赖 init_and_seed.py / generate_test_data.py 侧移除（本迁移不删行，
    避免破坏镜像表的重建一致性）。
    """
    if _table_exists(conn, SERVICE_MODULE_TABLE):
        sm_cols = _columns(conn, SERVICE_MODULE_TABLE)
        if 'status' in sm_cols:
            for code in GHOST_SM_CODES:
                cur = conn.execute(
                    "UPDATE %s SET status = 'inactive [retired-by-v255]' "
                    "WHERE code = ? AND (status IS NULL OR status NOT LIKE ?)"
                    % SERVICE_MODULE_TABLE, [code, '%retired-by-v255%'])
                if cur.rowcount:
                    print('[v255] RETIRE: 服务模块 %s' % code)
        else:
            print('[v255] SKIP: service_modules 无 status 列（镜像表，退役依赖种子脚本）')
    if _table_exists(conn, BUSINESS_OBJECT_TABLE):
        cols = _columns(conn, BUSINESS_OBJECT_TABLE)
        if 'status' in cols:
            for code in GHOST_BO_CODES:
                cur = conn.execute(
                    "UPDATE %s SET status = 'inactive' "
                    "WHERE code = ? AND status != 'inactive'"
                    % BUSINESS_OBJECT_TABLE, [code])
                if cur.rowcount:
                    print('[v255] RETIRE: 业务对象 %s' % code)


# ------------------------------------------------------------------- migrate

def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    db_path = Path(db_path)
    print('[v255] 开始: 采购发票权限 / 菜单 / 幽灵元数据退役')
    conn = _connect(db_path)
    try:
        _do_permissions(conn)
        _do_grants(conn)
        _do_menu(conn)
        _retire_auto_menus(conn)
        _retire_ghost_metadata(conn)
        conn.commit()
        print('[v255] 完成: 采购发票权限 / 菜单 / 幽灵元数据退役')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# -------------------------------------------------------------------- verify

def verify(db_path: Path) -> bool:
    db_path = Path(db_path)
    problems = []
    conn = _connect(db_path)
    try:
        if not _table_exists(conn, PERMISSION_TABLE):
            problems.append('缺少表 permissions')
        else:
            existing = {row[0] for row in conn.execute(
                'SELECT code FROM %s' % PERMISSION_TABLE)}
            missing = [code for code in PERMISSION_CODES if code not in existing]
            if missing:
                problems.append('缺少权限 %s' % ', '.join(missing))

        if not _table_exists(conn, MENU_TABLE):
            problems.append('缺少表 menus')
        else:
            row = conn.execute(
                'SELECT parent_menu, is_active FROM %s WHERE menu_code = ?'
                % MENU_TABLE, [MENU_CODE]).fetchone()
            if not row:
                problems.append('缺少菜单 %s' % MENU_CODE)
            elif row[0] != ROOT_MENU_CODE or int(row[1] or 0) != 1:
                problems.append('菜单 %s 未启用或未挂到 %s (parent=%r active=%r)'
                                % (MENU_CODE, ROOT_MENU_CODE, row[0], row[1]))
            for code in RETIRED_MENU_CODES:
                retired = conn.execute(
                    'SELECT is_active FROM %s WHERE menu_code = ?'
                    % MENU_TABLE, [code]).fetchone()
                if retired and int(retired[0] or 0) != 0:
                    problems.append('旧菜单 %s 未退役（is_active=%r）'
                                    % (code, retired[0]))

        for table in (MENU_PERMISSION_TABLE, SET_MENU_PERMISSION_TABLE):
            if not _table_exists(conn, table):
                continue
            if 'menu_code' not in _columns(conn, table):
                continue
            placeholders = ', '.join('?' for _ in RETIRED_MENU_CODES)
            orphan = conn.execute(
                'SELECT COUNT(*) FROM %s WHERE menu_code IN (%s) '
                'AND menu_code NOT IN (SELECT menu_code FROM %s)'
                % (table, placeholders, MENU_TABLE),
                list(RETIRED_MENU_CODES)).fetchone()
            if orphan and int(orphan[0]) > 0:
                problems.append('%s 存在 %d 条退役菜单孤儿行'
                                % (table, int(orphan[0])))

        if (_table_exists(conn, SERVICE_MODULE_TABLE)
                and 'status' in _columns(conn, SERVICE_MODULE_TABLE)):
            for code in GHOST_SM_CODES:
                row = conn.execute(
                    'SELECT status FROM %s WHERE code = ?' % SERVICE_MODULE_TABLE,
                    [code]).fetchone()
                if row and 'retired-by-v255' not in (row[0] or ''):
                    problems.append('幽灵服务模块 %s 未退役' % code)
        if _table_exists(conn, BUSINESS_OBJECT_TABLE) and 'status' in _columns(
                conn, BUSINESS_OBJECT_TABLE):
            for code in GHOST_BO_CODES:
                row = conn.execute(
                    'SELECT status FROM %s WHERE code = ?'
                    % BUSINESS_OBJECT_TABLE, [code]).fetchone()
                if row and row[0] != 'inactive':
                    problems.append('幽灵业务对象 %s 未退役（status=%r）'
                                    % (code, row[0]))
    finally:
        conn.close()

    if problems:
        for problem in problems:
            print('[v255] FAIL: %s' % problem)
        return False
    print('[v255] PASS: 19 权限 / 菜单 / 旧菜单退役 / 幽灵元数据退役')
    return True


# ------------------------------------------------------------------ rollback

def rollback(db_path: Path) -> bool:
    db_path = Path(db_path)
    print('[v255] 开始: 回滚采购发票权限 / 菜单')
    conn = _connect(db_path)
    try:
        if _table_exists(conn, GRANT_TABLE):
            cols = _columns(conn, GRANT_TABLE)
            placeholders = ', '.join('?' for _ in PERMISSION_CODES)
            if 'permission_code' in cols:
                conn.execute(
                    'DELETE FROM %s WHERE permission_code IN (%s)'
                    % (GRANT_TABLE, placeholders), list(PERMISSION_CODES))
            elif 'permission_id' in cols:
                conn.execute(
                    'DELETE FROM %s WHERE permission_id IN '
                    '(SELECT id FROM %s WHERE code IN (%s))'
                    % (GRANT_TABLE, PERMISSION_TABLE, placeholders),
                    list(PERMISSION_CODES))
        if _table_exists(conn, PERMISSION_TABLE):
            placeholders = ', '.join('?' for _ in PERMISSION_CODES)
            conn.execute('DELETE FROM %s WHERE code IN (%s)'
                         % (PERMISSION_TABLE, placeholders), list(PERMISSION_CODES))
        if _table_exists(conn, MENU_PERMISSION_TABLE):
            conn.execute('DELETE FROM %s WHERE menu_code = ?'
                         % MENU_PERMISSION_TABLE, [MENU_CODE])
        if _table_exists(conn, MENU_TABLE):
            conn.execute('UPDATE %s SET is_active = 0 WHERE menu_code = ?'
                         % MENU_TABLE, [MENU_CODE])
        conn.commit()
        print('[v255] 完成: 已删除权限并停用菜单')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()