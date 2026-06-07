# Spec: 状态管理增强 - 基于 enum_values 扩展

> **创建日期**: 2026-05-22
> **父文档**: spec-phase3-formula-state-schema.md
> **状态**: 待确认
> **优先级**: P2

---

## 1. Background & Objectives

### 1.1 问题陈述

原计划引入 `StateSchema` 模型来实现状态管理增强，但经过深入分析发现：

1. **重复定义风险**：状态枚举在 `enum_values` 和 `StateSchema.states` 中重复定义
2. **违反单一事实来源**：同一状态的定义分散在多处
3. **模型冗余**：现有 `MetaStateTransition` 已覆盖转换规则，无需重复

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| **单一事实来源** | 状态定义仅存在于 `enum_values` |
| **能力复用** | 复用现有 `MetaStateTransition`、`Computation`、`Formula` |
| **最小变更** | 扩展而非重构，保持向后兼容 |
| **渐进增强** | 新能力可选启用，不影响现有对象 |

### 1.3 现有实现状态

| 能力 | 实现位置 | 状态 | 说明 |
|------|---------|------|------|
| 状态枚举 | `MetaField.enum_values` | ✅ | 支持 value, label, color |
| 状态转换规则 | `MetaStateTransition` | ✅ | 支持 from_states, to_state, condition, side_effects |
| 转换 UI | `StateTransitionUIHints` | ✅ | 支持 label, icon, confirm_message, highlight |
| 转换执行 | `StateTransitionExecutor` | ✅ | 执行状态转换并验证 |
| 状态字段过滤 | `semantics.filter_type: enum` | ✅ | 前端下拉过滤 |
| **状态图标** | - | ❌ | enum_values 缺少 icon 属性 |
| **is_initial/is_final** | - | ❌ | 无法标识初始/终态 |
| **状态分类** | - | ❌ | 无法区分 active/inactive/final/error |
| **状态组** | - | ❌ | 无法定义状态分组 |
| **转换历史** | - | ❌ | 无历史记录表 | → 基于 audit_log 实现

---

## 2. Gap Analysis

### 2.1 现有 enum_values 结构

```yaml
enum_values:
  - value: active          # 状态值
    label: 活跃            # 显示标签
    color: success         # 颜色（Element Plus 颜色名或 HEX）
```

**缺失属性**：
- `icon`: 状态图标（如 edit, check, close）
- `is_initial`: 是否为初始状态（创建时自动设置）
- `is_final`: 是否为终态（不可再转换）
- `category`: 状态分类（active/inactive/final/error）
- `description`: 状态描述（用于 tooltip）

### 2.2 现有 MetaStateTransition 能力

```yaml
rules:
  - id: activate_user
    type: state_transition
    state_field: status
    from_states: [inactive, locked]
    to_state: active
    triggers: [before_update]
    validation_expression: "inactive_days < 90"  # 条件
    validation_message: "账号已超过90天未登录"
    side_effects:                         # 副作用
      - type: set_field
        target: last_activated_at
        value: "NOW()"
    ui_hints:
      label: 激活
      icon: check_circle
      confirm_message: "确定要激活此用户吗？"
      highlight: true
```

**已覆盖能力**：
- ✅ 转换条件验证
- ✅ 转换副作用
- ✅ 转换 UI 提示
- ✅ 触发时机

**缺失能力**：
- ❌ 转换历史记录
- ❌ 批量状态转换
- ❌ 状态转换 API（前端调用）

### 2.3 状态组需求分析

**业务场景**：将多个状态归组显示

| 状态组 | 包含状态 | 用途 |
|--------|---------|------|
| pending | draft, submitted | 待处理列表 |
| resolved | approved, rejected | 已完结列表 |
| active | active | 活跃对象统计 |

**现有实现方式**：通过 Computation 实现

```yaml
- id: is_pending
  type: boolean
  storage: virtual
  computation:
    formula: "status in ['draft', 'submitted']"
```

**结论**：状态组无需新增模型，通过 Formula + Computation 即可实现。

---

## 3. Solution Design

### 3.1 方案概述

