# -*- coding: utf-8 -*-
"""包装容器调拨接线（spec §11.5 补充）。

ALLOW_RAW_SQL: 测试替身直接造调拨单 / 收货单夹具，Factory 尚无对应支持；
仅豁免本文件。
"""

import pytest

pytestmark = pytest.mark.unit

from meta.services.handling_unit_service import (  # noqa: E402
    HandlingUnitError,
    HandlingUnitService,
)
from meta.tests.hu_test_doubles import (  # noqa: E402
    add_item,
    add_serial,
    build_db,
    ds,
    service,
)


def test_ship_transfer_same_org_moves_sealed_hu():
    conn = build_db()
    add_item(conn)
    svc = service(conn)
    serial_id = add_serial(conn, 'SN-001', org_id=1, location_id=7)
    hu = svc.create_hu({'hu_no': 'HU-001', 'org_id': 1, 'location_id': 7})
    svc.pack(hu['id'], [{'content_type': 'material', 'serial_id': serial_id}])
    svc.seal(hu['id'])
    conn.execute(
        'INSERT INTO transfer_orders (id, from_org_id, to_org_id, '
        'from_location_id, to_location_id, status) '
        "VALUES (1, 1, 1, 7, 8, 'released')")
    conn.execute(
        'INSERT INTO transfer_order_lines (id, transfer_order_id, item_id, qty, '
        "hu_no, status) VALUES (1, 1, 900, 1, 'HU-001', 'open')")

    result = svc.ship_transfer(1)

    assert result['moved'] == 1 and result['shipped'] == 0
    row = ds(conn).query(
        'SELECT location_id, status FROM handling_units WHERE id = ?',
        [hu['id']])[0]
    assert row['location_id'] == 8
    assert row['status'] == 'sealed'
    moves = ds(conn).query(
        "SELECT * FROM hu_transactions WHERE hu_id = ? AND txn_type = 'move'",
        [hu['id']])
    assert len(moves) == 1
    assert moves[0]['doc_type'] == 'transfer_order'
    assert moves[0]['to_location_id'] == 8


def test_ship_transfer_cross_org_ships_source_tree():
    conn = build_db()
    add_item(conn)
    svc = service(conn)
    serial_id = add_serial(conn, 'SN-001', org_id=1, location_id=7)
    hu = svc.create_hu({'hu_no': 'HU-001', 'org_id': 1, 'location_id': 7})
    svc.pack(hu['id'], [{'content_type': 'material', 'serial_id': serial_id}])
    svc.seal(hu['id'])
    conn.execute(
        'INSERT INTO transfer_orders (id, from_org_id, to_org_id, '
        'from_location_id, to_location_id, status) '
        "VALUES (1, 1, 2, 7, 9, 'released')")
    conn.execute(
        'INSERT INTO transfer_order_lines (id, transfer_order_id, item_id, qty, '
        "hu_no, status) VALUES (1, 1, 900, 1, 'HU-001', 'open')")

    result = svc.ship_transfer(1)

    assert result['shipped'] == 1 and result['moved'] == 0
    hu_row = ds(conn).query(
        'SELECT status, location_id FROM handling_units WHERE id = ?',
        [hu['id']])[0]
    assert hu_row['status'] == 'shipped'
    assert hu_row['location_id'] is None
    serial_row = ds(conn).query(
        'SELECT usage_status FROM serial_numbers WHERE id = ?', [serial_id])[0]
    assert serial_row['usage_status'] == 'shipped'


def test_ship_transfer_missing_hu_raises():
    conn = build_db()
    add_item(conn)
    svc = service(conn)
    conn.execute(
        'INSERT INTO transfer_orders (id, from_org_id, to_org_id, '
        'from_location_id, to_location_id, status) '
        "VALUES (1, 1, 1, 7, 8, 'released')")
    conn.execute(
        'INSERT INTO transfer_order_lines (id, transfer_order_id, item_id, qty, '
        "hu_no, status) VALUES (1, 1, 900, 1, 'HU-404', 'open')")
    with pytest.raises(HandlingUnitError) as exc:
        svc.ship_transfer(1)
    assert exc.value.rule == 'HU_NOT_FOUND'


def test_ship_transfer_same_hu_multi_lines_moves_once():
    """同一容器出现在同单据多行：同组织只移库一次（§11.15 P1-1）。"""
    conn = build_db()
    add_item(conn)
    svc = service(conn)
    serial_id = add_serial(conn, 'SN-001', org_id=1, location_id=7)
    hu = svc.create_hu({'hu_no': 'HU-001', 'org_id': 1, 'location_id': 7})
    svc.pack(hu['id'], [{'content_type': 'material', 'serial_id': serial_id}])
    svc.seal(hu['id'])
    conn.execute(
        'INSERT INTO transfer_orders (id, from_org_id, to_org_id, '
        'from_location_id, to_location_id, status) '
        "VALUES (1, 1, 1, 7, 8, 'released')")
    conn.execute(
        'INSERT INTO transfer_order_lines (id, transfer_order_id, item_id, qty, '
        "hu_no, status) VALUES (1, 1, 900, 1, 'HU-001', 'open')")
    conn.execute(
        'INSERT INTO transfer_order_lines (id, transfer_order_id, item_id, qty, '
        "hu_no, status) VALUES (2, 1, 901, 1, 'HU-001', 'open')")

    result = svc.ship_transfer(1)

    assert result['moved'] == 1
    moves = ds(conn).query(
        "SELECT * FROM hu_transactions WHERE hu_id = ? AND txn_type = 'move'",
        [hu['id']])
    assert len(moves) == 1


