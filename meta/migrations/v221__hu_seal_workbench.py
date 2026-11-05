# -*- coding: utf-8 -*-
"""v221：包装容器查询页 / 封箱作业台（权限 + 菜单）。

依据: docs/specs/p6-serial-number-model/spec.md §11.16.6
  · 两个 custom_page 菜单（静态路由在 src/router/modules/business.js 注册）。
  · 权限：handling_unit:handling_unit_seal / handling_unit:handling_unit_unseal。
    admin 全授；default 只保留 v211 已授的 read（不授 seal / unseal）。
  · 菜单退役口径：rollback 置 is_active=0 并删 menu_permissions 行，不物理删菜单。
"""

import json
import sqlite3
from pathlib import Path

PERMISSIONS = (
    ('handling_unit:handling_unit_seal', '包装容器封箱', 'handling_unit', 'seal'),
    ('handling_unit:handling_unit_unseal', '包装容器解封', 'handling_unit',
     'unseal'),
)

GRANT_TO_SETS = ('admin',)

# 库存域根菜单：v202 / v211 的菜单都挂在 inventory 下，但历史迁移未创建该根节点。
# 根节点缺失时子菜单会挂到顶层且 show_in_sidebar=0 ⇒ 侧栏不可见；这里补建。
ROOT_MENU = {
    'menu_code': 'inventory',
    'menu_name': '库存',
    'menu_path': '',
    'icon': 'Boxes',
    'color': '#22c55e',
    'description': '库存域：包装容器、序列号与库存作业',
    'sort_order': 50,
}

