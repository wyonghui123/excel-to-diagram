# Spec: Phase 24 - Product Version Draft 可见性控制

> **Spec ID**: phase-24-version-visibility-draft
> **版本**: v1.0.0
> **创建日期**: 2026-05-23
> **状态**: ✅ 已实现
> **优先级**: P1
> **关联文档**:
> - [主 Spec](../unified-metadata-api-architecture/spec.md)
> - [状态管理增强](../spec-state-management-enhancement.md)

---

## 目录

1. [背景与目标](#1-背景与目标)
2. [设计原则](#2-设计原则)
3. [功能需求](#3-功能需求)
4. [关键设计](#4-关键设计)
5. [代码变更](#5-代码变更)
6. [测试覆盖](#6-测试覆盖)
7. [数据库迁移](#7-数据库迁移)

---

## 1. 背景与目标

### 1.1 问题陈述

当前所有 Product Version 对有权限的用户均可见，无法区分正式发布版本和个人 work-in-progress 版本。需要引入 draft 状态来支持个人层面的工作空间隔离。

### 1.2 目标

| 目标 | 描述 |
|------|------|
| 个人工作空间隔离 | draft 版本仅 owner 可见 |
| 正式发布流程 | draft 可发布为 public，所有人可见 |
| 子对象继承 | 子对象强制继承父版本 visibility |
| 元数据驱动 | 所有配置通过 YAML 定义，不硬编码 |

---

## 2. 设计原则

| 原则 | 说明 |
|------|------|
| **元数据驱动** | visibility 字段、authorization.scope、状态转换规则均通过 YAML 定义 |
| **状态管理复用** | 接入现有 `MetaStateTransition` 状态机框架 |
| **最小变更** | 扩展现有 authorization.scope 表达式引擎支持 OR 条件 |
| **Code 共享序列** | draft 和 public 共享 KeyTemplate 序列号 |

---

## 3. 功能需求

### 3.1 功能需求清单

| ID | 需求 | 优先级 | 状态 |
|----|------|--------|------|
| FR-001 | Visibility 字段 | Must | ✅ |
| FR-002 | Draft 权限过滤 | Must | ✅ |
| FR-003 | 子对象强制继承 | Must | ✅ |
| FR-004 | 单向状态转换 | Must | ✅ |
| FR-005 | Code 共享序列 | Must | ✅ |
| FR-006 | Owner 转移与导入导出 | Should | ✅ |
| FR-007 | 状态录入时间戳 | Medium | ✅ |

### 3.2 关键决策记录

| 决策 | 选项 | 结论 | 理由 |
|------|------|------|------|
| 状态值 | public/private vs public/draft | **public/draft** | draft 通用性更高 |
| Code 策略 | 共享序列 vs 独立序列 | **共享序列** | 简单，接受编号不连续 |
| 可变性 | immutable vs 状态机 | **状态机** | 接入元模型驱动状态管理 |
| 子对象继承 | 独立设置 vs 强制继承 | **强制继承** | 数据一致性 |

---

## 4. 关键设计

### 4.1 YAML 配置 (version.yaml)

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

  - id: visibility_entered_at
    type: datetime
    db_column: visibility_entered_at

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
      confirm_message: "确定要发布此版本吗？发布后所有人可见，且不可撤销。"
```

### 4.2 Scope 表达式解析流程

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

### 4.3 状态机模型

```
        create             publish (before_update, StateTransitionExecutor)
draft ─────────→ draft ────────────────────────────────────────────→ public
  ↑                                                                      │
  └──────────────── 不可逆（from_states 只有 [draft]）───────────────────┘
```

### 4.4 子对象继承

```
查询 domain 列表
  → domain 无独立 authorization.scope
  → 查找父 version 的 authorization
  → 继承 inherit_scope_to_children: true
  → 对 domain 列表应用 "visibility = 'public' OR owner_id = $user.id"
```

---

## 5. 代码变更

### 5.1 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `meta/schemas/version.yaml` | 修改 | 添加 visibility、visibility_entered_at 字段；扩展 authorization.scope；新增 publish_version 规则 |
| `meta/api/manage_api.py` | 修改 | `_apply_scope_filter` 支持 OR 表达式；`get_record` 增加 scope 过滤 |
| `meta/core/interceptors/data_permission_interceptor.py` | 修改 | `_apply_scope_filter` 支持 OR 表达式；新增 `_parse_scope_expression` |
| `meta/services/query_service.py` | 修改 | `SearchRequest` 添加 `include_deleted`、`deleted_only` 参数 |
| `architecture.db` | 迁移 | versions 表新增 visibility、visibility_entered_at 列 |

### 5.2 核心代码变更

#### 5.2.1 Scope 表达式解析 (data_permission_interceptor.py)

```python
def _parse_scope_expression(self, expression: str, user_id: int) -> List[Dict]:
    """解析 OR 表达式的 scope 条件"""
    or_conditions = []
    for part in expression.split(' OR '):
        part = part.strip()
        if ' = ' in part:
            field, value = part.split(' = ', 1)
            value = value.strip("'\"")
            if value == '$user.id':
                value = str(user_id)
            or_conditions.append({
                'field': field.strip(),
                'operator': 'eq',
                'value': value
            })
    return or_conditions
```

#### 5.2.2 状态转换执行 (StateTransitionExecutor)

```python
class StateTransitionExecutor:
    def execute_publish_version(self, record, context):
        visibility_entered_at = datetime.now().isoformat()
        return {
            'visibility': 'public',
            'visibility_entered_at': visibility_entered_at
        }
```

---

## 6. 测试覆盖

| 测试文件 | 测试数 | 覆盖范围 |
|----------|--------|----------|
| `test_version_visibility_unit.py` | 42 | scope 解析、元数据验证、authorization、状态转换 |
| `test_version_visibility_integration.py` | 18 | 创建、列表过滤、状态转换、domain 继承 |
| `test_data_permission_interceptor_extended.py` | 18 | OR scope 解析、权限过滤器 |

**测试统计**: 78 个用例，覆盖核心功能

---

## 7. 数据库迁移

### 7.1 迁移 SQL

```sql
ALTER TABLE versions ADD COLUMN visibility VARCHAR(200) NOT NULL DEFAULT 'draft';
ALTER TABLE versions ADD COLUMN visibility_entered_at DATETIME;
```

### 7.2 兼容性

- 现有版本 visibility = 'public'（数据库默认值）
- 功能不受影响

---

## 文档历史

| 版本 | 日期 | 作者 | 变更内容 |
|------|------|------|---------|
| v1.0.0 | 2026-05-23 | AI Assistant | 初始版本，整合架构设计 |
