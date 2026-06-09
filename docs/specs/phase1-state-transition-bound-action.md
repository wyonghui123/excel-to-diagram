## 目录

1. [1. 背景与目标](#1-背景与目标)
2. [2. 需求类型概览](#2-需求类型概览)
3. [3. 功能需求](#3-功能需求)
4. [4. 非功能需求](#4-非功能需求)
5. [5. 外部接口需求](#5-外部接口需求)
6. [6. 过渡需求](#6-过渡需求)
7. [7. 约束与假设](#7-约束与假设)
8. [8. 优先级与里程碑](#8-优先级与里程碑)
9. [9. 变更/设计提案 (RFC)](#9-变更设计提案-(rfc))
10. [10. TBD 列表](#10-tbd-列表)

---
# Spec: Phase 1 — StateTransition Bound Action + Status Field Readonly

> **版本**: v1.0
> **状态**: 设计中
> **日期**: 2026-05-26
> **阶段**: Phase 1 of Architecture Improvement

---

## 1. 背景与目标

### 1.1 问题陈述

当前状态转换（State Transition）的实现存在架构缺陷：前端 `StateTransitionButtons.vue` 始终通过 `PUT /api/v2/bo/{object_type}/{obj_id}` 直接修改状态字段值，绕过了后端 `StateTransitionExecutor` 的规则校验链路。这导致：

1. **规则绕过风险**: `from_states` 校验、`condition` 条件评估、`{field}_entered_at` 时间戳设置均被跳过
2. **双路径不一致**: `StateTransitionButton.vue` 存在双路径逻辑——若 `transition.action` 存在则走 `POST actions/{action}`，否则走 `PUT`；而 `StateTransitionButtons.vue` 始终走 `PUT`
3. **状态字段可被随意修改**: 任何 `PUT` 请求均可直接修改状态字段，无规则保护
4. **组件职责重叠**: `StateTransitionButton.vue` 与 `StateTransitionButtons.vue` 功能高度重叠，增加维护成本

### 1.2 目标

| # | 目标 | 度量 |
|---|------|------|
| G-1 | 状态转换必须经过 `StateTransitionExecutor` 规则校验 | 100% 覆盖 |
| G-2 | 状态字段通过 `PUT` 直接修改应被拒绝 | FieldPolicy 拦截 |
| G-3 | 前端统一使用 `POST /actions/{rule_id}` 触发状态转换 | 单一路径 |
| G-4 | 合并两个前端组件为一个 | 组件数 -1 |

### 1.3 范围

- **In Scope**: 后端 `execute_action` 增强、FieldPolicy 自动派生 readonly、前端组件统一
- **Out of Scope**: Phase 2（批量状态转换）、Phase 3（状态机可视化编辑器）、自定义 action handler 注册机制

---

## 2. 需求类型概览

| 类型 | 数量 | 编号范围 |
|------|------|----------|
| 功能需求 (FR) | 5 | FR-001 ~ FR-005 |
| 非功能需求 (NFR) | 3 | NFR-001 ~ NFR-003 |
| 外部接口需求 (IF) | 2 | IF-001 ~ IF-002 |
| 过渡需求 (TR) | 2 | TR-001 ~ TR-002 |

---

## 3. 功能需求

### FR-001: 状态字段自动标记 Readonly

**优先级**: P0
**描述**: 当一个字段存在 `type: state_transition` 规则引用时，FieldPolicyEngine 应自动将其标记为 readonly，拒绝通过 `crud_update` 路径直接修改。

**详细规则**:
- 在 `FieldPolicyEngine.is_field_editable()` 判断链中，新增一层判断：若字段被 `state_transition` 规则引用，则 `crud_update` 场景下返回 `False`
- `crud_create` 场景下仍允许设置初始状态值（与 immutable 语义一致）
- 该 readonly 派生应优先级高于 `ui.editable` 显式配置，低于系统字段判断

**判定逻辑伪代码**:
```python
# 在 FieldPolicyEngine.is_field_editable() 中，immutable 判断之后插入
if self._is_state_transition_field(field_id):
    if context and context.action in ('crud_update', 'update'):
        return False
```

**涉及文件**:
- [field_policy_engine.py](file:///d:/filework/excel-to-diagram/meta/services/field_policy_engine.py) — 新增 `_is_state_transition_field()` 方法
- [field_policy_engine.py](file:///d:/filework/excel-to-diagram/meta/services/field_policy_engine.py#L139-L164) — 修改 `is_field_editable()` 判断链

**方法签名**:
```python
def _is_state_transition_field(self, field_id: str) -> bool:
    """
    判断字段是否被 state_transition 规则引用。
    
    遍历当前 meta_object 的 rules，检查是否存在
    type=state_transition 且 state_field=field_id 的规则。
    
    Args:
        field_id: 字段标识
        
    Returns:
        bool: 是否被 state_transition 规则引用
    """
```

### FR-002: execute_action 支持 StateTransition 规则

**优先级**: P0
**描述**: 增强 `BOFramework.execute_action()`，当 `action_id` 匹配到 `state_transition` 规则时，自动构造 `crud_update` 上下文并触发规则链。

**当前行为**:
```python
# bo_framework.py L187-188
def execute_action(self, object_type: str, action: str, params: Dict[str, Any]) -> ActionResult:
    return self.execute(object_type, action, params)
```
当前 `execute_action` 仅透传给 `execute()`，action 值为原始 action_id（如 `activate_user`），不经过 `crud_update` 路径，因此 `StateTransitionExecutor` 不会被触发。

**目标行为**:
```python
def execute_action(self, object_type: str, action: str, params: Dict[str, Any]) -> ActionResult:
    meta_object = registry.get(object_type)
    if meta_object:
        st_rule = self._find_state_transition_rule(meta_object, action)
        if st_rule:
            return self._execute_state_transition_action(object_type, st_rule, params)
    
    handler = self.get_action_handler(object_type, action)
    if handler:
        return handler(params)
    
    return self.execute(object_type, action, params)
```

**`_execute_state_transition_action` 实现要点**:
1. 从 `params['id']` 获取对象 ID
2. 读取当前记录数据（`self.read()`）
3. 校验当前状态是否在 `from_states` 中
4. 评估 `condition`（若存在）
5. 构造 `crud_update` 参数：`{state_field: to_state, id: obj_id}`
6. 调用 `self.update(object_type, obj_id, {state_field: to_state})`
7. `StateTransitionExecutor` 在拦截器链中自动执行（因为 `crud_update` 触发 `before_update`）

**涉及文件**:
- [bo_framework.py](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L187-L188) — 修改 `execute_action()`
- [bo_framework.py](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py) — 新增 `_find_state_transition_rule()` 和 `_execute_state_transition_action()`

**方法签名**:
```python
def _find_state_transition_rule(self, meta_object, action_id: str) -> Optional['MetaStateTransition']:
    """
    在 meta_object.rules 中查找 id 匹配且 type=state_transition 的规则。
    
    Args:
        meta_object: 元数据对象
        action_id: 规则 ID（如 'activate_user'）
        
    Returns:
        MetaStateTransition or None
    """

def _execute_state_transition_action(
    self,
    object_type: str,
    rule: 'MetaStateTransition',
    params: Dict[str, Any]
) -> ActionResult:
    """
    通过 state_transition 规则执行状态转换。
    
    流程：
    1. 读取当前记录
    2. 校验 from_states + condition
    3. 调用 self.update() 触发拦截器链（含 StateTransitionExecutor）
    
    Args:
        object_type: 对象类型
        rule: 状态转换规则
        params: 请求参数（至少包含 id）
        
    Returns:
        ActionResult
    """
```

**校验失败响应格式**:
```json
{
  "success": false,
  "message": "当前状态 'active' 不在允许的源状态 [inactive, locked] 中",
  "error_code": "STATE_TRANSITION_INVALID_FROM_STATE"
}
```

```json
{
  "success": false,
  "message": "条件不满足，无法执行状态转换",
  "error_code": "STATE_TRANSITION_CONDITION_NOT_MET"
}
```

### FR-003: 前端统一使用 POST /actions/{rule_id}

**优先级**: P0
**描述**: `StateTransitionButtons.vue` 的 `executeTransition` 方法应改为调用 `boService.executeAction()`，而非直接 `PUT`。

**当前代码** ([StateTransitionButtons.vue](file:///d:/filework/excel-to-diagram/src/components/bo/StateTransitionButtons.vue#L126-L160)):
```javascript
const executeTransition = async (transition) => {
  // ...
  const resp = await fetch(
    `${API_BASE_V2}/bo/${props.objectType}/${props.objectId}`,
    {
      method: 'PUT',
      headers: getHeaders(authStore),
      body: JSON.stringify({ [transition.state_field]: transition.to_state })
    }
  )
  // ...
}
```

**目标代码**:
```javascript
const executeTransition = async (transition) => {
  loading.value = true
  executingId.value = transition.id
  confirmDialogVisible.value = false

  try {
    const result = await boService.executeAction(
      props.objectType,
      props.objectId,
      transition.id,
      {}
    )

    if (result.success) {
      ElMessage.success(`${transition.label} 成功`)
      emit('success', { transition, result })
      emit('refresh')
      await loadTransitions()
    } else {
      ElMessage.error(result.message || `${transition.label} 失败`)
      emit('error', { transition, error: result.message })
    }
  } catch (error) {
    console.error('State transition error:', error)
    ElMessage.error(`${transition.label} 失败: ${error.message}`)
    emit('error', { transition, error: error.message })
  } finally {
    loading.value = false
    executingId.value = null
    pendingTransition.value = null
  }
}
```

**关键变更**:
- 移除直接 `fetch` 调用，改用 `boService.executeAction()`
- `transition.id` 即为 YAML 中的 `rule.id`（如 `activate_user`），直接作为 `action_id`
- 请求体为空对象 `{}`（状态转换的目标状态由后端规则决定，前端无需传递）

### FR-004: 合并 StateTransitionButton 与 StateTransitionButtons

**优先级**: P1
**描述**: 将 `StateTransitionButton.vue` 和 `StateTransitionButtons.vue` 合并为一个组件 `StateTransitionButtons.vue`，统一接口和行为。

**合并策略**:

| 特性 | StateTransitionButtons (保留) | StateTransitionButton (合并入) |
|------|-------------------------------|-------------------------------|
| 数据加载 | 自行调用 API 获取 | 通过 props.rules 接收 |
| 渲染模式 | 多按钮平铺 | 单按钮/下拉菜单 |
| 执行路径 | PUT (改为 POST action) | 双路径 (统一为 POST action) |
| 确认对话框 | 内置 | 内置 |

**合并后组件 Props**:
```typescript
interface StateTransitionButtonsProps {
  objectType: string              // 必填
  objectId: number | string       // 必填
  stateField?: string             // 可选，默认 'status'
  size?: 'small' | 'default' | 'large'  // 可选，默认 'small'
  disabled?: boolean              // 可选，默认 false
  autoLoad?: boolean              // 可选，默认 true
  rules?: Array                   // 可选，外部传入规则（不调 API）
  currentState?: string           // 可选，配合 rules 使用
  displayMode?: 'buttons' | 'dropdown'  // 可选，默认 'buttons'
}
```

**合并后组件 Emits**:
```typescript
interface StateTransitionButtonsEmits {
  (e: 'success', payload: { transition: any, result: any }): void
  (e: 'error', payload: { transition: any, error: any }): void
  (e: 'refresh'): void
  (e: 'transition', payload: { transition: any, result: any }): void
}
```

**渲染逻辑**:
- `displayMode === 'buttons'`（默认）: 多按钮平铺（当前 `StateTransitionButtons` 行为）
- `displayMode === 'dropdown'`: 单按钮 + 下拉菜单（当前 `StateTransitionButton` 行为）
- 当可用转换仅 1 个时，`dropdown` 模式退化为单按钮

**涉及文件**:
- [StateTransitionButtons.vue](file:///d:/filework/excel-to-diagram/src/components/bo/StateTransitionButtons.vue) — 重写
- [StateTransitionButton.vue](file:///d:/filework/excel-to-diagram/src/components/bo/StateTransitionButton.vue) — 废弃，导出重定向
- [index.js](file:///d:/filework/excel-to-diagram/src/components/bo/index.js) — 更新导出
- [ObjectPage.vue](file:///d:/filework/excel-to-diagram/src/components/common/ObjectPage/ObjectPage.vue#L51-L57) — 无需修改（已使用 `StateTransitionButtons`）

**`StateTransitionButton.vue` 废弃处理**:
```javascript
// StateTransitionButton.vue — 废弃兼容层
export { default } from './StateTransitionButtons.vue'
```

### FR-005: state_transitions API 响应增强

**优先级**: P2
**描述**: `GET /api/v2/bo/{object_type}/{obj_id}/state_transitions` 响应中增加 `action_id` 字段，明确告知前端应调用的 action 端点。

**当前响应** ([bo_api.py](file:///d:/filework/excel-to-diagram/meta/api/bo_api.py#L660-L673)):
```python
transition_info = {
    'id': rule.id,
    'name': rule.name,
    'state_field': rule.state_field,
    'from_states': list(rule.from_states),
    'to_state': rule.to_state,
    'current_state': current_state,
    'available': is_available,
    'label': ui_hints.label if ui_hints else rule.name,
    'icon': ui_hints.icon if ui_hints else '',
    'confirm_message': ui_hints.confirm_message if ui_hints else '',
    'highlight': ui_hints.highlight if ui_hints else False,
    'hidden': ui_hints.hidden if ui_hints else False,
}
```

**目标响应**:
```python
transition_info = {
    'id': rule.id,
    'action_id': rule.id,           # 新增：明确标识 action 端点
    'name': rule.name,
    'state_field': rule.state_field,
    'from_states': list(rule.from_states),
    'to_state': rule.to_state,
    'current_state': current_state,
    'available': is_available,
    'label': ui_hints.label if ui_hints else rule.name,
    'icon': ui_hints.icon if ui_hints else '',
    'confirm_message': ui_hints.confirm_message if ui_hints else '',
    'highlight': ui_hints.highlight if ui_hints else False,
    'hidden': ui_hints.hidden if ui_hints else False,
    'color': ui_hints.color if ui_hints else '',  # 新增：按钮颜色
}
```

**涉及文件**:
- [bo_api.py](file:///d:/filework/excel-to-diagram/meta/api/bo_api.py#L660-L673) — 修改 `get_state_transitions()`

---

## 4. 非功能需求

### NFR-001: 向后兼容

**描述**: 现有使用 `StateTransitionButton` 的代码应无感迁移。

**要求**:
- `StateTransitionButton.vue` 保留为兼容层，重新导出 `StateTransitionButtons.vue`
- `boService.executeAction()` 方法已存在，无需新增
- `POST /actions/{action_id}` 端点已存在，无需新增路由

### NFR-002: 性能

**描述**: 状态转换操作的性能不应显著退化。

**要求**:
- `execute_action` 走 `update()` 路径后的额外开销：1 次 `read()` 调用（用于 from_states 校验）
- `read()` 调用应在 `_execute_state_transition_action` 中执行，而非在 `execute_action` 入口
- `_is_state_transition_field()` 应利用 `meta_object.rules` 缓存，避免重复遍历

### NFR-003: 可观测性

**描述**: 状态转换操作应有完整的日志和审计记录。

**要求**:
- `BOFramework._execute_state_transition_action()` 应记录 INFO 级别日志：`[BOFramework] State transition action: {action_id}, from={current_state}, to={to_state}`
- 校验失败应记录 WARNING 级别日志
- 审计日志由现有 `AuditInterceptor` 自动记录（因为最终走 `crud_update`）

---

## 5. 外部接口需求

### IF-001: POST /api/v2/bo/{object_type}/{obj_id}/actions/{action_id}

**当前行为**: 调用 `bo.execute_action(object_type, action_id, params)`，透传给 `execute()`

**目标行为**:
1. 若 `action_id` 匹配 `state_transition` 规则 → 走 `_execute_state_transition_action()`
2. 若存在自定义 action handler → 走 handler
3. 否则 → 走原有 `execute()` 透传

**请求示例**:
```http
POST /api/v2/bo/user/42/actions/activate_user
Content-Type: application/json

{}
```

**成功响应**:
```json
{
  "success": true,
  "data": {
    "id": 42,
    "username": "zhangsan",
    "status": "active",
    "status_entered_at": "2026-05-26T14:30:00"
  },
  "message": "State transitioned from inactive to active"
}
```

**失败响应 — 非法源状态**:
```json
{
  "success": false,
  "message": "当前状态 'active' 不在允许的源状态 [inactive, locked] 中",
  "error_code": "STATE_TRANSITION_INVALID_FROM_STATE"
}
```

**失败响应 — 条件不满足**:
```json
{
  "success": false,
  "message": "条件不满足，无法执行状态转换",
  "error_code": "STATE_TRANSITION_CONDITION_NOT_MET"
}
```

### IF-002: PUT /api/v2/bo/{object_type}/{obj_id} — 状态字段保护

**当前行为**: 允许直接修改状态字段

**目标行为**: 若状态字段被 `state_transition` 规则引用，`PUT` 请求中包含该字段时应返回 400

**请求示例**:
```http
PUT /api/v2/bo/user/42
Content-Type: application/json

{"status": "active"}
```

**失败响应**:
```json
{
  "success": false,
  "message": "字段 '状态' 不可修改（受状态转换规则保护，请使用 POST /actions/{rule_id}）",
  "error_code": "FIELD_POLICY_VIOLATION"
}
```

---

## 6. 过渡需求

### TR-001: 前端渐进迁移

**描述**: 前端组件合并应支持渐进迁移，避免一次性大改动。

**步骤**:
1. 先修改 `StateTransitionButtons.vue` 的 `executeTransition` 改用 `boService.executeAction()`（FR-003）
2. 验证后端 `execute_action` 增强可用（FR-002）
3. 再合并组件（FR-004）
4. 最后添加 FieldPolicy 保护（FR-001）

**注意**: FR-001 必须最后实施，否则前端 PUT 路径被阻断但 POST 路径尚未就绪，会导致功能中断。

### TR-002: 后端 API 版本兼容

**描述**: `state_transitions` API 响应新增 `action_id` 和 `color` 字段为非破坏性变更，前端应忽略未知字段。

**要求**:
- 旧版前端不使用 `action_id` 字段，不影响现有行为
- 新版前端优先使用 `action_id`，若不存在则 fallback 到 `id`

---

## 7. 约束与假设

### 约束

| # | 约束 | 原因 |
|---|------|------|
| C-1 | 不修改 `StateTransitionExecutor` 核心逻辑 | 已稳定运行，避免回归风险 |
| C-2 | 不修改 `PersistenceInterceptor` | 拦截器链已稳定 |
| C-3 | `execute_action` 的拦截器链行为不变 | 所有 `execute()` 调用仍经过完整拦截器链 |
| C-4 | YAML 规则格式不新增字段 | `rule.id` 已满足 `action_id` 需求 |

### 假设

| # | 假设 | 验证方式 |
|---|------|----------|
| A-1 | `rule.id` 在同一 `object_type` 内唯一 | YAML schema 约束 |
| A-2 | `state_transition` 规则的 `triggers` 默认为 `[before_update]` | [MetaStateTransition.__post_init__](file:///d:/filework/excel-to-diagram/meta/core/models.py#L996-L998) |
| A-3 | `boService.executeAction()` 已实现且可用 | [boService.js#L127-L142](file:///d:/filework/excel-to-diagram/src/services/boService.js#L127-L142) |
| A-4 | `POST /actions/{action_id}` 端点已注册 | [bo_api.py#L258-L267](file:///d:/filework/excel-to-diagram/meta/api/bo_api.py#L258-L267) |
| A-5 | 前端 `transition.id` 与后端 `rule.id` 一致 | API 返回 `id: rule.id` |

---

## 8. 优先级与里程碑

### 实施顺序

```
Step 1: FR-002 (后端 execute_action 增强)
  ↓
Step 2: FR-003 (前端改用 POST action)
  ↓
Step 3: FR-005 (API 响应增强)
  ↓
Step 4: FR-004 (组件合并)
  ↓
Step 5: FR-001 (FieldPolicy readonly 保护)
```

### 里程碑

| 里程碑 | 包含需求 | 预计工时 | 验收标准 |
|--------|----------|----------|----------|
| M1: 后端增强 | FR-002, FR-005 | 2d | `POST /actions/activate_user` 可成功触发状态转换 |
| M2: 前端统一 | FR-003, FR-004 | 1.5d | 前端状态转换全部走 POST action，组件合并完成 |
| M3: 字段保护 | FR-001 | 1d | PUT 修改状态字段返回 400 |

---

## 9. 变更/设计提案 (RFC)

### RFC-001: execute_action 增强 — StateTransition 规则绑定

#### As-Is

```
Frontend: PUT /api/v2/bo/user/42
  Body: { status: "active" }
  ↓
bo_api.py update_bo() → bo.update('user', 42, {status: 'active'})
  ↓
BOFramework.execute('user', 'crud_update', {id: 42, status: 'active'})
  ↓
Interceptor Chain → StateTransitionExecutor (可能触发，但前端绕过了 from_states 校验)
  ↓
PersistenceInterceptor → UPDATE users SET status='active' WHERE id=42
```

**问题**: 前端直接设置目标状态值，`StateTransitionExecutor` 的 `from_states` 校验基于 `context.original_data`，但前端可以设置任意目标状态，规则校验形同虚设。

#### Target State

```
Frontend: POST /api/v2/bo/user/42/actions/activate_user
  Body: {}
  ↓
bo_api.py execute_action() → bo.execute_action('user', 'activate_user', {id: 42})
  ↓
BOFramework.execute_action()
  → _find_state_transition_rule() → 找到 activate_user 规则
  → _execute_state_transition_action()
    → read(42) → 获取 current_state
    → 校验 current_state in from_states
    → 校验 condition
    → self.update('user', 42, {status: 'active'})
      ↓
      BOFramework.execute('user', 'crud_update', {id: 42, status: 'active'})
      ↓
      Interceptor Chain → StateTransitionExecutor (完整执行)
      ↓
      PersistenceInterceptor → UPDATE users SET status='active', status_entered_at=NOW() WHERE id=42
```

#### Detailed Design

##### 9.1.1 BOFramework._find_state_transition_rule()

```python
def _find_state_transition_rule(self, meta_object, action_id: str):
    from meta.core.models import MetaStateTransition
    for rule in meta_object.rules:
        if isinstance(rule, MetaStateTransition) and rule.id == action_id:
            return rule
    return None
```

##### 9.1.2 BOFramework._execute_state_transition_action()

```python
def _execute_state_transition_action(
    self,
    object_type: str,
    rule: 'MetaStateTransition',
    params: Dict[str, Any]
) -> ActionResult:
    from meta.core.exceptions import ValidationFailedError
    
    obj_id = params.get('id')
    if not obj_id:
        return ActionResult(
            success=False,
            message="Missing 'id' in params",
        )
    
    read_result = self.read(object_type, obj_id)
    if not read_result.success:
        return ActionResult(
            success=False,
            message=f"Record not found: {object_type}/{obj_id}",
        )
    
    current_data = read_result.data
    current_state = current_data.get(rule.state_field)
    
    if current_state not in rule.from_states:
        logger.warning(
            f"[BOFramework] State transition '{rule.id}' rejected: "
            f"current state '{current_state}' not in from_states {rule.from_states}"
        )
        return ActionResult(
            success=False,
            message=f"当前状态 '{current_state}' 不在允许的源状态 {rule.from_states} 中",
            data={'error_code': 'STATE_TRANSITION_INVALID_FROM_STATE'},
        )
    
    if rule.condition:
        from meta.core.rule_executor import ExpressionEvaluator
        from meta.core.rule_chain import RuleChainContext
        context = RuleChainContext(
            data=current_data,
            original_data=current_data,
            changed_fields={rule.state_field},
        )
        if not ExpressionEvaluator.evaluate(rule.condition, context):
            logger.warning(
                f"[BOFramework] State transition '{rule.id}' rejected: "
                f"condition not met"
            )
            return ActionResult(
                success=False,
                message="条件不满足，无法执行状态转换",
                data={'error_code': 'STATE_TRANSITION_CONDITION_NOT_MET'},
            )
    
    logger.info(
        f"[BOFramework] State transition action: {rule.id}, "
        f"from={current_state}, to={rule.to_state}"
    )
    
    return self.update(object_type, obj_id, {rule.state_field: rule.to_state})
```

##### 9.1.3 BOFramework.execute_action() 修改

```python
def execute_action(self, object_type: str, action: str, params: Dict[str, Any]) -> ActionResult:
    meta_object = registry.get(object_type)
    if meta_object:
        st_rule = self._find_state_transition_rule(meta_object, action)
        if st_rule:
            return self._execute_state_transition_action(object_type, st_rule, params)
    
    handler = self.get_action_handler(object_type, action)
    if handler:
        return handler(params)
    
    return self.execute(object_type, action, params)
```

#### Alternatives

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| **A: 在 execute_action 中构造 crud_update** (当前方案) | 复用现有拦截器链，StateTransitionExecutor 自动执行 | 需额外 read() 调用 | ✅ 采用 |
| B: 在 execute_action 中直接调用 StateTransitionExecutor | 无需 read() 调用 | 绕过拦截器链，审计/约束等可能缺失 | ❌ 不采用 |
| C: 新增 state_transition_action 拦截器 | 关注点分离 | 增加拦截器复杂度，且拦截器链对非 crud action 行为有限 | ❌ 不采用 |

#### Implementation Plan

| 步骤 | 文件 | 变更 | 测试 |
|------|------|------|------|
| 1 | `meta/core/bo_framework.py` | 新增 `_find_state_transition_rule()` | 单元测试 |
| 2 | `meta/core/bo_framework.py` | 新增 `_execute_state_transition_action()` | 单元测试 |
| 3 | `meta/core/bo_framework.py` | 修改 `execute_action()` | 集成测试 |
| 4 | `meta/api/bo_api.py` | 修改 `get_state_transitions()` 响应 | API 测试 |
| 5 | `meta/tests/test_bo_api.py` | 新增测试用例 | — |

---

### RFC-002: FieldPolicy 自动派生 Readonly

#### As-Is

`FieldPolicyEngine.is_field_editable()` 判断链：
1. 系统字段 → 不可编辑
2. immutable 语义 → 创建可编辑，更新不可编辑
3. `ui.editable` 显式配置 → 使用配置值
4. 动态策略规则 → 按规则评估
5. mutability 逻辑 → 根据对象类型评估
6. 默认值 → 可编辑

状态字段（如 `status`）无任何保护，`ui.editable` 未显式设置时默认可编辑。

#### Target State

判断链增加第 2.5 步：
1. 系统字段 → 不可编辑
2. immutable 语义 → 创建可编辑，更新不可编辑
2.5. **state_transition 规则引用** → 创建可编辑，更新不可编辑
3. `ui.editable` 显式配置 → 使用配置值（但被 2.5 覆盖）
4. 动态策略规则 → 按规则评估
5. mutability 逻辑 → 根据对象类型评估
6. 默认值 → 可编辑

#### Detailed Design

##### 9.2.1 FieldPolicyEngine._is_state_transition_field()

```python
def _is_state_transition_field(self, field_id: str) -> bool:
    if not self.meta_object:
        return False
    from meta.core.models import MetaStateTransition
    for rule in self.meta_object.rules:
        if isinstance(rule, MetaStateTransition) and rule.state_field == field_id:
            return True
    return False
```

##### 9.2.2 FieldPolicyEngine.is_field_editable() 修改

在 immutable 判断之后、`ui.editable` 判断之前插入：

```python
def is_field_editable(self, field_id: str, context: Optional[PolicyContext] = None) -> bool:
    if self._is_system_field(field_id):
        return False
    
    field_def = self._get_field(field_id)
    if self._is_immutable(field_def):
        if context and context.action == 'create':
            return True
        return False
    
    # 新增：state_transition 规则保护
    if self._is_state_transition_field(field_id):
        if context and context.action in ('create',):
            return True
        return False
    
    # ... 后续逻辑不变
```

#### Alternatives

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| **A: FieldPolicyEngine 自动派生** (当前方案) | 零配置，规则驱动 | 需修改 FieldPolicyEngine | ✅ 采用 |
| B: YAML 中显式设置 `ui.editable: false` | 无代码修改 | 需手动维护，易遗漏 | ❌ 不采用 |
| C: 新增 FieldPolicy 规则 | 灵活 | 过度设计 | ❌ 不采用 |

#### Implementation Plan

| 步骤 | 文件 | 变更 | 测试 |
|------|------|------|------|
| 1 | `meta/services/field_policy_engine.py` | 新增 `_is_state_transition_field()` | 单元测试 |
| 2 | `meta/services/field_policy_engine.py` | 修改 `is_field_editable()` | 单元测试 |
| 3 | `meta/tests/test_derivation.py` | 新增测试用例 | — |

---

### RFC-003: 前端组件合并

#### As-Is

两个组件并存：

| 组件 | 位置 | 数据来源 | 执行路径 | 渲染 |
|------|------|----------|----------|------|
| `StateTransitionButtons.vue` | ObjectPage 使用 | API 自动加载 | PUT | 多按钮平铺 |
| `StateTransitionButton.vue` | 导出但未在 ObjectPage 使用 | props.rules | 双路径 | 单按钮/下拉 |

#### Target State

合并为单一 `StateTransitionButtons.vue`，支持两种数据来源和两种渲染模式。

#### Detailed Design

##### 9.3.1 合并后组件完整结构

```vue
<template>
  <div v-if="availableTransitions.length > 0" class="state-transition-buttons">
    <!-- buttons 模式 -->
    <template v-if="displayMode === 'buttons'">
      <template v-for="transition in availableTransitions" :key="transition.id">
        <el-button
          :type="getButtonType(transition)"
          :size="size"
          :disabled="disabled || loading"
          :loading="loading && executingId === transition.id"
          @click="handleTransition(transition)"
        >
          <el-icon v-if="transition.icon">
            <component :is="transition.icon" />
          </el-icon>
          {{ transition.label }}
        </el-button>
      </template>
    </template>

    <!-- dropdown 模式 -->
    <template v-else-if="displayMode === 'dropdown'">
      <template v-if="availableTransitions.length === 1">
        <el-button
          :type="getButtonType(availableTransitions[0])"
          :size="size"
          :disabled="disabled || loading"
          :loading="loading"
          @click="handleTransition(availableTransitions[0])"
        >
          {{ availableTransitions[0].label }}
        </el-button>
      </template>
      <template v-else>
        <el-dropdown
          trigger="click"
          :disabled="disabled || loading"
          @command="handleTransition"
        >
          <el-button
            :type="buttonType"
            :size="size"
            :disabled="disabled || loading"
            :loading="loading"
          >
            {{ buttonText }}
            <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                v-for="transition in availableTransitions"
                :key="transition.id"
                :command="transition"
              >
                <el-icon v-if="transition.icon">
                  <component :is="transition.icon" />
                </el-icon>
                {{ transition.label }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </template>
    </template>

    <!-- 确认对话框 -->
    <el-dialog
      v-model="confirmDialogVisible"
      :title="confirmTitle"
      width="400px"
      :close-on-click-modal="false"
      append-to-body
    >
      <p>{{ confirmMessage }}</p>
      <template #footer>
        <el-button @click="confirmDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="loading" @click="confirmTransition">
          确定
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import boService from '@/services/boService'
import { API_BASE_V2, getHeaders } from '@/utils/api'
import { useAuthStore } from '@/stores/authStore'

const authStore = useAuthStore()

const props = defineProps({
  objectType: { type: String, required: true },
  objectId: { type: [Number, String], required: true },
  stateField: { type: String, default: 'status' },
  size: { type: String, default: 'small' },
  disabled: { type: Boolean, default: false },
  autoLoad: { type: Boolean, default: true },
  rules: { type: Array, default: () => [] },
  currentState: { type: String, default: '' },
  displayMode: { type: String, default: 'buttons' },
  buttonType: { type: String, default: 'primary' },
  buttonText: { type: String, default: '状态操作' },
})

const emit = defineEmits(['success', 'error', 'refresh', 'transition'])

const loading = ref(false)
const executingId = ref(null)
const confirmDialogVisible = ref(false)
const pendingTransition = ref(null)
const apiTransitions = ref([])

const availableTransitions = computed(() => {
  if (props.rules && props.rules.length > 0) {
    return props.rules
      .filter(rule => rule.type === 'state_transition')
      .filter(rule => {
        if (rule.from_states?.length > 0) {
          return rule.from_states.includes(props.currentState)
        }
        return true
      })
      .map(rule => ({
        id: rule.id || rule.action_id,
        action_id: rule.action_id || rule.id,
        name: rule.name || rule.id,
        label: rule.label || rule.name || rule.id,
        toState: rule.to_state,
        icon: rule.icon,
        confirm_message: rule.confirm_message || '确定要执行此操作吗？',
        highlight: rule.highlight || false,
        color: rule.color || '',
      }))
  }
  return apiTransitions.value.filter(t => t.available && !t.hidden)
})

const confirmTitle = computed(() => pendingTransition.value?.label || '确认操作')
const confirmMessage = computed(() => pendingTransition.value?.confirm_message || '确定要执行此操作吗？')

const getButtonType = (transition) => {
  if (transition.highlight) return 'primary'
  if (transition.color === 'success') return 'success'
  if (transition.color === 'danger') return 'danger'
  if (transition.color === 'warning') return 'warning'
  return 'default'
}

const loadTransitions = async () => {
  if (!props.objectType || !props.objectId || props.objectId === 'new') return
  if (props.rules && props.rules.length > 0) return

  loading.value = true
  try {
    const resp = await fetch(
      `${API_BASE_V2}/bo/${props.objectType}/${props.objectId}/state_transitions`,
      { method: 'GET', headers: getHeaders(authStore) }
    )
    const data = await resp.json()
    if (data.success) {
      apiTransitions.value = data.data || []
    }
  } catch (error) {
    console.error('Failed to load state transitions:', error)
  } finally {
    loading.value = false
  }
}

const handleTransition = (transition) => {
  if (transition.confirm_message) {
    pendingTransition.value = transition
    confirmDialogVisible.value = true
  } else {
    executeTransition(transition)
  }
}

const confirmTransition = () => {
  if (pendingTransition.value) {
    executeTransition(pendingTransition.value)
  }
}

const executeTransition = async (transition) => {
  loading.value = true
  executingId.value = transition.id
  confirmDialogVisible.value = false

  try {
    const actionId = transition.action_id || transition.id
    const result = await boService.executeAction(
      props.objectType,
      props.objectId,
      actionId,
      {}
    )

    if (result.success) {
      ElMessage.success(`${transition.label} 成功`)
      emit('success', { transition, result })
      emit('transition', { transition, result })
      emit('refresh')
      if (props.autoLoad && !props.rules?.length) {
        await loadTransitions()
      }
    } else {
      ElMessage.error(result.message || `${transition.label} 失败`)
      emit('error', { transition, error: result.message })
    }
  } catch (error) {
    console.error('State transition error:', error)
    ElMessage.error(`${transition.label} 失败: ${error.message}`)
    emit('error', { transition, error: error.message })
  } finally {
    loading.value = false
    executingId.value = null
    pendingTransition.value = null
  }
}

onMounted(() => {
  if (props.autoLoad) loadTransitions()
})

watch(() => props.objectId, () => {
  if (props.autoLoad) loadTransitions()
})

defineExpose({ loadTransitions, availableTransitions, executeTransition })
</script>

<style scoped>
.state-transition-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
</style>
```

##### 9.3.2 StateTransitionButton.vue 兼容层

```vue
<script setup>
export { default } from './StateTransitionButtons.vue'
</script>
```

##### 9.3.3 index.js 更新

```javascript
export { default as AssociationSelector } from './AssociationSelector.vue'
export { default as StateTransitionButtons } from './StateTransitionButtons.vue'
export { default as StateTransitionButton } from './StateTransitionButtons.vue'
export { default as ActionExecutor } from './ActionExecutor.vue'
```

#### Implementation Plan

| 步骤 | 文件 | 变更 |
|------|------|------|
| 1 | `src/components/bo/StateTransitionButtons.vue` | 重写为合并组件 |
| 2 | `src/components/bo/StateTransitionButton.vue` | 替换为兼容层 |
| 3 | `src/components/bo/index.js` | 更新导出 |
| 4 | `src/components/bo/__tests__/StateTransitionButton.spec.js` | 更新测试 |

---

## 10. TBD 列表

| # | 待决项 | 影响 | 负责人 | 截止日期 |
|---|--------|------|--------|----------|
| TBD-1 | `_is_state_transition_field()` 是否需要缓存？若 meta_object.rules 数量很大（>100），每次调用遍历可能有性能影响 | NFR-002 | — | M3 前 |
| TBD-2 | `execute_action` 中 `condition` 评估使用 `ExpressionEvaluator` 还是 `RuleChainContext`？当前设计使用 `RuleChainContext`，但 `StateTransitionExecutor` 使用 `RuleContext`，两者表达式求值行为是否一致？ | FR-002 | — | M1 前 |
| TBD-3 | 合并组件后 `StateTransitionButton.spec.js` 测试用例如何迁移？是否需要新增 `StateTransitionButtons.spec.js`？ | FR-004 | — | M2 前 |
| TBD-4 | `error_code` 字段放在 `ActionResult.data` 中还是 `ActionResult.errors` 中？当前设计放在 `data` 中，但 `FieldPolicyViolationError` 放在 `errors` 中 | IF-001, IF-002 | — | M1 前 |
| TBD-5 | 是否需要在 `state_transitions` API 响应中返回 `allowed_roles` 信息，供前端做按钮权限控制？ | FR-005 | — | Phase 2 |
