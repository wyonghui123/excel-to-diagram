# Checklist

## Phase 1: 核心框架

### Task 1: Interceptor Base
- [ ] `meta/core/interceptors/__init__.py` 文件创建
- [ ] `meta/core/interceptors/base.py` 文件创建
- [ ] Interceptor 抽象基类定义正确
- [ ] before_action / after_action / on_error 方法签名正确

### Task 2: ActionContext
- [ ] `meta/core/action_context.py` 文件创建
- [ ] ActionContext 数据类定义正确
- [ ] 包含事务信息（transaction_id, is_nested）
- [ ] 包含锁信息（lock_type, lock_timeout）

### Task 3: BOFramework
- [ ] `meta/core/bo_framework.py` 文件创建
- [ ] create / read / update / delete 方法正确实现
- [ ] execute_action 方法正确实现
- [ ] associate 方法正确实现
- [ ] 拦截器链执行逻辑正确

### Task 4: Transaction Control
- [ ] begin_transaction() 正确实现
- [ ] commit() 正确实现
- [ ] rollback() 正确实现
- [ ] 嵌套事务支持
- [ ] 事务隔离级别配置支持

### Task 5: PersistenceInterceptor
- [ ] `meta/core/interceptors/persistence_interceptor.py` 文件创建
- [ ] 正确复用 ActionExecutor
- [ ] context.result 正确设置

### Task 6-8: Audit
- [ ] AuditConfig 数据类定义正确
- [ ] MetaObject.audit 字段可用
- [ ] YAML Loader 正确解析 audit 配置
- [ ] AuditInterceptor 正确实现
- [ ] changed_only 策略正确
- [ ] business_only 策略正确
- [ ] user.yaml / role.yaml / user_group.yaml 审计配置正确

### Task 9: LockInterceptor
- [ ] `meta/core/interceptors/lock_interceptor.py` 文件创建
- [ ] 乐观锁正确实现
- [ ] 悲观锁正确实现
- [ ] 锁超时配置支持

### Task 10-12: API Migration
- [ ] user_api.py 使用 BOFramework
- [ ] role_api.py 使用 BOFramework
- [ ] user_group_api.py 使用 BOFramework
- [ ] 审计日志正确

### Task 13: Tests
- [ ] `meta/tests/test_bo_framework.py` 文件创建
- [ ] CRUD 操作测试通过
- [ ] 事务控制测试通过
- [ ] 审计日志测试通过

---

## Phase 2: AI 代码生成

### Task 14: Code Generation Framework
- [ ] `meta/generators/__init__.py` 文件创建
- [ ] `meta/generators/base_generator.py` 文件创建
- [ ] Jinja2 模板引擎集成

### Task 15: API Generator
- [ ] `meta/generators/api_generator.py` 文件创建
- [ ] CRUD API 生成正确
- [ ] 业务动作 API 生成正确

### Task 16: Service Generator
- [ ] `meta/generators/service_generator.py` 文件创建
- [ ] Service 类生成正确
- [ ] DTO 类生成正确

### Task 17: Test Generator
- [ ] `meta/generators/test_generator.py` 文件创建
- [ ] 单元测试生成正确
- [ ] 集成测试生成正确

### Task 18: AI Generation Config
- [ ] MetaObject.ai_generation 字段可用
- [ ] 自定义模板配置支持

### Task 19: CLI
- [ ] `meta/cli/generate.py` 文件创建
- [ ] `python -m meta generate api` 命令正常
- [ ] `python -m meta generate all` 命令正常

---

## Phase 3: 动态 UI

### Task 20: UI Config
- [ ] MetaObject.ui_view_config 字段可用
- [ ] 列表配置支持
- [ ] 表单配置支持
- [ ] 详情页配置支持

### Task 21: UI Schema Parser
- [ ] `meta/ui/schema_parser.py` 文件创建
- [ ] YAML UI 配置解析正确
- [ ] 前端组件配置转换正确

### Task 22: DynamicList
- [ ] `src/components/DynamicList.vue` 文件创建
- [ ] 列配置正确
- [ ] 筛选、排序、分页正确
- [ ] 响应式布局正确

### Task 23: DynamicForm
- [ ] `src/components/DynamicForm.vue` 文件创建
- [ ] 字段验证正确
- [ ] 联动正确
- [ ] 分组、标签页正确

