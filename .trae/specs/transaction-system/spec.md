# Spec: 事务系统完备性改造

## 1. Background & Objectives

### 1.1 Background

当前项目的事务系统存在系统性缺陷：虽然设计了完整的事务抽象接口（`DataSource.transaction()`），但底层实现完全失效——`begin_transaction()` 为空操作（`pass`），所有写操作（insert/update/delete）自动 commit，导致事务上下文管理器无法保证原子性。级联删除、批量操作、多步创建等场景都面临数据不一致的风险。

具体问题清单：
- `SQLiteAdapter.begin_transaction()` 空实现，事务上下文管理器形同虚设
- `SQLDataSource` 的 insert/update/delete 每次调用都自动 `self.commit()`
- `ActionExecutor._do_create` 中 insert + hierarchy_path 更新 + 审计日志分多次 commit
- `CascadeService.execute_cascade` 每步操作独立 commit
- `user_api/role_api` 中裸调用 `ds.commit()`，无事务包裹
- 导入操作无事务保护，部分成功部分失败时数据不一致
- 无并发控制机制（乐观锁/悲观锁），并发更新存在丢失更新风险
- `SQLiteAdapter` 未启用 `PRAGMA foreign_keys = ON`，外键约束不生效

### 1.2 Business Objectives

- 确保所有 CRUD 操作的数据一致性：任何步骤失败可完整回滚
- 确保级联删除的原子性：要么全部删除，要么全部不删
- 确保批量操作的原子性：全有全无
- 确保并发更新的正确性：防止丢失更新
- 参照 SAP LUW / Salesforce 事务模型的企业级最佳实践
- **支持 Agentic AI 原生场景**：AI Agent 的多步 workflow 需要补偿机制、幂等性保障和推理链追踪

### 1.3 User / Stakeholder (涉众) Objectives

- **后端开发者**：事务 API 简单易用，不需要手动管理 commit/rollback
- **运维人员**：数据一致性有保障，故障恢复可预期
- **最终用户**：操作不会产生半完成状态的数据
- **AI Agent**：多步 workflow 失败时自动补偿，重复调用幂等安全，操作可追溯推理链

## 2. Requirement Type Overview

| Type | Applicable | Evidence |
|------|-----------|----------|
| Business | Yes | 数据一致性是企业应用的基本要求 |
| User/Stakeholder | Yes | 开发者需要可靠的事务API；AI Agent需要补偿和幂等 |
| Solution | Yes | 需要修复事务基础设施 + Agentic AI 事务扩展 |
| Functional | Yes | 事务管理、乐观锁、审计日志分离、Saga补偿、幂等 |
| Nonfunctional | Yes | 性能（锁粒度）、可靠性（回滚保证）、AI Agent并发 |
| External Interface | Yes | Agent API 需要扩展 tool_call 执行端点 |
| Transition | Yes | 数据库迁移（version字段）、代码兼容、Agent API升级 |

## 3. Functional Requirements

### FR-001: 实现 begin_transaction 显式事务开始

- **Description**: SQLiteAdapter 的 `begin_transaction()` 必须执行 `BEGIN` 语句，进入显式事务模式
- **Acceptance Criteria**:
  - 调用 `begin_transaction()` 后，SQLite 进入显式事务模式
  - 事务内的 insert/update/delete 不自动 commit
  - 调用 `commit()` 后事务提交，退出事务模式
  - 调用 `rollback()` 后事务回滚，退出事务模式
- **Priority**: Must
- **Type Mapping**: Solution/Functional
- **Source**: 代码分析 - sql_adapters.py:282-284

### FR-002: 消除写操作自动 commit

- **Description**: `SQLDataSource` 的 insert/update/delete 方法在事务内时不得自动 commit，仅在非事务模式下保持自动 commit 兼容
- **Acceptance Criteria**:
  - 新增 `_in_transaction` 状态标记
  - 事务内调用 insert/update/delete 不触发 commit
  - 非事务模式下调用 insert/update/delete 仍自动 commit（向后兼容）
  - `transaction()` 上下文管理器正确设置/清除事务状态
- **Priority**: Must
- **Type Mapping**: Solution/Functional
- **Source**: 代码分析 - sql_adapters.py:171-258

### FR-003: ActionExecutor CRUD 操作事务包裹

- **Description**: `_do_create/_do_update/_do_delete` 的核心数据库操作必须包裹在 `transaction()` 上下文管理器中
- **Acceptance Criteria**:
  - `_do_create`: insert + hierarchy_path 更新在同一事务中
  - `_do_update`: update 操作在同一事务中
  - `_do_delete`: delete 操作在同一事务中
  - 任何步骤失败，整个操作回滚
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 代码分析 - action_executor.py:603-935

### FR-004: CascadeService 级联操作统一事务

- **Description**: `execute_cascade` 中所有 set_null/set_default/delete 操作必须在同一事务中
- **Acceptance Criteria**:
  - 所有 set_null 操作在同一事务中
  - 所有 set_default 操作在同一事务中
  - 所有 delete 操作（子记录+父记录）在同一事务中
  - 任何步骤失败，整个级联操作回滚
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 代码分析 - cascade_service.py:338-422

### FR-005: API 层裸 commit 改为事务模式

