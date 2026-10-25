# -*- coding: utf-8 -*-
"""[v109 2026-10-25] 国际贸易术语（Incoterms）菜单与权限交付

背景:
  销售域新增字典对象 incoterms（ICC Incoterms 2020 的 11 条术语）。
  其 ui_view_config 声明了 skip_auto_menu: true —— 若交给 MenuAutoGenerator,
  得到的是 parent_menu='' + show_in_sidebar=0 的孤儿行, 导航树上不可达
  （同 MD-MENU 2026-10-11 / SRC-MENU 2026-10-24 / SALES-CFG v108）。

本迁移补齐 1 条主数据子页菜单:
    incoterm → 国际贸易术语  /incoterms  sort 78

权限口径:
  双段式 {object_id}:{object_id}_{action}, 与 permissions 表既有码一致
  （例 sales_line_type:sales_line_type_create）。共 5 条:
  create / read / update / delete / list。

  为什么迁移里也写 permissions:
    menus.required_permissions 引用不存在的权限码会被前端路由守卫
    （every 判定）整页拦下, 故显式落库, 不依赖启动时的
    PermissionSyncService 补码时机。

落位:
  挂 master-data(主数据, page_type=multi_object_hub) 下, show_in_sidebar=0。
  sort_order 78: 该组现存最大值 77(payment-term-management)。

幂等:
  permissions 用 INSERT OR IGNORE; menus / menu_permissions 先按 menu_code
  判存在, 缺失才 INSERT。重复执行只输出 [SKIP]。

回滚:
  删除 1 条菜单（menus + menu_permissions）。**保留** permissions 行 ——
  可能已被角色授予, 删除有风险。
"""
import json
import sqlite3
from pathlib import Path


PARENT_MENU = 'master-data'
MENU_CODE = 'incoterm-management'
OBJECT_ID = 'incoterm'

PERMISSIONS = (
    (f'{OBJECT_ID}:{OBJECT_ID}_create', '新建国际贸易术语',
     OBJECT_ID, f'{OBJECT_ID}_create'),
    (f'{OBJECT_ID}:{OBJECT_ID}_read', '查看国际贸易术语',
     OBJECT_ID, f'{OBJECT_ID}_read'),
    (f'{OBJECT_ID}:{OBJECT_ID}_update', '修改国际贸易术语',
     OBJECT_ID, f'{OBJECT_ID}_update'),
    (f'{OBJECT_ID}:{OBJECT_ID}_delete', '删除国际贸易术语',
     OBJECT_ID, f'{OBJECT_ID}_delete'),
    (f'{OBJECT_ID}:{OBJECT_ID}_list', '查询国际贸易术语列表',
     OBJECT_ID, f'{OBJECT_ID}_list'),
)

_RANK = ('create', 'read', 'update', 'delete', 'list')

