# 菜单元数据化与权限自动同步子 Spec

> **版本**: v1.2.0
> **最后更新**: 2026-05-19
> **状态**: In Progress（Phase 1,2 ✅ | Phase 2.5 Owner模型 ✅ | Phase 3,4 待实施）
> **主Spec**: [../spec.md](../spec.md)

## 1. 概述

### 1.1 背景

当前系统存在以下问题：

1. **路由硬编码**：前端路由在 `router/index.js` 中硬编码，未从菜单元数据动态生成
2. **权限同步不完整**：YAML actions 定义与 permissions 表可能存在同步缺口
3. **菜单与 BO 关联不明确**：`menu.yaml` 有 `object_types` 字段，但未形成闭环

### 1.2 目标

1. **菜单元数据化**：实现菜单从 YAML 元数据动态生成，消除路由硬编码
2. **权限自动同步**：确保 YAML actions → permissions 表的完整映射和自动同步
3. **菜单-权限联动**：实现 SAP PFCG 风格的菜单分配自动授予权限

### 1.3 对标参考

- **SAP PFCG**：角色维护事务，选菜单自动带入权限对象
- **SAP SU24**：权限对象维护，定义 TCode 与 Auth Object 的关联
- **Salesforce Profile**：配置文件与权限集的联动

***

## 2. 现状分析

### 2.1 当前菜单体系

| 组件       | 文件                       | 现状         | 问题         |
| -------- | ------------------------ | ---------- | ---------- |
| 前端路由     | `src/router/index.js`    | 硬编码 25+ 路由 | 未从元数据动态生成  |
| 菜单元数据    | `meta/schemas/menu.yaml` | 定义菜单 BO 结构 | 未与 BO 形成闭环 |
| 菜单自动生成   | `menu_auto_generator.py` | 从 BO 推导菜单  | 仅生成列表页菜单   |
| 菜单权限 API | `menu_permission_api.py` | 提供可见菜单树    | 正常         |

**路由硬编码示例**：

```javascript
// src/router/index.js - 当前硬编码
const routes = [
  { path: '/product-management', name: 'product-management', 
    component: () => import('@/views/GenericObjectList.vue'), 
    props: { objectType: 'product' } },
  // ... 更多硬编码
]
```

### 2.2 当前权限体系

| 组件     | 文件                           | 现状                       | 问题    |
| ------ | ---------------------------- | ------------------------ | ----- |
| 权限定义   | `permission.yaml`            | 定义权限 BO                  | 正常    |
| 权限同步   | `permission_sync_service.py` | 从 YAML actions 同步        | 需手动触发 |
| 角色菜单关联 | `role_menu_api.py`           | SAP PFCG 风格              | 正常    |
| 权限检查   | `auth_middleware.py`         | `require_permission` 装饰器 | 正常    |

**权限同步逻辑**：

```python
# permission_sync_service.py
def sync_all(self) -> Dict:
    expected = self._collect_all_permissions()  # 从 YAML actions 收集
    existing = self._load_existing_permissions()  # 从 DB 加载
    to_create = expected - existing
    # ... 创建缺失的权限
```

### 2.3 关键差距

#### 差距 1：路由与菜单元数据断裂

```
┌─────────────────┐     ┌─────────────────┐
│  menu.yaml      │     │  router/index.js │
│  (元数据定义)    │  ✗  │  (硬编码路由)    │
└─────────────────┘     └─────────────────┘
        │                       │
        ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│  menus 表       │     │  Vue Router     │
│  (DB 存储)      │     │  (运行时路由)    │
└─────────────────┘     └─────────────────┘
```

**问题**：菜单修改需要手动更新路由代码，违反 YAML 单一事实原则。

#### 差距 2：权限同步时机不明确

```yaml
# product.yaml - 定义了 actions
actions:
  - id: crud_create
    type: crud
    method: POST
    path: /api/v1/products
```

**问题**：

- 新增 action 后，权限可能未及时同步到 permissions 表
- 缺少自动触发机制（如 YAML 变更监听）

#### 差距 3：菜单与 BO 关联不完整

```yaml
# menu.yaml - 有字段但未形成闭环
fields:
  - id: object_types        # 关联业务对象 JSON 数组
  - id: primary_object_type # 主业务对象
```

**问题**：

- `object_types` 是自由文本，无 YAML 级别约束
- 无法在 YAML 中声明菜单与 BO 的关联关系

***

## 3. 方案设计

### 3.1 菜单元数据化方案

#### 3.1.1 核心设计：菜单 = 通用组件 × 对象(s) + 配置

```
┌─────────────────────────────────────────────────────────┐
│                    菜单元数据模型                         │
├─────────────────────────────────────────────────────────┤
│  menu_code: string          # 菜单编码                   │
│  menu_name: string          # 菜单名称                   │
│  menu_path: string          # 路由路径                   │
│  page_type: enum            # 页面类型                   │
│    - object_list            #   对象列表页               │
│    - object_detail          #   对象详情页               │
│    - multi_object_hub       #   多对象聚合页             │
│    - custom_page            #   自定义页面               │
│    - dashboard              #   仪表盘                   │
│  object_types: string[]     # 关联 BO ID 列表            │
│  primary_object_type: string # 主 BO（用于权限推导）      │
│  page_config: json          # 页面配置                   │
│  required_permissions: string[] # 所需权限（自动推导）    │
└─────────────────────────────────────────────────────────┘
```

#### 3.1.2 页面类型与组件映射