| 需求 | 方案 | 变更范围 |
|------|------|---------|
| 状态图标 | 扩展 `enum_values` 支持 `icon` | YAML schema |
| is_initial/is_final | 扩展 `enum_values` 支持 `is_initial`, `is_final` | YAML schema + yaml_loader |
| 状态分类 | 扩展 `enum_values` 支持 `category` | YAML schema |
| 状态组 | 通过 `Computation` 实现 | 无需变更 |
| 转换历史 | 基于 `audit_log` 查询 | API 封装 |
| 转换 API | 新增 `/objects/<id>/state/<transition_id>` 端点 | API |

### 3.2 FR-004-A: 扩展 enum_values 属性

#### 3.2.1 属性定义

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `value` | string | - | 状态值（必填） |
| `label` | string | - | 显示标签（必填） |
| `color` | string | "default" | 颜色（Element Plus 颜色名或 HEX） |
| `icon` | string | null | 图标名称（Element Plus 图标） |
| `is_initial` | boolean | false | 是否为初始状态 |
| `is_final` | boolean | false | 是否为终态 |
| `category` | string | "active" | 状态分类（active/inactive/final/error） |
| `description` | string | null | 状态描述（用于 tooltip） |
| `sort_order` | integer | 0 | 排序序号 |

#### 3.2.2 YAML 示例

```yaml
- id: status
  name: 状态
  type: string
  enum_values:
    - value: draft
      label: 草稿
      color: "#909399"
      icon: edit
      is_initial: true
      category: active
      description: 新创建的变更请求，尚未提交
      sort_order: 10
    - value: submitted
      label: 已提交
      color: "#409EFF"
      icon: upload
      category: active
      description: 已提交审批，等待审批人处理
      sort_order: 20
    - value: approved
      label: 已审批
      color: "#67C23A"
      icon: check
      is_final: true
      category: final
      description: 审批通过，变更请求已完成
      sort_order: 30
    - value: rejected
      label: 已拒绝
      color: "#F56C6C"
      icon: close
      is_final: true
      category: error
      description: 审批拒绝，变更请求已驳回
      sort_order: 40
```

#### 3.2.3 状态分类定义

| category | 说明 | UI 表现 |
|----------|------|---------|
| `active` | 活跃状态，可继续操作 | 正常颜色 |
| `inactive` | 非活跃状态，暂停/停用 | 灰色 |
| `final` | 终态，流程结束 | 绿色/成功色 |
| `error` | 错误状态，异常/拒绝 | 红色/警告色 |

#### 3.2.4 语义约束

1. **is_initial 唯一性**：每个状态字段最多一个 `is_initial: true` 的状态
2. **is_final 与 category**：`is_final: true` 时，`category` 应为 `final` 或 `error`
3. **category 与颜色**：建议按 category 设置默认颜色
   - `active` → primary/blue
   - `inactive` → info/gray
   - `final` → success/green
   - `error` → danger/red

### 3.3 FR-004-B: 状态转换历史（基于 audit_log）

> **设计决策**: 采用基于 `audit_log` 的方案，遵循单一事实来源原则。
> 如后续有性能问题，再考虑新增专用表优化。

#### 3.3.1 数据来源

**现有 audit_log 表已包含状态变更记录**：

| 字段 | 说明 | 用途 |
|------|------|------|
| `object_type` | 对象类型 | 过滤 |
| `object_id` | 对象 ID | 过滤 |
| `field_name` | 变更字段名 | 过滤状态字段 |
| `old_value` | 旧值 | from_state |
| `new_value` | 新值 | to_state |
| `created_at` | 变更时间 | 转换时间 |
| `user_id` / `user_name` | 操作人 | operator |
| `action` | 操作类型 | CREATE/UPDATE |

#### 3.3.2 API 设计

**获取状态转换历史**

```
GET /api/v1/<object_type>/<object_id>/state_history?field=status
```

**实现逻辑**：

