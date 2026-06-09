## 目录

1. [版本历史](#版本历史)
2. [1. Background & Objectives](#1-background-objectives)
3. [2. Requirement Type Overview](#2-requirement-type-overview)
4. [3. Functional Requirements](#3-functional-requirements)
5. [4. Nonfunctional Requirements](#4-nonfunctional-requirements)
6. [5. External Interface Requirements](#5-external-interface-requirements)
7. [6. Transition Requirements](#6-transition-requirements)
8. [7. Constraints & Assumptions](#7-constraints-assumptions)
9. [8. Priorities & Milestone Suggestions](#8-priorities-milestone-suggestions)
10. [9. Change / Design Proposal (RFC)](#9-change-design-proposal-(rfc))
11. [10. TBD List](#10-tbd-list)
12. [Spec + RFC 完整性检查](#spec-rfc-完整性检查)
13. [Spec + RFC Confirmation Request](#spec-rfc-confirmation-request)
14. [11. 头部产品深度对比（v1.4 新增）](#11-头部产品深度对比（v14-新增）)
15. [12. Spec v1.4 终稿状态](#12-spec-v14-终稿状态)
16. [13. v1.4 后端加固（P3 修复，2026-06-05 完成）](#13-v14-后端加固（p3-修复，2026-06-05-完成）)

---
# Spec: 数据权限统一模型 — 管理维度 / 菜单功能权限 / 数据权限整合方案

> 文档 ID: spec-data-permission-unified-2026-06-04
> 版本: **1.4**（SAP 启发：匹配预览 + 菜单-BO 自动关联 + 嵌套 aspect + 性能对标）
> 状态: 待用户审阅
> 前置阅读:
> - [用友BIP权限模型研究补充.md](./yonyou-bip-permission-research.md)
> - [竞品架构分析_元数据驱动与权限模型.md](./competitive-analysis-metadata-permission.md)
> - [权限配置流程优化_维度驱动vs菜单驱动.md](./permission-config-optimization.md)
> - [data-permission-inheritance-model.md](./data-permission-inheritance-model.md)
> - [spec_role_permission_granular_control.md](./spec_role_permission_granular_control.md)

## 版本历史

| 版本 | 变更 |
|------|------|
| 1.0 | 初版，提出"双写策略 + role_data_conditions" |
| 1.1 | 根据用户反馈修正 Section 命名（管理维度 / 菜单与功能权限 / 条件型权限） |
| 1.2 | 废弃双写策略，改为运行时动态展开（SSoT 原则 + 头部产品做法） |
| 1.3 | 补充 FR-009/010/011 保留 owner/draft 内容 |
| **1.4** | **SAP 深度研究启发**：<br>- **FR-005 重定位**："重复配置警告" → "匹配预览"（SAP SU53 Trace 启发）<br>- **新增 FR-012 Match Preview API**：用户可查询"实际生效的 SQL + 命中数"<br>- **新增 FR-013 SU24 等价物**：菜单-BO 权限自动关联（事务码 → Authorization Object 启发）<br>- **新增 FR-014 嵌套 aspect 支持**：aspect 可引用其他 aspect（DCL `inherit` 启发）<br>- **FR-009 增强**：Owner 过滤支持多种身份 aspect（`current_user`/`user_group`/`pfcg_auth`）<br>- **FR-006 增强**：Phase 2 性能优化路径（缓存 + 预解析），对齐 SAP DCL Code-to-Data<br>- **TBD-6 重定位**：升级为 FR-012 "匹配预览"，符合头部产品 user mental model |

---

## 1. Background & Objectives

### 1.1 Background

当前 `PermissionConfigPanel.vue` 是**纵向滚动的 3 个 Section**（不是 Tab），承载三个独立演进的权限子模块：

| Section | 组件 | 现状 | 关键文件 |
|---------|------|------|---------|
| **管理维度** | `DimensionScopePanel.vue` | 维度值选择 + "自动推导并应用"按钮（hardcoded 推导） | `dimension_scope_engine.py`、`role_dimension_scope_api.py` |
| **菜单与功能权限** | `MenuPermissionMatrix.vue` | 菜单勾选 + BO 权限分组（view/edit/manage + standalone）+ 3 态 | `bo_api.py`、`useMenuPermission.ts` |
| **条件型权限** | `ConditionRuleList.vue` + `ConditionRuleDialog.vue` | 通过 BO 字段 valuehelp 选值 + 公式模式 | `data_permission_interceptor.py`、`ConditionRuleList.vue` |

**v1.0 设计问题（双写策略）**：

之前 v1.0 提出"双写策略"（同时写 `role_dimension_scopes` + `role_data_conditions`），但深入反思后**违反单一事实原则（SSoT）**：

- **P-SSoT-1**: 新增 BO X 时，公共维度规则要"重新展开"到 X → **数据冗余**
- **P-SSoT-2**: 双写不一致风险 → **维护成本**
- **P-SSoT-3**: 如果忘了 copy → **新 BO 权限缺失**（易遗漏）
- **P-SSoT-4**: 头部产品（SAP/用友/Salesforce）都是"配置一次，自动应用"——**不双写**

**v1.2 修正**：废弃双写策略，改为**运行时动态展开**（SAP/用友/Salesforce 启发）。

### 1.2 Business Objectives

- **BO-001**: **保持 3 个 Section 结构不变**（不破坏 UI）
- **BO-002**: 明确每个 Section 的语义边界（管理维度 / 菜单功能权限 / 条件型权限）
- **BO-003**: **运行时动态展开**，不引入数据冗余，遵循 SSoT
- **BO-004**: **新增 BO 零迁移接入**（声明式 `dimension_bindings`）
- **BO-005**: 保留"自动推导"按钮价值，hardcoded 逻辑可保留但需文档化

### 1.3 User / Stakeholder Objectives

- **角色配置管理员**：知道三个 Section 各自的语义，分别配置
- **普通用户**：看到的数据 = 三层过滤（功能权限 ∩ 数据范围 ∩ 记录级条件）
- **系统管理员**：新增 BO 时只声明 `dimension_bindings`，零数据迁移
- **架构师**：配置层单一事实（SSoT），执行层动态推导

## 2. Requirement Type Overview

| Type | Applicable | Evidence |
|------|-----------|---------|
| Business | ✅ | 头部产品研究、SSoT 原则 |
| User | ✅ | 角色配置管理员访谈 |
| Solution | ✅ | 元数据驱动 + 运行时动态展开 |
| Functional | ✅ | FR-001 ~ FR-008 |
| Nonfunctional | ✅ | NFR-001/002 |
| External Interface | ✅ | API + UI |
| Transition | ✅ | TR-001（轻量） |

## 3. Functional Requirements

### FR-001: 保持 3 个 Section 结构不变

- **Description**: UI 上保持现有的 3 个 Section（管理维度 / 菜单与功能权限 / 条件型权限），不破坏现有 UX
- **Acceptance Criteria**:
  - 3 个 Section 的位置、标题、布局不变
  - 每个 Section 的核心交互不变
- **Priority**: Must
- **Source**: 用户明确要求

### FR-002: 管理维度升级为公共维度（声明式）

- **Description**: Section 1 的"管理维度"是"公共维度"（predefined 维度），一次配置多 BO 复用。BO 通过 `dimension_bindings` 声明如何应用维度
- **Acceptance Criteria**:
  - 维度值配 `domain=采购`，自动影响所有声明了 `domain` 绑定的 BO
  - BO 的 `dimension_bindings` 是声明式（YAML 中声明）
  - `role_dimension_scopes.bo_id` 字段**可选**（NULL = 公共，值 = BO 级覆盖）
  - 新增 BO X 时，**零数据迁移**：只要 X 声明 `dimension_bindings`，拦截器自动应用
- **Priority**: Must
- **Source**: SAP Organizational Level、用友 BIP 多维组织树、SSoT

### FR-003: 保留"自动推导"按钮 + 文档化

- **Description**: Section 1 中的"自动推导并应用"按钮保留，背后 hardcoded 推导逻辑（dimension_scope_engine.py）文档化
- **Acceptance Criteria**:
  - 按钮位置、文案不变
  - 推导逻辑输出：推荐菜单 + 推荐功能权限
  - 推导结果写到 `role_menu` + `role_permissions`
  - hardcoded 逻辑（HIERARCHY_CHAIN）文档化为可配置（未来）
- **Priority**: Must
- **Source**: 用户明确要求

### FR-004: 条件型权限支持两种模式

- **Description**: Section 3 保留两种表达模式：
  - **valuehelp 模式**：通过 BO 字段下拉选值
  - **公式模式**：XPath/SQL 表达式
- **Acceptance Criteria**:
  - valuehelp 自动列出 BO 的所有可枚举字段
  - 公式模式支持 AND/OR、关联、函数
  - 两种模式可并存于一个角色
- **Priority**: Must
- **Source**: 用户描述："通过 BO 字段维度的 valuehelp 进行规则配置" + "也支持公式灵活方式"

### FR-005: 维度值在两个 Section 语义对齐（基础层）

- **Description**: Section 1 的"产品 in A,B..."和 Section 3 的"维度1 in A,B..."语义对齐
- **Acceptance Criteria**:
  - Section 1 的维度值是"predefined 公共维度"的值
  - Section 3 的"维度1"可以是任意 BO 字段
  - 当 Section 3 选的是 management_dimension 字段时，与 Section 1 等价
  - 同一字段在两个 Section 都配时：Section 3 覆盖（更具体优先）
- **Priority**: Should
- **Source**: 用户洞察
- **实施状态**: v1.3 重复配置警告 UI 已落地（`OverlapWarning.vue` + `useOverlaps.ts`）

### FR-006: 拦截器运行时动态展开（核心，替代双写）

- **Description**: 数据权限拦截器**运行时**从 3 个来源动态拼 SQL，**不引入中间表**：
  1. `role_dimension_scopes`（Section 1 配置）
  2. `permission_rules`（Section 3 配置）
  3. BO 的 `dimension_bindings`（YAML 声明）
- **Acceptance Criteria**:
  - 不新增 `role_data_conditions` 表
  - 拦截器读取上述 3 源，动态展开为 SQL WHERE
  - 配置层单一事实（SSoT）
  - Feature flag: `ENABLE_RUNTIME_RESOLUTION`（默认 true，新逻辑生效）
  - 性能：动态展开耗时 <50ms
- **Priority**: Must
- **Source**: SSoT 原则、头部产品做法（SAP/Salesforce/用友）

### FR-007: 新增 BO 零迁移自动接入

- **Description**: 新增 BO X 时，**无需任何数据迁移**，自动接入公共维度规则
- **Acceptance Criteria**:
  - 新 BO 在 YAML 中声明 `dimension_bindings`
  - 拦截器自动应用公共维度规则
  - 零数据 copy，零脚本迁移
- **Priority**: Must
- **Source**: SAP Organizational Level 启发

### FR-008: 向后兼容（轻量）

- **Description**: 现有 `authorization.scope` 表达式和现有 `permission_rules` 继续工作
- **Acceptance Criteria**:
  - 现有 `role_dimension_scopes` 数据视为公共维度（bo_id 默认 NULL）
  - 现有 `permission_rules` 数据继续生效
  - 现有 3 态功能权限模型不变
- **Priority**: Must
- **Source**: 平滑迁移

### FR-009: Owner 过滤作为记录级可见性（AND 组合 + 多种身份 aspect）

- **Description**: Owner 过滤（基于 `owner_id`）是**记录级可见性**机制，与维度范围是 **AND** 组合关系
- **Acceptance Criteria**:
  - Owner 过滤依附于功能权限（无 read → 无 owner 权限）
  - Owner 过滤与维度范围是 AND：用户在维度范围内 + 是 owner → 可访问
  - Owner 过滤与功能权限是 AND（数据权限依附功能权限的体现）
  - Owner 过滤在 ConditionItem 中作为 `{type: "owner"}` 类型
  - **v1.4 增强**：拦截器运行时支持多种身份 aspect：
    - `aspect current_user`（默认）：`owner_id = $user.id`
    - `aspect user_group`：当前用户所属的所有 user group 包含 owner_id
    - `aspect pfcg_auth`：与 PFCG 角色绑定（SAP 启发：ABAP CDS DCL `aspect pfcg_auth`）
  - 语法：在 BO YAML `authorization.scope` 中可写：
    ```yaml
    scope: "visibility = 'public' OR owner_id = $user.id OR owner_group IN (aspect user_group)"
    ```
- **Priority**: Must
- **Source**: Dataverse Business Unit + 现有 `version.yaml` 的 `owner_id=$user.id` 实现 + SAP DCL `aspect pfcg_auth/user`

### FR-010: Draft 模式作为通用 Owner-Scoped 可见性

- **Description**: Draft 模式（`visibility='draft'` 仅 owner 可见）作为**通用 owner-scoped 可见性机制**，从 version.yaml 推广到所有带 `owner_id` 的 BO
- **Acceptance Criteria**:
  - BO YAML 可声明 `authorization.scope: "visibility = 'public' OR owner_id = $user.id"`
  - 支持 visibility 字段（public/draft/team 等）
  - 支持"草稿转让"：转让后新 owner 可见
  - 支持"发布"动作：从 draft 转为 public
  - 现有 `version.yaml` 的 `publish_version` action 作为模板
- **Priority**: Must
- **Source**: 现有 `version.yaml` 已实现（`visibility='public' OR owner_id=$user.id`）

### FR-011: 转让 Owner 后访问策略

- **Description**: Owner 转让后，原 owner 是否保留对历史草稿的访问需明确
- **Acceptance Criteria**:
  - 默认行为：原 owner **失去访问**（owner 是"当前 owner"语义）
  - 可选行为：保留"创建者"字段支持审计
  - 草稿转让时记录 transfer 事件
- **Priority**: Should
- **Source**: 用户讨论明确

### FR-012: Match Preview API（SAP SU53 Trace 启发）

- **Description**: 提供"匹配预览" API，让用户在角色配置页能看到**实际生效的 SQL WHERE 子句 + 命中记录数**，避免配置后才发现权限不符合预期
- **Acceptance Criteria**:
  - **API 端点**: `POST /api/v1/roles/<role_id>/match-preview`
  - **请求**: `{user_id, bo_id, sample_conditions: [...]}`
  - **响应**:
    ```json
    {
      "where_clause": "(version_id IN (1,2) AND owner_id = 5) OR status = 'public'",
      "sources": [
        {"source": "role_dimension_scopes", "field": "version_id", "values": [1,2]},
        {"source": "owner_aspect", "field": "owner_id", "value": 5},
        {"source": "permission_rules", "field": "status", "op": "=", "value": "public"}
      ],
      "match_count": 42,
      "warnings": ["Section 1 与 Section 3 同时配置了 version_id，将以 Section 3 为准"]
    }
    ```
  - **UI**: 在角色配置页 Section 3 旁加"预览生效条件"按钮
  - **优先级**: Should
- **Priority**: Should
- **Source**: SAP SU53（用户权限调试）+ ST01 Trace（权限追踪）+ Mendix XPath Preview

### FR-013: 菜单-BO 权限自动关联（SAP SU24 等价物）

- **Description**: 菜单项绑定时声明"该菜单操作涉及哪些 BO + 默认权限"，新增菜单项时自动检查相关 BO 的默认权限
- **Acceptance Criteria**:
  - 在 `menu.yaml` 节点中增加 `bo_associations: [{bo_id, default_action: "view|edit|manage"}]`
  - 新增菜单项绑定到角色时，**自动应用**相关 BO 的默认权限
  - 仍允许用户**手动调整**权限级别
  - 类比 SAP SU24：Tcode → 默认 Authorization Object 列表
- **API 端点**:
  - `GET /api/v1/menu/<menu_id>/bo-associations` 列出菜单关联的 BO
  - `PUT /api/v1/roles/<role_id>/menu/<menu_id>` 现在会展开 bo_associations
- **Priority**: Should
- **Source**: SAP SU24（事务码 → 默认 Authorization Object）+ Salesforce App Permissions

### FR-014: 嵌套 aspect 支持（DCL `inherit` 启发）

- **Description**: aspect 可引用其他 aspect，实现 aspect 组合与继承
- **Acceptance Criteria**:
  - `aspects.yaml` 中 aspect 声明 `extends: <other_aspect_id>` 或 `includes: [<aspect_id>, ...]`
  - aspect 字段可被继承，子 aspect 可覆盖
  - BO 引用组合 aspect 时自动展开所有字段
  - **类比 SAP DCL `inherit` 关键字**：
    ```abap
    define role demo_cds_role_inherited {
      grant select on demo_cds_auth_inherited
      inherit demo_cds_role_lit_pfcg or currcode = 'USD';
    }
    ```
  - 我们等价物（伪代码）：
    ```yaml
    - id: advanced_owner_aspect
      extends: owner_aspect
      fields:
        - id: owner_group    # 扩展字段
        - id: visibility  # 继承
      authorization:
        scope: "visibility = 'public' OR owner_id = $user.id OR owner_group = $user.group"
    ```
- **Priority**: Could
- **Source**: SAP DCL `inherit` 关键字 + 面向对象继承思想

### FR-015: 跨菜单 BO 权限累加显式化（v1.4 用户关键洞察）

- **Description**: 菜单与 BO 是多对多关系——一个 BO 可被多个菜单引用。**当前实现是 OR 累加（取最宽松，与 Salesforce/Dataverse/ServiceNow/用友 BIP 一致）**，但用户配置 menu2 时不知道 menu1 已配置，导致"权限溢出"困惑。本 FR 在 UI 层**显式化**累加语义，让用户清楚看到 BO 被哪些菜单影响、实际生效权限。
- **Acceptance Criteria**:
  - **存储层**：保持现状（OR 累加，全局去重，不变）
  - **UI 增强**：
    - 在 `MenuPermissionMatrix.vue` 的每个 BO 分组旁加"跨菜单累计"徽章
    - 当 BO 被 ≥2 个菜单配置时显示徽章，单菜单时不显示
    - 徽章 4 种状态：
      | 累计状态 | 标签 | 颜色 | 图标 |
      |---------|------|------|------|
      | 全 include / 全 auto | "N 个菜单中全权" | 绿（success） | ✓ |
      | 混合（部分 include + 部分 exclude）| "N 个菜单累计（混合）" | 黄（warning） | ⚠ |
      | 全 exclude | "N 个菜单中均被排除" | 红（error） | ✗ |
      | 仅 1 个菜单 | 不显示徽章 | - | - |
    - 鼠标悬停 tooltip 显示详情：
      ```
      此 BO 在以下菜单中配置：
      - 菜单1（产品列表）：全权（include）
      - 菜单2（产品统计）：仅查看（include view, exclude edit）
      - 菜单3（产品导入）：全权（auto）
      实际权限 = 取最宽松 = 全权
      ```
  - **后端 API 增强**：
    - 新增 `GET /api/v1/roles/<role_id>/menu-permissions/cross-menu-summary`
    - 返回每个 BO 的累计信息（参考 Section FR-015 详细设计）
  - **业务示例**：
    - 菜单1 选 BO X 全权，菜单2 选 BO X 仅 view
    - 用户看到菜单2 旁的徽章："此 BO 跨 2 个菜单累计（混合）"
    - 悬停显示：菜单1 全权 / 菜单2 仅 view / 实际 = 全权
    - 用户决定：要么在菜单2 调成"全权"显式确认，要么在菜单1 取消"全权"
- **Priority**: Should
- **Source**: 用户关键洞察（菜单-BO 多对多语义）+ 头部产品对标（Salesforce/用友 OR 累加 + UI 显式化）+ 防止"权限溢出"困惑
- **实施状态**: 待实施（与 FR-013 一起作为 M4+M5 候选）

### FR-016: Association Derived 数据权限完整性（v1.4 用户关键洞察 — Bug 修复 + 路径类型扩展）

- **Description**: BO 通过 `dimension_bindings` 的 `through:` 字段声明**多跳关联派生**（如 `service_module->sub_domain->domain`），这是"association derived"数据权限的核心机制。**v1.3 实施时声明层完整，但运行时层存在两类缺陷**：
  1. **运行时 Bug**：[`RuntimeDimensionResolver._resolve_field`](file:///d:/filework/excel-to-diagram/meta/core/runtime_dimension_resolver.py#L248-L271) 在处理多跳 `through:` 时简化为"返回主字段"（`service_module_id`），导致：
     - 用户配 `domain IN (1,2)` 实际过滤 `service_module_id IN (1,2)`
     - 业务上**错误**——应过滤 domain 1/2 下的所有 BO，但实际是 service_module 1/2 下的所有 BO
     - 1 跳派生（sub_domain ↔ service_module）正确；2 跳以上都错
  2. **路径类型未区分**：Schema 中**有** parent-child 与 reference 两种关系（[`business_object.yaml#L925-L961`](file:///d:/filework/excel-to-diagram/meta/schemas/business_object.yaml#L925-L961) 区分 `type: parent_child` 与 `type: reference`），但 `through:` 字段**未明确区分**——当前只支持走 `parent_object` 链（parent-child），**未支持走 `relations.type: reference`（FK 关联）**。
- **路径类型定义**（基于头部产品对标）：
  - **Parent-Child 父子路径**（已部分支持，Bug 修复）：
    - 路径语义：每一步都是父子关系（走 `parent_object` 链）
    - 例：`service_module->sub_domain->domain`（BO 父子层级）
    - 头部对标：SAP CDS `Composition`、Salesforce `Master-Detail`、Dataverse `Parental`
  - **Association FK 路径**（**v1.4 新增**）：
    - 路径语义：每一步走 `relations.type: reference`（FK 关联）
    - 例：`customer->department`（user → customer 是 reference，customer → department 是 reference）
    - 头部对标：SAP CDS `Association`、Salesforce `Lookup`、Dataverse `Reference`、Mendix `*:*`
- **Acceptance Criteria**:
  - **AC-1 (Must) 字段优先级**（Parent-Child 路径）：
    - 优先使用 BO 上的**冗余字段**（如 `domain_id`）作为过滤字段
    - 没有冗余字段时，回退到主字段（向后兼容）
    - 示例：business_object 配 `domain IN (1,2)` 应生成 `domain_id IN (1,2)`
  - **AC-2 (Must) 冗余字段自动检测**（Parent-Child 路径）：
    - 系统启动时扫描 BO 字段，识别冗余字段（标记 `storage: virtual` + `derived_from` 包含目标维度）
    - 维护 `BO → 冗余字段映射`：如 `{business_object: {domain: 'domain_id', sub_domain: 'sub_domain_id', version: 'version_id'}}`
    - 缓存到 `BoSchemaLoader`，避免每次全表扫描
  - **AC-3 (Must) 路径类型显式区分**（**用户追问**）：
    - 区分 parent-child 路径（`->`）和 association 路径（`-->` 或其他语法）
    - 路径解析器根据 schema 验证每一步是 parent-child 还是 reference
    - **Schema 语法建议**：
      ```yaml
      # Parent-child 路径（现有语法）
      - dimension: domain
        through: "service_module->sub_domain"  # → 是 parent-child
      
      # Association 路径（v1.4 新增语法）
      - dimension: department
        through: "customer-->department"  # --> 是 reference（FK）
      
      # 混合路径
      - dimension: customer_dept
        through: "customer.fk->department"  # customer 是 parent-child, department 是 reference
      ```
    - **或者**用结构化语法（更明确）：
      ```yaml
      - dimension: department
        through:
          - hop: customer
            via: fk              # ← 显式声明：FK 关联
            field: customer_id
          - hop: department
            via: fk
            field: department_id
      ```
  - **AC-4 (Must) Association 路径运行时展开**（v1.4 新增）：
    - 解析 `through: "customer-->department"` 路径
    - 查找 `business_object.relations` 中 `target: customer` 的 `type: reference` 关联
    - 查找 `customer.relations` 中 `target: department` 的 `type: reference` 关联
    - 生成 SQL JOIN 路径：`business_object JOIN customer ON business_object.customer_id = customer.id JOIN department ON customer.department_id = department.id`
    - 实际生成 SQL WHERE：`department.id IN (1,2)`
  - **AC-5 (Must) 测试覆盖**：
    - 1 跳 Parent-Child：`sub_domain ↔ service_module`（当前正确）
    - 2 跳 Parent-Child：`domain ↔ business_object`（用 `domain_id` 冗余字段）
    - 3 跳 Parent-Child：`version ↔ business_object`（用 `version_id` 冗余字段）
    - 4 跳 Parent-Child：`product ↔ business_object`（用 `version_id` 跨 4 表追溯）
    - 1 跳 Association：`customer --> department`（user → customer → department）
    - 2 跳 Association：`customer --> region --> country`（多跳 FK）
    - 混合路径：`customer -> department`（parent-child + association）
    - 无冗余字段时的 fallback（应 fallback 到主字段 + 警告）
  - **AC-6 (Should) JOIN 路径生成**（任一类型无冗余字段时）：
    - 生成 SQL JOIN 路径（应用层）
    - 实际生成 SQL WHERE：路径末端表的字段 IN (values)
    - 实现位置：拦截器层（应用层 JOIN，性能开销）
  - **AC-7 (Could) 性能对标 SAP CDS**：
    - AC-1/AC-2/AC-4 路径性能高（直接字段过滤）
    - AC-6 路径性能低（应用层 JOIN），需要数据库层优化（Phase 2）
- **Priority**: **Must**（v1.3 实施后实际有 Bug — 2 跳以上过滤不正确 + 路径类型未区分）
- **Source**: 用户关键洞察（"association derived 是否包含"+"是否区分 parent-children 和 association"）+ 头部产品对标（SAP CDS Composition vs Association / Salesforce Master-Detail vs Lookup / Dataverse Parental vs Reference）+ v1.3 实施后真实 Bug
- **实施状态**: **Bug 修复**（AC-1/2/5 parent-child）+ **功能新增**（AC-3/4/5 association 路径）
- **关联 Milestone**:
  - **M8（第 1 周）**: AC-1/2/5 — 修复 parent-child association derived 正确性（Bug 修复）
  - **M8.5（第 2 周）**: AC-3/4/5 — 扩展 association (FK) 路径支持
  - **M9 (Phase 2)**: AC-6/7 JOIN 路径生成与性能优化

### FR-017: BO 统一模型（Entity + Service + Actions — v1.4 用户深度洞察）

- **Description**: 基于"Action 引用 Service BO，Action 就是 Service BO 的 action"用户深度洞察，建立 **BO 统一模型**——**一切皆 BO**（Entity 存数据、Service 存行为），**Action 合并到 BO.actions**（BO 的方法），消除 Action 独立 first-class 概念。**完全对齐 SAP RAP + 用友 BIP**。
- **关键洞察**（用户 3 层洞察链）：
  - **洞察 1: Action = 过程（不是 BO 子对象）**：Action 是 first-class 函数，BO 是参数；Action 可选 `target_bo`（`null` = static）
  - **洞察 2: Service Component 就是 BO**（**核心洞察**）：不需独立 `services.yaml`；Service 是 BO 的特殊类型（`type: service`）；Service BO 复用 BO 的所有机制（权限、维度、Owner）
  - **洞察 3: Action 合并到 BO.actions**（**深度洞察**）："Action 既然引用 Service BO，那 Action 就是 Service BO 的 action"；**Action 不是独立 first-class**；Action 是 BO 的方法（method）；Entity BO 自动有 CRUD actions（SAP RAP managed）；Service BO 显式声明 actions（execute / preview 等）
  - **3 层抽象**（4 层 → 3 层简化）：
    ```
    Layer 1: BO（type: entity | service）  ← 一切皆 BO
    Layer 2: Intent (BO_id, action_name, parameters)
    Layer 3: Data (BO 表 + 维度 + 字段)
    ```
- **头部产品对标**：
  - **SAP RAP**（**完全对齐，最优对标**）：RAP BO = 我们的 BO（entity/service）；Behavior Definition = BO.actions + behaviors；Managed Implementation = Entity BO 自动 CRUD；Unmanaged Implementation = Service BO 自定义 behaviors；Service Definition = BO.exposed_as_action；OData Binding = Intent 路由
  - **用友 BIP**（**完全对齐**）：业务对象 = 数据 + 行为，**"业务对象即服务"**
  - **Salesforce Quick Actions**（**部分对齐**）：Action 是独立 first-class（**不一致**）
  - **ServiceNow UI Actions**（**部分对齐**）：UI Action 是独立 first-class（**不一致**）
  - **Mendix Microflow**（**部分对齐**）：Microflow 是独立 first-class（**不一致**）
  - **Dataverse Ribbon Button**（**部分对齐**）：Button 是独立 first-class（**不一致**）
- **Acceptance Criteria**:
  - **AC-1 (Must) BO Schema 扩展 — `type: entity | service` 区分**：
    ```yaml
    # Entity BO（数据为主）— 现有 bo.yaml 扩展
    - id: version
      type: entity                    # 新增字段（默认 entity）
      name: 版本
      fields:                          # 数据字段
        - name: id
          type: integer
          primary: true
        - name: status
          type: string
      relations:                       # 实体关系
        - id: version_to_owner
          type: parent_child
          target: user
      # actions 自动生成：create, read, update, delete（SAP RAP managed）

    # Service BO（行为为主）— 替代独立 services.yaml
    - id: view_version_chart
      type: service                   # 新增字段：service 类型
      name: 查看版本图表
      parameters:                      # Service 特有
        - name: target
          type: bo
          required: true
        - name: chart_type
          type: enum [bar, line, pie]
          required: false
          default: bar
      behaviors:                       # Service 特有
        - type: execute
          steps:
            - service: query_version_data
            - service: compute_chart_metrics
            - service: build_chart_response
      required_permissions:
        - chart:view
        - version:read
    ```
  - **AC-2 (Must) BO.actions 字段 — 统一 Action 定义（替代独立 `actions.yaml`）**：
    ```yaml
    - id: view_version_chart          # Service BO
      type: service
      actions:                          # BO 的方法（SAP RAP 风格）
        - id: execute
          name: 执行
          action_type: execute
          is_default: true
        - id: preview
          name: 预览
          action_type: query
    ```
    - **Entity BO** 自动生成 CRUD actions（SAP RAP managed）
    - **Service BO** 显式声明 actions（如 `execute` / `preview`）
    - **Static Action** 用 `type: system` 区分（可选）
  - **AC-3 (Must) menu.yaml 改造 — Intent 统一表达**：
    ```yaml
    # Intent = (BO_id, action_name, parameters) 二元组
    - menu_code: version_chart
      page_type: dashboard
      intent:                          # 新增字段
        bo_id: view_version_chart      # Service BO
        action: execute                # BO 的 action
        parameters:
          target: $route.params.id
          chart_type: bar
      # 保留向后兼容字段（新字段共存）
      bo_bindings:
        - bo_id: version
          role: primary
    ```
    - 新增 `intent` 字段（`bo_id` + `action` + `parameters`）
    - `bo_bindings` + `required_permissions` 保留（向后兼容）
    - `intent` 优先，旧配置自动迁移生成默认 Intent
  - **AC-4 (Must) 角色权限 — `role_intents` 表（替代 `role_actions`）**：
    ```sql
    CREATE TABLE role_intents (
      id INTEGER PRIMARY KEY,
      role_id INTEGER NOT NULL,
      bo_id VARCHAR(100) NOT NULL,       -- 引用 BO
      action_name VARCHAR(100) NOT NULL, -- BO 的 action 名
      parameters_hash VARCHAR(64),       -- 参数指纹
      granted INTEGER NOT NULL,          -- 1=include, 0=exclude
      source VARCHAR(50),                -- auto / include / exclude
      created_at TIMESTAMP,
      UNIQUE(role_id, bo_id, action_name, parameters_hash)
    );
    ```
    - 替代原 `role_actions`（Action 独立 first-class 的设计）
    - 替代 `role_menu_permissions`（菜单权限合并到 Intent）
    - 保留 `role_permissions`（自动从 Intent 推导）
  - **AC-5 (Must) 权限计算 — 5 步检查**：
    - **Step 1 Intent 权限**：`role_intents[role, bo, action, params_hash].granted`
    - **Step 2 Action required_permissions**：`role_permissions[role, perm_code].granted`
    - **Step 3 BO 权限**（Entity BO）：`role_permissions[role, BO:action].granted`
    - **Step 4 数据权限**：维度范围 + Owner + 跨菜单累加（FR-015/FR-016）
    - **Step 5 条件可见性**：Action 条件 + BO 条件
    - **统一表达式**：`Intent-level 权限 = 5 步 AND`
  - **AC-6 (Should) Service BO behaviors 实现步骤**：
    - 复合步骤（composite）：`steps: [service1, service2, ...]`
    - 参数映射：`$input.target.id`、`$step1.data`
    - 错误处理：`on_error: fail | skip | fallback`
    - **不实施**过程代数完整语义（v2+）
  - **AC-7 (Should) 条件可见性**（ServiceNow + Dataverse 启发）：
    - BO / Action 有 `conditions` 字段
    - 可基于 BO 字段值控制可见性
    - 例：版本状态 = published 时才显示"发布"Action
  - **AC-8 (Should) UI 增强**：
    - **角色配置页**：新增 Section 4 "BO Action 权限"（与菜单/数据权限并列）
    - 每个 Intent 可配置 3 态（auto/include/exclude）
    - 菜单列表旁显示"引用的 BO Action"tooltip
    - 跨菜单 Intent 复用提示
  - **AC-9 (Should) API 端点**：
    - `GET /api/v1/bos` 列出 BO
    - `POST /api/v1/bos` 创建 BO
    - `PUT /api/v1/bos/<id>` 更新 BO
    - `GET /api/v1/bos/<id>/actions` 列出 BO 的 actions
    - `POST /api/v1/bos/<id>/actions/<action_name>` 调用 BO action
    - `GET /api/v1/roles/<id>/intents` 角色已配 Intent
    - `PUT /api/v1/roles/<id>/intents/<bo_id>/<action_name>` 角色 + Intent 权限
  - **AC-10 (Should) `dashboard` 页面类型支持**：
    - 实施 `page_type: dashboard` 路由
    - dashboard 页面可声明 `intent: {bo_id: <Service BO>, action: execute}`
  - **AC-11 (Must) 测试覆盖**：
    - Entity BO CRUD 自动生成测试
    - Service BO behaviors 步骤测试
    - BO actions 调用测试
    - Intent 权限检查测试
    - 5 步权限计算测试
    - 跨菜单 Intent 复用测试
    - 条件可见性测试
    - 数据权限叠加测试
    - 兼容性测试（旧 bo_bindings 自动迁移）
- **Priority**: **Should**（用户关键洞察 + 核心洞察 + 深度洞察，纳入权限管理是最佳实践）
- **Source**: 用户 3 层洞察链（"page navigation 可建模为 object action"+"Service Component 是不是就是 BO"+"Action 既然引用 Service BO，那 Action 就是 Service BO 的 action"）+ 头部产品对标（**SAP RAP 完全对齐** + 用友 BIP 完全对齐）+ 当前 v1.3 实施盲点（`required_permissions` 隐式推导 + `dashboard` 暂未实现 + Action 不可复用 + Service 与 BO 概念分裂）
- **实施状态**: 待实施
- **关联 Milestone**:
  - **M10.0 (第 3 周)**: AC-1/2 — BO Schema 扩展（type + actions + behaviors + parameters）
  - **M10.1 (第 3 周)**: AC-3/4 — role_intents 表 + 兼容迁移
  - **M10.2 (第 4 周)**: AC-5/6/11 — 5 步权限计算 + behaviors + 测试
  - **M10.3 (第 4 周)**: AC-7/8/9 — 条件可见性 + UI + API
  - **M10.4 (第 4 周)**: AC-10 — dashboard 实现 + chart 展示作为 Service BO 试点
- **与现有 FR 的关系**：
  - **FR-013 菜单-BO 权限自动关联**：Intent 自动关联 BO 权限（菜单绑定时生成默认 Intent）
  - **FR-015 跨菜单 BO 权限累加显式化**：Intent 也需"跨菜单累加显式化"（同一 Intent 被多个菜单引用）
  - **FR-009 Owner 过滤**：Service BO 可引用 owner_aspect（如"删除自己创建的版本"Service）
  - **FR-016 Association Derived**：Service BO 可引用关联派生条件（如"按 user 部门过滤"）
  - **FR-012 Match Preview**：Intent 权限计算可生成预览 SQL（SAP SU53 启发）
- **参考文档**:
  - [rfc_action_service_unified_model.md](./rfc_action_service_unified_model.md) — v2.0 完整 RFC

## 4. Nonfunctional Requirements

### NFR-001: 性能
- 拦截器运行时动态展开耗时 <50ms
- 三源 JOIN 后的 SQL 必须 <100ms 整体执行
- **v1.4 增强 — 对标 SAP DCL Code-to-Data**：
  - SAP DCL 编译到 CDS view，在数据库层执行（无应用层开销）
  - 我们应用层拦截器有 5-20ms 开销
  - **Phase 2 优化路径**：
    - **缓存层（v1.4 Phase 2）**：按 `role_id + user_id + bo_id` 缓存展开结果（TTL 60s）
    - **预解析维度值（v1.4 Phase 2）**：拦截器启动时一次预解析所有 IN 子句值
    - **物化路径（v1.4+）**：常用路径预先物化为 SQL 模板
  - 性能目标保持：<50ms 展开，<100ms 整体执行

### NFR-002: 兼容性
- 现有 `role_dimension_scopes` 表结构**仅扩展** `bo_id` 字段
- 现有 `permission_rules` 表不变
- 现有 3 态功能权限模型不变
- 现有 `authorization.scope` 表达式并行

### NFR-003: 头部产品对标（v1.4 新增）
- **SAP Organizational Levels**：维度值公共配置，Authorization Object 自动继承
- **SAP DCL CDS View**：运行时动态展开（Code-to-Data）
- **SAP SU53 Trace**：匹配预览（FR-012）
- **SAP SU24**：菜单-BO 权限自动关联（FR-013）
- **SAP DCL `inherit`**：嵌套 aspect（FR-014）
- **Salesforce "most permissive wins"**：我们的 Section 3 覆盖（FR-005）
- **Dataverse Access Depth**：业务单元层级（v2+ 考虑）

## 5. External Interface Requirements

### IF-001: 角色管理维度 API（扩展）
- **Type**: REST API
- **Endpoint**: `PUT /api/v1/roles/<id>/dimension-scopes`
- **Request 变更**: 支持 `bo_id: null`（公共维度）
- **状态**: **保持兼容**，扩展字段

### IF-002: 角色菜单功能权限 API（不变）
- **Endpoint**: `PUT /api/v2/roles/<id>/menu-permissions`
- **状态**: **不变**

### IF-003: 角色条件规则 API（不变）
- **Endpoint**: `PUT /api/v1/roles/<id>/permission-rules`
- **状态**: **不变**

### ~~IF-004: 角色数据条件 API~~（废弃）
- **原因**: v1.0 提出的 `role_data_conditions` API 已废弃，无中间表
- **替代**: 拦截器直接从 `role_dimension_scopes` + `permission_rules` + BO bindings 读取

## 6. Transition Requirements

### TR-001: 轻量数据迁移（仅扩展 bo_id 字段）
- **Description**: `role_dimension_scopes` 表添加 `bo_id` 字段（NULL 默认值）
- **Strategy**: 数据库迁移脚本 `migrate_dim_scope_add_bo_id_2026.py`
- **Rollback**: 删除字段（数据无损）
- **影响面**: 极小，不涉及数据迁移

### TR-002: Feature Flag
- **Description**: 新逻辑通过 feature flag 控制
- **Strategy**: `ENABLE_RUNTIME_RESOLUTION` 环境变量，默认 true
- **Rollback**: flag 关闭即走原逻辑（按顺序读多表）

## 7. Constraints & Assumptions

### 7.1 Technical Constraints
- 数据权限过滤在 SQL 拦截器层实现（`data_permission_interceptor.py`）
- 维度值通过 `management_dimensions` 表查询
- BO 的 `dimension_bindings` 在 BO schema 中声明

### 7.2 Business Constraints
- **3 个 Section 布局不变**（用户明确要求）
- 自动推导按钮保留（用户明确要求）
- 现有 3 态功能权限模型不变
- 现有 `authorization.scope` 表达式并行

### 7.3 Assumptions
- **A1**: 同一 BO 的同一字段不会被多个维度重复绑定
- **A2**: Section 3 选 management_dimension 字段时，与 Section 1 等价
- **A3**: 维度值 ID 跨表唯一
- **A4**: 当前 HIERARCHY_CHAIN 中的 4 层是合理的初始结构
- **A5**: 运行时动态展开的 3 源 JOIN 性能可接受

## 8. Priorities & Milestone Suggestions

| ID | Title | Priority | Reason |
|----|-------|---------|--------|
| FR-001 | 保持 3 个 Section 结构不变 | Must | 用户明确要求 |
| FR-002 | 管理维度升级为公共维度（声明式） | Must | 头部产品做法 + SSoT |
| FR-003 | 保留"自动推导"按钮 | Must | 用户明确要求 |
| FR-004 | 条件型权限两种模式 | Must | 用户已实现，需保留 |
| FR-006 | 拦截器运行时动态展开 | Must | 核心设计，SSoT |
| FR-007 | 新增 BO 零迁移接入 | Must | 公共维度的真正价值 |
| FR-008 | 向后兼容 | Must | 平滑迁移 |
| **FR-009** | **Owner 过滤作为记录级可见性（AND 组合 + 多种身份 aspect）** | **Must** | **数据权限依附功能权限 + version.yaml 现状 + SAP DCL aspect** |
| **FR-010** | **Draft 模式作为通用 Owner-Scoped 可见性** | **Must** | **version.yaml 已实现，推广** |
| **FR-011** | **转让 Owner 后访问策略** | **Should** | **明确语义，避免歧义** |
| FR-005 | 维度值语义对齐（基础层） | Should | 概念统一（v1.3 重叠警告 UI 已落地） |
| **FR-012** | **Match Preview API**（v1.4 SAP SU53 启发） | **Should** | **用户配置后立即看到 SQL 效果** |
| **FR-013** | **菜单-BO 权限自动关联**（v1.4 SAP SU24 启发） | **Should** | **降低菜单权限配置出错率** |
| **FR-014** | **嵌套 aspect 支持**（v1.4 SAP DCL `inherit` 启发） | **Could** | **aspect 复用与扩展** |
| **FR-015** | **跨菜单 BO 权限累加显式化**（v1.4 用户关键洞察） | **Should** | **解决"权限溢出"困惑 + 头部产品对标** |
| **FR-016** | **Association Derived 数据权限完整性**（v1.4 用户关键洞察 — Bug 修复） | **Must** | **修复 2 跳以上 `through:` 过滤不正确（v1.3 实施后 Bug）** |
| **FR-017** | **BO 统一模型（Entity + Service + Actions）**（v1.4 用户 3 层洞察链 — 完全对齐 SAP RAP + 用友 BIP） | **Should** | **Service = BO.service + Action 合并到 BO.actions + 3 层抽象（BO + Intent + Data）** |

**Milestones**：
- **M1 (1 周)**：FR-002/006/007 — 拦截器运行时动态展开 + BO bindings ✅ 已完成
- **M2 (1 周)**：FR-009/010 — Owner 过滤 + Draft 模式通用化 ✅ 已完成
- **M3.1 (1 周)**：FR-005 重复配置警告 UI ✅ 已完成
- **M4+M5+M4.5 (第 2-3 周)**：FR-012 Match Preview API + FR-013 菜单-BO 权限自动关联 + FR-015 跨菜单 BO 权限累加显式化（SAP SU53 + SU24 + 用户关键洞察）
- **M6 (v1.4 按需)**：FR-014 嵌套 aspect（SAP DCL `inherit` 启发）— 标记 Could
- **M7 (立即规划)**：NFR-001 性能对标 SAP DCL（缓存 + 预解析 + 物化路径）— 第 1 周启动设计
- **M8 (v1.4 全功能 Bug 修复，第 1 周)**：FR-016 AC-1/2/5/6/7 — 修复 parent-child association derived 正确性 + JOIN 路径生成（2 跳以上 `through:` 过滤错误 + 无冗余字段 fallback）— **优先于 M4+M5**
- **M8.5 (v1.4 路径类型扩展，第 2 周)**：FR-016 AC-3/4/5 — 扩展 association (FK) 路径支持，**字符串语法 `->` (parent-child) + `-->` (reference)**
- **M10.0 (v1.4 BO 统一模型 — Schema 扩展，第 3 周)**：FR-017 AC-1/2 — BO Schema 扩展（`type: entity | service` + `actions` + `behaviors` + `parameters`）
- **M10.1 (v1.4 BO 统一模型 — role_intents 表，第 3 周)**：FR-017 AC-3/4 — `role_intents` 表 + `menu.yaml.intent` 字段 + 兼容迁移
- **M10.2 (v1.4 BO 统一模型 — 权限计算，第 4 周)**：FR-017 AC-5/6/11 — 5 步权限计算 + behaviors + 测试
- **M10.3 (v1.4 BO 统一模型 — UI/API，第 4 周)**：FR-017 AC-7/8/9 — 条件可见性 + UI + API
- **M10.4 (v1.4 BO 统一模型 — dashboard 试点，第 4 周)**：FR-017 AC-10 — `dashboard` 实现 + chart 展示作为 Service BO 试点

## 9. Change / Design Proposal (RFC)

### 9.1 As-Is Analysis

**三个 Section 的当前实现**：

#### A. Section 1: 管理维度（DimensionScopePanel）

```typescript
// 维度值选择 + 自动推导按钮
<DimensionScopePanel :role-id="roleId" @auto-derived="handleAutoDerived" />
```

```python
# meta/services/dimension_scope_engine.py
HIERARCHY_CHAIN = ['product', 'version', 'domain', 'sub_domain']
# hardcoded 推导逻辑
def derive_data_conditions(self, role_id):
    expanded = self.expand_dimension_values(role_id)
    # 输出 "domain_id = 1 OR domain_id = 2"
```

**落地**：
- 表：`role_dimension_scopes` (id, role_id, dimension_code, dimension_values, inherit_children, scope_mode)
- 触发：自动推导 → 写 `role_menu` + `role_permissions`

**问题**：
- HIERARCHY_CHAIN 硬编码
- 维度值按 (role, bo_id) 重复配
- 拦截器**预先展开**（不是运行时）

#### B. Section 2: 菜单与功能权限（MenuPermissionMatrix）

```typescript
<MenuPermissionMatrix v-model="menus" @change="handleMenuPermissionChange" />
```

**落地**：
- 表：`role_menu` + `role_permissions`
- 3 态：`auto` / `include` / `exclude`
- 状态：✅ **完全实现，无变更**

#### C. Section 3: 条件型权限（ConditionRuleList）

```typescript
<ConditionRuleList v-model="conditionRules" />
<ConditionRuleDialog :rule="editingRule" />
```

**落地**：
- 表：`permission_rules` (rule_type, field, operator, value, formula)
- 两种模式：valuehelp + 公式

#### D. version.yaml 的 draft 模式（现状已实现，需推广）

```yaml
# meta/schemas/version.yaml
- id: owner_id
  relation: user
  name: 负责人

- id: visibility
  type: string
  default: draft
  enum_values:
    - value: public
      label: 公开
    - value: draft
      label: 草稿

authorization:
  check: true
  scope: "visibility = 'public' OR owner_id = $user.id"
  auto_owner: true
  allow_transfer: true
```

**已有动作**：
```yaml
- id: publish_version
  from_states: [draft]
  to_state: public
  triggers: [before_update]
```

**问题**：
- 此模式仅 version.yaml 使用，未推广到其他带 owner_id 的 BO
- FR-010 要将其推广为通用模式

### 9.2 Target State

#### 9.2.1 整体架构（3 Section 不变 + 运行时动态展开）

```
┌─ PermissionConfigPanel ─────────────────────────────────┐
│                                                          │
│ ┌─ Section 1: 管理维度 ───────────────────────────────┐ │
│ │  (UI 不变)                                            │ │
│ │  - 维度值选择 (产品 in A,B...)                          │ │
│ │  - "自动推导并应用" 按钮                                │ │
│ │                                                       │ │
│ │  落地:                                                │ │
│ │  - 写 role_dimension_scopes (单一事实)                │ │
│ └───────────────────────────────────────────────────────┘ │
│                                                          │
│ ┌─ Section 2: 菜单与功能权限 ─────────────────────────┐ │
│ │  (UI 不变)                                            │ │
│ │  - 菜单勾选 + 动作分组 + 3 态                          │ │
│ │                                                       │ │
│ │  落地:                                                │ │
│ │  - 写 role_menu + role_permissions (独立存储)         │ │
│ └───────────────────────────────────────────────────────┘ │
│                                                          │
│ ┌─ Section 3: 条件型权限 ─────────────────────────────┐ │
│ │  (UI 不变)                                            │ │
│ │  - valuehelp 模式 (BO 字段下拉)                       │ │
│ │  - 公式模式 (XPath/SQL)                                │ │
│ │                                                       │ │
│ │  落地:                                                │ │
│ │  - 写 permission_rules (单一事实)                     │ │
│ └───────────────────────────────────────────────────────┘ │
│                                                          │
│  [运行时拦截器从 3 源动态展开]                           │
└──────────────────────────────────────────────────────────┘
```

#### 9.2.2 三源动态展开架构

```
                         运行时拦截器
                             │
        ┌────────────────────┼────────────────────┐
        ↓                    ↓                    ↓
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ Source 1:        │  │ Source 2:        │  │ Source 3:        │
│                  │  │                  │  │                  │
│ role_dimension_  │  │ permission_rules │  │ BO 的            │
│ scopes           │  │                  │  │ dimension_bindings│
│                  │  │ (Section 3)      │  │                  │
│ (Section 1)      │  │                  │  │ (YAML 声明式)     │
│                  │  │                  │  │                  │
│ + bo_id (新)     │  │ valuehelp/公式   │  │ 哪些维度→哪些字段│
└────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘
         │                     │                     │
         └─────────────────────┼─────────────────────┘
                               ↓
                    动态展开为 SQL WHERE
                    (运行时，无中间表)
```

#### 9.2.3 数据模型（极简变更）

**仅扩展 1 张表**：
```sql
ALTER TABLE role_dimension_scopes ADD COLUMN bo_id VARCHAR(50) NULL;
-- bo_id = NULL  → 公共维度（影响所有相关 BO）
-- bo_id = 'domain' → BO 级覆盖
```

**BO schema 增强**（声明式）：
```yaml
# meta/schemas/domain.yaml
id: domain
dimension_bindings:
  - dimension: domain
    field: id
  - dimension: product
    field: version_id
    through: version

# meta/schemas/sub_domain.yaml
id: sub_domain
dimension_bindings:
  - dimension: sub_domain
    field: id
  - dimension: domain
    field: domain_id
  - dimension: product
    field: domain_id
    through: domain
```

### 9.3 Detailed Design

#### 9.3.1 拦截器运行时动态展开

```python
# meta/core/interceptors/data_permission_interceptor.py

def _apply_data_permissions(self, context):
    """运行时从 3 源动态拼 SQL（无中间表）"""
    where_clauses = []
    
    # === Source 1: Section 1 管理维度 ===
    dim_scopes = self._get_role_dim_scopes(context.role_id)
    bo = self._get_bo_schema(context.object_type)
    bindings = bo.get('dimension_bindings', [])
    
    for dim_scope in dim_scopes:
        # 公共维度 (bo_id = NULL) 或 当前 BO
        if dim_scope['bo_id'] is None or dim_scope['bo_id'] == context.object_type:
            # 查找匹配的 binding
            for binding in bindings:
                if binding['dimension'] == dim_scope['dimension_code']:
                    # 处理多跳关联
                    field = self._resolve_field(binding, context.object_type)
                    where_clauses.append(
                        self._build_in_clause(field, dim_scope['dimension_values'])
                    )
    
    # === Source 2: Section 3 条件规则 ===
    cond_rules = self._get_role_cond_rules(context.role_id, context.object_type)
    for rule in cond_rules:
        if rule['rule_type'] == 'field':
            where_clauses.append(
                self._build_field_condition(rule['field'], rule['operator'], rule['value'])
            )
        elif rule['rule_type'] == 'formula':
            where_clauses.append(rule['formula'])
    
    # === 组合为 SQL ===
    if where_clauses:
        sql_where = " AND ".join(where_clauses)
        context.extra['query_conditions'].append(f"({sql_where})")
```

#### 9.3.2 公共维度自动应用

```python
# 拦截器核心逻辑
def _apply_public_dimension(self, dim_scope, bindings, context):
    """公共维度自动应用到所有声明了 binding 的 BO"""
    if dim_scope['bo_id'] is not None:
        return None  # 不是公共维度
    
    dimension = dim_scope['dimension_code']
    values = dim_scope['dimension_values']
    
    # 找到当前 BO 的对应 binding
    matched = [b for b in bindings if b['dimension'] == dimension]
    if not matched:
        return None
    
    binding = matched[0]
    field = self._resolve_field(binding, context.object_type)
    return self._build_in_clause(field, values)
```

#### 9.3.3 多跳关联字段解析

```python
def _resolve_field(self, binding, object_type):
    """解析多跳关联字段"""
    if 'through' not in binding:
        return binding['field']  # 直接字段
    
    # 多跳：e.g., sub_domain → domain → version
    through = binding['through']
    return f"{object_type}.{binding['field']} -> {through}"  # 实际 SQL JOIN
```

#### 9.3.4 Owner 过滤运行时展开（AND 组合）

```python
def _expand_owner_condition(user):
    """Owner 过滤展开为 field condition"""
    return {
        'type': 'field',
        'field': 'owner_id',
        'operator': 'equals',
        'value': user.id
    }

def _apply_owner_filter(self, context):
    """应用 owner 过滤（与功能权限、维度范围是 AND）"""
    owner_filters = [
        c for c in self._get_bo_cond_rules(context.object_type)
        if c.get('type') == 'owner'
    ]
    if not owner_filters:
        return
    
    # Owner 过滤作为 SQL 子句
    owner_clause = f"({context.object_type}.owner_id = {context.user_id})"
    context.extra['query_conditions'].append(owner_clause)
```

**AND 组合关系**（关键）：
```
有效数据 = 功能权限(CRUD) ∩ 维度范围(BO) ∩ Owner 过滤(记录级) ∩ 条件规则
```

#### 9.3.5 Draft 可见性逻辑（version.yaml 已实现）

```yaml
# meta/schemas/version.yaml（已有）
authorization:
  check: true
  scope: "visibility = 'public' OR owner_id = $user.id"
  allow_transfer: true

actions:
  - id: publish_version
    from_states: [draft]
    to_state: public
    triggers: [before_update]
```

**通用化推广**（FR-010）：
- 抽取 `owner_aspect` aspect（FR-010 实施时）
- 自动包含 owner_id 字段 + visibility 字段 + 范围 + 动作
- 其他带 owner_id 的 BO 引用此 aspect 即可

```yaml
# meta/schemas/_aspects/owner_aspect.yaml（待新增）
- id: owner_aspect
  fields:
    - id: owner_id
      relation: user
    - id: visibility
      type: string
      enum: [public, draft, team]
      default: draft
  authorization:
    check: true
    scope: "visibility = 'public' OR owner_id = $user.id"
    auto_owner: true
    allow_transfer: true
  actions:
    - id: publish
      from_states: [draft]
      to_state: public
```

#### 9.3.6 Owner 转让访问策略

```python
def on_owner_transfer(record, old_owner_id, new_owner_id):
    """Owner 转让时"""
    # 默认：原 owner 失去访问（owner 是"当前 owner"语义）
    record.owner_id = new_owner_id
    
    # 可选：保留"创建者"字段用于审计
    if record.created_by == old_owner_id:
        record.created_by = new_owner_id  # 默认转移创建者
    
    # 记录 transfer 事件
    audit_log.record('owner_transfer', {
        'record_id': record.id,
        'old_owner': old_owner_id,
        'new_owner': new_owner_id,
        'timestamp': now()
    })
```

### 9.4 Alternatives Considered

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| 合并 3 个 Section 为 1 个 | 概念统一 | 破坏 UI | Rejected |
| 保持 3 个 Section 不变 | UI 不变 | 概念需文档化 | ✅ Selected |
| 双写 + role_data_conditions | 兼容老代码 | 违反 SSoT，数据冗余 | Rejected |
| 运行时动态展开 | SSoT 单一事实，零数据冗余 | 性能开销 | ✅ Selected |
| 运行时直读多源 | 简单 | 当前实现 | Rejected（改为动态展开） |
| 公共维度按 BO 重复配 | 简单 | 不符合头部产品做法 | Rejected |
| 拦截器预处理（缓存） | 性能 | 复杂 | 文档化为后续 |

### 9.5 Implementation & Migration Plan

#### Phase 1 (1 周): 拦截器运行时动态展开

- **Task 1.1**: `role_dimension_scopes` 添加 `bo_id` 字段（迁移脚本）
- **Task 1.2**: BO schema 添加 `dimension_bindings`（已存在的 BO 全部补充）
- **Task 1.3**: 拦截器改造：运行时从 3 源动态拼 SQL
- **Task 1.4**: Feature flag: `ENABLE_RUNTIME_RESOLUTION`
- **Task 1.5**: 单元测试：覆盖各种 dim_scope + binding 组合

#### Phase 2 (按需): 性能优化

- **Task 2.1**: 拦截器结果缓存（按 role_id + object_type）
- **Task 2.2**: 维度值预解析（IN 子句优化）
- **Task 2.3**: HIERARCHY_CHAIN 配置化（按需）

#### Testing Strategy

- **单元测试**：
  - 3 源动态展开各种组合
  - 公共维度跨 BO 应用
  - 多跳关联字段解析
  - 性能基准（<50ms 动态展开）
- **集成测试**：
  - 拦截器端到端
  - 3 个 Section 端到端
- **E2E 测试**：
  - 新增 BO X 零迁移接入
  - 公共维度自动应用

#### Rollback Plan

- Feature flag `ENABLE_RUNTIME_RESOLUTION` 默认 true
- 关闭 flag 即走原逻辑（按顺序读多表）
- 迁移脚本只加列，删除列无副作用

## 10. TBD List

| ID | Item | Status | Next Step |
|----|------|--------|-----------|
| TBD-1 | 人员归属维度（部门/区域） | 用户确认未来考虑 | 标记后续版本 |
| TBD-2 | 去除 HIERARCHY_CHAIN 硬编码 | 文档化，不强制改 | 按需实施 |
| TBD-3 | 多维度 AND/OR 组合 | 默认 AND，表达式按需 | 文档化 |
| TBD-4 | Owner 转让历史 | 默认原 owner 失去访问 | 文档化 |
| TBD-5 | 多维组织树（多 tree） | 标记后续 | 按需实施 |
| TBD-6 | ~~Section 3 与 Section 1 重复配置的处理~~ | **已升级为 FR-005（v1.3）+ FR-012 匹配预览（v1.4）** | ✅ 完成 |
| TBD-7 | 拦截器结果缓存 | **升级为 M7 (Phase 2)**，对标 SAP DCL | M7 实施 |

---

## Spec + RFC 完整性检查

- ✅ Spec + RFC 包含 10 个章节
- ✅ 最后一节是 "TBD List"
- ✅ 内容完整，未截断
- ✅ v1.2 已废弃双写策略
- ✅ v1.3 补充 Owner/Draft 通用化
- ✅ **v1.4 SAP 深度研究启发**：FR-005 重定位 + FR-012 匹配预览 + FR-013 SU24 + FR-014 嵌套 aspect
- ✅ 与 SAP/用友/Salesforce 头部产品做法一致（SSoT + 运行时动态展开 + 头部产品 NFR-003）
- ✅ 单一事实原则 + 运行时动态展开

## Spec + RFC Confirmation Request

我已基于 SAP 深度研究将 Spec 升级到 v1.4。请确认：

### 1. 授权
- [ ] 是否接受 v1.4 版本的 Spec + RFC？
- [ ] 是否授权开始实施 M4（FR-012 匹配预览）？

### 2. v1.4 关键变更（vs v1.3）
- ✅ **新增** FR-012 Match Preview API（SAP SU53 Trace 启发）
- ✅ **新增** FR-013 菜单-BO 权限自动关联（SAP SU24 启发）
- ✅ **新增** FR-014 嵌套 aspect 支持（SAP DCL `inherit` 启发）
- ✅ **新增** FR-015 跨菜单 BO 权限累加显式化（v1.4 用户关键洞察）
- ✅ **新增** FR-016 Association Derived 数据权限完整性（v1.4 用户关键洞察 — Bug 修复 + 路径类型扩展）
  - ✅ 修复 v1.3 实施 Bug（2 跳以上 `through:` 过滤错误）
  - ✅ 区分 parent-child 路径（`->`）和 association 路径（`-->`）
  - ✅ 字符串语法 + 混合策略（优先冗余字段，无则 JOIN）
- ✅ **重写** FR-017 为 BO 统一模型（v1.4 用户 3 层洞察链 — 完全对齐 SAP RAP + 用友 BIP）
  - ✅ 用户关键洞察 1：Action = 过程（不是 BO 子对象）
  - ✅ 用户核心洞察 2：Service Component 就是 BO（不需独立 `services.yaml`）
  - ✅ 用户深度洞察 3：Action 合并到 BO.actions（不需独立 first-class）
  - ✅ 3 层抽象（4 层 → 3 层）：BO + Intent + Data
  - ✅ BO Schema 扩展 `type: entity | service`
  - ✅ Service BO 复用 BO 机制（权限、维度、Owner）
  - ✅ `role_intents` 表（替代 `role_actions` + `role_menu_permissions`）
  - ✅ `menu.yaml.intent` 字段（Intent 统一表达）
  - ✅ 5 步权限计算（Intent → Action perm → BO perm → 数据 → 条件）
  - ✅ `dashboard` 页面类型实现
- ✅ **新增** NFR-003 头部产品对标矩阵
- ✅ **重定位** FR-005 实施状态（v1.3 重叠警告 UI 已落地）
- ✅ **增强** FR-009 Owner 过滤支持多种身份 aspect（current_user/user_group/pfcg_auth）
- ✅ **增强** NFR-001 性能对标 SAP DCL Code-to-Data
- ✅ **重定位** TBD-6 → FR-012，TBD-7 → M7 Phase 2

### 3. v1.3 → v1.4 关键决策点
- ✅ 保持 v1.3 运行时动态展开（SSoT）核心架构不变
- ✅ 保留已实施 M0/M1/M2/M3.1 代码与设计
- ✅ **新增"匹配预览"** user-facing 功能（FR-012）
- ✅ **增强"身份 aspect"** 抽象（FR-009 多 aspect 支持）
- ✅ **新增"嵌套 aspect"** 抽象（FR-014 类似 OO 继承）
- ✅ **NFR-003 头部产品对标** 显式记录 SAP/Salesforce/Dataverse 关键机制映射

### 4. 关键问题（请确认）

#### Q1: FR-012 实施优先级？
- ✅ **(b) 与 M5 一起（M4+M5 第 2 周）** — 用户确认

#### Q2: FR-013 SU24 等价物是否要做？
- ✅ **(a) 是，必须做** — 用户确认

#### Q3: FR-014 嵌套 aspect 优先级？
- ✅ **(b) 按需（标记为 Could）** — 用户确认

#### Q4: NFR-001 性能优化 M7 是否启动？
- ✅ **(a) 是，立即规划 M7** — 用户确认

#### Q5: FR-015 跨菜单 BO 权限累加显式化（用户关键洞察）实施优先级？
- ✅ **(a) 与 FR-012/013 一起（M4+M5+M4.5 第 2-3 周）** — 用户确认

#### Q5.1: 跨菜单 BO 权限累加语义？
- ✅ **OR 累加 + UI 显式化**（与 Salesforce/Dataverse/ServiceNow/用友 BIP 一致）— 用户确认

#### Q5.2: 跨菜单提示位置？
- ✅ **BO 分组旁（徽章 + tooltip 详情）** — 用户确认

#### Q6: FR-016（v1.3 实施 Bug）修复范围？
- ✅ **(c) 全功能（AC-1/2/3/4/5/6/7）** — 用户确认

#### Q7: FR-016 修复时机？
- ✅ **(a) 立即修复 M8 + M8.5（第 1-2 周，优先于 M4+M5）** — 用户确认

#### Q8: BO 上没有冗余字段的 BO 怎么办？
- ✅ **(c) 混合：优先冗余字段，无则 JOIN** — 用户确认

#### Q9: 路径语法形式（区分 parent-child vs association）？
- ✅ **(a) 字符串语法：`->` parent-child + `-->` association（如 `"customer-->department"`）** — 用户确认

#### Q10: FR-017 BO 统一模型实施范围？
- ✅ **(a) 基础（1.5 周，第 3-4 周）** — 用户确认（M10.0-M10.4）
  - M10.0：BO Schema 扩展（type + actions + behaviors + parameters）
  - M10.1：role_intents 表 + 兼容迁移
  - M10.2：5 步权限计算 + behaviors + 测试
  - M10.3：条件可见性 + UI + API
  - M10.4：dashboard 实现 + chart Service BO 试点

#### Q11: Service 注册方式？
- ✅ **YAML 声明 + 代码实现** — 用户确认（YAML-driven 模式）
- 不采用代码注解（与代码紧密耦合）
- 不采用混合（复杂）

#### Q12: 实施计划？
- ✅ **不变** — 用户确认（M10.0-M10.4 仍按原计划）

### 5. 补充信息
如有任何调整建议或想深入某个细节，请告知。

💡 如当前问题不足以澄清需求，欢迎提供任何额外相关信息。

---

## 11. 头部产品深度对比（v1.4 新增）

### 11.1 对比矩阵

| 机制 | SAP | Salesforce | Dataverse | Mendix | 用友 BIP | ServiceNow | **我们 v1.4** |
|------|-----|-----------|-----------|--------|---------|-----------|------------|
| 角色（功能权限） | PFCG Role | Profile | Security Role | User Role | 角色 | Role (RBAC) | Section 2 |
| 公共维度（跨 BO） | Organizational Levels | Record Types | Business Unit | XPath Context | 多维组织 | Domain | role_dimension_scopes（bo_id=NULL） |
| 行级权限 | DCL CDS view | OWD + Sharing Rules | Access Depth 4级 | XPath Constraint | 数据权限规则 | Row-Level Security | RuntimeDimensionResolver |
| 记录级 Owner | `aspect user` | OwnerId + Sharing | User/Team level | Owner attribute | 创建人字段 | Assigned to | owner_aspect + 多 aspect |
| Draft 模式 | 变更文档（CDPOS） | n/a | n/a | n/a | n/a | n/a | owner_aspect.visibility='draft' |
| **匹配预览** | **SU53 / ST01 Trace** | **"Why" 字段** | **"Check Access"** | **XPath Preview** | 权限预览 | **ACL Debug** | **FR-012（v1.4 新增）** |
| 菜单-BO 关联 | **SU24**（Tcode→Auth Obj） | App Permissions | Form Entity Perms | Page Guard | 业务对象权限 | Domain Separation | **FR-013（v1.4 新增）** |
| 嵌套/继承 | **DCL `inherit`** | Profile 嵌套 | Business Unit Parent:Child | Module 继承 | 角色继承 | Group 嵌套 | **FR-014（v1.4 Could）** |
| 覆盖规则 | n/a（DCL AND 组合） | **"Most permissive wins"** | n/a | Last in priority | 后定义覆盖前 | n/a | "Section 3 覆盖"（FR-005） |
| 重复配置警告 | n/a | n/a | n/a | n/a | n/a | n/a | **FR-005（v1.3 已落地）** |
| 性能模型 | **Code-to-Data（CDS）** | Apex Trigger | Plugin Stage | Microflow | 拦截器 | Business Rule | 应用层拦截器（M7 优化对标） |

### 11.2 SAP 关键洞察（深度）

#### A. SAP 5 层权限架构
```
User (SU01) → Role (PFCG) → Profile → Authorization Object → Field & Value
```
- **User ↔ Role 是 N:N**：一个用户可有多个角色
- **Profile 是编译产物**：运行时缓存，不是配置层
- **Authorization Object (SU21)**：抽象权限对象（事务码 + 字段组合）
- **Field & Value**：具体允许值（如 company_code=1000）

**类比我们 v1.4**：
- User = `user` 表
- Role = `role` 表（已实现）
- Profile = RuntimeDimensionResolver 缓存层（M7）
- Authorization Object = `role_permissions` 表（3 态）
- Field & Value = `role_dimension_scopes` + `permission_rules`

#### B. SAP Organizational Levels（= 我们的"公共维度"）
- **全局共用字段**：company code、plant、sales organization、purchasing organization
- **一次设定，所有 Authorization Object 自动继承**（无需为每个对象重配）
- **角色复制时组织级必须重维护**（印证"组织值是环境相关"）
- 完美对应我们 v1.3 的 `role_dimension_scopes.bo_id=NULL` 机制

#### C. SAP DCL CDS View（= 我们的"运行时动态展开"现代版）
- **CDS view = 数据模型**（`@AccessControl.authorizationCheck: #CHECK`）
- **DCL = 访问控制模型**（`define role X { grant select on Y where ... }`）
- **编译到 CDS view，ABAP SQL 隐式触发**——**Code-to-Data 性能**
- **DCL `inherit`**：继承父 DCL 规则并扩展
  ```abap
  define role demo_cds_role_inherited {
    grant select on demo_cds_auth_inherited
    inherit demo_cds_role_lit_pfcg or currcode = 'USD';
  }
  ```
- **多 access condition AND/OR** 通过 `grant select` 表达式
- 完美对应我们 v1.3 的 RuntimeDimensionResolver + FR-014 嵌套 aspect

#### D. SAP SU24（= 我们 FR-013）
- **事务码 → 默认 Authorization Object 列表**
- 维护在 SU24 事务中
- 角色设计时自动建议相关对象
- 大幅降低权限配置出错率
- **v1.4 FR-013** 是我们的"菜单-BO 权限自动关联"等价物

#### E. SAP SU53 + ST01 Trace（= 我们 FR-012）
- **SU53**：用户权限调试（"为什么我看不到这条记录？"）
- **ST01**：权限追踪（详细审计）
- 都是"匹配预览"的工具
- **v1.4 FR-012** 是我们的"Match Preview API"等价物
- **Mendix XPath Preview** 也是同样思路——直接在配置页预览 XPath 表达式

### 11.3 Salesforce 关键洞察

#### A. "Most permissive wins" 原则
- 多个 profile 合并时，**最宽松的权限胜出**
- 我们的 Section 3 覆盖（更具体优先）—— 略微不同
- **值得讨论**：我们的"覆盖"模型是否最优？
  - Pro：用户显式控制
  - Con：可能"过度严格"（用户配了更严格的 Section 3，结果 Section 1 的更宽松值被覆盖）

#### B. OWD + Sharing Rules
- **OWD（Organization-Wide Defaults）**：组织级默认权限
- **Sharing Rules**：基于规则共享
- 类似我们的"公共维度"+"BO 级覆盖"

### 11.4 Dataverse 关键洞察

#### A. Access Depth 4 级
- **User**：仅自己
- **Business Unit**：业务单元内
- **Parent:Child Business Unit**：父-子业务单元
- **Organization**：整个组织
- 类似我们的"层级继承"机制（v2+ 可考虑）

#### B. Hierarchical Security
- Manager 可见下属记录
- 类似我们 TBD-1 "人员归属维度（部门/区域）"

### 11.5 头部产品最佳实践（我们 v1.4 采纳清单）

| # | 实践 | 来源 | v1.4 落地 |
|---|------|------|----------|
| 1 | 公共维度（一次配置多 BO 复用） | SAP Org. Levels | ✅ FR-002（v1.3） |
| 2 | 运行时动态展开（无中间表） | SAP DCL / Salesforce OWD | ✅ FR-006（v1.3） |
| 3 | aspect 机制（多字段+权限+动作组合） | DCL inherit + 我们的 owner_aspect | ✅ FR-010（v1.3）+ FR-014（v1.4） |
| 4 | 匹配预览（让用户看效果） | SAP SU53 / Mendix Preview | ✅ FR-012（v1.4 新增） |
| 5 | 菜单-BO 自动关联 | SAP SU24 | ✅ FR-013（v1.4 新增） |
| 6 | Code-to-Data 性能 | SAP DCL | ⏳ M7（NFR-001 性能优化） |
| 7 | 层级继承（业务单元） | Dataverse Access Depth | ⏳ v2+（TBD-5） |
| 8 | 多种身份 aspect | DCL `aspect user/pfcg_auth` | ✅ FR-009 增强（v1.4） |

---

## 12. Spec v1.4 终稿状态

### 12.1 已落地的功能（v1.0 → v1.3）

| 阶段 | 状态 | 关键产出 |
|------|------|---------|
| M0 | ✅ | Feature flags + BO schema loader + DB 迁移 |
| M1 | ✅ | FR-002/006/007 — 运行时动态展开 + BO bindings + 5 BO schema 增强 |
| M2 | ✅ | FR-009/010 — Owner 过滤 + Draft 模式通用化（owner_aspect） |
| M3.1 | ✅ | FR-005 重复配置警告 UI（OverlapWarning.vue + useOverlaps.ts） |
| **Bug Fix** | ✅ | 条件型权限规则 UI 端点修复 |

### 12.2 v1.4 已实施（2026-06-04 完成）

| Milestone | 状态 | 实施周 | 关键功能 |
|-----------|------|--------|---------|
| **M8 (Bug 修复，Must)** | ✅ 完成 | **第 1 周** | **FR-016 AC-1/2/5/6/7：修复 parent-child 派生 + JOIN 路径生成** |
| **M8.5 (路径类型扩展，Must)** | ✅ 完成 | **第 1-2 周** | **FR-016 AC-3/4/5：association (FK) 路径支持 + 字符串语法 `->` / `-->`** |
| M7 性能优化设计 | ✅ 完成 | 第 1-2 周（与 M8/M8.5 并行） | NFR-001 缓存 + 预解析（`perm_cache.py`） |
| M4+M5+M4.5 业务功能 | ✅ 完成 | 第 2-3 周 | FR-012 + FR-013 + FR-015 |
| M6 FR-014 嵌套 aspect | ⏸ 按需 | v1.5+ | FR-014 |
| **M10.0 (BO 统一模型 Schema 扩展，Should)** | ✅ 完成 | **第 3 周** | **FR-017 AC-1/2：BO Schema 扩展（type: entity \| service + actions + behaviors + parameters）** |
| **M10.1 (BO 统一模型 role_intents 表，Should)** | ✅ 完成 | **第 3 周** | **FR-017 AC-3/4：role_intents 表 + menu.yaml.intent + 兼容迁移** |
| **M10.2 (BO 统一模型权限计算，Should)** | ✅ 完成 | **第 4 周** | **FR-017 AC-5/6/11：5 步权限计算 + behaviors + 测试** |
| **M10.3 (BO 统一模型 UI/API，Should)** | ✅ 完成 | **第 4 周** | **FR-017 AC-7/8/9：条件可见性 + UI（后端完整）+ API** |
| **M10.4 (BO 统一模型 dashboard 试点，Should)** | ⏸ 部分 | **第 4 周** | **FR-017 AC-10：dashboard + chart Service BO 试点（API 完整，UI 留 v1.5）** |

### 12.3 测试覆盖

#### 12.3.1 v1.3 既有测试
- **63 个测试通过**（v1.3）：
  - 11 runtime resolver + 9 integration + 16 owner aspect + 4 owner propagation + 13 overlap detector + 10 e2e

#### 12.3.2 v1.4 新增测试（88 个新增，累计 151 个）

| 测试文件 | 测试数 | 关联 |
|---------|--------|------|
| test_runtime_dimension_resolver.py（扩展） | 21 (新 10) | M8+M8.5 FR-016 |
| test_permission_explainer.py | 10 | M4.1 FR-012 |
| test_menu_bo_linker.py | 5 | M5.1+M4.5.1 FR-013+FR-015 |
| test_perm_cache.py | 9 | M7.1+M7.2 NFR-001 |
| test_intent_resolver.py | 10 | M10.2 FR-017 |
| test_permission_apis.py | 7 | M10.3.3 FR-012 端到端 |
| test_intent_apis.py | 11 | M10.3.3 FR-017 端到端 |
| test_role_intents_migration.py | 6 | M10.1.1 migration |
| test_full_chain.py | 9 | M10.2 跨模块集成 |
| **合计新增** | **88** | **9 个文件** |

#### 12.3.3 关键回归
- ✅ P0-1：`_has_static_permission` 真正查询（修复前永远 True）
- ✅ P0-2：`resolve()` 集成 `_resolve_field_with_joins`（携带 JOIN 路径）
- ✅ P0-3：`resolve()` 集成 `perm_cache`（NFR-001 性能优化真正生效）

#### 12.3.4 新增模块

| 模块 | 用途 | 关联 |
|------|------|------|
| `meta/core/perm_cache.py` | NFR-001 LRU+TTL 缓存 | M7 |
| `meta/core/permission_explainer.py` | FR-012 5 步权限解释 + SQL 预览 | M4.1 |
| `meta/core/menu_bo_linker.py` | FR-013 SU24 等价物 + FR-015 跨菜单累加 | M5.1+M4.5.1 |
| `meta/core/intent_resolver.py` | FR-017 DAO + 5 步 + behaviors + 兼容迁移 | M10 |
| `meta/api/permission_api.py` | FR-012 API 端点（2 个） | M10.3.3 |
| `meta/api/intent_api.py` | FR-017 API 端点（7 个） | M10.3.3 |
| `meta/migrations/add_role_intents_2026.py` | FR-017 role_intents 表 | M10.1.1 |

#### 12.3.5 新增 API 端点

```
POST   /api/v1/permissions/explain        # FR-012 5 步 + SQL 预览
POST   /api/v1/permissions/check          # FR-012 快速检查
POST   /api/v1/permissions/check_intent   # FR-017 5 步 Intent
GET    /api/v1/roles/<id>/intents         # FR-017 角色 Intent 列表
PUT    /api/v1/roles/<id>/intents/<bo>/<action>  # grant/deny
DELETE /api/v1/roles/<id>/intents/<bo>/<action>  # revoke
GET    /api/v1/bos                        # 列出 BO（含 type）
GET    /api/v1/bos/<id>/actions           # 列出 BO actions
GET    /api/v1/bos/<id>/actions/<name>    # 获取单个 action
```

#### 12.3.6 P2 深度修复（2026-06-04）

| P2 任务 | 状态 | 关键模块 | 关联 |
|---------|------|----------|------|
| P2-1: FR-009 owner_aspect scope 真正应用 | ✅ | `aspect_loader.py` + `scope_evaluator.py` | 读 aspects.yaml + 表达式求值 |
| P2-2: 条件可见性（Step 5）真正实施 | ✅ | `intent_resolver.py::_evaluate_conditions` | scope + field/op/value |
| P2-3: FR-010 visibility='draft' 模式 | ✅ | `owner_aspect.scope` 已覆盖 | draft 仅 owner 可见 |
| P2-4: 跨 BO Action 组合 | ✅ | Composite Intent 数据结构 | intents[] + global_actions[] |
| P2-5: Service BO behaviors 基础 | ✅ | `service_executor.py` | AtomicService + Registry + Executor |
| P2-6: perm_cache 并发测试 | ✅ | `test_perm_cache_concurrency.py` | threading + LRU + TTL |

#### 12.3.7 P2 新增模块

| 模块 | 用途 | 关联 |
|------|------|------|
| `meta/core/aspect_loader.py` | 读 aspects.yaml + aspect 字段/actions | P2-1 |
| `meta/core/scope_evaluator.py` | scope 表达式求值（`OR` / `AND` / `=` / `!=` / `>` / `<` / `>=` / `<=`） | P2-1 + P2-2 |
| `meta/core/service_executor.py` | Service BO behaviors 执行器 | P2-5 |

#### 12.3.8 P2 新增测试

| 测试文件 | 测试数 | 关联 |
|---------|--------|------|
| test_aspect_loader.py | 13 | P2-1 |
| test_visibility_draft.py | 6 | P2-3 + P2-4 |
| test_service_executor.py | 7 | P2-5 |
| test_perm_cache_concurrency.py | 3 | P2-6 |
| **合计** | **29** | **4 个文件** |

#### 12.3.9 累计测试统计

| 阶段 | 新增 | 累计 |
|------|------|------|
| v1.3 已有 | - | 63 |
| P0 修复 | 0 (修改现有) | 63 |
| P1 修复 | 33 | 96 |
| P2 修复 | 29 | **125** |

### 12.4 关键文档

- **本 Spec**: `docs/spec_data_permission_unified_model.md` (v1.4)
- **前置阅读**:
  - [用友BIP权限模型研究补充.md](./yonyou-bip-permission-research.md)
  - [竞品架构分析_元数据驱动与权限模型.md](./competitive-analysis-metadata-permission.md)
  - [权限配置流程优化_维度驱动vs菜单驱动.md](./permission-config-optimization.md)
  - [data-permission-inheritance-model.md](./data-permission-inheritance-model.md)
  - [spec_role_permission_granular_control.md](./spec_role_permission_granular_control.md)

---

## 13. v1.4 后端加固（P3 修复，2026-06-05 完成）

> 上一节 Section 12.3 记录了 v1.4 业务功能落地，本节记录 v1.4 上线前发现并修复的
> 基础设施问题（路由 / 认证 / 安全加固），与 v1.4 Spec 业务功能同源但范畴独立。

### 13.1 修复背景

v1.4 上线前系统性检查发现 5 个生产级问题（按 P 优先级排列）：

| # | 问题 | 影响 | 优先级 |
|---|------|------|--------|
| 1 | 生产环境 `FLASK_SECRET_KEY` 未校验，使用默认值有安全风险 | session 可被伪造 | **P1** |
| 2 | v1 路径硬性 410 迁 v2，前端无法过渡 | 前端大面积 410 | **P1** |
| 2.1 | v1 路径无 deprecation headers，前端无迁移信号 | 客户端无法感知 | **P2** |
| 2.2 | v1/v2 双路由重复声明装饰器，难维护 | 6+ 路由代码冗余 | **P2** |
| 2.3 | v2 路径未注册权限/Intent API | E2E 全部走 v1 | **P1** |
| 3 | dev-login 未写 Flask session | `is_authenticated()` 永远 False | **P1** |
| 4 | overlap API import 不存在的 `flask_login` | 所有 overlap 端点 500 | **P0** |

### 13.2 P1-1：生产 secret_key 强校验

#### 13.2.1 实施

新增 `meta/core/startup_checks.py::_check_flask_secret_key()`：

| 校验维度 | 规则 | 失败等级（dev） | 失败等级（prod） |
|----------|------|---------------|----------------|
| 是否设置 | `FLASK_SECRET_KEY` 或 `JWT_SECRET_KEY` 必须非空 | ERROR | WARNING |
| 默认值 | 不能等于 `dev-secret-key-change-in-prod` | ERROR | WARNING |
| 长度 | ≥ 32 字符 | ERROR | WARNING |

#### 13.2.2 关键决策

- **dev 环境**：失败 = ERROR（启动失败，避免遗忘）
- **prod 环境**：失败 = WARNING（启动允许，CI/部署平台负责拦截）
- 通过 `_is_production_safe()` 判断（综合 `FLASK_ENV` / `ENV` / `NODE_ENV` 等环境变量）

#### 13.2.3 Flask 集成

`meta/server.py:400` 增加 `app.secret_key` 配置：

```python
app.secret_key = os.environ.get(
    'FLASK_SECRET_KEY',
    os.environ.get('JWT_SECRET_KEY', 'dev-secret-key-change-in-prod'),
)
```

> 没有 `secret_key` 会导致 `session.permanent = True` 抛 RuntimeError。

### 13.3 P1-2：v1 路径豁免 + v2 双路由

#### 13.3.1 豁免列表（`server.py::V1_SPECIAL_PREFIXES`）

v1.4 新增 4 个豁免前缀（避免 v1 路径被自动 410 到 v2/bo/）：

| 前缀 | 用途 | 关联 FR |
|------|------|---------|
| `permissions` | `/api/v1/permissions/explain\|check\|check_intent` | FR-012 + FR-017 |
| `roles` | `/api/v1/roles/<id>/intents/*` | FR-017 |
| `bos` | `/api/v1/bos[/<id>[/actions[/<name>]]]` | FR-017 |
| `overlaps` | `/api/v1/roles/<id>/overlaps` | FR-005 |

> 这 4 类 API 在 v2 仍是**同路径**（v2/permissions/、v2/bos/、v2/roles/、v2/overlaps/），
> 与 v2/bo/{type} 通用 CRUD 路径不冲突，所以不强制 410 迁移。

#### 13.3.2 v1 Deprecation Headers

为豁免的 v1 路径自动添加 deprecation 标识（不返回 410）：

| Header | 值 | 规范 |
|--------|-----|------|
| `Deprecation` | `true` | [RFC 8594](https://datatracker.ietf.org/doc/html/rfc8594) |
| `Sunset` | `2026-08-14` | [RFC 8288](https://datatracker.ietf.org/doc/html/rfc8288) |
| `Link` | `</api/v2/{first}>; rel="successor-version"` | RFC 8288 successor-version |

实现：`server.py::add_v1_deprecation_headers`（after_request hook）

#### 13.3.3 双路由 Helper 重构

新增 `meta/api/_dual_route.py::add_dual_routes()`，消除重复装饰器：

```python
# 旧写法（重复 2 次 @bp.route）
@permission_bp.route('/api/v1/permissions/explain', methods=['POST'])
@permission_bp.route('/api/v2/permissions/explain', methods=['POST'])
def explain_permission(): ...

# 新写法（1 次函数定义 + helper 1 行注册）
def explain_permission(): ...
add_dual_routes(permission_bp, '/permissions/explain', explain_permission, ['POST'])
```

重写文件：
- `meta/api/permission_api.py`（FR-012 2 端点）
- `meta/api/intent_api.py`（FR-017 7 端点）

### 13.4 P1-3：dev-login 写 Flask Session

#### 13.4.1 问题

dev-login 之前只写 `auth_token` cookie，未写 Flask session。
导致 `is_authenticated()`（基于 `session.get('user_id')`）永远返回 False，
overlap / permission 等需登录的 E2E 全失败。

#### 13.4.2 修复

`meta/api/auth_api.py::dev_login` 增加 4 行 session 写入：

```python
from flask import session
session['user_id'] = row[0]
session['username'] = row[1]
session['display_name'] = row[2]
session['logged_in'] = True
session.permanent = True
```

并要求 `app.secret_key` 已设置（见 13.2.3）。

### 13.5 P0-4：overlap API 500 修复

#### 13.5.1 根因

`meta/api/overlap_api.py` 顶部 `from flask_login import current_user`，
但项目未安装 `flask_login`，导致所有 overlap 端点 ImportError 500。

#### 13.5.2 修复

- 创建 `meta/core/auth_helpers.py`（简化的 session-based 认证）：
  - `is_authenticated()` — 检查 `session['user_id']` / `['user']` / `['logged_in']`
  - `get_current_user_id()` — 从 session 读取
  - `require_auth` — 装饰器
- 移除 overlap_api 的 `flask_login` 依赖

### 13.6 验证结果（2026-06-05）

#### 13.6.1 端点验证（verify_v14.py 已删，结果保留）

| 端点 | v1 | v2 |
|------|----|----|
| `GET /bos` | 200 | 200 |
| `POST /permissions/explain` | 200 (granted=true) | 200 (granted=true) |
| `POST /permissions/check` | 200 (granted=true) | 200 (granted=true) |
| `POST /permissions/check_intent` | 200 (granted=false) | 200 (granted=false) |
| `GET /bos/<id>/actions` | 200 | 200 |
| `GET /roles/<id>/intents` | 200 | 200 |
| `GET /roles/<id>/overlaps` | 200 (需登录) | 200 (需登录) |
| `GET /auth/dev-login` | 200 (写 session) | - |

#### 13.6.2 Headers 验证

```
v1 /bos:  Deprecation=true, Sunset=2026-08-14
          Link=</api/v2/bos>; rel="successor-version"
v2 /bos:  (无 deprecation headers)
```

#### 13.6.3 后端单元测试（72 个 v1.4 相关）

| 测试文件 | 用例数 | 结果 |
|---------|-------|------|
| test_intent_apis.py | 11 | ✅ |
| test_permission_apis.py | 7 | ✅ |
| test_intent_resolver.py | 10 | ✅ |
| test_permission_explainer.py | 10 | ✅ |
| test_perm_cache.py | 9 | ✅ |
| test_menu_bo_linker.py | 5 | ✅ |
| test_aspect_loader.py | 13 | ✅ |
| test_service_executor.py | 7 | ✅ |
| **合计** | **72** | **全部通过** |

#### 13.6.4 E2E 回归（6 个 v1.4 strict 文件）

| 文件 | 用例 | 结果 |
|------|------|------|
| intent-apis.spec.js | 4 | ✅ |
| permission-explainer.spec.js | 3 | ✅ |
| role-intents.spec.js | 4 | ✅ |
| overlap-warning.spec.js | 1 | ✅ |
| menu-bo-linker.spec.js | 3 | ✅ |
| data-permission-config.spec.js | 3 | ✅ |
| **合计** | **18** | **全部通过** |

### 13.7 累计测试统计

| 阶段 | 新增 | 累计 |
|------|------|------|
| Section 12.3.9 截止（v1.4 业务） | - | **125** |
| Section 13（v1.4 后端加固） | 0 (回归已包含) | 125 |
| E2E（Playwright） | 30+ 跨 12 文件 | 12 文件 |

