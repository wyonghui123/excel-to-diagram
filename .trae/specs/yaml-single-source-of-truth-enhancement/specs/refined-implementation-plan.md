# 实际现状细化方案

> **关联主 Spec**: [yaml-single-source-of-truth-enhancement spec.md](../spec.md)
> **关联子 Spec**: [menu-permission-sync-spec.md](menu-permission-sync-spec.md)
> **版本**: v1.2.0
> **创建日期**: 2026-05-19
> **最后更新**: 2026-05-19
> **状态**: In Progress（P0 Owner模型 ✅ | 核心功能完成，待前端 + 测试）

---

## 摘要

| 类别 | 已完成 | 待实施 | 实施文件 |
|------|--------|--------|---------|
| **权限同步** | ✅ sync_all/validate/report | - | permission_sync_service.py, permission_sync_api.py |
| **菜单元数据** | ✅ bo_bindings/required_permissions | - | menu.yaml, menu_auto_generator.py |
| **Owner 模型** | ✅ BO YAML修复 + OwnerTransferService + API | ⏳ 前端页面 | 7个BO YAML, owner_transfer_service.py, owner_transfer_api.py |
| **动态路由** | ✅ 已有基础（AppRootLayout已动态） | ⏳ 动态路由注册 | dynamicRoutes.js |
| **数据权限声明** | ✅ 已有基础（ConditionPermissionService） | ⏳ DataPermissionGenerator | data_permission_generator.py |

---

## 1. 实际现状总结

深入分析代码库后，发现 **比原始 Spec 预估的更成熟**：

### 1.1 已完成（超出预期）

| 功能 | 文件 | 成熟度 | 说明 |
|------|------|--------|------|
| 计算字段依赖追踪 | `meta/core/rule_chain.py` | ✅ 完整 | `DependencyGraph` + `RuleDependencyAnalyzer` + `ImplicitRuleChainExecutor`，917行 |
| 循环依赖检测 | 同上 | ✅ 完整 | `detect_cycle()` DFS 染色法 |
| 拓扑排序执行 | 同上 | ✅ 完整 | `topological_sort()` 按类型+优先级排序 |
| 变更传播 | 同上 | ✅ 完整 | `_get_downstream_rules()` 传递依赖，MAX_PROPAGATION_DEPTH=100 |
| 公式求值 | 同上 | ✅ 完整 | `_evaluate_formula()` 支持 `$field_name` 语法 |
| 菜单 UI 框架 | `AppRootLayout.vue` | ✅ 完整 | 从API动态生成导航，支持离线缓存 |
| 页面类型映射 | `AppRootLayout.vue:deriveRoutePath()` | ✅ 完整 | `object_list` → `/objects/{bo}` |
| LandingPage | `ArchWorkspaceNew.vue` | ✅ 完整 | 从 `accessibleMenus` 渲染快捷卡片 |
| 权限来源追溯 | `MenuPermissionMatrix.vue` | ✅ 前端已支持 | `source: 'auto' | 'manual'` 接口 |
| 权限同步 API | `permission_sync_api.py` | ✅ 新完成 | sync/validate/report/orphans API |

### 1.2 剩余差距

| 差距 | 严重程度 | 影响范围 | 工作量 |
|------|----------|----------|--------|
| 路由硬编码 | 🔴 高 | `router/index.js` ~25个路由 | 3天 |
| 数据权限未从YAML自动生成 | 🟡 中 | `data_permission.yaml` | 2天 |
| 测试覆盖不全（新代码） | 🟡 中 | 新增的 sync API | 2天 |

---

## 2. 差距 1：动态路由生成

### 2.1 现状分析

**当前 `router/index.js` 结构**：

```javascript
const routes = [
  // === 核心页面（保留） ===
  { path: '/', name: 'landing', component: () => import('@/components/ArchWorkspaceNew.vue') },
  { path: '/login', name: 'login', ... },
  
  // === 可元数据化的路由（应动态生成） ===
  { path: '/product-management', name: 'product-management',
    component: () => import('@/views/GenericObjectList.vue'),
    props: { objectType: 'product' } },
  { path: '/version-management', name: 'version-management',
    component: () => import('@/views/GenericObjectList.vue'),
    props: { objectType: 'version' } },
  // ... 约18个同类路由
  
  // === 多对象聚合路由（应动态生成） ===
  { path: '/user-permission/:tab?', name: 'user-permission',
    component: () => import('@/views/GenericTabContainer.vue'),
    props: { group: 'user-permission' } },
  // ... 约5个同类路由
  
  // === 固定路由（保留） ===
  { path: '/:pathMatch(.*)*', redirect: '/' }
]
```

**关键发现**：
- `AppRootLayout` 的 `deriveRoutePath()` 已经能推导路径，说明导航层面已动态化
- 但 Vue Router 的 `routes` 配置仍是硬编码
- **核心问题**：URL 直接访问 `/product-management` 时，如果路由未注册会 404

### 2.2 已有基础：菜单 API 返回结构

