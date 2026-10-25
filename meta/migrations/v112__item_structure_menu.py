# -*- coding: utf-8 -*-
"""[v112 2026-10-25] 物料结构 菜单与权限交付

背景:
  结构层新增两张表（item_structures / item_structure_lines）。
  结构头是独立主数据入口，给一条 object_list 菜单；结构行是子表，
  由 ui_view_config.child_sections 内联维护，不建顶层菜单。
  两者均声明 skip_auto_menu: true —— 交给 MenuAutoGenerator 只会得到
  parent_menu='' + show_in_sidebar=0 的孤儿行（同 v109 INCOTERM / v110 属性 / v111 税务）。

本迁移补齐:
    item_structure → 物料结构管理 /item-structures  sort 83

权限口径:
  双段式 {object_id}:{object_id}_{action}（例 item_structure:item_structure_create）。
  两个对象 × 5 个动作 = 10 条；行权限一并落库，供详情内联表格的按钮判定使用。

落位:
  挂 master-data（主数据）下，show_in_sidebar=0。
  sort_order 83：该组现存最大值为 82（v111 税务分类）。

幂等:
  permissions 用 INSERT OR IGNORE；menus / menu_permissions 先按 menu_code
  判存在，缺失才 INSERT。重复执行只输出 [SKIP]。

回滚:
  删除菜单（menus + menu_permissions）。**保留** permissions 行 ——
  可能已被角色授予，删除有风险。
"""
import json
import sqlite3
from pathlib import Path


PARENT_MENU = 'master-data'
ITEM_STRUCTURE_MENU_CODE = 'item-structure-management'

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
    _perms('item_structure', '物料结构')
    + _perms('item_structure_line', '物料结构行')
)

MENUS = (
    {
        'menu_code': ITEM_STRUCTURE_MENU_CODE,
        'menu_name': '物料结构管理',
        'menu_path': '/item-structures',
        'page_type': 'object_list',
        'primary_object_type': 'item_structure',
        'object_types': ['item_structure'],
        'bo_bindings': [
            {'bo_id': 'item_structure', 'role': 'primary', 'include_actions': list(_RANK)},
        ],
        'required_permissions': [
            f'item_structure:item_structure_{a}' for a in _RANK],
        'parent_menu': PARENT_MENU,
        'icon': 'Connection',
        'color': '#0ea5e9',
        'description': '物料结构（BOM / 选配模型）：按物料、用途、替代结构与版本维护组件行',
        'sort_order': 83,
        'is_active': 1,
        'show_in_sidebar': 0,
        'auto_generated': 0,
        'data_permission_hint': {
            'resource_types': ['item_structure'],
            'message': '建议分配物料结构数据权限',
        },
    },
)

_ORPHAN_MENU_CODES = (
    'item-structure-list',
    'item-structure-line-list',
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
    """写入 1 条菜单（menus 表）；已存在则跳过。"""
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
              f"@ {menu['menu_path']}, sort_order={menu['sort_order']}")


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
    """清掉自动生成器可能产出的孤儿菜单（* -list）。

    两个 YAML 均声明 skip_auto_menu: true，生成器此后不再产出这些行；
    但对象建表时若生成器先跑过一次，会留下 parent_menu='' + auto_generated=1 的孤儿行。
    """
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
        print(f'[v112] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v112] 开始: 物料结构 菜单与权限')
        _do_permissions(conn)
        _do_menus(conn)
        _do_menu_permissions(conn)
        _do_cleanup_auto_menu(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v112] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """断言 1 条菜单 / 10 条权限 / menu_permissions 就位。"""
    if not db_path.exists():
        print('[v112 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, 'menus'):
            print('[v112 verify] FAIL: menus 表不存在')
            return False
        if not _table_exists(conn, 'permissions'):
            print('[v112 verify] FAIL: permissions 表不存在')
            return False

        for menu in MENUS:
            row = conn.execute(
                "SELECT page_type, is_active, menu_path, primary_object_type, "
                "parent_menu, required_permissions, show_in_sidebar "
                "FROM menus WHERE menu_code = ?",
                (menu['menu_code'],),
            ).fetchone()
            if not row:
                print(f"[v112 verify] FAIL: 菜单 {menu['menu_code']} 不存在")
                return False

            page_type, is_active, menu_path, pot, parent, req, show = row
            if page_type != menu['page_type']:
                print(f"[v112 verify] FAIL: {menu['menu_code']} page_type={page_type}")
                return False
            if is_active != 1:
                print(f"[v112 verify] FAIL: {menu['menu_code']} is_active={is_active}")
                return False
            if show != 0:
                print(f"[v112 verify] FAIL: {menu['menu_code']} show_in_sidebar={show}, 期望 0")
                return False
            if menu_path != menu['menu_path']:
                print(f"[v112 verify] FAIL: {menu['menu_code']} menu_path={menu_path}")
                return False
            if pot != menu['primary_object_type']:
                print(f"[v112 verify] FAIL: {menu['menu_code']} "
                      f"primary_object_type={pot}")
                return False
            if parent != PARENT_MENU:
                print(f"[v112 verify] FAIL: {menu['menu_code']} parent_menu={parent}")
                return False

            try:
                codes = json.loads(req or '[]')
            except Exception:
                codes = []
            if not codes:
                print(f"[v112 verify] FAIL: {menu['menu_code']} required_permissions 为空")
                return False

        missing = []
        for code, _name, _rt, _action in PERMISSIONS:
            if not conn.execute(
                    "SELECT 1 FROM permissions WHERE code = ?", (code,)).fetchone():
                missing.append(code)
        if missing:
            print(f'[v112 verify] FAIL: 缺权限码 {missing}')
            return False
        malformed = [c for c, _n, _r, _a in PERMISSIONS
                     if c.count(':') != 1 or not c.split(':')[1].startswith(c.split(':')[0] + '_')]
        if malformed:
            print(f'[v112 verify] FAIL: 非双段式权限码 {malformed}')
            return False

        if _table_exists(conn, 'menu_permissions'):
            for menu in MENUS:
                cnt = conn.execute(
                    "SELECT COUNT(*) FROM menu_permissions WHERE menu_code = ?",
                    (menu['menu_code'],)).fetchone()[0]
                if cnt < 1:
                    print(f"[v112 verify] FAIL: menu_permissions 缺 {menu['menu_code']}")
                    return False

        for code in _ORPHAN_MENU_CODES:
            row = conn.execute(
                "SELECT 1 FROM menus WHERE menu_code = ?", (code,)).fetchone()
            if row:
                print(f'[v112 verify] FAIL: 仍存在孤儿菜单 {code}')
                return False

        print('[v112 verify] OK: 1 条菜单挂 master-data, 10 条双段式权限, '
              'menu_permissions 齐备, 无孤儿菜单')
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    """移除菜单；permissions 行保留（可能已被角色授予）。"""
    if not db_path.exists():
        print(f'[v112] DB 不存在: {db_path}')
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
        print(f'[v112] downgrade 失败: {e}')
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    _ok = migrate(_db)
    print(f'[v112] migrate: {"OK" if _ok else "FAIL"}')
    _v = verify(_db)
    print(f'[v112] verify: {"PASS" if _v else "FAIL"}')
