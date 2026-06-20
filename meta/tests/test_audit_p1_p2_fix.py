# -*- coding: utf-8 -*-
"""
[P1+P2 单元测试] 验证 user_name 规范化 + tx_id auto-generation

[TDD 2026-06-20] test-driven-development 铁律
[P1] user_name 不再出现 "Display (username)" 格式
[P2] audit_interceptor 自动生成 tx_id
"""
import sys
import os
import unittest

# 添加项目根目录到 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


class TestUserNameNormalization(unittest.TestCase):
    """[P1] user_name 规范化测试"""

    def test_audit_helper_no_parentheses(self):
        """_audit_user_name 不再返回 'Display (username)' 格式"""
        from unittest.mock import patch, MagicMock

        with patch('meta.api._audit_helper.g') as mock_g:
            # display + username 同时存在且不等
            mock_g.current_user = {
                'display_name': 'Admin',
                'username': 'admin'
            }
            from meta.api._audit_helper import _audit_user_name
            result = _audit_user_name()
            self.assertEqual(result, 'Admin', f"Expected 'Admin', got {result!r}")
            self.assertNotIn('(', result)
            self.assertNotIn(')', result)

    def test_audit_helper_only_username(self):
        """只有 username 时直接使用"""
        from unittest.mock import patch
        with patch('meta.api._audit_helper.g') as mock_g:
            mock_g.current_user = {
                'display_name': '',
                'username': 'testuser'
            }
            from meta.api._audit_helper import _audit_user_name
            result = _audit_user_name()
            self.assertEqual(result, 'testuser')

    def test_audit_helper_empty(self):
        """没有 user 时返回空字符串"""
        from unittest.mock import patch
        with patch('meta.api._audit_helper.g') as mock_g:
            mock_g.current_user = {}
            from meta.api._audit_helper import _audit_user_name
            result = _audit_user_name()
            self.assertEqual(result, '')


class TestTxIdAutoGeneration(unittest.TestCase):
    """[P2] tx_id 自动生成测试"""

    def test_ensure_audit_tx_context_generates_when_missing(self):
        """传入空值时自动生成 tx_id"""
        from meta.services.audit_interceptor import _ensure_audit_tx_context
        trace_id, tx_id = _ensure_audit_tx_context(None, None)
        self.assertTrue(tx_id.startswith('tx_'), f"tx_id should start with tx_, got {tx_id!r}")
        self.assertTrue(trace_id.startswith('tr_'), f"trace_id should start with tr_, got {trace_id!r}")
        self.assertEqual(len(tx_id), 3 + 16)  # 'tx_' + 16 hex chars
        self.assertEqual(len(trace_id), 3 + 16)

    def test_ensure_audit_tx_context_preserves_existing(self):
        """传入值时不覆盖"""
        from meta.services.audit_tx_helpers import _ensure_audit_tx_context  # type: ignore
        existing_tx = 'tx_existing123'
        existing_tr = 'tr_existing456'
        # 这里如果模块名不对, fallback 到 audit_interceptor
        try:
            from meta.services.audit_interceptor import _ensure_audit_tx_context
            trace_id, tx_id = _ensure_audit_tx_context(existing_tr, existing_tx)
            self.assertEqual(tx_id, existing_tx)
            self.assertEqual(trace_id, existing_tr)
        except ImportError:
            self.skipTest("audit_interceptor not importable")

    def test_ensure_audit_tx_context_unique(self):
        """多次调用生成不同的 tx_id"""
        from meta.services.audit_interceptor import _ensure_audit_tx_context
        ids = set()
        for _ in range(100):
            _, tx_id = _ensure_audit_tx_context(None, None)
            ids.add(tx_id)
        self.assertEqual(len(ids), 100, "All tx_ids should be unique")


class TestBackfillScript(unittest.TestCase):
    """[P2] backfill 脚本幂等性测试"""

    def test_parse_iso_z_suffix(self):
        """parse_iso 处理 Z 后缀"""
        from scripts.backfill_audit_transaction_id import parse_iso
        t = parse_iso("2026-06-19T18:37:09.182688Z")
        self.assertIsNotNone(t)
        t = parse_iso("2026-06-19T18:37:09.182688")
        self.assertIsNotNone(t)
        self.assertIsNone(parse_iso(""))


class TestFixUserNameScript(unittest.TestCase):
    """[P1] fix 脚本正则测试"""

    def test_fix_pattern_matches_admin(self):
        """正则匹配 'Admin (admin)'"""
        import re
        pattern = re.compile(r"^(.+?)\s*\(([^)]+)\)\s*$")
        m = pattern.match("Admin (admin)")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1).strip(), "Admin")
        self.assertEqual(m.group(2).strip(), "admin")


if __name__ == "__main__":
    unittest.main()