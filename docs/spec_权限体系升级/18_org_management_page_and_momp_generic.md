# Spec：Org 管理页面 + MultiObjectManagementPage(MOMP) 通用化改造

> 文档编号: 18 | 状态: 草案 | 更新: 2026-08-30
> 主题: 复用 MOMP 范式新建「组织(org) 管理页面」，并因此把 MOMP 从"架构数据专用"泛化为"通用多对象管理框架"
> 前置: `13_organization_model_integration.md` / `14_org_management_dimension_and_migration.md`
> 范围裁剪(本期不做): org_relationship 右 Tab（架构预留）; user / position / user_org_assignment（架构预留）; org 运行实例不做字段扩展（对齐 14 号路线 A）

---

## 1. 背景与目标（Background & Objectives）

### 1.1 现状（背景）
- 平台元模型已有一套成熟的**元数据驱动多对象管理范式** `MultiObjectManagementPage(MOMP)`（默认用于架构数据 ArchData 页）：左侧**多选范围筛树**(RelationScopeTree) + 右侧**平级对象 Tab 列表**(MetaListPage 懒加载 + v-show 保状态)。
- 组织模型(13 号)已定义 `org`(单类型 `parent_id` 自引用 / `org_scope` / `org_category`) 与 `org_relationship`(组织间关系)。**org 目前无树形管理 UI**，前端缺乏组织数据的浏览/维护入口。
- 在进一步接入权限体系(14 号路线 A：org 仅作为"用户归属 + 人员管理"维度)之前，需要一个**组织管理运维页面**。

### 1.2 业务目标（Business Objectives）
- BO-1：建立组织(org)树形 + 平级对象的管理入口，支撑后续 user_org_assignment / position 接入时的"选组织、看组织、维护组织"。
- BO-2：验证并沉淀 MOMP 的**可复用性**——把"左侧任意筛选树 + 右侧任意平级对象列表"抽成通用能力，org 页面只声明元数据即可接入。

### 1.3 用户/涉众目标（User/Stakeholder Objectives）
- 期望：左侧用**组织自身树**做多选范围筛选（勾选父节点 → 子孙全部选中，等价级联多选），右侧 org 列表按该范围展示/维护。
- 期望：不重复造轮子——复用 MOMP 的容器外壳、Tab 导航、懒加载、状态持久化、导入导出等工程资产。
- 期望：**不破坏现有 ArchData 页**（MOMP 的默认消费方）。

### 1.4 本次范围裁剪（明确界定）
| 项 | 本期 | 说明 |
|----|------|------|
| MOMP 通用化（左树注入 + 每 Tab 过滤策略接口） | ✅ 做 | 是拿到 org 页面的前提 |
| OrgScopeTree 组件（单类型自引用级联多选） | ✅ 做 | 组织树左栏 |
| 右 Tab「org」列表（**CRUD + 导入导出维护**）| ✅ 做 | 复用 MetaListPage + 现有 `v2/bo/user_group` 管理端点，**无需新后端** |
| 右 Tab「org_relationship」（范围=from/to 命中选中 org） | ❌ 本期不做 | **不作真实 Tab**（后端未建表，见 §1.4a），仅**过滤策略接口预留** |
| 右 Tab「user」 | ❌ 本期不暴露 | 已决策形态(b)：仅 `filterStrategies` 接口预留，objectTypes 不含 user（见 FR-007）|

> **§1.4a org_relationship 为何不能作真实 Tab**：org_relationship 在 13 号文档为"待建（Phase A）"、16 号明确"不引入留二期"，后端**无该对象 schema**。若强行加入 `objectTypes`，MetaListPage 调 manage_api 会因找不到 schema 而空态/报错。故预留只在**过滤策略接口**层面（§9.6），不加入本期 objectTypes。

---

## 2. 需求类型总览（Requirement Type Overview）

