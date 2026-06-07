# Spec: ObjectPage 布局密度与视觉优化

> **版本**: v1.0 (Draft)
> **日期**: 2026-06-05
> **作者**: Trae IDE Agent
> **状态**: 待评审
> **相关 Spec**: [spec-objectpage-container-adaptation.md](../architecture/spec-objectpage-container-adaptation.md) (容器适配) — 本 Spec 聚焦"容器内布局密度"，与之互补
> **作用范围**: 全屏路由详情页 (`/detail/:type/:id`) 的 ObjectPage 渲染层
> **不在范围**: 侧边抽屉（`RoleDetailDrawer.vue`、`AuditLogDetail.vue`）— 经核查，抽屉**未使用 ObjectPage**，本次优化不影响

---

## 1. Background & Objectives

### 1.1 Background

当前系统的详情页全屏路由（如 `/detail/user/1`）使用 ObjectPage 组件族（`ObjectPage` + `ObjectPageShell` + `ObjectPageHeader` + `ObjectPageContent` + `ObjectPageField` + `FieldGroupSection`）渲染业务对象详情。以"用户详情 admin"为例（见截图），存在以下布局问题：

| # | 问题 | 严重程度 | 影响 |
|---|------|---------|------|
| 1 | **2x2 网格信息密度极低** | 严重 | 4 个字段仅占屏幕 1/3 宽度，右侧 60% 完全空白 |
| 2 | **行间无视觉分隔** | 中 | 字段 baseline 对齐、间距不统一 |
| 3 | **label 宽度不固定** | 中 | "SSO用户ID" 8 字标签紧贴 value，"用户名" 3 字标签留白过大 |
| 4 | **Section 标题样式弱** | 中 | 折叠图标 + 标题贴边，无缩进；section 之间无视觉间隔 |
| 5 | **顶部 Tabs 拥挤截断** | 轻 | "用户与权限管理" 被截断，无关闭按钮 |
| 6 | **状态值用纯文本** | 轻 | "活跃" 应是带颜色的 Tag，增强视觉权重 |
| 7 | **危险操作混在主操作中** | 轻 | "删除/锁定/停用" 危险操作应放入 `···` 下拉 |
| 8 | **缺少审计元数据** | 轻 | 创建时间/更新人/最后登录不可见 |

**头部产品对比**（详见 [research/元数据驱动架构与权限体系-头部产品研究.md](../research/元数据驱动架构与权限体系-头部产品研究.md)）：

- SAP Fiori Object Page：1-2-3-4 列响应式，行内紧凑
- Salesforce Highlights：4 个 KPI 横排 + 下方 2 列
- Dynamics 365：2-3 列自适应
- ServiceNow：1-2 列高密度

