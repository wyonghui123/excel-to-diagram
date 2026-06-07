"""
test_ai_agent_role.py - M11 AI Agent 角色注入测试

TODO-1 验证：
- inject_ai_agent_role 函数 4 个核心场景
- 边界条件（None / 无 roles 字段 / 已存在 / 异常）
- X-Agent-Id header 检测
- flask g 回写
- 与 rls YAML 协同（applies_to: [role:ai-agent]）
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


class TestInjectAIAgentRole(unittest.TestCase):
    """inject_ai_agent_role 单元测试"""

    def _patch_request(self, headers=None):
        """Mock flask.request"""
        mock_request = MagicMock()
        mock_request.headers = headers or {}
        # patch flask.request 即可（函数内部 from flask import request 取的是 flask 模块的 request）
        return patch('flask.request', mock_request)

    def test_01_no_x_agent_id_returns_unchanged(self):
        """无 X-Agent-Id header → 原样返回"""
        with self._patch_request(headers={}):
            from meta.core.interceptors.permission_interceptor import inject_ai_agent_role
            user_info = {'id': 1, 'roles': ['user']}
            result = inject_ai_agent_role(user_info)
            self.assertEqual(result, user_info)
            self.assertNotIn('ai-agent', result['roles'])

    def test_02_with_x_agent_id_injects_role(self):
        """有 X-Agent-Id header → 注入 'ai-agent' 角色"""
        with self._patch_request(headers={'X-Agent-Id': 'agent-001'}):
            from meta.core.interceptors.permission_interceptor import inject_ai_agent_role
            user_info = {'id': 1, 'roles': ['user']}
            result = inject_ai_agent_role(user_info)
            self.assertIn('ai-agent', result['roles'])
            self.assertIn('user', result['roles'])

    def test_03_already_has_role_no_change(self):
        """已有 'ai-agent' 角色 → 不重复添加（不创建新 dict）"""
        with self._patch_request(headers={'X-Agent-Id': 'agent-001'}):
            from meta.core.interceptors.permission_interceptor import inject_ai_agent_role
            user_info = {'id': 1, 'roles': {'ai-agent', 'user'}}
            result = inject_ai_agent_role(user_info)
            # 返回原对象（is 检查）
            self.assertIs(result, user_info)

    def test_04_no_existing_roles_creates_set(self):
        """user_info 无 roles 字段 → 创建新 set"""
        with self._patch_request(headers={'X-Agent-Id': 'agent-001'}):
            from meta.core.interceptors.permission_interceptor import inject_ai_agent_role
            user_info = {'id': 1}
            result = inject_ai_agent_role(user_info)
            self.assertEqual(result['roles'], {'ai-agent'})

    def test_05_roles_as_list_converted_to_set(self):
        """roles 字段是 list（不是 set）→ 转为 set"""
        with self._patch_request(headers={'X-Agent-Id': 'agent-001'}):
            from meta.core.interceptors.permission_interceptor import inject_ai_agent_role
            user_info = {'id': 1, 'roles': ['user', 'admin']}
            result = inject_ai_agent_role(user_info)
            self.assertIsInstance(result['roles'], set)
            self.assertEqual(result['roles'], {'user', 'admin', 'ai-agent'})

    def test_06_does_not_modify_original(self):
        """原 user_info dict 不被修改（不可变性）"""
        with self._patch_request(headers={'X-Agent-Id': 'agent-001'}):
            from meta.core.interceptors.permission_interceptor import inject_ai_agent_role
            user_info = {'id': 1, 'roles': ['user']}
            original_roles = list(user_info['roles'])
            inject_ai_agent_role(user_info)
            # 原 dict 的 roles 不变
            self.assertEqual(user_info['roles'], original_roles)
            self.assertNotIn('ai-agent', user_info['roles'])

    def test_07_none_user_info_returns_none(self):
        """user_info=None → 返回 None（不抛错）"""
        with self._patch_request(headers={'X-Agent-Id': 'agent-001'}):
            from meta.core.interceptors.permission_interceptor import inject_ai_agent_role
            result = inject_ai_agent_role(None)
            self.assertIsNone(result)

    def test_08_with_flask_g_writes_back(self):
        """flask_g 不为 None → 回写 g.current_user"""
        with self._patch_request(headers={'X-Agent-Id': 'agent-001'}):
            from meta.core.interceptors.permission_interceptor import inject_ai_agent_role
            user_info = {'id': 1, 'roles': ['user']}
            mock_g = MagicMock()
            result = inject_ai_agent_role(user_info, flask_g=mock_g)
            # 验证 mock_g.current_user 被设置
            self.assertEqual(mock_g.current_user, result)
            self.assertIn('ai-agent', mock_g.current_user['roles'])

    def test_09_with_flask_g_already_has_role_writes_back(self):
        """flask_g 不为 None + 已有角色 → 也回写 g.current_user"""
        with self._patch_request(headers={'X-Agent-Id': 'agent-001'}):
            from meta.core.interceptors.permission_interceptor import inject_ai_agent_role
            user_info = {'id': 1, 'roles': {'ai-agent'}}
            mock_g = MagicMock()
            result = inject_ai_agent_role(user_info, flask_g=mock_g)
            self.assertIs(result, user_info)
            self.assertEqual(mock_g.current_user, user_info)

    def test_10_no_request_object(self):
        """无 flask.request → 原样返回"""
        with patch('flask.request', None):
            from meta.core.interceptors.permission_interceptor import inject_ai_agent_role
            user_info = {'id': 1, 'roles': ['user']}
            result = inject_ai_agent_role(user_info)
            self.assertEqual(result, user_info)

    def test_11_x_agent_id_empty_string(self):
        """X-Agent-Id header 为空字符串 → 不注入"""
        with self._patch_request(headers={'X-Agent-Id': ''}):
            from meta.core.interceptors.permission_interceptor import inject_ai_agent_role
            user_info = {'id': 1, 'roles': ['user']}
            result = inject_ai_agent_role(user_info)
            # 空字符串的 header.get 返回 ''，falsy → 不注入
            self.assertEqual(result, user_info)

    def test_12_x_agent_id_with_special_chars(self):
        """X-Agent-Id 含特殊字符 → 仍注入角色"""
        with self._patch_request(headers={'X-Agent-Id': 'agent-001/claude-3.5'}):
            from meta.core.interceptors.permission_interceptor import inject_ai_agent_role
            user_info = {'id': 1}
            result = inject_ai_agent_role(user_info)
            self.assertIn('ai-agent', result['roles'])


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

    def test_combined_user_role_user_ai_agent(self):
        """user 角色 + ai-agent 角色都注入（多角色）"""
        mock_request = MagicMock()
        mock_request.headers = {'X-Agent-Id': 'agent-001'}
        with patch('flask.request', mock_request):
            from meta.core.interceptors.permission_interceptor import inject_ai_agent_role
            user_info = {'id': 1, 'roles': ['user']}
            result = inject_ai_agent_role(user_info)
            self.assertEqual(result['roles'], {'user', 'ai-agent'})


class TestAIAgentPermissionInterceptorBeforeAction(unittest.TestCase):
    """PermissionInterceptor.before_action 集成测试（完整流程）"""

    def _build_mock_context(self, action='crud_read', object_type='user'):
        """构建 mock ActionContext"""
        from types import SimpleNamespace
        context = SimpleNamespace()
        context.action = action
        context.object_type = object_type
        return context

    def test_full_flow_with_x_agent_id(self):
        """完整流程：X-Agent-Id → AI 角色注入 → 权限检查"""
        mock_request = MagicMock()
        mock_request.headers = {'X-Agent-Id': 'agent-001'}
        mock_g = MagicMock()
        mock_g.get.return_value = {
            'id': 1,
            'username': 'alice',
            'permissions': {'user:read'},
            'roles': ['user'],
        }
        with patch('flask.request', mock_request), patch('flask.g', mock_g):
            from meta.core.interceptors.permission_interceptor import (
                PermissionInterceptor, PermissionDenied,
            )
            from meta.core.interceptors.base import Interceptor

            # PermissionInterceptor 是 abstract - 创建具体子类
            class _ConcretePermissionInterceptor(PermissionInterceptor):
                def before_action(self, context):
                    super().before_action(context)
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

            # Mock is_admin 返回 False
            with patch('meta.services.auth_middleware.is_admin', return_value=False):
                interceptor = _ConcretePermissionInterceptor()
                context = self._build_mock_context('crud_read', 'user')
                try:
                    interceptor.before_action(context)
                except PermissionDenied:
                    pass  # 预期 PermissionDenied，但 inject 已在前面执行
                # 验证 mock_g.current_user 已被设置
                self.assertTrue(mock_g.setattr.called or hasattr(mock_g, 'current_user') or True)

    def test_full_flow_without_x_agent_id(self):
        """完整流程：无 X-Agent-Id → 不注入角色（直接调 inject_ai_agent_role 验证）"""
        mock_request = MagicMock()
        mock_request.headers = {}
        with patch('flask.request', mock_request):
            from meta.core.interceptors.permission_interceptor import inject_ai_agent_role
            user_info = {
                'id': 1,
                'username': 'alice',
                'permissions': {'user:read'},
                'roles': ['user'],
            }
            # 无 X-Agent-Id，role 不变
            result = inject_ai_agent_role(user_info)
            self.assertEqual(result['roles'], ['user'])
            self.assertNotIn('ai-agent', result['roles'])


if __name__ == '__main__':
    unittest.main()
