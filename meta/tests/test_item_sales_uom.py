# -*- coding: utf-8 -*-
"""物料销售单位校验（V-SU-1 / V-SU-2 / V-SU-4）

覆盖 Spec 测试矩阵：
  T-A-6 物料 sales_uom 不可换算 → sales_uom_incompatible
  T-A-7 改 base_uom 导致已有 sales_uom 不可换算 → sales_uom_incompatible_with_base
  T-A-8 创建物料未给 sales_uom（空语义 = 基本单位）→ 通过
  V-SU-4 换算数据不足（is_compatible 返回 None）→ 放行

测试数据全部由假数据源注入，不连接真实运行库、不启动后端。

依据: docs/superpowers/specs/2026-10-26-sales-order-master-data-gap-spec.md
      §2.5 校验规则 / §2.8 测试矩阵
"""

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.uom_conversion_guard_interceptor import (
    UomConversionGuardInterceptor,
)
from meta.services.uom_conversion_guard_service import (
    UomConversionGuardError,
    UomConversionGuardService,
)


def _key(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


class _FakeDS:
    """按 SQL 特征片段分流的假数据源，覆盖换算判定用到的查询形态。"""

    def __init__(self, items=None, uoms=None, groups=None,
                 item_convs=None, group_convs=None):
        self.items = items or {}
        self.uoms = uoms or {}
        self.groups = groups or {}
        self.item_convs = item_convs or {}   # (item_id, uom_id) -> factor
        self.group_convs = group_convs or {}  # (group_id, uom_id) -> factor

    def query(self, sql, params=None):
        p = list(params or [])
        if 'COUNT(*)' in sql:
            return [{'cnt': self._count(sql, p)}]
        if 'FROM items' in sql:
            row = self.items.get(_key(p[0]))
            return [row] if row else []
        if 'FROM uoms' in sql:
            if ' IN (' in sql:
                wanted = {str(v) for v in p}
                return [row for uid, row in self.uoms.items()
                        if str(uid) in wanted]
            row = self.uoms.get(_key(p[0]))
            return [row] if row else []
        if 'FROM uom_groups' in sql:
            row = self.groups.get(_key(p[0]))
            return [row] if row else []
        if 'FROM item_uom_conversions' in sql:
            factor = self.item_convs.get((_key(p[0]), _key(p[1])))
            return [{'factor': factor}] if factor is not None else []
        if 'FROM uom_conversions' in sql:
            factor = self.group_convs.get((_key(p[0]), _key(p[1])))
            return [{'factor': factor}] if factor is not None else []
        raise AssertionError('unexpected sql: %s' % sql)

    def _count(self, sql, p):
        if 'FROM item_uom_conversions' in sql:
            idx = 0 if 'WHERE item_id' in sql else 1
            return sum(1 for key in self.item_convs if str(key[idx]) == str(p[0]))
        if 'FROM uom_conversions' in sql:
            idx = 0 if 'WHERE uom_group_id' in sql else 1
            return sum(1 for key in self.group_convs if str(key[idx]) == str(p[0]))
        if 'FROM uom_groups' in sql:
            return sum(1 for row in self.groups.values()
                       if str(row.get('base_uom_id')) == str(p[0]))
        raise AssertionError('unexpected count sql: %s' % sql)


def _units():
    """数量组（基本单位 KG）+ 体积组（基本单位 L）；组内 1 BOX = 10 KG。"""
    return dict(
        groups={
            1: {'id': 1, 'name': '数量', 'base_uom_id': 10, 'status': 'active'},
            2: {'id': 2, 'name': '体积', 'base_uom_id': 30, 'status': 'active'},
        },
        uoms={
            10: {'id': 10, 'name': 'KG', 'status': 'active', 'uom_group_id': 1},
            11: {'id': 11, 'name': 'G', 'status': 'active', 'uom_group_id': 1},
            20: {'id': 20, 'name': 'BOX', 'status': 'active', 'uom_group_id': 1},
            30: {'id': 30, 'name': 'L', 'status': 'active', 'uom_group_id': 2},
        },
        group_convs={(1, 20): 10, (1, 11): 1000},
    )


def _ds(items=None):
    return _FakeDS(items=items or {}, **_units())


# ─────────────────────────────────────────────────────────────────────────────
# T-A-6 / T-A-8 —— 物料写入 sales_uom
# ─────────────────────────────────────────────────────────────────────────────

class TestItemSalesUomWrite:

    def test_t_a_6_rejects_inconvertible_sales_uom(self):
        ds = _ds({1: {'id': 1, 'status': 'active', 'base_uom': 10,
                      'sales_uom': 30}})
        with pytest.raises(UomConversionGuardError) as e:
            UomConversionGuardService(ds).validate_item_sales_uom(1, 30)
        assert e.value.rule == 'sales_uom_incompatible'
        assert e.value.field_name == '销售单位'

    def test_t_a_6_rejects_inconvertible_sales_uom_on_create(self):
        """创建时 item_id 尚不可用，按传入 base_uom 做组内换算判定。"""
        with pytest.raises(UomConversionGuardError) as e:
            UomConversionGuardService(_ds()).validate_item_sales_uom(None, 30, 10)
        assert e.value.rule == 'sales_uom_incompatible'

    def test_t_a_8_allows_blank_sales_uom(self):
        UomConversionGuardService(_ds()).validate_item_sales_uom(None, None, 10)

    def test_t_a_8_allows_sales_uom_equal_to_base(self):
        ds = _ds({1: {'id': 1, 'status': 'active', 'base_uom': 10,
                      'sales_uom': 10}})
        svc = UomConversionGuardService(ds)
        svc.validate_item_sales_uom(None, 10, 10)
        svc.validate_item_sales_uom(1, 10)

    def test_convertible_sales_uom_passes(self):
        ds = _ds({1: {'id': 1, 'status': 'active', 'base_uom': 10,
                      'sales_uom': 20}})
        UomConversionGuardService(ds).validate_item_sales_uom(1, 20)


# ─────────────────────────────────────────────────────────────────────────────
# T-A-7 —— 物料改 base_uom
# ─────────────────────────────────────────────────────────────────────────────

class TestItemBaseUomChange:

    def test_t_a_7_rejects_base_change_breaking_sales_uom(self):
        """无物料级换算行（不触发 V7 锁定），但新基本单位与销售单位跨组。"""
        ds = _ds({1: {'id': 1, 'status': 'active', 'base_uom': 10,
                      'sales_uom': 20}})
        with pytest.raises(UomConversionGuardError) as e:
            UomConversionGuardService(ds).validate_item_update(1, 30)
        assert e.value.rule == 'sales_uom_incompatible_with_base'
        assert e.value.field_name == '销售单位'

    def test_base_change_keeping_compatibility_passes(self):
        ds = _ds({1: {'id': 1, 'status': 'active', 'base_uom': 10,
                      'sales_uom': 20}})
        UomConversionGuardService(ds).validate_item_update(1, 11)


# ─────────────────────────────────────────────────────────────────────────────
# V-SU-4 —— 换算数据不足（is_compatible = None）放行
# ─────────────────────────────────────────────────────────────────────────────

class TestInsufficientConversionData:

    def test_none_compatibility_allows_sales_uom(self):
        """销售单位不在 uoms 表中 → 判定不足，放行。"""
        ds = _ds({1: {'id': 1, 'status': 'active', 'base_uom': 10,
                      'sales_uom': 99}})
        UomConversionGuardService(ds).validate_item_sales_uom(1, 99)

    def test_none_compatibility_allows_base_change(self):
        """新基本单位不在 uoms 表中 → 判定不足，放行。"""
        ds = _ds({1: {'id': 1, 'status': 'active', 'base_uom': 10,
                      'sales_uom': 20}})
        UomConversionGuardService(ds).validate_item_update(1, 99)


# ─────────────────────────────────────────────────────────────────────────────
# 拦截器接线：item 创建 / 更新均覆盖
# ─────────────────────────────────────────────────────────────────────────────

class TestItemInterceptorWiring:

    @staticmethod
    def _ctx(ds, action, params):
        return SimpleNamespace(
            meta_object=SimpleNamespace(id='item'),
            action=action,
            object_id=params.get('id'),
            params=params,
            old_data={},
            extra={},
            data_source=ds,
        )

    def test_create_with_incompatible_sales_uom_raises(self):
        ctx = self._ctx(_ds(), 'crud_create',
                        {'base_uom': 10, 'sales_uom': 30})
        with pytest.raises(ValidationFailedError) as e:
            UomConversionGuardInterceptor().before_action(ctx)
        assert e.value.details[0]['rule'] == 'sales_uom_incompatible'

    def test_create_without_sales_uom_passes(self):
        ctx = self._ctx(_ds(), 'crud_create', {'base_uom': 10})
        UomConversionGuardInterceptor().before_action(ctx)
