"""
test_integration.py - M14 v1.0.0 拦截器集成测试
"""
import os
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


class TestInterceptorIntegration(unittest.TestCase):
    """拦截器 trace 集成测试"""

    def setUp(self):
        from telemetry.tracing import TraceContext
        TraceContext._local.set(None)
        from telemetry.storage import reset_storage
        reset_storage()

    def tearDown(self):
        from telemetry.tracing import TraceContext
        TraceContext._local.set(None)

    def test_wrap_interceptor_before(self):
        """wrap_interceptor_before 包装"""
        from telemetry.integration import wrap_interceptor_before
        from telemetry.tracing import TraceContext

        class FakeInterceptor:
            name = 'FakeInterceptor'
            priority = 50

            def before_action(self, context):
                return 'original'

        interceptor = FakeInterceptor()
        original_before = interceptor.before_action
        wrapped = wrap_interceptor_before(interceptor, original_before)

        # 调用应在 trace 下
        ctx = TraceContext.start('test')
        result = wrapped(None)
        self.assertEqual(result, 'original')
        self.assertGreater(len(ctx.spans), 0)

    def test_wrap_interceptor_after(self):
        """wrap_interceptor_after 包装"""
        from telemetry.integration import wrap_interceptor_after
        from telemetry.tracing import TraceContext

        class FakeInterceptor:
            name = 'FakeInterceptor'
            priority = 50

            def after_action(self, context):
                return 'after'

        interceptor = FakeInterceptor()
        wrapped = wrap_interceptor_after(interceptor, interceptor.after_action)

        ctx = TraceContext.start('test')
        result = wrapped(None)
        self.assertEqual(result, 'after')
        self.assertGreater(len(ctx.spans), 0)

    def test_install_global_tracer(self):
        """install_global_tracer 包装所有拦截器"""
        from telemetry.integration import install_global_tracer
        from telemetry.tracing import TraceContext
        from telemetry.storage import get_storage

        class FakeInterceptor1:
            name = 'Fake1'
            priority = 50
            def before_action(self, context): pass
            def after_action(self, context): pass

        class FakeInterceptor2:
            name = 'Fake2'
            priority = 60
            def before_action(self, context): pass
            def after_action(self, context): pass

        class NotInterceptor:
            pass

        interceptors = [FakeInterceptor1(), FakeInterceptor2(), NotInterceptor()]
        wrapped = install_global_tracer(interceptors)
        # 仅包装有 before/after 的（2 个）
        self.assertEqual(wrapped, 2)

        # 调用包装后的方法
        with __import__('telemetry.tracing', fromlist=['trace']).trace('test'):
            for interceptor in interceptors[:2]:
                if hasattr(interceptor, 'before_action'):
                    interceptor.before_action(None)
                if hasattr(interceptor, 'after_action'):
                    interceptor.after_action(None)

        # 验证 span 记录
        stats = get_storage().get_stats()
        self.assertGreater(stats['total_traces'], 0)

    def test_wrap_with_exception(self):
        """包装后异常处理"""
        from telemetry.integration import wrap_interceptor_before
        from telemetry.tracing import TraceContext

        class FakeInterceptor:
            name = 'Fake'
            priority = 50

            def before_action(self, context):
                raise ValueError('interceptor error')

        interceptor = FakeInterceptor()
        wrapped = wrap_interceptor_before(interceptor, interceptor.before_action)

        ctx = TraceContext.start('test')
        with self.assertRaises(ValueError):
            wrapped(None)
        # span 记录了 error
        self.assertEqual(len(ctx.spans), 1)
        self.assertEqual(ctx.spans[0].status, 'error')


if __name__ == '__main__':
    unittest.main()
