# -*- coding: utf-8 -*-
"""[v187 2026-11-01] 收货单菜单 / 授权对账

依据:
  docs/specs/spec-receipt-object-model-2026-11-01.md
    §12（页面 / 菜单 / 权限）、§13 实施清单步骤 14

背景（为什么需要这条迁移）:
  与 v181（采购订单菜单对账）同一模式：v186 已建表 / 类型 / 序列 / 权限，
  但菜单与授权段是在该迁移执行之后才补进文件的（DB 记录 checksum 与当前文件
  不一致，迁移框架拒绝重跑）。因此存量环境需要一条**只做幂等对账、不改表结构**
  的迁移，保证：
    · `procurement` 顶层容器存在且启用（缺则补建）
    · `goods-receipt-management` → `/receipts` 菜单存在、父级正确、启用
    · `menu_permissions` 行存在
    · admin / default 权限集拿到 8 个收货权限（5 个 CRUD + 过账 / 冲销 / 取消）
    · 清掉自动生成器可能留下的 `receipt-list` / `receipt_line-list` 孤儿菜单

幂等:
  菜单 / menu_permissions 先查后用；授权按 (permission_set_id, permission_id)
  去重；重复执行打印 [SKIP]。

回滚:
  删除本迁移写入的两个菜单行与 menu_permissions 行（权限与授权由 v186 负责，
  本迁移仅在缺失时补插，回滚不删权限）。
"""
import json
import sqlite3
from pathlib import Path

ROOT_MENU_CODE = 'procurement'
RECEIPT_MENU_CODE = 'goods-receipt-management'

ACTIONS = ('create', 'read', 'update', 'delete', 'list')

#: 授权范围 = 5 个 CRUD + 3 个单据动作（spec §12）
PERMISSION_CODES = tuple(
    'receipt:receipt_{0}'.format(a) for a in ACTIONS
) + ('receipt:receipt_post', 'receipt:receipt_reverse', 'receipt:receipt_cancel')

GRANT_TO_SETS = ('admin', 'default')

MENUS = (
    {
        # 顶层分组容器：无页面、无路径，仅承载子菜单（与 sales 同构）
        'menu_code': ROOT_MENU_CODE,
        'menu_name': '采购',
        'menu_path': '',
        'page_type': '',
        'primary_object_type': '',
        'object_types': [],
        'bo_bindings': [],
        'required_permissions': [],
        'parent_menu': '',
        'icon': 'ShoppingCart',
        'color': '#0ea5e9',
        'description': '采购域：采购订单、需求分配与到货计划',
        'sort_order': 40,
        'show_in_sidebar': 1,
        'data_permission_hint': {},
    },
    {
        'menu_code': RECEIPT_MENU_CODE,
        'menu_name': '收货单',
        'menu_path': '/receipts',
        'page_type': 'object_list',
        'primary_object_type': 'receipt',
        'object_types': ['receipt'],
        'bo_bindings': [
            {'bo_id': 'receipt', 'role': 'primary', 'include_actions': list(ACTIONS)},
        ],
        'required_permissions': [
            'receipt:receipt_{0}'.format(a) for a in ACTIONS],
        'parent_menu': ROOT_MENU_CODE,
        'icon': 'Inbox',
        'color': '#0ea5e9',
        'description': '收货单：抬头 + 收货行子表，按收货组织做数据范围（已过账 ≠ 已入库）',
        'sort_order': 2,
        'show_in_sidebar': 0,
        'data_permission_hint': {
            'resource_types': ['receipt'],
            'message': '建议分配收货单数据权限（按收货组织）',
        },
    },
)

