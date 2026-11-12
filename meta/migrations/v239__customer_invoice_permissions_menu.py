# -*- coding: utf-8 -*-
"""v239 —— 销售发票权限补齐与菜单分组（B6）。

背景：
  研究建议 P2-9：权限补 print 与独立 credit_memo 动作；菜单归入应收。
  v236 的权限 tuple 已扩到 7 个动作，但旧库执行过 v236 后不会自动补写。

内容：
  1. 复用 v236 的权限写入与授权逻辑，补 print / credit_memo 并授予 admin / default。
  2. menus 表存在但没有 customer_invoice-list 行时先补插（菜单自动生成器在
     应用启动后才 INSERT OR IGNORE，迁移阶段不能假定该行已存在）；随后若存在
     「应收」父菜单，把 customer_invoice-list 挂入其下（sort_order=50），
     无父菜单则保持顶层（不阻断）。
  3. verify：两个权限存在；存在父菜单时须已挂载。
  4. rollback：删除两个权限及授权，菜单恢复顶层。

幂等：INSERT OR IGNORE；菜单 INSERT/UPDATE 可重复执行。
"""

import json
import sqlite3
from pathlib import Path

from meta.migrations import v236__customer_invoice as v236

PERMISSION_TABLE = 'permissions'
GRANT_TABLE = 'permission_set_permissions'
MENU_TABLE = 'menus'
MENU_PERMISSION_TABLE = 'menu_permissions'
MENU_CODE = 'customer_invoice-list'
PARENT_HINT = '应收'
MENU_SORT_ORDER = 50

PERMISSION_CODES = (
    'customer_invoice:customer_invoice_print',
    'customer_invoice:customer_invoice_credit_memo',
)

#: 与 v236 种子的 7 个动作保持一致（全式权限码）
MENU_ACTIONS = ('view', 'create', 'post', 'reverse', 'cancel',
                'print', 'credit_memo')
MENU_PERMISSIONS = [
    'customer_invoice:customer_invoice_{0}'.format(action)
    for action in MENU_ACTIONS
]

#: 菜单行初值（字段与 menu_auto_generator.persist_to_db 对齐；
#: 迁移阶段按 menus 实际列做交集，兼容精简测试夹具）
MENU_ROW = {
    'menu_code': MENU_CODE,
    'menu_name': '销售发票管理',
    'menu_path': '/customer-invoice',
    'page_type': 'object_list',
    'object_types': json.dumps(['customer_invoice'], ensure_ascii=False),
    'primary_object_type': 'customer_invoice',
    'bo_bindings': json.dumps([{
        'bo_id': 'customer_invoice',
        'role': 'primary',
        'include_actions': list(MENU_ACTIONS),
    }], ensure_ascii=False),
    'required_permissions': json.dumps(MENU_PERMISSIONS, ensure_ascii=False),
    'required_any_permission': False,
    'data_permission_hint': json.dumps({
        'resource_types': ['customer_invoice'],
        'message': '建议分配销售发票数据权限（按发票所属组织）',
    }, ensure_ascii=False),
    'page_config': json.dumps({}, ensure_ascii=False),
    'parent_menu': '',
    'icon': 'Document',
    'color': '',
    'description': '销售发票：发货/手工开票、过账生成期次、红冲',
    'sort_order': 99,
    'is_active': 1,
    'show_in_sidebar': 0,
    'auto_generated': 0,
}


def _connect(db_path):
    return sqlite3.connect(str(db_path))


def _table_exists(conn, table):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        [table]).fetchone()
    return row is not None


def _columns(conn, table):
    return [row[1] for row in conn.execute('PRAGMA table_info(%s)' % table)]


def _find_parent_menu(conn):
    if not _table_exists(conn, MENU_TABLE):
        return None
    row = conn.execute(
        'SELECT menu_code FROM %s WHERE menu_name LIKE ? AND menu_code != ? '
        'ORDER BY sort_order, menu_code LIMIT 1' % MENU_TABLE,
        ['%' + PARENT_HINT + '%', MENU_CODE]).fetchone()
    return row[0] if row else None


def _insert_menu_if_missing(conn):
    """迁移阶段补插菜单行（应用启动后的 auto_generator 用 INSERT OR IGNORE，
    届时不会覆盖已存在行）。仅写入当前库 menus 表实际存在的列。"""
    if conn.execute('SELECT 1 FROM %s WHERE menu_code = ?' % MENU_TABLE,
                    [MENU_CODE]).fetchone():
        return False
    available = set(_columns(conn, MENU_TABLE))
    row = {key: value for key, value in MENU_ROW.items() if key in available}
    if 'menu_code' not in row:
        return False
    columns = list(row)
    conn.execute(
        'INSERT INTO %s (%s) VALUES (%s)' % (
            MENU_TABLE, ', '.join(columns),
            ', '.join('?' for _ in columns)),
        [row[key] for key in columns])
    print('[v239] menu %s inserted' % MENU_CODE)
    return True


