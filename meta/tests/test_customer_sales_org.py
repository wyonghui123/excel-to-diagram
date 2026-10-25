# -*- coding: utf-8 -*-
"""客户销售组织（W1-B）：逐字段回退解析 / 销售职能守卫 / 抬头变更重算

依据: docs/superpowers/specs/2026-10-25-sales-order-wave1-detailed-plan.md
      §4.3 解析链 / §4.5 W1-R11 / §4.6 验收

覆盖:
  1. `CustomerSalesOrgService.resolve` —— 组织差异覆盖、字段级回退、
     停用行忽略、零配置零回归、fail-open
  2. `CustomerSalesOrgGuardService.validate_write` —— W1-R11 销售职能
  3. 守卫拦截器（P49）—— 可实例化、作用域收窄、更新时合并旧行
  4. `bo_api._reapply_sales_order_defaults` —— 客户/组织变更时重算，
     用户手改值不覆盖

测试数据经 `meta/tests/factories/_customer_sales_org_helpers.py`
（conftest 的裸 SQL 门控白名单目录），本文件不含裸 SQL DML。
"""
import inspect
import sqlite3
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

from meta.api import bo_api
from meta.services.customer_sales_org_guard_service import (
    CustomerSalesOrgGuardError,
    CustomerSalesOrgGuardService,
)
from meta.services.customer_sales_org_service import CustomerSalesOrgService
from meta.tests.factories._customer_sales_org_helpers import (
    SqliteDS,
    create_tables,
    seed_account,
    seed_org_function,
    seed_order,
    seed_override,
)


@pytest.fixture()
def conn():
    c = sqlite3.connect(':memory:')
    create_tables(c)
    yield c
    c.close()


@pytest.fixture()
def ds(conn):
    return SqliteDS(conn)


# ── 1. 解析服务 ──

class TestResolve:
    """`resolve` 的输出只含非空字段；逐字段回退，不整行覆盖（W1-R10）。"""

    def test_override_wins_over_account(self, ds, conn):
        seed_account(conn, default_payment_term_id=1,
                     default_incoterm_code='EXW')
        seed_override(conn, payment_term_id=2, incoterm_code='FOB')

        out = CustomerSalesOrgService(ds).resolve(1, 318)
        assert out['payment_term_id'] == 2
        assert out['incoterm_code'] == 'FOB'

    def test_blank_override_field_falls_back(self, ds, conn):
        seed_account(conn, default_payment_term_id=1,
                     default_incoterm_code='EXW')
        seed_override(conn, payment_term_id=2, incoterm_code=None)

        out = CustomerSalesOrgService(ds).resolve(1, 318)
        assert out['payment_term_id'] == 2
        assert out['incoterm_code'] == 'EXW'

    def test_no_override_row_is_zero_regression(self, ds, conn):
        seed_account(conn, default_payment_term_id=1,
                     default_incoterm_code='EXW',
                     tax_classification_id=5)

        out = CustomerSalesOrgService(ds).resolve(1, 999)
        assert out == {'payment_term_id': 1, 'incoterm_code': 'EXW',
                       'tax_classification_id': 5}

    def test_inactive_override_ignored(self, ds, conn):
        seed_account(conn, default_payment_term_id=1)
        seed_override(conn, payment_term_id=2, status='inactive')

        out = CustomerSalesOrgService(ds).resolve(1, 318)
        assert out['payment_term_id'] == 1

    def test_tax_classification_falls_back_to_account(self, ds, conn):
        seed_account(conn, tax_classification_id=5)
        seed_override(conn, payment_term_id=2)

        out = CustomerSalesOrgService(ds).resolve(1, 318)
        assert out['tax_classification_id'] == 5

    def test_currency_only_from_override(self, ds, conn):
        seed_account(conn, default_payment_term_id=1)
        seed_override(conn, currency_id=8)

        service = CustomerSalesOrgService(ds)
        assert service.resolve(1, 318).get('currency_id') == 8
        # 账户级无币种来源 → 未配置组织行时不输出该字段
        assert 'currency_id' not in service.resolve(1, 999)

    def test_only_order_fields(self, ds, conn):
        seed_account(conn, tax_classification_id=5)
        seed_override(conn, payment_term_id=2, currency_id=8)

        out = CustomerSalesOrgService(ds).resolve(
            1, 318, fields=('payment_term_id', 'incoterm_code'))
        assert set(out) == {'payment_term_id'}

    def test_blank_customer_returns_empty(self, ds):
        assert CustomerSalesOrgService(ds).resolve(None, 318) == {}
        assert CustomerSalesOrgService(ds).resolve('', 318) == {}

    def test_blank_sales_org_skips_override(self, ds, conn):
        seed_account(conn, default_payment_term_id=1)
        seed_override(conn, payment_term_id=2)

        out = CustomerSalesOrgService(ds).resolve(1, None)
        assert out['payment_term_id'] == 1

    def test_query_error_fails_open(self):
        class _Broken:
            def query(self, sql, params=None):
                raise RuntimeError('db down')

        assert CustomerSalesOrgService(_Broken()).resolve(1, 318) == {}