```javascript
// useMenuPermissions().accessibleMenus → 来自 /api/v1/menu-permission/visible
[
  {
    menu_code: 'product-management',
    menu_name: '产品管理',
    menu_path: '/product-management',
    page_type: 'object_list',
    primary_object_type: 'product',
    object_types: ['product'],
    required_permissions: ['product:read'],
    ...
  }
]
```

### 2.3 已有基础：页面类型组件映射

```javascript
// AppRootLayout.vue: deriveRoutePath() 已实现
function deriveRoutePath(menu) {
  switch (menu.page_type) {
    case 'object_list':      return `/objects/${menu.primary_object_type}`
    case 'multi_object_hub': return `/${menu.menu_code}`
    default:                 return `/${menu.menu_code}`
  }
}

// 需要扩展的组件映射
const PAGE_TYPE_COMPONENTS = {
  object_list:      () => import('@/views/GenericObjectList.vue'),
  object_detail:    () => import('@/views/ObjectDetailPage.vue'),
  multi_object_hub: () => import('@/views/GenericTabContainer.vue'),
  dashboard:        () => import('@/views/Dashboard.vue'),
  custom_page:      null,  // 通过 menu.component_path 动态导入
}
```

### 2.4 实现方案（文件级）

#### 文件 1：`src/router/dynamicRoutes.js`（新建 ~80行）

```javascript
import { useMenuPermissions } from '@/composables/useMenuPermissions'
import { useMenuCache } from '@/composables/useMetaCache'

const PAGE_TYPE_COMPONENTS = {
  object_list: () => import('@/views/GenericObjectList.vue'),
  object_detail: () => import('@/views/ObjectDetailPage.vue'),
  multi_object_hub: () => import('@/views/GenericTabContainer.vue'),
  dashboard: () => import('@/views/Dashboard.vue'),
}

export async function generateDynamicRoutes(router) {
  const { accessibleMenus, loadMenuPermissions } = useMenuPermissions()
  const menuCache = useMenuCache()

  let menus = []
  try {
    await loadMenuPermissions()
    menus = accessibleMenus.value || []
    if (menus.length > 0) {
      menuCache.setCache(menus)
    }
  } catch (e) {
    console.warn('[DynamicRoutes] API加载失败，使用缓存:', e)
    const cached = menuCache.getCache()
    menus = cached?.data || []
  }

  for (const menu of menus) {
    const component = PAGE_TYPE_COMPONENTS[menu.page_type]
    if (!component) continue

    const props = {}
    if (menu.page_type === 'object_list') {
      props.objectType = menu.primary_object_type
    }
    if (menu.page_type === 'multi_object_hub') {
      props.group = menu.menu_code
    }
    if (menu.object_types) {
      props.objectTypes = menu.object_types
    }
    if (menu.page_config) {
      props.pageConfig = menu.page_config
    }

    // 路径处理：支持 /user-permission/:tab? 模式
    const path = menu.menu_path || `/${menu.menu_code.replace(/_/g, '-')}`

    router.addRoute({
      path,
      name: menu.menu_code,
      component,
      props: Object.keys(props).length > 0 ? props : true,
      meta: {
        title: menu.menu_name,
        requiresAuth: true,
        requiredPermissions: menu.required_permissions || [],
        requiredAny: menu.required_any_permission || false,
      }
    })
  }
}

export function checkRoutePermission(route) {
  const { accessibleMenus } = useMenuPermissions()
  const perms = route.meta?.requiredPermissions || []
  const requiredAny = route.meta?.requiredAny || false

  if (perms.length === 0) return true

  const menu = accessibleMenus.value?.find(m => m.menu_code === route.name)
  if (!menu) return false

  if (requiredAny) {
    return perms.some(p => menu.required_permissions?.includes(p))
  }
  return perms.every(p => menu.required_permissions?.includes(p))
}
```

#### 文件 2：`src/router/index.js`（修改 ~5行新增 + 保留结构）

```javascript
import { generateDynamicRoutes, checkRoutePermission } from './dynamicRoutes'

// === 静态路由（保持不变） ===
const staticRoutes = [
  { path: '/', name: 'landing', component: () => import('@/components/ArchWorkspaceNew.vue') },
  { path: '/login', name: 'login', component: () => import('@/views/Login.vue') },
  // ... 保留必须静态的路由
]

const router = createRouter({
  history: createWebHistory(),
  routes: [
    ...staticRoutes,
    // 移除所有硬编码的 objectList/objectDetail/multiObjectHub 路由
    // 这些路由将在 AppRootLayout mounted 后动态注册
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ]
})

// === 路由守卫 ===
router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()
  
  // 公开路由
  if (to.name === 'landing' || to.name === 'login') {
    return next()
  }

  // 认证检查
  if (!authStore.isAuthenticated) {
    return next({ name: 'login', query: { redirect: to.fullPath } })
  }

  // 权限检查
  if (!checkRoutePermission(to)) {
    return next({ name: 'landing' })
  }

  next()
})

// === 动态路由初始化 ===
// 在 App 挂载后调用
export async function initDynamicRoutes() {
  await generateDynamicRoutes(router)
}

export default router
```