MENUS = (
    {
        'menu_code': 'handling-unit-docs',
        'menu_name': '包装容器查询',
        'menu_path': '/warehouse/handling-unit-docs',
        'parent_menu': 'inventory',
        'required_permissions': ['handling_unit:handling_unit_read',
                                 'handling_unit:handling_unit_list'],
        'icon': 'Search',
        'color': '#0ea5e9',
        'sort_order': 11,
        'description': '单据查容器 / 容器查单据（只读）',
    },
    {
        'menu_code': 'handling-unit-seal',
        'menu_name': '封箱作业',
        'menu_path': '/warehouse/handling-unit-seal',
        'parent_menu': 'inventory',
        'required_permissions': ['handling_unit:handling_unit_read',
                                 'handling_unit:handling_unit_seal'],
        'icon': 'Lock',
        'color': '#f59e0b',
        'sort_order': 12,
        'description': '扫码预检、封箱、批量封箱、解封',
    },
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _do_permissions(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'permissions'):
        print('  - permissions 表不存在, 跳过权限写入')
        return
    created = 0
    for code, name, resource_type, action in PERMISSIONS:
        cur = conn.execute(
            'INSERT OR IGNORE INTO permissions (code, name, resource_type, action) '
            'VALUES (?, ?, ?, ?)', (code, name, resource_type, action))
        if cur.rowcount:
            created += 1
            print('  - [NEW] 权限 %s' % code)
    print('  - [SUMMARY] permissions: +%s' % created)


def _do_grants(conn: sqlite3.Connection) -> None:
    if not (_table_exists(conn, 'permissions')
            and _table_exists(conn, 'permission_sets')
            and _table_exists(conn, 'permission_set_permissions')):
        print('  - 权限集相关表缺失, 跳过授权')
        return
    cols = {row[1] for row in
            conn.execute('PRAGMA table_info(permission_set_permissions)')}
    id_col = ('permission_set_id' if 'permission_set_id' in cols
              else 'role_id' if 'role_id' in cols else '')
    if not id_col:
        return
    has_code_col = 'permission_code' in cols
    granted = 0
    for set_code in GRANT_TO_SETS:
        row = conn.execute(
            'SELECT id FROM permission_sets WHERE code=? AND is_active=1',
            (set_code,)).fetchone()
        if not row:
            print('  - [WARN] 权限集 %s 不存在, 跳过授权' % set_code)
            continue
        set_id = row[0]
        for code, _name, _rtype, _action in PERMISSIONS:
            prow = conn.execute(
                'SELECT id FROM permissions WHERE code=?', (code,)).fetchone()
            if not prow:
                continue
            if conn.execute(
                    'SELECT 1 FROM permission_set_permissions WHERE %s=? '
                    'AND permission_id=?' % id_col,
                    (set_id, prow[0])).fetchone():
                continue
            if has_code_col:
                conn.execute(
                    'INSERT INTO permission_set_permissions '
                    '(%s, permission_code, permission_id, granted, created_at) '
                    "VALUES (?, ?, ?, 1, datetime('now'))" % id_col,
                    (set_id, code, prow[0]))
            else:
                conn.execute(
                    'INSERT INTO permission_set_permissions '
                    '(%s, permission_id, granted, created_at) '
                    "VALUES (?, ?, 1, datetime('now'))" % id_col,
                    (set_id, prow[0]))
            granted += 1
    print('  - [SUMMARY] permission_set_permissions: +%s' % granted)


def _resolve_parent(conn: sqlite3.Connection, preferred: str) -> str:
    if conn.execute('SELECT 1 FROM menus WHERE menu_code=?',
                    (preferred,)).fetchone():
        return preferred
    print('  - [WARN] 父菜单 %s 不存在，菜单挂顶层' % preferred)
    return ''


def _ensure_root_menu(conn: sqlite3.Connection) -> None:
    """补建/激活库存域根菜单（子菜单可见的前提）。"""
    if not _table_exists(conn, 'menus'):
        return
    existing = conn.execute(
        'SELECT is_active, show_in_sidebar FROM menus WHERE menu_code=?',
        (ROOT_MENU['menu_code'],)).fetchone()
    if existing:
        conn.execute(
            'UPDATE menus SET is_active=1, show_in_sidebar=1, parent_menu=? '
            'WHERE menu_code=?', ('', ROOT_MENU['menu_code']))
        print('  - [OK] 根菜单 %s 已激活' % ROOT_MENU['menu_code'])
    else:
        conn.execute(
            'INSERT INTO menus (menu_code, menu_name, menu_path, page_type, '
            'object_types, primary_object_type, bo_bindings, '
            'required_permissions, parent_menu, icon, color, description, '
            "sort_order, is_active, show_in_sidebar, auto_generated) "
            "VALUES (?, ?, '', '', '[]', NULL, '[]', '[]', '', ?, ?, ?, ?, "
            "1, 1, 0)",
            (ROOT_MENU['menu_code'], ROOT_MENU['menu_name'],
             ROOT_MENU['icon'], ROOT_MENU['color'], ROOT_MENU['description'],
             ROOT_MENU['sort_order']))
        print('  - [NEW] 根菜单 %s' % ROOT_MENU['menu_code'])
    if _table_exists(conn, 'menu_permissions'):
        conn.execute(
            'INSERT OR IGNORE INTO menu_permissions (menu_code, menu_name, '
            'menu_path, required_permissions, required_any_permission, '
            'parent_menu, icon, sort_order, is_active, data_permission_hint) '
            "VALUES (?, ?, '', '[]', 0, '', ?, ?, 1, NULL)",
            (ROOT_MENU['menu_code'], ROOT_MENU['menu_name'],
             ROOT_MENU['icon'], ROOT_MENU['sort_order']))


def _next_sort_order(conn: sqlite3.Connection, parent: str,
                     preferred: int) -> int:
    row = conn.execute(
        "SELECT MAX(sort_order) FROM menus WHERE COALESCE(parent_menu, '') = ?",
        (parent,)).fetchone()
    current = int(row[0] or 0) if row else 0
    return max(int(preferred), current + 1)


def _upsert_menu(conn: sqlite3.Connection, menu: dict) -> None:
    parent = _resolve_parent(conn, menu['parent_menu'])
    sort_order = _next_sort_order(conn, parent, menu['sort_order'])
    required = json.dumps(menu['required_permissions'], ensure_ascii=False)
    existing = conn.execute(
        'SELECT id, page_type, is_active, required_permissions FROM menus '
        'WHERE menu_code=?', (menu['menu_code'],)).fetchone()
    if existing:
        conn.execute(
            'UPDATE menus SET menu_name=?, menu_path=?, page_type=?, '
            'object_types=?, primary_object_type=?, bo_bindings=?, '
            'required_permissions=?, parent_menu=?, icon=?, color=?, '
            'description=?, is_active=1, show_in_sidebar=0 '
            'WHERE menu_code=?',
            (menu['menu_name'], menu['menu_path'], 'custom_page', '[]', None,
             '[]', required, parent, menu['icon'], menu['color'],
             menu['description'], menu['menu_code']))
        print('  - [UPDATE] 菜单 %s' % menu['menu_code'])
    else:
        conn.execute(
            'INSERT INTO menus (menu_code, menu_name, menu_path, page_type, '
            'object_types, primary_object_type, bo_bindings, '
            'required_permissions, parent_menu, icon, color, description, '
            'sort_order, is_active, show_in_sidebar, auto_generated) '
            "VALUES (?, ?, ?, 'custom_page', '[]', NULL, '[]', ?, ?, ?, ?, ?, "
            "?, 1, 0, 0)",
            (menu['menu_code'], menu['menu_name'], menu['menu_path'], required,
             parent, menu['icon'], menu['color'], menu['description'],
             sort_order))
        print('  - [NEW] 菜单 %s (sort=%s)' % (menu['menu_code'], sort_order))

    if _table_exists(conn, 'menu_permissions'):
        row = conn.execute(
            'SELECT 1 FROM menu_permissions WHERE menu_code=?',
            (menu['menu_code'],)).fetchone()
        if row:
            conn.execute(
                'UPDATE menu_permissions SET menu_name=?, menu_path=?, '
                'required_permissions=?, parent_menu=?, icon=?, sort_order=?, '
                'is_active=1 WHERE menu_code=?',
                (menu['menu_name'], menu['menu_path'], required, parent,
                 menu['icon'], sort_order, menu['menu_code']))
        else:
            conn.execute(
                'INSERT INTO menu_permissions (menu_code, menu_name, menu_path, '
                'required_permissions, required_any_permission, parent_menu, '
                'icon, sort_order, is_active, data_permission_hint) '
                'VALUES (?, ?, ?, ?, 0, ?, ?, ?, 1, NULL)',
                (menu['menu_code'], menu['menu_name'], menu['menu_path'],
                 required, parent, menu['icon'], sort_order))
        print('  - [OK] menu_permissions: %s' % menu['menu_code'])


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print('[v221] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v221] 开始: 包装容器查询 / 封箱作业菜单')
        _do_permissions(conn)
        _do_grants(conn)
        if _table_exists(conn, 'menus'):
            _ensure_root_menu(conn)
            for menu in MENUS:
                _upsert_menu(conn, menu)
        else:
            print('  - menus 表不存在, 跳过菜单写入')
        conn.commit()
        print('[v221] 完成')
        return True
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        print('[v221] 失败: %s' % e)
        return False
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v221 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        for code, _name, _rtype, _action in PERMISSIONS:
            if not conn.execute('SELECT 1 FROM permissions WHERE code=?',
                                (code,)).fetchone():
                print('[v221 verify] FAIL: 缺权限 %s' % code)
                return False
        root = conn.execute(
            'SELECT is_active, show_in_sidebar FROM menus WHERE menu_code=?',
            (ROOT_MENU['menu_code'],)).fetchone()
        if not root or not root[0] or not root[1]:
            print('[v221 verify] FAIL: 根菜单 %s 缺失或不可见'
                  % ROOT_MENU['menu_code'])
            return False
        for menu in MENUS:
            row = conn.execute(
                'SELECT is_active, page_type FROM menus WHERE menu_code=?',
                (menu['menu_code'],)).fetchone()
            if not row or not row[0] or row[1] != 'custom_page':
                print('[v221 verify] FAIL: 菜单 %s' % menu['menu_code'])
                return False
        print('[v221 verify] OK')
        return True
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v221 rollback] DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        for menu in MENUS:
            conn.execute('UPDATE menus SET is_active=0 WHERE menu_code=?',
                         (menu['menu_code'],))
            if _table_exists(conn, 'menu_permissions'):
                conn.execute('DELETE FROM menu_permissions WHERE menu_code=?',
                             (menu['menu_code'],))
        conn.commit()
        print('[v221 rollback] 菜单已退役')
        return True
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        print('[v221 rollback] 失败: %s' % e)
        return False
    finally:
        conn.close()


downgrade = rollback