- **Description**: user_api/role_api/enum_api 等中的裸 `ds.commit()` 调用改为事务包裹
- **Acceptance Criteria**:
  - `user_api.create_user`: 用户创建+角色分配在同一事务中
  - `user_api.delete_user`: 用户删除+角色/权限清理在同一事务中
  - `role_api.create_role`: 角色创建+权限分配在同一事务中
  - `role_api.delete_role`: 角色删除+权限清理在同一事务中
  - 其他裸 commit 调用全部消除
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 代码分析 - user_api.py:130-171, role_api.py

### FR-006: 导入操作事务保护

- **Description**: 数据导入过程必须在事务保护下执行，失败时完整回滚
- **Acceptance Criteria**:
  - 同步导入：所有对象类型的导入在同一事务中
  - 异步导入：每个导入任务使用独立事务
  - 导入失败时，已导入数据完整回滚
  - 导入任务状态正确更新
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 代码分析 - export_import_api.py:240-308

### FR-007: 审计日志 V2 异步写入

- **Description**: 参考 SAP V2 Update 模式，审计日志在业务事务提交后独立写入
- **Acceptance Criteria**:
  - 业务操作（insert/update/delete）在主事务中执行
  - 主事务提交后，审计日志在独立 mini 事务中写入
  - 审计日志写入失败不影响业务结果
  - 审计日志写入失败时记录 warning 级别日志
- **Priority**: Must
- **Type Mapping**: Functional/Business
- **Source**: SAP V2 Update 最佳实践

### FR-008: 启用外键约束

- **Description**: SQLiteAdapter 连接时必须启用 `PRAGMA foreign_keys = ON`
- **Acceptance Criteria**:
  - 所有新连接默认启用外键约束
  - 违反外键约束的操作抛出异常
- **Priority**: Must
- **Type Mapping**: Solution
- **Source**: 代码分析 - sql_adapters.py:312-326

### FR-009: Savepoint 支持

- **Description**: 参考 Salesforce Database.setSavepoint()，实现事务内保存点
- **Acceptance Criteria**:
  - `set_savepoint(name)` 创建保存点
  - `rollback_to(name)` 回滚到指定保存点
  - `release_savepoint(name)` 释放保存点
  - 保存点可在事务内嵌套使用
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: Salesforce Savepoint 最佳实践

### FR-010: 乐观锁（version 字段）

- **Description**: 参考 SAP ENQUEUE 机制的思想，使用 version 字段实现乐观锁
- **Acceptance Criteria**:
  - 所有持久化对象自动包含 version 字段（默认值1）
  - 更新操作检查 version 是否匹配
  - version 不匹配时抛出 ConcurrentModificationError
  - 前端编辑表单携带当前 version 值
  - 数据库迁移：现有数据 version 默认为1
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: SAP ENQUEUE / Salesforce 版本号机制

### FR-011: 批量操作 allOrNone 模式

- **Description**: 参考 Salesforce allOrNone 参数，为批量操作提供两种模式
- **Acceptance Criteria**:
  - `all_or_none=True`（默认）：任一失败则全部回滚
  - `all_or_none=False`：单条失败不影响其他，返回每条结果
  - BatchOperationResult 包含每条记录的成功/失败状态
- **Priority**: Could
- **Type Mapping**: Functional
- **Source**: Salesforce Database.insert(records, allOrNone) 最佳实践

### FR-012: Operation Journal（操作日志 — Agentic AI 增强）

- **Description**: 在现有 audit_log 基础上，扩展为 Operation Journal，记录 AI Agent 的完整操作上下文，包括 agent_id、session_id、tool_call_id、推理链和补偿操作定义
- **Acceptance Criteria**:
  - operation_journals 表包含：operation_id, agent_id, agent_session_id, tool_call_id, reasoning, compensation_ops, idempotency_key 等字段
  - 每个写操作自动记录补偿操作定义（逆操作）
  - AI Agent 请求通过 X-Agent-Id / X-Agent-Session-Id / X-Tool-Call-Id 请求头传递上下文
  - 人类操作时 agent_id 为空，不影响现有行为
- **Priority**: Should
- **Type Mapping**: Functional/Business
- **Source**: ESAA (Event Sourcing for Autonomous Agents) 模式; Microsoft Ignite 2025 AI Agent 审计日志最佳实践

### FR-013: Saga 补偿模式（AI Agent Workflow 回滚）

- **Description**: 为 AI Agent 的多步 workflow 提供自动补偿机制。当 workflow 中某步失败时，自动执行已完成步骤的补偿操作
- **Acceptance Criteria**:
  - 新增 AgentWorkflow 编排器，管理多步 workflow 的执行
  - 每步执行成功后记录补偿操作到 Operation Journal
  - 某步失败时，自动逆序执行补偿操作
  - 补偿操作本身也有日志记录
  - 支持人工审批节点（Human-in-the-loop）暂停 workflow
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: Saga Pattern for AI Workflow Orchestration; Transactional AI v0.2

### FR-014: 幂等性保障（Idempotency）

