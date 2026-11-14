# -*- coding: utf-8 -*-
"""采购发票应付期次生成测试（AP Payment Plan，Spec §23 / R-VI-34~37）。

依据: docs/specs/spec-vendor-invoice-object-model-2026-11-11.md §23.9
夹具: meta/tests/factories/_vendor_invoice_helpers.py（v271 期次表）
"""
from decimal import Decimal

import pytest

pytestmark = pytest.mark.unit

from meta.services.vendor_invoice_match_service import (
    VendorInvoiceError,
    VendorInvoiceMatchService,
)
from meta.tests.factories._vendor_invoice_helpers import (
    PAYMENT_TERM_ID,
    SCHEDULE_ID,
    SUPPLIER_ACCOUNT_ID,
    audit_actions,
    get_header,
    get_schedules,
    insert_invoice,
    insert_line,
    make_env,
    seed_currency,
    seed_payment_term,
    seed_purchase_order,
    seed_vendor_account,
    set_payment_term,
)

INVOICE_DATE = '2026-11-01'

#: 默认条件：2 期 30% / 70%，到期日发票日 / +1 月
DEFAULT_LINES = ((1, 30, 0, None, 0), (2, 70, 1, None, 0))


def _setup(tmp_path, *, lines=DEFAULT_LINES, gross=452.0,
           invoice_date=INVOICE_DATE, term_id=PAYMENT_TERM_ID,
           basis_date_rule='invoice_date', cutoff_day=None):
    ds = make_env(tmp_path)
    seed_currency(ds)
    seed_payment_term(ds, term_id=term_id, basis_date_rule=basis_date_rule,
                      cutoff_day=cutoff_day, lines=lines)
    invoice_id = insert_invoice(ds, invoice_date=invoice_date,
                                gross_amount=gross, payment_term_id=term_id)
    service = VendorInvoiceMatchService(ds)
    return ds, service, service._require_header(invoice_id)


def test_two_periods_absorb_tail(tmp_path):
    _ds, service, header = _setup(tmp_path)

    rows = service._generate_schedules(header)

    assert [row['schedule_no'] for row in rows] == [1, 2]
    assert Decimal(str(rows[0]['amount'])) == Decimal('135.6')
    assert Decimal(str(rows[1]['amount'])) == Decimal('316.4')
    assert sum(Decimal(str(row['amount'])) for row in rows) == Decimal('452')


def test_no_payment_term_falls_back_to_single_period(tmp_path):
    ds, _service, _header = _setup(tmp_path)
    invoice_id = insert_invoice(ds, invoice_no='VI-0002',
                                invoice_date=INVOICE_DATE, gross_amount=113.0)
    service = VendorInvoiceMatchService(ds)
    header = get_header(ds, invoice_id)

    rows = service._generate_schedules(header)

    assert len(rows) == 1
    assert Decimal(str(rows[0]['ratio_percent'])) == Decimal('100')
    assert Decimal(str(rows[0]['amount'])) == Decimal('113')
    assert rows[0]['due_date'] == INVOICE_DATE
    assert rows[0]['payment_term_line_id'] is None


def test_due_date_before_invoice_date_rejected(tmp_path):
    _ds, service, header = _setup(
        tmp_path, lines=((1, 100, -1, None, 0),))

    with pytest.raises(VendorInvoiceError) as error:
        service._generate_schedules(header)
    assert error.value.rule == 'VENDOR_INVOICE_TERM_INVALID'


def test_cutoff_day_moves_base_date(tmp_path):
    _ds, service, header = _setup(
        tmp_path, invoice_date='2026-11-26',
        basis_date_rule='month_end', cutoff_day=25,
        lines=((1, 100, 0, None, 0),))

    rows = service._generate_schedules(header)

    assert len(rows) == 1
    assert rows[0]['due_date'] == '2026-12-30'


def test_fixed_day_of_month_clamps_to_month_end(tmp_path):
    _ds, service, header = _setup(
        tmp_path, lines=((1, 100, 1, 31, 0),))

    rows = service._generate_schedules(header)

    assert len(rows) == 1
    assert rows[0]['due_date'] == '2026-12-31'