```python
def get_state_history(object_type, object_id, field='status'):
    """基于 audit_log 查询状态转换历史"""
    logs = audit_log_query(
        object_type=object_type,
        object_id=object_id,
        field_name=field,
        order_by='created_at'
    )
    
    # 计算停留时长
    result = []
    for i, log in enumerate(logs):
        record = {
            'id': log.id,
            'from_state': log.old_value,
            'to_state': log.new_value,
            'from_state_label': get_state_label(log.old_value),
            'to_state_label': get_state_label(log.new_value),
            'operator_name': log.user_name,
            'created_at': log.created_at,
        }
        
        # 计算在上一状态的停留时长
        if i > 0:
            prev_log = logs[i - 1]
            duration = log.created_at - prev_log.created_at
            record['duration_in_prev_state'] = duration.total_seconds() / 86400  # 天数
        
        result.append(record)
    
    return result
```

**响应示例**：
```json
{
  "success": true,
  "data": [
    {
      "id": 101,
      "from_state": null,
      "to_state": "draft",
      "from_state_label": null,
      "to_state_label": "草稿",
      "operator_name": "张三",
      "created_at": "2026-05-18 09:00:00",
      "duration_in_prev_state": null
    },
    {
      "id": 102,
      "from_state": "draft",
      "to_state": "submitted",
      "from_state_label": "草稿",
      "to_state_label": "已提交",
      "operator_name": "张三",
      "created_at": "2026-05-20 10:30:00",
      "duration_in_prev_state": 2.06  // 在草稿状态停留 2.06 天
    },
    {
      "id": 103,
      "from_state": "submitted",
      "to_state": "approved",
      "from_state_label": "已提交",
      "to_state_label": "已审批",
      "operator_name": "李四",
      "created_at": "2026-05-21 14:20:00",
      "duration_in_prev_state": 1.16  // 在已提交状态停留 1.16 天
    }
  ]
}
```

**获取状态停留统计**

```
GET /api/v1/<object_type>/<object_id>/stage_metrics?field=status
```

**响应示例**：
```json
{
  "success": true,
  "data": {
    "current_state": "approved",
    "current_state_label": "已审批",
    "current_state_entered_at": "2026-05-21 14:20:00",
    "current_state_duration_days": 1.5,
    "total_lifecycle_days": 4.5,
    "stage_breakdown": [
      {"state": "draft", "label": "草稿", "duration_days": 2.06, "percentage": 45.8},
      {"state": "submitted", "label": "已提交", "duration_days": 1.16, "percentage": 25.8},
      {"state": "approved", "label": "已审批", "duration_days": 1.28, "percentage": 28.4}
    ]
  }
}
```

#### 3.3.3 当前阶段停留时长计算

**方案**: 在对象上新增 `status_entered_at` 字段，状态变更时自动维护。

```yaml
- id: status
  name: 状态
  type: string
  enum_values: [...]

- id: status_entered_at
  name: 状态进入时间
  type: datetime
  db_column: status_entered_at
  description: 进入当前状态的时间
  semantics:
    meaning: 用于计算当前阶段停留时长
    audit_field: true
```

**当前阶段停留时长 Formula**：

```yaml
- id: current_stage_duration_days
  name: 当前阶段停留天数
  type: integer
  storage: virtual
  computation:
    formula: "DATEDIFF(status_entered_at, NOW(), 'days')"
```

**自动维护逻辑**（在 StateTransitionExecutor 中）：

```python
def execute_state_transition(rule, context):
    # 执行状态转换
    context.data[rule.state_field] = rule.to_state
    # 自动更新状态进入时间
    context.data[f'{rule.state_field}_entered_at'] = datetime.now()
```

### 3.4 FR-004-C: 状态组实现

#### 3.4.1 方案：通过 Computation 实现

**定义状态组字段**：

```yaml
- id: is_pending
  name: 是否待处理
  type: boolean
  storage: virtual
  semantics:
    meaning: 状态是否属于待处理组
    analytics:
      category: dimension
  computation:
    formula: "status in ['draft', 'submitted']"
  ui:
    widget: tag
    editable: false

- id: is_resolved
  name: 是否已完结
  type: boolean
  storage: virtual
  computation:
    formula: "status in ['approved', 'rejected']"
```

**优点**：
- 复用现有 Formula 能力
- 可用于过滤、统计、显示
- 无需新增模型

#### 3.4.2 状态组统计视图

**按状态组统计**：

```yaml
- id: pending_count
  name: 待处理数量
  type: integer
  storage: virtual
  computation:
    type: count_with_filter
    filter: "is_pending = true"
```

