# -*- coding: utf-8 -*-
"""P6c 完工成品号与组件单父谱系测试（spec §7）。

覆盖：成品建档、qty>1 走 link、组件爆用与谱系、D7 四类组件校验、
成品未启序列号放行、红冲回退且保留谱系、genealogy 查询。
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.migrations import v202__serial_number_model as v202
from meta.migrations import v205__inventory_segment_reservation as v205
from meta.services.receipt_service import ReceiptError, ReceiptService
from meta.services.serial_number_service import SerialNumberService
from meta.tests.receipt_test_doubles import MemDS, seeded_db

_CORE_DDL = """
CREATE TABLE items (
    id INTEGER PRIMARY KEY,
    serial_tracked INTEGER DEFAULT 0,
    require_on_receipt INTEGER DEFAULT 0,
    require_on_issue INTEGER DEFAULT 0
);
CREATE TABLE inventory_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_event_key TEXT,
    source_line_id INTEGER
);
CREATE TABLE work_orders (
    id INTEGER PRIMARY KEY,
    work_order_no TEXT,
    order_type TEXT,
    status TEXT,
    org_id INTEGER
);
CREATE TABLE work_order_components (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_id INTEGER,
    line_no TEXT,
    component_item_id INTEGER,
    qty_required REAL,
    qty_per REAL,
    fixed_qty REAL DEFAULT 0,
    scrap_rate REAL DEFAULT 0,
    optional_flag INTEGER DEFAULT 0
);
"""

ITEM_FINISHED = 800
ITEM_COMPONENT = 810
ITEM_COMPONENT_ALT = 811
ITEM_UNTRACKED = 820


def _db(components=(), finished_tracked=1) -> object:
    """内存库：收货替身 + v202 三表 + 工单 / 组件 / 物料种子。"""
    conn = seeded_db()
    conn.executescript(_CORE_DDL)
    v202._do_tables(conn)
    v202._do_indexes(conn)
    conn.execute(
        'INSERT INTO items (id, serial_tracked, require_on_receipt, '
        'require_on_issue) VALUES (?, ?, 1, 0)',
        [ITEM_FINISHED, finished_tracked])
    conn.execute(
        'INSERT INTO items (id, serial_tracked, require_on_receipt, '
        'require_on_issue) VALUES (?, 1, 0, 0)', [ITEM_COMPONENT])
    conn.execute(
        'INSERT INTO items (id, serial_tracked, require_on_receipt, '
        'require_on_issue) VALUES (?, 1, 0, 0)', [ITEM_COMPONENT_ALT])
    conn.execute(
        'INSERT INTO items (id, serial_tracked, require_on_receipt, '
        'require_on_issue) VALUES (?, 0, 0, 0)', [ITEM_UNTRACKED])
    conn.execute(
        "INSERT INTO work_orders (id, work_order_no, order_type, status) "
        "VALUES (1, 'WO-0001', 'production', 'In Progress')")
    for seq, (component_item_id, qty_required, optional) in enumerate(
            components, start=1):
        conn.execute(
            'INSERT INTO work_order_components (id, work_order_id, line_no, '
            'component_item_id, qty_required, optional_flag) '
            'VALUES (?, 1, ?, ?, ?, ?)',
            [seq, str(seq * 10), component_item_id, qty_required, optional])
    conn.commit()
    return conn


def _service(conn) -> ReceiptService:
    service = ReceiptService(MemDS(conn))
    # 库存数量事务由 inventory 测试覆盖，这里只验证序列号钩子
    service._post_receipt_inventory = lambda *args, **kwargs: None
    return service


def _serial(conn, item_id, serial_no, status='in_stores', org_id=2,
            location_id=8, parent_serial_id=None) -> int:
    service = SerialNumberService(MemDS(conn))
    row = service.create_serial({
        'item_id': item_id, 'org_id': org_id, 'serial_no': serial_no,
        'source_type': 'opening', 'current_location_id': location_id})
    conn.execute(
        'UPDATE serial_numbers SET usage_status = ?, parent_serial_id = ? '
        'WHERE id = ?', [status, parent_serial_id, row['id']])
    conn.commit()
    return row['id']


def _link_components(conn, component_id, serial_ids) -> None:
    SerialNumberService(MemDS(conn)).link_serials(
        'work_order', 1, component_id, serial_ids, 'out')


def _make_receipt(conn, lines, **kwargs) -> dict:
    params = {'inventory_org_id': 2, 'org_id': 1,
              'receipt_date': '2026-11-01'}
    params.update(kwargs)
    return _service(conn).create_from_work_order(1, 8, lines, **params)


def _line_id(conn, receipt_id) -> int:
    return MemDS(conn).query(
        'SELECT id FROM receipt_lines WHERE receipt_id = ?',
        [receipt_id])[0]['id']


def _row(conn, sql, params):
    return MemDS(conn).query(sql, params)[0]


def test_completion_creates_produced_serial():
    conn = _db()
    receipt = _make_receipt(
        conn, [{'item_id': ITEM_FINISHED, 'uom_id': 3, 'qty_received': 1,
                'serial_no': 'FG-001'}])
    _service(conn).post(receipt['id'])

    row = _row(conn, 'SELECT * FROM serial_numbers WHERE serial_no = ?',
               ['FG-001'])
    assert row['usage_status'] == 'in_stores'
    assert row['source_type'] == 'produced'
    assert row['produced_at']
    assert row['current_location_id'] == 8
    txn_types = [t['txn_type'] for t in MemDS(conn).query(
        'SELECT txn_type FROM serial_transactions WHERE serial_id = ? '
        'ORDER BY id', [row['id']])]
    assert txn_types == ['create', 'receive']
    link = _row(conn, 'SELECT * FROM document_serial_links WHERE serial_id = ?',
                [row['id']])
    assert link['doc_type'] == 'receipt'
    assert link['direction'] == 'in'


def test_completion_qty_two_uses_links():
    conn = _db()
    serial_ids = [_serial(conn, ITEM_FINISHED, 'FG-A'),
                  _serial(conn, ITEM_FINISHED, 'FG-B')]
    receipt = _make_receipt(
        conn, [{'item_id': ITEM_FINISHED, 'uom_id': 3, 'qty_received': 2}])
    SerialNumberService(MemDS(conn)).link_serials(
        'receipt', receipt['id'], _line_id(conn, receipt['id']),
        serial_ids, 'in')

    _service(conn).post(receipt['id'])

    links = MemDS(conn).query(
        'SELECT * FROM document_serial_links WHERE doc_type = ? AND doc_id = ?',
        ['receipt', receipt['id']])
    assert len(links) == 2
    for serial_id in serial_ids:
        row = _row(conn, 'SELECT * FROM serial_numbers WHERE id = ?',
                   [serial_id])
        assert row['usage_status'] == 'in_stores'


def _component_scenario(conn, count=3):
    serial_ids = [_serial(conn, ITEM_COMPONENT, 'C-%s' % i)
                  for i in range(1, count + 1)]
    _link_components(conn, 1, serial_ids)
    receipt = _make_receipt(
        conn, [{'item_id': ITEM_FINISHED, 'uom_id': 3, 'qty_received': 1,
                'serial_no': 'FG-100'}])
    _service(conn).post(receipt['id'])
    return receipt, serial_ids


def test_completion_consumes_components_and_sets_genealogy():
    conn = _db(components=[(ITEM_COMPONENT, 3, 0)])
    receipt, serial_ids = _component_scenario(conn, count=3)

    finished = _row(conn, 'SELECT * FROM serial_numbers WHERE serial_no = ?',
                    ['FG-100'])
    for serial_id in serial_ids:
        row = _row(conn, 'SELECT * FROM serial_numbers WHERE id = ?',
                   [serial_id])
        assert row['usage_status'] == 'issued'
        assert row['current_location_id'] is None
        assert row['parent_serial_id'] == finished['id']
        assert row['relation_type'] == 'assembly'
        issues = MemDS(conn).query(
            "SELECT * FROM serial_transactions WHERE serial_id = ? "
            "AND txn_type = 'issue'", [serial_id])
        assert len(issues) == 1
        assert issues[0]['usage_from'] == 'in_stores'
        assert issues[0]['usage_to'] == 'issued'


def test_component_not_in_stores_rejected():
    conn = _db(components=[(ITEM_COMPONENT, 1, 0)])
    serial_id = _serial(conn, ITEM_COMPONENT, 'C-1', status='defined')
    _link_components(conn, 1, [serial_id])
    receipt = _make_receipt(
        conn, [{'item_id': ITEM_FINISHED, 'uom_id': 3, 'qty_received': 1,
                'serial_no': 'FG-100'}])

    with pytest.raises(ReceiptError) as exc:
        _service(conn).post(receipt['id'])
    assert exc.value.rule == 'SERIAL_COMPONENT_NOT_IN_STORES'
    row = _row(conn, 'SELECT * FROM serial_numbers WHERE id = ?', [serial_id])
    assert row['usage_status'] == 'defined'
    assert not MemDS(conn).query(
        "SELECT 1 FROM serial_transactions WHERE serial_id = ? "
        "AND txn_type = 'issue'", [serial_id])


def test_component_item_mismatch_rejected():
    conn = _db(components=[(ITEM_COMPONENT, 1, 0)])
    serial_id = _serial(conn, ITEM_COMPONENT_ALT, 'C-WRONG')
    _link_components(conn, 1, [serial_id])
    receipt = _make_receipt(
        conn, [{'item_id': ITEM_FINISHED, 'uom_id': 3, 'qty_received': 1,
                'serial_no': 'FG-100'}])

    with pytest.raises(ReceiptError) as exc:
        _service(conn).post(receipt['id'])
    assert exc.value.rule == 'SERIAL_COMPONENT_ITEM_MISMATCH'


def test_component_count_mismatch_rejected():
    conn = _db(components=[(ITEM_COMPONENT, 2, 0)])
    serial_id = _serial(conn, ITEM_COMPONENT, 'C-1')
    _link_components(conn, 1, [serial_id])
    receipt = _make_receipt(
        conn, [{'item_id': ITEM_FINISHED, 'uom_id': 3, 'qty_received': 1,
                'serial_no': 'FG-100'}])

    with pytest.raises(ReceiptError) as exc:
        _service(conn).post(receipt['id'])
    assert exc.value.rule == 'SERIAL_COMPONENT_COUNT_MISMATCH'


def test_component_already_has_parent_rejected():
    conn = _db(components=[(ITEM_COMPONENT, 1, 0)])
    other = _serial(conn, ITEM_COMPONENT, 'C-OTHER')
    serial_id = _serial(conn, ITEM_COMPONENT, 'C-1',
                        parent_serial_id=other)
    _link_components(conn, 1, [serial_id])
    receipt = _make_receipt(
        conn, [{'item_id': ITEM_FINISHED, 'uom_id': 3, 'qty_received': 1,
                'serial_no': 'FG-100'}])

    with pytest.raises(ReceiptError) as exc:
        _service(conn).post(receipt['id'])
    assert exc.value.rule == 'SERIAL_PARENT_ALREADY_SET'


def test_untracked_finished_item_still_consumes_components():
    conn = _db(components=[(ITEM_COMPONENT, 1, 0)], finished_tracked=0)
    serial_id = _serial(conn, ITEM_COMPONENT, 'C-1')
    _link_components(conn, 1, [serial_id])
    receipt = _make_receipt(
        conn, [{'item_id': ITEM_UNTRACKED, 'uom_id': 3, 'qty_received': 1}])

    _service(conn).post(receipt['id'])

    assert not MemDS(conn).query(
        'SELECT * FROM serial_numbers WHERE item_id = ?', [ITEM_UNTRACKED])
    row = _row(conn, 'SELECT * FROM serial_numbers WHERE id = ?', [serial_id])
    assert row['usage_status'] == 'issued'
    assert row['parent_serial_id'] is None


def test_completion_fulfills_component_reservation():
    """INV-2 核销链路：完工过账按累计完工量核销组件软预留。"""
    conn = _db(components=[(ITEM_COMPONENT, 1, 0)])
    serial_id = _serial(conn, ITEM_COMPONENT, 'C-1')
    _link_components(conn, 1, [serial_id])
    v205._do_tables(conn)
    conn.execute(
        'INSERT INTO inventory_reservations (reservation_no, org_id, item_id, '
        'uom_id, demand_object_type, demand_object_id, demand_line_id, '
        'stock_segment_type, qty_reserved, qty_fulfilled, peg_type, status, '
        'source_doc_type, source_doc_id, source_line_id, reservation_key, '
        'created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '
        '?, ?, ?, ?, ?, ?)',
        ['RSV-WO-1', 2, ITEM_COMPONENT, 3, 'work_order_component', 1, 1,
         'owned', 1, 0, 'soft', 'open', 'work_order', 1, 1, 'WO-COMP-1-1',
         '2026-11-01', '2026-11-01'])
    conn.commit()

    receipt = _make_receipt(
        conn, [{'item_id': ITEM_UNTRACKED, 'uom_id': 3, 'qty_received': 1}])
    _service(conn).post(receipt['id'])

    row = _row(conn, 'SELECT * FROM inventory_reservations WHERE id = 1', [])
    assert row['status'] == 'fulfilled'
    assert float(row['qty_fulfilled']) == pytest.approx(1)


def test_reverse_completion_restores_status_and_keeps_genealogy():
    conn = _db(components=[(ITEM_COMPONENT, 1, 0)])
    serial_id = _serial(conn, ITEM_COMPONENT, 'C-1')
    _link_components(conn, 1, [serial_id])
    receipt = _make_receipt(
        conn, [{'item_id': ITEM_FINISHED, 'uom_id': 3, 'qty_received': 1,
                'serial_no': 'FG-100'}])
    service = _service(conn)
    service.post(receipt['id'])

    service.reverse(receipt['id'])

    finished = _row(conn, 'SELECT * FROM serial_numbers WHERE serial_no = ?',
                    ['FG-100'])
    assert finished['usage_status'] == 'defined'
    assert finished['produced_at'] is None
    component = _row(conn, 'SELECT * FROM serial_numbers WHERE id = ?',
                     [serial_id])
    assert component['usage_status'] == 'in_stores'
    assert component['current_location_id'] == 8
    assert component['parent_serial_id'] == finished['id']
    assert len(MemDS(conn).query(
        'SELECT * FROM document_serial_links WHERE serial_id = ?',
        [serial_id])) == 1


def test_genealogy_returns_parents_and_children():
    conn = _db(components=[(ITEM_COMPONENT, 3, 0)])
    _receipt, serial_ids = _component_scenario(conn, count=3)
    finished = _row(conn, 'SELECT * FROM serial_numbers WHERE serial_no = ?',
                    ['FG-100'])

    tree = SerialNumberService(MemDS(conn)).genealogy(finished['id'], depth=1)

    assert len(tree['children']) == 3
    assert {node['serial']['id'] for node in tree['children']} \
        == set(serial_ids)
    for node in tree['children']:
        assert node['relation_type'] == 'assembly'
        assert node['children'] == []
    component = SerialNumberService(MemDS(conn)).genealogy(serial_ids[0], 1)
    assert [node['serial']['id'] for node in component['parents']] \
        == [finished['id']]


_TYPES_DDL = """
CREATE TABLE inventory_transaction_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE,
    name TEXT,
    category TEXT,
    direction TEXT,
    affects_on_hand INTEGER DEFAULT 1,
    status TEXT DEFAULT 'active',
    sort_order INTEGER,
    description TEXT,
    created_at TEXT
);
CREATE TABLE inventory_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_type_id INTEGER
);
"""


def test_v204_seeds_rcv_wo_type_idempotently():
    import sqlite3
    from meta.migrations import v204__inventory_work_order_receipt_type as v204

    conn = sqlite3.connect(':memory:')
    conn.executescript(_TYPES_DDL)
    v204._do_upgrade(conn)
    v204._do_upgrade(conn)
    row = conn.execute(
        "SELECT category, direction, status FROM inventory_transaction_types "
        "WHERE code = 'RCV_WO'").fetchone()
    assert row == ('receipt', 'in', 'active')
    assert conn.execute(
        'SELECT COUNT(*) FROM inventory_transaction_types '
        "WHERE code = 'RCV_WO'").fetchone()[0] == 1

