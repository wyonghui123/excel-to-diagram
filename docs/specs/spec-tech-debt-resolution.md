## 目录

1. [一、FR-005：层级配置 Fallback 缓存化](#一-fr-005：层级配置-fallback-缓存化)
2. [二、FR-010：Page Type 路由映射元数据化](#二-fr-010：page-type-路由映射元数据化)
3. [三、拦截器测试薄弱项补充](#三-拦截器测试薄弱项补充)
4. [四、实施优先级](#四-实施优先级)
5. [五、影响范围总结](#五-影响范围总结)

---
# Tech Debt Resolution Spec

> **关联文档**: [ARCHITECTURE_V2.md §8](../ARCHITECTURE_V2.md#八-技术债务与待处理事项)
> **来源**: Phase 19 Hardcode 风险消除（剩余 2 项）+ 拦截器测试薄弱项
> **状态**: 设计阶段

---

## 一、FR-005：层级配置 Fallback 缓存化

### 1.1 问题描述

[hierarchyFilterBuilder.js](file:///d:/filework/excel-to-diagram/src/utils/hierarchyFilterBuilder.js#L32-L66) 中的 `getFallbackConfig()` 函数硬编码了 4 级层级结构（domain/sub_domain/service_module/business_object），约 30 行。而 YAML 元数据（[hierarchies.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/hierarchies.yaml)）已定义了完整的 7 级层级结构（product→version→domain→sub_domain→service_module→business_object→relationship）。

### 1.2 现状分析

**缓存机制已实现**：

```javascript
// hierarchyFilterBuilder.js:L10-L30
let _cachedConfig = null           // 模块级单例缓存

export async function fetchHierarchyConfig() {
  if (_cachedConfig) {             // 命中缓存直接返回
    return _cachedConfig
  }
  try {
    const response = await fetch('/api/v1/meta/hierarchies/config')
    const result = await response.json()
    if (result.success) {
      _cachedConfig = result.data   // 写缓存
      return _cachedConfig
    }
  } catch (e) {
    console.warn('[hierarchyFilterBuilder] Failed to fetch config, using fallback')
  }
  return getFallbackConfig()        // ← 唯一需要改造的硬编码
}
```

**硬编码 fallback 与 YAML 元数据严重脱节**：

| 差异维度 | `getFallbackConfig()` | `hierarchies.yaml` |
|----------|----------------------|-------------------|
| 层级数 | **4 层** | **7 层** |
| 缺失层级 | `product`, `version` | 完整 |
| dimensions | 4 个 | 6 个（缺 product/version） |
| UI 配置 | 4 色 | 6 色 + icon |

**调用链**（3 处直接 + 6 处间接）：

```
直接调用:
  fetchHierarchyConfig() L29  → 网络失败时降级
  DIMENSIONS(config)      L69  → config || getFallbackConfig()
  HIERARCHY_LEVELS(config) L74 → config || getFallbackConfig()

间接调用（通过 DIMENSIONS / HIERARCHY_LEVELS 透传）:
  getFilterParam() → getParentFilterField() → getHierarchyLevel()
  → getLevelNumber() → isValidDimension() → buildHierarchyFilter()
```

### 1.3 改造方案

**路线 A（推荐）：替换 fallback 数据为从 YAML 对齐的静态映射**

将 `getFallbackConfig()` 的硬编码数据替换为与 [hierarchies.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/hierarchies.yaml) 一致的 6 层结构，消除"fallback 给的是残缺数据"的风险：

```javascript
export function getFallbackConfig() {
  return {
    dimensions: ['product', 'version', 'domain', 'sub_domain',
                 'service_module', 'business_object'],
    hierarchy_levels: {
      product: {
        level: 0,
        object: 'product',
        parent_object: null,
        filter_param: null,
        ui: { icon: 'inventory_2', color: '#9C27B0' }
      },
      version: {
        level: 1,
        object: 'version',
        parent_object: 'product',
        filter_param: 'product_id',
        ui: { icon: 'tag', color: '#FF9800' }
      },
      domain: {
        level: 2,
        object: 'domain',
        parent_object: 'version',
        filter_param: 'version_id',
        ui: { icon: 'business', color: '#4CAF50' }
      },
      sub_domain: {
        level: 3,
        object: 'sub_domain',
        parent_object: 'domain',
        filter_param: 'domain_id',
        ui: { icon: 'account_tree', color: '#2196F3' }
      },
      service_module: {
        level: 4,
        object: 'service_module',
        parent_object: 'sub_domain',
        filter_param: 'sub_domain_id',
        ui: { icon: 'widgets', color: '#FF9800' }
      },
      business_object: {
        level: 5,
        object: 'business_object',
        parent_object: 'service_module',
        filter_param: 'service_module_id',
        ui: { icon: 'description', color: '#9C27B0' }
      }
    }
  }
}
```

**额外发现（非阻塞，单独处理）**：`semantics.hierarchy_level`（从 1 开始）与 `hierarchy.level`（从 0 开始）偏移了 1，建议在后续迭代中对齐。

### 1.4 需同步修改的下游代码

fallback 从 4 层扩展到 6 层后，以下函数需同步更新：

| 文件 | 函数 | 改动 |
|------|------|------|
| hierarchyFilterBuilder.js:L195-L235 | `collectAncestorIds()` | `dimensionToParentType` 增加 `product: 'product'`, `version: 'product'` |
| hierarchyFilterBuilder.js:L249-L304 | `buildOriginalFilter()` | `typePrefixes` 增加 `product_`, `version_` 前缀 |
| hierarchyFilterBuilder.js:L309-L331 | `buildHierarchyFilter()` | 确认 6 维度的 filter 构建逻辑正确 |

### 1.5 验收标准

| ID | 标准 | 验证方式 |
|----|------|---------|
| AC-005-1 | `getFallbackConfig()` 返回 6 层结构（含 product/version） | 代码审查 |
| AC-005-2 | 6 层结构的 fields 与 `hierarchies.yaml` 一致 | 逐字段对比 |
| AC-005-3 | `fetchHierarchyConfig()` API 成功时正常返回缓存，失败时返回 fallback | 单元测试 |
| AC-005-4 | `buildHierarchyFilter()` 在 6 维度下正确生成过滤条件 | 单元测试 |
| AC-005-5 | `collectAncestorIds()` 正确处理 product/version 维度 | 单元测试 |

---

## 二、FR-010：Page Type 路由映射元数据化

### 2.1 问题描述

menu.yaml 定义了 5 种 `page_type`（object_list、object_detail、multi_object_hub、custom_page、dashboard），但路由路径生成逻辑**纯硬编码**在两处 `switch(page_type)` 中，且两处存在行为不一致。

### 2.2 两处硬编码详解

**位置 ①：AppRootLayout.vue `deriveRoutePath()`** [L55-L64](file:///d:/filework/excel-to-diagram/src/components/common/AppRootLayout.vue#L55-L64)

```javascript
function deriveRoutePath(menu) {
  switch (menu.page_type) {
    case 'object_list':
      return `/objects/${menu.primary_object_type}`
    case 'multi_object_hub':
      return `/${menu.menu_code}`
    default:
      return `/${menu.menu_code}`
  }
}
```

**位置 ②：dynamicRoutes.js `_resolvePath()`** [L62-L73](file:///d:/filework/excel-to-diagram/src/router/dynamicRoutes.js#L62-L73)

```javascript
function _resolvePath(menu) {
  if (menu.menu_path) return menu.menu_path
  switch (menu.page_type) {
    case 'object_list':
      return `/objects/${menu.primary_object_type}`
    case 'multi_object_hub':
      return `/${menu.menu_code}`
    default:
      return `/${menu.menu_code.replace(/_/g, '-')}`  // ← 与 deriveRoutePath 不一致！
  }
}
```

**两处 default 分支行为差异**：`deriveRoutePath` 直接使用 `menu_code`（可能含下划线），`_resolvePath` 做 `replace(/_/g, '-')`。这正是缺乏单一事实源的典型症状。

### 2.3 其他硬编码清单

| 编号 | 位置 | 硬编码内容 |
|------|------|-----------|
| ③ | `PAGE_TYPE_COMPONENTS` [L4-L8](file:///d:/filework/excel-to-diagram/src/router/dynamicRoutes.js#L4-L8) | `custom_page` 和 `dashboard` 无组件映射 |
| ④ | `_resolveComponent()` [L32-L34](file:///d:/filework/excel-to-diagram/src/router/dynamicRoutes.js#L32-L34) | `custom_page` 返回 `null` → 路由永不注册 |
| ⑤ | `_buildProps()` [L41-L49](file:///d:/filework/excel-to-diagram/src/router/dynamicRoutes.js#L41-L49) | `object_detail`/`dashboard`/`custom_page` 无 props 逻辑 |
| ⑥ | `menu_auto_generator.py` [L95](file:///d:/filework/excel-to-diagram/meta/services/menu_auto_generator.py#L95) | `menu_path` 固定为 `/{id.replace('_', '-')}` |

### 2.4 改造方案

**分两步实施，避免大爆炸重构**：

#### Step 1：统一路径逻辑 + menu.yaml 新增 `route_template`

在 [menu.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/menu.yaml) 的 `page_type` 枚举中增加 `route_template` 属性：

```yaml
- id: page_type
  name: 页面类型
  type: string
  required: true
  default: object_list
  enum_values:
    - value: object_list
      route_template: "/objects/{primary_object_type}"
    - value: object_detail
      route_template: "/objects/{primary_object_type}/{id}"
    - value: multi_object_hub
      route_template: "/{menu_code}"
    - value: custom_page
      route_template: "/{menu_code}"
    - value: dashboard
      route_template: "/{menu_code}"
```

在 menu 表中新增 `route_template` 字段（nullable），由 `menu_auto_generator.py` 在生成菜单时从 `page_type` 枚举查找对应模板写入。

#### Step 2：前端两处 switch → 统一的模板变量替换

创建共享工具函数：

```javascript
// src/utils/routeTemplate.js
export function resolveRoutePath(menu) {
  if (menu.menu_path) return menu.menu_path

  const template = menu.route_template || getDefaultTemplate(menu.page_type)
  if (!template) return `/${(menu.menu_code || '').replace(/_/g, '-')}`

  return template
    .replace('{primary_object_type}', menu.primary_object_type || '')
    .replace('{menu_code}', menu.menu_code || '')
    .replace('{id}', menu.id || ':id')
    .replace(/_/g, '-')  // 统一做下划线替换
}

function getDefaultTemplate(page_type) {
  const defaults = {
    object_list: '/objects/{primary_object_type}',
    multi_object_hub: '/{menu_code}',
  }
  return defaults[page_type] || '/{menu_code}'
}
```

然后替换两处：

```javascript
// AppRootLayout.vue — 删除 deriveRoutePath，改为:
to: menu.menu_path || resolveRoutePath(menu)

// dynamicRoutes.js — 删除 _resolvePath，改为:
const path = resolveRoutePath(menu)
```

**向后兼容**：如果 menu 表中没有 `route_template` 字段（存量数据），`getDefaultTemplate()` 提供与当前硬编码一致的默认值，确保平滑过渡。

#### Step 3（可后置）：扩展 PAGE_TYPE_COMPONENTS

为 `custom_page` 和 `dashboard` 增加组件映射入口，使其可被动态路由注册：

```javascript
const PAGE_TYPE_COMPONENTS = {
  object_list:      () => import('@/views/GenericObjectList.vue'),
  object_detail:    () => import('@/views/ObjectDetailPage.vue'),
  multi_object_hub: () => import('@/views/GenericTabContainer.vue'),
  dashboard:        () => import('@/views/Dashboard.vue'),
  custom_page:      () => import('@/views/CustomPageRenderer.vue'),
}
```

### 2.5 menu.yaml 需新增字段

在 [menu.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/menu.yaml) 的 `page_type` 枚举值中：

```yaml
enum_values:
  - value: object_list
    route_template: "/objects/{primary_object_type}"
    default_component: "GenericObjectList"
  - value: object_detail
    route_template: "/objects/{primary_object_type}/{id}"
    default_component: "ObjectDetailPage"
  - value: multi_object_hub
    route_template: "/{menu_code}"
    default_component: "GenericTabContainer"
  - value: custom_page
    route_template: "/{menu_code}"
    default_component: "CustomPageRenderer"
  - value: dashboard
    route_template: "/{menu_code}"
    default_component: "Dashboard"
```

同时在 menu 表 schema 中新增：
- `route_template` (string, nullable) — 路由模板
- `component_path` (string, nullable) — 自定义组件路径（仅 custom_page 使用）

### 2.6 改造文件清单

| 文件 | 改动 | 影响范围 |
|------|------|---------|
| **meta/schemas/menu.yaml** | page_type 枚举增加 `route_template` + `default_component` | 元数据声明 |
| **meta/services/menu_auto_generator.py** | 生成菜单时从枚举查找 `route_template` 写入 | 后端 |
| **src/utils/routeTemplate.js** | **新增**：统一路由路径解析工具函数 | 前端 |
| **src/components/common/AppRootLayout.vue** | 删除 `deriveRoutePath()`，改用 `resolveRoutePath()` | 侧边导航 |
| **src/router/dynamicRoutes.js** | 删除 `_resolvePath()`，改用 `resolveRoutePath()` | 动态路由 |

### 2.7 验收标准

| ID | 标准 | 验证方式 |
|----|------|---------|
| AC-010-1 | menu.yaml `page_type` 枚举值均有 `route_template` 字段 | YAML 校验 |
| AC-010-2 | `deriveRoutePath()` 和 `_resolvePath()` 均已删除 | 代码审查 |
| AC-010-3 | `resolveRoutePath()` 统一处理所有 5 种 page_type | 单元测试 |
| AC-010-4 | default 分支行为一致（统一下划线替换） | 单元测试 |
| AC-010-5 | 存量数据（无 route_template 字段）使用默认模板正常工作 | 集成测试 |
| AC-010-6 | menu_auto_generator.py 生成的菜单包含正确的 `route_template` | 集成测试 |
| AC-010-7 | Sidebar 导航链接和动态路由路径一致 | E2E 测试 |

---

## 三、拦截器测试薄弱项补充

### 3.1 问题描述

16 个拦截器中有 2 个缺少独立测试文件：

| 拦截器 | 当前测试覆盖 | 问题 |
|--------|----------|------|
| **CascadeInterceptor** | 仅 8 用例，在 `test_interceptors_unit.py` 中 | 无独立测试文件，未覆盖级联清理的实际业务场景 |
| **PersistenceInterceptor** | 仅 9 用例，在 `test_interceptors_unit.py` 中 | 无独立测试文件，未覆盖 CRUD 各路径的异常处理 |

相比之下，其他拦截器测试充分得多：AuditInterceptor 92 用例、FieldPolicyInterceptor 37 用例、BusinessLogInterceptor 37 用例。

### 3.2 CascadeInterceptor 独立测试

**文件**: `meta/tests/interceptors/test_cascade_interceptor_detailed.py`

**测试范围**：

| # | 场景 | 说明 |
|---|------|------|
| 1 | DELETE 触发 after_action | 验证 after_action 中执行级联逻辑 |
| 2 | 非 DELETE 操作跳过 | CREATE/UPDATE/READ 不触发级联 |
| 3 | 级联清理 annotations | 删除 BO 时清理关联的 annotation 记录 |
| 4 | 级联清理关联表（dict policy） | `cascade.delete: {association: "table_name"}` |
| 5 | 级联清理关联表（string policy） | `cascade.delete: "table_name"` |
| 6 | 无 cascade 配置时跳过 | YAML 未定义 cascade 时不执行清理 |
| 7 | FK 列自动推断 | 无 explicit cascade 配置时通过 FK 推断 |
| 8 | 级联清理子对象 | 通过 parent_id FK 清理子对象 |
| 9 | 错误处理 | 级联清理异常不应阻断主删除流程 |
| 10 | 清理顺序 | annotations → 关联表 → 子对象（顺序不可乱） |

**预估**: 12-15 用例

### 3.3 PersistenceInterceptor 独立测试

**文件**: `meta/tests/interceptors/test_persistence_interceptor_detailed.py`

**测试范围**：

| # | 场景 | 说明 |
|---|------|------|
| 1 | CREATE 委托 registry.create() | 验证正确委托 |
| 2 | READ 委托 registry.read() | 验证正确委托 |
| 3 | UPDATE 委托 registry.update() | 验证正确委托 |
| 4 | DELETE 委托 registry.delete() | 验证正确委托 |
| 5 | 非 CRUD action 跳过 | action 为 'query'/'export' 等非 CRUD 时跳过 |
| 6 | CREATE 返回新记录 | 返回的 record 包含 id 等数据库生成的字段 |
| 7 | UPDATE 返回更新后记录 | 返回的 record 反映数据库最新状态 |
| 8 | DELETE 返回 delete 结果 | 验证返回结构 |
| 9 | registry 方法抛异常时的处理 | 异常应正确传播或包装 |
| 10 | should_execute 控制 | 验证 should_execute 返回 True |
| 11 | 事务回滚 | 写入失败时不残留脏数据 |
| 12 | 批量操作 | 批量 create/update/delete 的正确性 |

**预估**: 15-18 用例

### 3.4 验收标准

| ID | 标准 | 验证方式 |
|----|------|---------|
| AC-TEST-1 | `test_cascade_interceptor_detailed.py` 存在且 ≥12 用例 | test runner |
| AC-TEST-2 | `test_persistence_interceptor_detailed.py` 存在且 ≥15 用例 | test runner |
| AC-TEST-3 | 两个测试文件全部通过 | `pytest` |
| AC-TEST-4 | 拦截器 16/16 均有独立测试文件 | 文件存在性检查 |

---

## 四、实施优先级

```
Phase 1 (本次):
  ✅ FR-005 Step 1: 替换 getFallbackConfig() 为 6 层数据结构
  ✅ FR-005 Step 2: 更新 downstream 函数（collectAncestorIds/buildOriginalFilter）
  ✅ FR-010 Step 1: menu.yaml 新增 route_template + 数据迁移
  ✅ FR-010 Step 2: 创建 routeTemplate.js + 替换两处 switch

Phase 2 (后续):
  ⏳ FR-010 Step 3: 扩展 PAGE_TYPE_COMPONENTS + custom_page/dashboard 组件
  ⏳ 拦截器测试补充: CascadeInterceptor + PersistenceInterceptor 独立测试文件
  ⏳ menu_auto_generator.py 适配 route_template 生成
```

---

## 五、影响范围总结

| 改动类型 | 文件数 | 风险等级 |
|----------|:---:|:---:|
| 前端工具函数新增 | 1 | 🟢 低 |
| 前端现有代码修改 | 2 (AppRootLayout + dynamicRoutes) | 🟡 中 |
| 前端工具函数数据更新 | 1 (hierarchyFilterBuilder) | 🟡 中 |
| YAML 元数据扩展 | 1 (menu.yaml) | 🟢 低 |
| 后端生成器适配 | 1 (menu_auto_generator.py) | 🟢 低 |
| 测试文件新增 | 2 (拦截器测试) | 🟢 低 |
| **合计** | **8** | 🟡 中 |

**回滚策略**: FR-005 和 FR-010 的改动均为纯前端替换，可通过 Git revert 快速回滚。FR-010 的 YAML 变更仅扩展枚举元数据，不影响已有的菜单记录。
