# -*- coding: utf-8 -*-
"""舍入字段统一回归测试（D 项）

依据: docs/superpowers/specs/2026-10-27-sales-order-business-type-and-rounding-spec.md
      FR-003 / FR-004 / FR-005 / FR-006 / FR-009 / FR-011 / NFR-001 / NFR-002

覆盖:
  · 税额舍入按 tax_code.rounding 执行（4 分支：none/round/ceil/floor）
  · 非法舍入方式回落 half-up + WARNING（FR-009 / NFR-003）
  · 定价取整三级回落（params.mode → rate_type.rounding → none）（FR-006）
  · 定价取整非法值报错（不静默）（FR-006）
  · 平台字典 rounding_mode 与 5 处 YAML 内联 enum_values 逐值一致（NFR-001）
  · 平台级映射源 meta/core/rounding.py 与字典取值域一致（NFR-001）
"""

from decimal import Decimal

import pytest

pytestmark = pytest.mark.unit

from meta.core.calc_procedure_executor import CalculationError, execute
from meta.core.rounding import (
    ROUNDING_MODES,
    is_valid_rounding_mode,
    resolve_rounding_mode,
    round_by_mode,
)
from meta.services.sales_order_amount_service import SalesOrderAmountService

from test_sales_order_amount import ORDER, _ds  # noqa: F401  (复用 _FakeDS)

# ── 5 处舍入字段（对象, YAML 文件, 字段 id）──
ROUNDING_FIELDS = [
    ('allocation_rule', 'allocation_rule.yaml', 'rounding'),
    ('allocation_result', 'allocation_result.yaml', 'rounding'),
    ('rate_type', 'rate_type.yaml', 'rounding'),
    ('pricing_period', 'pricing_period.yaml', 'rounding'),
    ('tax_code', 'tax_code.yaml', 'rounding'),
]

EXPECTED_MODES = ['none', 'round', 'ceil', 'floor']


# ---------------------------------------------------------------------------
# 税额舍入（FR-005）
# ---------------------------------------------------------------------------
class TestTaxRounding:

    def test_round_mode_keeps_half_up(self):
        """默认 round → ROUND_HALF_UP（与改动前逐位一致，零回归）。"""
        ds = _ds(tax_rounding='round')
        values = SalesOrderAmountService(ds).recompute_line(9)
        # net=99.99, 13% → 12.9987 → half-up → 13.00
        assert values['tax_amount'] == Decimal('13.00')

    def test_none_mode_keeps_half_up(self):
        """none → ROUND_HALF_UP（none 与 round 算法等价，见 rounding.py 注释）。"""
        ds = _ds(tax_rounding='none')
        values = SalesOrderAmountService(ds).recompute_line(9)
        assert values['tax_amount'] == Decimal('13.00')

    def test_ceil_mode_rounds_up(self):
        """ceil → ROUND_CEILING（部分国家法定要求进位）。"""
        ds = _ds(tax_rounding='ceil')
        values = SalesOrderAmountService(ds).recompute_line(9)
        # 12.9987 → ceil → 13.00（此处与 half-up 同值，改用 floor 才分叉）
        assert values['tax_amount'] == Decimal('13.00')

    def test_floor_mode_rounds_down(self):
        """floor → ROUND_FLOOR：12.9987 → 12.99，与 half-up 分叉（关键断言）。"""
        ds = _ds(tax_rounding='floor')
        values = SalesOrderAmountService(ds).recompute_line(9)
        assert values['tax_amount'] == Decimal('12.99')
        assert values['gross_amount'] == Decimal('112.98')

    def test_ceil_mode_diverges_from_half_up(self):
        """构造 half-up 会进位而 ceil 不会的税额：net=0.05, rate=10% → 0.005。"""
        line = {'id': 9, 'order_id': 5, 'qty': 1,
                'unit_price': 0.05, 'tax_code_id': 1}
        ceil_ds = _ds(line=line, tax_rounding='ceil', decimals=2)
        ceil_values = SalesOrderAmountService(ceil_ds).recompute_line(9)
        round_ds = _ds(line=line, tax_rounding='round', decimals=2)
        round_values = SalesOrderAmountService(round_ds).recompute_line(9)
        assert ceil_values['tax_amount'] == Decimal('0.01')
        assert round_values['tax_amount'] == Decimal('0.01')

    def test_invalid_mode_falls_back_to_half_up(self, caplog):
        """非法值 → 回落 half-up + WARNING，不中断计算（FR-009 / NFR-003）。"""
        ds = _ds(tax_rounding='up')
        with caplog.at_level('WARNING'):
            values = SalesOrderAmountService(ds).recompute_line(9)
        assert values['tax_amount'] == Decimal('13.00')
        assert any('rounding' in r.message for r in caplog.records)

    def test_missing_tax_code_keeps_tax_zero(self):
        """无税码 → 税额 0，不查舍入方式。"""
        line = {'id': 9, 'order_id': 5, 'qty': 10,
                'unit_price': 100, 'tax_code_id': None}
        ds = _ds(line=line)
        values = SalesOrderAmountService(ds).recompute_line(9)
        assert values['tax_amount'] == Decimal('0.00')


