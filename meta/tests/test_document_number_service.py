# -*- coding: utf-8 -*-
"""单据取号唯一入口：解析序列 / 幂等 / 失败策略。"""

import os

import pytest

os.environ.setdefault('ALLOW_RAW_SQL', '1')

from meta.services.document_number_service import (
    DocumentNumberError,
    DocumentNumberService,
)
from meta.tests.inventory_test_doubles import MemDS, build_db


def _ds(with_sequence=True):
    conn = build_db()
    conn.execute(
        'CREATE TABLE IF NOT EXISTS type_definitions '
        '(id INTEGER PRIMARY KEY, number_sequence_id INTEGER, '
        'scope_bo TEXT, level TEXT)')
    conn.execute(
        'CREATE TABLE IF NOT EXISTS number_sequences '
        '(id INTEGER PRIMARY KEY, code TEXT, pattern TEXT, '
        'scope_fields TEXT, date_field TEXT, start_value INTEGER, '
        'on_exhaust TEXT)')
    if with_sequence:
        conn.execute('INSERT INTO type_definitions '
                     '(id, number_sequence_id) VALUES (1, 11)')
        conn.execute(
            'INSERT INTO number_sequences '
            '(id, code, pattern, scope_fields, date_field, start_value, '
            'on_exhaust) VALUES '
            "(11, 'TO', 'TO-{SEQ:4}', '', 'transfer_date', 1, 'error')")
    conn.commit()
    return MemDS(conn)


def test_allocate_is_idempotent_when_number_present():
    service = DocumentNumberService(_ds(with_sequence=False))
    assert service.allocate_for(
        'transfer_order', {'transfer_order_no': 'TO-1'}, required=True) is None


def test_allocate_uses_type_sequence():
    number = DocumentNumberService(_ds()).allocate_for(
        'transfer_order',
        {'document_type_id': 1, 'transfer_date': '2026-11-06'})
    assert number.startswith('TO-')


def test_missing_sequence_is_silent_by_default():
    service = DocumentNumberService(_ds(with_sequence=False))
    assert service.allocate_for(
        'transfer_order',
        {'document_type_id': 9, 'transfer_date': '2026-11-06'}) is None


def test_missing_sequence_raises_when_required():
    service = DocumentNumberService(_ds(with_sequence=False))
    with pytest.raises(DocumentNumberError) as exc:
        service.allocate_for(
            'transfer_order',
            {'document_type_id': 9, 'transfer_date': '2026-11-06'},
            required=True)
    assert exc.value.rule == 'NUMBER_SEQUENCE_UNAVAILABLE'
    assert exc.value.field_name == 'transfer_order_no'


def test_missing_date_never_hits_sequence():
    service = DocumentNumberService(_ds())
    assert service.allocate_for('transfer_order', {'document_type_id': 1}) is None


def test_shipment_falls_back_to_sequence_code():
    ds = _ds(with_sequence=False)
    ds.execute(
        'INSERT INTO number_sequences '
        '(id, code, pattern, scope_fields, date_field, start_value, '
        'on_exhaust) VALUES '
        "(21, 'TRS', 'TS-{SEQ:4}', '', 'ship_date', 1, 'error')")
    ds.commit()
    number = DocumentNumberService(ds).allocate_for(
        'transfer_shipment', {'ship_date': '2026-11-06'}, required=True)
    assert number.startswith('TS-')


def test_unknown_object_raises():
    with pytest.raises(DocumentNumberError):
        DocumentNumberService(_ds()).allocate_for('no_such_doc', {})