| 类型 | 适用 | 依据（来源） |
|------|------|-------------|
| Business（业务） | 是 | 用户讨论/13号/14号 |
| User/Stakeholder（涉众） | 是 | 用户讨论（级联多选、复用 MOMP、不破坏 ArchData）|
| Solution（解决方案） | 是 | MOMP 代码分析 |
| Functional（功能） | 是 | 本文 §3 |
| Nonfunctional（非功能性） | 是 | 本文 §4（兼容性/性能/可测性）|
| External Interface（外部接口） | 是 | org_service API / MetaListPage / 导入导出 |
| Transition（迁移） | 是 | 本文 §6（org 无存量数据前置；MOMP 兼容默认）|

---

## 3. 功能需求（Functional Requirements）

### FR-001: MOMP 左栏筛选树组件注入
- **Description**: MOMP 将左侧写死的 `RelationScopeTree` 改为**可注入组件**。消费方通过 `options.scopeTree.component + options.scopeTree.propsProvider + options.scopeTree.events` 声明左树；**未声明时回退 `RelationScopeTree` + 当前 props/事件**，保证 ArchData 页默认行为不变。
- **说明**: MOMP.vue 的 master slot 当前硬编码 `RelationScopeTree`（L45-54），`scopeTreeRef`/`scopeTreeKey`/`handleScopeChange` 均耦合该组件。改造后注入组件必须暴露一致的 `scope-change` 事件与同名 ref 接口（见 FR-002 适配器）。
- **Acceptance Criteria**:
  - ArchData 页（不传 scopeTree）行为与现在**逐字节一致**（回归）。
  - org 页传入 OrgScopeTree 后，master slot 正确渲染注入树。
- **Priority**: Must
- **Type Mapping**: Solution/Functional
- **Source**: 用户讨论 + MOMP.vue L45-54

### FR-002: MOMP scope 事件适配器（scopeAdapter）
- **Description**: 左树 `scope-change` 携带的 scope 结构目前**硬编码**为 `{ selectedDomainIds/effectiveSubDomainIds/.../boIds/relationCodes }`（见 useMultiObjectPage.handleScopeChange 的 typeToShortField 映射 L433-485）。改造为可注入的 `config.scopeAdapter(scope, scopeIds, ctx)`，负责把注入树的事件结构映射进统一 `scopeIds[type].{selected,effective}`。
- **说明**: org 树的事件结构是 `{ orgIds, effectiveOrgIds }`（自引用，无 type 前缀、无 domain→sub_domain→service_module 四层）。默认 `scopeAdapter=默认对象范围映射`，org 页面注入 `orgScopeAdapter`。
- **Acceptance Criteria**:
  - 默认适配器行为与现状一致。
  - org 适配器可把 `orgIds/effectiveOrgIds` 写入 `scopeIds.org.selected/effective`。
- **Priority**: Must
- **Type Mapping**: Solution/Functional
- **Source**: useMultiObjectPage.js L433-485

### FR-003: 每 Tab 过滤策略接口（per-tab filter strategy）
- **Description**: `_computeTypeFilters` 目前按 `customFilterBuilders > association > entity > relationship` 分发（L282-298），其中 entity 分支靠 `hierarchyService.isHierarchyType` + `{parentType}_id__in` FK 硬约定。org 不满足该约定（org 无父对象类型 FK，是 `parent_id` 自引用；org_relationship 是 source/target，不是 hierarchy）。改造为显式 **per-tab 过滤策略注册表**：`config.filterStrategies[type] = (scopeIds, ctx) => filters`，entity/association/relationship 作为内置默认策略注册，**允许按 type 覆盖**。
- **说明**:
  - `org` Tab：当 `scopeIds.org.effective`(选中∪子孙) 非空 → `id__in=[effectiveOrgIds]`；否则退化为空过滤（配合 versionContext，不加载全量）。
  - `org_relationship` Tab：策略槽位**预留**（签名 `(scopeIds, ctx)=>filters`），本期返回空过滤器 + TODO 注释（source_org_id__in/target_org_id__in 组合，见 §9.6）。
  - `user` Tab：策略槽位预留。
- **Acceptance Criteria**:
  - entity/association/relationship 三类对象过滤结果与现状一致（回归）。
  - org Tab 按 effective 正确过滤；未选中任何 org 时**不触发全量加载**（对齐用户强约束"scopeCode 失败严禁回退全量"）。
- **Priority**: Must
- **Type Mapping**: Solution/Functional
- **Source**: useMultiObjectPage.js L282-298 / L348-412

