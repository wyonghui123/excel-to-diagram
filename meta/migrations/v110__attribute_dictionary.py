# -*- coding: utf-8 -*-
"""[v110] 属性字典 菜单与权限交付

背景:
  attribute_definitions / attribute_scopes / party_attribute_values 三张表由 schema 同步建表。
  本迁移补齐导航与权限，让定义层与适用范围在「主数据」下可达:
    - attribute_definition → 菜单 attribute-definition-management (/attribute-definitions)
    - attribute_scope      → 菜单 attribute-scope-management     (/attribute-scopes)
  值表 party_attribute_values 在业务伙伴详情页的嵌套分区内联维护
  （ui_view_config 声明 skip_auto_menu: true），不建顶层菜单。

权限口径:
  双段式 {object_id}:{object_id}_{action}，与 permissions 表既有码一致
  （例 incoterm:incoterm_create）。

落位:
  两条菜单挂 master-data（主数据）下，show_in_sidebar=0 —— 作为父 hub 的子页，侧边栏不单列。
  sort_order 79 / 80：该组现存最大值为 78（v109 incoterm-management）。

存量对账（只读，不写）:
  旧值表 item_attribute_values.attr_code 是自由文本、无字典外键。本迁移把「字典里没有的编码」
  列成清单输出，供人工决定是否补定义；不自动生成定义 —— 类型与值域无法从编码反推，
  猜出来的定义比没有更危险。

幂等:
  permissions 用 INSERT OR IGNORE；menus / menu_permissions 先按 menu_code 判存在，
  缺失才 INSERT。重复执行只输出 [SKIP]。

回滚:
  删除两条菜单（menus + menu_permissions）。保留 permissions 行 —— 可能已被角色授予。
"""
import json
import sqlite3
from pathlib import Path


PARENT_MENU = 'master-data'

DEFINITION_MENU_CODE = 'attribute-definition-management'
SCOPE_MENU_CODE = 'attribute-scope-management'

_DEFINITION_PERMISSIONS = [f'attribute_definition:attribute_definition_{a}'
                           for a in ('create', 'read', 'update', 'delete', 'list')]
_SCOPE_PERMISSIONS = [f'attribute_scope:attribute_scope_{a}'
                      for a in ('create', 'read', 'update', 'delete', 'list')]
_VALUE_PERMISSIONS = [f'party_attribute_value:party_attribute_value_{a}'
                      for a in ('create', 'read', 'update', 'delete', 'list')]

# 权限声明: (code, name, resource_type, action)
PERMISSIONS = tuple(
    [(code, f'新建属性定义' if code.endswith('_create') else
      f'查看属性定义' if code.endswith('_read') else
      f'修改属性定义' if code.endswith('_update') else
      f'删除属性定义' if code.endswith('_delete') else '查询属性定义列表',
      'attribute_definition', code.rsplit('_', 1)[-1]) for code in _DEFINITION_PERMISSIONS]
    + [(code, f'新建属性适用范围' if code.endswith('_create') else
        f'查看属性适用范围' if code.endswith('_read') else
        f'修改属性适用范围' if code.endswith('_update') else
        f'删除属性适用范围' if code.endswith('_delete') else '查询属性适用范围列表',
        'attribute_scope', code.rsplit('_', 1)[-1]) for code in _SCOPE_PERMISSIONS]
    + [(code, f'维护业务伙伴属性值（{code.rsplit("_", 1)[-1]}）',
        'party_attribute_value', code.rsplit('_', 1)[-1]) for code in _VALUE_PERMISSIONS]
)