### 3.5 FR-004-D: 前端适配

#### 3.5.1 状态渲染组件

**现有**：`EnumTag` 组件已支持 `color` 和 `label`

**扩展**：支持 `icon` 和 `description`

```vue
<template>
  <el-tag :type="tagType" :effect="effect">
    <el-icon v-if="icon"><component :is="icon" /></el-icon>
    <span>{{ label }}</span>
    <el-tooltip v-if="description" :content="description" placement="top">
      <el-icon><QuestionFilled /></el-icon>
    </el-tooltip>
  </el-tag>
</template>
```

#### 3.5.2 状态转换按钮

**现有**：通过 actions 配置

**扩展**：自动从 `MetaStateTransition` 生成可用转换按钮

```vue
<template v-for="transition in availableTransitions">
  <el-button
    :type="transition.ui_hints.highlight ? 'primary' : 'default'"
    @click="executeTransition(transition.id)"
  >
    <el-icon><component :is="transition.ui_hints.icon" /></el-icon>
    {{ transition.ui_hints.label }}
  </el-button>
</template>
```

#### 3.5.3 状态历史时间线

```vue
<el-timeline>
  <el-timeline-item
    v-for="record in stateHistory"
    :timestamp="record.created_at"
    placement="top"
  >
    <el-card>
      <h4>{{ record.from_state_label }} → {{ record.to_state_label }}</h4>
      <p>操作人: {{ record.operator_name }}</p>
      <p v-if="record.reason">原因: {{ record.reason }}</p>
    </el-card>
  </el-timeline-item>
</el-timeline>
```

---

## 4. Implementation Plan

### 4.1 Milestone 1: enum_values 扩展（1天）

| 步骤 | 内容 | 状态 |
|------|------|------|
| 1.1 | 扩展 `enum_values` YAML schema 支持 icon/is_initial/is_final/category/description | ⏳ |
| 1.2 | 修改 `yaml_loader.py` 解析新属性 | ⏳ |
| 1.3 | 更新存量对象 YAML（user/change_event/audit_log） | ⏳ |
| 1.4 | 前端 EnumTag 组件支持 icon | ⏳ |

### 4.2 Milestone 2: 状态转换历史 API（1天）

> **基于 audit_log 实现，无新增数据表**

| 步骤 | 内容 | 状态 |
|------|------|------|
| 2.1 | 新增 `/objects/<id>/state_history` API（基于 audit_log 查询） | ⏳ |
| 2.2 | 新增 `/objects/<id>/stage_metrics` API（状态停留统计） | ⏳ |
| 2.3 | 修改 `StateTransitionExecutor` 自动维护 `status_entered_at` | ⏳ |
| 2.4 | 新增 `/objects/<id>/state/<transition_id>` API | ⏳ |

### 4.3 Milestone 3: 前端适配（0.5天）

| 步骤 | 内容 | 状态 |
|------|------|------|
| 3.1 | 状态转换按钮组件 | ⏳ |
| 3.2 | 状态历史时间线组件 | ⏳ |
| 3.3 | 状态字段详情页集成 | ⏳ |

### 4.4 Milestone 4: 存量对象采纳（0.5天）

| 对象 | 采纳内容 |
|------|---------|
| user | 补充 status enum_values 新属性 |
| change_event | 补充 status enum_values + 状态转换规则 |
| audit_log | 补充 status enum_values + 状态转换规则 |

---

## 5. Verification

### 5.1 enum_values 扩展验证

```python
# 解析验证
meta_obj = registry.get('change_request')
status_field = meta_obj.get_field('status')
assert len(status_field.enum_values) == 4

draft = next(v for v in status_field.enum_values if v['value'] == 'draft')
assert draft['is_initial'] == True
assert draft['icon'] == 'edit'
assert draft['category'] == 'active'

approved = next(v for v in status_field.enum_values if v['value'] == 'approved')
assert approved['is_final'] == True
assert approved['category'] == 'final'
```

### 5.2 状态转换历史验证（基于 audit_log）

