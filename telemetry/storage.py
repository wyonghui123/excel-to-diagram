"""
telemetry/storage.py - M14 v1.0.0 Trace 存储（Ring buffer）

特性：
- 内存 ring buffer（最近 1000 trace）
- 线程安全（threading.Lock）
- 慢请求检测（> threshold 自动记录到慢请求列表）
- 统计查询（p50 / p95 / p99 / 总耗时）

回滚：删除 telemetry/ 目录即可（不影响业务）
"""
import logging
import threading
import time
from collections import deque
from typing import Dict, List, Optional, Any
from statistics import quantiles

logger = logging.getLogger(__name__)


# 默认配置
DEFAULT_MAX_TRACES = 1000
DEFAULT_SLOW_THRESHOLD_MS = 100.0


class TraceStorage:
    """Trace 存储（线程安全 ring buffer）"""

    def __init__(self, max_traces: int = DEFAULT_MAX_TRACES, slow_threshold_ms: float = DEFAULT_SLOW_THRESHOLD_MS):
        self._traces: deque = deque(maxlen=max_traces)
        self._slow_traces: deque = deque(maxlen=200)  # 慢请求单独保留
        self._lock = threading.Lock()
        self._slow_threshold_ms = slow_threshold_ms
        self._start_time = time.time()

    def record(self, ctx) -> None:
        """记录一个 trace"""
        try:
            summary = ctx.end()
            with self._lock:
                self._traces.append(summary)
                # 慢请求检测
                if summary['duration_ms'] > self._slow_threshold_ms:
                    self._slow_traces.append({
                        **summary,
                        'detected_at': time.time(),
                    })
        except Exception as e:
            logger.error(f'[Telemetry] record error: {e}')

    def get_recent(self, limit: int = 50, offset: int = 0) -> List[Dict]:
        """获取最近 trace（按时间倒序）"""
        with self._lock:
            traces = list(self._traces)
        # 倒序
        traces.reverse()
        return traces[offset:offset + limit]

    def get_slow(self, limit: int = 20) -> List[Dict]:
        """获取慢请求列表"""
        with self._lock:
            traces = list(self._slow_traces)
        traces.reverse()
        return traces[:limit]

    def get_by_trace_id(self, trace_id: str) -> Optional[Dict]:
        """通过 trace_id 查询"""
        with self._lock:
            for t in self._traces:
                if t['trace_id'] == trace_id:
                    return t
        return None

    def get_stats(self) -> Dict:
        """获取统计信息

        Returns:
            {
                'total_traces': int,
                'slow_count': int,
                'p50_duration_ms': float,
                'p95_duration_ms': float,
                'p99_duration_ms': float,
                'max_duration_ms': float,
                'avg_duration_ms': float,
                'uptime_seconds': float,
            }
        """
        with self._lock:
            traces = list(self._traces)
            slow = list(self._slow_traces)

        if not traces:
            return {
                'total_traces': 0,
                'slow_count': 0,
                'p50_duration_ms': 0.0,
                'p95_duration_ms': 0.0,
                'p99_duration_ms': 0.0,
                'max_duration_ms': 0.0,
                'avg_duration_ms': 0.0,
                'uptime_seconds': time.time() - self._start_time,
            }

        durations = [t['duration_ms'] for t in traces]
        durations_sorted = sorted(durations)
        n = len(durations_sorted)

        # 百分位（用 quantiles 插值）
        try:
            quantiles_list = quantiles(durations_sorted, n=100, method='inclusive')
            p50 = quantiles_list[49] if len(quantiles_list) > 49 else durations_sorted[n // 2]
            p95 = quantiles_list[94] if len(quantiles_list) > 94 else durations_sorted[int(n * 0.95)]
            p99 = quantiles_list[98] if len(quantiles_list) > 98 else durations_sorted[int(n * 0.99)]
        except Exception:
            p50 = p95 = p99 = durations_sorted[n // 2]

        return {
            'total_traces': len(traces),
            'slow_count': len(slow),
            'p50_duration_ms': round(p50, 2),
            'p95_duration_ms': round(p95, 2),
            'p99_duration_ms': round(p99, 2),
            'max_duration_ms': round(max(durations), 2),
            'avg_duration_ms': round(sum(durations) / n, 2),
            'uptime_seconds': round(time.time() - self._start_time, 2),
        }

    def clear(self) -> None:
        """清空（测试用）"""
        with self._lock:
            self._traces.clear()
            self._slow_traces.clear()

    def configure(self, max_traces: int = None, slow_threshold_ms: float = None) -> None:
        """更新配置"""
        with self._lock:
            if max_traces is not None and max_traces != self._traces.maxlen:
                # 重建 deque 保留已有数据
                old = list(self._traces)
                self._traces = deque(old[-max_traces:], maxlen=max_traces)
            if slow_threshold_ms is not None:
                self._slow_threshold_ms = slow_threshold_ms


# ==================== 单例 ====================

_storage_instance: Optional[TraceStorage] = None
_storage_lock = threading.Lock()


def get_storage() -> TraceStorage:
    """获取全局存储单例"""
    global _storage_instance
    if _storage_instance is None:
        with _storage_lock:
            if _storage_instance is None:
                _storage_instance = TraceStorage()
    return _storage_instance


def reset_storage() -> None:
    """重置存储（测试用）"""
    global _storage_instance
    _storage_instance = None