MENUS = (
    {
        'menu_code': MENU_CODE,
        'menu_name': '国际贸易术语',
        'menu_path': '/incoterms',
        'page_type': 'object_list',
        'primary_object_type': OBJECT_ID,
        'object_types': [OBJECT_ID],
        'bo_bindings': [
            {'bo_id': OBJECT_ID, 'role': 'primary',
             'include_actions': list(_RANK)},
        ],
        'required_permissions': [f'{OBJECT_ID}:{OBJECT_ID}_{a}' for a in _RANK],
        'parent_menu': PARENT_MENU,
        'icon': 'List',
        'color': '#0ea5e9',
        'description': 'Incoterms 术语字典：风险转移点与买卖双方责任划分',
        'sort_order': 78,
        'is_active': 1,
        'show_in_sidebar': 0,
        'auto_generated': 0,
        'data_permission_hint': {
            'resource_types': [OBJECT_ID],
            'message': '建议分配国际贸易术语数据权限',
        },
    },
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _do_permissions(conn: sqlite3.Connection) -> None:
    """写入 5 条权限码（已存在则忽略，不覆盖既有 name / 授权关系）。"""
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
        print('  - [SKIP] 5 条权限码均已存在, 无新增')


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
    """清掉自动生成器产出的孤儿菜单 incoterm-list。

    incoterm.yaml 已声明 skip_auto_menu: true, 生成器此后不再产出该行;
    但对象建表时若生成器先跑过一次, 会留下 parent_menu='' + auto_generated=1
    的孤儿行 (init_menu_permissions 的 7.6 只清 auto_generated=0 的未声明菜单)。
    留着会与手工菜单 /incoterms 形成两条指向同一对象的入口。
    """
    if not _table_exists(conn, 'menus'):
        return
    cur = conn.execute(
        "DELETE FROM menus WHERE menu_code = 'incoterm-list' AND auto_generated = 1")
    if cur.rowcount:
        print('  - [DROP] 孤儿自动菜单 incoterm-list')
    if _table_exists(conn, 'menu_permissions'):
        cur = conn.execute(
            "DELETE FROM menu_permissions WHERE menu_code = 'incoterm-list'")
        if cur.rowcount:
            print('  - [DROP] menu_permissions: incoterm-list')



def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v109] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v109] 开始: 国际贸易术语 菜单与权限')
        _do_permissions(conn)
        _do_menus(conn)
        _do_menu_permissions(conn)
        _do_cleanup_auto_menu(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v109] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """菜单形态正确，且 required_permissions 全部能在 permissions 表查到。"""
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, 'menus'):
            print('[v109 verify] FAIL: menus 表不存在')
            return False
        if not _table_exists(conn, 'permissions'):
            print('[v109 verify] FAIL: permissions 表不存在')
            return False

        for menu in MENUS:
            row = conn.execute(
                "SELECT page_type, is_active, menu_path, primary_object_type, "
                "parent_menu, required_permissions, show_in_sidebar "
                "FROM menus WHERE menu_code = ?",
                (menu['menu_code'],),
            ).fetchone()
            if not row:
                print(f"[v109 verify] FAIL: 菜单 {menu['menu_code']} 不存在")
                return False

            page_type, is_active, menu_path, pot, parent, req, show = row
            if page_type != menu['page_type']:
                print(f"[v109 verify] FAIL: {menu['menu_code']} page_type={page_type}, "
                      f"期望 {menu['page_type']}")
                return False
            if is_active != 1:
                print(f"[v109 verify] FAIL: {menu['menu_code']} is_active={is_active}, "
                      f"期望 1")
                return False
            if show != 0:
                print(f"[v109 verify] FAIL: {menu['menu_code']} "
                      f"show_in_sidebar={show}, 期望 0（父 hub 的子页）")
                return False
            if menu_path != menu['menu_path']:
                print(f"[v109 verify] FAIL: {menu['menu_code']} menu_path={menu_path}, "
                      f"期望 {menu['menu_path']}")
                return False
            if pot != menu['primary_object_type']:
                print(f"[v109 verify] FAIL: {menu['menu_code']} "
                      f"primary_object_type={pot}, 期望 {menu['primary_object_type']}")
                return False
            if parent != PARENT_MENU:
                print(f"[v109 verify] FAIL: {menu['menu_code']} parent_menu={parent}, "
                      f"期望 {PARENT_MENU}")
                return False

            try:
                codes = json.loads(req or '[]')
            except Exception:
                codes = []
            missing = []
            for code in codes:
                if not conn.execute(
                        "SELECT 1 FROM permissions WHERE code = ?", (code,)
                ).fetchone():
                    missing.append(code)
            if missing:
                print(f"[v109 verify] FAIL: {menu['menu_code']} "
                      f"required_permissions 含不存在的权限码 {missing}")
                return False
            if not codes:
                print(f"[v109 verify] FAIL: {menu['menu_code']} required_permissions 为空")
                return False

        print('[v109 verify] OK: 1 条菜单为 object_list 且挂 master-data, '
              '5 条权限码全部有效 (/incoterms)')
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    """移除菜单；permissions 行保留（可能已被角色授予）。"""
    if not db_path.exists():
        print(f'[v109] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        codes = tuple(menu['menu_code'] for menu in MENUS)
        placeholders = ', '.join('?' * len(codes))
        if _table_exists(conn, 'menus'):
            cur = conn.execute(
                f'DELETE FROM menus WHERE menu_code IN ({placeholders})', codes
            )
            print(f'  - [DROP] menus: {cur.rowcount} 条')
        if _table_exists(conn, 'menu_permissions'):
            cur = conn.execute(
                f'DELETE FROM menu_permissions WHERE menu_code IN ({placeholders})',
                codes,
            )
            print(f'  - [DROP] menu_permissions: {cur.rowcount} 条')
        print('  - [KEEP] permissions 行保留 (可能已被角色授予)')
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v109] downgrade 失败: {e}')
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    _ok = migrate(_db)
    print(f'[v109] migrate: {"OK" if _ok else "FAIL"}')
    _v = verify(_db)
    print(f'[v109] verify: {"PASS" if _v else "FAIL"}')
