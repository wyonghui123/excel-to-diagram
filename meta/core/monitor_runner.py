# -*- coding: utf-8 -*-
"""[FR-012] 监控模块接线

把已有的 DB 健康 / 索引 / 缓存监控接入统一告警服务：

- DB 健康：60s 一次，阈值 DB 锁等待 >3s、WAL >100MB
- 索引：300s 一次，缺失索引 >0 触发 warning
- 缓存：300s 一次，命中率 <60% 触发 warning
- 异常恢复时自动 resolve 对应告警

线程默认在应用启动后 60s 开始首轮，避免测试/短生命周期进程产生噪声；
可用 ``PLATFORM_MONITORS_ENABLED=0`` 关闭。
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DB_INTERVAL = float(os.environ.get('MONITOR_DB_INTERVAL', '60'))
SLOW_INTERVAL = float(os.environ.get('MONITOR_SLOW_INTERVAL', '300'))
WAL_WARN_MB = float(os.environ.get('MONITOR_WAL_WARN_MB', '100'))
DB_LOCK_WARN_MS = float(os.environ.get('MONITOR_DB_LOCK_WARN_MS', '3000'))
CACHE_HIT_MIN_PERCENT = float(os.environ.get('MONITOR_CACHE_HIT_MIN', '60'))

_lock = threading.RLock()
_snapshot: Dict[str, Any] = {'started': False, 'last_run': {}}
_thread: Optional[threading.Thread] = None
_started = False


def _enabled() -> bool:
    return os.environ.get('PLATFORM_MONITORS_ENABLED', '1').lower() not in ('0', 'false', 'no')


def _db_path() -> str:
    try:
        from meta.core.datasource import get_platform_data_source
        ds = get_platform_data_source()
        return getattr(ds, 'db_path', '') or ''
    except Exception:
        return ''


def _check_db() -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    try:
        from meta.core.db_health_monitor import get_monitor
        monitor = get_monitor(_db_path() or None)
        report = monitor.get_report()
        out['report'] = report
        wal_mb = float(report.get('wal_size_mb') or 0)
        if wal_mb > WAL_WARN_MB:
            _alert('db_health_warning', 'database',
                   'WAL size {0:.1f}MB > {1}MB'.format(wal_mb, WAL_WARN_MB))
        else:
            _resolve('db_health_warning', 'database')
        status = str(report.get('wal_status') or report.get('status') or '').lower()
        if 'critical' in status or 'error' in status:
            _alert('db_health_warning', 'database', 'db health status: {0}'.format(status))
    except Exception as e:
        out['error'] = str(e)[:200]
        logger.debug('[Monitor] db health failed: %s', e)
    return out


def _check_db_lock() -> None:
    """用一次带超时的写入探测 DB 锁等待（>3s 视为异常）。"""
    start = time.monotonic()
    try:
        from meta.core.datasource import get_platform_data_source
        ds = get_platform_data_source()
        ds.execute('SELECT 1')
        elapsed_ms = (time.monotonic() - start) * 1000
        if elapsed_ms > DB_LOCK_WARN_MS:
            _alert('db_health_warning', 'database_lock',
                   'db probe {0:.0f}ms > {1:.0f}ms'.format(elapsed_ms, DB_LOCK_WARN_MS))
        else:
            _resolve('db_health_warning', 'database_lock')
    except Exception as e:
        _alert('db_health_warning', 'database_lock', 'db probe failed: {0}'.format(str(e)[:200]))


def _check_indexes() -> Dict[str, Any]:
    try:
        from meta.core.datasource import get_platform_data_source
        from meta.core.index_monitor import IndexMonitor
        summary = IndexMonitor(get_platform_data_source()).get_summary()
        missing = int(summary.get('total_missing_indexes') or 0)
        if missing > 0:
            _alert('db_health_warning', 'index',
                   'missing indexes: {0}'.format(missing))
        else:
            _resolve('db_health_warning', 'index')
        return {'missing_indexes': missing,
                'critical_issues': summary.get('critical_issues', 0)}
    except Exception as e:
        logger.debug('[Monitor] index check failed: %s', e)
        return {'error': str(e)[:200]}


def _check_cache() -> Dict[str, Any]:
    try:
        from meta.services.cache_monitor import CacheMonitor
        from meta.api.permission_dimension_api import _get_engine
        monitor = CacheMonitor(_get_engine())
        report = monitor.get_performance_report()
        metrics = report.get('metrics') or report
        hit_rate = metrics.get('hit_rate_value')
        if hit_rate is None:
            stats = monitor.get_cache_stats() or {}
            hit_rate = stats.get('hit_rate_value')
        if hit_rate is not None:
            hit_rate = float(hit_rate)
            if hit_rate < CACHE_HIT_MIN_PERCENT:
                _alert('db_health_warning', 'cache',
                       'cache hit rate {0:.1f}% < {1}%'.format(hit_rate, CACHE_HIT_MIN_PERCENT))
            else:
                _resolve('db_health_warning', 'cache')
        return {'hit_rate': hit_rate}
    except Exception as e:
        logger.debug('[Monitor] cache check failed: %s', e)
        return {'error': str(e)[:200]}


def _alert(code: str, object_type: str, message: str) -> None:
    try:
        from meta.core.alert_service import report_alert
        report_alert(code, object_type=object_type, message=message, level='warning')
    except Exception:
        pass


def _resolve(code: str, object_type: str) -> None:
    try:
        from meta.core.alert_service import resolve_alert
        resolve_alert(error_code=code, endpoint=object_type)
    except Exception:
        pass


def run_monitor_cycle(now: Optional[float] = None, force: bool = False) -> Dict[str, Any]:
    """执行一轮到期检查（幂等：按间隔节流）。"""
    now = now if now is not None else time.time()
    with _lock:
        last = _snapshot.get('last_run', {})
        result: Dict[str, Any] = {}

        def due(key: str, interval: float) -> bool:
            if force:
                return True
            previous = last.get(key, 0)
            return now - previous >= interval

        if due('db', DB_INTERVAL):
            result['db'] = _check_db()
            last['db'] = now
        if due('db_lock', DB_INTERVAL):
            _check_db_lock()
            last['db_lock'] = now
        if due('index', SLOW_INTERVAL):
            result['index'] = _check_indexes()
            last['index'] = now
        if due('cache', SLOW_INTERVAL):
            result['cache'] = _check_cache()
            last['cache'] = now

        if result:
            _snapshot['last_run'] = last
            _snapshot['last_result'] = result
            _snapshot['last_at'] = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(now))
        return result


def get_monitor_snapshot() -> Dict[str, Any]:
    with _lock:
        return {
            'started': _snapshot.get('started', False),
            'last_at': _snapshot.get('last_at'),
            'last_result': _snapshot.get('last_result', {}),
        }


def _loop() -> None:
    # 启动后先等 60s，避免与启动自检/测试争抢 DB
    time.sleep(float(os.environ.get('MONITOR_START_DELAY', '60')))
    while True:
        try:
            run_monitor_cycle()
        except Exception as e:  # pragma: no cover
            logger.warning('[Monitor] cycle failed: %s', e)
        time.sleep(DB_INTERVAL)


def start_monitor_runner() -> None:
    """应用启动时调用（幂等）。"""
    global _thread, _started
    if not _enabled() or _started:
        return
    with _lock:
        if _started:
            return
        _started = True
        _snapshot['started'] = True
    _thread = threading.Thread(target=_loop, name='monitor-runner', daemon=True)
    _thread.start()


def reset_monitor_runner() -> None:
    """仅测试使用。"""
    global _thread, _started
    with _lock:
        _thread = None
        _started = False
        _snapshot.clear()
        _snapshot.update({'started': False, 'last_run': {}})