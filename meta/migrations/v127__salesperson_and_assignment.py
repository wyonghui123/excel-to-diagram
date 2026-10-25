# -*- coding: utf-8 -*-
"""[v127] 销售订单波次 1 W1-D：销售员 + 客户销售员分配 菜单与权限

依据:
  docs/superpowers/specs/2026-10-25-sales-order-wave1-detailed-plan.md
    §6.2 对象 / §6.4 UI 与菜单 / §6.6 迁移与验收

背景:
  `salesperson` 是独立主数据对象（YAML 声明 skip_auto_menu: true），菜单交由
  本迁移手工声明（否则 MenuAutoGenerator 只会产出 parent_menu='' +
  show_in_sidebar=0 的孤儿行）。`customer_salesperson_assignment` 挂客户档案
  详情子表，不单独成菜单，本迁移不处理。

本迁移:
  主数据（master-data）
    └── salesperson-list → 销售员 /salespersons  sort 84
  1. 菜单 + menu_permissions
  2. 5 条双段式权限 {salesperson}:{salesperson}_{action}
  3. 补 YAML 已声明的索引（sync_schema 正常已建；缺失时在此补齐，
     并对「主销售员唯一」「分配三元组唯一」做重复数据预检）

幂等:
  permissions 用 INSERT OR IGNORE；menus / menu_permissions 先按 menu_code
  判存在，缺失才 INSERT；索引已存在只输出 [SKIP]。

回滚:
  删除菜单（menus + menu_permissions）与本次补建的索引。
  **保留** permissions 行 —— 可能已被角色授予，删除有风险。
"""
import json
import sqlite3
from pathlib import Path

OBJECT_ID = 'salesperson'
MENU_CODE = 'salesperson-list'
PARENT_MENU = 'master-data'

SALESPERSON_TABLE = 'salespersons'
ASSIGNMENT_TABLE = 'customer_salesperson_assignments'

UIDX_CODE = 'uidx_salesperson_code'
IDX_USER = 'idx_salesperson_user'
UIDX_ASSIGN = 'uidx_customer_salesperson_assign'
UIDX_PRIMARY = 'uidx_customer_salesperson_primary'
UIDX_PRIMARY_ALL_ORG = 'uidx_customer_salesperson_primary_all_org'
IDX_ASSIGN_SALESPERSON = 'idx_customer_salesperson_salesperson'

_INDEX_DDL = (
    (UIDX_CODE,
     f'CREATE UNIQUE INDEX IF NOT EXISTS {UIDX_CODE} '
     f'ON {SALESPERSON_TABLE} (code)'),
    (IDX_USER,
     f'CREATE INDEX IF NOT EXISTS {IDX_USER} '
     f'ON {SALESPERSON_TABLE} (user_id)'),
    (UIDX_ASSIGN,
     f'CREATE UNIQUE INDEX IF NOT EXISTS {UIDX_ASSIGN} '
     f'ON {ASSIGNMENT_TABLE} '
     f'(customer_account_id, sales_org_id, salesperson_id)'),
    (UIDX_PRIMARY,
     f'CREATE UNIQUE INDEX IF NOT EXISTS {UIDX_PRIMARY} '
     f'ON {ASSIGNMENT_TABLE} (customer_account_id, sales_org_id) '
     f"WHERE is_primary = 1 AND status = 'active'"),
    (UIDX_PRIMARY_ALL_ORG,
     f'CREATE UNIQUE INDEX IF NOT EXISTS {UIDX_PRIMARY_ALL_ORG} '
     f'ON {ASSIGNMENT_TABLE} (customer_account_id) '
     f"WHERE sales_org_id IS NULL AND is_primary = 1 AND status = 'active'"),
    (IDX_ASSIGN_SALESPERSON,
     f'CREATE INDEX IF NOT EXISTS {IDX_ASSIGN_SALESPERSON} '
     f'ON {ASSIGNMENT_TABLE} (salesperson_id)'),
)

_RANK = ('create', 'read', 'update', 'delete', 'list')