- **Description**: AI Agent 可能因网络超时、LLM 重新生成等原因重复调用同一个 tool_call，系统需要保证幂等性
- **Acceptance Criteria**:
  - 每个 Agent 请求携带 X-Idempotency-Key 请求头（通常为 tool_call_id）
  - 服务端检查 idempotency_key 是否已处理
  - 已处理的请求直接返回之前的结果
  - 幂等键存储在 operation_journals 表中
  - 幂等键默认 TTL 为 24 小时
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: OpenAI Function Calling tool_call_id; Stripe Idempotency Key 模式

### FR-015: Agent Context Propagation（推理链追踪）

- **Description**: AI Agent 的每个操作都应携带 Agent 上下文，用于溯源和调试
- **Acceptance Criteria**:
  - 请求头支持：X-Agent-Id, X-Agent-Session-Id, X-Tool-Call-Id, X-Agent-Reasoning, X-Idempotency-Key
  - Flask before_request 中间件提取 Agent 上下文到 g 对象
  - Operation Journal 自动记录 Agent 上下文
  - ActionExecutor 的审计日志包含 agent_id 和 tool_call_id
  - 日志输出包含 agent_id 前缀，便于按 Agent 过滤
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: Microsoft Ignite 2025 Enterprise AI Agent 架构

## 4. Nonfunctional Requirements

### NFR-001: 事务性能

- **Description**: 事务引入不应显著降低系统性能
- **Measurement**: 单条 CRUD 操作响应时间增加 < 5ms；批量操作（100条）响应时间增加 < 50ms
- **Priority**: Must
- **Source**: 性能基线

### NFR-002: 事务隔离

- **Description**: SQLite WAL 模式下的事务隔离级别应保持一致
- **Measurement**: 并发读写不产生脏读；WAL 文件大小可控（定期 checkpoint）
- **Priority**: Should
- **Source**: SQLite WAL 文档

### NFR-003: 向后兼容

- **Description**: 事务改造不应破坏现有非事务模式的代码
- **Measurement**: 现有测试全部通过；非事务模式（直接调用 insert/update/delete）行为不变
- **Priority**: Must
- **Source**: 代码兼容性

### NFR-004: WAL 文件管理

- **Description**: 定期执行 WAL checkpoint，防止 WAL 文件无限增长
- **Measurement**: WAL 文件大小 < 100MB
- **Priority**: Should
- **Source**: SQLite 运维最佳实践

## 5. External Interface Requirements

### IF-001: DataSource 事务 API

- **Type**: API
- **Endpoint**: Python 内部 API
- **Request/Response**:
  ```python
  # 现有接口（不变）
  ds.transaction()           # 事务上下文管理器
  ds.begin_transaction()     # 开始事务
  ds.commit()                # 提交事务
  ds.rollback()              # 回滚事务

  # 新增接口
  ds.set_savepoint(name)     # 设置保存点 → 返回保存点名称
  ds.rollback_to(name)       # 回滚到保存点
  ds.release_savepoint(name) # 释放保存点

  # 新增属性
  ds.in_transaction          # 是否在事务中（只读属性）
  ```
- **Error Handling**:
  - 事务内操作失败自动回滚
  - 保存点不存在时抛出 ValueError
  - 非事务模式下调用 rollback_to 抛出 RuntimeError
- **Source**: 设计分析

### IF-002: ActionExecutor 乐观锁 API

- **Type**: API
- **Endpoint**: Python 内部 API
- **Request/Response**:
  ```python
  # 更新时传入 version
  result = executor.execute(meta_obj, "crud_update", {
      "id": 1,
      "name": "新名称",
      "version": 3          # 前端传入当前版本号
  })

  # 并发冲突时返回
  result.success == False
  result.error == "CONCURRENT_MODIFICATION"
  result.message == "记录已被其他用户修改，请刷新后重试"
  ```
- **Error Handling**:
  - version 不匹配 → ActionResult.fail(error="CONCURRENT_MODIFICATION")
  - 未传 version → 不做乐观锁检查（向后兼容）
- **Source**: 设计分析

## 6. Transition Requirements

### TR-001: 数据库迁移 - version 字段

- **Description**: 为所有持久化表添加 version 列
- **Strategy**:
  1. 使用 `sync_schema --diff` 检查变更
  2. 执行 `ALTER TABLE xxx ADD COLUMN version INTEGER DEFAULT 1`
  3. 现有数据 version 自动为1
  4. 不需要数据回填
- **Rollback Plan**: version 列可以保留不影响功能，无需回滚
- **Source**: 迁移分析

### TR-002: 代码兼容性迁移

- **Description**: 现有裸 `ds.commit()` 调用需逐步替换为事务模式
- **Strategy**:
  1. Phase 1: 修复基础设施，保持自动 commit 兼容
  2. Phase 2: 逐个 API 改为事务模式
  3. 每改一个 API 运行对应测试
- **Rollback Plan**: `_in_transaction` 标记确保非事务模式行为不变
- **Source**: 兼容性分析

## 7. Constraints & Assumptions

### 7.1 Technical Constraints

- SQLite 单连接 + 全局锁架构，长事务会阻塞所有操作
- SQLite 不支持嵌套事务（但支持 SAVEPOINT）
- WAL 模式允许读写并发，但写写仍串行
- Python sqlite3 模块的 autocommit 行为需要显式控制

### 7.2 Business Constraints

