# -*- coding: utf-8 -*-
"""
[MODULE] /_metrics Prometheus 端点 (v3.18 M.3)
[DESCRIPTION] 暴露 Prometheus 格式 metrics

格式: text/plain (Prometheus 标准)

返回示例:
  # HELP bo_action_total Total BO Action calls
  # TYPE bo_action_total counter
  bo_action_total{action_id="user.get_current",status="success"} 1234
  bo_action_duration_seconds_bucket{action_id="user.get_current",le="0.1"} 1100
  ...
"""
from collections import defaultdict
from typing import Dict


# 内存 metrics store (5min 滑动窗口)
_metrics: Dict[str, list] = defaultdict(list)


def record_metric(name: str, value: float, tags: dict = None) -> None:
    """[DECORATIVE] v3.18 M.4: 记录 metric (in-memory)"""
    import time
    _metrics[name].append((time.time(), value, tags or {}))


def get_metrics() -> Dict[str, list]:
    """取所有 metrics"""
    return dict(_metrics)


def _percentile(values, p):
    """计算百分位"""
    if not values:
        return 0.0
    sorted_v = sorted(values)
    idx = int(len(sorted_v) * p / 100)
    return sorted_v[min(idx, len(sorted_v) - 1)]


def format_prometheus() -> str:
    """[DECORATIVE] v3.18 M.3: 输出 Prometheus 文本格式"""
    import time
    now = time.time()
    # 5min 窗口
    window = 300

    lines = []

    # bo_action_total (counter)
    recent_count = [v for v in _metrics.get('bo_action_count', []) if now - v[0] < window]
    total = len(recent_count)
    lines.append('# HELP bo_action_total Total BO Action calls in last 5min')
    lines.append('# TYPE bo_action_total counter')
    lines.append(f'bo_action_total {total}')

    # bo_action_duration (histogram 简化)
    recent_durations = [v[1] for v in _metrics.get('bo_action_duration', [])
                        if now - v[0] < window]
    if recent_durations:
        p50 = _percentile(recent_durations, 50)
        p95 = _percentile(recent_durations, 95)
        p99 = _percentile(recent_durations, 99)
        lines.append('# HELP bo_action_duration_seconds Action duration distribution')
        lines.append('# TYPE bo_action_duration_seconds summary')
        lines.append(f'bo_action_duration_seconds{{quantile="0.5"}} {p50 / 1000}')
        lines.append(f'bo_action_duration_seconds{{quantile="0.95"}} {p95 / 1000}')
        lines.append(f'bo_action_duration_seconds{{quantile="0.99"}} {p99 / 1000}')

    # db_pool
    lines.append('# HELP db_pool_active Active DB pool connections')
    lines.append('# TYPE db_pool_active gauge')
    lines.append('db_pool_active 0  # TODO: 读 meta/core/db/connection_pool.py 实际值')

    # write_queue
    lines.append('# HELP write_queue_depth Current write queue depth')
    lines.append('# TYPE write_queue_depth gauge')
    lines.append('write_queue_depth 0  # TODO: 读 meta/core/db/write_queue.py 实际值')

    return '\n'.join(lines) + '\n'


# Flask 路由注册
def register_metrics_route(app):
    """注册 GET /_metrics (用 before_request 拦截)"""
    from flask import request, Response

    @app.before_request
    def _metrics_intercept():
        if request.path == '/_metrics' and request.method == 'GET':
            try:
                body = format_prometheus()
                return Response(body, status=200, content_type='text/plain; version=0.0.4; charset=utf-8')
            except Exception as e:
                import traceback
                return Response(
                    f"# error: {e}\n# traceback:\n{traceback.format_exc()}",
                    status=500,
                    content_type='text/plain; charset=utf-8',
                )
        return None