def _sync_menu_permissions(conn, parent, sort_order):
    if not _table_exists(conn, MENU_PERMISSION_TABLE):
        return
    available = set(_columns(conn, MENU_PERMISSION_TABLE))
    values = {
        'menu_code': MENU_CODE,
        'menu_name': MENU_ROW['menu_name'],
        'menu_path': MENU_ROW['menu_path'],
        'required_permissions': MENU_ROW['required_permissions'],
        'required_any_permission': 0,
        'parent_menu': parent or '',
        'icon': MENU_ROW['icon'],
        'sort_order': sort_order,
        'is_active': 1,
        'data_permission_hint': MENU_ROW['data_permission_hint'],
    }
    columns = [key for key in values if key in available]
    if 'menu_code' not in columns:
        return
    conn.execute(
        'INSERT OR IGNORE INTO %s (%s) VALUES (%s)' % (
            MENU_PERMISSION_TABLE, ', '.join(columns),
            ', '.join('?' for _ in columns)),
        [values[key] for key in columns])
    conn.execute(
        'UPDATE %s SET parent_menu = ?, sort_order = ? WHERE menu_code = ?'
        % MENU_PERMISSION_TABLE, [parent or '', sort_order, MENU_CODE])


def _attach_menu(conn):
    _insert_menu_if_missing(conn)
    parent = _find_parent_menu(conn)
    sort_order = MENU_SORT_ORDER if parent else 99
    if not parent:
        print('[v239] no parent menu matched %r, keep top-level' % PARENT_HINT)
    else:
        conn.execute(
            'UPDATE %s SET parent_menu = ?, sort_order = ? WHERE menu_code = ?'
            % MENU_TABLE, [parent, sort_order, MENU_CODE])
        print('[v239] menu %s -> %s' % (MENU_CODE, parent))
    _sync_menu_permissions(conn, parent, sort_order)
    return parent


def upgrade(db_path, skip_backup=True):
    path = Path(db_path)
    if not path.exists():
        print('[v239] SKIP: database not found: %s' % path)
        return False

    conn = _connect(path)
    try:
        if not _table_exists(conn, PERMISSION_TABLE):
            print('[v239] SKIP: permissions 表不存在')
            return False
        v236._do_permissions(conn)
        v236._do_grants(conn)
        _attach_menu(conn)
        conn.commit()
        return True
    finally:
        conn.close()


def verify(db_path):
    path = Path(db_path)
    if not path.exists():
        return False

    conn = _connect(path)
    try:
        if not _table_exists(conn, PERMISSION_TABLE):
            return False
        existing = {row[0] for row in conn.execute(
            'SELECT code FROM %s' % PERMISSION_TABLE)}
        missing = [code for code in PERMISSION_CODES if code not in existing]
        if missing:
            print('[v239] verify: 缺少权限 %s' % ', '.join(missing))
            return False

        parent = _find_parent_menu(conn)
        if parent:
            row = conn.execute(
                'SELECT parent_menu FROM %s WHERE menu_code = ?' % MENU_TABLE,
                [MENU_CODE]).fetchone()
            if not row or row[0] != parent:
                print('[v239] verify: 菜单 %s 未挂载到 %s'
                      % (MENU_CODE, parent))
                return False
        return True
    finally:
        conn.close()


def rollback(db_path):
    path = Path(db_path)
    if not path.exists():
        return False

    conn = _connect(path)
    try:
        if not _table_exists(conn, PERMISSION_TABLE):
            return False
        placeholders = ','.join('?' for _ in PERMISSION_CODES)
        ids = [row[0] for row in conn.execute(
            'SELECT id FROM %s WHERE code IN (%s)'
            % (PERMISSION_TABLE, placeholders), list(PERMISSION_CODES))]

        if _table_exists(conn, GRANT_TABLE):
            cols = _columns(conn, GRANT_TABLE)
            if 'permission_code' in cols:
                conn.execute(
                    'DELETE FROM %s WHERE permission_code IN (%s)'
                    % (GRANT_TABLE, placeholders), list(PERMISSION_CODES))
            elif ids:
                id_placeholders = ','.join('?' for _ in ids)
                conn.execute(
                    'DELETE FROM %s WHERE permission_id IN (%s)'
                    % (GRANT_TABLE, id_placeholders), ids)

        conn.execute('DELETE FROM %s WHERE code IN (%s)'
                     % (PERMISSION_TABLE, placeholders), list(PERMISSION_CODES))
        if _table_exists(conn, MENU_TABLE):
            conn.execute(
                "UPDATE %s SET parent_menu = '', sort_order = 99 "
                'WHERE menu_code = ?' % MENU_TABLE, [MENU_CODE])
        if _table_exists(conn, MENU_PERMISSION_TABLE):
            conn.execute(
                "UPDATE %s SET parent_menu = '', sort_order = 99 "
                'WHERE menu_code = ?' % MENU_PERMISSION_TABLE, [MENU_CODE])
        conn.commit()
        return True
    finally:
        conn.close()


migrate = upgrade


if __name__ == '__main__':
    import sys

    db = sys.argv[1] if len(sys.argv) > 1 else 'meta/architecture.db'
    upgrade(db)
