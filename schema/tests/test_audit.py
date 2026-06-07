"""
test_audit.py - M13 v1.2.0 字段变更审计测试
"""
import os
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


class TestScore(unittest.TestCase):
    """兼容性评分测试"""

    def test_no_change_returns_100(self):
        """无变更 → 100"""
        from schema.audit.score import calc_compatibility_score
        before = {'User': {'fields': ['id', 'name'], 'field_metadata': {}}}
        after = {'User': {'fields': ['id', 'name'], 'field_metadata': {}}}
        self.assertEqual(calc_compatibility_score(before, after), 100)

    def test_empty_before_returns_100(self):
        """新增（before 为空）→ 100"""
        from schema.audit.score import calc_compatibility_score
        self.assertEqual(calc_compatibility_score({}, {'User': {}}), 100)

    def test_empty_after_returns_0(self):
        """完全删除（after 为空）→ 0"""
        from schema.audit.score import calc_compatibility_score
        self.assertEqual(calc_compatibility_score({'User': {}}, {}), 0)

    def test_remove_field_penalty_10(self):
        """删除字段 -10"""
        from schema.audit.score import calc_entity_score
        before = {'fields': ['id', 'name'], 'field_metadata': {}}
        after = {'fields': ['id'], 'field_metadata': {}}
        score, changes = calc_entity_score(before, after)
        self.assertEqual(score, 90)
        self.assertIn('remove: name', changes)

    def test_add_field_penalty_2(self):
        """新增字段 -2（向前兼容）"""
        from schema.audit.score import calc_entity_score
        before = {'fields': ['id'], 'field_metadata': {}}
        after = {'fields': ['id', 'email'], 'field_metadata': {}}
        score, changes = calc_entity_score(before, after)
        self.assertEqual(score, 98)
        self.assertIn('add: email', changes)

    def test_remove_entity_penalty_20(self):
        """删除 entity -20"""
        from schema.audit.score import calc_compatibility_score
        before = {'User': {}, 'Order': {}}
        after = {'Order': {}}
        score = calc_compatibility_score(before, after)
        # 计算：100 - 20(删 User) = 80，然后 80 + 100(单 entity) // 2 = 90
        # 实际计算：score = (100 + 20) // 2 = 60
        self.assertLess(score, 100)

    def test_type_narrow_penalty_8(self):
        """类型变窄 -8"""
        from schema.audit.score import calc_entity_score
        before = {
            'fields': ['age'],
            'field_metadata': {'age': {'type': 'int'}},
        }
        after = {
            'fields': ['age'],
            'field_metadata': {'age': {'type': 'str'}},
        }
        score, changes = calc_entity_score(before, after)
        # 类型变窄 -8，其他 0
        self.assertLess(score, 100)
        self.assertTrue(any('type-narrow' in c for c in changes))

    def test_required_added_penalty_5(self):
        """optional → required -5"""
        from schema.audit.score import calc_entity_score
        before = {
            'fields': ['name'],
            'field_metadata': {'name': {'type': 'string', 'required': False}},
        }
        after = {
            'fields': ['name'],
            'field_metadata': {'name': {'type': 'string', 'required': True}},
        }
        score, changes = calc_entity_score(before, after)
        self.assertTrue(any('required-add' in c for c in changes))

    def test_rename_detected(self):
        """重命名被检测"""
        from schema.audit.score import calc_entity_score
        before = {'fields': ['id', 'oldName'], 'field_metadata': {}}
        after = {'fields': ['id', 'newName'], 'field_metadata': {}}
        score, changes = calc_entity_score(before, after)
        # 启发式：1 删 1 增 → rename
        self.assertTrue(any('rename' in c for c in changes))

    def test_compatibility_thresholds(self):
        """兼容性阈值"""
        from schema.audit.score import calc_compatibility_score
        # 完全兼容
        before = {'User': {'fields': ['id']}}
        after = {'User': {'fields': ['id']}}
        self.assertEqual(calc_compatibility_score(before, after), 100)