#### 文件 3：`src/components/common/AppRootLayout.vue`（修改 ~3行）

```javascript
// 在 onMounted 中新增一行
import { initDynamicRoutes } from '@/router'

onMounted(async () => {
  await loadMenuWithCache()
  await initDynamicRoutes()  // ← 新增：注册动态路由
})
```

### 2.5 迁移清单

| 当前硬编码路由 | page_type | primary_object_type | 迁移方式 |
|---------------|-----------|---------------------|----------|
| `/product-management` | object_list | product | 菜单记录 |
| `/version-management` | object_list | version | 菜单记录 |
| `/component-management` | object_list | component | 菜单记录 |
| `/diagram-management` | object_list | diagram | 菜单记录 |
| `/domain-management` | object_list | domain | 菜单记录 |
| `... ~18个` | object_list | 各 BO | 菜单记录 |
| `/user-permission/:tab?` | multi_object_hub | - | 菜单记录 |
| `... ~5个` | multi_object_hub | - | 菜单记录 |

### 2.6 验证方案

```
1. 启动应用 → 检查浏览器 Vue DevTools → Routes tab
   → 确认动态路由已注册

2. 新建菜单记录（menus 表） → 刷新页面
   → 确认新路由可访问

3. 设置无权限菜单 → 用户访问
   → 确认路由守卫重定向到 landing

4. URL 直接访问 /product-management
   → 确认动态路由已注册，正常渲染
```

---

## 3. 差距 2：数据权限声明化

### 3.1 现状分析

**已有基础**：

1. `data_permission.yaml` 定义了数据权限 BO：
   ```yaml
   id: data_permission
   fields:
     - id: user_id
     - id: resource_type
     - id: resource_id
     - id: permission_level     # admin/write/read
     - id: inherit_to_children
   ```

2. `DataPermissionService` 处理权限检查：
   ```python
   # data_permission_service.py
   class DataPermissionService:
       def check_permission(self, user_id, resource_type, resource_id, action='read')
       def get_user_permissions(self, user_id)
       def grant_permission(self, ...)
       def revoke_permission(self, ...)
   ```

3. `ConditionPermissionService` 处理 Oracle 风格条件：
   ```python
   # condition_permission_service.py
   class ConditionPermissionService:
       def check_permission()  # 条件型权限检查
       - Owner 权限（最高优先级）
       - 禁止权限
       - 条件型权限规则
       - 向上传播权限
   ```

4. BO 已有 `data_permission_hint` 字段（menu.yaml 中已添加）

**差距**：

```
YAML BO 定义                 DB data_permissions 表
┌───────────────────┐       ┌───────────────────┐
│ product.yaml      │       │ user_id=1         │
│  actions: [...]   │  ✗   │ resource_type=     │
│                   │───→─ │   'product'        │
│ data_permission_  │       │ permission_level=  │
│   hints: [...]    │       │   'read'          │
└───────────────────┘       └───────────────────┘
```

**无自动生成机制**：当前需手动创建数据权限记录

### 3.2 设计：YAML 数据权限声明

#### 3.2.1 BO 级声明

在 BO YAML 中新增 `data_permission_hints`：

```yaml
# product.yaml
id: product
name: 产品

data_permission_hints:
  auto_grant:
    - scope: creator        # 自动授予创建者 admin 权限
      permission_level: admin
    - scope: department     # 自动授予同部门 write 权限
      permission_level: write
      condition: "created_by.department = $current_user.department"
  resource_types:           # 数据权限作用域
    - product
    - version               # 级联到版本
```

#### 3.2.2 实现：DataPermissionGenerator

```python
# meta/services/data_permission_generator.py

class DataPermissionGenerator:
    """从 YAML 元数据自动生成数据权限记录"""
    
    def generate_default_permissions(self, meta_obj: MetaObject,
                                      user_id: int) -> List[Dict]:
        """根据 BO 的 data_permission_hints 生成默认数据权限"""
        hints = meta_obj.data_permission_hints or {}
        auto_grant = hints.get('auto_grant', [])
        resource_types = hints.get('resource_types', [meta_obj.id])
        
        permissions = []
        for grant in auto_grant:
            if grant['scope'] == 'creator':
                permissions.append({
                    'user_id': user_id,
                    'resource_type': resource_types[0],
                    'resource_id': None,  # 创建后填充
                    'permission_level': grant.get('permission_level', 'admin'),
                    'inherit_to_children': True,
                    'auto_generated': True,
                })
        return permissions
    
    def generate_on_create(self, meta_obj: MetaObject, 
                            resource_id: int, user_id: int,
                            data_source) -> int:
        """创建资源时自动授予创建者权限"""
        permissions = self.generate_default_permissions(meta_obj, user_id)
        
        count = 0
        for perm in permissions:
            data_source.execute(
                """INSERT OR IGNORE INTO data_permissions
                   (user_id, resource_type, resource_id, permission_level,
                    inherit_to_children, auto_generated, created_at)
                   VALUES (?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)""",
                [perm['user_id'], perm['resource_type'], 
                 resource_id, perm['permission_level'],
                 perm.get('inherit_to_children', True)]
            )
            count += 1
        
        return count

# 集成到 POST handler
# meta/api/bo_api.py
def create_bo(object_type):
    result = bo_service.create(data)
    
    # 数据权限自动授予
    meta_obj = registry.get(object_type)
    if meta_obj and meta_obj.data_permission_hints:
        gen = DataPermissionGenerator()
        gen.generate_on_create(
            meta_obj, result['id'], 
            g.current_user['user_id'], ds
        )
    
    return result
```

