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
