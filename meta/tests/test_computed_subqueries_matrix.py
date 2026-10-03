# -*- coding: utf-8 -*-
"""
Computed Subqueries Matrix 测试 (P0-2026-06-10)

覆盖 meta.services.query.computed_subqueries 的全部入口:
- build_count_relations_expr 各 (object_type, scope) 组合生成的 SQL
- build_count_children_expr 各 object_type 生成的 SQL + FK 字段
- build_count_subquery_expr 统一入口分发
- is_supported() 完整矩阵
"""
import pytest
from unittest.mock import patch

from meta.services.query.computed_subqueries import (
    build_count_relations_expr,
    build_count_children_expr,
    build_aggregate_field_expr,
    build_count_subquery_expr,
    resolve_parent_aggregation,
    is_supported,
)


# =============================================================================
# TestIsSupportedMatrix
# =============================================================================


class TestIsSupportedMatrix:
    """is_supported() 完整 (comp_type, object_type, scope) 矩阵"""

    @pytest.mark.parametrize("object_type,scope,expected", [
        # count_relations + self
        ("business_object", "self", True),
        ("org",             "self", True),
        ("domain",          "self", False),
        ("sub_domain",      "self", False),
        ("service_module",  "self", False),
        # count_relations + descendants
        ("domain",         "descendants", True),
        ("sub_domain",     "descendants", True),
        ("service_module", "descendants", True),
        ("business_object","descendants", False),
        ("org",            "descendants", False),
        # count_relations + 其他 scope
        ("business_object", "ancestors",  False),
    ])
    def test_is_supported_count_relations(self, object_type, scope, expected):
        """count_relations: 只支持 self+bo/user_group, descendants+domain/sub_domain/sm"""
        assert is_supported("count_relations", object_type, scope) is expected

    @pytest.mark.parametrize("object_type,expected", [
        ("version",        True),
        ("domain",         True),
        ("sub_domain",     True),
        ("service_module", True),
        ("business_object", False),
        ("user_group",     False),
        ("user",           False),
    ])
    def test_is_supported_count_children(self, object_type, expected):
        """count_children: 只支持 4 个层级对象"""
        # scope 对 count_children 无意义, 用 self 当默认值
        assert is_supported("count_children", object_type, "self") is expected

    @pytest.mark.parametrize("comp_type", ["formula", "expression", "aggregate", "sum", ""])
    def test_is_supported_unknown_comp_type(self, comp_type):
        """未知 comp_type 一律返回 False"""
        assert is_supported(comp_type, "domain", "self") is False
        assert is_supported(comp_type, "business_object", "self") is False


# =============================================================================
# TestBuildCountRelationsExpr
# =============================================================================


class TestBuildCountRelationsExpr:
    """build_count_relations_expr SQL 字符串正确性"""

    def test_business_object_self_uses_source_or_target(self):
        """BO + self: source_bo_id OR target_bo_id = table.id"""
        sql = build_count_relations_expr("business_objects", "business_object", scope="self")
        assert sql is not None
        assert "FROM relationships" in sql
        assert "relationships.source_bo_id = business_objects.id" in sql
        assert "relationships.target_bo_id = business_objects.id" in sql
        assert sql.startswith("(SELECT COUNT(*)")
        assert sql.endswith(")")

    def test_org_self_uses_org_members(self):
        """org + self: org_members WHERE org_id = id (Spec 16 迁移后)"""
        sql = build_count_relations_expr("orgs", "org", scope="self")
        assert sql is not None
        assert "FROM org_members" in sql
        assert "org_members.org_id = orgs.id" in sql

    def test_domain_descendants_joins_three_tables(self):
        """domain + descendants: 3 表 JOIN 数 BO, 再 IN 子查询数 rels"""
        sql = build_count_relations_expr("domains", "domain", scope="descendants")
        assert sql is not None
        assert "JOIN service_modules sm" in sql
        assert "JOIN sub_domains sd" in sql
        assert "WHERE sd.domain_id = domains.id" in sql
        assert "COUNT(DISTINCT r.id)" in sql
        assert "r.source_bo_id IN" in sql
        assert "r.target_bo_id IN" in sql

    def test_sub_domain_descendants_joins_two_tables(self):
        """sub_domain + descendants: 2 表 JOIN"""
        sql = build_count_relations_expr("sub_domains", "sub_domain", scope="descendants")
        assert sql is not None
        assert "JOIN service_modules sm" in sql
        assert "sm.sub_domain_id = sub_domains.id" in sql
        assert "COUNT(DISTINCT r.id)" in sql
        # 不应 JOIN sub_domains
        assert "JOIN sub_domains" not in sql

    def test_service_module_descendants_no_join(self):
        """service_module + descendants: 1 表 (无 JOIN)"""
        sql = build_count_relations_expr("service_modules", "service_module", scope="descendants")
        assert sql is not None
        assert "FROM business_objects bo" in sql
        assert "bo.service_module_id = service_modules.id" in sql
        # 不应 JOIN 任何表
        assert "JOIN " not in sql
        assert "COUNT(DISTINCT r.id)" in sql

    def test_custom_rel_table_name(self):
        """rel_table 参数能替换默认 relationships"""
        sql = build_count_relations_expr(
            "business_objects", "business_object", scope="self", rel_table="my_rels"
        )
        assert "FROM my_rels" in sql
        assert "my_rels.source_bo_id" in sql

    @pytest.mark.parametrize("object_type,scope", [
        ("business_object", "descendants"),
        ("org", "descendants"),
        ("version", "self"),
        ("user", "self"),
        ("domain", "ancestors"),
    ])
    def test_unsupported_combination_returns_none(self, object_type, scope):
        """不支持的组合返回 None"""
        result = build_count_relations_expr(
            "any_table", object_type, scope=scope
        )
        assert result is None