### 3.3 验证方案

```
1. 创建产品 → 检查 data_permissions 表
   → 确认创建者自动获得 admin 权限

2. 创建者删除自己的产品 → 检查权限
   → 确认 owner 权限生效

3. 修改 YAML data_permission_hints → 重新注册 BO
   → 确认新创建的记录使用新规则
```

---

## 4. 差距 3：测试覆盖

### 4.1 新增代码测试需求

| 新增代码 | 测试文件 | 测试内容 | 优先级 |
|----------|---------|---------|--------|
| `permission_sync_service.py` | `test_permission_sync_service.py` | sync_all, validate_consistency, sync_for_object | 🔴 高 |
| `permission_sync_api.py` | `test_permission_sync_api.py` | API 端点测试 | 🔴 高 |
| `dynamicRoutes.js` | 待定（前端测试） | 路由生成、权限守卫 | 🟡 中 |
| `data_permission_generator.py` | `test_data_permission_generator.py` | 自动授予、声明解析 | 🟡 中 |

### 4.2 测试文件计划

#### `meta/tests/test_permission_sync_service.py`（~150行）

```python
# 测试场景：
# 1. sync_all: 全量同步，验证 YAML actions → permissions 完整映射
# 2. sync_for_object: 增量同步，验证单个 BO 权限同步
# 3. validate_consistency: 验证一致性检查正确性
# 4. orphan_detection: 验证孤儿权限检测
```

#### `meta/tests/test_permission_sync_api.py`（~100行）

```python
# 测试场景：
# 1. POST /sync: 验证全量和增量同步
# 2. GET /validate: 验证一致性检查响应
# 3. GET /report: 验证报告结构
# 4. 权限检查: 验证 admin_required 装饰器
```

### 4.3 回归测试保障

现有 100+ 测试文件，新增功能需确保：
- `test_permission_service.py` - 权限服务测试
- `test_data_permission_service.py` - 数据权限测试
- `test_bo_api.py` - BO API 测试（CRUD 完整性）
- `test_auth_api.py` - 认证 API 测试

---

## 4. 差距 2.5：Owner 数据权限模型对比与增强

### 4.1 当前 Owner 权限实现现状

我们的系统已经实现了一套完整的 Owner 权限体系：

| 组件 | 文件 | 功能 | 状态 |
|------|------|------|------|
| **OwnerAutoPermissionInterceptor** | `meta/core/interceptors/owner_permission_interceptor.py` | 创建时注入 `owner_id` → 自动添加 admin 级数据权限 | ✅ |
| **DataPermissionService._is_owner()** | `meta/services/data_permission_service.py` | 检查 `resource.owner_id == user_id` | ✅ |
| **ConditionPermissionService._is_owner()** | `meta/services/condition_permission_service.py` | Owner 最高优先级返回 admin | ✅ |
| **YAML authorization** | `product.yaml`, `domain.yaml` 等 | `authorization: { check: true, scope: "owner_id = $user.id" }` | ✅ |
| **向上传播** | `data_permission_service.py` | 子级权限 → 父级 read 导航权限 | ✅ |
| **向下继承** | `data_permission_service.py` | `inherit_to_children` 标志 | ✅ |
| **权限级别** | `admin/write/read/none` | 四级权限体系 | ✅ |

**当前权限检查优先级**：
```
1. Owner     → admin（隐式，最高）
2. Denied    → none （禁止权优先）
3. Condition → 条件型权限规则
4. Parent    → 向上传播 read
```

### 4.2 核心发现：`auto_permission` 配置未在 BO YAML 中显式声明

BO YAML 中目前只有 `authorization: { check: true, scope: "owner_id = $user.id" }`，但 `auto_owner` 和 `auto_permission` 没有显式声明。拦截器 `OwnerAutoPermissionInterceptor` 读取 `authorization.auto_permission` 时，因为字段不存在会 fallback 到空字符串，然后跳过自动授权。

```python
# owner_permission_interceptor.py L72-78
auto_perm = ''
if isinstance(auth_config, dict):
    auto_perm = auth_config.get('auto_permission', '')
    # auth_config 只有 { check, scope } → auto_perm = ''
    # → 跳过自动授权！
```

**这意味着**：虽然权限检查层已经能识别 Owner（通过 `_is_owner`），但 **创建时自动授权的功能并未完全生效**。

### 4.3 头部产品 Owner 模型对比

#### 4.3.1 Salesforce — Owner = Record 最高权限

