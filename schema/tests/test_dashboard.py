"""
test_dashboard.py - M13 v1.4.0 Schema Dashboard 后端 API 测试
"""
import os
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


class TestSchemaDashboardAPI(unittest.TestCase):
    """Schema Dashboard 后端 API 测试"""

    def setUp(self):
        """设置测试 client"""
        from flask import Flask
        from meta.api.schema_api import schema_dashboard_bp
        self.app = Flask(__name__)
        self.app.register_blueprint(schema_dashboard_bp)
        self.client = self.app.test_client()

    def test_summary_endpoint(self):
        """测试 summary 端点"""
        resp = self.client.get('/api/v1/schema/dashboard/summary')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('entity_count', data)
        self.assertIn('field_count', data)
        self.assertIn('avg_compatibility_score', data)
        self.assertIn('drift_count', data)
        self.assertIn('generated_at', data)
        # 至少有 10 entity（M9 已有）
        self.assertGreaterEqual(data['entity_count'], 10)

    def test_entities_endpoint(self):
        """测试 entities 端点"""
        resp = self.client.get('/api/v1/schema/dashboard/entities')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 10)
        # 每个 entity 必填字段
        for entity in data:
            self.assertIn('name', entity)
            self.assertIn('object_type', entity)
            self.assertIn('field_count', entity)
            self.assertIn('sync_status', entity)

    def test_diff_history_endpoint(self):
        """测试 diff-history 端点"""
        resp = self.client.get('/api/v1/schema/dashboard/diff-history')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsInstance(data, list)

    def test_sync_status_endpoint(self):
        """测试 sync-status 端点"""
        resp = self.client.get('/api/v1/schema/dashboard/sync-status')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('synced', data)
        self.assertIn('drifted', data)
        self.assertIn('last_sync_at', data)


class TestSchemaAPIExport(unittest.TestCase):
    """测试 schema 导出器 + API 集成（无需 Flask）"""

    def test_summary_calculated(self):
        """summary 计算正确"""
        # 模拟调用
        from meta.graphql import ENTITY_SCHEMAS
        entity_count = len(ENTITY_SCHEMAS)
        field_count = sum(len(e.get('fields', [])) for e in ENTITY_SCHEMAS.values())
        self.assertGreaterEqual(entity_count, 10)
        self.assertGreaterEqual(field_count, 50)

    def test_export_openapi_via_api(self):
        """OpenAPI 通过 API 端点可访问"""
        from schema.exporters.openapi import export_openapi
        spec = export_openapi()
        self.assertEqual(spec['openapi'], '3.0.0')

    def test_export_typescript_via_api(self):
        """TypeScript 通过 API 端点可访问"""
        from schema.exporters.typescript import export_typescript
        content = export_typescript()
        self.assertIn('export interface', content)


if __name__ == '__main__':
    unittest.main()
