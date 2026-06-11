# -*- coding: utf-8 -*-
"""
ComputationService 单元测试 (P0-2026-06-10)

覆盖以下方法（之前 0 单元测试覆盖）：
- _count_children / _batch_count_children
- _count_relations 各 scope 分支
- _batch_count_user_group_members
- _evaluate_expression / _batch_evaluate_formula
- invalidate_cache
- merge_computed_columns / get_computed_columns_from_rules
"""
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from meta.services.computation_service import computation_service


# =============================================================================
# Fixtures
# =============================================================================


class MockDataSource:
    """模拟数据源（基于内存 sqlite）"""

    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=()):
        return self.conn.cursor().execute(sql, params)


@pytest.fixture
def mock_db():
    """内存 sqlite，建好 count_children/count_relations 所需的所有表"""
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()

    # 层级表（count_children 测试用）
    cur.execute("CREATE TABLE domains (id INTEGER PRIMARY KEY, name TEXT)")
    cur.execute("CREATE TABLE sub_domains (id INTEGER PRIMARY KEY, domain_id INTEGER, name TEXT)")
    cur.execute(
        "CREATE TABLE service_modules ("
        "id INTEGER PRIMARY KEY, sub_domain_id INTEGER, name TEXT)"
    )
    cur.execute(
        "CREATE TABLE business_objects ("
        "id INTEGER PRIMARY KEY, service_module_id INTEGER, name TEXT)"
    )

    # 关系表（count_relations 测试用）
    cur.execute(
        "CREATE TABLE relationships ("
        "id INTEGER PRIMARY KEY, source_bo_id INTEGER, target_bo_id INTEGER)"
    )

    # 用户组成员表（user_group.member_count 测试用）
    cur.execute(
        "CREATE TABLE user_group_members ("
        "group_id INTEGER, user_id INTEGER)"
    )

    # 测试数据
    cur.executemany(
        "INSERT INTO domains VALUES (?, ?)",
        [(1, "D1"), (2, "D2")],
    )
    cur.executemany(
        "INSERT INTO sub_domains VALUES (?, ?, ?)",
        [(10, 1, "SD1"), (11, 1, "SD2"), (12, 2, "SD3")],
    )
    cur.executemany(
        "INSERT INTO service_modules VALUES (?, ?, ?)",
        [(100, 10, "SM1"), (101, 10, "SM2"), (102, 11, "SM3")],
    )
    cur.executemany(
        "INSERT INTO business_objects VALUES (?, ?, ?)",
        [
            (1000, 100, "BO1"),
            (1001, 100, "BO2"),
            (1002, 101, "BO3"),
            (1003, 102, "BO4"),
        ],
    )
    cur.executemany(
        "INSERT INTO relationships VALUES (?, ?, ?)",
        [
            (1, 1000, 1001),
            (2, 1001, 1002),
            (3, 1002, 1003),
        ],
    )
    cur.executemany(
        "INSERT INTO user_group_members VALUES (?, ?)",
        [(500, 1), (500, 2), (500, 3), (501, 4)],
    )

    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def mock_ds(mock_db):
    return MockDataSource(mock_db)


# =============================================================================
# TestCountChildren
# =============================================================================