| page\_type         | 组件                        | 说明                   |
| ------------------ | ------------------------- | -------------------- |
| `object_list`      | `GenericObjectList.vue`   | 单对象列表页               |
| `object_detail`    | `ObjectDetailPage.vue`    | 对象详情页                |
| `multi_object_hub` | `GenericTabContainer.vue` | 多对象 Tab 容器           |
| `custom_page`      | 自定义组件                     | 需指定 `component_path` |
| `dashboard`        | `Dashboard.vue`           | 仪表盘                  |

#### 3.1.3 动态路由生成机制

**方案 A：启动时动态生成（推荐）**

```javascript
// src/router/dynamicRoutes.js
import { useMenuPermissions } from '@/composables/useMenuPermissions'

const PAGE_TYPE_COMPONENTS = {
  object_list: () => import('@/views/GenericObjectList.vue'),
  object_detail: () => import('@/views/ObjectDetailPage.vue'),
  multi_object_hub: () => import('@/views/GenericTabContainer.vue'),
  dashboard: () => import('@/views/Dashboard.vue'),
}

export async function generateDynamicRoutes() {
  const { loadMenuPermissions, menuPermissions } = useMenuPermissions()
  await loadMenuPermissions()
  
  return menuPermissions.value.map(menu => ({
    path: menu.menu_path,
    name: menu.menu_code,
    component: PAGE_TYPE_COMPONENTS[menu.page_type] || PAGE_TYPE_COMPONENTS.object_list,
    props: {
      objectType: menu.primary_object_type,
      objectTypes: menu.object_types,
      pageConfig: menu.page_config,
      group: menu.menu_code, // for multi_object_hub
    },
    meta: {
      title: menu.menu_name,
      requiresAuth: true,
      requiredPermissions: menu.required_permissions,
    }
  }))
}
```

**方案 B：构建时静态生成**

```javascript
// scripts/generateRoutes.js - 构建脚本
const fs = require('fs')
const yaml = require('js-yaml')

function generateRoutesFromMenuYaml() {
  const menuConfig = yaml.load(fs.readFileSync('meta/schemas/menu.yaml', 'utf8'))
  // 生成 routes 配置并写入 router/routes.generated.js
}
```

**推荐方案 A**，原因：

- 支持运行时菜单变更
- 无需重新构建
- 与权限检查天然集成

#### 3.1.4 菜单与 BO 关联声明

**增强 menu.yaml**：

```yaml
# meta/schemas/menu.yaml
id: menu
fields:
  # ... 现有字段

  # 新增：BO 关联声明（YAML 级别约束）
  - id: bo_bindings
    name: BO绑定
    type: json
    description: |
      声明菜单与 BO 的关联关系，用于：
      1. 自动推导 required_permissions
      2. 自动生成页面配置
      3. 数据权限提示
    schema:
      type: array
      items:
        type: object
        properties:
          bo_id:
            type: string
            description: 关联的 BO ID
          role:
            type: string
            enum: [primary, secondary, reference]
            description: |
              primary: 主对象，用于权限推导
              secondary: 辅助对象，显示在页面中
              reference: 引用对象，用于 Value Help
          include_actions:
            type: array
            items: { type: string }
            description: 包含的操作，用于权限推导
          exclude_actions:
            type: array
            items: { type: string }
            description: 排除的操作
```

**示例**：

```yaml
# 在 menus 表或 menu.yaml 实例中
menu_code: product-management
menu_name: 产品管理
page_type: object_list
bo_bindings:
  - bo_id: product
    role: primary
    include_actions: [crud_list, crud_read, crud_create, crud_update, crud_delete]
  - bo_id: version
    role: secondary
    include_actions: [crud_list, crud_read]
```

### 3.2 权限自动同步方案

#### 3.2.1 权限编码规范

```
权限编码格式: {resource_type}:{action_suffix}

示例:
- product:create    # 创建产品
- product:read      # 读取产品
- product:update    # 更新产品
- product:delete    # 删除产品
- role:assign_user  # 角色分配用户（业务操作）
- *                 # 超级权限
```

**Action ID → Permission Suffix 映射**：

```python
# models.py - MetaAction
ACTION_SUFFIX_MAP = {
    'crud_create': 'create',
    'crud_read': 'read',
    'crud_list': 'read',  # list 映射到 read
    'crud_update': 'update',
    'crud_delete': 'delete',
    'crud_export': 'export',
    'crud_import': 'import',
    # 业务操作保持原 ID
}
```

#### 3.2.2 权限同步触发机制

**方案：多触发点同步**

```
┌─────────────────────────────────────────────────────────┐
│                   权限同步触发点                          │
├─────────────────────────────────────────────────────────┤
│  1. 系统启动时                                           │
│     server.py → init_auth() → sync_all()                │
│                                                         │
│  2. YAML 变更时（开发环境）                               │
│     yaml_watcher.py → on_yaml_change() → sync_for_object()│
│                                                         │
│  3. BO 注册时                                           │
│     registry.register() → trigger_permission_sync()     │
│                                                         │
│  4. 手动触发                                            │
│     POST /api/v1/admin/permissions/sync                 │
└─────────────────────────────────────────────────────────┘
```

**增强 PermissionSyncService**：

