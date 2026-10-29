# -*- coding: utf-8 -*-
"""计划行 billing_amount 口径锁定测试（B2 / SO Wave3 T1.2）

依据: meta/schemas/sales_order_schedule.yaml
      docs/superpowers/specs/2026-10-29-so-wave3/spec.md D1

口径结论（已在 spec 取证）:
  `sales_order_lines.net_amount` = 行基额 + 抬头折扣分摊 + 抬头附加费分摊
  （`sales_order_amount_service.recompute_line`），且折扣列存负值，
  故 net_amount 即「折后行净额」，billing_amount 不应再单独加减两调整列。

本测试锁定:
  1. 字段定义与列表列两处公式一致（防止只改一处导致口径分叉）
  2. 公式求值 = billing_percent × net_amount / 100（2 位小数）
  3. 公式不得引用 header_discount_amount / header_surcharge_amount（否则重复计算）
"""

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

_SCHEMA_PATH = Path(__file__).resolve().parents[1] / 'schemas' / 'sales_order_schedule.yaml'
_DOUBLE_COUNT_FIELDS = ('header_discount_amount', 'header_surcharge_amount')


@pytest.fixture(scope='module')
def schema():
    with open(_SCHEMA_PATH, encoding='utf-8') as f:
        return yaml.safe_load(f)


def _field_formula(schema) -> str:
    for field in schema.get('fields') or []:
        if field.get('id') == 'billing_amount':
            return ((field.get('computation') or {}).get('formula') or '')
    raise AssertionError('billing_amount 字段缺失')


def _column_formula(schema) -> str:
    columns = ((schema.get('ui_view_config') or {}).get('list') or {}).get('columns') or []
    for column in columns:
        if column.get('field') == 'billing_amount':
            return ((column.get('computation') or {}).get('formula') or '')
    raise AssertionError('billing_amount 列表列缺失')


class _FakeDS:
    """只提供跨对象解析所需的 find_by_id。"""

    def __init__(self, line_row):
        self.line_row = line_row
        self.calls = []

    def find_by_id(self, table, record_id):
        self.calls.append((table, record_id))
        return dict(self.line_row) if table == 'sales_order_lines' else None


def _evaluate(formula: str, record: dict, line_row: dict):
    from meta.core.models import registry
    from meta.core.rule_executor import ExpressionEvaluator, RuleContext
    from meta.core.yaml_loader import get_yaml_schema_dir, register_from_directory

    if not registry._objects:
        register_from_directory(get_yaml_schema_dir())

    meta_object = registry.get('sales_order_schedule')
    assert meta_object is not None, 'sales_order_schedule 元对象未加载'
    context = RuleContext(meta_object, record, data_source=_FakeDS(line_row))
    return ExpressionEvaluator.evaluate(formula, context)


# net_amount = 850.00 即「基额 1000 − 抬头折扣 150」，已是折后行净额
BASE_RECORD = {'id': 1, 'line_id': 7}
LINE_ROW = {'id': 7, 'net_amount': 850.0}


class TestBillingAmountFormula:

    def test_two_formula_definitions_identical(self, schema):
        assert _field_formula(schema) == _column_formula(schema)

    def test_formula_does_not_double_count_header_adjustments(self, schema):
        formula = _field_formula(schema)
        for name in _DOUBLE_COUNT_FIELDS:
            assert name not in formula, (
                f'公式引用了 {name}：net_amount 已含该调整，会重复计算')

    def test_full_percent_equals_after_discount_line_net(self, schema):
        formula = _field_formula(schema)
        value = _evaluate(formula, {**BASE_RECORD, 'billing_percent': 100}, LINE_ROW)
        assert value == pytest.approx(850.0)

    def test_thirty_percent_scales_line_net(self, schema):
        formula = _field_formula(schema)
        value = _evaluate(formula, {**BASE_RECORD, 'billing_percent': 30}, LINE_ROW)
        assert value == pytest.approx(255.0)

    def test_null_percent_yields_null(self, schema):
        formula = _field_formula(schema)
        value = _evaluate(formula, {**BASE_RECORD, 'billing_percent': None}, LINE_ROW)
        assert value is None

    def test_missing_line_net_falls_back_to_zero(self, schema):
        formula = _field_formula(schema)
        value = _evaluate(formula, {**BASE_RECORD, 'billing_percent': 100},
                          {'id': 7, 'net_amount': None})
        assert value == pytest.approx(0.0)