class TestCountChildren:
    """_count_children / _batch_count_children"""

    def test_count_children_sub_domain(self, mock_ds):
        """sub_domain 字段: 显式 child_object + foreign_key"""
        # domain_id=1 有 2 个 sub_domain
        result = computation_service._count_children(
            mock_ds, "domain", 1,
            {"target_object": "sub_domain", "foreign_key": "domain_id"},
        )
        assert result == 2

    def test_count_children_zero_when_no_children(self, mock_ds):
        """无子节点时返回 0, 不是 None"""
        result = computation_service._count_children(
            mock_ds, "domain", 99,  # 不存在的 domain_id
            {"target_object": "sub_domain", "foreign_key": "domain_id"},
        )
        assert result == 0

    def test_count_children_no_target_object_returns_zero(self, mock_ds):
        """无 target_object / child_object 时返回 0"""
        result = computation_service._count_children(
            mock_ds, "domain", 1, {"target_object": ""}
        )
        assert result == 0

    def test_count_children_unknown_target_object_returns_zero(self, mock_ds):
        """target_object 在 registry 中查不到时返回 0"""
        result = computation_service._count_children(
            mock_ds, "domain", 1,
            {"target_object": "nonexistent_object", "foreign_key": "domain_id"},
        )
        assert result == 0

    def test_count_children_db_error_returns_zero(self, mock_ds):
        """SQL 异常时降级返回 0, 不抛错"""
        broken_ds = MagicMock()
        broken_ds.execute.side_effect = Exception("simulated DB error")
        result = computation_service._count_children(
            broken_ds, "domain", 1,
            {"target_object": "sub_domain", "foreign_key": "domain_id"},
        )
        assert result == 0

    def test_batch_count_children_multiple_records(self, mock_ds):
        """batch 模式一次算多个 record 的 child count"""
        records = [{"id": 1}, {"id": 2}, {"id": 99}]
        computation_service._batch_count_children(
            mock_ds, "domain", records, "child_count",
            {"target_object": "sub_domain", "foreign_key": "domain_id"},
        )
        assert records[0]["child_count"] == 2  # domain 1 → 2 sub_domains
        assert records[1]["child_count"] == 1  # domain 2 → 1 sub_domain
        assert records[2]["child_count"] == 0  # domain 99 → 0

    def test_batch_count_children_record_without_id(self, mock_ds):
        """record 缺 id 时设为 0, 不调用 SQL"""
        records = [{"id": 1}, {"name": "no_id"}]
        computation_service._batch_count_children(
            mock_ds, "domain", records, "child_count",
            {"target_object": "sub_domain", "foreign_key": "domain_id"},
        )
        assert records[0]["child_count"] == 2
        assert records[1]["child_count"] == 0


# =============================================================================
# TestCountRelations
# =============================================================================


class TestCountRelations:
    """_count_relations 各 scope 分支"""

    def test_count_bo_relations_self(self, mock_ds):
        """business_object + self scope → COUNT relationships WHERE source/target = ?"""
        # BO 1000: 1 rel (1000↔1001)
        result = computation_service._count_relations(mock_ds, "business_object", 1000, "self")
        assert result == 1

        # BO 1001: 2 rels (1000↔1001, 1001↔1002)
        result = computation_service._count_relations(mock_ds, "business_object", 1001, "self")
        assert result == 2

    def test_count_descendant_relations_domain(self, mock_ds):
        """domain + descendants → 3 表 JOIN, 算 relationships 表里匹配的 row 数"""
        # domain 1 包含 BO 1000/1001/1002/1003 (全部)
        # rels: 1(1000↔1001), 2(1001↔1002), 3(1002↔1003)
        # 这 3 行 relationships 全部涉及 domain 1 的 descendants
        result = computation_service._count_relations(mock_ds, "domain", 1, "descendants")
        assert result == 3

        # domain 2 包含 BO 1003 (通过 sub_domain 12 → 应该是空, 因为 sub_domain 12 无 service_module)
        result = computation_service._count_relations(mock_ds, "domain", 2, "descendants")
        assert result == 0

    def test_count_descendant_relations_sub_domain(self, mock_ds):
        """sub_domain + descendants → 2 表 JOIN"""
        # sub_domain 10 包含 BO 1000, 1001, 1002 (通过 sm 100/101)
        # rels:
        #   rel 1: source=1000, target=1001  → 两端都在 IN
        #   rel 2: source=1001, target=1002  → 两端都在 IN
        #   rel 3: source=1002, target=1003  → source 在 IN, 命中
        # 共 3 行
        result = computation_service._count_relations(mock_ds, "sub_domain", 10, "descendants")
        assert result == 3

    def test_count_descendant_relations_service_module(self, mock_ds):
        """service_module + descendants → 1 表 (无 JOIN)"""
        # service_module 100 包含 BO 1000, 1001
        # rel 1: 1000↔1001 命中
        # rel 2: 1001↔1002 命中 (1001 在内)
        # rel 3: 1002↔1003 不命中
        # 共 2 行
        result = computation_service._count_relations(
            mock_ds, "service_module", 100, "descendants"
        )
        assert result == 2

    def test_count_relations_unsupported_scope_returns_zero(self, mock_ds):
        """不支持的 scope 返回 0"""
        # business_object 不支持 descendants
        assert computation_service._count_relations(
            mock_ds, "business_object", 1000, "descendants"
        ) == 0
        # domain 不支持 self
        assert computation_service._count_relations(
            mock_ds, "domain", 1, "self"
        ) == 0

    def test_count_relations_unsupported_object_type_returns_zero(self, mock_ds):
        """完全未知的 object_type 返回 0"""
        assert computation_service._count_relations(
            mock_ds, "user_group", 1, "self"
        ) == 0

    def test_count_bo_relations_db_error_returns_zero(self, mock_ds):
        """SQL 异常时降级返回 0"""
        broken_ds = MagicMock()
        broken_ds.execute.side_effect = Exception("simulated DB error")
        result = computation_service._count_bo_relations(broken_ds, 1000)
        assert result == 0


