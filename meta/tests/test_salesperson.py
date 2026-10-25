# -*- coding: utf-8 -*-
"""销售员默认值解析与订单接线（W1-D）

依据: docs/superpowers/specs/2026-10-25-sales-order-wave1-detailed-plan.md §6.3 / §6.5

【本文件守什么】
  1. 解析链：组织专属主销售员 → 通用主销售员 → NULL（W1-R16 / W1-R17）
  2. 有效期：valid_from（含）~ valid_to（不含）；price_date 为空时忽略窗口
  3. 创建时只补空白字段，显式给值不覆盖
  4. 抬头变更重算：库中现值 == 变更前解析结果才改写（W1-R18，用户手选不动）
  5. 读侧异常一律 fail-open（不阻断保存）

测试隔离：内存 SQLite 最小表结构 + factories 播种；本文件不含裸 SQL DML。
"""
import sqlite3

import pytest

from meta.api import bo_api
from meta.services.salesperson_service import SalespersonService
from meta.tests.factories._salesperson_helpers import (
    SqliteDS,
    create_tables,
    seed_assignment,
    seed_order,
    seed_salesperson,
)

pytestmark = pytest.mark.unit


class _RaisingDS:
    def query(self, sql, params=None):
        raise RuntimeError('db down')


class _CountingDS(SqliteDS):
    def __init__(self, conn):
        super().__init__(conn)
        self.calls = 0

    def query(self, sql, params=None):
        self.calls += 1
        return super().query(sql, params)


@pytest.fixture()
def conn():
    c = sqlite3.connect(':memory:')
    create_tables(c)
    yield c
    c.close()


def _install(monkeypatch, ds):
    monkeypatch.setattr(bo_api, '_get_data_source', lambda: ds)


class TestResolve:

    def test_org_specific_primary(self, conn):
        seed_salesperson(conn, code='SP001', name='张三')
        seed_assignment(conn, customer_account_id=1, sales_org_id=318,
                        salesperson_id=1)
        assert SalespersonService(SqliteDS(conn)).resolve(1, 318, '2026-10-25') == 1

    def test_fallback_all_org(self, conn):
        seed_salesperson(conn, code='SP001', name='张三')
        seed_assignment(conn, customer_account_id=1, sales_org_id=None,
                        salesperson_id=1)
        assert SalespersonService(SqliteDS(conn)).resolve(1, 318, '2026-10-25') == 1

    def test_org_specific_preferred_over_generic(self, conn):
        seed_salesperson(conn, code='SP001', name='张三')
        seed_salesperson(conn, code='SP002', name='李四')
        seed_assignment(conn, customer_account_id=1, sales_org_id=None,
                        salesperson_id=2)
        seed_assignment(conn, customer_account_id=1, sales_org_id=318,
                        salesperson_id=1)
        svc = SalespersonService(SqliteDS(conn))
        assert svc.resolve(1, 318, '2026-10-25') == 1
        assert svc.resolve(1, 999, '2026-10-25') == 2

    def test_inactive_salesperson_ignored(self, conn):
        seed_salesperson(conn, status='inactive')
        seed_assignment(conn, customer_account_id=1, salesperson_id=1)
        assert SalespersonService(SqliteDS(conn)).resolve(1, 318) is None

    def test_inactive_assignment_ignored(self, conn):
        seed_salesperson(conn)
        seed_assignment(conn, customer_account_id=1, status='inactive')
        assert SalespersonService(SqliteDS(conn)).resolve(1, 318) is None

    def test_non_primary_ignored(self, conn):
        seed_salesperson(conn)
        seed_assignment(conn, customer_account_id=1, is_primary=0)
        assert SalespersonService(SqliteDS(conn)).resolve(1, 318) is None

    def test_date_window_inclusive_start_exclusive_end(self, conn):
        seed_salesperson(conn)
        seed_assignment(conn, customer_account_id=1,
                        valid_from='2026-01-01', valid_to='2026-06-01')
        svc = SalespersonService(SqliteDS(conn))
        assert svc.resolve(1, 318, '2026-03-01') == 1
        assert svc.resolve(1, 318, '2025-12-31') is None
        assert svc.resolve(1, 318, '2026-06-01') is None

    def test_blank_price_date_ignores_window(self, conn):
        seed_salesperson(conn)
        seed_assignment(conn, customer_account_id=1,
                        valid_from='2026-01-01', valid_to='2026-06-01')
        assert SalespersonService(SqliteDS(conn)).resolve(1, 318, None) == 1

    def test_blank_customer_skips_query(self, conn):
        ds = _CountingDS(conn)
        assert SalespersonService(ds).resolve(None, 318) is None
        assert ds.calls == 0

    def test_query_error_fails_open(self):
        assert SalespersonService(_RaisingDS()).resolve(1, 318) is None


