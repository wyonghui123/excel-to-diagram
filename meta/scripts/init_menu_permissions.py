# -*- coding: utf-8 -*-
"""
菜单权限表初始化脚本

创建 menu_permissions 表并插入系统菜单数据
每个菜单关联对应的业务对象（BO）

[H14.1] 单一事实源约定：
    yaml  meta/schemas/*.yaml  import_export: 段
        是导入导出权限的"业务能力声明" (ImportExportService 能否工作)
    menu menus.bo_bindings[*].include_actions
        是权限矩阵 UI 推导源 (_derive_bo_permission_groups 的 actions_map)
    步骤 6.5 自动从前者派生后者, 消除两层独立维护导致的漂移.
    人工显式声明 (yaml 未配但 menu 声明, 如 user_group 的 assign)
    通过反向 KEEP 保留, 不被本脚本删除.
"""

import sqlite3
import os
import json
import sys
import io
import glob
import yaml
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def init_menu_permissions(db_path):
    """初始化菜单权限表和 menus 导航表数据（元数据驱动）

    [V007.49-A] 增量更新模式（2026-07-12 修复）：
        修复原 "已有数据就跳过" 的问题。原逻辑会导致 BUG-V056 类的"代码已部署
        但 DB 数据未更新"的问题。改为：每次启动都执行 UPSERT 检测新增/变更
        的菜单权限声明、bo_bindings、required_permissions，并展开到角色。
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM menu_permissions")
    perm_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM menus")
    menu_count = cursor.fetchone()[0]

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
        CREATE TABLE IF NOT EXISTS permission_set_menu_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            permission_set_id INTEGER NOT NULL,
            menu_code VARCHAR(200) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(permission_set_id, menu_code)
        )
    """)
    # [2026-09-15 v089 Spec 19 M4 修复] role_menu_permissions → permission_set_menu_permissions
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rmp_role ON permission_set_menu_permissions(permission_set_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rmp_menu ON permission_set_menu_permissions(menu_code)")

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

    # ========== 步骤3：检查现有数据（[V007.49-A] 仅记录，不再跳过） ==========
    print("\n[步骤3] 检查现有数据...")
    cursor.execute("SELECT COUNT(*) FROM menu_permissions")
    perm_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM menus")
    menus_count = cursor.fetchone()[0]

    if perm_count > 0:
        print(f"  [INFO] 已有 {perm_count} 条权限数据，将进行增量 UPSERT")

    if menus_count > 0:
        print(f"  [INFO] 已有 {menus_count} 条导航数据，将进行增量 UPSERT")

    # ========== 步骤4：系统菜单定义（元数据驱动） ==========
    print("\n[步骤4] 同步系统菜单数据...")

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
            'object_types': json.dumps(['domain', 'sub_domain', 'service_module', 'relationship', 'audit_log']),
            'bo_bindings': json.dumps([
                {'bo_id': 'domain', 'role': 'primary', 'include_actions': ['create', 'read', 'update', 'delete', 'list', 'export', 'import']},
                # [H14.1] 同步 yaml import_export: sub_domain / service_module / business_object 支持导入导出
                {'bo_id': 'sub_domain', 'role': 'primary', 'include_actions': ['create', 'read', 'update', 'delete', 'list', 'export', 'import']},
                {'bo_id': 'service_module', 'role': 'primary', 'include_actions': ['create', 'read', 'update', 'delete', 'list', 'export', 'import']},
                {'bo_id': 'business_object', 'role': 'primary', 'include_actions': ['create', 'read', 'update', 'delete', 'list', 'export', 'import']},
                # [FIX BUG-V056 2026-07-12] relationship 补全 create/update/delete
                # 之前只有 read/export/import, 导致: 1) 用户无法在角色详情页勾选关系的编辑/管理权限
                # 2) 关系编辑权限不出现在 JWT permissions 中, 创建/更新关系被拒
                # relationship 不再是纯派生对象, 用户需要手动创建/编辑/删除关系
                {'bo_id': 'relationship', 'role': 'derived', 'include_actions': ['create', 'read', 'update', 'delete', 'list', 'export', 'import']},
                # [NEW] BMRD-2026-06-14 审计日志自动带入
                # domain 详情页"操作日志" tab 需要 read 权限, 紧化 v1 endpoint 后
                # (v1 现在也校验 audit_log:read) 必须显式 grant 才能看到
                # [H14.1] audit_log yaml import_enabled=false, 只保留 export
                {'bo_id': 'audit_log', 'role': 'derived', 'include_actions': ['read', 'export']},
            ]),
            'required_permissions': json.dumps([
                # [FIX 2026-07-10] BUG-V051: 补全所有架构对象的导入导出权限
                # 之前 required_permissions 只配了部分 export/import (e.g. domain:export/import),
                # 漏了 sub_domain:import, service_module:import, business_object:import/export,
                # relationship:import, audit_log:export
                # 导致: 1) 用户勾选这些权限保存没效果 (DB 不存在)  2) 详细权限列表显示不到
                # [FIX-2 2026-07-10] 移除 batch_import (与 import 重复, 委托给统一 export-import 端点)
                'domain:create', 'domain:read', 'domain:update', 'domain:delete', 'domain:export', 'domain:import',
                'sub_domain:create', 'sub_domain:read', 'sub_domain:update', 'sub_domain:delete',
                'sub_domain:export', 'sub_domain:import',
                'service_module:create', 'service_module:read', 'service_module:update', 'service_module:delete',
                'service_module:export', 'service_module:import',
                'business_object:create', 'business_object:read', 'business_object:update', 'business_object:delete',
                'business_object:export', 'business_object:import',
                # [FIX BUG-V056 2026-07-12] 关系对象补全 create/update/delete
                'relationship:create', 'relationship:read', 'relationship:update', 'relationship:delete',
                'relationship:export', 'relationship:import',
                # 🆕 审计日志 (derived) 的最低权限 (操作日志 tab 必需)
                'audit_log:read', 'audit_log:export',
            ]),
            'data_permission_hint': json.dumps({
                'resource_types': ['domain', 'sub_domain', 'relationship', 'audit_log'],
                'message': '建议分配领域/子域/关系/审计日志数据权限 (关系和审计随架构数据自动带入)'
            })
        },
        {
            'menu_code': 'product-management',
            'menu_name': '产品版本管理',
            'menu_path': '/product-management',
            'icon': 'Box',
            'color': '#06b6d4',
            'sort_order': 40,
            'page_type': 'object_list',
            'primary_object_type': 'product',
            'object_types': json.dumps(['product']),
            'bo_bindings': json.dumps([
                # [H14.1] 同步 yaml import_export: product / version 支持导入导出
                {'bo_id': 'product', 'role': 'primary', 'include_actions': ['create', 'read', 'update', 'delete', 'list', 'export', 'import']},
                {'bo_id': 'version', 'role': 'primary', 'include_actions': ['create', 'read', 'update', 'delete', 'list', 'export', 'import']},
            ]),
            'required_permissions': json.dumps([
                # [FIX 2026-07-10] BUG-V051: 补全 product/version 的 import/export/set_current/compare
                'product:create', 'product:read', 'product:update', 'product:delete',
                'product:import', 'product:export',
                'version:create', 'version:read', 'version:update', 'version:delete',
                'version:import', 'version:export',
                'version:set_current', 'version:compare',
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
            # [FIX 2026-09-01 v2] 父菜单 user-permission 作为分组容器 (multi_object_hub, page_type='multi_object_hub',
            #   show_in_sidebar=1 但不带 menu_path), 3 个子菜单 (用户/权限集/组织管理) 作为独立 landing 卡片.
            #   leaf_menus 算法:
            #     - 顶层 multi_object_hub 有 children → 被 parent_codes 排除 (不出现在 landing 卡片)
            #     - 但其 children 在第 376-403 行的 child_rows SQL 中按 visible parent_menu 附加到 flat
            #     - children 是 object_list → 进入 leaf_menus 显示为 3 张独立卡片
            #   侧边栏: user-permission 作为父节点, 3 个 child 嵌套渲染 (见 AppRootLayout.vue apiNavigationItems)
            'menu_code': 'user-permission',
            'menu_name': '用户与权限管理',
            'menu_path': '',  # 父容器无 path, 不可点击直达, 仅作分组
            'icon': 'User',
            'color': '#ef4444',
            'sort_order': 50,
            'parent_menu': '',
            'page_type': 'multi_object_hub',
            'primary_object_type': '',
            'object_types': json.dumps([]),
            'bo_bindings': json.dumps([]),
            'required_permissions': json.dumps([]),  # 父容器无权限要求, 由子菜单控制
            'data_permission_hint': None
        },
        {
            # 子菜单: 用户管理 - page_type=object_list, parent_menu=user-permission
            'menu_code': 'user-management',
            'menu_name': '用户',
            'menu_path': '/user-management',
            'icon': 'User',
            'color': '#ef4444',
            'sort_order': 51,
            'parent_menu': 'user-permission',
            'page_type': 'object_list',
            'primary_object_type': 'user',
            # [Plan D 2026-08-29 Spec16] role → permission_set, user_group → org
            'object_types': json.dumps(['user']),
            'bo_bindings': json.dumps([
                # user 支持导入导出
                {'bo_id': 'user', 'role': 'primary', 'include_actions': ['create', 'read', 'update', 'delete', 'list', 'export', 'import']},
            ]),
            'required_permissions': json.dumps([
                'user:create', 'user:read', 'user:update', 'user:delete',
            ]),
            'data_permission_hint': json.dumps({
                'resource_types': ['user'],
                'message': '需要用户管理相关权限'
            })
        },
        {
            # 子菜单: 权限集管理
            'menu_code': 'permission-set-management',
            'menu_name': '权限集',
            'menu_path': '/permission-set-management',
            'icon': 'Key',
            'color': '#f97316',
            'sort_order': 52,
            'parent_menu': 'user-permission',
            'page_type': 'object_list',
            'primary_object_type': 'permission_set',
            'object_types': json.dumps(['permission_set']),
            'bo_bindings': json.dumps([
                # permission_set 支持导入导出
                {'bo_id': 'permission_set', 'role': 'primary', 'include_actions': ['create', 'read', 'update', 'delete', 'list', 'export', 'import']},
            ]),
            'required_permissions': json.dumps([
                'permission_set:create', 'permission_set:read', 'permission_set:update', 'permission_set:delete',
            ]),
            'data_permission_hint': json.dumps({
                'resource_types': ['permission_set'],
                'message': '需要权限集管理相关权限'
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
                # [H14.1] 同步 yaml import_export: enum_type 仅 export_enabled=true (import_enabled=false)
                {'bo_id': 'enum_type', 'role': 'primary', 'include_actions': ['create', 'read', 'update', 'delete', 'list', 'export']},
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
                # [H14.1] 同步 yaml import_export: audit_log 仅 export_enabled=true (import_enabled=false)
                {'bo_id': 'audit_log', 'role': 'primary', 'include_actions': ['read', 'export']},
            ]),
            # [FIX 2026-06-14] 菜单 "日志管理" 限定 super-admin only.
            #   any(p in user_perms for p in required) 语义下, 普通权限 (如 audit_log:read) 会让所有业务用户都能看见.
            #   详情 tab 的操作日志 (audit_log:read) 跟菜单的日志管理 (admin only) 是两个独立维度.
            #   '*' 表示 "super-admin" (admin 角色自带, 普通用户没有).
            'required_permissions': json.dumps([
                '*',
            ]),
            'data_permission_hint': json.dumps({
                'resource_types': ['audit_log'],
                'message': '建议分配审计日志查看权限'
            })
        },
        {
            # [C6 2026-10-14] 平台运维作业 —— 进程内调度器状态 + 手动触发页。
            #   形态照抄 business-config / audit-log 等同父菜单(system)条目:
            #     - page_type=custom_page ⇒ 无自动菜单, 由静态路由
            #       /system/platform-ops-jobs 渲染 PlatformOpsJobs.vue
            #     - 无 BO 绑定, object_types / bo_bindings 均空
            #   required_permissions=["*"] : 平台运维 (调度器状态 / 手动触发) 属管理员
            #   职责, 仅超级权限可见 —— 与 audit-log 同口径, 亦与前端路由
            #   meta.requiresAdmin 一致。**不可为空**: get_visible_menu_tree 的
            #   _prune_empty_groups 把"custom_page + 无 children + 无权限门槛"当空分组
            #   裁掉(见 menu_permission_api.py); 设了权限门槛才会被识别为"真页面叶子"保留。
            #   sort_order=56: 排在系统管理组 audit-log(53) 之后
            #   （与设计文档 spec-task-scheduler.md §13.1 的序号一致）。
            'menu_code': 'platform-ops-jobs',
            'menu_name': '平台运维作业',
            'menu_path': '/system/platform-ops-jobs',
            'icon': 'Monitor',
            'color': '#64748b',
            'sort_order': 56,
            'parent_menu': 'system',
            'page_type': 'custom_page',
            'primary_object_type': '',
            'object_types': json.dumps([]),
            'bo_bindings': json.dumps([]),
            'required_permissions': json.dumps(['*']),
            'data_permission_hint': None
        },
        {
            # [MOMP 通用化 2026-08-30] 组织管理页（org 单类型 MOMP）
            #   - menu_path=/org-management 对应前端路由 name=OrgManagement
            #   - [FIX 2026-09-01 v2] 改为 user-permission 父菜单下的子菜单 (parent_menu='user-permission'),
            #     与 user-management / permission-set-management 并列作为独立 landing 卡片.
            #   - page_type=object_list (非 multi_object_hub), 避免被 line 491-494 排除.
            #   - [Plan D 2026-08-29 Spec16] user_group → org
            'menu_code': 'org-management',
            'menu_name': '组织管理',
            'menu_path': '/org-management',
            'icon': 'OfficeBuilding',
            'color': '#0ea5e9',
            'sort_order': 53,
            'parent_menu': 'user-permission',
            'page_type': 'object_list',
            'primary_object_type': 'org',
            'object_types': json.dumps(['org']),
            'bo_bindings': json.dumps([
                {'bo_id': 'org', 'role': 'primary', 'include_actions': ['create', 'read', 'update', 'delete', 'list', 'import', 'export']},
            ]),
            'required_permissions': json.dumps([
                'org:create', 'org:read', 'org:update', 'org:delete',
                'org:list', 'org:import', 'org:export',
            ]),
            'data_permission_hint': json.dumps({
                'resource_types': ['org'],
                'message': '建议分配组织数据权限'
            })
        },
        {
            # [MD-MENU 2026-10-11] 往来单位（party）—— 用户拍板开独立菜单
            #   背景: party.yaml 声明 ui_view_config.skip_auto_menu: true, 无自动菜单。
            #         但它是客户/供应商档案的**上游主数据**: customer_account.relation_id
            #         → party_relations.party2_id → parties.id。yaml 里不写菜单 ⇒ 用户在前端
            #         点不到 party, 而客户档案的「关联客户关系」value_help 恰好指向
            #         party_relation, 形成「选不出来的必填外键」。
            #   口径与 customer_account / vendor_account 一致: yaml 的 skip_auto_menu
            #   保持不变 (那是"不要自动生成"的声明, 不等于"不许有菜单"), 菜单在此手工声明。
            #   sort_order=59/60: 排在 customer_account(61) / vendor_account(62) 之前,
            #   符合「先主体后档案」的阅读顺序; 后续 v091 的自动菜单从 63 接续, 不冲突。
            #
            #   [MOMP 升级 2026-10-11] 由 object_list 升级为 multi_object_hub 单页 hub,
            #   形态照物料管理页 (material-management): 左树 = 往来单位组 (party_group),
            #   右表 = 往来单位 / 往来单位组 两个 tab。
            #     动机: party 不直挂 group, 分组关系在关系层 (party_relations.group_id
            #     → party2_id), 查某组伙伴的主路径收敛成"左树选组 → 右表看该组伙伴"
            #     (前端 PartyManagement.vue 做两段桥接)。
            #     往来单位组 tab 是 party_group 的维护入口; v093 下架了 party_group-list
            #     独立菜单 (同 v092 对 item_group 的处理)。
            #   GenericTabContainer 对该 menu_code 做精确映射 → PartyManagement.vue。
            'menu_code': 'party-management',
            'menu_name': '往来单位',
            'menu_path': '/party',
            'icon': 'User',
            'color': '#0ea5e9',
            'sort_order': 59,
            'parent_menu': 'master-data',
            'page_type': 'multi_object_hub',
            'primary_object_type': 'party',
            'object_types': json.dumps(['party', 'party_group']),
            'bo_bindings': json.dumps([
                {'bo_id': 'party', 'role': 'primary',
                 'include_actions': ['create', 'update', 'delete']},
                {'bo_id': 'party_group', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
            ]),
            'required_permissions': json.dumps([
                # [注意] party 只有 create/update/delete 三个动作 (party.yaml:31 actions),
                #   permissions 表里不存在 party_read / party_list。照 CRUD 惯例补齐
                #   会让菜单因权限码不存在而永不可见, 故只声明实际存在的三个。
                'party:party_create',
                'party:party_update',
                'party:party_delete',
                # 往来单位组 tab 需独立维护入口 (v093 下架 party_group-list 菜单),
                # 权限一并声明 (5 条权限码已存在 permissions 表, 见 party_group.yaml actions)。
                'party_group:party_group_create',
                'party_group:party_group_read',
                'party_group:party_group_update',
                'party_group:party_group_delete',
                'party_group:party_group_list',
            ]),
            'show_in_sidebar': 0,
            'data_permission_hint': json.dumps({
                'resource_types': ['party', 'party_group'],
                'message': '建议分配往来单位与往来单位组数据权限'
            })
        },
        {
            # [MD-MENU 2026-10-11] 往来单位关系（party_relation）—— 与 party 严格对称
            #   客户档案.relation_id 的直接指向对象, 不开菜单则该外键在前端无法选择。
            #   icon=User: AppRootLayout.iconMap 与 AppSideNav.iconMap 的真实交集只有 13 个
            #   (Bell/DataAnalysis/Document/Edit/FolderOpened/Grid/Home/Key/List/Lock/
            #   Search/Setting/Star), Connection 只在 rootlayout 单侧注册会渲染空白。
            #   语义上 party 与 party_relation 同属往来单位主体域, 用同一图标可接受。
            'menu_code': 'party-relation-management',
            'menu_name': '往来单位关系',
            'menu_path': '/party-relation',
            'icon': 'User',
            'color': '#0ea5e9',
            'sort_order': 60,
            'parent_menu': 'master-data',
            'page_type': 'object_list',
            'primary_object_type': 'party_relation',
            'object_types': json.dumps(['party_relation']),
            'bo_bindings': json.dumps([
                {'bo_id': 'party_relation', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
            ]),
            'required_permissions': json.dumps([
                'party_relation:party_relation_create',
                'party_relation:party_relation_read',
                'party_relation:party_relation_update',
                'party_relation:party_relation_delete',
                'party_relation:party_relation_list',
            ]),
            'show_in_sidebar': 0,
            'data_permission_hint': json.dumps({
                'resource_types': ['party_relation'],
                'message': '建议分配往来单位关系数据权限'
            })
        },
        {
            # [MD-MENU 2026-10-11] 主数据父菜单（分组容器）
            #   背景: 11 个主数据对象的自动菜单 (item-list / uom-list / location-list 等)
            #   此前 parent_menu='' 且 show_in_sidebar=0, 既不在侧边栏、也没挂任何父节点
            #   => get_visible_menu_tree 捞不到, 导航树上完全不可达.
            #   形态照抄 user-permission: page_type=multi_object_hub + menu_path=''
            #     - menu_path='' ⇒ leaf_menus 的 `if not m.get('menu_path'): continue` 跳过,
            #       不进 landing 卡片区 (与 user-permission 一致)
            #     - multi_object_hub ⇒ 有 children 时不被 _prune_empty_groups 裁掉;
            #       同时 dynamicRoutes 会注册 /master-data → GenericTabContainer
            #       (group='master-data'), 按 children 渲染 tab (聚合页, 与用户权限组同构)
            #   required_permissions=[] : 父容器不设权限门槛, 由各子菜单自行控制 (同 user-permission)
            #   [已知局限] (既存缺陷, 非本次引入): get_visible_menu_tree 对 show_in_sidebar=0
            #      的子菜单 (L383-409 child_rows) 不做权限过滤, 只按 parent_menu 挂载.
            #      故主数据子菜单对所有能看见父节点的用户可见; 点击后由前端路由守卫
            #      (requiredPermissions) 与 API 层权限拦截, 不泄露数据.
            'menu_code': 'master-data',
            'menu_name': '主数据',
            'menu_path': '',
            'icon': 'Goods',
            'color': '#0ea5e9',
            'sort_order': 45,
            'parent_menu': '',
            'page_type': 'multi_object_hub',
            'primary_object_type': '',
            'object_types': json.dumps([]),
            'bo_bindings': json.dumps([]),
            'required_permissions': json.dumps([]),
            'data_permission_hint': None
        },
        {
            # [MD-MENU 2026-10-11] 物料管理 —— 左树(物料组) + 右表(物料) 的 MOMP 聚合页
            #   动机: 物料组原先是独立菜单 item-group-list, 用户想按组找物料时只能
            #   点物料组菜单 → 记住组 id → 回物料菜单 → 手工填筛选条件。
            #   物料组是物料的天然分类维度 (items.item_group_id 直 FK), 把「组」从并列
            #   菜单升格为左侧导航树, 查物料的主路径收敛成"左树定位 → 右表看该组物料"。
            #   page_type=multi_object_hub + menu_path='/material-management':
            #     dynamicRoutes 按 multi_object_hub 注册, GenericTabContainer 里对该
            #     menu_code 做精确映射 (见 src/views/GenericTabContainer.vue),
            #     渲染 MaterialManagement.vue 而非 tab 容器。
            #   object_types=['item'] : 右表只有物料一个 tab; 物料组不做并列 tab
            #     (用户决策: 只做物料), 而是作为左树存在。
            #   sort_order=64 : 占用原物料的位置 (item-list 原 so=64), 物料组菜单下架后
            #     该序号空出, 物料组的入口即本页左树。
            'menu_code': 'material-management',
            'menu_name': '物料管理',
            'menu_path': '/material-management',
            'icon': 'Box',
            'color': '#0ea5e9',
            'sort_order': 64,
            'parent_menu': 'master-data',
            'page_type': 'multi_object_hub',
            'primary_object_type': 'item',
            'object_types': json.dumps(['item', 'item_group']),
            'bo_bindings': json.dumps([
                {'bo_id': 'item', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
                {'bo_id': 'item_group', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
            ]),
            'required_permissions': json.dumps([
                'item:item_create',
                'item:item_read',
                'item:item_update',
                'item:item_delete',
                'item:item_list',
                # 物料组 tab 需要独立维护入口 (v092 下架了 item-group-list 独立菜单),
                # 故权限一并声明; 少这 5 条会导致物料组 tab 被路由守卫拦下。
                'item_group:item_group_create',
                'item_group:item_group_read',
                'item_group:item_group_update',
                'item_group:item_group_delete',
                'item_group:item_group_list',
            ]),
            'show_in_sidebar': 0,
            'data_permission_hint': json.dumps({
                'resource_types': ['item', 'item_group'],
                'message': '建议分配物料与物料组数据权限'
            })
        },
        {
            # [MD-MENU 2026-10-11] 客户档案 —— 用户拍板开独立菜单
            #   yaml `ui_view_config.skip_auto_menu: true` 保持不变 (角色层档案不参与
            #   menu_auto_generator 自动生成的口径不动); 菜单在此手工声明, 与
            #   org-management / user-management 同一套路.
            #   show_in_sidebar=0 : 与同组 10 条自动菜单口径统一 —— 只在侧边栏展开可见,
            #   不进 landing 卡片区 (landing 留给工作台/快捷入口).
            'menu_code': 'customer-account-management',
            'menu_name': '客户档案',
            'menu_path': '/customer-account',
            'icon': 'User',
            'color': '#0ea5e9',
            'sort_order': 61,
            'parent_menu': 'master-data',
            'page_type': 'object_list',
            'primary_object_type': 'customer_account',
            'object_types': json.dumps(['customer_account']),
            'bo_bindings': json.dumps([
                {'bo_id': 'customer_account', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
            ]),
            # 权限码取自 permissions 表实际值 `{bo}:{bo}_{action}` (双段式),
            # 与 menu_auto_generator._derive_permissions_from_bindings 的口径一致
            'required_permissions': json.dumps([
                'customer_account:customer_account_create',
                'customer_account:customer_account_read',
                'customer_account:customer_account_update',
                'customer_account:customer_account_delete',
                'customer_account:customer_account_list',
            ]),
            'show_in_sidebar': 0,
            'data_permission_hint': json.dumps({
                'resource_types': ['customer_account'],
                'message': '建议分配客户档案数据权限'
            })
        },
        {
            # [MD-MENU 2026-10-11] 供应商档案 —— 与 customer_account 严格对称
            'menu_code': 'vendor-account-management',
            'menu_name': '供应商档案',
            'menu_path': '/vendor-account',
            'icon': 'User',
            'color': '#0ea5e9',
            'sort_order': 62,
            'parent_menu': 'master-data',
            'page_type': 'object_list',
            'primary_object_type': 'vendor_account',
            'object_types': json.dumps(['vendor_account']),
            'bo_bindings': json.dumps([
                {'bo_id': 'vendor_account', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
            ]),
            'required_permissions': json.dumps([
                'vendor_account:vendor_account_create',
                'vendor_account:vendor_account_read',
                'vendor_account:vendor_account_update',
                'vendor_account:vendor_account_delete',
                'vendor_account:vendor_account_list',
            ]),
            'show_in_sidebar': 0,
            'data_permission_hint': json.dumps({
                'resource_types': ['vendor_account'],
                'message': '建议分配供应商档案数据权限'
            })
        },
        # === [PRICE-MENU 2026-10-13] 定价域菜单接线 ===
        #   15 个对象分 3 组, 每组一个 multi_object_hub 聚合页 + N 个 object_list 子菜单.
        #   不挂 external_rate_source / pricing_period (M8 未开工, 挂了会误导「能配但配了不生效」).
        #   定价域定位 = 平台内置业务域(非应用包): 留在 meta/schemas/, 不拆 apps/ ——
        #     roadmap G2 (table_prefix) 实测未实现, 拆包会进已敞开的撞表风险区.
        {
            # [PRICE-MENU 2026-10-13] 价目与取价 —— 定价域 价目与取价 组聚合页
            #   背景: 定价域 15 个对象的自动菜单 (rate-table-list / calc-result-list 等)
            #     此前 parent_menu='' 且 show_in_sidebar=0, 既不在侧边栏、也没挂任何父节点
            #     => get_visible_menu_tree 捞不到, 导航树上完全不可达 (同 MD-MENU 2026-10-11 主数据修法).
            #   page_type=multi_object_hub + menu_path 非空 => dynamicRoutes 注册该路径,
            #     GenericTabContainer 把 children 渲染成 tab (聚合页, 与用户权限/主数据组同构).
            #   [结构约束] 子菜单必须是 page_type=object_list —— GenericTabContainer.vue
            #     只在 object_list 时给 tab 赋 objectType, 再用 GenericObjectList 渲染;
            #     子菜单若也是 multi_object_hub 则既无 component 又无 objectType,
            #     tab 标题渲染但内容空白 (GenericTabContainer.vue L94-95 记录的用户实测坑).
            #     故本组为**并列顶层hub**, 下挂 object_list 子菜单, 不再嵌套第三层.
            #   required_permissions: 声明本组 全部对象的权限码 —— 父容器不设门槛时
            #     子菜单可见性由各自守卫负责, 但列出可避免"组可见而组内全空"的误判。
            'menu_code': 'pricing-price',
            'menu_name': '价目与取价',
            'menu_path': '/pricing/price',
            'icon': 'List',
            'color': '#8b5cf6',
            'sort_order': 20,
            'parent_menu': '',
            'page_type': 'multi_object_hub',
            'primary_object_type': 'rate_table',
            'object_types': json.dumps(['rate_table', 'rate_record', 'rate_type', 'key_schema', 'lookup_sequence', 'exclusion_group']),
            'bo_bindings': json.dumps([
                {'bo_id': 'rate_table', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
                {'bo_id': 'rate_record', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
                {'bo_id': 'rate_type', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
                {'bo_id': 'key_schema', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
                {'bo_id': 'lookup_sequence', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
                {'bo_id': 'exclusion_group', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
            ]),
            'required_permissions': json.dumps([
                'rate_table:rate_table_create',
                'rate_table:rate_table_read',
                'rate_table:rate_table_update',
                'rate_table:rate_table_delete',
                'rate_table:rate_table_list',
                'rate_record:rate_record_create',
                'rate_record:rate_record_read',
                'rate_record:rate_record_update',
                'rate_record:rate_record_delete',
                'rate_record:rate_record_list',
                'rate_type:rate_type_create',
                'rate_type:rate_type_read',
                'rate_type:rate_type_update',
                'rate_type:rate_type_delete',
                'rate_type:rate_type_list',
                'key_schema:key_schema_create',
                'key_schema:key_schema_read',
                'key_schema:key_schema_update',
                'key_schema:key_schema_delete',
                'key_schema:key_schema_list',
                'lookup_sequence:lookup_sequence_create',
                'lookup_sequence:lookup_sequence_read',
                'lookup_sequence:lookup_sequence_update',
                'lookup_sequence:lookup_sequence_delete',
                'lookup_sequence:lookup_sequence_list',
                'exclusion_group:exclusion_group_create',
                'exclusion_group:exclusion_group_read',
                'exclusion_group:exclusion_group_update',
                'exclusion_group:exclusion_group_delete',
                'exclusion_group:exclusion_group_list',
            ]),
            'show_in_sidebar': 1,
            'data_permission_hint': json.dumps({
                'resource_types': ['rate_table', 'rate_record', 'rate_type', 'key_schema', 'lookup_sequence', 'exclusion_group'],
                'message': '建议分配价目与取价相关对象的数据权限'
            })
        },
        {
            # [PRICE-MENU 2026-10-13] 费率表 —— 定价域/价目与取价组
            #   权限码取自 permissions 表实际值 `{bo}:{bo}_{action}` (双段式),
            #     与 menu_auto_generator._derive_permissions_from_bindings 口径一致.
            #   show_in_sidebar=0: 与主数据组 11 条子菜单口径统一 —— 随父 hub 在侧边栏
            #     展开可见, 不进landing 卡片区.
            'menu_code': 'rate_table-list',
            'menu_name': '费率表',
            'menu_path': '/rate-table',
            'icon': 'List',
            'color': '#8b5cf6',
            'sort_order': 90,
            'parent_menu': 'pricing-price',
            'page_type': 'object_list',
            'primary_object_type': 'rate_table',
            'object_types': json.dumps(['rate_table']),
            'bo_bindings': json.dumps([
                {'bo_id': 'rate_table', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
            ]),
            'required_permissions': json.dumps([
                'rate_table:rate_table_create',
                'rate_table:rate_table_read',
                'rate_table:rate_table_update',
                'rate_table:rate_table_delete',
                'rate_table:rate_table_list',
            ]),
            'show_in_sidebar': 0,
            'data_permission_hint': json.dumps({
                'resource_types': ['rate_table'],
                'message': '建议分配费率表数据权限'
            })
        },
        {
            # [PRICE-MENU 2026-10-13] 费率记录 —— 定价域/价目与取价组
            #   权限码取自 permissions 表实际值 `{bo}:{bo}_{action}` (双段式),
            #     与 menu_auto_generator._derive_permissions_from_bindings 口径一致.
            #   show_in_sidebar=0: 与主数据组 11 条子菜单口径统一 —— 随父 hub 在侧边栏
            #     展开可见, 不进landing 卡片区.
            'menu_code': 'rate_record-list',
            'menu_name': '费率记录',
            'menu_path': '/rate-record',
            'icon': 'List',
            'color': '#8b5cf6',
            'sort_order': 91,
            'parent_menu': 'pricing-price',
            'page_type': 'object_list',
            'primary_object_type': 'rate_record',
            'object_types': json.dumps(['rate_record']),
            'bo_bindings': json.dumps([
                {'bo_id': 'rate_record', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
            ]),
            'required_permissions': json.dumps([
                'rate_record:rate_record_create',
                'rate_record:rate_record_read',
                'rate_record:rate_record_update',
                'rate_record:rate_record_delete',
                'rate_record:rate_record_list',
            ]),
            'show_in_sidebar': 0,
            'data_permission_hint': json.dumps({
                'resource_types': ['rate_record'],
                'message': '建议分配费率记录数据权限'
            })
        },
        {
            # [PRICE-MENU 2026-10-13] 费率类型 —— 定价域/价目与取价组
            #   权限码取自 permissions 表实际值 `{bo}:{bo}_{action}` (双段式),
            #     与 menu_auto_generator._derive_permissions_from_bindings 口径一致.
            #   show_in_sidebar=0: 与主数据组 11 条子菜单口径统一 —— 随父 hub 在侧边栏
            #     展开可见, 不进landing 卡片区.
            'menu_code': 'rate_type-list',
            'menu_name': '费率类型',
            'menu_path': '/rate-type',
            'icon': 'List',
            'color': '#8b5cf6',
            'sort_order': 92,
            'parent_menu': 'pricing-price',
            'page_type': 'object_list',
            'primary_object_type': 'rate_type',
            'object_types': json.dumps(['rate_type']),
            'bo_bindings': json.dumps([
                {'bo_id': 'rate_type', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
            ]),
            'required_permissions': json.dumps([
                'rate_type:rate_type_create',
                'rate_type:rate_type_read',
                'rate_type:rate_type_update',
                'rate_type:rate_type_delete',
                'rate_type:rate_type_list',
            ]),
            'show_in_sidebar': 0,
            'data_permission_hint': json.dumps({
                'resource_types': ['rate_type'],
                'message': '建议分配费率类型数据权限'
            })
        },
        {
            # [PRICE-MENU 2026-10-13] 匹配键表 —— 定价域/价目与取价组
            #   权限码取自 permissions 表实际值 `{bo}:{bo}_{action}` (双段式),
            #     与 menu_auto_generator._derive_permissions_from_bindings 口径一致.
            #   show_in_sidebar=0: 与主数据组 11 条子菜单口径统一 —— 随父 hub 在侧边栏
            #     展开可见, 不进landing 卡片区.
            'menu_code': 'key_schema-list',
            'menu_name': '匹配键表',
            'menu_path': '/key-schema',
            'icon': 'List',
            'color': '#8b5cf6',
            'sort_order': 93,
            'parent_menu': 'pricing-price',
            'page_type': 'object_list',
            'primary_object_type': 'key_schema',
            'object_types': json.dumps(['key_schema']),
            'bo_bindings': json.dumps([
                {'bo_id': 'key_schema', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
            ]),
            'required_permissions': json.dumps([
                'key_schema:key_schema_create',
                'key_schema:key_schema_read',
                'key_schema:key_schema_update',
                'key_schema:key_schema_delete',
                'key_schema:key_schema_list',
            ]),
            'show_in_sidebar': 0,
            'data_permission_hint': json.dumps({
                'resource_types': ['key_schema'],
                'message': '建议分配匹配键表数据权限'
            })
        },
        {
            # [PRICE-MENU 2026-10-13] 查找序列 —— 定价域/价目与取价组
            #   权限码取自 permissions 表实际值 `{bo}:{bo}_{action}` (双段式),
            #     与 menu_auto_generator._derive_permissions_from_bindings 口径一致.
            #   show_in_sidebar=0: 与主数据组 11 条子菜单口径统一 —— 随父 hub 在侧边栏
            #     展开可见, 不进landing 卡片区.
            'menu_code': 'lookup_sequence-list',
            'menu_name': '查找序列',
            'menu_path': '/lookup-sequence',
            'icon': 'List',
            'color': '#8b5cf6',
            'sort_order': 94,
            'parent_menu': 'pricing-price',
            'page_type': 'object_list',
            'primary_object_type': 'lookup_sequence',
            'object_types': json.dumps(['lookup_sequence']),
            'bo_bindings': json.dumps([
                {'bo_id': 'lookup_sequence', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
            ]),
            'required_permissions': json.dumps([
                'lookup_sequence:lookup_sequence_create',
                'lookup_sequence:lookup_sequence_read',
                'lookup_sequence:lookup_sequence_update',
                'lookup_sequence:lookup_sequence_delete',
                'lookup_sequence:lookup_sequence_list',
            ]),
            'show_in_sidebar': 0,
            'data_permission_hint': json.dumps({
                'resource_types': ['lookup_sequence'],
                'message': '建议分配查找序列数据权限'
            })
        },
        {
            # [PRICE-MENU 2026-10-13] 排斥组 —— 定价域/价目与取价组
            #   权限码取自 permissions 表实际值 `{bo}:{bo}_{action}` (双段式),
            #     与 menu_auto_generator._derive_permissions_from_bindings 口径一致.
            #   show_in_sidebar=0: 与主数据组 11 条子菜单口径统一 —— 随父 hub 在侧边栏
            #     展开可见, 不进landing 卡片区.
            'menu_code': 'exclusion_group-list',
            'menu_name': '排斥组',
            'menu_path': '/exclusion-group',
            'icon': 'List',
            'color': '#8b5cf6',
            'sort_order': 95,
            'parent_menu': 'pricing-price',
            'page_type': 'object_list',
            'primary_object_type': 'exclusion_group',
            'object_types': json.dumps(['exclusion_group']),
            'bo_bindings': json.dumps([
                {'bo_id': 'exclusion_group', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
            ]),
            'required_permissions': json.dumps([
                'exclusion_group:exclusion_group_create',
                'exclusion_group:exclusion_group_read',
                'exclusion_group:exclusion_group_update',
                'exclusion_group:exclusion_group_delete',
                'exclusion_group:exclusion_group_list',
            ]),
            'show_in_sidebar': 0,
            'data_permission_hint': json.dumps({
                'resource_types': ['exclusion_group'],
                'message': '建议分配排斥组数据权限'
            })
        },
        {
            # [PRICE-MENU 2026-10-13] 计算过程 —— 定价域 计算过程 组聚合页
            #   背景: 定价域 15 个对象的自动菜单 (rate-table-list / calc-result-list 等)
            #     此前 parent_menu='' 且 show_in_sidebar=0, 既不在侧边栏、也没挂任何父节点
            #     => get_visible_menu_tree 捞不到, 导航树上完全不可达 (同 MD-MENU 2026-10-11 主数据修法).
            #   page_type=multi_object_hub + menu_path 非空 => dynamicRoutes 注册该路径,
            #     GenericTabContainer 把 children 渲染成 tab (聚合页, 与用户权限/主数据组同构).
            #   [结构约束] 子菜单必须是 page_type=object_list —— GenericTabContainer.vue
            #     只在 object_list 时给 tab 赋 objectType, 再用 GenericObjectList 渲染;
            #     子菜单若也是 multi_object_hub 则既无 component 又无 objectType,
            #     tab 标题渲染但内容空白 (GenericTabContainer.vue L94-95 记录的用户实测坑).
            #     故本组为**并列顶层hub**, 下挂 object_list 子菜单, 不再嵌套第三层.
            #   required_permissions: 声明本组 全部对象的权限码 —— 父容器不设门槛时
            #     子菜单可见性由各自守卫负责, 但列出可避免"组可见而组内全空"的误判。
            'menu_code': 'pricing-calc',
            'menu_name': '计算过程',
            'menu_path': '/pricing/calc',
            'icon': 'DataAnalysis',
            'color': '#8b5cf6',
            'sort_order': 21,
            'parent_menu': '',
            'page_type': 'multi_object_hub',
            'primary_object_type': 'calc_procedure',
            'object_types': json.dumps(['calc_procedure', 'factor_catalog']),
            'bo_bindings': json.dumps([
                {'bo_id': 'calc_procedure', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
                {'bo_id': 'factor_catalog', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
            ]),
            'required_permissions': json.dumps([
                'calc_procedure:calc_procedure_create',
                'calc_procedure:calc_procedure_read',
                'calc_procedure:calc_procedure_update',
                'calc_procedure:calc_procedure_delete',
                'calc_procedure:calc_procedure_list',
                'factor_catalog:factor_catalog_create',
                'factor_catalog:factor_catalog_read',
                'factor_catalog:factor_catalog_update',
                'factor_catalog:factor_catalog_delete',
                'factor_catalog:factor_catalog_list',
            ]),
            'show_in_sidebar': 1,
            'data_permission_hint': json.dumps({
                'resource_types': ['calc_procedure', 'factor_catalog'],
                'message': '建议分配计算过程相关对象的数据权限'
            })
        },
        {
            # [PRICE-MENU 2026-10-13] 定价过程 —— 定价域/计算过程组
            #   权限码取自 permissions 表实际值 `{bo}:{bo}_{action}` (双段式),
            #     与 menu_auto_generator._derive_permissions_from_bindings 口径一致.
            #   show_in_sidebar=0: 与主数据组 11 条子菜单口径统一 —— 随父 hub 在侧边栏
            #     展开可见, 不进landing 卡片区.
            'menu_code': 'calc_procedure-list',
            'menu_name': '定价过程',
            'menu_path': '/calc-procedure',
            'icon': 'DataAnalysis',
            'color': '#8b5cf6',
            'sort_order': 90,
            'parent_menu': 'pricing-calc',
            'page_type': 'object_list',
            'primary_object_type': 'calc_procedure',
            'object_types': json.dumps(['calc_procedure']),
            'bo_bindings': json.dumps([
                {'bo_id': 'calc_procedure', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
            ]),
            'required_permissions': json.dumps([
                'calc_procedure:calc_procedure_create',
                'calc_procedure:calc_procedure_read',
                'calc_procedure:calc_procedure_update',
                'calc_procedure:calc_procedure_delete',
                'calc_procedure:calc_procedure_list',
            ]),
            'show_in_sidebar': 0,
            'data_permission_hint': json.dumps({
                'resource_types': ['calc_procedure'],
                'message': '建议分配定价过程数据权限'
            })
        },
        {
            # [PRICE-MENU 2026-10-13] 因子目录 —— 定价域/计算过程组
            #   权限码取自 permissions 表实际值 `{bo}:{bo}_{action}` (双段式),
            #     与 menu_auto_generator._derive_permissions_from_bindings 口径一致.
            #   show_in_sidebar=0: 与主数据组 11 条子菜单口径统一 —— 随父 hub 在侧边栏
            #     展开可见, 不进landing 卡片区.
            'menu_code': 'factor_catalog-list',
            'menu_name': '因子目录',
            'menu_path': '/factor-catalog',
            'icon': 'DataAnalysis',
            'color': '#8b5cf6',
            'sort_order': 91,
            'parent_menu': 'pricing-calc',
            'page_type': 'object_list',
            'primary_object_type': 'factor_catalog',
            'object_types': json.dumps(['factor_catalog']),
            'bo_bindings': json.dumps([
                {'bo_id': 'factor_catalog', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
            ]),
            'required_permissions': json.dumps([
                'factor_catalog:factor_catalog_create',
                'factor_catalog:factor_catalog_read',
                'factor_catalog:factor_catalog_update',
                'factor_catalog:factor_catalog_delete',
                'factor_catalog:factor_catalog_list',
            ]),
            'show_in_sidebar': 0,
            'data_permission_hint': json.dumps({
                'resource_types': ['factor_catalog'],
                'message': '建议分配因子目录数据权限'
            })
        },
        {
            # [PRICE-MENU 2026-10-13] 结果与追溯 —— 定价域 结果与追溯 组聚合页
            #   背景: 定价域 15 个对象的自动菜单 (rate-table-list / calc-result-list 等)
            #     此前 parent_menu='' 且 show_in_sidebar=0, 既不在侧边栏、也没挂任何父节点
            #     => get_visible_menu_tree 捞不到, 导航树上完全不可达 (同 MD-MENU 2026-10-11 主数据修法).
            #   page_type=multi_object_hub + menu_path 非空 => dynamicRoutes 注册该路径,
            #     GenericTabContainer 把 children 渲染成 tab (聚合页, 与用户权限/主数据组同构).
            #   [结构约束] 子菜单必须是 page_type=object_list —— GenericTabContainer.vue
            #     只在 object_list 时给 tab 赋 objectType, 再用 GenericObjectList 渲染;
            #     子菜单若也是 multi_object_hub 则既无 component 又无 objectType,
            #     tab 标题渲染但内容空白 (GenericTabContainer.vue L94-95 记录的用户实测坑).
            #     故本组为**并列顶层hub**, 下挂 object_list 子菜单, 不再嵌套第三层.
            #   required_permissions: 声明本组 全部对象的权限码 —— 父容器不设门槛时
            #     子菜单可见性由各自守卫负责, 但列出可避免"组可见而组内全空"的误判。
            'menu_code': 'pricing-result',
            'menu_name': '结果与追溯',
            'menu_path': '/pricing/result',
            'icon': 'Grid',
            'color': '#8b5cf6',
            'sort_order': 22,
            'parent_menu': '',
            'page_type': 'multi_object_hub',
            'primary_object_type': 'calc_result',
            'object_types': json.dumps(['calc_result', 'calc_detail', 'adjustment', 'allocation_rule', 'allocation_result', 'cumulative_usage', 'usage_group']),
            'bo_bindings': json.dumps([
                {'bo_id': 'calc_result', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
                {'bo_id': 'calc_detail', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
                {'bo_id': 'adjustment', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
                {'bo_id': 'allocation_rule', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
                {'bo_id': 'allocation_result', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
                {'bo_id': 'cumulative_usage', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
                {'bo_id': 'usage_group', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
            ]),
            'required_permissions': json.dumps([
                'calc_result:calc_result_create',
                'calc_result:calc_result_read',
                'calc_result:calc_result_update',
                'calc_result:calc_result_delete',
                'calc_result:calc_result_list',
                'calc_detail:calc_detail_create',
                'calc_detail:calc_detail_read',
                'calc_detail:calc_detail_update',
                'calc_detail:calc_detail_delete',
                'calc_detail:calc_detail_list',
                'adjustment:adjustment_create',
                'adjustment:adjustment_read',
                'adjustment:adjustment_update',
                'adjustment:adjustment_delete',
                'adjustment:adjustment_list',
                'allocation_rule:allocation_rule_create',
                'allocation_rule:allocation_rule_read',
                'allocation_rule:allocation_rule_update',
                'allocation_rule:allocation_rule_delete',
                'allocation_rule:allocation_rule_list',
                'allocation_result:allocation_result_create',
                'allocation_result:allocation_result_read',
                'allocation_result:allocation_result_update',
                'allocation_result:allocation_result_delete',
                'allocation_result:allocation_result_list',
                'cumulative_usage:cumulative_usage_create',
                'cumulative_usage:cumulative_usage_read',
                'cumulative_usage:cumulative_usage_update',
                'cumulative_usage:cumulative_usage_delete',
                'cumulative_usage:cumulative_usage_list',
                'usage_group:usage_group_create',
                'usage_group:usage_group_read',
                'usage_group:usage_group_update',
                'usage_group:usage_group_delete',
                'usage_group:usage_group_list',
            ]),
            'show_in_sidebar': 1,
            'data_permission_hint': json.dumps({
                'resource_types': ['calc_result', 'calc_detail', 'adjustment', 'allocation_rule', 'allocation_result', 'cumulative_usage', 'usage_group'],
                'message': '建议分配结果与追溯相关对象的数据权限'
            })
        },
        {
            # [PRICE-MENU 2026-10-13] 定价结果 —— 定价域/结果与追溯组
            #   权限码取自 permissions 表实际值 `{bo}:{bo}_{action}` (双段式),
            #     与 menu_auto_generator._derive_permissions_from_bindings 口径一致.
            #   show_in_sidebar=0: 与主数据组 11 条子菜单口径统一 —— 随父 hub 在侧边栏
            #     展开可见, 不进landing 卡片区.
            'menu_code': 'calc_result-list',
            'menu_name': '定价结果',
            'menu_path': '/calc-result',
            'icon': 'Grid',
            'color': '#8b5cf6',
            'sort_order': 90,
            'parent_menu': 'pricing-result',
            'page_type': 'object_list',
            'primary_object_type': 'calc_result',
            'object_types': json.dumps(['calc_result']),
            'bo_bindings': json.dumps([
                {'bo_id': 'calc_result', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
            ]),
            'required_permissions': json.dumps([
                'calc_result:calc_result_create',
                'calc_result:calc_result_read',
                'calc_result:calc_result_update',
                'calc_result:calc_result_delete',
                'calc_result:calc_result_list',
            ]),
            'show_in_sidebar': 0,
            'data_permission_hint': json.dumps({
                'resource_types': ['calc_result'],
                'message': '建议分配定价结果数据权限'
            })
        },
        {
            # [PRICE-MENU 2026-10-13] 定价明细 —— 定价域/结果与追溯组
            #   权限码取自 permissions 表实际值 `{bo}:{bo}_{action}` (双段式),
            #     与 menu_auto_generator._derive_permissions_from_bindings 口径一致.
            #   show_in_sidebar=0: 与主数据组 11 条子菜单口径统一 —— 随父 hub 在侧边栏
            #     展开可见, 不进landing 卡片区.
            'menu_code': 'calc_detail-list',
            'menu_name': '定价明细',
            'menu_path': '/calc-detail',
            'icon': 'Grid',
            'color': '#8b5cf6',
            'sort_order': 91,
            'parent_menu': 'pricing-result',
            'page_type': 'object_list',
            'primary_object_type': 'calc_detail',
            'object_types': json.dumps(['calc_detail']),
            'bo_bindings': json.dumps([
                {'bo_id': 'calc_detail', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
            ]),
            'required_permissions': json.dumps([
                'calc_detail:calc_detail_create',
                'calc_detail:calc_detail_read',
                'calc_detail:calc_detail_update',
                'calc_detail:calc_detail_delete',
                'calc_detail:calc_detail_list',
            ]),
            'show_in_sidebar': 0,
            'data_permission_hint': json.dumps({
                'resource_types': ['calc_detail'],
                'message': '建议分配定价明细数据权限'
            })
        },
        {
            # [PRICE-MENU 2026-10-13] 追溯调整 —— 定价域/结果与追溯组
            #   权限码取自 permissions 表实际值 `{bo}:{bo}_{action}` (双段式),
            #     与 menu_auto_generator._derive_permissions_from_bindings 口径一致.
            #   show_in_sidebar=0: 与主数据组 11 条子菜单口径统一 —— 随父 hub 在侧边栏
            #     展开可见, 不进landing 卡片区.
            'menu_code': 'adjustment-list',
            'menu_name': '追溯调整',
            'menu_path': '/adjustment',
            'icon': 'Edit',
            'color': '#8b5cf6',
            'sort_order': 92,
            'parent_menu': 'pricing-result',
            'page_type': 'object_list',
            'primary_object_type': 'adjustment',
            'object_types': json.dumps(['adjustment']),
            'bo_bindings': json.dumps([
                {'bo_id': 'adjustment', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
            ]),
            'required_permissions': json.dumps([
                'adjustment:adjustment_create',
                'adjustment:adjustment_read',
                'adjustment:adjustment_update',
                'adjustment:adjustment_delete',
                'adjustment:adjustment_list',
            ]),
            'show_in_sidebar': 0,
            'data_permission_hint': json.dumps({
                'resource_types': ['adjustment'],
                'message': '建议分配追溯调整数据权限'
            })
        },
        {
            # [PRICE-MENU 2026-10-13] 分摊规则 —— 定价域/结果与追溯组
            #   权限码取自 permissions 表实际值 `{bo}:{bo}_{action}` (双段式),
            #     与 menu_auto_generator._derive_permissions_from_bindings 口径一致.
            #   show_in_sidebar=0: 与主数据组 11 条子菜单口径统一 —— 随父 hub 在侧边栏
            #     展开可见, 不进landing 卡片区.
            'menu_code': 'allocation_rule-list',
            'menu_name': '分摊规则',
            'menu_path': '/allocation-rule',
            'icon': 'Grid',
            'color': '#8b5cf6',
            'sort_order': 93,
            'parent_menu': 'pricing-result',
            'page_type': 'object_list',
            'primary_object_type': 'allocation_rule',
            'object_types': json.dumps(['allocation_rule']),
            'bo_bindings': json.dumps([
                {'bo_id': 'allocation_rule', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
            ]),
            'required_permissions': json.dumps([
                'allocation_rule:allocation_rule_create',
                'allocation_rule:allocation_rule_read',
                'allocation_rule:allocation_rule_update',
                'allocation_rule:allocation_rule_delete',
                'allocation_rule:allocation_rule_list',
            ]),
            'show_in_sidebar': 0,
            'data_permission_hint': json.dumps({
                'resource_types': ['allocation_rule'],
                'message': '建议分配分摊规则数据权限'
            })
        },
        {
            # [PRICE-MENU 2026-10-13] 分摊结果 —— 定价域/结果与追溯组
            #   权限码取自 permissions 表实际值 `{bo}:{bo}_{action}` (双段式),
            #     与 menu_auto_generator._derive_permissions_from_bindings 口径一致.
            #   show_in_sidebar=0: 与主数据组 11 条子菜单口径统一 —— 随父 hub 在侧边栏
            #     展开可见, 不进landing 卡片区.
            'menu_code': 'allocation_result-list',
            'menu_name': '分摊结果',
            'menu_path': '/allocation-result',
            'icon': 'Grid',
            'color': '#8b5cf6',
            'sort_order': 94,
            'parent_menu': 'pricing-result',
            'page_type': 'object_list',
            'primary_object_type': 'allocation_result',
            'object_types': json.dumps(['allocation_result']),
            'bo_bindings': json.dumps([
                {'bo_id': 'allocation_result', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
            ]),
            'required_permissions': json.dumps([
                'allocation_result:allocation_result_create',
                'allocation_result:allocation_result_read',
                'allocation_result:allocation_result_update',
                'allocation_result:allocation_result_delete',
                'allocation_result:allocation_result_list',
            ]),
            'show_in_sidebar': 0,
            'data_permission_hint': json.dumps({
                'resource_types': ['allocation_result'],
                'message': '建议分配分摊结果数据权限'
            })
        },
        {
            # [PRICE-MENU 2026-10-13] 累计用量 —— 定价域/结果与追溯组
            #   权限码取自 permissions 表实际值 `{bo}:{bo}_{action}` (双段式),
            #     与 menu_auto_generator._derive_permissions_from_bindings 口径一致.
            #   show_in_sidebar=0: 与主数据组 11 条子菜单口径统一 —— 随父 hub 在侧边栏
            #     展开可见, 不进landing 卡片区.
            'menu_code': 'cumulative_usage-list',
            'menu_name': '累计用量',
            'menu_path': '/cumulative-usage',
            'icon': 'Grid',
            'color': '#8b5cf6',
            'sort_order': 95,
            'parent_menu': 'pricing-result',
            'page_type': 'object_list',
            'primary_object_type': 'cumulative_usage',
            'object_types': json.dumps(['cumulative_usage']),
            'bo_bindings': json.dumps([
                {'bo_id': 'cumulative_usage', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
            ]),
            'required_permissions': json.dumps([
                'cumulative_usage:cumulative_usage_create',
                'cumulative_usage:cumulative_usage_read',
                'cumulative_usage:cumulative_usage_update',
                'cumulative_usage:cumulative_usage_delete',
                'cumulative_usage:cumulative_usage_list',
            ]),
            'show_in_sidebar': 0,
            'data_permission_hint': json.dumps({
                'resource_types': ['cumulative_usage'],
                'message': '建议分配累计用量数据权限'
            })
        },
        {
            # [PRICE-MENU 2026-10-13] 条件更新组 —— 定价域/结果与追溯组
            #   权限码取自 permissions 表实际值 `{bo}:{bo}_{action}` (双段式),
            #     与 menu_auto_generator._derive_permissions_from_bindings 口径一致.
            #   show_in_sidebar=0: 与主数据组 11 条子菜单口径统一 —— 随父 hub 在侧边栏
            #     展开可见, 不进landing 卡片区.
            'menu_code': 'usage_group-list',
            'menu_name': '条件更新组',
            'menu_path': '/usage-group',
            'icon': 'Grid',
            'color': '#8b5cf6',
            'sort_order': 96,
            'parent_menu': 'pricing-result',
            'page_type': 'object_list',
            'primary_object_type': 'usage_group',
            'object_types': json.dumps(['usage_group']),
            'bo_bindings': json.dumps([
                {'bo_id': 'usage_group', 'role': 'primary',
                 'include_actions': ['create', 'read', 'update', 'delete', 'list']},
            ]),
            'required_permissions': json.dumps([
                'usage_group:usage_group_create',
                'usage_group:usage_group_read',
                'usage_group:usage_group_update',
                'usage_group:usage_group_delete',
                'usage_group:usage_group_list',
            ]),
            'show_in_sidebar': 0,
            'data_permission_hint': json.dumps({
                'resource_types': ['usage_group'],
                'message': '建议分配条件更新组数据权限'
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
    # [V007.49-A] 增量更新：每次启动都会 UPSERT，触发条件由 7.5 检测权限变更日志输出
    print("\n[步骤5] 同步 menu_permissions 表...")
    perm_new = 0
    perm_updated = 0
    for menu in system_menus:
        cursor.execute(
            "SELECT menu_code, required_permissions FROM menu_permissions WHERE menu_code = ?",
            [menu['menu_code']]
        )
        existing = cursor.fetchone()
        if existing:
            old_perms_str = existing[1]
            old_perms = set(json.loads(old_perms_str) if old_perms_str else [])
            # [FIX 2026-10-11] 声明侧的值是 json.dumps 的字符串, 必须先 loads 再取集合。
            # 原写法 set(menu['required_permissions']) 直接对字符串取集合, 得到的是
            # 字符集合 {' ', '"', ',', ...} 而非权限码, 使 added 恒为噪声、
            # [UPDATE] perm 行打印出 "+17 perms: [' ', '"', ...]" 这类假增量。
            # 此前未暴露是因为所有菜单的声明与库中已有值恰好相同 => added 恒为空集;
            # 新增菜单 (party / party_relation) 一进来就现形。
            new_perms = set(json.loads(menu['required_permissions']))
            added = new_perms - old_perms
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
            if added:
                print(f"  [UPDATE] perm: {menu['menu_name']} (+{len(added)} perms: {sorted(added)})")
                perm_updated += 1
            else:
                print(f"  [SKIP]   perm: {menu['menu_name']} (无变化)")
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
            print(f"  [NEW]    perm: {menu['menu_name']} ({menu['menu_code']})")
            perm_new += 1
    print(f"  [SUMMARY] menu_permissions: +{perm_new} 新增, ~{perm_updated} 更新")

    # ========== 步骤6：同步 menus 导航表（每次启动 UPSERT） ==========
    # [V007.49-A] 增量更新：每次启动都同步 bo_bindings 等关键字段
    print("\n[步骤6] 同步 menus 导航表...")
    nav_new = 0
    nav_updated = 0
    for menu in system_menus:
        cursor.execute(
            "SELECT menu_code, bo_bindings FROM menus WHERE menu_code = ?",
            [menu['menu_code']]
        )
        existing = cursor.fetchone()
        if existing:
            old_bindings = existing[1]
            new_bindings = json.dumps(menu.get('bo_bindings', '[]'), ensure_ascii=False)
            bindings_changed = old_bindings != new_bindings
            cursor.execute("""
                UPDATE menus SET
                    menu_name = ?, menu_path = ?, page_type = ?,
                    primary_object_type = ?, object_types = ?,
                    bo_bindings = ?, required_permissions = ?,
                    parent_menu = ?, icon = ?, color = ?,
                    description = ?, sort_order = ?, show_in_sidebar = ?
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
                # [MD-MENU 2026-10-11] 同 INSERT 分支: 未声明时为 1, 与历史行一致
                menu.get('show_in_sidebar', 1),
                menu['menu_code'],
            ])
            if bindings_changed:
                print(f"  [UPDATE] nav:  {menu['menu_name']} (bo_bindings changed)")
                nav_updated += 1
            else:
                print(f"  [SKIP]   nav:  {menu['menu_name']}")
        else:
            cursor.execute("""
                INSERT INTO menus
                (menu_code, menu_name, menu_path, page_type, object_types,
                 primary_object_type, bo_bindings, required_permissions,
                 parent_menu, icon, color, description,
                 sort_order, is_active, show_in_sidebar, auto_generated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 0)
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
                # [MD-MENU 2026-10-11] 子菜单声明 show_in_sidebar: 0 时按 0 落库
                #   (默认 1, 与历史行为一致; 仅 master-data 组的客户/供应商档案显式声明 0)
                menu.get('show_in_sidebar', 1),
            ])
            print(f"  [NEW]    nav:  {menu['menu_name']} ({menu['menu_code']})")
            nav_new += 1
    print(f"  [SUMMARY] menus: +{nav_new} 新增, ~{nav_updated} 更新")

    # ========== 步骤6.5: yaml import_export → menu bo_bindings 自动对齐 ==========
    # [H14.1] 单一事实源同步: 从 meta/schemas/*.yaml 读 import_export.import_enabled /
    # export_enabled, 自动补全到 menus.bo_bindings 对应 BO 的 include_actions.
    # 不删除人工显式声明 (yaml 未配但 menu 声明), 用 [KEEP] 日志标记.
    print("\n[步骤6.5] 对齐 yaml import_export → menu bo_bindings ...")
    schemas_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'schemas')
    yaml_action_map = {}  # bo_id -> {'import': bool, 'export': bool}
    for yaml_path in glob.glob(os.path.join(schemas_dir, '*.yaml')):
        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
        except Exception as e:
            print(f"  [WARN] 解析失败 {os.path.basename(yaml_path)}: {e}")
            continue
        if not data or 'id' not in data:
            continue
        ie = data.get('import_export')
        if not ie:
            continue
        bo_id = data['id']
        yaml_action_map[bo_id] = {
            'import': bool(ie.get('import_enabled', False)),
            'export': bool(ie.get('export_enabled', False)),
        }

    align_total = 0
    keep_total = 0
    for menu in system_menus:
        menu_code = menu['menu_code']
        # 从 DB 读最新 bo_bindings (步骤 6 UPSERT 后)
        cursor.execute("SELECT bo_bindings FROM menus WHERE menu_code = ?", [menu_code])
        row = cursor.fetchone()
        if not row or not row[0]:
            continue
        try:
            bindings = json.loads(row[0])
        except Exception:
            continue
        if not bindings:
            continue
        menu_dirty = False
        for b in bindings:
            bo_id = b.get('bo_id')
            if not bo_id:
                continue
            include_actions = b.get('include_actions', [])
            # 1) 从 yaml 派生 import/export
            yaml_acts = yaml_action_map.get(bo_id)
            if yaml_acts:
                for act_key, enabled in yaml_acts.items():
                    if enabled and act_key not in include_actions:
                        include_actions.append(act_key)
                        print(f"  [ALIGN] {menu_code}/{bo_id}: +{act_key}")
                        align_total += 1
                        menu_dirty = True
            # 2) 反向 KEEP: yaml 未配 export/import 但 menu 显式声明, 保留 (人工意图)
            for act_key in ('export', 'import'):
                if act_key in include_actions:
                    if not yaml_acts or not yaml_acts.get(act_key):
                        keep_total += 1
                        # 不打日志避免噪音, 仅在最终统计报告
        if menu_dirty:
            cursor.execute(
                "UPDATE menus SET bo_bindings = ? WHERE menu_code = ?",
                [json.dumps(bindings, ensure_ascii=False), menu_code]
            )
    if align_total == 0 and keep_total == 0:
        print("  [OK] 无需对齐 (yaml ↔ menu 已一致)")
    else:
        print(f"  [OK] 对齐完成: +{align_total} 个独立动作, 保留 {keep_total} 个人工显式声明")

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

    # ========== 步骤7.7：FR-013 轻量版 — 把菜单权限展开到角色 ==========
    # 背景 (BMRD-2026-06-14): 菜单的 required_permissions 只是元数据声明, 运行时权限
    # 检查 (permission_interceptor.py) 走 role_permissions 表, 中间链路断了导致
    # 角色访问菜单后做具体操作仍 403。修复: 把 role_menu_permissions 关联的
    # 菜单的 required_permissions 自动 grant 到 role_permissions。
    # 注: 这是 init-time 展开, 跟 SAP SU24 的"事务码 → 默认授权对象"等价。
    print("\n[步骤7.7] 展开菜单权限到角色 (FR-013 轻量版)...")
    cursor.execute("""
        SELECT rmp.permission_set_id, r.code, mp.required_permissions
        FROM permission_set_menu_permissions rmp
        JOIN permission_sets r ON r.id = rmp.permission_set_id
        JOIN menu_permissions mp ON mp.menu_code = rmp.menu_code
        WHERE r.is_active = 1
    """)
    role_menu_rows = cursor.fetchall()
    total_granted = 0
    roles_touched = 0
    for role_id, role_code, req_perms_str in role_menu_rows:
        if not req_perms_str:
            continue
        try:
            req_perms = json.loads(req_perms_str)
        except Exception:
            continue
        granted_for_role = 0
        for perm_code in req_perms:
            cursor.execute("SELECT id FROM permissions WHERE code = ?", [perm_code])
            perm_row = cursor.fetchone()
            if not perm_row:
                # 权限定义不存在, 跳过 (init_menus 会补)
                continue
            perm_id = perm_row[0]
            cursor.execute("""
                SELECT 1 FROM permission_set_permissions
                WHERE permission_set_id = ? AND permission_id = ?
            """, [role_id, perm_id])
            if cursor.fetchone():
                continue  # 已存在
            cursor.execute("""
                INSERT INTO permission_set_permissions (permission_set_id, permission_id, granted)
                VALUES (?, ?, 1)
            """, [role_id, perm_id])
            granted_for_role += 1
        if granted_for_role > 0:
            roles_touched += 1
            total_granted += granted_for_role
            rel_count = sum(1 for p in req_perms if 'relationship' in p)
            print(f"  [OK] {role_code}: +{granted_for_role} permissions (含 {rel_count} relationship)")

    if total_granted == 0:
        print("  [OK] 无需展开 (所有权限已存在)")
    else:
        print(f"  [OK] 跨 {roles_touched} 个角色共授权 {total_granted} 条 permissions")

    # ========== 步骤7.8：把核心系统菜单默认绑定到 admin 角色 ==========
    # 目的：新初始化环境 admin 开箱即可看到系统管理菜单（如 org-management），
    #   否则这些新菜单因无角色绑定而不出现在侧边栏/accessibleMenus。
    # role_menu_permissions 列: (role_id, menu_code, created_at)，无 granted 列。
    print("\n[步骤7.8] 默认绑定核心系统菜单到 admin 角色...")
    # 幂等: 仅当 admin 角色(role code='admin')存在时绑定, 不覆盖已有其他角色绑定
    admin_role = cursor.execute("SELECT id FROM permission_sets WHERE code = 'admin' AND is_active = 1 LIMIT 1").fetchone()
    if not admin_role:
        print("  [SKIP] 未找到 admin 角色 (code='admin'), 跳过默认绑定")
    else:
        admin_role_id = admin_role[0]
        bound = 0
        # 需默认对 admin 可见的系统菜单编码（新菜单在此登记）
        # [FIX 2026-09-01] 拆 3 个: 用户 / 权限集 / 组织管理
        default_admin_menus = ['user-management', 'permission-set-management', 'org-management']
        for mcode in default_admin_menus:
            # 仅当该菜单已入 menu_permissions 白名单才绑定
            if cursor.execute("SELECT 1 FROM menu_permissions WHERE menu_code = ?", [mcode]).fetchone():
                cursor.execute(
                    "INSERT OR IGNORE INTO permission_set_menu_permissions (permission_set_id, menu_code, created_at) VALUES (?,?,datetime('now'))",
                    [admin_role_id, mcode]
                )
                bound += 1
        if bound:
            print(f"  [OK] admin 角色(#{admin_role_id}) 已绑定 {bound} 个系统菜单: {default_admin_menus}")
        else:
            print("  [OK] 无需绑定")

    print("\n" + "=" * 60)
    print("[OK] 菜单权限表 & 导航表初始化完成！")
    print("=" * 60)

    conn.close()


if __name__ == '__main__':
    # [H14.1] 支持通过环境变量指定 db_path (与 server.py:455-456 行为一致)
    # 优先级: CLI 参数 > ARCH_DB_PATH > SQLITE_DB_PATH > meta/architecture.db
    db_path = None
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    if not db_path:
        db_path = os.environ.get('ARCH_DB_PATH')
    if not db_path:
        db_path = os.environ.get('SQLITE_DB_PATH')
    if not db_path:
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'architecture.db')
    print(f"数据库路径: {db_path}")
    init_menu_permissions(db_path)
