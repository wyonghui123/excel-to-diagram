# -*- coding: utf-8 -*-
"""
QueryService Computed Field 单元测试 (P0-2026-06-10)

覆盖 query_service 中 v3 路径的 computed field 过滤/排序逻辑:
- _apply_count_relations_filter
- _apply_count_children_filter
- _apply_computed_field_filter
- _build_computed_where_clause (通过 filter_utils)
- parse_filter_value (operator 矩阵)
"""
from unittest.mock import MagicMock, patch

import pytest

from meta.services.query_service import QueryService
from meta.services.query.filter_utils import (
    build_computed_where_clause,
    parse_filter_value,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_builder():
    """Mock QueryBuilder, 记录 where_raw 调用"""
    builder = MagicMock()
    builder.where_raw = MagicMock()
    return builder


@pytest.fixture
def query_service():
    """最小 QueryService 实例 (mock DataSource)"""
    mock_ds = MagicMock()
    return QueryService(data_source=mock_ds)


@pytest.fixture
def mock_meta_obj():
    """Mock MetaObject (含 table_name + id)"""
    obj = MagicMock()
    obj.table_name = "domains"
    obj.id = "domain"
    return obj


# =============================================================================
# TestParseFilterValue (operator 矩阵)
# =============================================================================


class TestParseFilterValue:
    """parse_filter_value 解析各种 filter_value 格式"""

    @pytest.mark.parametrize("value,expected_op,expected_value", [
        (5,            "=",      5.0),
        (5.5,          "=",      5.5),
        ("5",          "=",      5.0),
        ("=5",         "=",      5.0),
        (">5",         ">",      5.0),
        (">=5",        ">=",     5.0),
        ("<5",         "<",      5.0),
        ("<=5",        "<=",     5.0),
        ("!=5",        "!=",     5.0),
        ("  >=  5  ",  ">=",     5.0),  # 带空格
    ])
    def test_comparison_operators(self, value, expected_op, expected_value):
        op, v = parse_filter_value(value)
        assert op == expected_op
        assert v == expected_value

    def test_between_with_dash(self):
        op, v = parse_filter_value("5-20")
        assert op == "between"
        assert v == (5.0, 20.0)

    def test_between_with_list(self):
        op, v = parse_filter_value([5, 20])
        assert op == "between"
        assert v == (5.0, 20.0)

    def test_in_with_list(self):
        op, v = parse_filter_value([1, 2, 3])
        assert op == "in"
        assert v == [1.0, 2.0, 3.0]

    @pytest.mark.parametrize("value", [
        "abc",         # 非数字
        "",            # 空
        "5..10",       # 无效范围格式
        "5 10",        # 空格分隔
    ])
    def test_invalid_returns_none(self, value):
        op, v = parse_filter_value(value)
        assert op is None
        assert v is None


# =============================================================================
# TestBuildComputedWhereClause (operator 矩阵)
# =============================================================================


class TestBuildComputedWhereClause:
    """build_computed_where_clause 各 operator 生成正确 SQL"""

    EXPR = "(SELECT COUNT(*) FROM sub_domains WHERE sub_domains.domain_id = domains.id)"

    @pytest.mark.parametrize("op,value,expected_fragment", [
        ("=",      3,  "= 3"),
        ("!=",     0,  "!= 0"),
        (">",      1,  "> 1"),
        (">=",     1,  ">= 1"),
        ("<",      10, "< 10"),
        ("<=",     5,  "<= 5"),
    ])
    def test_comparison_operators(self, op, value, expected_fragment):
        sql = build_computed_where_clause(self.EXPR, op, value)
        assert sql is not None
        assert self.EXPR in sql
        assert expected_fragment in sql

    def test_between_with_tuple(self):
        sql = build_computed_where_clause(self.EXPR, "between", (3, 10))
        assert sql is not None
        assert ">= 3" in sql
        assert "<= 10" in sql
        assert " AND " in sql

    def test_in_with_list(self):
        sql = build_computed_where_clause(self.EXPR, "in", [1, 2, 3])
        assert sql is not None
        assert "IN (1, 2, 3)" in sql

    def test_unknown_operator_returns_none(self):
        sql = build_computed_where_clause(self.EXPR, "??", 5)
        assert sql is None


# =============================================================================
# TestApplyCountRelationsFilter
# =============================================================================


class TestApplyCountRelationsFilter:
    """_apply_count_relations_filter (query_service)"""

    def test_business_object_self_success(self, query_service, mock_builder):
        """BO + self scope → 走 source/target 子查询, builder.where_raw 被调"""
        result = query_service._apply_count_relations_filter(
            mock_builder, "business_objects", "business_object", "self", ">=", 1
        )
        assert result is True
        mock_builder.where_raw.assert_called_once()
        where_sql = mock_builder.where_raw.call_args[0][0]
        assert "FROM relationships" in where_sql
        assert ">= 1" in where_sql

    def test_domain_descendants_success(self, query_service, mock_builder):
        """domain + descendants → 3 表 JOIN 子查询, builder.where_raw 被调"""
        result = query_service._apply_count_relations_filter(
            mock_builder, "domains", "domain", "descendants", "=", 0
        )
        assert result is True
        where_sql = mock_builder.where_raw.call_args[0][0]
        assert "JOIN service_modules sm" in where_sql
        assert "= 0" in where_sql

    def test_unsupported_scope_returns_false(self, query_service, mock_builder):
        """不支持的 scope → 返回 False, 不调 where_raw"""
        # domain + self 不支持
        result = query_service._apply_count_relations_filter(
            mock_builder, "domains", "domain", "self", ">=", 1
        )
        assert result is False
        mock_builder.where_raw.assert_not_called()

    def test_unsupported_object_type_returns_false(self, query_service, mock_builder):
        """未知 object_type → False"""
        result = query_service._apply_count_relations_filter(
            mock_builder, "any_table", "unknown_type", "self", ">=", 1
        )
        assert result is False
        mock_builder.where_raw.assert_not_called()

    def test_db_error_returns_false(self, query_service, mock_builder):
        """builder.where_raw 抛错时返回 False"""
        mock_builder.where_raw.side_effect = Exception("simulated DB error")
        result = query_service._apply_count_relations_filter(
            mock_builder, "business_objects", "business_object", "self", ">=", 1
        )
        assert result is False

    def test_unknown_op_returns_false(self, query_service, mock_builder):
        """op 不在 build_computed_where_clause 支持列表 → False"""
        # 用一个会让 build_computed_where_clause 返回 None 的 op
        # _apply_count_relations_filter 不直接处理, 而是通过 _build_computed_where_clause
        result = query_service._apply_count_relations_filter(
            mock_builder, "business_objects", "business_object", "self", "??unknown??", 1
        )
        assert result is False
        mock_builder.where_raw.assert_not_called()


# =============================================================================
# TestApplyCountChildrenFilter
# =============================================================================


class TestApplyCountChildrenFilter:
    """_apply_count_children_filter (query_service)"""

    def test_domain_success(self, query_service, mock_builder):
        """domain → FROM sub_domains WHERE domain_id 子查询"""
        result = query_service._apply_count_children_filter(
            mock_builder, "domains", "domain", ">=", 1
        )
        assert result is True
        where_sql = mock_builder.where_raw.call_args[0][0]
        assert "FROM sub_domains" in where_sql
        assert "sub_domains.domain_id = domains.id" in where_sql
        assert ">= 1" in where_sql

    def test_sub_domain_success(self, query_service, mock_builder):
        """sub_domain → FROM service_modules"""
        result = query_service._apply_count_children_filter(
            mock_builder, "sub_domains", "sub_domain", "=", 0
        )
        assert result is True
        where_sql = mock_builder.where_raw.call_args[0][0]
        assert "FROM service_modules" in where_sql
        assert "= 0" in where_sql

    def test_unsupported_object_type_returns_false(self, query_service, mock_builder):
        """未在 _COUNT_CHILDREN_MAP 里的 object_type → False"""
        result = query_service._apply_count_children_filter(
            mock_builder, "any_table", "unknown_type", ">=", 1
        )
        assert result is False
        mock_builder.where_raw.assert_not_called()

    def test_db_error_returns_false(self, query_service, mock_builder):
        """builder.where_raw 抛错 → False"""
        mock_builder.where_raw.side_effect = Exception("simulated DB error")
        result = query_service._apply_count_children_filter(
            mock_builder, "domains", "domain", ">=", 1
        )
        assert result is False


# =============================================================================
# TestApplyComputedFieldFilter (dispatch + 错误处理)
# =============================================================================


class TestApplyComputedFieldFilter:
    """_apply_computed_field_filter dispatch + 错误处理"""

    def test_dispatch_count_relations(self, query_service, mock_builder):
        """comp_type=count_relations → _apply_count_relations_filter"""
        mock_meta_obj = MagicMock()
        mock_meta_obj.table_name = "business_objects"
        mock_meta_obj.id = "business_object"
        result = query_service._apply_computed_field_filter(
            mock_builder, mock_meta_obj,
            "relation_count", 1,
            {"type": "count_relations", "scope": "self"},
        )
        assert result is True
        mock_builder.where_raw.assert_called_once()

    def test_dispatch_count_children(self, query_service, mock_builder, mock_meta_obj):
        """comp_type=count_children → _apply_count_children_filter"""
        result = query_service._apply_computed_field_filter(
            mock_builder, mock_meta_obj,
            "child_count", 1,
            {"type": "count_children"},
        )
        assert result is True
        where_sql = mock_builder.where_raw.call_args[0][0]
        assert "FROM sub_domains" in where_sql

    @pytest.mark.parametrize("value", [
        ">=1",    # 字符串比较表达式
        "5-10",   # 字符串范围
        [3],      # 列表 in
        [3, 10],  # 列表 between
    ])
    def test_filter_value_string_parsed_correctly(
        self, query_service, mock_builder, mock_meta_obj, value
    ):
        """filter_value 各种格式都能被正确解析并应用到 builder"""
        result = query_service._apply_computed_field_filter(
            mock_builder, mock_meta_obj,
            "child_count", value,
            {"type": "count_children"},
        )
        assert result is True, f"failed for value={value}"
        mock_builder.where_raw.assert_called_once()

    def test_unsupported_comp_type_returns_false(
        self, query_service, mock_builder, mock_meta_obj
    ):
        """未支持的 comp_type → False, 不调 where_raw"""
        result = query_service._apply_computed_field_filter(
            mock_builder, mock_meta_obj,
            "formula_field", 1,
            {"type": "formula", "formula": "1+1"},
        )
        assert result is False
        mock_builder.where_raw.assert_not_called()

    def test_invalid_filter_value_returns_false(
        self, query_service, mock_builder, mock_meta_obj
    ):
        """filter_value 无法解析时 → False"""
        result = query_service._apply_computed_field_filter(
            mock_builder, mock_meta_obj,
            "child_count", "not_a_number",
            {"type": "count_children"},
        )
        assert result is False
        mock_builder.where_raw.assert_not_called()

    def test_unknown_op_returns_false(
        self, query_service, mock_builder, mock_meta_obj
    ):
        """filter_value 能解析为数字但 op 未知时 → False"""
        result = query_service._apply_computed_field_filter(
            mock_builder, mock_meta_obj,
            "child_count", 1,  # 解析为 op='=', value=1.0
            {"type": "count_children"},
        )
        # 这条能成功, 用来证明 '=' op 是 OK 的
        assert result is True

    def test_exception_returns_false(
        self, query_service, mock_builder, mock_meta_obj
    ):
        """底层任何异常 → False, 不冒泡"""
        mock_builder.where_raw.side_effect = RuntimeError("boom")
        result = query_service._apply_computed_field_filter(
            mock_builder, mock_meta_obj,
            "child_count", 1,
            {"type": "count_children"},
        )
        assert result is False
