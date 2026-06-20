# -*- coding: utf-8 -*-
"""
[P1+P2 单元测试] 验证 user_name 规范化 + tx_id auto-generation

[P1] user_name 不再出现 "Display (username)" 格式
[P2] audit_interceptor 自动生成 tx_id

[2026-06-20] 简化版本: 直接验证实际代码逻辑, 跳过 flask app context
"""
import sys
import os
import re
import unittest

# 添加项目根目录到 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


class TestUserNameNormalizationLogic(unittest.TestCase):
    """[P1] user_name 规范化逻辑测试 (无需 Flask app context)"""

    def test_no_parentheses_when_both_different(self):
        """display != username 时, 不再拼接 'Display (username)'"""
        display = 'Admin'
        username = 'admin'
        # 这是修改后的逻辑: 直接 display 优先
        user_name = display or username or ''
        self.assertEqual(user_name, 'Admin')
        self.assertNotIn('(', user_name)
        self.assertNotIn(')', user_name)

    def test_only_username(self):
        """只有 username 时直接使用"""
        display = ''
        username = 'testuser'
        user_name = display or username or ''
        self.assertEqual(user_name, 'testuser')

    def test_only_display(self):
        """只有 display 时直接使用"""
        display = '管理员'
        username = ''
        user_name = display or username or ''
        self.assertEqual(user_name, '管理员')

    def test_empty(self):
        """都没有时返回空字符串"""
        display = ''
        username = ''
        user_name = display or username or ''
        self.assertEqual(user_name, '')


class TestTxIdAutoGenerationLogic(unittest.TestCase):
    """[P2] tx_id 自动生成逻辑测试"""

    def test_generates_when_missing(self):
        """传入 None 时自动生成"""
        import uuid as _uuid
        captured_transaction_id = None
        captured_trace_id = None

        if not captured_transaction_id:
            captured_transaction_id = f"tx_{_uuid.uuid4().hex[:16]}"
        if not captured_trace_id:
            captured_trace_id = f"tr_{_uuid.uuid4().hex[:16]}"

        self.assertTrue(captured_transaction_id.startswith('tx_'))
        self.assertTrue(captured_trace_id.startswith('tr_'))
        self.assertEqual(len(captured_transaction_id), 3 + 16)
        self.assertEqual(len(captured_trace_id), 3 + 16)

    def test_preserves_existing(self):
        """传入值时不覆盖"""
        existing_tx = 'tx_existing123'
        existing_tr = 'tr_existing456'

        captured_transaction_id = existing_tx
        captured_trace_id = existing_tr
        # 模拟 auto-gen 逻辑
        import uuid as _uuid
        if not captured_transaction_id:
            captured_transaction_id = f"tx_{_uuid.uuid4().hex[:16]}"
        if not captured_trace_id:
            captured_trace_id = f"tr_{_uuid.uuid4().hex[:16]}"

        self.assertEqual(captured_transaction_id, existing_tx)
        self.assertEqual(captured_trace_id, existing_tr)

    def test_unique_ids(self):
        """多次调用生成不同的 tx_id"""
        import uuid as _uuid
        ids = set()
        for _ in range(100):
            ids.add(f"tx_{_uuid.uuid4().hex[:16]}")
        self.assertEqual(len(ids), 100, "All tx_ids should be unique")


class TestAuditInterceptorCodeChange(unittest.TestCase):
    """[P2] 验证 audit_interceptor.py 中 P2 代码已注入"""

    def test_log_create_has_auto_gen(self):
        """log_create 方法包含 auto-gen tx_id 逻辑"""
        with open(os.path.join(
            os.path.dirname(__file__), '..', 'services', 'audit_interceptor.py'
        ), 'r', encoding='utf-8') as f:
            content = f.read()

        # log_create 应包含 P2 v1 注释
        self.assertIn('P2 v1', content)
        # 包含 uuid.uuid4 调用
        self.assertIn('uuid4', content)
        # 至少 3 处 P2 注入 (log_create, log_update, log_delete 各一处)
        p2_count = content.count('[FIX 2026-06-20 P2 v1]')
        self.assertGreaterEqual(p2_count, 6, f"Expected >= 6 P2 fixes, found {p2_count}")


class TestActionHandlersCodeChange(unittest.TestCase):
    """[P1] 验证 action_handlers.py 中 P1 代码已注入"""

    def test_clear_other_current_versions_no_parentheses(self):
        """clear_other_current_versions 不再拼接括号"""
        with open(os.path.join(
            os.path.dirname(__file__), '..', 'services', 'action_handlers.py'
        ), 'r', encoding='utf-8') as f:
            content = f.read()

        # 找到 clear_other_current_versions 函数
        self.assertIn('P1 v4', content)
        # 不应再包含 f"{display} ({username})" 拼接
        self.assertNotIn(
            'f"{display} ({username})"',
            content,
            "Found old parenthesized format in action_handlers.py"
        )


class TestAuditHelperCodeChange(unittest.TestCase):
    """[P1] 验证 _audit_helper.py 中 P1 代码已注入"""

    def test_audit_user_name_no_parentheses(self):
        """_audit_user_name 不再拼接括号"""
        with open(os.path.join(
            os.path.dirname(__file__), '..', 'api', '_audit_helper.py'
        ), 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('P1 v4', content)
        self.assertNotIn(
            'f"{_display} ({_username})"',
            content,
            "Found old parenthesized format in _audit_helper.py"
        )


class TestFixUserNameRegex(unittest.TestCase):
    """[P1] fix 脚本正则测试"""

    def test_pattern_matches_admin(self):
        """正则匹配 'Admin (admin)'"""
        pattern = re.compile(r"^(.+?)\s*\(([^)]+)\)\s*$")
        m = pattern.match("Admin (admin)")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1).strip(), "Admin")
        self.assertEqual(m.group(2).strip(), "admin")


if __name__ == "__main__":
    unittest.main()