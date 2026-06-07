"""
test_loader.py - rls/loader.py 单元测试

D1 验证：
- YAML 加载基本功能
- 缓存机制
- 3 个公开 API（get_row_filters / get_field_masks / get_allowed_actions）
- 错误降级
- 角色过滤逻辑
"""
import os
import sys
import unittest
import tempfile
import shutil
from pathlib import Path

# 路径：rls/tests/test_loader.py -> d:\filework\excel-to-diagram
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# Module-level（避免依赖 setUp）
from rls.loader import (
    RLSLoader, get_loader, get_row_filters, get_field_masks,
    get_allowed_actions, clear_cache
)
from rls import get_loader as get_loader_public


class TestRLSLoader(unittest.TestCase):
    """RLSLoader 单元测试（D1）"""

    def setUp(self):
        # 每个 test 前清空单例
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None
        # 临时目录
        self.tmpdir = tempfile.mkdtemp(prefix='rls_test_')
        self._write_yaml('order.yaml', """
entity: order
row_filters:
  - applies_to: [role:user]
    condition: "user.company_id == order.company_id"
  - applies_to: [role:admin]
    condition: "true"
field_masks:
  - field: phone
    mask: "***-****-{}"
    applies_to: [role:user, role:viewer]
actions:
  create: [role:admin]
  read: [role:admin, role:user, role:viewer]
  update: [role:admin]
  delete: [role:admin]
""")
        self._write_yaml('user_entity.yaml', """
entity: user_entity
row_filters:
  - applies_to: [role:user]
    condition: "user.id == current_user_id"
""")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None

    def _write_yaml(self, filename, content):
        path = os.path.join(self.tmpdir, filename)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content.lstrip())

    # ==================== 基础加载 ====================

    def test_load_all_returns_2_entities(self):
        """加载 2 个 entity"""
        loader = get_loader(self.tmpdir)
        rules = loader.load_all()
        self.assertEqual(len(rules), 2)
        self.assertIn('order', rules)
        self.assertIn('user_entity', rules)

    def test_load_all_handles_empty_dir(self):
        """空目录返回空 dict"""
        empty_dir = tempfile.mkdtemp(prefix='rls_empty_')
        try:
            loader = get_loader(empty_dir)
            self.assertEqual(loader.load_all(), {})
        finally:
            shutil.rmtree(empty_dir, ignore_errors=True)

    def test_load_all_handles_nonexistent_dir(self):
        """不存在目录返回空 dict（不抛错）"""
        loader = get_loader('/nonexistent/path')
        self.assertEqual(loader.load_all(), {})

    # ==================== get_row_filters ====================

    def test_get_row_filters_user_role(self):
        """user 角色在 order 实体有 1 个 row_filter"""
        loader = get_loader(self.tmpdir)
        filters = loader.get_row_filters('order', 'role:user')
        self.assertEqual(len(filters), 1)
        self.assertIn('user.company_id', filters[0]['condition'])

    def test_get_row_filters_admin_role(self):
        """admin 角色在 order 实体有 1 个 row_filter（condition: true）"""
        loader = get_loader(self.tmpdir)
        filters = loader.get_row_filters('order', 'role:admin')
        self.assertEqual(len(filters), 1)
        self.assertEqual(filters[0]['condition'], 'true')

    def test_get_row_filters_unmatched_role(self):
        """manager 角色在 order 实体无 row_filter（不在 applies_to）"""
        loader = get_loader(self.tmpdir)
        filters = loader.get_row_filters('order', 'role:manager')
        self.assertEqual(filters, [])

    def test_get_row_filters_unknown_entity(self):
        """未知 entity 返回空 list"""
        loader = get_loader(self.tmpdir)
        filters = loader.get_row_filters('unknown', 'role:user')
        self.assertEqual(filters, [])

    # ==================== get_field_masks ====================

    def test_get_field_masks_user_role(self):
        """user 角色有 phone 字段脱敏"""
        loader = get_loader(self.tmpdir)
        masks = loader.get_field_masks('order', 'role:user')
        self.assertEqual(len(masks), 1)
        self.assertEqual(masks[0]['field'], 'phone')
        self.assertEqual(masks[0]['mask'], '***-****-{}')

    def test_get_field_masks_viewer_role(self):
        """viewer 角色有 phone 字段脱敏"""
        loader = get_loader(self.tmpdir)
        masks = loader.get_field_masks('order', 'role:viewer')
        self.assertEqual(len(masks), 1)

    def test_get_field_masks_admin_no_mask(self):
        """admin 角色无 phone 字段脱敏（admin 看全量）"""
        loader = get_loader(self.tmpdir)
        masks = loader.get_field_masks('order', 'role:admin')
        self.assertEqual(masks, [])

    # ==================== get_allowed_actions ====================

    def test_get_allowed_actions_user(self):
        """user 角色允许：read（create/update/delete 不可）"""
        loader = get_loader(self.tmpdir)
        actions = loader.get_allowed_actions('order', 'role:user')
        self.assertEqual(actions, ['read'])

    def test_get_allowed_actions_admin(self):
        """admin 角色允许：create + read + update + delete"""
        loader = get_loader(self.tmpdir)
        actions = loader.get_allowed_actions('order', 'role:admin')
        self.assertIn('create', actions)
        self.assertIn('read', actions)
        self.assertIn('update', actions)
        self.assertIn('delete', actions)

    def test_get_allowed_actions_viewer(self):
        """viewer 角色仅允许：read"""
        loader = get_loader(self.tmpdir)
        actions = loader.get_allowed_actions('order', 'role:viewer')
        self.assertEqual(actions, ['read'])

    # ==================== 缓存机制 ====================

    def test_cache_uses_mtime(self):
        """mtime 未变时缓存命中（不重新加载）"""
        loader = get_loader(self.tmpdir)
        loader.load_all()
        # 修改一个不存在的文件（不应报错）
        rules = loader.load_all()
        self.assertEqual(len(rules), 2)

    def test_clear_cache(self):
        """clear_cache 后重新加载"""
        loader = get_loader(self.tmpdir)
        loader.load_all()
        loader.clear_cache()
        self.assertEqual(loader._rules, {})
        self.assertEqual(loader._mtimes, {})
        # 重新加载应恢复
        rules = loader.load_all()
        self.assertEqual(len(rules), 2)

    # ==================== 错误降级 ====================

    def test_invalid_yaml_does_not_crash(self):
        """无效 YAML 不抛错（降级到空）"""
        self._write_yaml('bad.yaml', ":\ninvalid: : :")
        loader = get_loader(self.tmpdir)
        # 不应抛错
        rules = loader.load_all()
        # 有效 entity 仍加载
        self.assertIn('order', rules)

    def test_missing_entity_field_skipped(self):
        """缺少 entity 字段的 YAML 被跳过"""
        self._write_yaml('no_entity.yaml', "row_filters: []")
        loader = get_loader(self.tmpdir)
        rules = loader.load_all()
        # order 和 user_entity 仍加载
        self.assertEqual(len(rules), 2)

    # ==================== 单例 ====================

    def test_singleton(self):
        """get_loader 返回单例"""
        loader1 = get_loader(self.tmpdir)
        loader2 = get_loader(self.tmpdir)
        self.assertIs(loader1, loader2)

    def test_get_entities(self):
        """get_entities 返回所有 entity 名"""
        loader = get_loader(self.tmpdir)
        entities = loader.get_entities()
        self.assertIn('order', entities)
        self.assertIn('user_entity', entities)
        self.assertEqual(len(entities), 2)

    def test_has_rule_for(self):
        """has_rule_for 正确判断"""
        loader = get_loader(self.tmpdir)
        self.assertTrue(loader.has_rule_for('order'))
        self.assertFalse(loader.has_rule_for('unknown'))

    # ==================== 公开 API ====================

    def test_public_api_get_row_filters(self):
        """公开 API get_row_filters"""
        filters = get_row_filters('order', 'role:user', self.tmpdir)
        self.assertEqual(len(filters), 1)

    def test_public_api_get_field_masks(self):
        """公开 API get_field_masks"""
        masks = get_field_masks('order', 'role:user', self.tmpdir)
        self.assertEqual(len(masks), 1)

    def test_public_api_get_allowed_actions(self):
        """公开 API get_allowed_actions"""
        actions = get_allowed_actions('order', 'role:admin', self.tmpdir)
        self.assertIn('create', actions)

    def test_rls_init_get_loader(self):
        """rls 包的 get_loader 公开 API"""
        loader = get_loader_public(self.tmpdir)
        self.assertIsInstance(loader, RLSLoader)


if __name__ == '__main__':
    unittest.main()
