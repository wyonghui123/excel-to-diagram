# -*- coding: utf-8 -*-
"""
Subflow Metrics (v3.7)
========================

收集 subflow 执行指标:
- 每次执行的 name / total_steps / succeeded / failed / duration_ms / timestamp
- 按 action_id 分组的指标 (count / avg_ms / p99_ms / failure_rate)
- 限长 1000 条, 滚动覆盖
"""
import logging
import threading
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_HISTORY = 1000
_lock = threading.Lock()


class SubflowMetrics:
    _history: List[Dict[str, Any]] = []
    _per_action: Dict[str, List[float]] = defaultdict(list)  # action_id -> [durations]

    @classmethod
    def record(cls, name: str, total_steps: int, succeeded: int, failed: int,
               duration_ms: float, step_durations: Optional[List[Dict[str, Any]]] = None):
        """记录一次 subflow 执行"""
        with _lock:
            entry = {
                'name': name,
                'total_steps': total_steps,
                'succeeded': succeeded,
                'failed': failed,
                'skipped': max(0, total_steps - succeeded - failed),
                'duration_ms': round(duration_ms, 2),
                'at': time.time(),
            }
            cls._history.append(entry)
            if len(cls._history) > MAX_HISTORY:
                cls._history = cls._history[-MAX_HISTORY:]

            # 按 action 累计
            if step_durations:
                for s in step_durations:
                    aid = s.get('action_id', 'unknown')
                    dur = s.get('duration_ms', 0)
                    cls._per_action[aid].append(dur)
                    if len(cls._per_action[aid]) > 500:
                        cls._per_action[aid] = cls._per_action[aid][-500:]

    @classmethod
    def get_summary(cls) -> Dict[str, Any]:
        """返回聚合统计"""
        with _lock:
            history = list(cls._history)
            per_action = dict(cls._per_action)

        if not history:
            return {
                'total_executions': 0,
                'total_steps': 0,
                'avg_duration_ms': 0,
                'p50_duration_ms': 0,
                'p99_duration_ms': 0,
                'failure_rate': 0,
                'unique_subflows': 0,
            }

        total_steps = sum(h['total_steps'] for h in history)
        durations = [h['duration_ms'] for h in history]
        durations.sort()
        n = len(durations)
        p50 = durations[int(n * 0.50)] if n > 0 else 0
        p99 = durations[int(n * 0.99)] if n > 0 else 0
        total_succeeded_steps = sum(h['succeeded'] for h in history)
        total_failed_steps = sum(h['failed'] for h in history)
        total = total_succeeded_steps + total_failed_steps
        failure_rate = round(total_failed_steps / total, 4) if total > 0 else 0
        unique_subflows = len(set(h['name'] for h in history))

        return {
            'total_executions': len(history),
            'total_steps': total_steps,
            'avg_duration_ms': round(sum(durations) / n, 2),
            'p50_duration_ms': round(p50, 2),
            'p99_duration_ms': round(p99, 2),
            'min_duration_ms': round(min(durations), 2),
            'max_duration_ms': round(max(durations), 2),
            'failure_rate': failure_rate,
            'unique_subflows': unique_subflows,
        }

    @classmethod
    def get_by_action(cls) -> Dict[str, Dict[str, Any]]:
        """按 action_id 分组"""
        with _lock:
            per_action = dict(cls._per_action)

        result = {}
        for aid, durs in per_action.items():
            if not durs:
                continue
            sorted_durs = sorted(durs)
            n = len(sorted_durs)
            p50 = sorted_durs[int(n * 0.50)]
            p99 = sorted_durs[int(n * 0.99)] if n > 1 else sorted_durs[-1]
            result[aid] = {
                'count': n,
                'avg_ms': round(sum(sorted_durs) / n, 2),
                'p50_ms': round(p50, 2),
                'p99_ms': round(p99, 2),
                'min_ms': round(min(sorted_durs), 2),
                'max_ms': round(max(sorted_durs), 2),
            }
        return result

    @classmethod
    def get_recent(cls, limit: int = 20) -> List[Dict[str, Any]]:
        with _lock:
            history = list(cls._history)
        return history[-limit:][::-1]  # 反序 (最新在前)

    @classmethod
    def reset(cls):
        with _lock:
            cls._history = []
            cls._per_action = defaultdict(list)
