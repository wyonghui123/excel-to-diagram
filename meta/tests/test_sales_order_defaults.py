# -*- coding: utf-8 -*-
"""销售订单商务默认值解析测试（§2.4 账户默认 → 控制参数 → 留空）"""

import pytest

pytestmark = pytest.mark.unit

from meta.api import bo_api


class _FakeDS:
    def __init__(self, account=None):
        self.account = account or {}
        self.queries = []

    def query(self, sql, params=None):
        self.queries.append((sql, params))
        if 'FROM customer_sales_orgs' in sql:
            return []          # 未配置组织差异 = 沿用账户级（零回归）
        if 'FROM customer_accounts' in sql:
            return [self.account] if self.account else []
        raise AssertionError('unexpected sql: %s' % sql)


class _FakeResolver:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def resolve_many(self, codes, dims, domain=None):
        self.calls.append((list(codes), dict(dims), domain))
        return {code: self.mapping.get(code) for code in codes}


BASE = {
    'order_type_id': 1,
    'order_date': '2026-10-25',
    'customer_account_id': 4,
    'org_id': 318,
    'sales_org_id': 318,
    'currency_id': 8,
    'exchange_rate': 1,
}


@pytest.fixture()
def ds(monkeypatch):
    from meta.api import bo_api as mod
    fake = _FakeDS(account={'default_payment_term_id': 1,
                            'default_incoterm_code': 'EXW'})
    monkeypatch.setattr(mod, '_get_data_source', lambda: fake)
    return fake


class TestSalesOrderDefaults:

    def test_account_defaults_fill_blank_fields(self, ds):
        out = bo_api._apply_sales_order_defaults('sales_order', dict(BASE))
        assert out['payment_term_id'] == 1
        assert out['incoterm_code'] == 'EXW'

    def test_explicit_values_are_not_overridden(self, ds):
        data = dict(BASE, payment_term_id=99, incoterm_code='FOB')
        out = bo_api._apply_sales_order_defaults('sales_order', data)
        assert out['payment_term_id'] == 99
        assert out['incoterm_code'] == 'FOB'

    def test_control_parameter_fallback(self, monkeypatch):
        from meta.services import control_parameter_service as cps
        fake = _FakeDS(account={})
        monkeypatch.setattr(bo_api, '_get_data_source', lambda: fake)
        resolver = _FakeResolver({'default_payment_term': 7,
                                  'default_incoterm': 'CPT'})
        monkeypatch.setattr(cps, 'get_control_parameter_resolver', lambda: resolver)

        out = bo_api._apply_sales_order_defaults('sales_order', dict(BASE))
        assert out['payment_term_id'] == 7
        assert out['incoterm_code'] == 'CPT'
        codes, dims, domain = resolver.calls[0]
        assert codes == ['default_payment_term', 'default_incoterm']
        assert dims == {'org_id': 318, 'document_type_id': 1}
        assert domain == 'sales'

    def test_control_parameter_left_blank(self, monkeypatch):
        from meta.services import control_parameter_service as cps
        monkeypatch.setattr(bo_api, '_get_data_source', lambda: _FakeDS(account={}))
        monkeypatch.setattr(
            cps, 'get_control_parameter_resolver',
            lambda: _FakeResolver({}))
        out = bo_api._apply_sales_order_defaults('sales_order', dict(BASE))
        assert out.get('payment_term_id') is None
        assert out.get('incoterm_code') is None

    def test_other_objects_untouched(self):
        data = {'foo': 1}
        assert bo_api._apply_sales_order_defaults('customer_account', data) is data
