# -*- coding: utf-8 -*-
"""T6.1 外部编号校验测试（内存 sqlite，不依赖 DB）。"""

import pytest

from meta.services.document_number_service import (
    DocumentNumberError,
    DocumentNumberService,
)
from meta.tests.document_number_doubles import build_ds, insert_order_no


@pytest.fixture()
def ds():
    connection = build_ds()
    yield connection
    connection.conn.close()


def _payload(document_type_id=1, order_date='2026-11-06'):
    return {'document_type_id': document_type_id, 'order_date': order_date}


def _rule(error):
    return getattr(error.value, 'rule', '')


def test_valid_external_number_passes(ds):
    svc = DocumentNumberService(ds)
    result = svc.validate_external_number(
        'purchase_order', 'PO-202611-0010', _payload(), table_name='purchase_orders')
    assert result == 'PO-202611-0010'


def test_format_mismatch_rejected(ds):
    svc = DocumentNumberService(ds)
    with pytest.raises(DocumentNumberError) as error:
        svc.validate_external_number(
            'purchase_order', 'PO-202610-0010', _payload(),  # 日期段不符
            table_name='purchase_orders')
    assert _rule(error) == 'NUMBER_FORMAT_INVALID'

    with pytest.raises(DocumentNumberError) as error:
        svc.validate_external_number(
            'purchase_order', 'PO-202611-010', _payload(),  # 流水位数不足 4
            table_name='purchase_orders')
    assert _rule(error) == 'NUMBER_FORMAT_INVALID'


def test_below_start_value_rejected(ds):
    svc = DocumentNumberService(ds)
    with pytest.raises(DocumentNumberError) as error:
        svc.validate_external_number(
            'purchase_order', 'PO-202611-0009', _payload(),
            table_name='purchase_orders')
    assert _rule(error) == 'NUMBER_OUT_OF_RANGE'


def test_duplicate_rejected(ds):
    insert_order_no(ds, 'purchase_orders', 'PO-202611-0010')
    svc = DocumentNumberService(ds)
    with pytest.raises(DocumentNumberError) as error:
        svc.validate_external_number(
            'purchase_order', 'PO-202611-0010', _payload(),
            table_name='purchase_orders')
    assert _rule(error) == 'NUMBER_DUPLICATE'


def test_exclude_id_allows_self_update(ds):
    insert_order_no(ds, 'purchase_orders', 'PO-202611-0010', row_id=7)
    svc = DocumentNumberService(ds)
    result = svc.validate_external_number(
        'purchase_order', 'PO-202611-0010', _payload(),
        table_name='purchase_orders', exclude_id=7)
    assert result == 'PO-202611-0010'


def test_extend_mode_allows_longer_but_not_shorter(ds):
    svc = DocumentNumberService(ds)
    payload = _payload(document_type_id=2)
    assert svc.validate_external_number(
        'sales_order', 'SO-1234', payload, table_name='sales_orders') == 'SO-1234'
    with pytest.raises(DocumentNumberError) as error:
        svc.validate_external_number(
            'sales_order', 'SO-12', payload, table_name='sales_orders')
    assert _rule(error) == 'NUMBER_FORMAT_INVALID'


def test_error_mode_rejects_beyond_capacity(ds):
    """on_exhaust=error 时超出 {SEQ:4} 位数即拒绝。"""
    svc = DocumentNumberService(ds)
    with pytest.raises(DocumentNumberError) as error:
        svc.validate_external_number(
            'purchase_order', 'PO-202611-10000', _payload(),
            table_name='purchase_orders')
    assert _rule(error) == 'NUMBER_FORMAT_INVALID'


def test_unbound_sequence_and_unsupported_object(ds):
    svc = DocumentNumberService(ds)
    with pytest.raises(DocumentNumberError) as error:
        svc.validate_external_number(
            'purchase_order', 'PO-202611-0010',
            {'order_date': '2026-11-06'}, table_name='purchase_orders')
    assert _rule(error) == 'NUMBER_SEQUENCE_UNAVAILABLE'

    with pytest.raises(DocumentNumberError) as error:
        svc.validate_external_number(
            'outbound_order', 'OUT-1', {}, table_name='outbound_orders')
    assert _rule(error) == 'NUMBER_SEQUENCE_UNSUPPORTED'
