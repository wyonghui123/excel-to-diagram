# -*- coding: utf-8 -*-
"""收货 / 完工 / 发运 / 红冲接线（spec §11.5）。

门控口径：HU 三表缺失时所有钩子 no-op，不改变旧行为。

ALLOW_RAW_SQL: 收货 / 发运抬头与行需原生 INSERT 造夹具；仅豁免本文件。
"""

import pytest

pytestmark = pytest.mark.unit

from meta.services.handling_unit_service import HandlingUnitError  # noqa: E402
from meta.tests.hu_test_doubles import (  # noqa: E402
    add_item,
    add_serial,
    build_db,
    ds,
    link_receipt_serial,
    service,
)


def _receipt_with_hu(conn, hu_no='HU-R'):
    conn.execute(
        'INSERT INTO receipts (id, receipt_no, inventory_org_id, '
        "deliver_to_location_id, status) VALUES (1, 'RC-1', 1, 7, 'posted')")
    conn.execute(
        'INSERT INTO receipt_lines (id, receipt_id, item_id, uom_id, '
        'qty_received, qty_rejected, putaway_location_id, hu_no, hu_type, '
        "status) VALUES (1, 1, 900, 1, 1, 0, 7, ?, 'carton', 'posted')",
        [hu_no])


def test_pack_receipt_skips_without_hu_tables():
    conn = build_db(with_hu=False)
    result = service(conn).pack_receipt(1)
    assert result == {'skipped': True, 'packed': 0}


def test_pack_receipt_creates_hu_and_packs_serial():
    conn = build_db()
    add_item(conn)
    serial_id = add_serial(conn)
    _receipt_with_hu(conn)
    link_receipt_serial(conn, 1, 1, serial_id)

    result = service(conn).pack_receipt(1)
    assert result['packed'] == 1

    hu = ds(conn).query('SELECT * FROM handling_units WHERE hu_no = ?',
                        ['HU-R'])[0]
    assert hu['org_id'] == 1
    assert hu['location_id'] == 7
    assert hu['source_doc_type'] == 'receipt'
    contents = service(conn).hu_contents('HU-R', org_id=1)['items']
    assert contents[0]['serial_no'] == 'SN-001'

    # 重复过账同一单据：不重复装箱
    assert service(conn).pack_receipt(1)['packed'] == 1
    assert len(service(conn).hu_contents('HU-R', org_id=1)['items']) == 1


def test_pack_receipt_moves_sealed_hu_same_org():
    """同组织调拨收货：命中已密封 HU 时整体 move，不拆箱重装。"""
    conn = build_db()
    add_item(conn)
    serial_id = add_serial(conn)
    svc = service(conn)
    hu = svc.create_hu({'hu_no': 'HU-T', 'org_id': 1, 'location_id': 7})
    svc.pack(hu['id'], [{'serial_id': serial_id}])
    svc.seal(hu['id'])

    conn.execute(
        'INSERT INTO receipts (id, receipt_no, inventory_org_id, '
        "deliver_to_location_id, status) VALUES (1, 'RC-T', 1, 8, 'posted')")
    conn.execute(
        'INSERT INTO receipt_lines (id, receipt_id, item_id, uom_id, '
        'qty_received, qty_rejected, putaway_location_id, hu_no, hu_type, '
        "status) VALUES (1, 1, 900, 1, 1, 0, 8, 'HU-T', 'carton', 'posted')")

    result = svc.pack_receipt(1)
    assert result['packed'] == 1
    row = ds(conn).query('SELECT status, location_id FROM handling_units '
                         'WHERE id = ?', [hu['id']])[0]
    assert row['status'] == 'sealed'
    assert row['location_id'] == 8


def test_ship_shipment_requires_sealed_hu():
    conn = build_db()
    add_item(conn)
    serial_id = add_serial(conn)
    _receipt_with_hu(conn, hu_no='HU-OPEN')
    link_receipt_serial(conn, 1, 1, serial_id)
    svc = service(conn)
    svc.pack_receipt(1)
    conn.execute(
        'INSERT INTO shipments (id, delivery_no, ship_from_location_id, '
        "status) VALUES (1, 'DN-1', 7, 'confirmed')")
    conn.execute(
        'INSERT INTO shipment_lines (id, delivery_id, item_id, qty, hu_no, '
        "status) VALUES (1, 1, 900, 1, 'HU-OPEN', 'confirmed')")

    with pytest.raises(HandlingUnitError) as exc:
        svc.ship_shipment(1)
    assert exc.value.rule == 'HU_SHIP_STATUS_INVALID'


def test_ship_shipment_marks_hu_and_serial_shipped():
    conn = build_db()
    add_item(conn)
    serial_id = add_serial(conn)
    _receipt_with_hu(conn, hu_no='HU-R')
    link_receipt_serial(conn, 1, 1, serial_id)
    svc = service(conn)
    svc.pack_receipt(1)
    hu = ds(conn).query('SELECT id FROM handling_units WHERE hu_no = ?',
                        ['HU-R'])[0]
    svc.seal(hu['id'])

    conn.execute(
        'INSERT INTO shipments (id, delivery_no, ship_from_location_id, '
        "status) VALUES (1, 'DN-1', 7, 'confirmed')")
    conn.execute(
        'INSERT INTO shipment_lines (id, delivery_id, item_id, qty, hu_no, '
        "status) VALUES (1, 1, 900, 1, 'HU-R', 'confirmed')")
    result = svc.ship_shipment(1)
    assert result['shipped'] == 1

    hu_row = ds(conn).query('SELECT status, shipped_at FROM handling_units '
                            'WHERE id = ?', [hu['id']])[0]
    serial = ds(conn).query('SELECT usage_status, current_location_id '
                            'FROM serial_numbers WHERE id = ?', [serial_id])[0]
    assert hu_row['status'] == 'shipped'
    assert hu_row['shipped_at']
    assert serial['usage_status'] == 'shipped'
    assert serial['current_location_id'] is None


