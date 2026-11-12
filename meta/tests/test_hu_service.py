# -*- coding: utf-8 -*-
"""HandlingUnitService 主档 / 装箱 / 状态机（spec §11.3 / §11.4）。

ALLOW_RAW_SQL: 服务按 hu_id 读回投影行须用原生 SELECT/INSERT 造夹具，
Factory 尚无 handling_unit 支持；仅豁免本文件。
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

VALID_SSCC = '123456789012345675'
INVALID_SSCC = '123456789012345670'


def test_create_hu_writes_create_event():
    conn = build_db()
    svc = service(conn)
    result = svc.create_hu({'hu_no': 'HU-001', 'org_id': 1, 'location_id': 7})

    row = ds(conn).query('SELECT * FROM handling_units WHERE id = ?',
                         [result['id']])[0]
    assert row['status'] == 'open'
    assert row['root_hu_id'] == result['id']
    assert row['cycle_no'] == 1
    events = ds(conn).query(
        'SELECT txn_type, to_hu_id FROM hu_transactions WHERE hu_id = ?',
        [result['id']])
    assert [e['txn_type'] for e in events] == ['create']


def test_create_hu_rejects_duplicate_no():
    conn = build_db()
    service(conn).create_hu({'hu_no': 'HU-001', 'org_id': 1})
    with pytest.raises(HandlingUnitError) as exc:
        service(conn).create_hu({'hu_no': 'HU-001', 'org_id': 1})
    assert exc.value.rule == 'HU_NO_DUPLICATE'


def test_create_hu_sscc_checksum():
    conn = build_db()
    service(conn).create_hu({'hu_no': VALID_SSCC, 'org_id': 1})
    with pytest.raises(HandlingUnitError) as exc:
        service(conn).create_hu({'hu_no': INVALID_SSCC, 'org_id': 1})
    assert exc.value.rule == 'HU_SSCC_CHECKSUM_INVALID'


def test_pack_serial_content_and_location():
    conn = build_db()
    add_item(conn)
    serial_id = add_serial(conn)
    svc = service(conn)
    hu = svc.create_hu({'hu_no': 'HU-001', 'org_id': 1})

    result = svc.pack(hu['id'], [{'content_type': 'material',
                                 'serial_id': serial_id}])
    contents = svc.hu_contents('HU-001', org_id=1)
    assert result['location_id'] == 7
    assert contents['hu']['location_id'] == 7
    assert len(contents['items']) == 1
    assert contents['items'][0]['serial_no'] == 'SN-001'
    assert contents['items'][0]['qty'] == 1


def test_pack_rejects_serial_not_in_stores():
    conn = build_db()
    add_item(conn)
    serial_id = add_serial(conn, status='defined', location_id=None)
    svc = service(conn)
    hu = svc.create_hu({'hu_no': 'HU-001', 'org_id': 1, 'location_id': 7})
    with pytest.raises(HandlingUnitError) as exc:
        svc.pack(hu['id'], [{'serial_id': serial_id}])
    assert exc.value.rule == 'HU_SERIAL_NOT_IN_STORES'


def test_pack_rejects_serial_already_packed():
    conn = build_db()
    add_item(conn)
    serial_id = add_serial(conn)
    svc = service(conn)
    hu1 = svc.create_hu({'hu_no': 'HU-001', 'org_id': 1, 'location_id': 7})
    hu2 = svc.create_hu({'hu_no': 'HU-002', 'org_id': 1, 'location_id': 7})
    svc.pack(hu1['id'], [{'serial_id': serial_id}])
    with pytest.raises(HandlingUnitError) as exc:
        svc.pack(hu2['id'], [{'serial_id': serial_id}])
    assert exc.value.rule == 'HU_SERIAL_ALREADY_PACKED'


def test_pack_rejects_location_mismatch():
    conn = build_db()
    add_item(conn)
    serial_id = add_serial(conn, location_id=8)
    svc = service(conn)
    hu = svc.create_hu({'hu_no': 'HU-001', 'org_id': 1, 'location_id': 7})
    with pytest.raises(HandlingUnitError) as exc:
        svc.pack(hu['id'], [{'serial_id': serial_id}])
    assert exc.value.rule == 'HU_CONTENT_LOCATION_MISMATCH'


def test_pack_rejects_serial_other_org():
    conn = build_db()
    add_item(conn)
    serial_id = add_serial(conn, org_id=2, location_id=9)
    svc = service(conn)
    hu = svc.create_hu({'hu_no': 'HU-001', 'org_id': 1, 'location_id': 7})
    with pytest.raises(HandlingUnitError) as exc:
        svc.pack(hu['id'], [{'serial_id': serial_id}])
    assert exc.value.rule == 'HU_ORG_MISMATCH'


def test_seal_requires_content_and_location():
    conn = build_db()
    svc = service(conn)
    hu = svc.create_hu({'hu_no': 'HU-001', 'org_id': 1})
    with pytest.raises(HandlingUnitError) as exc:
        svc.seal(hu['id'])
    assert exc.value.rule == 'HU_CONTENT_EMPTY'


def test_seal_infers_location_from_serial():
    conn = build_db()
    add_item(conn)
    serial_id = add_serial(conn)
    svc = service(conn)
    hu = svc.create_hu({'hu_no': 'HU-001', 'org_id': 1})
    svc.pack(hu['id'], [{'serial_id': serial_id}])

    result = svc.seal(hu['id'])
    assert result['status'] == 'sealed'
    assert result['location_id'] == 7
    with pytest.raises(HandlingUnitError) as exc:
        svc.pack(hu['id'], [{'serial_id': add_serial(conn, serial_no='SN-002')}])
    assert exc.value.rule == 'HU_STATUS_INVALID'


def test_unseal_returns_open():
    conn = build_db()
    add_item(conn)
    serial_id = add_serial(conn)
    svc = service(conn)
    hu = svc.create_hu({'hu_no': 'HU-001', 'org_id': 1})
    svc.pack(hu['id'], [{'serial_id': serial_id}])
    svc.seal(hu['id'])
    assert svc.unseal(hu['id'])['status'] == 'open'


def test_reuse_requires_reusable_and_empty():
    conn = build_db()
    add_item(conn)
    serial_id = add_serial(conn)
    svc = service(conn)
    plain = svc.create_hu({'hu_no': 'HU-001', 'org_id': 1})
    svc.pack(plain['id'], [{'serial_id': serial_id}])
    svc.seal(plain['id'])
    with pytest.raises(HandlingUnitError) as exc:
        svc.reuse(plain['id'])
    assert exc.value.rule == 'HU_NOT_REUSABLE'

    reusable = svc.create_hu({'hu_no': 'HU-002', 'org_id': 1,
                              'location_id': 7, 'is_reusable': True})
    svc.ds.execute(
        "INSERT INTO handling_unit_items (hu_id, content_type, item_id, qty, "
        "created_at) VALUES (?, 'material', 900, 1, 'now')", [reusable['id']])
    svc.seal(reusable['id'])
    with pytest.raises(HandlingUnitError) as exc:
        service(conn).reuse(reusable['id'])
    assert exc.value.rule == 'HU_NOT_EMPTY'


def test_reuse_reusable_empty_increments_cycle():
    conn = build_db()
    svc = service(conn)
    hu = svc.create_hu({'hu_no': 'HU-001', 'org_id': 1, 'location_id': 7,
                        'is_reusable': True,
                        'source_doc_type': 'manual'})
    svc.ds.execute(
        "INSERT INTO handling_unit_items (hu_id, content_type, item_id, qty, "
        "created_at) VALUES (?, 'material', 900, 1, 'now')", [hu['id']])
    svc.seal(hu['id'])
    svc.unseal(hu['id'])
    svc.unpack(hu['id'])
    result = svc.reuse(hu['id'])
    assert result['status'] == 'open'
    assert result['cycle_no'] == 2


def test_void_requires_empty():
    conn = build_db()
    add_item(conn)
    serial_id = add_serial(conn)
    svc = service(conn)
    hu = svc.create_hu({'hu_no': 'HU-001', 'org_id': 1})
    svc.pack(hu['id'], [{'serial_id': serial_id}])
    with pytest.raises(HandlingUnitError) as exc:
        svc.void_hu(hu['id'])
    assert exc.value.rule == 'HU_NOT_EMPTY'

    svc.unpack(hu['id'])
    assert svc.void_hu(hu['id'], '测试作废')['status'] == 'void'


def test_pack_child_rejects_cycle():
    conn = build_db()
    svc = service(conn)
    parent = svc.create_hu({'hu_no': 'HU-P', 'org_id': 1, 'location_id': 7})
    child = svc.create_hu({'hu_no': 'HU-C', 'org_id': 1, 'location_id': 7})
    svc.ds.execute(
        "INSERT INTO handling_unit_items (hu_id, content_type, item_id, qty, "
        "created_at) VALUES (?, 'material', 900, 1, 'now')", [child['id']])
    svc.seal(child['id'])
    svc.pack(parent['id'], [{'child_hu_id': child['id']}])
    svc.seal(parent['id'])
    svc.unseal(child['id'])
    with pytest.raises(HandlingUnitError) as exc:
        svc.pack(child['id'], [{'child_hu_id': parent['id']}])
    assert exc.value.rule == 'HU_PARENT_CYCLE'


def test_pack_child_requires_sealed():
    conn = build_db()
    svc = service(conn)
    parent = svc.create_hu({'hu_no': 'HU-P', 'org_id': 1, 'location_id': 7})
    child = svc.create_hu({'hu_no': 'HU-C', 'org_id': 1, 'location_id': 7})
    with pytest.raises(HandlingUnitError) as exc:
        svc.pack(parent['id'], [{'child_hu_id': child['id']}])
    assert exc.value.rule == 'HU_CHILD_STATUS_INVALID'