class TestCreate:

    def test_blank_filled(self, conn, monkeypatch):
        seed_salesperson(conn)
        seed_assignment(conn, customer_account_id=1, salesperson_id=1)
        _install(monkeypatch, SqliteDS(conn))
        payload = {'customer_account_id': 1, 'sales_org_id': 318}
        out = bo_api._apply_sales_order_salesperson('sales_order', payload)
        assert out['salesperson_id'] == 1

    def test_explicit_value_kept_without_query(self, monkeypatch):
        _install(monkeypatch, _RaisingDS())
        payload = {'customer_account_id': 1, 'sales_org_id': 318,
                   'salesperson_id': 99}
        out = bo_api._apply_sales_order_salesperson('sales_order', payload)
        assert out['salesperson_id'] == 99

    def test_other_object_untouched(self, monkeypatch):
        _install(monkeypatch, _RaisingDS())
        payload = {'customer_account_id': 1, 'sales_org_id': 318}
        out = bo_api._apply_sales_order_salesperson('customer_account', payload)
        assert 'salesperson_id' not in out

    def test_query_error_does_not_block(self, monkeypatch):
        _install(monkeypatch, _RaisingDS())
        payload = {'customer_account_id': 1, 'sales_org_id': 318}
        out = bo_api._apply_sales_order_salesperson('sales_order', payload)
        assert 'salesperson_id' not in out


class TestReapply:

    def test_customer_change_switches(self, conn, monkeypatch):
        seed_salesperson(conn, code='SP001', name='张三')
        seed_salesperson(conn, code='SP002', name='李四')
        seed_assignment(conn, customer_account_id=1, salesperson_id=1)
        seed_assignment(conn, customer_account_id=2, salesperson_id=2)
        seed_order(conn, customer_account_id=1, salesperson_id=1)
        _install(monkeypatch, SqliteDS(conn))
        out = bo_api._reapply_sales_order_salesperson(
            'sales_order', 1, {'customer_account_id': 2})
        assert out['salesperson_id'] == 2

    def test_new_customer_without_primary_clears(self, conn, monkeypatch):
        seed_salesperson(conn)
        seed_assignment(conn, customer_account_id=1, salesperson_id=1)
        seed_order(conn, customer_account_id=1, salesperson_id=1)
        _install(monkeypatch, SqliteDS(conn))
        out = bo_api._reapply_sales_order_salesperson(
            'sales_order', 1, {'customer_account_id': 2})
        assert out['salesperson_id'] is None

    def test_manual_value_kept(self, conn, monkeypatch):
        seed_salesperson(conn)
        seed_assignment(conn, customer_account_id=1, salesperson_id=1)
        seed_order(conn, customer_account_id=1, salesperson_id=99)
        _install(monkeypatch, SqliteDS(conn))
        out = bo_api._reapply_sales_order_salesperson(
            'sales_order', 1, {'customer_account_id': 2})
        assert 'salesperson_id' not in out

    def test_explicit_payload_kept(self, conn, monkeypatch):
        seed_salesperson(conn)
        seed_assignment(conn, customer_account_id=1, salesperson_id=1)
        seed_order(conn, customer_account_id=1, salesperson_id=1)
        _install(monkeypatch, SqliteDS(conn))
        out = bo_api._reapply_sales_order_salesperson(
            'sales_order', 1, {'customer_account_id': 2, 'salesperson_id': 5})
        assert out['salesperson_id'] == 5

    def test_no_trigger_skips_query(self, monkeypatch):
        _install(monkeypatch, _RaisingDS())
        out = bo_api._reapply_sales_order_salesperson(
            'sales_order', 1, {'order_no': 'SO-1'})
        assert out == {'order_no': 'SO-1'}

    def test_order_not_found_untouched(self, conn, monkeypatch):
        _install(monkeypatch, SqliteDS(conn))
        out = bo_api._reapply_sales_order_salesperson(
            'sales_order', 999, {'customer_account_id': 2})
        assert out == {'customer_account_id': 2}

    def test_other_object_untouched(self, monkeypatch):
        _install(monkeypatch, _RaisingDS())
        out = bo_api._reapply_sales_order_salesperson(
            'customer_account', 1, {'customer_account_id': 2})
        assert out == {'customer_account_id': 2}

    def test_query_error_untouched(self, monkeypatch):
        _install(monkeypatch, _RaisingDS())
        out = bo_api._reapply_sales_order_salesperson(
            'sales_order', 1, {'customer_account_id': 2})
        assert out == {'customer_account_id': 2}