| 特性 | Salesforce 做法 | 我们的现状 |
|------|----------------|-----------|
| **Owner 定义** | 每条记录有且仅有一个 Owner（User 或 Queue） | `owner_id` 字段 |
| **Owner 权限级别** | Owner = Full Access（等同于我们 admin） | ✅ `_is_owner` → admin |
| **Owner 转移** | 支持手动/自动转移，Role Hierarchy 继承链调整 | ❌ 未实现 |
| **Role Hierarchy** | 上级可查看下级记录（Grant Access Using Hierarchies） | ⚠️ 部分（通过 manage_role 场景） |
| **Sharing Rules** | Owner-based + Criteria-based 两种规则 | ✅ ConditionPermissionService 条件规则 |
| **Manual Sharing** | Owner 或 Full Access 用户可手动分享 | ❌ 未实现 |
| **Queue Owner** | 队列拥有记录，成员共享 | ❌ 未实现 |
| **OWD** | Private/Read-Only/Read-Write 全局默认 | ⚠️ 无全局默认概念 |

**Salesforce 关键洞察**：
- **"Record ownership and full access are synonymous"** — 官方文档明确 Owner = 最高访问权限
- Owner 受 **Profile 对象权限** 约束：即使 Owner，Profile 没给 Edit 权限也无法编辑
- **Owner transfer** 是企业级必备：人员变动后批量转移记录所有权
- **Role Hierarchy** 不是可选的：几乎所有的共享模型都基于 Role

#### 4.3.2 SAP — Data Ownership Concept

| 特性 | SAP 做法 | 我们的现状 |
|------|---------|-----------|
| **Data Ownership** | 系统级开关，可在对象级别启用/禁用 | ⚠️ YAML `authorization` 声明 |
| **Owner 关系** | 预定义关系类型（部门/团队/个人） | ✅ `owner_id` |
| **权限粒度** | Full / Read / None 三级 | ✅ admin/write/read/none |

**SAP 关键洞察**：
- Data Ownership 是**可选的系统特性**，而非默认行为
- 权限通过 **Authorization Object + Field Values** 组合检查
- **SU24 事务**维护 TCode 与 Auth Object 的关联（类似我们的 YAML actions → permissions）

#### 4.3.3 ServiceNow — ACL 模型（无隐式 Owner）

| 特性 | ServiceNow 做法 | 我们的现状 |
|------|----------------|-----------|
| **Owner 概念** | **无隐式 Owner 权限**，全部通过 ACL 控制 | ⚠️ 我们有隐式 Owner |
| **ACL 规则** | Table-level + Field-level，条件脚本 | ✅ ConditionPermissionService |
| **记录所有权** | 通过 `assigned_to` + `assignment_group` 判定 | ❌ 无 assignment_group |
| **权限脚本** | `gs.getUser().isMemberOf()` 等动态判断 | ✅ ConditionEvaluator |

**ServiceNow 关键洞察**：
- **没有隐式 Owner 权限**，所有权限必须显式通过 ACL 声明
- 所有权通过"分配"概念表达，而非"创建"
- `security_admin` 角色是最高安全角色

#### 4.3.4 Jira — Permission Scheme + Issue Security

| 特性 | Jira 做法 | 我们的现状 |
|------|----------|-----------|
| **Reporter 权限** | 可配置"Reporter"能否浏览/编辑自己的 Issue | ❌ 未实现 Reporter 概念 |
| **Project Role** | Administrator/Developer/User 三级 | ✅ Role 体系 |
| **Permission Scheme** | 全局方案 + 项目方案 | ⚠️ 无 Permission Scheme 概念 |
| **Issue Security** | Issue 级别安全方案 | ⚠️ 部分（通过条件规则） |

**Jira 关键洞察**：
- **Reporter ≠ Owner**：Reporter（报告人）可能不是 Owner
- Permission Scheme 可复用（类似我们的数据权限可能是跨 BO 的）
- "Browse Projects" 权限是所有访问的基础

### 4.4 差距分析总结

| 差距 | 严重程度 | 说明 |
|------|----------|------|
| `auto_permission` 未显式声明 | 🔴 高 | BO YAML 中缺少 `auto_owner: true` / `auto_permission: admin` 显式声明，拦截器 fallback 空值 |
| **Owner 转移** | 🟡 中 | 人员离职/转岗时需手动转移，无可视化工具 |
| **Queue/Owner Group** | 🟡 中 | 仅支持 User 作为 Owner，不支持队列/组 |
| **Manual Sharing** | 🟢 低 | Owner 无法手动将记录分享给他人 |
| **Role Hierarchy 继承** | 🟡 中 | 管理维度已部分覆盖，但非标准 Role Hierarchy |
| **OWD 全局默认** | 🟢 低 | 无组织级默认共享设置 |
| **Reporter vs Owner 分离** | 🟢 低 | `created_by` 和 `owner_id` 是同一字段 |

### 4.5 增强建议

#### 4.5.1 修复：BO YAML 显式声明 auto_permission（✅ 已实施）

