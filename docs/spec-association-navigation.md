## 目录

1. [1. 功能概述](#1-功能概述)
2. [2. 功能需求 (FR)](#2-功能需求-(fr))
3. [3. 非功能需求 (NFR)](#3-非功能需求-(nfr))
4. [4. 架构设计](#4-架构设计)
5. [5. 数据模型](#5-数据模型)
6. [6. API 设计](#6-api-设计)
7. [7. 核心算法](#7-核心算法)
8. [8. 组件规格](#8-组件规格)
9. [9. Composable 规格](#9-composable-规格)
10. [10. 文件清单](#10-文件清单)
11. [11. 测试矩阵](#11-测试矩阵)
12. [12. 交互流程图](#12-交互流程图)
13. [13. 设计决策记录 (ADR)](#13-设计决策记录-(adr))
14. [14. 未来扩展方向](#14-未来扩展方向)

---
# 关联导航功能 - 技术规格说明书 (Spec)

> **版本**: 1.0  
> **状态**: 已实施  
> **日期**: 2026-05-16  
> **关联测试**: 后端 32 个 + 前端 43 个 = **75 个测试全部通过**

---

## 1. 功能概述

### 1.1 目标

实现基于选中对象（支持多选）的通用关联导航能力：用户在列表页面选择一个或多个对象后，通过"关联导航"下拉菜单选择某个关联关系（Association），系统自动跳转到目标对象的列表页面，并以源对象为过滤条件展示关联数据。

### 1.2 核心能力

| 能力 | 描述 |
|------|------|
| 多选导航 | 支持同时选中多个源对象进行导航 |
| 智能推导 | YAML 无需配置 navigation 字段，后端根据关联类型自动推导 |
| 批量查询 | 单次 API 调用合并多个源对象的关联目标 |
| 状态恢复 | 导航后可完整恢复源页面的选中、滚动、过滤状态 |
| 来源追踪 | 目标页面显示来源信息栏，提供返回入口 |
| 多来源适配 | 支持列表页、组合页面（如架构数据管理）、弹窗三种来源场景 |

---

## 2. 功能需求 (FR)

| ID | 需求描述 | 优先级 |
|----|----------|--------|
| FR-001 | 列表页工具栏在选中对象时显示"关联导航"按钮 | P0 |
| FR-002 | 点击按钮展开下拉菜单，列出所有可导航的关联选项 | P0 |
| FR-003 | 仅显示所有选中对象共有的关联选项（交集） | P0 |
| FR-004 | 选择关联后跳转到目标列表页面 | P0 |
| FR-005 | 目标页面以源对象为过滤条件预筛选数据 | P0 |
| FR-006 | 目标页面顶部显示来源信息栏和"返回来源"按钮 | P1 |
| FR-007 | 返回来源时完全恢复源页面状态（选中、滚动、过滤） | P1 |
| FR-008 | 组合页面导航时跳转到独立的目标列表页面 | P1 |
| FR-009 | 弹窗内导航时关闭当前弹窗打开新弹窗 | P2 |
| FR-010 | 下拉菜单中每个关联项显示目标计数 | P2 |

## 3. 非功能需求 (NFR)

| ID | 需求 | 要求 |
|-----|------|------|
| NFR-001 | YAML 最小化原则 | navigation 配置由后端智能推导，YAML 中无需声明 |
| NFR-002 | 会话级状态管理 | 使用 SessionStorage 存储导航状态，关闭标签页自动清除 |
| NFR-003 | 性能 | 批量查询使用单次 SQL 合并，避免 N+1 问题 |
| NFR-004 | 兼容性 | 不影响现有 MetaListPage 功能，纯增量集成 |

---

## 4. 架构设计

### 4.1 分层架构

```
┌─────────────────────────────────────────────────────┐
│                    前端 (Vue 3)                      │
│                                                      │
│  ┌──────────────────┐  ┌─────────────────────────┐  │
│  │ NavigationSourceInfo│  │ AssociationNavigationMenu│  │
│  │ (目标页来源信息栏)  │  │ (工具栏下拉菜单组件)      │  │
│  └────────┬──────────┘  └──────────┬──────────────┘  │
│           │                        │                 │
│  ┌────────▼────────────────────────▼──────────────┐  │
│  │              useAssociationNavigation           │  │
│  │         (导航逻辑 + SessionStorage 管理)          │  │
│  └──────────────────────┬─────────────────────────┘  │
│                         │                            │
│  ┌──────────────────────▼─────────────────────────┐  │
│  │              useMetaList                        │  │
│  │    (navigableAssociations / batchGetCounts)     │  │
│  └──────────────────────┬─────────────────────────┘  │
│                         │                            │
│  ┌──────────────────────▼─────────────────────────┐  │
│  │              boService.js                       │  │
│  │       batchQueryAssociations()                  │  │
│  └──────────────────────┬─────────────────────────┘  │
├─────────────────────────┼───────────────────────────┤
│                    HTTP API                         │
│   POST /api/v2/bo/{type}/$associations/{name}/batch-query│
├─────────────────────────┼───────────────────────────┤
│                    后端 (Python/Flask)               │
│  ┌──────────────────────▼─────────────────────────┐  │
│  │              bo_api.py                          │  │
│  │        batch_query_associations 端点             │  │
│  └──────────────────────┬─────────────────────────┘  │
│                         │                            │
│  ┌──────────────────────▼─────────────────────────┐  │
│  │              BOFramework                        │  │
│  │   _infer_navigation() ← 智能推导导航配置          │  │
│  │   get_ui_config() ← 注入 navigation 到 UI配置    │  │
│  └──────────┬──────────────────────┬───────────────┘  │
│             │                      │                   │
│  ┌──────────▼──────────┐  ┌───────▼──────────────┐   │
│  │ AssociationEngine    │  │ PersistenceInterceptor│   │
│  │ batch_query_* ()     │  │ action 分发           │   │
│  └─────────────────────┘  └──────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### 4.2 数据流

```
用户选中对象 → selectedIds 变更 → visible=true 显示导航菜单
     ↓
用户点击关联项 → onNavigate(assoc)
     ↓
navigateToAssociation(assoc, ids, objectType)
  ├─ 1. 查询源对象名称 (boService.query)
  ├─ 2. 保存源页面状态到 SessionStorage
  └─ 3. router.push({ path, query: { _nav_source_type, _nav_source_ids, ... } })
     ↓
目标页面加载 → parseNavigationParams()
  ├─ isNavigationTarget() = true
  ├─ getNavigationFilterParam() → { role_id__in: "1,2,3" }
  └─ setContextFilters(filterParam) → 自动过滤
     ↓
NavigationSourceInfo 渲染来源信息栏
     ↓
用户点击"返回来源" → navigateBack()
  ├─ 从 SessionStorage 恢复 state
  └─ router.push({ path: state.path, query: state.query })
```

---

## 5. 数据模型

### 5.1 导航配置结构 (navigation)

```yaml
# 由 _infer_navigation() 自动推导，无需在 YAML 中声明
navigation:
  enabled: boolean        # 是否可导航
  label: string           # 显示名称
  icon: string            # 图标名称
  display_mode: string    # 展示模式 (固定 "list")
  readonly: boolean       # 是否只读
```

### 5.2 URL 导航参数

| 参数名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `_nav_source_type` | string | 源对象类型 | `role` |
| `_nav_source_ids` | string | 源对象ID，逗号分隔 | `1,2,3` |
| `_nav_source_names` | string | 源对象显示名，逗号分隔 | `Admin,Editor,Viewer` |
| `_nav_assoc_name` | string | 关联名称 | `users` |
| `_nav_context` | string | 来源上下文 (可选) | `dialog` |

### 5.3 SessionStorage 状态结构

**Key 格式**: `_nav_source_state_{objectType}`

```json
{
  "path": "/user-permission/roles",
  "query": { "page": "2", "status": "active" },
  "scrollPosition": 300,
  "selectedIds": [1, 2, 3],
  "filters": { "status": "active" },
  "sort": { "prop": "name", "order": "ascending" },
  "pagination": { "current": 2, "pageSize": 50 },
  "timestamp": 1742000000000
}
```

### 5.4 批量查询响应格式

```json
{
  "success": true,
  "data": {
    "items": [...],           // 去重后的目标对象列表
    "total": 15,              // 去重后的总数
    "page": 1,
    "page_size": 20,
    "counts": {               // 每个源对象的关联计数
      "1": 5,
      "2": 8,
      "3": 12
    }
  }
}
```

---

## 6. API 设计

### 6.1 批量查询关联目标

**端点**: `POST /api/v2/bo/<object_type>/$associations/<association_name>/batch-query`

**请求体**:

```json
{
  "source_ids": [1, 2, 3],
  "page": 1,
  "page_size": 20,
  "search": ""
}
```

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `source_ids` | Array[int] | 是 | - | 源对象ID列表 |
| `page` | int | 否 | 1 | 页码 |
| `page_size` | int | 否 | 20 | 每页条数 |
| `search` | string | 否 | "" | 搜索关键词 |

**响应**: 见 5.4 节

### 6.2 错误处理

| 场景 | HTTP 状态码 | 响应 |
|------|-------------|------|
| source_ids 为空 | 200 | `{ success: true, data: { items: [], total: 0, counts: {} } }` |
| 对象类型不存在 | 200 | 同上（静默处理） |
| 关联名称不存在 | 200 | 同上（静默处理） |

---

## 7. 核心算法

### 7.1 导航配置智能推导规则 (`_infer_navigation`)

```
输入: assoc_dict (关联元数据字典)

IF assoc_dict.navigation 已存在 THEN
    RETURN  // 不覆盖已有配置
END IF

enabled_map = {
    'many_to_many'         → True,
    'composition'          → True,
    'reverse_many_to_many' → True,
    'reference'            → False,
}
enabled = enabled_map.get(assoc.type, False)

icon_map = {
    'user'        → 'User',
    'role'        → 'Key',
    'permission'  → 'Lock',
    'user_group'  → 'UserFilled',
    'enum_type'   → 'Collection',
    'audit_log'   → 'Document',
    *(其他)*      → 'Link',
}

label 优先级:
  1. assoc.navigation.label (已有配置时)
  2. assoc.label
  3. assoc.name
  4. '' (空字符串)

输出: assoc_dict.navigation = { enabled, label, icon, display_mode:'list', readonly }
```

### 7.2 可导航关联过滤规则 (`navigableAssociations`)

```
FOR EACH assoc IN metaConfig.associations:
    nav = assoc.navigation || {}
    IF nav.enabled === false THEN CONTINUE
    IF assoc.type NOT IN ['many_to_many', 'composition', 'reverse_many_to_many'] THEN CONTINUE
    RETURN assoc
END FOR
```

### 7.3 批量多对多查询算法 (`_batch_query_m2m`)

```
输入: source_ids=[s1,s2,...,sn], through_table, source_key, target_key, target_table

-- Step 1: 通过中间表 GROUP BY 统计每源的关联数量
SELECT {source_key}, COUNT(DISTINCT {target_key}) AS cnt
FROM {through_table}
WHERE {source_key} IN (s1, s2, ..., sn)
GROUP BY {source_key}
→ 结果: counts = { s1: c1, s2: c2, ..., sn: cn }

-- Step 2: DISTINCT 查询所有去重的目标对象
SELECT t.* FROM {target_table} t
INNER JOIN {through_table} m ON t.id = m.{target_key}
WHERE m.{source_key} IN (s1, s2, ..., sn)
ORDER BY t.id
LIMIT page_size OFFSET (page-1) * page_size
→ 结果: items (去重), total (COUNT DISTINCT)

输出: { items, total, page, page_size, counts }
```

---

## 8. 组件规格

### 8.1 AssociationNavigationMenu.vue

**位置**: `src/components/common/MetaListPage/AssociationNavigationMenu.vue`

**Props**:

| Prop | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `associations` | Array | `[]` | 可导航关联列表 |
| `selectedIds` | Set | `new Set()` | 当前选中的对象ID集合 |
| `loading` | Boolean | `false` | 加载状态 |

**Emits**:

| Event | Payload | 说明 |
|-------|---------|------|
| `navigate` | `association` object | 用户选择了某个关联进行导航 |

**行为**:

- `visible = selectedIds.size > 0 && associations.length > 0` 时渲染
- 使用 Element Plus `el-dropdown` + `el-button` 实现
- 每个下拉项显示: 图标 + 标签 + 计数(可选)
- loading 时所有菜单项禁用

**模板结构**:

```
el-dropdown (v-if="visible", trigger="click")
  └─ el-button: [Link图标] 关联导航 [ArrowDown]
  └─ template #dropdown
      └─ el-dropdown-menu.assoc-nav-menu
          ├─ el-dropdown-item (v-for="assoc") → @command="onNavigate(assoc)"
          │   ├─ el-icon (动态图标)
          │   ├─ span.assoc-nav-label (标签文本)
          │   └─ span.assoc-nav-count (计数, 可选)
          └─ div.assoc-nav-empty (associations 为空时)
```

### 8.2 NavigationSourceInfo.vue

**位置**: `src/components/common/MetaListPage/NavigationSourceInfo.vue`

**Props**:

| Prop | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `sourceType` | String | `''` | 源对象类型 |
| `sourceIds` | Array | `[]` | 源对象ID列表 |
| `sourceNames` | Array | `[]` | 源对象显示名列表 |
| `associationName` | String | `''` | 关联名称 |
| `associationLabel` | String | `''` | 关联显示标签 |

**Emits**:

| Event | Payload | 说明 |
|-------|---------|------|
| `navigate-back` | - | 用户点击返回来源 |

**行为**:

- `sourceInfo` computed: 当 sourceType 和 sourceIds 都有值时生成信息对象
- 无 sourceNames 时回退显示 `#{id}`
- 多个对象 (>1) 时显示数量 Tag
- associationLabel 缺失时回退到 associationName

**视觉样式**:

```
┌──────────────────────────────────────────────────────────┐
│ [Link] 从 Admin, Editor 的 用户 导航  [3 个对象]  [← 返回来源] │
│ 背景: #ecf5ff 边框: #c6e2ff                                │
└──────────────────────────────────────────────────────────┘
```

---

## 9. Composable 规格

### 9.1 useAssociationNavigation()

**文件**: `src/composables/useAssociationNavigation.js`

**导出接口**:

| 函数/属性 | 类型 | 说明 |
|-----------|------|------|
| `navigationSource` | `Ref<Object\|null>` | 当前导航来源信息 |
| `parseNavigationParams()` | `Function → Object\|null` | 解析 URL query 中的导航参数 |
| `navigateToAssociation(assoc, ids, type, opts?)` | `Async Function` | 执行导航跳转 |
| `navigateBack()` | `Function → boolean` | 返回源页面 |
| `isNavigationTarget()` | `Function → boolean` | 判断是否为导航目标页 |
| `getNavigationFilterParam()` | `Function → Object` | 生成导航过滤参数 |
| `saveSourceState(...)` | `Function` | 保存源页面状态 |
| `restoreSourceState(type)` | `Function → Object\|null` | 恢复源页面状态 |
| `clearSourceState(type)` | `Function` | 清除存储的状态 |

**路由映射表** (`routePathMap`):

| target_entity | 路径 |
|---------------|------|
| `user` | `/user-permission/users` |
| `role` | `/user-permission/roles` |
| `permission` | `/user-permission/permissions` |
| `user_group` | `/user-permission/groups` |
| `enum_type` | `/business-config/enums` |
| *(其他)* | `/{target_entity.replace(/_/g, '-')}` |

### 9.2 useMetaList 新增导出

| 属性 | 类型 | 说明 |
|------|------|------|
| `navigableAssociations` | Computed\<Array\> | 过滤后的可导航关联列表 |
| `getNavigableAssociations()` | Async Function → Array | 获取可导航关联 |
| `batchGetAssociationCounts(name)` | Async Function → Object | 批量获取某关联的计数 |

---

## 10. 文件清单

### 10.1 新增文件

| 文件 | 类型 | 行数 | 说明 |
|------|------|------|------|
| `src/components/common/MetaListPage/AssociationNavigationMenu.vue` | Vue 组件 | 107 | 关联导航下拉菜单 |
| `src/components/common/MetaListPage/NavigationSourceInfo.vue` | Vue 组件 | 119 | 导航来源信息栏 |
| `src/composables/__tests__/useAssociationNavigation.test.js` | 测试 | ~250 | Composable 测试 (18 cases) |
| `src/components/common/MetaListPage/__tests__/AssociationNavigationMenu.test.js` | 测试 | ~185 | 菜单组件测试 (14 cases) |
| `src/components/common/MetaListPage/__tests__/NavigationSourceInfo.test.js` | 测试 | ~120 | 信息栏组件测试 (11 cases) |
| `meta/tests/test_navigation.py` | 测试 | ~280 | 推导逻辑测试 (21 cases) |
| `meta/tests/test_batch_navigation.py` | 测试 | ~250 | 批量查询测试 (11 cases) |

### 10.2 修改文件

| 文件 | 修改内容 |
|------|----------|
| `meta/core/bo_framework.py` | 新增 `_infer_navigation()` 静态方法; `get_ui_config()` 中调用推导; 新增 `batch_query_associations()` 便捷方法 |
| `meta/core/association_engine.py` | 新增 `batch_query_associations()` 入口; `_batch_query_m2m()` / `_batch_query_composition()` / `_batch_query_reverse_m2m()` 子方法; `_get_search_fields()` 辅助方法 |
| `meta/api/bo_api.py` | 新增 `POST /.../$associations/<name>/batch-query` 端点 |
| `meta/core/interceptors/persistence_interceptor.py` | after_action 白名单添加 `batch_query_associations`; 添加分发分支 |
| `src/services/boService.js` | 新增 `batchQueryAssociations(objectType, associationName, data)` 方法 |
| `src/composables/useAssociationNavigation.js` | **新建** - 导航核心 composable (169行) |
| `src/composables/useMetaList.js` | 新增 `navigableAssociations` computed; `getNavigableAssociations()`; `batchGetAssociationCounts()` |
| `src/components/common/MetaListPage/MetaListPage.vue` | 导入新组件+composable; 工具栏集成 AssociationNavigationMenu; 页面顶集成 NavigationSourceInfo; onMounted 解析导航参数; defineExpose 暴露新属性 |

---

## 11. 测试矩阵

### 11.1 后端测试 (32 个)

| 测试类 | 用例数 | 覆盖范围 |
|--------|--------|----------|
| TestInferNavigation | 15 | 所有关联类型的 enabled 推断; icon 映射(7种); label 优先级; readonly 继承 |
| TestInferNavigationEdgeCases | 3 | 空字典; target_type 回退; navigation=None |
| TestGetUIConfigNavigationIntegration | 3 | m2m 导航生成; reference disabled; 多关联各自推导 |
| TestBatchQueryAssociationsEntry | 4 | 空/缺失参数; 未知类型/关联 |
| TestBatchQueryM2M | 4 | 单源/多源/无数据/计数正确性 |
| TestBatchQueryComposition | 1 | 组合关系基本查询 |
| TestBOFrameworkBatchQueryIntegration | 2 | 方法存在性; 便捷调用 |

### 11.2 前端测试 (43 个)

| 测试文件 | 用例数 | 覆盖范围 |
|----------|--------|----------|
| useAssociationNavigation.test.js | 18 | parseNavigationParams (4); navigateToAssociation (4); navigateBack (3); isNavigationTarget (2); getNavigationFilterParam (2); 状态管理 (3) |
| AssociationNavigationMenu.test.js | 14 | 可见性 (3); 事件触发 (1); 属性传递 (3); computed (4); 边界 (3) |
| NavigationSourceInfo.test.js | 11 | 渲染条件 (4); 多对象标签 (1); 交互 (1); 回退逻辑 (2) |

### 11.3 运行命令

```bash
# 后端测试
cd meta && python -m pytest tests/test_navigation.py tests/test_batch_navigation.py -v

# 前端测试
npx vitest run src/composables/__tests__/useAssociationNavigation.test.js \
  src/components/common/MetaListPage/__tests__/AssociationNavigationMenu.test.js \
  src/components/common/MetaListPage/__tests__/NavigationSourceInfo.test.js
```

---

## 12. 交互流程图

### 12.1 主流程: 列表页导航

```
┌─────────────┐     选中对象      ┌──────────────────────┐
│  MetaListPage │ ──────────────→ │  toolbar-left 区域    │
│  (用户列表)   │                  │  [搜索] [操作] [批量]   │
└─────────────┘                  │  [关联导航 ▼] ← NEW   │
                                 └──────────┬───────────┘
                                            │ 点击
                                 ┌──────────▼───────────┐
                                 │  el-dropdown-menu      │
                                 │  ├─ [Key] 角色 (5)     │
                                 │  ├─ [UserFilled] 用户组(3)│
                                 │  └─ [Lock] 权限 (12)   │
                                 └──────────┬───────────┘
                                            │ 选择
                                 ┌──────────▼───────────┐
                                 │ navigateToAssociation  │
                                 │ 1. 查询源对象名称       │
                                 │ 2. 保存状态→SessionStorage│
                                 │ 3. router.push          │
                                 └──────────┬───────────┘
                                            │
                                 ┌──────────▼───────────┐
                                 │  角色列表页              │
                                 │  ┌──────────────────┐  │
                                 │  │[Link]从Admin,Editor│  │
                                 │  │ 的角色导航 [2个对象]│  │
                                 │  │        [←返回来源] │  │
                                 │  └──────────────────┘  │
                                 │  ┌──────────────────┐  │
                                 │  │ 表格 (已按role_id__in│  │
                                 │  │  过滤)              │  │
                                 │  └──────────────────┘  │
                                 └───────────────────────┘
```

### 12.2 返回流程

```
┌──────────────────────┐     点击      ┌────────────────────┐
│ [← 返回来源] 按钮     │ ──────────→ │ navigateBack()      │
└──────────────────────┘              │ 1. 读取SessionStorage│
                                      │ 2. router.push       │
                                      │    (path + query)    │
                                      └──────────┬─────────┘
                                                 │
                                      ┌──────────▼─────────┐
                                      │ 源列表页 (完全恢复)   │
                                      │ ✓ 选中对象恢复        │
                                      │ ✓ 滚动位置恢复        │
                                      │ ✓ 过滤条件恢复        │
                                      │ ✓ 分页位置恢复        │
                                      └────────────────────┘
```

---

## 13. 设计决策记录 (ADR)

### ADR-001: 智能推导 vs YAML 显式配置

**决策**: 采用智能推导，YAML 无需声明 navigation 配置

**理由**:
- 符合单一事实原则 (Single Source of Truth): 元模型已包含 type/target_entity 等信息
- 减少维护成本: 新增关联类型时无需同步修改 YAML
- 向后兼容: 已有 navigation 配置不被覆盖 (检测到即跳过)

### ADR-002: SessionStorage vs LocalStorage

**决策**: 使用 SessionStorage

**理由**:
- 会话级生命周期: 关闭标签页自动清除，无残留风险
- 安全性: 不持久化到磁盘，适合临时导航状态
- 多标签隔离: 每个标签页有独立的 sessionStorage

### ADR-002: URL Query 参数传递导航上下文

**决策**: 使用 URL query 参数 (`_nav_*`) 而非路由 meta 或 Pinia store

**理由**:
- 可书签化/分享: URL 完整编码了导航来源
- 服务端渲染友好: SSR 可直接从 URL 读取
- 无需额外状态管理: 不依赖全局 store
- 命名空间隔离: `_nav_` 前缀避免与业务参数冲突

### ADR-003: 批量查询 vs 逐个查询

**决策**: 单次 API 合并多个源对象的关联查询

**理由**:
- 性能: N 个源对象只需 1 次 DB 查询 (而非 N 次)
- 一致性: 单次事务保证数据一致性
- 用户体验: 一次性获取去重结果 + 各源计数

---

## 14. 未来扩展方向

| 方向 | 描述 | 优先级 |
|------|------|--------|
| 弹窗内导航 | FR-009 完整实现: 关闭当前弹窗打开新弹窗 | P2 |
| 权限控制 | 基于 authorization 配置限制可导航的关联 | P2 |
| 导航历史 | 支持多级导航链 (A→B→C) 的面包屑 | P3 |
| 预取计数 | 选中对象后异步预取所有关联计数 | P2 |
| 快捷键 | Ctrl+K 打开导航搜索面板 | P3 |
