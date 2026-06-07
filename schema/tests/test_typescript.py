"""
test_typescript.py - M13 v1.1.0 TypeScript 导出器测试
"""
import os
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


class TestTypeScriptExporter(unittest.TestCase):
    """TypeScript 导出器单元测试"""

    def test_export_all_returns_string(self):
        """导出所有 entity 返回 string"""
        from schema.exporters.typescript import export_typescript
        content = export_typescript()
        self.assertIsInstance(content, str)
        self.assertIn('export interface', content)

    def test_export_contains_header(self):
        """导出包含 header"""
        from schema.exporters.typescript import export_typescript
        content = export_typescript()
        self.assertIn('Auto-generated', content)
        self.assertIn('DO NOT EDIT', content)

    def test_export_contains_10_entity_interfaces(self):
        """导出包含 10 entity interface"""
        from schema.exporters.typescript import export_typescript
        content = export_typescript()
        interface_count = content.count('export interface')
        self.assertGreaterEqual(
            interface_count, 10,
            f'应至少 10 interface，实际：{interface_count}'
        )

    def test_export_single_entity(self):
        """导出单个 entity"""
        from schema.exporters.typescript import export_typescript
        content = export_typescript('User')
        self.assertIn('export interface User', content)
        # 只有一个 interface
        self.assertEqual(content.count('export interface'), 1)

    def test_export_unknown_entity_raises(self):
        """未知 entity 抛 ValueError"""
        from schema.exporters.typescript import export_typescript
        with self.assertRaises(ValueError):
            export_typescript('NonExistentEntity')

    def test_python_type_to_ts_mapping(self):
        """Python 类型 → TypeScript 类型映射"""
        from schema.exporters.typescript import _to_ts_type
        # string → string
        self.assertEqual(_to_ts_type('string', {}), 'string')
        # int → number
        self.assertEqual(_to_ts_type('int', {}), 'number')
        # bool → boolean
        self.assertEqual(_to_ts_type('bool', {}), 'boolean')
        # datetime → string
        self.assertEqual(_to_ts_type('datetime', {}), 'string')
        # nullable → string | null
        self.assertEqual(_to_ts_type('string', {'nullable': True}), 'string | null')

    def test_interface_has_fields(self):
        """interface 包含字段"""
        from schema.exporters.typescript import _to_ts_interface
        entity_def = {
            'fields': ['id', 'name', 'email'],
            'field_metadata': {
                'id': {'type': 'int', 'required': True},
                'name': {'type': 'string', 'required': True},
                'email': {'type': 'string', 'required': False},
            },
        }
        content = _to_ts_interface('Test', entity_def)
        self.assertIn('export interface Test', content)
        self.assertIn('id: number;', content)
        self.assertIn('name: string;', content)
        # optional 字段加 ?
        self.assertIn('email?: string;', content)

    def test_deprecated_field_has_jsdoc(self):
        """弃用字段加 JSDoc @deprecated"""
        from schema.exporters.typescript import _to_ts_interface
        entity_def = {
            'fields': ['oldField', 'newField'],
            'field_metadata': {
                'oldField': {'type': 'string', 'deprecated': True, 'deprecation_reason': 'Use newField'},
                'newField': {'type': 'string', 'required': True},
            },
        }
        content = _to_ts_interface('Test', entity_def)
        self.assertIn('@deprecated', content)
        self.assertIn('Use newField', content)


if __name__ == '__main__':
    unittest.main()
