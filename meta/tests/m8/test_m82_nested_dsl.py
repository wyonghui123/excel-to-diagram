"""M8 VP-2 Nested WHERE DSL 测试。

[M8 2026-06-06] 嵌套 WHERE DSL 单元测试。

覆盖：
- AND / OR / NOT 组合
- IN / BETWEEN / IS NULL
- 跨实体路径（生成 JOIN）
- 深度限制（MAX_DEPTH=5）
- 条件数限制（MAX_CONDITIONS=100）
- 冲突 op（and + or）
- 错误码

不依赖 DB（纯 SQL 构造测试）。
"""
import pytest


class TestNestedWhereEmpty:
    """M8 VP-2.1 空 DSL。"""

    def test_empty_where(self):
        from meta.core.nested_where_dsl import NestedWhereParser
        sql, params, joins = NestedWhereParser().parse({})
        assert sql == '1=1'
        assert params == []
        assert joins == []

    def test_none_where(self):
        from meta.core.nested_where_dsl import NestedWhereParser
        sql, params, joins = NestedWhereParser().parse(None)
        assert sql == '1=1'


class TestNestedWhereLogical:
    """M8 VP-2.2 AND/OR/NOT 组合。"""

    def test_and_two_conditions(self):
        from meta.core.nested_where_dsl import NestedWhereParser
        sql, params, _ = NestedWhereParser().parse({
            'and': [
                {'status__eq': 'active'},
                {'total__gt': 100},
            ],
        })
        assert 'status = ?' in sql
        assert 'total > ?' in sql
        assert params == ['active', 100]

    def test_or_two_conditions(self):
        from meta.core.nested_where_dsl import NestedWhereParser
        sql, params, _ = NestedWhereParser().parse({
            'or': [
                {'name__ilike': '张'},
                {'code__ilike': 'U001'},
            ],
        })
        assert 'OR' in sql
        assert params == ['张', 'U001']

    def test_not_inverts(self):
        from meta.core.nested_where_dsl import NestedWhereParser
        sql, params, _ = NestedWhereParser().parse({
            'not': {'status__eq': 'deleted'},
        })
        assert 'NOT' in sql
        assert params == ['deleted']

    def test_complex_nested_a_or_b_and_c_or_d(self):
        from meta.core.nested_where_dsl import NestedWhereParser
        sql, params, _ = NestedWhereParser().parse({
            'and': [
                {'or': [
                    {'customer.region__eq': '上海'},
                    {'customer.tier__eq': 'gold'},
                ]},
                {'and': [
                    {'create_date__gte': '2024-01-01'},
                    {'status__in': ['paid', 'shipped']},
                ]},
            ],
        })
        assert 'AND' in sql
        assert 'OR' in sql
        assert len(params) == 5
        assert '上海' in params
        assert 'gold' in params

    def test_single_condition_no_and_or(self):
        from meta.core.nested_where_dsl import NestedWhereParser
        sql, params, _ = NestedWhereParser().parse({
            'status__eq': 'active',
        })
        assert 'status = ?' in sql
        assert params == ['active']


class TestNestedWhereOps:
    """M8 VP-2.3 操作符完整集。"""

    def test_eq(self):
        from meta.core.nested_where_dsl import NestedWhereParser
        sql, params, _ = NestedWhereParser().parse({'a__eq': 1})
        assert '= ?' in sql
        assert params == [1]

    def test_ne(self):
        from meta.core.nested_where_dsl import NestedWhereParser
        sql, params, _ = NestedWhereParser().parse({'a__ne': 1})
        assert '!= ?' in sql

    def test_gt(self):
        from meta.core.nested_where_dsl import NestedWhereParser
        sql, params, _ = NestedWhereParser().parse({'a__gt': 100})
        assert '> ?' in sql

    def test_gte(self):
        from meta.core.nested_where_dsl import NestedWhereParser
        sql, params, _ = NestedWhereParser().parse({'a__gte': 100})
        assert '>= ?' in sql

    def test_lt(self):
        from meta.core.nested_where_dsl import NestedWhereParser
        sql, params, _ = NestedWhereParser().parse({'a__lt': 100})
        assert '< ?' in sql

    def test_lte(self):
        from meta.core.nested_where_dsl import NestedWhereParser
        sql, params, _ = NestedWhereParser().parse({'a__lte': 100})
        assert '<= ?' in sql

    def test_in(self):
        from meta.core.nested_where_dsl import NestedWhereParser
        sql, params, _ = NestedWhereParser().parse({'a__in': [1, 2, 3]})
        assert 'IN' in sql
        assert '?,?,?' in sql
        assert params == [1, 2, 3]

    def test_in_empty_returns_false(self):
        from meta.core.nested_where_dsl import NestedWhereParser
        sql, params, _ = NestedWhereParser().parse({'a__in': []})
        assert sql == '1=0'

    def test_not_in(self):
        from meta.core.nested_where_dsl import NestedWhereParser
        sql, params, _ = NestedWhereParser().parse({'a__not_in': [1, 2]})
        assert 'NOT IN' in sql
        assert params == [1, 2]

    def test_not_in_empty_returns_true(self):
        from meta.core.nested_where_dsl import NestedWhereParser
        sql, params, _ = NestedWhereParser().parse({'a__not_in': []})
        assert sql == '1=1'

    def test_like(self):
        from meta.core.nested_where_dsl import NestedWhereParser
        sql, params, _ = NestedWhereParser().parse({'a__like': '%foo%'})
        assert 'LIKE ?' in sql
        assert params == ['%foo%']

    def test_ilike(self):
        from meta.core.nested_where_dsl import NestedWhereParser
        sql, params, _ = NestedWhereParser().parse({'a__ilike': 'foo'})
        assert 'ILIKE ?' in sql

    def test_regex(self):
        from meta.core.nested_where_dsl import NestedWhereParser
        sql, params, _ = NestedWhereParser().parse({'a__regex': '^A[0-9]+$'})
        assert 'REGEXP ?' in sql
        assert params == ['^A[0-9]+$']

    def test_iregex(self):
        from meta.core.nested_where_dsl import NestedWhereParser
        sql, params, _ = NestedWhereParser().parse({'a__iregex': 'foo'})
        assert 'REGEXP ? COLLATE NOCASE' in sql

    def test_between(self):
        from meta.core.nested_where_dsl import NestedWhereParser
        sql, params, _ = NestedWhereParser().parse({
            'a__between': {'start': 100, 'end': 1000},
        })
        assert 'BETWEEN ? AND ?' in sql
        assert params == [100, 1000]

    def test_is_null(self):
        from meta.core.nested_where_dsl import NestedWhereParser
        sql, params, _ = NestedWhereParser().parse({'a__is_null': True})
        assert 'IS NULL' in sql
        assert params == []

    def test_is_not_null(self):
        from meta.core.nested_where_dsl import NestedWhereParser
        sql, params, _ = NestedWhereParser().parse({'a__is_not_null': True})
        assert 'IS NOT NULL' in sql


