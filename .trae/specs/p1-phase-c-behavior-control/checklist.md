# Phase C: 行为控制 Checklist

## 验收标准

### Part 1: Deletability/Addability

- [ ] **AC1.1**: 对象可以配置 `deletability.condition`，删除时自动检查条件
- [ ] **AC1.2**: 删除条件不满足时返回配置的错误消息
- [ ] **AC1.3**: 对象可以配置 `addability.condition`，新增时自动检查条件
- [ ] **AC1.4**: 新增条件不满足时返回配置的错误消息
- [ ] **AC1.5**: 条件表达式支持 `parent.field` 语法访问父对象字段
- [ ] **AC1.6**: 条件表达式支持基本比较和逻辑操作符

### Part 2: Action Type

- [ ] **AC2.1**: Action 可以配置 `behavior.precondition`，执行前自动检查
- [ ] **AC2.2**: Action 可以配置 `behavior.effects.set_fields`，执行时自动设置字段
- [ ] **AC2.3**: `set_fields` 支持 `$now`、`$user.id`、`$user.name` 伪变量
- [ ] **AC2.4**: `set_fields` 支持 `$parameters.xxx` 访问 Action 参数
- [ ] **AC2.5**: 自定义 Action 可以通过 API 端点调用执行

### Part 3: API 增强

- [ ] **AC3.1**: 查询单条记录时返回 `can_delete` 标志
- [ ] **AC3.2**: 查询列表时返回每条记录的 `can_delete` 标志
- [ ] **AC3.3**: `GET /api/v1/<object_type>/<id>/actions` 返回可用 Action 列表
- [ ] **AC3.4**: `POST /api/v1/<object_type>/<id>/actions/<action_id>` 执行自定义 Action

### Part 4: 测试覆盖

- [ ] **AC4.1**: 条件评估引擎单元测试覆盖率 >= 90%
- [ ] **AC4.2**: Deletability 集成测试通过
- [ ] **AC4.3**: Addability 集成测试通过
- [ ] **AC4.4**: Action Behavior 集成测试通过
- [ ] **AC4.5**: 所有现有测试保持通过

## 技术检查清单

### 代码质量

- [ ] 新增代码有完整的类型注解
- [ ] 新增代码有 docstring 文档
- [ ] 遵循现有代码风格
- [ ] 无 lint 错误

### 向后兼容

- [ ] 现有 YAML 配置无需修改即可正常工作
- [ ] 现有 API 行为不变
- [ ] 新增属性有默认值，不影响现有代码

### 安全性

- [ ] 条件表达式评估有安全限制（防止代码注入）
- [ ] API 端点有适当的权限检查
- [ ] 敏感操作有审计日志

## 文档更新

- [ ] 更新 BACKLOG-MetaModel-Enhancement.md 标记 Phase C 完成
- [ ] 更新相关 API 文档