def test_ship_transfer_cross_org_is_idempotent():
    """跨组织重复发运：容器已 shipped 时按幂等跳过，不抛错（§11.15 P1-1）。"""
    conn = build_db()
    add_item(conn)
    svc = service(conn)
    serial_id = add_serial(conn, 'SN-001', org_id=1, location_id=7)
    hu = svc.create_hu({'hu_no': 'HU-001', 'org_id': 1, 'location_id': 7})
    svc.pack(hu['id'], [{'content_type': 'material', 'serial_id': serial_id}])
    svc.seal(hu['id'])
    conn.execute(
        'INSERT INTO transfer_orders (id, from_org_id, to_org_id, '
        'from_location_id, to_location_id, status) '
        "VALUES (1, 1, 2, 7, 9, 'released')")
    conn.execute(
        'INSERT INTO transfer_order_lines (id, transfer_order_id, item_id, qty, '
        "hu_no, status) VALUES (1, 1, 900, 1, 'HU-001', 'open')")

    first = svc.ship_transfer(1)
    again = svc.ship_transfer(1)

    assert first['shipped'] == 1
    assert again['shipped'] == 0 and again['skipped_lines'] == 1


def test_pack_receipt_clones_cross_org_tree():
    conn = build_db()
    add_item(conn)
    svc = service(conn)
    serial_id = add_serial(conn, 'SN-001', org_id=1, location_id=7)

    child = svc.create_hu({'hu_no': 'C1', 'org_id': 1, 'location_id': 7})
    svc.pack(child['id'], [{'content_type': 'material',
                            'serial_id': serial_id}])
    svc.seal(child['id'])
    parent = svc.create_hu({'hu_no': 'P1', 'org_id': 1, 'location_id': 7})
    svc.pack(parent['id'], [{'content_type': 'hu',
                             'child_hu_id': child['id']}])
    svc.seal(parent['id'])
    # 源组织已发运
    svc.ship_hu(parent['id'], None, {'doc_type': 'transfer_order',
                                     'doc_id': 1, 'line_id': 1})

    conn.execute(
        'INSERT INTO receipts (id, receipt_no, inventory_org_id, '
        "deliver_to_location_id, status) VALUES (1, 'R1', 2, 9, 'posted')")
    conn.execute(
        'INSERT INTO receipt_lines (id, receipt_id, item_id, qty_received, '
        "putaway_location_id, hu_no, status) "
        "VALUES (1, 1, 900, 1, 9, 'P1', 'open')")

    result = svc.pack_receipt(1)

    assert result['packed'] == 1
    cloned_parent = ds(conn).query(
        "SELECT * FROM handling_units WHERE hu_no = 'P1' AND org_id = 2")[0]
    assert cloned_parent['status'] == 'sealed'
    assert cloned_parent['location_id'] == 9
    cloned_child = ds(conn).query(
        "SELECT * FROM handling_units WHERE hu_no = 'C1' AND org_id = 2")[0]
    assert cloned_child['parent_hu_id'] == cloned_parent['id']
    assert cloned_child['root_hu_id'] == cloned_parent['id']
    materials = ds(conn).query(
        'SELECT * FROM handling_unit_items WHERE hu_id = ? '
        "AND content_type = 'material'", [cloned_child['id']])
    assert len(materials) == 1
    assert materials[0]['serial_id'] is None
    assert materials[0]['qty'] == 1


def test_pack_receipt_clone_is_idempotent():
    conn = build_db()
    add_item(conn)
    svc = service(conn)
    serial_id = add_serial(conn, 'SN-001', org_id=1, location_id=7)
    source = svc.create_hu({'hu_no': 'P1', 'org_id': 1, 'location_id': 7})
    svc.pack(source['id'], [{'content_type': 'material',
                             'serial_id': serial_id}])
    svc.seal(source['id'])
    svc.ship_hu(source['id'], None, {'doc_type': 'transfer_order',
                                     'doc_id': 1, 'line_id': 1})

    conn.execute(
        'INSERT INTO receipts (id, receipt_no, inventory_org_id, '
        "deliver_to_location_id, status) VALUES (1, 'R1', 2, 9, 'posted')")
    conn.execute(
        'INSERT INTO receipt_lines (id, receipt_id, item_id, qty_received, '
        "putaway_location_id, hu_no, status) "
        "VALUES (1, 1, 900, 1, 9, 'P1', 'open')")

    svc.pack_receipt(1)
    svc.pack_receipt(1)

    cloned = ds(conn).query(
        "SELECT * FROM handling_units WHERE hu_no = 'P1' AND org_id = 2")[0]
    items = ds(conn).query(
        'SELECT * FROM handling_unit_items WHERE hu_id = ?', [cloned['id']])
    assert len(items) == 1


def test_ship_transfer_skips_when_schema_missing():
    conn = build_db(with_hu=False)
    svc = HandlingUnitService(ds(conn))
    result = svc.ship_transfer(1)
    assert result['skipped'] is True
