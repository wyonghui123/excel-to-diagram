# M7 Spec: v3 查询引擎 — 平台化能力

> **版本**: v7.0.0（M7 阶段）
> **日期**: 2026-06-05
> **状态**: ✅ Completed
> **前置**: M1-M6 已完成
> **范围**: Multi-DB / CDC / Auto Schema / Deep Mutation / FTS5

---

## 0. 现状调研（v1/v2 已具备的基础）

> M7 **不重新发明**，**激活 + 完善 + 补全**

| 能力 | 现状 | M7 任务 |
|------|------|---------|
| `MySQLAdapter` ([sql_adapters.py:1013](file:///d:/filework/excel-to-diagram/meta/core/sql_adapters.py#L1013)) | ✅ 完整实现 | 激活 + 完善 JSON/事务 |
| `PostgreSQLAdapter` ([sql_adapters.py:1147](file:///d:/filework/excel-to-diagram/meta/core/sql_adapters.py#L1147)) | ✅ 完整实现 | 激活 + 完善 JSON/事务 |
| `WriteQueue.commit` ([sql_write_queue.py:249](file:///d:/filework/excel-to-diagram/meta/core/sql_write_queue.py#L249)) | ✅ 实现 | 加 `add_commit_hook` 钩子 |
| `yaml_loader.register_from_directory` ([yaml_loader.py](file:///d:/filework/excel-to-diagram/meta/core/yaml_loader.py)) | ✅ 实现 | 旁路 Auto Introspector |
| `DeepInsertEngine` ([deep_insert_engine.py](file:///d:/filework/excel-to-diagram/meta/core/deep_insert_engine.py)) | ✅ 部分实现 | 补全 Deep Update / Deep Delete |
| `DataSource` 抽象 ([datasource.py](file:///d:/filework/excel-to-diagram/meta/core/datasource.py)) | ✅ 基础 | 加 `json_extract / full_text_search` 抽象 |

---

## 1. 目标（4 个 P0/P1 任务）

| ID | 任务 | 优先级 | 工作量 |
|----|------|:-----:|--------|
| **M7.1** | CDC 实时订阅（Event Bus + SSE） | P0 | 5d |
| **M7.2** | Multi-DB 激活（MySQL/PostgreSQL） | P0 | 10d |
| **M7.3** | Deep Insert/Update/Delete 完整化 | P1 | 3d |
| **M7.4** | Auto Schema Introspection | P1 | 5d |

**核心闭环（M7.1 + M7.2）= 15 天** → 平台核心
**完整 M7 = 23 天** → 平台完整

---

## 2. 详细设计

### 2.1 M7.1 CDC 实时订阅

**问题**：实时数据流缺失，前端靠轮询。

**设计**：

**Layer 1: WriteQueue 钩子**（不改核心 commit 逻辑）
```python
# meta/core/sql_write_queue.py 新增
class WriteQueue:
    def __init__(self):
        # ... 既有 ...
        self._commit_hooks: List[Callable] = []  # [M7.1]
    
    def add_commit_hook(self, hook: Callable):
        """注册 commit 钩子（外部订阅）"""
        self._commit_hooks.append(hook)
    
    def commit(self):
        # 原 commit 逻辑
        # ... 既有 ...
        # [M7.1] commit 后通知
        for hook in self._commit_hooks:
            try:
                hook(self._last_operation)
            except Exception as e:
                logger.error(f"[M7.1] commit hook error: {e}")
```

**Layer 2: CDC Event Bus**
```python
# meta/core/cdc_bus.py（新增）
from collections import defaultdict, deque
import threading
import time
import uuid
from typing import Callable, Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class CDCEvent:
    """变更数据捕获事件。"""
    event_id: str
    entity_type: str
    action: str  # 'create' / 'update' / 'delete'
    affected_ids: List[int]
    transaction_id: str
    timestamp: float
    user_context: Dict = field(default_factory=dict)
    
    def to_sse(self) -> str:
        """SSE 序列化。"""
        return f"id: {self.event_id}\ndata: {json.dumps(self.to_dict())}\n\n"
    
    def to_dict(self) -> Dict:
        return {
            'event_id': self.event_id,
            'entity_type': self.entity_type,
            'action': self.action,
            'affected_ids': self.affected_ids,
            'transaction_id': self.transaction_id,
            'timestamp': self.timestamp,
        }


class CDCBus:
    """CDC 事件总线（线程安全 + 内存缓冲）。"""
    
    def __init__(self, max_buffer_per_entity: int = 1000):
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._event_buffer: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=max_buffer_per_entity)
        )
        self._lock = threading.RLock()
        self.published_count = 0
    
    def subscribe(
        self,
        entity_type: str,
        callback: Callable,
        last_event_id: str = '',
    ) -> 'Subscription':
        """订阅 entity_type 变更。
        
        Returns:
            Subscription: 订阅句柄（with 块退出自动取消）
        """
        with self._lock:
            self._subscribers[entity_type].append(callback)
            # 重放历史事件
            if last_event_id:
                for event in list(self._event_buffer[entity_type]):
                    if event.event_id > last_event_id:
                        try:
                            callback(event)
                        except Exception:
                            pass
        return Subscription(self, entity_type, callback)
    
    def publish(self, event: CDCEvent) -> None:
        """发布事件。"""
        with self._lock:
            self._event_buffer[event.entity_type].append(event)
            for cb in self._subscribers.get(event.entity_type, []):
                try:
                    cb(event)
                except Exception as e:
                    logger.error(f"[CDCBus.M7.1] subscriber error: {e}")
            self.published_count += 1
    
    def unsubscribe(self, entity_type: str, callback: Callable) -> None:
        with self._lock:
            if entity_type in self._subscribers:
                try:
                    self._subscribers[entity_type].remove(callback)
                except ValueError:
                    pass


class Subscription:
    """订阅句柄（context manager）。"""
    def __init__(self, bus: CDCBus, entity_type: str, callback: Callable):
        self.bus = bus
        self.entity_type = entity_type
        self.callback = callback
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.bus.unsubscribe(self.entity_type, self.callback)
        return False


# 全局实例
_default_cdc_bus: Optional[CDCBus] = None


def get_cdc_bus() -> CDCBus:
    global _default_cdc_bus
    if _default_cdc_bus is None:
        _default_cdc_bus = CDCBus()
    return _default_cdc_bus
```

**Layer 3: WriteQueue 钩子集成**
```python
# meta/core/sql_adapters.py SQLiteAdapter.connect() 末尾
def connect(self, **kwargs) -> bool:
    # 原 connect
    # ... 既有 ...
    # [M7.1] 注册 CDC 钩子
    if self._write_queue and kwargs.get('cdc_enabled', True):
        cdc_bus = get_cdc_bus()
        def _hook(op: WriteOperation):
            if not op.entity_type or not op.affected_ids:
                return
            event = CDCEvent(
                event_id=f"cdc-{uuid.uuid4().hex[:16]}",
                entity_type=op.entity_type,
                action=op.action,
                affected_ids=op.affected_ids,
                transaction_id=op.transaction_id or '',
                timestamp=time.time(),
            )
            cdc_bus.publish(event)
        self._write_queue.add_commit_hook(_hook)
    return True
```

**Layer 4: SSE API**
```python
# meta/api/sse_api.py（新增）
import queue
import threading

from meta.core.cdc_bus import get_cdc_bus, CDCEvent


@api_bp.route('/api/v1/subscribe/<entity_type>', methods=['GET'])
def subscribe_sse(entity_type: str):
    """SSE 端点：订阅 entity_type 变更。"""
    last_event_id = request.headers.get('Last-Event-ID', '')
    
    def event_stream():
        event_queue = queue.Queue(maxsize=100)
        bus = get_cdc_bus()
        
        def callback(event: CDCEvent):
            try:
                event_queue.put(event)
            except queue.Full:
                pass
        
        with bus.subscribe(entity_type, callback, last_event_id):
            # 30 秒心跳保活
            last_heartbeat = time.time()
            while True:
                try:
                    event = event_queue.get(timeout=5)
                    yield event.to_sse()
                except queue.Empty:
                    if time.time() - last_heartbeat > 30:
                        yield ": heartbeat\n\n"
                        last_heartbeat = time.time()
    
    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        },
    )
```

**Layer 5: WriteOperation 增加 entity_type / affected_ids**

当前 `WriteOperation` 没有 entity_type 字段（v1 不传递）。需要扩展：
```python
# meta/core/sql_write_queue.py
@dataclass
class WriteOperation:
    command: str
    params: Optional[tuple] = None
    # [M7.1] 上下文
    entity_type: str = ''
    action: str = ''  # 'create' / 'update' / 'delete'
    affected_ids: List[int] = field(default_factory=list)
    transaction_id: str = ''
```

修改 `_execute_via_write_queue`（[sql_adapters.py:841](file:///d:/filework/excel-to-diagram/meta/core/sql_adapters.py#L841)）：在 submit 时解析 entity_type / action（用 `_classify_operation` 已经是 'write'，需要更细粒度）。

**简化版（M7.1 阶段 1）**：仅从 SQL 文本里正则提取 `INSERT|UPDATE|DELETE FROM <table>` 拿 entity_type，action 从动词拿，affected_ids 从 `cursor.lastrowid` / `cursor.rowcount` 拿。

---

### 2.2 M7.2 Multi-DB 激活

**问题**：MySQLAdapter / PostgreSQLAdapter 完整但未激活。

**设计**：

**Step 1: 完善 DataSource 抽象**（json_extract / full_text_search）
```python
# meta/core/datasource.py
class DataSource(ABC):
    # ... 既有 ...
    
    @abstractmethod
    def json_extract(self, field: str, path: str) -> str:
        """构造 JSON 提取 SQL 表达式。
        
        Returns:
            SQL 表达式字符串
        """
        pass
    
    @abstractmethod
    def supports_full_text_search(self) -> bool:
        """是否支持原生 FTS。"""
        pass
    
    @abstractmethod
    def build_fts_query(self, table: str, columns: List[str], query: str) -> tuple:
        """构造 FTS 查询 SQL + params。"""
        pass


# SQLiteAdapter 实现
class SQLiteAdapter(SQLDataSource):
    def json_extract(self, field: str, path: str) -> str:
        # SQLite JSON1: $.key
        return f"JSON_EXTRACT({field}, '$.{path}')"
    
    def supports_full_text_search(self) -> bool:
        return True  # FTS5
    
    def build_fts_query(self, table: str, columns: List[str], query: str) -> tuple:
        return (
            f"SELECT * FROM {table} WHERE id IN "
            f"(SELECT rowid FROM {table}_fts WHERE {table}_fts MATCH ?)",
            [query],
        )

# MySQLAdapter 实现
class MySQLAdapter(SQLDataSource):
    def json_extract(self, field: str, path: str) -> str:
        # MySQL JSON: $.key
        return f"JSON_EXTRACT({field}, '$.{path}')"
    
    def supports_full_text_search(self) -> bool:
        return True  # FULLTEXT
    
    def build_fts_query(self, table: str, columns: List[str], query: str) -> tuple:
        match_cols = ', '.join(columns)
        return (
            f"SELECT * FROM {table} WHERE MATCH({match_cols}) AGAINST (? IN NATURAL LANGUAGE MODE)",
            [query],
        )

# PostgreSQLAdapter 实现
class PostgreSQLAdapter(SQLDataSource):
    def json_extract(self, field: str, path: str) -> str:
        # PG JSONB: ->> 'key'  /  #> '{key}'
        return f"({field})::jsonb ->> '{path}'"
    
    def supports_full_text_search(self) -> bool:
        return True  # tsvector
    
    def build_fts_query(self, table: str, columns: List[str], query: str) -> tuple:
        tsvector = ' || '.join(
            f"to_tsvector('simple', coalesce({col}, ''))" for col in columns
        )
        return (
            f"SELECT * FROM {table} WHERE {tsvector} @@ plainto_tsquery('simple', ?)",
            [query],
        )
```

**Step 2: Tenant 路由**
```python
# meta/core/tenant_router.py（新增）
class TenantRouter:
    """按请求上下文路由到对应 DataSource。"""
    
    def __init__(self):
        self._ds_pool: Dict[str, DataSource] = {}
        self._default_ds: Optional[DataSource] = None
    
    def register(self, tenant_id: str, ds: DataSource) -> None:
        self._ds_pool[tenant_id] = ds
    
    def set_default(self, ds: DataSource) -> None:
        self._default_ds = ds
    
    def get(self, request_context: Optional[Dict] = None) -> DataSource:
        if request_context and 'tenant_id' in request_context:
            tenant_id = request_context['tenant_id']
            if tenant_id in self._ds_pool:
                return self._ds_pool[tenant_id]
        return self._default_ds


_default_router: Optional[TenantRouter] = None


def get_tenant_router() -> TenantRouter:
    global _default_router
    if _default_router is None:
        _default_router = TenantRouter()
    return _default_router
```

**Step 3: facade.execute 集成**
```python
# meta/core/unified_query_facade.py execute() 入口
def execute(self, req, request_context=None):
    # [M7.2] Tenant 路由
    if request_context and 'tenant_id' in request_context:
        router = get_tenant_router()
        ds = router.get(request_context)
        if ds is not self.ds:
            # 创建新 facade 用 tenant DS
            facade = UnifiedQueryFacade(data_source=ds)
            return facade.execute(req, request_context)
    # ... 原逻辑 ...
```

**Step 4: 多 DataSource 配置**
```python
# meta/config/database_configs.py（新增）
import os
from meta.core.sql_adapters import SQLiteAdapter, MySQLAdapter, PostgreSQLAdapter


def init_default_data_source():
    """根据环境变量选择 DataSource。"""
    db_type = os.environ.get('DATABASE_TYPE', 'sqlite').lower()
    
    if db_type == 'sqlite':
        return SQLiteAdapter().connect(
            db_path=os.environ.get('DATABASE_PATH', 'meta/architecture.db')
        )
    elif db_type == 'mysql':
        return MySQLAdapter().connect(
            host=os.environ.get('MYSQL_HOST', 'localhost'),
            port=int(os.environ.get('MYSQL_PORT', 3306)),
            user=os.environ.get('MYSQL_USER', 'root'),
            password=os.environ.get('MYSQL_PASSWORD', ''),
            database=os.environ.get('MYSQL_DATABASE', 'arch'),
        )
    elif db_type == 'postgresql':
        return PostgreSQLAdapter().connect(
            host=os.environ.get('PG_HOST', 'localhost'),
            port=int(os.environ.get('PG_PORT', 5432)),
            user=os.environ.get('PG_USER', 'postgres'),
            password=os.environ.get('PG_PASSWORD', ''),
            database=os.environ.get('PG_DATABASE', 'arch'),
        )
    else:
        raise ValueError(f"Unknown DATABASE_TYPE: {db_type}")
```

---

### 2.3 M7.3 Deep Insert/Update/Delete 完整化

**问题**：DeepInsertEngine 已有但仅 Insert；Deep Update / Deep Delete 未实现。

**设计**：

**Deep Insert**（已存在）— 补全测试
**Deep Update**（新增）：
```python
# meta/core/deep_mutation_engine.py（新增）
class DeepMutationEngine:
    """深度写入引擎（Insert + Update + Delete）。"""
    
    def __init__(self, deep_insert_engine=None, bo_framework=None):
        from meta.core.deep_insert_engine import DeepInsertEngine
        from meta.core.bo_framework import bo_framework as default_bf
        self._insert_engine = deep_insert_engine or DeepInsertEngine()
        self._bo_framework = bo_framework or default_bf
    
    def deep_insert(self, object_type, payload, data_source) -> ActionResult:
        """M5.6 已实现。"""
        return self._insert_engine.execute(object_type, payload, data_source)
    
    def deep_update(
        self,
        object_type: str,
        filter_clause: Dict,
        patch_data: Dict,
        options: Dict = None,
        data_source=None,
    ) -> ActionResult:
        """[M7.3] 深度更新。
        
        用法：
            deep_update('order', {'id': 100}, {
                'status': 'paid',
                'items': [  # 嵌套子操作
                    {'update': {'id': 1, 'quantity': 5}},
                    {'create': {'product_id': 10, 'quantity': 1}},
                    {'delete': {'id': 3}},
                ],
            })
        """
        options = options or {}
        transaction_mode = options.get('transaction_mode', 'all_or_nothing')
        
        if transaction_mode == 'all_or_nothing':
            return self._update_with_txn(
                object_type, filter_clause, patch_data, data_source
            )
        return self._update_without_txn(
            object_type, filter_clause, patch_data, data_source
        )
    
    def _update_with_txn(self, object_type, filter_clause, patch_data, data_source):
        ds = data_source or self._bo_framework._data_source
        affected = []
        already_in_txn = bool(ds.in_transaction)
        try:
            if already_in_txn:
                # 嵌套识别
                return self._do_update_steps(
                    object_type, filter_clause, patch_data, ds, affected
                )
            with ds.transaction():
                return self._do_update_steps(
                    object_type, filter_clause, patch_data, ds, affected
                )
        except Exception as e:
            logger.error(f"[DeepUpdate.M7.3] rolled back: {e}")
            return ActionResult(
                success=False,
                message=f'deep update failed: {e}',
                data={'rolled_back': True},
                errors=[str(e)],
            )
    
    def _do_update_steps(self, object_type, filter_clause, patch_data, ds, affected):
        # 1. 父对象 update
        from meta.core.action_context import ActionResult
        parent_result = self._bo_framework.update(
            object_type,
            filter_clause.get('id'),
            {k: v for k, v in patch_data.items() if not isinstance(v, (list, dict))}
        )
        if not parent_result.success:
            raise RuntimeError(f"parent update failed: {parent_result.message}")
        affected.append(parent_result.data.get('id'))
        
        # 2. 嵌套子操作
        for key, value in patch_data.items():
            if not isinstance(value, list):
                continue
            for child_op in value:
                if 'update' in child_op:
                    self._bo_framework.update(
                        self._infer_child_type(object_type, key),
                        child_op['update']['id'],
                        child_op['update'],
                    )
                elif 'create' in child_op:
                    # 推断 FK
                    child_data = child_op['create']
                    fk = self._infer_fk(object_type, key)
                    child_data[fk] = affected[0]
                    self._bo_framework.create(
                        self._infer_child_type(object_type, key),
                        child_data,
                    )
                elif 'delete' in child_op:
                    self._bo_framework.delete(
                        self._infer_child_type(object_type, key),
                        child_op['delete']['id'],
                    )
        return ActionResult(
            success=True,
            data={'affected': affected, 'parent_id': affected[0] if affected else None},
            message='deep update completed',
        )
    
    def deep_delete(
        self,
        object_type: str,
        filter_clause: Dict,
        cascade: bool = False,
        data_source=None,
    ) -> ActionResult:
        """[M7.3] 深度删除（可选级联）。"""
        ds = data_source or self._bo_framework._data_source
        try:
            with ds.transaction():
                # 1. 先查 id（事务内）
                ids = self._find_ids(object_type, filter_clause, ds)
                # 2. 如果 cascade：删所有关联
                if cascade:
                    for child_type in self._get_child_types(object_type):
                        self._cascade_delete_children(object_type, ids, child_type, ds)
                # 3. 删主对象
                for id_ in ids:
                    self._bo_framework.delete(object_type, id_)
            return ActionResult(
                success=True,
                data={'deleted_ids': ids, 'cascade': cascade},
                message=f'deep delete completed ({len(ids)} records)',
            )
        except Exception as e:
            logger.error(f"[DeepDelete.M7.3] rolled back: {e}")
            return ActionResult(
                success=False,
                message=f'deep delete failed: {e}',
                data={'rolled_back': True},
                errors=[str(e)],
            )
```

**API 接入**：
```python
# meta/api/manage_api.py（新增端点）
@api_bp.route('/<object_type>/deep_update', methods=['POST'])
@_auth_required
def deep_update(object_type):
    payload = request.get_json()
    engine = get_deep_mutation_engine()
    result = engine.deep_update(
        object_type=object_type,
        filter_clause=payload.get('filter', {'id': payload.get('id')}),
        patch_data=payload.get('patch', {}),
    )
    return jsonify(_action_result_to_dict(result))

@api_bp.route('/<object_type>/deep_delete', methods=['POST'])
@_auth_required
def deep_delete(object_type):
    payload = request.get_json()
    engine = get_deep_mutation_engine()
    result = engine.deep_delete(
        object_type=object_type,
        filter_clause=payload.get('filter', {'id': payload.get('id')}),
        cascade=payload.get('cascade', False),
    )
    return jsonify(_action_result_to_dict(result))
```

---

### 2.4 M7.4 Auto Schema Introspection

**问题**：手动 yaml 维护成本高。

**设计**：

**Schema Introspector**：
```python
# meta/core/schema_introspector.py（新增）
class SchemaIntrospector:
    """扫描数据库表 → 自动生成 BODefinition。"""
    
    def __init__(self, data_source):
        from meta.core.bo_framework import bo_framework
        self._ds = data_source or bo_framework._data_source
    
    def list_tables(self) -> List[str]:
        """列出所有业务表（排除系统表）。"""
        # SQLite: SELECT name FROM sqlite_master WHERE type='table'
        # PG: SELECT tablename FROM pg_tables WHERE schemaname='public'
        # MySQL: SHOW TABLES
        ...
    
    def introspect(self, table_name: str) -> Dict:
        """扫描表结构 → BODefinition dict（可序列化为 yaml）。"""
        columns = self._get_columns(table_name)
        fks = self._get_foreign_keys(table_name)
        indexes = self._get_indexes(table_name)
        
        return {
            'object_type': self._to_camel_case(table_name),
            'table_name': table_name,
            'fields': [self._column_to_field(c) for c in columns],
            'associations': [self._fk_to_association(fk) for fk in fks],
            'indexes': indexes,
        }
    
    def generate_yaml(self, table_name: str) -> str:
        """生成 yaml 文件内容。"""
        bd = self.introspect(table_name)
        import yaml
        return yaml.dump(
            {'business_object': bd},
            default_flow_style=False,
            sort_keys=False,
        )
    
    def diff_with_yaml(self, table_name: str, yaml_path: str) -> List[str]:
        """对比 DB 当前结构 vs yaml 文件 → 返回差异列表。"""
        actual = self.introspect(table_name)
        # 读 yaml
        with open(yaml_path, 'r', encoding='utf-8') as f:
            yaml_content = yaml.safe_load(f)
        declared = yaml_content.get('business_object', {})
        # 字段差异
        actual_fields = {f['name'] for f in actual.get('fields', [])}
        declared_fields = {f['name'] for f in declared.get('fields', [])}
        return [
            f'+ field: {f}' for f in actual_fields - declared_fields
        ] + [
            f'- field: {f}' for f in declared_fields - actual_fields
        ]


# meta/core/app_builder.py 新增
def with_auto_schema(self, db_url=None) -> 'ApplicationBuilder':
    """[M7.4] 自动从 DB 扫描所有表 → 注册 BO（替代 with_yaml_schemas）。"""
    from meta.core.schema_introspector import SchemaIntrospector
    from meta.core.models import registry
    from meta.core.yaml_loader import get_yaml_schema_dir
    
    introspector = SchemaIntrospector(self._data_source)
    for table in introspector.list_tables():
        bd = introspector.introspect(table)
        # 转 BODefinition 对象 → register
        ...
    return self
```

---

## 3. 风险与缓解

| 风险 | 缓解 |
|------|------|
| MySQL/PG adapter 激活后 SQLite 路径失效 | 保留 SQLite 默认；环境变量 `DATABASE_TYPE=sqlite` 强制默认 |
| WriteQueue 钩子高频调用影响性能 | 钩子内做空检查（entity_type 为空则跳过）；缓冲队列异步 |
| Auto schema 误识别临时表 | 黑名单：`_temp_%`, `tmp_%`, `sqlite_%` |
| Deep Update 嵌套子操作性能 | 限制子操作数（max 100）；事务批量化 |

---

## 4. 验收

### M7.1 CDC
```python
# 1. subscribe/unsubscribe
bus = get_cdc_bus()
received = []
with bus.subscribe('user_group', lambda e: received.append(e)):
    bus.publish(CDCEvent(event_id='e1', entity_type='user_group', action='create', ...))
    bus.publish(CDCEvent(event_id='e2', entity_type='user_group', action='update', ...))
assert len(received) == 2

# 2. SSE 端点
client.get('/api/v1/subscribe/user_group', headers={'Last-Event-ID': ''})

# 3. WriteQueue commit 钩子触发
ds = SQLiteAdapter().connect()
op = WriteOperation('INSERT INTO user_groups ...', entity_type='user_group', action='create')
ds._write_queue.submit(op)  # → hook fires
```

### M7.2 Multi-DB
```python
# 1. 三种 adapter 都能 connect
for AdapterCls in [SQLiteAdapter, MySQLAdapter, PostgreSQLAdapter]:
    ds = AdapterCls()
    assert ds.connect()

# 2. json_extract 跨 DB 一致
for AdapterCls in [SQLiteAdapter, MySQLAdapter, PostgreSQLAdapter]:
    ds = AdapterCls()
    expr = ds.json_extract('metadata', 'name')
    # 验证表达式语法

# 3. Tenant 路由
router = TenantRouter()
router.register('tenant_001', ds1)
router.register('tenant_002', ds2)
router.set_default(ds_default)
assert router.get({'tenant_id': 'tenant_001'}) is ds1
```

### M7.3 Deep Mutation
```python
# deep_update 嵌套 create + delete
result = engine.deep_update('order', {'id': 100}, {
    'status': 'paid',
    'items': [
        {'create': {'product_id': 10, 'quantity': 1}},
        {'delete': {'id': 3}},
    ],
})
assert result.success
assert result.data['affected'] == [100]

# deep_delete cascade
result = engine.deep_delete('order', {'id': 100}, cascade=True)
assert result.success
```

### M7.4 Auto Schema
```python
introspector = SchemaIntrospector(ds)
tables = introspector.list_tables()
bd = introspector.introspect('user_groups')
assert 'object_type' in bd
assert 'fields' in bd
yaml_content = introspector.generate_yaml('user_groups')
assert 'object_type' in yaml_content
```

---

## 5. 零回归

`test.py --status` 失败数 ≤ M6 末值（7 failed）。

新增测试覆盖：
- M7.1: CDC subscribe/publish/unsubscribe / SSE 端点 / 钩子触发
- M7.2: 三种 adapter connect / json_extract / FTS query
- M7.3: deep_insert / deep_update / deep_delete 单测
- M7.4: introspect / generate_yaml / diff_with_yaml

---

## 6. 不在 M7 范围

- i18n field query — 已记录待 M8
- FTS5 全文检索 — 已部分支持（LIKE）— 可作 M7.5 选项

---

## 7. 累计 M1-M7 进展

| 阶段 | 增量 | 客户可接受度 |
|------|------|------------|
| M1-M4 | 读路径企业级基线 | 80% 中小客户 |
| M5 | 写路径 + 事务 | 95% 客户 |
| M6 | Allow-list + expand + Explain + 权限 | **100% 大客户/金融/政府** |
| **M7** | **CDC + Multi-DB + Deep Mutation + Auto Schema** | **可对外 SaaS 化** |
| M8+ | i18n / FTS / 跨数据中心 | 全球 SaaS |

**执行开始**：本 spec 写完即实施。优先级 M7.1 + M7.2（核心闭环 15 天）。