> **实施日期**: 2026-05-19
> **实施文件**: 
> - `meta/schemas/product.yaml`
> - `meta/schemas/version.yaml`
> - `meta/schemas/domain.yaml`
> - `meta/schemas/sub_domain.yaml`
> - `meta/schemas/service_module.yaml`
> - `meta/schemas/business_object.yaml`
> - `meta/schemas/relationship.yaml`

**已完成的 YAML 增强**（7个 BO 全部添加）：

```yaml
# 修改前（原因：拦截器 fallback 空值导致自动授权跳过）
authorization:
  check: true
  scope: "owner_id = $user.id"

# 修改后（拦截器现在能正确读取 auto_owner/auto_permission）
authorization:
  check: true
  scope: "owner_id = $user.id"
  auto_owner: true                # 创建时自动注入 owner_id
  auto_permission: admin          # 创建后自动授予 admin 权限
  inherit_to_children: true       # 权限向下继承
  allow_transfer: true            # 允许 Owner 转移
  transfer_keep_permissions: true # 转移后保留原始读权限
```

**relationship.yaml 特殊处理**（级联权限，不继承不转移）：
```yaml
authorization:
  check: true
  scope: "version_id IN (SELECT id FROM versions WHERE owner_id = $user.id)"
  auto_owner: true
  auto_permission: admin
  inherit_to_children: false
  allow_transfer: false
```

**验证方法**：
```
1. 创建产品 → 检查 data_permissions 表
   → owner_id 自动注入为当前用户
   → auto_generated=1 的 admin 权限自动创建

2. 其他用户访问该产品 → 被拒绝（非 owner）

3. 创建者访问 → _is_owner 返回 admin，通过
```

#### 4.5.2 新增：OwnerTransferService（✅ 已实施）

> **实施日期**: 2026-05-19
> **实施文件**:
> - `meta/services/owner_transfer_service.py` — Owner 转移服务（270行）
> - `meta/api/owner_transfer_api.py` — Owner 转移 API（230行）
> - `meta/server.py` — 注册 `owner_transfer_bp` blueprint

**API 端点**：

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/v1/admin/owner/transfer` | POST | 单记录 Owner 转移 |
| `/api/v1/admin/owner/bulk-transfer` | POST | 批量转移（人员离职场景） |
| `/api/v1/admin/owner/validate` | POST | 转移前校验 |
| `/api/v1/admin/owner/transfer-history` | GET | 转移历史查询 |

**转移流程**（一个事务内原子执行）：

```
1. validate_transfer() → 校验 YAML allow_transfer + 用户存在性
2. UPDATE {table} SET owner_id = new_user_id
3. _revoke_auto_permissions() → 移除旧 Owner 的 auto_generated 权限
4. _grant_owner_permissions() → 授予新 Owner admin 权限
5. _keep_read_write_permissions() → 保留旧 Owner read 权限（可选）
6. _log_transfer() → 写入 owner_transfer_log 审计表
```

**数据库变更**（自动创建）：
```sql
CREATE TABLE IF NOT EXISTS owner_transfer_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_type VARCHAR(100) NOT NULL,
    resource_id INTEGER NOT NULL,
    from_user_id INTEGER NOT NULL,
    to_user_id INTEGER NOT NULL,
    admin_user_id INTEGER,
    permissions_kept INTEGER DEFAULT 0,
    transferred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 4.5.3 YAML 声明式 Owner 策略配置（⏳ 设计完成，待前端）

```yaml
# BO YAML 中可选的 owner_policy 配置块（未来扩展）
# 当前 authorization 块已覆盖 90% 需求
# product.yaml

owner_policy:
  mode: single_user                      # single_user | group | queue
  auto_assign_on_create: true            # 创建时自动分配
  allow_transfer: true                   # 允许转移（已在 authorization 中）
  transfer_audit: true                   # 转移审计（已通过 owner_transfer_log 实现）
  fallback_owner: null                   # 兜底 Owner（可选 role_id）
  co_owners_enabled: false               # 是否允许多 Owner（未来）
```

**当前状态**：
- ✅ `authorization` 块已覆盖：`auto_owner` / `auto_permission` / `inherit_to_children` / `allow_transfer`
- ✅ `owner_transfer_log` 审计表已实现
- ⏳ `owner_policy` 独立块作为未来扩展（Queue/Group/Co-owner 场景）

#### 4.5.4 业界对标总结

