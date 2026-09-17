# 22 · 对象状态转换动作的权限矩阵接入

> 文档编号: 22 | 状态: 草案 v1.2 | 更新: 2026-09-13
> 修订: v1.1 (§6.5 5 状态机扩展 + 8 transitions) → v1.2 (§6.7 撤销 archive/restore → 6 transitions)
> 主题: 把对象级业务动作（state_transition，如启用/停用/锁定/重设密码）作为通用 action
>       进入标准动作池 `_standard_actions.yaml`；并通过 `action_ref` 字段在对象 yaml 的
>       rules 区段引用，使矩阵「更多动作」列、详情页 StateTransitionButtons 共用同一套
>       action 注册与权限模型，与已有的 instance_scope / action_type 体系无缝对齐。
> 前置: [21_action_object_instance_scope_clarification](./21_action_object_instance_scope_clarification.md)
>       （action_type 分组、instance_scope 副标签）
> 关联: [15_permission_config_unification](./15_permission_config_unification.md)
>       / [16_role_to_permission_set_and_user_group_to_org](./16_role_to_permission_set_and_user_group_to_org.md)
>       / [_standard_actions.yaml](../../meta/schemas/_standard_actions.yaml)

---

## 1. 背景与动机

### 1.1 现状（已就绪部分）