### FR-004: OrgScopeTree 组件（单类型自引用级联多选）
- **Description**: 新建 `src/components/common/OrgScopeTree/`，渲染组织树（`org.parent_id` 单类型自引用）。采用 `show-checkbox + check-strictly=false`（勾父含子 = 级联多选），复用 ObjectScopeSection 的工程资产（expand 持久化 `store.setData` 钩子、collectLeafKeys/collectInitialExpandedKeys 防卡顿、搜索过滤/全选/清空/silent 刷新不丢选中）。
- **node 模型**: 无 type 前缀（全为 org），id 即 org.id；顶层节点为 `parent_id is null` 的根组织；children 由 `parent_id` 组装。
- **事件**: `emit('scope-change', { orgIds, effectiveOrgIds })`：
  - `orgIds` = 被勾选的节点 id（含父节点本身，不含其子孙——因级联勾选父时子树都进 `effective` 表达，但为与 MetaListPage 的 `id__in` 精确语义对齐，此处取"实际勾选叶/父集合"）。
  - `effectiveOrgIds` = `orgIds ∪ 全部子孙`（供 org Tab `id__in` 使用）。
- **UI 资产**: 工具栏（展开/收起、全选、清空、刷新）、搜索框、节点计数，对齐 ObjectScopeSection。
- **Acceptance Criteria**:
  - 勾选父节点 → effective 含全部子孙；org 列表随之展示该域。
  - 展开/刷新后选中态不丢。
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 用户讨论（级联多选）+ ObjectScopeSection.vue L43-74/L434-534

### FR-005: Org 管理页面（左 OrgScopeTree + 右 org 列表 Tab，CRUD + 导入导出维护）
- **Description**: 新建路由页（见 §7.4 命名建议，`objectTypes=['org']`）。左侧 OrgScopeTree（数据源 `OrgService.get_org_tree()`，返回已组装的嵌套 children），右侧 org 列表 MetaListPage（`object-type='org'`），**支持 CRUD + 导入/导出维护**，`org_type/org_scope/org_category` 等字段展示 **name/label 而非 raw id**。
- **说明**: ① org 的通用 CRUD 走现有 `v2/bo/user_group` 统一管理端点（org_api.py L102-107 已确认 v1 主表 CRUD 迁移至此），MetaListPage 直接消费，**无需任何新后端**。② 复用 MOMP 外壳（GlobalToolbar + MasterDetailLayout + 按钮式 Tab nav + 懒加载 + 状态持久化）。③ org 无 versionContext → `options.disableVersionContext` 生效时隐藏版本选择器、baseFilters 不含 version_id/product_id。
- **Acceptance Criteria**:
  - 进入页面默认展开 org 树；org 列表可新增/编辑/删除/导入/导出。
  - 勾选任一组织节点 → 列表过滤到该组织及其子孙（`id__in=[effectiveOrgIds]`）。
  - 未勾选任何组织时，**不触发全量加载**（空选择 → 空过滤守卫）。
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 用户讨论（确认 CRUD+导入导出）+ org_api.py 核实

### FR-006: org_relationship 右 Tab（仅过滤策略接口预留，本期不做、不建 Tab）
- **Description**: org_relationship **本期不加入 `objectTypes` 真实 Tab**（后端未建表，见 §1.4a）。预留仅体现在 FR-003 的 `filterStrategies` 注册表：当未来后端建好 org_relationship schema 后，注册 `filterStrategies['org_relationship']`。本期**不实现**该过滤逻辑、不建树节点。
- **说明（未来过滤语义，用于接口签名设计，勿本期实现）**: `from_org_id__in / to_org_id__in` 组合 → 命中选中 org（任一向关系）：`(from_org_id∈selected) OR (to_org_id∈selected)`。
- **Acceptance Criteria**: `filterStrategies` 接口预留的签名可无侵入表达该语义；本期不触发任何 org_relationship 加载。
- **Priority**: Should（预留）
- **Type Mapping**: Functional / Transition
- **Source**: 用户指令「org_relationship 本期先不做，架构预留」+ org_api.py 核实（未建表）

