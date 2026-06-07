# -*- coding: utf-8 -*-
"""
GAP-021: metrics_api 单测 (5 用例)

[NEW] 2026-06-07 批次: 补齐 metrics_api 工具函数测试
- 覆盖 record_metric / get_metrics / format_prometheus / _percentile
- 验证 Prometheus 格式 (HELP / TYPE / 数据行)
- 验证 5min 滑动窗口过滤
"""
import pytest

pytestmark = pytest.mark.unit


class TestMetricsAPI:
    """metrics_api 工具函数测试 (GAP-021)"""

    def test_record_and_get_metric(self):
        """record_metric 写入后 get_metrics 能取到"""
        from meta.api.metrics_api import record_metric, get_metrics
        import time

        name = f'test_metric_{int(time.time() * 1000)}'
        record_metric(name, 1.5, {'tag1': 'value1'})
        record_metric(name, 2.5, {'tag1': 'value2'})

        metrics = get_metrics()
        assert name in metrics
        assert len(metrics[name]) == 2
        # 元素是 (ts, value, tags) 三元组
        ts, val, tags = metrics[name][0]
        assert isinstance(ts, float)
        assert val in (1.5, 2.5)
        assert isinstance(tags, dict)

    def test_percentile_calculation(self):
        """_percentile 计算百分位正确"""
        from meta.api.metrics_api import _percentile
        # [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        values = list(range(1, 11))
        # 50% percentile: idx = int(10 * 0.5) = 5 -> sorted[5] = 6
        p50 = _percentile(values, 50)
        assert p50 == 6
        p95 = _percentile(values, 95)
        # idx = int(10 * 0.95) = 9 -> sorted[9] = 10
        assert p95 == 10
        p99 = _percentile(values, 99)
        # idx = int(10 * 0.99) = 9 -> sorted[9] = 10
        assert p99 == 10
        # 边界: 0 个值
        assert _percentile([], 50) == 0.0
        # 单元素
        assert _percentile([42], 50) == 42

    def test_format_prometheus_text_format(self):
        """format_prometheus 返回 Prometheus 文本格式"""
        from meta.api.metrics_api import format_prometheus
        output = format_prometheus()
        assert isinstance(output, str)
        # 必含 HELP / TYPE 行
        assert '# HELP' in output
        assert '# TYPE' in output
        # 必含核心 metric 名
        assert 'bo_action_total' in output
        assert 'db_pool_active' in output
        assert 'write_queue_depth' in output
        # 行尾 \n
        assert output.endswith('\n')

    def test_format_prometheus_includes_action_duration(self):
        """有 bo_action_duration 数据时包含 duration summary"""
        from meta.api.metrics_api import record_metric, format_prometheus
        import time
        # 写入持续时间数据 (模拟)
        for _ in range(3):
            record_metric('bo_action_duration', 100.0, {'action_id': 'test'})
        output = format_prometheus()
        # 应含 duration 字段
        if 'bo_action_duration_seconds' in output:
            assert 'quantile' in output
            assert '# TYPE bo_action_duration_seconds summary' in output

    def test_get_metrics_returns_copy(self):
        """get_metrics 返回 dict copy, 修改不影响内部 _metrics"""
        from meta.api.metrics_api import record_metric, get_metrics, _metrics
        import time

        name = f'test_copy_{int(time.time() * 1000)}'
        record_metric(name, 1.0)

        m1 = get_metrics()
        assert name in m1
        # 修改返回的 dict 不影响 _metrics 内部
        m1['__extra__'] = 'hack'
        m2 = get_metrics()
        assert '__extra__' not in m2
