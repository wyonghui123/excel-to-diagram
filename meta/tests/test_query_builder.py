import pytest

pytestmark = pytest.mark.integration

import pytest
from unittest.mock import MagicMock, patch
from meta.core.query_builder import (
    QueryBuilder,
    QuerySpec,
    QueryCondition,
    query,
)
from meta.core.models import MetaObject, MetaField, FieldType, QueryOperator


@pytest.fixture
def mock_meta_object():
    """创建模拟元模型对象"""
    obj = MagicMock(spec=MetaObject)
    obj.table_name = "test_table"
    obj.fields = [
        MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id"),
        MetaField(id="name", name="名称", field_type=FieldType.STRING, db_column="name"),
        MetaField(id="status", name="状态", field_type=FieldType.STRING, db_column="status"),
        MetaField(id="count", name="数量", field_type=FieldType.INTEGER, db_column="count_val"),
        MetaField(id="price", name="价格", field_type=FieldType.FLOAT, db_column="price"),
        MetaField(id="is_active", name="是否激活", field_type=FieldType.BOOLEAN, db_column="is_active"),
    ]
    return obj


@pytest.fixture
def mock_datasource():
    """创建模拟数据源"""
    ds = MagicMock()
    return ds


@pytest.fixture
def builder(mock_datasource, mock_meta_object):
    """创建 QueryBuilder 实例"""
    return QueryBuilder(mock_datasource, mock_meta_object)


class TestQueryBuilderInit:
    """测试 QueryBuilder 初始化"""

    def test_init_basic(self, builder):
        assert builder._spec.table_name == "test_table"
        assert len(builder._spec.conditions) == 0
        assert len(builder._spec.sorts) == 0

    def test_init_field_map_populated(self, builder):
        assert "id" in builder._field_map
        assert "name" in builder._field_map
        assert builder._field_map["name"].db_column == "name"


class TestQueryBuilderWhere:
    """测试 WHERE 条件"""

    def test_where_eq_with_enum(self, builder):
        result = builder.where("name", QueryOperator.EQ, "test")
        assert result is builder
        assert len(builder._spec.conditions) == 1
        assert builder._spec.conditions[0].operator == QueryOperator.EQ

    def test_where_eq_string_operator(self, builder):
        builder.where("name", "eq", "test")
        assert builder._spec.conditions[0].operator == QueryOperator.EQ

    def test_where_ne(self, builder):
        builder.where_ne("status", "deleted")
        assert builder._spec.conditions[0].operator == QueryOperator.NE

    def test_where_gt_lt(self, builder):
        builder.where_gt("count", 10).where_lt("count", 100)
        assert len(builder._spec.conditions) == 2
        assert builder._spec.conditions[0].operator == QueryOperator.GT
        assert builder._spec.conditions[1].operator == QueryOperator.LT

    def test_where_ge_le(self, builder):
        builder.where_ge("price", 50.0).where_le("price", 200.0)
        assert builder._spec.conditions[0].operator == QueryOperator.GE
        assert builder._spec.conditions[1].operator == QueryOperator.LE

    def test_where_like(self, builder):
        builder.where_like("name", "%test%")
        assert builder._spec.conditions[0].operator == QueryOperator.LIKE
        assert builder._spec.conditions[0].value == "%test%"

    def test_where_in(self, builder):
        builder.where_in("status", ["active", "pending"])
        cond = builder._spec.conditions[0]
        assert cond.operator == QueryOperator.IN
        assert len(cond.values) == 2

    def test_where_not_in(self, builder):
        builder.where_not_in("status", ["deleted", "archived"])
        assert builder._spec.conditions[0].operator == QueryOperator.NOT_IN

    def test_where_between(self, builder):
        builder.where_between("price", 10.0, 100.0)
        cond = builder._spec.conditions[0]
        assert cond.operator == QueryOperator.BETWEEN
        assert cond.values == [10.0, 100.0]

    def test_where_null(self, builder):
        builder.where_null("description")
        assert builder._spec.conditions[0].operator == QueryOperator.IS_NULL

    def test_where_not_null(self, builder):
        builder.where_not_null("updated_at")
        assert builder._spec.conditions[0].operator == QueryOperator.IS_NOT_NULL


class TestQueryBuilderOrWhere:
    """测试 OR 条件组"""

    def test_or_where_single_group(self, builder):
        builder.or_where([
            ("status", QueryOperator.EQ, "active"),
            ("status", QueryOperator.EQ, "pending"),
        ])
        assert len(builder._spec.or_conditions) == 1
        assert len(builder._spec.or_conditions[0]) == 2

    def test_or_where_multiple_groups(self, builder):
        builder.or_where([("status", QueryOperator.EQ, "active")])
        builder.or_where([("type", QueryOperator.EQ, "urgent")])
        assert len(builder._spec.or_conditions) == 2


class TestQueryBuilderOrder:
    """测试排序"""

    def test_order_by_asc(self, builder):
        builder.order_by("name", "asc")
        assert builder._spec.sorts == [("name", "asc")]

    def test_order_by_desc(self, builder):
        builder.order_by("created_at", "desc")
        assert builder._spec.sorts == [("created_at", "desc")]

    def test_order_by_multiple(self, builder):
        builder.order_by("status", "asc").order_by("created_at", "desc")
        assert len(builder._spec.sorts) == 2


