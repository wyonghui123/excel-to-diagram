# -*- coding: utf-8 -*-
"""v234 —— 销售发票权限补齐与菜单分组（B6）。

背景：
  研究建议 P2-9：权限补 print 与独立 credit_memo 动作；菜单归入应收。
  v231 的权限 tuple 已扩到 7 个动作，但旧库执行过 v231 后不会自动补写。

内容：
  1. 复用 v231 的权限写入与授权逻辑，补 print / credit_memo 并授予 admin / default。
  2. 若 menus 表存在「应收」父菜单，把 customer_invoice-list 挂入其下
     （sort_order=50）；无父菜单则保持顶层（不阻断）。
  3. verify：两个权限存在；存在父菜单时须已挂载。
  4. rollback：删除两个权限及授权，菜单恢复顶层。

幂等：INSERT OR IGNORE；菜单 UPDATE 可重复执行。
"""

import sqlite3
from pathlib import Path

from meta.migrations import v231__customer_invoice as v231

PERMISSION_TABLE = 'permissions'
GRANT_TABLE = 'permission_set_permissions'
MENU_TABLE = 'menus'
MENU_CODE = 'customer_invoice-list'
PARENT_HINT = '应收'
MENU_SORT_ORDER = 50

PERMISSION_CODES = (
    'customer_invoice:customer_invoice_print',
    'customer_invoice:customer_invoice_credit_memo',
)


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


def _attach_menu(conn):
    parent = _find_parent_menu(conn)
    if not parent:
        print('[v234] no parent menu matched %r, keep top-level' % PARENT_HINT)
        return None
    conn.execute(
        'UPDATE %s SET parent_menu = ?, sort_order = ? WHERE menu_code = ?'
        % MENU_TABLE, [parent, MENU_SORT_ORDER, MENU_CODE])
    print('[v234] menu %s -> %s' % (MENU_CODE, parent))
    return parent


def upgrade(db_path, skip_backup=True):
    path = Path(db_path)
    if not path.exists():
        print('[v234] SKIP: database not found: %s' % path)
        return False

    conn = _connect(path)
    try:
        if not _table_exists(conn, PERMISSION_TABLE):
            print('[v234] SKIP: permissions 表不存在')
            return False
        v231._do_permissions(conn)
        v231._do_grants(conn)
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
            print('[v234] verify: 缺少权限 %s' % ', '.join(missing))
            return False

        parent = _find_parent_menu(conn)
        if parent:
            row = conn.execute(
                'SELECT parent_menu FROM %s WHERE menu_code = ?' % MENU_TABLE,
                [MENU_CODE]).fetchone()
            if not row or row[0] != parent:
                print('[v234] verify: 菜单 %s 未挂载到 %s'
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
        conn.commit()
        return True
    finally:
        conn.close()


migrate = upgrade


if __name__ == '__main__':
    import sys

    db = sys.argv[1] if len(sys.argv) > 1 else 'meta/architecture.db'
    upgrade(db)