# =============================================================================
# TestCountUserGroupMembers
# =============================================================================


class TestCountUserGroupMembers:
    """_batch_count_user_group_members"""

    def test_count_user_group_members_with_data(self, mock_ds):
        """user_group.member_count = COUNT user_group_members GROUP BY group_id"""
        records = [{"id": 500}, {"id": 501}, {"id": 999}]
        computation_service._batch_count_user_group_members(mock_ds, records, "member_count")
        assert records[0]["member_count"] == 3  # group 500 → 3 members
        assert records[1]["member_count"] == 1  # group 501 → 1 member
        assert records[2]["member_count"] == 0  # group 999 → 0 members (no group)

    def test_count_user_group_members_empty_records(self, mock_ds):
        """空 records 列表安全返回"""
        records = []
        computation_service._batch_count_user_group_members(mock_ds, records, "member_count")
        assert records == []

    def test_count_user_group_members_all_without_id(self, mock_ds):
        """全部 record 都没 id 时直接返回"""
        records = [{"name": "no_id_1"}, {"name": "no_id_2"}]
        computation_service._batch_count_user_group_members(mock_ds, records, "member_count")
        # 不会写入 member_count 字段
        for r in records:
            assert "member_count" not in r

    def test_count_user_group_members_db_error_fills_zero(self, mock_ds):
        """SQL 异常时所有 record 的 member_count 设为 0"""
        broken_ds = MagicMock()
        broken_ds.execute.side_effect = Exception("simulated DB error")
        records = [{"id": 500}, {"id": 501}]
        computation_service._batch_count_user_group_members(broken_ds, records, "member_count")
        assert records[0]["member_count"] == 0
        assert records[1]["member_count"] == 0


# =============================================================================
# TestFormulaEvaluation
# =============================================================================


