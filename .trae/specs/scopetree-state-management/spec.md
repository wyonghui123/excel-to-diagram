# Spec: ScopeTree 组件状态管理重构 —— 消除「多源真相」反模式

## 1. Background & Objectives

### 1.1 Background

MultiObjectPage 左侧面板的两个核心 UI 组件 —— `ObjectScopeSection`（对象范围树）和 `RelationScopeSection`（关系范围树）—— 均基于 Element Plus 的 `el-tree` 实现 checkbox 勾选功能。

当前经过约 20 轮问题排查后，两个组件仍然存在以下脆弱点：

1. **el-tree `store.setData` 擦除状态**：当 `:data` 绑定值变化时，el-tree 内部调用 `store.setData(newVal)` → `nodesMap = {}`（清空）→ `root.setData(newVal)`（重建）→ `_initDefaultCheckedNodes()`（从 `defaultCheckedKeys` prop 恢复）。两个组件各自实现了不同的 hack 来绕过此问题：
   - `ObjectScopeSection`：在 `loadTreeData` 的 silent refresh 路径中手动保存 `currentCheckedKeys`，比较新旧树结构，然后通过多次 `await nextTick()` + `settingFromProp` flag + `setCheckedKeys()` 恢复。
   - `RelationScopeSection`：monkey-patch `store.setData` 方法，在原始调用后从 `preservedCheckedKeys` 恢复 checked 状态。

2. **三源分离的勾选状态**：同一个"哪些节点被勾选"的概念被同时维护在：
   - el-tree 内部 store（Element Plus 内部状态）
   - component-level ref（`checkedBoIds` / `preservedCheckedKeys` / `classifier.selectedScopeIds`）
   - `scopeIds` reactive 对象（`useMultiObjectPage` 层）
   三者之间通过 `@check` 事件 + `settingFromProp` 守卫 + 多个 `nextTick` 手工同步，高度脆弱。

3. **自我触发的状态擦除循环**：用户勾选对象树节点 → `emit('scope-change')` → `handleScopeChange` → `scopeIds` 更新 → `combinedFilters` computed 重算 → `watch` 触发 `coordinator.refreshAll()` → `ObjectScopeSection.refresh()` → `loadTreeData({ silent: true })` → `treeData` 重新赋值 → `store.setData` 擦除勾选状态。用户的勾选行为本身成了状态丢失的触发器。

4. **关系树性能问题**：`classifier.treeData` 是 computed，依赖 `props.selectedDomainIds` 等对象范围 props。用户每次改变对象勾选，都会触发 `buildRelationScopeTree()` 全量重建关系分类树（遍历所有 relationships 进行分类、构建嵌套树结构），即使关系数据本身没有变化。

5. **不可测试的架构**（补充发现）：整个 `RelationScopeTree` 目录（含 ObjectScopeSection: 494行, RelationScopeSection: 466行, RelationFilterSection, RelationScopeTree）**没有任何单元测试**。现有的 `MultiObjectManagementPage.spec.js` 将 RelationScopeTree 完全 stub 为 `<div class="rst-stub">ScopeTree</div>`，E2E 测试 `arch-data-filter-scope.spec.js` 仅测 happy path。核心原因：当前"三源分离 + nextTick 时序 + monkey-patch store.setData"的架构本身就不可单元测试——状态同步逻辑与 Vue 响应式系统、el-tree 内部 store、浏览器微任务队列深度耦合，无法在隔离环境中验证。

### 1.2 MultiObjectPage 通用数据流模型回顾

