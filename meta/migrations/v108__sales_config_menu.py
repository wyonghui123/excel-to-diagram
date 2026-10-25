# -*- coding: utf-8 -*-
"""[v108 2026-10-25] 销售域结构身份 / 控制参数 / 付款条件 菜单与权限交付

背景:
  销售域主数据这一批新建了 5 张表 (control_parameter_defs /
  control_parameter_values / sales_document_types / sales_line_types /
  sales_line_type_assignments), 加上上一批的 payment_terms, 共 4 个可独立
  维护的头对象。它们的菜单若只靠 MenuAutoGenerator, 得到的是
  parent_menu='' + show_in_sidebar=0 的「孤儿行」—— 既不在侧边栏、也没挂任何
  父节点, get_visible_menu_tree 捞不到, 导航树上完全不可达 (同 MD-MENU
  2026-10-11 主数据修法 / SRC-MENU 2026-10-24 供应来源规则)。

  本迁移补齐 4 条主数据子页菜单:
    - sales_document_type → 销售单据类型  /sales-document-types   sort 74
    - sales_line_type     → 销售行类型    /sales-line-types       sort 75
    - control_parameter_def → 控制参数    /control-parameters     sort 76
    - payment_term        → 付款条件      /payment-terms          sort 77

  两个子对象 control_parameter_value / sales_line_type_assignment 的
  ui_view_config 声明了 skip_auto_menu: true, 在父详情页内联维护, 故不建菜单。

权限口径:
  双段式 {object_id}:{object_id}_{action}, 与 permissions 表既有码一致
  (例 allocation_rule:allocation_rule_create)。共 20 条: 4 对象 ×
  create/read/update/delete/list。

  为什么迁移里也写 permissions:
    启动时的 PermissionSyncService 会按 YAML actions 自动补码, 但迁移可能
    先于服务启动执行; 而 menus.required_permissions 引用不存在的权限码会被
    前端路由守卫 (every 判定) 整页拦下 (v099–v103 反复踩过)。故显式落库。

落位:
  4 条菜单均挂 master-data(主数据, page_type=multi_object_hub)下,
  show_in_sidebar=0 —— 与 party-management / item-list / location-list /
  uom-list / sourcing-rule-management 同款(父 hub 的子页)。
  sort_order 74–77: 该组现存最大值 73(sourcing-mode-policy-management)。

幂等:
  permissions 用 INSERT OR IGNORE; menus / menu_permissions 先按 menu_code 判存在,
  缺失才 INSERT。重复执行只输出 [SKIP], 不产生新增。

回滚:
  删除 4 条菜单(menus + menu_permissions)。**保留** permissions 行 —— 可能已被角色
  授予, 删除有风险。
"""
import json
import sqlite3
from pathlib import Path


PARENT_MENU = 'master-data'

DOC_TYPE_MENU_CODE = 'sales-document-type-management'
LINE_TYPE_MENU_CODE = 'sales-line-type-management'
PARAM_MENU_CODE = 'control-parameter-management'
PAYMENT_TERM_MENU_CODE = 'payment-term-management'

# 权限声明: (code, name, resource_type, action)
PERMISSIONS = (
    ('sales_document_type:sales_document_type_create', '新建销售单据类型',
     'sales_document_type', 'sales_document_type_create'),
    ('sales_document_type:sales_document_type_read', '查看销售单据类型',
     'sales_document_type', 'sales_document_type_read'),
    ('sales_document_type:sales_document_type_update', '修改销售单据类型',
     'sales_document_type', 'sales_document_type_update'),
    ('sales_document_type:sales_document_type_delete', '删除销售单据类型',
     'sales_document_type', 'sales_document_type_delete'),
    ('sales_document_type:sales_document_type_list', '查询销售单据类型列表',
     'sales_document_type', 'sales_document_type_list'),
    ('sales_line_type:sales_line_type_create', '新建销售行类型',
     'sales_line_type', 'sales_line_type_create'),
    ('sales_line_type:sales_line_type_read', '查看销售行类型',
     'sales_line_type', 'sales_line_type_read'),
    ('sales_line_type:sales_line_type_update', '修改销售行类型',
     'sales_line_type', 'sales_line_type_update'),
    ('sales_line_type:sales_line_type_delete', '删除销售行类型',
     'sales_line_type', 'sales_line_type_delete'),
    ('sales_line_type:sales_line_type_list', '查询销售行类型列表',
     'sales_line_type', 'sales_line_type_list'),
    ('control_parameter_def:control_parameter_def_create', '新建控制参数',
     'control_parameter_def', 'control_parameter_def_create'),
    ('control_parameter_def:control_parameter_def_read', '查看控制参数',
     'control_parameter_def', 'control_parameter_def_read'),
    ('control_parameter_def:control_parameter_def_update', '修改控制参数',
     'control_parameter_def', 'control_parameter_def_update'),
    ('control_parameter_def:control_parameter_def_delete', '删除控制参数',
     'control_parameter_def', 'control_parameter_def_delete'),
    ('control_parameter_def:control_parameter_def_list', '查询控制参数列表',
     'control_parameter_def', 'control_parameter_def_list'),
    ('payment_term:payment_term_create', '新建付款条件',
     'payment_term', 'payment_term_create'),
    ('payment_term:payment_term_read', '查看付款条件',
     'payment_term', 'payment_term_read'),
    ('payment_term:payment_term_update', '修改付款条件',
     'payment_term', 'payment_term_update'),
    ('payment_term:payment_term_delete', '删除付款条件',
     'payment_term', 'payment_term_delete'),
    ('payment_term:payment_term_list', '查询付款条件列表',
     'payment_term', 'payment_term_list'),
)


