"""
test_decorators.py - M14 v1.0.0 @trace 装饰器测试
"""
import os
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


class TestTraceDecorator(unittest.TestCase):
    """@trace 装饰器测试"""

    def setUp(self):
        from telemetry.tracing import TraceContext
        TraceContext._local.set(None)
        from telemetry.storage import reset_storage
        reset_storage()

    def tearDown(self):
        from telemetry.tracing import TraceContext
        TraceContext._local.set(None)

    def test_trace_decorator_basic(self):
        """@trace 基本用法"""
        from telemetry.decorators import trace
        from telemetry.storage import get_storage

        @trace('my_function')
        def my_function(x, y):
            return x + y

        result = my_function(1, 2)
        self.assertEqual(result, 3)
        stats = get_storage().get_stats()
        self.assertGreater(stats['total_traces'], 0)

    def test_trace_decorator_default_name(self):
        """@trace 默认用函数名"""
        from telemetry.decorators import trace
        from telemetry.storage import get_storage

        @trace()
        def my_default_function():
            return 42

        my_default_function()
        stats = get_storage().get_stats()
        self.assertGreater(stats['total_traces'], 0)

    def test_trace_decorator_with_exception(self):
        """@trace 异常处理"""
        from telemetry.decorators import trace
        from telemetry.storage import get_storage

        @trace('failing')
        def failing():
            raise ValueError('test error')

        with self.assertRaises(ValueError):
            failing()
        # 即使异常，trace 仍记录
        stats = get_storage().get_stats()
        self.assertGreater(stats['total_traces'], 0)

    def test_trace_decorator_with_attributes(self):
        """@trace 带静态 attributes"""
        from telemetry.decorators import trace
        from telemetry.storage import get_storage

        @trace('tagged', attributes={'category': 'test'})
        def tagged_function():
            return 'tagged'

        tagged_function()
        stats = get_storage().get_stats()
        self.assertGreater(stats['total_traces'], 0)

    def test_trace_decorator_nested(self):
        """@trace 嵌套调用"""
        from telemetry.decorators import trace
        from telemetry.storage import get_storage

        @trace('outer')
        def outer():
            return inner()

        @trace('inner')
        def inner():
            return 1

        outer()
        stats = get_storage().get_stats()
        # 嵌套应在同一 trace 下，只算 1 个 trace
        self.assertEqual(stats['total_traces'], 1)

    def test_trace_interceptor_decorator(self):
        """@trace_interceptor 拦截器装饰器"""
        from telemetry.decorators import trace_interceptor
        from telemetry.storage import get_storage

        class FakeContext:
            object_type = 'user'
            action = 'create'

        class FakeInterceptor:
            @trace_interceptor('fake_before')
            def before_action(self, context):
                return 'ok'

        interceptor = FakeInterceptor()
        result = interceptor.before_action(FakeContext())
        self.assertEqual(result, 'ok')
        stats = get_storage().get_stats()
        self.assertGreater(stats['total_traces'], 0)


if __name__ == '__main__':
    unittest.main()