**当前问题根因**：
- [FieldGroupSection.vue:140](file:///d:/filework/excel-to-diagram/src/components/common/ObjectPage/FieldGroupSection.vue) `gridClass` 默认为 `grid-4`，但实际渲染时可能由于父容器宽度限制被强制 wrap 成 2 列
- [ObjectPageField.vue:365-372](file:///d:/filework/excel-to-diagram/src/components/common/ObjectPage/ObjectPageField.vue) `label` 用 `min-width: 70px` 而非定宽 + 无 ellipsis
- 缺少顶部 Highlights 组件、状态 Tag 化、危险操作下拉等 YonDesign 标配

### 1.2 Business Objectives

| # | 目标 | 衡量指标 |
|---|------|---------|
| BO-1 | 详情页信息密度提升 50% | 4 字段详情页的"字段数 / 屏幕占用"比从 1.0 提升到 1.5+ |
| BO-2 | 关键信息扫读效率提升 30% | 用户从顶部 Highlights 即可识别对象状态，无需 scroll |
| BO-3 | 危险操作误触率降低 | 通过 `···` 菜单隔离主操作与危险操作 |
| BO-4 | 样式符合 YonDesign 规范 | 视觉走查通过率 100% |

### 1.3 User / Stakeholder (涉众) Objectives

| 涉众 | 目标 |
|------|------|
| 终端用户 | 进入详情页 1 秒内识别对象状态；无需 scroll 即看到关键属性 |
| 前端开发者 | YAML 配 `columnCount` 即可控制列数，无需改组件代码 |
| 架构师 | ObjectPage 渲染层与容器宽度解耦，未来嵌入 Drawer/Dialog 自动适配 |
| 产品经理 | 详情页 KPI 高亮区可承载运营/审计所需的"一眼可见"信息 |

---

## 2. Requirement Type Overview

| Type | Applicable | Evidence |
|------|-----------|----------|
| Business | Yes | 信息密度直接影响用户操作效率（BO-1~4） |
| User/Stakeholder (涉众) | Yes | 终端用户、前端开发者、架构师多方需求 |
| Solution | Yes | 容器查询 + YAML 配置 + 3 个新组件 |
| Functional | Yes | FR-001 ~ FR-008（详见第 3 节） |
| Nonfunctional | Yes | NFR-001 ~ NFR-005（详见第 4 节） |
| External Interface | Yes | YAML schema 扩展 + ObjectPage props + 新组件 API |
| Transition | Yes | 灰度发布 + 老 YAML 向后兼容（详见第 6 节） |

---

## 3. Functional Requirements

### FR-001: 容器查询自适应列数

- **Description**: FieldGroupSection 必须根据**容器实际宽度**自适应列数（1-4 列），不依赖父级媒体查询或显式 props。
- **Acceptance Criteria**:
  - 容器宽度 ≥ 1400px：4 列
  - 容器宽度 1000-1399px：3 列
  - 容器宽度 700-999px：2 列
  - 容器宽度 < 700px：1 列
  - 同一份代码在全屏 (1920px)、嵌入式 (1000px)、极窄 (480px) 容器中渲染列数自动调整
- **Priority**: Must
- **Type Mapping**: Solution, Functional
- **Source**: 用户讨论 2026-06-05（方案 ① 容器查询）

### FR-002: Highlights KPI 顶部展示

- **Description**: ObjectPageHeader 下方增加 Highlights 区域，渲染 YAML 指定的 3-4 个 KPI 卡片横排，每个卡显示 label + value + （可选）icon。
- **Acceptance Criteria**:
  - YAML 配置 `detail.highlights: [username, display_name, status, created_at]`
  - 状态字段（enum）自动用 Tag 组件渲染（颜色由 enum color 决定）
  - 容器宽度 < 700px 时 Highlights 自动降为 2x2 网格
  - Highlights 区域可点击 collapse 收起
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: 头部产品研究 + 业务需求

### FR-003: 状态字段 Tag 化

- **Description**: ObjectPageField 渲染 enum 字段时，必须用 `<el-tag :type="color">` 而非纯文本。
- **Acceptance Criteria**:
  - 已知 enum 字段（status、type、enabled、locked 等）渲染为 Tag
  - Tag 颜色从 `fieldDef.enum_values[].color` 映射（success → success, danger → danger, warning → warning, info → info）
  - 未知 enum 字段降级为纯文本（保持向后兼容）
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: [ObjectPageField.vue:12-18](file:///d:/filework/excel-to-diagram/src/components/common/ObjectPage/ObjectPageField.vue) 现状分析

### FR-004: 危险操作下拉菜单

- **Description**: ObjectPageHeader 操作区将"编辑"保留为主按钮（`AppButton variant="primary"`），"删除/锁定/停用"等危险操作合并到 `···`（AppButton variant="secondary"）下拉菜单。
- **Acceptance Criteria**:
  - 单一主操作（编辑）显示为按钮
  - 危险操作（删除、锁定、停用等）进入 `el-dropdown` 触发器 `···` 菜单
  - 菜单项带 icon + label + 可选 `danger` 样式
  - 列表为空时仅显示主操作按钮（不显示 `···`）
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: 头部产品（SAP Fiori、Notion、Linear）通用模式

### FR-005: Section 标题缩进 + 视觉间隔

- **Description**: FieldGroupSection 标题与卡片边缘增加 16-20px 缩进，section 之间增加 12px 视觉间隔（通过 padding-bottom 或 margin）。
- **Acceptance Criteria**:
  - 标题区左缩进 16px
  - section 标题字体加粗，字号 14px
  - section 之间 12px 间距
  - 折叠状态：折叠图标 + 标题 + 字段数 badge + 收起/展开 hint
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: 视觉走查 + 头部产品参考

### FR-006: Label 定宽 + 间距统一

- **Description**: ObjectPageField label 改为定宽 90px + 右对齐 + 长 label 省略号，value 与 label 间距统一 12px。
- **Acceptance Criteria**:
  - label `width: 90px; text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap`
  - value 与 label 间距 `gap: 12px`
  - 短 label（"邮箱"）右对齐到 90px 边界后左对齐
  - 长 label（"SSO用户ID"）截断为 `SSO用...` + title 全名 tooltip
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: [ObjectPageField.vue:365-372](file:///d:/filework/excel-to-diagram/src/components/common/ObjectPage/ObjectPageField.vue) 当前实现

### FR-007: 顶部 Tabs 关闭按钮 + 溢出滚动

- **Description**: ObjectPageHeader 内的顶部 Tabs 超过 5 个时启用横向滚动（左右箭头按钮），每个 tab 右侧加 `×` 关闭按钮。
- **Acceptance Criteria**:
  - 浏览器原生横向滚动 + 左右滚动箭头（点击移动 200px）
  - 每个非激活 tab 显示 `×`（hover 时显示）
  - 激活 tab 的 `×` 隐藏在"关闭其他 tab" hover 操作中
  - 关闭最后一个 tab 时跳转到默认页（如 list 页）
- **Priority**: Could
- **Type Mapping**: Functional
- **Source**: 浏览器标签页通用模式（Chrome、VSCode）

### FR-008: YAML 配置扩展

- **Description**: 在 `ui_view_config.detail` 下新增 `columnCount` 和 `highlights` 字段，支持按对象配置列数和 Highlights 字段。
- **Acceptance Criteria**:
  - `detail.columnCount: 1 | 2 | 3 | 4` (default: 4) — 仅作为"上限"提示，实际列数受容器查询自适应
  - `detail.highlights: ['field1', 'field2', 'field3', 'field4']` — 列出的字段将出现在 Highlights 区
  - 老 YAML 不含此字段时行为不变（向后兼容）
  - YAML Schema 文档同步更新
- **Priority**: Must
- **Type Mapping**: External Interface, Functional
- **Source**: 本 Spec 设计

---

## 4. Nonfunctional Requirements

### NFR-001: 向后兼容

- **Description**: 老 YAML（不含 `columnCount` 和 `highlights`）必须保持现有行为，无任何破坏性变更。
- **Measurement**: 现有 50+ 个 YAML 文件加载无错；现有 E2E 测试无回归。
- **Priority**: Must
- **Type Mapping**: Transition, Nonfunctional
- **Source**: 测试覆盖率 100% 目标

### NFR-002: 性能

- **Description**: 容器查询仅 CSS 层（无 JS），运行时无额外开销。
- **Measurement**:
  - LCP 不退化（保持 ≤ 2.5s）
  - CLS（累积布局偏移）≤ 0.05
  - JS bundle 增量 < 5KB（gzip）
- **Priority**: Must
- **Type Mapping**: Nonfunctional
- **Source**: 性能基线（FRONTEND_OPTIMIZATION.md）

### NFR-003: 浏览器降级

- **Description**: 不支持容器查询的浏览器（Chrome < 105, Safari < 16, Firefox < 110）优雅降级为 2 列。
- **Measurement**:
  - `@supports not (container-type: inline-size)` 时使用 2 列布局
  - 降级不报错、不白屏
  - 所有功能（编辑、保存、删除）正常工作
- **Priority**: Must
- **Type Mapping**: Nonfunctional
- **Source**: 浏览器兼容矩阵

### NFR-004: 视觉一致性（YonDesign）

- **Description**: 严格遵守 YonDesign 规范：主色 `#ea580c`、按钮用 `AppButton`、弹窗用 `AppModal`、禁用 Emoji、颜色用 CSS 变量。
- **Measurement**:
  - 无硬编码颜色（grep 检查）
  - 无 Emoji 符号
  - `AppButton` 替代 `el-button`
  - `AppModal` 替代 `el-dialog`
- **Priority**: Must
- **Type Mapping**: External Interface, Nonfunctional
- **Source**: [YON_DESIGN_CONSTANTS.md](../../src/styles/YON_DESIGN_CONSTANTS.md) + [project_rules.md](../../.trae/rules/project_rules.md)

### NFR-005: 测试覆盖

- **Description**: 新组件/改动必须有单元测试 + 视觉回归测试。
- **Measurement**:
  - FieldGroupSection 单元测试覆盖率 ≥ 80%
  - ObjectPageHeader 单元测试覆盖率 ≥ 80%
  - 视觉回归测试（Playwright screenshot 对比）通过
  - E2E 测试：编辑/保存/删除流程无回归
- **Priority**: Must
- **Type Mapping**: Nonfunctional
- **Source**: [test-case-standards.md](../../.trae/rules/test-case-standards.md)

---

## 5. External Interface Requirements

### IF-001: YAML Schema 扩展

- **Type**: External Interface (Configuration)
- **Endpoint / Entry**: `ui_view_config.detail` in `meta/schemas/*.yaml`
- **Schema**:
  ```yaml
  ui_view_config:
    detail:
      columnCount: 4              # NEW: 列数上限（实际由容器查询自适应）
      highlights:                 # NEW: 顶部 KPI 区
        - username                # 字段名
        - display_name
        - status
        - created_at
      tabs: [...]                 # 已有
      fieldGroups: [...]          # 已有
  ```
- **Source / Constraint**: 必须保持 `fieldGroups` 兼容性

### IF-002: ObjectPageProps 扩展

- **Type**: External Interface (Component API)
- **Component**: `ObjectPage` (`src/components/common/ObjectPage/ObjectPage.vue`)
- **Props**:
  | Prop | Type | Default | Description |
  |------|------|---------|-------------|
  | `objectType` | String | required | 业务对象类型 |
  | `objectId` | String/Number | required | 对象 ID |
  | `maxColumns` | Number | 4 | 列数上限（FR-001 容器查询的上界） |
  | `highlights` | Array<String> | [] | Highlights 字段列表（FR-002） |
- **Source**: 内部组件 API

### IF-003: 新组件 API

- **Type**: External Interface (New Components)
- **新组件**:
  | 组件 | 路径 | Props |
  |------|------|-------|
  | `<Highlights>` | `src/components/common/ObjectPage/Highlights.vue` | `fields: Array`, `formData: Object`, `fieldDefs: Object` |
  | `<OperationMenu>` | `src/components/common/ObjectPage/OperationMenu.vue` | `primaryAction: Object`, `dangerActions: Array`, `@action` |
  | `<StatusTag>` (utility) | 内联在 ObjectPageField | — |

### IF-004: CSS 变量

- **Type**: External Interface (Design Tokens)
- **新增 CSS 变量** (位于 `src/styles/yon-ep.scss`):
  ```scss
  :root {
    --op-field-label-width: 90px;       /* label 定宽 */
    --op-field-gap: 12px;                /* field 内 gap */
    --op-section-title-indent: 16px;     /* section 标题缩进 */
    --op-section-spacing: 12px;          /* section 间距 */
    --op-highlight-card-padding: 16px;   /* highlight 卡片内边距 */
  }
  ```

---

## 6. Transition Requirements

### TR-001: 灰度发布

- **Description**: 新布局分两批上线，先在 1-2 个非核心对象（如 `user`、`role`）上验证，再推广到全部对象。
- **Strategy**:
  - Phase 1（PR-1）：实现 FR-001/003/006（基础布局），仅修改 `user` YAML
  - Phase 2（PR-2）：实现 FR-002/004/005（Highlights + 危险操作），应用于 `user` + `role`
  - Phase 3（PR-3）：FR-007（顶部 Tabs）+ 全量推广
- **Rollback Plan**: 通过 `git revert` 回滚，YAML 不变则行为不变
- **Source**: 风险控制

### TR-002: YAML 向后兼容

- **Description**: 老 YAML（无 `columnCount`/`highlights`）必须保持现有行为。
- **Strategy**:
  - 组件内对 undefined 用默认值（`columnCount ?? 4`，`highlights ?? []`）
  - 不修改 `meta/schemas/*.yaml` 的 schema 定义文件
  - 运行时动态构造配置，不持久化到 DB
- **Rollback Plan**: N/A（无破坏性变更）
- **Source**: NFR-001

### TR-003: 容器查询特性检测

- **Description**: 部署后监控浏览器兼容性数据。
- **Strategy**:
  - 部署后通过 `navigator.userAgent` 统计 Chrome/Safari/Firefox 占比
  - 兼容矩阵：Chrome 105+ (2022)、Safari 16+ (2022)、Firefox 110+ (2023) — 99%+ 现代浏览器支持
  - 老浏览器降级到 grid-2（已有 CSS 兜底）
- **Rollback Plan**: CSS 降级即可
- **Source**: NFR-003

---

## 7. Constraints & Assumptions

### 7.1 Technical Constraints

| ID | 约束 |
|----|------|
| TC-1 | ObjectPage 仅在全屏路由使用，不影响现有 Drawer 实现（已验证：RoleDetailDrawer / AuditLogDetail 未用 ObjectPage） |
| TC-2 | 容器查询需 `container-type: inline-size` 属性，需确认项目 Vite 配置支持现代 CSS（已确认：Vite 5+） |
| TC-3 | 测试必须遵循 `python d:\filework\test.py` 入口（不能直接 pytest） |
| TC-4 | 前端测试用 happy-dom + Vitest，E2E 用 PlaywrightCLI |

### 7.2 Business Constraints

| ID | 约束 |
|----|------|
| BC-1 | 主色必须用 YonDesign Orange `#ea580c` |
| BC-2 | 不引入新的第三方 UI 库 |
| BC-3 | 所有改动必须通过组件对比页面（http://localhost:3004/component-comparison）验证 |

### 7.3 Assumptions

| ID | 假设 | 来源 | 验证方式 |
|----|------|------|---------|
| AS-1 | 现代浏览器占比 ≥ 95% | 项目 [package.json](file:///d:/filework/excel-to-diagram/package.json) Vite 5+ | 可通过浏览器统计验证 |
| AS-2 | 容器查询支持 4 个 breakpoint（1400/1000/700） | FR-001 | 视觉走查 |
| AS-3 | 老 YAML 不会因 defaults 变化而出现渲染差异 | NFR-001 | 全量 E2E 回归 |
| AS-4 | ObjectPage 在 Drawer 中暂未使用，未来若嵌入可自动受益 | TR-001 Phase 3 | 容器查询通用性 |
| AS-5 | 侧边抽屉独立技术债不在本 Spec 范围 | 现状核查 | 单独 Spec 跟进 |

---

## 8. Priorities & Milestone Suggestions

| ID | Requirement | Priority | Reason |
|----|-------------|----------|--------|
| FR-001 | 容器查询自适应列数 | Must | 核心需求，NFR-003 兜底 |
| FR-003 | 状态字段 Tag 化 | Must | 实施成本最低，收益高 |
| FR-006 | Label 定宽 + 间距统一 | Must | 实施成本低，影响全对象 |
| FR-008 | YAML 配置扩展 | Must | 支撑 FR-001/002 |
| NFR-001 | 向后兼容 | Must | 50+ YAML 不能回归 |
| NFR-002 | 性能 | Must | 不能退步 |
| NFR-003 | 浏览器降级 | Must | 老浏览器兜底 |
| NFR-004 | 视觉一致性 | Must | YonDesign 铁律 |
| NFR-005 | 测试覆盖 | Must | 质量门禁 |
| FR-002 | Highlights KPI | Should | 业务增值，下个 milestone |
| FR-004 | 危险操作下拉 | Should | 体验改进 |
| FR-005 | Section 视觉优化 | Should | 体验改进 |
| FR-007 | 顶部 Tabs 优化 | Could | 边界场景 |

### 建议 Milestone

- **Milestone 1（基础布局，1-2 周）**：
  - FR-001, FR-003, FR-006, FR-008, NFR-001~005
  - 目标：`user` 对象布局密度提升 50%
- **Milestone 2（增值组件，1-2 周）**：
  - FR-002, FR-004, FR-005
  - 目标：`user` + `role` 对象具备 Highlights + 危险操作隔离
- **Milestone 3（边界优化，1 周）**：
  - FR-007
  - 目标：顶部 Tabs 体验改善

---

## 9. Change / Design Proposal (RFC)

### 9.1 As-Is Analysis

#### 9.1.1 当前架构

```
ObjectPageShell.vue              // 壳：Header + Content
  └─ ObjectPageHeader.vue         // 标题 + 操作按钮
  └─ ObjectPageContent.vue        // Tabs + Sections
      └─ FieldGroupSection.vue    // Field group 卡片
          └─ ObjectPageField.vue  // 单个 field
              └─ FkLinkField.vue  // FK 链接（已上轮迭代）
```

#### 9.1.2 现状问题清单

| 问题 | 位置 | 影响 |
|------|------|------|
| 默认 grid-4 但实际渲染 wrap | [FieldGroupSection.vue:140](file:///d:/filework/excel-to-diagram/src/components/common/ObjectPage/FieldGroupSection.vue) | 密度低 |
| label `min-width: 70px` 非定宽 | [ObjectPageField.vue:365-372](file:///d:/filework/excel-to-diagram/src/components/common/ObjectPage/ObjectPageField.vue) | 长 label 挤压 |
| enum 字段已用 `<el-tag>` 渲染 | [ObjectPageField.vue:12-18](file:///d:/filework/excel-to-diagram/src/components/common/ObjectPage/ObjectPageField.vue) | 良好（FR-003 仅需补默认行为） |
| 无 Highlights 组件 | — | 缺失 |
| 危险操作与主操作平铺 | [ObjectPageHeader.vue](file:///d:/filework/excel-to-diagram/src/components/common/ObjectPage/ObjectPageHeader.vue) | 误触风险 |
| 顶部 Tabs 无关闭按钮 | [ObjectPageShell.vue](file:///d:/filework/excel-to-diagram/src/components/common/ObjectPage/ObjectPageShell.vue) | 体验差 |

#### 9.1.3 关键文件

| 文件 | 当前作用 | 本次改动 |
|------|---------|---------|
| `src/components/common/ObjectPage/FieldGroupSection.vue` | field group 渲染 | 加容器查询 CSS |
| `src/components/common/ObjectPage/ObjectPageField.vue` | 单 field 渲染 | label 定宽 + gap 统一 |
| `src/components/common/ObjectPage/ObjectPageHeader.vue` | 标题 + 操作 | 危险操作下拉 |
| `src/components/common/ObjectPage/Highlights.vue` | **不存在** | 新增 |
| `src/components/common/ObjectPage/OperationMenu.vue` | **不存在** | 新增 |
| `src/styles/yon-ep.scss` | YonDesign 变量 | 新增 CSS 变量 |
| `src/components/common/ObjectPage/index.js` | 组件导出 | 导出新组件 |

### 9.2 Target State

#### 9.2.1 目标架构

```
ObjectPageShell.vue
  └─ ObjectPageHeader.vue
      ├─ 标题 + 主操作（AppButton primary）
      └─ ⋯ 菜单（AppButton secondary + el-dropdown）  ← NEW
  └─ Highlights.vue  ← NEW
      └─ 3-4 KPI 卡（响应式 4 列 → 2x2）
  └─ ObjectPageContent.vue
      └─ FieldGroupSection.vue
          └─ ObjectPageField.vue  (label 定宽 90px)
              └─ <el-tag>  // enum 字段
              └─ FkLinkField.vue
```

#### 9.2.2 关键变更

1. **FieldGroupSection 添加容器查询**（CSS-only）
2. **ObjectPageField label 定宽**（CSS）
3. **ObjectPageHeader 危险操作下拉**（Vue）
4. **新增 Highlights 组件**（Vue + 容器查询）
5. **新增 OperationMenu 组件**（Vue + el-dropdown）

### 9.3 Detailed Design

#### 9.3.1 容器查询 CSS（FR-001 核心）

```scss
/* FieldGroupSection.vue */
.op-fg-body {
  display: grid;
  gap: 12px 24px;
  container-type: inline-size;  /* 关键 */
  container-name: op-fg;
}

/* 默认 4 列 */
.op-fg-body.op-grid-4 {
  grid-template-columns: repeat(4, 1fr);
}
.op-fg-body.op-grid-3 {
  grid-template-columns: repeat(3, 1fr);
}
.op-fg-body.op-grid-2 {
  grid-template-columns: repeat(2, 1fr);
}
.op-fg-body.op-grid-1 {
  grid-template-columns: 1fr;
}

/* 容器查询：容器宽度 < 1400 时降到 3 列 */
@container op-fg (max-width: 1399px) {
  .op-grid-4 { grid-template-columns: repeat(3, 1fr); }
}
@container op-fg (max-width: 999px) {
  .op-grid-4,
  .op-grid-3 { grid-template-columns: repeat(2, 1fr); }
}
@container op-fg (max-width: 699px) {
  .op-grid-4,
  .op-grid-3,
  .op-grid-2 { grid-template-columns: 1fr; }
}

/* NFR-003 降级 */
@supports not (container-type: inline-size) {
  .op-grid-4,
  .op-grid-3 { grid-template-columns: repeat(2, 1fr); }
}
```

#### 9.3.2 Label 定宽 CSS（FR-006）

```scss
/* ObjectPageField.vue */
.op-field {
  display: flex;
  flex-direction: row;
  align-items: baseline;
  gap: var(--op-field-gap);
  min-width: 0;
  width: 100%;
  padding: 4px 0;
}

.op-field > label {
  width: var(--op-field-label-width);  /* 90px 定宽 */
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex-shrink: 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  font-weight: 500;
}
```

#### 9.3.3 Highlights 组件（FR-002）

```vue
<!-- src/components/common/ObjectPage/Highlights.vue -->
<template>
  <div v-if="visibleFields.length" class="op-highlights" :class="{ 'op-highlights--collapsed': collapsed }">
    <div v-for="fieldKey in visibleFields" :key="fieldKey" class="op-highlight-card">
      <div class="op-highlight-card__label">{{ getLabel(fieldKey) }}</div>
      <div class="op-highlight-card__value">
        <el-tag v-if="isEnum(fieldKey)" :type="getEnumColor(fieldKey)">
          {{ formatValue(fieldKey) }}
        </el-tag>
        <span v-else>{{ formatValue(fieldKey) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
// props: fields, formData, fieldDefs
// 响应式：容器查询 4 列 → 2x2 → 1 列
</script>

<style scoped>
.op-highlights {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  padding: var(--op-highlight-card-padding);
  margin-bottom: 16px;
  background: var(--color-bg-container);
  border-radius: 6px;
  container-type: inline-size;
  container-name: op-highlights;
}

@container op-highlights (max-width: 999px) {
  .op-highlights { grid-template-columns: repeat(2, 1fr); }
}
@container op-highlights (max-width: 499px) {
  .op-highlights { grid-template-columns: 1fr; }
}
</style>
```

#### 9.3.4 OperationMenu 组件（FR-004）

```vue
<!-- src/components/common/ObjectPage/OperationMenu.vue -->
<template>
  <div class="op-operation-menu">
    <AppButton
      v-if="primaryAction"
      variant="primary"
      @click="$emit('action', primaryAction)"
    >
      {{ primaryAction.label }}
    </AppButton>
    <el-dropdown
      v-if="dangerActions.length > 0"
      trigger="click"
      @command="handleCommand"
    >
      <AppButton variant="secondary" :icon="true">
        <el-icon><MoreFilled /></el-icon>
      </AppButton>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item
            v-for="action in dangerActions"
            :key="action.key"
            :command="action"
            :class="{ 'op-dropdown-item--danger': action.danger }"
          >
            <el-icon v-if="action.icon"><component :is="action.icon" /></el-icon>
            {{ action.label }}
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>
```

#### 9.3.5 YAML 示例

```yaml
# meta/schemas/user.yaml
ui_view_config:
  detail:
    columnCount: 4                # NEW: 列数上限
    highlights:                   # NEW: 顶部 KPI
      - username
      - display_name
      - status
      - created_at
    tabs:
      - id: basic
        title: 基本信息
        fieldGroups:
          - title: 基本信息
            layout: grid-4         # 已有，会被容器查询覆盖
            fields: [username, display_name, email, status]
          - title: 认证信息
            layout: grid-2
            fields: [sso_provider, sso_user_id]
```

### 9.4 Alternatives Considered

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| **A. 容器查询 (CSS @container)** | 零业务代码；自动适配；老浏览器降级 | 老浏览器不支持（但降级到 2 列） | **Selected** |
| B. 显式 `mode` prop | 控制力强；老浏览器兼容 | 调用方多传一个 prop；新加模式要改代码 | Rejected |
| C. JavaScript ResizeObserver | 兼容老浏览器 | 运行时 JS 开销；与 React/Vue 响应式易冲突 | Rejected |
| D. 媒体查询 (media query) | 浏览器支持最好 | 基于视口宽度，**嵌入 Drawer 时不准** | Rejected |
| E. 只改 user.yaml 不改组件 | 0 风险 | 只能加 highlights，列数问题未解决 | Rejected (治标不治本) |

### 9.5 Implementation & Migration Plan

#### 9.5.1 实施顺序

| Phase | PR | 范围 | 风险 | 验证 |
|-------|----|----|------|------|
| 1 | PR-1 | FR-006（label 定宽） + FR-008（YAML） + NFR-001~005 基础 | 低 | 50+ YAML 无回归 |
| 2 | PR-2 | FR-001（容器查询） + FR-003（Tag 化） | 中 | 视觉走查 + 单元测试 |
| 3 | PR-3 | FR-002（Highlights） + FR-004（操作下拉） + FR-005（Section 视觉） | 中 | 单元 + E2E |
| 4 | PR-4 | FR-007（Tabs 优化） | 低 | E2E 走查 |

#### 9.5.2 风险与缓解

| 风险 | 严重度 | 缓解策略 |
|------|--------|---------|
| 容器查询浏览器兼容 | 中 | `@supports` 降级 + NFR-003 验证 |
| 现有 E2E 测试因 DOM 结构变化失败 | 高 | 仅改样式不改 DOM 结构；视觉测试用 Playwright screenshot 比对 |
| Highlights 字段未配置导致空白区 | 低 | 条件渲染：visibleFields.length > 0 才显示 |
| 操作下拉菜单影响外部回调 | 中 | 保持 emit('action') 事件签名不变 |

#### 9.5.3 测试策略

| 测试类型 | 范围 | 工具 |
|---------|------|------|
| 单元测试 | FieldGroupSection / ObjectPageField / Highlights / OperationMenu | Vitest + happy-dom |
| 视觉回归 | `user` / `role` 详情页 full screenshot | Playwright screenshot diff |
| E2E | 创建/编辑/删除流程 | PlaywrightCLI |
| 兼容性 | 容器查询 4 个 breakpoint | Playwright viewport resize |

#### 9.5.4 回滚方案

- 每个 PR 独立可回滚（`git revert`）
- YAML 不变则行为不变（YAML schema 完全向后兼容）
- 容器查询 CSS 可通过 feature flag 关掉（`VITE_OP_CONTAINER_QUERY=false`）
- 实施时用 `git worktree` 隔离，避免污染主分支

#### 9.5.5 关键代码路径

```
实施 PR-1:
  src/components/common/ObjectPage/ObjectPageField.vue     # label 定宽
  src/styles/yon-ep.scss                                    # 新增 CSS 变量
  meta/schemas/user.yaml                                    # 加 columnCount + highlights（仅 user）
  src/components/common/ObjectPage/FieldGroupSection.vue   # 不动（PR-2 改）

实施 PR-2:
  src/components/common/ObjectPage/FieldGroupSection.vue   # 容器查询 CSS
  src/components/common/ObjectPage/ObjectPageField.vue     # enum Tag 化兜底
  src/components/common/ObjectPage/FieldGroupSection.spec.js  # 单元测试

实施 PR-3:
  src/components/common/ObjectPage/Highlights.vue          # 新组件
  src/components/common/ObjectPage/OperationMenu.vue       # 新组件
  src/components/common/ObjectPage/ObjectPageHeader.vue    # 集成
  src/components/common/ObjectPage/index.js                # 导出

实施 PR-4:
  src/components/common/ObjectPage/ObjectPageShell.vue    # 顶部 Tabs 优化
```

---

## 10. TBD List

| ID | Item | Missing Information | Next Step |
|----|------|---------------------|-----------|
| TBD-1 | Highlights 字段选择策略 | 是手选（YAML 配）还是自动（按字段 importance / `ui.featured` 标记）？ | Ask user：倾向手选还是自动？建议手选（YAML 已有此能力） |
| TBD-2 | 哪些对象先迁移 | `user` 单对象？还是首批 `user` + `role` + `business_object`？ | Ask user：建议先用 `user` + `role` 验证 |
| TBD-3 | Highlights 区是否需要折叠按钮 | 复杂对象（>10 字段）时折叠是有用还是干扰？ | 建议默认展开，可配 `collapsible: true` |
| TBD-4 | 危险操作是否含 "导入/导出" 类操作 | YAML 中 action 的 `danger` 标记标准？ | 需在 YAML schema 中增加 `action.danger: bool` 字段 |
| TBD-5 | 顶部 Tabs 是否属于 ObjectPage 职责 | 还是属于 PageShell？ | 当前在 ObjectPageShell，确认是否需移到 PageShell |
| TBD-6 | 审计元数据（创建时间/更新人）位置 | Highlights 区 vs 底部 "Audit Info" 区？ | 建议 Highlights 放关键（创建时间），详细（更新人/变更历史）放底部 |
| TBD-7 | 侧边抽屉技术债何时清理 | `RoleDetailDrawer.vue` 是自定义实现，未来是否统一到 ObjectPage？ | 单独 Spec 跟进，本次范围外 |
| TBD-8 | 视觉回归测试的基线截图 | 现有 user/role 详情页的 baseline screenshot 是否已存档？ | 跑 `python test.py --file e2e/visual/objectpage.spec.js` 生成 |

---

**Spec 完整性检查**：

- [x] Section 1-10 全部存在
- [x] 涵盖所有 7 个需求类型（Business / User / Solution / Functional / Nonfunctional / External Interface / Transition）
- [x] 每个 FR/NFR 都有 ID、Description、Priority、Source
- [x] RFC 包含 As-Is / Target / Detailed Design / Alternatives / Implementation Plan
- [x] TBD List 含 8 项待用户决策
- [x] 显式声明作用范围（ObjectPage 全屏路由）与不在范围（侧边抽屉）
- [x] 引用现有 `spec-objectpage-container-adaptation.md` 避免冲突

**等待用户确认**：是否接受本 Spec + RFC？如接受，是否授权按 PR-1 → PR-4 顺序实施？
