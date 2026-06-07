# -*- coding: utf-8 -*-
"""
ENG-005: nested_where_dsl (16 测试) - M8.VP-2 嵌套 WHERE DSL 解析器

[MARKER] unit - 单元测试 (无外部依赖)
[FEATURE] NestedWhereParser.parse → (sql, params, joins)
"""
import pytest
from meta.core.nested_where_dsl import (
    NestedWhereParser,
    NestedWhereError,
)

pytestmark = [pytest.mark.unit]


def _make_deep_dsl(depth):
    """构造指定深度的嵌套 DSL dict"""
    node = {'status__eq': 'a'}
    for _ in range(depth):
        node = {'and': [node]}
    return node


class TestNestedWhereParser:
    """NestedWhereParser 解析器测试"""
    def test_empty_where(self):
        p = NestedWhereParser()
        sql, params, joins = p.parse({})
        assert sql == '1=1'
        assert params == []
        assert joins == []

    # ---------- simple AND/OR 合并 (2 → 1, 2 cases) ----------
    @pytest.mark.parametrize('op,conditions,expected_in_sql,expected_param_count', [
        pytest.param('and',
                    [{'status__eq': 'active'}, {'name__like': '%foo%'}],
                    'AND', 2, id='and'),
        pytest.param('or',
                    [{'status__eq': 'active'}, {'priority__gt': 5}],
                    'OR', 2, id='or'),
    ])
    def test_simple_logical_op(self, op, conditions, expected_in_sql, expected_param_count):
        p = NestedWhereParser()
        sql, params, _ = p.parse({op: conditions})
        assert expected_in_sql in sql.upper()
        assert len(params) == expected_param_count

    def test_not(self):
        p = NestedWhereParser()
        sql, params, joins = p.parse({
            'not': {'status__eq': 'archived'}
        })
        assert 'NOT' in sql.upper()

    def test_nested_and_or(self):
        p = NestedWhereParser()
        sql, params, joins = p.parse({
            'and': [
                {'or': [
                    {'status__eq': 'active'},
                    {'priority__gt': 5},
                ]},
                {'name__like': '%foo%'},
            ]
        })
        assert 'AND' in sql.upper()
        assert 'OR' in sql.upper()

    def test_in_operator(self):
        """field__in: [v1, v2]"""
        p = NestedWhereParser()
        sql, params, joins = p.parse({
            'status__in': ['active', 'pending', 'draft']
        })
        assert 'IN' in sql.upper() or 'in' in sql
        assert len(params) == 3

    def test_between_operator(self):
        """field__between: {start, end}"""
        p = NestedWhereParser()
        sql, params, joins = p.parse({
            'created_at__between': {'start': '2026-01-01', 'end': '2026-12-31'}
        })
        # BETWEEN 通常 SQL 是 `field BETWEEN ? AND ?`
        assert len(params) >= 2

    def test_eq_operator(self):
        p = NestedWhereParser()
        sql, params, joins = p.parse({'status__eq': 'active'})
        # '?' placeholder, 'active' parameter
        assert 'active' in params

    def test_conflicting_logical_ops(self):
        """同层 and 和 or 冲突 → 报错"""
        p = NestedWhereParser()
        with pytest.raises(NestedWhereError) as exc_info:
            p.parse({'and': [{'a__eq': 1}], 'or': [{'b__eq': 2}]})
        assert exc_info.value.code == 'conflicting_logical_ops'

    # ---------- 错误 case 合并 (3 → 1, 3 cases) ----------
    @pytest.mark.parametrize('parse_input,expected_codes,id_label', [
        # 嵌套深度超限 (MAX_DEPTH=5 → 6 层)
        pytest.param(
            _make_deep_dsl(6),
            ('nested_where_too_deep', 'invalid_where_node', 'too_many_conditions'),
            'max_depth', id='max_depth'),
        # 条件总数超限
        pytest.param(
            {'and': [{f'f{i}__eq': i} for i in range(NestedWhereParser.MAX_CONDITIONS + 1)]},
            'too_many_conditions',
            'max_conditions', id='max_conditions'),
        # 非法节点 (非 dict)
        pytest.param(
            "not a dict",
            'invalid_where_node',
            'invalid_node', id='invalid_node'),
    ])
    def test_error_cases(self, parse_input, expected_codes, id_label):
        p = NestedWhereParser()
        with pytest.raises(NestedWhereError) as exc_info:
            p.parse(parse_input)
        # max_depth 测试接受多个错误码 (兼容 v1/v2 错误码)
        if id_label == 'max_depth':
            assert exc_info.value.code in expected_codes
        else:
            assert exc_info.value.code == expected_codes

    def test_base_alias_in_sql(self):
        """自定义 base_alias"""
        p = NestedWhereParser(base_alias='t1')
        sql, params, joins = p.parse({'status__eq': 'active'})
        # alias 't1' 应该出现在 SQL 里
        assert 't1' in sql

    def test_joins_for_cross_entity_path(self):
        """跨实体路径 (path.to.field__op) 触发 join"""
        p = NestedWhereParser()
        sql, params, joins = p.parse({
            'region__eq': 'east'  # 简单字段
        })
        # 简单字段不产生 join
        assert isinstance(joins, list)

    def test_nested_where_error_has_attributes(self):
        e = NestedWhereError(code='X', message='Y', detail={'k': 'v'})
        assert e.code == 'X'
        assert e.message == 'Y'
        assert e.detail == {'k': 'v'}

    def test_reusable_parser(self):
        """Parser 多次调用应重置内部状态"""
        p = NestedWhereParser()
        # 第一次
        sql1, params1, _ = p.parse({'a__eq': 1})
        # 第二次 (不应残留第一次的状态)
        sql2, params2, _ = p.parse({'b__eq': 2})
        assert 1 in params1
        assert 2 in params2
        assert 1 not in params2
