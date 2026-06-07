"""
test_enforce.py - rls/enforce.py 单元测试

D2 验证：
- check_action: 角色权限检查（含 'role:' 前缀兼容、fail-closed）
- get_active_row_filter: 行级过滤 condition 提取
- apply_field_masks: 字段脱敏（含 {} 占位符）
- apply_field_masks_to_list: 批量脱敏
- 边界条件：None、空 dict、未知角色
"""
import os
import sys
import unittest
import tempfile
import shutil
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from rls.enforce import (
    check_action, get_active_row_filter,
    apply_field_masks, apply_field_masks_to_list,
)
from rls.loader import RLSLoader


class TestCheckAction(unittest.TestCase):
    """check_action 单元测试"""

    def setUp(self):
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None
        self.tmpdir = tempfile.mkdtemp(prefix='rls_test_enforce_')
        self._write_yaml('order.yaml', """
entity: order
actions:
  create: [role:admin, role:manager]
  read: [role:admin, role:manager, role:user, role:viewer]
  update: [role:admin, role:manager]
  delete: [role:admin]
""")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None

    def _write_yaml(self, filename, content):
        with open(os.path.join(self.tmpdir, filename), 'w', encoding='utf-8') as f:
            f.write(content.lstrip())

    def test_check_action_admin_can_create(self):
        """admin 可以 create order"""
        self.assertTrue(check_action('admin', 'order', 'create', self.tmpdir))

    def test_check_action_user_cannot_create(self):
        """user 不可以 create order"""
        self.assertFalse(check_action('user', 'order', 'create', self.tmpdir))

    def test_check_action_user_can_read(self):
        """user 可以 read order"""
        self.assertTrue(check_action('user', 'order', 'read', self.tmpdir))

    def test_check_action_viewer_can_read(self):
        """viewer 可以 read order"""
        self.assertTrue(check_action('viewer', 'order', 'read', self.tmpdir))

    def test_check_action_viewer_cannot_update(self):
        """viewer 不可以 update order"""
        self.assertFalse(check_action('viewer', 'order', 'update', self.tmpdir))

    def test_check_action_accepts_role_prefix(self):
        """支持 'role:admin' 形式"""
        self.assertTrue(check_action('role:admin', 'order', 'create', self.tmpdir))
        self.assertTrue(check_action('role:user', 'order', 'read', self.tmpdir))

    def test_check_action_unknown_entity_denied(self):
        """未知 entity 默认拒绝（fail-closed）"""
        self.assertFalse(check_action('admin', 'unknown', 'create', self.tmpdir))

    def test_check_action_unknown_action_denied(self):
        """未知 action 默认拒绝"""
        self.assertFalse(check_action('admin', 'order', 'fly', self.tmpdir))


class TestGetActiveRowFilter(unittest.TestCase):

    def setUp(self):
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None
        self.tmpdir = tempfile.mkdtemp(prefix='rls_test_enforce_')
        self._write_yaml('order.yaml', """
entity: order
row_filters:
  - applies_to: [role:user]
    condition: "user.company_id == order.company_id"
  - applies_to: [role:admin]
    condition: "true"
""")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None

    def _write_yaml(self, filename, content):
        with open(os.path.join(self.tmpdir, filename), 'w', encoding='utf-8') as f:
            f.write(content.lstrip())

    def test_user_gets_company_filter(self):
        """user 角色获得 company 过滤条件"""
        cond = get_active_row_filter('user', 'order', self.tmpdir)
        self.assertIsNotNone(cond)
        self.assertIn('company_id', cond)

    def test_admin_gets_true(self):
        """admin 角色获得 'true' 条件"""
        cond = get_active_row_filter('admin', 'order', self.tmpdir)
        self.assertEqual(cond, 'true')

    def test_viewer_no_filter(self):
        """viewer 角色无规则（返回 None）"""
        cond = get_active_row_filter('viewer', 'order', self.tmpdir)
        self.assertIsNone(cond)

    def test_unknown_entity_no_filter(self):
        """未知 entity 返回 None"""
        cond = get_active_row_filter('admin', 'unknown', self.tmpdir)
        self.assertIsNone(cond)


