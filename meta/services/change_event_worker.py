# -*- coding: utf-8 -*-
"""变更事件异步派发 worker（P1-d）。

职责：
    - 周期性轮询 change_events 中 status='pending' 的事件，按 id 升序交给
      ChangeEventDispatcher 派发（发布侧只写库，不再内联阻塞业务事务）。
    - 周期性调用 dispatcher.retry_due_deliveries 推进到期的自动重试。

调度节奏：
    - 有待处理事件：poll_interval（默认 2s）
    - 空闲：idle_interval（默认 10s，退避降低空轮询开销）
    - 自动重试：retry_interval（默认 30s）

开关：
    META_CHANGE_EVENT_WORKER=off 时 is_worker_enabled() 返回 False；
    测试态由 meta/tests/shared/env_flags.py 统一注入 off，用例直接调用 dispatch。
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, Optional

from meta.services.change_event_dispatcher import ChangeEventDispatcher

logger = logging.getLogger(__name__)

WORKER_ENABLED_ENV = 'META_CHANGE_EVENT_WORKER'
EVENTS_TABLE = 'change_events'

DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_IDLE_INTERVAL = 10.0
DEFAULT_RETRY_INTERVAL = 30.0
DEFAULT_BATCH_SIZE = 50

_DISABLED_VALUES = ('0', 'off', 'false', 'no', 'disabled')


def is_worker_enabled(env_value: Optional[str] = None) -> bool:
    """判断是否启用异步派发 worker（默认启用）。"""
    value = env_value
    if value is None:
        value = os.environ.get(WORKER_ENABLED_ENV, '1')
    return str(value).strip().lower() not in _DISABLED_VALUES


class ChangeEventWorker:
    """单线程轮询派发器；一个进程只应启动一个实例。"""

    def __init__(
        self,
        data_source,
        dispatcher: Optional[ChangeEventDispatcher] = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        idle_interval: float = DEFAULT_IDLE_INTERVAL,
        retry_interval: float = DEFAULT_RETRY_INTERVAL,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ):
        self.ds = data_source
        self.dispatcher = dispatcher or ChangeEventDispatcher(data_source)
        self.poll_interval = float(poll_interval)
        self.idle_interval = float(idle_interval)
        self.retry_interval = float(retry_interval)
        self.batch_size = max(int(batch_size), 1)

        self._wake = threading.Event()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_retry = 0.0

    # ------------------------------------------------------------ lifecycle
    @property
    def is_running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """启动后台线程（幂等）。"""
        if self.is_running:
            return
        self._running = True
        self._wake.clear()
        self._thread = threading.Thread(
            target=self._loop, name='change-event-worker', daemon=True
        )
        self._thread.start()
        logger.info(
            "[change_event_worker] started: poll=%.1fs idle=%.1fs retry=%.1fs batch=%s",
            self.poll_interval, self.idle_interval, self.retry_interval, self.batch_size,
        )

    def stop(self, timeout: float = 5.0) -> None:
        """停止后台线程并等待退出。"""
        self._running = False
        self._wake.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self._thread = None
        logger.info("[change_event_worker] stopped")

    def notify(self, event_id: Optional[int] = None) -> None:
        """唤醒轮询线程（发布事件后调用，缩短空闲等待）。"""
        self._wake.set()

    # ----------------------------------------------------------- processing
    def run_once(self) -> Dict[str, Any]:
        """执行一轮：派发 pending 事件 + 到期的自动重试。"""
        processed = self.process_pending()
        retries = self.process_due_retries()
        return {'processed': processed, 'retries': retries}

    def process_pending(self) -> int:
        """派发一批 pending 事件，返回实际处理条数。"""
        try:
            rows = self.ds.find(
                EVENTS_TABLE,
                filters={'status': 'pending'},
                order_by='id ASC',
                limit=self.batch_size,
            ) or []
        except Exception as e:
            logger.warning("[change_event_worker] 查询 pending 事件失败: %s", e)
            return 0

        processed = 0
        for row in rows:
            event_id = int(row.get('id') or 0)
            if not event_id:
                continue
            try:
                event = self.dispatcher.normalize_event(row)
                self.dispatcher.dispatch(event_id, event)
                processed += 1
            except Exception as e:
                logger.warning(
                    "[change_event_worker] 派发失败: event_id=%s err=%s", event_id, e
                )
        return processed

    def process_due_retries(self, now: Optional[datetime] = None) -> Dict[str, int]:
        """执行到期的自动重试。"""
        try:
            return self.dispatcher.retry_due_deliveries(
                limit=self.batch_size, now=now
            )
        except Exception as e:
            logger.warning("[change_event_worker] 自动重试失败: %s", e)
            return {'events': 0, 'attempted': 0, 'delivered': 0, 'failed': 0, 'skipped': 0}

    def next_interval(self, processed: int) -> float:
        """根据本轮是否有事件决定下一轮等待时长（空闲退避）。"""
        return self.poll_interval if processed > 0 else self.idle_interval

    # ---------------------------------------------------------------- inner
    def _loop(self) -> None:
        while self._running:
            try:
                processed = self.process_pending()
                now = time.monotonic()
                if now - self._last_retry >= self.retry_interval:
                    self.process_due_retries()
                    self._last_retry = now
                interval = self.next_interval(processed)
            except Exception as e:  # 后台线程必须自愈，不能因单轮异常退出
                logger.warning("[change_event_worker] 轮询异常: %s", e)
                interval = self.idle_interval
            self._wake.wait(interval)
            self._wake.clear()


# ------------------------------------------------------------ process singleton
_ACTIVE_WORKER: Optional[ChangeEventWorker] = None
_WORKER_LOCK = threading.Lock()


def start_change_event_worker(data_source, **kwargs) -> Optional[ChangeEventWorker]:
    """启动进程级 worker；已启动则复用。META_CHANGE_EVENT_WORKER=off 时返回 None。"""
    global _ACTIVE_WORKER
    if not is_worker_enabled():
        return None
    with _WORKER_LOCK:
        if _ACTIVE_WORKER is not None and _ACTIVE_WORKER.is_running:
            return _ACTIVE_WORKER
        worker = ChangeEventWorker(data_source, **kwargs)
        worker.start()
        _ACTIVE_WORKER = worker
        return worker


def stop_change_event_worker() -> None:
    """停止进程级 worker（幂等）。"""
    global _ACTIVE_WORKER
    with _WORKER_LOCK:
        worker = _ACTIVE_WORKER
        _ACTIVE_WORKER = None
    if worker is not None:
        worker.stop()


def get_active_worker() -> Optional[ChangeEventWorker]:
    """返回当前进程内活跃 worker（诊断 / 测试用）。"""
    return _ACTIVE_WORKER


def notify_pending(event_id: Optional[int] = None) -> bool:
    """发布事件后唤醒 worker；未启动时静默返回 False（fail-open）。"""
    worker = _ACTIVE_WORKER
    if worker is None or not worker.is_running:
        return False
    worker.notify(event_id)
    return True