### FR-007: user 预留（已决策：形态 b——仅接口预留，本期不暴露 UI）
- **Description**: 用户确认采纳**形态(b) 仅接口预留**：本期**不在 UI 暴露 user Tab**，仅在 `filterStrategies` 注册表与文档中声明扩展点——未来按"任职 org"过滤 user。`objectTypes` 保持 `['org']`，不加入 `user`。
- **说明（未来扩展语义，勿本期实现）**: `filterStrategies['user']`：按用户任职 org 过滤（user_org_assignment.org_id ∈ selected 或其祖先链）。
- **Acceptance Criteria**: 本期无任何 user Tab/加载；`filterStrategies` 签名不排斥未来注册 `user`。
- **Priority**: Could（预留）
- **Type Mapping**: Transition
- **Source**: 用户讨论（选定形态 b）+ 后端任职模型二期未就绪

### FR-008: 状态持久化 + versionContext 解耦（GlobalToolbar 决策已锁定）
- **Description**: MOMP 现存依赖：路由推导 menuCode（L277-283）、versionContext（useVersionContext，L144）。org 页无产品/版本概念。改造：`menuCodeProvider` 可注入（默认现有 route-name 推导）；`versionContext` 可禁用或提供 `disableVersionContext`（此时 baseFilters 不含 version_id/product_id）。sessionStorage 快照机制（saveStateForDiagram/restoreStateFromDiagram）改为**通用状态键**（非硬编码 archManagerStateBeforeDiagram），org 页也可复用。
- **决策(TBD-6，用户确认)**: org 页 `disableVersionContext` 后，GlobalToolbar **仅隐藏产品/版本选择器，保留「刷新 / 导入 / 导出」等顶部操作**。
- **Acceptance Criteria**:
  - ArchData 页路由推导与 versionContext 行为不变。
  - org 页不请求产品/版本数据。
- **Priority**: Must
- **Type Mapping**: Solution/Functional
- **Source**: MOMP.vue L277-283 / useMultiObjectPage.js L144-178/L763

---

## 4. 非功能需求（Nonfunctional Requirements）

### NFR-001: 兼容性（ArchData 零回归）
- **Description**: MOMP 的所有默认入口（不传 scopeTree/scopeAdapter/filterStrategies/menuCodeProvider）必须保持现行行为。
- **Measurement**: 相关单测 + 前端 E2E（ArchData 页对象树勾选、关系筛选、图表切换）全部通过。
- **Priority**: Must

### NFR-002: 性能（严禁全量加载 + 级联防卡顿）
- **Description**: 未选组织时不加载全部组织/对象；树级联展开/勾选不卡顿（沿用 collectLeafKeys/collectInitialExpandedKeys）。
- **Measurement**: 未选组织时 org 请求返回空/不触发；展开大组织子树无感知卡顿。
- **Priority**: Must

### NFR-003: 可测试性 / 可排查性
- **Description**: 注入的树与过滤策略可独立单测；scope 事件映射可单测；dev 环境暴露 `window.__orgPage` 便于 E2E。
- **Measurement**: 新增单测覆盖 scopeAdapter 与 filterStrategies。
- **Priority**: Should

---

## 5. 外部接口需求（External Interface Requirements）

### IF-001: org 组织树 API
- **Type**: API
- **Endpoint / Entry**: `OrgService.get_org_tree()`（worktree `meta/services/org_service.py` L200-223），返回**已组装的嵌套 children 树**，字段 `id/name/code/parent_id/manager_id/description/created_at/children`（根 = parent_id 不在 map 中的节点）。前端 OrgScopeTree 可直接消费，无需再组装。
- **注意**: 该接口含 `code/parent_id` 但**不含 org_type/org_scope/org_category**；若组织树节点需展示类型标签，需额外补充查询（或本期树节点仅显示 name，标注为可选项）。
- **Error Handling**: 树加载失败显示空态 + 提示，不静默全量。
- **Source**: 代码分析（org_service.py L200-223）