class TestFormulaEvaluation:
    """_evaluate_expression / _batch_evaluate_formula"""

    def test_evaluate_expression_empty_formula_returns_none(self, mock_ds):
        """formula 为空时返回 None"""
        result = computation_service._evaluate_expression(
            mock_ds, "domain", 1, {"formula": ""}
        )
        assert result is None

    def test_evaluate_expression_no_formula_key_returns_none(self, mock_ds):
        """computation 没 formula key 时返回 None"""
        result = computation_service._evaluate_expression(
            mock_ds, "domain", 1, {}
        )
        assert result is None

    def test_evaluate_expression_syntax_error_returns_none(self, mock_ds):
        """formula 语法错误时降级返回 None, 不抛错"""
        result = computation_service._evaluate_expression(
            mock_ds, "domain", 1, {"formula": "@@invalid@@"}
        )
        assert result is None

    def test_batch_evaluate_formula_empty_records(self, mock_ds):
        """空 records 安全返回"""
        records = []
        computation_service._batch_evaluate_formula(
            mock_ds, "domain", records, "calc_field", {"formula": "1+1"}
        )
        assert records == []

    def test_batch_evaluate_formula_no_formula_skips(self, mock_ds):
        """无 formula 时直接返回, 不动 records"""
        records = [{"id": 1, "value": 10}]
        computation_service._batch_evaluate_formula(
            mock_ds, "domain", records, "calc_field", {"formula": ""}
        )
        # 不会写入 calc_field
        assert "calc_field" not in records[0]

    def test_batch_evaluate_formula_unknown_object_type_skips(self, mock_ds):
        """object_type 不在 registry 时直接返回, 不抛错"""
        records = [{"id": 1}]
        computation_service._batch_evaluate_formula(
            mock_ds, "nonexistent_object", records, "calc_field", {"formula": "1+1"}
        )
        assert "calc_field" not in records[0]


# =============================================================================
# TestCacheInvalidation
# =============================================================================


class TestCacheInvalidation:
    """invalidate_cache"""

    def test_invalidate_specific_object_type(self):
        """invalidate_cache(object_type) 只清该类型"""
        computation_service._cache["user"] = {"key": "user_data"}
        computation_service._cache["domain"] = {"key": "domain_data"}
        computation_service.invalidate_cache("user")
        assert "user" not in computation_service._cache
        assert "domain" in computation_service._cache

    def test_invalidate_all_clears_cache(self):
        """invalidate_cache() 不带参数清空所有"""
        computation_service._cache["user"] = {"key": "user_data"}
        computation_service._cache["domain"] = {"key": "domain_data"}
        computation_service.invalidate_cache()
        assert computation_service._cache == {}

    def test_invalidate_nonexistent_type_no_error(self):
        """invalidate 不存在的类型不报错"""
        computation_service.invalidate_cache("never_existed")
        # 不会抛错


# =============================================================================
# TestMergeAndGetComputedColumns
# =============================================================================


class TestMergeAndGetComputedColumns:
    """merge_computed_columns / get_computed_columns_from_rules"""

    def test_merge_ui_columns_take_precedence(self):
        """UI 配置优先: 重复 key 时 UI 列赢"""
        ui = [
            {"key": "calc_field", "formula": "ui_formula"},
            {"key": "other", "value": 1},
        ]
        rule = [
            {"key": "calc_field", "formula": "rule_formula"},
            {"key": "new_field", "value": 2},
        ]
        merged = computation_service.merge_computed_columns(ui, rule)
        keys = [c["key"] for c in merged]
        assert keys.count("calc_field") == 1
        assert merged[0]["formula"] == "ui_formula"  # UI 胜
        # new_field 被补充进来
        assert any(c["key"] == "new_field" for c in merged)

    def test_merge_empty_inputs(self):
        """空入参时返回空列表"""
        assert computation_service.merge_computed_columns([], []) == []
        assert computation_service.merge_computed_columns([], [{"key": "x"}]) == [{"key": "x"}]
        assert computation_service.merge_computed_columns([{"key": "x"}], []) == [{"key": "x"}]

    def test_get_computed_columns_from_rules_no_meta(self):
        """object_type 不在 registry 时返回空列表"""
        result = computation_service.get_computed_columns_from_rules("nonexistent_object")
        assert result == []

    def test_get_computed_columns_from_rules_empty_rules(self):
        """meta_obj 无 rules 时返回空列表"""
        with patch("meta.services.computation_service.registry") as mock_reg:
            mock_meta = MagicMock()
            mock_meta.rules = []
            mock_reg.get.return_value = mock_meta
            result = computation_service.get_computed_columns_from_rules("user")
            assert result == []
