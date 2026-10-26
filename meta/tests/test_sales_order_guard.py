# -*- coding: utf-8 -*-
"""销售订单守卫测试（W0-R1/R2/R4/R5/R6/R8/R9/R10 + 类型删除引用保护）

依据: meta/schemas/sales_order.yaml / sales_order_line.yaml 头注释
      docs/superpowers/specs/2026-10-24-sales-order-wave0-detailed-plan.md §1.4
"""

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.sales_order_guard_interceptor import (
    SalesOrderGuardInterceptor,
)
from meta.services.sales_order_guard_service import (
    SalesOrderGuardError,
    SalesOrderGuardService,
)
from meta.services.type_definition_guard_service import (
    TypeDefinitionGuardError,
    TypeDefinitionGuardService,
)


class _FakeDS:
    """按 SQL 特征片段分流，只覆盖守卫与删除引用检查用到的查询。"""

    def __init__(self, types=None, orders=None, lines=None,
                 org_functions=None, refs=None, items=None,
                 addresses=None, divisions=None, raise_on_query=False):
        self.types = types or {}
        self.orders = orders or {}
        self.lines = lines or {}
        self.org_functions = org_functions or set()
        self.refs = refs or {}
        self.items = items or {}
        self.addresses = addresses or {}
        self.divisions = divisions or {}
        self.raise_on_query = raise_on_query

    def query(self, sql, params=None):
        if self.raise_on_query:
            raise RuntimeError('db down')
        p = list(params or [])

        if 'FROM type_definitions WHERE id' in sql:
            row = self.types.get(p[0])
            return [row] if row else []
        if 'FROM items WHERE id' in sql:
            row = self.items.get(p[0])
            return [row] if row else []
        if 'FROM addresses WHERE id' in sql:
            row = self.addresses.get(p[0])
            return [row] if row else []
        if 'FROM divisions WHERE code' in sql:
            row = self.divisions.get(p[0])
            return [row] if row else []
        if 'FROM sales_orders WHERE id' in sql:
            row = self.orders.get(p[0])
            return [row] if row else []
        if 'FROM sales_order_lines WHERE parent_line_id' in sql:
            hit = any(str(v.get('parent_line_id')) == str(p[0])
                      for v in self.lines.values())
            return [{'ok': 1}] if hit else []
        # E6 / R-RET-8：累计退货量（排除已取消行 / 单，可排除当前行）
        if 'FROM sales_order_lines rl' in sql:
            exclude_id = p[1] if len(p) > 1 else None
            total = 0.0
            for line in self.lines.values():
                if str(line.get('reference_line_id')) != str(p[0]):
                    continue
                if str(line.get('status')) == 'cancelled':
                    continue
                order = self.orders.get(line.get('order_id')) or {}
                if str(order.get('status')) == 'cancelled':
                    continue
                if exclude_id is not None \
                        and str(line.get('id')) == str(exclude_id):
                    continue
                total += float(line.get('qty') or 0)
            return [{'qty': total}]
        # E6 / R-RET-2：引用行及其订单上下文（JOIN sales_orders）
        if 'FROM sales_order_lines l' in sql:
            row = self.lines.get(p[0])
            if not row:
                return []
            order = self.orders.get(row.get('order_id')) or {}
            merged = dict(row)
            merged['ref_order_type_id'] = order.get('order_type_id')
            merged['ref_order_status'] = order.get('status')
            merged['ref_customer_account_id'] = order.get('customer_account_id')
            return [merged]
        # E6 / R-RET-9：原行是否已被退货行引用
        if 'WHERE reference_line_id = ?' in sql:
            hit = any(str(v.get('reference_line_id')) == str(p[0])
                      for v in self.lines.values())
            return [{'ok': 1}] if hit else []
        if 'FROM sales_order_lines WHERE id' in sql:
            row = self.lines.get(p[0])
            return [row] if row else []
        if 'FROM org_functions' in sql:
            return [{'ok': 1}] if (p[0], p[1]) in self.org_functions else []
        if 'COUNT(*) AS cnt' in sql:
            table = sql.split('FROM ', 1)[1].split(' WHERE', 1)[0].strip()
            return [{'cnt': self.refs.get(table, {}).get(p[0], 0)}]
        raise AssertionError('unexpected sql: %s' % sql)


TYPES = {
    1: {'id': 1, 'code': 'TA', 'scope_bo': 'sales_order', 'level': 'header',
        'document_category': 'standard'},
    2: {'id': 2, 'code': 'RE', 'scope_bo': 'sales_order', 'level': 'header',
        'document_category': 'return'},
    5: {'id': 5, 'code': 'DLV', 'scope_bo': 'delivery', 'level': 'header',
        'document_category': 'standard'},
    101: {'id': 101, 'code': 'STD', 'scope_bo': 'sales_order', 'level': 'line',
          'document_category': None, 'line_category': 'material'},
    102: {'id': 102, 'code': 'SVC', 'scope_bo': 'sales_order', 'level': 'line',
          'document_category': None, 'line_category': 'service'},
    103: {'id': 103, 'code': 'RET', 'scope_bo': 'sales_order', 'level': 'line',
          'document_category': None, 'line_category': 'return'},
}

