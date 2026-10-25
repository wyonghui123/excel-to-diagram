# -*- coding: utf-8 -*-
"""[v121 2026-10-25] 销售订单 菜单与权限交付（波次 0 · 步 5）

背景:
  波次 0 新增两张表（sales_orders / sales_order_lines）。
  订单头是独立单据入口，给一条 object_list 菜单；订单行是子表，
  由 sales_order.ui_view_config.child_sections 内联维护，不建顶层菜单。
  两个 YAML 均声明 skip_auto_menu: true —— 交给 MenuAutoGenerator 只会得到
  parent_menu='' + show_in_sidebar=0 的孤儿行（同 v109 INCOTERM / v112 物料结构）。

本迁移补齐:
    sales（销售，顶层分组）
      └── sales-order-management → 销售订单 /sales-orders  sort 1

  顶层分组用「空 page_type + 空 menu_path + show_in_sidebar=1」的容器形态
  （同 app_warehouse）。前端的 landing 卡片过滤会排除 menu_path 为空与
  有 children 的节点，故该容器只作侧栏分组，不会变成一张空页。

权限口径:
  双段式 {object_id}:{object_id}_{action}（例 sales_order:sales_order_create）。
  两个对象 × 5 个动作 = 10 条；行权限一并落库，供详情内联子表的按钮判定使用。
  迁移可能先于服务启动执行，而 menus.required_permissions 引用不存在的权限码
  会被前端路由守卫整页拦下，故显式落库（v108 已踩过）。

幂等:
  permissions 用 INSERT OR IGNORE；menus / menu_permissions 先按 menu_code
  判存在，缺失才 INSERT。重复执行只输出 [SKIP]。

回滚:
  删除两条菜单（menus + menu_permissions）。**保留** permissions 行 ——
  可能已被角色授予，删除有风险。
"""
import json
import sqlite3
from pathlib import Path


SALES_ROOT_CODE = 'sales'
ORDER_MENU_CODE = 'sales-order-management'

_RANK = ('create', 'read', 'update', 'delete', 'list')

_ACTION_LABEL = {
    'create': '新建', 'read': '查看', 'update': '修改',
    'delete': '删除', 'list': '查询',
}


def _perms(obj_id, label):
    return [(code, f'{_ACTION_LABEL[code.rsplit("_", 1)[-1]]}{label}',
             obj_id, code.rsplit('_', 1)[-1])
            for code in (f'{obj_id}:{obj_id}_{a}' for a in _RANK)]


PERMISSIONS = tuple(
    _perms('sales_order', '销售订单')
    + _perms('sales_order_line', '销售订单行')
)

MENUS = (
    {
        # 顶层分组容器：无页面、无路径，仅承载子菜单
        'menu_code': SALES_ROOT_CODE,
        'menu_name': '销售',
        'menu_path': '',
        'page_type': '',
        'primary_object_type': '',
        'object_types': [],
        'bo_bindings': [],
        'required_permissions': [],
        'parent_menu': '',
        'icon': 'Tickets',
        'color': '#f59e0b',
        'description': '销售域：销售订单及其后续履约单据',
        'sort_order': 30,
        'is_active': 1,
        'show_in_sidebar': 1,
        'auto_generated': 0,
        'data_permission_hint': {},
    },
    {
        'menu_code': ORDER_MENU_CODE,
        'menu_name': '销售订单',
        'menu_path': '/sales-orders',
        'page_type': 'object_list',
        'primary_object_type': 'sales_order',
        'object_types': ['sales_order'],
        'bo_bindings': [
            {'bo_id': 'sales_order', 'role': 'primary', 'include_actions': list(_RANK)},
        ],
        'required_permissions': [
            f'sales_order:sales_order_{a}' for a in _RANK],
        'parent_menu': SALES_ROOT_CODE,
        'icon': 'List',
        'color': '#f59e0b',
        'description': '销售订单：抬头 + 可编辑行子表，按销售组织做数据范围',
        'sort_order': 1,
        'is_active': 1,
        'show_in_sidebar': 0,
        'auto_generated': 0,
        'data_permission_hint': {
            'resource_types': ['sales_order'],
            'message': '建议分配销售订单数据权限（按销售组织）',
        },
    },
)

