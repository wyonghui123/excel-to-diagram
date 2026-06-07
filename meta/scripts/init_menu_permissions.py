# -*- coding: utf-8 -*-
"""
菜单权限表初始化脚本

创建 menu_permissions 表并插入系统菜单数据
每个菜单关联对应的业务对象（BO）
"""

import sqlite3
import os
import json
import sys
import io
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def init_menu_permissions(db_path):
    """初始化菜单权限表和 menus 导航表数据（元数据驱动）"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("=" * 60)
    print("初始化菜单权限表 & menus 导航表")
    print("=" * 60)

    # ========== 步骤1：创建 menu_permissions 表（权限） ==========
    print("\n[步骤1] 创建 menu_permissions 表...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS menu_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            menu_code VARCHAR(200) UNIQUE NOT NULL,
            menu_name VARCHAR(200) NOT NULL,
            menu_path VARCHAR(500) NOT NULL,
            required_permissions TEXT,
            required_any_permission INTEGER DEFAULT 0,
            parent_menu VARCHAR(200),
            icon VARCHAR(200),
            sort_order INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            data_permission_hint TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_menu_permission_code ON menu_permissions(menu_code)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_menu_permission_parent ON menu_permissions(parent_menu)")

    # 创建 role_menu_permissions 关联表（many-to-many: role <-> menu_permission）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS role_menu_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            menu_code VARCHAR(200) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(role_id, menu_code)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rmp_role ON role_menu_permissions(role_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rmp_menu ON role_menu_permissions(menu_code)")

    # ========== 步骤2：创建 menus 表（导航） ==========
    print("\n[步骤2] 创建 menus 导航表...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS menus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            menu_code VARCHAR(200) UNIQUE NOT NULL,
            menu_name VARCHAR(200) NOT NULL,
            menu_path VARCHAR(500) NOT NULL DEFAULT '',
            page_type VARCHAR(200) DEFAULT 'object_list',
            object_types TEXT DEFAULT '[]',
            primary_object_type VARCHAR(200) DEFAULT '',
            page_config TEXT DEFAULT '{}',
            parent_menu VARCHAR(200) DEFAULT '',
            icon VARCHAR(200) DEFAULT '',
            color VARCHAR(200) DEFAULT '',
            description VARCHAR(500) DEFAULT '',
            sort_order INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            show_in_sidebar INTEGER DEFAULT 1,
            auto_generated INTEGER DEFAULT 0
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_menus_code ON menus(menu_code)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_menus_parent ON menus(parent_menu)")

    # 兼容旧表：补充 bo_bindings / required_permissions 列
    try:
        cursor.execute("ALTER TABLE menus ADD COLUMN bo_bindings TEXT DEFAULT '[]'")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE menus ADD COLUMN required_permissions TEXT DEFAULT '[]'")
    except Exception:
        pass

    print("  [OK] 两表创建完成")

    # ========== 步骤3：检查 menu_permissions 是否已有数据 ==========
    print("\n[步骤3] 检查现有数据...")
    cursor.execute("SELECT COUNT(*) FROM menu_permissions")
    perm_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM menus")
    menus_count = cursor.fetchone()[0]

    if perm_count > 0:
        print(f"  ⏭️  已有 {perm_count} 条权限数据")

    if menus_count > 0:
        print(f"  ⏭️  已有 {menus_count} 条导航数据")

    # ========== 步骤4：系统菜单定义（元数据驱动） ==========
    print("\n[步骤4] 插入系统菜单数据...")

    system_menus = [
        {
            'menu_code': 'dashboard',
            'menu_name': '仪表盘',
            'menu_path': '/dashboard',
            'icon': 'Home',
            'color': '#3b82f6',
            'sort_order': 0,
            'page_type': 'dashboard',
            'primary_object_type': '',
            'object_types': json.dumps([]),
            'required_permissions': json.dumps([]),
            'data_permission_hint': None
        },
        {
            'menu_code': 'arch-data',
            'menu_name': '架构数据管理',
            'menu_path': '/data',
            'icon': 'FolderOpened',
            'color': '#10b981',
            'sort_order': 20,
            'page_type': 'multi_object_hub',
            'primary_object_type': 'domain',
            'object_types': json.dumps(['domain', 'sub_domain', 'service_module']),
            'bo_bindings': json.dumps([
                {'bo_id': 'domain', 'role': 'primary', 'include_actions': ['create', 'read', 'update', 'delete', 'list', 'export', 'import']},
                {'bo_id': 'sub_domain', 'role': 'primary', 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
                {'bo_id': 'service_module', 'role': 'primary', 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
                {'bo_id': 'business_object', 'role': 'primary', 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
            ]),
            'required_permissions': json.dumps([
                'domain:create', 'domain:read', 'domain:update', 'domain:delete', 'domain:export', 'domain:import',
                'sub_domain:create', 'sub_domain:read', 'sub_domain:update', 'sub_domain:delete',
                'service_module:create', 'service_module:read', 'service_module:update', 'service_module:delete',
                'business_object:create', 'business_object:read', 'business_object:update', 'business_object:delete',
            ]),
            'data_permission_hint': json.dumps({
                'resource_types': ['domain', 'sub_domain'],
                'message': '建议分配领域/子域数据权限'
            })
        },
        {
            'menu_code': 'aa-diagram',
            'menu_name': 'AA图监查',
            'menu_path': '/diagram',
            'icon': 'PictureFilled',
            'color': '#f59e0b',
            'sort_order': 30,
            'page_type': 'custom_page',
            'primary_object_type': '',
            'object_types': json.dumps([]),
            'bo_bindings': json.dumps([
                {'bo_id': 'relationship', 'role': 'primary', 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
            ]),
            'required_permissions': json.dumps([
                'relationship:create', 'relationship:read', 'relationship:update', 'relationship:delete',
            ]),
            'data_permission_hint': json.dumps({
                'resource_types': ['relationship'],
                'message': '建议分配关系数据权限'
            })
        },
        {
            'menu_code': 'product-management',
            'menu_name': '产品管理',
            'menu_path': '/product-management',
            'icon': 'Box',
            'color': '#06b6d4',
            'sort_order': 40,
            'page_type': 'object_list',
            'primary_object_type': 'product',
            'object_types': json.dumps(['product']),
            'bo_bindings': json.dumps([
                {'bo_id': 'product', 'role': 'primary', 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
                {'bo_id': 'version', 'role': 'primary', 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
            ]),
            'required_permissions': json.dumps([
                'product:create', 'product:read', 'product:update', 'product:delete',
            ]),
            'data_permission_hint': json.dumps({
                'resource_types': ['product'],
                'message': '建议分配产品数据权限'
            })
        },
        {
            'menu_code': 'system',
            'menu_name': '系统管理',
            'menu_path': '',
            'icon': 'Setting',
            'color': '#6b7280',
            'sort_order': 50,
            'page_type': 'custom_page',
            'primary_object_type': '',
            'object_types': json.dumps([]),
            'required_permissions': json.dumps([]),
            'data_permission_hint': None
        },
        {
            'menu_code': 'user-permission',
            'menu_name': '用户与权限管理',
            'menu_path': '/user-permission',
            'icon': 'User',
            'color': '#ef4444',
            'sort_order': 51,
            'parent_menu': 'system',
            'page_type': 'multi_object_hub',
            'primary_object_type': 'user',
            'object_types': json.dumps(['user', 'role', 'user_group']),
            'bo_bindings': json.dumps([
                {'bo_id': 'user', 'role': 'primary', 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
                {'bo_id': 'role', 'role': 'primary', 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
                {'bo_id': 'user_group', 'role': 'primary', 'include_actions': ['create', 'read', 'update', 'delete', 'list', 'assign', 'unassign', 'grant', 'revoke']},
            ]),
            'required_permissions': json.dumps([
                'user:create', 'user:read', 'user:update', 'user:delete',
                'role:create', 'role:read', 'role:update', 'role:delete',
                'user_group:create', 'user_group:read', 'user_group:update', 'user_group:delete',
                'user_group:assign', 'user_group:unassign', 'user_group:grant', 'user_group:revoke',
            ]),
            'data_permission_hint': json.dumps({
                'resource_types': ['user', 'role', 'user_group'],
                'message': '需要用户管理相关权限'
            })
        },
        {
            'menu_code': 'business-config',
            'menu_name': '业务配置',
            'menu_path': '/business-config',
            'icon': 'Tools',
            'color': '#8b5cf6',
            'sort_order': 52,
            'parent_menu': 'system',
            'page_type': 'multi_object_hub',
            'primary_object_type': 'enum_type',
            'object_types': json.dumps(['enum_type']),
            'bo_bindings': json.dumps([
                {'bo_id': 'enum_type', 'role': 'primary', 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
            ]),
            'required_permissions': json.dumps([
                'enum_type:create', 'enum_type:read', 'enum_type:update', 'enum_type:delete',
            ]),
            'data_permission_hint': json.dumps({
                'resource_types': ['service_module'],
                'message': '建议分配服务模块数据权限'
            }),
        },
        {
            'menu_code': 'audit-log',
            'menu_name': '日志管理',
            'menu_path': '/system-admin',
            'icon': 'List',
            'color': '#64748b',
            'sort_order': 53,
            'parent_menu': 'system',
            'page_type': 'object_list',
            'primary_object_type': 'audit_log',
            'object_types': json.dumps(['audit_log']),
            'bo_bindings': json.dumps([
                {'bo_id': 'audit_log', 'role': 'primary', 'include_actions': ['read', 'delete', 'list']},
            ]),
            'required_permissions': json.dumps([
                'audit_log:read', 'audit_log:delete',
            ]),
            'data_permission_hint': json.dumps({
                'resource_types': ['audit_log'],
                'message': '建议分配审计日志查看权限'
            })
        },
    ]

    # ========== 步骤4.5：清理已废弃菜单 ==========
    deprecated_codes = ['product-version']
    for code in deprecated_codes:
        cursor.execute("DELETE FROM menus WHERE menu_code = ?", [code])
        cursor.execute("DELETE FROM menu_permissions WHERE menu_code = ?", [code])
    conn.commit()

    # ========== 步骤5：写入/更新 menu_permissions 表（权限） ==========
    print("\n[步骤5] 同步 menu_permissions 表...")
    for menu in system_menus:
        cursor.execute(
            "SELECT menu_code FROM menu_permissions WHERE menu_code = ?",
            [menu['menu_code']]
        )
        if cursor.fetchone():
            cursor.execute("""
                UPDATE menu_permissions SET
                    menu_name = ?, menu_path = ?,
                    required_permissions = ?, parent_menu = ?,
                    icon = ?, sort_order = ?, is_active = 1,
                    data_permission_hint = ?
                WHERE menu_code = ?
            """, [
                menu['menu_name'],
                menu['menu_path'],
                menu['required_permissions'],
                menu.get('parent_menu'),
                menu.get('icon'),
                menu['sort_order'],
                menu.get('data_permission_hint'),
                menu['menu_code'],
            ])
            print(f"  [OK] perm: {menu['menu_name']} ({menu['menu_code']})")
        else:
            cursor.execute("""
                INSERT INTO menu_permissions
                (menu_code, menu_name, menu_path, required_permissions, required_any_permission,
                 parent_menu, icon, sort_order, is_active, data_permission_hint)
                VALUES (?, ?, ?, ?, 0, ?, ?, ?, 1, ?)
            """, [
                menu['menu_code'],
                menu['menu_name'],
                menu['menu_path'],
                menu['required_permissions'],
                menu.get('parent_menu'),
                menu.get('icon'),
                menu['sort_order'],
                menu.get('data_permission_hint')
            ])
            print(f"  [OK] perm: {menu['menu_name']} ({menu['menu_code']})")

    # ========== 步骤6：同步 menus 导航表（每次启动 UPSERT） ==========
    print("\n[步骤6] 同步 menus 导航表...")
    for menu in system_menus:
        cursor.execute(
            "SELECT menu_code FROM menus WHERE menu_code = ?",
            [menu['menu_code']]
        )
        if cursor.fetchone():
            cursor.execute("""
                UPDATE menus SET
                    menu_name = ?, menu_path = ?, page_type = ?,
                    primary_object_type = ?, object_types = ?,
                    bo_bindings = ?, required_permissions = ?,
                    parent_menu = ?, icon = ?, color = ?,
                    description = ?, sort_order = ?
                WHERE menu_code = ?
            """, [
                menu['menu_name'],
                menu['menu_path'],
                menu.get('page_type', 'custom_page'),
                menu.get('primary_object_type', ''),
                menu.get('object_types', '[]'),
                menu.get('bo_bindings', '[]'),
                menu['required_permissions'],
                menu.get('parent_menu', ''),
                menu.get('icon', ''),
                menu.get('color', ''),
                menu.get('description', ''),
                menu['sort_order'],
                menu['menu_code'],
            ])
            print(f"  [OK] nav:  {menu['menu_name']} ({menu['menu_code']}) [{menu.get('page_type')}]")
        else:
            cursor.execute("""
                INSERT INTO menus
                (menu_code, menu_name, menu_path, page_type, object_types,
                 primary_object_type, bo_bindings, required_permissions,
                 parent_menu, icon, color, description,
                 sort_order, is_active, show_in_sidebar, auto_generated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, 0)
            """, [
                menu['menu_code'],
                menu['menu_name'],
                menu['menu_path'],
                menu.get('page_type', 'custom_page'),
                menu.get('object_types', '[]'),
                menu.get('primary_object_type', ''),
                menu.get('bo_bindings', '[]'),
                menu['required_permissions'],
                menu.get('parent_menu', ''),
                menu.get('icon', ''),
                menu.get('color', ''),
                menu.get('description', ''),
                menu['sort_order'],
            ])
            print(f"  [OK] nav:  {menu['menu_name']} ({menu['menu_code']}) [{menu.get('page_type')}]")

    # ========== 步骤7：验证结果 ==========
    print("\n[步骤7] 验证初始化结果...")

    cursor.execute("SELECT COUNT(*) FROM menus")
    nav_count = cursor.fetchone()[0]
    print(f"  menus 导航表: {nav_count} 条")

    cursor.execute("SELECT COUNT(*) FROM menu_permissions")
    perm_count = cursor.fetchone()[0]
    print(f"  menu_permissions 权限表: {perm_count} 条")

    cursor.execute("""
        SELECT menu_name, page_type, primary_object_type, parent_menu
        FROM menus ORDER BY sort_order
    """)
    menus = cursor.fetchall()

    print("\n  菜单列表 (page_type):")
    for name, page_type, primary_obj, parent in menus:
        indent = "  " if parent else ""
        print(f"    {indent}- {name} [{page_type}] {primary_obj or ''}")

    conn.commit()

    # ========== 步骤7.5：清理 menu_permissions 表中不属于白名单的条目 ==========
    print("\n[步骤7.5] 清理 menu_permissions 表冗余条目...")
    valid_perm_codes = {m['menu_code'] for m in system_menus}
    valid_perm_codes.add('task-management')

    cursor.execute("SELECT menu_code, menu_name FROM menu_permissions")
    all_perm_entries = cursor.fetchall()
    removed = 0
    for menu_code, menu_name in all_perm_entries:
        if menu_code not in valid_perm_codes:
            cursor.execute("DELETE FROM menu_permissions WHERE menu_code = ?", [menu_code])
            print(f"  [SYMBOL]  stale perm: {menu_name} ({menu_code})")
            removed += 1

    if removed == 0:
        print("  [OK] 无冗余条目")
    else:
        print(f"  [OK] 清理了 {removed} 条冗余菜单权限")

    # 也清理 menus 表中的冗余条目
    print("\n[步骤7.6] 清理 menus 导航表冗余条目...")
    valid_nav_codes = {m['menu_code'] for m in system_menus}
    valid_nav_codes.add('task-management')
    valid_nav_codes.add('task-definitions')
    valid_nav_codes.add('task-queues')
    valid_nav_codes.add('task-executions')
    valid_nav_codes.add('ai-async-tasks')

    cursor.execute("SELECT menu_code, menu_name, auto_generated FROM menus WHERE auto_generated = 0")
    all_manual_menus = cursor.fetchall()
    removed_nav = 0
    for menu_code, menu_name, _ in all_manual_menus:
        if menu_code not in valid_nav_codes:
            cursor.execute("DELETE FROM menus WHERE menu_code = ?", [menu_code])
            print(f"  [SYMBOL]  stale nav: {menu_name} ({menu_code})")
            removed_nav += 1

    if removed_nav == 0:
        print("  [OK] 无冗余条目")
    else:
        print(f"  [OK] 清理了 {removed_nav} 条冗余导航菜单")

    print("\n" + "=" * 60)
    print("[OK] 菜单权限表 & 导航表初始化完成！")
    print("=" * 60)

    conn.close()


if __name__ == '__main__':
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'architecture.db')
    print(f"数据库路径: {db_path}")
    init_menu_permissions(db_path)
