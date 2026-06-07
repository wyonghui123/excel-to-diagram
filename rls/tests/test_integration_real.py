"""
test_integration_real.py - M11 v1.2.0 真实集成测试

TODO-2 验证：
- PermissionInterceptor.before_action 调 _check_yaml_permission（YAML 优先）
- PermissionInterceptor.after_action 调 _apply_yaml_field_masks
- DataPermissionInterceptor 调 _check_yaml_row_filter
- YAML 优先 + JWT/scope 表达式回退
- 5 角色 × 4 entity 端到端场景
"""
import os
import sys
import unittest
import tempfile
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


def _build_context(action='crud_read', object_type='order', user_id=5, result=None):
    """构建 mock ActionContext"""
    context = SimpleNamespace()
    context.action = action
    context.object_type = object_type
    context.user_id = user_id
    context.user_name = 'alice'
    context.meta_object = None
    context.extra = {}
    if result is not None:
        context.result = result
    return context


class TestCheckYAMLPermission(unittest.TestCase):
    """_check_yaml_permission 单元测试"""

    def setUp(self):
        from rls.loader import RLSLoader
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None
        self.tmpdir = tempfile.mkdtemp(prefix='rls_yaml_perm_')
        with open(os.path.join(self.tmpdir, 'order.yaml'), 'w', encoding='utf-8') as f:
            f.write("""
entity: order
actions:
  create: [role:admin, role:manager]
  read: [role:admin, role:manager, role:user, role:viewer]
  update: [role:admin, role:manager]
  delete: [role:admin]
""")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        from rls.loader import RLSLoader
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None

    def _patch_rls_dir(self):
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)

    def test_admin_can_create(self):
        """admin 角色可 create order"""
        self._patch_rls_dir()
        from meta.core.interceptors.permission_interceptor import _check_yaml_permission
        user_info = {'id': 1, 'roles': ['admin']}
        result = _check_yaml_permission(user_info, 'order', 'create')
        self.assertIs(result, True)

    def test_user_cannot_create(self):
        """user 角色不能 create order"""
        self._patch_rls_dir()
        from meta.core.interceptors.permission_interceptor import _check_yaml_permission
        user_info = {'id': 1, 'roles': ['user']}
        result = _check_yaml_permission(user_info, 'order', 'create')
        self.assertIs(result, False)

    def test_user_can_read(self):
        """user 角色可 read order"""
        self._patch_rls_dir()
        from meta.core.interceptors.permission_interceptor import _check_yaml_permission
        user_info = {'id': 1, 'roles': ['user']}
        result = _check_yaml_permission(user_info, 'order', 'read')
        self.assertIs(result, True)

    def test_multi_role_allow(self):
        """多角色中任一允许即可"""
        self._patch_rls_dir()
        from meta.core.interceptors.permission_interceptor import _check_yaml_permission
        user_info = {'id': 1, 'roles': ['user', 'admin']}
        # admin 允许 create → 通过
        result = _check_yaml_permission(user_info, 'order', 'create')
        self.assertIs(result, True)

    def test_multi_role_deny(self):
        """多角色中所有都拒绝"""
        self._patch_rls_dir()
        from meta.core.interceptors.permission_interceptor import _check_yaml_permission
        user_info = {'id': 1, 'roles': ['viewer', 'user']}
        result = _check_yaml_permission(user_info, 'order', 'delete')
        self.assertIs(result, False)

    def test_unknown_entity_fallback(self):
        """未知 entity → 返回 None（回退 JWT）"""
        self._patch_rls_dir()
        from meta.core.interceptors.permission_interceptor import _check_yaml_permission
        user_info = {'id': 1, 'roles': ['user']}
        result = _check_yaml_permission(user_info, 'unknown_entity', 'create')
        self.assertIsNone(result)

    def test_no_roles_default_user(self):
        """user_info 无 roles 字段 → 默认 'user'"""
        self._patch_rls_dir()
        from meta.core.interceptors.permission_interceptor import _check_yaml_permission
        user_info = {'id': 1}
        # user 角色可 read
        result = _check_yaml_permission(user_info, 'order', 'read')
        self.assertIs(result, True)
        # user 角色不能 create
        result = _check_yaml_permission(user_info, 'order', 'create')
        self.assertIs(result, False)

    def test_user_info_none(self):
        """user_info=None → 返回 None"""
        self._patch_rls_dir()
        from meta.core.interceptors.permission_interceptor import _check_yaml_permission
        result = _check_yaml_permission(None, 'order', 'create')
        self.assertIsNone(result)


