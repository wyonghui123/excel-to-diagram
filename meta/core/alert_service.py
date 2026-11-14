# -*- coding: utf-8 -*-
"""[FR-009] 统一告警服务

把系统错误/异常事件按「去重 → 聚合 → 阈值 → 渠道」处理，并送达运维。

核心语义（对齐 Alertmanager）：
- fingerprint = error_code + endpoint/object_type，**不含 trace_id**
- group_wait=30s      同组首条最多等待聚合
- group_interval=5m   同组新增/恢复的最短重发间隔
- repeat_interval=4h  持续未恢复才重复提醒
- 状态机 open → resolved；恢复后不再提醒
- 限流：单 fingerprint ≤20/min；平台 100/min、5/s、单条 ≤20KB
- 渠道：飞书自定义机器人 webhook（topic=system_alert，独立于业务事件）
- 无渠道/失败：降级 error 日志 + /ops/alerts 可查；重试退避 1/5/15min ±20%，3 次后 dead_letter

设计约束：
- 所有 DB 操作 best-effort，任何异常都不得影响主请求；
- 发送在后台线程/显式 flush 中完成，report() 不阻塞请求；
- 时间以 float 时间戳参与判定，DB 中存 ISO 字符串便于运维查询。
"""
from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from meta.core.observability import metrics_alert_inc, metrics_error_inc

logger = logging.getLogger(__name__)

# ── 可调参数（环境变量便于测试/运维） ─────────────────────────────────────
GROUP_WAIT_SECONDS = float(os.environ.get('ALERT_GROUP_WAIT', '30'))
GROUP_INTERVAL_SECONDS = float(os.environ.get('ALERT_GROUP_INTERVAL', '300'))
REPEAT_INTERVAL_SECONDS = float(os.environ.get('ALERT_REPEAT_INTERVAL', '14400'))
PER_FINGERPRINT_PER_MINUTE = int(os.environ.get('ALERT_FP_LIMIT_PER_MINUTE', '20'))
PLATFORM_PER_MINUTE = int(os.environ.get('ALERT_PLATFORM_PER_MINUTE', '100'))
PLATFORM_PER_SECOND = int(os.environ.get('ALERT_PLATFORM_PER_SECOND', '5'))
MAX_PAYLOAD_BYTES = int(os.environ.get('ALERT_MAX_PAYLOAD_BYTES', '20480'))
MAX_ATTEMPTS = int(os.environ.get('ALERT_MAX_ATTEMPTS', '3'))
RETRY_BACKOFF_SECONDS = (60.0, 300.0, 900.0)
RETENTION_DAYS = int(os.environ.get('ALERT_RETENTION_DAYS', '30'))
FLUSH_INTERVAL_SECONDS = float(os.environ.get('ALERT_FLUSH_INTERVAL', '1'))
TOPIC = 'system_alert'

