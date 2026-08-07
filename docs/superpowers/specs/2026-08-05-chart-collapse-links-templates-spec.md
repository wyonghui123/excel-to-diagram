# Spec：图表折叠语义 + 任意类型连线 + 视图模板

> 版本：v1.0 | 日期：2026-08-05 | 状态：已确认（用户按推荐默认值成稿）

## 1. Background & Objectives

### 1.1 Background
当前架构图中，分组可见性由 `enabled` 控制，但其语义是"子元素上浮"（`groupFlattener.flattenDisabledGroups` 与 `groupedLayout.generateGroupCode`），无法把整棵子树收敛为单个节点。同时连线端点仅支持 BO→BO（`buildLinks`）与 SM→SM（`serviceModuleDiagramBuilder`）两类，无法表达"折叠后跨层级/任意可见节点"的连线。用户需要：禁用分组子孙 → 折叠为单节点；连线在可见节点间重映射；两种视图模板一键切换；子孙便捷级联折叠/恢复。

### 1.2 Business Objectives
- 支持分组级折叠，将整棵子树收敛为单个聚合节点，聚焦关键架构视角。
- 连线在任意可见节点（含聚合节点）间连通，反映折叠后的真实依赖关系。
- 提供"全启用 / 仅服务模块"两个视图模板，快速切换分析粒度。

### 1.3 User / Stakeholder（涉众）Objectives
- 架构配置人员可在图表设置面板对任意分组执行"折叠 + 级联子孙"，并单点恢复。
- 折叠后图表仍保持连线连通性，不丢失依赖信息。
- 一键应用模板，避免逐项手动配置。

## 2. Requirement Type Overview

| Type | Applicable | Evidence (Source) |
|------|-----------|-------------------|
| Business | Yes | 用户需求①③ |
| User/Stakeholder（涉众） | Yes | 用户需求④、面板操作 |
| Solution | Yes | 折叠模型 + 连线重映射设计 |
| Functional | Yes | FR-001 ~ FR-006 |
| Nonfunctional | Yes | NFR-001 ~ NFR-003 |
| External Interface | Yes | 面板折叠交互、模板按钮 |
| Transition | Yes | 兼容现有 enabled 上浮语义 |

## 3. Functional Requirements

### FR-001: 新增折叠模型字段
- **Description**: 系统 MUST 在 Group/Container 上提供 `collapsed: boolean` 字段（默认 `false`），与现有 `enabled`（上浮）语义正交、互不影响。
- **Acceptance Criteria**:
  - 分组可被标记 `collapsed=true`。
  - `collapsed=true` 不改变子孙的 `enabled/visible` 原始状态（可独立恢复）。
- **Priority**: Must
- **Type Mapping**: Solution / Functional
- **Source**: 用户需求① + 决策"新增折叠语义，保留现有禁用"

### FR-002: 折叠分组渲染为单个聚合节点
- **Description**: 当分组 `collapsed=true` 时，系统 MUST 将该分组渲染为单个聚合节点，隐藏其所有子孙，且不创建 subgraph。
- **Acceptance Criteria**:
  - 折叠"采购云"后，图表仅显示"采购云"一个节点，其下子分组与节点均不渲染。
  - 折叠节点编码稳定（如 `COLLAPSE_<group.id>`），可作为连线端点。
- **Priority**: Must
- **Type Mapping**: Solution / Functional
- **Source**: 用户需求①

### FR-003: 连线重映射到最近可见祖先
- **Description**: 系统 MUST 在渲染前将每条连线的 source/target 重映射到最近可见祖先；若端点位于某 `collapsed` 子树内，则重映射到该折叠聚合节点；若两端均不可见，则丢弃该连线。
- **Acceptance Criteria**:
  - 指向被折叠子孙的连线改为连接折叠聚合节点。
  - 折叠后图表连线始终连通可见节点。
- **Priority**: Must
- **Type Mapping**: Solution / Functional
- **Source**: 用户需求② + 决策"重映射到最近可见祖先"

### FR-004: 任意类型连线端点
- **Description**: 系统 MUST 支持任意 object 类型（BO/SM/折叠聚合节点）作为连线源和目标，统一以"节点编码"为端点建模。
- **Acceptance Criteria**:
  - 折叠聚合节点（BO 或 SM 层级）均可作为连线端点。
  - tooltip 展示折叠聚合节点的子树摘要（含若干 BO/SM）。
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: 用户需求②