_ORPHAN_MENU_CODES = (
    'receipt-list',
    'receipt_line-list',
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _do_menus(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'menus'):
        print('  - menus 表不存在, 跳过菜单写入')
        return
    for menu in MENUS:
        if conn.execute(
            'SELECT 1 FROM menus WHERE menu_code=?', (menu['menu_code'],)
        ).fetchone():
            print(f"  - [SKIP] 菜单 {menu['menu_code']} 已存在")
        else:
            conn.execute(
                "INSERT INTO menus (menu_code, menu_name, menu_path, page_type, "
                "object_types, primary_object_type, bo_bindings, "
                "required_permissions, parent_menu, icon, color, description, "
                "sort_order, is_active, show_in_sidebar, auto_generated) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 0)",
                (
                    menu['menu_code'], menu['menu_name'], menu['menu_path'],
                    menu['page_type'],
                    json.dumps(menu['object_types'], ensure_ascii=False),
                    menu['primary_object_type'],
                    json.dumps(menu['bo_bindings'], ensure_ascii=False),
                    json.dumps(menu['required_permissions'], ensure_ascii=False),
                    menu['parent_menu'], menu['icon'], menu['color'],
                    menu['description'], menu['sort_order'],
                    menu['show_in_sidebar'],
                ),
            )
            print(f"  - [NEW] 菜单 {menu['menu_code']} ({menu['menu_name']})")

        if _table_exists(conn, 'menu_permissions'):
            cur = conn.execute(
                "INSERT OR IGNORE INTO menu_permissions (menu_code, menu_name, "
                "menu_path, required_permissions, required_any_permission, "
                "parent_menu, icon, sort_order, is_active, data_permission_hint) "
                "VALUES (?, ?, ?, ?, 0, ?, ?, ?, 1, ?)",
                (
                    menu['menu_code'], menu['menu_name'], menu['menu_path'],
                    json.dumps(menu['required_permissions'], ensure_ascii=False),
                    menu['parent_menu'], menu['icon'], menu['sort_order'],
                    json.dumps(menu['data_permission_hint'], ensure_ascii=False),
                ),
            )
            if cur.rowcount:
                print(f"  - [NEW] menu_permissions: {menu['menu_code']}")
            else:
                print(f"  - [SKIP] menu_permissions: {menu['menu_code']} 已存在")


def _do_grants(conn: sqlite3.Connection) -> None:
    if not (_table_exists(conn, 'permission_sets')
            and _table_exists(conn, 'permission_set_permissions')
            and _table_exists(conn, 'permissions')):
        print('  - 权限集相关表缺失, 跳过授权')
        return
    granted = 0
    for set_code in GRANT_TO_SETS:
        row = conn.execute(
            'SELECT id FROM permission_sets WHERE code=? AND is_active=1', (set_code,)
        ).fetchone()
        if not row:
            print(f'  - [SKIP] 权限集 {set_code} 不存在')
            continue
        permission_set_id = row[0]
        for code in PERMISSION_CODES:
            prow = conn.execute('SELECT id FROM permissions WHERE code=?', (code,)).fetchone()
            if not prow:
                print(f'  - [SKIP] 权限 {code} 未落库')
                continue
            if conn.execute(
                'SELECT 1 FROM permission_set_permissions '
                'WHERE permission_set_id=? AND permission_id=?',
                (permission_set_id, prow[0]),
            ).fetchone():
                continue
            conn.execute(
                'INSERT INTO permission_set_permissions '
                '(permission_set_id, permission_id, granted, created_at) '
                "VALUES (?, ?, 1, datetime('now'))",
                (permission_set_id, prow[0]),
            )
            granted += 1
    print(f'  - [SUMMARY] permission_set_permissions: +{granted} 授权')


def _do_cleanup_auto_menu(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'menus'):
        return
    for code in _ORPHAN_MENU_CODES:
        cur = conn.execute(
            'DELETE FROM menus WHERE menu_code=? AND auto_generated=1', (code,))
        if cur.rowcount:
            print(f'  - [DROP] 孤儿自动菜单 {code}')
        if _table_exists(conn, 'menu_permissions'):
            cur = conn.execute(
                'DELETE FROM menu_permissions WHERE menu_code=?', (code,))
            if cur.rowcount:
                print(f'  - [DROP] menu_permissions: {code}')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print(f'[v187] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v187] 开始: 收货单菜单 / 授权对账')
        _do_menus(conn)
        _do_grants(conn)
        _do_cleanup_auto_menu(conn)
        conn.commit()
        print('[v187] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v187] 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v187 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        for menu in MENUS:
            row = conn.execute(
                'SELECT menu_name, menu_path, parent_menu, show_in_sidebar, is_active '
                'FROM menus WHERE menu_code=?', (menu['menu_code'],)
            ).fetchone()
            if not row:
                print(f"  - [FAIL] 菜单 {menu['menu_code']} 缺失")
                ok = False
                continue
            expected = (menu['menu_name'], menu['menu_path'],
                        menu['parent_menu'], menu['show_in_sidebar'], 1)
            if tuple(row) != expected:
                print(f"  - [FAIL] 菜单 {menu['menu_code']} 字段不符: {tuple(row)} != {expected}")
                ok = False
        if conn.execute(
            "SELECT 1 FROM menus WHERE auto_generated=1 "
            "AND menu_code IN ('receipt-list','receipt_line-list')"
        ).fetchone():
            print('  - [FAIL] 仍有孤儿自动菜单')
            ok = False
        if _table_exists(conn, 'menu_permissions'):
            for menu in MENUS:
                if not conn.execute(
                    'SELECT 1 FROM menu_permissions WHERE menu_code=?',
                    (menu['menu_code'],)
                ).fetchone():
                    print(f"  - [FAIL] menu_permissions 缺 {menu['menu_code']}")
                    ok = False
        if _table_exists(conn, 'permissions'):
            for code in PERMISSION_CODES:
                if not conn.execute(
                    'SELECT 1 FROM permissions WHERE code=?', (code,)
                ).fetchone():
                    print(f'  - [FAIL] 缺权限 {code}')
                    ok = False
        print('[v187 verify]', 'OK' if ok else 'FAIL')
        return ok
    finally:
        conn.close()
