"""
test_rls_integration.py - M11 TODO-7: M10 MCP + M11 RLS 集成测试
"""
import os
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


class TestNormalizeUserContext(unittest.TestCase):
    """_normalize_user_context 测试"""

    def setUp(self):
        """重置 RLS loader（确保 test 间隔离）"""
        from rls.loader import RLSLoader
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None
        from rls import loader as loader_mod
        loader_mod.get_loader('rls_rules')

    def test_empty_user_context(self):
        """空 user_context"""
        from mcp.rls_integration import _normalize_user_context
        result = _normalize_user_context(None)
        self.assertEqual(result, {'id': 0, 'roles': set()})

    def test_basic_user_context(self):
        """基本 user context"""
        from mcp.rls_integration import _normalize_user_context
        result = _normalize_user_context({'id': 5, 'roles': ['user']})
        self.assertEqual(result['id'], 5)
        self.assertIn('user', result['roles'])

    def test_ai_agent_flag(self):
        """is_ai_agent=True 注入角色"""
        from mcp.rls_integration import _normalize_user_context
        result = _normalize_user_context({'is_ai_agent': True})
        self.assertIn('ai-agent', result['roles'])

    def test_ai_agent_via_agent_id(self):
        """agent_id 存在 → 注入 ai-agent 角色"""
        from mcp.rls_integration import _normalize_user_context
        result = _normalize_user_context({'agent_id': 'claude-3.5'})
        self.assertIn('ai-agent', result['roles'])
        self.assertTrue(result['is_ai_agent'])


class TestApplyRLSToResult(unittest.TestCase):
    """apply_rls_to_result 测试"""

    def test_admin_allowed(self):
        """admin 角色允许"""
        from mcp.rls_integration import apply_rls_to_result
        from rls import loader as loader_mod
        loader_mod.get_loader('rls_rules')
        result = apply_rls_to_result(
            entity='user',
            action='read',
            user_context={'id': 1, 'roles': ['admin']},
            raw_result={'tool': 'get_user_by_id', 'id': 5, 'result': 'data'},
        )
        self.assertTrue(result['allowed'])
        self.assertIsNone(result.get('deny_reason'))

    def test_viewer_allowed_read(self):
        """viewer 角色允许 read"""
        from mcp.rls_integration import apply_rls_to_result
        from rls import loader as loader_mod
        loader_mod.get_loader('rls_rules')
        result = apply_rls_to_result(
            entity='user',
            action='read',
            user_context={'id': 1, 'roles': ['viewer']},
            raw_result={'tool': 'get_user_by_id', 'id': 5, 'result': 'data'},
        )
        self.assertTrue(result['allowed'])

    def test_viewer_denied_create(self):
        """viewer 角色不能 create"""
        from mcp.rls_integration import apply_rls_to_result
        from rls import loader as loader_mod
        loader_mod.get_loader('rls_rules')
        result = apply_rls_to_result(
            entity='user',
            action='create',
            user_context={'id': 1, 'roles': ['viewer']},
            raw_result={'tool': 'create_user', 'result': 'data'},
        )
        self.assertFalse(result['allowed'])
        self.assertIn('cannot create', result['deny_reason'])

    def test_ai_agent_auto_inject(self):
        """AI Agent 自动注入 + 允许 read"""
        from mcp.rls_integration import apply_rls_to_result
        from rls import loader as loader_mod
        loader_mod.get_loader('rls_rules')
        result = apply_rls_to_result(
            entity='user',
            action='read',
            user_context={'id': 1, 'is_ai_agent': True},
            raw_result={'tool': 'get_user_by_id', 'id': 5, 'result': 'data'},
        )
        # ai-agent 应允许 read
        self.assertTrue(result['allowed'])

    def test_ai_agent_denied_create(self):
        """AI Agent 不能 create"""
        from mcp.rls_integration import apply_rls_to_result
        from rls import loader as loader_mod
        loader_mod.get_loader('rls_rules')
        result = apply_rls_to_result(
            entity='user',
            action='create',
            user_context={'id': 1, 'is_ai_agent': True},
            raw_result={'tool': 'create_user', 'result': 'data'},
        )
        self.assertFalse(result['allowed'])

    def test_field_masks_applied(self):
        """字段脱敏被应用"""
        from mcp.rls_integration import apply_rls_to_result
        from rls import loader as loader_mod
        loader_mod.get_loader('rls_rules')
        result = apply_rls_to_result(
            entity='user',
            action='read',
            user_context={'id': 1, 'roles': ['user']},
            raw_result={
                'tool': 'get_user_by_id',
                'result': {'id': 5, 'phone': '13800001234', 'name': 'Test'},
            },
        )
        self.assertTrue(result['allowed'])
        # user 角色下 phone 应被脱敏（mask 含 {} 占位符）
        if 'phone' in result.get('result', {}):
            self.assertNotEqual(result['result']['phone'], '13800001234')

    def test_admin_no_mask(self):
        """admin 角色无字段脱敏"""
        from mcp.rls_integration import apply_rls_to_result
        from rls import loader as loader_mod
        loader_mod.get_loader('rls_rules')
        result = apply_rls_to_result(
            entity='user',
            action='read',
            user_context={'id': 1, 'roles': ['admin']},
            raw_result={
                'tool': 'get_user_by_id',
                'result': {'id': 5, 'phone': '13800001234', 'name': 'Test'},
            },
        )
        # admin 角色 phone 不脱敏
        self.assertEqual(result['result']['phone'], '13800001234')

    def test_empty_roles_denied(self):
        """空 roles 拒绝"""
        from mcp.rls_integration import apply_rls_to_result
        result = apply_rls_to_result(
            entity='user',
            action='read',
            user_context={'id': 1, 'roles': []},
            raw_result={'tool': 'get_user_by_id', 'result': 'data'},
        )
        self.assertFalse(result['allowed'])


if __name__ == '__main__':
    unittest.main()