def _permissions_of(object_id: str):
    return [
        f'{object_id}:{object_id}_create',
        f'{object_id}:{object_id}_read',
        f'{object_id}:{object_id}_update',
        f'{object_id}:{object_id}_delete',
        f'{object_id}:{object_id}_list',
    ]


# 菜单声明: menus 与 menu_permissions 共用同一份字段（写库时各自展开）
MENUS = (
    {
        'menu_code': DOC_TYPE_MENU_CODE,
        'menu_name': '销售单据类型',
        'menu_path': '/sales-document-types',
        'page_type': 'object_list',
        'primary_object_type': 'sales_document_type',
        'object_types': ['sales_document_type'],
        'bo_bindings': [
            {'bo_id': 'sales_document_type', 'role': 'primary',
             'include_actions': ['create', 'read', 'update', 'delete', 'list']},
        ],
        'required_permissions': _permissions_of('sales_document_type'),
        'parent_menu': PARENT_MENU,
        'icon': 'List',
        'color': '#0ea5e9',
        'description': '销售单据类型的结构身份；行类型确定规则在详情页内联维护',
        'sort_order': 74,
        'is_active': 1,
        'show_in_sidebar': 0,
        'auto_generated': 0,
        'data_permission_hint': {
            'resource_types': ['sales_document_type'],
            'message': '建议分配销售单据类型数据权限',
        },
    },
    {
        'menu_code': LINE_TYPE_MENU_CODE,
        'menu_name': '销售行类型',
        'menu_path': '/sales-line-types',
        'page_type': 'object_list',
        'primary_object_type': 'sales_line_type',
        'object_types': ['sales_line_type'],
        'bo_bindings': [
            {'bo_id': 'sales_line_type', 'role': 'primary',
             'include_actions': ['create', 'read', 'update', 'delete', 'list']},
        ],
        'required_permissions': _permissions_of('sales_line_type'),
        'parent_menu': PARENT_MENU,
        'icon': 'List',
        'color': '#0ea5e9',
        'description': '销售行类型字典（物料行 / 服务行 / 退货行 / 免费行 / 文本行）',
        'sort_order': 75,
        'is_active': 1,
        'show_in_sidebar': 0,
        'auto_generated': 0,
        'data_permission_hint': {
            'resource_types': ['sales_line_type'],
            'message': '建议分配销售行类型数据权限',
        },
    },
    {
        'menu_code': PARAM_MENU_CODE,
        'menu_name': '控制参数',
        'menu_path': '/control-parameters',
        'page_type': 'object_list',
        'primary_object_type': 'control_parameter_def',
        'object_types': ['control_parameter_def'],
        'bo_bindings': [
            {'bo_id': 'control_parameter_def', 'role': 'primary',
             'include_actions': ['create', 'read', 'update', 'delete', 'list']},
        ],
        'required_permissions': _permissions_of('control_parameter_def'),
        'parent_menu': PARENT_MENU,
        'icon': 'Setting',
        'color': '#0ea5e9',
        'description': '行为开关与业务默认值的两表配置；维度取值在详情页内联维护',
        'sort_order': 76,
        'is_active': 1,
        'show_in_sidebar': 0,
        'auto_generated': 0,
        'data_permission_hint': {
            'resource_types': ['control_parameter_def'],
            'message': '建议分配控制参数数据权限',
        },
    },
    {
        'menu_code': PAYMENT_TERM_MENU_CODE,
        'menu_name': '付款条件',
        'menu_path': '/payment-terms',
        'page_type': 'object_list',
        'primary_object_type': 'payment_term',
        'object_types': ['payment_term'],
        'bo_bindings': [
            {'bo_id': 'payment_term', 'role': 'primary',
             'include_actions': ['create', 'read', 'update', 'delete', 'list']},
        ],
        'required_permissions': _permissions_of('payment_term'),
        'parent_menu': PARENT_MENU,
        'icon': 'Timer',
        'color': '#0ea5e9',
        'description': '付款条件（账期规则头）；分期与折扣行在详情页内联维护',
        'sort_order': 77,
        'is_active': 1,
        'show_in_sidebar': 0,
        'auto_generated': 0,
        'data_permission_hint': {
            'resource_types': ['payment_term'],
            'message': '建议分配付款条件数据权限',
        },
    },
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _do_permissions(conn: sqlite3.Connection) -> None:
    """写入 20 条权限码（已存在则忽略，不覆盖既有 name / 授权关系）。"""
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
        print('  - [SKIP] 20 条权限码均已存在, 无新增')


def _do_menus(conn: sqlite3.Connection) -> None:
    """写入 4 条菜单（menus 表）；已存在则跳过。"""
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
        print(f'[v108] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v108] 开始: 销售单据类型 / 销售行类型 / 控制参数 / 付款条件 菜单与权限')
        _do_permissions(conn)
        _do_menus(conn)
        _do_menu_permissions(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v108] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """4 条菜单形态正确，且 required_permissions 全部能在 permissions 表查到。"""
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, 'menus'):
            print('[v108 verify] FAIL: menus 表不存在')
            return False
        if not _table_exists(conn, 'permissions'):
            print('[v108 verify] FAIL: permissions 表不存在')
            return False

        for menu in MENUS:
            row = conn.execute(
                "SELECT page_type, is_active, menu_path, primary_object_type, "
                "parent_menu, required_permissions FROM menus WHERE menu_code = ?",
                (menu['menu_code'],),
            ).fetchone()
            if not row:
                print(f"[v108 verify] FAIL: 菜单 {menu['menu_code']} 不存在")
                return False

            page_type, is_active, menu_path, pot, parent, req = row
            if page_type != menu['page_type']:
                print(f"[v108 verify] FAIL: {menu['menu_code']} page_type={page_type}, "
                      f"期望 {menu['page_type']}")
                return False
            if is_active != 1:
                print(f"[v108 verify] FAIL: {menu['menu_code']} is_active={is_active}, "
                      f"期望 1")
                return False
            if menu_path != menu['menu_path']:
                print(f"[v108 verify] FAIL: {menu['menu_code']} menu_path={menu_path}, "
                      f"期望 {menu['menu_path']}")
                return False
            if pot != menu['primary_object_type']:
                print(f"[v108 verify] FAIL: {menu['menu_code']} "
                      f"primary_object_type={pot}, 期望 {menu['primary_object_type']}")
                return False
            if parent != PARENT_MENU:
                print(f"[v108 verify] FAIL: {menu['menu_code']} parent_menu={parent}, "
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
                print(f"[v108 verify] FAIL: menu['menu_code'] required_permissions "
                      f"含不存在的权限码 {missing}")
                return False
            if not codes:
                print(f"[v108 verify] FAIL: {menu['menu_code']} required_permissions 为空")
                return False

        print('[v108 verify] OK: 4 条菜单均为 object_list 且挂 master-data, '
              '20 条权限码全部有效 '
              '(/sales-document-types /sales-line-types /control-parameters /payment-terms)')
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    """移除 4 条菜单；permissions 行保留（可能已被角色授予）。"""
    if not db_path.exists():
        print(f'[v108] DB 不存在: {db_path}')
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
        print(f'[v108] downgrade 失败: {e}')
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    _ok = migrate(_db)
    print(f'[v108] migrate: {"OK" if _ok else "FAIL"}')
    _v = verify(_db)
    print(f'[v108] verify: {"PASS" if _v else "FAIL"}')