- 审计日志不能阻塞业务操作
- 并发冲突提示需要用户友好
- 批量导入需要支持大量数据（1000+行）

### 7.3 Assumptions

- 项目当前为单实例部署，不需要分布式事务 – Source: Assumed
- SQLite 的性能瓶颈在可接受范围内 – Source: Assumed
- 前端可以在编辑表单中携带 version 字段 – Source: Assumed

## 8. Priorities & Milestone Suggestions

| ID | Requirement | Priority | Reason |
|----|------------|----------|--------|
| FR-001 | begin_transaction 实现 | Must | 事务系统根基 |
| FR-002 | 消除自动 commit | Must | 事务生效前提 |
| FR-003 | ActionExecutor 事务包裹 | Must | 核心CRUD一致性 |
| FR-004 | CascadeService 统一事务 | Must | 级联删除一致性 |
| FR-005 | API 层裸 commit 修复 | Must | 用户/角色操作一致性 |
| FR-006 | 导入操作事务保护 | Must | 导入数据一致性 |
| FR-007 | 审计日志 V2 异步 | Must | SAP最佳实践 |
| FR-008 | 启用外键约束 | Must | 数据完整性 |
| FR-009 | Savepoint 支持 | Should | 部分回滚能力 |
| FR-010 | 乐观锁 | Should | 并发控制 |
| FR-011 | allOrNone 模式 | Could | 高级批量能力 |
| FR-012 | Operation Journal | Should | Agentic AI 操作溯源 |
| FR-013 | Saga 补偿模式 | Should | Agentic AI workflow 回滚 |
| FR-014 | 幂等性保障 | Should | Agentic AI 重试安全 |
| FR-015 | Agent Context Propagation | Should | Agentic AI 推理链追踪 |

- Suggested Milestones:
  - **Milestone 1 (Phase 1)**: FR-001, FR-002, FR-008 — 事务基础设施修复
  - **Milestone 2 (Phase 2)**: FR-003, FR-004, FR-005, FR-006, FR-007 — 关键场景事务包裹
  - **Milestone 3 (Phase 3)**: FR-009, FR-010, FR-011 — 高级事务能力
  - **Milestone 4 (Phase 4)**: FR-012, FR-013, FR-014, FR-015 — Agentic AI 事务能力

## 9. Change / Design Proposal (RFC)

### 9.1 As-Is Analysis

- **Current Architecture**: DataSource 抽象层 + SQLiteAdapter 实现 + ActionExecutor 业务层
- **Current Issues**:
  1. `begin_transaction()` 空实现（sql_adapters.py:282-284）
  2. 所有写操作自动 commit（sql_adapters.py:171-258）
  3. ActionExecutor CRUD 无事务保护（action_executor.py:603-935）
  4. CascadeService 每步独立 commit（cascade_service.py:338-422）
  5. API 层裸 commit（user_api.py:158,165 等）
  6. 无并发控制
  7. 外键约束未启用
- **Relevant Code Paths**:
  - `meta/core/datasource.py` — DataSource 抽象接口
  - `meta/core/sql_adapters.py` — SQLiteAdapter 实现
  - `meta/core/action_executor.py` — ActionExecutor CRUD 操作
  - `meta/services/manage_service.py` — ManageService 批量操作
  - `meta/services/cascade_service.py` — CascadeService 级联操作
  - `meta/api/user_api.py, role_api.py, enum_api.py` — API 层裸 commit
  - `meta/api/export_import_api.py` — 导入操作

### 9.2 Target State

- **Proposed Architecture**: 三层事务模型
  - 第1层：操作级事务（Operation Transaction）— ActionExecutor/Service 层使用 `transaction()` 上下文管理器
  - 第2层：Savepoint（精确回滚点）— 批量操作中部分回滚
  - 第3层：乐观锁（并发控制）— version 字段防止丢失更新

- **Key Changes**:
  1. `begin_transaction()` 执行 `BEGIN` 语句
  2. 写操作条件化 commit（事务内不 commit，事务外自动 commit）
  3. ActionExecutor CRUD 包裹 `transaction()`
  4. CascadeService 统一事务
  5. API 层裸 commit 改为事务模式
  6. 审计日志 V2 异步写入
  7. 全量添加 version 字段
  8. Savepoint 支持

### 9.3 Detailed Design

#### 9.3.1 SQLiteAdapter 事务状态管理

