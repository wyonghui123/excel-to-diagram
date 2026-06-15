# WORKFLOW_STATE_MACHINE.md

> **Workflow 状态机规则文档**
> 版本: v1.0
> 创建: 2026-06-14
> BMRD DEFER ID: WF-STATE-MACHINE

## 1. 概述

Workflow 状态机用于控制业务实体的状态转换。
基于 `MetaStateTransition` 规则 (meta/core/models.py:244)。

## 2. 数据模型

### 2.1 MetaStateTransition
```python
@dataclass
class MetaStateTransition(MetaRule):
    rule_type: RuleType = field(default=RuleType.STATE_TRANSITION)
    state_field: str = "status"        # 状态字段名
    from_states: List[str] = []        # 允许的源状态 (空=任意)
    to_state: str = ""                 # 目标状态
    allowed_roles: List[str] = []      # 允许执行的角色 (空=不限制)
    auto_actions: List[str] = []       # 状态转换后自动执行的动作
    validation_expression: str = ""    # 前置验证表达式
    validation_message: str = ""       # 验证失败提示
    side_effects: List[StateTransitionSideEffect] = []  # 副作用
    ui_hints: Optional[StateTransitionUIHints] = None    # UI 提示
```

### 2.2 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `state_field` | 是 | 状态字段名 (例: "status", "approval_status") |
| `from_states` | 否 | 源状态列表, 空表示允许任意状态 |
| `to_state` | 是 | 目标状态 |
| `allowed_roles` | 否 | 允许执行此转换的角色, 空表示不限制 |
| `auto_actions` | 否 | 转换后自动执行的动作列表 |
| `validation_expression` | 否 | 前置验证表达式 (例: "amount < 10000") |
| `validation_message` | 否 | 验证失败时显示给用户 |
| `side_effects` | 否 | 副作用列表 (发通知/调外部 API) |
| `ui_hints` | 否 | UI 显示配置 (按钮标签/隐藏) |

## 3. 触发时机 (Triggers)

默认触发时机: `BEFORE_UPDATE` (在保存前)

可在 YAML 中覆盖:
```yaml
- id: approve_order
  rule_type: state_transition
  triggers: [BEFORE_UPDATE]  # 默认
  state_field: status
  from_states: [pending]
  to_state: approved
```

## 4. 执行语义 (Gating Rules)

### 4.1 4 种情况 (`rule_executor.py:701`)

| 情况 | 条件 | 行为 |
|------|------|------|
| **Case 0** | `state_field` 不在 `data` dict | **跳过** (普通 update 不触发) |
| **Case 1** | `current_state == to_state` | **跳过** (无变化) |
| **Case 2** | `current_state in from_states` | **执行** (状态真的需要变化) |
| **Case 3** | 其他 | **跳过** (源状态不匹配) |

### 4.2 Bug 历史 (2026-06-09 修复)
- **原 Bug**: 3 个 state_transition rule 全部满足 → 串行 fire → 反复覆盖 status_entered_at
- **修复**: 引入 `data dict has state_field` 显式判断
- **正确语义**: 普通 PUT update (不改 status) → 0 规则 fire

## 5. 调用方式

### 5.1 显式 Action 调用
```
POST /api/v2/bo/{object_type}/actions/{rule_id}
```
- 触发指定 rule_id 的 state_transition
- handler 会把 `state_field` 显式设到 data dict
- 命中 Case 2, 执行转换

### 5.2 普通 PUT 更新
```
PUT /api/v2/bo/{object_type}/{id}
{
  "display_name": "new value"  // 没改 status
}
```
- `data` dict 中**没有** state_field
- 命中 Case 0, 全部 state_transition rule **跳过**

### 5.3 状态变更
```
PUT /api/v2/bo/{object_type}/{id}
{
  "status": "approved"  // 显式改 status
}
```
- 命中 Case 2, 找到匹配 rule, 执行转换

## 6. 工作流实例与任务

### 6.1 端点
| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v2/bo/workflow` | GET | 列出工作流定义 |
| `/api/v2/bo/workflow_instance` | GET | 列出运行中的工作流实例 |
| `/api/v2/bo/workflow_task` | GET | 列出工作流任务 (待办/已办) |
| `/api/v2/bo/workflow_instance` | POST | 启动工作流实例 |
| `/api/v2/bo/workflow_task/{id}/complete` | POST | 完成任务 |

### 6.2 工作流定义
- 包含节点 (start/end/user_task/service_task/gateway)
- 包含流转 (sequence_flow)
- 包含监听器 (start_listener/end_listener)

## 7. UI 提示配置

```python
@dataclass
class StateTransitionUIHints:
    hidden: bool = False   # UI 是否隐藏此转换
    label: str = ""        # 按钮显示标签
    color: str = ""        # 按钮颜色
    icon: str = ""         # 按钮图标
