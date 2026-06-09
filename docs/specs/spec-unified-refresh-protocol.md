## 目录

1. [1. 背景与目标](#1-背景与目标)
2. [2. 需求类型概览](#2-需求类型概览)
3. [3. 功能需求](#3-功能需求)
4. [4. 非功能需求](#4-非功能需求)
5. [5. 外部接口需求](#5-外部接口需求)
6. [6. 过渡需求](#6-过渡需求)
7. [7. 约束与假设](#7-约束与假设)
8. [8. 优先级 & 里程碑建议](#8-优先级-里程碑建议)
9. [9. 变更 / 设计提案 (RFC)](#9-变更-设计提案-(rfc))
10. [10. 风险评估](#10-风险评估)
11. [附录 A：对标参考](#附录-a：对标参考)
12. [附录 B：TBD 列表](#附录-b：tbd-列表)

---
# Spec: 元数据驱动 MultiObjectPage 统一刷新协议 & 服务层收敛

> **状态**: Draft  
> **创建日期**: 2026-05-25  
> **作者**: AI Assistant  
> **对标参考**: TanStack Query, Apollo Client, Salesforce Lightning Data Service

---

## 1. 背景与目标

### 1.1 背景

架构数据管理页面（MultiObjectManagementPage）是元数据模型驱动的通用多对象管理页面，支持 product / version / domain / sub_domain / service_module / business_process 等任意 YAML 配置的对象类型。当前存在两大结构性缺陷：

1. **刷新链路松散**：对象的新增、编辑保存、删除、批量删除后，需要同时刷新三处 UI（列表、对象范围树、关系范围树）。但刷新逻辑散落在 5+ 个文件中，通过逐级 `emit`/`watch` 串联，任何一环断裂（如 `@saved` 未监听、`emit('refresh')` 遗漏）就导致部分区域不刷新。

2. **DetailPage 绕过服务层**：DetailPage 使用裸 `fetch()` 直接调用后端 API，绕过了 `boService` 的 `create()` / `update()` / `delete()`。boService 的「Mutation 后自动清除查询缓存」机制因此完全失效，导致刷新时命中脏缓存、UI 显示旧数据。

### 1.2 业务目标

- 任意 BO 对象的新增/编辑/删除/批量删除后，用户界面三区域（列表、对象范围树、关系范围树）**自动且可靠地**刷新。
- 新的对象类型接入 MultiObjectPage 时，**无需编写任何刷新代码**。
- 所有写操作统一经过 boService，根治缓存失效漏洞。

### 1.3 用户/涉众目标

| 角色 | 目标 |
|------|------|
| **架构数据管理员** | 修改数据后界面立即反映变更，不需手动点击刷新按钮 |
| **后续接入的任意 BO 类型** | 零配置自动获得刷新能力 |
| **开发者** | CRUD 后不再需要手动 `emit('refresh')` 和 `watch refreshTrigger` |

---

## 2. 需求类型概览

| 类型 | 适用 | 证据 |
|------|:---:|------|
| Business Requirements | ✅ | 多次迭代反馈"刷新不工作"，用户操作效率受损 |
| User / Stakeholder Requirements | ✅ | 架构数据管理员日常工作流 |
| Solution Requirements | ✅ | boService 收敛 + 刷新协议统一 |
| Functional Requirements | ✅ | 见第 3 节 FR-001 ~ FR-006 |
| Nonfunctional Requirements | ✅ | 见第 4 节 NFR-001 ~ NFR-004 |
| External Interface Requirements | ✅ | boService → REST API，见第 5 节 |
| Transition Requirements | ✅ | 向后兼容现有代码，见第 6 节 |

---

## 3. 功能需求

### FR-001: DetailPage CRUD 统一走 boService

- **描述**：DetailPage 的 `handleSave()`（CREATE/UPDATE）和 `handleDelete()` MUST 使用 `boService.create()` / `boService.update()` / `boService.delete()` 替代裸 `fetch()`。
- **涉及文件**：`src/components/common/DetailPage/DetailPage.vue`
  - `fetchData()` [L789-L795](file:///d:/filework/excel-to-diagram/src/components/common/DetailPage/DetailPage.vue#L789-L795) → 改用 `boService.read(objectType, id, { forceRefresh: true })`
  - `handleSave()` [L938-L947](file:///d:/filework/excel-to-diagram/src/components/common/DetailPage/DetailPage.vue#L938-L947) → 改用 `boService.create()` / `boService.update()`
  - `handleSave()` 刷新 [L964-L966](file:///d:/filework/excel-to-diagram/src/components/common/DetailPage/DetailPage.vue#L964-L966) → 改用 `boService.read(objectType, id, { forceRefresh: true })`
  - `handleDelete()` [L1006-L1012](file:///d:/filework/excel-to-diagram/src/components/common/DetailPage/DetailPage.vue#L1006-L1012) → 改用 `boService.delete()`
- **验收标准**：
  - [ ] DetailPage 不再包含任何 `fetch('/api/v2/bo/...')` 调用
  - [ ] 创建/更新/删除成功后，boService 内部自动清除该 objectType 的 list 和 read 缓存
  - [ ] `fetchData()` 读取最新数据（含 computed fields）
- **优先级**：Must
- **类型映射**：Solution / Functional
- **来源**：代码分析 + 用户反馈

### FR-002: 统一刷新协调器 `useRefreshCoordinator`

- **描述**：创建 `useRefreshCoordinator` Composable，提供以下接口：
  - `register(key, fn)`: 注册刷新回调
  - `unregister(key)`: 注销刷新回调
  - `refreshAll()`: 依次执行所有已注册的回调，失败项静默 catch 并 console.error
- **设计原则**：
  - **对标 TanStack Query**：Mutation 成功后按"数据域"（objectType）失效缓存，不关心"哪些组件需要刷新"
  - **对标 Apollo Client**：显式声明 Mutation 影响哪些资源，正规划缓存 + 定向驱逐
  - **对标 Salesforce LDS**：缓存共享 + 变更广播，组件无需手动 emit
- **注册 key 约定**：使用唯一 key 避免多 tab 实例冲突
  - 列表：`list:${objectType}`（如 `list:sub_domain`）
  - 范围树：`scopeTree`
- **涉及文件**：新建 `src/composables/useRefreshCoordinator.js`
- **验收标准**：
  - [ ] MetaListPage automatically registers with key=`list:${objectType}`, fn=`forceRefresh`
  - [ ] RelationScopeTree automatically registers with key=`scopeTree`, fn=`refresh`
  - [ ] boService create/update/delete 成功后 automatically calls `refreshAll()`
  - [ ] `refreshAll()` defensively skips unregistered keys (no error)
- **优先级**：Must
- **类型映射**：Solution / Functional
- **来源**：代码分析 + TanStack Query 对标设计

### FR-003: boService 缓存失效增强 & 协调器绑定

- **描述**：boService 新增能力：
  - `setRefreshCoordinator(coordinator)`: 绑定协调器实例
  - `clearListCache(objectType)`: 按 objectType 前缀清除 list 查询缓存
  - `clearReadCache(objectType, id)`: 清除单条 read 缓存
  - `read()` 方法新增 `forceRefresh` 参数，绕开缓存直接请求
  - `create()` / `update()` / `delete()` 成功后: `clearCache → coordinator.refreshAll()`
- **涉及文件**：
  - `src/services/boService.js` — 新增方法
  - `src/services/baseService.js` — 已有 `_clearCache()` [L40-L42](file:///d:/filework/excel-to-diagram/src/services/baseService.js#L40-L42)
- **验收标准**：
  - [ ] 保存后 DetailPage 重新 fetchData 获取最新数据
  - [ ] 不再出现 `📦 缓存命中` 导致 UI 显示旧数据
  - [ ] 无 coordinator 绑定时，boService 仍正常清除自身缓存（不会 crash）
- **优先级**：Must
- **类型映射**：Solution / Functional
- **来源**：代码分析（boService.js L50 缓存日志）

### FR-004: 移除散列的 emit/watch 刷新路径

- **描述**：统一由 FR-002 协调器接管后，移除以下分散的刷新代码：
  - MetaListPage: `handleDetailCreated()/Saved()/Delete()` 和 `executeDelete()` 中的 `emit('refresh')`
  - MetaListPage: `handleBatchActionWrapper()` 函数
  - MetaListPage: `emit` 定义中的 `'refresh'` 事件
  - MultiObjectManagementPage: `@refresh="handleDataChange"` 监听
  - MultiObjectManagementPage: `handleDataChange()` 函数
  - MultiObjectManagementPage: `watch(() => page.refreshTrigger, ...)`
  - useMultiObjectPage: `refreshTrigger` 定义及 `handleGlobalAction` / `handleImportSuccess` 中的递增逻辑（改为调用 `coordinator.refreshAll()`）
- **涉及文件**：
  - [MetaListPage.vue#L1197-L1232](file:///d:/filework/excel-to-diagram/src/components/common/MetaListPage/MetaListPage.vue#L1197-L1232)
  - [MetaListPage.vue#L711-L716](file:///d:/filework/excel-to-diagram/src/components/common/MetaListPage/MetaListPage.vue#L711-L716)
  - [MultiObjectManagementPage.vue#L311-L322](file:///d:/filework/excel-to-diagram/src/components/common/MultiObjectManagementPage/MultiObjectManagementPage.vue#L311-L322)
  - [MultiObjectManagementPage.vue#L344-L353](file:///d:/filework/excel-to-diagram/src/components/common/MultiObjectManagementPage/MultiObjectManagementPage.vue#L344-L353)
  - [useMultiObjectPage.js#L527](file:///d:/filework/excel-to-diagram/src/composables/useMultiObjectPage.js#L527)
  - [useMultiObjectPage.js#L635-L637](file:///d:/filework/excel-to-diagram/src/composables/useMultiObjectPage.js#L635-L637)
- **验收标准**：
  - [ ] 创建/编辑/删除后，列表 + 对象范围 + 关系范围全部自动刷新
  - [ ] 工具栏刷新按钮 → `coordinator.refreshAll()`
  - [ ] 导入成功 → `coordinator.refreshAll()`
  - [ ] 批量删除 → `coordinator.refreshAll()`
- **优先级**：Should
- **类型映射**：Functional
- **来源**：代码分析 + 用户反馈

### FR-005: 批量删除纳入统一刷新

- **描述**：`useMetaList` 中的 `handleBatchAction` 批量删除/批量操作成功后，自动触发刷新协调器。
- **涉及文件**：
  - `src/composables/useMetaList.js` — `handleBatchAction()` 成功后调用注入的 coordinator
- **验收标准**：
  - [ ] 批量删除 N 条记录后，列表自动刷新显示减少 N 条
  - [ ] 对象范围树和关系范围树同步刷新
- **优先级**：Must
- **类型映射**：Functional
- **来源**：用户反馈 "批量删除没有刷新 对象范围，关系范围"

### FR-006: 工具栏刷新按钮接入协调器

- **描述**：工具条刷新按钮 → `handleGlobalAction('refresh')` → 改为调用 `coordinator.refreshAll()` 而非递增 `refreshTrigger`。
- **涉及文件**：
  - `src/composables/useMultiObjectPage.js` — `handleGlobalAction()` 方法
- **验收标准**：
  - [ ] 点击刷新按钮后，列表 + 对象范围 + 关系范围三处全部刷新
  - [ ] 刷新过程中不出现 500 错误（如果 relationships 后端接口健康）
- **优先级**：Must
- **类型映射**：Functional
- **来源**：代码分析 + 用户反馈

---

## 4. 非功能需求

### NFR-001: 可靠性

- **描述**：Mutation 后必须清除缓存并刷新全部已注册的回调，不允许静默跳过。
- **测量**：E2E 测试覆盖 CRUD → 验证 UI 数据一致性（数据条数、内容匹配）
- **优先级**：Must

### NFR-002: 通用性

- **描述**：任意 YAML meta 对象接入 MultiObjectPage 时，不应编写任何刷新代码。
- **测量**：新增一个 `_template.yaml` 对象类型 → 配置路由 → 页面自动具备完整刷新能力。
- **优先级**：Must

### NFR-003: 可追溯性（Observability）

- **描述**：每一步刷新操作有 console.log 级别的日志轨迹，格式：`[coordinator] refreshAll → list:sub_domain`, `[boService] clearListCache(sub_domain)`。
- **测量**：控制台日志可在 DevTools 中完整追踪 mutation → clearCache → refreshAll → 各回调执行。
- **优先级**：Should

### NFR-004: 回滚安全

- **描述**：修改不涉及后端 API 变更，纯前端重构。如果出现未覆盖的边界 case，可立即回滚到当前 commit。
- **测量**：单一 commit 粒度，`git revert` 不影响后端。
- **优先级**：Must

---

## 5. 外部接口需求

### IF-001: boService R/W API（不变更端点，仅替换调用方）

| 方法 | 端点 | 变更 |
|------|------|------|
| `create(objectType, data)` | `POST /api/v2/bo/{objectType}` | 已有，内部增加 `coordinator.refreshAll()` 调用 |
| `update(objectType, id, data)` | `PUT /api/v2/bo/{objectType}/{id}` | 已有，内部增加 `coordinator.refreshAll()` 调用 |
| `delete(objectType, id)` | `DELETE /api/v2/bo/{objectType}/{id}` | 已有，内部增加 `coordinator.refreshAll()` 调用 |
| `read(objectType, id, opts)` | `GET /api/v2/bo/{objectType}/{id}` | 已有，新增 `opts.forceRefresh` 参数 |

### IF-002: 不新增后端端点，不改变后端 API schema

---

## 6. 过渡需求

### TR-001: 向后兼容

- **描述**：现有所有 MultiObjectPage 使用场景（`/system/archdata` 及其他产品线）不破坏。
- **策略**：分步实施，每步独立可验证。新旧代码可共存一期，确认稳定后清理旧路径。
- **回滚方案**：单一 commit 纯前端改动，`git revert` 即刻恢复。

---

## 7. 约束与假设

### 7.1 技术约束

- 项目基于 **Vue 3 + Composition API + Element Plus**
- boService 继承自 BaseService，使用 LRU 缓存
- 不使用 Vuex/Pinia 之外的第三方状态管理库

### 7.2 业务约束

- 不影响现有 YAML 元数据驱动机制
- 不改变后端 API 端点和 schema

### 7.3 假设

| 假设 | 验证状态 |
|------|---------|
| boService 单例在所有页面生命周期内存在 | ✅ 已验证 — 模块级单例 |
| `el-table` `:key` 强制重建方案稳定 | ✅ 已验证 — forceRefresh + tableKey 方案已生效 |
| `useRefreshCoordinator` 仅 MOMP 页面需要，独立 ObjectPage 仍走自身数据流 | ⚠️ 假设 — 低风险，独立页不受影响 |

---

## 8. 优先级 & 里程碑建议

| ID | 需求 | 优先级 | 里程碑 | 原因 |
|----|------|--------|--------|------|
| FR-003 | boService 缓存失效增强 + 协调器绑定 | Must | M1 | 当前最大 bug 根源 |
| FR-001 | DetailPage 收敛到 boService | Must | M1 | 架构逃逸，根因层 |
| FR-002 | 统一刷新协调器 | Must | M2 | 消灭散列代码 |
| FR-005 | 批量删除纳入统一刷新 | Must | M2 | 用户已反馈 |
| FR-006 | 刷新按钮接入协调器 | Must | M2 | 用户已反馈 |
| FR-004 | 移除散列 emit/watch 路径 | Should | M3 | 清理冗余 |

**里程碑概览**：

| 里程碑 | 范围 | 可验证的标准 |
|--------|------|-------------|
| **M1**: Service Layer Convergence | FR-001 + FR-003 | DetailPage 保存后不再出现 `📦 缓存命中`；fetchData 返回最新数据 |
| **M2**: Coordinator Integration | FR-002 + FR-005 + FR-006 | 新建/编辑/删除/批量删除/刷新按钮 → 三处 UI 全部自动刷新 |
| **M3**: Legacy Cleanup | FR-004 | 无冗余 emit/watch 路径；代码更简洁 |

---

## 9. 变更 / 设计提案 (RFC)

### 9.1 As-Is 现状分析

```
┌────────────────────── 当前架构（问题版） ──────────────────────┐
│                                                                │
│  DetailPage ── fetch() ──► /api/v2/bo/*  （绕过 boService）    │
│      │                                                         │
│      └─ emit('saved') ──► MetaListPage                        │
│                              │                                 │
│                              └─ emit('refresh') ──► MOMP       │
│                                                      │         │
│                          ┌───────────────────────────┤         │
│                          ▼                           ▼         │
│                 metaListPageRef             scopeTreeRef       │
│                 .refresh()                 .refresh()          │
│                     │                           │              │
│                     ▼                           ▼              │
│              useMetaList.refresh()     RelationScopeTree       │
│                  │                     .refresh()               │
│                  ▼                          │                  │
│             boService.query()       ┌───────┴───────┐          │
│             （命中脏缓存!）          ▼               ▼         │
│                           objectScope        relationScope     │
│                           .loadTreeData()    .loadRelationships│
│                             ↑ 也命中脏缓存                     │
│                                                                │
│  ❌ 问题①：fetch() 绕过 boService → 缓存永远不失效             │
│  ❌ 问题②：5层 emit 链 → 任意一环断裂 = 局部不刷新             │
│  ❌ 问题③：没有统一的刷新触发源                                │
└────────────────────────────────────────────────────────────────┘
```

**当前痛点清单（基于 2026-05-25 实际调试）**：

| # | 痛点 | 定位 |
|---|------|------|
| 1 | `scopeTreeRef.loadRawRelationships()` 方法不存在 | [MultiObjectManagementPage.vue#L336](file:///d:/filework/excel-to-diagram/src/components/common/MultiObjectManagementPage/MultiObjectManagementPage.vue#L336) |
| 2 | `@saved` 事件未被监听 | [MetaListPage.vue#L440](file:///d:/filework/excel-to-diagram/src/components/common/MetaListPage/MetaListPage.vue#L440) |
| 3 | CURD 操作缺少 `emit('refresh')` | [MetaListPage.vue#L1195-L1232](file:///d:/filework/excel-to-diagram/src/components/common/MetaListPage/MetaListPage.vue#L1195-L1232) |
| 4 | `el-table` 固定高度 + 数据变更 ≠ 重绘 | 需 `:key` 强制重建 |
| 5 | boService 缓存未失效 → 脏数据 | `📦 缓存命中: sub_domain query` |
| 6 | DetailPage 裸 `fetch()` 绕过 boService | [DetailPage.vue#L938-L947](file:///d:/filework/excel-to-diagram/src/components/common/DetailPage/DetailPage.vue#L938-L947) |

### 9.2 目标架构

```
┌──────────────────────── 目标架构 ────────────────────────┐
│                                                           │
│  DetailPage                                               │
│      │                                                    │
│      ├─ handleSave()   → boService.create/update          │
│      ├─ handleDelete() → boService.delete                 │
│      └─ fetchData()    → boService.read(id,{forceRefresh})│
│                              │                             │
│  boService（单例）           │                             │
│      │                       │                             │
│      ├─ clearListCache(objectType) ←─────────────────────  │
│      ├─ clearReadCache(objectType, id)                    │
│      └─ coordinator.refreshAll()  ←─── 统一触发点          │
│              │                                             │
│  useRefreshCoordinator (provide/inject)                   │
│      │                                                     │
│      ├─ register('list:sub_domain')    → forceRefresh()   │
│      ├─ register('list:domain')        → forceRefresh()   │
│      └─ register('scopeTree')          → refresh()        │
│              │                                             │
│              └─ refresh() {                                │
│                   objectScopeRef.loadTreeData()            │
│                   relationScopeRef.loadRelationships()     │
│                 }                                          │
│                                                           │
│  触发点一览：                                              │
│  ✅ DetailPage handleSave → boService.mutation → refreshAll│
│  ✅ DetailPage handleDelete → boService.mutation → same    │
│  ✅ MetaListPage batchDelete → coordinator.refreshAll()    │
│  ✅ 工具条刷新按钮 → coordinator.refreshAll()              │
│  ✅ 导入成功 → coordinator.refreshAll()                    │
└───────────────────────────────────────────────────────────┘
```

### 9.3 详细设计

#### 9.3.1 `useRefreshCoordinator` — 核心 Composable

**文件位置**：新建 `src/composables/useRefreshCoordinator.js`

```javascript
/**
 * useRefreshCoordinator — 统一刷新协调器
 *
 * 对标 TanStack Query 的 invalidateQueries 模式:
 *   Mutation 成功后，按"数据域"通知所有注册的回调进行刷新。
 *   组件不关心"谁触发了刷新"，只关心"我注册的回调有没有被执行"。
 *
 * 对标 Salesforce LDS 的 getRecordNotifyChange 模式:
 *   缓存共享 + 变更广播，组件通过 register 声明依赖。
 *
 * Usage:
 *   const coordinator = useRefreshCoordinator()
 *   provide('refreshCoordinator', coordinator)
 *
 *   // 子组件中
 *   const coordinator = inject('refreshCoordinator')
 *   onMounted(() => coordinator.register('list:sub_domain', forceRefresh))
 *   onUnmounted(() => coordinator.unregister('list:sub_domain'))
 */
export function useRefreshCoordinator() {
  const callbacks = new Map()
  const isRefreshing = ref(false)

  /**
   * 注册刷新回调
   * @param {string} key - 唯一标识，推荐格式 'list:{objectType}' 或 'scopeTree'
   * @param {Function} fn - 异步或同步回调函数
   */
  function register(key, fn) {
    callbacks.set(key, fn)
  }

  /**
   * 注销刷新回调
   * @param {string} key
   */
  function unregister(key) {
    callbacks.delete(key)
  }

  /**
   * 执行全部已注册的回调
   * 失败项不阻断后续回调，通过 console.error 报告
   */
  async function refreshAll() {
    if (callbacks.size === 0) return

    isRefreshing.value = true
    const entries = Array.from(callbacks.entries())
    for (const [key, fn] of entries) {
      try {
        await fn()
      } catch (e) {
        console.error(`[coordinator] refresh failed for "${key}":`, e)
      }
    }
    isRefreshing.value = false
  }

  return { register, unregister, refreshAll, isRefreshing }
}
```

#### 9.3.2 boService 改造

**文件**：`src/services/boService.js`

新增内容：

```javascript
// === 协调器绑定 ===
let _coordinator = null

/**
 * @param {object} coordinator - useRefreshCoordinator() 的返回值
 */
export function setRefreshCoordinator(coordinator) {
  _coordinator = coordinator
}

// === create / update / delete 增强 ===
async create(objectType, data) {
  const response = await fetch(`${this.API_BASE_V2}/bo/${objectType}`, {
    method: 'POST',
    headers: this._getHeaders(),
    body: JSON.stringify(data)
  })
  const result = await this._handleResponse(response)
  if (result.success) {
    // 1. 清除 list 缓存（前缀匹配）
    service._clearCache(objectType)
    // 2. 通知所有注册的回调刷新
    _coordinator?.refreshAll()
  }
  return result
}
// update / delete 同理

// === read 增加 forceRefresh ===
/**
 * @param {string} objectType
 * @param {number|string} id
 * @param {object} options
 * @param {boolean} [options.forceRefresh=false]
 */
async read(objectType, id, options = {}) {
  const cacheKey = this._getCacheKey(objectType, 'read', id)

  if (!options.forceRefresh) {
    const cached = this._getCached(cacheKey)
    if (cached) return cached
  }

  // ... existing fetch logic ...
  // 成功后 setCache
}
```

#### 9.3.3 DetailPage 改造

**文件**：`src/components/common/DetailPage/DetailPage.vue`

```javascript
// handleSave() 当前 (L938-L947)
const response = await fetch(url, { method, headers, body: JSON.stringify(payload) })
const result = await response.json()
// → 改为 →
const result = isCreate
  ? await boService.create(props.objectType, payload)
  : await boService.update(props.objectType, props.id, payload)

// fetchData() 当前 (L789-L795)
const response = await fetch(`/api/v2/bo/${props.objectType}/${props.id}`, { headers })
// → 改为 →
const result = await boService.read(props.objectType, props.id, { forceRefresh: true })
if (result.success) {
  data.value = result.data
}

// handleDelete() 当前 (L1006-L1013)
const response = await fetch(`/api/v2/bo/${props.objectType}/${props.id}`, { method: 'DELETE', ... })
// → 改为 →
const result = await boService.delete(props.objectType, props.id)
```

#### 9.3.4 MultiObjectManagementPage 绑定协调器

**文件**：`src/components/common/MultiObjectManagementPage/MultiObjectManagementPage.vue`

```javascript
// setup() 中新增
import { useRefreshCoordinator } from '@/composables/useRefreshCoordinator'
import { setRefreshCoordinator } from '@/services/boService'

const coordinator = useRefreshCoordinator()
provide('refreshCoordinator', coordinator)
setRefreshCoordinator(coordinator)
```

#### 9.3.5 MetaListPage 注册回调

**文件**：`src/components/common/MetaListPage/MetaListPage.vue`

```javascript
import { inject, onMounted, onUnmounted } from 'vue'

const coordinator = inject('refreshCoordinator')

onMounted(() => {
  coordinator.register(`list:${props.objectType}`, forceRefresh)
})

onUnmounted(() => {
  coordinator.unregister(`list:${props.objectType}`)
})
```

#### 9.3.6 RelationScopeTree 注册回调

**文件**：`src/components/common/RelationScopeTree/RelationScopeTree.vue`

```javascript
import { inject, onMounted, onUnmounted } from 'vue'

const coordinator = inject('refreshCoordinator')

onMounted(() => {
  coordinator.register('scopeTree', refresh)
})

onUnmounted(() => {
  coordinator.unregister('scopeTree')
})
```

#### 9.3.7 useMultiObjectPage 改造

**文件**：`src/composables/useMultiObjectPage.js`

```javascript
// handleGlobalAction 中 refresh case:
case 'refresh':
  _coordinator?.refreshAll()  // 改为调用协调器
  break

// handleImportSuccess:
function handleImportSuccess() {
  importDialogVisible.value = false
  _coordinator?.refreshAll()  // 改为调用协调器
}
```

#### 9.3.8 清理清单

移除以下代码（由协调器接管后不再需要）：

| 文件 | 行号 | 移除内容 |
|------|------|---------|
| MetaListPage.vue | ~L1197-L1232 | handleDetailCreated/Saved/Delete 中的 `emit('refresh')` |
| MetaListPage.vue | ~L711-L716 | `handleBatchActionWrapper()` 函数定义 |
| MetaListPage.vue | ~L600 | `defineEmits` 中的 `'refresh'` |
| MetaListPage.vue | ~L82 | `@click="handleBatchActionWrapper(action)"` → 恢复为 `@click="handleBatchAction(action)"` |
| MultiObjectManagementPage.vue | ~L60 | `@refresh="handleDataChange"` |
| MultiObjectManagementPage.vue | ~L311-L322 | `handleDataChange()` 函数 |
| MultiObjectManagementPage.vue | ~L344-L353 | `watch(() => page.refreshTrigger, ...)` |

### 9.4 备选方案

| 方案 | 优点 | 缺点 | 决策 |
|------|------|------|:---:|
| **A: provide/inject + useRefreshCoordinator** | 作用域明确、不外泄；利用 Vue 组件树生命周期；简单可靠 | 需 MOMP 显式 provide | ✅ **选定** |
| B: EventBus（mitt） | 完全解耦，全局可达 | 无法限制作用域，易意外广播；需手动解绑 | ❌ |
| C: Pinia store | 有 devtools 支持，标准化 | 项目未使用 Pinia；对简单场景过度设计 | ❌ |
| D: 仅增强 boService 缓存清除 | 改动最小 | 仍需要 emit 链传递刷新到 UI 层 | ❌ |

**选择方案 A 的理由**：
- 与 Vue 组件树生命周期天然对齐（注册/注销与组件挂载/卸载同步）
- 对标 TanStack Query 的 QueryClient（provider 模式）
- 对标 Salesforce LDS 的 shared cache + notify 模式
- 不引入新的依赖，纯 Composition API 即可实现

### 9.5 实施与迁移计划

| 步骤 | 内容 | 预估影响 | 风险 |
|------|------|---------|------|
| **1** | 新建 `useRefreshCoordinator.js` | 纯新增文件 | 🟢 低 |
| **2** | boService: `setRefreshCoordinator()` + `clearReadCache()` + `read()` forceRefresh + mutation 后 refreshAll | 修改核心服务 | 🟡 中 |
| **3** | DetailPage: 用 boService.create/update/delete/read 替代裸 fetch() | 修改核心业务组件 | 🔴 高 |
| **4** | MOMP: 创建协调器 → provide → 绑定 boService | 修改外壳页面 | 🟡 中 |
| **5** | MetaListPage: inject 协调器 → register/unregister | 修改核心组件 | 🟡 中 |
| **6** | RelationScopeTree: inject 协调器 → register/unregister | 修改范围树组件 | 🟡 中 |
| **7** | useMultiObjectPage: refresh case → coordinator.refreshAll() | 修改 Composable | 🟢 低 |
| **8** | 移除旧的 emit/watch 清理代码 | 删除已迁移代码 | 🟢 低 |
| **9** | E2E 测试全量回归 | 验证 | 🟢 低 |

### 9.6 测试策略

| 测试层级 | 覆盖范围 | 工具 |
|---------|---------|------|
| Unit | `useRefreshCoordinator`: register/unregister/refreshAll/错误隔离 | Vitest |
| Unit | boService: mutation → cache clear + refreshAll 调用 | Vitest + mock |
| Integration | DetailPage 保存 → boService → coordinator → 列表刷新 | Playwright |
| E2E | 完整 CRUD 流程 + 批量删除 + 刷新按钮 | Playwright（现有 `e2e/features/arch-data-crud.spec.js`） |

---

## 10. 风险评估

### 🔴 高风险

| 风险 | 触发条件 | 影响 | 缓解措施 |
|------|---------|------|---------|
| **DetailPage fetch → boService 返回值格式不一致** | boService._handleResponse 与 DetailPage 的裸 response.json() 解析逻辑不同 | 数据解析失败或字段丢失 | 逐字段对比两端 response 处理差异；先做并行对比测试 |
| **DetailPage payload 构建与 boService.create 的参数不匹配** | DetailPage 去掉了 `_name`/`_label`/`can_delete` 后再发送，boService 可能期望不同结构 | 后端校验失败 | 保留 DetailPage 的 payload 构建逻辑，仅替换 `fetch()` → `boService.create(payload)` |

### 🟡 中风险

| 风险 | 触发条件 | 影响 | 缓解措施 |
|------|---------|------|---------|
| **协调器生命周期与组件不同步** | tab 切换时 MetaListPage 因 `:key="page.activeTab"` 重新挂载 | 旧 tab 的回调被 unregister，新 tab 未 register 时有间隙 | `onMounted` 注册 + `onUnmounted` 注销，利用 Vue 生命周期天然同步 |
| **`list:sub_domain` 被旧组件 unregister** | tab 切换 → 旧组件 onUnmounted 删除 key → 新组件尚未 onMounted | 刷新丢失 | 使用唯一 key `list:${objectType}` 而非固定 `'list'`（**已确认** ✅） |
| **boService 单例的 coordinator 引用被覆盖** | 多个 MOMP 实例创建时调用 `setRefreshCoordinator()` | 引用覆盖可能导致旧绑定失效 | 允许覆盖（最新 MOMP 唯一活跃），与页面生命周期一致 |
| **DetailPage read 缓存与 forceRefresh** | 保存后 re-fetchData 走缓存可能返回旧 computed fields | 保存后界面显示旧数据 | 已通过 `{ forceRefresh: true }` 参数绕开缓存 |

### 🟢 低风险

| 风险 | 触发条件 | 影响 | 缓解措施 |
|------|---------|------|---------|
| `el-table :key` 强制重建导致选中状态丢失 | 刷新时 tableKey++ | 选中行被清空 | 现有 `watch(data)` 中有选中恢复逻辑，保留 |
| 工具条刷新按钮不走 refreshTrigger | 调用 `coordinator.refreshAll()` 替代 | 无影响，行为一致 | 同路径 |
| coordinator 未 inject（独立页面场景） | MetaListPage inject 时找不到 provide | TypeError | 使用 `inject('refreshCoordinator', null)` 提供默认值 |

---

## 附录 A：对标参考

### A.1 TanStack Query (React Query)

```typescript
const mutation = useMutation({
  mutationFn: updateUser,
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['users'] })
    // 所有 useQuery(['users', ...]) 的组件自动 refetch
  }
})
```

**核心洞见**：不关心"哪些组件"，只声明"哪些数据过期"。查询侧自动感知。

### A.2 Apollo Client

```javascript
const [updateUser] = useMutation(UPDATE_USER, {
  refetchQueries: ['GetUsers', 'GetUserDetail']
})

// 或细粒度驱逐
cache.evict({ id: `User:${userId}` })
cache.gc()
```

**核心洞见**：正规划缓存 + 显式声明 Mutation 影响哪些 Query。

### A.3 Salesforce Lightning Data Service (LDS)

```javascript
import { getRecordNotifyChange } from 'lightning/uiRecordApi'
getRecordNotifyChange([{ recordId: '0xXxx...' }])
// 所有 @wire 到相同 record 的组件自动收到新数据
```

**核心洞见**：缓存共享 + 变更广播。组件无需手动 emit，框架层面解决同步。

### A.4 我们的方案对标

| 维度 | TanStack | Apollo | Salesforce LDS | **本项目** |
|------|:---:|:---:|:---:|:---:|
| 缓存失效触发 | `invalidateQueries(queryKey)` | `refetchQueries` / `cache.evict` | `getRecordNotifyChange(recordId)` | **`clearListCache(objectType)` + `coordinator.refreshAll()`** |
| 刷新作用域 | queryKey 层级 | Query name | recordId 粒度 | **objectType 层级 + 全局 scopeTree** |
| 写操作入口 | `useMutation` | `useMutation` | `uiRecordApi` | **`boService.create/update/delete`** |
| 消费者声明方式 | `useQuery(queryKey)` | `useQuery(QUERY)` | `@wire(adapter)` | **`coordinator.register(key, fn)`** |
| 服务层保障 | QueryClient 单例 | ApolloClient 单例 | LDS framework | **boService 单例** |

---

## 附录 B：TBD 列表

| ID | 项目 | 状态 | 决策 |
|----|------|------|------|
| TBD-1 | `clearListCache` 和 `clearReadCache` 的清除粒度 | ✅ 已确认 | `clearListCache` 用 `deleteByPrefix('${objectType}:')`；`clearReadCache` 用 `deleteByPrefix('${objectType}:read:')` |
| TBD-2 | ObjectScope 和 RelationScope 树的数据获取是否有缓存 | ✅ 已确认 | 都走 boService.query → 协调器刷新后自动清除相关缓存 |
| TBD-3 | Multi-tab 场景下 MetaListPage 回调 key 唯一性 | ✅ 已确认 | **key=`list:${objectType}`**，如 `list:sub_domain` |
| TBD-4 | 独立页面（非MOMP）的兼容性 | ⚠️ 待验证 | inject 时提供 `null` 默认值，boService mutation 后检查 `_coordinator` 存在性 |

---

> **Spec 完整性自检**: ✅ 10 sections, 最后 section 为 "附录 B：TBD 列表", 内容完整。
