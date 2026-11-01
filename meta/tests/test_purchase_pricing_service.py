# -*- coding: utf-8 -*-
"""采购取价服务断言（M3 / spec §4.3 / §4.4 / §14 冒烟 4-bullet7）

依据 `docs/specs/spec-purchase-order-object-model-2026-11-01.md` §4.3 / §4.4。
口径：协议阶梯（1-99 件 / 100+）命中后行写 price_source='agreement' 与单价、
头写 price_list_id；本地协议不匹配时回落全局；无来源回落 manual 且无 trace；
多档同时覆盖本次数量且未配 price_break_cumulative → 直接报错，不猜。

不依赖真实 DB：`PurchasePricingService` 已把 `_query / _load_* / _write_*` 拆成
可覆写钩子，本文件用内存替身注入 rate_tables / rate_records / 协议评定。
"""

import json

import pytest

from meta.services.purchase_pricing_service import (
    PurchasePricingError,
    PurchasePricingService,
    SOURCE_AGREEMENT,
    SOURCE_MANUAL,
)

pytestmark = pytest.mark.unit


def _record(record_id, rate, qty_from=None, qty_to=None, item_id=101,
            currency='CNY'):
    return {
        'id': record_id,
        'code': 'R%d' % record_id,
        'keys': {'item_id': item_id},
        'rate': rate,
        'rate_qty': 1,
        'currency': currency,
        'priority': 0,
        'qty_from': qty_from,
        'qty_to': qty_to,
        'ship_to_location_id': None,
        'valid_from': None,
        'valid_to': None,
    }


def _table(table_id, code, table_type, scope_bo='purchase_order',
           status='approved'):
    return {
        'id': table_id,
        'code': code,
        'name': code,
        'type': table_type,
        'currency': 'CNY',
        'owner_org_id': None,
        'scope_bo': scope_bo,
        'status': status,
    }


def _determination(det_id, scope, table_id, org_id=7):
    return {
        'id': det_id,
        'code': 'D%d' % det_id,
        'seq': 0,
        'rate_table_id': table_id,
        'purchase_org_id': org_id,
        'document_type_id': None,
        'supplier_party_id': None,
        'base_date_from': None,
        'base_date_to': None,
        'status': 'active',
        'agreement_scope': scope,
    }


class _FakePricingService(PurchasePricingService):
    """内存替身：只实现取价链路用到的查询，写入落到 self.writes。"""

    def __init__(self, line, order, tables=None, records=None,
                 determinations=None, currency_code='CNY'):
        super().__init__(None)
        self.line = dict(line)
        self.order = dict(order)
        self.tables = tables or []
        self.records = records or []
        self.determinations = determinations or []
        self.currency_code = currency_code
        self.writes = {'line': {}, 'order': {}}

    # ---- 查询替身 ----
    def _query(self, sql, params=None):
        params = params or []
        if 'FROM purchase_pricing_determinations' in sql:
            scope = params[0] if params else None
            rows = [d for d in self.determinations
                    if d['status'] == 'active' and d['agreement_scope'] == scope]
            rows.sort(key=lambda d: (
                d['supplier_party_id'] is not None,
                d['purchase_org_id'] is not None,
                -d['seq'], -d['id']))
            return rows
        if 'FROM rate_tables' in sql:
            rows = [t for t in self.tables
                    if t['status'] == 'approved' and t['scope_bo'] == 'purchase_order']
            if 'NOT IN' in sql:
                rows = [t for t in rows if (t['type'] or 'standard') not in
                        ('quotation', 'quote', 'agreement', 'bpa', 'contract')]
            else:
                rows = [t for t in rows if (t['type'] or 'standard')
                        in ('quotation', 'quote')]
            return rows
        if 'FROM rate_records' in sql:
            table_id = params[0]
            return [r for r in self.records if r.get('_table_id') == table_id]
        if 'JOIN purchase_orders o' in sql:
            return []  # last_po / 累计数量：本用例无历史已确认单
        if 'FROM purchase_order_lines WHERE id' in sql:
            return [self.line] if params and params[0] == self.line['id'] else []
        if 'FROM purchase_orders WHERE id' in sql:
            return [self.order] if params and params[0] == self.order['id'] else []
        if 'FROM currencies' in sql:
            return [{'code': self.currency_code}] if self.currency_code else []
        raise AssertionError('未覆盖的查询: %s' % sql)

    def _load_line(self, line_id):
        return dict(self.line)

    def _load_order(self, order_id):
        return dict(self.order)

    def _price_break_cumulative(self):
        return None  # 未配置控制参数 → 由单调档位决定，多档覆盖即报错

    # ---- 写入替身 ----
    def _write_line(self, line_id, values):
        self.writes['line'].update(values)

    def _write_order(self, order_id, values):
        self.writes['order'].update(values)


