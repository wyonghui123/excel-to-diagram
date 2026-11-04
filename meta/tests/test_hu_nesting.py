# -*- coding: utf-8 -*-
"""包装容器嵌套 / 移库 / 合并 / 拆分 / 汇总（spec §11.7 / §11.13）。

ALLOW_RAW_SQL: 嵌套与索引约束需原生 SQL 造夹具；仅豁免本文件。
"""

import pytest

pytestmark = pytest.mark.unit

from meta.services.handling_unit_service import (  # noqa: E402
    HandlingUnitError,
)
from meta.tests.hu_test_doubles import (  # noqa: E402
    add_item,
    add_serial,
    build_db,
    ds,
    service,
)


def _sealed_carton(conn, hu_no, serial_no):
    add_serial(conn, serial_no=serial_no)
    svc = service(conn)
    hu = svc.create_hu({'hu_no': hu_no, 'org_id': 1, 'location_id': 7})
    serial_id = ds(conn).query(
        'SELECT id FROM serial_numbers WHERE serial_no = ?', [serial_no])[0]['id']
    svc.pack(hu['id'], [{'serial_id': serial_id}])
    svc.seal(hu['id'])
    return hu


def test_nested_parent_sets_root_and_exploded_path():
    conn = build_db()
    add_item(conn)
    svc = service(conn)
    carton = _sealed_carton(conn, 'HU-C', 'SN-C')
    pallet = svc.create_hu({'hu_no': 'HU-P', 'org_id': 1, 'location_id': 7})
    svc.pack(pallet['id'], [{'child_hu_id': carton['id']}])

    child = ds(conn).query('SELECT * FROM handling_units WHERE id = ?',
                           [carton['id']])[0]
    assert child['parent_hu_id'] == pallet['id']
    assert child['root_hu_id'] == pallet['id']

    exploded = svc.hu_contents('HU-P', org_id=1, mode='exploded')
    assert len(exploded['items']) == 1
    leaf = exploded['items'][0]
    assert leaf['serial_no'] == 'SN-C'
    assert [p['hu_no'] for p in leaf['path']] == ['HU-P', 'HU-C']


def test_hu_stock_sums_leaf_material_only():
    conn = build_db()
    add_item(conn)
    svc = service(conn)
    carton = _sealed_carton(conn, 'HU-C', 'SN-C')
    pallet = svc.create_hu({'hu_no': 'HU-P', 'org_id': 1, 'location_id': 7})
    svc.pack(pallet['id'], [{'child_hu_id': carton['id']}])

    stock = svc.hu_stock(pallet['id'], mode='exploded')
    assert stock['total_qty'] == 1.0
    assert stock['rows'][0]['item_id'] == 900


def test_move_updates_whole_subtree():
    conn = build_db()
    add_item(conn)
    svc = service(conn)
    carton = _sealed_carton(conn, 'HU-C', 'SN-C')
    pallet = svc.create_hu({'hu_no': 'HU-P', 'org_id': 1, 'location_id': 7})
    svc.pack(pallet['id'], [{'child_hu_id': carton['id']}])

    result = svc.move(pallet['id'], 8)
    assert result['moved'] == 2
    rows = ds(conn).query(
        'SELECT location_id FROM handling_units WHERE id IN (?, ?) '
        'ORDER BY id', [pallet['id'], carton['id']])
    assert [row['location_id'] for row in rows] == [8, 8]
    moves = ds(conn).query(
        "SELECT COUNT(*) AS n FROM hu_transactions WHERE txn_type = 'move'")
    assert moves[0]['n'] == 2


def test_consolidate_moves_content_and_voids_source():
    conn = build_db()
    add_item(conn)
    source_serial = add_serial(conn, serial_no='SN-S')
    svc = service(conn)
    source = svc.create_hu({'hu_no': 'HU-S', 'org_id': 1, 'location_id': 7})
    svc.pack(source['id'], [{'serial_id': source_serial}])
    target = svc.create_hu({'hu_no': 'HU-T', 'org_id': 1, 'location_id': 7})

    result = svc.consolidate([source['id']], target['id'])
    assert result['moved'] == 1
    assert svc.hu_contents('HU-T', org_id=1)['items'][0]['serial_no'] == 'SN-S'
    source_row = ds(conn).query('SELECT status FROM handling_units WHERE id = ?',
                                [source['id']])[0]
    assert source_row['status'] == 'void'
    with pytest.raises(HandlingUnitError) as exc:
        svc.consolidate([source['id']], target['id'])
    assert exc.value.rule == 'HU_STATUS_INVALID'


def test_split_moves_selected_lines():
    conn = build_db()
    add_item(conn)
    add_serial(conn, serial_no='SN-1')
    add_serial(conn, serial_no='SN-2')
    svc = service(conn)
    source = svc.create_hu({'hu_no': 'HU-S', 'org_id': 1, 'location_id': 7})
    rows = ds(conn).query('SELECT id FROM serial_numbers ORDER BY id')
    svc.pack(source['id'], [{'serial_id': rows[0]['id']},
                            {'serial_id': rows[1]['id']}])
    target = svc.create_hu({'hu_no': 'HU-T', 'org_id': 1})

    line = ds(conn).query(
        'SELECT id FROM handling_unit_items WHERE hu_id = ? AND serial_id = ?',
        [source['id'], rows[1]['id']])[0]
    result = svc.split(source['id'], [line['id']], target['id'])
    assert result['moved'] == 1
    assert ds(conn).query(
        'SELECT hu_id FROM handling_unit_items WHERE id = ?', [line['id']])[0][
            'hu_id'] == target['id']
    assert target['id'] == ds(conn).query(
        'SELECT root_hu_id FROM handling_units WHERE id = ?', [target['id']])[0][
            'root_hu_id']


def test_where_used_returns_ancestor_path():
    conn = build_db()
    add_item(conn)
    svc = service(conn)
    carton = _sealed_carton(conn, 'HU-C', 'SN-C')
    pallet = svc.create_hu({'hu_no': 'HU-P', 'org_id': 1, 'location_id': 7})
    svc.pack(pallet['id'], [{'child_hu_id': carton['id']}])

    result = svc.hu_where_used('SN-C', org_id=1)
    match = result['matches'][0]
    assert match['current_hu']['hu_no'] == 'HU-C'
    assert match['current_hu']['root_hu_no'] == 'HU-P'
    assert [p['hu_no'] for p in match['path']] == ['HU-P', 'HU-C']
