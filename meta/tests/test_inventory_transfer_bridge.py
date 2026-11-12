# -*- coding: utf-8 -*-
"""INV-1 调拨桥接测试：发货 → ISSUE_TO_SHIP，收货 → RCV_TO，在途派生。

覆盖 spec FR-005 / FR-007 / FR-010 / 9.4 集成口径。
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.services.transfer_order_service import (
    TransferOrderError, TransferOrderService,
)
from meta.services.transfer_shipment_service import TransferShipmentService
from meta.tests import inventory_test_doubles as inv
from meta.tests import transfer_order_test_doubles as tod

TO_ID = 1
TO_LINE_ID = 100
STOCK_LOCATION = 9   # 属调出组织 2
RECEIPT_LOCATION = 10  # 属调入组织 3


def _seeded(status='released', enable=True):
    conn = tod.seeded_db(line_qtys=(100.0,), status=status)
    inv.install_inventory(conn, enable=enable)
    conn.execute(
        'UPDATE transfer_orders SET from_location_id = ?, to_location_id = ? '
        'WHERE id = ?', [STOCK_LOCATION, RECEIPT_LOCATION, TO_ID])
    conn.commit()
    return conn


def _seed_stock(conn, qty=100.0):
    """期初库存：org2 / location9 / item900。"""
    inv.posting_service(conn).post([{
        'transaction_type': 'OPENING',
        'transaction_date': '2026-11-01',
        'org_id': 2,
        'location_id': STOCK_LOCATION,
        'item_id': 900,
        'uom_id': 3,
        'qty': qty,
        'source_line_id': 1,
    }], {
        'source_doc_type': 'inventory_opening',
        'source_doc_id': 1,
        'source_event_key': 'opening:BRIDGE',
    })


def _transactions(conn):
    return inv.MemDS(conn).query(
        'SELECT t.*, ty.code AS type_code '
        'FROM inventory_transactions t '
        'JOIN inventory_transaction_types ty ON ty.id = t.transaction_type_id '
        'ORDER BY t.id')


def _line(conn):
    return inv.MemDS(conn).query(
        'SELECT * FROM transfer_order_lines WHERE id = ?', [TO_LINE_ID])[0]


def _on_hand(conn, org_id, location_id):
    rows = inv.MemDS(conn).query(
        'SELECT qty_on_hand FROM inventory_balances WHERE org_id = ? '
        'AND location_id = ? AND item_id = 900 AND batch_id = 0 '
        "AND stock_status = 'unrestricted'", [org_id, location_id])
    return rows[0]['qty_on_hand'] if rows else 0.0


# ---------------- 发货出账 ----------------

def test_ship_writes_issue_to_ship_and_decrements_balance():
    conn = _seeded()
    _seed_stock(conn)

    TransferOrderService(inv.MemDS(conn)).ship(
        TO_ID, [{'line_id': TO_LINE_ID, 'qty': 100.0,
                 'ship_date': '2026-11-03'}])

    tx = _transactions(conn)
    assert [row['type_code'] for row in tx] == ['OPENING', 'ISSUE_TO_SHIP']
    issue = tx[1]
    assert issue['direction'] == 'out'
    assert issue['qty'] == 100.0
    assert issue['org_id'] == 2
    assert issue['location_id'] == STOCK_LOCATION
    assert issue['source_event_key'] == 'transfer_order:1:ship:1'

    assert _on_hand(conn, 2, STOCK_LOCATION) == 0.0
    assert _line(conn)['qty_shipped'] == 100.0


def test_ship_negative_stock_rolls_back_whole_action():
    conn = _seeded()

    with pytest.raises(TransferOrderError) as exc:
        TransferOrderService(inv.MemDS(conn)).ship(
            TO_ID, [{'line_id': TO_LINE_ID, 'qty': 100.0,
                     'ship_date': '2026-11-03'}])
    assert exc.value.rule == 'INV_NEGATIVE_STOCK'
    assert exc.value.field_name == 'inventory'
    assert _transactions(conn) == []
    assert _line(conn)['qty_shipped'] == 0.0


def test_ship_skips_inventory_when_switch_off():
    conn = _seeded(enable=False)
    inv.set_param(conn, 'inventory_posting_enabled', '0')

    TransferOrderService(inv.MemDS(conn)).ship(
        TO_ID, [{'line_id': TO_LINE_ID, 'qty': 100.0,
                 'ship_date': '2026-11-03'}])

    assert _transactions(conn) == []
    assert _line(conn)['qty_shipped'] == 100.0


def test_shipment_post_delegates_to_ship_once():
    conn = _seeded()
    _seed_stock(conn)
    svc = TransferShipmentService(inv.MemDS(conn))

    shipment = svc.create(TO_ID, '2026-11-03',
                          [{'transfer_order_line_id': TO_LINE_ID, 'qty': 50.0}])
    svc.post(shipment['id'])

    issues = [row for row in _transactions(conn)
              if row['type_code'] == 'ISSUE_TO_SHIP']
    assert len(issues) == 1
    assert issues[0]['qty'] == 50.0
    assert _line(conn)['qty_shipped'] == 50.0
    assert _on_hand(conn, 2, STOCK_LOCATION) == 50.0


def test_shipment_cancel_writes_no_inventory():
    conn = _seeded()
    svc = TransferShipmentService(inv.MemDS(conn))
    shipment = svc.create(TO_ID, '2026-11-03',
                          [{'transfer_order_line_id': TO_LINE_ID, 'qty': 50.0}])
    svc.cancel(shipment['id'])

    assert _transactions(conn) == []
    assert _line(conn)['qty_shipped'] == 0.0


def test_transfer_order_cancel_writes_no_inventory():
    conn = _seeded(status='draft')
    TransferOrderService(inv.MemDS(conn)).cancel(TO_ID)

    assert _transactions(conn) == []


# ---------------- 在途派生 ----------------

def test_in_transit_derived_from_transfer_lines():
    conn = _seeded()
    _seed_stock(conn)
    svc = TransferOrderService(inv.MemDS(conn))
    svc.ship(TO_ID, [{'line_id': TO_LINE_ID, 'qty': 60.0,
                      'ship_date': '2026-11-03'}])

    posting = inv.posting_service(conn)
    rows = posting.in_transit(org_id=2)
    assert rows == [{'item_id': 900, 'outbound': 60.0, 'inbound': 0.0}]

    svc.apply_receipt(TO_ID, [{'line_id': TO_LINE_ID, 'qty_received': 60.0}])
    assert posting.in_transit(org_id=2) == []


# ---------------- 全链路：发货 → 收货 ----------------

def test_full_transfer_cycle_posts_issue_then_receipt():
    conn = _seeded()
    _seed_stock(conn)
    order_svc = TransferOrderService(inv.MemDS(conn))
    order_svc.ship(TO_ID, [{'line_id': TO_LINE_ID, 'qty': 100.0,
                            'ship_date': '2026-11-03'}])

    receipt = tod.receipt_svc(conn).create_from_transfer_order(TO_ID)
    tod.receipt_svc(conn).post(receipt['id'])

    tx = _transactions(conn)
    assert [row['type_code'] for row in tx] == [
        'OPENING', 'ISSUE_TO_SHIP', 'RCV_TO']
    receipt_tx = tx[2]
    assert receipt_tx['direction'] == 'in'
    assert receipt_tx['org_id'] == 3
    assert receipt_tx['location_id'] == RECEIPT_LOCATION

    assert _on_hand(conn, 2, STOCK_LOCATION) == 0.0
    assert _on_hand(conn, 3, RECEIPT_LOCATION) == 100.0


def test_smoke_cycle_reversal_and_reconciliation():
    """期初 → 发货 → 收货 → 红冲 → 对账/重建。"""
    conn = _seeded()
    _seed_stock(conn, 100.0)
    order_svc = TransferOrderService(inv.MemDS(conn))
    order_svc.ship(TO_ID, [{'line_id': TO_LINE_ID, 'qty': 100.0,
                            'ship_date': '2026-11-03'}])
    receipt_svc = tod.receipt_svc(conn)
    receipt = receipt_svc.create_from_transfer_order(TO_ID)
    receipt_svc.post(receipt['id'])
    receipt_svc.reverse(receipt['id'])

    assert [row['type_code'] for row in _transactions(conn)] == [
        'OPENING', 'ISSUE_TO_SHIP', 'RCV_TO', 'REVERSAL']
    assert _on_hand(conn, 3, RECEIPT_LOCATION) == 0.0

    posting = inv.posting_service(conn)
    report = posting.diff_report()
    assert report['ok'] is True and report['diff_count'] == 0

    conn.execute(
        'UPDATE inventory_balances SET qty_on_hand = qty_on_hand + 5 '
        'WHERE org_id = 3')
    conn.commit()
    assert posting.diff_report()['diff_count'] == 1

    posting.rebuild_balances()
    assert posting.diff_report()['ok'] is True
