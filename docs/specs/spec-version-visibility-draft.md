## 目录

1. [1. Background & Objectives](#1-background-objectives)
2. [2. Requirement Type Overview](#2-requirement-type-overview)
3. [3. Functional Requirements](#3-functional-requirements)
4. [4. Nonfunctional Requirements](#4-nonfunctional-requirements)
5. [5. External Interface Requirements](#5-external-interface-requirements)
6. [6. Transition Requirements](#6-transition-requirements)
7. [7. Constraints & Assumptions](#7-constraints-assumptions)
8. [8. Priorities & Milestones](#8-priorities-milestones)
9. [9. Change / Design Proposal (RFC)](#9-change-design-proposal-(rfc))
10. [10. TBD List](#10-tbd-list)

---
# Spec: Product Version Draft 可见性控制与 Code 唯一性

> **创建日期**: 2026-05-23
> **状态**: 已实现
> **优先级**: P1
> **关联 Spec**: spec-state-management-enhancement.md

---

## 1. Background & Objectives

### 1.1 问题陈述

当前所有 Product Version 对有权限的用户均可见，无法区分正式发布版本和个人 work-in-progress 版本。需要引入 draft 状态来支持个人层面的工作空间隔离。

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| **元数据驱动** | visibility 字段、authorization.scope、状态转换规则均通过 YAML 定义，不硬编码 |
| **状态管理复用** | 接入现有 `MetaStateTransition` 状态机框架 |
| **最小变更** | 扩展现有 authorization.scope 表达式引擎支持 OR 条件 |

### 1.3 关键决策记录

| 决策 | 选项 | 结论 | 理由 |
|------|------|------|------|
| 状态值 | public/private 还是 public/draft | **public/draft** | draft 通用性更高，业界认知统一 |
| Code 策略 | 共享序列 vs 独立序列 | **共享序列** | 简单，接受编号不连续 |
| 可变性 | immutable vs 状态机 | **状态机 (draft→public 单向)** | 接入元模型驱动状态管理 |
| 子对象继承 | 独立设置 vs 强制继承 | **强制继承** | 数据一致性 |
| 时间戳 | 存字段 vs Audit Log 推导 | **Audit Log 推导** | 避免数据冗余，复用 state_history API |

---

## 2. Requirement Type Overview

| Type | Applicable | Evidence |
|------|------------|----------|
| Business | Yes | 个人工作空间隔离 |
| User/Stakeholder | Yes | 多角色场景 |
| Solution | Yes | 元数据驱动 |
| Functional | Yes | FR-001 ~ FR-007 |
| Nonfunctional | Yes | NFR-001 ~ NFR-003 |
| External Interface | Yes | API + UI |
| Transition | Yes | 数据库迁移 |

---

## 3. Functional Requirements

### FR-001: Visibility 字段

- **Description**: Version 新增 `visibility` 字段，取值 `public` 或 `draft`。
- **Acceptance Criteria**:
  - `visibility` 类型 string，默认 `draft`
  - 通过 YAML 元数据定义
  - UI 中为下拉选择器
- **Priority**: Must

### FR-002: Draft 权限过滤

- **Description**:
  - `visibility = 'public'`：所有有权限的用户可见
  - `visibility = 'draft'`：仅 owner 可见
- **Acceptance Criteria**:
  - 列表 API 自动过滤非 owner 的 draft 版本
  - 详情 API 检查可见性，无权限返回 404
  - 过滤逻辑通过 `authorization.scope` 动态解析
- **Priority**: Must

### FR-003: 子对象强制继承

- **Description**: 子对象（domain/sub_domain/service_module/business_object）强制继承父版本的 visibility。
- **Acceptance Criteria**:
  - 子对象查询时自动应用父版本 visibility 过滤
  - 子对象无独立 visibility 字段
  - 通过 `authorization.inherit_scope_to_children: true` 配置驱动
- **Priority**: Must

### FR-004: Draft → Public 单向状态转换（状态机驱动）

- **Description**: 接入元模型状态管理，支持 draft 发布为 public。
- **Acceptance Criteria**:
  - 通过 `MetaStateTransition` 规则定义，触发时机 `before_update`
  - `from_states: [draft]`，`to_state: public`
  - 自动记录 `visibility_entered_at` 时间戳
  - public 无法逆向转回 draft（from_states 不含 public）
- **Priority**: Must

### FR-005: Version Code 共享序列号

- **Description**: draft 和 public 共享 KeyTemplate 序列号。
- **Acceptance Criteria**:
  - 使用现有 `{product_code}_{SEQ:2}` 模式，scope 不变
  - draft 消费序列号后，public 版本继续递增
  - 自动生成的 code 冲突时保存前重试（最多 10 次）
  - code 唯一约束不变
- **Priority**: Must

### FR-006: Owner 转移与导入导出

- **Description**: Owner 转移时 draft 保持 draft；导入导出与 public 行为一致。
- **Acceptance Criteria**:
  - Owner 转移后 visibility 不变
  - draft 版本可导入导出
  - 导入版本 owner 设为导入用户
- **Priority**: Should

### FR-007: 状态变更时间戳

- **Description**: visibility 变更时间戳直接从 Audit Log 推导，无需存到版本表。
- **Acceptance Criteria**:
  - `GET /api/manage/version/{id}/state_history?field=visibility` 返回变更时间线
  - 复用现有 `state_history` API，零额外成本
- **Priority**: Medium

---

## 4. Nonfunctional Requirements

### NFR-001: 元数据驱动

- **Description**: 整个方案通过 YAML 元数据驱动，不硬编码。
- **Priority**: Must

### NFR-002: 查询性能

- **Description**: visibility 过滤不影响显著性能。
- **Measurement**: 列表查询响应时间增加 < 50ms
- **Priority**: Should

### NFR-003: 审计日志

- **Description**: 创建/删除/发布 draft 版本复用现有审计日志机制。
- **Priority**: Should

---

## 5. External Interface Requirements

### IF-001: Version API 扩展

- **Type**: API
- **新增字段**: `visibility` (string, enum: ["public", "draft"], default: "draft")
- **过滤规则**: `GET /api/v2/bo/version` 自动过滤非 owner 的 draft

### IF-002: 获取可用状态转换

- **Type**: API
- **Endpoint**: `GET /api/manage/version/{id}/state_transitions`
- **Response**: 返回 `publish_version` 规则（含 label, icon, confirm_message 等 UI hints）

### IF-003: UI 交互

- **Type**: UI
- 创建表单：下拉选择 public/draft，默认 draft
- 列表：draft 版本显示"草稿"标签（黄色警告色）
- 详情：draft 版本显示"发布"按钮

---

## 6. Transition Requirements

### TR-001: 数据库迁移

- **Description**: versions 表添加 `visibility` 字段。
- **Migration SQL**:
```sql
ALTER TABLE versions ADD COLUMN visibility VARCHAR(200) NOT NULL DEFAULT 'draft';
```
- **备注**: visibility 变更时间戳不另存字段，通过 `GET /api/manage/version/{id}/state_history?field=visibility` 从 Audit Log 推导。
- **Rollback**: 删除 `visibility` 列

### TR-002: 现有数据兼容

- **Description**: 现有版本 visibility = 'public'（数据库默认），功能不受影响。

---

## 7. Constraints & Assumptions

### 7.1 Technical Constraints

- YAML 元数据驱动，不硬编码
- 与现有 authorization、KeyTemplate、StateTransition 机制兼容
- `_apply_scope_filter` 需扩展支持 OR 表达式解析

### 7.2 Business Constraints

- draft 发布后不可撤销（单向转换）
- 子对象强制继承父版本 visibility
- 默认 visibility = draft

### 7.3 Assumptions

- draft 覆盖测试/演示/开发中所有场景
- 共享序列号的不连续性是可接受的

---

## 8. Priorities & Milestones

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-001 | Visibility 字段 | Must | ✅ 已实现 |
| FR-002 | Draft 权限过滤 | Must | ✅ 已实现 |
| FR-003 | 子对象继承 | Must | ✅ 已实现 |
| FR-004 | 单向状态转换 | Must | ✅ 已实现 |
| FR-005 | Code 共享序列 | Must | ✅ 已实现 |
| FR-006 | Owner/导入导出 | Should | ✅ 已实现 |
| FR-007 | 时间戳 | Medium | ✅ 已实现 |

---

## 9. Change / Design Proposal (RFC)

### 9.1 As-Is 分析

- Version `authorization.scope: "owner_id = $user.id"`
- KeyTemplate: `{product_code}_{SEQ:2}`，scope=`product_code`
- 子对象有独立 authorization
- `_apply_scope_filter` 仅支持简单 `field = value` 表达式

### 9.2 Target State

- Version 添加 `visibility` 字段 + `visibility_entered_at` 时间戳
- `authorization.scope: "visibility = 'public' OR owner_id = $user.id"`（OR 表达式）
- 子对象通过 `inherit_scope_to_children: true` 继承
- 状态转换规则 `publish_version`: draft → public（MetaStateTransition 驱动）

### 9.3 关键设计

#### 9.3.1 YAML 配置 (version.yaml)

```yaml
fields:
  - id: visibility
    name: 可见性
    type: string
    db_column: visibility
    default: draft
    required: true
    enum_values:
      - { value: public, label: 公开, color: success, description: 所有人可见 }
      - { value: draft, label: 草稿, color: warning, description: 仅负责人可见 }
    ui: { widget: select, visible: true, editable: true }
    semantics: { meaning: 控制版本的可见范围, data_category: code,
                 import_visible: true, export_visible: true }

authorization:
  check: true
  scope: "visibility = 'public' OR owner_id = $user.id"
  inherit_to_children: true
  inherit_scope_to_children: true

rules:
  - id: publish_version
    name: 发布版本
    type: state_transition
    state_field: visibility
    from_states: [draft]
    to_state: public
    triggers: [before_update]
    ui_hints:
      label: 发布
      icon: rocket
      highlight: true
      confirm_message: "确定要发布此版本吗？发布后所有人可见，且不可撤销。"
```

#### 9.3.2 Scope 表达式解析流程

```
输入:  "visibility = 'public' OR owner_id = $user.id"
       ↓ $user.id → 42
       "visibility = 'public' OR owner_id = 42"
       ↓ _parse_scope_expression()
       [{type: 'or', conditions: [
         {field: 'visibility', operator: 'eq', value: 'public'},
         {field: 'owner_id', operator: 'eq', value: '42'}
       ]}]
       ↓ build_where_clause()
       WHERE (visibility = 'public' OR owner_id = 42)
```

#### 9.3.3 状态机模型

```
        create             publish (before_update, StateTransitionExecutor)
draft ─────────→ draft ────────────────────────────────────────────→ public
  ↑                                                                      │
  └──────────────── 不可逆（from_states 只有 [draft]）───────────────────┘
```

#### 9.3.4 子对象继承

```
查询 domain 列表
  → domain 无独立 authorization.scope
  → 查找父 version 的 authorization
  → 继承 inherit_scope_to_children: true
  → 对 domain 列表应用 "visibility = 'public' OR owner_id = $user.id"
```

### 9.4 代码变更清单

| 文件 | 变更 | 说明 |
|------|------|------|
| `meta/schemas/version.yaml` | 修改 | 添加 visibility 字段；扩展 authorization.scope；新增 publish_version 规则 |
| `meta/api/manage_api.py` | 修改 | `_apply_scope_filter` 支持 OR 表达式；`get_record` 增加 scope 过滤；`get_current_user()` 容错 |
| `meta/core/interceptors/data_permission_interceptor.py` | 修改 | `_apply_scope_filter` 支持 OR 表达式；新增 `_parse_scope_expression` |
| `meta/services/query_service.py` | 修改 | `SearchRequest` 添加 `include_deleted`、`deleted_only`；补全 `_apply_soft_delete_filter` |
| `src/components/common/MetaForm.vue` | 修改 | 新增判断：有 `options`（enum_values）的字段也渲染为下拉选择器 |
| `architecture.db` | 迁移 | versions 表新增 visibility 列 |

### 9.5 测试策略

| 测试文件 | 测试数 | 覆盖 |
|----------|--------|------|
| `meta/tests/test_version_visibility_unit.py` | 42 | scope 解析（14）、元数据验证（10）、authorization（3）、状态转换规则（10）、其他（5） |
| `meta/tests/test_version_visibility_integration.py` | 18 | 创建（4）、列表过滤（3）、状态转换（4）、domain继承（3）、完整性（4） |
| `meta/tests/test_data_permission_interceptor_extended.py` | 18 | OR scope 解析（7）、权限过滤器（11） |

---

## 10. TBD List

| ID | Item | Status |
|----|------|--------|
| TBD-1 | UI 是否需要提示 draft 版本数量 | 待确认 |
| TBD-2 | draft 版本数量是否需要限制 | 暂不限制 |
| TBD-3 | 前端 E2E 测试 | 待补充 |
