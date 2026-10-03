# -*- coding: utf-8 -*-
"""T-01 纯守恒算法 plan() 单测 (无 I/O, 不含 raw SQL)。"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from meta.core.models import registry
from meta.services.allocation_service import AllocationError, AllocationService, plan


class TestPlanBasic:
    def test_third_split_100(self):
        """100 按 3 等份 → 余数给前 1 行 (确定性 tie-break 按序号升序)。"""
        result = plan(100, [1, 1, 1])
        assert result == [Decimal('33.34'), Decimal('33.33'), Decimal('33.33')]

    def test_proportional_weights(self):
        """按 3:7 比例分 100 → 30 / 70。"""
        assert plan(100, [3, 7]) == [Decimal('30.00'), Decimal('70.00')]

    def test_single_weight_takes_all(self):
        assert plan(58.5, [1]) == [Decimal('58.50')]

    def test_scale_zero(self):
        """scale=0 → 整数分配, 余数给序号靠前的行。"""
        assert plan(1, [1, 1, 1], scale=0) == [
            Decimal('1'), Decimal('0'), Decimal('0'),
        ]

    def test_scale_three(self):
        assert plan(10, [1, 1, 1], scale=3) == [
            Decimal('3.334'), Decimal('3.333'), Decimal('3.333'),
        ]

    def test_decimal_weights(self):
        """小数权重 1.5:2.5 = 3:5 → 分 80 得 30 / 50。"""
        assert plan(80, [Decimal('1.5'), Decimal('2.5')]) == [
            Decimal('30.00'), Decimal('50.00'),
        ]

    def test_str_inputs(self):
        assert plan('100', ['3', '7']) == [Decimal('30.00'), Decimal('70.00')]


class TestPlanConservation:
    @pytest.mark.parametrize('total,weights', [
        (100, [1, 1, 1]),
        (0.1, [1, 1, 1]),
        (999.99, [7, 11, 13, 17]),
        (1000000, [1, 2, 3, 4, 5, 6, 7]),
        (-100, [1, 1, 1]),
        (-0.05, [2, 3]),
    ])
    def test_sum_is_exact(self, total, weights):
        """硬性断言: Σ 分配值 == 总额 (精确, 非近似)。"""
        result = plan(total, weights)
        assert sum(result) == Decimal(str(total))

    def test_negative_total(self):
        """负总额 (红字/冲销) 同样守恒, 余数补给序号靠前的行。"""
        result = plan(-100, [1, 1, 1])
        assert sum(result) == Decimal('-100')
        assert result == [Decimal('-33.33'), Decimal('-33.33'), Decimal('-33.34')]

    def test_no_float_drift(self):
        """0.1 三分 → 0.04/0.03/0.03, 用二进制浮点无法精确守恒。"""
        assert plan(0.1, [1, 1, 1]) == [
            Decimal('0.04'), Decimal('0.03'), Decimal('0.03'),
        ]


class TestPlanValidation:
    def test_empty_weights(self):
        with pytest.raises(AllocationError):
            plan(100, [])

    def test_zero_weight(self):
        with pytest.raises(AllocationError):
            plan(100, [1, 0, 2])

    def test_negative_weight(self):
        with pytest.raises(AllocationError):
            plan(100, [1, -2])

    def test_negative_scale(self):
        with pytest.raises(AllocationError):
            plan(100, [1], scale=-1)

    def test_non_numeric_weight(self):
        with pytest.raises(AllocationError):
            plan(100, ['abc'])

    def test_allocation_error_is_value_error(self):
        """AllocationError 继承 ValueError, 便于上层按 ValueError 统一捕获。"""
        assert issubclass(AllocationError, ValueError)


class FakeDataSource:
    """只实现 find 的最小数据源替身 (T-02 子行定位)。"""

    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def find(self, table_name, filters=None, order_by=None, limit=None):
        self.queries.append((table_name, filters, order_by))
        fk, val = next(iter((filters or {}).items()))
        rows = [r for r in self.rows if r.get(fk) == val]
        if order_by:
            rows = sorted(rows, key=lambda r: r.get(order_by))
        return rows


@pytest.fixture
def child_meta():
    meta_obj = MagicMock()
    meta_obj.table_name = 'order_lines'
    return meta_obj


@pytest.fixture
def patched_registry(child_meta):
    with patch.object(registry, 'get', return_value=child_meta):
        yield


class TestResolveChildren:
    def test_explicit_fk_returns_ids_ordered(self, patched_registry):
        ds = FakeDataSource([
            {'id': 2, 'order_id': 1},
            {'id': 1, 'order_id': 1},
            {'id': 3, 'order_id': 2},
        ])
        svc = AllocationService(data_source=ds)
        ids = svc._resolve_children('order_line', 1, fk_field='order_id')
        assert ids == [1, 2]
        assert ds.queries[0] == ('order_lines', {'order_id': 1}, 'id')

    def test_fk_derived_when_omitted(self, patched_registry):
        ds = FakeDataSource([{'id': 5, 'order_id': 7}])
        svc = AllocationService(data_source=ds)
        with patch(
            'meta.services.cascade_service.HierarchyConfigLoader.get_foreign_key',
            return_value='order_id',
        ):
            ids = svc._resolve_children('order_line', 7)
        assert ids == [5]
        assert ds.queries[0][1] == {'order_id': 7}

    def test_count_mismatch_raises_422(self, patched_registry):
        ds = FakeDataSource([{'id': 1, 'order_id': 1}, {'id': 2, 'order_id': 1}])
        svc = AllocationService(data_source=ds)
        with pytest.raises(AllocationError) as exc:
            svc._resolve_children(
                'order_line', 1, fk_field='order_id', expected_count=3
            )
        assert exc.value.status_code == 422

    def test_count_match_passes(self, patched_registry):
        ds = FakeDataSource([{'id': 1, 'order_id': 1}, {'id': 2, 'order_id': 1}])
        svc = AllocationService(data_source=ds)
        assert svc._resolve_children(
            'order_line', 1, fk_field='order_id', expected_count=2
        ) == [1, 2]

    def test_unknown_object(self):
        with patch.object(registry, 'get', return_value=None):
            svc = AllocationService(data_source=FakeDataSource([]))
            with pytest.raises(AllocationError):
                svc._resolve_children('nope', 1, fk_field='order_id')

    def test_unresolvable_fk(self, patched_registry):
        svc = AllocationService(data_source=FakeDataSource([]))
        with patch(
            'meta.services.cascade_service.HierarchyConfigLoader.get_foreign_key',
            return_value=None,
        ):
            with pytest.raises(AllocationError):
                svc._resolve_children('order_line', 1)