def test_schedule_rows_persist_with_open_status_and_sum_to_gross(tmp_path):
    ds, service, header = _setup(tmp_path, gross=9999.99)

    service._generate_schedules(header)

    rows = get_schedules(ds, header['id'])
    assert [row['status'] for row in rows] == ['open', 'open']
    assert [row['amount_applied'] for row in rows] == [0, 0]
    assert sum(Decimal(str(row['amount'])) for row in rows) \
        == Decimal('9999.99')
    assert sum(Decimal(str(row['ratio_percent'])) for row in rows) \
        == Decimal('100')


def test_credit_memo_without_source_skips_schedules(tmp_path):
    """R-VI-49：无回指源单的贷项不生成期次，audit 记录跳过原因。"""
    ds, _service, _header = _setup(tmp_path)
    credit_id = insert_invoice(ds, invoice_no='VI-CN-0001',
                               category='credit_memo', direction=-1,
                               invoice_date=INVOICE_DATE,
                               gross_amount=-452.0,
                               payment_term_id=PAYMENT_TERM_ID)
    service = VendorInvoiceMatchService(ds)
    header = get_header(ds, credit_id)

    assert service._generate_schedules(header) == []
    assert get_schedules(ds, credit_id) == []
    assert audit_actions(ds, credit_id) == ['schedule_skip']


def test_red_credit_memo_mirrors_negative_schedules(tmp_path):
    """R-VI-49：红字贷项按期次比例镜像生成负额期次，与原票净额为 0。"""
    ds, service, source_header = _setup(tmp_path)
    service._generate_schedules(source_header)
    credit_id = insert_invoice(ds, invoice_no='VI-CN-RED-0001',
                               category='credit_memo', direction=-1,
                               invoice_date=INVOICE_DATE,
                               gross_amount=-452.0,
                               payment_term_id=PAYMENT_TERM_ID,
                               reversal_of_invoice_id=source_header['id'])

    rows = service._generate_schedules(get_header(ds, credit_id))

    assert [Decimal(str(row['amount'])) for row in rows] \
        == [Decimal('-135.6'), Decimal('-316.4')]
    assert [Decimal(str(row['ratio_percent'])) for row in rows] \
        == [Decimal('-30'), Decimal('-70')]
    assert [row['status'] for row in rows] == ['open', 'open']
    assert [row['amount_applied'] for row in rows] == [0, 0]
    source_due = [row['due_date'] for row in
                  get_schedules(ds, source_header['id'])]
    assert [row['due_date'] for row in rows] == source_due
    net = sum(Decimal(str(row['amount'])) for row in rows) + sum(
        Decimal(str(row['amount']))
        for row in get_schedules(ds, source_header['id']))
    assert net == Decimal('0')


def test_adjustment_mirrors_signed_schedules(tmp_path):
    """R-VI-49：调整单按增减方向镜像正 / 负额期次，原期次不变。"""
    ds, service, source_header = _setup(tmp_path)
    service._generate_schedules(source_header)
    decrease_id = insert_invoice(ds, invoice_no='VI-ADJ-D-0001',
                                 category='adjustment', direction=1,
                                 invoice_date=INVOICE_DATE,
                                 gross_amount=-100.0,
                                 payment_term_id=PAYMENT_TERM_ID,
                                 adjustment_of_invoice_id=source_header['id'])
    increase_id = insert_invoice(ds, invoice_no='VI-ADJ-I-0001',
                                 category='adjustment', direction=1,
                                 invoice_date=INVOICE_DATE,
                                 gross_amount=50.0,
                                 payment_term_id=PAYMENT_TERM_ID,
                                 adjustment_of_invoice_id=source_header['id'])

    decrease = service._generate_schedules(get_header(ds, decrease_id))
    increase = service._generate_schedules(get_header(ds, increase_id))

    assert [Decimal(str(row['amount'])) for row in decrease] \
        == [Decimal('-30'), Decimal('-70')]
    assert [Decimal(str(row['amount'])) for row in increase] \
        == [Decimal('15'), Decimal('35')]
    # 原票期次只读（R-VI-35 / R-VI-49）
    assert [Decimal(str(row['amount'])) for row in
            get_schedules(ds, source_header['id'])] \
        == [Decimal('135.6'), Decimal('316.4')]