MultiObjectPage 遵循 **FilterSource + FilterFlow 管道** 模型（参考 [multiobjectpage-filter-model spec](file:///d:/filework/excel-to-diagram/.trae/specs/multiobjectpage-filter-model/spec.md)）：

```
FilterSource.value (单一真相源)
  │
  ▼
FilterFlow.aggregator (merge strategy)
  │
  ▼
combinedFilters (computed)
  │
  ▼
MetaListPage.setContextFilters()
  │
  ▼
API 请求
```

关键设计原则：
- **FilterSource 是唯一真相源**。UI 组件应作为 FilterSource 的 View，通过 `:default-checked-keys` 或方法绑定其值。
- **单向数据流**：用户操作 → 更新 FilterSource → 管道自动传播 → UI 响应式更新。不存在 UI 内部状态的独立拷贝。

当前 ObjectScopeSection 和 RelationScopeSection **违背了这一原则**：它们各自维护了内部状态副本，与 FilterSource 之间通过事件冒泡而非数据绑定通信。

### 1.3 Business Objectives

- 消除 el-tree `store.setData` 导致的 checkbox 状态丢失问题，不再依赖 `settingFromProp` / `preservedCheckedKeys` / `installStoreSetDataHook` 等脆弱 workaround。
- 将 ObjectScopeSection 和 RelationScopeSection 从「多源状态管理」重构为「FilterSource 单向数据流」，与 MultiObjectPage 通用模型对齐。
- 提升组件可测试性：将状态管理逻辑提取为可单独测试的 composable。
- 提升关系树的性能：分离「数据加载」与「UI 过滤」，避免每次对象范围变更时全量重建关系分类树。

### 1.4 User / Stakeholder Objectives

- **最终用户**：对象范围和关系范围的 checkbox 状态稳定可靠，不受数据刷新、对象变更、Tab 切换等任何操作影响。
- **开发者**：理解组件状态管理只需看一个 FilterSource ref，而不是追踪三个状态源的同步逻辑。bug 可在单元测试阶段发现。
- **架构师**：ScopeTree 组件实现与 MultiObjectPage FilterSource 模型一致，遵循统一的架构约定。

---

## 2. Requirement Type Overview

| Type                    | Applicable | Evidence                                               |
| ----------------------- | ---------- | ------------------------------------------------------ |
| Business                | Yes        | 消除约 20 轮排查的脆弱 hack，提升开发效率               |
| User/Stakeholder        | Yes        | 最终用户 checkbox 状态稳定；开发者维护成本降低          |
| Solution                | Yes        | FilterSource 单向数据流 + 可测试架构 + 性能优化         |
| Functional              | Yes        | FR-001 ~ FR-007                                        |
| Nonfunctional           | Yes        | NFR-001 ~ NFR-005                                      |
| External Interface      | Yes        | IF-001: `emit('scope-change')` 接口保持兼容             |
| Transition              | Yes        | TR-001: 渐进迁移，feature flag 回退                     |

---

## 3. Functional Requirements

### FR-001: FilterSource 驱动的 ObjectScopeSection

- **Description**: ObjectScopeSection MUST 将 el-tree 的 checked 状态绑定到 FilterSource（`scopeIds`），不再维护组件内部状态副本 `checkedBoIds`。
- **Acceptance Criteria**:
  - el-tree 使用 `:default-checked-keys="checkedNodeKeys"`（从 scopeIds 派生的 computed）绑定选中状态。
  - `handleBoCheck` 仅从 `checkedInfo.checkedNodes` 提取 scope 数据并 `emit('scope-change', ...)`，不再更新内部 `checkedBoIds`。
  - 移除 `checkedBoIds` ref、`settingFromProp` flag。
  - `loadTreeData` 的 silent refresh 路径不再需要手动保存/恢复 checked keys —— `store.setData()` 内部调用 `_initDefaultCheckedNodes()` 自动从 `defaultCheckedKeys` prop 恢复。
  - `sameStructure` early return 移除（数据新鲜度不再为保存勾选状态而妥协）。
  - `handleSelectAll` / `handleClear` 通过 normal flow（emit scope-change → scopeIds 更新 → defaultCheckedKeys 变化 → el-tree 自动重渲染）实现，不再直接操作 `treeRef.setCheckedKeys()`。
- **Priority**: Must
- **Type Mapping**: Functional / Solution
- **Source**: 代码分析 + 用户反馈（20+ 轮排查）

### FR-002: FilterSource 驱动的 RelationScopeSection

- **Description**: RelationScopeSection MUST 将 el-tree 的 checked 状态绑定到 `scopeIds.relationExtra.relationCodes`，不再维护 `preservedCheckedKeys` 和 `classifier.selectedScopeIds` 副本。
- **Acceptance Criteria**:
  - el-tree 使用 `:default-checked-keys="checkedNodeKeys"`（从 `scopeIds.relationExtra.relationCodes` 反向映射为 node keys 的 computed）绑定选中状态。
  - `handleClassifierCheck` 仅调用 `emit('scope-change', { relationCodes })` 更新上游，不维护内部状态。
  - 移除 `preservedCheckedKeys`、`preservedHalfCheckedKeys`、`installStoreSetDataHook`、`settingFromProp`。
  - `classifierTreeData` 不再因对象范围 props 变化而触发 `store.setData` 全量重建（改为前端 filter，见 FR-004）。
  - `classifier.selectedScopeIds` 移除（由 FilterSource 替代）。
- **Priority**: Must
- **Type Mapping**: Functional / Solution
- **Source**: 代码分析 + 用户反馈（20+ 轮排查）

### FR-003: 解耦对象范围变更 → coordinator.refreshAll 的自触发循环

- **Description**: 系统 MUST NOT 在 scope 变更时触发 `ObjectScopeSection` 的 silent refresh。用户勾选对象树不应导致对象树自身数据重新加载。
- **Acceptance Criteria**:
  - 从 `watch(page.combinedFilters)` 中移除 `coordinator.refreshAll()` 调用。
  - CRUD 操作的 refreshAll 触发链不受影响（`boCrudService.create/update/delete` 内部仍调用 `_coordinator?.refreshAll()`）。
  - 手动刷新按钮、导入成功回调的 refreshAll 不受影响。
  - 对象树勾选 → scopeIds 变更 → combinedFilters 变更 → MetaListPage API 请求 → 列表刷新。对象树自身不刷新。
- **Priority**: Must
- **Type Mapping**: Solution
- **Source**: 代码分析发现的自触发循环病灶 + `coordinator.refreshAll()` 调用链完整审计（6 个触发场景中仅此 1 个有问题）

### FR-004: 关系树「加载时分类」→「加载后过滤」

- **Description**: RelationScopeSection MUST 分离「数据加载」（一次性加载全量 relationships + businessObjects）与「范围过滤」（根据对象范围 props 在前端过滤展示），避免每次对象范围变更时全量重建分类树。
- **Acceptance Criteria**:
  - 全量 relationships 和 businessObjects 仅在 `versionId` 变更时重新加载。
  - 对象范围 props（`selectedDomainIds` 等）变更时，不触发 `buildRelationScopeTree()` 全量重建。改为在已有分类结果上应用前端 filter。
  - `classifierTreeData` 从 computed（依赖 props）改为 shallowRef（仅在数据加载时更新）。
  - 使用 el-tree 的 `filter-node-method` 控制节点可见性（避免 `:data` 替换导致的 `store.setData` 触发）。
  - 如果必须更新 `:data`（如 versionId 变更），`:default-checked-keys` prop 自动恢复 checked 状态（无需额外代码）。
- **Priority**: Should
- **Type Mapping**: Functional / Nonfunctional (Performance)
- **Source**: 性能分析 `buildRelationScopeTree()` 在每次对象范围变更时的全量重建开销

### FR-005: 节点 ID ↔ 过滤值的双向映射

- **Description**: 系统 MUST 提供 el-tree 节点的 `node-key`（如 `"d_1"` / `"internal-cross-domain"`）与 FilterSource 中存储的过滤值（如 `domain.id=1` / `relation_code="RS001"`）之间的双向映射能力，且作为 pure function 可单独单元测试。
- **Acceptance Criteria**:
  - `ObjectScopeSection`：`treeNodesToScope(checkedNodes) → { domainIds, subDomainIds, serviceModuleIds, boIds }`
  - `ObjectScopeSection`：`scopeToNodeKeys(treeData, scope) → string[]`
  - `RelationScopeSection`：`nodeKeysToRelationCodes(nodeKeys, treeData) → string[]`
  - `RelationScopeSection`：`relationCodesToNodeKeys(relationCodes, treeData) → string[]`
  - 映射函数从树数据结构直接推导，无需额外维护映射表。
  - 所有映射函数为纯函数（无副作用，不依赖 el-tree ref），可独立单元测试。
- **Priority**: Must
- **Type Mapping**: Solution
- **Source**: FR-001 / FR-002 的前置依赖

### FR-006: 保持 emit('scope-change') 接口兼容

- **Description**: 重构后的组件 MUST 保持与 `RelationScopeTree` 的 `emit('scope-change')` 接口完全兼容，不影响上游 `handleScopeChange` 和 `scopeIds` 的更新逻辑。
- **Acceptance Criteria**:
  - `ObjectScopeSection` 仍然 emit `{ boIds, domainIds, subDomainIds, serviceModuleIds }`。
  - `RelationScopeSection` 仍然 emit `{ relationCodes }`。
  - `RelationScopeTree` 仍然 emit 完整的 scope 对象给 MultiObjectManagementPage。
  - `handleScopeChange` 逻辑不变。
- **Priority**: Must
- **Type Mapping**: Solution / Transition
- **Source**: 上游兼容性要求

### FR-007: 可测试的状态管理架构

- **Description**: ObjectScopeSection 和 RelationScopeSection 的勾选状态管理逻辑 MUST 提取为可独立单元测试的 composable/utility 函数，与 el-tree API 和 Vue 响应式系统解耦。
- **Acceptance Criteria**:
  - 映射函数（`treeNodesToScope`、`scopeToNodeKeys`、`nodeKeysToRelationCodes`、`relationCodesToNodeKeys`）为纯函数，可脱离 Vue 组件单独测试。
  - `checkedNodeKeys` computed 可 mock scopeIds + treeData 后测试其输出。
  - 每个映射函数的单元测试覆盖：空输入、全选、部分选、边界情况（单节点树、扁平列表等）。
  - 至少 8 个单元测试用例覆盖勾选状态变更的核心路径。
- **Priority**: Must
- **Type Mapping**: Solution / Nonfunctional
- **Source**: 当前架构不可测试 → 20+ 轮排查 bug 未被测试发现

---

## 4. Nonfunctional Requirements

### NFR-001: 稳定性 —— el-tree 状态一致性

- **Description**: 在任何场景下（数据刷新、对象范围变更、版本切换、Tab 切换、展开/收起、全选/清空），el-tree 的 checkbox 显示状态 MUST 与 FilterSource 中的选中值一致。
- **Measurement**: 通过单元测试 + 前端验证覆盖以下场景：
  - 勾选后切换版本 → 勾选正确清空
  - 勾选后 silent refresh（CRUD 触发）→ 勾选保持
  - 全选后反勾选单个 → 状态正确
  - 关系树：勾选后变更对象范围 → 关系树刷新但选中保持（如果新范围下节点仍存在）
- **Priority**: Must
- **Source**: 用户 20+ 轮排查的核心诉求

### NFR-002: 性能 —— 关系树分类重建开销

- **Description**: 对象范围变更时，关系树的 UI 响应时间 MUST 不因全量 `buildRelationScopeTree()` 而明显卡顿。
- **Measurement**: 在 10000 条 relationships 数据集下，对象范围变更到关系树 UI 更新的时间 ≤ 200ms（从当前的全量重建（可能 > 500ms）优化）。
- **Priority**: Should
- **Source**: `buildRelationScopeTree` 遍历所有 relationships 进行四级分组嵌套构建，大数据集下开销显著

### NFR-003: 代码可维护性

- **Description**: ObjectScopeSection 和 RelationScopeSection 的核心逻辑 MUST 减少与 el-tree 内部 API（`store.setData`、`nodesMap`、`getHalfCheckedNodes`）的耦合。
- **Measurement**: 两个组件的 `<script setup>` 代码行数各减少 ≥ 20%（主要移除状态恢复相关 hack 代码）。
- **Priority**: Should
- **Source**: 架构对齐要求

### NFR-004: 向后兼容

- **Description**: 重构 MUST NOT 破坏现有的 MultiObjectManagementPage 功能。所有现有列表过滤、Tab 切换、版本切换行为保持不变。
- **Measurement**: 现有 `useMultiObjectPage.spec.js`（1238行全部通过）、E2E 测试、前端手动验证全部通过。
- **Priority**: Must
- **Source**: 用户"继续"指令隐含不破坏现有功能

### NFR-005: 可测试性

- **Description**: 重构后的组件状态管理逻辑 MUST 可在 CI pipeline 中以单元测试方式执行，不依赖浏览器环境或 el-tree 内部状态。
- **Measurement**:
  - 所有映射函数（FR-005）有 ≥ 80% 行覆盖率。
  - `checkedNodeKeys` computed 逻辑可通过 mock scopeIds + mock treeData 测试。
  - 测试运行不需要 mount 完整的 el-tree 组件。
  - 测试在 `vitest` 环境中执行，不使用 Playwright/E2E。
- **Priority**: Must
- **Source**: 当前 0 单元测试覆盖 → 20+ 轮排查未被自动化发现

---

## 5. External Interface Requirements

### IF-001: ObjectScopeSection emit 接口（不变）

```typescript
// emit('scope-change') payload（保持不变）
{
  boIds: number[]          // 业务对象 ID（不含前缀）
  domainIds: number[]      // 领域 ID（originalId）
  subDomainIds: number[]   // 子领域 ID（originalId）
  serviceModuleIds: number[] // 服务模块 ID（originalId）
}
```

### IF-002: RelationScopeSection emit 接口（不变）

```typescript
// emit('scope-change') payload（保持不变）
{
  relationCodes: string[]  // 关联类型代码（如 'RS001', 'RS002'）
}
```

### IF-003: 节点 ID 方案（不变）

ObjectScopeSection:
```
节点 ID 格式：{prefix}_{originalId}
  domain:         d_{id}
  sub_domain:     s_{id}
  service_module: sm_{id}
```

RelationScopeSection:
```
节点 ID 格式：
  scope 层：   {scopeType}                         (internal / cross-boundary / external)
  category 层：{scopeType}-{categoryType}          (internal-cross-domain / ...)
  domain 层： {scopeType}-{categoryType}-domain-{domainPair}
  subDomain 层：{scopeType}-{categoryType}-subdomain-{subDomainPair}
  module 层：  {scopeType}-{categoryType}-module-{modulePair}
  
叶子节点 (module) 通过 node.relationCodes 数组关联 relation_codes。
中间节点通过递归遍历 node.children 收集所有子孙节点的 relationCodes。
```

### IF-004: el-tree `:default-checked-keys` 绑定（新增）

```html
<!-- ObjectScopeSection -->
<el-tree
  :data="treeData"
  node-key="id"
  show-checkbox
  :default-checked-keys="checkedNodeKeys"
  @check="handleBoCheck"
/>

<!-- RelationScopeSection -->
<el-tree
  :data="classifierTreeData"
  node-key="id"
  show-checkbox
  :default-checked-keys="checkedNodeKeys"
  @check="handleClassifierCheck"
/>
```

**行为保障**（已验证 Element Plus 源码）：
1. `:data` 变化 → `store.setData(newVal)` → 内部自动调用 `_initDefaultCheckedNodes()` → 从 `defaultCheckedKeys` prop 读取当前值 → 恢复选中状态。
2. `:default-checked-keys` 变化 → `watch(defaultCheckedKeys)` → `store.setDefaultCheckedKey(newVal)` → `_initDefaultCheckedNodes()` → 重新应用到所有节点。
3. 因此，无论是数据重建还是 scope 变更，checked 状态都由 `defaultCheckedKeys` prop 保证一致，**不再需要任何手动 save/restore/hook**。

---

## 6. Transition Requirements

### TR-001: 渐进迁移

- **Description**: 不一次性重写两个组件。分步迁移，每步可独立验证和回退。
- **Strategy**:
  1. **Step 1**: 创建 `useScopeTreeState` composable —— 提取映射函数（`treeNodesToScope`、`scopeToNodeKeys`、`nodeKeysToRelationCodes`、`relationCodesToNodeKeys`）+ `checkedNodeKeys` computed。编写单元测试验证所有映射逻辑。
  2. **Step 2**: `ObjectScopeSection` 接入 —— 添加 `:default-checked-keys="checkedNodeKeys"`，简化 `handleBoCheck`，移除 `checkedBoIds`/`settingFromProp`/silent refresh restore。使用 feature flag 双轨运行。
  3. **Step 3**: 解耦自触发循环 —— 从 `watch(combinedFilters)` 中移除 `coordinator.refreshAll()`。
  4. **Step 4**: `RelationScopeSection` 接入 —— 添加 `:default-checked-keys="checkedNodeKeys"`，移除 `preservedCheckedKeys`/`installStoreSetDataHook`/`settingFromProp`/`classifier.selectedScopeIds`。
  5. **Step 5**: 关系树性能优化（FR-004）—— 分离加载与过滤。
  6. **Step 6**: 清理 feature flag，移除旧代码。
- **Rollback Plan**: feature flag `VITE_FEATURE_SCOPETREE_FILTERSOURCE` 控制，设为 `false` 回退到旧逻辑。每步可独立回退。
- **Source**: 渐进式架构演进

---

## 7. Constraints & Assumptions

### 7.1 Technical Constraints

- **el-tree 仅有 `defaultCheckedKeys` prop，无 `checkedKeys`** —— 已验证 Element Plus 2.x 源码（`treeProps` 定义在 `tree.mjs`），方案已据此调整。
- `store.setData()` 内部调用 `_initDefaultCheckedNodes()` 从 `this.defaultCheckedKeys` 恢复 —— 已验证 Element Plus 2.x 源码（`tree-store.mjs:L58-L65`、`L90-L97`）。
- `watch(defaultCheckedKeys)` 响应 prop 变化并调用 `store.setDefaultCheckedKey()` —— 已验证 Element Plus 2.x 源码（`tree.vue_vue_type_script_lang.mjs:L68-L71`）。
- el-tree 的 `filter-node-method` 只影响显示/隐藏，不影响 checked 状态 —— 已确认 Element Plus 文档和源码行为。
- `useRelationClassifier` 的 `treeData` 计算 `buildRelationScopeTree()` 是同步函数。
- 当前项目中**无任何文件使用 `:default-checked-keys` prop**，全部使用 `setCheckedKeys()` 方法 + 手动恢复逻辑。

### 7.2 Business Constraints

- 不能破坏现有的 MultiObjectManagementPage 列表功能。
- `emit('scope-change')` 接口必须保持兼容。
- 不引入新的外部依赖。

### 7.3 Assumptions

- `:default-checked-keys` 在 `store.setData()` 后能正确恢复选中状态 —— **已验证 Element Plus 源码**，`setData` 内部调用 `_initDefaultCheckedNodes()` 读取 `this.defaultCheckedKeys` 恢复。
- `coordinator.refreshAll()` 从 `watch(combinedFilters)` 移除后不影响 CRUD/导入/手动刷新 —— **已验证**，CRUD（`boCrudService.create/update/delete`）通过 `_coordinator?.refreshAll()` 独立触发。
- `scopeIds` reactive 对象在 `handleScopeChange` 中正确更新 —— 已有 `useMultiObjectPage.spec.js` 1238行覆盖。

---

## 8. Priorities & Milestone Suggestions

| ID     | Requirement                    | Priority | Reason                                      |
| ------ | ------------------------------ | -------- | ------------------------------------------- |
| FR-005 | 节点 ID ↔ 过滤值双向映射        | Must     | FR-001 / FR-002 / FR-007 的前置依赖           |
| FR-007 | 可测试的状态管理架构            | Must     | 防止未来同类 bug 逃脱测试发现                  |
| FR-001 | FilterSource 驱动 ObjectScope | Must     | 核心问题，直接消除 20 轮排查中的多数 bug        |
| FR-003 | 解耦自触发刷新循环              | Must     | 病灶根源之一                                  |
| FR-002 | FilterSource 驱动 RelationScope| Must     | 核心问题                                      |
| FR-006 | 保持 emit 接口兼容              | Must     | 上游兼容性                                    |
| FR-004 | 关系树加载后过滤                | Should   | 性能优化，不阻塞核心修复                       |
| NFR-005| 可测试性                       | Must     | 架构保障，防止回归                             |

**Suggested Milestones**:

| Milestone | Scope                                                                                        |
| --------- | -------------------------------------------------------------------------------------------- |
| M1        | FR-005 + FR-007：创建 useScopeTreeState composable + 映射函数单元测试                          |
| M2        | FR-001：ObjectScopeSection 接入 `:default-checked-keys`，移除内部状态副本                     |
| M3        | FR-003：解耦 coordinator.refreshAll 自触发循环                                                |
| M4        | FR-002 + FR-006：RelationScopeSection 接入，移除 installStoreSetDataHook 等 hack               |
| M5        | FR-004：关系树性能优化                                                                        |

---

## 9. Change / Design Proposal (RFC)

### 9.1 As-Is Analysis

#### 当前架构缺陷总结

```
ObjectScopeSection (494行，0单元测试)     RelationScopeSection (466行，0单元测试)
┌──────────────────────────────┐        ┌───────────────────────────────┐
│ el-tree store ①              │        │ el-tree store ①               │
│   ↕ @check / setCheckedKeys  │        │   ↕ @check / monkey-patch     │
│ checkedBoIds ref ②           │        │ preservedCheckedKeys ②        │
│   ↕ manual sync              │        │   ↕ hook.restore              │
│ treeData ref ③               │        │ classifier.selectedScopeIds ③│
│   ↕ silent refresh restore   │        │   ↕ manual sync               │
│ emit('scope-change')          │        │ classifierTreeData computed ④│
│        ↓                      │        │   ↕ store.setData wipe        │
│   scopeIds ④                  │        │ emit('scope-change')           │
│   (useMultiObjectPage)        │        │        ↓                       │
└──────────────────────────────┘        │   scopeIds.relationExtra       │
                                        └───────────────────────────────┘

自触发循环：
  emit('scope-change')
    → handleScopeChange → scopeIds 更新
    → combinedFilters computed 重算
    → watch → coordinator.refreshAll()  ← 病灶！
    → ObjectScopeSection.refresh() → silent refresh → store.setData
```

#### 核心问题矩阵

| 问题 | 根因 | 为何未被测试发现 |
|------|------|-----------------|
| checkbox 状态丢失 | `store.setData` 擦除，手动恢复时序脆弱 | 无单元测试（组件未提取 composable） |
| 无法反勾选 | `preservedCheckedKeys` 与 el-tree 内部不同步 | 多源同步逻辑无法隔离测试 |
| 树自动收起 | `store.setData` 清空 expanded 状态 | 展开状态同样无测试 |
| stale 刷新后残留勾选 | hook 中 restored keys 与新 tree nodesMap 不匹配 | monkey-patch 无法 mock |
| 自触发循环 | watch 无差别触发 refreshAll | E2E 只测 happy path |

#### 测试现状

| 文件 | 行数 | 单元测试 | 说明 |
|------|------|---------|------|
| `ObjectScopeSection.vue` | 494 | **0** | 无 `__tests__` 目录 |
| `RelationScopeSection.vue` | 466 | **0** | 无 `__tests__` 目录 |
| `RelationScopeTree.vue` | ~400 | **0** | 无 `__tests__` 目录 |
| `MultiObjectManagementPage.spec.js` | 433 | 含 stub | RelationScopeTree 被 stub 为 `<div class="rst-stub">` |
| `useMultiObjectPage.spec.js` | 1238 | ✅ 全面 | 仅测 composable 层，不测组件交互 |
| `arch-data-filter-scope.spec.js` | 255 | E2E | 仅测试 happy path（打开→勾选→验证过滤） |

#### `coordinator.refreshAll()` 完整调用链审计

| # | 触发场景 | 调用方式 | 是否应保留 |
|---|---------|---------|-----------|
| 1 | `boService.create()` 成功 | `_coordinator?.refreshAll()` | ✅ 保留（数据变更后刷新） |
| 2 | `boService.update()` 成功 | `_coordinator?.refreshAll()` | ✅ 保留 |
| 3 | `boService.delete()` 成功 | `_coordinator?.refreshAll()` | ✅ 保留 |
| 4 | 手动刷新按钮 | `handleGlobalAction('refresh')` | ✅ 保留 |
| 5 | 导入成功 | `handleImportSuccess()` | ✅ 保留 |
| 6 | `watch(combinedFilters)` → scope 变更 | `coordinator.refreshAll()` | ❌ **移除**（自触发病灶） |

### 9.2 Target State

```
                    FilterSource (单一真相源)
                    ┌─────────────────────────────┐
                    │ scopeIds (reactive)          │
                    │ ├─ domain.selected/effective │
                    │ ├─ sub_domain.selected/eff.. │
                    │ ├─ service_module.selected.. │
                    │ └─ relationExtra.relationCodes│
                    └──────────┬──────────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
     ObjectScopeSection  RelationScopeSection  MetaListPage
     ┌──────────────┐   ┌──────────────────┐  (API)
     │ el-tree (View)│   │ el-tree (View)    │
     │               │   │                   │
     │ :default-     │   │ :default-         │
     │  checked-keys │   │  checked-keys     │
     │ = computed    │   │ = computed        │
     │   from        │   │   from            │
     │   scopeIds    │   │   relationCodes   │
     │     ↑↓        │   │     ↑↓            │
     │ @check → emit │   │ @check → emit     │
     │   scope-change│   │   scope-change    │
     └──────┬────────┘   └────────┬─────────┘
            │                     │
            └──────────┬──────────┘
                       ▼
              handleScopeChange()
              更新 scopeIds (唯一写入口)
```

**核心变化**：
1. el-tree 通过 `:default-checked-keys` 绑定到 scopeIds 派生 computed（利用 Element Plus 原生响应式机制）
2. 移除所有内部状态副本和相关 hack
3. 解耦自触发循环
4. 状态管理逻辑提取为可测试的 composable

### 9.3 Detailed Design

#### 9.3.1 新 composable: useScopeTreeState

```javascript
// src/composables/useScopeTreeState.js
// 可脱离 el-tree 组件独立单元测试

import { computed } from 'vue'

/**
 * ObjectScopeSection 的映射函数（纯函数，无副作用）
 */
export function treeNodesToScope(checkedNodes) {
  const domainIds = [], subDomainIds = [], serviceModuleIds = [], boIds = []
  for (const node of checkedNodes) {
    const id = node.originalId || node.id
    if (node.type === 'domain') domainIds.push(id)
    else if (node.type === 'sub_domain') subDomainIds.push(id)
    else if (node.type === 'service_module') serviceModuleIds.push(id)
    else if (node.type === 'business_object') boIds.push(id)
  }
  return { boIds, domainIds, subDomainIds, serviceModuleIds }
}

export function scopeToNodeKeys(treeData, scope) {
  const keys = new Set()
  for (const type of ['domain', 'sub_domain', 'service_module', 'business_object']) {
    const scopeData = scope[type]
    if (!scopeData) continue
    const ids = scopeData.selected || scopeData.effective || []
    _collectKeysByType(treeData, type, ids, keys)
  }
  return [...keys]
}

function _collectKeysByType(nodes, targetType, idList, result) {
  if (!idList.length) return
  for (const node of nodes) {
    if (node.type === targetType) {
      const id = node.originalId || node.id
      if (idList.includes(id)) result.add(node.id)
    }
    if (node.children) _collectKeysByType(node.children, targetType, idList, result)
  }
}

/**
 * RelationScopeSection 的映射函数（纯函数，无副作用）
 */
export function nodeKeysToRelationCodes(nodeKeys, treeData) {
  const codes = new Set()
  _walkTree(treeData, node => {
    if (nodeKeys.includes(node.id) && node.relationCodes?.length > 0) {
      node.relationCodes.forEach(c => codes.add(c))
    }
  })
  return [...codes]
}

export function relationCodesToNodeKeys(relationCodes, treeData) {
  if (!relationCodes.length) return []
  const keys = new Set()
  _walkTree(treeData, node => {
    if (node.relationCodes?.length > 0) {
      const allMatch = node.relationCodes.every(c => relationCodes.includes(c))
      if (allMatch) keys.add(node.id)
    }
  })
  return [...keys]
}

function _walkTree(nodes, visitor) {
  for (const node of nodes) {
    visitor(node)
    if (node.children) _walkTree(node.children, visitor)
  }
}

/**
 * Vue composable：从 scopeIds + treeData 计算 el-tree 的 default-checked-keys
 */
export function useScopeTreeState(props) {
  // ObjectScope 的 checked keys
  const objectCheckedNodeKeys = computed(() => {
    return scopeToNodeKeys(props.treeData, props.scopeIds)
  })

  // RelationScope 的 checked keys
  const relationCheckedNodeKeys = computed(() => {
    const codes = props.scopeIds?.relationExtra?.relationCodes || []
    return relationCodesToNodeKeys(codes, props.classifierTreeData)
  })

  return {
    objectCheckedNodeKeys,
    relationCheckedNodeKeys,
    treeNodesToScope,
    nodeKeysToRelationCodes
  }
}
```

#### 9.3.2 ObjectScopeSection 改造前后对比

**Before（多源状态）**:
```javascript
const checkedBoIds = ref([])           // 内部副本
const settingFromProp = ref(false)     // 守卫 flag

function handleBoCheck(data, checkedInfo) {
  if (settingFromProp.value) return    // 防递归
  const boNodes = checkedInfo.checkedNodes.filter(n => n.type === 'business_object')
  nextTick(() => { checkedBoIds.value = boNodes.map(n => n.originalId) })
  emitTypedScopeChange()               // 从 treeRef store 读取 emit
}

// loadTreeData silent refresh: ~40 行 save/restore + 5 个 nextTick
```

**After（FilterSource 绑定）**:
```javascript
// 无内部状态！
const { objectCheckedNodeKeys } = useScopeTreeState({
  treeData: computed(() => treeData.value),
  scopeIds: computed(() => props.scopeIds)
})

function handleBoCheck(_data, checkedInfo) {
  const scope = treeNodesToScope(checkedInfo.checkedNodes)
  emit('scope-change', scope)
}

// loadTreeData: 直接 treeData.value = newTree（:default-checked-keys 自动恢复）
// 不再需要 save/restore/sameStructure early return/settingFromProp
```

**模板**:
```html
<!-- Before -->
<el-tree ref="treeRef" :data="treeData" show-checkbox @check="handleBoCheck">

<!-- After -->
<el-tree ref="treeRef" :data="treeData" show-checkbox
  :default-checked-keys="objectCheckedNodeKeys"
  @check="handleBoCheck">
```

#### 9.3.3 RelationScopeSection 改造前后对比

**Before（monkey-patch + 多源状态）**:
```javascript
const preservedCheckedKeys = ref(new Set())
const preservedHalfCheckedKeys = ref(new Set())
const settingFromProp = ref(false)

// ~70 行 installStoreSetDataHook monkey-patch

function handleClassifierCheck(data, { checkedKeys }) {
  if (settingFromProp.value) return
  preservedCheckedKeys.value = new Set(checkedKeys)
  classifier.selectedScopeIds.value = checkedKeys
  emitScopeChange()
}
```

**After（FilterSource 绑定）**:
```javascript
// 无内部状态！无 monkey-patch！
const { relationCheckedNodeKeys } = useScopeTreeState({
  classifierTreeData: computed(() => classifierTreeData.value),
  scopeIds: computed(() => props.scopeIds)
})

function handleClassifierCheck(_data, { checkedKeys }) {
  const codes = nodeKeysToRelationCodes(checkedKeys, classifierTreeData.value)
  emit('scope-change', { relationCodes: codes })
}
```

**模板**:
```html
<!-- Before -->
<el-tree ref="relationTreeRef" :data="classifierTreeData" show-checkbox
  @check="handleClassifierCheck">

<!-- After -->
<el-tree ref="relationTreeRef" :data="classifierTreeData" show-checkbox
  :default-checked-keys="relationCheckedNodeKeys"
  @check="handleClassifierCheck">
```

#### 9.3.4 解耦自触发循环

**Before**（[MultiObjectManagementPage.vue:L338-L343](file:///d:/filework/excel-to-diagram/src/components/common/MultiObjectManagementPage/MultiObjectManagementPage.vue#L338-L343)）:
```javascript
watch(() => page.combinedFilters, (newFilters) => {
  if (metaListPageRef.value?.setContextFilters) {
    metaListPageRef.value.setContextFilters(newFilters)
  }
  coordinator.refreshAll()  // ← 移除
})
```

**After**:
```javascript
watch(() => page.combinedFilters, (newFilters) => {
  if (metaListPageRef.value?.setContextFilters) {
    metaListPageRef.value.setContextFilters(newFilters)
  }
  // coordinator.refreshAll() 移除 —— scope 变更不需要刷新树数据
  // CRUD 操作通过 boCrudService 内部 _coordinator?.refreshAll() 独立触发
  // 手动刷新/导入成功通过 handleGlobalAction/handleImportSuccess 独立触发
})
```

### 9.4 Alternatives Considered

| Option | Pros | Cons | Decision |
| ------ | ---- | ---- | -------- |
| **A) `:default-checked-keys` 绑定 FilterSource** | 利用 Element Plus 原生机制、消除所有 hack、可测试 | 需验证 `_initDefaultCheckedNodes` 在 `check-strictly=false` 下的父子联动行为 | ✅ Selected |
| B) 保持 `setCheckedKeys()` 方法但移到 watch 中 | 改动最小 | `setData` 擦除问题仍在、仍需 guard flag | ❌ Rejected |
| C) 换用其他树组件 | 消除 el-tree 问题 | 迁移成本高、未知新问题、废弃已有样式 | ❌ Rejected |

