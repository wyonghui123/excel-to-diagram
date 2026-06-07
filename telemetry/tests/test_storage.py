"""
test_storage.py - M14 v1.0.0 Trace 存储测试
"""
import os
import sys
import unittest
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


class TestTraceStorage(unittest.TestCase):
    """TraceStorage 测试"""

    def setUp(self):
        from telemetry.storage import reset_storage
        reset_storage()

    def tearDown(self):
        from telemetry.storage import reset_storage
        reset_storage()

    def test_record_trace(self):
        """记录 trace"""
        from telemetry.tracing import TraceContext
        from telemetry.storage import get_storage
        ctx = TraceContext.start('test')
        time.sleep(0.001)
        ctx.add_span_type = lambda x: None  # 避免错误
        get_storage().record(ctx)
        stats = get_storage().get_stats()
        self.assertEqual(stats['total_traces'], 1)

    def test_get_recent(self):
        """获取最近 trace"""
        from telemetry.tracing import TraceContext
        from telemetry.storage import get_storage
        for i in range(5):
            ctx = TraceContext.start(f'test_{i}')
            get_storage().record(ctx)
        recent = get_storage().get_recent(limit=3)
        self.assertEqual(len(recent), 3)
        # 倒序：最新在前
        self.assertEqual(recent[0]['root_span_name'], 'test_4')

    def test_get_slow(self):
        """获取慢请求"""
        from telemetry.tracing import TraceContext
        from telemetry.storage import get_storage
        # 慢请求（>100ms）
        ctx = TraceContext.start('slow')
        get_storage().record(ctx)
        # 模拟慢请求：直接 append 到 slow_traces
        get_storage()._slow_traces.append({
            'trace_id': 'fake_slow',
            'root_span_name': 'fake_slow',
            'duration_ms': 200.0,
            'span_count': 0,
            'spans': [],
            'detected_at': time.time(),
        })
        slow = get_storage().get_slow()
        self.assertGreaterEqual(len(slow), 1)

    def test_get_by_trace_id(self):
        """通过 trace_id 查询"""
        from telemetry.tracing import TraceContext
        from telemetry.storage import get_storage
        ctx = TraceContext.start('test')
        target_id = ctx.trace_id
        get_storage().record(ctx)
        result = get_storage().get_by_trace_id(target_id)
        self.assertIsNotNone(result)
        self.assertEqual(result['trace_id'], target_id)

    def test_get_by_trace_id_not_found(self):
        """未找到返回 None"""
        from telemetry.storage import get_storage
        result = get_storage().get_by_trace_id('non_existent_id')
        self.assertIsNone(result)

    def test_get_stats_empty(self):
        """空 storage stats"""
        from telemetry.storage import get_storage
        stats = get_storage().get_stats()
        self.assertEqual(stats['total_traces'], 0)
        self.assertEqual(stats['avg_duration_ms'], 0.0)

    def test_get_stats_with_data(self):
        """有数据时 stats"""
        from telemetry.tracing import TraceContext
        from telemetry.storage import get_storage
        for i in range(10):
            ctx = TraceContext.start(f'test_{i}')
            time.sleep(0.001)
            get_storage().record(ctx)
        stats = get_storage().get_stats()
        self.assertEqual(stats['total_traces'], 10)
        self.assertGreater(stats['avg_duration_ms'], 0)
        self.assertIn('p50_duration_ms', stats)
        self.assertIn('p95_duration_ms', stats)
        self.assertIn('p99_duration_ms', stats)
        self.assertIn('max_duration_ms', stats)

    def test_clear(self):
        """清空 storage"""
        from telemetry.tracing import TraceContext
        from telemetry.storage import get_storage
        for i in range(5):
            ctx = TraceContext.start(f'test_{i}')
            get_storage().record(ctx)
        get_storage().clear()
        stats = get_storage().get_stats()
        self.assertEqual(stats['total_traces'], 0)

    def test_configure(self):
        """configure 更新配置"""
        from telemetry.storage import get_storage
        get_storage().configure(max_traces=500, slow_threshold_ms=200)
        self.assertEqual(get_storage()._traces.maxlen, 500)
        self.assertEqual(get_storage()._slow_threshold_ms, 200)

    def test_max_traces_ring_buffer(self):
        """超过 maxlen 自动淘汰"""
        from telemetry.tracing import TraceContext
        from telemetry.storage import TraceStorage
        storage = TraceStorage(max_traces=5)
        for i in range(10):
            ctx = TraceContext.start(f'test_{i}')
            storage.record(ctx)
        stats = storage.get_stats()
        self.assertEqual(stats['total_traces'], 5)


if __name__ == '__main__':
    unittest.main()
