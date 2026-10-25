# -*- coding: utf-8 -*-
"""W1-C 往来单位地址：默认地址解析 / 订单带出与重算

覆盖:
  §5.3 解析链（ship_to / bill_to，含售达方回退）
  §5.5 W1-R13（同角色至多一条默认）/ R14（只认启用地址）/ R15（留空不报错）

测试数据经 `meta/tests/factories/_party_address_helpers.py`
（conftest 的裸 SQL 门控白名单目录），本文件不含裸 SQL DML。
"""
import sqlite3

import pytest

pytestmark = pytest.mark.unit

from meta.api import bo_api
from meta.services.party_address_service import PartyAddressService
from meta.tests.factories._party_address_helpers import (
    SqliteDS,
    create_tables,
    seed_account,
    seed_address,
    seed_order,
    seed_party_address,
    seed_relation,
)


@pytest.fixture()
def conn():
    c = sqlite3.connect(':memory:')
    create_tables(c)
    yield c
    c.close()


def _install(monkeypatch, ds):
    monkeypatch.setattr(bo_api, '_get_data_source', lambda: ds)


class TestResolve:
    """解析链：只认 is_default=1 + 双方 active（W1-R13/R14）。"""

    def test_ship_to_from_ship_party(self, conn):
        seed_address(conn, id=1)
        seed_party_address(conn, party_id=7, address_id=1)
        out = PartyAddressService(SqliteDS(conn)).resolve({'ship_to_party_id': 7})
        assert out['ship_to_address_id'] == 1

    def test_ship_to_falls_back_to_customer_party(self, conn):
        seed_relation(conn, id=1, party2_id=5)
        seed_account(conn, id=1, relation_id=1)
        seed_address(conn, id=3)
        seed_party_address(conn, party_id=5, address_id=3)
        out = PartyAddressService(SqliteDS(conn)).resolve(
            {'customer_account_id': 1})
        assert out['ship_to_address_id'] == 3

    def test_non_default_row_ignored(self, conn):
        seed_address(conn, id=1)
        seed_party_address(conn, party_id=7, address_id=1, is_default=0)
        out = PartyAddressService(SqliteDS(conn)).resolve({'ship_to_party_id': 7})
        assert out['ship_to_address_id'] is None

    def test_inactive_party_address_ignored(self, conn):
        seed_address(conn, id=1)
        seed_party_address(conn, party_id=7, address_id=1, status='inactive')
        out = PartyAddressService(SqliteDS(conn)).resolve({'ship_to_party_id': 7})
        assert out['ship_to_address_id'] is None

    def test_inactive_address_ignored(self, conn):
        """W1-R14：停用地址不允许作为默认值来源。"""
        seed_address(conn, id=1, status='inactive')
        seed_party_address(conn, party_id=7, address_id=1)
        out = PartyAddressService(SqliteDS(conn)).resolve({'ship_to_party_id': 7})
        assert out['ship_to_address_id'] is None

    def test_bill_to_from_bill_to_account(self, conn):
        seed_relation(conn, id=2, party2_id=9)
        seed_account(conn, id=2, relation_id=2)
        seed_address(conn, id=4)
        seed_party_address(conn, party_id=9, address_id=4, role='bill_to')
        out = PartyAddressService(SqliteDS(conn)).resolve(
            {'customer_account_id': 1, 'bill_to_account_id': 2})
        assert out['bill_to_address_id'] == 4

    def test_bill_to_falls_back_to_customer_party(self, conn):
        seed_relation(conn, id=1, party2_id=5)
        seed_account(conn, id=1, relation_id=1)
        seed_address(conn, id=5)
        seed_party_address(conn, party_id=5, address_id=5, role='bill_to')
        out = PartyAddressService(SqliteDS(conn)).resolve(
            {'customer_account_id': 1})
        assert out['bill_to_address_id'] == 5

    def test_no_data_returns_none(self, conn):
        out = PartyAddressService(SqliteDS(conn)).resolve({})
        assert out == {'ship_to_address_id': None,
                       'bill_to_address_id': None}

    def test_blank_inputs_do_not_query(self):
        class _DS:
            def query(self, sql, params=None):
                raise AssertionError('不应查询')

        out = PartyAddressService(_DS()).resolve(
            {'customer_account_id': None, 'ship_to_party_id': ''})
        assert out == {'ship_to_address_id': None,
                       'bill_to_address_id': None}

    def test_query_error_fails_open(self):
        class _DS:
            def query(self, sql, params=None):
                raise RuntimeError('db down')

        out = PartyAddressService(_DS()).resolve(
            {'customer_account_id': 1, 'ship_to_party_id': 7})
        assert out['ship_to_address_id'] is None
        assert out['bill_to_address_id'] is None


