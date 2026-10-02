# -*- coding: utf-8 -*-
"""RuleProvider 单元测试

覆盖：
- get_rules 必须"原样返回"（保序、含未启用），这是历史行为的等价替换
- 空对象 / rules 为 None 的容错
- get_enabled_rules / get_rules_by_type 的过滤语义（保序）
- 全局提供者可替换（供后期切换在线配置实现 / 测试注入）
"""

import unittest

from meta.core.models import MetaObject, MetaRule
from meta.core.models_enums import RuleType
from meta.core.rule_provider import RuleProvider, get_rule_provider, set_rule_provider


def _make_rule(rule_id, rule_type=RuleType.VALIDATION, enabled=True, priority=100):
    return MetaRule(id=rule_id, name=rule_id, rule_type=rule_type,
                    enabled=enabled, priority=priority)


class TestRuleProviderGetRules(unittest.TestCase):
    """get_rules 的透传语义（M1 零行为变更的保证）"""

    def setUp(self):
        self.provider = RuleProvider()

    def test_returns_all_rules_in_original_order(self):
        """原样返回：不排序、不过滤，顺序与定义一致"""
        meta_obj = MetaObject(id='order', name='订单', table_name='t_order')
        meta_obj.rules = [
            _make_rule('r3', priority=30),
            _make_rule('r1', priority=10),
            _make_rule('r2', priority=20),
        ]
        rules = self.provider.get_rules(meta_obj)
        self.assertEqual([r.id for r in rules], ['r3', 'r1', 'r2'])

    def test_does_not_filter_disabled_rules(self):
        """关键回归护栏：get_rules 不得过滤 enabled（历史调用点依赖全量）"""
        meta_obj = MetaObject(id='order', name='订单', table_name='t_order')
        meta_obj.rules = [
            _make_rule('r_enabled', enabled=True),
            _make_rule('r_disabled', enabled=False),
        ]
        rules = self.provider.get_rules(meta_obj)
        self.assertEqual(len(rules), 2)

    def test_none_object_returns_empty(self):
        self.assertEqual(self.provider.get_rules(None), [])

    def test_none_rules_returns_empty(self):
        meta_obj = MetaObject(id='order', name='订单', table_name='t_order')
        meta_obj.rules = None
        self.assertEqual(self.provider.get_rules(meta_obj), [])


class TestRuleProviderFiltering(unittest.TestCase):

    def setUp(self):
        self.provider = RuleProvider()
        self.meta_obj = MetaObject(id='order', name='订单', table_name='t_order')
        self.meta_obj.rules = [
            _make_rule('v1', rule_type=RuleType.VALIDATION),
            _make_rule('c1', rule_type=RuleType.COMPUTATION, enabled=False),
            _make_rule('c2', rule_type=RuleType.COMPUTATION),
        ]

    def test_get_enabled_rules_preserves_order(self):
        rules = self.provider.get_enabled_rules(self.meta_obj)
        self.assertEqual([r.id for r in rules], ['v1', 'c2'])

    def test_get_rules_by_type_preserves_order(self):
        rules = self.provider.get_rules_by_type(self.meta_obj, RuleType.COMPUTATION)
        self.assertEqual([r.id for r in rules], ['c1', 'c2'])

    def test_get_rules_by_type_no_match(self):
        rules = self.provider.get_rules_by_type(self.meta_obj, RuleType.DERIVATION)
        self.assertEqual(rules, [])


class TestRuleProviderGlobal(unittest.TestCase):

    def tearDown(self):
        set_rule_provider(None)

    def test_default_provider_is_singleton(self):
        self.assertIs(get_rule_provider(), get_rule_provider())

    def test_provider_can_be_replaced(self):
        """后期切换在线配置实现的能力保证"""
        custom = RuleProvider()
        set_rule_provider(custom)
        self.assertIs(get_rule_provider(), custom)


if __name__ == '__main__':
    unittest.main()