### IF-002: org 列表（MetaListPage 消费，走统一管理端点）
- **Type**: UI/API
- **Endpoint / Entry**: `object-type='org'` → 复用现有 `v2/bo/user_group` 管理端点（org_api.py L102-107 确认 v1 主表 CRUD 迁至此处）；过滤 `id__in=[effectiveOrgIds]`。
- **Interaction**: 复用 MetaListPage 列表/详情/CRUD/导入导出；`org_type/org_scope/org_category` 用 label 展示。
- **Source**: org_api.py + MOMP 现状

### IF-003: 导入导出对话框
- **Type**: UI
- **Entry**: 复用 ImportDialog/ExportDialog；org 无关系/备注类型时隐藏相关可选类型。
- **Source**: MOMP.vue L123-149

---

## 6. 迁移与过渡需求（Transition Requirements）

### TR-001: MOMP 泛化不改动默认消费方
- **Description**: MOMP 引入默认参数后，ArchData 页无需任何改动，即不传新参数即走旧逻辑。
- **Strategy**: 全部新能力走 `options.xxx`，未传时默认旧实现；通过单测与 E2E 建立回归护栏。
- **Rollback Plan**: 若泛化引发回归，回退 MOMP.vue/useMultiObjectPage.js 的增量改动即可（ArchData 无新增依赖）。
- **Source**: 用户约束

### TR-002: org 页面数据与权限
- **Description**: org 当前无生产存量管理数据（前端无管理 UI），无需数据迁移。权限接入按 14 号路线 A 后置。
- **Source**: 13号/14号

---

## 7. 约束与假设（Constraints & Assumptions）

### 7.1 技术约束
- 对齐 13/14 号：**org 默认不加字段**，数据范围走业务维度；org 页面仅作"人员维度/组织管理"，不改造平台元模型。
- MOMP 原则：**纯元数据驱动，严禁在组件内硬编码之类型**；泛化也须保持——org 的 self-ref/source-target 过滤必须通过**策略/适配器注入**，而非写进 MOMP 核心。
- org 树是单类型（`parent_id`自引用），非 4 级业务树。

### 7.2 业务约束
- `org_relationship` 与现有 `relationship.yaml` **是两类不同对象**，不得复用（13号结论）。
- org_scope/org_category 本期仅用于展示 name，不扩展运行实例字段。

### 7.3 假设
- 「勾选父→子孙全选」= 用户所说的"多选"（级联多选，check-strictly=false）。– Source: 已确认
- org 树节点规模可控（组织数通常远小于 3000 BO），可整体加载并级联勾选。– Source: Assumed
- org_service.py 的树/子树能力可直接被前端复用。– Source: Verified（worktree 存在）
- org 的通用 CRUD 由 `v2/bo/user_group` 管理端点承载，MetaListPage 可直接消费。– Source: Verified（org_api.py L102-107）

### 7.4 路由/菜单命名建议（用户要求给出建议）
> 现状参照：架构数据 `/system/archdata`（route name `ArchDataManagement`，menu_code `arch-data`，MOMP 经 route.name 推导菜单权限，MOMP.vue L277-283）。

**推荐**：
- 路由：`/system/org`（与 `SystemManagement` 下 `/system/user`、`/system/group` 风格一致，`/system/{object}`）
- route name：`OrgManagement`
- menu_code：`org-management`
- 菜单挂点：平台管理 → 系统管理 → 组织管理（与 org.yaml 作为一等管理维度匹配）

**落地要点**：MOMP 的 `menuCodeProvider` 默认推导逻辑（见 FR-008）需扩展识别 `OrgManagement` → `org-management`，避免沿用"仅 archdata 系列"的白名单导致导入/导出权限码为空（MOMP.vue L277-283）。

---

## 8. 优先级与里程碑建议（Priorities & Milestone Suggestions）

| ID | 需求 | 优先级 | 理由 |
|----|------|--------|------|
| FR-001 | 左树组件注入 | Must | org 页面前提 |
| FR-002 | scope 适配器 | Must | 统一事件契约 |
| FR-003 | 每 Tab 过滤策略 | Must | 解耦 FK 硬约定 |
| FR-004 | OrgScopeTree | Must | org 左树 |
| FR-005 | Org 管理页面 | Must | 交付物 |
| FR-008 | versionContext 解耦+持久化 | Must | org 无版本上下文 |
| FR-006 | org_relationship 预留 | Should | 架构预留 |
| FR-007 | user 预留 | Could | 远期 |

