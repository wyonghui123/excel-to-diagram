"""
telemetry/tests/run_all.py - M14 v1.0.0 测试运行器
"""
import os
import sys
import unittest

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, _PROJECT_ROOT)


def load_all_tests():
    """加载所有 M14 测试"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # T1 tracing
    from telemetry.tests.test_tracing import (
        TestTraceContext, TestSpan, TestTraceContextManager,
    )
    suite.addTests(loader.loadTestsFromTestCase(TestTraceContext))
    suite.addTests(loader.loadTestsFromTestCase(TestSpan))
    suite.addTests(loader.loadTestsFromTestCase(TestTraceContextManager))

    # T2 storage
    from telemetry.tests.test_storage import TestTraceStorage
    suite.addTests(loader.loadTestsFromTestCase(TestTraceStorage))

    # T3 decorators
    from telemetry.tests.test_decorators import TestTraceDecorator
    suite.addTests(loader.loadTestsFromTestCase(TestTraceDecorator))

    # T4 integration
    from telemetry.tests.test_integration import TestInterceptorIntegration
    suite.addTests(loader.loadTestsFromTestCase(TestInterceptorIntegration))

    # T5 API
    from telemetry.tests.test_api import TestTelemetryAPI
    suite.addTests(loader.loadTestsFromTestCase(TestTelemetryAPI))

    return suite


if __name__ == '__main__':
    suite = load_all_tests()
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
