# -*- coding: utf-8 -*-
"""
[MODULE] M.4 P50/P95/P99 滑动窗口 metrics store (v3.18)
[DESCRIPTION] 替代 /_metrics 内的 inline 计算, 提供可重用的 sliding window

合规:
- [OK] 5min 默认窗口 (可配)
- [OK] 内存级 (无外部依赖)
- [OK] 线程安全 (RLock)
"""
import time
import threading
from collections import defaultdict
from typing import Dict, List, Tuple, Optional


class SlidingWindow:
    """[DECORATIVE] v3.18 M.4: 滑动窗口, 5min 默认"""

    def __init__(self, window_seconds: int = 300):
        self.window = window_seconds
        self._data: List[Tuple[float, float]] = []  # (ts, value)
        self._lock = threading.RLock()

    def add(self, value: float, ts: Optional[float] = None) -> None:
        if ts is None:
            ts = time.time()
        with self._lock:
            self._data.append((ts, value))
            self._evict_old(ts)

    def _evict_old(self, now: float) -> None:
        cutoff = now - self.window
        while self._data and self._data[0][0] < cutoff:
            self._data.pop(0)

    def values(self) -> List[float]:
        with self._lock:
            return [v for _, v in self._data]

    def count(self) -> int:
        with self._lock:
            return len(self._data)

    def percentile(self, p: int) -> float:
        """[DECORATIVE] M.4: 计算 P50/P95/P99"""
        with self._lock:
            data = sorted(v for _, v in self._data)
        if not data:
            return 0.0
        idx = int(len(data) * p / 100)
        idx = min(idx, len(data) - 1)
        return data[idx]

    def avg(self) -> float:
        with self._lock:
            data = [v for _, v in self._data]
        return sum(data) / len(data) if data else 0.0


class MetricsStore:
    """[DECORATIVE] v3.18 M.4: 多指标 metrics store"""

    def __init__(self, window_seconds: int = 300):
        self.windows: Dict[str, SlidingWindow] = defaultdict(lambda: SlidingWindow(window_seconds))
        self._counters: Dict[str, int] = defaultdict(int)
        self._lock = threading.RLock()

    def record(self, name: str, value: float, tags: Optional[dict] = None) -> None:
        """记录一个数据点"""
        with self._lock:
            self.windows[name].add(value)
            if tags:
                key = f"{name}|{','.join(f'{k}={v}' for k, v in sorted(tags.items()))}"
                self._counters[key] += 1

    def count(self, name: str = None) -> int:
        if name is None:
            return sum(self._counters.values())
        with self._lock:
            return self._counters.get(name, 0)

    def p50(self, name: str) -> float:
        return self.windows[name].percentile(50)

    def p95(self, name: str) -> float:
        return self.windows[name].percentile(95)

    def p99(self, name: str) -> float:
        return self.windows[name].percentile(99)

    def avg(self, name: str) -> float:
        return self.windows[name].avg()


# 全局 store
_store: Optional[MetricsStore] = None
_store_lock = threading.Lock()


def get_metrics_store() -> MetricsStore:
    """[DECORATIVE] v3.18: 获取全局 metrics store (singleton)"""
    global _store
    with _store_lock:
        if _store is None:
            _store = MetricsStore(window_seconds=300)
        return _store