ORDERS = {
    10: {'id': 10, 'order_no': 'SO-202610-000001', 'order_type_id': 1,
         'status': 'draft', 'currency_id': 8, 'exchange_rate': 1,
         'sales_org_id': 318, 'org_id': 318, 'order_date': '2026-10-25',
         'customer_account_id': 501},
    11: {'id': 11, 'order_no': 'SO-202610-000002', 'order_type_id': 1,
         'status': 'submitted', 'currency_id': 8, 'exchange_rate': 1,
         'sales_org_id': 318, 'org_id': 318, 'order_date': '2026-10-25',
         'ship_to_address_id': 301, 'bill_to_address_id': 302,
         'customer_account_id': 501},
    12: {'id': 12, 'order_no': 'SO-202610-000003', 'order_type_id': 1,
         'status': 'confirmed', 'currency_id': 8, 'exchange_rate': 1,
         'sales_org_id': 318, 'org_id': 318, 'order_date': '2026-10-25',
         'customer_account_id': 501},
    13: {'id': 13, 'order_no': 'SO-202610-000004', 'order_type_id': 5,
         'status': 'draft', 'currency_id': 8, 'exchange_rate': 1,
         'sales_org_id': 318, 'org_id': 318, 'order_date': '2026-10-25',
         'customer_account_id': 501},
    14: {'id': 14, 'order_no': 'SO-202610-000005', 'order_type_id': 2,
         'status': 'draft', 'currency_id': 8, 'exchange_rate': 1,
         'sales_org_id': 318, 'org_id': 318, 'order_date': '2026-10-25',
         'customer_account_id': 501},
    15: {'id': 15, 'order_no': 'SO-202610-000006', 'order_type_id': 2,
         'status': 'draft', 'currency_id': 8, 'exchange_rate': 1,
         'sales_org_id': 318, 'org_id': 318, 'order_date': '2026-10-25',
         'customer_account_id': 502},
    16: {'id': 16, 'order_no': 'SO-202610-000007', 'order_type_id': 2,
         'status': 'draft', 'currency_id': 8, 'exchange_rate': 1,
         'sales_org_id': 318, 'org_id': 318, 'order_date': '2026-10-25',
         'customer_account_id': 501},
}

LINES = {
    100: {'id': 100, 'order_id': 10, 'line_no': '1', 'line_type_id': 101},
    101: {'id': 101, 'order_id': 11, 'line_no': '1', 'line_type_id': 101},
    # E6：已确认原单（12）的被引用行，供退货行复制字段 / 累计数量比对
    200: {'id': 200, 'order_id': 12, 'line_no': '2', 'line_type_id': 101,
          'item_id': 2, 'qty': 5, 'uom_id': 2, 'tax_code_id': 7,
          'customer_item_code': 'C-200', 'description': '原行描述',
          'unit_price': 99, 'plant_location_id': 7},
    # E6：退货单（14）内的退货行，供「同单引用」反向用例
    300: {'id': 300, 'order_id': 14, 'line_no': '2', 'line_type_id': 103,
          'item_id': 2, 'qty': 1, 'uom_id': 2},
}

ITEMS = {
    2: {'id': 2, 'item_type': 'goods', 'status': 'active'},
    3: {'id': 3, 'item_type': 'service', 'status': 'active',
        'billing_method_default': 'fixed_price',
        'required_resource_type': 'engineer',
        'standard_duration': 8,
        'duration_type': 'hour'},
    4: {'id': 4, 'item_type': 'service', 'status': 'draft'},
}


ADDRESSES = {
    301: {'id': 301, 'formatted_address': '上海市浦东新区世纪大道 100 号'},
    302: {'id': 302, 'formatted_address': '上海市静安区南京西路 200 号'},
}

DIVISIONS = {
    'DEFAULT': {'code': 'DEFAULT', 'status': 'active'},
    'OLD': {'code': 'OLD', 'status': 'inactive'},
}


