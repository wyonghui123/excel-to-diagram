# Phase C: 行为控制（Deletability + Action Type）Spec

## Why

当前元模型缺少对业务行为的动态控制能力：(1) 删除和新增操作的权限控制是硬编码的，无法根据业务状态动态判断；(2) 自定义业务操作需要手写代码实现，无法通过声明式配置定义；(3) 与 SAP 的 `@OData.OperationAvailable` 和 Palantir 的 Action Type 体系不对齐，影响企业级业务场景的灵活性。Phase C 将实现 Deletability/Addability 动态 CRUD 控制和 Action Type 声明式操作。

## What Changes

### Part 1: Deletability/Addability 动态 CRUD 控制

- **YAML 配置扩展**：`MetaObject` 新增 `deletability` 和 `addability` 配置块，支持条件表达式
- **条件评估引擎**：新增 `ConditionEvaluator` 类，支持运行时评估业务条件
- **ManageService 扩展**：`create()`/`delete()` 方法增加动态条件检查
- **API 响应增强**：返回 `can_delete`/`can_add` 标志，供前端使用

### Part 2: Action Type 声明式操作

- **MetaAction 扩展**：新增 `behavior` 属性，支持 `precondition`、`effects`、`set_fields`
- **声明式执行引擎**：实现 `ActionExecutor._execute_business()` 的声明式执行
- **自定义 Action API**：新增 `POST /api/v1/<object_type>/actions/<action_id>` 端点

## Impact

- Affected specs: p1-phase-a-aspect-pseudo-variables（behavior 可复用 auto_fill 的伪变量）
- Affected code:
  - `meta/core/models.py` - MetaAction 新增 behavior 属性；MetaObject 新增 deletability/addability
  - `meta/core/yaml_loader.py` - 解析 deletability/addability/behavior 配置
  - `meta/core/condition_evaluator.py` - 新增条件评估引擎
  - `meta/core/action_executor.py` - _execute_business() 实现声明式执行
  - `meta/services/manage_service.py` - create()/delete() 增加动态条件检查
  - `meta/api/manage_api.py` - 新增 action 端点；响应返回 can_delete/can_add
  - `meta/schemas/*.yaml` - 添加 deletability/addability 配置

## ADDED Requirements

### Requirement: Deletability 配置

系统 SHALL 支持在对象级别配置 `deletability`，定义删除操作的业务条件。

#### Scenario: 条件化删除控制
- **WHEN** 对象配置了 `deletability.condition: "status != 'released' and child_count == 0"`
- **THEN** 只有满足条件的记录才能被删除，否则返回错误消息

#### Scenario: 删除条件消息
- **WHEN** 删除条件不满足
- **THEN** 返回配置的 `deletability.message` 作为错误提示

#### YAML 示例
```yaml
deletability:
  condition: "status != 'released' and child_count == 0"
  message: "已发布或有子对象的数据不能删除"
```

### Requirement: Addability 配置

系统 SHALL 支持在对象级别配置 `addability`，定义新增操作的业务条件。

#### Scenario: 条件化新增控制
- **WHEN** 子对象配置了 `addability.condition: "parent.status in ['open', 'draft']"`
- **THEN** 只有父对象状态为 open 或 draft 时才能新增子对象

#### Scenario: 父对象状态检查
- **WHEN** 新增子对象时父对象状态不允许
- **THEN** 返回配置的 `addability.message` 作为错误提示

#### YAML 示例
```yaml
addability:
  condition: "parent.status in ['open', 'draft']"
  message: "父对象状态不允许新增"
```

### Requirement: 条件评估引擎

系统 SHALL 提供条件评估引擎，支持运行时评估业务条件表达式。

#### Scenario: 基本条件评估
- **WHEN** 调用 `ConditionEvaluator.evaluate("status == 'active'", context)`
- **THEN** 返回布尔值结果

#### Scenario: 字段访问
- **WHEN** 条件表达式包含 `parent.status`
- **THEN** 自动解析父对象并访问其 status 字段

#### Scenario: 支持的操作符
- **GIVEN** 条件表达式
- **THEN** 支持 `==`, `!=`, `>`, `<`, `>=`, `<=`, `in`, `not in`, `and`, `or`, `not` 操作符

### Requirement: Action Behavior 声明式配置

系统 SHALL 支持在 Action 中配置 `behavior`，定义前置条件和执行效果。