```python
# permission_sync_service.py
class PermissionSyncService:
    
    def sync_all(self) -> Dict:
        """全量同步：从所有 YAML actions 同步到 permissions 表"""
        expected = self._collect_all_permissions()
        existing = self._load_existing_permissions()
        
        to_create = expected - existing
        to_update = expected & existing  # 检查名称变更
        orphaned = existing - expected   # 识别孤立权限
        
        # 创建新权限
        for code in to_create:
            self._create_permission(code)
        
        # 更新权限名称（如有变更）
        for code in to_update:
            self._update_permission_if_changed(code)
        
        # 记录孤立权限（不自动删除，需人工确认）
        if orphaned:
            logger.warning(f"Orphaned permissions: {orphaned}")
        
        return {
            'created': list(to_create),
            'updated': list(to_update),
            'orphaned': list(orphaned),
        }
    
    def sync_for_object(self, object_id: str) -> Dict:
        """增量同步：同步单个 BO 的权限"""
        meta_obj = registry.get(object_id)
        if not meta_obj:
            return {'error': f'Object not found: {object_id}'}
        
        perms = self._derive_from_object(meta_obj)
        created = []
        for code in perms:
            if self._create_permission_if_not_exists(code):
                created.append(code)
        
        return {'created': created, 'total': len(perms)}
    
    def validate_consistency(self) -> Dict:
        """一致性校验：检查 YAML actions 与 permissions 表的一致性"""
        expected = self._collect_all_permissions()
        existing = self._load_existing_permissions()
        
        missing = expected - existing
        extra = existing - expected
        
        return {
            'is_consistent': len(missing) == 0,
            'missing_permissions': list(missing),
            'extra_permissions': list(extra),
            'expected_count': len(expected),
            'existing_count': len(existing),
        }
```

#### 3.2.3 菜单分配 → 权限自动授予

**当前实现（role\_menu\_api.py）**：

```python
@role_menu_bp.route('/<int:role_id>/menu-permissions', methods=['PUT'])
def update_role_menu_permissions(role_id):
    """SAP PFCG 风格：选中菜单时自动授予所需功能权限"""
    menu_codes = request.json.get('menu_codes', [])
    
    with ds.transaction():
        # 1. 更新角色菜单关联
        ds.execute("DELETE FROM role_menu_permissions WHERE role_id = ?", [role_id])
        for menu_code in menu_codes:
            ds.execute("INSERT INTO role_menu_permissions ...", [role_id, menu_code])
        
        # 2. 自动授予关联的功能权限
        auto_perm_codes = set()
        for menu_code in menu_codes:
            menu = get_menu(menu_code)
            auto_perm_codes.update(menu.required_permissions)
        
        for perm_code in auto_perm_codes:
            ds.execute("INSERT OR IGNORE INTO role_permissions ...", [role_id, perm_id])
    
    return {'synced_permissions': list(auto_perm_codes)}
```

**增强：支持权限来源追溯**

```sql
-- role_permissions 表增加来源字段
ALTER TABLE role_permissions ADD COLUMN source VARCHAR(20) DEFAULT 'manual';
ALTER TABLE role_permissions ADD COLUMN source_menu_code VARCHAR(200);
ALTER TABLE role_permissions ADD COLUMN granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
```

```python
# 权限来源类型
class PermissionSource(Enum):
    MANUAL = 'manual'        # 手动授予
    AUTO_MENU = 'auto_menu'  # 菜单自动带入
    AUTO_ROLE = 'auto_role'  # 角色继承
    AUTO_GROUP = 'auto_group'  # 用户组继承
```

### 3.3 菜单-权限联动机制

#### 3.3.1 统一权限视图（SAP PFCG 风格）

```
┌─────────────────────────────────────────────────────────┐
│                 角色权限配置界面                          │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────┐   │
│  │ 菜单树（入口层）                                  │   │
│  │ ☑ 产品管理                                       │   │
│  │   └─ 自动带入: product:read, product:create...  │   │
│  │ ☑ 用户管理                                       │   │
│  │   └─ 自动带入: user:read, user:update...        │   │
│  │ ☐ 系统配置                                       │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 功能权限（能力层）                                │   │
│  │ product:read     [✓ 自动]                        │   │
│  │ product:create   [✓ 自动]                        │   │
│  │ user:read        [✓ 自动]                        │   │
│  │ report:export    [  手动]  ← 额外授予            │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 数据权限（约束层）                                │   │
│  │ 产品: [全部 / 本人 / 部门]                        │   │
│  │ 用户: [全部 / 本人]                              │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

#### 3.3.2 权限一致性检查

```python
# menu_permission_service.py
class MenuPermissionService:
    
    def check_menu_consistency(self, user_id: int, menu_code: str) -> Dict:
        """检查用户菜单权限一致性
        
        返回：
        - has_menu: 是否有菜单权限
        - has_required_permissions: 是否有所有必需的功能权限
        - missing_permissions: 缺失的功能权限
        - is_consistent: 是否一致
        """
        user_perms = self._get_user_permissions(user_id)
        menu = self._get_menu(menu_code)
        required = menu.required_permissions or []
        
        missing = [p for p in required if p not in user_perms]
        
        return {
            'has_menu': self._has_menu_access(user_id, menu_code),
            'has_required_permissions': len(missing) == 0,
            'missing_permissions': missing,
            'is_consistent': len(missing) == 0,
        }
    
    def get_user_permission_report(self, user_id: int) -> Dict:
        """生成用户权限一致性报告"""
        menus = self._get_user_menus(user_id)
        inconsistencies = []
        
        for menu in menus:
            check = self.check_menu_consistency(user_id, menu.menu_code)
            if not check['is_consistent']:
                inconsistencies.append({
                    'menu_code': menu.menu_code,
                    'menu_name': menu.menu_name,
                    'missing_permissions': check['missing_permissions'],
                })
        
        return {
            'user_id': user_id,
            'total_menus': len(menus),
            'inconsistent_count': len(inconsistencies),
            'inconsistencies': inconsistencies,
            'is_consistent': len(inconsistencies) == 0,
        }
