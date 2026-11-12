"""
test_ai_agent_role.py - AI Agent 角色注入测试

[T14] 安全契约变更（2026-11-11）：
- 不再依据未签名的 X-Agent-Id HTTP 请求头注入 'ai-agent' 角色；
  PermissionInterceptor 中的 inject_ai_agent_role 已移除。
- AI Agent 身份只来自 MCP 内部上下文（mcp.rls_integration._normalize_user_context）。
- rls_rules 中 role:ai-agent 的放行规则本身仍有效。
"""
import os
import sys
import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


class TestHeaderInjectionRemoved(unittest.TestCase):
    """X-Agent-Id 请求头不再具备角色自抬能力"""

    def test_inject_function_removed(self):
        """inject_ai_agent_role 已从拦截器移除"""
        import meta.core.interceptors.permission_interceptor as pi
        self.assertFalse(hasattr(pi, 'inject_ai_agent_role'))

    def test_x_agent_id_header_does_not_grant_ai_agent(self):
        """带 X-Agent-Id 且无权限的用户读 user 实体 → 必须 403"""
        from types import SimpleNamespace

        mock_request = MagicMock()
        mock_request.headers = {'X-Agent-Id': 'agent-001'}
        original_user = {
            'id': 1,
            'username': 'alice',
            'permissions': set(),
            'roles': ['user'],
        }
        mock_g = MagicMock()
        mock_g.get.return_value = original_user

        with patch('flask.request', mock_request), \
                patch('flask.g', mock_g), \
                patch('meta.services.auth_middleware.is_admin', return_value=False), \
                patch('meta.core.permission_audit.log_permission_decision'):
            from meta.core.interceptors.permission_interceptor import (
                PermissionInterceptor, PermissionDenied,
            )

            class _ConcretePermissionInterceptor(PermissionInterceptor):
                def after_action(self, context):
                    super().after_action(context)

                @property
                def name(self):
                    return 'permission'

                @property
                def priority(self):
                    return 30

                def should_execute(self, context):
                    return context.action.startswith('crud_')

            context = SimpleNamespace(action='crud_read', object_type='user')
            with self.assertRaises(PermissionDenied):
                _ConcretePermissionInterceptor().before_action(context)

            # 角色未被篡改
            self.assertNotIn('ai-agent', original_user['roles'])


class TestMcpInternalAiAgentContext(unittest.TestCase):
    """MCP 内部上下文（可信来源）仍然可以声明 AI Agent 身份"""

    def test_is_ai_agent_flag_injects(self):
        from mcp.rls_integration import _normalize_user_context
        ctx = _normalize_user_context({'id': 5, 'is_ai_agent': True})
        self.assertIn('ai-agent', ctx['roles'])

    def test_agent_id_injects(self):
        from mcp.rls_integration import _normalize_user_context
        ctx = _normalize_user_context({'id': 5, 'agent_id': 'claude-3.5'})
        self.assertIn('ai-agent', ctx['roles'])

    def test_plain_user_not_injected(self):
        from mcp.rls_integration import _normalize_user_context
        ctx = _normalize_user_context({'id': 5, 'roles': ['user']})
        self.assertNotIn('ai-agent', ctx['roles'])


class TestAIAgentRoleWithRLS(unittest.TestCase):
    """AI Agent 角色与 rls YAML 协同"""

    def setUp(self):
        from rls.loader import RLSLoader
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None
        self.tmpdir = tempfile.mkdtemp(prefix='rls_ai_agent_')
        with open(os.path.join(self.tmpdir, 'user.yaml'), 'w', encoding='utf-8') as f:
            f.write("""
entity: user
row_filters:
  - applies_to: [role:ai-agent]
    condition: "user.is_public == true"
field_masks:
  - field: phone
    mask: "***-****-{}"
    applies_to: [role:ai-agent]
actions:
  read: [role:admin, role:ai-agent]
""")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        from rls.loader import RLSLoader
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None

    def test_ai_agent_gets_ai_agent_role_filter(self):
        """ai-agent 角色在 user 实体有 1 个 row_filter"""
        from rls import get_row_filters
        filters = get_row_filters('user', 'role:ai-agent', self.tmpdir)
        self.assertEqual(len(filters), 1)
        self.assertIn('is_public', filters[0]['condition'])

    def test_ai_agent_phone_field_masked(self):
        """ai-agent 角色 phone 字段被脱敏"""
        from rls import get_field_masks
        masks = get_field_masks('user', 'role:ai-agent', self.tmpdir)
        self.assertEqual(len(masks), 1)
        self.assertEqual(masks[0]['field'], 'phone')

    def test_ai_agent_can_read_user(self):
        """ai-agent 角色可以 read user"""
        from rls.enforce import check_action
        self.assertTrue(check_action('ai-agent', 'user', 'read', self.tmpdir))

    def test_ai_agent_cannot_create_user(self):
        """ai-agent 角色不可以 create user"""
        from rls.enforce import check_action
        self.assertFalse(check_action('ai-agent', 'user', 'create', self.tmpdir))


if __name__ == '__main__':
    unittest.main()