# Tasks: 事务系统完备性改造

## Phase 1: 事务基础设施修复

### Task 1.1: 修改 SQLiteAdapter 事务核心实现
- **File**: `meta/core/sql_adapters.py`
- **Changes**:
  - [ ] 添加 `_in_transaction` 和 `_savepoint_counter` 属性
  - [ ] 实现 `begin_transaction()` — 执行 `BEGIN` 语句
  - [ ] 修改 `commit()` — 仅事务内时提交并重置状态
  - [ ] 修改 `rollback()` — 仅事务内时回滚并重置状态
  - [ ] 添加 `in_transaction` 只读属性
  - [ ] 添加 `set_savepoint(name)` 方法
  - [ ] 添加 `rollback_to(savepoint_name)` 方法
  - [ ] 添加 `release_savepoint(savepoint_name)` 方法
  - [ ] 在 `connect()` 中添加 `PRAGMA foreign_keys = ON`
  - [ ] 在 `connect()` 中初始化 `_in_transaction = False`

### Task 1.2: 修改 SQLDataSource 条件化 commit
- **File**: `meta/core/sql_adapters.py`
- **Changes**:
  - [ ] `insert()` — 添加 `if not self.in_transaction` 条件
  - [ ] `update()` — 添加 `if not self.in_transaction` 条件
  - [ ] `delete()` — 添加 `if not self.in_transaction` 条件
  - [ ] `batch_insert()` — 添加 `if not self.in_transaction` 条件
  - [ ] `create_index()` — 添加 `if not self.in_transaction` 条件

### Task 1.3: 修改 DataSource 抽象接口
- **File**: `meta/core/datasource.py`
- **Changes**:
  - [ ] 添加 `in_transaction` 抽象属性
  - [ ] 添加 `set_savepoint()` 抽象方法
  - [ ] 添加 `rollback_to()` 抽象方法
  - [ ] 添加 `release_savepoint()` 抽象方法
  - [ ] 验证 `transaction()` 上下文管理器异常回滚逻辑

### Task 1.4: 创建异常类
- **File**: `meta/core/exceptions.py` (新建)
- **Changes**:
  - [ ] 定义 `ConcurrentModificationError` 异常

### Task 1.5: 编写 Phase 1 单元测试
- **File**: `meta/tests/test_transaction_basic.py` (新建)
- **Test Cases**:
  - [ ] test_begin_transaction_enters_explicit_mode
  - [ ] test_commit_exits_transaction
  - [ ] test_rollback_exits_transaction
  - [ ] test_insert_no_auto_commit_in_transaction
  - [ ] test_insert_auto_commit_outside_transaction
  - [ ] test_update_no_auto_commit_in_transaction
  - [ ] test_delete_no_auto_commit_in_transaction
  - [ ] test_transaction_context_manager_commit
  - [ ] test_transaction_context_manager_rollback_on_exception
  - [ ] test_savepoint_create_and_rollback
  - [ ] test_savepoint_nested
  - [ ] test_foreign_keys_enabled
  - [ ] test_in_transaction_property

## Phase 2: 关键场景事务包裹

### Task 2.1: ActionExecutor 事务包裹
- **File**: `meta/core/action_executor.py`
- **Changes**:
  - [ ] `_do_create` — 包裹 `with self.ds.transaction()`
  - [ ] `_do_create` — 移除事务内的审计日志写入
  - [ ] `_do_create` — 添加 V2 审计日志写入（事务后）
  - [ ] `_do_update` — 包裹 `with self.ds.transaction()`
  - [ ] `_do_update` — 添加 V2 审计日志写入
  - [ ] `_do_delete` — 包裹 `with self.ds.transaction()`
  - [ ] `_do_delete` — 添加 V2 审计日志写入
  - [ ] 添加 `_write_audit_log_async()` 方法

### Task 2.2: CascadeService 统一事务
- **File**: `meta/services/cascade_service.py`
- **Changes**:
  - [ ] `execute_cascade` — 包裹 `with self.ds.transaction()`
  - [ ] 移除所有 `self.ds.commit()` 调用

### Task 2.3: user_api 事务修复
- **File**: `meta/api/user_api.py`
- **Changes**:
  - [ ] `create_user` — 包裹事务，消除裸 commit
  - [ ] `delete_user` — 包裹事务，消除裸 commit
  - [ ] `update_user` — 消除裸 commit
  - [ ] `reset_password` — 消除裸 commit

### Task 2.4: role_api 事务修复
- **File**: `meta/api/role_api.py`
- **Changes**:
  - [ ] `create_role` — 包裹事务
  - [ ] `delete_role` — 包裹事务
  - [ ] `update_role` — 消除裸 commit
  - [ ] `assign_permissions` — 消除裸 commit

### Task 2.5: 其他 API 事务修复
- **File**: `meta/api/enum_api.py`, `meta/api/schema_api.py`, `meta/api/manage_api.py`
- **Changes**:
  - [ ] `enum_api.py` — 消除裸 commit
  - [ ] `schema_api.py` — 消除裸 commit
  - [ ] `manage_api.py` — `delete_annotations_by_target` 包裹事务

### Task 2.6: 导入操作事务保护
- **File**: `meta/services/import_export_service.py`
- **Changes**:
  - [ ] `import_cascade` — 包裹事务
  - [ ] 异步导入线程 — 使用独立事务
  - [ ] 移除导入过程中的裸 commit

