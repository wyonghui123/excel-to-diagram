# -*- coding: utf-8 -*-
"""[多产品平台] 跨应用事件：Outbox + Dispatcher（roadmap §6.14.2 / §6.14.4）

为什么不用 cdc_bus（§6.14.1）:
    `meta/core/cdc_bus.py` 是**纯内存** pub/sub（deque, maxlen=1000），进程重启即丢、
    订阅者异常不重试。它只能服务"页面实时刷新"这类**可丢失**场景；跨应用的**业务写**
    必须走 outbox —— 否则会出现"WMS 已出库、TMS 无运单"的永久不一致（R15）。

四个必需件（§6.14.2）：
    1. Outbox 表 —— 与业务写**同事务**落库（本模块 + `OutboxInterceptor`）
    2. Dispatcher —— 轮询 outbox → 投递 → 标记；重试上限后进**死信**（status='dead'）
    3. 幂等消费 —— `event_consumer.py`（at-least-once 投递 + 消费端去重）
    4. 事件契约 —— `app.yaml` 的 `events.publish/subscribe`，启动期校验（app_registry）

关键约束（§6.14.4）：
    ① outbox 表位于**发布方的应用库**，与业务写同库同事务（"事务不跨库"的正向应用）
    ② 投递语义是 at-least-once —— 消费端幂等是硬要求
    ③ 不做分布式事务：失败靠重试 + 死信 + 人工介入
    ④ 订阅了不存在的事件 → **启动时失败**（不是运行期静默无响应）
"""
from __future__ import annotations

import ast
import json
import logging
import operator
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from meta.core.app_loader import EVENT_TRIGGERS

logger = logging.getLogger(__name__)

OUTBOX_TABLE = "event_outbox"

STATUS_PENDING = "pending"
STATUS_DELIVERED = "delivered"
STATUS_DEAD = "dead"

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_POLL_INTERVAL = 1.0

#: 平台 action 常量 → 契约 trigger（§6.14.3）
ACTION_TO_TRIGGER = {
    "crud_create": "after_create",
    "crud_update": "after_update",
    "crud_delete": "after_delete",
}

OUTBOX_DDL = f"""
CREATE TABLE IF NOT EXISTS {OUTBOX_TABLE} (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id       TEXT    NOT NULL,
    event_name     TEXT    NOT NULL,
    source_app     TEXT    NOT NULL,
    entity         TEXT    NOT NULL,
    entity_id      INTEGER,
    payload        TEXT    NOT NULL DEFAULT '{{}}',
    status         TEXT    NOT NULL DEFAULT '{STATUS_PENDING}',
    attempts       INTEGER NOT NULL DEFAULT 0,
    last_error     TEXT    NOT NULL DEFAULT '',
    transaction_id TEXT    NOT NULL DEFAULT '',
    created_at     TEXT    NOT NULL,
    delivered_at   TEXT
)
"""

OUTBOX_INDEX_DDL = (
    f"CREATE INDEX IF NOT EXISTS idx_event_outbox_status "
    f"ON {OUTBOX_TABLE} (status, id)"
)

_PENDING_SQL = (
    f"SELECT id, event_id, event_name, source_app, entity, entity_id, payload, attempts "
    f"FROM {OUTBOX_TABLE} WHERE status = ? ORDER BY id LIMIT ?"
)


