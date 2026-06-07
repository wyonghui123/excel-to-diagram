# Tasks

## Phase 1: 核心框架 (Week 1-3)

### 1.1 拦截器基础设施

- [ ] Task 1: 创建拦截器基类
  - [ ] 创建 `meta/core/interceptors/__init__.py`
  - [ ] 创建 `meta/core/interceptors/base.py`
  - [ ] 定义 `Interceptor` 抽象基类
  - [ ] 定义 `before_action` / `after_action` / `on_error` 方法

- [ ] Task 2: 创建执行上下文
  - [ ] 创建 `meta/core/action_context.py`
  - [ ] 定义 `ActionContext` 数据类（含事务、锁信息）

### 1.2 BOFramework 核心

- [ ] Task 3: 创建 BOFramework 核心
  - [ ] 创建 `meta/core/bo_framework.py`
  - [ ] 实现 CRUD 操作：create / read / update / delete / query
  - [ ] 实现业务操作：execute_action / associate / convert_key
  - [ ] 实现拦截器链执行逻辑

- [ ] Task 4: 实现事务控制
  - [ ] 实现 `begin_transaction()` / `commit()` / `rollback()`
  - [ ] 支持嵌套事务
  - [ ] 支持事务隔离级别配置

- [ ] Task 5: 创建 PersistenceInterceptor
  - [ ] 创建 `meta/core/interceptors/persistence_interceptor.py`
  - [ ] 复用现有 `ActionExecutor` 执行 CRUD

### 1.3 审计拦截器

- [ ] Task 6: 扩展元模型支持审计配置
  - [ ] 在 `meta/core/models.py` 添加 `AuditConfig` 数据类
  - [ ] 扩展 `MetaObject` 添加 `audit` 字段
  - [ ] 更新 YAML Loader 解析 audit 配置

- [ ] Task 7: 实现 AuditInterceptor
  - [ ] 创建 `meta/core/interceptors/audit_interceptor.py`
  - [ ] 实现 `before_action`：获取旧数据
  - [ ] 实现 `after_action`：根据配置记录审计日志
  - [ ] 支持 `changed_only` / `business_only` 策略

- [ ] Task 8: 添加 YAML 审计配置
  - [ ] 更新 `meta/schemas/user.yaml` 添加 audit 配置
  - [ ] 更新 `meta/schemas/role.yaml` 添加 audit 配置
  - [ ] 更新 `meta/schemas/user_group.yaml` 添加 audit 配置

### 1.4 锁机制

- [ ] Task 9: 实现 LockInterceptor
  - [ ] 创建 `meta/core/interceptors/lock_interceptor.py`
  - [ ] 实现乐观锁（版本号）
  - [ ] 实现悲观锁（数据库锁）
  - [ ] 支持锁超时配置

### 1.5 API 迁移

- [ ] Task 10: 迁移 user_api.py
  - [ ] 重构使用 BOFramework
  - [ ] 验证审计日志正确

- [ ] Task 11: 迁移 role_api.py
  - [ ] 重构使用 BOFramework
  - [ ] 验证审计日志正确

- [ ] Task 12: 迁移 user_group_api.py
  - [ ] 重构使用 BOFramework
  - [ ] 验证审计日志正确

### 1.6 测试

- [ ] Task 13: 核心框架测试
  - [ ] 创建 `meta/tests/test_bo_framework.py`
  - [ ] 测试 CRUD 操作
  - [ ] 测试事务控制
  - [ ] 测试审计日志

---

## Phase 2: AI 代码生成 (Week 4-5)

### 2.1 代码生成基础设施

- [ ] Task 14: 创建代码生成框架
  - [ ] 创建 `meta/generators/__init__.py`
  - [ ] 创建 `meta/generators/base_generator.py`
  - [ ] 基于 Jinja2 模板引擎

- [ ] Task 15: 实现 API 代码生成器
  - [ ] 创建 `meta/generators/api_generator.py`
  - [ ] 生成 CRUD API 端点
  - [ ] 生成业务动作 API