# ── 2. 守卫服务（W1-R11） ──

class TestGuard:
    """`sales_org_id` 必须具备 sales 职能；查询失败 fail-open。"""

    def test_sales_function_passes(self, ds, conn):
        seed_org_function(conn, 318, 'sales')
        CustomerSalesOrgGuardService(ds).validate_write({'sales_org_id': 318})

    def test_missing_org_skips(self, ds):
        # 缺字段交给必填校验，不在此处报错
        CustomerSalesOrgGuardService(ds).validate_write({})
        CustomerSalesOrgGuardService(ds).validate_write({'sales_org_id': None})

    def test_non_sales_function_rejected(self, ds, conn):
        seed_org_function(conn, 318, 'purchase')
        with pytest.raises(CustomerSalesOrgGuardError) as exc:
            CustomerSalesOrgGuardService(ds).validate_write({'sales_org_id': 318})
        assert exc.value.rule == 'sales_org_not_sales'
        assert exc.value.field_name == 'sales_org_id'
        assert '不具备销售职能' in str(exc.value)

    def test_org_without_any_function_rejected(self, ds):
        with pytest.raises(CustomerSalesOrgGuardError):
            CustomerSalesOrgGuardService(ds).validate_write({'sales_org_id': 777})

    def test_query_error_fails_open(self):
        class _Broken:
            def query(self, sql, params=None):
                raise RuntimeError('db down')

        CustomerSalesOrgGuardService(_Broken()).validate_write({'sales_org_id': 318})


# ── 3. 拦截器接线（P49） ──

class TestInterceptor:
    """拦截器可实例化（抽象方法齐全）+ 只对 customer_sales_org 写动作生效。"""

    def test_interceptor_is_concrete(self):
        from meta.core.interceptors.customer_sales_org_guard_interceptor import (
            CustomerSalesOrgGuardInterceptor,
        )
        assert not inspect.isabstract(CustomerSalesOrgGuardInterceptor)
        assert CustomerSalesOrgGuardInterceptor().priority == 49

    def _ctx(self, ds, object_id='customer_sales_org',
             action='crud_create', params=None, old_data=None):
        return SimpleNamespace(
            meta_object=SimpleNamespace(id=object_id),
            action=action, params=params or {}, old_data=old_data or {},
            data_source=ds)

    def test_should_execute_scope(self, ds):
        from meta.core.interceptors.customer_sales_org_guard_interceptor import (
            CustomerSalesOrgGuardInterceptor,
        )
        interceptor = CustomerSalesOrgGuardInterceptor()
        assert interceptor.should_execute(self._ctx(ds)) is True
        assert interceptor.should_execute(
            self._ctx(ds, action='crud_read')) is False
        assert interceptor.should_execute(
            self._ctx(ds, object_id='customer_account')) is False

    def test_before_action_rejects_non_sales_org(self, ds, conn):
        from meta.core.exceptions import ValidationFailedError
        from meta.core.interceptors.customer_sales_org_guard_interceptor import (
            CustomerSalesOrgGuardInterceptor,
        )
        seed_org_function(conn, 318, 'purchase')

        with pytest.raises(ValidationFailedError) as exc:
            CustomerSalesOrgGuardInterceptor().before_action(
                self._ctx(ds, params={'sales_org_id': 318}))
        assert exc.value.details[0]['rule'] == 'sales_org_not_sales'

    def test_before_action_update_merges_old_row(self, ds, conn):
        from meta.core.interceptors.customer_sales_org_guard_interceptor import (
            CustomerSalesOrgGuardInterceptor,
        )
        seed_org_function(conn, 318, 'purchase')

        # 更新只带 description：旧行的 sales_org_id 仍需校验
        ctx = self._ctx(ds, action='crud_update',
                        params={'description': 'x'},
                        old_data={'customer_account_id': 1, 'sales_org_id': 318})
        from meta.core.exceptions import ValidationFailedError
        with pytest.raises(ValidationFailedError):
            CustomerSalesOrgGuardInterceptor().before_action(ctx)


