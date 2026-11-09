# -*- coding: utf-8 -*-
"""销售发票期次生成测试（S8 Wave A）—— 尾差 / 基准日 / 合并 / 红字豁免。

依据: docs/specs/s8-customer-invoice-wave-a/spec.md §8.2（期次 6 条）
夹具: meta/tests/factories/_customer_invoice_helpers.py
"""
from decimal import Decimal

import pytest

pytestmark = pytest.mark.unit

from meta.services.customer_invoice_service import CustomerInvoiceError
from meta.services.customer_invoice_service import CustomerInvoiceService
from meta.tests.factories._customer_invoice_helpers import (
    CURRENCY_ID,
    CUSTOMER_ID,
    INVOICE_DATE,
    ORG_ID,
    PAYMENT_TERM_ID,
    build_conn,
    get_schedules,
    make_ds,
    set_order_terms,
    set_payment_term_line,
)

BASE_HEADER = {
    'invoice_date': INVOICE_DATE,
    'customer_account_id': CUSTOMER_ID,
    'currency_id': CURRENCY_ID,
    'org_id': ORG_ID,
}


def _draft(conn, *, invoice_date=INVOICE_DATE, payment_term_id=PAYMENT_TERM_ID):
    service = CustomerInvoiceService(make_ds(conn))
    payload = dict(BASE_HEADER, invoice_date=invoice_date)
    if payment_term_id is not None:
        payload['payment_term_id'] = payment_term_id
    header = service.prepare_header(payload)
    invoice_id = service._insert_header(header)
    return service, service._require_header(invoice_id)


def test_two_periods_absorb_tail():
    conn = build_conn()
    service, header = _draft(conn)

    rows = service._generate_schedules(header, Decimal('452'))

    assert [row['schedule_no'] for row in rows] == [1, 2]
    assert Decimal(str(rows[0]['amount'])) == Decimal('135.6')
    assert Decimal(str(rows[1]['amount'])) == Decimal('316.4')
    assert sum(Decimal(str(row['amount'])) for row in rows) == Decimal('452')


def test_no_payment_term_falls_back_to_single_period():
    conn = build_conn()
    service, header = _draft(conn, payment_term_id=None)

    rows = service._generate_schedules(header, Decimal('113'))

    assert len(rows) == 1
    assert Decimal(str(rows[0]['ratio_percent'])) == Decimal('100')
    assert Decimal(str(rows[0]['amount'])) == Decimal('113')
    assert rows[0]['due_date'] == INVOICE_DATE
    assert rows[0]['payment_term_line_id'] is None


def test_due_date_before_invoice_date_rejected():
    conn = build_conn()
    set_payment_term_line(conn, 500, offset_months=-1)
    service, header = _draft(conn)

    with pytest.raises(CustomerInvoiceError) as error:
        service._generate_schedules(header, Decimal('100'))
    assert error.value.rule == 'INVOICE_TERM_INVALID'


def test_zero_ratio_period_merged_into_next():
    conn = build_conn(payment_term_lines=((1, 0, 0, None, 0),
                                          (2, 100, 1, None, 0)))
    service, header = _draft(conn)

    rows = service._generate_schedules(header, Decimal('250'))

    assert len(rows) == 1
    assert Decimal(str(rows[0]['ratio_percent'])) == Decimal('100')
    assert Decimal(str(rows[0]['amount'])) == Decimal('250')


def test_cutoff_day_moves_base_to_next_month_end():
    conn = build_conn()
    set_order_terms(conn, basis_date_rule='month_end', cutoff_day=25)
    service, header = _draft(conn, invoice_date='2026-11-26')

    rows = service._generate_schedules(header, Decimal('100'))

    assert rows[0]['due_date'] == '2026-12-30'
    assert rows[1]['due_date'] == '2027-01-30'


def test_fixed_day_of_month_clamps_to_month_end():
    conn = build_conn(payment_term_lines=((1, 100, 1, 31, 0),))
    service, header = _draft(conn)

    rows = service._generate_schedules(header, Decimal('100'))

    assert len(rows) == 1
    assert rows[0]['due_date'] == '2026-12-31'


def test_schedule_rows_persist_with_open_status_and_sum_to_gross():
    conn = build_conn()
    service, header = _draft(conn)

    service._generate_schedules(header, Decimal('9999.99'))

    rows = get_schedules(conn, header['id'])
    assert [row['status'] for row in rows] == ['open', 'open']
    total = sum(Decimal(str(row['amount'])) for row in rows)
    assert total == Decimal('9999.99')
    assert sum(Decimal(str(row['ratio_percent'])) for row in rows) \
        == Decimal('100')