# =============================================================================
# TestBuildCountChildrenExpr
# =============================================================================


class TestBuildCountChildrenExpr:
    """build_count_children_expr SQL + FK 字段正确性"""

    @pytest.mark.parametrize("object_type,expected_child_table,expected_fk", [
        ("version",        "domains",          "version_id"),
        ("domain",         "sub_domains",      "domain_id"),
        ("sub_domain",     "service_modules",  "sub_domain_id"),
        ("service_module", "business_objects", "service_module_id"),
    ])
    def test_generated_sql_uses_correct_fk(
        self, object_type, expected_child_table, expected_fk
    ):
        """每个层级 object_type 生成的 SQL 用正确的外键字段名 (regression: 之前用错 child.id 风格)"""
        sql = build_count_children_expr("parent_table", object_type)
        assert sql is not None
        assert f"FROM {expected_child_table}" in sql
        assert f"{expected_child_table}.{expected_fk}" in sql
        assert "= parent_table.id" in sql
        assert sql.startswith("(SELECT COUNT(*)")
        assert sql.endswith(")")

    @pytest.mark.parametrize("object_type", [
        "business_object", "user_group", "user", "unknown_type", "",
    ])
    def test_unsupported_object_type_returns_none(self, object_type):
        """不在 map 里的 object_type → None"""
        result = build_count_children_expr("any_table", object_type)
        assert result is None


# =============================================================================
# TestBuildCountSubqueryExprDispatch
# =============================================================================


class TestBuildCountSubqueryExprDispatch:
    """build_count_subquery_expr 统一入口分发"""

    def test_dispatch_to_count_relations(self):
        """comp_type=count_relations → 调用 build_count_relations_expr"""
        sql = build_count_subquery_expr(
            "count_relations", "business_objects", "business_object", scope="self"
        )
        assert sql is not None
        assert "FROM relationships" in sql

    def test_dispatch_to_count_children(self):
        """comp_type=count_children → 调用 build_count_children_expr"""
        sql = build_count_subquery_expr(
            "count_children", "domains", "domain", scope="self"
        )
        assert sql is not None
        assert "FROM sub_domains" in sql

    def test_dispatch_unknown_comp_type_returns_none(self):
        """未知 comp_type 返回 None + 警告日志"""
        result = build_count_subquery_expr(
            "formula", "any_table", "any_object", scope="self"
        )
        assert result is None

    def test_dispatch_propagates_unsupported(self):
        """不支持的 (comp_type, object_type, scope) 组合返回 None"""
        # count_relations + domain + self 不支持
        result = build_count_subquery_expr(
            "count_relations", "domains", "domain", scope="self"
        )
        assert result is None


# =============================================================================
# TestSqlSafety (regression for SQL 注入/字段名错误)
# =============================================================================


class TestSqlSafety:
    """生成的 SQL 字符串结构稳定性 (防止 FK 字段名回退)"""

    def test_no_repeated_count_keyword_underscore(self):
        """不应出现 'count_count' 之类的拼写错误"""
        sql = build_count_children_expr("domains", "domain")
        assert "count_count" not in sql.lower()

    def test_count_children_sql_does_not_contain_relationships(self):
        """count_children 不应涉及 relationships 表 (那是 count_relations 的事)"""
        sql = build_count_children_expr("domains", "domain")
        assert "relationships" not in sql
        assert "user_group_members" not in sql

    def test_count_relations_self_does_not_join(self):
        """count_relations self 不应有 JOIN (直接 source/target)"""
        sql = build_count_relations_expr("business_objects", "business_object", scope="self")
        assert "JOIN " not in sql