```python
class SQLiteAdapter(SQLDataSource):
    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
        self._in_transaction = False
        self._savepoint_counter = 0

    def connect(self, **kwargs) -> bool:
        # ... 现有连接代码 ...
        self._in_transaction = False
        self._savepoint_counter = 0
        # 新增：启用外键约束
        if db_path != ":memory:":
            self._cursor.execute("PRAGMA journal_mode=WAL")
            self._cursor.execute("PRAGMA synchronous=NORMAL")
            self._cursor.execute("PRAGMA foreign_keys = ON")

    @property
    def in_transaction(self) -> bool:
        return self._in_transaction

    def begin_transaction(self) -> None:
        with self._lock:
            if self._connection and not self._in_transaction:
                self._connection.execute("BEGIN")
                self._in_transaction = True

    def commit(self) -> None:
        with self._lock:
            if self._connection and self._in_transaction:
                self._connection.commit()
                self._in_transaction = False

    def rollback(self) -> None:
        with self._lock:
            if self._connection and self._in_transaction:
                self._connection.rollback()
                self._in_transaction = False

    def set_savepoint(self, name: str = None) -> str:
        with self._lock:
            if not self._in_transaction:
                self.begin_transaction()
            self._savepoint_counter += 1
            sp_name = name or f"sp_{self._savepoint_counter}"
            self._connection.execute(f"SAVEPOINT {sp_name}")
            return sp_name

    def rollback_to(self, savepoint_name: str) -> None:
        with self._lock:
            if self._connection and self._in_transaction:
                self._connection.execute(
                    f"ROLLBACK TO SAVEPOINT {savepoint_name}"
                )

    def release_savepoint(self, savepoint_name: str) -> None:
        with self._lock:
            if self._connection and self._in_transaction:
                self._connection.execute(
                    f"RELEASE SAVEPOINT {savepoint_name}"
                )
```

#### 9.3.2 SQLDataSource 条件化 commit

```python
class SQLDataSource(DataSource):
    @property
    def in_transaction(self) -> bool:
        return getattr(self, '_in_transaction', False)

    def insert(self, table_name, data):
        # ... 现有代码 ...
        cursor = self.execute(sql, tuple(data.values()))
        if not self.in_transaction:
            self.commit()
        return cursor.lastrowid

    def update(self, table_name, id_value, data):
        # ... 现有代码 ...
        self.execute(sql, tuple(params))
        if not self.in_transaction:
            self.commit()
        return True

    def delete(self, table_name, id_value):
        # ... 现有代码 ...
        self.execute(sql, (id_value,))
        if not self.in_transaction:
            self.commit()
        return True

    def batch_insert(self, table_name, data_list):
        # ... 现有代码 ...
        for data in data_list:
            self.execute(sql, tuple(data.get(k) for k in columns))
            count += 1
        if not self.in_transaction:
            self.commit()
        return count
```

#### 9.3.3 ActionExecutor 事务包裹 + 审计日志 V2

```python
class ActionExecutor:
    def _do_create(self, meta_object, params, skip_rules=False):
        # ... 前置校验（无DB操作）...

        with self.ds.transaction():
            last_id = self.ds.insert(meta_object.table_name, data)

            if meta_object.get_hierarchy_path_field():
                self.ds.update(meta_object.table_name, last_id, {...})
                data["id"] = last_id
                data = self._compute_hierarchy_path(meta_object, data, params)
                self.ds.update(meta_object.table_name, last_id, {...})

            if not skip_rules:
                data["id"] = last_id
                self.rule_engine.execute_rules(
                    meta_object, RuleTrigger.AFTER_CREATE, data
                )
                self.rule_engine.execute_rules(
                    meta_object, RuleTrigger.AFTER_SAVE, data
                )

        # V2 审计日志：事务提交后独立写入
        self._write_audit_log_async(
            lambda: self.audit_logger.log_create(
                object_type=meta_object.id,
                object_id=last_id, data=data
            )
        )

        return ActionResult.ok(data={"id": last_id}, ...)

    def _do_update(self, meta_object, params, skip_rules=False):
        # ... 前置校验 ...
        version = params.get('version')

        with self.ds.transaction():
            if version is not None:
                self._check_version(meta_object, id_value, version)
            self.ds.update(meta_object.table_name, id_value, data)

            if not skip_rules:
                self.rule_engine.execute_rules(
                    meta_object, RuleTrigger.AFTER_UPDATE, data
                )
                self.rule_engine.execute_rules(
                    meta_object, RuleTrigger.AFTER_SAVE, data
                )

        self._write_audit_log_async(
            lambda: self.audit_logger.log_update(
                object_type=meta_object.id,
                object_id=id_value, old_data=original_data,
                new_data=data
            )
        )
        return ActionResult.ok(...)

    def _do_delete(self, meta_object, params, skip_rules=False):
        # ... 前置校验 ...

        with self.ds.transaction():
            self.ds.delete(meta_object.table_name, id_value)
            if not skip_rules:
                self.rule_engine.execute_rules(
                    meta_object, RuleTrigger.AFTER_DELETE, data
                )

        self._write_audit_log_async(
            lambda: self.audit_logger.log_delete(
                object_type=meta_object.id,
                object_id=id_value, data=data
            )
        )
        return ActionResult.ok(...)

    def _write_audit_log_async(self, audit_fn):
        """V2 审计日志写入 — 参考 SAP V2 Update"""
        try:
            with self.ds.transaction():
                audit_fn()
        except Exception as e:
            logger.warning("Audit log write failed: %s", str(e))

    def _check_version(self, meta_object, id_value, expected_version):
        """乐观锁版本检查"""
        record = self.ds.find_by_id(meta_object.table_name, id_value)
        if record and record.get('version') != expected_version:
            raise ConcurrentModificationError(
                f"记录已被其他用户修改（期望版本 {expected_version}，"
                f"当前版本 {record.get('version')}）"
            )
```

#### 9.3.4 CascadeService 统一事务