```
┌─────────────────────────────────────────────────────────────────┐
│                  Owner 权限模型对比矩阵                            │
├──────────────┬────────────┬──────────┬──────────┬──────────────┤
│ 特性          │ Salesforce │ SAP B1   │ServiceNow│ 本系统(当前)  │
├──────────────┼────────────┼──────────┼──────────┼──────────────┤
│ 隐式 Owner    │ ✅ 强      │ ✅ 可配置 │ ❌ 无    │ ✅ 强         │
│ Owner=最高权限 │ ✅ Full   │ ✅ Full  │ N/A     │ ✅ admin      │
│ Owner 转移    │ ✅ 内置    │ ✅ 内置  │ N/A     │ ❌ 未实现     │
│ 受对象权限约束  │ ✅ Profile │ ✅ 授权  │ ✅ ACL  │ ✅ actions    │
│ Queue/Group   │ ✅ Queue  │ ❌       │ ✅ Group │ ❌ 未实现     │
│ Manual Share  │ ✅        │ ❌       │ ❌      │ ❌ 未实现     │
│ Role Hierarchy│ ✅ 核心    │ ❌       │ ❌      │ ⚠️ 管理维度   │
│ OWD           │ ✅        │ ✅       │ ✅ ACL  │ ❌ 未实现     │
│ 创建时自动授权  │ ✅ (默认) │ ✅ 可配置 │ ❌      │ ⚠️ 需显式声明 │
│ 禁止权优先     │ ❌        │ ❌       │ ✅ ACL  │ ✅            │
│ 可审计        │ ✅        │ ✅       │ ✅      │ ✅ (待增强)   │
└──────────────┴────────────┴──────────┴──────────┴──────────────┘
```

**结论**：我们的 Owner 模型在核心设计上对标 **Salesforce + 用友BIP**（禁止权优先），属于业界领先水平。主要差距在于：
1. **`auto_permission` 需显式声明** — 简单的 YAML 补齐
2. **Owner 转移** — 企业级必备但尚未实现
3. **Queue/Group Owner** — 团队协作场景需要

---

## 5. 管理维度关联分析

### 5.1 管理维度与我们的方案的关系

管理维度（Management Dimension）是角色权限配置的关键入口，与我们的菜单元数据化+权限自动同步方案 **深度关联**。

#### 现有架构链路

```
┌────────────────────────────────────────────────────────────────┐
│              角色权限配置 - 四大集成组件                           │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  PermissionConfigPanel (权限配置面板)                            │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ ① DimensionScopePanel (管理维度范围)                       │ │
│  │    配置维度范围 → 自动推导 → menu/permission/condition    │ │
│  │    ↓ 调用 /roles/{id}/derived-permissions               │ │
│  │    ↓ 调用 DimensionScopeEngine.auto_sync_all()           │ │
│  │                                                          │ │
│  │ ② MenuPermissionMatrix (菜单与功能权限)                    │ │
│  │    勾选菜单 → 自动授予功能权限                             │ │
│  │                                                          │ │
│  │ ③ ConditionRuleList (条件型权限)                          │ │
│  │                                                          │ │
│  │ ④ 保存全部权限                                           │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│  RolePermissionCenter (独立管理维度+条件规则管理页)              │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ ManagementDimensionSelector → ConditionRuleEditor        │ │
│  │ → ImpactPreview (影响范围预览)                            │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

#### DimensionScopeEngine 已经读取我们的增强字段

```python
# dimension_scope_engine.py - derive_recommended_menus()
# 已读取 menus 表的 required_permissions、object_types、primary_object_type
cursor = self._ds.execute(
    "SELECT menu_code, primary_object_type, object_types "
    "FROM menus WHERE auto_generated = 1 AND is_active = 1"
)

# derive_permissions() - 已读取 menus.required_permissions
cursor = self._ds.execute(
    f"SELECT required_permissions FROM menus WHERE menu_code IN ({placeholders})",
    menus
)
```

**这意味着**：我们的 `menus.required_permissions`、`menus.bo_bindings` 增强字段会 **自动流入管理维度的推导引擎**。

### 5.2 管理维度组件适配状态

| 组件 | 路径 | 功能 | 适配状态 |
|------|------|------|----------|
| **DimensionScopePanel.vue** | `src/views/SystemManagement/components/DimensionScopePanel.vue` | 维度范围配置 + 自动推导 | ✅ 无需修改 |
| **PermissionConfigPanel.vue** | `src/views/SystemManagement/components/PermissionConfigPanel.vue` | 整合 维度→菜单→条件 三组件 | ✅ 无需修改 |
| **RoleDetail.vue** | `src/views/SystemManagement/RoleDetail.vue` | 角色详情页，通过 slot 注入 PermissionConfigPanel | ✅ 无需修改 |
| **RolePermissionCenter.vue** | `src/views/SystemManagement/RolePermissionCenter.vue` | 独立管理维度+条件规则管理 | ✅ 无需修改 |
| **ManagementDimensionEngine** | `meta/services/management_dimension_engine.py` | 层级维度加载、影响范围计算 | ✅ 无需修改 |
| **DimensionScopeEngine** | `meta/services/dimension_scope_engine.py` | 自动推导菜单/权限/数据条件 | ✅ 受益于增强字段 |
| **role_dimension_scope_api.py** | `meta/api/role_dimension_scope_api.py` | 维度范围 CRUD + `auto_sync_all` | ✅ 无需修改 |

### 5.3 方案对管理维度的增强

我们的方案对管理维度体系的增强：

| 增强点 | 之前 | 之后 |
|--------|------|------|
| `derive_recommended_menus()` | 只读 `object_types` 判断菜单是否有数据 | **还能读 `bo_bindings.include_actions`** 精准确权 |
| `derive_permissions()` | 读取已有的 `required_permissions` | **required_permissions 已自动推导**，更准确 |
| 权限来源追溯 | 无法区分推导来源 | `source='auto_dimension'` 区分 |
| `auto_sync_all()` | 返回推荐菜单和权限 | **还能返回 `bo_bindings` 信息** |

### 5.4 扩展权限来源类型

```python
# 权限来源枚举扩展
class PermissionSource(Enum):
    MANUAL = 'manual'            # 手动授予
    AUTO_MENU = 'auto_menu'      # 菜单自动带入
    AUTO_DIMENSION = 'auto_dimension'  # 🆕 管理维度自动推导
    AUTO_ROLE = 'auto_role'      # 角色继承
    AUTO_GROUP = 'auto_group'    # 用户组继承