class TestCreate:
    """创建时只在空白字段上带出默认地址（W1-R15）。"""

    def test_blank_addresses_filled(self, conn, monkeypatch):
        seed_relation(conn, id=1, party2_id=5)
        seed_account(conn, id=1, relation_id=1)
        seed_address(conn, id=1)
        seed_party_address(conn, party_id=5, address_id=1, role='ship_to')
        seed_party_address(conn, party_id=5, address_id=1, role='bill_to')
        _install(monkeypatch, SqliteDS(conn))

        out = bo_api._apply_sales_order_address_defaults(
            {'customer_account_id': 1})
        assert out['ship_to_address_id'] == 1
        assert out['bill_to_address_id'] == 1

    def test_explicit_address_kept(self, conn, monkeypatch):
        seed_relation(conn, id=1, party2_id=5)
        seed_account(conn, id=1, relation_id=1)
        seed_address(conn, id=1)
        seed_party_address(conn, party_id=5, address_id=1)
        _install(monkeypatch, SqliteDS(conn))

        out = bo_api._apply_sales_order_address_defaults(
            {'customer_account_id': 1, 'ship_to_address_id': 88})
        assert out['ship_to_address_id'] == 88

    def test_all_explicit_skips_lookup(self, monkeypatch):
        class _DS:
            def query(self, sql, params=None):
                raise AssertionError('不应查询')

        _install(monkeypatch, _DS())
        data = {'ship_to_address_id': 1, 'bill_to_address_id': 2}
        assert bo_api._apply_sales_order_address_defaults(data) is data

    def test_lookup_error_does_not_block_save(self, monkeypatch):
        def _boom():
            raise RuntimeError('db down')

        monkeypatch.setattr(bo_api, '_get_data_source', _boom)
        out = bo_api._apply_sales_order_address_defaults(
            {'customer_account_id': 1})
        assert out == {'customer_account_id': 1}


class TestReapply:
    """抬头变更时重算地址；用户手选过的地址不覆盖（§5.3）。"""

    def test_ship_party_change_switches_address(self, conn, monkeypatch):
        seed_address(conn, id=1)
        seed_address(conn, id=2)
        seed_party_address(conn, party_id=7, address_id=1)
        seed_party_address(conn, party_id=8, address_id=2)
        seed_order(conn, id=11, ship_to_party_id=7, ship_to_address_id=1)
        _install(monkeypatch, SqliteDS(conn))

        out = bo_api._reapply_sales_order_addresses(
            'sales_order', 11, {'ship_to_party_id': 8})
        assert out['ship_to_address_id'] == 2

    def test_ship_party_change_without_default_clears(self, conn, monkeypatch):
        seed_address(conn, id=1)
        seed_party_address(conn, party_id=7, address_id=1)
        seed_order(conn, id=11, ship_to_party_id=7, ship_to_address_id=1)
        _install(monkeypatch, SqliteDS(conn))

        out = bo_api._reapply_sales_order_addresses(
            'sales_order', 11, {'ship_to_party_id': 8})
        assert out['ship_to_address_id'] is None

    def test_manual_address_kept(self, conn, monkeypatch):
        seed_address(conn, id=1)
        seed_address(conn, id=2)
        seed_party_address(conn, party_id=7, address_id=1)
        seed_party_address(conn, party_id=8, address_id=2)
        seed_order(conn, id=11, ship_to_party_id=7, ship_to_address_id=99)
        _install(monkeypatch, SqliteDS(conn))

        out = bo_api._reapply_sales_order_addresses(
            'sales_order', 11, {'ship_to_party_id': 8})
        assert 'ship_to_address_id' not in out

    def test_explicit_payload_address_kept(self, conn, monkeypatch):
        seed_address(conn, id=1)
        seed_address(conn, id=2)
        seed_party_address(conn, party_id=7, address_id=1)
        seed_party_address(conn, party_id=8, address_id=2)
        seed_order(conn, id=11, ship_to_party_id=7, ship_to_address_id=1)
        _install(monkeypatch, SqliteDS(conn))

        out = bo_api._reapply_sales_order_addresses(
            'sales_order', 11,
            {'ship_to_party_id': 8, 'ship_to_address_id': 55})
        assert out['ship_to_address_id'] == 55

    def test_customer_change_recomputes_bill_to(self, conn, monkeypatch):
        seed_relation(conn, id=1, party2_id=5)
        seed_relation(conn, id=2, party2_id=6)
        seed_account(conn, id=1, relation_id=1)
        seed_account(conn, id=2, relation_id=2)
        seed_address(conn, id=3)
        seed_address(conn, id=4)
        seed_party_address(conn, party_id=5, address_id=3, role='bill_to')
        seed_party_address(conn, party_id=6, address_id=4, role='bill_to')
        seed_order(conn, id=11, customer_account_id=1, bill_to_address_id=3)
        _install(monkeypatch, SqliteDS(conn))

        out = bo_api._reapply_sales_order_addresses(
            'sales_order', 11, {'customer_account_id': 2})
        assert out['bill_to_address_id'] == 4

    def test_non_sales_order_returns_same_object(self):
        data = {'ship_to_party_id': 8}
        assert bo_api._reapply_sales_order_addresses('item', 1, data) is data

    def test_no_trigger_field_skips_lookup(self, monkeypatch):
        def _boom():
            raise AssertionError('不应查询')

        monkeypatch.setattr(bo_api, '_get_data_source', _boom)
        data = {'description': 'x'}
        assert bo_api._reapply_sales_order_addresses(
            'sales_order', 11, data) == data

    def test_order_not_found_returns_payload(self, conn, monkeypatch):
        _install(monkeypatch, SqliteDS(conn))
        out = bo_api._reapply_sales_order_addresses(
            'sales_order', 999, {'ship_to_party_id': 8})
        assert out == {'ship_to_party_id': 8}

    def test_query_error_returns_payload(self, monkeypatch):
        class _DS:
            def query(self, sql, params=None):
                raise RuntimeError('db down')

        _install(monkeypatch, _DS())
        out = bo_api._reapply_sales_order_addresses(
            'sales_order', 11, {'ship_to_party_id': 8})
        assert out == {'ship_to_party_id': 8}