| 维度 | 已落地 | 来源 |
|---|---|---|
| 标准动作池 | 16 个通用 action（CRUD / 批量 / 业务）带 `action_type` + `instance_scope` | [`_standard_actions.yaml`](../../meta/schemas/_standard_actions.yaml) |
| 矩阵「更多动作」列 | 支持率 < 50% 的差异化 action 走 popover 勾选，与主列同权 | [ResourceActionMatrix.vue §3.3.1](21_action_object_instance_scope_clarification.md#3-3-fr-001-列头语义标识) |
| 状态转换 endpoint | `GET /bo/{type}/{id}/state_transitions` 返回 transition 列表 + ui_hints | [bo_api.py:1987](../../meta/api/bo_api.py#L1987) |
| 详情页按钮 | `StateTransitionButtons` 组件自动按 `from_states` 渲染 | [StateTransitionButtons.vue](../../src/components/bo/StateTransitionButtons.vue) |
| 对象 yaml rules | 已支持 `state_field / from_states / to_state / ui_hints / allowed_roles` | [user.yaml](../../meta/schemas/user.yaml#L540-L589) / [product.yaml](../../meta/schemas/product.yaml#L530-L559) |

### 1.2 现状痛点

1. **动作权限未入矩阵**：`rules:` 段定义的 state_transition 在详情页可点，**但 `permission_set_permissions` 表无对应记录** —— 任何持有该权限集的人都能触发任何 state_transition，没有 RBAC 校验。
2. **label/icon 重复声明**：每个对象的 yaml 都自创 `enable_user` / `enable_product` / `enable_permission_set` 各自的 `ui_hints`，无法跨对象复用「启用」动作的统一样式与权限码。
3. **action_ref 字段缺失**：`MetaStateTransition` 数据类（[models.py:244](../../meta/core/models.py#L244)）没有 `action_ref` 字段 —— state_transition 与通用 action 池无映射关系。
4. **前端不感知 state_transition 是 action**：矩阵中看不到「锁定 user」「重设密码 user」等可勾选行；管理员只能依赖 `allowed_roles` 字段硬编码（且当前未在 UI 暴露）。
5. **重设密码 / 锁定 / 合并 等业务动作缺位**：`user.yaml` 只有 3 条 state_transition（activate / lock / deactivate），缺 `business_reset_password` 等头部产品标配动作。

### 1.3 横向对比（头部产品对对象级业务动作的处理）

| 产品 | 业务动作（如 Reset Passwords）落点 |
|---|---|
| **Salesforce** | System Permissions（独立 tab，不入 Object Permissions 矩阵）；同一 Permission Set 可同时持有两者 |
| **Microsoft Entra ID** | action 字符串 `microsoft.directory/users/resetPassword`，按 resource+action 扁平列；扁平 action 列表 |
| **AWS IAM** | action 字符串 `iam:ResetPassword` / `iam:DeactivateUser`，独立 action 维度 |
| **SAP Fiori** | PFCG Role 内含 Authorization Object（S_TCODE 等），与业务 Catalog 平级独立 |

→ **设计共识**：**业务动作（启用/重设密码）必须独立于 CRUD 矩阵**，但与 CRUD **共用同一份 action 注册表 + 同一套权限模型**。

### 1.4 与已有 instance_scope 体系的关系

我们项目 [_standard_actions.yaml line 4-13](../../meta/schemas/_standard_actions.yaml#L4-L13) 已定义：

```yaml
# instance_scope: object | instance
#   - object:  对象级动作（对该资源类型生效，无需指定具体实例）
#   - instance: 实例级动作（对资源类型的具体实例生效）
```

**state_transition 天然是 instance 级别**（在具体实例上做状态推进），不是 object 级别。所以新增的 state_transition 通用 action 应统一标 `instance_scope: instance`，与 `business_approve` / `business_assign` 等已有 business action 一致。

→ **设计结论**：复用已有 action 池 + 复用 instance_scope 标识 + 复用「更多动作」列展示；**不新增维度**，不破坏已有 UI 语义。

## 2. 目标

### 2.1 必须达到（MUST）

| FR | 标题 | 说明 |
|---|---|---|
| **FR-001** | **state_transition 通用 action 入池** | 在 `_standard_actions.yaml` 新增 `business_activate` / `business_deactivate` / `business_lock` / `business_unlock` / `business_reset_password` / `business_freeze` / `business_unfreeze` 等通用 action（带 `action_type: business` + `instance_scope: instance` + `method: PUT`） |
| **FR-002** | **MetaStateTransition 新增 action_ref 字段** | yaml `rules:` 段用 `action_ref: business_activate` 引用通用 action；不再在 yaml 内重声明 label/icon |
| **FR-003** | **状态转换 GET endpoint 返回 action_ref** | `GET /bo/{type}/{id}/state_transitions` 返回的 transition dict 增加 `actionRef` 字段 |
| **FR-004** | **状态转换 PUT 入口做 action_ref 权限校验** | `PUT /bo/{type}/{id}` 当请求体含 `state_field 字段` 时，后端用 `effective_actions` 校验当前用户是否持有对应 `action_ref` 权限；不持有 → 403 |
| **FR-005** | **矩阵「更多动作」列展示 state_transition** | ResourceActionMatrix 在 `extraActionsOf()` 计算时，把该资源支持的 state_transition action（通过 `action_ref` 关联 `_standard_actions.yaml`）一并纳入差异化动作，自动出现在 popover |

### 2.2 应当达到（SHOULD）

| FR | 标题 | 说明 |
|---|---|---|
| **FR-006** | **详情页按钮按权限可见性渲染** | StateTransitionButtons 在渲染时调用 `/api/v2/auth/effective-actions?object_type=user` 获取当前用户实际持有的 business action 列表；不持有的 transition 按钮不渲染（不只置灰） |
| **FR-007** | **`allowed_roles` 字段标 deprecated** | `MetaStateTransition.allowed_roles` 字段仍保留向后兼容，但 yaml 注释说明建议改用 `action_ref` 走标准 action 池 |
| **FR-008** | **测试覆盖完整闭环** | 单元测试 + e2e 测试覆盖 yaml rules 解析、GET endpoint 返回、PUT 权限校验、矩阵展示、详情页可见性 |

### 2.3 不做（WON'T）

| 标题 | 理由 |
|---|---|
| 在 action 上加 `level: object/instance` 字段 | 已有 `instance_scope` 字段是相同语义，重复 |
| 拆分 `crud_update` 与 `state_transition_update` | state_transition 在「非法转换」时拒绝，crud update 不校验；二者行为不同但语义重叠容易混淆 |
| `action_ref` 强制必填 | 保留向后兼容，旧 yaml 仍可自创 ui_hints label |
| 在 `permissions` 表加 `permission_level` | 与 `data_permissions.permission_level` 重名，破坏双轴模型（[Spec 21 WON'T §2.3](./21_action_object_instance_scope_clarification.md#23-不做wont)） |

## 3. 详细设计

### 3.1 FR-001 state_transition 通用 action 入池

**文件**：[`meta/schemas/_standard_actions.yaml`](../../meta/schemas/_standard_actions.yaml)

**插入位置**：在已有 `business_associate / dissociate` 之后（约 100 行后），保持 action_type 分组连续性。

```yaml
# ────────────────────────────────────────────
# 对象级业务 action：状态转换通用池
# [Spec 22 FR-001 2026-09-13] state_transition 通用 action
# instance_scope: instance —— 在具体实例上做状态推进
# action_type: business —— 与 business_approve/bind 等同类
# 对象 yaml 的 rules.action_ref 引用这些 action，避免重复声明 label
# ────────────────────────────────────────────

- id: business_activate
  name: 启用
  action_type: business
  instance_scope: instance
  method: PUT
  description: 启用对象的某个状态字段（如 user.status: active）。通用 action，由各对象 yaml rules 引用并指定 state_field + from_states。

- id: business_deactivate
  name: 停用
  action_type: business
  instance_scope: instance
  method: PUT
  description: 停用对象的某个状态字段。

- id: business_lock
  name: 锁定
  action_type: business
  instance_scope: instance
  method: PUT
  description: 锁定对象（如 user.status: locked），限制登录。

- id: business_unlock
  name: 解锁
  action_type: business
  instance_scope: instance
  method: PUT
  description: 解锁已锁定对象。

- id: business_freeze
  name: 冻结
  action_type: business
  instance_scope: instance
  method: PUT
  description: 冻结对象（保留数据但禁止操作），Salesforce Freeze User 等价物。

- id: business_unfreeze
  name: 解冻
  action_type: business
  instance_scope: instance
  method: PUT
  description: 解冻已冻结对象。

- id: business_reset_password
  name: 重设密码
  action_type: business
  instance_scope: instance
  method: POST
  description: 重设用户密码（Salesforce Reset Passwords 等价物）。

- id: business_archive
  name: 归档
  action_type: business
  instance_scope: instance
  method: PUT
  description: 归档对象（数据保留但不再活跃）。

- id: business_restore
  name: 恢复
  action_type: business
  instance_scope: instance
  method: PUT
  description: 从归档恢复对象到活跃状态。
```

**新增 action 列表**（9 个）：

| action id | instance_scope | method | 典型 from_states → to_state |
|---|---|---|---|
| business_activate | instance | PUT | inactive/frozen/locked → active |
| business_deactivate | instance | PUT | active/locked/frozen → inactive |
| business_lock | instance | PUT | active/inactive → locked |
| business_unlock | instance | PUT | locked → active |
| business_freeze | instance | PUT | active → frozen |
| business_unfreeze | instance | PUT | frozen → active |
| business_reset_password | instance | POST | 任意 → 重置密码邮件 |
| business_archive | instance | PUT | active/inactive → archived |
| business_restore | instance | PUT | archived → active |

**兼容性**：旧 yaml 自创的 state_transition（如 user.yaml 当前 activate_user）暂不强制迁移，详见 FR-007。

### 3.2 FR-002 MetaStateTransition 新增 action_ref 字段

**文件**：[`meta/core/models.py`](../../meta/core/models.py#L244)

```python
@dataclass
class MetaStateTransition(MetaRule):
    """
    状态转换规则
    
    [Spec 22 FR-002 2026-09-13] action_ref 字段关联通用 action 池
    """
    rule_type: RuleType = field(default=RuleType.STATE_TRANSITION)
    state_field: str = "status"
    from_states: List[str] = field(default_factory=list)
    to_state: str = ""
    
    # ── 新增 [Spec 22 FR-002] ──
    # 关联 _standard_actions.yaml 的 action_id。
    # 留空 = 自定义 transition（不进入标准 action 池，向后兼容旧 yaml）
    # 非空 = 该 transition 与对应 action 共享 label/icon/permissions
    action_ref: str = ""
    # ── 新增结束 ──
    
    allowed_roles: List[str] = field(default_factory=list)  # [Spec 22 FR-007] deprecated，建议改用 action_ref
    auto_actions: List[str] = field(default_factory=list)
    validation_expression: str = ""
    validation_message: str = ""
    side_effects: List[StateTransitionSideEffect] = field(default_factory=list)
    ui_hints: Optional[StateTransitionUIHints] = None
```

**文件**：[`meta/core/yaml_loader.py`](../../meta/core/yaml_loader.py#L1503)

**插入位置**：`parse_state_transition` 函数返回值构造前。

```python
def parse_state_transition(data: Dict[str, Any]) -> MetaStateTransition:
    """解析状态转换规则"""
    scope_str = data.get("scope", "object").lower()
    scope = RULE_SCOPE_MAP.get(scope_str, RuleScope.OBJECT)
    
    triggers = _parse_triggers(data.get("triggers", []))
    
    side_effects = []
    # ... 现有 side_effects 解析逻辑 ...
    
    # [Spec 22 FR-002] ui_hints 可选 —— 当 yaml 声明了 action_ref 时，
    # label/icon/confirm_message 从 _standard_actions.yaml 继承（ui_hints 可省略或仅作 override）
    ui_hints = _parse_state_transition_ui_hints(data.get("ui_hints", {}))
    
    return MetaStateTransition(
        id=data.get("id", ""),
        name=data.get("name", ""),
        type=RuleType.STATE_TRANSITION,
        state_field=data.get("state_field", "status"),
        from_states=data.get("from_states", []),
        to_state=data.get("to_state", ""),
        action_ref=data.get("action_ref", ""),     # ← 新增
        allowed_roles=data.get("allowed_roles", []),
        auto_actions=data.get("auto_actions", []),
        validation_expression=data.get("validation_expression", ""),
        validation_message=data.get("validation_message", ""),
        side_effects=side_effects,
        ui_hints=ui_hints,
        scope=scope,
        triggers=triggers,
        # ... 其他 MetaRule 字段 ...
    )
```

**yaml 写法对比**（以 user.yaml activate_user 为例）：

```yaml
# 改前（自创 label/icon，与通用动作池无关联）
rules:
  - id: activate_user
    name: 激活用户
    type: state_transition
    state_field: status
    from_states: [inactive, locked]
    to_state: active
    triggers: [before_update]
    ui_hints:
      label: 激活
      icon: check_circle
      confirm_message: "确定要激活此用户吗？"
      highlight: true

# 改后（action_ref 引用通用 action，ui_hints 仅作 override）
rules:
  - id: activate_user
    name: 激活用户                          # 显示名可保留（覆盖通用 action 的 name）
    type: state_transition
    action_ref: business_activate          # ← 新增：引用通用 action 池
    state_field: status
    from_states: [inactive, locked]
    to_state: active
    triggers: [before_update]
    ui_hints:                              # ui_hints 可省略（继承通用 action 的默认样式）
      confirm_message: "确定要激活此用户吗？"   # 仅覆盖需要定制的字段
```

### 3.3 FR-003 GET /state_transitions endpoint 返回 action_ref

**文件**：[`meta/api/bo_api.py`](../../meta/api/bo_api.py#L1987)

**改动位置**：`get_state_transitions()` 函数返回值构造处（约 line 2013）。

```python
@bo_bp.route('/<object_type>/<int:obj_id>/state_transitions', methods=['GET'])
@login_required
def get_state_transitions(object_type, obj_id):
    # ... 既有代码 ...
    
    state_transitions = []
    for rule in meta_obj.rules:
        if not hasattr(rule, 'state_field'):
            continue
        if not hasattr(rule, 'from_states') or not hasattr(rule, 'to_state'):
            continue
        
        current_state = record.get(rule.state_field) if isinstance(record, dict) else getattr(record, rule.state_field, None)
        is_available = current_state in rule.from_states
        
        ui_hints = getattr(rule, 'ui_hints', None)
        action_ref = getattr(rule, 'action_ref', '')   # ← 新增 [Spec 22 FR-003]
        
        # [Spec 22 FR-003] action_ref 字段暴露给前端 StateTransitionButtons + 权限校验
        transition_info = {
            'id': rule.id,
            'name': rule.name,
            'stateField': rule.state_field,
            'fromStates': list(rule.from_states),
            'toState': rule.to_state,
            'currentState': current_state,
            'available': is_available,
            # ↓↓↓ 新增字段 ↓↓↓
            'actionRef': action_ref,
            # ↑↑↑ 新增结束 ↑↑↑
            'label': ui_hints.label if ui_hints else rule.name,
            'icon': ui_hints.icon if ui_hints else '',
            'confirmMessage': ui_hints.confirm_message if ui_hints else '',
            'highlight': ui_hints.highlight if ui_hints else False,
            'hidden': ui_hints.hidden if ui_hints else False,
        }
        
        # ... 后续逻辑不变 ...
    
    return jsonify({
        'success': True,
        'data': state_transitions,
    })
```

**接口契约变更**：

```jsonc
// GET /api/v1/bo/user/123/state_transitions 返回 data 中每项增字段：
{
  "id": "activate_user",
  "name": "激活用户",
  "stateField": "status",
  "fromStates": ["inactive", "locked"],
  "toState": "active",
  "currentState": "locked",
  "available": true,
  "actionRef": "business_activate",       // ← 新增（向后兼容：空字符串 = 自定义 transition）
  "label": "激活",
  "icon": "check_circle",
  "confirmMessage": "确定要激活此用户吗？",
  "highlight": true,
  "hidden": false
}
```

**兼容性**：`actionRef` 字段对前端可选 —— 旧前端不读该字段行为不变；新前端按 `actionRef` 判断是否走权限校验。

### 3.4 FR-004 PUT /bo/{type}/{id} 入口做 action_ref 权限校验

**目标**：当请求体含 `state_field 字段值变更` 时（即用户在详情页点 state_transition 按钮），后端拦截器自动校验当前用户是否持有该 action_ref 对应的 permission。

**入口选择**：`PUT /bo/{type}/{id}` 是通用更新入口，需要区分「普通字段更新」和「state_transition 触发」。区分策略：**当请求体含且仅含 `{state_field: to_state}` 或附带其他允许字段（side_effects 字段）时，识别为 state_transition**。

#### 3.4.1 新增 ActionPermissionInterceptor

**文件**：[`meta/core/interceptors/action_permission_interceptor.py`](../../meta/core/interceptors/action_permission_interceptor.py)（新建）

```python
"""
[Spec 22 FR-004] 状态转换 action_ref 权限校验拦截器

触发条件：
  - 请求方法：PUT
  - 请求路径：/bo/{type}/{id}
  - 请求体：含与该对象 yaml 中某条 state_transition 规则匹配的 state_field + 目标 to_state

校验逻辑：
  - 在 meta_obj.rules 中查找满足：
    rule.action_ref == request_action_ref
    AND request.state_field == rule.state_field
    AND request[state_field] in rule.to_state (or == rule.to_state for enum)
  - 若找到匹配 rule 且 rule.action_ref 非空：
    用 PermissionInterceptor 检查当前用户是否持有 action_ref 对应 permission
    不持有 → 403 FORBIDDEN
  - 若 action_ref 为空（自定义 transition）：走旧的 allowed_roles 校验，向后兼容
"""

from typing import Any, Dict, Optional, List
from .base import Interceptor, InterceptorPhase
from ..permission_resolver import get_effective_actions
from ..exceptions import ForbiddenError


class ActionPermissionInterceptor(Interceptor):
    phase = InterceptorPhase.PRE_WRITE
    order = 110  # 在 PermissionInterceptor (100) 之后
    
    def should_apply(self, context) -> bool:
        """仅对 PUT /bo/{type}/{id} 生效"""
        return (
            context.method == 'PUT' and
            context.path.startswith('/bo/') and
            '/state_transitions' not in context.path
        )
    
    def execute(self, context):
        """检查 state_transition 的 action_ref 权限"""
        body = context.request_body or {}
        meta_obj = context.meta_obj
        if not meta_obj or not hasattr(meta_obj, 'rules'):
            return context  # 无 rules 定义的对象跳过
        
        # 遍历 rules 找匹配的 state_transition
        for rule in meta_obj.rules:
            if not hasattr(rule, 'state_field') or not hasattr(rule, 'to_state'):
                continue
            if not hasattr(rule, 'action_ref'):
                continue
            
            state_field = rule.state_field
            target_state = rule.to_state
            
            # 请求体是否命中此 transition（state_field 值变更为 to_state）
            if body.get(state_field) != target_state:
                continue
            
            action_ref = rule.action_ref
            if not action_ref:
                # [Spec 22 FR-007] action_ref 为空 = 自定义 transition，走 allowed_roles 校验
                if rule.allowed_roles:
                    current_role = getattr(context, 'current_user_role', None)
                    if current_role not in rule.allowed_roles:
                        raise ForbiddenError(
                            f"当前角色 {current_role} 不在 state_transition {rule.id} 的 allowed_roles 中"
                        )
                continue
            
            # action_ref 非空 → 走标准 action 权限校验
            effective = get_effective_actions(context.current_user_id, meta_obj.bo_id)
            if action_ref not in effective:
                raise ForbiddenError(
                    f"当前用户无权限执行 {action_ref}（state_transition: {rule.id}）"
                )
        
        return context
```

#### 3.4.2 拦截器注册

**文件**：[`meta/core/interceptors/__init__.py`](../../meta/core/interceptors/__init__.py)（或对应注册表）

```python
# [Spec 22 FR-004] 注册 ActionPermissionInterceptor 到全局拦截器链
from .action_permission_interceptor import ActionPermissionInterceptor

ALL_INTERCEPTORS = [
    # ... 现有拦截器 ...
    PermissionInterceptor,         # 基础权限校验 (order=100)
    ActionPermissionInterceptor,   # state_transition action_ref 校验 (order=110)
    # ... 其他拦截器 ...
]
```

#### 3.4.3 effective_actions 接口契约

**已存在**：[`get_effective_actions()`](../../meta/services/permission_resolver.py) 返回当前用户在某资源类型上的全部有效 action_id 列表（含 permission_set 矩阵继承 + data scope 过滤后）。

**用法**：

```python
effective = get_effective_actions(user_id='alice', resource_type='user')
# 返回示例: ['read', 'update', 'business_assign', 'business_activate', ...]

# 校验
if 'business_activate' not in effective:
    raise ForbiddenError("无权限执行 business_activate")
```

### 3.5 FR-005 矩阵「更多动作」列展示 state_transition

#### 3.5.1 数据流

```
1. 后端 /bo/{type}/state-transitions-actions endpoint（新建）
   返回该资源类型支持的所有 state_transition 对应的 action_ref
   
2. 前端 ResourceActionMatrix
   props.supportedActions[resourceType] 增补 state_transition 对应的 action_ref
   
3. extraActionsOf(resourceType) 计算时
   返回 = supportedActions[resourceType] - matrix.columns (主矩阵列)
   包含 state_transition action_ref → 自动出现在「更多动作」popover
```

#### 3.5.2 后端新增 endpoint

**文件**：[`meta/api/bo_api.py`](../../meta/api/bo_api.py)（在 state_transitions 路由后追加）

```python
@bo_bp.route('/<object_type>/state-transition-actions', methods=['GET'])
@login_required
def get_state_transition_actions(object_type):
    """
    [Spec 22 FR-005] 返回该对象类型所有 state_transition 引用的 action_ref 列表
    
    用于前端 ResourceActionMatrix 把 state_transition 作为可勾选 action
    纳入 supportedActions，自动在「更多动作」列展示。
    """
    meta_obj = registry.get(object_type)
    if not meta_obj:
        return jsonify({'success': False, 'message': f'Object type not found: {object_type}'}), 404
    
    action_refs = []
    for rule in (meta_obj.rules or []):
        if not hasattr(rule, 'action_ref') or not hasattr(rule, 'state_field'):
            continue
        if rule.action_ref:
            action_refs.append({
                'action_ref': rule.action_ref,
                'rule_id': rule.id,
                'state_field': rule.state_field,
                'to_state': rule.to_state,
            })
    
    return jsonify({
        'success': True,
        'data': action_refs,
    })
```

**接口契约**：

```jsonc
// GET /api/v1/bo/user/state-transition-actions
{
  "success": true,
  "data": [
    { "action_ref": "business_activate", "rule_id": "activate_user", "state_field": "status", "to_state": "active" },
    { "action_ref": "business_lock", "rule_id": "lock_user", "state_field": "status", "to_state": "locked" },
    { "action_ref": "business_reset_password", "rule_id": "reset_password_user", "state_field": "password_hash", "to_state": "<reset>" }
  ]
}
```

#### 3.5.3 前端 PermissionConfigPanel 加载

**文件**：[`src/views/SystemManagement/components/PermissionConfigPanel.vue`](../../src/views/SystemManagement/components/PermissionConfigPanel.vue)

**改动位置**：在加载 `supportedActions` 处（既有逻辑后追加）。

```javascript
// [Spec 22 FR-005] 把 state_transition action_ref 纳入 supportedActions
async function loadSupportedActions(objectType) {
  const baseActions = await boService.getSupportedActions(objectType)
  
  // 加载该对象类型 state_transition 引用的 action_ref
  try {
    const stResp = await boService.getStateTransitionActions(objectType)
    const transitionActions = (stResp.data || []).map(t => t.action_ref)
    baseActions = Array.from(new Set([...baseActions, ...transitionActions]))
  } catch (e) {
    console.warn(`[Spec 22 FR-005] state_transition actions 加载失败: ${e}`)
  }
  
  return baseActions
}
```

**前端 Service 新增**：

**文件**：[`src/services/boService.js`](../../src/services/boService.js)

```javascript
// [Spec 22 FR-005]
export async function getStateTransitionActions(objectType) {
  return await request.get(`/api/v1/bo/${objectType}/state-transition-actions`)
}
```

#### 3.5.4 ResourceActionMatrix 自动展示

无需改动 —— `extraActionsOf()`（[ResourceActionMatrix.vue:1252](../../src/views/SystemManagement/components/ResourceActionMatrix.vue#L1252)）已支持自动把 `supportedActions` 中未进主矩阵列的 action 渲染到「更多动作」popover：

```javascript
function extraActionsOf(resourceType) {
  const acts = props.supportedActions[resourceType] || []
  const cols = props.matrix?.columns || []
  return acts.filter((a) => !cols.includes(a))
}
```

只要 `supportedActions` 包含 `business_activate` / `business_lock` 等 state_transition action_ref（且未在主矩阵列），popover 自动展示。

### 3.6 FR-006 详情页按钮按权限可见性渲染

**目标**：当前 StateTransitionButtons 不渲染的按钮仅基于 `available: false`（即 from_states 不匹配），未考虑**用户权限**。新增可见性过滤。

**文件**：[`src/components/bo/StateTransitionButtons.vue`](../../src/components/bo/StateTransitionButtons.vue)

```vue
<!-- 在现有 v-for 循环的 <template> 内增加 v-if -->
<template v-for="transition in transitions" :key="transition.id">
  <el-button
    v-if="canPerform(transition)"           <!-- ← 新增 [Spec 22 FR-006] -->
    :type="transition.highlight ? 'primary' : 'default'"
    :icon="iconName(transition.icon)"
    :disabled="!transition.available"
    @click="handleTransition(transition)"
    :data-test="`stt-btn-${transition.actionRef || transition.id}`"
  >
    {{ transition.label }}
  </el-button>
</template>
```

```javascript
// [Spec 22 FR-006] 当前用户在当前资源上的有效 action 列表
const effectiveActions = ref(new Set())

onMounted(async () => {
  // 加载当前用户有效 actions（一次拉取，所有 transition 共用）
  try {
    const resp = await authService.getEffectiveActions({
      objectType: props.objectType,
      objectId: props.objectId
    })
    effectiveActions.value = new Set(resp.data || [])
  } catch (e) {
    console.warn(`[Spec 22 FR-006] effective actions 加载失败: ${e}`)
  }
})

function canPerform(transition) {
  // actionRef 为空 = 自定义 transition，按 available 控制显隐（向后兼容）
  if (!transition.actionRef) {
    return transition.available
  }
  // actionRef 非空 = 必须持有该 action 权限且当前状态可用
  return effectiveActions.value.has(transition.actionRef) && transition.available
}
```

**效果**：用户 A 没有 `business_lock` 权限 → 详情页不显示「锁定」按钮（不只是置灰）。

### 3.7 FR-007 allowed_roles 字段 deprecated

**文件**：[`meta/core/models.py`](../../meta/core/models.py#L254)

```python
allowed_roles: List[str] = field(default_factory=list)
# ↑ 现有字段保留，注释加 deprecated 标记：

# [Spec 22 FR-007 2026-09-13] allowed_roles 字段已 deprecated
# 建议改用 action_ref 字段引用 _standard_actions.yaml 的通用 action，
# 通过标准 permission_set_permissions 矩阵授权。
# 此字段保留仅为向后兼容旧 yaml，新 yaml 不再使用。
# 移除计划：Spec 22 v2（预计 2027 年）
```

**yaml 注释**：[`user.yaml`](../../meta/schemas/user.yaml) line 540 附近

```yaml
# [Spec 22 FR-007] allowed_roles 字段已 deprecated。
# 如需做「只有 admin 才能锁定用户」的权限控制，请改用：
#   action_ref: business_lock
# 然后在 admin 权限集的「更多动作」列勾选 business_lock 即可。
# 此处保留 allowed_roles 仅作向后兼容示例。
```

**不强制迁移**：旧 yaml 仍可使用 allowed_roles 字段，ActionPermissionInterceptor 兼容两条路径（FR-004 §3.4.1 已实现）。

### 3.8 FR-008 测试覆盖

#### 3.8.1 后端单元测试（pytest）

**新文件**：[`meta/tests/test_spec22_state_transition_action_pool.py`](../../meta/tests/test_spec22_state_transition_action_pool.py)

| Test | 断言 |
|---|---|
| `test_standard_actions_includes_business_activate` | StandardActionLoader 加载后包含 `business_activate` |
| `test_standard_actions_business_activate_instance_scope` | business_activate.instance_scope == 'instance' |
| `test_yaml_loader_parses_action_ref` | user.yaml rules 中 activate_user 的 action_ref 解析为 'business_activate' |
| `test_get_state_transitions_returns_action_ref` | GET /bo/user/1/state_transitions 返回的 transition 含 actionRef |
| `test_get_state_transition_actions_returns_action_refs` | GET /bo/user/state-transition-actions 返回 list 含 business_activate |
| `test_action_permission_interceptor_blocks_unauthorized` | 当前用户无 business_lock 权限时，PUT 触发 lock_user transition → 403 |
| `test_action_permission_interceptor_allows_authorized` | 当前用户有 business_activate 权限时，PUT 触发 activate_user → 200 |
| `test_allowed_roles_still_works` | 旧 yaml 仅声明 allowed_roles 的 transition 仍按角色白名单校验 |
| `test_action_ref_empty_falls_back_to_allowed_roles` | action_ref 为空且 allowed_roles 非空时，走 allowed_roles 路径 |

#### 3.8.2 前端单元测试（vitest）

**新文件**：[`src/views/SystemManagement/__tests__/Spec22_state_transition.spec.js`](../../src/views/SystemManagement/__tests__/Spec22_state_transition.spec.js)

| Test | 断言 |
|---|---|
| `test_extra_actions_includes_state_transition_action_ref` | ResourceActionMatrix props.supportedActions 含 business_activate 时，extraActionsOf 包含它 |
| `test_state_transition_button_hidden_without_permission` | StateTransitionButtons 在 effectiveActions 不含 business_lock 时，不渲染 lock 按钮 |
| `test_state_transition_button_visible_with_permission` | effectiveActions 含 business_lock 且 from_states 匹配时，渲染按钮 |

#### 3.8.3 E2E 测试（Playwright）

**新文件**：`tests/e2e/spec22_state_transition_e2e.spec.js`

| Scenario | 断言 |
|---|---|
| 管理员在 user 资源矩阵勾选 `business_lock`（在「更多动作」列） | popover 显示该 action 可勾选；保存成功 |
| 持有 `business_lock` 权限的用户在 user 详情页 | 「锁定」按钮可见 |
| 无 `business_lock` 权限的用户在 user 详情页 | 「锁定」按钮不渲染（DOM 中不存在） |
| 用户 A 调用 PUT /bo/user/123 含 `status: 'locked'` | 无权限 → 403；有权限 → 200 + 状态切换成功 |
| YAML 自定义 transition（action_ref 为空）仍走 allowed_roles 校验 | 向后兼容 |

## 4. 验收清单

### 4.1 FR-001 通用 action 入池

- [ ] `_standard_actions.yaml` 新增 9 个 business_xxx action
- [ ] StandardActionLoader 加载后总数从 16 增至 25
- [ ] 所有新增 action 的 `instance_scope == 'instance'`
- [ ] 所有新增 action 的 `action_type == 'business'`

### 4.2 FR-002 yaml action_ref 字段

- [ ] `MetaStateTransition` 数据类新增 `action_ref: str = ""` 字段
- [ ] yaml `rules:` 段可声明 `action_ref: business_activate`
- [ ] `parse_state_transition()` 正确解析 action_ref 字段
- [ ] 旧 yaml（无 action_ref 字段）仍能正常加载

### 4.3 FR-003 GET endpoint 返回 action_ref

- [ ] `GET /bo/{type}/{id}/state_transitions` 返回 dict 含 `actionRef`
- [ ] actionRef 为空字符串（自定义 transition）不报错
- [ ] 现有 transition 测试用例仍通过

### 4.4 FR-004 PUT 权限校验

- [ ] `ActionPermissionInterceptor` 注册到拦截器链
- [ ] 用户无 `business_lock` 权限时，PUT 触发 lock transition 返回 403
- [ ] 用户有 `business_activate` 权限时，PUT 触发 activate transition 返回 200
- [ ] 旧 yaml 用 allowed_roles 校验仍生效

### 4.5 FR-005 矩阵「更多动作」列展示

- [ ] `GET /bo/{type}/state-transition-actions` endpoint 返回正确数据
- [ ] PermissionConfigPanel 加载时合并 supportedActions + state_transition actions
- [ ] ResourceActionMatrix 渲染时 business_lock 等出现在「更多动作」popover
- [ ] 勾选保存后，permission_set_permissions 表新增对应记录

### 4.6 FR-006 详情页按钮按权限可见性

- [ ] StateTransitionButtons 加载时调用 getEffectiveActions
- [ ] 无权限的 transition 按钮不渲染（DOM 中不存在，非 disabled）
- [ ] 有权限且状态可用的 transition 渲染为可用按钮
- [ ] 有权限但当前状态不可用（from_states 不匹配）渲染为 disabled 按钮

### 4.7 FR-007 allowed_roles 兼容

- [ ] `MetaStateTransition.allowed_roles` 字段保留不删
- [ ] yaml 注释加 deprecated 提示
- [ ] 旧 yaml 测试用例（user.yaml 当前 activate_user 等）全部通过

### 4.8 FR-008 测试覆盖

- [ ] 后端 9 个 pytest 用例全 PASS
- [ ] 前端 3 个 vitest 用例全 PASS
- [ ] E2E 5 个 Playwright 场景全 PASS

## 5. 实施计划

### 5.1 任务拆分

| 票号 | 标题 | 类型 | 工作量 | 依赖 |
|---|---|---|---|---|
| **T-22-01** | `_standard_actions.yaml` 新增 9 个 business_xxx | 后端 yaml | 0.5d | 无 |
| **T-22-02** | `MetaStateTransition` 加 `action_ref` 字段 + `parse_state_transition` 解析 | 后端 | 0.5d | 无 |
| **T-22-03** | `GET /bo/{type}/{id}/state_transitions` 返回 actionRef | 后端 | 0.3d | T-22-02 |
| **T-22-04** | `GET /bo/{type}/state-transition-actions` 新建 | 后端 | 0.3d | T-22-02 |
| **T-22-05** | `ActionPermissionInterceptor` 新建 + 注册 | 后端 | 1d | T-22-02 |
| **T-22-06** | `boService.getStateTransitionActions` 前端 service | 前端 | 0.3d | T-22-04 |
| **T-22-07** | PermissionConfigPanel 合并 supportedActions | 前端 | 0.5d | T-22-06 |
| **T-22-08** | StateTransitionButtons 加 effectiveActions 过滤 | 前端 | 0.5d | 无（可独立） |
| **T-22-09** | 后端 pytest 测试（9 用例） | 测试 | 1d | T-22-05 |
| **T-22-10** | 前端 vitest 测试（3 用例） | 测试 | 0.5d | T-22-07, T-22-08 |
| **T-22-11** | E2E Playwright 测试（5 场景） | 测试 | 1d | T-22-05, T-22-07 |
| **T-22-12** | user.yaml / permission_set.yaml / product.yaml 改造示例 | yaml | 0.5d | T-22-02 |

### 5.2 依赖与风险

| 风险 | 缓解策略 |
|---|---|
| `ActionPermissionInterceptor` 拦截 PUT 误判（普通字段更新被识别为 state_transition） | 严格匹配条件：请求体中 state_field 值必须等于某条 rule 的 to_state 才拦截；其他字段独立 update 不受影响 |
| effective_actions 性能开销（每次详情页加载都拉一次） | 加 30s localStorage 缓存 + 仅当 transitions 列表变更时刷新 |
| 旧 yaml 迁移工作量大 | 不强制迁移，allowed_roles 字段保留向后兼容；新 yaml 推荐用 action_ref |
| `StandardActionLoader` 加载失败兜底 | 现有 try/except 已保留；action 池加载失败 → 所有 action_meta 走 crud 兜底（[Spec 21 FR-003 §3.3.1](./21_action_object_instance_scope_clarification.md#3-3-fr-001-列头语义标识)） |

### 5.3 上线策略（两阶段渐进）

| Phase | 范围 | 风险 | 可单独回滚 |
|---|---|---|---|
| **Phase 1** | T-22-01 ~ T-22-04 + T-22-12 —— 数据层就绪（yaml / endpoint） | 低：纯后端数据扩展 | 是 |
| **Phase 2** | T-22-05 ~ T-22-11 —— 权限校验 + 前端展示 + 测试 | 中：拦截器改动 | 是 |

### 5.4 回滚

- Phase 1：新增 yaml 字段 + endpoint，回滚成本 0
- Phase 2：ActionPermissionInterceptor 加 `enabled=False` 配置开关（默认开启）；关闭后所有 PUT 走旧的 `allowed_roles` 校验路径

## 6. TBD（未来 spec 议题）

| 编号 | 议题 | 备注 |
|---|---|---|
| **TBD-1** | **action 池扩展到菜单权限** | 当前 action 池只覆盖 BO CRUD/业务，未来菜单权限（如 export_excel / batch_approve）也可纳入同一池，统一矩阵 |
| **TBD-2** | **`allowed_roles` 字段移除计划** | v2（预计 2027 年）移除该字段，所有 transition 走 action_ref |
| **TBD-3** | **state_transition 副作用引擎** | `side_effects: [send_email, fire_webhook]` 当前后端未实现，待单独 spec |
| **TBD-4** | **effective_actions 缓存层** | 当前每次详情页加载都拉一次；待权限缓存服务（[perm_cache.py](../../meta/core/perm_cache.py)）增强后切换 |
| **TBD-5** | **跨对象 state_transition** | 当前 state_transition 局限于单对象字段变更（如 user.status）；跨对象级联（如 user.lock → user_session.expire）需另立 spec |

## 6.5 PM 反馈第十六次：user.yaml 5 状态机扩展（2026-09-13）

### 6.5.1 原始问题

> "用户的锁定 激活你看看是否重复了，lock unlock activate deactivate"

PM 观察到 user.yaml 的 state_transition 似有重复：
- `activate` 与 `deactivate` 是一对
- `lock` 与 `unlock` 是一对

担心权限码冗余。

### 6.5.2 业界研究结论

研究 **Salesforce / Microsoft Entra ID / SAP** 三大产品，结论是 lock/unlock、activate/deactivate、freeze/unfreeze、archive/restore **都是配对反向操作**（独立权限码），是「职责分离 (segregation of duties)」的业界标准：

| 产品 | 业务开关 | 安全锁定 | 审查冻结 | 长期归档 |
|---|---|---|---|---|
| **Salesforce** | Active / Inactive | Unlock（密码错锁） | **Freeze**（保留 license） | — |
| **Microsoft Entra ID** | `AccountEnabled=true/false` | `LoginBlocked=true`（独立属性） | — | — |
| **SAP** | T / 空（业务关闭） | 1-7 类锁定（密码/管理员/…） | — | — |
| **本项目 (after v1.1)** | activate / deactivate | lock / unlock | **freeze / unfreeze** | **archive / restore** |

→ 5 类场景对应 5 种业务责任，**权限码必须独立**才能支持 SoD（管理员可只授 unlock 而不授 lock；安全员可只授 freeze 而不授 activate）。

### 6.5.3 决策

通过 `AskUserQuestion` 让 PM 在 3 个方案中选择，最终选择 **「扩 5 个状态」**：

| 方案 | 优点 | 缺点 |
|---|---|---|
| ❌ A. 合并为 3 状态（保留 activate/lock/deactivate） | 简单 | 客服无法只授 unlock，违反 SoD |
| ❌ B. 删除 lock，保留 activate/deactivate | UI 简单 | 无法区分"业务关闭"vs"违规锁定" |
| ✅ **C. 扩 5 个状态**（active/inactive/locked/frozen/archived） | 对齐 Salesforce；9 个通用 action 全部入状态机；权限精细化 | 状态机变大，需更新 color_map |

**最终状态机**：

```
         ┌─────────┐
         │ active  │ ◄─────────────────────────┐
         └────┬────┘                           │
              │                               │
    ┌─────────┼─────────┐                     │
    │lock    freeze     deactivate            │
    ▼         ▼           ▼                   │
┌──────┐ ┌────────┐ ┌──────────┐              │
│locked│ │ frozen │ │ inactive │              │
└──┬───┘ └───┬────┘ └────┬─────┘              │
   │unlock   │unfreeze    │activate            │
   │         │            │                    │
   └─────────┴────────────┴────────────────────┘
                             │
                        archive (inactive/frozen → archived)
                             │
                             ▼
                        ┌──────────┐
                        │ archived │ ── restore ──→ inactive
                        └──────────┘
```

### 6.5.4 关键修复：activate 不再兼任 unlock

**Before**（错误）：
```yaml
- id: activate_user
  from_states: [inactive, locked]   # 错误：activate 同时承担"解锁"
  to_state: active
- id: lock_user
  from_states: [active, locked]     # 错误：lock 能"再锁"
  to_state: locked
```

**After**（职责分离）：
```yaml
- id: activate_user
  from_states: [inactive]           # 仅从 inactive 激活
  to_state: active
- id: lock_user
  from_states: [active]             # 仅从 active 锁定
  to_state: locked
- id: unlock_user                   # [新增] 独立权限码
  from_states: [locked]
  to_state: active
```

→ **效果**：客服角色只勾 `unlock` 不勾 `lock` 即可解锁违规账号，无法锁定健康账号。

### 6.5.5 user.yaml 8 个 state_transition 完整列表

| rule_id | action_ref | from_states | to_state | 角色 |
|---|---|---|---|---|
| `activate_user` | `activate` | `[inactive]` | `active` | HR 业务 |
| `deactivate_user` | `deactivate` | `[active]` | `inactive` | HR 业务 |
| `lock_user` | `lock` | `[active]` | `locked` | 安全应急 |
| `unlock_user` | `unlock` | `[locked]` | `active` | 安全应急（独立权限码） |
| `freeze_user` | `freeze` | `[active, locked]` | `frozen` | 合规审查 |
| `unfreeze_user` | `unfreeze` | `[frozen]` | `active` | 合规审查 |
| _（已撤销，见 §6.7）_ | ~~`archive`~~ | — | — | 数据治理 |
| _（已撤销，见 §6.7）_ | ~~`restore`~~ | — | — | 数据治理 |
| _（不动 status）_ | `reset_password` | — | — | 凭证类（独立 endpoint） |

### 6.5.6 数据迁移影响（v1.1，后被 §6.7 撤销 archive/restore）

- enum_values **加 1 个新值**（`frozen`）：老数据 status 仍是 3 状态值，**无需迁移**
  - `archived` 已在 v1.2（§6.7）撤销
- 7 个 action_ref 接入：`activate`/`deactivate`/`lock`/`unlock`/`freeze`/`unfreeze`/`reset_password`
- 2 处 color_map 同步加 `frozen: warning`：semantics.presentation / list.columns.badge_colors / ui_badge.status.color_map
- `MetaStateTransition` 数据类不变（已支持 `action_ref` 字段）

### 6.5.7 验证结果（v1.1）

```
$ pytest meta/tests/test_spec22_state_transition_action_pool.py
============================= 14 passed in 0.48s ==============================

$ curl http://127.0.0.1:3006/api/v2/bo/user/state-transition-actions
{
  "data": [
    { "action_ref": "activate",  "rule_id": "activate_user",   "to_state": "active"    },
    { "action_ref": "deactivate","rule_id": "deactivate_user", "to_state": "inactive"  },
    { "action_ref": "lock",      "rule_id": "lock_user",       "to_state": "locked"    },
    { "action_ref": "unlock",    "rule_id": "unlock_user",     "to_state": "active"    },
    { "action_ref": "freeze",    "rule_id": "freeze_user",     "to_state": "frozen"    },
    { "action_ref": "unfreeze",  "rule_id": "unfreeze_user",   "to_state": "active"    }
  ],
  "success": true
}
```

✅ 14/14 pytest 通过（含 §6.7 新增 `test_standard_actions_excludes_archive_restore` 反向断言）  
✅ 后端 API 返回 6 个 transition action_ref（v1 是 3 个，v1.1 是 8 个后撤 2 改 6）  
✅ user.yaml schema 加载校验通过（registry.get('user').rules 包含 6 条 MetaStateTransition）

### 6.5.8 后续 TODO（PM 未要求，仅记录）

- 是否同步给 permission_set.yaml / product.yaml 同样扩 4 状态？（当前未实施，仅 user 扩）
- list filter widget 是否同步加 frozen 选项？
- reset_password 不创建 state_transition rule（不改 status 字段），由 BoActionRegistry 独立 endpoint 处理

## 6.7 PM 反馈第十七次：撤销 archive / restore（2026-09-13）

### 6.7.1 原始问题链

PM 抛出三个连续追问，最终推翻 v1.1 设计的 archive/restore：

1. **「归档是否适合放在详情这个页面」** → UI 错位，归档和激活/锁定平铺不合理
2. **「归档不是系统用户操作的吗」** → 根因：归档 90% 由工作流/系统触发，不是真人手动操作
3. **「理论上我们有 auditlog，是不是都是可以恢复的」** → 验证后：auditlog 当前只记 diff 不记 snapshot，确实不能恢复——但**应该让 auditlog 升级承担这个能力**，而不是再造一个 archive transition

### 6.7.2 决策

| 决策点 | v1.1 → v1.2 变更 |
|---|---|
| `_standard_actions.yaml` | 移除 `archive` / `restore`（共 25 → 23 个 action） |
| `user.yaml` rules | 移除 `archive_user` / `restore_user`（共 8 → 6 个 transition） |
| `user.yaml` status enum | 移除 `archived` 状态（5 → 4 状态） |
| `user.yaml` color_map | 移除 `archived: secondary`（3 处） |
| `_ACTION_LABELS`（后端） | 移除 `archive` / `restore` 标签 |
| `ResourceActionMatrix.vue`（前端兜底） | 移除 label fallback |
| pytest | 加 `test_standard_actions_excludes_archive_restore` 反向断言 |
| pytest | `test_standard_actions_total_count` 25 → 23 |

### 6.7.3 撤销理由（与业界对照）

| 维度 | archive transition（v1.1） | audit_log row_snapshot + restore（v1.2 方案） |
|---|---|---|
| 触发主体 | 期望用户手动点（错位） | 系统/工作流/管理员事后恢复 |
| 权限语义 | 谁**允许**归档（RBAC） | 谁**有能力**恢复（系统天然能做） |
| 授权模型 | permission_set 误勾选 → 客服可归档 | 不进矩阵，无需授权 |
| 审计语义 | actor_user_id 是 HR（失真） | actor_type + workflow_id（真实） |
| workflow 集成 | 必须伪造 user_id 走 RBAC | 系统 service 身份直接调用 |
| 适用场景 | 长期不活跃（与 deactivate 重叠） | 数据**找回**（删错、误删） |

→ **业界做法（Salesforce / Notion / Slack / GitHub / Microsoft Entra）一致**：

- 长期不活跃 → `deactivate` / `Disable`（业务开关）
- 数据恢复 → `audit_log` / `Recycle Bin` / `Archive snapshot`（独立能力）

### 6.7.4 长期不活跃语义改由 deactivate + frozen 覆盖

| 业务场景 | v1.1 走 archive | v1.2 改走 |
|---|---|---|
| 员工离职 | `archive_user`（只读保留） | `deactivate_user`（释放 license）+ 长期 `inactive` |
| 客户流失 | `archive_user` | `deactivate_user` |
| 安全审查期 | `freeze_user` | `freeze_user`（保持不变） |
| 临时违规锁定 | `lock_user` | `lock_user`（保持不变） |
| 误删数据 | ~~无能力~~ | `audit_log.restore`（TBD 实施） |

### 6.7.5 TODO（PM 认可暂缓实施）

| 任务 | 描述 | 优先级 |
|---|---|---|
| TODO-1 | `audit_log.yaml` 加 `row_snapshot`（json）+ `snapshot_version`（string）字段 | P1 |
| TODO-2 | `AuditInterceptor.before_action` 在 DELETE 时序列化全行到 `row_snapshot` | P1 |
| TODO-3 | 新增 `POST /api/v2/audit_log/{id}/restore` endpoint，独立权限码 `audit_log:restore`（只给 admin） | P1 |
| TODO-4 | 文档化「长期不活跃场景用 deactivate + frozen」决策到 onboarding 文档 | P2 |

### 6.7.6 验证

- ✅ `_standard_actions.yaml` 已移除 archive/restore
- ✅ `user.yaml` rules 6 条 transition，status enum 4 状态，3 处 color_map 同步
- ✅ `_ACTION_LABELS` 不含 archive/restore
- ✅ `ResourceActionMatrix.vue` label 兜底不含 archive/restore
- ✅ pytest 14/14 通过（含新加的反向断言 `test_standard_actions_excludes_archive_restore`）

## 6.8 PM 反馈第十八次：复用债治理（2026-09-13）

### 6.8.1 触发问题

PM 反馈：「权限预览 tab 在的资源矩阵中看不到这些 action（state_transition），两边老是会有差异，难道背后不是复用的组件或者代码吗？」

调查后定位根因：
1. `PermissionConfigPanel.vue` 走 `usePermissionMeta` + 独家 `loadStateTransitionActions` + `mergedSupportedActions`
2. `ReadonlyAggregateSection.vue` 直接 `loadPermissionMeta()`，**state_transition 合并步骤缺失**

两套数据加载链，两套合并逻辑 → 必然遗漏。

### 6.8.2 修复 §6.8.3 + §6.8.4

#### §6.8.3 单一真源化（usePermissionMeta）— commit `b76dfee`

- `usePermissionMeta.js` 升级为单一真源：
  - 内置 `stateTransitionActionRefs` + `loadStateTransitionActions`
  - 暴露 `supportedActions` (computed) 自动合并 base + state_transition
  - `loadMetaWithScope` 成功后自动 await `loadStateTransitionActions`
- `PermissionConfigPanel.vue` 删除 35 行重复逻辑
- `ReadonlyAggregateSection.vue` 改用 `usePermissionMeta`，与前者同入口、同 scope 保护、同 state_transition 合并

#### §6.8.4 ConditionRuleDialog composable 抽取 — 本 commit

**重复现状**（改动前）：
- `PermissionConfigPanel.vue`：散落 `editingRule` ref / `showAddConditionDialog` ref / `dialogReadonly` ref / `handleOpenConditionDialog` (15 行) / `handleConditionRuleSaved` (35 行) / `handleConditionDialogClose` (3 行)
- `ReadonlyAggregateSection.vue`：`editingRule` ref / `showConditionDialog` ref / `handleOpenConditionDialog` (15 行) / `handleConditionDialogClose` (3 行)
- 两边合计 ~120 行重复代码；payload 字段差异（PermissionConfigPanel 用 Rule Builder 结构化 `__rules`，ReadonlyAggregateSection 用聚合只读说明）容易遗漏

**新建 `src/composables/useConditionRuleDialog.js`**：

```js
useConditionRuleDialog({
  permissionSetId: Ref<string>,
  getRowScope: (rt) => any,         // 调用方各自决定 rt 级 scope 来源
  isEditing: ComputedRef<boolean>,    // 唯一判断源，自动算 dialogReadonly
  onSaved?: (savedRule) => void,      // 可选，仅编辑态写入 scopeMatrix
}) => {
  editingRule, showDialog, dialogReadonly,
  open(payload), close(), handleSaved(savedRule)
}
```

**核心内置逻辑**：
- `open(payload)` 自动应用 `payload.rowScope` 优先 → `getRowScope(rt)` 兜底（融合视图拆行场景）
- `open(payload)` 自动回填 `condition / condition_display / initialRules / rule_id`
- `dialogReadonly = !isEditing.value`（调用方无需自己算）
- `handleSaved` 仅编辑态触发 `onSaved`，只读态静默关闭（防止误保存）

**接入**：
- `PermissionConfigPanel.vue` 删 ~60 行重复，引入 composable + onConditionRuleSaved 薄回调
- `ReadonlyAggregateSection.vue` 删 ~30 行重复，引入 composable（`isReadonly = computed(() => true)` 永远只读）

### 6.8.5 复用债盘点（PM 二次确认结论）

| 债 | 实际复杂度 | 本轮做？ | TODO |
|---|---|---|---|
| ~~菜单数据源 composable~~ | **误判** — 两组件菜单数据来源不同（单 ps vs fused）、结构不同 | ❌ 不做 | 无 |
| ✅ ConditionRuleDialog composable | 中（两边真实重复） | ✅ 本轮 | 已完成 |
| scopeMatrix 平铺逻辑抽取 | 高（含 dimension 业务键锚点分离、hydrateAnchorPreviews） | ❌ 暂缓 | P2 backlog（仅 PermissionConfigPanel 内部使用） |
| DetailPage section.type 分发器重构 | 高（DetailPage + ObjectPageContent 同时改） | ❌ 暂缓 | P3 独立专项 |
| ResourceActionMatrix / MenuPermissionMatrix props 类型统一 | 中（spec 不同步易引发徽章脱节类 bug） | ❌ 暂缓 | P3 backlog |

### 6.8.6 验证

- ✅ `vite build` 通过，无 TypeScript / 模板编译错误
- ✅ pytest 15/15 passed（Spec 22 测试无回归）
- ✅ PermissionConfigPanel 与 ReadonlyAggregateSection 走同一条 `useConditionRuleDialog` 调用模板
- ✅ 两边行为对齐：dialogReadonly、payload.rowScope 优先、initialRules 回填、rule_id 回写

## 7. 关联阅读

- [Spec 21 动作对象级/实例级语义显式化](./21_action_object_instance_scope_clarification.md)（action_type / instance_scope 体系）
- [Spec 15 §2.2 数据权限单一"范围 + 例外"二分](./15_permission_config_unification.md#22-数据权限单一范围--例外二分)
- [Spec 16 role → permission_set 迁移](./16_role_to_permission_set_and_user_group_to_org.md)
- [`_standard_actions.yaml`](../../meta/schemas/_standard_actions.yaml)（标准动作池）
- [`MetaStateTransition`](../../meta/core/models.py#L244)（状态转换数据类）
- [`MetaAction` / `ActionType`](../../meta/core/models.py#L557-L573)
- [`StandardActionLoader`](../../meta/core/standard_action_loader.py)
- [StateTransitionButtons](../../src/components/bo/StateTransitionButtons.vue)
- [ResourceActionMatrix.vue:1252](../../src/views/SystemManagement/components/ResourceActionMatrix.vue#L1252)（extraActionsOf 实现）
- [`PermissionInterceptor`](../../meta/core/interceptors/permission_interceptor.py)（基础权限拦截器）
- [`/bo/{type}/{id}/state_transitions` endpoint](../../meta/api/bo_api.py#L1987)
- [`user.yaml` rules 示例](../../meta/schemas/user.yaml#L540-L589)
- [`product.yaml` rules 示例](../../meta/schemas/product.yaml#L530-L559)

***

**修订记录**

| 日期 | 版本 | 变更 | 作者 |
|---|---|---|---|
| 2026-09-13 | v1 | 初稿，基于 Spec 21 PM 反馈第十一次（用户/组织 action 缺失） | AI Assistant |
| 2026-09-13 | v1.1 | PM 反馈第十六次：user.yaml status 从 3 状态扩到 5 状态（active/inactive/locked/frozen/archived），新增 unlock/freeze/unfreeze/archive/restore 5 个独立权限码；activate from_states 收紧为 `[inactive]` 不再兼任 unlock | AI Assistant |
