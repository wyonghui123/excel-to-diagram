# -*- coding: utf-8 -*-
"""
[V007.15 L6] 可观测性基础设施 (Prometheus + 结构化日志)

提供:
- 19 Prometheus counters + 1 gauge
- 1 AuditRetryWrapper (L4)
- 1 metrics_inc() / log_tx_event() helper
- Lazy import Prometheus (无硬依赖, fallback to log)
"""
import logging
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Counter dict (lazy)
_prometheus_counters: Dict[str, any] = {}

OBS_COUNTERS = {
    # commit/rollback
    'commit_success': 'v007_15_commit_success_total',
    'commit_failure': 'v007_15_commit_failure_total',
    'rollback_success': 'v007_15_rollback_success_total',
    'rollback_failure': 'v007_15_rollback_failure_total',
    'forced_rollback_after_commit': 'v007_15_forced_rollback_after_commit_total',
    'forced_rollback_after_rollback': 'v007_15_forced_rollback_after_rollback_total',
    # begin_transaction
    'begin_success': 'v007_15_begin_success_total',
    'begin_skipped_already_in_tx': 'v007_15_begin_skipped_already_in_tx_total',
    'begin_locked': 'v007_15_begin_locked_total',
    'phantom_tx_detected': 'v007_15_phantom_tx_detected_total',
    # audit
    'audit_write_success': 'v007_15_audit_write_success_total',
    'audit_write_failure': 'v007_15_audit_write_failure_total',
    'audit_write_exhausted': 'v007_15_audit_write_exhausted_total',
    # [V007.15 L4.5] audit async queue
    'audit_async_enqueued': 'v007_15_audit_async_enqueued_total',
    'audit_async_flushed': 'v007_15_audit_async_flushed_total',
    'audit_async_failed': 'v007_15_audit_async_failed_total',
    'audit_async_batch_count': 'v007_15_audit_async_batch_count_total',
    'audit_async_dropped_queue_full': 'v007_15_audit_async_dropped_queue_full_total',
    # orphan detector
    'orphan_detector_runs': 'v007_15_orphan_detector_runs_total',
    'orphan_detector_clean': 'v007_15_orphan_detector_clean_total',
    'orphan_recovered': 'v007_15_orphan_recovered_total',
    'orphan_app_state_pollution': 'v007_15_orphan_app_state_pollution_total',
    # state
    'runtime_state': 'v007_15_runtime_state_info',
    # [V007.24] DataSource 缓存 (fd 泄漏检测)
    'pool_init_count': 'v007_24_pool_init_count',
    'pool_init_leak_warning': 'v007_24_pool_init_leak_warning_total',
}


def _get_prometheus_counter(name: str):
    if name in _prometheus_counters:
        return _prometheus_counters[name]
    try:
        from prometheus_client import Counter, Gauge
        if name == OBS_COUNTERS['runtime_state']:
            obj = Gauge(name, 'V007.15 runtime state code (0=A,1=B,2=C,3=UNKNOWN)')
        else:
            obj = Counter(name, f'V007.15 metric: {name}')
        _prometheus_counters[name] = obj
        return obj
    except ImportError:
        return None


def metrics_inc(counter_key: str, value: int = 1):
    if counter_key not in OBS_COUNTERS:
        return
    if counter_key == 'runtime_state':
        return  # 用 metrics_set_state
    name = OBS_COUNTERS[counter_key]
    counter = _get_prometheus_counter(name)
    if counter is not None:
        try:
            counter.inc(value)
        except Exception:
            pass


def metrics_set_state(state_code: int):
    """0=A, 1=B, 2=C, 3=UNKNOWN"""
    gauge = _get_prometheus_counter(OBS_COUNTERS['runtime_state'])
    if gauge is not None:
        try:
            gauge.set(state_code)
        except Exception:
            pass


def log_tx_event(event_type: str, tx_id: Optional[str], status: str, detail: Optional[str]):
    """结构化日志, 总是输出 (不管 Prometheus 是否可用)"""
    extra = {
        'event_type': event_type,
        'tx_id': tx_id,
        'status': status,
        'detail': detail[:500] if detail else None,
    }
    msg = f"[V007.15] {event_type} tx_id={tx_id} status={status}"
    if detail:
        msg += f" detail={detail[:200]}"
    if status in ('error', 'recovered', 'failed', 'exhausted'):
        logger.error(msg, extra=extra)
    elif status in ('locked', 'forced_rollback', 'retry'):
        logger.warning(msg, extra=extra)
    else:
        logger.info(msg, extra=extra)


# [V007.15 L4 包装] Audit retry wrapper
class AuditRetryWrapper:
    """包装 audit_service.create, 加 state-aware retry (不改 audit_service.py)"""
    def __init__(self, audit_service):
        self.audit = audit_service

    def create_with_retry(self, record: dict, critical: bool = True) -> bool:
        from meta.core.db_config_detector import get_runtime_config
        config = get_runtime_config()
        max_retries = config.audit_retry_max if critical else 0
        last_err = None
        for attempt in range(max_retries + 1):
            try:
                self.audit.create(record)
                metrics_inc(OBS_COUNTERS['audit_write_success'])
                return True
            except Exception as e:
                err = str(e).lower()
                last_err = e
                if ("locked" in err or "busy" in err) and attempt < max_retries:
                    backoff = 0.1 * (2 ** attempt) * (config.busy_timeout_ms // 5000)
                    log_tx_event(
                        'audit', str(record.get('id', '')),
                        'retry', f"attempt={attempt}, backoff={backoff:.2f}s, err={err}"
                    )
                    time.sleep(backoff)
                    continue
                metrics_inc(OBS_COUNTERS['audit_write_failure'])
                if critical:
                    log_tx_event('audit', str(record.get('id', '')), 'failed', str(e))
                    raise
                return False
        metrics_inc(OBS_COUNTERS['audit_write_exhausted'])
        log_tx_event('audit', str(record.get('id', '')), 'exhausted', str(last_err))
        return False