**建议里程碑**
- **M1（MOMP 泛化，回归护栏）**: FR-001/002/003/008 前置长，配 ArchData 回归单测+E2E。交付后可复用但 org 未建页。
- **M2（OrgScopeTree + org 页面）**: FR-004/005，右上 org 列表可维护。
- **M3（预留槽位）**: FR-006/007 文档化 + 空策略注册（不实现逻辑）。

---

## 9. 变更/设计方案（RFC）

### 9.1 As-Is 现状分析

**现状架构**
- 入口组件 `MultiObjectManagementPage.vue`：GlobalToolbar(顶部全局操作) + MasterDetailLayout(左树右详) + RelationScopeTree(master slot，**硬编码**) + MetaListPage(右侧平级 Tab，懒加载+v-show) + 按钮式 Tab nav + Import/ExportDialog。
- 逻辑集中在 `useMultiObjectPage.js`：`scopeIds`(reactive, key=type) → `handleScopeChange`(映射树 scope 事件) → `tabFilters.computed`(`_computeTypeFilters` 按 entity/association/relationship 分发) → `combinedFilters`(合并 versionContext + global + per-type)。
- Tab→树过滤核心约定：`{parentType}_id__in`（getParentType 推导），entity 分支直接用。

**现存痛点（相对通用化）**
1. 左树写死 `RelationScopeTree`（MOMP.vue L45-54），且 `scopeTreeRef`（shortcut/applyScopeCode 用）、`scopeTreeKey`(图表返回重建)都耦合它。
2. `handleScopeChange` 的 typeToShortField 硬编码 domain/sub_domain/service_module/business_object + relationship 语义（useMultiObjectPage.js L433-485）。
3. `_computeTypeFilters` entity 分支依赖 `{parentType}_id__in` FK 硬约定（L348-412），org 自引用/source-target 无法表达。
4. MOMP 依赖 route-name→menu_code（MOMP.vue L277-283）+ versionContext（useMultiObjectPage.js L144），org 页无产品/版本。
5. 图表/状态快照键硬编码 `archManagerStateBeforeDiagram`（useMultiObjectPage.js L763）。

**关键代码路径**
- MOMP.vue L45-54（左树）、L61-121（MasterDetail/detail 区）、L277-283（menuCode）、L123-149（对话框）、L286-303（viewMode/provide chartConfig 联动）
- MOMP.vue 与 MetaListPage 的 slot 透传 L101-103（`#default` 转发 `$slots` 到每个 MetaListPage）
- useMultiObjectPage.js L116-196（scopeIds）、L282-412（过滤分发/构建）、L433-508（handleScopeChange/clearScope）、L763-890（状态快照）
- ObjectScopeSection.vue L43-74（树结构）、L434-534（store.setData expand 持久化）、L293-360（collectLeaf/collectInitialExpanded 防卡顿）、L582-686（搜索/全选/清空/silent刷新）

**ArchiData 对 MOMP 的全部耦合（泛化必须逐一保持，缺一即回归）**：
1. **slot 转发**：`#chart-config`、`#detailContent`、`#cell-source_bo_name` 等都经 MOMP `<template v-for in $slots #[slotName]>` 转发给 MetaListPage（L101-103）。
2. **provide**：MOMP 在 L286-303/347-349 provide `mompViewMode`、`refreshCoordinator`；ArchData 自身 provide `chartConfig`（ArchDataManagement.vue L117）供 RelationScopeTree inject。
3. **scopeTreeRef + _test 接口**：shortcut/applyScopeCode 依赖 `scopeTreeRef._test.treeData`（MOMP.vue L388、L436），那是 RelationScopeTree 暴露的测试钩子。
4. **scopeTreeKey 强制重建**：返回图表后按 key 重建左树恢复勾选（L293、L46）。
5. **menuCode 白名单**：仅 archdata/archdata-chart/archdata 系列（L279-282），org 页需扩展。
6. **versionContext / GlobalToolbar**：ArchData 依赖产品/版本选择；org 页 disableVersionContext 后该区不可再要求 version（涉及 GlobalToolbar 是否渲染版本选择器）。
7. **defaultTab / options**：ArchData 传 `{ defaultTab:'business_object' }`（ArchDataManagement.vue L99），泛化须向前兼容。

