# -*- coding: utf-8 -*-
"""销售订单行默认单位与单位兼容校验（R-SU-1 ~ R-SU-5 / V-SU-3 / V-SU-4）

覆盖 Spec 测试矩阵：
  T-A-1 物料有 sales_uom，行不填 uom_id → 默认取 sales_uom
  T-A-2 物料无 sales_uom，行不填 uom_id → 默认取 base_uom
  T-A-3 行显式填 uom_id → 不被覆盖
  T-A-4 行单位与基本单位不可换算 → item_uom_incompatible
  T-A-5 换算数据缺失（is_compatible = None）→ 放行
  R-SU-5 更新已存在行、仅改描述 → 不触发单位兼容校验
  T-A-9 服务物料行仍补服务字段

测试数据全部由假数据源注入，不连接真实运行库、不启动后端。

依据: docs/superpowers/specs/2026-10-26-sales-order-master-data-gap-spec.md
      §2.4 默认规则 / §2.5 校验规则 / §2.8 测试矩阵
"""

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

from meta.core.interceptors.sales_order_guard_interceptor import (
    SalesOrderGuardInterceptor,
)
from meta.services.sales_order_guard_service import (
    SalesOrderGuardError,
    SalesOrderGuardService,
)


def _key(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


class _FakeDS:
    """按 SQL 特征片段分流的假数据源，覆盖守卫与换算判定用到的查询。"""

    def __init__(self, items=None, uoms=None, groups=None,
                 item_convs=None, group_convs=None, types=None,
                 orders=None, lines=None):
        self.items = items or {}
        self.uoms = uoms or {}
        self.groups = groups or {}
        self.item_convs = item_convs or {}
        self.group_convs = group_convs or {}
        self.types = types or {}
        self.orders = orders or {}
        self.lines = lines or {}

    def query(self, sql, params=None):
        p = list(params or [])
        if 'FROM type_definitions' in sql:
            row = self.types.get(_key(p[0]))
            return [row] if row else []
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
        if 'FROM sales_orders WHERE id' in sql:
            row = self.orders.get(_key(p[0]))
            return [row] if row else []
        if 'FROM sales_order_lines WHERE parent_line_id' in sql:
            hit = any(str(v.get('parent_line_id')) == str(p[0])
                      for v in self.lines.values())
            return [{'ok': 1}] if hit else []
        if 'FROM sales_order_lines WHERE id' in sql:
            row = self.lines.get(_key(p[0]))
            return [row] if row else []
        raise AssertionError('unexpected sql: %s' % sql)


def _seed():
    """订单 10（draft）+ 行类型 + 4 个物料。

    item 1 基本单位 KG、销售单位 BOX，物料级可换算 1 BOX = 10 KG；
    item 2 只有基本单位 KG；
    item 3 服务物料，带销售单位与服务默认字段；
    item 4 基本单位 KG、销售单位 L（跨组不可换算）。
    """
    return _FakeDS(
        groups={
            1: {'id': 1, 'name': '数量', 'base_uom_id': 10, 'status': 'active'},
            2: {'id': 2, 'name': '体积', 'base_uom_id': 30, 'status': 'active'},
        },
        uoms={
            10: {'id': 10, 'name': 'KG', 'status': 'active', 'uom_group_id': 1},
            20: {'id': 20, 'name': 'BOX', 'status': 'active', 'uom_group_id': 1},
            30: {'id': 30, 'name': 'L', 'status': 'active', 'uom_group_id': 2},
        },
        group_convs={(1, 20): 10},
        item_convs={(1, 20): 10},
        items={
            1: {'id': 1, 'item_type': 'goods', 'status': 'active',
                'base_uom': 10, 'sales_uom': 20},
            2: {'id': 2, 'item_type': 'goods', 'status': 'active',
                'base_uom': 10, 'sales_uom': None},
            3: {'id': 3, 'item_type': 'service', 'status': 'active',
                'base_uom': 10, 'sales_uom': 20,
                'billing_method_default': 'fixed_price',
                'required_resource_type': 'engineer',
                'standard_duration': 8, 'duration_type': 'hour'},
            4: {'id': 4, 'item_type': 'goods', 'status': 'active',
                'base_uom': 10, 'sales_uom': 30},
        },
        types={
            1: {'id': 1, 'code': 'TA', 'scope_bo': 'sales_order',
                'level': 'header', 'document_category': 'standard'},
            101: {'id': 101, 'code': 'STD', 'scope_bo': 'sales_order',
                  'level': 'line', 'document_category': None},
            102: {'id': 102, 'code': 'SVC', 'scope_bo': 'sales_order',
                  'level': 'line', 'document_category': None},
        },
        orders={
            10: {'id': 10, 'order_no': 'SO-202610-000001', 'order_type_id': 1,
                 'order_date': '2026-10-26', 'status': 'draft',
                 'sales_org_id': 318, 'org_id': 318, 'currency_id': 8,
                 'exchange_rate': 1},
        },
    )


BASE_LINE = {'order_id': 10, 'line_no': '1', 'line_type_id': 101,
             'item_id': 1, 'qty': 1}


def _ctx(ds, action, params, old_data=None):
    return SimpleNamespace(
        meta_object=SimpleNamespace(id='sales_order_line'),
        action=action,
        object_id=params.get('id'),
        params=params,
        old_data=old_data or {},
        extra={},
        data_source=ds,
    )


# ─────────────────────────────────────────────────────────────────────────────
# T-A-1 / T-A-2 / T-A-3 —— 行默认单位（service_line_defaults）
# ─────────────────────────────────────────────────────────────────────────────

class TestLineUomDefaults:

    def test_t_a_1_defaults_to_sales_uom(self):
        defaults = SalesOrderGuardService(_seed()).service_line_defaults(
            {'item_id': 1})
        assert defaults == {'uom_id': 20}

    def test_t_a_2_defaults_to_base_uom(self):
        defaults = SalesOrderGuardService(_seed()).service_line_defaults(
            {'item_id': 2})
        assert defaults == {'uom_id': 10}

    def test_t_a_3_explicit_uom_not_overridden(self):
        defaults = SalesOrderGuardService(_seed()).service_line_defaults(
            {'item_id': 1, 'uom_id': 10})
        assert defaults == {}


# ─────────────────────────────────────────────────────────────────────────────
# T-A-1 / T-A-3 —— 拦截器创建路径（默认值并入写入参数）
# ─────────────────────────────────────────────────────────────────────────────

class TestLineInterceptorDefaults:

    def test_t_a_1_create_fills_sales_uom(self):
        ctx = _ctx(_seed(), 'crud_create', dict(BASE_LINE))
        SalesOrderGuardInterceptor().before_action(ctx)
        assert ctx.params['uom_id'] == 20

    def test_t_a_3_create_keeps_explicit_uom(self):
        ctx = _ctx(_seed(), 'crud_create', {**BASE_LINE, 'uom_id': 10})
        SalesOrderGuardInterceptor().before_action(ctx)
        assert ctx.params['uom_id'] == 10


# ─────────────────────────────────────────────────────────────────────────────
# T-A-4 / T-A-5 / R-SU-5 —— 行单位兼容校验
# ─────────────────────────────────────────────────────────────────────────────

class TestLineUomValidation:

    def test_t_a_4_rejects_inconvertible_line_uom(self):
        data = {**BASE_LINE, 'item_id': 4, 'uom_id': 30}
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_seed()).validate_line_write(
                data, is_create=True)
        assert e.value.rule == 'item_uom_incompatible'
        assert e.value.field_name == 'uom_id'

    def test_t_a_5_insufficient_conversion_data_allows(self):
        """行单位不在 uoms 表中 → is_compatible = None → 放行。"""
        data = {**BASE_LINE, 'item_id': 4, 'uom_id': 99}
        SalesOrderGuardService(_seed()).validate_line_write(data, is_create=True)

    def test_r_su_5_description_only_update_skips_uom_check(self):
        """存量行单位本就不可换算，仅改描述不应被打回（R-SU-5）。"""
        old = {'id': 100, 'order_id': 10, 'line_no': '1',
               'line_type_id': 101, 'item_id': 4, 'qty': 1,
               'uom_id': 30, 'description': '旧描述'}
        ctx = _ctx(_seed(), 'crud_update', {'id': 100, 'description': '新描述'},
                   old_data=old)
        SalesOrderGuardInterceptor().before_action(ctx)
        assert 'uom_id' not in ctx.params


# ─────────────────────────────────────────────────────────────────────────────
# T-A-9 —— 服务物料仍补服务字段
# ─────────────────────────────────────────────────────────────────────────────

class TestServiceItemDefaults:

    def test_t_a_9_service_item_still_fills_service_fields(self):
        defaults = SalesOrderGuardService(_seed()).service_line_defaults(
            {'item_id': 3})
        assert defaults == {
            'uom_id': 20,
            'billing_method': 'fixed_price',
            'required_resource_type': 'engineer',
            'service_duration': 8,
            'duration_type': 'hour',
        }