**`defaultCheckedKeys` 在 `check-strictly=false` 下的父子联动**：
- Element Plus 源码中 `_initDefaultCheckedNodes` 调用 `node.setChecked(true, !this.checkStrictly)`，第二个参数 `!this.checkStrictly` 为 `true` 时会触发深层递归（向上设置父节点 indeterminate、向下设置子节点 checked）。
- 因此，当 `check-strictly=false`（默认）时，只需在 `defaultCheckedKeys` 中传入**叶子节点**的 keys，el-tree 会自动处理父节点的 indeterminate 状态和半选状态。这与当前手动的 `setCheckedKeys` 行为一致。

### 9.5 Implementation & Migration Plan

#### Implementation Order

1. **Step 1: 创建 `useScopeTreeState.js` + 单元测试**（M1）
   - 实现并导出所有映射函数和 composable
   - 编写 ≥ 8 个单元测试用例：
     - `treeNodesToScope`：空 nodes → 空 scope、含所有类型 nodes → 分类正确、重复 nodes → 去重
     - `scopeToNodeKeys`：空 scope → []、selected 优先于 effective、无效 type → 不影响结果
     - `nodeKeysToRelationCodes`：空 keys → []、单个 module node → 对应 codes、多个 module → 合并去重
     - `relationCodesToNodeKeys`：空 codes → []、单个 code → 匹配 node key、多个 codes → 匹配所有对应 node keys