_ORPHAN_MENU_CODES = (
    # 命名口径来自 menu_auto_generator.generate_object_list_menu:
    #   menu_code = f'{meta_obj.id}-list' —— 对象 id 本身带下划线,
    #   故实际行是 sales_order-list / sales_order_line-list (不是 sales-order-list)。
    'sales_order-list',
    'sales_order_line-list',
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _do_permissions(conn: sqlite3.Connection) -> None:
    """写入 10 条权限码（已存在则忽略，不覆盖既有 name / 授权关系）。"""
    if not _table_exists(conn, 'permissions'):
        print('  - permissions 表不存在, 跳过权限写入')
        return

    created = 0
    for code, name, resource_type, action in PERMISSIONS:
        cur = conn.execute(
            "INSERT OR IGNORE INTO permissions (code, name, resource_type, action) "
            "VALUES (?, ?, ?, ?)",
            (code, name, resource_type, action),
        )
        if cur.rowcount:
            created += 1
            print(f'  - [NEW] 权限 {code} ({name})')

    if created:
        print(f'  - [SUMMARY] permissions: +{created} 新增')
    else:
        print(f'  - [SKIP] {len(PERMISSIONS)} 条权限码均已存在, 无新增')


def _do_menus(conn: sqlite3.Connection) -> None:
    """写入 2 条菜单（menus 表）；已存在则跳过。"""
    if not _table_exists(conn, 'menus'):
        print('  - menus 表不存在, 跳过菜单写入')
        return

    for menu in MENUS:
        if conn.execute(
                "SELECT 1 FROM menus WHERE menu_code = ?", (menu['menu_code'],)
        ).fetchone():
            print(f"  - [SKIP] 菜单 {menu['menu_code']} ({menu['menu_name']}) 已存在")
            continue

        conn.execute(
            "INSERT INTO menus (menu_code, menu_name, menu_path, page_type, "
            "object_types, primary_object_type, bo_bindings, required_permissions, "
            "parent_menu, icon, color, description, sort_order, is_active, "
            "show_in_sidebar, auto_generated) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                menu['menu_code'],
                menu['menu_name'],
                menu['menu_path'],
                menu['page_type'],
                json.dumps(menu['object_types'], ensure_ascii=False),
                menu['primary_object_type'],
                json.dumps(menu['bo_bindings'], ensure_ascii=False),
                json.dumps(menu['required_permissions'], ensure_ascii=False),
                menu['parent_menu'],
                menu['icon'],
                menu['color'],
                menu['description'],
                menu['sort_order'],
                menu['is_active'],
                menu['show_in_sidebar'],
                menu['auto_generated'],
            ),
        )
        print(f"  - [NEW] 菜单 {menu['menu_code']} ({menu['menu_name']}) "
              f"@ {menu['menu_path'] or '(容器)'}, sort_order={menu['sort_order']}")


def _do_menu_permissions(conn: sqlite3.Connection) -> None:
    """同步 menu_permissions（旧接口读这张表），保证两处口径一致。"""
    if not _table_exists(conn, 'menu_permissions'):
        print('  - menu_permissions 表不存在, 跳过同步')
        return

    for menu in MENUS:
        cur = conn.execute(
            "INSERT OR IGNORE INTO menu_permissions (menu_code, menu_name, menu_path, "
            "required_permissions, required_any_permission, parent_menu, icon, "
            "sort_order, is_active, data_permission_hint) "
            "VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?)",
            (
                menu['menu_code'],
                menu['menu_name'],
                menu['menu_path'],
                json.dumps(menu['required_permissions'], ensure_ascii=False),
                menu['parent_menu'],
                menu['icon'],
                menu['sort_order'],
                menu['is_active'],
                json.dumps(menu['data_permission_hint'], ensure_ascii=False),
            ),
        )
        if cur.rowcount:
            print(f"  - [NEW] menu_permissions: {menu['menu_code']}")
        else:
            print(f"  - [SKIP] menu_permissions: {menu['menu_code']} 已存在")


