# -*- coding: utf-8 -*-
"""调拨单服务测试（spec-transfer-order-object-model §6 / §7 / §10）

覆盖：release / ship / cancel / close 状态机，履约派生，收货回写与红冲回退。
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.services.transfer_order_service import TransferOrderError
from meta.tests.transfer_order_test_doubles import (MemDS, release_transfer_order,
                                                   seeded_db, to_service)

LINE_ID = 100
ORDER_ID = 1


def _header(conn, oid=ORDER_ID):
    return MemDS(conn).query(
        'SELECT * FROM transfer_orders WHERE id = ?', [oid])[0]


def _line(conn, lid=LINE_ID):
    return MemDS(conn).query(
        'SELECT * FROM transfer_order_lines WHERE id = ?', [lid])[0]


def _single_line_db(**kwargs):
    return seeded_db(line_qtys=(100.0,), **kwargs)


def _released(shipped=100.0):
    conn = _single_line_db()
    release_transfer_order(conn, ORDER_ID, {LINE_ID: shipped})
    return conn


# ---------------------------------------------------------------------------
# release
# ---------------------------------------------------------------------------
def test_release_draft_to_released():
    conn = _single_line_db()
    result = to_service(conn).release(ORDER_ID)

    assert result['status'] == 'released'
    assert result['idempotent'] is False
    assert result['line_count'] == 1
    assert _header(conn)['status'] == 'released'


def test_release_requires_lines():
    conn = seeded_db(line_qtys=())
    with pytest.raises(TransferOrderError) as exc:
        to_service(conn).release(ORDER_ID)
    assert exc.value.rule == 'TO_NO_LINES'


def test_release_is_idempotent():
    conn = _single_line_db()
    svc = to_service(conn)
    svc.release(ORDER_ID)
    result = svc.release(ORDER_ID)

    assert result['status'] == 'released'
    assert result['idempotent'] is True


def test_release_rejects_terminal_status():
    conn = seeded_db(line_qtys=(100.0,), status='cancelled')
    with pytest.raises(TransferOrderError) as exc:
        to_service(conn).release(ORDER_ID)
    assert exc.value.rule == 'TO_TERMINAL_IMMUTABLE'


# ---------------------------------------------------------------------------
# ship
# ---------------------------------------------------------------------------
def test_ship_requires_released():
    conn = _single_line_db()
    with pytest.raises(TransferOrderError) as exc:
        to_service(conn).ship(ORDER_ID, [{'line_id': LINE_ID, 'qty': 10}])
    assert exc.value.rule == 'TO_STATE_INVALID'


def test_ship_accumulates_and_sets_first_ship_date():
    conn = _released(shipped=0.0)
    svc = to_service(conn)

    svc.ship(ORDER_ID, [{'line_id': LINE_ID, 'qty': 40,
                         'ship_date': '2026-11-05'}])
    assert _line(conn)['qty_shipped'] == pytest.approx(40.0)
    assert _header(conn)['fulfillment_status'] == 'partially_shipped'

    svc.ship(ORDER_ID, [{'line_id': LINE_ID, 'qty': 60}])
    line = _line(conn)
    assert line['qty_shipped'] == pytest.approx(100.0)
    assert line['fulfillment_status'] == 'shipped'
    assert _header(conn)['fulfillment_status'] == 'shipped'
    # 首次发货日期不被后续发货覆盖
    assert _header(conn)['actual_ship_date'] == '2026-11-05'


def test_ship_rejects_exceeding_plan_and_rolls_back():
    conn = _released(shipped=0.0)
    svc = to_service(conn)
    svc.ship(ORDER_ID, [{'line_id': LINE_ID, 'qty': 40}])

    with pytest.raises(TransferOrderError) as exc:
        svc.ship(ORDER_ID, [{'line_id': LINE_ID, 'qty': 70}])
    assert exc.value.rule == 'TO_SHIP_QTY_EXCEEDED'
    assert _line(conn)['qty_shipped'] == pytest.approx(40.0)


def test_ship_rejects_non_positive_qty():
    conn = _released()
    with pytest.raises(TransferOrderError) as exc:
        to_service(conn).ship(ORDER_ID, [{'line_id': LINE_ID, 'qty': 0}])
    assert exc.value.rule == 'TO_SHIP_QTY_POSITIVE'


# ---------------------------------------------------------------------------
# cancel
# ---------------------------------------------------------------------------
def test_cancel_draft_marks_lines_cancelled():
    conn = _single_line_db()
    result = to_service(conn).cancel(ORDER_ID)

    assert result['status'] == 'cancelled'
    assert _header(conn)['status'] == 'cancelled'
    assert _line(conn)['status'] == 'cancelled'


def test_cancel_released_without_shipment():
    conn = _released(shipped=0.0)
    result = to_service(conn).cancel(ORDER_ID)

    assert result['status'] == 'cancelled'
    assert _line(conn)['status'] == 'cancelled'


def test_cancel_rejects_shipped_order():
    conn = _released(shipped=40.0)
    with pytest.raises(TransferOrderError) as exc:
        to_service(conn).cancel(ORDER_ID)
    assert exc.value.rule == 'TO_SHIPPED_CANNOT_CANCEL'


def test_cancel_is_idempotent():
    conn = _single_line_db()
    svc = to_service(conn)
    svc.cancel(ORDER_ID)
    result = svc.cancel(ORDER_ID)
    assert result['status'] == 'cancelled'
    assert result['idempotent'] is True


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------
def test_close_requires_released():
    conn = _single_line_db()
    with pytest.raises(TransferOrderError) as exc:
        to_service(conn).close(ORDER_ID)
    assert exc.value.rule == 'TO_STATE_INVALID'


def test_close_rejects_in_transit_balance():
    conn = _released(shipped=50.0)
    with pytest.raises(TransferOrderError) as exc:
        to_service(conn).close(ORDER_ID)
    assert exc.value.rule == 'TO_IN_TRANSIT_NOT_EMPTY'


def test_close_rejects_nothing_received():
    conn = _released(shipped=0.0)
    with pytest.raises(TransferOrderError) as exc:
        to_service(conn).close(ORDER_ID)
    assert exc.value.rule == 'TO_NOTHING_RECEIVED'


def test_close_short_receipt_succeeds():
    conn = _released(shipped=80.0)
    conn.execute('UPDATE transfer_order_lines SET qty_received = 80 '
                 'WHERE id = ?', [LINE_ID])
    conn.commit()

    result = to_service(conn).close(ORDER_ID)

    assert result['status'] == 'closed'
    header = _header(conn)
    assert header['status'] == 'closed'
    assert header['fulfillment_status'] == 'partially_received'
    assert _line(conn)['status'] == 'closed'


def test_close_is_idempotent():
    conn = _released(shipped=80.0)
    conn.execute('UPDATE transfer_order_lines SET qty_received = 80 '
                 'WHERE id = ?', [LINE_ID])
    conn.commit()
    svc = to_service(conn)
    svc.close(ORDER_ID)
    result = svc.close(ORDER_ID)
    assert result['status'] == 'closed'
    assert result['idempotent'] is True


# ---------------------------------------------------------------------------
# recompute_fulfillment
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('shipped,received,expected', [
    (0.0, 0.0, 'open'),
    (40.0, 0.0, 'partially_shipped'),
    (100.0, 0.0, 'shipped'),
    (100.0, 40.0, 'partially_received'),
    (100.0, 100.0, 'received'),
])
def test_recompute_fulfillment_derives_header_and_line(shipped, received,
                                                       expected):
    conn = _released(shipped=shipped)
    conn.execute('UPDATE transfer_order_lines SET qty_received = ? '
                 'WHERE id = ?', [received, LINE_ID])
    conn.commit()

    derived = to_service(conn).recompute_fulfillment(ORDER_ID)

    assert derived == expected
    assert _header(conn)['fulfillment_status'] == expected
    assert _line(conn)['fulfillment_status'] == expected


# ---------------------------------------------------------------------------
# apply_receipt / reverse_receipt
# ---------------------------------------------------------------------------
def test_apply_receipt_accumulates_qty():
    conn = _released()
    result = to_service(conn).apply_receipt(
        ORDER_ID, [{'line_id': LINE_ID, 'qty_received': 40}])

    assert result['status'] == 'released'
    assert result['fulfillment_status'] == 'partially_received'
    assert _line(conn)['qty_received'] == pytest.approx(40.0)


def test_apply_receipt_rejects_qty_over_shipped():
    conn = _released()
    conn.execute('UPDATE transfer_order_lines SET qty_received = 40 '
                 'WHERE id = ?', [LINE_ID])
    conn.commit()

    with pytest.raises(TransferOrderError) as exc:
        to_service(conn).apply_receipt(
            ORDER_ID, [{'line_id': LINE_ID, 'qty_received': 70}])
    assert exc.value.rule == 'TO_RECEIVE_EXCEEDED'
    assert _line(conn)['qty_received'] == pytest.approx(40.0)


def test_apply_receipt_full_auto_closes_order():
    conn = _released()
    result = to_service(conn).apply_receipt(
        ORDER_ID, [{'line_id': LINE_ID, 'qty_received': 100}])

    assert result['status'] == 'closed'
    assert result['fulfillment_status'] == 'received'
    header = _header(conn)
    assert header['status'] == 'closed'
    assert header['fulfillment_status'] == 'received'
    line = _line(conn)
    assert line['qty_received'] == pytest.approx(100.0)
    assert line['status'] == 'closed'


def test_apply_receipt_requires_released():
    conn = _single_line_db()
    with pytest.raises(TransferOrderError) as exc:
        to_service(conn).apply_receipt(
            ORDER_ID, [{'line_id': LINE_ID, 'qty_received': 10}])
    assert exc.value.rule == 'TO_STATE_INVALID'


def test_reverse_receipt_reopens_auto_closed_order():
    conn = _released()
    svc = to_service(conn)
    svc.apply_receipt(ORDER_ID, [{'line_id': LINE_ID, 'qty_received': 100}])

    result = svc.reverse_receipt(ORDER_ID, [{'line_id': LINE_ID, 'qty': 40}])

    assert result['status'] == 'released'
    assert result['fulfillment_status'] == 'partially_received'
    assert _header(conn)['status'] == 'released'
    line = _line(conn)
    assert line['status'] == 'open'
    assert line['qty_received'] == pytest.approx(60.0)


def test_reverse_receipt_keeps_manual_close():
    """短收结案（手工 close）不是收货自动关闭，红冲后仍保持 closed。"""
    conn = _released(shipped=80.0)
    conn.execute('UPDATE transfer_order_lines SET qty_received = 80 '
                 'WHERE id = ?', [LINE_ID])
    conn.commit()
    svc = to_service(conn)
    svc.close(ORDER_ID)
    assert _header(conn)['fulfillment_status'] == 'partially_received'

    svc.reverse_receipt(ORDER_ID, [{'line_id': LINE_ID, 'qty': 80}])

    header = _header(conn)
    assert header['status'] == 'closed'
    line = _line(conn)
    assert line['status'] == 'closed'
    assert line['qty_received'] == pytest.approx(0.0)
