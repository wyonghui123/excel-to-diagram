# -*- coding: utf-8 -*-
"""调拨单守卫测试（spec-transfer-order-object-model §10 R-TO-0 ~ R-TO-13）

覆盖：头类型 / 组织 / 同一法人 / 行类型与物料 / 数量区间 / 状态限制 /
行号自动生成 / 删除 / 更新冻结。
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.services.transfer_order_service import TransferOrderError
from meta.tests.transfer_order_test_doubles import (
    TO_GOODS_TYPE_ID, TO_STANDARD_TYPE_ID, MemDS, add_transfer_order,
    release_transfer_order, seeded_db, to_guard)

ORDER_ID = 1
LINE_ID = 100


def _header_data(**extra):
    data = {
        'document_type_id': TO_STANDARD_TYPE_ID,
        'transfer_date': '2026-11-01',
        'from_org_id': 2,
        'to_org_id': 3,
    }
    data.update(extra)
    return data


def _line_data(**extra):
    data = {
        'line_type_id': TO_GOODS_TYPE_ID,
        'item_id': 900,
        'uom_id': 3,
        'qty': 100.0,
    }
    data.update(extra)
    return data


def _header_row(conn, oid=ORDER_ID):
    return MemDS(conn).query(
        'SELECT * FROM transfer_orders WHERE id = ?', [oid])[0]


def _persist_line(conn, lid, oid, values):
    conn.execute(
        'INSERT INTO transfer_order_lines (id, transfer_order_id, line_no, '
        'line_type_id, item_id, uom_id, qty, qty_shipped, qty_received, status) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [lid, oid, values['line_no'], values['line_type_id'],
         values['item_id'], values['uom_id'], values['qty'],
         values['qty_shipped'], values['qty_received'], 'open'])


# ---------------------------------------------------------------------------
# 头：类型 / 日期 / 组织 / 法人 / 库位
# ---------------------------------------------------------------------------
def test_create_requires_header_type():
    conn = seeded_db()
    data = _header_data()
    data.pop('document_type_id')
    with pytest.raises(TransferOrderError) as exc:
        to_guard(conn).validate_create(data)
    assert exc.value.rule == 'TO_DOCUMENT_TYPE_REQUIRED'


def test_create_rejects_unknown_header_type():
    conn = seeded_db()
    with pytest.raises(TransferOrderError) as exc:
        to_guard(conn).validate_create(_header_data(document_type_id=999))
    assert exc.value.rule == 'TO_DOCUMENT_TYPE_NOT_FOUND'


def test_create_rejects_non_transfer_order_type():
    """收货单头类型（scope_bo=receipt）不得用于调拨单。"""
    conn = seeded_db()
    with pytest.raises(TransferOrderError) as exc:
        to_guard(conn).validate_create(_header_data(document_type_id=1))
    assert exc.value.rule == 'TO_HEADER_TYPE_INVALID'
    assert exc.value.field_name == 'document_type_id'


def test_create_rejects_line_type_as_header():
    conn = seeded_db()
    with pytest.raises(TransferOrderError) as exc:
        to_guard(conn).validate_create(
            _header_data(document_type_id=TO_GOODS_TYPE_ID))
    assert exc.value.rule == 'TO_HEADER_TYPE_INVALID'


def test_create_requires_transfer_date():
    conn = seeded_db()
    data = _header_data()
    data.pop('transfer_date')
    with pytest.raises(TransferOrderError) as exc:
        to_guard(conn).validate_create(data)
    assert exc.value.rule == 'TO_DATE_REQUIRED'


def test_create_requires_both_orgs():
    conn = seeded_db()
    data = _header_data()
    data.pop('to_org_id')
    with pytest.raises(TransferOrderError) as exc:
        to_guard(conn).validate_create(data)
    assert exc.value.rule == 'TO_ORG_REQUIRED'
    assert exc.value.field_name == 'to_org_id'


def test_create_rejects_same_org():
    conn = seeded_db()
    with pytest.raises(TransferOrderError) as exc:
        to_guard(conn).validate_create(_header_data(to_org_id=2))
    assert exc.value.rule == 'TO_ORG_SAME'
    assert exc.value.field_name == 'to_org_id'


def test_create_rejects_missing_org():
    conn = seeded_db()
    with pytest.raises(TransferOrderError) as exc:
        to_guard(conn).validate_create(_header_data(from_org_id=999))
    assert exc.value.rule == 'TO_ORG_NOT_FOUND'
    assert exc.value.field_name == 'from_org_id'


def test_create_rejects_inactive_org():
    conn = seeded_db()
    with pytest.raises(TransferOrderError) as exc:
        to_guard(conn).validate_create(_header_data(from_org_id=4))
    assert exc.value.rule == 'TO_ORG_INACTIVE'


def test_create_rejects_org_without_inventory_function():
    conn = seeded_db()
    with pytest.raises(TransferOrderError) as exc:
        to_guard(conn).validate_create(_header_data(from_org_id=5))
    assert exc.value.rule == 'TO_ORG_NOT_INVENTORY'


def test_create_resolves_same_legal_entity():
    conn = seeded_db()
    header = to_guard(conn).validate_create(_header_data())
    assert header['legal_entity_id'] == 1


def test_create_rejects_cross_legal_entity():
    conn = seeded_db()
    with pytest.raises(TransferOrderError) as exc:
        to_guard(conn).validate_create(_header_data(to_org_id=11))
    assert exc.value.rule == 'TO_CROSS_LEGAL_ENTITY'
    assert exc.value.field_name == 'to_org_id'


def test_create_rejects_unresolved_legal_entity():
    conn = seeded_db()
    with pytest.raises(TransferOrderError) as exc:
        to_guard(conn).validate_create(_header_data(from_org_id=6))
    assert exc.value.rule == 'TO_LEGAL_ENTITY_UNRESOLVED'
    assert exc.value.field_name == 'from_org_id'


def test_create_rejects_same_location():
    conn = seeded_db()
    with pytest.raises(TransferOrderError) as exc:
        to_guard(conn).validate_create(
            _header_data(from_location_id=7, to_location_id=7))
    assert exc.value.rule == 'TO_LOCATION_SAME'
    assert exc.value.field_name == 'to_location_id'


# ---------------------------------------------------------------------------
# 行：类型 / 物料 / 数量 / 状态
# ---------------------------------------------------------------------------
def test_line_requires_line_type():
    conn = seeded_db()
    data = _line_data()
    data.pop('line_type_id')
    with pytest.raises(TransferOrderError) as exc:
        to_guard(conn).validate_line(data, ORDER_ID)
    assert exc.value.rule == 'TO_LINE_TYPE_REQUIRED'


def test_line_rejects_po_line_type():
    conn = seeded_db()
    with pytest.raises(TransferOrderError) as exc:
        to_guard(conn).validate_line(_line_data(line_type_id=10), ORDER_ID)
    assert exc.value.rule == 'TO_LINE_TYPE_INVALID'


def test_line_rejects_service_item():
    conn = seeded_db()
    with pytest.raises(TransferOrderError) as exc:
        to_guard(conn).validate_line(_line_data(item_id=901), ORDER_ID)
    assert exc.value.rule == 'TO_ITEM_TYPE_INVALID'
    assert exc.value.field_name == 'item_id'


def test_line_rejects_inactive_item():
    conn = seeded_db()
    with pytest.raises(TransferOrderError) as exc:
        to_guard(conn).validate_line(_line_data(item_id=902), ORDER_ID)
    assert exc.value.rule == 'TO_ITEM_INACTIVE'


@pytest.mark.parametrize('qty', [0, -5])
def test_line_rejects_non_positive_qty(qty):
    conn = seeded_db()
    with pytest.raises(TransferOrderError) as exc:
        to_guard(conn).validate_line(_line_data(qty=qty), ORDER_ID)
    assert exc.value.rule == 'TO_LINE_QTY_POSITIVE'
    assert exc.value.field_name == 'qty'


def test_line_rejects_shipped_over_qty():
    conn = seeded_db()
    with pytest.raises(TransferOrderError) as exc:
        to_guard(conn).validate_line(
            _line_data(qty_shipped=120), ORDER_ID)
    assert exc.value.rule == 'TO_LINE_SHIPPED_RANGE'


def test_line_rejects_received_over_shipped():
    conn = seeded_db()
    with pytest.raises(TransferOrderError) as exc:
        to_guard(conn).validate_line(
            _line_data(qty_shipped=10, qty_received=20), ORDER_ID)
    assert exc.value.rule == 'TO_LINE_RECEIVED_RANGE'


def test_line_only_editable_on_draft_header():
    conn = seeded_db()
    release_transfer_order(conn, ORDER_ID)
    with pytest.raises(TransferOrderError) as exc:
        to_guard(conn).validate_line(_line_data(), ORDER_ID)
    assert exc.value.rule == 'TO_LINE_ONLY_DRAFT'
    assert exc.value.field_name == 'transfer_order_id'


def test_line_immutable_on_terminal_header():
    conn = seeded_db(status='cancelled')
    with pytest.raises(TransferOrderError) as exc:
        to_guard(conn).validate_line(_line_data(), ORDER_ID)
    assert exc.value.rule == 'TO_TERMINAL_IMMUTABLE'


def test_line_auto_numbers_in_steps_of_ten():
    conn = seeded_db(line_qtys=())
    add_transfer_order(conn, oid=2, order_no='TRF-202611-000002')
    conn.commit()
    guard = to_guard(conn)

    for index in range(3):
        values = guard.validate_line(_line_data(), 2)
        assert values['line_no'] == 10 * (index + 1)
        _persist_line(conn, 200 + index, 2, values)

    line_nos = [row['line_no'] for row in MemDS(conn).query(
        'SELECT line_no FROM transfer_order_lines WHERE transfer_order_id = ? '
        'ORDER BY line_no', [2])]
    assert line_nos == [10, 20, 30]


# ---------------------------------------------------------------------------
# 删除 / 更新
# ---------------------------------------------------------------------------
def test_delete_only_draft():
    conn = seeded_db()
    assert to_guard(conn).validate_delete(ORDER_ID) is None

    release_transfer_order(conn, ORDER_ID)
    with pytest.raises(TransferOrderError) as exc:
        to_guard(conn).validate_delete(ORDER_ID)
    assert exc.value.rule == 'TO_DELETE_ONLY_DRAFT'
    assert exc.value.field_name == 'status'


def test_delete_missing_order():
    conn = seeded_db()
    with pytest.raises(TransferOrderError) as exc:
        to_guard(conn).validate_delete(999)
    assert exc.value.rule == 'TO_NOT_FOUND'


def test_update_draft_recomputes_legal_entity():
    conn = seeded_db()
    guard = to_guard(conn)
    old = _header_row(conn)

    result = guard.validate_update({'from_org_id': 12}, old)

    assert result == {'legal_entity_id': 1}


def test_update_released_freezes_key_fields():
    conn = seeded_db()
    release_transfer_order(conn, ORDER_ID)
    guard = to_guard(conn)
    old = _header_row(conn)

    with pytest.raises(TransferOrderError) as exc:
        guard.validate_update({'transfer_date': '2026-12-01'}, old)
    assert exc.value.rule == 'TO_FIELD_IMMUTABLE'
    assert exc.value.field_name == 'transfer_date'


def test_update_released_allows_non_frozen_fields():
    conn = seeded_db()
    release_transfer_order(conn, ORDER_ID)
    guard = to_guard(conn)
    old = _header_row(conn)

    assert guard.validate_update({'remark': '补录备注'}, old) == {}


def test_update_rejects_direct_status_change():
    conn = seeded_db()
    release_transfer_order(conn, ORDER_ID)
    guard = to_guard(conn)
    old = _header_row(conn)

    with pytest.raises(TransferOrderError) as exc:
        guard.validate_update({'status': 'closed'}, old)
    assert exc.value.rule == 'TO_STATUS_ACTION_REQUIRED'
    assert exc.value.field_name == 'status'


def test_update_rejects_terminal_order():
    conn = seeded_db(status='closed')
    guard = to_guard(conn)
    old = _header_row(conn)

    with pytest.raises(TransferOrderError) as exc:
        guard.validate_update({'remark': 'x'}, old)
    assert exc.value.rule == 'TO_TERMINAL_IMMUTABLE'