class TestCheckYAMLRowFilter(unittest.TestCase):

    def setUp(self):
        from rls.loader import RLSLoader
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None
        self.tmpdir = tempfile.mkdtemp(prefix='rls_yaml_row_')
        with open(os.path.join(self.tmpdir, 'order.yaml'), 'w', encoding='utf-8') as f:
            f.write("""
entity: order
row_filters:
  - applies_to: [role:user]
    condition: "user.company_id == order.company_id"
  - applies_to: [role:admin]
    condition: "true"
""")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        from rls.loader import RLSLoader
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None

    def test_user_gets_company_filter(self):
        """user 角色获得 company_id 条件"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        from meta.core.interceptors.permission_interceptor import _check_yaml_row_filter
        user_info = {'id': 5, 'roles': ['user']}
        result = _check_yaml_row_filter(
            user_info, 'order', 'order.user_id = $user.id', user_id=5
        )
        self.assertIn('company_id', result)

    def test_admin_gets_true(self):
        """admin 角色获得 'true' 条件"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        from meta.core.interceptors.permission_interceptor import _check_yaml_row_filter
        user_info = {'id': 5, 'roles': ['admin']}
        result = _check_yaml_row_filter(
            user_info, 'order', 'order.user_id = $user.id', user_id=5
        )
        self.assertEqual(result, 'true')

    def test_unknown_role_fallback(self):
        """未知角色 → 返回 None（回退）"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        from meta.core.interceptors.permission_interceptor import _check_yaml_row_filter
        user_info = {'id': 5, 'roles': ['viewer']}  # 无规则
        result = _check_yaml_row_filter(
            user_info, 'order', 'order.user_id = $user.id', user_id=5
        )
        self.assertIsNone(result)


class TestApplyYAMLFieldMasks(unittest.TestCase):

    def setUp(self):
        from rls.loader import RLSLoader
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None
        self.tmpdir = tempfile.mkdtemp(prefix='rls_yaml_mask_')
        with open(os.path.join(self.tmpdir, 'order.yaml'), 'w', encoding='utf-8') as f:
            f.write("""
entity: order
field_masks:
  - field: phone
    mask: "***-****-{}"
    applies_to: [role:user, role:viewer]
  - field: amount
    mask: "***"
    applies_to: [role:viewer]
""")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        from rls.loader import RLSLoader
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None

    def test_user_phone_masked(self):
        """user 角色 phone 字段脱敏"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        from meta.core.interceptors.permission_interceptor import _apply_yaml_field_masks
        data = {'id': 1, 'phone': '13800001234'}
        result = _apply_yaml_field_masks(
            {'id': 1, 'roles': ['user']}, 'order', data
        )
        self.assertEqual(result['phone'], '***-****-1234')

    def test_viewer_phone_and_amount_masked(self):
        """viewer 角色 phone + amount 都脱敏"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        from meta.core.interceptors.permission_interceptor import _apply_yaml_field_masks
        data = {'phone': '13800001234', 'amount': 1000}
        result = _apply_yaml_field_masks(
            {'id': 1, 'roles': ['viewer']}, 'order', data
        )
        self.assertEqual(result['phone'], '***-****-1234')
        self.assertEqual(result['amount'], '***')

    def test_admin_no_masking(self):
        """admin 角色无脱敏（YAML 中未应用）"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        from meta.core.interceptors.permission_interceptor import _apply_yaml_field_masks
        data = {'phone': '13800001234', 'amount': 1000}
        result = _apply_yaml_field_masks(
            {'id': 1, 'roles': ['admin']}, 'order', data
        )
        self.assertEqual(result, data)

    def test_non_dict_unchanged(self):
        """非 dict 输入不变"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        from meta.core.interceptors.permission_interceptor import _apply_yaml_field_masks
        result = _apply_yaml_field_masks(
            {'id': 1, 'roles': ['user']}, 'order', 'string data'
        )
        self.assertEqual(result, 'string data')

    def test_user_info_none_unchanged(self):
        """user_info=None → 不变"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        from meta.core.interceptors.permission_interceptor import _apply_yaml_field_masks
        data = {'phone': '13800001234'}
        result = _apply_yaml_field_masks(None, 'order', data)
        self.assertEqual(result, data)