```

### 5.5 管理维度流程验证

```
角色创建 → 配置管理维度范围（DimensionScopePanel）
         → 保存维度范围（POST /roles/{id}/dimension-scopes）
         → 自动推导（GET /roles/{id}/derived-permissions）
              ↓
         ┌──────────────────────────────────────┐
         │ DimensionScopeEngine.auto_sync_all() │
         │                                      │
         │ 1. expand_dimension_values()         │
         │    读取 role_dimension_scopes        │
         │    + 继承展开子级资源                 │
         │                                      │
         │ 2. derive_recommended_menus()        │
         │    → 读取 menus 表                   │
         │    → 🆕 利用 bo_bindings 判断        │
         │                                      │
         │ 3. derive_permissions()              │
         │    → 读取 menus.required_permissions │
         │    → 🆕 更准确的自动推导权限          │
         │                                      │
         │ 4. derive_data_conditions()          │
         │    → 生成 SQL WHERE 条件             │
         └──────────────────────────────────────┘
              ↓
         DimensionScopePanel 显示推导预览
         → 管理员确认 → 自动应用菜单+权限+数据条件
```

### 5.6 需扩展的地方

#### 5.6.1 role_permissions 支持 auto_dimension 来源

```sql
-- 扩展 source 字段枚举（已有 source 列，无需 ALTER TABLE）
-- 在代码中新增 auto_dimension 值
```

#### 5.6.2 DimensionScopeEngine auto_sync_all 记录来源

```python
# dimension_scope_engine.py - auto_sync_all() 增强
def auto_sync_all(self, role_id: int) -> Dict:
    # ... 现有逻辑
    
    # 新增：记录权限来源为 auto_dimension
    for perm_code in permissions:
        ds.execute(
            """INSERT OR IGNORE INTO role_permissions 
               (role_id, permission_id, source, source_menu_code, granted_at) 
               VALUES (?, ?, 'auto_dimension', ?, CURRENT_TIMESTAMP)""",
            [role_id, pid, f"dimension:{','.join(scopes)}"]
        )
```

---

## 6. 风险与缓解

| 天数 | 内容 | 交付物 |
|------|------|--------|
| **Day 1** | 动态路由生成 | `src/router/dynamicRoutes.js` + `src/router/index.js` 修改 + `AppRootLayout.vue` 修改 |
| **Day 2** | 路由权限守卫 | `beforeEach` 守卫 + admin_required 集成 |
| **Day 3** | 迁移硬编码路由 | 清理 router/index.js + 生成菜单数据 |
| **Day 4** | 数据权限声明化 | `data_permission_generator.py` + BO YAML 增强 |
| **Day 5** | 数据权限集成 | POST handler 集成 + data_permission_hints 解析 |
| **Day 6** | 权限同步测试 | `test_permission_sync_service.py` + `test_permission_sync_api.py` |
| **Day 7** | 数据权限测试 | `test_data_permission_generator.py` |
| **Day 8** | 回归测试 + 文档 | 全量测试 + 更新 ARCHITECTURE_V2.md |

**总计: 8 工作日 ≈ 1.5 周**

---

## 6. 风险与缓解

| 风险 | 影响 | 概率 | 缓解 |
|------|------|------|------|
| 动态路由与现有路由冲突 | 页面404 | 低 | 先排除现有路径再注册 |
| 路由守卫性能下降 | 每次导航检查权限 | 中 | 缓存菜单-权限映射 |
| 数据权限自动授予遗漏 | 权限缺失 | 低 | 提供手动授予 fallback |
| 现有测试回归失败 | 破坏现有功能 | 低 | 先跑全量测试基线 |

---

## 7. 附录：完整文件清单

### 新建文件

```
src/router/dynamicRoutes.js                          # 动态路由生成
meta/services/data_permission_generator.py             # 数据权限自动生成
meta/tests/test_permission_sync_service.py             # 权限同步服务测试
meta/tests/test_permission_sync_api.py                 # 权限同步 API 测试
meta/tests/test_data_permission_generator.py           # 数据权限生成器测试
```

### 修改文件

```
src/router/index.js                                    # 集成动态路由 + 守卫
src/components/common/AppRootLayout.vue                # 初始化动态路由
meta/api/bo_api.py                                     # POST handler 集成数据权限
meta/schemas/product.yaml (示例)                       # 添加 data_permission_hints
```
