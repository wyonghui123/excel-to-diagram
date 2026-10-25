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
                 addresses=None, raise_on_query=False):
        self.types = types or {}
        self.orders = orders or {}
        self.lines = lines or {}
        self.org_functions = org_functions or set()
        self.refs = refs or {}
        self.items = items or {}
        self.addresses = addresses or {}
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
        if 'FROM sales_orders WHERE id' in sql:
            row = self.orders.get(p[0])
            return [row] if row else []
        if 'FROM sales_order_lines WHERE parent_line_id' in sql:
            hit = any(str(v.get('parent_line_id')) == str(p[0])
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
          'document_category': None},
    102: {'id': 102, 'code': 'SVC', 'scope_bo': 'sales_order', 'level': 'line',
          'document_category': None},
}

ORDERS = {
    10: {'id': 10, 'order_no': 'SO-202610-000001', 'order_type_id': 1,
         'status': 'draft', 'currency_id': 8, 'exchange_rate': 1,
         'sales_org_id': 318, 'org_id': 318, 'order_date': '2026-10-25'},
    11: {'id': 11, 'order_no': 'SO-202610-000002', 'order_type_id': 1,
         'status': 'submitted', 'currency_id': 8, 'exchange_rate': 1,
         'sales_org_id': 318, 'org_id': 318, 'order_date': '2026-10-25',
         'ship_to_address_id': 301, 'bill_to_address_id': 302},
    12: {'id': 12, 'order_no': 'SO-202610-000003', 'order_type_id': 1,
         'status': 'confirmed', 'currency_id': 8, 'exchange_rate': 1,
         'sales_org_id': 318, 'org_id': 318, 'order_date': '2026-10-25'},
    13: {'id': 13, 'order_no': 'SO-202610-000004', 'order_type_id': 5,
         'status': 'draft', 'currency_id': 8, 'exchange_rate': 1,
         'sales_org_id': 318, 'org_id': 318, 'order_date': '2026-10-25'},
}

LINES = {
    100: {'id': 100, 'order_id': 10, 'line_no': '1', 'line_type_id': 101},
    101: {'id': 101, 'order_id': 11, 'line_no': '1', 'line_type_id': 101},
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


def _ds(**kwargs):
    return _FakeDS(types=TYPES, orders=ORDERS, lines=LINES, items=ITEMS,
                   addresses=ADDRESSES,
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
