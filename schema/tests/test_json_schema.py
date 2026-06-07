"""
test_json_schema.py - M13 v1.1.0 JSON Schema 导出器测试
"""
import os
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


class TestJSONSchemaExporter(unittest.TestCase):
    """JSON Schema 导出器单元测试"""

    def test_export_full_json_schemas(self):
        """导出所有 entity JSON Schema"""
        from schema.exporters.json_schema import export_json_schema_all
        all_schemas = export_json_schema_all()
        self.assertGreaterEqual(
            len(all_schemas), 10,
            f'应至少 10 entity，实际：{len(all_schemas)}'
        )

    def test_export_single_entity_user(self):
        """导出 User entity JSON Schema"""
        from schema.exporters.json_schema import export_json_schema
        schema = export_json_schema('User')
        self.assertIn('$schema', schema)
        self.assertIn('http://json-schema.org/draft-07', schema['$schema'])
        self.assertEqual(schema['type'], 'object')
        self.assertEqual(schema['title'], 'User')

    def test_export_unknown_entity_raises(self):
        """未知 entity 抛 ValueError"""
        from schema.exporters.json_schema import export_json_schema
        with self.assertRaises(ValueError):
            export_json_schema('NonExistentEntity')

    def test_properties_have_types(self):
        """properties 含类型"""
        from schema.exporters.json_schema import export_json_schema
        schema = export_json_schema('User')
        for field_name, prop in schema['properties'].items():
            self.assertIn(
                'type', prop,
                f'{field_name} 应有 type，实际：{prop}'
            )

    def test_required_in_schema(self):
        """required 字段在 schema.required 中"""
        from schema.exporters.json_schema import _to_json_property
        # 模拟 entity_def
        entity_def = {
            'fields': ['id', 'name', 'email'],
            'field_metadata': {
                'id': {'type': 'int', 'required': True},
                'name': {'type': 'string', 'required': True},
                'email': {'type': 'string', 'required': False},
            },
        }
        from schema.exporters.json_schema import export_json_schema
        # Monkey-patch ENTITY_SCHEMAS
        from meta.graphql import ENTITY_SCHEMAS
        original = ENTITY_SCHEMAS.get('TestEntity')
        ENTITY_SCHEMAS['TestEntity'] = entity_def
        try:
            schema = export_json_schema('TestEntity')
            self.assertIn('required', schema)
            self.assertIn('id', schema['required'])
            self.assertIn('name', schema['required'])
            self.assertNotIn('email', schema['required'])
        finally:
            if original is None:
                ENTITY_SCHEMAS.pop('TestEntity', None)
            else:
                ENTITY_SCHEMAS['TestEntity'] = original
        # 引用 _to_json_property 避免未使用警告
        self.assertIn('type', _to_json_property('string', {}))

    def test_nullable_type_as_array(self):
        """nullable 字段类型是 [type, null]"""
        from schema.exporters.json_schema import _to_json_property
        prop = _to_json_property('string', {'nullable': True})
        self.assertEqual(prop['type'], ['string', 'null'])

    def test_deprecated_field_has_deprecated_true(self):
        """弃用字段 deprecated=true"""
        from schema.exporters.json_schema import _to_json_property
        prop = _to_json_property('string', {'deprecated': True})
        self.assertTrue(prop['deprecated'])


if __name__ == '__main__':
    unittest.main()