- [ ] Task 16: 实现 Service 代码生成器
  - [ ] 创建 `meta/generators/service_generator.py`
  - [ ] 生成强类型 Service 类
  - [ ] 生成 DTO 类

- [ ] Task 17: 实现测试代码生成器
  - [ ] 创建 `meta/generators/test_generator.py`
  - [ ] 生成单元测试
  - [ ] 生成集成测试

### 2.2 AI 生成配置

- [ ] Task 18: 扩展元模型支持 AI 生成配置
  - [ ] 在 `MetaObject` 添加 `ai_generation` 字段
  - [ ] 支持自定义模板配置

### 2.3 代码生成 CLI

- [ ] Task 19: 创建代码生成 CLI
  - [ ] 创建 `meta/cli/generate.py`
  - [ ] 支持 `python -m meta generate api purchase_order`
  - [ ] 支持 `python -m meta generate all purchase_order`

---

## Phase 3: 动态 UI (Week 6-7)

### 3.1 UI Schema 解析

- [ ] Task 20: 扩展元模型支持 UI 配置
  - [ ] 在 `MetaObject` 添加 `ui_view_config` 字段
  - [ ] 支持列表、表单、详情页配置

- [ ] Task 21: 创建 UI Schema 解析器
  - [ ] 创建 `meta/ui/schema_parser.py`
  - [ ] 解析 YAML UI 配置
  - [ ] 转换为前端组件配置

### 3.2 动态组件

- [ ] Task 22: 创建动态列表组件
  - [ ] 创建 `src/components/DynamicList.vue`
  - [ ] 支持列配置、筛选、排序、分页
  - [ ] 支持响应式布局

- [ ] Task 23: 创建动态表单组件
  - [ ] 创建 `src/components/DynamicForm.vue`
  - [ ] 支持字段验证、联动
  - [ ] 支持分组、标签页

- [ ] Task 24: 创建动态详情组件
  - [ ] 创建 `src/components/DynamicDetail.vue`
  - [ ] 支持字段布局
  - [ ] 支持关联数据展示

### 3.3 UI 生成 API

- [ ] Task 25: 创建 UI Schema API
  - [ ] 创建 `meta/api/ui_schema_api.py`
  - [ ] 提供 `GET /api/v1/ui/schema/{object_type}` 端点
  - [ ] 返回前端可用的 UI 配置

---

## Phase 4: 工作流集成 (Week 8-9)

### 4.1 工作流引擎

- [ ] Task 26: 创建工作流引擎
  - [ ] 创建 `meta/workflow/engine.py`
  - [ ] 实现状态机
  - [ ] 支持状态转换规则

- [ ] Task 27: 实现 WorkflowInterceptor
  - [ ] 创建 `meta/core/interceptors/workflow_interceptor.py`
  - [ ] 触发工作流
  - [ ] 处理状态转换

### 4.2 审批流程

- [ ] Task 28: 实现审批流程
  - [ ] 创建 `meta/workflow/approval_flow.py`
  - [ ] 支持多级审批
  - [ ] 支持会签、或签

- [ ] Task 29: 实现通知服务
  - [ ] 创建 `meta/services/notification_service.py`
  - [ ] 支持邮件通知
  - [ ] 支持站内消息

### 4.3 工作流配置

- [ ] Task 30: 扩展元模型支持工作流配置
  - [ ] 在 `MetaObject` 添加 `workflow` 字段
  - [ ] 支持状态定义、转换规则

---

## Phase 5: 业务规则引擎 (Week 10-11)

### 5.1 规则引擎

- [ ] Task 31: 创建规则引擎
  - [ ] 创建 `meta/rules/engine.py`
  - [ ] 支持规则表达式解析
  - [ ] 支持规则执行

- [ ] Task 32: 实现 BusinessRuleInterceptor
  - [ ] 创建 `meta/core/interceptors/business_rule_interceptor.py`
  - [ ] 执行业务规则
  - [ ] 处理规则异常