### FR-005: 视图模板（全启用 / 仅服务模块）
- **Description**: 系统 MUST 提供两个视图模板：`allEnabled`（所有分组 `collapsed=false`、所有节点 `enabled=true`）与 `onlyServiceModules`（所有 BO 叶节点 `enabled=false` 隐藏，SM 容器保留，连线在 SM 层聚合）。
- **Acceptance Criteria**:
  - 应用 `allEnabled` 后所有折叠/禁用清除。
  - 应用 `onlyServiceModules` 后 BO 节点隐藏、SM 容器保留。
- **Priority**: Must
- **Type Mapping**: Business / Functional
- **Source**: 用户需求③ + 决策"对象隐藏，SM 容器保留"

### FR-006: 子孙级联折叠与恢复
- **Description**: 系统 MUST 在折叠父分组时提供"级联子孙"操作，将子孙标记折叠；折叠状态独立存储，允许对单个子孙单独恢复。
- **Acceptance Criteria**:
  - 折叠父分组 → 子孙批量折叠。
  - 面板可对单个子孙单独展开/恢复。
- **Priority**: Must
- **Type Mapping**: User / Functional
- **Source**: 用户需求④ + 决策"禁用父=子孙全折叠，可单独恢复"

## 4. Nonfunctional Requirements

### NFR-001: 兼容性
- **Description**: 新增折叠语义不得破坏现有 `enabled`（上浮）行为；二者同时启用时 `collapsed` 优先。
- **Measurement**: 现有 `groupModel` 与 `groupedLayout` 单测全部通过；E2E 回归现有禁用场景。
- **Priority**: Must
- **Source**: System Integration 分析

### NFR-002: 可测试性
- **Description**: 折叠为纯前端状态 + 渲染，需可单测（对 mermaidCode 输出断言）与 E2E（面板折叠 → SVG 节点数变化）。
- **Measurement**: `groupedLayout` 折叠分支覆盖单测；E2E 用例含存活断言（DOM 节点数）。
- **Priority**: Should
- **Source**: Completeness & Quality 分析

### NFR-003: 可逆性
- **Description**: 折叠/恢复、模板应用均需可逆，不产生不可恢复的副作用。
- **Measurement**: 每次折叠/恢复后图表配置可无损回退。
- **Priority**: Should
- **Source**: Inverse 分析

## 5. External Interface Requirements

### IF-001: 面板折叠操作
- **Type**: UI
- **Entry**: 架构图表设置面板（LayoutControlPanel）分组行
- **Interaction**: 分组行新增"折叠/展开"操作，附"级联子孙"开关；点击执行折叠/恢复。
- **Error Handling**: 无后端错误；折叠结果即时反映到图表。
- **Source**: 用户需求④

### IF-002: 模板应用按钮
- **Type**: UI
- **Entry**: 面板顶部"视图模板"下拉/按钮（`allEnabled` / `onlyServiceModules`）
- **Interaction**: 选择模板 → 批量写入 collapsed/enabled 状态 → 触发重渲。
- **Error Handling**: 无。
- **Source**: 用户需求③

## 6. Transition Requirements

### TR-001: 兼容现有 enabled 上浮行为
- **Description**: 现有 `enabled` 上浮逻辑与数据保持不变。
- **Strategy**: 新增 `collapsed` 字段独立存在，不迁移现有数据默认值（默认 `false`）。
- **Rollback Plan**: 移除折叠分支即可回退到现有渲染，不影响既有 enabled 行为。
- **Source**: 决策"新增折叠语义，保留现有禁用"

## 7. Constraints & Assumptions

### 7.1 Technical Constraints
- 前端框架结构不变，仅做迭代式增量优化。
- 折叠状态随 `layoutControlConfig` 持久化（推荐默认值）。
- 导出（彩色HTML/PDF）与全屏保留折叠形态（推荐默认值）。

### 7.2 Business Constraints
- 不改动现有 `enabled` 上浮语义。
- 模板"仅服务模块"= 对象隐藏、SM 容器保留。

### 7.3 Assumptions
- 折叠聚合节点编码用 `COLLAPSE_<group.id>`，与现有节点编码不冲突。– Source: Assumed
- 同一折叠节点聚合到多条连线时合并为一条聚合连线（标签展示聚合信息）。– Source: Assumed（推荐默认）
- `collapsed` 与 `enabled` 同时启用时 `collapsed` 优先。– Source: Assumed（推荐默认）

## 8. Priorities & Milestone Suggestions

| ID | Requirement | Priority | Reason |
|----|------------|----------|--------|
| FR-001 | 折叠模型字段 | Must | 其它 FR 的基础 |
| FR-002 | 折叠聚合节点渲染 | Must | 需求①核心 |
| FR-003 | 连线重映射 | Must | 需求②核心 |
| FR-005 | 视图模板 | Must | 需求③核心 |
| FR-006 | 级联折叠/恢复 | Must | 需求④核心 |
| FR-004 | 任意类型端点 + tooltip | Should | 增强体验 |

