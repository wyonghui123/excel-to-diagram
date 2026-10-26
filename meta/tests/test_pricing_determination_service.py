# -*- coding: utf-8 -*-
"""定价确定服务测试：规则解析打分 + 行级取价编排

依据: docs/superpowers/specs/2026-10-25-sales-order-wave1-detailed-plan.md
      §3.6（解析算法与失败原因码）/ §3.7（取价编排）/ §3.8（不变量）

口径:
  解析查询依赖 SQL 的 WHERE / ORDER BY 语义，故这里用**临时 SQLite**
  建最小表结构，而不是伪造 DataSource —— 避免「测的是假 SQL」。
  建表与播种的 DML 放在 factories 助手，保证本文件默认口径即运行。
"""
from pathlib import Path
import json
import sqlite3

import pytest

pytestmark = pytest.mark.unit

from meta.core.sql_adapters import SQLiteAdapter
from meta.services.pricing_determination_service import (
    REASON_CURRENCY_MISMATCH,
    REASON_NO_CANDIDATE,
    REASON_NO_DETERMINATION,
    REASON_NO_RATE_TABLE,
    REASON_ZERO_QTY,
    PricingDeterminationService,
)
from meta.services.pricing_service import PricingError
from meta.tests.factories._pricing_w1_helpers import (
    create_pricing_tables,
    seed_rate_table,
    seed_rule,
    seed_row,
    update_row,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / 'pricing.db'
    conn = sqlite3.connect(str(path))
    try:
        create_pricing_tables(conn)
    finally:
        conn.close()

    seed_row(path, 'calc_procedures', id=1, code='PRICE_STD',
             name='标准销售定价过程')
    seed_row(path, 'lookup_sequences', id=1, code='LK_ITEM_STD',
             name='物料标准查找序列')
    seed_rate_table(path, code='PL_STD', name='标准价目表')
    return path


@pytest.fixture
def ds(db_path: Path):
    adapter = SQLiteAdapter()
    assert adapter.connect(path=str(db_path))
    yield adapter
    adapter.disconnect()


def _service(ds) -> PricingDeterminationService:
    return PricingDeterminationService(ds)


class _StubPricing:
    """桩 PricingService：只保留取价编排用到的两个入口。"""

    def __init__(self, candidates=(1,), dry=None, persisted=None, error=None):
        self.candidates = list(candidates)
        self.dry = dry if dry is not None else {
            'hit_ids': [11], 'result_id': None, 'net_amount': 37.5}
        self.persisted = persisted if persisted is not None else {
            'hit_ids': [11], 'result_id': 99, 'net_amount': 37.5}
        self.error = error
        self.calls = []
        self.candidate_calls = []

    def load_candidates(self, rate_table_id, valid_on=None):
        self.candidate_calls.append((rate_table_id, valid_on))
        return self.candidates

    def price_line(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.persisted if kwargs.get('persist') else self.dry


# ─────────────────────────────────────────────────────────────────────────────
# resolve：打分与定表
# ─────────────────────────────────────────────────────────────────────────────

class TestResolveScoring:

    def test_org_specific_beats_wildcard(self, db_path, ds):
        seed_rule(db_path, code='PD_WILD', seq=1)
        seed_rule(db_path, code='PD_ORG', seq=900, sales_org_id=318)

        out = _service(ds).resolve(
            sales_org_id=318, order_type_id=1, price_date='2026-10-25',
            currency='CNY')

        assert out['matched'] is True
        assert out['rule']['code'] == 'PD_ORG'

    def test_type_specific_beats_wildcard(self, db_path, ds):
        seed_rule(db_path, code='PD_WILD', seq=1)
        seed_rule(db_path, code='PD_TYPE', seq=900, order_type_id=1)

        out = _service(ds).resolve(
            sales_org_id=318, order_type_id=1, price_date='2026-10-25',
            currency='CNY')

        assert out['rule']['code'] == 'PD_TYPE'

    def test_seq_breaks_tie(self, db_path, ds):
        seed_rule(db_path, code='PD_SLOW', seq=50)
        seed_rule(db_path, code='PD_FAST', seq=5)

        out = _service(ds).resolve(
            sales_org_id=318, order_type_id=1, price_date='2026-10-25',
            currency='CNY')

        assert out['rule']['code'] == 'PD_FAST'

    def test_id_breaks_tie_when_seq_equal(self, db_path, ds):
        first = seed_rule(db_path, code='PD_FIRST', seq=10)
        second = seed_rule(db_path, code='PD_SECOND', seq=10)
        assert first < second

        out = _service(ds).resolve(
            sales_org_id=318, order_type_id=1, price_date='2026-10-25',
            currency='CNY')

        assert out['rule']['code'] == 'PD_FIRST'

    def test_no_active_rule(self, db_path, ds):
        seed_rule(db_path, code='PD_DRAFT', status='draft')

        out = _service(ds).resolve(
            sales_org_id=318, order_type_id=1, price_date='2026-10-25',
            currency='CNY')

        assert out['matched'] is False
        assert out['reason'] == REASON_NO_DETERMINATION
        assert out['rate_table'] is None

    def test_validity_window_is_end_exclusive(self, db_path, ds):
        # valid_to == 基准日 → 不命中（区间含下不含上）
        seed_rule(db_path, code='PD_EXPIRED',
                  valid_from='2026-01-01', valid_to='2026-10-25')
        out = _service(ds).resolve(
            sales_org_id=318, order_type_id=1, price_date='2026-10-25',
            currency='CNY')
        assert out['reason'] == REASON_NO_DETERMINATION

        # valid_from == 基准日 → 命中
        seed_rule(db_path, code='PD_FROM_TODAY', valid_from='2026-10-25',
                  seq=200)
        out = _service(ds).resolve(
            sales_org_id=318, order_type_id=1, price_date='2026-10-25',
            currency='CNY')
        assert out['matched'] is True
        assert out['rule']['code'] == 'PD_FROM_TODAY'


class TestResolveCurrency:

    def test_rule_currency_mismatch(self, db_path, ds):
        seed_rule(db_path, currency='USD')

        out = _service(ds).resolve(
            sales_org_id=318, order_type_id=1, price_date='2026-10-25',
            currency='CNY')

        assert out['matched'] is False
        assert out['reason'] == REASON_CURRENCY_MISMATCH
        assert out['rule']['code'] == 'PD'

    def test_rule_currency_is_case_insensitive(self, db_path, ds):
        seed_rule(db_path, currency='CNY')

        out = _service(ds).resolve(
            sales_org_id=318, order_type_id=1, price_date='2026-10-25',
            currency='cny')

        assert out['matched'] is True


class TestResolveRateTable:

    def test_pinned_table_must_be_approved(self, db_path, ds):
        table_id = seed_rate_table(db_path, code='PL_DRAFT', status='draft')
        seed_rule(db_path, rate_table_id=table_id)

        out = _service(ds).resolve(
            sales_org_id=318, order_type_id=1, price_date='2026-10-25',
            currency='CNY')

        assert out['matched'] is False
        assert out['reason'] == REASON_NO_RATE_TABLE

    def test_pinned_table_currency_must_match(self, db_path, ds):
        table_id = seed_rate_table(db_path, code='PL_USD', currency='USD')
        seed_rule(db_path, rate_table_id=table_id)

        out = _service(ds).resolve(
            sales_org_id=318, order_type_id=1, price_date='2026-10-25',
            currency='CNY')

        assert out['matched'] is False
        assert out['reason'] == REASON_CURRENCY_MISMATCH

    def test_pinned_table_org_scope(self, db_path, ds):
        foreign = seed_rate_table(db_path, code='PL_OTHER', owner_org_id=999)
        seed_rule(db_path, rate_table_id=foreign)

        out = _service(ds).resolve(
            sales_org_id=318, order_type_id=1, price_date='2026-10-25',
            currency='CNY')
        assert out['reason'] == REASON_NO_RATE_TABLE

        own = seed_rate_table(db_path, code='PL_OWN', owner_org_id=318)
        seed_rule(db_path, rate_table_id=own, code='PD_OWN', seq=1)
        out = _service(ds).resolve(
            sales_org_id=318, order_type_id=1, price_date='2026-10-25',
            currency='CNY')
        assert out['matched'] is True
        assert out['rate_table']['code'] == 'PL_OWN'

    def test_auto_table_prefers_org_specific(self, db_path, ds):
        seed_rate_table(db_path, code='PL_ORG', owner_org_id=318)
        seed_rule(db_path, rate_table_id=None)

        out = _service(ds).resolve(
            sales_org_id=318, order_type_id=1, price_date='2026-10-25',
            currency='CNY')

        assert out['matched'] is True
        assert out['rate_table']['code'] == 'PL_ORG'

    def test_auto_table_requires_currency(self, db_path, ds):
        seed_rule(db_path, rate_table_id=None)

        out = _service(ds).resolve(
            sales_org_id=318, order_type_id=1, price_date='2026-10-25',
            currency=None)

        assert out['matched'] is False
        assert out['reason'] == REASON_NO_RATE_TABLE

    def test_auto_table_needs_approved_candidate(self, db_path, ds):
        update_row(db_path, 'rate_tables', 1, status='draft')
        seed_rule(db_path, rate_table_id=None)

        out = _service(ds).resolve(
            sales_org_id=318, order_type_id=1, price_date='2026-10-25',
            currency='CNY')

        assert out['reason'] == REASON_NO_RATE_TABLE


class TestPreferredRateTable:
    """E1：客户价目表只作优选，任一条件不满足即静默回退既有定表规则。"""

    def test_preferred_table_wins_over_pinned(self, db_path, ds):
        pinned = seed_rate_table(db_path, code='PL_PINNED')
        seed_rule(db_path, rate_table_id=pinned)
        preferred = seed_rate_table(db_path, code='PL_PREFERRED')

        out = _service(ds).resolve(
            sales_org_id=318, order_type_id=1, price_date='2026-10-25',
            currency='CNY', preferred_rate_table_id=preferred)

        assert out['matched'] is True
        assert out['rate_table']['code'] == 'PL_PREFERRED'

    def test_preferred_wins_over_auto_candidate(self, db_path, ds):
        seed_rate_table(db_path, code='PL_ORG', owner_org_id=318)
        seed_rule(db_path, rate_table_id=None)
        preferred = seed_rate_table(db_path, code='PL_PREF_ONLY')

        out = _service(ds).resolve(
            sales_org_id=318, order_type_id=1, price_date='2026-10-25',
            currency='CNY', preferred_rate_table_id=preferred)

        assert out['rate_table']['code'] == 'PL_PREF_ONLY'

    def test_preferred_draft_falls_back_to_pinned(self, db_path, ds):
        pinned = seed_rate_table(db_path, code='PL_PINNED')
        seed_rule(db_path, rate_table_id=pinned)
        preferred = seed_rate_table(
            db_path, code='PL_PREF_DRAFT', status='draft')

        out = _service(ds).resolve(
            sales_org_id=318, order_type_id=1, price_date='2026-10-25',
            currency='CNY', preferred_rate_table_id=preferred)

        assert out['rate_table']['code'] == 'PL_PINNED'

    def test_preferred_currency_mismatch_falls_back(self, db_path, ds):
        pinned = seed_rate_table(db_path, code='PL_PINNED')
        seed_rule(db_path, rate_table_id=pinned)
        preferred = seed_rate_table(
            db_path, code='PL_PREF_USD', currency='USD')

        out = _service(ds).resolve(
            sales_org_id=318, order_type_id=1, price_date='2026-10-25',
            currency='CNY', preferred_rate_table_id=preferred)

        assert out['rate_table']['code'] == 'PL_PINNED'

    def test_preferred_out_of_scope_falls_back(self, db_path, ds):
        pinned = seed_rate_table(db_path, code='PL_PINNED')
        seed_rule(db_path, rate_table_id=pinned)
        preferred = seed_rate_table(
            db_path, code='PL_PREF_FOREIGN', owner_org_id=999)

        out = _service(ds).resolve(
            sales_org_id=318, order_type_id=1, price_date='2026-10-25',
            currency='CNY', preferred_rate_table_id=preferred)

        assert out['rate_table']['code'] == 'PL_PINNED'

    def test_missing_preferred_falls_back(self, db_path, ds):
        pinned = seed_rate_table(db_path, code='PL_PINNED')
        seed_rule(db_path, rate_table_id=pinned)

        out = _service(ds).resolve(
            sales_org_id=318, order_type_id=1, price_date='2026-10-25',
            currency='CNY', preferred_rate_table_id=99999)

        assert out['rate_table']['code'] == 'PL_PINNED'


class TestResolveCodes:

    def test_procedure_and_sequence_codes(self, db_path, ds):
        seed_rule(db_path)

        out = _service(ds).resolve(
            sales_org_id=318, order_type_id=1, price_date='2026-10-25',
            currency='CNY')

        assert out['procedure_code'] == 'PRICE_STD'
        assert out['sequence_code'] == 'LK_ITEM_STD'

    def test_sequence_code_none_when_not_declared(self, db_path, ds):
        seed_rule(db_path, lookup_sequence_id=None)

        out = _service(ds).resolve(
            sales_org_id=318, order_type_id=1, price_date='2026-10-25',
            currency='CNY')

        assert out['matched'] is True
        assert out['sequence_code'] is None


# ─────────────────────────────────────────────────────────────────────────────
# determine_line：行级取价编排
# ─────────────────────────────────────────────────────────────────────────────

def _with_stub(db_path, stub):
    adapter = SQLiteAdapter()
    assert adapter.connect(path=str(db_path))
    return adapter, PricingDeterminationService(adapter, pricing_service=stub)


class TestDetermineLine:

    def test_zero_qty_fails_without_calling_pricing(self, db_path):
        seed_rule(db_path)
        stub = _StubPricing()
        adapter, service = _with_stub(db_path, stub)
        try:
            out = service.determine_line(
                item_id=2, qty=0, currency='CNY', price_date='2026-10-25',
                sales_org_id=318, order_type_id=1)
        finally:
            adapter.disconnect()

        assert out['pricing_status'] == 'failed'
        assert out['reason'] == REASON_ZERO_QTY
        assert stub.calls == []

    def test_missing_item_fails(self, db_path):
        seed_rule(db_path)
        stub = _StubPricing()
        adapter, service = _with_stub(db_path, stub)
        try:
            out = service.determine_line(
                item_id=None, qty=2, currency='CNY', price_date='2026-10-25',
                sales_org_id=318, order_type_id=1)
        finally:
            adapter.disconnect()

        assert out['reason'] == REASON_NO_CANDIDATE
        assert stub.calls == []

    def test_no_rule_fails(self, db_path):
        stub = _StubPricing()
        adapter, service = _with_stub(db_path, stub)
        try:
            out = service.determine_line(
                item_id=2, qty=2, currency='CNY', price_date='2026-10-25',
                sales_org_id=318, order_type_id=1)
        finally:
            adapter.disconnect()

        assert out['pricing_status'] == 'failed'
        assert out['reason'] == REASON_NO_DETERMINATION
        assert stub.calls == []

    def test_no_candidates_fails(self, db_path):
        seed_rule(db_path)
        stub = _StubPricing(candidates=())
        adapter, service = _with_stub(db_path, stub)
        try:
            out = service.determine_line(
                item_id=2, qty=2, currency='CNY', price_date='2026-10-25',
                sales_org_id=318, order_type_id=1)
        finally:
            adapter.disconnect()

        assert out['reason'] == REASON_NO_CANDIDATE
        assert out['trace']['candidates'] == 0
        assert stub.calls == []

    def test_dry_run_without_hit_fails(self, db_path):
        seed_rule(db_path)
        stub = _StubPricing(dry={'hit_ids': [], 'result_id': None,
                                 'net_amount': 0})
        adapter, service = _with_stub(db_path, stub)
        try:
            out = service.determine_line(
                item_id=2, qty=2, currency='CNY', price_date='2026-10-25',
                sales_org_id=318, order_type_id=1)
        finally:
            adapter.disconnect()

        assert out['reason'] == REASON_NO_CANDIDATE
        assert len(stub.calls) == 1
        assert stub.calls[0]['persist'] is False

    def test_success_derives_unit_price_from_amount(self, db_path):
        seed_rule(db_path)
        stub = _StubPricing()
        adapter, service = _with_stub(db_path, stub)
        try:
            out = service.determine_line(
                item_id=2, qty=3, currency='CNY', price_date='2026-10-25',
                sales_org_id=318, order_type_id=1)
        finally:
            adapter.disconnect()

        assert out['pricing_status'] == 'determined'
        assert out['unit_price'] == pytest.approx(12.5)
        assert out['amount'] == pytest.approx(37.5)
        assert out['trace']['hit_ids'] == [11]
        assert out['trace']['rate_table_code'] == 'PL_STD'
        assert out['trace']['procedure_code'] == 'PRICE_STD'
        assert out['trace']['reason'] is None
        assert len(stub.calls) == 1
        assert stub.calls[0]['persist'] is False
        assert stub.calls[0]['slot_keys'] == [{'item_id': 2}]
        assert stub.calls[0]['base'] == pytest.approx(3)

    def test_persist_true_writes_result_id(self, db_path):
        seed_rule(db_path)
        stub = _StubPricing()
        adapter, service = _with_stub(db_path, stub)
        try:
            out = service.determine_line(
                item_id=2, qty=3, currency='CNY', price_date='2026-10-25',
                sales_org_id=318, order_type_id=1,
                document_id=10, document_line_id=100, persist=True)
        finally:
            adapter.disconnect()

        assert len(stub.calls) == 2
        assert stub.calls[0]['persist'] is False
        assert stub.calls[1]['persist'] is True
        assert stub.calls[1]['document_id'] == 10
        assert stub.calls[1]['document_line_id'] == 100
        assert out['trace']['result_id'] == 99
        assert out['unit_price'] == pytest.approx(12.5)

    def test_pricing_exception_degrades_to_failed(self, db_path):
        seed_rule(db_path)
        stub = _StubPricing(error=PricingError('procedure missing'))
        adapter, service = _with_stub(db_path, stub)
        try:
            out = service.determine_line(
                item_id=2, qty=3, currency='CNY', price_date='2026-10-25',
                sales_org_id=318, order_type_id=1)
        finally:
            adapter.disconnect()

        assert out['pricing_status'] == 'failed'
        assert out['reason'] == REASON_NO_CANDIDATE
        assert out['unit_price'] is None
        assert out['trace']['reason'] == REASON_NO_CANDIDATE


# ─────────────────────────────────────────────────────────────────────────────
# W2-F：按查找序列构造槽位键值
# ─────────────────────────────────────────────────────────────────────────────

def _seed_two_slot_sequence(db_path):
    """把 LK_ITEM_STD 改成两槽位：客户×物料 → 物料。"""
    ks_item = seed_row(db_path, 'key_schemas', code='KS_ITEM',
                       key_fields=json.dumps(['item_id']))
    ks_cust = seed_row(db_path, 'key_schemas', code='KS_ITEM_CUST',
                       key_fields=json.dumps(['customer_account_id', 'item_id']))
    steps = [{'seq': 1, 'key_schema_id': ks_cust},
             {'seq': 2, 'key_schema_id': ks_item}]
    update_row(db_path, 'lookup_sequences', 1, steps=json.dumps(steps))


class TestSlotKeys:
    """R-KEY-1~3：首槽客户价、次槽物料兜底、客户空跳过首槽。"""

    def test_two_slot_sequence_builds_customer_slot_first(self, db_path):
        seed_rule(db_path)
        _seed_two_slot_sequence(db_path)
        stub = _StubPricing()
        adapter, service = _with_stub(db_path, stub)
        try:
            service.determine_line(
                item_id=2, qty=1, customer_account_id=4, currency='CNY',
                price_date='2026-10-25', sales_org_id=318, order_type_id=1)
        finally:
            adapter.disconnect()

        assert stub.calls[0]['slot_keys'] == [
            {'customer_account_id': 4, 'item_id': 2},
            {'item_id': 2},
        ]

    def test_empty_customer_skips_first_slot(self, db_path):
        seed_rule(db_path)
        _seed_two_slot_sequence(db_path)
        stub = _StubPricing()
        adapter, service = _with_stub(db_path, stub)
        try:
            service.determine_line(
                item_id=2, qty=1, currency='CNY', price_date='2026-10-25',
                sales_org_id=318, order_type_id=1)
        finally:
            adapter.disconnect()

        assert stub.calls[0]['slot_keys'] == [None, {'item_id': 2}]

    def test_single_slot_sequence_ignores_customer(self, db_path):
        """单槽序列（LK_ITEM_STD）零改动：带客户也只传物料键（R-KEY-3）。"""
        seed_rule(db_path)
        stub = _StubPricing()
        adapter, service = _with_stub(db_path, stub)
        try:
            service.determine_line(
                item_id=2, qty=1, customer_account_id=4, currency='CNY',
                price_date='2026-10-25', sales_org_id=318, order_type_id=1)
        finally:
            adapter.disconnect()

        assert stub.calls[0]['slot_keys'] == [{'item_id': 2}]
