# Phase C: 行为控制 Tasks

## 任务列表

### Task 1: 模型定义扩展
**优先级**: 高
**预估复杂度**: 小

- [ ] 在 `models.py` 中添加 `DeletabilityConfig` 数据类
- [ ] 在 `models.py` 中添加 `AddabilityConfig` 数据类
- [ ] 在 `models.py` 中添加 `ActionPrecondition` 数据类
- [ ] 在 `models.py` 中添加 `ActionEffect` 数据类
- [ ] 在 `models.py` 中添加 `ActionBehavior` 数据类
- [ ] 扩展 `MetaObject` 添加 `deletability` 和 `addability` 属性
- [ ] 扩展 `MetaAction` 添加 `behavior` 属性

### Task 2: YAML 解析扩展
**优先级**: 高
**预估复杂度**: 小

- [ ] 在 `yaml_loader.py` 中添加 `parse_deletability()` 函数
- [ ] 在 `yaml_loader.py` 中添加 `parse_addability()` 函数
- [ ] 在 `yaml_loader.py` 中添加 `parse_behavior()` 函数
- [ ] 在 `parse_meta_object()` 中调用新的解析函数
- [ ] 在 `parse_action()` 中调用 `parse_behavior()`

### Task 3: 条件评估引擎
**优先级**: 高
**预估复杂度**: 中

- [ ] 创建 `meta/core/condition_evaluator.py` 文件
- [ ] 实现 `ConditionEvaluator` 类
- [ ] 支持基本比较操作符 (`==`, `!=`, `>`, `<`, `>=`, `<=`)
- [ ] 支持逻辑操作符 (`and`, `or`, `not`)
- [ ] 支持成员操作符 (`in`, `not in`)
- [ ] 支持 `parent.field` 语法访问父对象字段
- [ ] 支持 `self.field` 语法访问当前对象字段
- [ ] 添加单元测试

### Task 4: Deletability/Addability 检查集成
**优先级**: 高
**预估复杂度**: 中

- [ ] 在 `ManageService.delete()` 中集成 deletability 检查
- [ ] 在 `ManageService.create()` 中集成 addability 检查
- [ ] 在 `ActionExecutor._do_delete()` 中集成 deletability 检查
- [ ] 在 `ActionExecutor._do_create()` 中集成 addability 检查
- [ ] 添加单元测试

### Task 5: Action Behavior 声明式执行
**优先级**: 高
**预估复杂度**: 中

- [ ] 在 `ActionExecutor` 中实现 `_execute_business()` 声明式执行
- [ ] 实现 precondition 检查逻辑
- [ ] 实现 set_fields 效果执行
- [ ] 支持伪变量解析 (`$now`, `$user.id`, `$user.name`, `$parameters.xxx`)
- [ ] 添加单元测试

### Task 6: API 端点扩展
**优先级**: 中
**预估复杂度**: 中

- [ ] 在 `manage_api.py` 中添加 `GET /api/v1/<object_type>/<id>/actions` 端点
- [ ] 在 `manage_api.py` 中添加 `POST /api/v1/<object_type>/<id>/actions/<action_id>` 端点
- [ ] 在查询响应中添加 `can_delete` 标志
- [ ] 在查询响应中添加 `can_add` 标志
- [ ] 添加 API 测试

### Task 7: YAML Schema 示例
**优先级**: 低
**预估复杂度**: 小

- [ ] 在 `business_object.yaml` 中添加 deletability 配置示例
- [ ] 在 `domain.yaml` 中添加 deletability 配置示例
- [ ] 创建自定义 action 配置示例

### Task 8: 测试和验证
**优先级**: 高
**预估复杂度**: 中

- [ ] 添加 `test_deletability.py` 测试文件
- [ ] 添加 `test_addability.py` 测试文件
- [ ] 添加 `test_action_behavior.py` 测试文件
- [ ] 添加 `test_condition_evaluator.py` 测试文件
- [ ] 运行完整测试套件验证

## 依赖关系

```
Task 1 (模型定义) ─────────────────────────────────────────┐
                                                            │
Task 2 (YAML解析) ─────────────────────────────────────────┤
                                                            │
Task 3 (条件评估引擎) ─────────────────────────────────────┤
                                                            │
Task 4 (Deletability/Addability 集成) ←── Task 1, 2, 3 ───┤
                                                            │
Task 5 (Action Behavior 执行) ←── Task 1, 2, 3 ───────────┤
                                                            │
Task 6 (API 端点) ←── Task 4, 5 ──────────────────────────┤
                                                            │
Task 7 (YAML Schema 示例) ←── Task 1, 2 ──────────────────┤
                                                            │
Task 8 (测试验证) ←── Task 1-7 ────────────────────────────┘
```

## 实施顺序

1. **Task 1 + Task 2**: 模型定义和 YAML 解析（可并行）
2. **Task 3**: 条件评估引擎
3. **Task 4**: Deletability/Addability 集成
4. **Task 5**: Action Behavior 执行
5. **Task 6**: API 端点扩展
6. **Task 7**: YAML Schema 示例
7. **Task 8**: 测试验证