```

***

## 4. 实施计划

> **当前状态**: Phase 1 ✅ | Phase 2 ✅ | Phase 2.5 Owner模型 ✅ | Phase 3 ⏳ | Phase 4 ⏳
> **最后更新**: 2026-05-19
> **完成进度**: 80% (4/5 Phases)
> **主Spec任务ID映射**: P0-1, P1-1, P1-2, P1, P2, P3-1, P3-2, P4, P5

### Phase 1：权限同步增强（1 周） ✅ 已完成

**目标**：确保 YAML actions → permissions 表的完整同步

**任务**：

1. ✅ 增强 `PermissionSyncService.sync_all()` 支持增量同步
2. ✅ 添加 `validate_consistency()` 一致性校验方法
3. ✅ 添加 `/api/v1/admin/permissions/sync` 手动触发 API
4. ✅ 添加 `/api/v1/admin/permissions/validate` 校验 API
5. ⏳ 系统启动时自动调用 `sync_all()`（待集成）

**验收标准**：

- [x] 所有 YAML actions 都有对应的 permissions 记录
- [x] 一致性校验 API 返回 `is_consistent: true`
- [x] 新增 action 后自动创建权限

**实施文件**：
- `meta/services/permission_sync_service.py` - 增强权限同步服务
- `meta/api/permission_sync_api.py` - 新增权限同步管理 API
- `meta/server.py` - 注册新 API blueprint

### Phase 2：菜单元数据增强（1 周） ✅ 已完成

**目标**：增强菜单与 BO 的关联声明

**任务**：

1. ✅ 增强 `menu.yaml` 添加 `bo_bindings` 字段
2. ✅ 更新 `MenuAutoGenerator` 支持 `bo_bindings` 推导
3. ✅ 添加菜单-BO 关联校验
4. ✅ 更新菜单权限 API 返回 `bo_bindings` 信息

**验收标准**：

- [x] 菜单可声明与多个 BO 的关联关系
- [x] `required_permissions` 从 `bo_bindings` 自动推导
- [x] 菜单详情页显示关联的 BO 信息

**实施文件**：
- `meta/schemas/menu.yaml` - 新增 bo_bindings、required_permissions 等字段
- `meta/services/menu_auto_generator.py` - 支持 bo_bindings 推导
- `meta/api/menu_permission_api.py` - 返回 bo_bindings
- `meta/api/role_menu_api.py` - 返回 bo_bindings

### Phase 3：动态路由生成（1 周） ⏳ 待实施

> **详细方案**: [实际现状细化方案](refined-implementation-plan.md)

**目标**：前端路由从菜单元数据动态生成

**任务**：

1. ⏳ 创建 `src/router/dynamicRoutes.js` 动态路由生成模块
2. ⏳ 修改 `src/router/index.js` 集成动态路由
3. ⏳ 添加路由守卫检查 `required_permissions`
4. ⏳ 迁移硬编码路由到菜单数据

**验收标准**：

- [ ] 菜单变更后刷新页面即可生效
- [ ] 无权限菜单不生成路由
- [ ] 路由 meta 包含权限信息

**已有基础**：
- ✅ `AppRootLayout` 已从 API 动态获取导航 (`accessibleMenus → apiNavigationItems`)
- ✅ `deriveRoutePath()` 已根据 `page_type` 自动推导路径
- ✅ 菜单已支持离线缓存 (`useMenuCache`)
- ✅ `PAGE_TYPE_COMPONENTS` 映射可复用

**实施文件**：
- `src/router/dynamicRoutes.js` - 动态路由生成（新建）
- `src/router/index.js` - 集成动态路由（修改）
- `src/components/common/AppRootLayout.vue` - 初始化动态路由（修改）

### Phase 4：权限来源追溯（1 周） ✅ 已完成

**目标**：支持权限来源追溯和一致性检查

**任务**：

1. ✅ 扩展 `role_permissions` 表添加来源字段
2. ✅ 更新角色菜单分配 API 记录权限来源
3. ✅ 添加权限一致性检查 API
4. ✅ 添加权限一致性报告 API

**验收标准**：

- [x] 可追溯每个权限的来源（手动/菜单自动）
- [x] 可检查用户菜单-权限一致性
- [x] 管理界面显示权限来源

**实施文件**：
- `scripts/migrate_role_permissions_source.py` - 数据库迁移脚本
- `meta/api/role_menu_api.py` - 记录权限来源
- `src/views/SystemManagement/components/MenuPermissionMatrix.vue` - 显示 bo_bindings

**数据库变更**：
```sql
-- role_permissions 表新增字段
ALTER TABLE role_permissions ADD COLUMN source VARCHAR(20) DEFAULT 'manual';
ALTER TABLE role_permissions ADD COLUMN source_menu_code VARCHAR(200);
ALTER TABLE role_permissions ADD COLUMN granted_at TIMESTAMP;