### 9.2 目标架构

- MOMP 从"ArchData 专用"升级为**通用多对象管理框架**，新增三组可注入钩子，默认值=ArchData 现状：
  1. `options.scopeTree`：左树组件 + propsProvider + 事件映射。
  2. `options.scopeAdapter`：树 scope 事件 → `scopeIds` 的统一适配器。
  3. `options.filterStrategies[type]`：per-tab 过滤策略注册表（内置 entity/association/relationship，允许覆盖/新增）。
  4. `options.menuCodeProvider` + `options.disableVersionContext`：解耦路由与版本上下文。
  5. `options.stateKey`：通用化状态快照键。

### 9.3 详细设计（Detailed Design）

**组件设计**
- `OrgScopeTree.vue`（新建，`src/components/common/OrgScopeTree/`）：
  - props: `initialOrgIds`, `scopeIds`(仅 `{org:{selected,effective}}`), 可选 `filterDisabled`。
  - 数据: 调 `OrgService.get_org_tree()`（返回嵌套 children）→ 直接作为 `treeData`（无需前端组装）；节点 `{id, name, parent_id, children}`。
  - 树: `show-checkbox + check-strictly=false`，`node-key='id'`（无前缀，纯 org id）。
  - emit `scope-change`：`{ orgIds, effectiveOrgIds }`（effective=选中∪子孙，复用 collectLeafKeys/递归 descendant 收集）。
  - UI: 工具栏(展开/收起/全选/清空/刷新) + 搜索 + 计数，对齐 ObjectScopeSection。
- 复用资产：把 ObjectScopeSection 的扩展开销逻辑**抽离或复制**为 OrgScopeTree 用（评估：ObjectScopeSection 强绑 versionId + 4级业务树 + type 前缀，**不适合直接复用**，新建单类型版本）。

**数据模型**
- `scopeIds.org = { selected: orgIds, effective: effectiveOrgIds }`。
- `scopeIds.org_relationship = { selected: [], effective: [] }`（预留）。

**API 设计**
- 前端 `orgService.getOrgTree()`（或复用现有能力），返回平铺 `[{id, name, parent_id, org_scope, org_category}]`。
- org 列表过滤：`id__in=[effectiveOrgIds]`。
- org_relationship（预留）：`source_org_id__in / target_org_id__in` 组合 + Union。

**主流程**
1. 进入 org 页 → MOMP 渲染注入 OrgScopeTree（master slot）+ org 列表 Tab。
2. 用户勾选 org 节点（级联）→ `scope-change({orgIds,effectiveOrgIds})` → OrgScopeAdapter 写入 `scopeIds.org.selected/effective` → filterStrategies['org'] 生成 `id__in=[effectiveOrgIds]` → MetaListPage 过滤刷新。
3. 导入导出/CRUD/状态快照全部复用 MOMP 现有能力。

**MOMP 泛化改动落点（谨慎评估 ArchData 影响）**
- MOMP.vue：master slot 改为 `<component :is="scopeTreeComponent" ...>`，默认 `RelationScopeTree` + 现有 props；`menuCode` 改由 `menuCodeProvider` 计算（默认现有推导）。
- useMultiObjectPage.js：
  - `handleScopeChange` 改为调用 `scopeAdapter(scope, scopeIds, ctx)`（默认现有映射函数）。
  - `_computeTypeFilters` 改为查 `filterStrategies`（默认 entity/association/relationship 策略 = 现有逻辑）。
  - versionContext 依据 `disableVersionContext` 短路 baseFilters。
  - 状态键用 `stateKey`(默认现有值)。
- **回归护栏**：所有这些默认 = 现状，ArchData 不传新参数 → 完全等价。新增单测断言默认路径行为不变。

### 9.4 备选方案对比（Alternatives Considered）