TABLE_DDL = """
CREATE TABLE IF NOT EXISTS system_alert_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT NOT NULL UNIQUE,
    error_code TEXT NOT NULL,
    endpoint TEXT,
    object_type TEXT,
    level TEXT NOT NULL DEFAULT 'error',
    status TEXT NOT NULL DEFAULT 'open',
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    resolved_at TEXT,
    count INTEGER NOT NULL DEFAULT 0,
    pending_count INTEGER NOT NULL DEFAULT 0,
    sample_trace_id TEXT,
    last_message TEXT,
    delivery_status TEXT,
    delivery_attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    next_retry_at REAL,
    last_notified_at REAL,
    deliveries INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

INDEX_DDL = (
    'CREATE INDEX IF NOT EXISTS idx_system_alert_status '
    'ON system_alert_log(status, last_seen)'
)


def _now_iso(ts: Optional[float] = None) -> str:
    return datetime.fromtimestamp(ts if ts is not None else time.time()).isoformat(timespec='seconds')


def _fingerprint(error_code: str, endpoint: Optional[str], object_type: Optional[str]) -> str:
    scope = endpoint or object_type or 'unknown'
    return f'{error_code}::{scope}'


def _enabled() -> bool:
    return os.environ.get('ALERT_ENABLED', '1').lower() not in ('0', 'false', 'no', 'off')


def _webhook_url() -> str:
    for key in ('ALERT_FEISHU_WEBHOOK', 'FEISHU_ALERT_WEBHOOK', 'FEISHU_WEBHOOK_URL'):
        value = os.environ.get(key)
        if value:
            return value
    return ''


@dataclass
class AlertGroup:
    fingerprint: str
    error_code: str
    endpoint: Optional[str]
    object_type: Optional[str]
    level: str = 'error'
    status: str = 'open'
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    count: int = 0
    pending_count: int = 0
    sample_trace_id: Optional[str] = None
    last_message: str = ''
    delivery_status: str = ''
    delivery_attempts: int = 0
    last_error: str = ''
    next_retry_at: Optional[float] = None
    last_notified_at: Optional[float] = None
    deliveries: int = 0
    sent_timestamps: List[float] = field(default_factory=list)


class AlertService:
    """进程内告警聚合器（单例）。线程安全。"""

    def __init__(self):
        self._lock = threading.RLock()
        self._groups: Dict[str, AlertGroup] = {}
        self._platform_sends: List[float] = []
        self._flusher_started = False
        self._last_cleanup = 0.0
        self._table_ready = False

    # ── 数据源 ────────────────────────────────────────────────────────────
    def _ds(self):
        try:
            from meta.core.datasource import get_platform_data_source
            return get_platform_data_source()
        except Exception as e:  # pragma: no cover - 降级路径
            logger.debug('[Alert] data source unavailable: %s', e)
            return None

    def _ensure_table(self, ds) -> None:
        if self._table_ready or ds is None:
            return
        try:
            ds.execute(TABLE_DDL)
            ds.execute(INDEX_DDL)
            self._table_ready = True
        except Exception as e:
            logger.warning('[Alert] create table failed: %s', e)

    # ── 上报 ──────────────────────────────────────────────────────────────
    def report(self, error_code: str, endpoint: Optional[str] = None,
               object_type: Optional[str] = None, message: str = '',
               trace_id: Optional[str] = None, level: str = 'error') -> Optional[str]:
        """记录一次错误事件，返回 fingerprint。不阻塞、不抛异常。"""
        if not _enabled() or not error_code:
            return None
        metrics_error_inc(error_code, endpoint or object_type)
        fp = _fingerprint(error_code, endpoint, object_type)
        now = time.time()
        try:
            with self._lock:
                group = self._groups.get(fp)
                if group is None:
                    group = AlertGroup(
                        fingerprint=fp, error_code=error_code,
                        endpoint=endpoint, object_type=object_type,
                        level=level, first_seen=now,
                    )
                    self._groups[fp] = group
                group.last_seen = now
                group.count += 1
                group.pending_count += 1
                group.level = level or group.level
                if message:
                    group.last_message = message[:1000]
                if trace_id:
                    group.sample_trace_id = trace_id
                if group.status == 'resolved':
                    # 恢复后再次出现视为新事件，重新计时
                    group.status = 'open'
                    group.resolved_at = None
                    group.first_seen = now
                    group.last_notified_at = None
                    group.pending_count = group.count
            self._persist(group)
            self._ensure_flusher()
        except Exception as e:  # pragma: no cover - 防御
            logger.warning('[Alert] report failed: %s', e)
        return fp

    def resolve(self, fingerprint: Optional[str] = None, error_code: Optional[str] = None,
                endpoint: Optional[str] = None) -> bool:
        if not _enabled():
            return False
        fp = fingerprint or _fingerprint(error_code or '', endpoint, None)
        with self._lock:
            group = self._groups.get(fp)
            if group is None:
                return False
            group.status = 'resolved'
            group.resolved_at = time.time()
            group.pending_count = 0
            group.next_retry_at = None
            group.delivery_status = 'resolved'
        self._persist(group)
        logger.info('[Alert] resolved fingerprint=%s', fp)
        return True

    # ── 聚合/发送 ─────────────────────────────────────────────────────────
    def flush(self, now: Optional[float] = None, force: bool = False) -> int:
        """处理到期的分组聚合与重试，返回发送条数。"""
        now = now if now is not None else time.time()
        sent = 0
        due: List[AlertGroup] = []
        with self._lock:
            for group in self._groups.values():
                if group.status != 'open':
                    continue
                if group.next_retry_at is not None and now >= group.next_retry_at:
                    due.append(group)
                    continue
                if group.pending_count <= 0:
                    continue
                waited = now - group.first_seen
                if not force and waited < GROUP_WAIT_SECONDS:
                    continue
                if group.last_notified_at is not None:
                    gap = now - group.last_notified_at
                    if not force and gap < GROUP_INTERVAL_SECONDS:
                        continue
                    if gap < REPEAT_INTERVAL_SECONDS:
                        # 未到 repeat_interval，仅吞掉待发计数
                        group.pending_count = 0
                        continue
                due.append(group)
        for group in due:
            if self._deliver(group, now=now, force=force):
                sent += 1
        self._maybe_cleanup(now)
        return sent

    def _deliver(self, group: AlertGroup, now: float, force: bool = False) -> bool:
        with self._lock:
            # 单 fingerprint 限流（滑动 60s）
            group.sent_timestamps = [t for t in group.sent_timestamps if now - t < 60]
            if len(group.sent_timestamps) >= PER_FINGERPRINT_PER_MINUTE:
                metrics_alert_inc('none', 'rate_limited')
                logger.warning('[Alert] fingerprint rate limited: %s', group.fingerprint)
                group.delivery_status = 'rate_limited'
                group.next_retry_at = now + 60
                group.pending_count = 0
                target = group
                should_persist = True
            else:
                should_persist = False
                target = group
            # 平台限流（100/min、5/s）
            self._platform_sends = [t for t in self._platform_sends if now - t < 60]
            last_second = [t for t in self._platform_sends if now - t < 1]
            if len(self._platform_sends) >= PLATFORM_PER_MINUTE or len(last_second) >= PLATFORM_PER_SECOND:
                metrics_alert_inc('feishu', 'rate_limited')
                logger.error('[Alert] platform rate limited, degrade to log: %s', group.fingerprint)
                group.delivery_status = 'rate_limited'
                group.next_retry_at = now + 60
                target = group
                should_persist = True
            else:
                self._platform_sends.append(now)
                group.sent_timestamps.append(now)
        if should_persist:
            self._persist(target)
            return False

        text = self._format_message(group)
        channel, error = self._send(text)
        with self._lock:
            group.deliveries += 1
            group.last_notified_at = now
            group.pending_count = 0
            group.last_error = error or ''
            if error:
                group.delivery_attempts += 1
                if group.delivery_attempts >= MAX_ATTEMPTS:
                    group.delivery_status = 'dead_letter'
                    group.next_retry_at = None
                    metrics_alert_inc(channel, 'dead_letter')
                    logger.error(
                        '[Alert] dead letter after %d attempts: %s',
                        group.delivery_attempts, group.fingerprint)
                else:
                    group.delivery_status = 'retrying'
                    group.next_retry_at = now + self._backoff(group.delivery_attempts)
                    metrics_alert_inc(channel, 'failed')
            else:
                group.delivery_attempts = 0
                group.next_retry_at = None
                group.delivery_status = 'sent' if channel == 'feishu' else 'logged'
                metrics_alert_inc(channel, 'sent')
        self._persist(group)
        return True

    def _backoff(self, attempt: int) -> float:
        base = RETRY_BACKOFF_SECONDS[min(max(attempt - 1, 0), len(RETRY_BACKOFF_SECONDS) - 1)]
        return base * random.uniform(0.8, 1.2)

    def _format_message(self, group: AlertGroup) -> str:
        scope = group.endpoint or group.object_type or 'unknown'
        lines = [
            f'[{TOPIC}][{group.level.upper()}] {group.error_code}',
            f'fingerprint: {group.fingerprint}',
            f'scope: {scope}',
            f'count: {group.count}',
            f'first_seen: {_now_iso(group.first_seen)}',
            f'last_seen: {_now_iso(group.last_seen)}',
        ]
        if group.sample_trace_id:
            lines.append(f'sample_trace_id: {group.sample_trace_id}')
        if group.last_message:
            lines.append(f'message: {group.last_message}')
        text = '\n'.join(lines)
        return self._truncate(text)

    @staticmethod
    def _truncate(text: str) -> str:
        raw = text.encode('utf-8')
        if len(raw) <= MAX_PAYLOAD_BYTES:
            return text
        return raw[: MAX_PAYLOAD_BYTES - 64].decode('utf-8', errors='ignore') + '\n...(truncated)'

    def _send(self, text: str) -> Tuple[str, Optional[str]]:
        """返回 (channel, error)。error 为 None 表示成功。"""
        payload = json.dumps({
            'msg_type': 'text',
            'content': {'text': text},
        }, ensure_ascii=False).encode('utf-8')
        if len(payload) > MAX_PAYLOAD_BYTES:
            payload = json.dumps({
                'msg_type': 'text',
                'content': {'text': self._truncate(text)},
            }, ensure_ascii=False).encode('utf-8')
        url = _webhook_url()
        if not url:
            logger.error('[Alert][degraded] %s', text)
            return 'log', None
        try:
            req = urllib.request.Request(
                url, data=payload,
                headers={'Content-Type': 'application/json; charset=utf-8'},
                method='POST',
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                body = resp.read(512).decode('utf-8', errors='ignore')
            if resp.status >= 300:
                return 'feishu', f'HTTP {resp.status}: {body[:200]}'
            return 'feishu', None
        except Exception as e:
            logger.error('[Alert] feishu delivery failed: %s', e)
            return 'feishu', str(e)[:300]

    # ── 持久化 ────────────────────────────────────────────────────────────
    def _persist(self, group: AlertGroup) -> None:
        ds = self._ds()
        if ds is None:
            return
        self._ensure_table(ds)
        try:
            ds.execute(
                """INSERT INTO system_alert_log (
                    fingerprint, error_code, endpoint, object_type, level, status,
                    first_seen, last_seen, resolved_at, count, pending_count,
                    sample_trace_id, last_message, delivery_status, delivery_attempts,
                    last_error, next_retry_at, last_notified_at, deliveries,
                    created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(fingerprint) DO UPDATE SET
                    error_code=excluded.error_code,
                    endpoint=excluded.endpoint,
                    object_type=excluded.object_type,
                    level=excluded.level,
                    status=excluded.status,
                    last_seen=excluded.last_seen,
                    resolved_at=excluded.resolved_at,
                    count=excluded.count,
                    pending_count=excluded.pending_count,
                    sample_trace_id=excluded.sample_trace_id,
                    last_message=excluded.last_message,
                    delivery_status=excluded.delivery_status,
                    delivery_attempts=excluded.delivery_attempts,
                    last_error=excluded.last_error,
                    next_retry_at=excluded.next_retry_at,
                    last_notified_at=excluded.last_notified_at,
                    deliveries=excluded.deliveries,
                    updated_at=excluded.updated_at
                """,
                (
                    group.fingerprint, group.error_code, group.endpoint, group.object_type,
                    group.level, group.status,
                    _now_iso(group.first_seen), _now_iso(group.last_seen),
                    _now_iso(group.resolved_at) if group.resolved_at else None,
                    group.count, group.pending_count, group.sample_trace_id,
                    group.last_message, group.delivery_status, group.delivery_attempts,
                    group.last_error, group.next_retry_at, group.last_notified_at,
                    group.deliveries, _now_iso(group.first_seen), _now_iso(),
                ),
            )
        except Exception as e:
            logger.warning('[Alert] persist failed: %s', e)

    def _maybe_cleanup(self, now: float) -> None:
        if now - self._last_cleanup < 3600:
            return
        self._last_cleanup = now
        ds = self._ds()
        if ds is None:
            return
        cutoff = (datetime.now() - timedelta(days=RETENTION_DAYS)).isoformat(timespec='seconds')
        try:
            ds.execute(
                'DELETE FROM system_alert_log WHERE status = ? AND last_seen < ?',
                ('resolved', cutoff),
            )
        except Exception as e:
            logger.debug('[Alert] cleanup failed: %s', e)

    # ── 后台线程 ──────────────────────────────────────────────────────────
    def _ensure_flusher(self) -> None:
        if self._flusher_started:
            return
        if os.environ.get('ALERT_FLUSHER_AUTOSTART', '1').lower() in ('0', 'false', 'no'):
            return
        with self._lock:
            if self._flusher_started:
                return
            self._flusher_started = True
        thread = threading.Thread(target=self._flusher_loop, name='alert-flusher', daemon=True)
        thread.start()

    def _flusher_loop(self) -> None:
        while True:
            try:
                self.flush()
            except Exception as e:  # pragma: no cover
                logger.warning('[Alert] flush loop error: %s', e)
            time.sleep(FLUSH_INTERVAL_SECONDS)

    # ── 运维查询 ──────────────────────────────────────────────────────────
    def list_alerts(self, status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        ds = self._ds()
        if ds is not None:
            self._ensure_table(ds)
            try:
                sql = ('SELECT * FROM system_alert_log '
                       + ('WHERE status = ? ' if status else '')
                       + 'ORDER BY last_seen DESC LIMIT ?')
                params = ((status, limit) if status else (limit,))
                cursor = ds.execute(sql, params)
                rows = cursor.fetchall() if cursor is not None else []
                return [dict(row) if not isinstance(row, dict) else row for row in rows]
            except Exception as e:
                logger.warning('[Alert] list failed: %s', e)
        with self._lock:
            items = [g for g in self._groups.values() if status is None or g.status == status]
        items.sort(key=lambda g: g.last_seen, reverse=True)
        return [self._as_dict(g) for g in items[:limit]]

    @staticmethod
    def _as_dict(group: AlertGroup) -> Dict[str, Any]:
        return {
            'fingerprint': group.fingerprint,
            'error_code': group.error_code,
            'endpoint': group.endpoint,
            'object_type': group.object_type,
            'level': group.level,
            'status': group.status,
            'first_seen': _now_iso(group.first_seen),
            'last_seen': _now_iso(group.last_seen),
            'resolved_at': _now_iso(group.resolved_at) if group.resolved_at else None,
            'count': group.count,
            'pending_count': group.pending_count,
            'sample_trace_id': group.sample_trace_id,
            'last_message': group.last_message,
            'delivery_status': group.delivery_status,
            'delivery_attempts': group.delivery_attempts,
            'last_error': group.last_error,
            'deliveries': group.deliveries,
        }

    def replay(self, alert_id: Optional[int] = None, fingerprint: Optional[str] = None) -> bool:
        """把 dead_letter/已停止的告警重新置为待发送。"""
        fp = fingerprint
        if fp is None and alert_id is not None:
            for row in self.list_alerts(limit=1000):
                if row.get('id') == alert_id:
                    fp = row.get('fingerprint')
                    break
        if not fp:
            return False
        with self._lock:
            group = self._groups.get(fp)
            if group is None:
                return False
            group.status = 'open'
            group.delivery_status = 'retrying'
            group.delivery_attempts = 0
            group.next_retry_at = time.time()
            group.pending_count = max(group.pending_count, 1)
        self._persist(group)
        return True

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            groups = list(self._groups.values())
        return {
            'open': sum(1 for g in groups if g.status == 'open'),
            'resolved': sum(1 for g in groups if g.status == 'resolved'),
            'dead_letter': sum(1 for g in groups if g.delivery_status == 'dead_letter'),
            'channel_configured': bool(_webhook_url()),
            'group_wait_seconds': GROUP_WAIT_SECONDS,
            'group_interval_seconds': GROUP_INTERVAL_SECONDS,
            'repeat_interval_seconds': REPEAT_INTERVAL_SECONDS,
        }


_service: Optional[AlertService] = None
_service_lock = threading.Lock()


def get_alert_service() -> AlertService:
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = AlertService()
    return _service


# ── 模块级便捷函数（供 error_handlers / 调度器 / 监控调用） ─────────────────
def report_alert(error_code: str, endpoint: Optional[str] = None,
                 object_type: Optional[str] = None, message: str = '',
                 trace_id: Optional[str] = None, level: str = 'error') -> Optional[str]:
    try:
        return get_alert_service().report(
            error_code, endpoint=endpoint, object_type=object_type,
            message=message, trace_id=trace_id, level=level,
        )
    except Exception as e:  # pragma: no cover
        logger.warning('[Alert] report_alert failed: %s', e)
        return None


def resolve_alert(fingerprint: Optional[str] = None, error_code: Optional[str] = None,
                  endpoint: Optional[str] = None) -> bool:
    try:
        return get_alert_service().resolve(fingerprint, error_code, endpoint)
    except Exception:
        return False


def flush_alerts(now: Optional[float] = None, force: bool = False) -> int:
    try:
        return get_alert_service().flush(now=now, force=force)
    except Exception as e:  # pragma: no cover
        logger.warning('[Alert] flush_alerts failed: %s', e)
        return 0


def list_alerts(status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    return get_alert_service().list_alerts(status=status, limit=limit)


def replay_alert(alert_id: Optional[int] = None, fingerprint: Optional[str] = None) -> bool:
    return get_alert_service().replay(alert_id=alert_id, fingerprint=fingerprint)


def alert_stats() -> Dict[str, Any]:
    return get_alert_service().stats()


def start_alert_flusher() -> None:
    """应用启动时显式拉起后台聚合/重试线程（幂等）。"""
    try:
        get_alert_service()._ensure_flusher()
    except Exception as e:  # pragma: no cover
        logger.warning('[Alert] start flusher failed: %s', e)


def reset_alert_service() -> None:
    """仅测试使用：清空内存状态。"""
    global _service
    with _service_lock:
        _service = AlertService()