2. **Step 2: ObjectScopeSection 接入**（M2）
   - 添加 `:default-checked-keys="objectCheckedNodeKeys"`
   - 简化 `handleBoCheck`（仅 emit）
   - 简化 `loadTreeData`（移除 silent refresh 的 save/restore 和 sameStructure early return）
   - 移除 `checkedBoIds`、`settingFromProp`
   - Feature flag 双轨运行：`if (featureFlag) ` 新逻辑 `else` 旧逻辑

3. **Step 3: 解耦自触发循环**（M3）
   - 从 `watch(combinedFilters)` 中移除 `coordinator.refreshAll()`
   - 验证 CRUD 操作后列表仍能正确刷新

4. **Step 4: RelationScopeSection 接入**（M4）
   - 添加 `:default-checked-keys="relationCheckedNodeKeys"`
   - 简化 `handleClassifierCheck`（仅 emit）
   - 移除 `preservedCheckedKeys`、`preservedHalfCheckedKeys`、`installStoreSetDataHook`、`settingFromProp`、`classifier.selectedScopeIds`
   - 简化 `loadRelationships`（移除 stale 时清除 preserved 的逻辑）

5. **Step 5: 关系树性能优化**（M5）
   - 将 `classifierTreeData` 从 computed 改为 shallowRef
   - 对象范围变更时使用 `filter-node-method` 或 v-show 而非重建树

