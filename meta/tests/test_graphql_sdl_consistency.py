"""
test_graphql_sdl_consistency.py - SDL 与 Python ENTITY_SCHEMAS 一致性验证

v1.5.1 (M9 D5+ P5) 增量：
- 验证 SDL 文件存在
- 验证 10 entity 类型在 SDL 中定义
- 验证 20 root queries 在 SDL 中定义
- 验证字段在 SDL 和 Python 一致
"""
import re
import unittest
from pathlib import Path


# Module-level：避免依赖 setUp/setUpClass（兼容 test_m9.py 直接 cls() 实例化）
_SDL_PATH = Path(__file__).parent.parent / 'graphql' / 'schema.graphql'
SDL_TEXT = _SDL_PATH.read_text(encoding='utf-8')

from meta.graphql import ENTITY_SCHEMAS, ROOT_QUERIES  # noqa: E402


class TestGraphQLSDLConsistency(unittest.TestCase):
    """SDL 与 Python ENTITY_SCHEMAS 一致性"""

    def test_sdl_file_exists(self):
        """SDL 文件存在"""
        sdl_path = Path(__file__).parent.parent / 'graphql' / 'schema.graphql'
        self.assertTrue(sdl_path.exists())

    def test_sdl_defines_all_10_entities(self):
        """SDL 定义所有 10 entity"""
        for entity_name in ENTITY_SCHEMAS.keys():
            pattern = rf'type\s+{entity_name}\s*\{{'
            self.assertRegex(
                SDL_TEXT, pattern,
                f'[X] SDL 缺少 type {entity_name}'
            )

    def test_sdl_defines_all_20_root_queries(self):
        """SDL 定义所有 20 root queries"""
        for query_name in ROOT_QUERIES.keys():
            # query 形如: `user(id: ID!): User` 或 `users(page: Int = 1): [User!]!`
            pattern = rf'\b{query_name}\s*\('
            self.assertRegex(
                SDL_TEXT, pattern,
                f'[X] SDL 缺少 query {query_name}'
            )

    def test_each_entity_fields_in_sdl(self):
        """每个 entity 的 fields 在 SDL 中都有"""
        for entity_name, schema in ENTITY_SCHEMAS.items():
            # 找到 type X { ... } 块
            type_match = re.search(
                rf'type\s+{entity_name}\s*\{{([^}}]+)\}}',
                SDL_TEXT
            )
            self.assertIsNotNone(
                type_match,
                f'[X] SDL 中找不到 type {entity_name}'
            )
            type_body = type_match.group(1)

            # 检查每个 field
            for field in schema['fields']:
                pattern = rf'\b{field}\s*:'
                self.assertRegex(
                    type_body, pattern,
                    f'[X] SDL {entity_name} 缺少 field {field}'
                )

    def test_root_queries_count(self):
        """Root queries 数量 = 20（10 entity × 2）"""
        self.assertEqual(
            len(ROOT_QUERIES), 20,
            f'[X] ROOT_QUERIES 应该 20 个，实际 {len(ROOT_QUERIES)}'
        )

    def test_each_entity_has_exactly_2_queries(self):
        """每个 entity 恰好有 2 个 query（单数+复数）"""
        for entity_name in ENTITY_SCHEMAS.keys():
            # PascalCase → camelCase
            camel = entity_name[0].lower() + entity_name[1:]
            singular = camel  # user
            plural = camel + 's'  # users

            self.assertIn(
                singular, ROOT_QUERIES,
                f'[X] ROOT_QUERIES 缺少 {singular} ({entity_name})'
            )
            self.assertIn(
                plural, ROOT_QUERIES,
                f'[X] ROOT_QUERIES 缺少 {plural} ({entity_name})'
            )

    def test_field_map_snake_to_camel_consistent(self):
        """field_map 中 snake_case → camelCase 与 SDL 字段名一致"""
        for entity_name, schema in ENTITY_SCHEMAS.items():
            for snake_key, camel_value in schema['field_map'].items():
                # camel_value 应该是 SDL 中的字段名
                self.assertIn(
                    camel_value, schema['fields'],
                    f'[X] {entity_name}: field_map {snake_key}→{camel_value} 不在 fields 列表'
                )


if __name__ == '__main__':
    unittest.main()
