import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""P1-005: SQL操作符检测歧义修复的回归测试"""

import pytest
from meta.core.sql_adapters import SQLiteAdapter


class TestBuildConditionsOperators:

    def test_build_conditions_gte_operator(self):
        adapter = SQLiteAdapter()
        conditions, params = adapter._build_conditions({"age >=": 18})
        assert "age >= ?" in conditions[0]
        assert params[0] == 18

    def test_build_conditions_gt_operator(self):
        adapter = SQLiteAdapter()
        conditions, params = adapter._build_conditions({"age >": 18})
        assert "age > ?" in conditions[0]
        assert params[0] == 18

    def test_build_conditions_lte_operator(self):
        adapter = SQLiteAdapter()
        conditions, params = adapter._build_conditions({"price <=": 100})
        assert "price <= ?" in conditions[0]
        assert params[0] == 100

    def test_build_conditions_lt_operator(self):
        adapter = SQLiteAdapter()
        conditions, params = adapter._build_conditions({"price <": 100})
        assert "price < ?" in conditions[0]
        assert params[0] == 100

    def test_build_conditions_mixed_operators(self):
        adapter = SQLiteAdapter()
        conditions, params = adapter._build_conditions({
            "age >=": 18,
            "age <": 65,
            "status": "active",
        })
        condition_strs = " ".join(conditions)
        assert "age >= ?" in condition_strs
        assert "age < ?" in condition_strs
        assert "status = ?" in condition_strs
        assert len(params) == 3

    def test_build_conditions_field_name_with_gt_in_name(self):
        adapter = SQLiteAdapter()
        conditions, params = adapter._build_conditions({"hashtag": "test"})
        assert "hashtag = ?" in conditions[0]
        assert params[0] == "test"

    def test_build_conditions_like_operator(self):
        adapter = SQLiteAdapter()
        conditions, params = adapter._build_conditions({"name LIKE": "%test%"})
        assert "name LIKE ?" in conditions[0]
        assert params[0] == "%test%"

    def test_build_conditions_in_operator(self):
        adapter = SQLiteAdapter()
        conditions, params = adapter._build_conditions({"status IN": ["active", "pending"]})
        assert "status IN (?, ?)" in conditions[0]
        assert params == ["active", "pending"]

    def test_build_conditions_gt_followed_by_equals_not_misinterpreted(self):
        adapter = SQLiteAdapter()
        conditions, params = adapter._build_conditions({"count >=": 5, "count <=": 10})
        condition_strs = " ".join(conditions)
        assert "count >= ?" in condition_strs
        assert "count <= ?" in condition_strs
        assert "count > ?" not in condition_strs
        assert "count < ?" not in condition_strs
        assert params == [5, 10]