# ── 4. 抬头变更重算（bo_api） ──

class _OrderDS:
    """按 SQL 形态返回订单现值 / 组织差异 / 账户默认；差异行按销售组织区分。"""

    def __init__(self, order=None, overrides=None, account=None):
        self.order = order
        self.overrides = overrides or {}
        self.account = account

    def query(self, sql, params=None):
        if 'FROM sales_orders' in sql:
            return [self.order] if self.order else []
        if 'FROM customer_sales_orgs' in sql:
            row = self.overrides.get(params[1])
            return [row] if row else []
        if 'FROM customer_accounts' in sql:
            return [self.account] if self.account else []
        raise AssertionError('unexpected sql: %s' % sql)


ACC = {'default_payment_term_id': 1, 'default_incoterm_code': 'EXW'}


def _install(monkeypatch, fake):
    monkeypatch.setattr(bo_api, '_get_data_source', lambda: fake)


class TestReapply:
    """仅当「未显式给值 + 现值仍是旧解析结果」时改写（用户手改值不覆盖）。"""

    def test_org_change_applies_new_override(self, monkeypatch):
        fake = _OrderDS(
            order={'customer_account_id': 1, 'sales_org_id': 318,
                   'order_type_id': 1, 'payment_term_id': 1,
                   'incoterm_code': 'EXW'},
            overrides={320: {'payment_term_id': 2, 'incoterm_code': 'FOB'}},
            account=ACC)
        _install(monkeypatch, fake)

        out = bo_api._reapply_sales_order_defaults(
            'sales_order', 11, {'sales_org_id': 320})
        assert out['payment_term_id'] == 2
        assert out['incoterm_code'] == 'FOB'

    def test_org_change_falls_back_to_account(self, monkeypatch):
        fake = _OrderDS(
            order={'customer_account_id': 1, 'sales_org_id': 318,
                   'order_type_id': 1, 'payment_term_id': 2,
                   'incoterm_code': 'FOB'},
            overrides={318: {'payment_term_id': 2, 'incoterm_code': 'FOB'}},
            account=ACC)
        _install(monkeypatch, fake)

        out = bo_api._reapply_sales_order_defaults(
            'sales_order', 11, {'sales_org_id': 320})
        assert out['payment_term_id'] == 1
        assert out['incoterm_code'] == 'EXW'

    def test_manual_value_not_overwritten(self, monkeypatch):
        fake = _OrderDS(
            order={'customer_account_id': 1, 'sales_org_id': 318,
                   'order_type_id': 1, 'payment_term_id': 99,
                   'incoterm_code': 'EXW'},
            overrides={320: {'payment_term_id': 2, 'incoterm_code': 'FOB'}},
            account=ACC)
        _install(monkeypatch, fake)

        out = bo_api._reapply_sales_order_defaults(
            'sales_order', 11, {'sales_org_id': 320})
        assert 'payment_term_id' not in out  # 手改的 99 保持
        assert out['incoterm_code'] == 'FOB'

    def test_explicit_payload_value_wins(self, monkeypatch):
        fake = _OrderDS(
            order={'customer_account_id': 1, 'sales_org_id': 318,
                   'order_type_id': 1, 'payment_term_id': 1,
                   'incoterm_code': 'EXW'},
            overrides={320: {'payment_term_id': 2, 'incoterm_code': 'FOB'}},
            account=ACC)
        _install(monkeypatch, fake)

        out = bo_api._reapply_sales_order_defaults(
            'sales_order', 11,
            {'sales_org_id': 320, 'payment_term_id': 5, 'incoterm_code': ''})
        assert out['payment_term_id'] == 5
        assert out['incoterm_code'] == ''  # 显式清空也不覆盖

    def test_unchanged_party_returns_as_is(self, monkeypatch):
        fake = _OrderDS(
            order={'customer_account_id': 1, 'sales_org_id': 318,
                   'order_type_id': 1, 'payment_term_id': 1,
                   'incoterm_code': 'EXW'},
            overrides={318: {'payment_term_id': 2, 'incoterm_code': 'FOB'}},
            account=ACC)
        _install(monkeypatch, fake)

        data = {'sales_org_id': 318, 'note': 'x'}
        out = bo_api._reapply_sales_order_defaults('sales_order', 11, data)
        assert out == data

    def test_unrelated_update_untouched(self, monkeypatch):
        def _boom():
            raise AssertionError('不应查询数据源')

        monkeypatch.setattr(bo_api, '_get_data_source', _boom)
        data = {'note': 'x'}
        out = bo_api._reapply_sales_order_defaults('sales_order', 11, data)
        assert out == data

    def test_other_object_untouched(self):
        data = {'sales_org_id': 320}
        assert bo_api._reapply_sales_order_defaults(
            'customer_sales_org', 1, data) is data

    def test_order_not_found_returns_as_is(self, monkeypatch):
        fake = _OrderDS(order=None, account=ACC)
        _install(monkeypatch, fake)
        data = {'sales_org_id': 320}
        assert bo_api._reapply_sales_order_defaults(
            'sales_order', 999, data) == data

    def test_query_error_returns_as_is(self, monkeypatch):
        class _Broken:
            def query(self, sql, params=None):
                raise RuntimeError('db down')

        _install(monkeypatch, _Broken())
        data = {'sales_org_id': 320}
        assert bo_api._reapply_sales_order_defaults(
            'sales_order', 11, data) == data

    def test_empty_result_uses_control_parameter(self, monkeypatch):
        from meta.services import control_parameter_service as cps

        fake = _OrderDS(
            order={'customer_account_id': 1, 'sales_org_id': 318,
                   'order_type_id': 1, 'payment_term_id': 1,
                   'incoterm_code': 'EXW'},
            overrides={318: {'payment_term_id': 1, 'incoterm_code': 'EXW'}},
            account=None)
        _install(monkeypatch, fake)

        class _Resolver:
            def resolve_many(self, codes, dims, domain=None):
                return {'default_payment_term': 7, 'default_incoterm': 'CPT'}

        monkeypatch.setattr(cps, 'get_control_parameter_resolver',
                            lambda: _Resolver())

        out = bo_api._reapply_sales_order_defaults(
            'sales_order', 11, {'sales_org_id': 320})
        assert out['payment_term_id'] == 7
        assert out['incoterm_code'] == 'CPT'

    def test_empty_result_clears_when_nothing_left(self, monkeypatch):
        from meta.services import control_parameter_service as cps

        fake = _OrderDS(
            order={'customer_account_id': 1, 'sales_org_id': 318,
                   'order_type_id': 1, 'payment_term_id': 1,
                   'incoterm_code': 'EXW'},
            overrides={318: {'payment_term_id': 1, 'incoterm_code': 'EXW'}},
            account=None)
        _install(monkeypatch, fake)

        class _Resolver:
            def resolve_many(self, codes, dims, domain=None):
                return {}

        monkeypatch.setattr(cps, 'get_control_parameter_resolver',
                            lambda: _Resolver())

        out = bo_api._reapply_sales_order_defaults(
            'sales_order', 11, {'sales_org_id': 320})
        assert out['payment_term_id'] is None
        assert out['incoterm_code'] is None