class TestQueryBuilderPagination:
    """测试分页"""

    def test_limit(self, builder):
        builder.limit(10)
        assert builder._spec.limit == 10

    def test_offset(self, builder):
        builder.offset(20)
        assert builder._spec.offset == 20

    def test_page_calculation(self, builder):
        builder.page(2, 10)
        assert builder._spec.offset == 10
        assert builder._spec.limit == 10

    def test_page_first(self, builder):
        builder.page(1, 20)
        assert builder._spec.limit == 20


class TestQueryBuilderSelectAndGroup:
    """测试选择和分组"""

    def test_select_fields(self, builder):
        builder.select("id", "name")
        assert builder._spec.fields == ["id", "name"]

    def test_distinct(self, builder):
        builder.distinct()
        assert builder._spec.distinct is True

    def test_group_by(self, builder):
        builder.group_by("status")
        assert builder._spec.group_by == ["status"]


class TestQueryBuilderAggregates:
    """测试聚合函数"""

    def test_count_aggregate(self, builder):
        builder.count()
        assert "count" in builder._spec.aggregates

    def test_sum_aggregate(self, builder):
        builder.sum("price", "total_price")
        assert "total_price" in builder._spec.aggregates

    def test_avg_aggregate(self, builder):
        builder.avg("price")
        assert "avg_price" in builder._spec.aggregates

    def test_max_min_aggregate(self, builder):
        builder.max("price").min("price")
        assert "max_price" in builder._spec.aggregates
        assert "min_price" in builder._spec.aggregates


class TestQueryBuilderBuildSQL:
    """测试 SQL 构建"""

    def test_build_simple_select(self, builder):
        sql, params = builder.build_sql()
        assert "SELECT * FROM test_table" in sql
        assert len(params) == 0

    def test_build_with_where(self, builder):
        builder.where("status", QueryOperator.EQ, "active")
        sql, params = builder.build_sql()
        assert "WHERE" in sql
        assert "status = ?" in sql
        assert params == ["active"]

    def test_build_with_order(self, builder):
        builder.order_by("name", "asc")
        sql, params = builder.build_sql()
        assert "ORDER BY" in sql
        assert "name ASC" in sql

    def test_build_with_pagination(self, builder):
        builder.limit(10)
        sql, params = builder.build_sql()
        assert "LIMIT 10" in sql

    def test_build_with_like(self, builder):
        builder.where_like("name", "%test%")
        sql, params = builder.build_sql()
        assert "LIKE" in sql

    def test_build_with_in(self, builder):
        builder.where_in("status", ["a", "b", "c"])
        sql, params = builder.build_sql()
        assert "IN (?, ?, ?)" in sql
        assert len(params) == 3

    def test_build_with_between(self, builder):
        builder.where_between("price", 10, 100)
        sql, params = builder.build_sql()
        assert "BETWEEN" in sql
        assert len(params) == 2

    def test_build_with_or_conditions(self, builder):
        builder.or_where([
            ("status", QueryOperator.EQ, "a"),
            ("status", QueryOperator.EQ, "b"),
        ])
        sql, params = builder.build_sql()
        assert "(status = ? OR status = ?)" in sql

    def test_build_method_returns_formatted_sql(self, builder):
        builder.where("id", QueryOperator.EQ, 1)
        result = builder.build()
        assert "SELECT * FROM test_table" in result
        assert "WHERE id = ?" in result
        assert ("-- params: [1]" in result or "params" in result)

    def test_build_with_group_by(self, builder):
        builder.group_by("status").count()
        sql, params = builder.build_sql()
        assert "GROUP BY" in sql
        assert "COUNT(*)" in sql

    def test_build_distinct(self, builder):
        builder.distinct().select("name")
        sql, params = builder.build_sql()
        assert "SELECT DISTINCT" in sql


class TestQueryBuilderTypeConversion:
    """测试类型转换"""

    def test_integer_conversion(self, builder):
        builder.where("count", QueryOperator.EQ, "123")
        assert builder._spec.conditions[0].value == 123
        assert isinstance(builder._spec.conditions[0].value, int)

    def test_float_conversion(self, builder):
        builder.where("price", QueryOperator.EQ, "99.99")
        assert builder._spec.conditions[0].value == 99.99
        assert isinstance(builder._spec.conditions[0].value, float)

    def test_boolean_conversion_from_string(self, builder):
        builder.where("is_active", QueryOperator.EQ, "true")
        assert builder._spec.conditions[0].value is True

        builder2 = QueryBuilder(builder.ds, builder.meta_object)
        builder2.where("is_active", QueryOperator.EQ, "false")
        assert builder2._spec.conditions[0].value is False

    def test_unknown_field_no_conversion(self, builder):
        builder.where("unknown_field", QueryOperator.EQ, "keep_as_string")
        assert builder._spec.conditions[0].value == "keep_as_string"


class TestQueryHelperFunction:
    """测试便捷函数"""

    def test_query_function_creates_builder(self, mock_datasource, mock_meta_object):
        qb = query(mock_datasource, mock_meta_object)
        assert isinstance(qb, QueryBuilder)


class TestQuerySpecDataclass:
    """测试 QuerySpec 数据类"""

    def test_default_values(self):
        spec = QuerySpec(table_name="test")
        assert spec.table_name == "test"
        assert spec.conditions == []
        assert spec.limit == 0
        assert spec.distinct is False

    def test_custom_values(self):
        spec = QuerySpec(
            table_name="users",
            conditions=[QueryCondition("id", QueryOperator.EQ, 1)],
            sorts=[("name", "asc")],
            limit=10,
        )
        assert len(spec.conditions) == 1
        assert len(spec.sorts) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