```python
class CascadeService:
    def execute_cascade(self, actions):
        deleted_counts = {}
        # 分类操作
        set_null_actions = [a for a in actions if a["type"] == "set_null"]
        set_default_actions = [a for a in actions if a["type"] == "set_default"]
        delete_actions = [a for a in actions if a["type"] == "delete"]

        with self.ds.transaction():
            for action in set_null_actions:
                # ... SET NULL 操作 ...
                self.ds.execute(sql, tuple(ids))
                # 不再 self.ds.commit()

            for action in set_default_actions:
                # ... SET DEFAULT 操作 ...
                self.ds.execute(sql, ...)
                # 不再 self.ds.commit()

            for action in reversed(delete_actions):
                # ... DELETE 子记录 ...
                if child_ids_to_delete:
                    self.ds.execute(sql, tuple(child_ids_to_delete))
                    # 不再 self.ds.commit()
                # ... DELETE 父记录 ...
                if ids:
                    self.ds.execute(sql, tuple(ids))
                    # 不再 self.ds.commit()

        return deleted_counts
```

#### 9.3.5 乐观锁 version 字段

```python
# models.py — MetaObject 自动追加 version 字段
class MetaObject:
    def get_persistent_fields(self):
        fields = [f for f in self.fields if f.persistent]
        if not any(f.db_column == 'version' for f in fields):
            fields.append(Field(
                id='version', name='版本号', type='integer',
                db_column='version', default=1, persistent=True,
                description='乐观锁版本号'
            ))
        return fields

# sql_adapters.py — update 方法支持 version 检查
class SQLDataSource(DataSource):
    def update_with_version(self, table_name, id_value, data,
                            expected_version=None):
        if expected_version is not None:
            data['version'] = expected_version + 1
            set_parts = [f"{k} = {self._placeholder()}" for k in data.keys()]
            sql = f"UPDATE {table_name} SET {', '.join(set_parts)} " \
                  f"WHERE id = {self._placeholder()} AND version = {self._placeholder()}"
            params = list(data.values()) + [id_value, expected_version]
            cursor = self.execute(sql, tuple(params))
            if cursor.rowcount == 0:
                raise ConcurrentModificationError(
                    f"记录已被其他用户修改"
                )
            return True
        else:
            return self.update(table_name, id_value, data)
```

#### 9.3.6 ConcurrentModificationError 定义

```python
# meta/core/exceptions.py
class ConcurrentModificationError(Exception):
    """并发修改异常 — 乐观锁版本不匹配"""
    pass
```

#### 9.3.7 API 层事务修复示例（user_api.py）

```python
@user_bp.route('', methods=['POST'])
@login_required
def create_user():
    # ... 校验 ...

    with _data_source.transaction():
        cursor = _data_source.execute(
            "INSERT INTO users ...", [...]
        )
        user_id = cursor.lastrowid

        role_ids = data.get('role_ids', [])
        for role_id in role_ids:
            _get_perm_service().assign_role(user_id, role_id)
        # 不再单独 commit

    return jsonify({'success': True, 'data': {'id': user_id, ...}})
```

### 9.4 Alternatives Considered

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| A. 请求级自动事务（Flask中间件） | 开发者无感知，最简单 | 长事务阻塞、只读请求也开事务 | Rejected（Phase 3考虑） |
| B. 操作级显式事务（transaction()） | 精确控制事务边界，灵活 | 开发者需手动包裹 | **Selected** |
| C. 混合模式（中间件+显式） | 兼顾自动和手动 | 复杂度高 | Rejected（过度设计） |
| D. 审计日志同事务 | 实现简单 | 回滚丢失审计 | Rejected |
| E. 审计日志V2异步 | SAP最佳实践，审计不阻塞业务 | 审计可能丢失 | **Selected** |
| F. 乐观锁仅关键对象 | 迁移成本低 | 不一致，易遗漏 | Rejected |
| G. 乐观锁全量添加 | 一致性好，元模型驱动 | 迁移成本略高 | **Selected** |

### 9.3.8 Operation Journal 数据模型（Agentic AI）

```sql
CREATE TABLE IF NOT EXISTS operation_journals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id TEXT NOT NULL UNIQUE,        -- 操作唯一ID（幂等键）
    agent_id TEXT,                            -- AI Agent 标识
    agent_session_id TEXT,                    -- Agent 会话ID
    tool_call_id TEXT,                        -- OpenAI tool_call ID
    reasoning TEXT,                           -- Agent 推理说明
    object_type TEXT NOT NULL,                -- 操作对象类型
    object_id INTEGER,                        -- 操作对象ID
    action TEXT NOT NULL,                     -- 操作类型 (CREATE/UPDATE/DELETE)
    data TEXT,                                -- 操作数据 (JSON)
    compensation_ops TEXT,                    -- 补偿操作定义 (JSON)
    idempotency_key TEXT,                     -- 幂等键
    result TEXT,                              -- 操作结果 (JSON)
    status TEXT DEFAULT 'completed',          -- completed/compensated/failed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    compensated_at TIMESTAMP                  -- 补偿执行时间
);

CREATE INDEX IF NOT EXISTS idx_opjournal_agent ON operation_journals(agent_id);
CREATE INDEX IF NOT EXISTS idx_opjournal_session ON operation_journals(agent_session_id);
CREATE INDEX IF NOT EXISTS idx_opjournal_idempotency ON operation_journals(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_opjournal_object ON operation_journals(object_type, object_id);
CREATE INDEX IF NOT EXISTS idx_opjournal_time ON operation_journals(created_at);
```