- Suggested Milestones:
  - Milestone 1（P1）: FR-001 + FR-002（折叠模型 + 聚合节点渲染）
  - Milestone 2（P2）: FR-003 + FR-004（连线重映射 + 统一端点）
  - Milestone 3（P3）: FR-005（模板）
  - Milestone 4（P4）: FR-006（级联 UI + 测试）

## 9. Change / Design Proposal (RFC)

### 9.1 As-Is Analysis
- **Current Architecture**: `enabled` 控制分组可见性，禁用时子元素上浮；BO 图与 SM 图连线端点建模不同（name vs code）。
- **Current Issues**:
  - 无"折叠为单节点"能力。
  - 连线端点仅支持 BO→BO / SM→SM。
  - `collapsed` 与 `enabled` 语义混用风险。
- **Relevant Code Paths**: `groupModel/types.js`、`groupedLayout.js`、`diagramDataBuilder.js`、`serviceModuleDiagramBuilder.js`、`LayoutControlPanel.vue`、`diagramConfigStore.js`。

### 9.2 Target State
- **Proposed Architecture**: 新增 `collapsed` 折叠模型（与 `enabled` 正交）；折叠分组渲染为聚合节点；渲染前执行连线端点重映射；store 提供 `viewTemplate`。
- **Key Changes**:
  - `types.js` 增加 `collapsed` 字段。
  - `groupedLayout.js` 增加折叠分支（聚合节点 + 不遍历子孙）。
  - 新增 `remapLinksToVisibleAncestors` 工具。
  - `diagramConfigStore.js` 增加 `viewTemplate`。
  - `LayoutControlPanel.vue` 增加折叠操作 + 模板按钮 + 级联开关。

### 9.3 Detailed Design
- **Module/Component Design**:
  - `groupModel/`: 数据模型扩展 `collapsed`。
  - `useMermaid/layouts/groupedLayout.js`: 折叠渲染分支。
  - `services/` 新增 remap 工具 + 统一端点。
  - `stores/diagramConfigStore.js`: `viewTemplate` 状态。
  - `LayoutControlPanel.vue`: 折叠/模板/级联 UI。
- **Data Model**: Group/Container 新增 `collapsed:boolean=false`；聚合节点编码 `COLLAPSE_<group.id>`。
- **API Design**: 无后端 API；`viewTemplate` 应用于本地配置。
- **Main Flows**:
  1. 面板折叠分组（+级联） → 写 `collapsed`。
  2. `generateGroupCode` 折叠分支 → 输出聚合节点。
  3. `remapLinksToVisibleAncestors` 规整端点 → 连线连通。
  4. 模板应用 → 批量写状态 → 重渲。

### 9.4 Alternatives Considered
| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| 新增 collapsed 折叠语义 | 与现有 enabled 正交、可独立恢复 | 新增字段/分支 | Selected |
| 改造现有 enabled 为折叠 | 复用字段 | 破坏现有上浮行为、风险高 | Rejected |
| 连线仅保留两端可见 | 简单 | 连线明显减少、丢失信息 | Rejected |
| 对象折叠进各自 SM | 保留存在感 | 与"仅服务模块"模板目标不符 | Rejected |

### 9.5 Implementation & Migration Plan
- **Implementation Order**:
  1. P1: FR-001 + FR-002（折叠字段 + 聚合节点渲染）
  2. P2: FR-003 + FR-004（连线重映射 + 统一端点）
  3. P3: FR-005（模板）
  4. P4: FR-006（级联 UI + 单测）
- **Risk Mitigation**:
  - 破坏现有 enabled 行为 → 保留旧分支，折叠分支独立。
  - 端点重映射丢失关系元数据 → 保留原始 relation 字段，仅改写端点。
- **Testing Strategy**:
  - Unit: `groupedLayout` 折叠分支、`remapLinksToVisibleAncestors` 单测。
  - Integration: 模板应用后图表重渲。
  - E2E: 面板折叠 → SVG 节点数变化（含存活断言）。
- **Rollback Plan**: 移除折叠分支 / 置 `collapsed=false` 即回退。

## 10. TBD List

| ID | Item | Missing Information | Next Step |
|----|------|--------------------|-----------|
| TBD-1 | 折叠聚合节点的 tooltip 摘要格式 | 具体展示哪些字段 | 实现时按已有 tooltip 规范扩展 |
| TBD-2 | 聚合连线的标签文案 | 合并连线的具体标签格式 | P2 实现时确定 |
| TBD-3 | `collapsed` 与 `enabled` 并存优先级 | 已按推荐默认（collapsed 优先） | 确认采纳 |