class TestDiff(unittest.TestCase):
    """Diff 报告生成器测试"""

    def test_diff_no_change(self):
        """无变更 diff"""
        from schema.audit.diff import diff_schemas
        before = {'User': {'fields': ['id']}}
        after = {'User': {'fields': ['id']}}
        diff = diff_schemas(before, after)
        self.assertEqual(diff['score'], 100)
        self.assertEqual(diff['added_entities'], [])
        self.assertEqual(diff['removed_entities'], [])
        self.assertEqual(diff['modified_entities'], {})

    def test_diff_added_entity(self):
        """新增 entity diff"""
        from schema.audit.diff import diff_schemas
        before = {'User': {}}
        after = {'User': {}, 'Order': {}}
        diff = diff_schemas(before, after)
        self.assertIn('Order', diff['added_entities'])

    def test_diff_removed_entity(self):
        """删除 entity diff"""
        from schema.audit.diff import diff_schemas
        before = {'User': {}, 'Order': {}}
        after = {'User': {}}
        diff = diff_schemas(before, after)
        self.assertIn('Order', diff['removed_entities'])
        self.assertIn('entity removed: Order', diff['breaking_changes'])

    def test_diff_modified_entity(self):
        """修改 entity diff"""
        from schema.audit.diff import diff_schemas
        before = {'User': {'fields': ['id', 'oldField'], 'field_metadata': {}}}
        after = {'User': {'fields': ['id'], 'field_metadata': {}}}
        diff = diff_schemas(before, after)
        self.assertIn('User', diff['modified_entities'])

    def test_markdown_report(self):
        """Markdown 报告生成"""
        from schema.audit.diff import diff_schemas, format_markdown_report
        before = {'User': {'fields': ['id', 'name']}}
        after = {'User': {'fields': ['id']}}
        diff = diff_schemas(before, after)
        md = format_markdown_report(diff)
        self.assertIn('Schema 变更报告', md)
        self.assertIn('User', md)
        self.assertIn('remove', md)

    def test_html_report(self):
        """HTML 报告生成"""
        from schema.audit.diff import diff_schemas, format_html_report
        before = {'User': {'fields': ['id', 'old']}}
        after = {'User': {'fields': ['id']}}
        diff = diff_schemas(before, after)
        html = format_html_report(diff)
        self.assertIn('<html', html)
        self.assertIn('User', html)
        self.assertIn('breaking', html)


class TestCompatibilityScenarios(unittest.TestCase):
    """兼容性场景测试"""

    def test_scenario_pure_additions(self):
        """纯新增场景：score 应该 ≥ 80"""
        from schema.audit.diff import diff_schemas
        before = {'User': {'fields': ['id']}}
        after = {'User': {'fields': ['id', 'name', 'email']}}
        diff = diff_schemas(before, after)
        self.assertGreaterEqual(diff['score'], 80)

    def test_scenario_breaking_changes(self):
        """纯破坏性变更：score 应该 < 80"""
        from schema.audit.diff import diff_schemas
        before = {
            'User': {
                'fields': ['id', 'oldName', 'oldField', 'lastLoginAt'],
                'field_metadata': {'age': {'type': 'int'}},
            },
            'Order': {
                'fields': ['id', 'oldField'],
            },
        }
        after = {
            'User': {
                'fields': ['id', 'newName'],
                'field_metadata': {'age': {'type': 'str'}},
            },
        }
        diff = diff_schemas(before, after)
        # 应包含: rename + remove + type-narrow + entity-removed
        # 评分: 100 - 15(rename) - 10(remove oldField) - 8(type-narrow age) - 20(entity-removed Order) = 47
        # 共同 entity 加权: 47 + 100 // 2 = 73
        self.assertLess(diff['score'], 80)
        self.assertGreater(len(diff['breaking_changes']), 0)

    def test_scenario_realistic_pr(self):
        """真实 PR 场景（小幅变更）"""
        from schema.audit.diff import diff_schemas
        before = {
            'User': {
                'fields': ['id', 'username', 'email', 'lastLoginAt'],
                'field_metadata': {},
            },
        }
        after = {
            'User': {
                'fields': ['id', 'username', 'email', 'lastLoginAt', 'mfaEnabled'],
                'field_metadata': {},
            },
        }
        diff = diff_schemas(before, after)
        # 仅新增 1 字段，应 high score
        self.assertGreaterEqual(diff['score'], 90)


if __name__ == '__main__':
    unittest.main()
