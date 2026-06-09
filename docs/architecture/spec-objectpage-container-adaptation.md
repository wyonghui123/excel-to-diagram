## 目录

1. [1. Background & Objectives](#1-background-objectives)
2. [2. Requirement Type Overview](#2-requirement-type-overview)
3. [3. Functional Requirements](#3-functional-requirements)
4. [4. Nonfunctional Requirements](#4-nonfunctional-requirements)
5. [5. External Interface Requirements](#5-external-interface-requirements)
6. [6. Transition Requirements](#6-transition-requirements)
7. [7. Constraints & Assumptions](#7-constraints-assumptions)
8. [8. Priorities & Milestone Suggestions](#8-priorities-milestone-suggestions)
9. [9. Change / Design Proposal (RFC)](#9-change-design-proposal-(rfc))
10. [10. TBD List](#10-tbd-list)

---
# Spec: ObjectPage 容器适配与智能展示模式

## 1. Background & Objectives

### 1.1 Background

当前系统中 ObjectPage 是统一的对象详情渲染引擎，可在多种容器中展示：

- **FullPage**（PageShell + ObjectPage）：独立路由页面，如 `/product/:id`
- **Drawer**（DetailPage + ObjectPage）：侧边栏抽屉，从列表行点击触发
- **Dialog**（尚未实现）：对话框模式，适用于 AI Agent 交互等场景

**现状问题**：

1. **容器选择 hardcode**：`detail.mode` 在 YAML 中硬编码为 `drawer` 或 `page`，缺乏智能推导规则
2. **DetailPage 与 FullPage 配置来源不统一**：DetailPage 自行从 `metaService.getUIConfig` 加载配置并构建 sections/actions/fieldDefs，而 FullPage（如 `ProductDetailPage.vue`）也各自独立配置，逻辑重复
3. **后端 `detail.actions` 为空**：API 返回的 `ui_view_config.detail.actions` 始终为空数组，编辑/保存/取消/删除按钮由 DetailPage 自行生成，未与 YAML 配置打通
4. **ObjectPage 内部 editing 状态冲突**：ObjectPage 内部的 `handleObjectPageAction` 和外部容器（DetailPage）的 editing 状态管理存在双重控制
5. **容器模式不可切换**：用户在 Drawer 中发现内容复杂时，无法"展开"为 FullPage；反之也无法从 FullPage "收回"为 Drawer
6. **缺少 Dialog 容器**：AI Agent 交互场景需要轻量级 Dialog 展示对象详情，目前不支持
7. **Association Section 刚实现**：ObjectPage 新增了 `type: 'association'` section 支持，但与 Drawer/FullPage 的集成尚未完全验证

**已具备的基础设施**：

- `ObjectPage`：支持 sections（standard/association/custom/history）、actions、editing 模式
- `DetailPage`：Drawer 容器，内部已集成 ObjectPage
- `PageShell`：FullPage 容器（面包屑 + 标题栏 + 返回按钮）
- `MetaListPage`：YAML 驱动列表页
- `useParentChild`：父子关系 composable
- `ObjectChildSection`：子对象列表 Section 组件
- YAML Schema：已支持 `ui_view_config.detail`（facets/tabs/actions/mode）

### 1.2 Business Objectives

- **统一容器适配**：ObjectPage 内容可在 Drawer/FullPage/Dialog 三种容器中无缝渲染
- **智能模式推导**：系统根据 YAML 配置 + 上下文信息自动推导最优展示容器
- **配置驱动**：容器选择、sections 构建、actions 生成全部由 YAML 配置驱动，消除 hardcode
- **扩展性**：为 AI Agent 交互场景预留 Dialog 容器接口

### 1.3 User / Stakeholder Objectives

| 涉众 | 目标 |
|------|------|
| 终端用户 | 无论从列表点击还是导航进入，详情页体验一致 |
| 前端开发者 | 通过 YAML 配置即可控制容器模式，无需修改组件代码 |
| 架构师 | 容器适配层标准化，ObjectPage 渲染与容器解耦 |
| 产品经理 | AI Agent 交互场景中对象详情可嵌入对话流 |

---

## 2. Requirement Type Overview

| Type | Applicable | Evidence |
|------|-----------|----------|
| Business | Yes | 需要统一容器适配以提升开发效率和用户体验 |
| User/Stakeholder | Yes | 终端用户需要一致的详情页体验 |
| Solution | Yes | 需要新增 `useDetailMode` composable 和 `DetailDialog` 组件 |
| Functional | Yes | 详见 FR-001 ~ FR-008 |
| Nonfunctional | Yes | 详见 NFR-001 ~ NFR-003 |
| External Interface | Yes | YAML Schema 扩展、后端 API |
| Transition | Yes | 现有 DetailPage 需要重构 |

---

## 3. Functional Requirements

### FR-001: ObjectPage 容器无关渲染

- **Description**: ObjectPage 必须能在 Drawer、FullPage、Dialog 三种容器中无缝渲染，内部功能完全一致。
- **Acceptance Criteria**:
  - ObjectPage 在三种容器中渲染相同的 sections（standard/association/custom/history）
  - ObjectPage 在三种容器中渲染相同的 actions（编辑/保存/取消/删除）
  - 编辑模式（editing）在三种容器中行为一致
  - Association Tab（MetaListPage）在三种容器中正常工作
  - 审计日志 Tab 在三种容器中正常工作
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 当前实现分析 + 用户讨论

### FR-002: YAML `detail.mode` 配置

- **Description**: YAML Schema 必须支持 `detail.mode` 配置，控制对象详情的默认展示容器。
- **Acceptance Criteria**:
  - `detail.mode` 支持 `auto`、`drawer`、`page`、`dialog` 四种值
  - `auto` 模式下系统根据智能推导规则自动选择容器
  - 非 `auto` 模式下系统使用显式声明的容器
  - 后端 API 返回 `detail.mode` 配置
  - 当 `detail.mode` 缺失时，默认为 `auto`
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 用户讨论

### FR-003: 智能模式推导规则（`useDetailMode`）

- **Description**: 系统必须提供 `useDetailMode` composable，根据上下文信息智能推导最优展示容器。
- **Acceptance Criteria**:
  - 推导规则按优先级从高到低执行：
    1. YAML 显式声明 `mode: drawer/page/dialog` → 按声明
    2. 对象有 `child_sections`（子对象列表）→ `page`
    3. 对象有 association tabs ≥ 2 个 → `page`
    4. 对象字段 > 10 个 → `page`
    5. 触发来源为列表行点击（`triggerSource: 'list-row'`）→ `drawer`
    6. 触发来源为导航菜单/面包屑（`triggerSource: 'navigation'`）→ `page`
    7. 触发来源为 AI Agent 对话（`triggerSource: 'agent-dialog'`）→ `dialog`
    8. 默认 → `drawer`
  - 推导结果可通过 prop 或配置覆盖
  - 推导逻辑可单元测试
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 用户讨论 + 架构分析

### FR-004: DetailPage 配置统一化

- **Description**: DetailPage 的 sections/actions/fieldDefs 构建逻辑必须统一，与 FullPage 的 ObjectPage 配置来源一致。
- **Acceptance Criteria**:
  - DetailPage 从 `metaService.getUIConfig` 获取 `ui_view_config.detail` 配置
  - `computedSections` 同时支持 `detail.tabs` 和 `detail.facets` 两种 YAML 格式
  - `computedActions` 优先使用 YAML `detail.actions`，缺失时自动生成 edit/save/cancel/delete
  - `computedFieldDefs` 根据 editing 状态动态切换 editable
  - 后端 `detail.actions` 返回完整的 action 配置（edit/save/cancel/delete）
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 当前代码分析

### FR-005: DetailDialog 容器组件

- **Description**: 系统必须提供 `DetailDialog` 组件，作为 Dialog 容器嵌入 ObjectPage。
- **Acceptance Criteria**:
  - 使用 `el-dialog` 实现，支持 `modelValue`、`objectType`、`id` props
  - 内部集成 ObjectPage，与 DetailPage 功能等价
  - 支持 `size` prop 控制 Dialog 宽度（sm/md/lg）
  - 支持编辑模式（editing/save/cancel）
  - 关闭时重置 editing 状态
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: AI Agent 交互场景需求

### FR-006: ObjectPage editing 状态管理统一

- **Description**: ObjectPage 的 editing 状态管理必须统一，避免内部和外部双重控制。
- **Acceptance Criteria**:
  - ObjectPage 通过 `editing` prop 接收外部 editing 状态
  - ObjectPage 内部 `handleObjectPageAction` 不再自行设置 `internalEditing`，而是 emit `action` 事件
  - 外部容器（DetailPage/DetailDialog/FullPage）负责 editing 状态管理
  - `editing` prop 变化时 ObjectPage 内部 `internalEditing` 同步更新
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 当前代码分析（双重 editing 状态冲突）

### FR-007: 触发来源（triggerSource）传递机制

- **Description**: 系统必须支持在打开详情时传递触发来源信息，供智能推导使用。
- **Acceptance Criteria**:
  - MetaListPage 行操作点击时传递 `triggerSource: 'list-row'`
  - 导航菜单/面包屑点击时传递 `triggerSource: 'navigation'`
  - AI Agent 交互时传递 `triggerSource: 'agent-dialog'`
  - `triggerSource` 通过 MetaListPage emit 事件或路由 query 参数传递
  - DetailPage/DetailDialog 接收 `triggerSource` 并传给 `useDetailMode`
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: 智能推导规则需要

### FR-008: 后端 `detail.actions` 动态返回

- **Description**: 后端 API 必须返回动态的 `detail.actions` 配置，前端不再自行生成默认 actions。Actions 应根据对象类型、用户权限、对象状态等上下文动态生成。
- **Acceptance Criteria**:
  - `GET /api/v2/meta/:objectType/ui-config` 返回 `ui_view_config.detail.actions`
  - actions 是**动态的**：根据以下维度返回不同的 actions：
    - **对象类型维度**：不同 objectType 有不同的标准 actions（如 role 有 grant/revoke，product 有 activate/deactivate）
    - **用户权限维度**：当前用户无编辑权限时不返回 edit/save actions，无删除权限时不返回 delete action
    - **对象状态维度**：对象已归档时不返回 edit/delete，对象为草稿状态时返回 publish action
  - actions 包含标准操作配置（edit/save/cancel/delete）及自定义操作
  - 前端在 `detail.actions` 为空时仍提供默认 actions 兜底
  - actions 配置包含 `condition` 字段支持前端条件显示（如 `condition: "editing"` 表示仅在编辑模式显示）
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 当前 API 返回 actions 为空数组 + 用户确认 actions 需动态化

### FR-009: 容器模式手动切换

- **Description**: 用户必须能在 Drawer 和 FullPage 之间手动切换容器模式，保持当前状态不丢失。这是三层决策模型的最终层——系统给出智能默认，用户拥有最终决定权。
- **Acceptance Criteria**:
  - Drawer 右上角显示"展开"按钮（↗ 图标），点击后切换为 FullPage
  - FullPage 右上角显示"收回"按钮（↙ 图标），点击后切换为 Drawer（仅当从 Drawer 展开而来时显示）
  - 切换时保持当前状态：editing 状态、active tab、form data（含未保存修改）、滚动位置
  - Drawer → FullPage 时自动 push 路由（URL 可书签），query 携带 `expanded=true`
  - FullPage → Drawer 时自动 replace 路由（避免历史污染）
  - 切换按钮位于 ObjectPage header 右侧，状态 badge 旁边
  - 切换动画平滑，不闪烁
  - 智能推导给出默认模式，用户手动切换覆盖默认模式
  - 直接通过 URL 访问 FullPage 时不显示"收回"按钮（无前置 Drawer 上下文）
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 用户讨论 + 业界成熟模式（Jira/Slack/VS Code/Notion）

#### FR-009 附：三层决策模型

容器模式的选择遵循三层决策模型，优先级从高到低：

```
Layer 1: YAML 静态声明（业务默认值）
  detail.mode: drawer | page
  → 适用于业务规则明确的场景，如"角色详情永远在 Drawer 中打开"

Layer 2: useDetailMode 智能推导（上下文感知）
  根据 triggerSource / 字段数 / association 数 / child_sections 推导
  → 适用于同一对象在不同上下文中需要不同容器的场景

Layer 3: 用户手动切换（最终决定权）
  点击 ↗/↙ 按钮覆盖推导结果
  → 适用于系统推荐不符合用户当前需求的场景
```

**业界参考**：

| 产品 | 默认模式 | 切换后模式 | 切换触发 |
|------|---------|-----------|---------|
| Jira | Board → Side Panel | Side Panel → Full Page | 点击"查看全部" |
| Slack | Thread → 侧边栏 | 侧边栏 → 独立窗口 | 点击"Pop out" |
| VS Code | 单击 → Preview Tab | Preview → Pinned Tab | 双击 |
| Notion | 链接 → Peek View | Peek → Full Page | 点击"Open as Page" |

**本系统设计**：

| 场景 | Layer 1 (YAML) | Layer 2 (推导) | Layer 3 (用户) |
|------|---------------|---------------|---------------|
| 列表点击简单对象 | auto | drawer | 可 ↗ 展开 |
| 列表点击复杂对象 | auto | page | 可 ↙ 收回 |
| 导航菜单进入 | auto | page | — |
| YAML 显式声明 drawer | drawer | drawer | 可 ↗ 展开 |
| YAML 显式声明 page | page | page | — |

---

## 4. Nonfunctional Requirements

### NFR-001: 渲染一致性

- **Description**: ObjectPage 在三种容器中的渲染结果必须功能等价。
- **Measurement**: E2E 测试验证同一对象在 Drawer/FullPage/Dialog 中的字段数、Tab 数、Action 数一致。
- **Priority**: Must
- **Source**: 用户体验一致性要求

### NFR-002: 智能推导可测试性

- **Description**: `useDetailMode` 的推导逻辑必须 100% 可单元测试。
- **Measurement**: 推导规则的每个分支都有对应的单元测试用例。
- **Priority**: Should
- **Source**: 代码质量要求

### NFR-003: 向后兼容性

- **Description**: 新架构必须兼容现有的 DetailPage、PageShell、ObjectPage 使用方式。
- **Measurement**: 所有现有页面在无修改的情况下正常运行。
- **Priority**: Must
- **Source**: 迁移要求

---

## 5. External Interface Requirements

### IF-001: YAML Schema `detail` 配置

- **Type**: System Integration
- **Endpoint**: `GET /api/v2/meta/:objectType/ui-config`
- **Request/Response**:
  ```yaml
  ui_view_config:
    detail:
      # mode: 前端 useDetailMode 自行推导，后端暂不返回此字段
      # 未来可扩展：mode: auto | drawer | page | dialog
      actions:
        - id: edit
          key: edit
          label: 编辑
          icon: edit
          variant: primary
          condition: "!editing"        # 仅非编辑模式显示
          permission: "edit"           # 需要编辑权限
        - id: save
          key: save
          label: 保存
          icon: save
          variant: primary
          condition: "editing"         # 仅编辑模式显示
          permission: "edit"
        - id: cancel
          key: cancel
          label: 取消
          icon: close
          variant: secondary
          condition: "editing"         # 仅编辑模式显示
        - id: delete
          key: delete
          label: 删除
          icon: delete
          variant: danger
          condition: "!editing"
          permission: "delete"
          state_filter: ["active"]     # 仅 active 状态对象可删除
        - id: activate
          key: activate
          label: 启用
          icon: check
          variant: primary
          condition: "!editing"
          permission: "edit"
          state_filter: ["draft"]      # 仅 draft 状态可启用
      tabs: [...]          # 现有格式
      facets: [...]        # 现有格式
  ```
- **Error Handling**: `actions` 缺失时前端兜底生成默认 edit/save/cancel/delete；`condition` 缺失时默认始终显示
- **Dynamic Actions**: 后端根据请求上下文（用户权限、对象状态）动态过滤 actions 列表，仅返回当前用户可执行的 actions
- **Source**: 技术设计 + 用户确认 actions 需动态化

### IF-002: 触发来源传递接口

- **Type**: UI
- **Entry Point**: MetaListPage emit `detail` 事件 + 路由 query 参数
- **Interaction**:
  - MetaListPage: `emit('detail', { row, triggerSource: 'list-row' })`
  - 路由跳转: `router.push({ path: '/product/70', query: { source: 'navigation' } })`
  - AI Agent: `openDetail({ objectType, id, triggerSource: 'agent-dialog' })`
- **Error Handling**: `triggerSource` 缺失时默认 `list-row`
- **Source**: 技术设计

---

## 6. Transition Requirements

### TR-001: DetailPage 重构

- **Description**: 现有 DetailPage 需要重构为配置驱动模式，消除 hardcode 逻辑。
- **Strategy**:
  1. Phase 1：修复 ObjectPage editing 状态双重控制问题（FR-006）
  2. Phase 2：统一 DetailPage 的 sections/actions/fieldDefs 构建逻辑（FR-004）
  3. Phase 3：实现 `useDetailMode` composable（FR-003）
  4. Phase 4：实现 `DetailDialog` 组件（FR-005）
  5. Phase 5：后端扩展 `detail.actions` 返回（FR-008）
  6. Phase 6：实现 `triggerSource` 传递机制（FR-007）
- **Rollback Plan**: 每个 Phase 独立提交，发现问题可快速回滚
- **Source**: 迁移策略

---

## 7. Constraints & Assumptions

### 7.1 Technical Constraints

- 必须使用 Vue 3 Composition API + Element Plus
- 必须兼容现有的 `MetaListPage`、`ObjectPage`、`DetailPage`、`PageShell`
- 必须使用 YAML Schema 驱动配置
- 路由使用 Vue Router 4.x
- 智能布局引擎（动态 Section 类型注册表）不在本期范围，记入 Backlog

### 7.2 Business Constraints

- AI Agent 交互场景的 Dialog 需求优先级为 Should，本期实现基础支持
- 智能推导规则需要可配置覆盖，不能完全替代人工判断

### 7.3 Assumptions

- ~~后端可以扩展 `detail.mode` 配置返回~~ → ✅ 暂不扩展后端，前端 useDetailMode 自行推导
- 后端可以扩展 `detail.actions` 动态返回（根据对象类型、用户权限、对象状态） — Source: 待确认
- `triggerSource` 通过 emit 事件传递即可满足需求，不需要全局状态管理 — Source: 已验证
- ObjectPage 的 `editing` prop 双向绑定机制可以解决状态冲突 — Source: 已验证
- 容器模式切换的状态保持使用 SessionStorage + Route Query 方案 — Source: 已分析验证

---

## 8. Priorities & Milestone Suggestions

| ID | Requirement | Priority | Reason |
|----|-------------|----------|--------|
| FR-001 | ObjectPage 容器无关渲染 | Must | 核心架构要求 |
| FR-006 | editing 状态管理统一 | Must | 当前存在 bug，阻塞其他功能 |
| FR-004 | DetailPage 配置统一化 | Must | 消除 hardcode，配置驱动 |
| FR-008 | 后端 detail.actions 动态返回 | Must | actions 需根据权限/状态动态化 |
| FR-009 | 容器模式手动切换 | Must | 核心用户体验，渐进式披露 |
| FR-003 | `useDetailMode` composable | Must | 智能推导核心逻辑 |
| FR-002 | YAML `detail.mode` 前端消费 | Must | 智能推导的前提（前端推导，不扩展后端） |
| NFR-001 | 渲染一致性 | Must | 用户体验底线 |
| NFR-003 | 向后兼容性 | Must | 迁移安全 |
| FR-005 | DetailDialog 容器 | Deferred | AI Agent 场景暂不实现 |
| FR-007 | triggerSource 传递 | Should | 智能推导增强 |
| NFR-002 | 推导可测试性 | Should | 代码质量 |

- **Suggested Milestones**:
  - **Milestone 1**: FR-006 + FR-004 — 修复 editing 状态 + 统一配置
  - **Milestone 2**: FR-008 + FR-003 + FR-002 — 后端 actions 动态化 + 智能推导 + 前端 mode 消费
  - **Milestone 3**: FR-009 — 容器模式手动切换（useDetailContainer + ObjectPage expand/collapse）
  - **Milestone 4**: FR-007 — triggerSource 传递
  - **Deferred**: FR-005（DetailDialog）— AI Agent 场景暂不实现

---

## 9. Change / Design Proposal (RFC)

### 9.1 As-Is Analysis

**Current Architecture**:

```
┌─────────────────────────────────────────────────────────────┐
│  FullPage (PageShell + ObjectPage)                          │
│  - 各页面自行配置 sections/actions/fieldDefs                 │
│  - editing 状态由页面自行管理                                 │
│  - 容器选择 hardcode 在路由配置中                             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  Drawer (DetailPage + ObjectPage)                           │
│  - DetailPage 自行加载 meta + 构建 sections/actions         │
│  - editing 状态由 DetailPage 管理，但 ObjectPage 内部        │
│    handleObjectPageAction 也设置 internalEditing（双重控制）  │
│  - 容器选择 hardcode 为 drawer                               │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  Dialog (未实现)                                             │
│  - 无 Dialog 容器支持                                        │
│  - AI Agent 交互场景无法嵌入对象详情                           │
└─────────────────────────────────────────────────────────────┘
```

**Current Issues**:

1. **editing 双重控制**：ObjectPage 内部 `handleObjectPageAction` 设置 `internalEditing`，外部容器也设置 `editing` prop，两者可能冲突
2. **配置来源不统一**：DetailPage 自行构建 sections/actions，FullPage 各自配置
3. **容器选择 hardcode**：没有智能推导，YAML `detail.mode` 未被消费
4. **后端 actions 为空**：前端兜底逻辑与 YAML 配置割裂
5. **缺少 Dialog**：AI Agent 场景无法使用

**Relevant Code Paths**:

- `src/components/common/ObjectPage/ObjectPage.vue` — 对象页容器
- `src/components/common/DetailPage/DetailPage.vue` — Drawer 容器
- `src/components/common/PageShell/PageShell.vue` — FullPage 容器
- `src/composables/useMetaList.js` — 列表逻辑（含 `openDetailDrawer`）
- `src/views/ProductManagement/ProductDetailPage.vue` — FullPage 示例
- `src/views/SystemManagement/RolePermissionDetail.vue` — FullPage 示例

### 9.2 Target State

**Proposed Architecture**:

```
┌─────────────────────────────────────────────────────────────┐
│  YAML Schema (配置层)                                        │
│  - detail.mode: auto | drawer | page | dialog               │
│  - detail.actions: [edit, save, cancel, delete, ...]        │
│  - detail.tabs / detail.facets: [...]                        │
└─────────────────────────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────────────────────────┐
│  useDetailMode (推导层)                                      │
│  - 输入: entityMeta + triggerSource + context               │
│  - 输出: inferredMode (drawer | page | dialog)              │
│  - 推导规则按优先级执行                                       │
└─────────────────────────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────────────────────────┐
│  容器适配层 (Container Layer)                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │ DetailPage│  │PageShell │  │DetailDia-│                  │
│  │ (Drawer) │  │(FullPage)│  │  log     │                  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                  │
│       └──────────┬───┘──────────┘                          │
│                  ↓                                           │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  ObjectPage (渲染引擎)                                 │  │
│  │  - sections (standard/association/custom/history)      │  │
│  │  - actions (edit/save/cancel/delete)                   │  │
│  │  - editing (外部控制)                                   │  │
│  │  - fieldDefs (动态 editable)                            │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**Key Changes**:

1. ObjectPage `handleObjectPageAction` 不再自行设置 `internalEditing`，改为纯 emit
2. 新增 `useDetailMode` composable — 智能推导展示容器
3. 新增 `DetailDialog` 组件 — Dialog 容器
4. DetailPage 配置逻辑统一化 — sections/actions/fieldDefs 全部从 YAML 驱动
5. 后端扩展 `detail.mode` 和 `detail.actions` 返回
6. MetaListPage 支持 `triggerSource` 传递

### 9.3 Detailed Design

#### 9.3.1 `useDetailMode` Composable

```javascript
// src/composables/useDetailMode.js
export function useDetailMode(entityMeta, triggerSource, options = {}) {
  const inferredMode = computed(() => {
    const detailConfig = entityMeta.value?.ui_view_config?.detail

    // Rule 1: YAML 显式声明（非 auto）
    if (detailConfig?.mode && detailConfig.mode !== 'auto') {
      return detailConfig.mode
    }

    // Rule 2: 有 child_sections → page
    const childSections = entityMeta.value?.ui_view_config?.child_sections || []
    if (childSections.length > 0) return 'page'

    // Rule 3: association tabs ≥ 2 → page
    const tabs = detailConfig?.tabs || []
    const facets = detailConfig?.facets || []
    const assocCount = tabs.filter(t => t.type === 'association').length
      + facets.filter(f => f.type === 'association').length
    if (assocCount >= 2) return 'page'

    // Rule 4: 字段 > 10 → page
    const visibleFields = (entityMeta.value?.fields || [])
      .filter(f => f.ui?.visible !== false)
    if (visibleFields.length > 10) return 'page'

    // Rule 5-7: triggerSource 推导
    const source = triggerSource.value || triggerSource
    if (source === 'list-row') return 'drawer'
    if (source === 'navigation') return 'page'
    if (source === 'agent-dialog') return 'dialog'

    // Rule 8: 默认 drawer
    return 'drawer'
  })

  return { inferredMode }
}
```

#### 9.3.2 ObjectPage editing 状态统一

**改动**：ObjectPage 的 `handleObjectPageAction` 不再自行设置 `internalEditing`，改为纯 emit：

```javascript
// Before (当前):
function handleObjectPageAction(action) {
  if (action.key === 'edit') {
    internalEditing.value = true        // ← 双重控制
    emit('update:editing', true)
    emit('action', { action, editing: true })
    return
  }
  // ...
}

// After (修改后):
function handleObjectPageAction(action) {
  if (action.key === 'edit') {
    emit('update:editing', true)        // ← 只 emit，不自行设置
    emit('action', { action, editing: true })
    return
  }
  if (action.key === 'cancel') {
    emit('update:editing', false)
    emit('cancel')
    emit('action', { action, editing: false })
    return
  }
  // save/delete 同理，只 emit
  emit('action', { action })
}
```

ObjectPage 的 `internalEditing` 完全由 `props.editing` 驱动（通过 watch 同步）。

#### 9.3.3 DetailDialog 组件

```vue
<!-- src/components/common/DetailDialog/DetailDialog.vue -->
<template>
  <el-dialog
    :model-value="visible"
    :title="dialogTitle"
    :width="dialogWidth"
    destroy-on-close
    @close="handleClose"
  >
    <div class="detail-dialog">
      <!-- 与 DetailPage 结构一致，使用 ObjectPage 渲染 -->
      <div v-if="loading" class="dd-loading">...</div>
      <div v-else-if="error" class="dd-error">...</div>
      <div v-else-if="!data" class="dd-empty">...</div>
      <div v-else class="dd-content">
        <ObjectPage
          v-if="metaLoaded"
          :title="dialogTitle"
          :sections="computedSections"
          :form-data="data"
          :field-definitions="computedFieldDefs"
          :actions="computedActions"
          :editing="internalEditing"
          :saving="saving"
          :auto-load-meta="false"
          :object-type="objectType"
          :object-id="id"
          size="sm"
          @action="handleObjectPageAction"
          @field-update="handleFieldUpdate"
        />
      </div>
    </div>
    <template #footer>
      <AppButton variant="secondary" @click="handleClose">关闭</AppButton>
    </template>
  </el-dialog>
</template>
```

#### 9.3.4 MetaListPage triggerSource 传递

```javascript
// MetaListPage.vue 修改
function openDetailDrawer(row, isCreate = false) {
  selectedDetailId.value = isCreate ? null : row.id
  detailCreateMode.value = isCreate
  showDetailDrawer.value = true
  detailTriggerSource.value = 'list-row'  // ← 新增
}
```

DetailPage 接收 `triggerSource` prop：

```vue
<DetailPage
  v-model="showDetailDrawer"
  :object-type="objectType"
  :id="selectedDetailId"
  :trigger-source="detailTriggerSource"
/>
```

#### 9.3.5 Data Model

**YAML Schema 扩展**:

```yaml
# product.yaml
ui_view_config:
  detail:
    mode: auto                # auto | drawer | page | dialog
    actions:
      - id: edit
        key: edit
        label: 编辑
        icon: edit
        variant: primary
      - id: delete
        key: delete
        label: 删除
        icon: delete
        variant: danger
    facets:
      - type: fieldGroup
        title: 基本信息
        fields: [name, code, description, is_active]
      - type: fieldGroup
        title: 系统信息
        fields: [created_at, updated_at, created_by, updated_by]
```

#### 9.3.6 容器模式手动切换（FR-009）

**核心交互**：

```
Drawer 模式:
┌──────────────────────────────┐
│ 产品详情        [↗] [编辑] [×]│  ← ↗ 展开按钮
│ ┌──────────────────────────┐ │
│ │ ObjectPage               │ │
│ │ activeTab: basic         │ │
│ │ editing: false           │ │
│ └──────────────────────────┘ │
└──────────────────────────────┘

点击 ↗ → 状态转移 → FullPage 模式:
┌─────────────────────────────────────────────────┐
│ ‹ 返回  产品管理 › ERP系统      [↙] [编辑]      │  ← ↙ 收回按钮（仅 expanded 来源时显示）
│ ┌───────────────────────────────────────────────┐│
│ │ ObjectPage (状态保留)                          ││
│ │ activeTab: basic (保留)                        ││
│ │ editing: false (保留)                          ││
│ └───────────────────────────────────────────────┘│
└─────────────────────────────────────────────────┘
```

**状态保持技术方案：SessionStorage + Route Query**

选择 SessionStorage 而非 Pinia/Provide-Inject 的原因：
- Drawer 和 FullPage **不会同时挂载**——Drawer 关闭后才导航到 FullPage
- 两者之间没有组件生命周期重叠，provide/inject 无法跨生命周期传递状态
- SessionStorage 按标签页隔离，不会串扰，且页面刷新后自动清除

```javascript
// src/composables/useDetailContainer.js
const STATE_KEY_PREFIX = 'detail_state_'

export function useDetailContainer(objectType, id, options = {}) {
  const router = useRouter()
  const route = useRoute()

  const currentMode = ref(options.initialMode || 'drawer')
  const canCollapse = computed(() => route.query.expanded === 'true')

  function _stateKey() {
    return `${STATE_KEY_PREFIX}${objectType.value || objectType}_${id.value || id}`
  }

  function preserveState(stateSource) {
    const state = {
      activeTab: stateSource.activeTab?.value || null,
      editing: stateSource.editing?.value || false,
      formData: stateSource.formData?.value || null,
      scrollTop: stateSource.scrollTop?.value || 0,
      timestamp: Date.now()
    }
    sessionStorage.setItem(_stateKey(), JSON.stringify(state))
  }

  function restoreState() {
    const raw = sessionStorage.getItem(_stateKey())
    if (!raw) return null
    try {
      const state = JSON.parse(raw)
      if (Date.now() - state.timestamp > 30 * 60 * 1000) {
        sessionStorage.removeItem(_stateKey())
        return null
      }
      sessionStorage.removeItem(_stateKey())
      return state
    } catch {
      sessionStorage.removeItem(_stateKey())
      return null
    }
  }

  function expandToFullPage(stateSource) {
    preserveState(stateSource)
    currentMode.value = 'page'
    router.push({
      path: `/${objectType.value || objectType}/${id.value || id}`,
      query: { ...route.query, expanded: 'true' }
    })
  }

  function collapseToDrawer(stateSource) {
    preserveState(stateSource)
    currentMode.value = 'drawer'
    router.back()
  }

  return {
    currentMode,
    canCollapse,
    preserveState,
    restoreState,
    expandToFullPage,
    collapseToDrawer
  }
}
```

**边界情况处理**：

| 边界情况 | 处理策略 |
|---------|---------|
| 编辑中切换（Drawer → FullPage） | 保留 editing=true + 未保存的 formData |
| 浏览器刷新 FullPage | `?expanded=true` 仍在但 sessionStorage 已清空 → 正常加载（不恢复状态） |
| 直接访问 FullPage URL（无前置 Drawer） | 不显示"收回"按钮（`canCollapse = route.query.expanded === 'true'`） |
| 多标签页 | sessionStorage 按标签页隔离，不会串扰 |
| 状态过期 | 超过 30 分钟的 preserved state 自动丢弃 |
| Drawer 中有未保存修改 | 切换前提示用户"有未保存的修改，是否继续？"（可选，v2） |

**ObjectPage 切换按钮**：

```vue
<!-- ObjectPage header 右侧 -->
<div class="object-page__header-right">
  <span v-if="status" :class="['status-badge', ...]">{{ status }}</span>

  <!-- 容器模式切换按钮 -->
  <AppButton
    v-if="containerMode === 'drawer'"
    variant="text"
    size="sm"
    title="展开为全屏页面"
    @click="$emit('expand')"
  >
    <AppIcon name="expand" size="sm" />
  </AppButton>
  <AppButton
    v-if="containerMode === 'page' && canCollapse"
    variant="text"
    size="sm"
    title="收回为侧边栏"
    @click="$emit('collapse')"
  >
    <AppIcon name="collapse" size="sm" />
  </AppButton>

  <!-- YAML-Driven 操作按钮 -->
  <div v-if="hasActionsConfig" class="op-actions">...</div>
</div>
```

**ObjectPage 新增 Props**：

```typescript
defineProps({
  // ... 现有 props
  containerMode: {
    type: String,
    default: 'page',       // 'drawer' | 'page' | 'dialog'
    validator: v => ['drawer', 'page', 'dialog'].includes(v)
  },
  canCollapse: {
    type: Boolean,
    default: false          // 仅从 Drawer 展开而来时为 true
  }
})

defineEmits([
  // ... 现有 emits
  'expand',                 // Drawer → FullPage
  'collapse'                // FullPage → Drawer
])
```

#### 9.3.7 Main Flows

**Flow 1: 列表行点击 → 智能推导 → Drawer**

```
用户 → 产品列表 → 点击"查看"按钮
  → MetaListPage emit('detail', { row, triggerSource: 'list-row' })
  → useDetailMode 推导: product 无 child_sections, 无 association, 字段≤10, triggerSource='list-row'
  → 推导结果: drawer
  → 打开 DetailPage(Drawer) + ObjectPage
```

**Flow 2: 导航菜单 → 智能推导 → FullPage**

```
用户 → 侧边栏"产品管理" → 点击某个产品
  → 路由跳转 /product/:id?source=navigation
  → useDetailMode 推导: triggerSource='navigation'
  → 推导结果: page
  → 打开 PageShell + ObjectPage
```

**Flow 3: AI Agent → 智能推导 → Dialog**

```
AI Agent → 需要展示对象详情
  → openDetail({ objectType: 'product', id: 70, triggerSource: 'agent-dialog' })
  → useDetailMode 推导: triggerSource='agent-dialog'
  → 推导结果: dialog
  → 打开 DetailDialog + ObjectPage
```

**Flow 4: 有子对象的详情 → 智能推导 → FullPage**

```
用户 → 枚举类型列表 → 点击"查看"
  → useDetailMode 推导: enum_type 有 child_sections=[enum_value]
  → 推导结果: page（即使 triggerSource='list-row'）
  → 打开 PageShell + ObjectPage（含枚举值列表 Section）
```

**Flow 5: Drawer → 手动切换 → FullPage**

```
用户 → 产品列表 → 点击"查看" → Drawer 打开
  → 在 Drawer 中浏览详情，发现需要更多空间
  → 点击 ↗ 展开按钮
  → 保存当前状态（activeTab, editing, formData）
  → 路由 push 到 /product/70?expanded=true
  → FullPage 打开，恢复状态
  → 用户在 FullPage 中继续操作
```

**Flow 6: FullPage → 手动切换 → Drawer**

```
用户 → 从导航进入 /product/70 → FullPage 打开
  → 浏览完毕，点击 ↙ 收回按钮
  → 保存当前状态
  → 路由 back 回列表页
  → Drawer 打开，恢复状态
```

### 9.4 Alternatives Considered

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| A. 完全 YAML 声明（无 auto） | 简单、可预测 | 每个对象都需要配置、无法适应上下文变化 | Rejected |
| B. 纯智能推导（无 YAML 覆盖） | 零配置 | 推导可能不符合业务需求、无法覆盖 | Rejected |
| C. YAML 声明 + 智能推导（auto 模式） | 兼顾配置灵活性和零配置默认行为 | 推导规则需要维护 | **Selected** |
| D. 全局状态管理 triggerSource | 跨组件传递方便 | 过度设计、增加复杂度 | Rejected（emit 事件足够） |

**Rationale for Selection**:

- Option C 兼顾了配置灵活性和零配置默认行为
- `auto` 模式让大多数对象无需配置即可获得合理的容器选择
- 显式声明允许业务需求覆盖推导结果
- emit 事件传递 triggerSource 足够轻量，不需要全局状态

### 9.5 Implementation & Migration Plan

**Implementation Order**:

1. **Step 1**: 修复 ObjectPage editing 状态双重控制（FR-006）
   - 修改 `handleObjectPageAction` 为纯 emit
   - 确保 `internalEditing` 完全由 `props.editing` 驱动
2. **Step 2**: 统一 DetailPage 配置逻辑（FR-004）
   - 确认 `computedSections`/`computedActions`/`computedFieldDefs` 逻辑正确
   - 添加后端 `detail.actions` 兜底逻辑
3. **Step 3**: 后端扩展 `detail.actions` 动态返回（FR-008）
   - 后端根据对象类型、用户权限、对象状态返回不同的 actions
   - 前端消费 `detail.actions`
4. **Step 4**: 实现 `useDetailMode` composable（FR-003）
   - 编写推导规则
   - 编写单元测试
5. **Step 5**: 扩展 YAML `detail.mode` 前端消费（FR-002）
   - 前端读取 `detail.mode` 并传给 `useDetailMode`
6. **Step 6**: 实现容器模式手动切换（FR-009）
   - 实现 `useDetailContainer` composable
   - ObjectPage 添加 expand/collapse 按钮
   - DetailPage 支持 expand → FullPage
   - FullPage 支持 collapse → Drawer
7. **Step 7**: 实现 `DetailDialog` 组件（FR-005）
   - 复用 DetailPage 的配置逻辑
   - 使用 `el-dialog` 容器
8. **Step 8**: 实现 `triggerSource` 传递（FR-007）
   - MetaListPage emit `triggerSource`
   - DetailPage/DetailDialog 接收 `triggerSource`
9. **Step 9**: E2E 测试覆盖

**Risk Mitigation**:

| Risk | Mitigation |
|------|-----------|
| editing 状态修改导致现有页面崩溃 | 修改后全面 E2E 测试 |
| 智能推导规则不符合业务预期 | 提供 YAML 显式声明覆盖 |
| DetailDialog 与 DetailPage 代码重复 | 提取共享逻辑到 composable |
| 后端不返回 detail.actions | 前端兜底生成默认 actions |

**Testing Strategy**:

- **Unit tests**: `useDetailMode` 推导规则每个分支
- **Integration tests**: DetailPage + ObjectPage editing 状态同步
- **E2E tests**: Drawer/FullPage/Dialog 三种容器的字段、Tab、Action 一致性

**Rollback Plan**:

- 每个 Step 独立 Git 提交
- 使用 feature 分支开发
- 发现问题可快速回滚到主分支

---

## 10. TBD List

| ID | Item | Missing Information | Next Step |
|----|------|-------------------|-----------|
| ~~TBD-1~~ | ~~后端 `detail.mode` 返回~~ | ✅ 暂不扩展后端，前端 useDetailMode 自行推导 | FR-002 改为"前端消费"，不依赖后端返回 mode |
| TBD-2 | 后端 `detail.actions` 动态返回 | actions 需根据对象类型、用户权限、对象状态动态返回 | 与后端确认实现方案，定义 actions 动态生成规则 |
| ~~TBD-3~~ | ~~智能推导规则阈值~~ | ✅ 字段 > 10 和 association ≥ 2 已确认 | 实现时验证 |
| TBD-4 | 容器模式切换的状态保持方案 | ✅ 已确定 SessionStorage + Route Query 方案 | Milestone 3 实现时验证编辑中切换场景 |
| TBD-5 | `detail.actions` 动态化规则定义 | 需定义各 objectType 的标准 actions + 权限/状态条件映射 | 与后端确认 actions 动态生成引擎设计 |

### Backlog（不在本期范围）

| ID | Item | Description |
|----|------|-------------|
| BL-1 | 智能布局引擎 | 动态 Section 类型注册表（chart/timeline/agent-interaction），根据内容自动选择最优布局 |
| BL-2 | 四级层级页面标准化 | Domain/SubDomain/ServiceModule/BusinessObject 使用标准化父子模式重构 |
| BL-3 | 路由自动生成 | 基于 YAML `parent_object` 自动生成父子路由 |
| BL-4 | DetailDialog + AI Agent 集成 | Dialog 容器与 AI Agent 交互的集成方式（FR-005 Deferred） |
| BL-5 | `detail.mode` 后端扩展 | 后端返回 mode 配置，前端 useDetailMode 可消费后端声明 |

### 实现状态

| 功能 | 状态 | 文件 |
|------|------|------|
| ObjectPage `type: 'association'` section | ✅ 已完成 | `ObjectPage.vue` |
| DetailPage 集成 ObjectPage | ✅ 已完成 | `DetailPage.vue` |
| DetailPage computedSections 支持 tabs/facets | ✅ 已完成 | `DetailPage.vue` |
| DetailPage computedActions 自动生成 | ✅ 已完成 | `DetailPage.vue` |
| DetailPage editing/save/cancel/delete | ✅ 已完成 | `DetailPage.vue` |
| ProductVersionApp 迁移 | ✅ 已完成 | `ProductListPage.vue` + `ProductDetailPage.vue` |
| ObjectPage editing 双重控制修复 | ❌ 待实现 | `ObjectPage.vue` |
| `useDetailMode` composable | ❌ 待实现 | 新文件 |
| `useDetailContainer` composable | ❌ 待实现 | 新文件 |
| ObjectPage expand/collapse 按钮 | ❌ 待实现 | `ObjectPage.vue` |
| ObjectPage containerMode/canCollapse props | ❌ 待实现 | `ObjectPage.vue` |
| 后端 `detail.actions` 动态返回 | ❌ 待实现 | 后端 |
| `triggerSource` 传递机制 | ❌ 待实现 | `MetaListPage.vue` |
| DetailDialog 组件 | ⏸️ Deferred | 新文件 |

---

Spec + RFC contain 10 sections, last section is "TBD List", content is complete.