def _order(qty_currency_id=1):
    return {
        'id': 9001,
        'order_no': 'PO-TEST-1',
        'status': 'draft',
        'order_date': '2026-11-01',
        'price_date': '2026-11-01',
        'currency_id': qty_currency_id,
        'supplier_party_id': 501,
        'purchase_org_id': 7,
        'document_type_id': 31,
        'deliver_to_location_id': None,
    }


def _line(qty, unit_price=None, price_source='manual'):
    return {
        'id': 9101,
        'order_id': 9001,
        'item_id': 101,
        'qty': qty,
        'uom_id': 1,
        'unit_price': unit_price,
        'price_source': price_source,
        'deliver_to_location_id': None,
    }


def _tier_agreement(scope='local', table_id=601):
    """1-99 件 ¥10 / 100 件以上 ¥9 的协议阶梯。"""
    records = [
        dict(_record(1, 10, qty_from=1, qty_to=99), _table_id=table_id),
        dict(_record(2, 9, qty_from=100), _table_id=table_id),
    ]
    return ([_table(table_id, 'AG-%s' % scope, 'agreement')], records,
            [_determination(701, scope, table_id)])


def _run(qty, scope='local'):
    tables, records, determinations = _tier_agreement(scope=scope)
    svc = _FakePricingService(_line(qty), _order(),
                              tables=tables, records=records,
                              determinations=determinations)
    result = svc.price_line(9101, force=True)
    return svc, result


def test_tier_low_band_hits_agreement_price():
    svc, result = _run(50)
    assert result['price_source'] == SOURCE_AGREEMENT
    assert result['unit_price'] == 10.0
    assert svc.writes['order']['price_list_id'] == 601
    assert svc.writes['line']['price_source'] == SOURCE_AGREEMENT
    trace = json.loads(svc.writes['line']['price_trace'])
    assert trace['price_break_cumulative'] is False
    assert trace['result']['scope'] == 'local'


def test_tier_high_band_hits_agreement_price():
    svc, result = _run(150)
    assert result['unit_price'] == 9.0
    assert json.loads(svc.writes['line']['price_trace'])['result']['scope'] == 'local'


def test_tier_boundary_belongs_to_higher_band():
    _svc, result = _run(100)
    assert result['unit_price'] == 9.0


def test_local_miss_falls_back_to_global_agreement():
    tables = [_table(601, 'AG-local', 'agreement'),
              _table(602, 'AG-global', 'agreement')]
    records = [
        dict(_record(1, 12, qty_from=1, item_id=999), _table_id=601),
        dict(_record(2, 11, qty_from=1), _table_id=602),
    ]
    determinations = [_determination(701, 'local', 601),
                      _determination(702, 'global', 602)]
    svc = _FakePricingService(_line(10), _order(), tables=tables,
                              records=records, determinations=determinations)
    result = svc.price_line(9101, force=True)
    assert result['price_source'] == SOURCE_AGREEMENT
    assert result['unit_price'] == 11.0
    assert json.loads(svc.writes['line']['price_trace'])['result']['scope'] == 'global'


def test_overlapping_bands_raise_instead_of_guessing():
    table_id = 603
    records = [
        dict(_record(1, 10, qty_from=1), _table_id=table_id),
        dict(_record(2, 9, qty_from=100), _table_id=table_id),
    ]
    svc = _FakePricingService(_line(150), _order(),
                              tables=[_table(table_id, 'AG-x', 'agreement')],
                              records=records,
                              determinations=[_determination(701, 'local', table_id)])
    with pytest.raises(PurchasePricingError) as exc:
        svc.price_line(9101, force=True)
    assert exc.value.rule == 'price_break_cumulative_missing'
    assert exc.value.field_name == 'price_break_cumulative'


def test_no_source_falls_back_to_manual_without_trace():
    svc = _FakePricingService(_line(10), _order())
    result = svc.price_line(9101, force=True)
    assert result['price_source'] == SOURCE_MANUAL
    assert svc.writes['line']['price_trace'] is None