-- menus 表新增字段
ALTER TABLE menus ADD COLUMN bo_bindings TEXT;
ALTER TABLE menus ADD COLUMN required_permissions TEXT;
ALTER TABLE menus ADD COLUMN required_any_permission BOOLEAN DEFAULT 0;
ALTER TABLE menus ADD COLUMN data_permission_hint TEXT;
```

### Phase 5：迁移与测试（1 周） ⏳ 待实施

> **详细方案**: [实际现状细化方案](refined-implementation-plan.md) 第 4-5 节

**目标**：迁移现有硬编码路由，完善测试

**任务**：

1. ⏳ 将 `router/index.js` 硬编码路由迁移到菜单元数据
2. ⏳ 创建权限同步服务测试 (`test_permission_sync_service.py`)
3. ⏳ 创建权限同步 API 测试 (`test_permission_sync_api.py`)
4. ⏳ 回归测试 + 更新文档

**验收标准**：

- [ ] 所有硬编码路由已迁移
- [ ] 新增测试覆盖率为 100%
- [ ] 回归测试全部通过
- [ ] 文档更新完成

***

## 5. API 设计

### 5.1 权限同步 API

```
POST /api/v1/admin/permissions/sync
请求: { "scope": "all" | "object", "object_id": "product" }
响应: { "created": [...], "updated": [...], "orphaned": [...] }

GET /api/v1/admin/permissions/validate
响应: { 
  "is_consistent": true,
  "missing_permissions": [],
  "extra_permissions": [],
  "expected_count": 100,
  "existing_count": 100
}
```

### 5.2 菜单权限 API（增强）

```
GET /api/v1/menu-permission/visible
响应: {
  "menus": [{
    "menu_code": "product-management",
    "menu_name": "产品管理",
    "menu_path": "/product-management",
    "page_type": "object_list",
    "primary_object_type": "product",
    "object_types": ["product", "version"],
    "bo_bindings": [...],
    "required_permissions": ["product:read", "product:create", ...],
    "page_config": {...}
  }]
}

GET /api/v1/roles/{role_id}/unified-permissions
响应: {
  "menus": [{
    "menu_code": "product-management",
    "assigned": true,
    "required_permissions": [...],
    "required_permissions_display": [{
      "code": "product:read",
      "label": "读取产品",
      "granted": true,
      "source": "auto"
    }]
  }],
  "role_function_permissions": [...],
  "summary": {...}
}
```

### 5.3 权限一致性检查 API

```
GET /api/v1/menu-permission/menus/{menu_code}/consistency
响应: {
  "has_menu": true,
  "has_required_permissions": true,
  "missing_permissions": [],
  "is_consistent": true
}

GET /api/v1/menu-permission/menus/report
响应: {
  "user_id": 1,
  "total_menus": 10,
  "inconsistent_count": 0,
  "inconsistencies": [],
  "is_consistent": true
}
```

***

## 6. 数据模型变更

### 6.1 menu 表增强

```sql
-- 新增字段
ALTER TABLE menus ADD COLUMN bo_bindings TEXT;  -- JSON
ALTER TABLE menus ADD COLUMN required_permissions TEXT;  -- JSON array
ALTER TABLE menus ADD COLUMN required_any_permission BOOLEAN DEFAULT FALSE;
ALTER TABLE menus ADD COLUMN data_permission_hint TEXT;  -- JSON
```

### 6.2 role\_permissions 表增强

```sql
-- 新增字段
ALTER TABLE role_permissions ADD COLUMN source VARCHAR(20) DEFAULT 'manual';
ALTER TABLE role_permissions ADD COLUMN source_menu_code VARCHAR(200);
ALTER TABLE role_permissions ADD COLUMN granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
```

### 6.3 permissions 表索引

```sql
-- 优化查询
CREATE INDEX idx_permissions_code ON permissions(code);
CREATE INDEX idx_permissions_resource_type ON permissions(resource_type);
CREATE INDEX idx_role_permissions_role ON role_permissions(role_id);
CREATE INDEX idx_role_permissions_source ON role_permissions(source);
```

***

## 7. 风险与缓解

| 风险       | 影响            | 缓解措施           |
| -------- | ------------- | -------------- |
| 动态路由性能   | 启动时加载菜单可能慢    | 使用缓存，异步加载      |
| 权限同步遗漏   | 新增 action 未同步 | 多触发点同步，启动时自动同步 |
| 菜单-权限不一致 | 用户有菜单但无权限     | 一致性检查 API，定期巡检 |
| 迁移数据丢失   | 硬编码路由迁移遗漏     | 迁移脚本校验，灰度发布    |

***

## 8. 验收标准

### 8.1 功能验收

- [ ] 所有 YAML actions 都有对应的 permissions 记录
- [ ] 菜单变更后刷新页面即可生效
- [ ] 角色分配菜单时自动授予关联权限
- [ ] 权限来源可追溯
- [ ] 一致性检查 API 正常工作

### 8.2 性能验收

- [ ] 动态路由生成时间 < 500ms
- [ ] 权限同步时间 < 5s（100 个 BO）
- [ ] 一致性检查时间 < 1s

### 8.3 安全验收

- [ ] 无权限菜单不生成路由
- [ ] 路由守卫正确检查权限
- [ ] 权限来源不可篡改

***

## 9. 现有角色权限配置页面适配

### 9.1 现有组件分析

当前系统已实现完整的角色权限配置界面，核心组件如下：

| 组件 | 路径 | 功能 | 适配状态 |
|------|------|------|----------|
| **RoleDetail.vue** | `src/views/SystemManagement/RoleDetail.vue` | 角色详情页，包含权限配置 Tab | ✅ 无需修改 |
| **PermissionConfigPanel.vue** | `src/views/SystemManagement/components/PermissionConfigPanel.vue` | 权限配置面板，整合菜单/功能/数据权限 | ✅ 无需修改 |
| **MenuPermissionMatrix.vue** | `src/views/SystemManagement/components/MenuPermissionMatrix.vue` | 菜单权限矩阵，SAP PFCG 风格 | ⚠️ 需增强 bo_bindings 显示 |
| **useMenuPermission.ts** | `src/views/SystemManagement/composables/useMenuPermission.ts` | 菜单权限 composable | ✅ 已支持统一权限 API |
| **role_menu_api.py** | `meta/api/role_menu_api.py` | 角色菜单权限 API | ⚠️ 需返回 bo_bindings |

### 9.2 现有实现亮点

**已实现的 SAP PFCG 风格功能**：

1. **菜单-权限自动联动**：
```typescript
// MenuPermissionMatrix.vue - 勾选菜单时自动授予权限
function handleToggleMenu(menu: Menu) {
  menu.assigned = !menu.assigned
  
  if (menu.assigned) {
    // 自动授予关联的功能权限
    menu.required_permissions?.forEach(p => {
      p.granted = true
      p.source = 'auto'  // 标记来源为自动
    })
  }
}
```

2. **权限来源追溯**：
```typescript
interface Permission {
  code: string
  label: string
  granted: boolean
  source: 'auto' | 'manual' | ''  // 已支持来源追溯
}
```

3. **统一权限视图 API**：
```typescript
// useMenuPermission.ts - 调用统一权限 API
const response = await fetch(
  `${API_BASE_V2}/roles/${roleId.value}/unified-permissions`,
  { headers: boService._getHeaders() }
)
```

### 9.3 适配方案

#### 9.3.1 MenuPermissionMatrix 增强

**新增 bo_bindings 显示**：

```vue
<!-- MenuPermissionMatrix.vue - 增强菜单卡片 -->
<div class="menu-card-body">
  <!-- 新增：BO 绑定信息 -->
  <div v-if="menu.bo_bindings?.length" class="bo-bindings-section">
    <div class="bo-label">
      <AppIcon name="cube" :size="12" />
      关联业务对象
    </div>
    <div class="bo-binding-list">
      <div v-for="binding in menu.bo_bindings" :key="binding.bo_id" 
           :class="['bo-item', `role-${binding.role}`]">
        <span class="bo-name">{{ getBoName(binding.bo_id) }}</span>
        <span class="bo-role-tag">{{ getBindingRoleLabel(binding.role) }}</span>
      </div>
    </div>
  </div>
  
  <!-- 现有：功能权限列表 -->
  <div v-if="menu.required_permissions?.length" class="capability-list">
    ...
  </div>