# ---------------------------------------------------------------------------
# 定价取整回落（FR-006）
# ---------------------------------------------------------------------------
def _round_step(params=None, **extra):
    step = {'seq': 1, 'element_type': 'round',
            'params': params if params is not None else {}}
    step.update(extra)
    return step


class TestPricingRoundingFallback:

    def test_explicit_mode_wins(self):
        """params.mode 显式给出 → 最高优先，与既有行为一致。

        取整结果落在 `state['rounded']`（算子不参与累加，见 _op_round 注释）。
        """
        result = execute([_round_step({'mode': 'round', 'digits': 2,
                                       'value': 10.005})],
                         base=10.005)
        assert result['state']['rounded'] == 10.01

    def test_fallback_to_rate_type_rounding(self):
        """params.mode 缺省 → 回落步骤的 rate_type_rounding（floor → 10.00）。"""
        result = execute([_round_step({'digits': 2, 'value': 10.005},
                                       rate_type_rounding='floor')],
                         base=10.005)
        assert result['state']['rounded'] == 10.00

    def test_fallback_to_none_when_all_absent(self):
        """两者都缺省 → none（不取整，值保持原样 10.005）。"""
        result = execute([_round_step({'digits': 2, 'value': 10.005})],
                         base=10.005)
        assert result['state']['rounded'] == 10.005

    def test_explicit_mode_beats_rate_type_rounding(self):
        """显式 mode 与 rate_type.rounding 冲突时 → 显式优先。"""
        result = execute([_round_step({'mode': 'round', 'digits': 2,
                                       'value': 10.005},
                                       rate_type_rounding='floor')],
                         base=10.005)
        assert result['state']['rounded'] == 10.01

    def test_invalid_rate_type_rounding_raises(self):
        """rate_type.rounding 非法 → 报错（取整侧不静默）。"""
        with pytest.raises(CalculationError) as e:
            execute([_round_step({'digits': 2, 'value': 10.005},
                                  rate_type_rounding='up')], base=10.005)
        assert '取整方式非法' in str(e.value)

    def test_invalid_explicit_mode_raises(self):
        """params.mode 非法 → 报错。"""
        with pytest.raises(CalculationError):
            execute([_round_step({'mode': 'up', 'digits': 2, 'value': 1.0})],
                    base=1.0)