### Task 2.7: 编写 Phase 2 集成测试
- **File**: `meta/tests/test_transaction_integration.py` (新建)
- **Test Cases**:
  - [ ] test_create_rollback_on_hierarchy_path_failure
  - [ ] test_update_rollback_on_rule_failure
  - [ ] test_delete_rollback_on_rule_failure
  - [ ] test_cascade_delete_atomicity
  - [ ] test_cascade_delete_rollback_on_failure
  - [ ] test_user_create_with_roles_atomicity
  - [ ] test_user_delete_with_cleanup_atomicity
  - [ ] test_import_atomicity
  - [ ] test_audit_log_v2_writes_after_commit
  - [ ] test_audit_log_v2_failure_does_not_affect_business

## Phase 3: 高级事务能力

### Task 3.1: 乐观锁 version 字段
- **Files**: `meta/core/models.py`, `meta/core/sql_adapters.py`, `meta/core/action_executor.py`
- **Changes**:
  - [ ] `models.py` — MetaObject.get_persistent_fields() 自动追加 version
  - [ ] `sql_adapters.py` — 添加 `update_with_version()` 方法
  - [ ] `action_executor.py` — `_do_update` 支持 version 检查
  - [ ] 数据库迁移 — ALTER TABLE ADD COLUMN version INTEGER DEFAULT 1

### Task 3.2: allOrNone 批量操作模式
- **File**: `meta/services/manage_service.py`
- **Changes**:
  - [ ] `batch_create` — 添加 `all_or_none` 参数
  - [ ] `batch_update` — 添加 `all_or_none` 参数
  - [ ] `batch_delete` — 添加 `all_or_none` 参数
  - [ ] all_or_none=False 时每条记录独立事务

### Task 3.3: WAL checkpoint 管理
- **File**: `meta/core/sql_adapters.py`
- **Changes**:
  - [ ] 添加 `checkpoint()` 方法
  - [ ] 在 commit 后定期执行 checkpoint

### Task 3.4: 编写 Phase 3 测试
- **File**: `meta/tests/test_transaction_advanced.py` (新建)
- **Test Cases**:
  - [ ] test_optimistic_lock_success
  - [ ] test_optimistic_lock_conflict
  - [ ] test_optimistic_lock_no_version_backward_compat
  - [ ] test_batch_create_all_or_none_true
  - [ ] test_batch_create_all_or_none_false
  - [ ] test_wal_checkpoint

## Phase 4: Agentic AI 事务能力

### Task 4.1: Operation Journal 数据模型与服务
- **Files**: `meta/schemas/operation_journal.yaml` (新建), `meta/services/operation_journal_service.py` (新建)
- **Changes**:
  - [ ] 创建 operation_journal.yaml 元模型定义
  - [ ] 创建 operation_journals 表（含索引）
  - [ ] 实现 OperationJournalService:
    - [ ] record() — 记录操作日志
    - [ ] find_by_idempotency_key() — 幂等键查询
    - [ ] find_by_tool_call_id() — tool_call 查询
    - [ ] find_by_agent_session() — Agent 会话查询
    - [ ] mark_compensated() — 标记补偿完成
    - [ ] cleanup_expired() — 清理过期记录

### Task 4.2: Agent Context 中间件
- **File**: `meta/server.py`
- **Changes**:
  - [ ] before_request 提取 X-Agent-Id 请求头
  - [ ] before_request 提取 X-Agent-Session-Id 请求头
  - [ ] before_request 提取 X-Tool-Call-Id 请求头
  - [ ] before_request 提取 X-Agent-Reasoning 请求头
  - [ ] before_request 提取 X-Idempotency-Key 请求头
  - [ ] g 对象存储 agent context
  - [ ] 日志格式增加 agent_id 前缀

### Task 4.3: ActionExecutor 集成 Operation Journal
- **File**: `meta/core/action_executor.py`
- **Changes**:
  - [ ] _do_create 记录补偿操作 (compensation: delete)
  - [ ] _do_update 记录补偿操作 (compensation: update with old data)
  - [ ] _do_delete 记录补偿操作 (compensation: create with deleted data)
  - [ ] 补偿操作定义写入 Operation Journal
  - [ ] 人类操作时 agent_id 为空

### Task 4.4: AgentWorkflow 编排器
- **File**: `meta/services/agent_workflow.py` (新建)
- **Changes**:
  - [ ] AgentWorkflow 类实现
  - [ ] execute_step() — 执行单步 + 记录补偿
  - [ ] _compensate() — 逆序执行补偿链
  - [ ] _build_compensation() — 自动构建补偿操作
  - [ ] _execute_compensation() — 执行单个补偿操作
  - [ ] 补偿失败时记录错误日志

### Task 4.5: 幂等性服务
- **File**: `meta/services/idempotency_service.py` (新建)
- **Changes**:
  - [ ] IdempotencyService 类实现
  - [ ] check_and_execute() — 幂等键去重
  - [ ] manage_api 中集成幂等检查
  - [ ] 幂等键 TTL 管理（默认24小时）

### Task 4.6: Agent API 执行端点
- **File**: `meta/api/agent_api.py`
- **Changes**:
  - [ ] 新增 POST /api/v1/agent/execute 端点
  - [ ] 接收 tool_call_id, operation, params
  - [ ] 集成 IdempotencyService
  - [ ] 集成 AgentWorkflow
  - [ ] 返回结构化执行结果

### Task 4.7: 编写 Phase 4 测试
- **File**: `meta/tests/test_agent_transaction.py` (新建)
- **Test Cases**:
  - [ ] test_operation_journal_record
  - [ ] test_operation_journal_compensation_record
  - [ ] test_agent_context_extraction
  - [ ] test_idempotency_duplicate_request
  - [ ] test_idempotency_first_request
  - [ ] test_saga_compensation_on_failure
  - [ ] test_saga_multi_step_success
  - [ ] test_saga_compensation_partial_failure
  - [ ] test_human_operation_no_agent_context