</div>
```

**新增样式**：
```scss
.bo-bindings-section {
  margin-bottom: var(--spacing-sm);
  padding: var(--spacing-sm);
  background: var(--color-bg-spotlight);
  border-radius: var(--radius-sm);
}

.bo-item {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: 11px;
  
  &.role-primary {
    background: #e6f7ff;
    color: #1890ff;
  }
  
  &.role-secondary {
    background: #f6ffed;
    color: #52c41a;
  }
  
  &.role-reference {
    background: #fff7e6;
    color: #fa8c16;
  }
}
```

#### 9.3.2 API 返回增强

**role_menu_api.py 返回 bo_bindings**：

```python
# role_menu_api.py - get_role_unified_permissions
@role_menu_bp.route('/<int:role_id>/unified-permissions', methods=['GET'])
def get_role_unified_permissions(role_id):
    # ... 现有逻辑
    
    for menu in all_menus:
        # 新增：解析并返回 bo_bindings
        bo_bindings_raw = menu.get('bo_bindings') or '[]'
        try:
            bo_bindings = json.loads(bo_bindings_raw) if isinstance(bo_bindings_raw, str) else bo_bindings_raw
        except:
            bo_bindings = []
        
        result.append({
            'menu_code': code,
            'display_name': menu.get('menu_name', code),
            # ... 现有字段
            
            # 新增
            'bo_bindings': bo_bindings,
            'primary_object_type': menu.get('primary_object_type', ''),
            'object_types': _safe_parse_json_list(menu.get('object_types')),
        })
```

#### 9.3.3 权限来源追溯数据库变更

**现有组件已支持 source 字段**，只需扩展数据库：

```sql
-- role_permissions 表增加来源字段
ALTER TABLE role_permissions ADD COLUMN source VARCHAR(20) DEFAULT 'manual';
ALTER TABLE role_permissions ADD COLUMN source_menu_code VARCHAR(200);
ALTER TABLE role_permissions ADD COLUMN granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
```

**后端保存时记录来源**：

```python
# role_menu_api.py - update_role_menu_permissions
for code in auto_perm_codes:
    pid = perm_id_map.get(code)
    if pid:
        ds.execute(
            """INSERT OR IGNORE INTO role_permissions 
               (role_id, permission_id, source, source_menu_code, granted_at) 
               VALUES (?, ?, 'auto', ?, CURRENT_TIMESTAMP)""",
            [role_id, pid, menu_code]  # 记录来源菜单
        )