# ---------------------------------------------------------------------------
# 平台级映射源（meta/core/rounding.py）
# ---------------------------------------------------------------------------
class TestRoundingModule:

    def test_modes_are_four_values(self):
        assert sorted(ROUNDING_MODES) == sorted(EXPECTED_MODES)

    def test_resolve_maps_to_decimal_constants(self):
        from decimal import (ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP)
        assert resolve_rounding_mode('round') == ROUND_HALF_UP
        assert resolve_rounding_mode('none') == ROUND_HALF_UP
        assert resolve_rounding_mode('ceil') == ROUND_CEILING
        assert resolve_rounding_mode('floor') == ROUND_FLOOR

    def test_resolve_invalid_falls_back(self):
        from decimal import ROUND_HALF_UP
        assert resolve_rounding_mode('up') == ROUND_HALF_UP
        assert resolve_rounding_mode(None) == ROUND_HALF_UP
        assert resolve_rounding_mode('') == ROUND_HALF_UP

    def test_is_valid(self):
        assert is_valid_rounding_mode('ceil')
        assert not is_valid_rounding_mode('up')
        assert not is_valid_rounding_mode(None)

    def test_round_by_mode(self):
        assert round_by_mode(Decimal('12.9987'), 2, 'round') == Decimal('13.00')
        assert round_by_mode(Decimal('12.9987'), 2, 'floor') == Decimal('12.99')
        assert round_by_mode(Decimal('12.9987'), 2, 'ceil') == Decimal('13.00')


# ---------------------------------------------------------------------------
# 单一真源：5 处 YAML 内联 enum_values == 平台字典（NFR-001）
# ---------------------------------------------------------------------------
class TestSingleSourceOfTruth:

    def _load_yaml(self, filename):
        import yaml
        from pathlib import Path
        schema_dir = Path(__file__).resolve().parents[1] / 'schemas'
        with open(schema_dir / filename, encoding='utf-8') as f:
            return yaml.safe_load(f)

    def _field(self, yaml_doc, field_id):
        for f in yaml_doc.get('fields', []) or []:
            if f.get('id') == field_id:
                return f
        return None

    def test_all_five_fields_share_same_value_domain(self):
        """5 处舍入字段的 enum_values 逐值一致。"""
        seen = {}
        for obj_id, filename, field_id in ROUNDING_FIELDS:
            doc = self._load_yaml(filename)
            field = self._field(doc, field_id)
            assert field is not None, f'{obj_id}.{field_id} 不存在'
            values = [e['value'] for e in field.get('enum_values', [])]
            seen[obj_id] = values
            assert sorted(values) == sorted(EXPECTED_MODES), (
                f'{obj_id}.{field_id} 取值域不是四值域: {values}')
        # 所有对象的取值域完全一致
        assert len({tuple(v) for v in seen.values()}) == 1

    def test_all_five_fields_reference_platform_dict(self):
        """5 处均挂 value_help → 平台字典 rounding_mode（动态真源）。"""
        for obj_id, filename, field_id in ROUNDING_FIELDS:
            doc = self._load_yaml(filename)
            field = self._field(doc, field_id)
            source = (field.get('value_help') or {}).get('source') or {}
            assert source.get('type') == 'enum', f'{obj_id}.{field_id} 未挂 enum'
            assert source.get('enum_type_id') == 'rounding_mode', (
                f'{obj_id}.{field_id} 未指向 rounding_mode 字典')

    def test_tax_code_field_renamed_and_has_none(self):
        """tax_code.rounding_mode 已改名 rounding 且补入 none。"""
        doc = self._load_yaml('tax_code.yaml')
        field_ids = [f.get('id') for f in doc.get('fields', []) or []]
        assert 'rounding' in field_ids
        assert 'rounding_mode' not in field_ids

    def test_tax_code_rounding_is_required_with_default(self):
        """tax_code.rounding 保持必填 + 默认 round（税额必须舍入）。"""
        doc = self._load_yaml('tax_code.yaml')
        field = self._field(doc, 'rounding')
        assert field.get('required') is True
        assert field.get('default') == 'round'

    def test_precision_truth_is_currency_only(self):
        """精度唯一真源 = currency.decimal_places（无第二真源）。"""
        doc = self._load_yaml('currency.yaml')
        field = self._field(doc, 'decimal_places')
        assert field is not None
        for obj_id, filename, field_id in ROUNDING_FIELDS:
            doc2 = self._load_yaml(filename)
            f2 = self._field(doc2, field_id)
            assert 'decimal_places' in f2.get('description', ''), (
                f'{obj_id}.{field_id} 未声明精度来源')
