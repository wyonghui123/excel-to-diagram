"""
test_ci.py - M13 v1.3.0 CI 校验脚本测试
"""
import os
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


class TestExtractEntitySchemas(unittest.TestCase):
    """ENTITY_SCHEMAS 提取测试"""

    def test_extract_basic(self):
        """提取基本 ENTITY_SCHEMAS"""
        from schema.audit.ci_check import extract_entity_schemas_from_file
        content = '''
ENTITY_SCHEMAS = {
    'User': {
        'object_type': 'user',
        'fields': ['id', 'name'],
    },
    'Order': {
        'object_type': 'order',
        'fields': ['id', 'total'],
    },
}
'''
        result = extract_entity_schemas_from_file(content)
        self.assertIn('User', result)
        self.assertIn('Order', result)
        self.assertEqual(result['User']['fields'], ['id', 'name'])

    def test_extract_empty(self):
        """提取空文件"""
        from schema.audit.ci_check import extract_entity_schemas_from_file
        result = extract_entity_schemas_from_file('')
        self.assertEqual(result, {})

    def test_extract_syntax_error_returns_empty(self):
        """语法错误返回空 dict"""
        from schema.audit.ci_check import extract_entity_schemas_from_file
        result = extract_entity_schemas_from_file('this is @@@ invalid python')
        self.assertEqual(result, {})

    def test_extract_no_entity_schemas(self):
        """无 ENTITY_SCHEMAS 变量返回空 dict"""
        from schema.audit.ci_check import extract_entity_schemas_from_file
        result = extract_entity_schemas_from_file('x = 1\ny = 2')
        self.assertEqual(result, {})


class TestRunCICheck(unittest.TestCase):
    """run_ci_check 函数测试"""

    def test_pass_with_high_score(self):
        """高评分 → 通过"""
        from schema.audit.ci_check import run_ci_check
        before = {'User': {'fields': ['id', 'name']}}
        after = {'User': {'fields': ['id', 'name', 'email']}}
        # 新增字段 -2 → 98
        exit_code = run_ci_check(before, after, threshold=80, output_format='text')
        self.assertEqual(exit_code, 0)

    def test_fail_with_low_score(self):
        """低评分 → 失败"""
        from schema.audit.ci_check import run_ci_check
        # 多破坏性变更：rename + remove + type-narrow + entity-removed
        before = {
            'User': {
                'fields': ['id', 'oldName', 'oldField', 'lastLoginAt'],
                'field_metadata': {'age': {'type': 'int'}},
            },
            'Order': {'fields': ['id', 'oldField']},
        }
        after = {
            'User': {
                'fields': ['id', 'newName'],
                'field_metadata': {'age': {'type': 'str'}},
            },
        }
        # 评分: < 80
        exit_code = run_ci_check(before, after, threshold=80, output_format='text')
        self.assertEqual(exit_code, 1)

    def test_custom_threshold(self):
        """自定义阈值"""
        from schema.audit.ci_check import run_ci_check
        before = {'User': {'fields': ['id', 'oldField', 'another', 'yetAnother']}}
        after = {'User': {'fields': ['id']}}
        # 删除 3 字段 -30, 加权平均 → 85
        # threshold=90 应失败
        exit_code = run_ci_check(before, after, threshold=90, output_format='text')
        self.assertEqual(exit_code, 1)

    def test_json_output(self):
        """JSON 输出格式"""
        import io
        import json
        from contextlib import redirect_stdout

        from schema.audit.ci_check import run_ci_check
        before = {'User': {'fields': ['id']}}
        after = {'User': {'fields': ['id', 'name']}}

        buf = io.StringIO()
        with redirect_stdout(buf):
            run_ci_check(before, after, threshold=80, output_format='json')
        output = buf.getvalue()
        # 解析 JSON 验证
        data = json.loads(output)
        self.assertIn('score', data)
        self.assertIn('breaking_changes', data)

    def test_markdown_output(self):
        """Markdown 输出格式"""
        import io
        from contextlib import redirect_stdout

        from schema.audit.ci_check import run_ci_check
        before = {'User': {'fields': ['id', 'old']}}
        after = {'User': {'fields': ['id']}}

        buf = io.StringIO()
        with redirect_stdout(buf):
            run_ci_check(before, after, threshold=80, output_format='markdown')
        output = buf.getvalue()
        self.assertIn('Schema 变更报告', output)
        self.assertIn('User', output)


if __name__ == '__main__':
    unittest.main()