class TestNestedWherePath:
    """M8 VP-2.4 跨实体路径（自动生成 JOIN）。"""

    def test_single_hop_path_generates_join(self):
        from meta.core.nested_where_dsl import NestedWhereParser
        sql, params, joins = NestedWhereParser().parse({
            'customer.region__eq': '上海',
        })
        assert any('LEFT JOIN customer' in j for j in joins)
        assert any('customer_id' in j for j in joins)

    def test_two_hop_path_generates_chain_join(self):
        from meta.core.nested_where_dsl import NestedWhereParser
        sql, params, joins = NestedWhereParser().parse({
            'customer.region.country__eq': 'CN',
        })
        # 至少有一个 JOIN
        assert len(joins) >= 1

    def test_path_in_or_conditions(self):
        from meta.core.nested_where_dsl import NestedWhereParser
        sql, params, joins = NestedWhereParser().parse({
            'or': [
                {'customer.region__eq': '上海'},
                {'customer.tier__eq': 'gold'},
            ],
        })
        # OR 内的 path 也应生成 JOIN
        assert len(joins) >= 1


class TestNestedWhereErrors:
    """M8 VP-2.5 错误处理。"""

    def test_too_deep_raises(self):
        from meta.core.nested_where_dsl import NestedWhereParser, NestedWhereError
        deep_where = {
            'and': [
                {'a__eq': 1},
                {'and': [
                    {'b__eq': 2},
                    {'and': [
                        {'c__eq': 3},
                        {'and': [
                            {'d__eq': 4},
                            {'and': [
                                {'e__eq': 5},
                                {'and': [
                                    {'f__eq': 6},
                                ]},
                            ]},
                        ]},
                    ]},
                ]},
            ],
        }
        with pytest.raises(NestedWhereError) as exc_info:
            NestedWhereParser().parse(deep_where)
        assert exc_info.value.code == 'nested_where_too_deep'

    def test_conflicting_logical_ops_raises(self):
        from meta.core.nested_where_dsl import NestedWhereParser, NestedWhereError
        with pytest.raises(NestedWhereError) as exc_info:
            NestedWhereParser().parse({'and': [], 'or': []})
        assert exc_info.value.code == 'conflicting_logical_ops'

    def test_too_many_conditions_raises(self):
        from meta.core.nested_where_dsl import NestedWhereParser, NestedWhereError
        big_where = {'and': [{'a__eq': i} for i in range(200)]}
        with pytest.raises(NestedWhereError) as exc_info:
            NestedWhereParser().parse(big_where)
        assert exc_info.value.code == 'too_many_conditions'

    def test_invalid_in_value_raises(self):
        from meta.core.nested_where_dsl import NestedWhereParser, NestedWhereError
        with pytest.raises(NestedWhereError) as exc_info:
            NestedWhereParser().parse({'a__in': 'not_a_list'})
        assert exc_info.value.code == 'invalid_in_value'

    def test_invalid_between_raises(self):
        from meta.core.nested_where_dsl import NestedWhereParser, NestedWhereError
        with pytest.raises(NestedWhereError) as exc_info:
            NestedWhereParser().parse({'a__between': 'wrong_format'})
        assert exc_info.value.code == 'invalid_between'

    def test_unknown_op_raises(self):
        from meta.core.nested_where_dsl import NestedWhereParser, NestedWhereError
        with pytest.raises(NestedWhereError) as exc_info:
            NestedWhereParser().parse({'a__unknown_op': 1})
        assert exc_info.value.code == 'unknown_op'

    def test_invalid_where_node_raises(self):
        from meta.core.nested_where_dsl import NestedWhereParser, NestedWhereError
        with pytest.raises(NestedWhereError) as exc_info:
            NestedWhereParser().parse("not_a_dict")
        assert exc_info.value.code == 'invalid_where_node'


class TestNestedWhereBlueprint:
    """M8 VP-2.6 Blueprint 集成。"""

    def test_dsl_blueprint_registered(self):
        from meta.api.m8_api import query_dsl_bp
        assert query_dsl_bp.name == 'm8_query_dsl'
        assert query_dsl_bp.url_prefix == '/api/v1'