# =============================================================================
# 取值聚合 (rollup): sum_field / avg_field / max_field / min_field
# =============================================================================


class TestBuildAggregateFieldExpr:
    """build_aggregate_field_expr: 相关子查询 SQL 结构 + 标识符白名单"""

    def test_sum_expr_is_correlated_subquery(self):
        """与 count_children 同构: (SELECT SUM(child.col) ... WHERE child.fk = parent.id)"""
        sql = build_aggregate_field_expr(
            "sub_domains", "service_modules", "sub_domain_id", "amount", "SUM"
        )
        assert sql == (
            "(SELECT SUM(service_modules.amount) FROM service_modules "
            "WHERE service_modules.sub_domain_id = sub_domains.id)"
        )

    @pytest.mark.parametrize("sql_func", ["SUM", "AVG", "MAX", "MIN"])
    def test_all_whitelisted_functions(self, sql_func):
        sql = build_aggregate_field_expr("parents", "children", "parent_id", "amount", sql_func)
        assert f"SELECT {sql_func}(children.amount)" in sql

    def test_illegal_sql_func_rejected(self):
        """聚合函数必须在白名单内 (防注入)"""
        assert build_aggregate_field_expr(
            "parents", "children", "parent_id", "amount", "DROP TABLE"
        ) is None

    @pytest.mark.parametrize("bad_field", ["amount; DROP TABLE x", "amount--", "1amount", "", None])
    def test_illegal_source_field_rejected(self, bad_field):
        assert build_aggregate_field_expr(
            "parents", "children", "parent_id", bad_field, "SUM"
        ) is None

    @pytest.mark.parametrize("bad_fk", ["parent id", "parent_id)", "--x"])
    def test_illegal_fk_rejected(self, bad_fk):
        assert build_aggregate_field_expr(
            "parents", "children", bad_fk, "amount", "SUM"
        ) is None


class TestResolveParentAggregation:
    """resolve_parent_aggregation: rollup 参数解析的唯一入口"""

    def test_missing_child_object_returns_none(self):
        assert resolve_parent_aggregation({"type": "sum_field", "source_field": "amount"}) is None

    def test_missing_source_field_returns_none(self):
        assert resolve_parent_aggregation({
            "type": "sum_field", "child_object": "sub_domain",
            "foreign_key": "domain_id",
        }) is None

    def test_unknown_child_object_returns_none(self):
        with patch("meta.core.models.registry") as reg:
            reg.get.return_value = None
            assert resolve_parent_aggregation({
                "type": "sum_field", "child_object": "__no_such__",
                "foreign_key": "domain_id", "source_field": "amount",
            }) is None

    def test_unknown_comp_type_returns_none(self):
        with patch("meta.core.models.registry") as reg:
            reg.get.return_value.table_name = "sub_domains"
            assert resolve_parent_aggregation({
                "type": "median_field", "child_object": "sub_domain",
                "foreign_key": "domain_id", "source_field": "amount",
            }) is None

    def test_resolves_with_explicit_foreign_key(self):
        with patch("meta.core.models.registry") as reg:
            reg.get.return_value.table_name = "sub_domains"
            resolved = resolve_parent_aggregation({
                "type": "sum_field", "child_object": "sub_domain",
                "foreign_key": "domain_id", "source_field": "amount",
            })
        assert resolved == ("sub_domains", "domain_id", "amount", "SUM")


class TestAggregateDispatch:
    """build_count_subquery_expr 对聚合类型的分发"""

    def test_dispatch_without_computation_returns_none(self):
        """聚合类型缺少 computation 配置 → None (调用方 fail-fast)"""
        assert build_count_subquery_expr("sum_field", "sub_domains", "sub_domain") is None

    def test_dispatch_with_computation_returns_expr(self):
        with patch("meta.core.models.registry") as reg:
            reg.get.return_value.table_name = "service_modules"
            sql = build_count_subquery_expr(
                "sum_field", "sub_domains", "sub_domain", "self",
                {"type": "sum_field", "child_object": "service_module",
                 "foreign_key": "sub_domain_id", "source_field": "amount"},
            )
        assert sql == (
            "(SELECT SUM(service_modules.amount) FROM service_modules "
            "WHERE service_modules.sub_domain_id = sub_domains.id)"
        )

    def test_is_supported_requires_computation(self):
        """sum_field 的可支持性取决于 computation 配置, 与 object_type 无关"""
        assert is_supported("sum_field", "sub_domain", "self") is False
        with patch("meta.core.models.registry") as reg:
            reg.get.return_value.table_name = "service_modules"
            assert is_supported("sum_field", "sub_domain", "self", {
                "type": "sum_field", "child_object": "service_module",
                "foreign_key": "sub_domain_id", "source_field": "amount",
            }) is True
