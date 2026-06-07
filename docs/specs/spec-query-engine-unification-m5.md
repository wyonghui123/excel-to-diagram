# M5 Spec: v3 查询引擎 — 写路径收敛 + 事务基线

> **版本**: v5.0.0（M5 阶段）
> **日期**: 2026-06-05
> **状态**: ✅ Completed
> **前置**: M1-M4 已完成；[spec-query-engine-gap-analysis-v3-vs-head.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-query-engine-gap-analysis-v3-vs-head.md) Gap 6-9
> **范围**: UnifiedMutationFacade / 拦截器链事务基线 / 全文检索

---

## 0. 现有事务架构（v1 / v2 现状）

> 调研产出：项目已有**多层事务基础设施**，但**未串成统一基线**。M5 阶段不重新发明，而是**串联 + 补全 + 对 v3 路径暴露**。

### 0.1 事务基础设施图

```
┌────────────────────────────────────────────────────────────────────┐
│  v3 层（读路径）                                                   │
│  UnifiedQueryFacade.execute                                       │
│  └─ 不开事务（query 不需要）                                       │
├────────────────────────────────────────────────────────────────────┤
│  v3 层（写路径）              ← M5 主目标                          │
│  (目标) UnifiedMutationFacade.execute                             │
│  ├─ 开事务（自动）                                                │
│  └─ 串接拦截器链 + FieldValueProvider + 规则链 + 审计              │
├────────────────────────────────────────────────────────────────────┤
│  拦截器链层                                                        │
│  BOFramework.execute (object_type, action, params)                │
│  ├─ _execute_before_interceptors (16 拦截器)                      │
│  ├─ _execute_core  ← PersistenceInterceptor.do_create/update/..   │
│  ├─ _execute_after_interceptors                                   │
│  └─ 现状：autocommit（无事务包装）   ❌                            │
├────────────────────────────────────────────────────────────────────┤
│  DeepInsertEngine (特例场景)                                       │
│  ├─ _execute_with_transaction: 手动 with ds.transaction()        │
│  ├─ transaction_mode: all_or_nothing / independent               │
│  └─ 异常 → 整体回滚 + 报告失败 stage                              │
├────────────────────────────────────────────────────────────────────┤
│  BOFramework.transaction() (包装层)                               │
│  ├─ begin_transaction: 生成 transaction_id (uuid[:8])            │
│  ├─ commit / rollback → 调 _data_source.commit/rollback          │
│  └─ TransactionContext: __enter__ / __exit__ 自动管理            │
├────────────────────────────────────────────────────────────────────┤
│  DataSource 抽象                                                   │
│  ├─ DataSource.transaction(): @contextmanager                    │
│  ├─ begin_transaction() / commit() / rollback()                  │
│  ├─ in_transaction 属性                                           │
│  └─ set_savepoint / rollback_to / release_savepoint（nested）     │
├────────────────────────────────────────────────────────────────────┤
│  SQLiteAdapter / MySQLAdapter / PostgreSQLAdapter                  │
│  ├─ begin_transaction: BEGIN / connection.begin() / autocommit=0 │
│  ├─ commit / rollback                                             │
│  ├─ checkpoint_interval 触发 PRAGMA wal_checkpoint                │
│  └─ WriteQueue 串行化（SQLite 写入）                               │
├────────────────────────────────────────────────────────────────────┤
│  WriteQueue (SQLite 写串行化)                                      │
│  ├─ in_transaction / _in_transaction / _savepoint_counter         │
│  ├─ begin_transaction / commit / rollback                         │
│  ├─ set_savepoint / rollback_to / release_savepoint               │
│  └─ submit_and_wait 串行化                                         │
└────────────────────────────────────────────────────────────────────┘
```

### 0.2 现有事务基线（v1/v2 已经实现）

