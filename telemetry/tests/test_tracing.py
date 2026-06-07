"""
test_tracing.py - M14 v1.0.0 Trace 上下文 + Span 测试
"""
import os
import sys
import unittest
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


class TestTraceContext(unittest.TestCase):
    """TraceContext 测试"""

    def setUp(self):
        from telemetry.tracing import TraceContext
        TraceContext._local.set(None)

    def tearDown(self):
        from telemetry.tracing import TraceContext
        TraceContext._local.set(None)

    def test_start_creates_context(self):
        """start 创建 context"""
        from telemetry.tracing import TraceContext
        ctx = TraceContext.start('test')
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.root_span_name, 'test')
        self.assertEqual(len(ctx.trace_id), 32)  # UUID4 hex

    def test_current_returns_context(self):
        """current 返回当前 context"""
        from telemetry.tracing import TraceContext
        ctx = TraceContext.start('test')
        current = TraceContext.current()
        self.assertIs(ctx, current)

    def test_end_returns_summary(self):
        """end 返回 summary dict"""
        from telemetry.tracing import TraceContext
        ctx = TraceContext.start('test')
        time.sleep(0.01)
        summary = ctx.end()
        self.assertIn('trace_id', summary)
        self.assertIn('duration_ms', summary)
        self.assertGreaterEqual(summary['duration_ms'], 10)

    def test_add_span(self):
        """add_span 正确累加"""
        from telemetry.tracing import TraceContext, Span
        ctx = TraceContext.start('test')
        s1 = Span.start('span1')
        s2 = Span.start('span2')
        self.assertEqual(len(ctx.spans), 2)


class TestSpan(unittest.TestCase):
    """Span 测试"""

    def setUp(self):
        from telemetry.tracing import TraceContext
        TraceContext._local.set(None)

    def tearDown(self):
        from telemetry.tracing import TraceContext
        TraceContext._local.set(None)

    def test_start_creates_span(self):
        """start 创建 span"""
        from telemetry.tracing import Span
        s = Span.start('test_span')
        self.assertEqual(s.name, 'test_span')
        self.assertEqual(s.status, 'ok')

    def test_end_records_duration(self):
        """end 记录 duration"""
        from telemetry.tracing import Span
        s = Span.start('test_span')
        time.sleep(0.01)
        s.end()
        self.assertGreaterEqual(s.duration_ms, 10)

    def test_end_with_error(self):
        """end 记录错误状态"""
        from telemetry.tracing import Span
        s = Span.start('test_span')
        s.end(status='error', error='something failed')
        self.assertEqual(s.status, 'error')
        self.assertEqual(s.error, 'something failed')

    def test_set_attribute(self):
        """set_attribute 设置属性"""
        from telemetry.tracing import Span
        s = Span.start('test_span', attributes={'k1': 'v1'})
        s.set_attribute('k2', 'v2')
        self.assertEqual(s.attributes['k1'], 'v1')
        self.assertEqual(s.attributes['k2'], 'v2')

    def test_to_dict(self):
        """to_dict 返回 dict"""
        from telemetry.tracing import Span
        s = Span.start('test_span')
        s.end()
        d = s.to_dict()
        self.assertIn('name', d)
        self.assertIn('duration_ms', d)
        self.assertIn('status', d)


class TestTraceContextManager(unittest.TestCase):
    """trace() 和 span() 上下文管理器测试"""

    def setUp(self):
        from telemetry.tracing import TraceContext
        TraceContext._local.set(None)
        from telemetry.storage import reset_storage
        reset_storage()

    def tearDown(self):
        from telemetry.tracing import TraceContext
        TraceContext._local.set(None)

    def test_trace_context_manager(self):
        """trace() 上下文管理器自动 start/end"""
        from telemetry.tracing import trace
        with trace('test') as ctx:
            self.assertEqual(ctx.root_span_name, 'test')
        # ctx 自动 end，recorded to storage
        from telemetry.storage import get_storage
        stats = get_storage().get_stats()
        self.assertGreater(stats['total_traces'], 0)

    def test_span_context_manager(self):
        """span() 上下文管理器"""
        from telemetry.tracing import trace, span
        with trace('test') as ctx:
            with span('inner') as s:
                pass
        # 验证 inner span 记录
        self.assertEqual(len(ctx.spans), 1)

    def test_trace_with_error(self):
        """trace() 异常处理"""
        from telemetry.tracing import trace
        with self.assertRaises(ValueError):
            with trace('test'):
                raise ValueError('test error')


if __name__ == '__main__':
    unittest.main()
