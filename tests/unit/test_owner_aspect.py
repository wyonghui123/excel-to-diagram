# -*- coding: utf-8 -*-
r"""
M2.4 Aspect 测试 — owner_aspect 与 Draft 模式

测试覆盖：
1. owner_aspect 字段定义（owner_id, visibility）
2. authorization scope 表达式
3. actions 定义（publish, make_draft, transfer_owner）
4. BO schema 加载器识别 owner_id
5. RuntimeDimensionResolver.resolve_owner_filter
6. resolve_with_owner 组合

通过 test.py 入口运行：
    python d:\filework\test.py --file d:\filework\excel-to-diagram\tests\unit\test_owner_aspect.py
"""
import sys
import os
import yaml
import unittest

sys.path.insert(0, 'd:/filework/excel-to-diagram')

from meta.core.feature_flags import set_flag, clear_cache
from meta.core.bo_schema_loader import get_bo_schema_loader
from meta.core.runtime_dimension_resolver import get_runtime_dimension_resolver


class TestOwnerAspect(unittest.TestCase):
    """owner_aspect 单元测试"""

    ASPECTS_PATH = 'd:/filework/excel-to-diagram/meta/schemas/aspects.yaml'

    @classmethod
    def setUpClass(cls):
        with open(cls.ASPECTS_PATH, 'r', encoding='utf-8') as f:
            cls.aspects = yaml.safe_load(f) or {}

    def setUp(self):
        clear_cache()
        get_bo_schema_loader().clear_cache()
        set_flag('ENABLE_OWNER_FILTER', True)
        set_flag('ENABLE_DRAFT_PATTERN', True)

    def test_01_owner_aspect_exists(self):
        """测试：owner_aspect 在 aspects.yaml 中存在"""
        self.assertIn('owner_aspect', self.aspects)

    def test_02_owner_aspect_has_owner_id_field(self):
        """测试：owner_aspect 包含 owner_id 字段"""
        oa = self.aspects['owner_aspect']
        field_ids = [f.get('id') for f in oa.get('fields', [])]
        self.assertIn('owner_id', field_ids)

    def test_03_owner_aspect_has_visibility_field(self):
        """测试：owner_aspect 包含 visibility 字段（FR-010）"""
        oa = self.aspects['owner_aspect']
        field_ids = [f.get('id') for f in oa.get('fields', [])]
        self.assertIn('visibility', field_ids)

    def test_04_visibility_default_is_draft(self):
        """测试：visibility 默认值是 draft"""
        oa = self.aspects['owner_aspect']
        for f in oa.get('fields', []):
            if f.get('id') == 'visibility':
                self.assertEqual(f.get('default'), 'draft')
                return
        self.fail('visibility field not found')

    def test_05_visibility_has_enum_values(self):
        """测试：visibility 有 3 个枚举值：public/draft/team"""
        oa = self.aspects['owner_aspect']
        for f in oa.get('fields', []):
            if f.get('id') == 'visibility':
                enums = f.get('semantics', {}).get('enum_values', [])
                values = [e.get('value') for e in enums]
                self.assertIn('public', values)
                self.assertIn('draft', values)
                self.assertIn('team', values)
                return
        self.fail('visibility field not found')

    def test_06_authorization_scope(self):
        """测试：authorization.scope 表达式正确（visibility OR owner）"""
        oa = self.aspects['owner_aspect']
        auth = oa.get('authorization', {})
        self.assertTrue(auth.get('check'))
        scope = auth.get('scope', '')
        self.assertIn("visibility = 'public'", scope)
        self.assertIn('owner_id', scope)
        self.assertIn('$user.id', scope)

    def test_07_authorization_allow_transfer(self):
        """测试：authorization.allow_transfer = true"""
        oa = self.aspects['owner_aspect']
        auth = oa.get('authorization', {})
        self.assertTrue(auth.get('allow_transfer'))

    def test_08_actions_exist(self):
        """测试：actions 包含 publish/make_draft/transfer_owner"""
        oa = self.aspects['owner_aspect']
        action_ids = [a.get('id') for a in oa.get('actions', [])]
        self.assertIn('publish', action_ids)
        self.assertIn('make_draft', action_ids)
        self.assertIn('transfer_owner', action_ids)

    def test_09_publish_action(self):
        """测试：publish action 转换 visibility 到 public"""
        oa = self.aspects['owner_aspect']
        for a in oa.get('actions', []):
            if a.get('id') == 'publish':
                self.assertEqual(a.get('to_state'), 'public')
                self.assertIn('draft', a.get('from_states', []))
                return
        self.fail('publish action not found')

    def test_10_transfer_owner_audit(self):
        """测试：transfer_owner action 启用审计"""
        oa = self.aspects['owner_aspect']
        for a in oa.get('actions', []):
            if a.get('id') == 'transfer_owner':
                audit = a.get('audit', {})
                self.assertTrue(audit.get('log'))
                return
        self.fail('transfer_owner action not found')

    # ---- 集成测试 ----

    def test_11_bo_schema_loader_detects_owner(self):
        """测试：BO schema 加载器正确识别 owner_id"""
        loader = get_bo_schema_loader()
        # version BO 引用 owner_aspect
        self.assertTrue(loader.has_owner_id('version'))
        self.assertTrue(loader.has_owner_id('domain'))
        self.assertTrue(loader.has_owner_id('sub_domain'))

    def test_12_bo_schema_loader_no_owner_for_user(self):
        """测试：user/role/user_group 不含 owner_id"""
        loader = get_bo_schema_loader()
        self.assertFalse(loader.has_owner_id('user'))
        self.assertFalse(loader.has_owner_id('role'))
        self.assertFalse(loader.has_owner_id('user_group'))

    def test_13_resolve_owner_filter_for_version(self):
        """测试：RuntimeDimensionResolver.resolve_owner_filter"""
        resolver = get_runtime_dimension_resolver()
        cond = resolver.resolve_owner_filter(user_id=5, bo_id='version')
        self.assertIsNotNone(cond)
        self.assertEqual(cond['field'], 'owner_id')
        self.assertEqual(cond['operator'], 'eq')
        self.assertEqual(cond['value'], 5)
        self.assertEqual(cond['source'], 'owner')

    def test_14_resolve_owner_filter_for_user_returns_none(self):
        """测试：user BO 无 owner_id，resolve_owner_filter 返回 None"""
        resolver = get_runtime_dimension_resolver()
        cond = resolver.resolve_owner_filter(user_id=5, bo_id='user')
        self.assertIsNone(cond)

    def test_15_resolve_owner_filter_disabled(self):
        """测试：Feature flag 关闭时返回 None"""
        set_flag('ENABLE_OWNER_FILTER', False)
        try:
            resolver = get_runtime_dimension_resolver()
            cond = resolver.resolve_owner_filter(user_id=5, bo_id='version')
            self.assertIsNone(cond)
        finally:
            set_flag('ENABLE_OWNER_FILTER', True)

    def test_16_resolve_with_owner_includes_owner(self):
        """测试：resolve_with_owner 包含 owner 过滤（AND 组合）"""
        resolver = get_runtime_dimension_resolver()
        # 注入测试数据
        import json
        import sqlite3
        db = resolver._db_path
        conn = sqlite3.connect(db)
        cursor = conn.cursor()
        try:
            # 清理已有
            cursor.execute("DELETE FROM role_dimension_scopes WHERE role_id = 997")
            # 创建测试角色
            cursor.execute(
                "INSERT OR IGNORE INTO roles (id, name, code, description, is_system) "
                "VALUES (997, 'Owner Aspect Test', 'owner_aspect_test', 'Test', 0)"
            )
            cursor.execute(
                "INSERT INTO role_dimension_scopes "
                "(role_id, dimension_code, dimension_values, inherit_children, scope_mode, bo_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (997, 'domain', json.dumps([1, 2]), 1, 'include', None),
            )
            conn.commit()

            # 不带 owner
            conditions = resolver.resolve(user_id=1, bo_id='domain', role_ids=[997])
            without_owner = len([c for c in conditions if c['source'] == 'owner'])
            self.assertEqual(without_owner, 0)

            # 带 owner
            conditions_with = resolver.resolve_with_owner(
                user_id=1, bo_id='domain', role_ids=[997]
            )
            owner_count = len([c for c in conditions_with if c['source'] == 'owner'])
            self.assertEqual(owner_count, 1)

            # 验证 owner 过滤在结果中
            owner_cond = next(
                (c for c in conditions_with if c['source'] == 'owner'), None
            )
            self.assertIsNotNone(owner_cond)
            self.assertEqual(owner_cond['field'], 'owner_id')
            self.assertEqual(owner_cond['value'], 1)
        finally:
            cursor.execute("DELETE FROM role_dimension_scopes WHERE role_id = 997")
            cursor.execute("DELETE FROM roles WHERE id = 997")
            conn.commit()
            conn.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