class TestApplyFieldMasks(unittest.TestCase):

    def setUp(self):
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None
        self.tmpdir = tempfile.mkdtemp(prefix='rls_test_enforce_')
        self._write_yaml('order.yaml', """
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
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None

    def _write_yaml(self, filename, content):
        with open(os.path.join(self.tmpdir, filename), 'w', encoding='utf-8') as f:
            f.write(content.lstrip())

    def test_user_phone_masked(self):
        """user 角色 phone 字段被脱敏"""
        data = {'id': 1, 'phone': '13800001234', 'amount': 1000}
        masked = apply_field_masks('user', 'order', data, self.tmpdir)
        self.assertEqual(masked['phone'], '***-****-1234')
        self.assertEqual(masked['amount'], 1000)  # amount 不脱敏

    def test_viewer_phone_and_amount_masked(self):
        """viewer 角色 phone + amount 都脱敏"""
        data = {'id': 1, 'phone': '13800001234', 'amount': 1000}
        masked = apply_field_masks('viewer', 'order', data, self.tmpdir)
        self.assertEqual(masked['phone'], '***-****-1234')
        self.assertEqual(masked['amount'], '***')

    def test_admin_no_masking(self):
        """admin 角色无脱敏"""
        data = {'id': 1, 'phone': '13800001234', 'amount': 1000}
        masked = apply_field_masks('admin', 'order', data, self.tmpdir)
        self.assertEqual(masked, data)

    def test_original_data_not_modified(self):
        """原 data 不被修改"""
        data = {'id': 1, 'phone': '13800001234'}
        original = dict(data)
        apply_field_masks('user', 'order', data, self.tmpdir)
        self.assertEqual(data, original)

    def test_missing_field_unchanged(self):
        """mask 规则中不存在的字段不变"""
        data = {'id': 1, 'name': 'order1'}
        masked = apply_field_masks('user', 'order', data, self.tmpdir)
        self.assertEqual(masked, data)

    def test_non_dict_data_unchanged(self):
        """非 dict 入参原样返回"""
        data = 'string data'
        masked = apply_field_masks('user', 'order', data, self.tmpdir)
        self.assertEqual(masked, 'string data')

    def test_none_value_preserved(self):
        """None 值不抛错"""
        data = {'phone': None, 'amount': 100}
        masked = apply_field_masks('user', 'order', data, self.tmpdir)
        self.assertIsNone(masked['phone'])

    def test_mask_without_placeholder(self):
        """不含 {} 占位符的 mask 直接替换"""
        # amount: "***" (no {})
        data = {'amount': 1000}
        masked = apply_field_masks('viewer', 'order', data, self.tmpdir)
        self.assertEqual(masked['amount'], '***')


class TestApplyFieldMasksToList(unittest.TestCase):

    def setUp(self):
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None
        self.tmpdir = tempfile.mkdtemp(prefix='rls_test_enforce_')
        self._write_yaml('order.yaml', """
entity: order
field_masks:
  - field: phone
    mask: "***-****-{}"
    applies_to: [role:user]
""")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None

    def _write_yaml(self, filename, content):
        with open(os.path.join(self.tmpdir, filename), 'w', encoding='utf-8') as f:
            f.write(content.lstrip())

    def test_list_masks_all(self):
        """list 中所有元素都被脱敏"""
        data = [
            {'id': 1, 'phone': '13800001234'},
            {'id': 2, 'phone': '13800005678'},
        ]
        masked = apply_field_masks_to_list('user', 'order', data, self.tmpdir)
        self.assertEqual(masked[0]['phone'], '***-****-1234')
        self.assertEqual(masked[1]['phone'], '***-****-5678')

    def test_empty_list(self):
        """空 list 返回空 list"""
        masked = apply_field_masks_to_list('user', 'order', [], self.tmpdir)
        self.assertEqual(masked, [])

    def test_non_list_passthrough(self):
        """非 list 原样返回"""
        data = {'id': 1}
        masked = apply_field_masks_to_list('user', 'order', data, self.tmpdir)
        self.assertEqual(masked, data)


if __name__ == '__main__':
    unittest.main()