_ACTION_LABEL = {
    'create': '新建', 'read': '查看', 'update': '修改',
    'delete': '删除', 'list': '查询',
}

PERMISSIONS = tuple(
    (f'{OBJECT_ID}:{OBJECT_ID}_{a}', f'{_ACTION_LABEL[a]}销售员',
     OBJECT_ID, a)
    for a in _RANK
)

MENUS = (
    {
        'menu_code': MENU_CODE,
        'menu_name': '销售员',
        'menu_path': '/salespersons',
        'page_type': 'object_list',
        'primary_object_type': OBJECT_ID,
        'object_types': [OBJECT_ID],
        'bo_bindings': [
            {'bo_id': OBJECT_ID, 'role': 'primary', 'include_actions': list(_RANK)},
        ],
        'required_permissions': [code for code, _n, _r, _a in PERMISSIONS],
        'parent_menu': PARENT_MENU,
        'icon': 'List',
        'color': '#0ea5e9',
        'description': '销售员字典：编码、姓名及人员 / 账号绑定',
        'sort_order': 84,
        'is_active': 1,
        'show_in_sidebar': 0,
        'auto_generated': 0,
        'data_permission_hint': {
            'resource_types': [OBJECT_ID],
            'message': '建议分配销售员数据权限',
        },
    },
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone() is not None


def _duplicate_assignments(conn: sqlite3.Connection):
    return conn.execute(
        f'SELECT customer_account_id, sales_org_id, salesperson_id, COUNT(*) AS n '
        f'FROM {ASSIGNMENT_TABLE} '
        f'GROUP BY customer_account_id, sales_org_id, salesperson_id '
        f'HAVING n > 1').fetchall()


def _duplicate_primary(conn: sqlite3.Connection):
    return conn.execute(
        f'SELECT customer_account_id, sales_org_id, COUNT(*) AS n '
        f'FROM {ASSIGNMENT_TABLE} '
        f"WHERE is_primary = 1 AND status = 'active' "
        f'GROUP BY customer_account_id, sales_org_id '
        f'HAVING n > 1').fetchall()


def _do_permissions(conn: sqlite3.Connection) -> None:
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


def _do_indexes(conn: sqlite3.Connection) -> bool:
    """补建 YAML 已声明的索引；建唯一索引前先查重复数据。"""
    for table in (SALESPERSON_TABLE, ASSIGNMENT_TABLE):
        if not _table_exists(conn, table):
            print(f'  - 表 {table} 不存在：请先执行 sync_schema 建表')
            return False

    duplicates = _duplicate_assignments(conn)
    if duplicates:
        print(f'  - 发现重复 (客户, 销售组织, 销售员) 组合，无法建唯一索引: {duplicates}')
        return False
    primaries = _duplicate_primary(conn)
    if primaries:
        print(f'  - 发现重复主销售员 (客户, 销售组织)，无法建唯一索引: {primaries}')
        return False

    for name, ddl in _INDEX_DDL:
        if _index_exists(conn, name):
            print(f'  - [SKIP] 索引 {name} 已存在')
        else:
            conn.execute(ddl)
            print(f'  - [NEW] 索引 {name}')
    return True


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v127] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v127] 开始: 销售员 菜单 / 权限 / 索引')
        if not _do_indexes(conn):
            conn.rollback()
            return False
        _do_permissions(conn)
        _do_menus(conn)
        _do_menu_permissions(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v127] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """断言表结构 / 索引 / 菜单 1 条 / 权限 5 条 / menu_permissions 就位。"""
    if not db_path.exists():
        print('[v127 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        for table in (SALESPERSON_TABLE, ASSIGNMENT_TABLE, 'menus', 'permissions'):
            if not _table_exists(conn, table):
                print(f'[v127 verify] FAIL: {table} 表不存在')
                return False

        for name, _ddl in _INDEX_DDL:
            if not _index_exists(conn, name):
                print(f'[v127 verify] FAIL: 缺索引 {name}')
                return False

        if not conn.execute("SELECT 1 FROM menus WHERE menu_code = ?",
                            (PARENT_MENU,)).fetchone():
            print(f'[v127 verify] FAIL: 父菜单 {PARENT_MENU} 不存在')
            return False

        for menu in MENUS:
            row = conn.execute(
                "SELECT page_type, is_active, menu_path, primary_object_type, "
                "parent_menu, required_permissions, show_in_sidebar "
                "FROM menus WHERE menu_code = ?",
                (menu['menu_code'],),
            ).fetchone()
            if not row:
                print(f"[v127 verify] FAIL: 菜单 {menu['menu_code']} 不存在")
                return False

            page_type, is_active, menu_path, pot, parent, req, show = row
            if page_type != menu['page_type']:
                print(f"[v127 verify] FAIL: {menu['menu_code']} page_type={page_type!r}")
                return False
            if is_active != 1:
                print(f"[v127 verify] FAIL: {menu['menu_code']} is_active={is_active}")
                return False
            if show != menu['show_in_sidebar']:
                print(f"[v127 verify] FAIL: {menu['menu_code']} "
                      f"show_in_sidebar={show}, 期望 {menu['show_in_sidebar']}")
                return False
            if (menu_path or '') != menu['menu_path']:
                print(f"[v127 verify] FAIL: {menu['menu_code']} menu_path={menu_path!r}")
                return False
            if (pot or '') != menu['primary_object_type']:
                print(f"[v127 verify] FAIL: {menu['menu_code']} "
                      f"primary_object_type={pot!r}")
                return False
            if (parent or '') != menu['parent_menu']:
                print(f"[v127 verify] FAIL: {menu['menu_code']} parent_menu={parent!r}")
                return False

            try:
                codes = json.loads(req or '[]')
            except Exception:
                codes = []
            if sorted(codes) != sorted(menu['required_permissions']):
                print(f"[v127 verify] FAIL: {menu['menu_code']} "
                      f"required_permissions={codes}")
                return False

        missing = [code for code, _n, _r, _a in PERMISSIONS
                   if not conn.execute(
                       "SELECT 1 FROM permissions WHERE code = ?", (code,)).fetchone()]
        if missing:
            print(f'[v127 verify] FAIL: 缺权限码 {missing}')
            return False
        malformed = [c for c, _n, _r, _a in PERMISSIONS
                     if c.count(':') != 1
                     or not c.split(':')[1].startswith(c.split(':')[0] + '_')]
        if malformed:
            print(f'[v127 verify] FAIL: 非双段式权限码 {malformed}')
            return False

        if _table_exists(conn, 'menu_permissions'):
            for menu in MENUS:
                cnt = conn.execute(
                    "SELECT COUNT(*) FROM menu_permissions WHERE menu_code = ?",
                    (menu['menu_code'],)).fetchone()[0]
                if cnt < 1:
                    print(f"[v127 verify] FAIL: menu_permissions 缺 {menu['menu_code']}")
                    return False

        print(f'[v127 verify] OK: {PARENT_MENU} 下 1 条销售员菜单, '
              f'{len(PERMISSIONS)} 条双段式权限, 6 条索引, menu_permissions 齐备')
        return True
    finally:
        conn.close()


def rollback(db_path: Path, skip_backup: bool = False) -> bool:
    """移除菜单与本次补建的索引；permissions 行保留（可能已被角色授予）。"""
    if not db_path.exists():
        print(f'[v127] DB 不存在: {db_path}')
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
        for name, _ddl in _INDEX_DDL:
            if _index_exists(conn, name):
                conn.execute(f'DROP INDEX {name}')
                print(f'  - [DROP] 索引 {name}')
        print('  - [KEEP] permissions 行保留 (可能已被角色授予)')
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v127] rollback 失败: {e}')
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
        print(f'[v127] rollback: {"OK" if _ok else "FAIL"}')
    else:
        _ok = migrate(_db)
        print(f'[v127] migrate: {"OK" if _ok else "FAIL"}')
        _v = verify(_db)
        print(f'[v127] verify: {"PASS" if _v else "FAIL"}')
