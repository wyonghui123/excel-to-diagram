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
                 org_functions=None, refs=None, raise_on_query=False):
        self.types = types or {}
        self.orders = orders or {}
        self.lines = lines or {}
        self.org_functions = org_functions or set()
        self.refs = refs or {}
        self.raise_on_query = raise_on_query

    def query(self, sql, params=None):
        if self.raise_on_query:
            raise RuntimeError('db down')
        p = list(params or [])

        if 'FROM type_definitions WHERE id' in sql:
            row = self.types.get(p[0])
            return [row] if row else []
        if 'FROM sales_orders WHERE id' in sql:
            row = self.orders.get(p[0])
            return [row] if row else []
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
         'sales_org_id': 318, 'org_id': 318, 'order_date': '2026-10-25'},
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


def _ds(**kwargs):
    return _FakeDS(types=TYPES, orders=ORDERS, lines=LINES,
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