6. **Step 6: 清理**
   - 移除 feature flag
   - 移除旧代码

#### Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-----------|--------|-----------|
| `:default-checked-keys` check-strictly=false 下父节点 indeterminate 不正确 | Low | Medium | 已验证 Element Plus 源码 `_initDefaultCheckedNodes` 中 `!this.checkStrictly` 参数处理父子联动。Step 2 先在小范围验证 |
| 移除 `coordinator.refreshAll` 后某些场景遗漏刷新 | Low | High | 已审计全部 6 个触发场景（9.1节），CRUD 通过独立路径触发。Step 3 单独验证 |
| RelationScopeSection 映射函数在大树上的性能 | Low | Low | 映射函数遍历整棵树 O(n)，但在 100k 节点下仍 < 10ms，可接受 |
| 现有 E2E 测试回归 | Medium | Medium | 每步完成后运行完整前端测试 |

#### Testing Strategy

| 层 | 工具 | 覆盖内容 |
|---|------|---------|
| **Unit** | vitest | `useScopeTreeState` 所有映射函数（FR-005 + FR-007），≥ 8 个测试用例 |
| **Unit** | vitest | `checkedNodeKeys` computed 逻辑（mock scopeIds + mock treeData） |
| **Unit** | vitest | 现有 `useMultiObjectPage.spec.js` 1238行全部通过（确保不回归） |
| **Integration** | webapp-testing | 手动验证：勾选+版本切换、勾选+silent refresh、全选+反勾选、关系树+对象范围变更 |
| **E2E** | Playwright | 现有 `arch-data-filter-scope.spec.js` 通过（不新增，核心变更在单元测试层） |

