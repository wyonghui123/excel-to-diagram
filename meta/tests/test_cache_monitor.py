# -*- coding: utf-8 -*-
"""
SVC-004: cache_monitor 单元测试 (6 用例)

[NEW] 2026-06-07 批次: 补齐 CacheMonitor + CachePerformanceMetrics 测试
- hit_rate / avg_hit_time_ms / avg_miss_time_ms 计算
- record_hit / record_miss / record_slow_query / record_error
- to_dict 序列化
- _evaluate_health (issue/warning)
- _generate_recommendations
"""
from datetime import datetime
import pytest

pytestmark = pytest.mark.unit


class _MockEngine:
    """模拟 ManagementDimensionEngine"""
    def get_cache_stats(self):
        return {
            'cache_size': 50,
            'max_size': 100,
            'ttl_seconds': 300,
            'hits': 95,
            'misses': 5,
        }


class TestCacheMonitor:
    """CacheMonitor 单元测试 (SVC-004)"""

    def test_hit_rate_calculation(self):
        """CachePerformanceMetrics.hit_rate 计算"""
        from meta.services.cache_monitor import CachePerformanceMetrics
        m = CachePerformanceMetrics()
        # 0 请求 → 100%
        assert m.hit_rate == 100.0
        # 7 命中 / 3 未命中 = 70%
        for _ in range(7):
            m.record_hit(0.5)
        for _ in range(3):
            m.record_miss(1.0)
        assert m.hit_rate == 70.0

    def test_avg_time_calculation(self):
        """CachePerformanceMetrics.avg_hit_time_ms / avg_miss_time_ms"""
        from meta.services.cache_monitor import CachePerformanceMetrics
        m = CachePerformanceMetrics()
        m.record_hit(1.0)
        m.record_hit(3.0)
        assert m.avg_hit_time_ms == 2.0
        m.record_miss(10.0)
        m.record_miss(20.0)
        assert m.avg_miss_time_ms == 15.0

    def test_slow_query_recording(self):
        """慢查询 (>100ms) 记录, 限制 100 条"""
        from meta.services.cache_monitor import CachePerformanceMetrics
        m = CachePerformanceMetrics()
        m.record_slow_query('q1', 150)
        m.record_slow_query('q2', 50)  # 不算慢查询
        m.record_slow_query('q3', 200)
        assert len(m.slow_queries) == 2
        assert m.slow_queries[0]['key'] == 'q1'

    def test_error_recording(self):
        """错误记录 + 限制 50 条"""
        from meta.services.cache_monitor import CachePerformanceMetrics
        m = CachePerformanceMetrics()
        for i in range(5):
            m.record_error(f'error {i}', f'key_{i}')
        assert m.errors == 5
        assert len(m.error_log) == 5

    def test_to_dict_structure(self):
        """to_dict 序列化所有指标"""
        from meta.services.cache_monitor import CachePerformanceMetrics
        m = CachePerformanceMetrics()
        m.record_hit(1.0)
        m.record_miss(2.0)
        d = m.to_dict()
        # 必含字段
        for key in ('uptime_seconds', 'total_requests', 'cache_hits', 'cache_misses',
                    'hit_rate', 'hit_rate_value', 'avg_hit_time_ms', 'avg_miss_time_ms',
                    'invalidations', 'errors', 'slow_queries_count', 'requests_per_second'):
            assert key in d
        assert d['total_requests'] == 2
        assert d['cache_hits'] == 1
        assert d['cache_misses'] == 1

    def test_health_evaluation_healthy(self):
        """健康状态评估 (良好情况 is_healthy=True)"""
        from meta.services.cache_monitor import CacheMonitor
        engine = _MockEngine()
        monitor = CacheMonitor(engine, target_hit_rate=95.0, target_avg_time_ms=0.1, alert_threshold=90.0)
        # 注入一些指标
        for _ in range(95):
            monitor.metrics.record_hit(0.05)
        for _ in range(5):
            monitor.metrics.record_miss(0.5)
        # 评估
        is_healthy = monitor.check_health()
        assert is_healthy is True
        # 报告
        report = monitor.get_performance_report()
        assert 'health_status' in report
        assert 'recommendations' in report
        assert 'targets' in report