```

### 9.4 适配检查清单

| 检查项 | 现状 | 适配动作 |
|--------|------|----------|
| RoleDetail.vue 是否需要修改 | ✅ 无需修改 | - |
| PermissionConfigPanel.vue 是否需要修改 | ✅ 无需修改 | - |
| MenuPermissionMatrix 是否支持 bo_bindings | ⚠️ 未显示 | 增加显示区域 |
| useMenuPermission 是否支持新字段 | ✅ 自动透传 | - |
| unified-permissions API 是否返回 bo_bindings | ⚠️ 未返回 | 增加返回字段 |
| 数据库 role_permissions 是否有 source 字段 | ⚠️ 未添加 | ALTER TABLE |
| 权限来源是否正确记录 | ⚠️ 未记录 | 修改保存逻辑 |

### 9.5 兼容性保证

**向后兼容**：
- `bo_bindings` 为空时不影响现有功能
- `source` 字段默认值为 `'manual'`，兼容历史数据
- API 新增字段不影响现有前端解析

**迁移策略**：
1. 先执行数据库 ALTER TABLE
2. 部署后端 API 更新
3. 部署前端组件更新
4. 历史数据 source 字段保持 `'manual'`

### 9.6 菜单 UI 框架组件适配

#### 9.6.1 组件架构分析

当前菜单 UI 框架已实现完整的元数据驱动架构：

```
┌─────────────────────────────────────────────────────────────────┐
│                      菜单渲染链路                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  useMenuPermissions() ──→ accessibleMenus                       │
│         │                                                       │
│         ▼                                                       │
│  ┌─────────────────┐     ┌─────────────────┐                   │
│  │ AppRootLayout   │ ──→ │ navigationItems │                   │
│  │ (根布局)        │     │ (菜单树转换)    │                   │
│  └─────────────────┘     └─────────────────┘                   │
│         │                        │                              │
│         ▼                        ▼                              │
│  ┌─────────────────┐     ┌─────────────────┐                   │
│  │ AppLayout       │ ──→ │ sidebarItems    │                   │
│  │ (应用布局)      │     │ (侧边栏菜单)    │                   │
│  └─────────────────┘     └─────────────────┘                   │
│         │                        │                              │
│         ▼                        ▼                              │
│  ┌─────────────────┐     ┌─────────────────┐                   │
│  │ AppSideNav      │ ──→ │ items 渲染      │                   │
│  │ (侧边导航)      │     │ (菜单树 UI)     │                   │
│  └─────────────────┘     └─────────────────┘                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### 9.6.2 核心组件适配状态

| 组件 | 路径 | 功能 | 适配状态 |
|------|------|------|----------|
| **AppRootLayout.vue** | `src/components/common/AppRootLayout.vue` | 根布局，菜单加载与转换 | ✅ 已适配 |
| **AppLayout.vue** | `src/components/common/AppLayout/AppLayout.vue` | 应用布局，传递菜单数据 | ✅ 无需修改 |
| **AppSideNav.vue** | `src/components/common/AppSideNav/AppSideNav.vue` | 侧边导航渲染 | ✅ 无需修改 |
| **ArchWorkspaceNew.vue** | `src/components/ArchWorkspaceNew.vue` | LandingPage，快捷应用 | ✅ 已适配 |
| **useMenuPermissions.js** | `src/composables/useMenuPermissions.js` | 菜单权限 composable | ✅ 已适配 |

#### 9.6.3 AppRootLayout 适配分析

**现有实现**（已完美适配）：

```javascript
// AppRootLayout.vue
const { accessibleMenus, loadMenuPermissions } = useMenuPermissions()

// 菜单转换逻辑
const apiNavigationItems = computed(() => {
  return menus.map(menu => ({
    key: menu.menu_code,
    label: menu.menu_name,
    icon: mapMenuIcon(menu.icon),
    to: menu.menu_path || deriveRoutePath(menu),
    pageType: menu.page_type,           // ✅ 已透传
    objectTypes: menu.object_types,     // ✅ 已透传
    children: menu.children.map(...)
  }))
})
```

**关键特性**：
- ✅ 使用 `useMenuPermissions()` 从 API 获取菜单
- ✅ 支持 `page_type` 字段（object_list, multi_object_hub 等）
- ✅ 支持 `object_types` 字段
- ✅ 支持离线缓存（`useMenuCache`）
- ✅ 自动推导路由路径（`deriveRoutePath`）

**无需修改**，已完全适配菜单元数据化方案。

#### 9.6.4 LandingPage (ArchWorkspaceNew) 适配分析

**现有实现**（已完美适配）：

```javascript
// ArchWorkspaceNew.vue
const { accessibleMenus, loadMenuPermissions } = useMenuPermissions()

// 渲染快捷应用卡片
<div v-for="menu in accessibleMenus" :key="menu.menu_code" class="app-tile">
  <div class="tile-icon">{{ menu.icon }}</div>
  <div class="tile-info">
    <span class="tile-name">{{ menu.menu_name }}</span>
    <span class="tile-desc">{{ menu.description }}</span>
  </div>
</div>

// 点击跳转
const openApp = (menuCode) => {
  const menu = accessibleMenus.value.find(m => m.menu_code === menuCode)
  router.push(menu.menu_path)
}
```

**关键特性**：
- ✅ 使用 `useMenuPermissions()` 获取可访问菜单
- ✅ 根据 `menu_path` 跳转路由
- ✅ 显示菜单图标、名称、描述

**无需修改**，已完全适配菜单元数据化方案。

#### 9.6.5 菜单数据流完整性验证

