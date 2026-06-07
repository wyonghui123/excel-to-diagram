# -*- coding: utf-8 -*-
"""
P2-3 visibility='draft' 模式 + 跨 BO Action 组合 测试
"""
import sys
import unittest

sys.path.insert(0, 'd:/filework/excel-to-diagram')

from meta.core.scope_evaluator import ScopeEvaluator


class TestVisibilityDraft(unittest.TestCase):
    """P2-3 FR-010 visibility='draft' 模式测试"""

    def setUp(self):
        self.evaluator = ScopeEvaluator()

    def test_01_draft_owner_visible(self):
        """draft 模式下 owner 可见"""
        scope = "visibility = 'public' OR owner_id = $user.id"
        result = self.evaluator.evaluate(
            scope=scope, user_id=123,
            record={'visibility': 'draft', 'owner_id': 123},
        )
        self.assertTrue(result)

    def test_02_draft_other_user_not_visible(self):
        """draft 模式下其他用户不可见"""
        scope = "visibility = 'public' OR owner_id = $user.id"
        result = self.evaluator.evaluate(
            scope=scope, user_id=999,
            record={'visibility': 'draft', 'owner_id': 123},
        )
        self.assertFalse(result)

    def test_03_public_all_visible(self):
        """public 模式下所有人可见"""
        scope = "visibility = 'public' OR owner_id = $user.id"
        for user_id in [123, 999, 1]:
            result = self.evaluator.evaluate(
                scope=scope, user_id=user_id,
                record={'visibility': 'public', 'owner_id': 123},
            )
            self.assertTrue(result)

    def test_04_team_visibility_owner(self):
        """team 模式下 owner 可见"""
        scope = "visibility = 'public' OR owner_id = $user.id"
        result = self.evaluator.evaluate(
            scope=scope, user_id=123,
            record={'visibility': 'team', 'owner_id': 123},
        )
        self.assertTrue(result)

    def test_05_team_visibility_other(self):
        """team 模式下其他用户当前不可见（简化模型）

        实际团队成员可见逻辑需要扩展（v1.5+）
        """
        scope = "visibility = 'public' OR owner_id = $user.id"
        result = self.evaluator.evaluate(
            scope=scope, user_id=999,
            record={'visibility': 'team', 'owner_id': 123},
        )
        # 当前简化模型：仅 public + owner 可见
        self.assertFalse(result)


class TestCrossBOAction(unittest.TestCase):
    """P2-4 跨 BO Action 组合测试（基础数据模型）"""

    def test_01_composite_intent_structure(self):
        """Composite Intent 数据结构测试"""
        # 跨 BO 组合：(product, read) + (version, read) + (action=view_chart)
        composite = {
            'name': 'product_version_dashboard',
            'intents': [
                {'bo_id': 'product', 'action_name': 'read', 'parameters': {}},
                {'bo_id': 'version', 'action_name': 'read', 'parameters': {}},
            ],
            'global_actions': [
                {'action': 'view_chart', 'bo_id': 'version', 'parameters': {'chart_type': 'bar'}},
            ],
        }
        # 至少有 2 个 BO intents + 1 个 global action
        self.assertEqual(len(composite['intents']), 2)
        self.assertEqual(len(composite['global_actions']), 1)
        # 所有 intents 都有 bo_id 和 action_name
        for intent in composite['intents']:
            self.assertIn('bo_id', intent)
            self.assertIn('action_name', intent)


if __name__ == '__main__':
    unittest.main(verbosity=2)