```python
# API 验证
response = client.get('/api/v1/change_requests/1/state_history')
assert response.status_code == 200
assert len(response.json['data']) > 0

record = response.json['data'][0]
assert record['from_state'] is not None or record['to_state'] == 'draft'  # 首条记录
assert record['operator_name'] is not None
assert 'duration_in_prev_state' in record  # 包含停留时长

# 状态停留统计验证
response = client.get('/api/v1/change_requests/1/stage_metrics')
assert response.status_code == 200
assert 'current_state' in response.json['data']
assert 'stage_breakdown' in response.json['data']
```

### 5.3 状态组验证

```python
# Computation 验证
data = {'status': 'draft'}
context = RuleContext(meta_obj, data)
result = ExpressionEvaluator.evaluate("status in ['draft', 'submitted']", context)
assert result == True  # is_pending
```

---

## 6. Comparison: StateSchema vs enum_values Extension

| 维度 | StateSchema 方案 | enum_values 扩展方案 |
|------|-----------------|---------------------|
| **模型数量** | 新增 StateSchema + StateDefinition + StateGroup | 无新增 |
| **定义位置** | 状态定义分散在 enum_values + StateSchema | 状态定义集中在 enum_values |
| **单一事实来源** | ❌ 违反（重复定义） | ✅ 符合 |
| **实现复杂度** | 高（新模型 + 解析 + API） | 低（扩展现有） |
| **向后兼容** | ⚠️ 需迁移 | ✅ 完全兼容 |
| **状态转换规则** | 与 MetaStateTransition 重复 | 复用 MetaStateTransition |
| **状态组** | 新增 StateGroup 模型 | 复用 Computation |
| **转换历史** | ✅ 新增专用表 | ✅ 基于 audit_log（无新增表） |

**结论**：`enum_values` 扩展 + 基于 audit_log 的方案在保持功能完整性的同时，避免了模型冗余、数据冗余和重复定义，推荐采用。

---

## 7. Risks & Mitigations

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| enum_values 属性过多 | YAML 配置复杂 | 提供默认值，可选配置 |
| audit_log 查询性能 | 状态历史查询慢 | 添加索引 `(object_type, object_id, field_name)`；如性能不足再新增专用表 |
| 前端组件兼容性 | 旧版不显示 icon | 渐进增强，icon 可选 |
| 状态组通过 Computation 实现 | 配置分散 | 提供状态组快捷配置语法糖 |

---

## 8. Appendix: 存量对象状态字段分析

### 8.1 已有 enum_values 的状态字段

| 对象 | 字段 | 状态值 | 缺失属性 |
|------|------|--------|---------|
| user | status | active/inactive/locked | icon, is_initial, category |
| version | is_current | 1/0 | 非状态枚举，是布尔标记 |
| audit_log | category | business/security/operation/performance/system | 非状态字段，是分类枚举 |

### 8.2 缺少 enum_values 的状态字段

| 对象 | 字段 | 建议状态值 | 建议添加 |
|------|------|-----------|---------|
| change_event | status | pending/processing/delivered/failed | enum_values + state_transition |
| audit_log | status | written/pending/failed | enum_values + state_transition |

### 8.3 建议新增状态转换规则

**change_event 状态机**：

```yaml
rules:
  - id: process_event
    type: state_transition
    state_field: status
    from_states: [pending]
    to_state: processing
    triggers: [before_update]
    
  - id: deliver_event
    type: state_transition
    state_field: status
    from_states: [processing]
    to_state: delivered
    triggers: [before_update]
    
  - id: fail_event
    type: state_transition
    state_field: status
    from_states: [processing]
    to_state: failed
    triggers: [before_update]
    
  - id: retry_event
    type: state_transition
    state_field: status
    from_states: [failed]
    to_state: pending
    triggers: [before_update]
```

**audit_log 状态机**：

```yaml
rules:
  - id: mark_written
    type: state_transition
    state_field: status
    from_states: [pending]
    to_state: written
    triggers: [before_update]
    
  - id: mark_failed
    type: state_transition
    state_field: status
    from_states: [pending]
    to_state: failed
    triggers: [before_update]
    
  - id: retry_audit
    type: state_transition
    state_field: status
    from_states: [failed]
    to_state: pending
    triggers: [before_update]
```