def _do_cleanup_auto_menu(conn: sqlite3.Connection) -> None:
    """清掉自动生成器可能产出的孤儿菜单（* -list）。"""
    if not _table_exists(conn, 'menus'):
        return
    for code in _ORPHAN_MENU_CODES:
        cur = conn.execute(
            "DELETE FROM menus WHERE menu_code = ? AND auto_generated = 1", (code,))
        if cur.rowcount:
            print(f'  - [DROP] 孤儿自动菜单 {code}')
        if _table_exists(conn, 'menu_permissions'):
            cur = conn.execute(
                "DELETE FROM menu_permissions WHERE menu_code = ?", (code,))
            if cur.rowcount:
                print(f'  - [DROP] menu_permissions: {code}')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v121] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v121] 开始: 销售订单 菜单与权限')
        _do_permissions(conn)
        _do_menus(conn)
        _do_menu_permissions(conn)
        _do_cleanup_auto_menu(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v121] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """断言 2 条菜单 / 10 条权限 / menu_permissions 就位。"""
    if not db_path.exists():
        print('[v121 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        for table in ('menus', 'permissions'):
            if not _table_exists(conn, table):
                print(f'[v121 verify] FAIL: {table} 表不存在')
                return False

        for menu in MENUS:
            row = conn.execute(
                "SELECT page_type, is_active, menu_path, primary_object_type, "
                "parent_menu, required_permissions, show_in_sidebar "
                "FROM menus WHERE menu_code = ?",
                (menu['menu_code'],),
            ).fetchone()
            if not row:
                print(f"[v121 verify] FAIL: 菜单 {menu['menu_code']} 不存在")
                return False

            page_type, is_active, menu_path, pot, parent, req, show = row
            if page_type != menu['page_type']:
                print(f"[v121 verify] FAIL: {menu['menu_code']} page_type={page_type!r}")
                return False
            if is_active != 1:
                print(f"[v121 verify] FAIL: {menu['menu_code']} is_active={is_active}")
                return False
            if show != menu['show_in_sidebar']:
                print(f"[v121 verify] FAIL: {menu['menu_code']} "
                      f"show_in_sidebar={show}, 期望 {menu['show_in_sidebar']}")
                return False
            if (menu_path or '') != menu['menu_path']:
                print(f"[v121 verify] FAIL: {menu['menu_code']} menu_path={menu_path!r}")
                return False
            if (pot or '') != menu['primary_object_type']:
                print(f"[v121 verify] FAIL: {menu['menu_code']} "
                      f"primary_object_type={pot!r}")
                return False
            if (parent or '') != menu['parent_menu']:
                print(f"[v121 verify] FAIL: {menu['menu_code']} parent_menu={parent!r}")
                return False

            try:
                codes = json.loads(req or '[]')
            except Exception:
                codes = []
            if sorted(codes) != sorted(menu['required_permissions']):
                print(f"[v121 verify] FAIL: {menu['menu_code']} "
                      f"required_permissions={codes}")
                return False

        missing = []
        for code, _name, _rt, _action in PERMISSIONS:
            if not conn.execute(
                    "SELECT 1 FROM permissions WHERE code = ?", (code,)).fetchone():
                missing.append(code)
        if missing:
            print(f'[v121 verify] FAIL: 缺权限码 {missing}')
            return False
        malformed = [c for c, _n, _r, _a in PERMISSIONS
                     if c.count(':') != 1
                     or not c.split(':')[1].startswith(c.split(':')[0] + '_')]
        if malformed:
            print(f'[v121 verify] FAIL: 非双段式权限码 {malformed}')
            return False

        if _table_exists(conn, 'menu_permissions'):
            for menu in MENUS:
                cnt = conn.execute(
                    "SELECT COUNT(*) FROM menu_permissions WHERE menu_code = ?",
                    (menu['menu_code'],)).fetchone()[0]
                if cnt < 1:
                    print(f"[v121 verify] FAIL: menu_permissions 缺 {menu['menu_code']}")
                    return False

        for code in _ORPHAN_MENU_CODES:
            row = conn.execute(
                "SELECT 1 FROM menus WHERE menu_code = ?", (code,)).fetchone()
            if row:
                print(f'[v121 verify] FAIL: 仍存在孤儿菜单 {code}')
                return False

        print(f'[v121 verify] OK: 销售分组挂 {SALES_ROOT_CODE} 下 1 条订单菜单, '
              f'{len(PERMISSIONS)} 条双段式权限, menu_permissions 齐备, 无孤儿菜单')
        return True
    finally:
        conn.close()


def rollback(db_path: Path, skip_backup: bool = False) -> bool:
    """移除菜单；permissions 行保留（可能已被角色授予）。"""
    if not db_path.exists():
        print(f'[v121] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        codes = tuple(menu['menu_code'] for menu in MENUS)
        placeholders = ', '.join('?' * len(codes))
        if _table_exists(conn, 'menus'):
            cur = conn.execute(
                f'DELETE FROM menus WHERE menu_code IN ({placeholders})', codes)
            print(f'  - [DROP] menus: {cur.rowcount} 条')
        if _table_exists(conn, 'menu_permissions'):
            cur = conn.execute(
                f'DELETE FROM menu_permissions WHERE menu_code IN ({placeholders})', codes)
            print(f'  - [DROP] menu_permissions: {cur.rowcount} 条')
        print('  - [KEEP] permissions 行保留 (可能已被角色授予)')
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v121] rollback 失败: {e}')
        raise
    finally:
        conn.close()


downgrade = rollback


if __name__ == '__main__':
    import sys
    from meta.core.db_path import get_meta_db_path

    _args = [a for a in sys.argv[1:] if a != '--rollback']
    _db = Path(_args[0]) if _args else Path(get_meta_db_path())
    if '--rollback' in sys.argv[1:]:
        _ok = rollback(_db)
        print(f'[v121] rollback: {"OK" if _ok else "FAIL"}')
    else:
        _ok = migrate(_db)
        print(f'[v121] migrate: {"OK" if _ok else "FAIL"}')
        _v = verify(_db)
        print(f'[v121] verify: {"PASS" if _v else "FAIL"}')
