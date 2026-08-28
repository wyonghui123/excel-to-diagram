# -*- coding: utf-8 -*-
"""
P2-Matrix-02 scopeCode 3 层保护（BLOCKER）后端测试

覆盖（Spec 5.5.5 第 0 项 / 5.4.1 P2-Matrix-02）：
- ① scope_code=INVALID_VALUE → 400 SCOPE_CODE_INVALID + available_scope_codes
- ② scope_code 无效时**绝不**返回 200 OK + 空数组/全量（响应体不含 data）
- ③ 逗号分隔多编码中任一无效 → 400（与前端 scopeCode=SCP,SCM 一致）
- 有效 scope_code → 200 success（正常元数据）
- 不带 scope_code → 200 success（兼容旧行为）
"""
import os
import sys
import unittest

sys.path.insert(0, 'd:/filework/excel-to-diagram')

os.environ.setdefault('TESTING', '1')

from flask import Flask
from meta.api.permission_dimension_api import permission_dimension_bp


class TestPermissionMetaScopeCode(unittest.TestCase):
    """P2-Matrix-02 /meta scope_code 白名单校验"""

    @classmethod
    def setUpClass(cls):
        cls.app = Flask(__name__)
        cls.app.register_blueprint(permission_dimension_bp)
        cls.client = cls.app.test_client()
        cls.meta_url = '/api/v2/bo/permission_dimension/meta'

    def _get_valid_scope_code(self):
        """从数据库读一个真实存在的 sub_domain code（动态，不硬编码）"""
        import sqlite3
        conn = sqlite3.connect('meta/architecture.db')
        c = conn.cursor()
        c.execute("SELECT code FROM sub_domains WHERE code IS NOT NULL AND code != '' LIMIT 1")
        row = c.fetchone()
        conn.close()
        return row[0] if row else None

    def test_invalid_scope_code_returns_400(self):
        """① scope_code=INVALID_VALUE → 400 SCOPE_CODE_INVALID + available_scope_codes"""
        resp = self.client.get(self.meta_url, query_string={'scope_code': 'INVALID_VALUE'})
        self.assertEqual(resp.status_code, 400)
        body = resp.get_json()
        self.assertFalse(body.get('success'))
        self.assertEqual(body.get('error'), 'SCOPE_CODE_INVALID')
        # available_scope_codes 必须是数组且非空（真实库有 sub_domains.code）
        self.assertIsInstance(body.get('available_scope_codes'), list)
        self.assertTrue(len(body['available_scope_codes']) > 0)
        # ② 无效时不返回任何 data（绝不 200 OK + 空数组/全量）
        self.assertNotIn('data', body)

    def test_invalid_scope_code_never_returns_200(self):
        """② 后端 scopeCode=INVALID 绝不返回 200 OK + 空数组/全量"""
        resp = self.client.get(self.meta_url, query_string={'scope_code': 'INVALID'})
        self.assertEqual(resp.status_code, 400)
        body = resp.get_json()
        self.assertNotIn('data', body)
        self.assertIn('INVALID', body.get('message', ''))

    def test_multi_scope_code_with_one_invalid_returns_400(self):
        """③ 逗号分隔多编码中任一无效 → 400（与前端 scopeCode=SCP,SCM 一致）"""
        resp = self.client.get(
            self.meta_url, query_string={'scope_code': 'SCP,NOT_A_REAL_CODE'}
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.get_json()
        self.assertEqual(body.get('error'), 'SCOPE_CODE_INVALID')
        self.assertNotIn('data', body)

    def test_valid_scope_code_returns_200(self):
        """有效 scope_code → 200 success（正常元数据）"""
        valid_code = self._get_valid_scope_code()
        if not valid_code:
            self.skipTest('数据库无 sub_domains.code，跳过')
        resp = self.client.get(self.meta_url, query_string={'scope_code': valid_code})
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body.get('success'))
        self.assertIn('dimension_priority', body.get('data', {}))

    def test_valid_multi_scope_codes_returns_200(self):
        """多编码全部有效 → 200 success"""
        codes = []
        import sqlite3
        conn = sqlite3.connect('meta/architecture.db')
        c = conn.cursor()
        c.execute("SELECT code FROM sub_domains WHERE code IS NOT NULL AND code != '' LIMIT 2")
        codes = [r[0] for r in c.fetchall()]
        conn.close()
        if len(codes) < 2:
            self.skipTest('数据库 sub_domains.code 不足 2 个，跳过')
        resp = self.client.get(
            self.meta_url, query_string={'scope_code': ','.join(codes)}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get('success'))

    def test_no_scope_code_returns_200(self):
        """不带 scope_code → 200 success（兼容旧行为）"""
        resp = self.client.get(self.meta_url)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get('success'))

    def test_empty_scope_code_returns_200(self):
        """scope_code 为空字符串 → 200 success（视为未传）"""
        resp = self.client.get(self.meta_url, query_string={'scope_code': ''})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get('success'))


if __name__ == '__main__':
    unittest.main()
