# -*- coding: utf-8 -*-
"""[v107 2026-10-24] 供应来源规则 / 供应方式策略 菜单与权限交付

背景:
  v106 已建 4 张表(sourcing_rules / sourcing_rule_lines / sourcing_rule_assignments /
  sourcing_mode_policies)。本迁移补齐导航与权限，让两个头对象在「主数据」下可达:
    - sourcing_rule        → 菜单 sourcing-rule-management  (/sourcing-rules)
    - sourcing_mode_policy → 菜单 sourcing-mode-policy-management (/sourcing-mode-policies)
  两个子对象 sourcing_rule_line / sourcing_rule_assignment 的 ui_view_config 声明了
  skip_auto_menu: true，在规则详情页内联维护，故不建菜单。

权限口径:
  双段式 {object_id}:{object_id}_{action}，与 permissions 表既有码一致
  (例 allocation_rule:allocation_rule_create)。共 10 条: 两个对象 × create/read/update/
  delete/list。

落位:
  两条菜单均挂 master-data(主数据, page_type=multi_object_hub)下，show_in_sidebar=0 ——
  与 party-management / material-management / location-list / address-list /
  region-list / calendar-list / uom-list 同款(作为父 hub 的子页，侧边栏不单列)。
  sort_order 取 72 / 73: 该组现存最大值 71(calendar-list)，此后未被占用。

幂等:
  permissions 用 INSERT OR IGNORE；menus / menu_permissions 先按 menu_code 判存在，
  缺失才 INSERT。重复执行只输出 [SKIP]，不产生新增。

回滚:
  删除两条菜单(menus + menu_permissions)。**保留** permissions 行 —— 可能已被角色
  授予，删除有风险。
"""
import json
import sqlite3
from pathlib import Path


PARENT_MENU = 'master-data'

RULE_MENU_CODE = 'sourcing-rule-management'
POLICY_MENU_CODE = 'sourcing-mode-policy-management'

# 权限声明: (code, name, resource_type, action)
PERMISSIONS = (
    ('sourcing_rule:sourcing_rule_create', '新建供应来源规则', 'sourcing_rule', 'create'),
    ('sourcing_rule:sourcing_rule_read', '查看供应来源规则', 'sourcing_rule', 'read'),
    ('sourcing_rule:sourcing_rule_update', '修改供应来源规则', 'sourcing_rule', 'update'),
    ('sourcing_rule:sourcing_rule_delete', '删除供应来源规则', 'sourcing_rule', 'delete'),
    ('sourcing_rule:sourcing_rule_list', '查询供应来源规则列表', 'sourcing_rule', 'list'),
    ('sourcing_mode_policy:sourcing_mode_policy_create', '新建供应方式策略',
     'sourcing_mode_policy', 'create'),
    ('sourcing_mode_policy:sourcing_mode_policy_read', '查看供应方式策略',
     'sourcing_mode_policy', 'read'),
    ('sourcing_mode_policy:sourcing_mode_policy_update', '修改供应方式策略',
     'sourcing_mode_policy', 'update'),
    ('sourcing_mode_policy:sourcing_mode_policy_delete', '删除供应方式策略',
     'sourcing_mode_policy', 'delete'),
    ('sourcing_mode_policy:sourcing_mode_policy_list', '查询供应方式策略列表',
     'sourcing_mode_policy', 'list'),
)