def _ds(**kwargs):
    return _FakeDS(types=TYPES, orders=ORDERS, lines=LINES, items=ITEMS,
                   addresses=ADDRESSES, divisions=DIVISIONS,
                   org_functions={(318, 'sales')}, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# 抬头
# ─────────────────────────────────────────────────────────────────────────────

class TestOrderWrite:

    def test_create_ok(self):
        SalesOrderGuardService(_ds()).validate_order_write(
            {'order_type_id': 1, 'sales_org_id': 318, 'order_no': 'SO-X'}, is_create=True)

    def test_order_type_must_be_header_scope(self):
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_order_write(
                {'order_type_id': 101, 'sales_org_id': 318}, is_create=True)
        assert e.value.rule == 'order_type_scope'

    def test_sales_org_requires_sales_function(self):
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_order_write(
                {'order_type_id': 1, 'sales_org_id': 1}, is_create=True)
        assert e.value.rule == 'sales_org_not_sales'

    def test_division_ok_on_create(self):
        SalesOrderGuardService(_ds()).validate_order_write(
            {'order_type_id': 1, 'sales_org_id': 318, 'division_code': 'DEFAULT'},
            is_create=True)

    def test_division_not_found(self):
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_order_write(
                {'order_type_id': 1, 'sales_org_id': 318, 'division_code': 'NOPE'},
                is_create=True)
        assert e.value.rule == 'division_not_found'
        assert e.value.field_name == 'division_code'

    def test_division_inactive(self):
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_order_write(
                {'order_type_id': 1, 'sales_org_id': 318, 'division_code': 'OLD'},
                is_create=True)
        assert e.value.rule == 'division_inactive'

    def test_division_unchanged_on_update_ok(self):
        """存量订单已带停用产品组时，改其他字段不因历史值被拦。"""
        SalesOrderGuardService(_ds()).validate_order_write(
            {'division_code': 'OLD', 'note': '改备注'},
            old_data={'division_code': 'OLD'})

    def test_division_query_failure_fail_open(self):
        SalesOrderGuardService(_ds(raise_on_query=True)).validate_order_write(
            {'order_type_id': 1, 'sales_org_id': 318, 'division_code': 'NOPE'},
            is_create=True)

    def test_order_no_immutable(self):
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_order_write(
                {'order_no': 'SO-NEW'}, old_data=ORDERS[10])
        assert e.value.rule == 'order_no_immutable'
        assert e.value.field_name == 'order_no'

    def test_order_no_unchanged_ok(self):
        SalesOrderGuardService(_ds()).validate_order_write(
            {'order_no': 'SO-202610-000001'}, old_data=ORDERS[10])

    def test_frozen_fields_after_draft(self):
        for field, value in (('currency_id', 9), ('order_type_id', 2)):
            with pytest.raises(SalesOrderGuardError) as e:
                SalesOrderGuardService(_ds()).validate_order_write(
                    {field: value}, old_data=ORDERS[11])
            assert e.value.rule == 'field_frozen_after_draft'
            assert e.value.field_name == field

    def test_exchange_rate_frozen_after_confirm(self):
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_order_write(
                {'exchange_rate': 7.5}, old_data=ORDERS[12])
        assert e.value.rule == 'exchange_rate_frozen'

    def test_exchange_rate_same_value_ok(self):
        SalesOrderGuardService(_ds()).validate_order_write(
            {'exchange_rate': 1}, old_data=ORDERS[12])

    def test_exchange_rate_date_required_when_converted(self):
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_order_write(
                {'exchange_rate': 7.08}, old_data=ORDERS[10])
        assert e.value.rule == 'exchange_rate_date_required'
        assert e.value.field_name == 'exchange_rate_date'

    def test_exchange_rate_date_not_required_for_local(self):
        SalesOrderGuardService(_ds()).validate_order_write(
            {'exchange_rate': 1}, old_data=ORDERS[10])

    def test_exchange_rate_date_present_ok(self):
        SalesOrderGuardService(_ds()).validate_order_write(
            {'exchange_rate': 7.08, 'exchange_rate_date': '2026-10-25'},
            old_data=ORDERS[10])

    def test_exchange_rate_date_required_on_create(self):
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_order_write(
                {'order_type_id': 1, 'sales_org_id': 318, 'exchange_rate': 7.08},
                is_create=True)
        assert e.value.rule == 'exchange_rate_date_required'

    def test_exchange_rate_type_frozen_after_confirm(self):
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_order_write(
                {'exchange_rate_type': 'corporate'}, old_data=ORDERS[12])
        assert e.value.rule == 'exchange_rate_frozen'
        assert e.value.field_name == 'exchange_rate_type'

    def test_exchange_rate_date_frozen_after_confirm(self):
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_order_write(
                {'exchange_rate_date': '2026-10-24'}, old_data=ORDERS[12])
        assert e.value.rule == 'exchange_rate_frozen'
        assert e.value.field_name == 'exchange_rate_date'

    def test_delete_only_draft(self):
        svc = SalesOrderGuardService(_ds())
        svc.validate_order_delete(10)
        with pytest.raises(SalesOrderGuardError) as e:
            svc.validate_order_delete(11)
        assert e.value.rule == 'order_delete_not_draft'

    def test_fail_open_on_query_error(self):
        svc = SalesOrderGuardService(_ds(raise_on_query=True))
        svc.validate_order_write({'order_type_id': 1, 'sales_org_id': 1}, is_create=True)
        svc.validate_order_delete(11)


# ─────────────────────────────────────────────────────────────────────────────
# 订单行
# ─────────────────────────────────────────────────────────────────────────────

BASE_LINE = {'order_id': 10, 'line_no': '1', 'line_type_id': 101,
             'item_id': 2, 'qty': 1, 'uom_id': 2, 'unit_price': 10}


class TestLineWrite:

    def test_create_ok(self):
        SalesOrderGuardService(_ds()).validate_line_write(dict(BASE_LINE), is_create=True)

    def test_parent_must_be_draft(self):
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_line_write(
                {**BASE_LINE, 'order_id': 11}, is_create=True)
        assert e.value.rule == 'line_write_parent_not_draft'

    def test_qty_must_be_positive(self):
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_line_write(
                {**BASE_LINE, 'qty': 0}, is_create=True)
        assert e.value.rule == 'qty_not_positive'

    def test_line_type_must_be_line_level(self):
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_line_write(
                {**BASE_LINE, 'line_type_id': 1}, is_create=True)
        assert e.value.rule == 'line_type_scope'

    def test_line_type_scope_must_match_order_type(self):
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_line_write(
                {**BASE_LINE, 'order_id': 13}, is_create=True)
        assert e.value.rule == 'line_type_scope_mismatch'

    def test_uom_required(self):
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_line_write(
                {k: v for k, v in BASE_LINE.items() if k != 'uom_id'}, is_create=True)
        assert e.value.rule == 'uom_required'

    def test_description_required_when_no_item(self):
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_line_write(
                {k: v for k, v in BASE_LINE.items() if k != 'item_id'}, is_create=True)
        assert e.value.rule == 'description_required'

    def test_no_item_with_description_ok(self):
        data = {k: v for k, v in BASE_LINE.items() if k != 'item_id'}
        data['description'] = '运费'
        SalesOrderGuardService(_ds()).validate_line_write(data, is_create=True)

    def test_delete_requires_draft_parent(self):
        svc = SalesOrderGuardService(_ds())
        svc.validate_line_delete(100)
        with pytest.raises(SalesOrderGuardError) as e:
            svc.validate_line_delete(101)
        assert e.value.rule == 'line_delete_parent_not_draft'


# ─────────────────────────────────────────────────────────────────────────────
# 结构展开守卫（W2-R1 ~ W2-R6）
# ─────────────────────────────────────────────────────────────────────────────

class TestExpandLineWrite:

    def test_rejects_expand_fields_on_create(self):
        for field, value in (('configuration_id', 901),
                             ('parent_line_id', 100),
                             ('component_no', 'L0010')):
            with pytest.raises(SalesOrderGuardError) as e:
                SalesOrderGuardService(_ds()).validate_line_write(
                    {**BASE_LINE, field: value}, is_create=True)
            assert e.value.rule == 'expand_field_readonly'
            assert e.value.field_name == field

    def test_rejects_changed_expand_field_on_update(self):
        old = dict(BASE_LINE, id=100, order_id=10, parent_line_id=100)
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_line_write(
                {**BASE_LINE, 'component_no': 'L0020'}, old_data=old)
        assert e.value.rule == 'expand_field_readonly'

    def test_allows_same_expand_field_on_update(self):
        old = dict(BASE_LINE, id=100, order_id=10, parent_line_id=100,
                   component_no='L0010')
        SalesOrderGuardService(_ds()).validate_line_write(
            {**BASE_LINE, 'component_no': 'L0010', 'parent_line_id': 100},
            old_data=old)

    def test_rejects_component_item_change(self):
        old = dict(BASE_LINE, id=100, order_id=10, parent_line_id=100)
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_line_write(
                {**BASE_LINE, 'item_id': 3}, old_data=old)
        assert e.value.rule == 'component_item_immutable'

    def test_rejects_component_no_format(self):
        old = dict(BASE_LINE, id=100, order_id=10, parent_line_id=100,
                   component_no='X0010')
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_line_write(
                {**BASE_LINE, 'component_no': 'X0010', 'parent_line_id': 100},
                old_data=old)
        assert e.value.rule == 'component_no_format'

    def test_rejects_unknown_pricing_mode(self):
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_line_write(
                {**BASE_LINE, 'pricing_mode': 'gift'}, is_create=True)
        assert e.value.rule == 'pricing_mode_invalid'

    def test_accepts_known_pricing_mode(self):
        for mode in ('standalone', 'bundle_price', 'component_price',
                     'base_plus_option'):
            SalesOrderGuardService(_ds()).validate_line_write(
                {**BASE_LINE, 'pricing_mode': mode}, is_create=True)

    def test_rejects_location_on_service_line(self):
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_line_write(
                {**BASE_LINE, 'line_type_id': 102, 'plant_location_id': 7},
                is_create=True)
        assert e.value.rule == 'service_line_no_location'

    def test_delete_rejects_parent_with_children(self):
        lines = dict(LINES)
        lines[200] = {'id': 200, 'order_id': 10, 'line_no': '2',
                      'line_type_id': 101, 'parent_line_id': 100}
        ds = _FakeDS(types=TYPES, orders=ORDERS, lines=lines,
                     org_functions={(318, 'sales')})
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(ds).validate_line_delete(100)
        assert e.value.rule == 'line_has_children'

    def test_delete_child_ok(self):
        lines = dict(LINES)
        lines[200] = {'id': 200, 'order_id': 10, 'line_no': '2',
                      'line_type_id': 101, 'parent_line_id': 100}
        ds = _FakeDS(types=TYPES, orders=ORDERS, lines=lines,
                     org_functions={(318, 'sales')})
        SalesOrderGuardService(ds).validate_line_delete(200)


# ─────────────────────────────────────────────────────────────────────────────
# W2-A 服务行属性
# ─────────────────────────────────────────────────────────────────────────────

SERVICE_LINE = {**BASE_LINE, 'line_type_id': 102, 'item_id': 3}


class TestServiceLine:

    def test_service_line_ok(self):
        SalesOrderGuardService(_ds()).validate_line_write(
            {**SERVICE_LINE, 'service_start_date': '2026-11-01',
             'service_end_date': '2026-11-02', 'billing_method': 'fixed_price',
             'service_duration': 4, 'duration_type': 'hour'}, is_create=True)

    def test_goods_item_rejects_service_fields(self):
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_line_write(
                {**BASE_LINE, 'billing_method': 'fixed_price'}, is_create=True)
        assert e.value.rule == 'service_field_non_service_item'

    def test_no_item_rejects_service_fields(self):
        data = {k: v for k, v in BASE_LINE.items() if k != 'item_id'}
        data.update({'description': '咨询', 'service_start_date': '2026-11-01'})
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_line_write(data, is_create=True)
        assert e.value.rule == 'service_field_non_service_item'

    def test_service_item_must_be_active(self):
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_line_write(
                {**SERVICE_LINE, 'item_id': 4}, is_create=True)
        assert e.value.rule == 'service_item_not_sellable'

    def test_end_before_start_rejected(self):
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_line_write(
                {**SERVICE_LINE, 'service_start_date': '2026-11-02',
                 'service_end_date': '2026-11-01'}, is_create=True)
        assert e.value.rule == 'service_date_range'

    def test_duration_must_be_positive(self):
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_line_write(
                {**SERVICE_LINE, 'service_duration': 0, 'duration_type': 'hour'},
                is_create=True)
        assert e.value.rule == 'service_duration_invalid'

    def test_duration_requires_duration_type(self):
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_line_write(
                {**SERVICE_LINE, 'service_duration': 2}, is_create=True)
        assert e.value.rule == 'duration_type_required'

    def test_enum_must_be_whitelisted(self):
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_line_write(
                {**SERVICE_LINE, 'billing_method': 'free'}, is_create=True)
        assert e.value.rule == 'service_enum_invalid'

    def test_item_missing_is_fail_open(self):
        data = {**SERVICE_LINE, 'item_id': 999, 'billing_method': 'fixed_price'}
        SalesOrderGuardService(_ds()).validate_line_write(data, is_create=True)

    def test_defaults_from_item(self):
        defaults = SalesOrderGuardService(_ds()).service_line_defaults({'item_id': 3})
        assert defaults == {'billing_method': 'fixed_price',
                            'required_resource_type': 'engineer',
                            'service_duration': 8, 'duration_type': 'hour'}

    def test_defaults_do_not_override_explicit_values(self):
        defaults = SalesOrderGuardService(_ds()).service_line_defaults(
            {'item_id': 3, 'billing_method': 'milestone'})
        assert 'billing_method' not in defaults
        assert defaults['duration_type'] == 'hour'

    def test_defaults_empty_for_goods(self):
        assert SalesOrderGuardService(_ds()).service_line_defaults(
            {'item_id': 2}) == {}


# ─────────────────────────────────────────────────────────────────────────────
# W2-D 地址文本快照
# ─────────────────────────────────────────────────────────────────────────────

class TestAddressSnapshot:

    def test_snapshot_filled_on_confirm(self):
        snapshot = SalesOrderGuardService(_ds()).snapshot_address_text(
            {'status': 'confirmed', 'ship_to_address_id': 301,
             'bill_to_address_id': 302}, ORDERS[11])
        assert snapshot == {
            'ship_to_address_text': '上海市浦东新区世纪大道 100 号',
            'bill_to_address_text': '上海市静安区南京西路 200 号'}

    def test_snapshot_skipped_when_already_confirmed(self):
        assert SalesOrderGuardService(_ds()).snapshot_address_text(
            {'status': 'confirmed', 'ship_to_address_id': 301}, ORDERS[12]) == {}

    def test_snapshot_skipped_without_address(self):
        assert SalesOrderGuardService(_ds()).snapshot_address_text(
            {'status': 'confirmed'}, ORDERS[11]) == {}

    def test_snapshot_fail_open_on_query_error(self):
        svc = SalesOrderGuardService(_ds(raise_on_query=True))
        assert svc.snapshot_address_text(
            {'status': 'confirmed', 'ship_to_address_id': 301}, ORDERS[11]) == {}

    def test_frozen_after_non_draft(self):
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_order_write(
                {'ship_to_address_text': '改过的地址'}, old_data=ORDERS[12])
        assert e.value.rule == 'address_snapshot_locked'
        assert e.value.field_name == 'ship_to_address_text'

    def test_confirm_allows_snapshot_write(self):
        SalesOrderGuardService(_ds()).validate_order_write(
            {'status': 'confirmed', 'ship_to_address_text': '快照值'},
            old_data=ORDERS[11])

    def test_confirm_cannot_clear_snapshot(self):
        old = {**ORDERS[11], 'ship_to_address_text': '原快照'}
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(_ds()).validate_order_write(
                {'status': 'confirmed', 'ship_to_address_text': ''}, old_data=old)
        assert e.value.rule == 'address_snapshot_locked'

    def test_draft_can_edit_snapshot(self):
        SalesOrderGuardService(_ds()).validate_order_write(
            {'ship_to_address_text': '草稿手工填写'}, old_data=ORDERS[10])


# ─────────────────────────────────────────────────────────────────────────────
# 拦截器接线
# ─────────────────────────────────────────────────────────────────────────────

class TestGuardInterceptor:

    def _ctx(self, object_id, action, params=None, old_data=None):
        return SimpleNamespace(
            meta_object=SimpleNamespace(id=object_id),
            action=action,
            object_id=(params or {}).get('id'),
            params=params or {},
            old_data=old_data,
            extra={},
            data_source=_ds(),
            result=None,
        )

    def test_should_execute_matrix(self):
        it = SalesOrderGuardInterceptor()
        assert it.priority == 49
        assert it.should_execute(self._ctx('sales_order', 'crud_create'))
        assert it.should_execute(self._ctx('sales_order_line', 'crud_delete'))
        assert not it.should_execute(self._ctx('sales_order', 'crud_read'))
        assert not it.should_execute(self._ctx('customer_account', 'crud_create'))

    def test_before_action_converts_to_validation_error(self):
        it = SalesOrderGuardInterceptor()
        ctx = self._ctx('sales_order', 'crud_create',
                        {'order_type_id': 1, 'sales_org_id': 1})
        with pytest.raises(ValidationFailedError) as e:
            it.before_action(ctx)
        assert e.value.details[0]['rule'] == 'sales_org_not_sales'

    def test_before_action_merges_old_data_on_update(self):
        it = SalesOrderGuardInterceptor()
        ctx = self._ctx('sales_order', 'crud_update',
                        {'id': 10, 'status': 'submitted'}, old_data=ORDERS[10])
        it.before_action(ctx)  # 不抛出 = 冻结字段未被误改

    def test_before_action_line_delete_records_parent(self):
        it = SalesOrderGuardInterceptor()
        ctx = self._ctx('sales_order_line', 'crud_delete',
                        {'id': 100}, old_data=LINES[100])
        it.before_action(ctx)
        assert ctx.extra['so_parent_order_id'] == 10

    def test_create_fills_service_line_defaults(self):
        it = SalesOrderGuardInterceptor()
        ctx = self._ctx('sales_order_line', 'crud_create',
                        {'order_id': 10, 'line_no': '1', 'line_type_id': 102,
                         'item_id': 3, 'qty': 1, 'uom_id': 2})
        it.before_action(ctx)
        assert ctx.params['billing_method'] == 'fixed_price'
        assert ctx.params['service_duration'] == 8
        assert ctx.params['duration_type'] == 'hour'

    def test_confirm_update_fills_address_snapshot(self):
        it = SalesOrderGuardInterceptor()
        ctx = self._ctx('sales_order', 'crud_update',
                        {'id': 11, 'status': 'confirmed'}, old_data=ORDERS[11])
        it.before_action(ctx)
        assert ctx.params['ship_to_address_text'] == \
            '上海市浦东新区世纪大道 100 号'
        assert ctx.params['bill_to_address_text'] == \
            '上海市静安区南京西路 200 号'

    def test_create_fills_return_line_defaults(self):
        # E6：创建退货行时按引用行补空字段，且与写入参数同一份
        it = SalesOrderGuardInterceptor()
        ctx = self._ctx('sales_order_line', 'crud_create',
                        {'order_id': 14, 'line_no': '3', 'line_type_id': 103,
                         'reference_line_id': 200, 'qty': 1, 'uom_id': 2,
                         'unit_price': 10})
        it.before_action(ctx)
        assert ctx.params['item_id'] == 2
        assert ctx.params['description'] == '原行描述'
        assert ctx.params['customer_item_code'] == 'C-200'
        assert ctx.params['tax_code_id'] == 7


# ─────────────────────────────────────────────────────────────────────────────
# 类型删除引用保护（验收第 6 条）
# ─────────────────────────────────────────────────────────────────────────────

class TestTypeDefinitionDeleteGuard:

    def test_reject_when_referenced_by_orders(self):
        ds = _ds(refs={'sales_orders': {1: 2}})
        with pytest.raises(TypeDefinitionGuardError) as e:
            TypeDefinitionGuardService(ds).validate_delete(1)
        assert e.value.rule == 'referenced_in_use'
        assert '2 条销售订单' in str(e.value)

    def test_reject_when_referenced_by_lines(self):
        ds = _ds(refs={'sales_order_lines': {101: 3}})
        with pytest.raises(TypeDefinitionGuardError) as e:
            TypeDefinitionGuardService(ds).validate_delete(101)
        assert '3 条销售订单行' in str(e.value)

    def test_reject_when_referenced_as_default_type(self):
        ds = _ds(refs={'type_definitions': {101: 1}})
        with pytest.raises(TypeDefinitionGuardError):
            TypeDefinitionGuardService(ds).validate_delete(101)

    def test_allow_when_unreferenced(self):
        TypeDefinitionGuardService(_ds()).validate_delete(999)

    def test_interceptor_handles_delete(self):
        from meta.core.interceptors.type_definition_guard_interceptor import (
            TypeDefinitionGuardInterceptor,
        )
        it = TypeDefinitionGuardInterceptor()
        assert it.should_execute(SimpleNamespace(
            meta_object=SimpleNamespace(id='type_definition'),
            action='crud_delete'))


# ─────────────────────────────────────────────────────────────────────────────
# E6 退货引用链（R-RET-1 ~ R-RET-9）
# ─────────────────────────────────────────────────────────────────────────────

RETURN_LINE = {'order_id': 14, 'line_no': '1', 'line_type_id': 103,
               'item_id': 2, 'qty': 1, 'uom_id': 2, 'unit_price': 10}

# 累计退货夹具：201 有效（4 件）/ 202 已取消（5 件，不占额度）。
# 不并入全局 LINES，避免「引用 200」的行影响既有的行删除用例。
RETURN_HISTORY = {
    201: {'id': 201, 'order_id': 14, 'line_no': '1', 'line_type_id': 103,
          'reference_line_id': 200, 'item_id': 2, 'qty': 4, 'uom_id': 2,
          'status': 'active'},
    202: {'id': 202, 'order_id': 16, 'line_no': '1', 'line_type_id': 103,
          'reference_line_id': 200, 'item_id': 2, 'qty': 5, 'uom_id': 2,
          'status': 'cancelled'},
}


class TestReturnReference:

    def _guard(self):
        lines = dict(LINES)
        lines.update(RETURN_HISTORY)
        ds = _FakeDS(types=TYPES, orders=ORDERS, lines=lines, items=ITEMS,
                     addresses=ADDRESSES, divisions=DIVISIONS,
                     org_functions={(318, 'sales')})
        return SalesOrderGuardService(ds)

    def test_return_line_with_reference_ok(self):
        self._guard().validate_line_write(
            {**RETURN_LINE, 'reference_line_id': 200}, is_create=True)

    def test_reference_rejected_on_standard_order(self):
        # R-RET-1：非退货单（10 是标准单）
        with pytest.raises(SalesOrderGuardError) as e:
            self._guard().validate_line_write(
                {**RETURN_LINE, 'order_id': 10, 'reference_line_id': 200},
                is_create=True)
        assert e.value.rule == 'return_ref_not_allowed'

    def test_reference_rejected_on_non_return_line(self):
        # R-RET-1：退货单内的非退货行（101 是物料行）
        with pytest.raises(SalesOrderGuardError) as e:
            self._guard().validate_line_write(
                {**RETURN_LINE, 'line_type_id': 101,
                 'reference_line_id': 200}, is_create=True)
        assert e.value.rule == 'return_ref_not_allowed'

    def test_reference_line_not_found(self):
        # R-RET-2：引用行不存在
        with pytest.raises(SalesOrderGuardError) as e:
            self._guard().validate_line_write(
                {**RETURN_LINE, 'reference_line_id': 999}, is_create=True)
        assert e.value.rule == 'return_ref_not_found'

    def test_reference_same_order_rejected(self):
        # R-RET-3：引用本单内的行（300 属于 14）
        with pytest.raises(SalesOrderGuardError) as e:
            self._guard().validate_line_write(
                {**RETURN_LINE, 'reference_line_id': 300}, is_create=True)
        assert e.value.rule == 'return_ref_same_order'

    def test_reference_return_line_rejected(self):
        # R-RET-4：被引用行本身是退货行（201 属于 14）
        with pytest.raises(SalesOrderGuardError) as e:
            self._guard().validate_line_write(
                {**RETURN_LINE, 'order_id': 16,
                 'reference_line_id': 201}, is_create=True)
        assert e.value.rule == 'return_ref_not_return'

    def test_reference_order_not_confirmed(self):
        # R-RET-5：原单（11）仅 submitted
        with pytest.raises(SalesOrderGuardError) as e:
            self._guard().validate_line_write(
                {**RETURN_LINE, 'reference_line_id': 101}, is_create=True)
        assert e.value.rule == 'return_ref_order_not_confirmed'

    def test_reference_customer_mismatch(self):
        # R-RET-6：退货单（15）客户 502 与原单（12）客户 501 不一致
        with pytest.raises(SalesOrderGuardError) as e:
            self._guard().validate_line_write(
                {**RETURN_LINE, 'order_id': 15,
                 'reference_line_id': 200}, is_create=True)
        assert e.value.rule == 'return_ref_customer_mismatch'

    def test_reference_item_mismatch(self):
        # R-RET-7：退货行物料 3 与原行物料 2 不一致
        with pytest.raises(SalesOrderGuardError) as e:
            self._guard().validate_line_write(
                {**RETURN_LINE, 'item_id': 3,
                 'reference_line_id': 200}, is_create=True)
        assert e.value.rule == 'return_ref_item_mismatch'

    def test_reference_qty_exceeded(self):
        # R-RET-8：已退 4 + 本次 2 > 原行 5
        with pytest.raises(SalesOrderGuardError) as e:
            self._guard().validate_line_write(
                {**RETURN_LINE, 'qty': 2, 'reference_line_id': 200},
                is_create=True)
        assert e.value.rule == 'return_qty_exceeded'

    def test_cancelled_return_not_counted(self):
        # R-RET-8：202 已取消不占额度，4 + 1 = 5 恰好等于原行数量
        self._guard().validate_line_write(
            {**RETURN_LINE, 'reference_line_id': 200}, is_create=True)

    def test_no_reference_skips_return_checks(self):
        # R-RET-1：引用为空时整段跳过（标准单物料行照常写入）
        self._guard().validate_line_write(dict(BASE_LINE), is_create=True)

    def test_delete_rejected_when_referenced_by_return(self):
        # R-RET-9：原行被退货行引用时禁止删除
        lines = dict(LINES)
        lines[211] = {'id': 211, 'order_id': 14, 'line_no': '9',
                      'line_type_id': 103, 'reference_line_id': 100}
        ds = _FakeDS(types=TYPES, orders=ORDERS, lines=lines,
                     org_functions={(318, 'sales')})
        with pytest.raises(SalesOrderGuardError) as e:
            SalesOrderGuardService(ds).validate_line_delete(100)
        assert e.value.rule == 'line_has_return_refs'

    def test_defaults_copy_blank_fields(self):
        # E6：只复制空值字段，且不含 qty / unit_price / plant_location_id
        defaults = SalesOrderGuardService(_ds()).return_line_defaults(
            {'reference_line_id': 200})
        assert defaults == {'item_id': 2, 'customer_item_code': 'C-200',
                            'description': '原行描述', 'uom_id': 2,
                            'tax_code_id': 7}
        for field in ('qty', 'unit_price', 'plant_location_id'):
            assert field not in defaults

    def test_defaults_do_not_override_explicit_values(self):
        defaults = SalesOrderGuardService(_ds()).return_line_defaults(
            {'reference_line_id': 200, 'item_id': 3,
             'description': '手工描述'})
        assert 'item_id' not in defaults
        assert 'description' not in defaults
        assert defaults['customer_item_code'] == 'C-200'

    def test_defaults_empty_without_reference(self):
        assert SalesOrderGuardService(_ds()).return_line_defaults({}) == {}

    def test_defaults_empty_when_reference_missing(self):
        assert SalesOrderGuardService(_ds()).return_line_defaults(
            {'reference_line_id': 999}) == {}