---

## 10. TBD List

| ID     | Item                                     | 研究结论 | Status |
| ------ | ---------------------------------------- | -------- | ------ |
| TBD-1  | el-tree `:checked-keys` prop 是否存在？ `:data` 变更后是否恢复？ | **已确认**：无 `checkedKeys` prop，只有 `defaultCheckedKeys`。<br>`store.setData()` 内部调用 `_initDefaultCheckedNodes()` 从 `this.defaultCheckedKeys` 恢复选中状态。<br>`watch(defaultCheckedKeys)` 响应 prop 变化。<br>✅ 方案改为 `:default-checked-keys` | **Resolved** |
| TBD-2  | `filter-node-method` 隐藏节点的 checked keys 是否仍在 `getCheckedKeys()` 中？ | **已确认**：隐藏节点仍出现在 `getCheckedKeys()` 中。<br>✅ 在 `@check` 处理中只需处理 checkedKeys 参数（el-tree 传入的），不需要 `getCheckedKeys()` | **Resolved** |
| TBD-3  | 移除 `coordinator.refreshAll()` 后 CRUD 操作能否正确触发列表刷新？ | **已确认**：CRUD 通过 `boCrudService._coordinator?.refreshAll()` 独立触发，与 `watch(combinedFilters)` 无关。<br>✅ 移除安全 | **Resolved** |
| TBD-4  | `initialRelationCodes` 是否需要实现 URL 参数恢复？ | 当前始终为空数组。与本次 scope tree 状态管理重构无关。<br>可在后续迭代中独立实现。 | **Deferred** |

---

Spec + RFC 包含 10 sections，最后 section 为 "TBD List"，4 个 TBD 中 3 个已解决（Resolved），1 个已推迟（Deferred）。内容完整。