```

## 8. 副作用配置

```python
@dataclass
class StateTransitionSideEffect:
    type: str = ""         # 类型: "send_email" / "call_api" / "publish_event"
    target: str = ""       # 目标: 邮件地址 / API URL / event name
    payload: str = ""      # 载荷模板 (支持表达式)
```

### 8.1 支持的副作用类型
| 类型 | 说明 |
|------|------|
| `send_email` | 发送邮件 |
| `call_api` | 调用外部 API |
| `publish_event` | 发布事件 (内部 pub/sub) |
| `create_task` | 创建待办任务 |
| `update_field` | 更新其他字段 |
| `set_cache` | 设置缓存值 |

## 9. 示例规则

### 示例 1: 订单审批状态机
```yaml
rules:
  - id: submit_order
    rule_type: state_transition
    state_field: status
    from_states: [draft]
    to_state: pending
    allowed_roles: [sales, manager]
    auto_actions: [notify_manager]
    validation_expression: amount > 0
    validation_message: 订单金额必须大于 0
    side_effects:
      - type: send_email
        target: ${manager.email}
        payload: "新订单待审批: ${order.code}"
    ui_hints:
      label: 提交审批
      color: primary
      icon: upload

  - id: approve_order
    rule_type: state_transition
    state_field: status
    from_states: [pending]
    to_state: approved
    allowed_roles: [manager]
    auto_actions: [notify_sales, update_inventory]
    ui_hints:
      label: 批准
      color: success
      icon: check

  - id: reject_order
    rule_type: state_transition
    state_field: status
    from_states: [pending]
    to_state: rejected
    allowed_roles: [manager]
    validation_message: 请填写拒绝原因
    ui_hints:
      label: 拒绝
      color: danger
      icon: close
```

### 示例 2: 用户账户状态
```yaml
rules:
  - id: activate_user
    rule_type: state_transition
    state_field: account_status
    from_states: [inactive, suspended]
    to_state: active
    allowed_roles: [admin]
    side_effects:
      - type: publish_event
        target: user.activated
        payload: "${user.code}"
```

## 10. BMRD 规则

| 规则 ID | 状态 | 说明 |
|---------|------|------|
| WF-1 | ACTIVE | workflow 列表端点 |
| WF-2 | ACTIVE | workflow_instance 列表 |
| WF-3 | ACTIVE | workflow_task 列表 |
| WF-STATE-MACHINE | 🟡 DEFER (文档化完成) | 等后端状态机上线后改 ACTIVE |

## 11. 解锁条件

WF-STATE-MACHINE DEFER → ACTIVE:
- [x] 文档化完成 ✅
- [x] 关键代码确认 ✅ (`MetaStateTransition` + `StateTransitionExecutor`)
- [x] 端点确认 ✅ (workflow/instance/task 端点)
- [x] Bug 修复历史记录 ✅ (2026-06-09 修复)
- [x] BMRD 规则引用 ✅
- [x] 示例规则 ✅
- [ ] 解锁: 改 `_masterdata_schema_workflow_rules.yaml` 中 `WF-STATE-MACHINE` 为 ACTIVE

## 12. 测试覆盖

- `meta/tests/test_state_transition_executor.py` (待建)
- `meta/tests/test_workflow_api.py` (待建)
- `meta/tests/test_workflow_instance.py` (待建)
- `meta/tests/test_workflow_task.py` (待建)

## 13. 已知限制

| 限制 | 原因 | 解决方案 |
|------|------|----------|
| 状态回退未文档化 | 业务侧判断 | P2: 添加回退规则 |
| 跨实体状态机未实现 | 复杂度高 | P3: 长期规划 |
| 状态机可视化 | UI 工作 | P2: 配合前端实现 |

## 14. 参考

- 核心模型: `meta/core/models.py:244` (MetaStateTransition)
- 执行器: `meta/core/rule_executor.py:662` (StateTransitionExecutor)
- 关键修复: `meta/core/rule_executor.py:684` (2026-06-09 Bug 修复注释)
- BMRD 规则: `.trae/specs/_business_rules/_masterdata_schema_workflow_rules.yaml`