# 菜单声明: menus 与 menu_permissions 共用同一份字段（写库时各自展开）
MENUS = (
    {
        'menu_code': RULE_MENU_CODE,
        'menu_name': '供应来源规则',
        'menu_path': '/sourcing-rules',
        'page_type': 'object_list',
        'primary_object_type': 'sourcing_rule',
        'object_types': ['sourcing_rule'],
        'bo_bindings': [
            {'bo_id': 'sourcing_rule', 'role': 'primary',
             'include_actions': ['create', 'read', 'update', 'delete', 'list']},
        ],
        'required_permissions': [
            'sourcing_rule:sourcing_rule_create',
            'sourcing_rule:sourcing_rule_read',
            'sourcing_rule:sourcing_rule_update',
            'sourcing_rule:sourcing_rule_delete',
            'sourcing_rule:sourcing_rule_list',
        ],
        'parent_menu': PARENT_MENU,
        'icon': 'Share',
        'color': '#0ea5e9',
        'description': '供应来源路由规则，来源行与作用域分配在规则详情页内联维护',
        'sort_order': 72,
        'is_active': 1,
        'show_in_sidebar': 0,
        'auto_generated': 0,
        'data_permission_hint': {
            'resource_types': ['sourcing_rule'],
            'message': '建议分配供应来源规则数据权限',
        },
    },
    {
        'menu_code': POLICY_MENU_CODE,
        'menu_name': '供应方式策略',
        'menu_path': '/sourcing-mode-policies',
        'page_type': 'object_list',
        'primary_object_type': 'sourcing_mode_policy',
        'object_types': ['sourcing_mode_policy'],
        'bo_bindings': [
            {'bo_id': 'sourcing_mode_policy', 'role': 'primary',
             'include_actions': ['create', 'read', 'update', 'delete', 'list']},
        ],
        'required_permissions': [
            'sourcing_mode_policy:sourcing_mode_policy_create',
            'sourcing_mode_policy:sourcing_mode_policy_read',
            'sourcing_mode_policy:sourcing_mode_policy_update',
            'sourcing_mode_policy:sourcing_mode_policy_delete',
            'sourcing_mode_policy:sourcing_mode_policy_list',
        ],
        'parent_menu': PARENT_MENU,
        'icon': 'Share',
        'color': '#0ea5e9',
        'description': '物料组 / 物料在目标组织上的供应方式基线（自制 / 采购 / 调拨）',
        'sort_order': 73,
        'is_active': 1,
        'show_in_sidebar': 0,
        'auto_generated': 0,
        'data_permission_hint': {
            'resource_types': ['sourcing_mode_policy'],
            'message': '建议分配供应方式策略数据权限',
        },
    },
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
        print('  - [SKIP] 10 条权限码均已存在, 无新增')


def _do_menus(conn: sqlite3.Connection) -> None:
    """写入两条菜单（menus 表）；已存在则跳过。"""
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


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v107] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v107] 开始: 供应来源规则 / 供应方式策略 菜单与权限')
        _do_permissions(conn)
        _do_menus(conn)
        _do_menu_permissions(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v107] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """两条菜单形态正确，且 required_permissions 全部能在 permissions 表查到。"""
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, 'menus'):
            print('[v107 verify] FAIL: menus 表不存在')
            return False
        if not _table_exists(conn, 'permissions'):
            print('[v107 verify] FAIL: permissions 表不存在')
            return False

        for menu in MENUS:
            row = conn.execute(
                "SELECT page_type, is_active, menu_path, primary_object_type, "
                "required_permissions FROM menus WHERE menu_code = ?",
                (menu['menu_code'],),
            ).fetchone()
            if not row:
                print(f"[v107 verify] FAIL: 菜单 {menu['menu_code']} 不存在")
                return False

            page_type, is_active, menu_path, pot, req = row
            if page_type != menu['page_type']:
                print(f"[v107 verify] FAIL: {menu['menu_code']} page_type={page_type}, "
                      f"期望 {menu['page_type']}")
                return False
            if is_active != 1:
                print(f"[v107 verify] FAIL: {menu['menu_code']} is_active={is_active}, "
                      f"期望 1")
                return False
            if menu_path != menu['menu_path']:
                print(f"[v107 verify] FAIL: {menu['menu_code']} menu_path={menu_path}, "
                      f"期望 {menu['menu_path']}")
                return False
            if pot != menu['primary_object_type']:
                print(f"[v107 verify] FAIL: {menu['menu_code']} "
                      f"primary_object_type={pot}, 期望 {menu['primary_object_type']}")
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
                print(f"[v107 verify] FAIL: {menu['menu_code']} required_permissions "
                      f"含不存在的权限码 {missing}")
                return False
            if not codes:
                print(f"[v107 verify] FAIL: {menu['menu_code']} required_permissions 为空")
                return False

        print('[v107 verify] OK: 两条菜单均为 object_list 且启用, 10 条权限码全部有效 '
              '(sourcing-rule-management /sourcing-rules, '
              'sourcing-mode-policy-management /sourcing-mode-policies)')
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    """移除两条菜单；permissions 行保留（可能已被角色授予）。"""
    if not db_path.exists():
        print(f'[v107] DB 不存在: {db_path}')
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
        print(f'[v107] downgrade 失败: {e}')
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    _ok = migrate(_db)
    print(f'[v107] migrate: {"OK" if _ok else "FAIL"}')
    _v = verify(_db)
    print(f'[v107] verify: {"PASS" if _v else "FAIL"}')