MENUS = (
    {
        'menu_code': DEFINITION_MENU_CODE,
        'menu_name': '属性定义',
        'menu_path': '/attribute-definitions',
        'page_type': 'object_list',
        'primary_object_type': 'attribute_definition',
        'object_types': ['attribute_definition'],
        'bo_bindings': [
            {'bo_id': 'attribute_definition', 'role': 'primary',
             'include_actions': ['create', 'read', 'update', 'delete', 'list']},
        ],
        'required_permissions': _DEFINITION_PERMISSIONS,
        'parent_menu': PARENT_MENU,
        'icon': 'Tags',
        'color': '#0ea5e9',
        'description': '可扩展属性字典：类型、值域、使用分级与启用状态',
        'sort_order': 79,
        'is_active': 1,
        'show_in_sidebar': 0,
        'auto_generated': 0,
        'data_permission_hint': {
            'resource_types': ['attribute_definition'],
            'message': '建议分配属性定义数据权限',
        },
    },
    {
        'menu_code': SCOPE_MENU_CODE,
        'menu_name': '属性适用范围',
        'menu_path': '/attribute-scopes',
        'page_type': 'object_list',
        'primary_object_type': 'attribute_scope',
        'object_types': ['attribute_scope'],
        'bo_bindings': [
            {'bo_id': 'attribute_scope', 'role': 'primary',
             'include_actions': ['create', 'read', 'update', 'delete', 'list']},
        ],
        'required_permissions': _SCOPE_PERMISSIONS,
        'parent_menu': PARENT_MENU,
        'icon': 'Sliders',
        'color': '#0ea5e9',
        'description': '属性作用于哪些对象或物料分类，以及是否必填',
        'sort_order': 80,
        'is_active': 1,
        'show_in_sidebar': 0,
        'auto_generated': 0,
        'data_permission_hint': {
            'resource_types': ['attribute_scope'],
            'message': '建议分配属性适用范围数据权限',
        },
    },
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


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
            print(f'  - [NEW] 权限 {code}')

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
        print(f"  - [NEW] 菜单 {menu['menu_code']} @ {menu['menu_path']}, "
              f"sort_order={menu['sort_order']}")


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


def _report_legacy_attr_codes(conn: sqlite3.Connection) -> None:
    """存量对账（只读）：列出旧值表里字典未覆盖的编码，不做自动补定义。"""
    if not _table_exists(conn, 'item_attribute_values'):
        print('  - [SKIP] item_attribute_values 不存在, 无存量可对账')
        return
    if not _table_exists(conn, 'attribute_definitions'):
        print('  - [SKIP] attribute_definitions 尚未建表, 对账延后')
        return

    total = conn.execute('SELECT COUNT(*) FROM item_attribute_values').fetchone()[0]
    if total == 0:
        print('  - [OK] item_attribute_values 为空, 无存量需对账')
        return

    rows = conn.execute(
        "SELECT attr_code, COUNT(*) AS cnt FROM item_attribute_values "
        "WHERE attr_code NOT IN "
        "(SELECT code FROM attribute_definitions WHERE tenant_id = 0) "
        "GROUP BY attr_code ORDER BY attr_code"
    ).fetchall()

    if not rows:
        print('  - [OK] 存量编码均有字典定义')
        return
    print(f'  - [TODO] {len(rows)} 个存量编码尚无字典定义（需人工补定义，迁移不自动生成）:')
    for code, cnt in rows:
        print(f'      · {code}  ({cnt} 行)')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v110] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v110] 开始: 属性字典 菜单与权限')
        _do_permissions(conn)
        _do_menus(conn)
        _do_menu_permissions(conn)
        _report_legacy_attr_codes(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v110] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        for required in ('menus', 'permissions'):
            if not _table_exists(conn, required):
                print(f'[v110 verify] FAIL: {required} 表不存在')
                return False

        for menu in MENUS:
            row = conn.execute(
                "SELECT page_type, is_active, menu_path, primary_object_type, "
                "required_permissions FROM menus WHERE menu_code = ?",
                (menu['menu_code'],),
            ).fetchone()
            if not row:
                print(f"[v110 verify] FAIL: 菜单 {menu['menu_code']} 不存在")
                return False

            page_type, is_active, menu_path, pot, req = row
            if page_type != menu['page_type'] or is_active != 1:
                print(f"[v110 verify] FAIL: {menu['menu_code']} page_type/is_active 不符")
                return False
            if menu_path != menu['menu_path'] or pot != menu['primary_object_type']:
                print(f"[v110 verify] FAIL: {menu['menu_code']} 路径或主对象不符")
                return False

            try:
                codes = json.loads(req or '[]')
            except Exception:
                codes = []
            if not codes:
                print(f"[v110 verify] FAIL: {menu['menu_code']} required_permissions 为空")
                return False
            missing = [c for c in codes if not conn.execute(
                "SELECT 1 FROM permissions WHERE code = ?", (c,)).fetchone()]
            if missing:
                print(f"[v110 verify] FAIL: {menu['menu_code']} 含失效权限码 {missing}")
                return False

        print('[v110 verify] OK: 两条菜单均为 object_list 且启用，权限码全部有效')
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v110] DB 不存在: {db_path}')
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
        print(f'[v110] downgrade 失败: {e}')
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    _ok = migrate(_db)
    print(f'[v110] migrate: {"OK" if _ok else "FAIL"}')
    _v = verify(_db)
    print(f'[v110] verify: {"PASS" if _v else "FAIL"}')