class EventContractError(RuntimeError):
    """事件契约非法 / 缺失（启动期快速失败，§6.14.4 ④）。"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ─────────────────────────────────────────────────────────────────────────────
# 事件契约（app.yaml 的 events.publish / events.subscribe）
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PublisherContract:
    """发布方声明：某应用的某 BO 在某触发点产生某事件。"""

    app_id: str
    name: str
    entity: str
    trigger: str
    condition: str = ""
    payload: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SubscriptionContract:
    """订阅方声明：某应用消费某事件，并按 idempotency_key 去重。"""

    consumer_app: str
    name: str
    source_app: str
    handler: str          # 相对应用目录的 handler 路径
    idempotency_key: str
    app_dir: str = ""     # 应用目录绝对路径（注册时由 app_registry 填入）


class EventContractRegistry:
    """进程级事件契约注册表。

    **幂等**：以 `(app_id, event_name)` 为键，重复注册只保留一份 —— 避免
    同一个进程内第二次 `create_app()` 把契约累加成两份（PoC 2 的拦截器
    重复注册教训，roadmap §10.12）。
    """

    def __init__(self) -> None:
        self._publishers: Dict[Tuple[str, str], PublisherContract] = {}
        self._subscribers: Dict[Tuple[str, str], SubscriptionContract] = {}

    # ---- 注册 ----

    def register_publish(self, app_id: str, decl: Any) -> None:
        self._publishers[(app_id, decl.name)] = PublisherContract(
            app_id=app_id,
            name=decl.name,
            entity=decl.entity,
            trigger=decl.trigger,
            condition=decl.condition,
            payload=tuple(decl.payload),
        )

    def register_subscribe(self, app_id: str, decl: Any, app_dir: str = "") -> None:
        self._subscribers[(app_id, decl.name)] = SubscriptionContract(
            consumer_app=app_id,
            name=decl.name,
            source_app=decl.source_app,
            handler=decl.handler,
            idempotency_key=decl.idempotency_key,
            app_dir=app_dir or "",
        )

    def reset(self) -> None:
        """清空契约（供测试与进程内重建使用）。"""
        self._publishers.clear()
        self._subscribers.clear()

    # ---- 查询 ----

    @property
    def is_empty(self) -> bool:
        return not self._publishers and not self._subscribers

    @property
    def publisher_app_ids(self) -> List[str]:
        return sorted({c.app_id for c in self._publishers.values()})

    @property
    def publishers(self) -> List[PublisherContract]:
        return list(self._publishers.values())

    @property
    def subscribers(self) -> List[SubscriptionContract]:
        return list(self._subscribers.values())

    def publishers_for(self, app_id: str, entity: str, trigger: str) -> List[PublisherContract]:
        return [
            c for c in self._publishers.values()
            if c.app_id == app_id and c.entity == entity and c.trigger == trigger
        ]

    def subscribers_for(self, event_name: str) -> List[SubscriptionContract]:
        return [c for c in self._subscribers.values() if c.name == event_name]

    # ---- 校验 ----

    def validate(self, enabled_app_ids: List[str]) -> None:
        """启动期契约校验（§6.14.4 ④）。

        Raises:
            EventContractError: 订阅方来源应用未启用 / 发布方不存在该事件 / 缺幂等键
        """
        enabled = list(enabled_app_ids)
        published = {(p.app_id, p.name) for p in self._publishers.values()}
        for sub in self._subscribers.values():
            if sub.consumer_app not in enabled:
                continue  # 未启用的应用不参与校验
            if not sub.idempotency_key:
                raise EventContractError(
                    f"app '{sub.consumer_app}' 订阅 '{sub.name}' 缺少 idempotency_key"
                    "（投递是 at-least-once，消费端幂等是硬要求）"
                )
            if sub.source_app not in enabled:
                raise EventContractError(
                    f"app '{sub.consumer_app}' 订阅 '{sub.name}' 的来源应用 "
                    f"'{sub.source_app}' 未被启用（ENABLED_APPS）"
                )
            if (sub.source_app, sub.name) not in published:
                raise EventContractError(
                    f"app '{sub.consumer_app}' 订阅了不存在的事件 '{sub.name}'"
                    f"（来源应用 '{sub.source_app}' 未声明 events.publish）"
                )


_default_registry: Optional[EventContractRegistry] = None
_registry_lock = threading.Lock()


def get_event_contract_registry() -> EventContractRegistry:
    global _default_registry
    if _default_registry is None:
        with _registry_lock:
            if _default_registry is None:
                _default_registry = EventContractRegistry()
    return _default_registry


# ─────────────────────────────────────────────────────────────────────────────
# condition 求值（仅字面比较，无 eval / 无函数调用）
# ─────────────────────────────────────────────────────────────────────────────

_CMP_OPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}


def evaluate_condition(expression: str, row: Dict[str, Any]) -> bool:
    """求值 `events.publish[].condition`（如 `status == 'shipped'`）。

    刻意用 ast 白名单而非 eval —— 契约来自应用包，属于外部输入（R4 同类风险）。
    不支持函数调用 / 下标 / 属性访问，仅：比较、and/or/not、字面量、字段名。
    """
    try:
        tree = ast.parse(expression, mode="eval").body
    except SyntaxError as e:
        raise EventContractError(f"condition 语法错误: {expression!r} ({e})") from e
    return bool(_eval_node(tree, row))


def _eval_node(node: ast.AST, row: Dict[str, Any]) -> Any:
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(_eval_node(v, row) for v in node.values)
        if isinstance(node.op, ast.Or):
            return any(_eval_node(v, row) for v in node.values)
        raise EventContractError(f"condition 不支持的布尔运算: {type(node.op).__name__}")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _eval_node(node.operand, row)
    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, row)
        for op, comparator in zip(node.ops, node.comparators):
            fn = _CMP_OPS.get(type(op))
            if fn is None:
                raise EventContractError(
                    f"condition 不支持的比较运算: {type(op).__name__}"
                )
            right = _eval_node(comparator, row)
            if not fn(left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.Name):
        return row.get(node.id)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        return [_eval_node(e, row) for e in node.elts]
    raise EventContractError(
        f"condition 含不支持的表达式: {type(node).__name__}（仅允许字段比较）"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Outbox 表操作
# ─────────────────────────────────────────────────────────────────────────────

def resolve_event_data_source(app_id: str):
    """事件表所在的数据源 —— **必须与业务表同库**（§6.14.4 ①）。

    `APP_DB_ROUTING=0`（默认）→ 平台库（应用表也在平台库，语义一致）
    `APP_DB_ROUTING=1`        → 该应用自己的库
    """
    from meta.core.datasource import (
        get_platform_data_source, is_app_db_routing_enabled, open_app_data_source,
    )

    if not is_app_db_routing_enabled():
        return get_platform_data_source()

    from meta.core.app_registry import get_app_database_file
    return open_app_data_source(app_id, get_app_database_file(app_id))


def ensure_outbox_table(data_source) -> None:
    """建 outbox 表（启动期调用；表与业务表同库）。"""
    data_source.execute(OUTBOX_DDL)
    data_source.execute(OUTBOX_INDEX_DDL)


def enqueue_event(
    data_source,
    contract: PublisherContract,
    entity_id: Optional[int],
    payload: Dict[str, Any],
    transaction_id: str = "",
) -> Optional[str]:
    """把事件写入 outbox —— 由调用方保证处于业务写所在事务中（**不自行提交**）。

    Args:
        data_source: 发布方的数据源（= 业务写所用实例，同事务）
        contract: 命中的发布契约
        entity_id: 业务对象 id
        payload: 契约声明字段的快照
        transaction_id: 业务事务 id，用于**同事务去重**（见下）

    Returns:
        event_id；同事务内已存在同一 (event_name, entity_id) 时返回 None（跳过）

    去重说明：拦截器是进程级注册，若同一进程内多次 `create_app()` 会让同一次
    写入触发多次入队。以 (event_name, entity_id, transaction_id) 做同事务去重，
    保证"一次业务写 = 一行事件"。
    """
    event_name = contract.name
    if transaction_id and entity_id is not None:
        existing = data_source.execute(
            f"SELECT id FROM {OUTBOX_TABLE} WHERE event_name = ? AND entity_id = ? "
            f"AND transaction_id = ? LIMIT 1",
            (event_name, entity_id, transaction_id),
        ).fetchone()
        if existing:
            logger.debug(
                "[EventOutbox] 同事务已入队, 跳过: %s entity_id=%s txn=%s",
                event_name, entity_id, transaction_id,
            )
            return None

    event_id = f"evt-{uuid.uuid4().hex[:16]}"
    data_source.execute(
        f"INSERT INTO {OUTBOX_TABLE} (event_id, event_name, source_app, entity, "
        f"entity_id, payload, status, attempts, transaction_id, created_at) "
        f"VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
        (
            event_id, event_name, contract.app_id, contract.entity, entity_id,
            json.dumps(payload, ensure_ascii=False, default=str),
            STATUS_PENDING, transaction_id or "", _now_iso(),
        ),
    )
    logger.info(
        "[EventOutbox] 入队: %s.%s entity_id=%s event_id=%s",
        contract.app_id, event_name, entity_id, event_id,
    )
    return event_id


def fetch_pending(data_source, limit: int = 100) -> List[Dict[str, Any]]:
    """取待投递事件（按入队顺序）。"""
    rows = data_source.execute(_PENDING_SQL, (STATUS_PENDING, limit)).fetchall()
    keys = ("id", "event_id", "event_name", "source_app", "entity", "entity_id",
            "payload", "attempts")
    return [dict(zip(keys, row)) for row in rows]


def _mark(data_source, row_id: int, **sets) -> None:
    if not sets:
        return
    assignments = ", ".join(f"{k} = ?" for k in sets)
    data_source.execute(
        f"UPDATE {OUTBOX_TABLE} SET {assignments} WHERE id = ?",
        (*sets.values(), row_id),
    )


def mark_delivered(data_source, row_id: int) -> None:
    _mark(data_source, row_id, status=STATUS_DELIVERED,
          delivered_at=_now_iso(), attempts=_next_attempts(data_source, row_id))


def mark_failed(data_source, row_id: int, error: str, max_attempts: int) -> str:
    """投递失败：未超上限 → 保持 pending 待重试；超上限 → 死信。返回新状态。"""
    attempts = _next_attempts(data_source, row_id)
    status = STATUS_DEAD if attempts >= max_attempts else STATUS_PENDING
    _mark(data_source, row_id, status=status, attempts=attempts,
          last_error=str(error)[:500])
    return status


def _next_attempts(data_source, row_id: int) -> int:
    row = data_source.execute(
        f"SELECT attempts FROM {OUTBOX_TABLE} WHERE id = ?", (row_id,)
    ).fetchone()
    current = row[0] if row else 0
    return int(current or 0) + 1


# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────────────────────

class EventDispatcher:
    """轮询 outbox → 投递给订阅方 → 标记（§6.14.2）。

    独立线程、不阻塞业务写（Phase 2 只需把**传输层**换成 Redis Stream/Kafka，
    outbox 与幂等消费框架可完整复用，§6.14.5）。
    """

    def __init__(self, contract_registry: Optional[EventContractRegistry] = None,
                 max_attempts: int = DEFAULT_MAX_ATTEMPTS,
                 poll_interval: float = DEFAULT_POLL_INTERVAL,
                 batch_size: int = 100):
        self.registry = contract_registry or get_event_contract_registry()
        self.max_attempts = max_attempts
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        # 非重入锁：同一时刻只允许一次投递（避免多线程并发搬运同一批事件）
        self._lock = threading.Lock()
        self._handler_cache: Dict[str, Any] = {}
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ---- 投递 ----

    def dispatch_once(self) -> Dict[str, int]:
        """扫描一轮并投递。返回统计（供测试与运维观测）。"""
        stats = {"scanned": 0, "delivered": 0, "deferred": 0, "dead": 0}
        if self.registry.is_empty:
            return stats

        with self._lock:
            for app_id in self.registry.publisher_app_ids:
                try:
                    data_source = resolve_event_data_source(app_id)
                    pending = fetch_pending(data_source, self.batch_size)
                except Exception as e:  # noqa: BLE001 - 单库异常不拖垮其他库
                    logger.warning(
                        "[EventDispatcher] 读取 %s 的 outbox 失败: %s", app_id, e
                    )
                    continue

                stats["scanned"] += len(pending)
                for row in pending:
                    outcome = self._deliver(data_source, row)
                    stats[outcome] = stats.get(outcome, 0) + 1
        return stats

    def _deliver(self, publisher_ds, row: Dict[str, Any]) -> str:
        """投递给该事件的全部订阅方。全部成功才算 delivered。"""
        from meta.core.event_consumer import consume_event

        event_name = row["event_name"]
        subscribers = self.registry.subscribers_for(event_name)
        if not subscribers:
            # 启动期 validate() 已拦住这种配置；运行期兜底进死信而非无限重试
            mark_failed(
                publisher_ds, row["id"],
                f"无订阅方（契约缺失）: {event_name}", self.max_attempts,
            )
            logger.error("[EventDispatcher] 事件无订阅方 → 死信: %s", event_name)
            return "dead"

        try:
            payload = json.loads(row["payload"] or "{}")
        except json.JSONDecodeError as e:
            mark_failed(publisher_ds, row["id"], f"payload 非法 JSON: {e}", self.max_attempts)
            return "dead"

        errors: List[str] = []
        for sub in subscribers:
            try:
                handler = self._load_handler(sub)
                consume_event(
                    resolve_event_data_source(sub.consumer_app),
                    consumer_app=sub.consumer_app,
                    event_name=event_name,
                    idempotency_key=str(payload.get(sub.idempotency_key, "")),
                    payload=payload,
                    event_id=row["event_id"],
                    handler=handler,
                )
            except Exception as e:  # noqa: BLE001 - 投递失败靠重试+死信, 不吞不重试在此处
                logger.warning(
                    "[EventDispatcher] 投递失败 %s → %s: %s",
                    event_name, sub.consumer_app, e,
                )
                errors.append(f"{sub.consumer_app}: {e}")

        if errors:
            status = mark_failed(publisher_ds, row["id"], "; ".join(errors),
                                 self.max_attempts)
            if status == STATUS_DEAD:
                logger.error(
                    "[EventDispatcher] 事件进入死信: %s event_id=%s 错误=%s",
                    event_name, row["event_id"], "; ".join(errors),
                )
            return "dead" if status == STATUS_DEAD else "deferred"

        mark_delivered(publisher_ds, row["id"])
        logger.info(
            "[EventDispatcher] 投递成功: %s event_id=%s → %s",
            event_name, row["event_id"], [s.consumer_app for s in subscribers],
        )
        return "delivered"

    def _load_handler(self, sub: SubscriptionContract):
        """按订阅方应用目录加载 handler，返回 `handle(data_source, payload)`。"""
        cached = self._handler_cache.get(sub.consumer_app + ":" + sub.name)
        if cached is not None:
            return cached

        from meta.core.app_registry import load_app_module

        module = load_app_module(
            Path(sub.app_dir) / sub.handler,
            f"app_event_handler_{sub.consumer_app}_{sub.name}",
        )
        handler = getattr(module, "handle", None)
        if not callable(handler):
            raise EventContractError(
                f"app '{sub.consumer_app}' 的 handler '{sub.handler}' "
                f"未定义 handle(data_source, payload)"
            )
        self._handler_cache[sub.consumer_app + ":" + sub.name] = handler
        return handler

    def clear_handler_cache(self) -> None:
        self._handler_cache.clear()

    # ---- 后台线程 ----

    def start(self) -> bool:
        """启动后台投递线程（幂等：已在运行则返回 False）。"""
        if self._thread is not None and self._thread.is_alive():
            return False
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="event-dispatcher", daemon=True
        )
        self._thread.start()
        logger.info(
            "[EventDispatcher] 已启动 (interval=%ss, publishers=%s)",
            self.poll_interval, self.registry.publisher_app_ids,
        )
        return True

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.dispatch_once()
            except Exception:  # noqa: BLE001 - 后台线程绝不因单轮异常退出
                logger.exception("[EventDispatcher] dispatch_once 异常")
            self._stop_event.wait(self.poll_interval)


_default_dispatcher: Optional[EventDispatcher] = None


def start_event_dispatcher() -> Optional[EventDispatcher]:
    """启动全局 Dispatcher。契约注册表为空（无应用声明 events）时不启动 → legacy 零变化。"""
    global _default_dispatcher
    registry = get_event_contract_registry()
    if registry.is_empty:
        logger.debug("[EventDispatcher] 无事件契约 → 不启动")
        return None
    if _default_dispatcher is None:
        _default_dispatcher = EventDispatcher(registry)
    _default_dispatcher.start()
    return _default_dispatcher


def stop_event_dispatcher() -> None:
    global _default_dispatcher
    if _default_dispatcher is not None:
        _default_dispatcher.stop()


def get_event_dispatcher() -> Optional[EventDispatcher]:
    return _default_dispatcher