补偿操作定义格式：
```json
{
    "type": "update",
    "object_type": "domain",
    "object_id": 3,
    "data": {"parent_id": 2, "version": 2}
}
```

### 9.3.9 AgentWorkflow 编排器（Saga 补偿）

```python
class AgentWorkflow:
    """AI Agent 多步 workflow 编排器 — Saga 补偿模式"""

    def __init__(self, data_source, agent_id, session_id):
        self.ds = data_source
        self.agent_id = agent_id
        self.session_id = session_id
        self.steps = []          # 已完成的步骤
        self.journal = OperationJournalService(data_source)

    def execute_step(self, tool_call_id, action, object_type, params,
                     reasoning="", executor=None):
        """执行单步操作，成功后记录补偿"""
        idempotency_key = tool_call_id

        # 幂等性检查
        existing = self.journal.find_by_idempotency_key(idempotency_key)
        if existing:
            return existing.result

        # 执行操作
        result = executor.execute(...)

        if result.success:
            # 记录补偿操作
            compensation = self._build_compensation(action, object_type, params, result)
            self.journal.record(
                operation_id=f"op_{uuid.uuid4().hex[:12]}",
                agent_id=self.agent_id,
                agent_session_id=self.session_id,
                tool_call_id=tool_call_id,
                reasoning=reasoning,
                object_type=object_type,
                object_id=result.last_insert_id or params.get('id'),
                action=action,
                compensation_ops=compensation,
                idempotency_key=idempotency_key,
                result=result
            )
            self.steps.append(tool_call_id)
        else:
            # 执行补偿链
            self._compensate()

        return result

    def _compensate(self):
        """逆序执行补偿操作"""
        for step_id in reversed(self.steps):
            record = self.journal.find_by_tool_call_id(step_id)
            if record and record.compensation_ops:
                try:
                    self._execute_compensation(record.compensation_ops)
                    self.journal.mark_compensated(record.operation_id)
                except Exception as e:
                    logger.error(
                        "Compensation failed for %s: %s",
                        record.operation_id, str(e)
                    )

    def _build_compensation(self, action, object_type, params, result):
        """构建补偿操作定义"""
        if action == "CREATE":
            return {"type": "delete", "object_type": object_type,
                    "object_id": result.last_insert_id}
        elif action == "UPDATE":
            return {"type": "update", "object_type": object_type,
                    "object_id": params.get('id'),
                    "data": params.get('_original_data', {})}
        elif action == "DELETE":
            return {"type": "create", "object_type": object_type,
                    "data": params.get('_deleted_data', {})}
        return None
```

### 9.3.10 Agent Context 中间件

```python
# meta/server.py 中添加
@app.before_request
def extract_agent_context():
    """提取 AI Agent 上下文"""
    g.agent_id = request.headers.get('X-Agent-Id', '')
    g.agent_session_id = request.headers.get('X-Agent-Session-Id', '')
    g.tool_call_id = request.headers.get('X-Tool-Call-Id', '')
    g.agent_reasoning = request.headers.get('X-Agent-Reasoning', '')
    g.idempotency_key = request.headers.get('X-Idempotency-Key', '')
    g.request_id = g.idempotency_key or str(uuid.uuid4())[:8]
```

### 9.3.11 幂等性检查服务

```python
class IdempotencyService:
    """幂等性检查服务"""

    def __init__(self, data_source):
        self.ds = data_source

    def check_and_execute(self, idempotency_key, operation_fn):
        """检查幂等键，已处理则返回之前结果"""
        if not idempotency_key:
            return operation_fn()

        existing = self.ds.find(
            'operation_journals',
            {'idempotency_key': idempotency_key}
        )
        if existing:
            return existing[0].get('result')

        result = operation_fn()
        return result
```

### 9.5 Implementation & Migration Plan

#### Implementation Order

**Phase 1: 事务基础设施修复（FR-001, FR-002, FR-008）**

1. 修改 `sql_adapters.py`:
   - 添加 `_in_transaction`, `_savepoint_counter` 属性
   - 实现 `begin_transaction()` — 执行 `BEGIN`
   - 修改 `commit()` — 仅事务内时提交
   - 修改 `rollback()` — 仅事务内时回滚
   - 修改 `insert/update/delete/batch_insert` — 条件化 commit
   - 添加 `set_savepoint/rollback_to/release_savepoint`
   - 添加 `PRAGMA foreign_keys = ON`
   - 添加 `in_transaction` 属性

2. 修改 `datasource.py`:
   - 添加 `in_transaction` 抽象属性
   - 添加 `set_savepoint/rollback_to/release_savepoint` 抽象方法
   - 修改 `transaction()` 上下文管理器 — 确保异常时回滚

3. 创建 `meta/core/exceptions.py`:
   - 定义 `ConcurrentModificationError`

**Phase 2: 关键场景事务包裹（FR-003, FR-004, FR-005, FR-006, FR-007）**