#### Scenario: 前置条件检查
- **WHEN** Action 配置了 `behavior.precondition`
- **THEN** 执行前检查条件，不满足则返回错误

#### Scenario: 字段设置效果
- **WHEN** Action 配置了 `behavior.effects` 中的 `set_fields`
- **THEN** 执行时自动设置指定字段的值

#### Scenario: 伪变量支持
- **WHEN** `set_fields` 中使用 `$now`、`$user.id` 等伪变量
- **THEN** 自动解析为实际值

#### YAML 示例
```yaml
actions:
  - id: promote
    name: 晋升
    type: custom
    method: POST
    path: /api/v1/employees/{id}/actions/promote
    parameters:
      - id: new_role
        name: 新角色
        type: string
        required: true
    behavior:
      precondition:
        condition: "status == 'active'"
        message: "非活跃员工不能晋升"
      effects:
        - type: set_fields
          target: self
          fields:
            role: $parameters.new_role
            promoted_at: $now
            promoted_by: $user.name
```

### Requirement: 自定义 Action API

系统 SHALL 提供自定义 Action 的 API 端点。

#### Scenario: 执行自定义 Action
- **WHEN** 调用 `POST /api/v1/employees/1/actions/promote` 并传入参数
- **THEN** 执行对应的 Action 并返回结果

#### Scenario: Action 列表查询
- **WHEN** 调用 `GET /api/v1/employees/1/actions`
- **THEN** 返回该对象可执行的所有 Action 列表及其可用性

### Requirement: API 响应增强

系统 SHALL 在 API 响应中返回操作可用性标志。

#### Scenario: 查询返回 can_delete
- **WHEN** 查询单条记录
- **THEN** 响应中包含 `can_delete` 字段，表示当前记录是否可删除

#### Scenario: 查询返回 can_add
- **WHEN** 查询父对象的子对象列表
- **THEN** 响应中包含 `can_add` 字段，表示是否可以新增子对象

## MODIFIED Requirements

### Requirement: MetaObject 扩展

`MetaObject` 数据类 SHALL 新增以下属性：

```python
@dataclass
class DeletabilityConfig:
    condition: str = ""
    message: str = ""
    
@dataclass
class AddabilityConfig:
    condition: str = ""
    message: str = ""

@dataclass
class MetaObject:
    # ... existing fields ...
    deletability: Optional[DeletabilityConfig] = None
    addability: Optional[AddabilityConfig] = None
```

### Requirement: MetaAction 扩展

`MetaAction` 数据类 SHALL 新增 `behavior` 属性：

```python
@dataclass
class ActionPrecondition:
    condition: str = ""
    message: str = ""

@dataclass
class ActionEffect:
    type: str = ""  # set_fields | trigger
    target: str = "self"  # self | parent | children
    fields: Dict[str, Any] = field(default_factory=dict)
    handler: str = ""

@dataclass
class ActionBehavior:
    precondition: Optional[ActionPrecondition] = None
    effects: List[ActionEffect] = field(default_factory=list)

@dataclass
class MetaAction:
    # ... existing fields ...
    behavior: Optional[ActionBehavior] = None
```

### Requirement: yaml_loader 解析扩展

`yaml_loader.py` SHALL 扩展解析以下配置：

```python
def parse_deletability(data: Dict) -> Optional[DeletabilityConfig]:
    if "deletability" in data:
        d = data["deletability"]
        return DeletabilityConfig(
            condition=d.get("condition", ""),
            message=d.get("message", "")
        )
    return None

def parse_addability(data: Dict) -> Optional[AddabilityConfig]:
    if "addability" in data:
        a = data["addability"]
        return AddabilityConfig(
            condition=a.get("condition", ""),
            message=a.get("message", "")
        )
    return None

def parse_behavior(data: Dict) -> Optional[ActionBehavior]:
    if "behavior" in data:
        b = data["behavior"]
        precondition = None
        if "precondition" in b:
            p = b["precondition"]
            precondition = ActionPrecondition(
                condition=p.get("condition", ""),
                message=p.get("message", "")
            )
        effects = []
        for e in b.get("effects", []):
            effects.append(ActionEffect(
                type=e.get("type", ""),
                target=e.get("target", "self"),
                fields=e.get("fields", {}),
                handler=e.get("handler", "")
            ))
        return ActionBehavior(precondition=precondition, effects=effects)
    return None
```

## REMOVED Requirements

无移除的需求。所有现有功能保持向后兼容。
