"""
test_openapi.py - M13 v1.1.0 OpenAPI 导出器测试
"""
import os
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


class TestOpenAPIExporter(unittest.TestCase):
    """OpenAPI 导出器单元测试"""

    def test_export_full_openapi(self):
        """导出完整 OpenAPI spec"""
        from schema.exporters.openapi import export_openapi
        spec = export_openapi()
        self.assertEqual(spec['openapi'], '3.0.0')
        self.assertIn('info', spec)
        self.assertIn('paths', spec)
        self.assertIn('components', spec)

    def test_export_has_10_entities(self):
        """包含 10 entity schema（与 M9 ENTITY_SCHEMAS 一致）"""
        from schema.exporters.openapi import export_openapi
        spec = export_openapi()
        self.assertGreaterEqual(
            len(spec['components']['schemas']), 10,
            f'应至少 10 entity，实际：{len(spec["components"]["schemas"])}'
        )

    def test_export_entity_openapi_user(self):
        """导出 User entity schema"""
        from schema.exporters.openapi import export_entity_openapi
        schema = export_entity_openapi('User')
        self.assertEqual(schema['type'], 'object')
        self.assertIn('properties', schema)
        self.assertIn('id', schema['properties'])

    def test_export_unknown_entity_raises(self):
        """未知 entity 抛 ValueError"""
        from schema.exporters.openapi import export_entity_openapi
        with self.assertRaises(ValueError):
            export_entity_openapi('NonExistentEntity')

    def test_export_paths_contain_list_endpoint(self):
        """paths 包含 list 端点"""
        from schema.exporters.openapi import export_openapi
        spec = export_openapi()
        # 应有 /api/v1/user GET 路径
        list_paths = [p for p in spec['paths'] if p.startswith('/api/v1/') and p.count('/') == 3]
        self.assertGreater(
            len(list_paths), 0,
            f'应至少 1 个 list 端点，实际：{list_paths[:3]}'
        )

    def test_export_paths_contain_get_by_id(self):
        """paths 包含 get by id 端点"""
        from schema.exporters.openapi import export_openapi
        spec = export_openapi()
        # 应有 /api/v1/user/{id} GET 路径
        get_paths = [p for p in spec['paths'] if p.endswith('/{id}')]
        self.assertGreater(
            len(get_paths), 0,
            f'应至少 1 个 get-by-id 端点，实际：{get_paths[:3]}'
        )

    def test_python_type_to_openapi_mapping(self):
        """Python 类型 → OpenAPI 类型映射"""
        from schema.exporters.openapi import _to_openapi_type
        # int → integer/int64
        result = _to_openapi_type('int')
        self.assertEqual(result['type'], 'integer')
        # datetime → string/date-time
        result = _to_openapi_type('datetime')
        self.assertEqual(result['type'], 'string')
        self.assertEqual(result['format'], 'date-time')
        # bool → boolean
        result = _to_openapi_type('bool')
        self.assertEqual(result['type'], 'boolean')

    def test_required_fields_in_schema(self):
        """required 字段在 schema 中"""
        from schema.exporters.openapi import _to_openapi_schema
        entity_def = {
            'fields': ['id', 'name', 'email'],
            'field_metadata': {
                'id': {'type': 'int', 'required': True},
                'name': {'type': 'string', 'required': True},
                'email': {'type': 'string', 'required': False},
            },
        }
        schema = _to_openapi_schema('Test', entity_def)
        self.assertIn('required', schema)
        self.assertIn('id', schema['required'])
        self.assertIn('name', schema['required'])
        self.assertNotIn('email', schema['required'])


if __name__ == '__main__':
    unittest.main()