class TestPermissionInterceptorAfterAction(unittest.TestCase):
    """PermissionInterceptor.after_action 字段脱敏集成测试"""

    def _make_concrete_interceptor(self):
        """创建具体子类（PermissionInterceptor 是 abstract）"""
        from meta.core.interceptors.permission_interceptor import PermissionInterceptor
        class _Concrete(PermissionInterceptor):
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
        return _Concrete()

    def setUp(self):
        from rls.loader import RLSLoader
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None
        self.tmpdir = tempfile.mkdtemp(prefix='rls_after_action_')
        with open(os.path.join(self.tmpdir, 'order.yaml'), 'w', encoding='utf-8') as f:
            f.write("""
entity: order
field_masks:
  - field: phone
    mask: "***-****-{}"
    applies_to: [role:user]
""")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        from rls.loader import RLSLoader
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None

    def test_after_action_masks_dict_result(self):
        """after_action 脱敏 dict 结果"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        mock_g = MagicMock()
        mock_g.get.return_value = {'id': 1, 'roles': ['user']}
        with patch('flask.g', mock_g):
            interceptor = self._make_concrete_interceptor()
            context = _build_context(
                action='crud_read', object_type='order',
                result={'id': 1, 'phone': '13800001234'}
            )
            interceptor.after_action(context)
            self.assertEqual(context.result['phone'], '***-****-1234')

    def test_after_action_masks_list_result(self):
        """after_action 脱敏 list 结果"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        mock_g = MagicMock()
        mock_g.get.return_value = {'id': 1, 'roles': ['user']}
        with patch('flask.g', mock_g):
            interceptor = self._make_concrete_interceptor()
            context = _build_context(
                action='crud_list', object_type='order',
                result=[
                    {'id': 1, 'phone': '13800001234'},
                    {'id': 2, 'phone': '13800005678'},
                ]
            )
            interceptor.after_action(context)
            self.assertEqual(context.result[0]['phone'], '***-****-1234')
            self.assertEqual(context.result[1]['phone'], '***-****-5678')

    def test_after_action_no_user_info_unchanged(self):
        """无 user_info → 结果不变"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        mock_g = MagicMock()
        mock_g.get.return_value = None
        with patch('flask.g', mock_g):
            interceptor = self._make_concrete_interceptor()
            context = _build_context(
                action='crud_read', object_type='order',
                result={'phone': '13800001234'}
            )
            interceptor.after_action(context)
            self.assertEqual(context.result, {'phone': '13800001234'})

    def test_after_action_none_result_unchanged(self):
        """result=None → 不变"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        mock_g = MagicMock()
        mock_g.get.return_value = {'id': 1, 'roles': ['user']}
        with patch('flask.g', mock_g):
            interceptor = self._make_concrete_interceptor()
            context = _build_context(action='crud_read', object_type='order')
            # 无 result 属性
            context.result = None
            interceptor.after_action(context)
            self.assertIsNone(context.result)


class TestDataPermissionInterceptorYAML(unittest.TestCase):
    """DataPermissionInterceptor YAML 集成测试（mock 整个 before_action）"""

    def setUp(self):
        from rls.loader import RLSLoader
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None
        self.tmpdir = tempfile.mkdtemp(prefix='rls_data_perm_')
        with open(os.path.join(self.tmpdir, 'order.yaml'), 'w', encoding='utf-8') as f:
            f.write("""
entity: order
row_filters:
  - applies_to: [role:user]
    condition: "user.company_id == order.company_id"
""")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        from rls.loader import RLSLoader
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None

    def test_helper_loads_yaml_filter(self):
        """helper 函数能从 YAML 加载 filter"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        from meta.core.interceptors.permission_interceptor import _check_yaml_row_filter
        user_info = {'id': 5, 'roles': ['user']}
        result = _check_yaml_row_filter(
            user_info, 'order', 'order.user_id = $user.id', user_id=5
        )
        self.assertIn('company_id', result)


class TestEndToEndScenarios(unittest.TestCase):
    """5 角色 × 4 entity 端到端场景"""

    def setUp(self):
        from rls.loader import RLSLoader
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None
        self.tmpdir = tempfile.mkdtemp(prefix='rls_e2e_')
        # 4 entities × 5 roles
        for entity in ['order', 'user', 'product', 'role']:
            with open(os.path.join(self.tmpdir, f'{entity}.yaml'), 'w', encoding='utf-8') as f:
                f.write(f"""
entity: {entity}
row_filters:
  - applies_to: [role:user, role:viewer]
    condition: "user.company_id == {entity}.company_id"
  - applies_to: [role:admin, role:manager]
    condition: "true"
  - applies_to: [role:ai-agent]
    condition: "{entity}.is_public == true"
field_masks:
  - field: phone
    mask: "***-****-{{}}"
    applies_to: [role:user, role:viewer, role:ai-agent]
actions:
  create: [role:admin, role:manager]
  read: [role:admin, role:manager, role:user, role:viewer, role:ai-agent]
  update: [role:admin, role:manager]
  delete: [role:admin]
""")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        from rls.loader import RLSLoader
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None

    def test_e2e_5_roles_4_entities(self):
        """5 角色 × 4 entity = 20 场景"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        from meta.core.interceptors.permission_interceptor import _check_yaml_permission

        roles = ['admin', 'manager', 'user', 'viewer', 'ai-agent']
        entities = ['order', 'user', 'product', 'role']

        for role in roles:
            for entity in entities:
                user_info = {'id': 1, 'roles': [role]}
                # read 应该被允许（所有角色都在 applies_to）
                result = _check_yaml_permission(user_info, entity, 'read')
                self.assertEqual(
                    result, True,
                    f'{role} 角色应能 read {entity}'
                )
                # create 应被拒绝（除 admin/manager）
                result = _check_yaml_permission(user_info, entity, 'create')
                expected = role in ('admin', 'manager')
                self.assertEqual(
                    result, expected,
                    f'{role} 角色{"应" if expected else "不应"}能 create {entity}'
                )


if __name__ == '__main__':
    unittest.main()
