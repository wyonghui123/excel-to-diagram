# -*- coding: utf-8 -*-
"""
P2-5 Service Executor 单元测试
"""
import sys
import unittest

sys.path.insert(0, 'd:/filework/excel-to-diagram')

from meta.core.service_executor import (
    AtomicService,
    ServiceRegistry,
    ServiceExecutor,
    get_service_registry,
)


class TestAtomicService(unittest.TestCase):
    """AtomicService 测试"""

    def test_01_stub_execution(self):
        """无 handler 时 stub 执行"""
        service = AtomicService(
            id='test', name='Test',
            inputs=[], outputs={},
        )
        result = service.execute({'a': 1})
        self.assertTrue(result['stub'])
        self.assertEqual(result['service_id'], 'test')

    def test_02_with_handler(self):
        """带 handler 时真正执行"""
        def add(a, b):
            return {'sum': a + b}
        service = AtomicService(
            id='add', name='Add',
            inputs=[{'name': 'a'}, {'name': 'b'}],
            outputs={'sum': 'number'},
            handler=add,
        )
        result = service.execute({'a': 2, 'b': 3})
        self.assertEqual(result['sum'], 5)


class TestServiceRegistry(unittest.TestCase):
    """ServiceRegistry 测试"""

    def setUp(self):
        self.registry = ServiceRegistry()

    def test_01_register_and_get(self):
        """注册 + 获取"""
        s = AtomicService(id='s1', name='S1', inputs=[], outputs={})
        self.registry.register(s)
        self.assertIs(self.registry.get('s1'), s)
        self.assertIsNone(self.registry.get('s2'))

    def test_02_default_services_registered(self):
        """默认 service 已注册"""
        reg = get_service_registry()
        self.assertIn('query_version_data', reg.list())
        self.assertIn('compute_chart_metrics', reg.list())
        self.assertIn('chart_render', reg.list())


class TestServiceExecutor(unittest.TestCase):
    """ServiceExecutor 测试"""

    def setUp(self):
        self.executor = ServiceExecutor()

    def test_01_execute_chart_composite(self):
        """执行图表 composite service"""
        steps = [
            {
                'service': 'query_version_data',
                'params': {'version_id': '$input.version_id'},
            },
            {
                'service': 'compute_chart_metrics',
                'params': {
                    'data': '$step1.stub',
                    'chart_type': '$input.chart_type',
                },
            },
            {
                'service': 'chart_render',
                'params': {
                    'metrics': '$step2.stub',
                    'chart_type': '$input.chart_type',
                },
            },
        ]
        result = self.executor.execute(
            composite_steps=steps,
            input_params={'version_id': 'v1.0', 'chart_type': 'bar'},
        )
        # 最终输出是最后一步
        self.assertIsNotNone(result)
        self.assertTrue(result.get('stub'))

    def test_02_execute_step_not_found(self):
        """未注册的 service 应 error"""
        steps = [
            {'service': 'non_existent_service', 'params': {}},
        ]
        result = self.executor.execute(
            composite_steps=steps,
            input_params={},
        )
        self.assertIn('error', result)

    def test_03_execute_with_real_handler(self):
        """带 handler 的 service 真正执行"""
        def add(a, b):
            return {'sum': a + b}
        registry = ServiceRegistry()
        registry.register(AtomicService(
            id='add', name='Add',
            inputs=[], outputs={},
            handler=add,
        ))
        executor = ServiceExecutor(registry=registry)
        result = executor.execute(
            composite_steps=[{'service': 'add', 'params': {'a': 1, 'b': 2}}],
        )
        self.assertEqual(result['sum'], 3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
