# -*- coding: utf-8 -*-
"""
P2-1 aspect_loader + scope_evaluator 单元测试
"""
import sys
import unittest

sys.path.insert(0, 'd:/filework/excel-to-diagram')

from meta.core.aspect_loader import AspectLoader, get_aspect_loader
from meta.core.scope_evaluator import ScopeEvaluator, get_scope_evaluator


class TestAspectLoader(unittest.TestCase):
    """AspectLoader 单元测试"""

    def setUp(self):
        self.loader = AspectLoader()

    def test_01_get_owner_aspect(self):
        """获取 owner_aspect 配置"""
        aspect = self.loader.get_aspect('owner_aspect')
        self.assertIsNotNone(aspect)
        self.assertIn('fields', aspect)
        self.assertIn('authorization', aspect)

    def test_02_get_authorization_scope(self):
        """获取 owner_aspect 的 authorization.scope"""
        scope = self.loader.get_authorization_scope('owner_aspect')
        self.assertIsNotNone(scope)
        self.assertIn('visibility', scope)
        self.assertIn('owner_id', scope)
        self.assertIn('$user.id', scope)

    def test_03_has_visibility_field(self):
        """owner_aspect 包含 visibility 字段"""
        self.assertTrue(self.loader.has_field('owner_aspect', 'visibility'))
        self.assertTrue(self.loader.has_field('owner_aspect', 'owner_id'))

    def test_04_get_actions(self):
        """获取 owner_aspect 的 actions"""
        actions = self.loader.get_actions('owner_aspect')
        action_ids = [a['id'] for a in actions]
        self.assertIn('publish', action_ids)
        self.assertIn('make_draft', action_ids)
        self.assertIn('transfer_owner', action_ids)

    def test_05_nonexistent_aspect(self):
        """不存在的 aspect 返回 None"""
        self.assertIsNone(self.loader.get_aspect('non_existent_aspect'))
        self.assertIsNone(self.loader.get_authorization_scope('non_existent_aspect'))

    def test_06_singleton(self):
        """get_aspect_loader 是单例"""
        self.assertIs(get_aspect_loader(), get_aspect_loader())


class TestScopeEvaluator(unittest.TestCase):
    """Scope 表达式求值器测试"""

    def setUp(self):
        self.evaluator = ScopeEvaluator()

    def test_01_owner_aspect_scope_owner_match(self):
        """owner_aspect scope: 当前用户是 owner → True"""
        scope = "visibility = 'public' OR owner_id = $user.id"
        # 用户 123 是 owner
        result = self.evaluator.evaluate(
            scope=scope, user_id=123,
            record={'visibility': 'draft', 'owner_id': 123},
        )
        self.assertTrue(result)

    def test_02_owner_aspect_scope_public(self):
        """public 记录所有人可见 → True"""
        scope = "visibility = 'public' OR owner_id = $user.id"
        result = self.evaluator.evaluate(
            scope=scope, user_id=999,
            record={'visibility': 'public', 'owner_id': 123},
        )
        self.assertTrue(result)

    def test_03_owner_aspect_scope_draft_other(self):
        """draft 且非 owner → False"""
        scope = "visibility = 'public' OR owner_id = $user.id"
        result = self.evaluator.evaluate(
            scope=scope, user_id=999,
            record={'visibility': 'draft', 'owner_id': 123},
        )
        self.assertFalse(result)

    def test_04_and_expression(self):
        """AND 表达式"""
        scope = "status = 'active' AND owner_id = $user.id"
        # 都满足
        result = self.evaluator.evaluate(
            scope=scope, user_id=123,
            record={'status': 'active', 'owner_id': 123},
        )
        self.assertTrue(result)
        # status 不满足
        result = self.evaluator.evaluate(
            scope=scope, user_id=123,
            record={'status': 'inactive', 'owner_id': 123},
        )
        self.assertFalse(result)

    def test_05_not_equal(self):
        """!= 操作符"""
        scope = "status != 'deleted'"
        self.assertTrue(self.evaluator.evaluate(
            scope=scope, user_id=1,
            record={'status': 'active'},
        ))
        self.assertFalse(self.evaluator.evaluate(
            scope=scope, user_id=1,
            record={'status': 'deleted'},
        ))

    def test_06_empty_scope(self):
        """空 scope 返回 True"""
        self.assertTrue(self.evaluator.evaluate('', user_id=1, record={}))

    def test_07_complex_or_and(self):
        """复杂 OR + AND（无括号）"""
        # 无括号版本（OR 顶层分隔，AND 内部连接）
        scope = "visibility = 'public' OR owner_id = $user.id OR status = 'active'"
        # public → True
        self.assertTrue(self.evaluator.evaluate(
            scope=scope, user_id=999,
            record={'visibility': 'public', 'owner_id': 123, 'status': 'active'},
        ))
        # owner → True
        self.assertTrue(self.evaluator.evaluate(
            scope=scope, user_id=123,
            record={'visibility': 'draft', 'owner_id': 123, 'status': 'inactive'},
        ))
        # active → True
        self.assertTrue(self.evaluator.evaluate(
            scope=scope, user_id=999,
            record={'visibility': 'draft', 'owner_id': 123, 'status': 'active'},
        ))


if __name__ == '__main__':
    unittest.main(verbosity=2)