### 5.2 规则类型

- [ ] Task 33: 实现验证规则
  - [ ] 支持跨字段验证
  - [ ] 支持跨对象验证

- [ ] Task 34: 实现计算规则
  - [ ] 支持字段自动计算
  - [ ] 支持聚合计算

### 5.3 规则配置

- [ ] Task 35: 扩展元模型支持业务规则配置
  - [ ] 在 `MetaObject` 添加 `business_rules` 字段
  - [ ] 支持规则定义、触发条件

---

## Phase 6: 其他拦截器 (Week 12)

### 6.1 ContextInterceptor

- [ ] Task 36: 实现 ContextInterceptor
  - [ ] 创建 `meta/core/interceptors/context_interceptor.py`
  - [ ] 设置用户上下文
  - [ ] 设置 Trace ID

### 6.2 PermissionInterceptor

- [ ] Task 37: 实现 PermissionInterceptor
  - [ ] 创建 `meta/core/interceptors/permission_interceptor.py`
  - [ ] 检查权限
  - [ ] 支持数据级权限

### 6.3 ValidationInterceptor

- [ ] Task 38: 实现 ValidationInterceptor
  - [ ] 创建 `meta/core/interceptors/validation_interceptor.py`
  - [ ] 执行字段验证
  - [ ] 支持自定义验证器

### 6.4 DeterminationInterceptor

- [ ] Task 39: 实现 DeterminationInterceptor
  - [ ] 创建 `meta/core/interceptors/determination_interceptor.py`
  - [ ] 执行字段自动计算
  - [ ] 支持 `updated_at` 自动填充

---

# Task Dependencies

```
Phase 1:
  Task 2 depends on Task 1
  Task 3 depends on Task 1, Task 2
  Task 4, Task 5 depend on Task 3
  Task 6 independent
  Task 7 depends on Task 1, Task 2, Task 6
  Task 8 depends on Task 6
  Task 9 depends on Task 3
  Task 10, Task 11, Task 12 depend on Task 3, Task 7, Task 8
  Task 13 depends on Task 10, Task 11, Task 12

Phase 2:
  Task 14, Task 15, Task 16, Task 17 depend on Task 3
  Task 18 depends on Task 6
  Task 19 depends on Task 14, Task 15, Task 16, Task 17

Phase 3:
  Task 20 depends on Task 6
  Task 21 depends on Task 20
  Task 22, Task 23, Task 24 depend on Task 21
  Task 25 depends on Task 21

Phase 4:
  Task 26 independent
  Task 27 depends on Task 3, Task 26
  Task 28 depends on Task 26
  Task 29 independent
  Task 30 depends on Task 6

Phase 5:
  Task 31 independent
  Task 32 depends on Task 3, Task 31
  Task 33, Task 34 depend on Task 31
  Task 35 depends on Task 6

Phase 6:
  Task 36, Task 37, Task 38, Task 39 depend on Task 3
```

# Parallelizable Work

- Task 10, Task 11, Task 12（API 迁移）
- Task 15, Task 16, Task 17（代码生成器）
- Task 22, Task 23, Task 24（动态组件）
- Task 36, Task 37, Task 38, Task 39（其他拦截器）

# Implementation Progress

```
Phase 1: 核心框架           ░░░░░░░░░░░░░░░░░░░░░   0% ⏳
Phase 2: AI 代码生成        ░░░░░░░░░░░░░░░░░░░░░   0% ⏳
Phase 3: 动态 UI            ░░░░░░░░░░░░░░░░░░░░░   0% ⏳
Phase 4: 工作流集成         ░░░░░░░░░░░░░░░░░░░░░   0% ⏳
Phase 5: 业务规则引擎       ░░░░░░░░░░░░░░░░░░░░░   0% ⏳
Phase 6: 其他拦截器         ░░░░░░░░░░░░░░░░░░░░░   0% ⏳
```

**总进度：0%**