### Task 24: DynamicDetail
- [ ] `src/components/DynamicDetail.vue` 文件创建
- [ ] 字段布局正确
- [ ] 关联数据展示正确

### Task 25: UI Schema API
- [ ] `meta/api/ui_schema_api.py` 文件创建
- [ ] GET /api/v1/ui/schema/{object_type} 端点正常
- [ ] 返回正确的 UI 配置

---

## Phase 4: 工作流集成

### Task 26: Workflow Engine
- [ ] `meta/workflow/engine.py` 文件创建
- [ ] 状态机正确实现
- [ ] 状态转换规则正确

### Task 27: WorkflowInterceptor
- [ ] `meta/core/interceptors/workflow_interceptor.py` 文件创建
- [ ] 工作流触发正确
- [ ] 状态转换处理正确

### Task 28: Approval Flow
- [ ] `meta/workflow/approval_flow.py` 文件创建
- [ ] 多级审批支持
- [ ] 会签、或签支持

### Task 29: Notification Service
- [ ] `meta/services/notification_service.py` 文件创建
- [ ] 邮件通知支持
- [ ] 站内消息支持

### Task 30: Workflow Config
- [ ] MetaObject.workflow 字段可用
- [ ] 状态定义支持
- [ ] 转换规则支持

---

## Phase 5: 业务规则引擎

### Task 31: Rules Engine
- [ ] `meta/rules/engine.py` 文件创建
- [ ] 规则表达式解析正确
- [ ] 规则执行正确

### Task 32: BusinessRuleInterceptor
- [ ] `meta/core/interceptors/business_rule_interceptor.py` 文件创建
- [ ] 业务规则执行正确
- [ ] 规则异常处理正确

### Task 33: Validation Rules
- [ ] 跨字段验证支持
- [ ] 跨对象验证支持

### Task 34: Calculation Rules
- [ ] 字段自动计算支持
- [ ] 聚合计算支持

### Task 35: Business Rules Config
- [ ] MetaObject.business_rules 字段可用
- [ ] 规则定义支持
- [ ] 触发条件支持

---

## Phase 6: 其他拦截器

### Task 36: ContextInterceptor
- [ ] `meta/core/interceptors/context_interceptor.py` 文件创建
- [ ] 用户上下文设置正确
- [ ] Trace ID 设置正确

### Task 37: PermissionInterceptor
- [ ] `meta/core/interceptors/permission_interceptor.py` 文件创建
- [ ] 权限检查正确
- [ ] 数据级权限支持

### Task 38: ValidationInterceptor
- [ ] `meta/core/interceptors/validation_interceptor.py` 文件创建
- [ ] 字段验证正确
- [ ] 自定义验证器支持

### Task 39: DeterminationInterceptor
- [ ] `meta/core/interceptors/determination_interceptor.py` 文件创建
- [ ] 字段自动计算正确
- [ ] updated_at 自动填充正确

---

## 企业级特性验收

### 事务控制
- [ ] ACID 事务正确
- [ ] 嵌套事务正确
- [ ] 事务隔离级别配置正确

### 锁机制
- [ ] 乐观锁正确
- [ ] 悲观锁正确
- [ ] 锁超时处理正确

### 工作流
- [ ] 状态机正确
- [ ] 审批流程正确
- [ ] 通知服务正确

### 业务规则
- [ ] 规则引擎正确
- [ ] 跨对象验证正确
- [ ] 自动计算正确

---

## AI-Enhanced 特性验收

### 代码生成
- [ ] API 代码生成正确
- [ ] Service 代码生成正确
- [ ] 测试代码生成正确
- [ ] CLI 命令正常

### 动态 UI
- [ ] 列表组件正确
- [ ] 表单组件正确
- [ ] 详情组件正确
- [ ] UI Schema API 正常

---

## 最终验收

### 核心功能
- [ ] BOFramework CRUD 正常
- [ ] 事务控制正常
- [ ] 锁机制正常
- [ ] 审计日志正常

### 企业级特性
- [ ] 工作流集成正常
- [ ] 业务规则引擎正常
- [ ] 权限检查正常

### AI-Enhanced 特性
- [ ] 代码生成效率提升
- [ ] 动态 UI 正常
- [ ] 开发效率提升

### 性能
- [ ] 拦截器链开销 < 5ms
- [ ] 事务性能正常
- [ ] 锁机制性能正常
