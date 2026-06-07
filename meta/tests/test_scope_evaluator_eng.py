# -*- coding: utf-8 -*-
"""
ENG-002: scope_evaluator (15 测试) - FR-009/010 Scope 表达式求值器

[MARKER] unit - 单元测试 (无外部依赖)
[FEATURE] ScopeEvaluator 表达式求值 / get_scope_evaluator 单例
"""
import pytest
from meta.core.scope_evaluator import ScopeEvaluator, get_scope_evaluator

pytestmark = [pytest.mark.unit]


class TestScopeEvaluator:
    """ScopeEvaluator 表达式求值测试"""
    def test_empty_scope_returns_true(self):
        ev = ScopeEvaluator()
        assert ev.evaluate("", user_id=1, record={}) is True
        assert ev.evaluate(None, user_id=1, record={}) is True

    # ---------- 等值运算符 合并 (2 → 1, 4 cases) ----------
    @pytest.mark.parametrize('op,record,expected', [
        # == (match / no-match)
        pytest.param('=', {'visibility': 'public'}, True, id='eq_match'),
        pytest.param('=', {'visibility': 'private'}, False, id='eq_no_match'),
        # !=
        pytest.param('!=', {'status': 'active'}, True, id='neq_match'),
        pytest.param('!=', {'status': 'archived'}, False, id='neq_no_match'),
    ])
    def test_equality_op(self, op, record, expected):
        ev = ScopeEvaluator()
        # 用对应的字段/literal
        if op == '=':
            expr = "visibility = 'public'"
        else:
            expr = "status != 'archived'"
        assert ev.evaluate(expr, user_id=1, record=record) is expected

    def test_user_id_substitution(self):
        ev = ScopeEvaluator()
        assert ev.evaluate(
            "owner_id = $user.id",
            user_id=42,
            record={'owner_id': 42},
        ) is True
        assert ev.evaluate(
            "owner_id = $user.id",
            user_id=42,
            record={'owner_id': 99},
        ) is False

    # ---------- 逻辑 OR/AND 合并 (2 → 1, 4 cases) ----------
    @pytest.mark.parametrize('op,true_record,false_record', [
        # OR: owner_id match
        pytest.param('or', {'visibility': 'draft', 'owner_id': 1},
                    {'visibility': 'draft', 'owner_id': 2}, id='or_owner_match'),
        # OR: visibility match
        pytest.param('or', {'visibility': 'public', 'owner_id': 999},
                    {'visibility': 'draft', 'owner_id': 2}, id='or_visibility_match'),
        # AND: both match (true_record 满足两个条件)
        pytest.param('and', {'visibility': 'public', 'active': 1},
                    {'visibility': 'public', 'active': 0}, id='and_active_fail'),
        # AND: visibility no-match (true_record 也满足两个条件才能 True)
        pytest.param('and', {'visibility': 'public', 'active': 1},
                    {'visibility': 'private', 'active': 1}, id='and_visibility_fail'),
    ])
    def test_logical_op(self, op, true_record, false_record):
        ev = ScopeEvaluator()
        if op == 'or':
            expr = "visibility = 'public' OR owner_id = 1"
        else:
            expr = "visibility = 'public' AND active = 1"
        assert ev.evaluate(expr, user_id=1, record=true_record) is True
        assert ev.evaluate(expr, user_id=1, record=false_record) is False

    # ---------- 数值比较运算符 合并 (4 → 1, 8 cases) ----------
    @pytest.mark.parametrize('op,value,expected', [
        # > 10
        pytest.param('>', 15, True, id='gt_15'),
        pytest.param('>', 5, False, id='gt_5'),
        # < 10
        pytest.param('<', 5, True, id='lt_5'),
        pytest.param('<', 15, False, id='lt_15'),
        # >= 10
        pytest.param('>=', 10, True, id='ge_10'),
        pytest.param('>=', 9, False, id='ge_9'),
        # <= 10
        pytest.param('<=', 10, True, id='le_10'),
        pytest.param('<=', 11, False, id='le_11'),
    ])
    def test_numeric_comparison(self, op, value, expected):
        ev = ScopeEvaluator()
        expr = f'count {op} 10'
        record = {'count': value}
        assert ev.evaluate(expr, user_id=1, record=record) is expected

    def test_string_with_spaces(self):
        """含空格的字符串值"""
        ev = ScopeEvaluator()
        assert ev.evaluate(
            "label = 'hello world'",
            user_id=1,
            record={'label': 'hello world'},
        ) is True

    def test_string_with_or_keyword(self):
        """值中含有 'OR' 不应被分割"""
        ev = ScopeEvaluator()
        assert ev.evaluate(
            "name = 'ORANGE'",
            user_id=1,
            record={'name': 'ORANGE'},
        ) is True

    def test_evaluation_error_returns_false(self):
        ev = ScopeEvaluator()
        # 不合法表达式 → except → False
        assert ev.evaluate(
            "invalid syntax ==== ",
            user_id=1,
            record={},
        ) is False


class TestGetScopeEvaluator:
    def test_returns_singleton(self):
        ev1 = get_scope_evaluator()
        ev2 = get_scope_evaluator()
        assert ev1 is ev2

    def test_singleton_works(self):
        ev = get_scope_evaluator()
        assert ev.evaluate("a = 1", user_id=1, record={'a': 1}) is True