4. 修改 `action_executor.py`:
   - `_do_create` 包裹 `transaction()` + V2审计
   - `_do_update` 包裹 `transaction()` + V2审计
   - `_do_delete` 包裹 `transaction()` + V2审计
   - 添加 `_write_audit_log_async()` 方法

5. 修改 `cascade_service.py`:
   - `execute_cascade` 包裹 `transaction()`
   - 移除所有 `self.ds.commit()`

6. 修改 API 层:
   - `user_api.py` — create_user, delete_user 改为事务
   - `role_api.py` — create_role, delete_role 改为事务
   - `enum_api.py` — 消除裸 commit
   - `manage_api.py` — delete_annotations_by_target 改为事务

7. 修改 `import_export_service.py`:
   - `import_cascade` 包裹事务
   - 异步导入使用独立事务

**Phase 3: 高级事务能力（FR-009, FR-010, FR-011）**

8. 乐观锁:
   - `models.py` — MetaObject 自动追加 version 字段
   - `sql_adapters.py` — 添加 `update_with_version()`
   - `action_executor.py` — `_do_update` 支持 version 检查
   - 数据库迁移 — ALTER TABLE ADD COLUMN version

9. allOrNone 模式:
   - `manage_service.py` — batch_create/update/delete 支持 all_or_none 参数
   - all_or_none=True 时使用统一事务
   - all_or_none=False 时每条记录独立事务

10. WAL checkpoint:
    - 定期执行 `PRAGMA wal_checkpoint(TRUNCATE)`

**Phase 4: Agentic AI 事务能力（FR-012, FR-013, FR-014, FR-015）**

11. Operation Journal:
    - 创建 `operation_journals` 表
    - 创建 `OperationJournalService` 服务
    - ActionExecutor 写操作时自动记录补偿操作定义
    - 人类操作时 agent_id 为空

12. Agent Context 中间件:
    - Flask before_request 提取 X-Agent-* 请求头
    - g 对象存储 agent_id, session_id, tool_call_id, reasoning
    - 日志输出包含 agent_id 前缀

13. AgentWorkflow 编排器:
    - 创建 `AgentWorkflow` 类（Saga 补偿模式）
    - `execute_step()` 执行单步 + 记录补偿
    - `_compensate()` 逆序执行补偿链
    - `_build_compensation()` 自动构建补偿操作

14. 幂等性服务:
    - 创建 `IdempotencyService`
    - `check_and_execute()` 幂等键去重
    - manage_api 中集成幂等检查
    - 幂等键 TTL 管理

#### Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| 事务改造破坏现有功能 | Phase 1 保持非事务模式兼容；每步运行测试 |
| 长事务阻塞 SQLite | 事务粒度控制在操作级，不跨请求 |
| 乐观锁导致频繁冲突 | 冲突时返回友好提示，前端自动刷新 |
| 审计日志写入失败 | V2 模式下仅 warning 日志，不影响业务 |
| version 字段迁移失败 | ALTER TABLE ADD COLUMN 是安全操作 |

#### Testing Strategy

- **Unit tests**:
  - `test_transaction_basic.py` — begin/commit/rollback 基本流程
  - `test_transaction_rollback.py` — 异常回滚验证
  - `test_savepoint.py` — Savepoint 创建/回滚/释放
  - `test_optimistic_lock.py` — version 检查/冲突检测
  - `test_conditional_commit.py` — 事务内/外 commit 行为

- **Integration tests**:
  - `test_action_executor_transaction.py` — CRUD 操作事务完整性
  - `test_cascade_transaction.py` — 级联删除事务完整性
  - `test_import_transaction.py` — 导入操作事务完整性
  - `test_api_transaction.py` — API 层事务完整性
  - `test_audit_v2.py` — 审计日志 V2 异步写入

- **E2E tests**:
  - 并发更新冲突场景
  - 级联删除部分失败回滚场景
  - 批量导入部分失败回滚场景

#### Rollback Plan

1. `_in_transaction` 标记确保非事务模式行为不变
2. 如果事务改造导致问题，可通过设置 `_autocommit = True` 全局回退到自动提交模式
3. version 字段是附加列，不影响现有功能

## 10. TBD List

| ID | Item | Missing Information | Next Step |
|----|------|-------------------|-----------|
| TBD-1 | 事务超时控制 | 是否需要限制事务最大执行时间 | Phase 3 评估 |
| TBD-2 | 请求级事务中间件 | Flask before_request 自动开事务 | Phase 3 评估 |
| TBD-3 | WAL checkpoint 策略 | 定时频率（每小时？每次commit后？） | 实施时决定 |
| TBD-4 | 前端 version 字段传递 | 编辑表单如何携带和回传 version | Phase 3 前端改造时确认 |
| TBD-5 | Agent API tool_call 执行端点 | agent_api.py 目前是预留接口，需要新增 POST /agent/execute | Phase 4 设计 |
| TBD-6 | 补偿操作失败处理 | 补偿链中某步补偿失败时的策略（重试？人工介入？） | Phase 4 设计 |
| TBD-7 | 幂等键 TTL 清理策略 | 过期幂等键的清理机制 | Phase 4 实施 |
| TBD-8 | Human-in-the-loop 审批节点 | workflow 暂停/恢复机制 | Phase 4 评估 |