```
┌─────────────────────────────────────────────────────────────────┐
│                    数据流完整性检查                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  YAML menu.yaml                                                 │
│       │                                                         │
│       ▼                                                         │
│  menus 表 (DB)                                                  │
│       │                                                         │
│       ▼                                                         │
│  /api/v1/menu-permission/visible ──────────────────── ✅ 正常   │
│       │                                                         │
│       ▼                                                         │
│  useMenuPermissions().accessibleMenus ──────────────── ✅ 正常   │
│       │                                                         │
│       ├─→ AppRootLayout → navigationItems ──────────── ✅ 正常   │
│       │        │                                                │
│       │        └─→ AppLayout → sidebarItems ────────── ✅ 正常   │
│       │                 │                                       │
│       │                 └─→ AppSideNav 渲染 ────────── ✅ 正常   │
│       │                                                         │
│       └─→ ArchWorkspaceNew (LandingPage) ───────────── ✅ 正常   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### 9.6.6 新增字段透传检查

| 新增字段 | API 返回 | useMenuPermissions | AppRootLayout | AppSideNav |
|----------|----------|---------------------|---------------|------------|
| `bo_bindings` | ⚠️ 待添加 | ✅ 自动透传 | ✅ 已透传 objectTypes | - |
| `primary_object_type` | ✅ 已返回 | ✅ 自动透传 | ✅ 已使用 | - |
| `page_type` | ✅ 已返回 | ✅ 自动透传 | ✅ 已透传 pageType | - |
| `required_permissions` | ⚠️ 待添加 | ✅ 自动透传 | - | - |

**结论**：菜单 UI 框架组件已完全适配，无需修改。只需确保 API 返回新增字段即可。

#### 9.6.7 动态路由生成集成点

当前 `AppRootLayout` 已支持 `deriveRoutePath` 自动推导：

```javascript
function deriveRoutePath(menu) {
  switch (menu.page_type) {
    case 'object_list':
      return `/objects/${menu.primary_object_type}`  // ✅ 已支持
    case 'multi_object_hub':
      return `/${menu.menu_code}`                    // ✅ 已支持
    default:
      return `/${menu.menu_code}`                    // ✅ 已支持
  }
}
```

**Phase 3 动态路由生成**只需：
1. 在 `router/index.js` 中集成 `generateDynamicRoutes()`
2. 保持 `AppRootLayout` 现有逻辑不变

### 9.7 适配检查清单汇总

| 检查项 | 现状 | 适配动作 |
|--------|------|----------|
| **角色权限配置页面** |||
| RoleDetail.vue | ✅ 无需修改 | - |
| PermissionConfigPanel.vue | ✅ 无需修改 | - |
| MenuPermissionMatrix.vue | ⚠️ 未显示 bo_bindings | 增加显示区域 |
| useMenuPermission.ts | ✅ 已支持统一权限 API | - |
| **菜单 UI 框架** |||
| AppRootLayout.vue | ✅ 已适配 | - |
| AppLayout.vue | ✅ 无需修改 | - |
| AppSideNav.vue | ✅ 无需修改 | - |
| ArchWorkspaceNew.vue (LandingPage) | ✅ 已适配 | - |
| useMenuPermissions.js | ✅ 已适配 | - |
| **API 与数据库** |||
| unified-permissions API 返回 bo_bindings | ⚠️ 未返回 | 增加返回字段 |
| role_permissions 表 source 字段 | ⚠️ 未添加 | ALTER TABLE |
| 权限来源记录 | ⚠️ 未记录 | 修改保存逻辑 |

***

## 10. 附录

### A. 相关文件清单

**前端 - 菜单 UI 框架**：
- `src/components/common/AppRootLayout.vue` - 根布局（菜单加载与转换）
- `src/components/common/AppLayout/AppLayout.vue` - 应用布局
- `src/components/common/AppSideNav/AppSideNav.vue` - 侧边导航
- `src/components/ArchWorkspaceNew.vue` - LandingPage（快捷应用）
- `src/composables/useMenuPermissions.js` - 菜单权限 composable

**前端 - 角色权限配置**：
- `src/views/SystemManagement/RoleDetail.vue` - 角色详情页
- `src/views/SystemManagement/components/PermissionConfigPanel.vue` - 权限配置面板
- `src/views/SystemManagement/components/MenuPermissionMatrix.vue` - 菜单权限矩阵
- `src/views/SystemManagement/composables/useMenuPermission.ts` - 菜单权限 composable

**前端 - 路由**：
- `src/router/index.js` - 路由配置
- `src/router/dynamicRoutes.js` - 动态路由生成（新增）

**后端**：
- `meta/services/permission_sync_service.py` - 权限同步服务
- `meta/services/menu_auto_generator.py` - 菜单自动生成
- `meta/api/menu_permission_api.py` - 菜单权限 API
- `meta/api/role_menu_api.py` - 角色菜单 API
- `meta/services/auth_middleware.py` - 权限检查中间件

**元数据**：
- `meta/schemas/menu.yaml` - 菜单元数据
- `meta/schemas/permission.yaml` - 权限元数据
- `meta/schemas/role.yaml` - 角色元数据

### B. 业界对标

| 产品 | 菜单-权限联动 | 权限同步 | 来源追溯 |
|------|--------------|----------|----------|
| SAP PFCG | ✓ TCode → Auth Object | ✓ SU24 | ✓ |
| Salesforce | ✓ Profile → Permission Set | ✓ 自动 | ✓ |
| ServiceNow | ✓ Role → Module | ✓ 自动 | 部分 |
| 本系统 | ✓ 菜单 → 功能权限 | ✅ 已实现 | ✅ 已实现 |

### C. 管理维度关联

> **详细分析**: 参见 [实际现状细化方案](refined-implementation-plan.md) 第 5 节

| 组件 | 关联方式 | 适配动作 |
|------|----------|----------|
| **DimensionScopePanel** | 在 PermissionConfigPanel 中作为第一入口 | ✅ 无需修改 |
| **DimensionScopeEngine** | 已读取 `menus.required_permissions` | ✅ 受益于增强字段 |
| **auto_sync_all()** | 从维度范围推导菜单+权限+数据条件 | ⚠️ 需记录来源 |
| **PermissionSource** | 新增 `auto_dimension` 来源类型 | ⚠️ 需扩展枚举 |

