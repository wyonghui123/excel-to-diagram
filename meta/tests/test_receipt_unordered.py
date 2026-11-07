# -*- coding: utf-8 -*-
"""无单收货（source_doc_type=unordered）测试。

覆盖 Oracle「Allow unordered receipts」（组织参数）+「AllowUnorderedReceiptsFlag」
（物料开关）双开口径；对标 SAP 501/511 无采购订单收货。

口径:
  · 参数与物料开关任一关闭 → RC_UNORDERED_DISABLED（fail closed）。
  · source_doc_id 统一填 0（沿用平台「0 = 无引用」约定），source_doc_no 置空。
  · 过账写 RCV_UNORDERED 入库事务；红字单复制来源方 / 原因字段。
"""

import pytest

pytestmark = pytest.mark.unit

from meta.migrations import v230__unordered_receipt as v230
from meta.services.receipt_service import ReceiptError, ReceiptService
from meta.tests import inventory_test_doubles as inv
from meta.tests import receipt_test_doubles as rt

DOC_TYPE_STD = 1
DOC_TYPE_RED = 2
ORG_ID = 1
INVENTORY_ORG_ID = 2
LOCATION_ID = 8
ITEM_ID = 900
UOM_ID = 3
PARTY_ID = 500


def _seeded(param='1', item_flag=1):
    """库存表 + v230 列/移动类型 + 物料主数据 + 无单收货双开关。"""
    conn = rt.seeded_db()
    inv.install_inventory(conn, enable=True)
    v230._do_columns(conn)
    v230._do_type(conn)
    rt.add_item(conn, item_id=ITEM_ID, base_uom=UOM_ID)
    rt.add_uom(conn, uom_id=UOM_ID)
    rt.allow_unordered(conn, param=param, item_id=ITEM_ID, item_flag=item_flag)
    conn.commit()
    return conn


def _svc(conn):
    return ReceiptService(rt.MemDS(conn))


def _header(**over):
    header = {
        'document_type_id': DOC_TYPE_STD,
        'receipt_date': '2026-11-07',
        'source_doc_type': 'unordered',
        'org_id': ORG_ID,
        'inventory_org_id': INVENTORY_ORG_ID,
        'deliver_to_location_id': LOCATION_ID,
        'received_from_party_id': PARTY_ID,
        'reason_code': 'found_stock',
    }
    header.update(over)
    return header


def _lines(qty=10.0, **over):
    line = {'item_id': ITEM_ID, 'uom_id': UOM_ID, 'qty_received': qty}
    line.update(over)
    return [line]


def _create(conn, lines=None, **over):
    return _svc(conn).create_receipt(_header(**over), lines or _lines())


def _receipt(conn, receipt_id):
    rows = rt.MemDS(conn).query('SELECT * FROM receipts WHERE id = ?', [receipt_id])
    return rows[0]


def _transactions(conn):
    return rt.MemDS(conn).query(
        'SELECT t.*, ty.code AS type_code FROM inventory_transactions t '
        'JOIN inventory_transaction_types ty ON ty.id = t.transaction_type_id '
        'ORDER BY t.id')


# ---------------------------------------------------------------- 双开关
def test_param_closed_rejects_create():
    conn = _seeded(param='0')
    with pytest.raises(ReceiptError) as err:
        _create(conn)
    assert err.value.rule == 'RC_UNORDERED_DISABLED'


def test_item_flag_off_rejects_create():
    conn = _seeded(item_flag=0)
    with pytest.raises(ReceiptError) as err:
        _create(conn)
    assert err.value.rule == 'RC_UNORDERED_DISABLED'


# ---------------------------------------------------------------- 抬头必填
def test_received_from_party_required():
    conn = _seeded()
    with pytest.raises(ReceiptError) as err:
        _create(conn, received_from_party_id=None)
    assert err.value.field_name == 'received_from_party_id'


def test_reason_code_required():
    conn = _seeded()
    with pytest.raises(ReceiptError) as err:
        _create(conn, reason_code='')
    assert err.value.field_name == 'reason_code'


def test_reason_code_must_be_known():
    conn = _seeded()
    with pytest.raises(ReceiptError) as err:
        _create(conn, reason_code='whatever')
    assert err.value.rule == 'RC_UNORDERED_REASON_INVALID'


def test_doc_type_must_be_standard():
    conn = _seeded()
    with pytest.raises(ReceiptError) as err:
        _create(conn, document_type_id=DOC_TYPE_RED)
    assert err.value.rule == 'RC_DOC_TYPE_INVALID'


# ---------------------------------------------------------------- 建单
def test_create_sets_zero_source_and_keeps_origin():
    conn = _seeded()
    result = _create(conn)
    row = _receipt(conn, result['id'])

    assert result['source_doc_id'] == 0
    assert row['source_doc_type'] == 'unordered'
    assert row['source_doc_id'] == 0
    assert row['source_doc_no'] is None
    assert row['received_from_party_id'] == PARTY_ID
    assert row['reason_code'] == 'found_stock'
    assert row['purchase_org_id'] is None
    assert row['supplier_party_id'] is None
    assert row['receipt_no'].startswith('RCV-')


# ---------------------------------------------------------------- 过账
def test_post_writes_rcv_unordered():
    conn = _seeded()
    receipt = _create(conn, lines=_lines(qty=10.0))
    _svc(conn).post(receipt['id'])

    row = _receipt(conn, receipt['id'])
    assert row['status'] == 'posted'
    assert row['actual_arrival_date']

    txs = _transactions(conn)
    assert len(txs) == 1
    assert txs[0]['type_code'] == 'RCV_UNORDERED'
    assert txs[0]['direction'] == 'in'
    assert txs[0]['qty'] == 10.0
    assert txs[0]['org_id'] == INVENTORY_ORG_ID
    assert txs[0]['source_doc_type'] == 'receipt'
    assert txs[0]['source_event_key'] == 'receipt:%s:post' % receipt['id']

    balance = rt.MemDS(conn).query(
        'SELECT qty_on_hand FROM inventory_balances '
        'WHERE org_id = ? AND location_id = ? AND item_id = ? '
        'AND batch_id = 0 AND stock_status = ?',
        [INVENTORY_ORG_ID, LOCATION_ID, ITEM_ID, 'unrestricted'])[0]
    assert balance['qty_on_hand'] == 10.0


def test_post_rechecks_item_flag():
    conn = _seeded()
    receipt = _create(conn)
    rt.set_item_unordered(conn, item_flag=0, item_id=ITEM_ID)
    conn.commit()
    with pytest.raises(ReceiptError) as err:
        _svc(conn).post(receipt['id'])
    assert err.value.rule == 'RC_UNORDERED_DISABLED'


# ---------------------------------------------------------------- 红冲
def test_reversal_copies_unordered_origin():
    conn = _seeded()
    receipt = _create(conn)
    _svc(conn).post(receipt['id'])

    red = _svc(conn).create_reversal_document(
        receipt['id'], receipt_date='2026-11-07', receipt_no='RCV-RED-0001')
    red_row = _receipt(conn, red['id'])

    assert red_row['reversal_of_receipt_id'] == receipt['id']
    assert red_row['source_doc_type'] == 'unordered'
    assert red_row['source_doc_id'] == 0
    assert red_row['received_from_party_id'] == PARTY_ID
    assert red_row['reason_code'] == 'found_stock'
    assert red_row['status'] == 'posted'