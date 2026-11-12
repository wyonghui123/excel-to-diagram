# -*- coding: utf-8 -*-
"""INV-1 收货桥接测试：PO 收货 → RCV_PO，TO 收货 → RCV_TO，红冲 → REVERSAL。

覆盖 spec FR-004 / FR-008 / FR-009 / 9.4 集成口径。
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.services.receipt_service import ReceiptError, ReceiptService
from meta.tests import inventory_test_doubles as inv
from meta.tests import receipt_test_doubles as rt

DOC_TYPE_STD = 1
ORG_ID = 2
LOCATION_ID = 8

TRANSFER_SCHEMA = """
CREATE TABLE transfer_orders (
    id INTEGER PRIMARY KEY,
    transfer_order_no TEXT,
    document_type_id INTEGER,
    transfer_date TEXT,
    status TEXT,
    approval_status TEXT,
    fulfillment_status TEXT,
    from_org_id INTEGER,
    to_org_id INTEGER,
    legal_entity_id INTEGER,
    from_location_id INTEGER,
    to_location_id INTEGER,
    project_id INTEGER,
    actual_ship_date TEXT,
    carrier_name TEXT,
    waybill_no TEXT,
    reversal_of_transfer_id INTEGER,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE transfer_order_lines (
    id INTEGER PRIMARY KEY,
    transfer_order_id INTEGER,
    line_no INTEGER,
    line_type_id INTEGER,
    item_id INTEGER,
    uom_id INTEGER,
    qty REAL,
    qty_shipped REAL DEFAULT 0,
    qty_received REAL DEFAULT 0,
    status TEXT,
    fulfillment_status TEXT,
    created_at TEXT,
    updated_at TEXT
);
"""


def _seeded(enable=True):
    """PO 收货种子 + 库存表/主数据。

    `seeded_db` 的库位 8 归属库存组织 2；补 items/uoms 让守卫可换算基本单位。
    """
    conn = rt.seeded_db()
    inv.install_inventory(conn, enable=enable)
    conn.execute(
        "INSERT OR IGNORE INTO items (id, code, name, status, base_uom) "
        "VALUES (900, 'ITEM900', '物料900', 'active', 3)")
    conn.execute(
        "INSERT OR IGNORE INTO uoms (id, code, name, status) "
        "VALUES (3, 'UOM3', '单位3', 'active')")
    conn.commit()
    return conn


def _svc(conn):
    return ReceiptService(rt.MemDS(conn))


def _create_po_receipt(conn, qty=100.0, inventory_org_id=ORG_ID,
                       location_id=LOCATION_ID):
    header = {
        'document_type_id': DOC_TYPE_STD,
        'receipt_date': '2026-11-03',
        'source_doc_id': 1,
    }
    if inventory_org_id is not None:
        header['inventory_org_id'] = inventory_org_id
    if location_id is not None:
        header['deliver_to_location_id'] = location_id
    return _svc(conn).create_receipt(
        header, [{'schedule_id': 1, 'qty_received': qty}])


def _transactions(conn):
    return inv.MemDS(conn).query(
        'SELECT t.*, ty.code AS type_code '
        'FROM inventory_transactions t '
        'JOIN inventory_transaction_types ty ON ty.id = t.transaction_type_id '
        'ORDER BY t.id')


def _balance(conn):
    rows = inv.MemDS(conn).query(
        'SELECT * FROM inventory_balances WHERE org_id = ? AND location_id = ? '
        'AND item_id = 900 AND batch_id = 0 AND stock_status = ?',
        [ORG_ID, LOCATION_ID, 'unrestricted'])
    return rows[0] if rows else None


def _add_transfer_order(conn):
    """补最小调拨单表；TO 1 已发货 100 待收，收货组织 = 2，收货库位 = 8。"""
    conn.executescript(TRANSFER_SCHEMA)
    conn.execute(
        "INSERT INTO transfer_orders (id, transfer_order_no, document_type_id, "
        "transfer_date, status, approval_status, fulfillment_status, "
        "from_org_id, to_org_id, legal_entity_id, to_location_id) "
        "VALUES (1, 'TO-0001', NULL, '2026-11-03', 'released', "
        "'not_required', 'shipped', 2, 2, 1, 8)")
    conn.execute(
        "INSERT INTO transfer_order_lines (id, transfer_order_id, line_no, "
        "line_type_id, item_id, uom_id, qty, qty_shipped, qty_received, "
        "status, fulfillment_status) "
        "VALUES (100, 1, 10, NULL, 900, 3, 100, 100, 0, 'open', 'shipped')")
    conn.commit()


# ---------------- PO 收货 ----------------

def test_po_receipt_post_writes_rcv_po():
    conn = _seeded()
    receipt = _create_po_receipt(conn)
    _svc(conn).post(receipt['id'])

    tx = _transactions(conn)
    assert len(tx) == 1
    assert tx[0]['type_code'] == 'RCV_PO'
    assert tx[0]['direction'] == 'in'
    assert tx[0]['qty'] == 100.0
    assert tx[0]['org_id'] == ORG_ID
    assert tx[0]['location_id'] == LOCATION_ID
    assert tx[0]['source_doc_type'] == 'receipt'
    assert tx[0]['source_event_key'] == 'receipt:%s:post' % receipt['id']

    balance = _balance(conn)
    assert balance['qty_on_hand'] == 100.0


def test_po_receipt_post_is_idempotent_for_inventory():
    conn = _seeded()
    receipt = _create_po_receipt(conn)
    svc = _svc(conn)
    svc.post(receipt['id'])
    svc.post(receipt['id'])  # 已过账 → 服务直接幂等返回

    assert len(_transactions(conn)) == 1


def test_po_receipt_reverse_writes_reversal():
    conn = _seeded()
    receipt = _create_po_receipt(conn)
    svc = _svc(conn)
    svc.post(receipt['id'])
    svc.reverse(receipt['id'])

    tx = _transactions(conn)
    assert [row['type_code'] for row in tx] == ['RCV_PO', 'REVERSAL']
    assert tx[1]['direction'] == 'out'
    assert tx[1]['base_qty'] == 100.0
    assert tx[1]['reversal_of_transaction_id'] == tx[0]['id']
    assert _balance(conn)['qty_on_hand'] == 0.0


def test_po_receipt_without_inventory_org_raises():
    conn = _seeded()
    receipt = _create_po_receipt(conn, inventory_org_id=None,
                                 location_id=None)

    with pytest.raises(ReceiptError) as exc:
        _svc(conn).post(receipt['id'])
    assert exc.value.rule == 'INV_ORG_REQUIRED'
    assert exc.value.field_name == 'inventory'
    assert _transactions(conn) == []


def test_po_receipt_post_skips_when_switch_off():
    conn = _seeded(enable=False)
    receipt = _create_po_receipt(conn)
    _svc(conn).post(receipt['id'])

    assert _transactions(conn) == []
    assert inv.MemDS(conn).query(
        'SELECT id FROM receipts WHERE id = ?', [receipt['id']])[0]


# ---------------- TO 收货 ----------------

def test_transfer_receipt_post_writes_rcv_to():
    conn = _seeded()
    _add_transfer_order(conn)
    receipt = _svc(conn).create_from_transfer_order(1)

    header = inv.MemDS(conn).query(
        'SELECT * FROM receipts WHERE id = ?', [receipt['id']])[0]
    assert header['inventory_org_id'] == ORG_ID
    assert header['deliver_to_location_id'] == LOCATION_ID

    _svc(conn).post(receipt['id'])

    tx = _transactions(conn)
    assert len(tx) == 1
    assert tx[0]['type_code'] == 'RCV_TO'
    assert tx[0]['direction'] == 'in'
    assert tx[0]['qty'] == 100.0
    assert tx[0]['source_doc_type'] == 'receipt'

    balance = _balance(conn)
    assert balance['qty_on_hand'] == 100.0

    line = inv.MemDS(conn).query(
        'SELECT * FROM transfer_order_lines WHERE id = 100')[0]
    assert line['qty_received'] == 100.0