def test_reverse_shipment_restores_sealed_and_in_stores():
    conn = build_db()
    add_item(conn)
    serial_id = add_serial(conn)
    _receipt_with_hu(conn, hu_no='HU-R')
    link_receipt_serial(conn, 1, 1, serial_id)
    svc = service(conn)
    svc.pack_receipt(1)
    hu = ds(conn).query('SELECT id FROM handling_units WHERE hu_no = ?',
                        ['HU-R'])[0]
    svc.seal(hu['id'])
    conn.execute(
        'INSERT INTO shipments (id, delivery_no, ship_from_location_id, '
        "status) VALUES (1, 'DN-1', 7, 'confirmed')")
    conn.execute(
        'INSERT INTO shipment_lines (id, delivery_id, item_id, qty, hu_no, '
        "status) VALUES (1, 1, 900, 1, 'HU-R', 'confirmed')")
    svc.ship_shipment(1)

    result = svc.reverse_document('shipment', 1)
    assert result['reversed'] >= 1
    hu_row = ds(conn).query('SELECT status, shipped_at FROM handling_units '
                            'WHERE id = ?', [hu['id']])[0]
    serial = ds(conn).query('SELECT usage_status, current_location_id '
                            'FROM serial_numbers WHERE id = ?', [serial_id])[0]
    assert hu_row['status'] == 'sealed'
    assert hu_row['shipped_at'] is None
    assert serial['usage_status'] == 'in_stores'
    assert serial['current_location_id'] == 7


def test_reverse_receipt_removes_packed_content():
    conn = build_db()
    add_item(conn)
    serial_id = add_serial(conn)
    _receipt_with_hu(conn, hu_no='HU-R')
    link_receipt_serial(conn, 1, 1, serial_id)
    svc = service(conn)
    svc.pack_receipt(1)

    svc.reverse_document('receipt', 1)
    assert service(conn).hu_contents('HU-R', org_id=1)['items'] == []
    pack_events = ds(conn).query(
        "SELECT COUNT(*) AS n FROM hu_transactions WHERE txn_type = 'pack' ")
    assert pack_events[0]['n'] == 1


def test_linked_receipt_twice_is_idempotent():
    conn = build_db()
    add_item(conn)
    serial_id = add_serial(conn)
    _receipt_with_hu(conn, hu_no='HU-R')
    link_receipt_serial(conn, 1, 1, serial_id)
    svc = service(conn)
    svc.pack_receipt(1)
    svc.pack_receipt(1)
    pack_events = ds(conn).query(
        "SELECT COUNT(*) AS n FROM hu_transactions WHERE txn_type = 'pack' ")
    assert pack_events[0]['n'] == 1


def test_ship_shipment_same_hu_two_lines_ships_once():
    """同一容器出现在同单据多行：只发一次，两个 line_id 都落事件（§11.15 P1-1）。"""
    conn = build_db()
    add_item(conn)
    serial_id = add_serial(conn)
    _receipt_with_hu(conn, hu_no='HU-R')
    link_receipt_serial(conn, 1, 1, serial_id)
    svc = service(conn)
    svc.pack_receipt(1)
    hu = ds(conn).query('SELECT id FROM handling_units WHERE hu_no = ?',
                        ['HU-R'])[0]
    svc.seal(hu['id'])
    conn.execute(
        'INSERT INTO shipments (id, delivery_no, ship_from_location_id, '
        "status) VALUES (1, 'DN-1', 7, 'confirmed')")
    conn.execute(
        'INSERT INTO shipment_lines (id, delivery_id, item_id, qty, hu_no, '
        "status) VALUES (1, 1, 900, 1, 'HU-R', 'confirmed')")
    conn.execute(
        'INSERT INTO shipment_lines (id, delivery_id, item_id, qty, hu_no, '
        "status) VALUES (2, 1, 901, 1, 'HU-R', 'confirmed')")

    result = svc.ship_shipment(1)

    assert result['shipped'] == 1
    events = ds(conn).query(
        "SELECT line_id FROM hu_transactions WHERE hu_id = ? "
        "AND txn_type = 'ship' ORDER BY line_id", [hu['id']])
    assert [row['line_id'] for row in events] == [1, 2]
    hu_row = ds(conn).query('SELECT status FROM handling_units WHERE id = ?',
                            [hu['id']])[0]
    assert hu_row['status'] == 'shipped'

    # 重复过账：容器已 shipped，整单按幂等跳过，不重复写事件
    again = svc.ship_shipment(1)
    assert again['shipped'] == 0 and again['skipped_lines'] == 2
    count = ds(conn).query(
        "SELECT COUNT(*) AS n FROM hu_transactions WHERE hu_id = ? "
        "AND txn_type = 'ship'", [hu['id']])[0]
    assert count['n'] == 2
