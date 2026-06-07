"""
test_yaml_files.py - M11 v1.4.0 10 entity YAML 规则验证

TODO-6 验证：
- 8 个新 YAML 加载成功
- 每个 entity 的关键规则存在
- 10 entity 端到端 5 角色场景
"""
import os
import sys
import unittest
import tempfile
import shutil
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


# rls_rules/ 目录下的 10 entity
ALL_ENTITIES = [
    'order', 'user', 'product', 'role', 'user_group',
    'business_object', 'version', 'domain', 'sub_domain', 'service_module',
]


class TestYAMLFilesLoad(unittest.TestCase):
    """所有 rls_rules/*.yaml 加载测试"""

    def setUp(self):
        from rls.loader import RLSLoader
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None
        # 真实 rls_rules/ 目录
        self.rules_dir = os.path.join(
            _PROJECT_ROOT, 'rls_rules'
        )

    def tearDown(self):
        from rls.loader import RLSLoader
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None

    def test_10_entity_files_exist(self):
        """10 entity YAML 文件存在"""
        for entity in ALL_ENTITIES:
            yaml_path = os.path.join(self.rules_dir, f'{entity}.yaml')
            self.assertTrue(
                os.path.isfile(yaml_path),
                f'{entity}.yaml 不存在'
            )

    def test_10_entities_load_successfully(self):
        """10 entity 加载成功"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.rules_dir)
        from rls.loader import RLSLoader
        rules = RLSLoader.get_instance().load_all()
        for entity in ALL_ENTITIES:
            self.assertIn(
                entity, rules,
                f'{entity} 加载失败：{list(rules.keys())}'
            )

    def test_each_entity_has_row_filters(self):
        """每个 entity 都有 row_filters"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.rules_dir)
        from rls.loader import RLSLoader
        rules = RLSLoader.get_instance().load_all()
        for entity in ALL_ENTITIES:
            self.assertIn(
                'row_filters', rules[entity],
                f'{entity} 缺少 row_filters'
            )
            self.assertGreater(
                len(rules[entity]['row_filters']), 0,
                f'{entity}.row_filters 为空'
            )

    def test_each_entity_has_field_masks(self):
        """每个 entity 都有 field_masks"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.rules_dir)
        from rls.loader import RLSLoader
        rules = RLSLoader.get_instance().load_all()
        for entity in ALL_ENTITIES:
            self.assertIn(
                'field_masks', rules[entity],
                f'{entity} 缺少 field_masks'
            )

    def test_each_entity_has_actions(self):
        """每个 entity 都有 actions"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.rules_dir)
        from rls.loader import RLSLoader
        rules = RLSLoader.get_instance().load_all()
        for entity in ALL_ENTITIES:
            self.assertIn(
                'actions', rules[entity],
                f'{entity} 缺少 actions'
            )
            # read 必须被允许
            self.assertIn(
                'read', rules[entity]['actions'],
                f'{entity} actions 中缺少 read'
            )

    def test_admin_role_allows_everything(self):
        """admin 角色在所有 entity 都允许 create/read/update/delete"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.rules_dir)
        from rls.loader import RLSLoader
        rules = RLSLoader.get_instance().load_all()
        for entity in ALL_ENTITIES:
            actions = rules[entity]['actions']
            for act in ['create', 'read', 'update', 'delete']:
                self.assertIn(
                    'role:admin', actions.get(act, []),
                    f'admin 应能 {act} {entity}'
                )


class TestYAMLFilesFiveRoles(unittest.TestCase):
    """10 entity × 5 角色 端到端"""

    ROLES = ['admin', 'manager', 'user', 'viewer', 'ai-agent']

    def setUp(self):
        from rls.loader import RLSLoader
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None
        self.rules_dir = os.path.join(
            _PROJECT_ROOT, 'rls_rules'
        )

    def tearDown(self):
        from rls.loader import RLSLoader
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None

    def test_10_entities_5_roles_50_scenarios(self):
        """10 entity × 5 角色 = 50 场景 read 操作全部允许"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.rules_dir)
        from meta.core.interceptors.permission_interceptor import _check_yaml_permission
        failed = []
        for role in self.ROLES:
            for entity in ALL_ENTITIES:
                user_info = {'id': 1, 'roles': [role]}
                result = _check_yaml_permission(user_info, entity, 'read')
                if result is not True:
                    failed.append(f'{role}->{entity}.read（{result}）')
        self.assertEqual(
            failed, [],
            f'50 场景失败：{failed[:5]}...'
        )

    def test_10_entities_have_company_id_filter(self):
        """10 entity 中 user/viewer 角色都获得 company_id 过滤"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.rules_dir)
        from meta.core.interceptors.permission_interceptor import _check_yaml_row_filter
        for entity in ALL_ENTITIES:
            for role in ['user', 'viewer']:
                user_info = {'id': 1, 'roles': [role]}
                result = _check_yaml_row_filter(
                    user_info, entity, '', user_id=1
                )
                self.assertIsNotNone(
                    result,
                    f'{role} 角色在 {entity} 应获得 row_filter（实际 None）'
                )
                self.assertIn(
                    'company_id', result,
                    f'{role} 角色在 {entity} 应含 company_id（实际：{result[:50]}）'
                )

    def test_10_entities_ai_agent_has_is_public_filter(self):
        """10 entity 中 ai-agent 角色都获得 is_public/is_published 过滤"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.rules_dir)
        from meta.core.interceptors.permission_interceptor import _check_yaml_row_filter
        for entity in ALL_ENTITIES:
            user_info = {'id': 1, 'roles': ['ai-agent']}
            result = _check_yaml_row_filter(
                user_info, entity, '', user_id=1
            )
            # 接受 is_public / is_published 两种字段名（业务差异）
            self.assertTrue(
                'is_public' in result or 'is_published' in result,
                f'{entity} ai-agent 条件应含 is_public/is_published（实际：{result}）'
            )


if __name__ == '__main__':
    unittest.main()