# ------------------------------------------------------------------ §23.5 带出链

ACCOUNT_TERM_ID = 6002


def _setup_blank_term(tmp_path, *, po_term=None, account_term=None):
    """头表不填付款条件，按带出链解析的环境。"""
    ds = make_env(tmp_path)
    seed_currency(ds)
    seed_payment_term(ds, lines=DEFAULT_LINES)
    seed_payment_term(ds, term_id=ACCOUNT_TERM_ID, code='NT15',
                      lines=((1, 100, 0, None, 0),))
    seed_vendor_account(ds, default_payment_term_id=account_term)
    seed_purchase_order(ds, payment_term_id=po_term)
    invoice_id = insert_invoice(ds, invoice_date=INVOICE_DATE, gross_amount=452.0)
    service = VendorInvoiceMatchService(ds)
    return ds, service, invoice_id


def test_po_anchor_derives_term_and_persists_snapshot(tmp_path):
    ds, service, invoice_id = _setup_blank_term(
        tmp_path, po_term=PAYMENT_TERM_ID, account_term=ACCOUNT_TERM_ID)
    insert_line(ds, invoice_id, schedule_id=SCHEDULE_ID)
    header = get_header(ds, invoice_id)

    rows = service._generate_schedules(header, service._load_lines(invoice_id))

    # PO 优先于供应商默认
    assert get_header(ds, invoice_id)['payment_term_id'] == PAYMENT_TERM_ID
    assert [Decimal(str(row['amount'])) for row in rows] \
        == [Decimal('135.6'), Decimal('316.4')]


def test_vendor_account_default_used_when_no_po_anchor(tmp_path):
    ds, service, invoice_id = _setup_blank_term(
        tmp_path, account_term=ACCOUNT_TERM_ID)
    insert_line(ds, invoice_id)
    header = get_header(ds, invoice_id)

    rows = service._generate_schedules(header, service._load_lines(invoice_id))

    assert get_header(ds, invoice_id)['payment_term_id'] == ACCOUNT_TERM_ID
    assert len(rows) == 1
    assert rows[0]['due_date'] == INVOICE_DATE


def test_explicit_header_term_not_overridden_by_po(tmp_path):
    ds, service, invoice_id = _setup_blank_term(
        tmp_path, po_term=PAYMENT_TERM_ID, account_term=ACCOUNT_TERM_ID)
    set_payment_term(ds, invoice_id, ACCOUNT_TERM_ID)
    insert_line(ds, invoice_id, schedule_id=SCHEDULE_ID)
    header = get_header(ds, invoice_id)

    rows = service._generate_schedules(header, service._load_lines(invoice_id))

    assert get_header(ds, invoice_id)['payment_term_id'] == ACCOUNT_TERM_ID
    assert len(rows) == 1


def test_create_hook_fills_supplier_default_only_when_blank(tmp_path, monkeypatch):
    ds = make_env(tmp_path)
    seed_vendor_account(ds, default_payment_term_id=PAYMENT_TERM_ID)
    from meta.api import bo_api
    monkeypatch.setattr(bo_api, '_get_data_source', lambda: ds)

    filled = bo_api._apply_vendor_invoice_defaults(
        'vendor_invoice', {'supplier_account_id': SUPPLIER_ACCOUNT_ID})
    assert filled['payment_term_id'] == PAYMENT_TERM_ID

    explicit = bo_api._apply_vendor_invoice_defaults(
        'vendor_invoice',
        {'supplier_account_id': SUPPLIER_ACCOUNT_ID, 'payment_term_id': 9})
    assert explicit['payment_term_id'] == 9

    other = {'supplier_account_id': SUPPLIER_ACCOUNT_ID}
    assert bo_api._apply_vendor_invoice_defaults('vendor_account', other) is other