| 方案 | 优点 | 缺点 | 决策 |
|------|------|------|------|
| A. 新建独立 Org 页面，不泛化 MOMP | 改动小、零回归风险 | 与 MOMP 大量重复（外壳/Tab/懒加载/持久化）；后续 user/position 又要复制 | 拒绝 |
| B. 直接复用 RelationScopeTree 表达 org | 零新组件 | 强绑 versionId+4级业务树+type前缀，与 org 单类型自引用不匹配，改造成本≈重写 | 拒绝 |
| C. MOMP 泛化(左树注入+过滤策略接口)+ 新建 OrgScopeTree | 复用框架、org 树独立、向前兼容 | 需谨慎回归护栏 | **选定** |

### 9.5 实施与迁移计划（Implementation & Migration Plan）

**实施顺序**
1. MOMP 泛化（FR-001/002/003/008）：加可注入钩子，默认=现状。
2. 回归护栏：跑 ArchData 相关单测 + E2E，确认零回归。
3. OrgScopeTree 组件（FR-004）单测。
4. Org 管理页面（FR-005）+ versionContext 解耦联调。
5. org_relationship/user 预留槽位登记 + 文档（FR-006/007）。

**风险缓解**
- R1: MOMP 泛化破坏 ArchData → 缓解：默认参数=旧逻辑 + 回归单测 + E2E（NFR-001）。
- R2: org 树加载/级联卡顿 → 缓解：复用 collectLeafKeys/collectInitialExpandedKeys + silent 刷新（NFR-002，对齐 ObjectScopeSection L293-360/L434-534）。
- R3: 全量加载回退（用户强约束）→ 缓解：未选 org 时不发 `id__in` 或返回空；过滤策略绝不静默 `selectAll()`。

**测试策略**
- 单测：scopeAdapter（org 结构 → scopeIds）、filterStrategies['org']（为空/有选两种）、OrgScopeTree（级联勾选 effective 计算）、ObjectScopeSection 回归。
- 集成/E2E：org 页进入 →勾选父→列表过滤到子孙→刷新不丢选中。

**回滚方案**
- ArchData 不依赖新增参数，泛化单独可回退；org 页面独立于 ArchData，删除不影响。

### 9.6 org_relationship 预留设计（本期不实现）
```
# 目标（后置，后端需先建 org_relationship schema）
org_relationship: from_org_id / to_org_id / relation_family / relation_type / status ...
# 过滤（后置）
selectedOrgIds → (from_org_id__in=selected) OR (to_org_id__in=selected)
即: 与选中 org 存在任一向(发起/接收)关系的组织间关系记录
# 本期：仅 filterStrategies 注册表预留签名；不加入 objectTypes，不触发加载
```

---

## 10. TBD 清单（TBD List）

| ID | 条目 | 状态/缺失信息 | 下一步 |
|----|------|--------------|--------|
| TBD-1 | org 数据源字段 | ✅ 已核实：`get_org_tree` 返回嵌套 children(`id/name/code/parent_id/...`)，但**不含 org_type/org_scope/org_category** | 决策：树节点是否需展示类型标签，或仅 name |
| TBD-2 | org 页面路由/菜单命名 | 🟡 已建议（§7.4: `/system/org` + name `OrgManagement` + menu_code `org-management`） | 用户确认 |
| TBD-3 | org 列表可维护性 | ✅ 已确认：本期 **CRUD + 导入导出**维护 | 无需输入 |
| TBD-4 | user 预留 Tab | ✅ 已决策：**形态(b)** 仅接口预留，本期不暴露 UI | 无需输入 |
| TBD-5 | MOMP 泛化默认路径回归 | ✅ 设计为保证等价；需**单测+E2E 实证** | 实施阶段跑回归护栏 |
| TBD-6 | GlobalToolbar 在 disableVersionContext 下的行为 | ✅ 已决策：**保留刷新/导入/导出，仅隐藏产品/版本选择器** | 无需输入 |

---

## 附：规范完整性自查

- 本文档含 10 节，末节为「TBD 清单」，内容完整。
- 与 13/14 号一致性：org 默认不加字段（路线 A）；org_relationship 与 relationship 边界明确；position/user_org_assignment 后置哲学一致。
- MOMP 泛化对 ArchData 的接受标准：默认路径逐字节等价（NFR-001 + 回归护卫）。