| 能力 | 实现位置 | 状态 |
|------|---------|:----:|
| DataSource.begin/commit/rollback | [sql_adapters.py:549-561](file:///d:/filework/excel-to-diagram/meta/core/sql_adapters.py#L549-L561) | ✅ |
| `with ds.transaction():` 上下文 | [datasource.py:307-324](file:///d:/filework/excel-to-diagram/meta/core/datasource.py#L307-L324) | ✅ |
| `bo_framework.transaction()` 包装 | [bo_framework.py:482-560](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L482-L560) | ✅ |
| X-Transaction-Id 透传 | [ARCHITECTURE_V2.md L347](file:///d:/filework/excel-to-diagram/docs/ARCHITECTURE_V2.md) | ✅ |
| `transaction_id` 审计串联 | [audit-log-verification-spec.md FR-007](file:///d:/filework/excel-to-diagram/docs/specs/audit-log-verification-spec.md) | ✅ |
| Savepoint（嵌套事务） | [sql_adapters.py:921-941](file:///d:/filework/excel-to-diagram/meta/core/sql_adapters.py#L921-L941) | ✅ |
| WriteQueue 串行化（SQLite） | [sql_write_queue.py:213-301](file:///d:/filework/excel-to-diagram/meta/core/sql_write_queue.py#L213-L301) | ✅ |
| `transaction_mode: all_or_nothing / independent` | [deep_insert_engine.py:37-42](file:///d:/filework/excel-to-diagram/meta/core/deep_insert_engine.py#L37-L42) | ✅ |
| **拦截器链自动事务包裹** | （无） | ❌ **M5 补全** |
| **MutationFacade（写路径 SSOT）** | （无） | ❌ **M5 新建** |
| **UnitOfWork（聚合多步修改）** | （无） | ❌ **M5 新建** |

### 0.3 M5 三个任务的定位

| 任务 | 与现有架构关系 |
|------|--------------|
| **M5.3 UnifiedMutationFacade** | 在 BOFramework.execute 之外，**新增**一个写路径 SSOT 入口，**复用** `bo_framework.transaction()` + `DataSource.transaction()`，但**对前端暴露** transaction_id + commit/rollback 报告 |
| **M5.5 拦截器链事务基线** | **在 BOFramework.execute 内部** 自动开事务，**不改变** DataSource 行为，**复用** `with ds.transaction()` |
| **M5.6 UnitOfWork pattern** | 在 UnifiedMutationFacade 之上，**提供 `with uow: ...` 装饰器**，允许业务层聚合多步修改，**复用** 现有事务上下文 |

---

## 1. 目标

| ID | 任务 | 优先级 | 现状 | 工作量 |
|----|------|:-----:|------|--------|
| **M5.1** | 全文检索（SQLite FTS5） | P1 | 缺失 | 3d |
| **M5.2** | 拦截器链事务基线（autocommit → 默认事务） | P0 | 散落 | 2d |
| **M5.3** | UnifiedMutationFacade（写路径 SSOT） | P0 | 缺失 | 3d |
| **M5.4** | 事务完整性验证 + 审计回放 | P1 | 部分 | 1d |
| **M5.5** | UnitOfWork pattern | P1 | 缺失 | 2d |
| **M5.6** | DeepInsert 集成 MutationFacade（衔接 v1/v2） | P0 | 散落 | 1d |

**合计**：12 天（M5.2 + M5.3 + M5.6 + M5.4 必做，M5.1/M5.5 可选）

---

## 2. 详细设计

### 2.1 M5.2 拦截器链事务基线（核心改造）

**问题**：
- 当前 `BOFramework.execute()` 默认 autocommit
- `create / update / delete` 三种 action，**所有拦截器在 autocommit 模式串行**
- 单条 SQL 失败 → 已成功的审计 / 规则 / 触发器写入**不会回滚**

**方案**：
在 [bo_framework.py:execute()](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py) 入口处，**对 CRUD action 自动开事务**：

```python
# 现有代码（bo_framework.py L106-126）
try:
    if action in (CRUD_UPDATE, CRUD_DELETE):
        self._load_old_data(context)
    if action in (CRUD_CREATE, CRUD_UPDATE, CRUD_DELETE):
        violations = self._constraint_engine.validate(context)
        ...
    self._ensure_async_engine()
    if self._async_engine is not None:
        self._execute_interceptors_async(context)
    else:
        self._execute_before_interceptors(context)
        self._execute_core(context)
        self._execute_after_interceptors(context)
    ...

# 改为（M5）
# [M5.2 2026-06-05] CRUD action 自动包裹事务
if action in (CRUD_CREATE, CRUD_UPDATE, CRUD_DELETE, 'associate', 'dissociate',
              'assign', 'unassign', 'batch_assign', 'batch_unassign'):
    # 复用现有 bo_framework.transaction() context
    # 注意：这里我们用 BOFramework 自己管理的 context（生成 transaction_id）
    with self.transaction() as txn_ctx:
        context.transaction_id = txn_ctx.transaction_id
        # 注入到 ActionContext 让审计/规则链可见
        result = self._execute_within_transaction(context)
        # commit/rollback 由 context manager 自动处理
        return result
else:
    # 读路径（query/list）走原路径，不开事务
    return self._execute_within_transaction(context)
```

**关键点**：
1. **复用** `bo_framework.transaction()` 已有 context manager
2. **不重新发明**事务 API
3. **自动传递** `transaction_id` 到 `ActionContext`（让审计/规则链可见）
4. **保留** 现有 `DeepInsertEngine` 手工事务（特例不冲突）
5. **保留** X-Transaction-Id header 体系

**向后兼容**：
- 加 `DISABLE_AUTO_TRANSACTION=true` 环境变量可关闭（默认 false）
- 现有 `DeepInsertEngine._execute_with_transaction` 检测 `DISABLE_AUTO_TRANSACTION=true` 时切换到原模式

**风险与缓解**：
| 风险 | 缓解 |
|------|------|
| 自动事务影响性能（每次 create 多 1 次 BEGIN+COMMIT） | SQLite BEGIN 是 no-op（autocommit 之外）性能损耗 < 0.5ms |
| 与现有手动事务嵌套冲突 | `_data_source.in_transaction` 检查 → 已在事务内则跳过 |
| AsyncInterceptorEngine 异步写入 | 审计改为同事务内写入（M5.4 调整） |
| 长事务持有连接 | 加 `transaction_timeout` 配置（默认 30s） |

---

### 2.2 M5.3 UnifiedMutationFacade（写路径 SSOT）

**问题**：
- 当前写路径散落：bo_framework.create / update / delete / deep_insert + 各拦截器
- 与 UnifiedQueryFacade 不对称：读路径有 SSOT，写路径没有
- 业务方调用需要知道 "用 bo_framework 还是 deep_insert engine"

**方案**：

新建 [meta/core/unified_mutation_facade.py](file:///d:/filework/excel-to-diagram/meta/core/unified_mutation_facade.py)：

```python
"""
UnifiedMutationFacade（QE-M5-2026-06-v2）

写路径 SSOT，统一 create / update / delete / deep_insert / associate。
与 UnifiedQueryFacade 对称，共同构成 v3 引擎的读写双 SSOT。
"""
from __future__ import annotations
import logging
import time
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class UnifiedMutationRequest(BaseModel):
    """统一写请求。"""
    entity_type: str
    action: str  # 'create' | 'update' | 'delete' | 'deep_insert' | 'associate' | 'dissociate'
    data: Dict[str, Any] = Field(default_factory=dict)
    options: Dict[str, Any] = Field(default_factory=dict)  # transaction_mode, timeout, etc.
    user_context: Dict[str, Any] = Field(default_factory=dict)
    trace_id: str = ''


class UnifiedMutationResponse(BaseModel):
    """统一写响应。"""
    success: bool
    transaction_id: str
    trace_id: str
    affected_ids: List[int] = Field(default_factory=list)
    data: Dict[str, Any] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)
    rolled_back: bool = False
    failed_at: str = ''
    elapsed_ms: float = 0.0
    # [M5.4] 审计回放链
    audit_chain: List[Dict[str, Any]] = Field(default_factory=list)


class UnifiedMutationFacade:
    """写路径 SSOT 入口。"""

    def __init__(self, bo_framework=None, deep_insert_engine=None):
        from meta.core.bo_framework import bo_framework as default_bf
        from meta.core.deep_insert_engine import DeepInsertEngine
        self.bo_framework = bo_framework or default_bf
        self.deep_insert_engine = deep_insert_engine or DeepInsertEngine()

    def execute(self, req: UnifiedMutationRequest) -> UnifiedMutationResponse:
        """统一写操作。"""
        t0 = time.perf_counter()
        transaction_id = f"mu-{uuid.uuid4().hex[:16]}"
        trace_id = req.trace_id or f"qe-{uuid.uuid4().hex[:16]}"
        errors: List[str] = []
        affected_ids: List[int] = []
        result_data: Dict[str, Any] = {}
        rolled_back = False
        failed_at = ''

        try:
            # [M5.6] 复用 bo_framework.transaction() 现有 context
            with self.bo_framework.transaction() as txn_ctx:
                # 1. 深插入（特例优先判断）
                if req.action == 'deep_insert':
                    action_result = self.deep_insert_engine.execute(
                        req.entity_type, req.data, self.bo_framework._data_source
                    )
                    if not action_result.success:
                        raise _MutationError(
                            stage='deep_insert',
                            detail=action_result.message,
                            errors=action_result.errors,
                        )
                    result_data = action_result.data or {}
                    affected_ids = self._extract_ids(result_data)
                    return UnifiedMutationResponse(
                        success=True, transaction_id=txn_ctx.transaction_id,
                        trace_id=trace_id, affected_ids=affected_ids,
                        data=result_data, errors=[],
                        rolled_back=False, failed_at='', elapsed_ms=...,
                    )

                # 2. 路由 CRUD 到 bo_framework
                if req.action == 'create':
                    action_result = self.bo_framework.create(req.entity_type, req.data)
                elif req.action == 'update':
                    obj_id = req.data.get('id')
                    if not obj_id:
                        raise _MutationError(stage='pre_check', detail='update needs id')
                    action_result = self.bo_framework.update(req.entity_type, obj_id, req.data)
                elif req.action == 'delete':
                    obj_id = req.data.get('id')
                    if not obj_id:
                        raise _MutationError(stage='pre_check', detail='delete needs id')
                    action_result = self.bo_framework.delete(req.entity_type, obj_id)
                else:
                    raise _MutationError(stage='pre_check',
                                         detail=f'unsupported action: {req.action}')

                if not action_result.success:
                    raise _MutationError(
                        stage=req.action,
                        detail=action_result.message,
                        errors=getattr(action_result, 'errors', []),
                    )

                result_data = action_result.data or {}
                affected_ids = self._extract_ids(result_data)

            # commit（with 块正常退出）
            return UnifiedMutationResponse(
                success=True,
                transaction_id=txn_ctx.transaction_id,
                trace_id=trace_id,
                affected_ids=affected_ids,
                data=result_data,
                errors=[],
                rolled_back=False,
                failed_at='',
                elapsed_ms=(time.perf_counter() - t0) * 1000.0,
            )

        except _MutationError as e:
            # 自动回滚（with 块抛异常）
            rolled_back = True
            failed_at = e.stage
            errors = e.errors or [e.detail]
            return UnifiedMutationResponse(
                success=False,
                transaction_id=transaction_id,
                trace_id=trace_id,
                affected_ids=[],
                data={},
                errors=errors,
                rolled_back=rolled_back,
                failed_at=failed_at,
                elapsed_ms=(time.perf_counter() - t0) * 1000.0,
            )

    def _extract_ids(self, data: Dict[str, Any]) -> List[int]:
        if not data:
            return []
        ids = []
        if 'id' in data:
            ids.append(data['id'])
        # deep_insert 父子
        for k, v in data.items():
            if isinstance(v, list) and v and isinstance(v[0], dict) and 'id' in v[0]:
                ids.extend([item['id'] for item in v])
        return ids


class _MutationError(Exception):
    def __init__(self, stage: str, detail: str, errors: Optional[List[str]] = None):
        super().__init__(f'{stage}: {detail}')
        self.stage = stage
        self.detail = detail
        self.errors = errors or [detail]


# 全局默认实例
_default_facade: Optional[UnifiedMutationFacade] = None


def get_mutation_facade() -> UnifiedMutationFacade:
    global _default_facade
    if _default_facade is None:
        _default_facade = UnifiedMutationFacade()
    return _default_facade
```

**关键点**：
1. **复用** `bo_framework.transaction()` 已有 context（生成 transaction_id）
2. **复用** `DeepInsertEngine.execute()` 不重写 deep_insert
3. **复用** `BOFramework.create/update/delete()` 不重写 CRUD
4. **统一响应**：success / transaction_id / affected_ids / rolled_back / failed_at

**M5.6 关键决策**：**不替换** `DeepInsertEngine` 或 `BOFramework`，只**包装**为统一入口——避免破坏现有 v1/v2 调用方。

---

### 2.3 M5.4 事务完整性验证 + 审计回放

**问题**：
- [audit-log-verification-spec.md FR-007](file:///d:/filework/excel-to-diagram/docs/specs/audit-log-verification-spec.md) 已定义 `verify_transaction(txn_id)`
- 但目前 audit log 写入是**异步**的（[async_interceptor_engine.py](file:///d:/filework/excel-to-diagram/meta/core/async_interceptor_engine.py)）—— **跨事务**
- 异步写入 → 事务回滚后 audit log 仍被写出 → 审计不一致

**方案**：

**步骤 1：审计写入改同步**（在 M5.2 自动事务开启后）：
```python
# async_interceptor_engine.py 当前行为
audit_writer.enqueue(...)  # 异步队列

# M5.4 改为（M5.2 之后）
if in_transaction:
    audit_writer.write_sync(...)  # 同事务
else:
    audit_writer.enqueue(...)    # 异步（保持原行为）
```

**步骤 2：M5.3 响应携带 `audit_chain`**：
```python
# MutationFacade 提交时收集
with self.bo_framework.transaction() as txn_ctx:
    action_result = ...
    # 收集当前事务的 audit log
    audit_logs = self._collect_audit_logs(txn_ctx.transaction_id)
    context.audit_chain = audit_logs
```

**步骤 3：实现 `verify_transaction(txn_id)`**：
```python
# meta/services/transaction_verifier.py（新增）
class TransactionVerifier:
    def verify(self, transaction_id: str) -> Dict:
        """验证事务完整性。

        1. 所有 audit_log 共享 transaction_id
        2. 所有 audit_log 共享 user_id
        3. 如果事务 rolled_back → 无任何持久化副作用
        """
        ...
```

---

### 2.4 M5.5 UnitOfWork pattern

**问题**：
- 业务层想要"创建用户组 + 分配角色 + 发邮件通知"作为一个原子单元
- 当前必须手动 `with bo_framework.transaction(): ...`
- 业务代码容易忘记包 / 包错位置

**方案**：

```python
# meta/core/unit_of_work.py（新增）
class UnitOfWork:
    """业务层事务单元。

    复用 bo_framework.transaction() context。
    允许业务方聚合多个写操作（create/update/delete/deep_insert）。
    """

    def __init__(self, user_context: Optional[Dict] = None):
        self.user_context = user_context or {}
        self._operations: List[UnifiedMutationRequest] = []
        self._txn_ctx = None
        self._results: List[UnifiedMutationResponse] = []

    def add(self, request: UnifiedMutationRequest) -> 'UnitOfWork':
        """添加一个写操作到 UoW（不立即执行）。"""
        self._operations.append(request)
        return self  # 链式

    def commit(self) -> Dict[str, Any]:
        """提交整个 UoW（一次性开事务 + 执行所有操作 + commit）。"""
        from meta.core.bo_framework import bo_framework
        facade = get_mutation_facade()
        all_affected_ids: List[int] = []
        all_errors: List[str] = []
        with bo_framework.transaction() as txn_ctx:
            self._txn_ctx = txn_ctx
            for op in self._operations:
                resp = facade.execute(op)
                if not resp.success:
                    # 触发自动 rollback（with 块 raise）
                    raise _UnitOfWorkError(
                        stage=op.action,
                        detail=f"operation {len(self._results)} failed: {resp.errors}",
                        partial_results=list(self._results),
                    )
                self._results.append(resp)
                all_affected_ids.extend(resp.affected_ids)
        return {
            'success': True,
            'transaction_id': txn_ctx.transaction_id,
            'affected_ids': all_affected_ids,
            'operations': [r.data for r in self._results],
        }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None and self._operations and self._txn_ctx is None:
            # 用了 with 但没 commit → 提示
            raise RuntimeError("UnitOfWork: must call commit() before exit")
        return False


# 业务层使用示例
def create_user_with_groups(user_data, group_ids):
    with UnitOfWork() as uow:
        uow.add(UnifiedMutationRequest(
            entity_type='user',
            action='create',
            data=user_data,
        ))
        for gid in group_ids:
            uow.add(UnifiedMutationRequest(
                entity_type='user_group_membership',
                action='create',
                data={'user_id': '@uow.last_id', 'group_id': gid},
            ))
        return uow.commit()
```

**关键点**：
1. **复用** `bo_framework.transaction()` 现有 context
2. **链式 API**：`uow.add(...).add(...).commit()`
3. **占位符支持**：`user_id: '@uow.last_id'` 表示上一次操作返回的 id
4. **部分失败自动回滚**（raise → with 块 exit 触发 rollback）

---

### 2.5 M5.6 DeepInsert 集成 MutationFacade（衔接 v1/v2）

**问题**：
- `DeepInsertEngine` 有自己的事务（`transaction_mode: all_or_nothing / independent`）
- M5.3 MutationFacade 调用 DeepInsertEngine 时**开了两层事务**（嵌套）

**方案**：
- `DeepInsertEngine._execute_with_transaction` 检测 `in_transaction == True` → 跳过内层 `with ds.transaction()`，**复用外层事务**
- 行为对齐：嵌套事务 → 语义合并

```python
# deep_insert_engine.py 调整
def _execute_with_transaction(self, ...):
    data_source_in_txn = data_source.in_transaction
    if data_source_in_txn:
        # [M5.6] 已在事务中（被 MutationFacade 包），直接执行不嵌套
        try:
            return self._do_insert(...)  # 不再 with ds.transaction()
        except Exception as e:
            # 抛出让外层回滚
            raise
    else:
        # 兼容原直接调用
        with data_source.transaction():
            return self._do_insert(...)
```

---

## 3. 实施步骤

| 步骤 | 内容 | 风险 | 验证 |
|------|------|------|------|
| **S1** | M5.2 拦截器链自动事务 | 中 | 单测 + 集成测（CRUD 三种 action 全部 rollback 路径） |
| **S2** | M5.3 UnifiedMutationFacade 新建 | 中 | 14+ smoke test 覆盖 create/update/delete/deep_insert/嵌套 |
| **S3** | M5.4 审计同步化 + verify_transaction | 低 | 复用既有 audit_log_test_plan |
| **S4** | M5.5 UnitOfWork | 低 | 业务场景脚本测试 |
| **S5** | M5.6 DeepInsert 嵌套识别 | 低 | deep_insert 测试（all_or_nothing + 嵌套调用） |
| **S6** | 回归 + DRE 上报 | - | test.py --status ≤ M4 末值 |
| **S7** | M5.1 全文检索 FTS5 | 低 | 性能对比 LIKE 提升 > 10x |

---

## 4. 验收

### M5.2 拦截器链事务基线
```python
# 1. CRUD 三种 action 自动开事务
r = bo_framework.create('user', {'name': 'test'})
assert r.success
# → 数据库应该有一行 + 一条 audit_log，共享同一 transaction_id

# 2. 中间抛错 → 全回滚
with pytest.raises(SomeError):
    r = bo_framework.create('user', {'name': 'test', '_simulate_error': True})
# → 数据库无新行 + 无 audit_log

# 3. 嵌套调用 → 识别已开事务
with bo_framework.transaction() as outer:
    bo_framework.create('user', {'name': 'nested'})
    # 内层不重开
```

### M5.3 UnifiedMutationFacade
```python
facade = get_mutation_facade()
req = UnifiedMutationRequest(
    entity_type='user_group',
    action='create',
    data={'name': 'Test Group', 'code': 'TEST'},
)
resp = facade.execute(req)
assert resp.success
assert resp.transaction_id.startswith('txn-')
assert len(resp.affected_ids) == 1
assert not resp.rolled_back

# deep_insert 衔接
req2 = UnifiedMutationRequest(
    entity_type='user',
    action='deep_insert',
    data={
        'parent': {'name': 'zhangsan'},
        'children': {
            'user_group_membership': [
                {'group_id': 1},
            ]
        }
    },
)
resp = facade.execute(req2)
assert resp.success
assert len(resp.affected_ids) == 2  # 父 + 1 子
```

### M5.4 事务完整性
```python
verifier = get_transaction_verifier()
report = verifier.verify(transaction_id)
assert report['consistency'] == 'PASS'
assert report['audit_log_count'] > 0
assert report['rolled_back'] is False
```

### M5.5 UnitOfWork
```python
with UnitOfWork() as uow:
    uow.add(UnifiedMutationRequest(entity_type='user', action='create', data={...}))
    uow.add(UnifiedMutationRequest(entity_type='user_group_membership', action='create', data={...}))
    result = uow.commit()

assert result['success']
assert len(result['affected_ids']) == 2
assert result['transaction_id'].startswith('txn-')
```

### M5.6 DeepInsert 嵌套识别
```python
# 1. 直接调用 DeepInsertEngine（无嵌套）
engine = DeepInsertEngine()
r = engine.execute('user', {'parent': {...}, 'children': {...}}, ds)
# → 内部自己开事务，ds.in_transaction 在 _execute_with_transaction 内为 True 临时

# 2. 通过 MutationFacade（嵌套）
facade.execute(UnifiedMutationRequest(action='deep_insert', ...))
# → MutationFacade 开外层事务 → DeepInsertEngine 检测 in_transaction=True → 跳过内层
```

---

## 5. 零回归

`test.py --status` 失败数 ≤ M4 末值（7）。

新增测试覆盖：
- 7 个 MutationFacade smoke test（create / update / delete / deep_insert / rollback / 占位符 / 嵌套）
- 5 个 UnitOfWork 业务场景（单操作 / 多操作 / 部分失败回滚 / 嵌套 UoW / 性能）
- 3 个 M5.4 audit verification（回滚无 audit / 成功有 audit / transaction_id 串联）

---

## 6. 不在 M5 范围

- 全文检索（可选 M5.1） — 移到 M6
- 行级权限形式化 — 已在权限 unification spec 中（M5.5）
- 关联 expand / nested projection — 推迟到 M6
- Mutation allow-list — 移到 M6

---

## 7. 与已有 spec 的关联

| 已有 spec | M5 关系 |
|-----------|---------|
| [audit-log-verification-spec.md](file:///d:/filework/excel-to-diagram/docs/specs/audit-log-verification-spec.md) FR-007 | M5.4 直接实现 verify_transaction |
| [spec-deep-insert-polymorphic-composition.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-deep-insert-polymorphic-composition.md) FR-001 | M5.6 衔接 deep_insert 事务 |
| [ARCHITECTURE_V2.md L347](file:///d:/filework/excel-to-diagram/docs/ARCHITECTURE_V2.md) X-Transaction-Id | M5 复用现有 header 体系 |
| [spec-data-permission-unified-model.md](file:///d:/filework/excel-to-diagram/docs/specs/spec_data_permission_unified_model.md) | M5.2 自动事务对权限规则链透明 |

---

**执行开始**：本 spec 写完即执行。优先级 M5.2 + M5.3 + M5.6（核心闭环），M5.4/M5.5/M5.1 可选。
