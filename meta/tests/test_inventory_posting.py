# -*- coding: utf-8 -*-
"""INV-1 库存过账单元测试（guard / posting / opening / rebuild）。

覆盖:
  FR-001 事务账追加 / FR-003 余额投影 / FR-008 幂等反冲
  FR-009 维度一致性 / FR-010 负库存 / FR-012 重建对账 / FR-013 期初导入
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.services.inventory_guard_service import (
    ALL_STATUSES, InventoryError,
)
from meta.tests import inventory_test_doubles as inv


def _entry(**extra):
    entry = {
        'transaction_type': 'RCV_PO',
        'transaction_date': '2026-11-03',
        'org_id': inv.ORG_ID,
        'location_id': inv.LOCATION_ID,
        'item_id': inv.ITEM_ID,
        'uom_id': inv.UOM_ID,
        'qty': 10.0,
        'source_line_id': 1,
    }
    entry.update(extra)
    return entry


def _source(**extra):
    source = {
        'source_doc_type': 'receipt',
        'source_doc_id': 1,
        'source_event_key': 'receipt:1:post',
        'transaction_date': '2026-11-03',
    }
    source.update(extra)
    return source


def _rows(conn, sql, params=None):
    return inv.MemDS(conn).query(sql, params or [])


# ---------------- 入账 / 余额 ----------------

def test_post_inbound_creates_transaction_and_balance():
    conn = inv.seed()
    svc = inv.posting_service(conn)

    result = svc.post([_entry()], _source())

    assert result['created'] == 1
    tx = _rows(conn, 'SELECT * FROM inventory_transactions')[0]
    assert tx['transaction_no'] == 'INV-202611-000001'
    assert tx['direction'] == 'in'
    assert tx['qty'] == 10.0 and tx['base_qty'] == 10.0
    assert tx['stock_status'] == 'unrestricted'
    assert tx['source_doc_type'] == 'receipt'
    balance = _rows(conn, 'SELECT * FROM inventory_balances')[0]
    assert balance['qty_on_hand'] == 10.0
    assert balance['batch_id'] == 0


def test_duplicate_post_is_idempotent():
    conn = inv.seed()
    svc = inv.posting_service(conn)

    first = svc.post([_entry()], _source())
    second = svc.post([_entry()], _source())

    assert first['created'] == 1
    assert second['created'] == 0
    assert len(second['existing']) == 1
    assert len(_rows(conn, 'SELECT * FROM inventory_transactions')) == 1
    balance = _rows(conn, 'SELECT * FROM inventory_balances')[0]
    assert balance['qty_on_hand'] == 10.0


def test_outbound_decreases_balance():
    conn = inv.seed()
    svc = inv.posting_service(conn)
    svc.post([_entry(qty=10.0)], _source())
    svc.post(
        [_entry(transaction_type='ISSUE_TO_SHIP', direction='out',
                qty=4.0, source_line_id=2)],
        _source(source_event_key='transfer_order:1:ship:1'))

    balance = _rows(conn, 'SELECT * FROM inventory_balances')[0]
    assert balance['qty_on_hand'] == 6.0


def test_negative_stock_rejected_by_default():
    conn = inv.seed()
    svc = inv.posting_service(conn)

    with pytest.raises(InventoryError) as exc:
        svc.post(
            [_entry(transaction_type='ISSUE_TO_SHIP', direction='out',
                    qty=5.0)],
            _source(source_event_key='transfer_order:1:ship:1'))

    assert exc.value.code == 'INV_NEGATIVE_STOCK'
    assert _rows(conn, 'SELECT * FROM inventory_transactions') == []


def test_negative_stock_allowed_when_parameter_on():
    conn = inv.seed(allow_negative=True)
    svc = inv.posting_service(conn)

    result = svc.post(
        [_entry(transaction_type='ISSUE_TO_SHIP', direction='out', qty=5.0)],
        _source(source_event_key='transfer_order:1:ship:1'))

    assert result['created'] == 1
    balance = _rows(conn, 'SELECT * FROM inventory_balances')[0]
    assert balance['qty_on_hand'] == -5.0


def test_posting_disabled_switch_skips():
    conn = inv.seed()
    inv.enable_posting(conn, False)
    svc = inv.posting_service(conn)

    result = svc.post([_entry()], _source())

    assert result['skipped'] is True
    assert result['created'] == 0
    assert _rows(conn, 'SELECT * FROM inventory_transactions') == []


# ---------------- 反冲 ----------------

def test_reverse_creates_reversal_and_restores_balance():
    conn = inv.seed()
    svc = inv.posting_service(conn)
    svc.post([_entry(qty=10.0)], _source())
    original = _rows(conn, 'SELECT * FROM inventory_transactions')[0]

    result = svc.reverse([original['id']], _source(
        source_event_key='receipt:1:reverse'))

    assert result['created'] == 1
    assert len(_rows(conn, 'SELECT * FROM inventory_transactions')) == 2
    reversal = _rows(
        conn, "SELECT * FROM inventory_transactions WHERE direction = 'out'")[0]
    assert reversal['reversal_of_transaction_id'] == original['id']
    assert reversal['base_qty'] == 10.0
    balance = _rows(conn, 'SELECT * FROM inventory_balances')[0]
    assert balance['qty_on_hand'] == 0.0


def test_reverse_is_idempotent_and_reversal_cannot_reverse():
    conn = inv.seed()
    svc = inv.posting_service(conn)
    svc.post([_entry()], _source())
    original = _rows(conn, 'SELECT * FROM inventory_transactions')[0]
    svc.reverse([original['id']], _source(
        source_event_key='receipt:1:reverse'))
    reversal = _rows(
        conn, "SELECT * FROM inventory_transactions WHERE direction = 'out'")[0]

    again = svc.reverse([original['id']], _source(
        source_event_key='receipt:1:reverse'))
    assert again['created'] == 0 and len(again['existing']) == 1

    with pytest.raises(InventoryError) as exc:
        svc.reverse([reversal['id']], _source(
            source_event_key='receipt:1:reverse-2'))
    assert exc.value.code == 'INV_REVERSAL_INVALID'


def test_reverse_by_source_skips_when_nothing_posted():
    conn = inv.seed()
    svc = inv.posting_service(conn)

    result = svc.reverse_by_source('receipt:99:post',
                                   _source(source_event_key='receipt:99:reverse'))

    assert result['created'] == 0


# ---------------- 维度守卫 ----------------

def test_org_without_inventory_function_rejected():
    conn = inv.seed()
    conn.execute("INSERT INTO orgs (id, status) VALUES (3, 'active')")
    conn.execute("INSERT INTO locations (id, org_id) VALUES (9, 3)")
    svc = inv.posting_service(conn)

    with pytest.raises(InventoryError) as exc:
        svc.post([_entry(org_id=3, location_id=9)], _source())
    assert exc.value.code == 'INV_ORG_INVALID'


def test_location_org_mismatch_rejected():
    conn = inv.seed()
    svc = inv.posting_service(conn)

    with pytest.raises(InventoryError) as exc:
        svc.post([_entry(location_id=inv.OTHER_LOCATION_ID)], _source())
    assert exc.value.code == 'INV_LOCATION_ORG_MISMATCH'


def test_missing_location_falls_back_to_org_default():
    conn = inv.seed()
    svc = inv.posting_service(conn)

    result = svc.post([_entry(location_id=None)], _source())

    assert result['created'] == 1
    tx = _rows(conn, 'SELECT * FROM inventory_transactions')[0]
    assert tx['location_id'] == inv.LOCATION_ID


def test_missing_location_without_default_rejected():
    conn = inv.seed()
    conn.execute(
        'UPDATE orgs SET default_inventory_location_id = NULL WHERE id = ?',
        [inv.ORG_ID])
    inv.enable_posting(conn)
    svc = inv.posting_service(conn)

    with pytest.raises(InventoryError) as exc:
        svc.post([_entry(location_id=None)], _source())
    assert exc.value.code == 'INV_LOCATION_REQUIRED'


def test_batch_item_mismatch_rejected():
    conn = inv.seed()
    conn.execute(
        "INSERT INTO items (id, code, name, status, base_uom) "
        "VALUES (901, 'I901', '物料901', 'active', 3)")
    svc = inv.posting_service(conn)

    with pytest.raises(InventoryError) as exc:
        svc.post([_entry(item_id=901, batch_id=inv.BATCH_ID)], _source())
    assert exc.value.code == 'INV_BATCH_MISMATCH'


def test_batch_blocked_cannot_issue():
    conn = inv.seed()
    conn.execute(
        "UPDATE batches SET quality_status = 'blocked' WHERE id = ?",
        [inv.BATCH_ID])
    svc = inv.posting_service(conn)
    svc.post([_entry(qty=10.0, batch_id=inv.BATCH_ID)], _source())

    with pytest.raises(InventoryError) as exc:
        svc.post(
            [_entry(transaction_type='ISSUE_TO_SHIP', direction='out',
                    qty=5.0, batch_id=inv.BATCH_ID, source_line_id=2)],
            _source(source_event_key='transfer_order:1:ship:1'))
    assert exc.value.code == 'INV_BATCH_BLOCKED'


def test_uom_not_convertible_rejected():
    conn = inv.seed()
    svc = inv.posting_service(conn)

    with pytest.raises(InventoryError) as exc:
        svc.post([_entry(uom_id=4)], _source())
    assert exc.value.code == 'INV_UOM_INVALID'


def test_type_direction_conflict_rejected():
    conn = inv.seed()
    svc = inv.posting_service(conn)

    with pytest.raises(InventoryError) as exc:
        svc.post([_entry(direction='out')], _source())
    assert exc.value.code == 'INV_TYPE_INVALID'


def test_inactive_type_rejected():
    conn = inv.seed()
    conn.execute(
        "UPDATE inventory_transaction_types SET status = 'inactive' "
        "WHERE code = 'RCV_PO'")
    svc = inv.posting_service(conn)

    with pytest.raises(InventoryError) as exc:
        svc.post([_entry()], _source())
    assert exc.value.code == 'INV_TYPE_INVALID'


def test_daily_posting_rejects_non_unrestricted_status():
    conn = inv.seed()
    svc = inv.posting_service(conn)

    with pytest.raises(InventoryError) as exc:
        svc.post([_entry(stock_status='inspection')], _source())
    assert exc.value.code == 'INV_STATUS_INVALID'


# ---------------- 期初导入 ----------------

def test_opening_allows_three_statuses_and_is_idempotent():
    conn = inv.seed()
    svc = inv.opening_service(conn)
    rows = [
        {'org_id': inv.ORG_ID, 'location_id': inv.LOCATION_ID,
         'item_id': inv.ITEM_ID, 'uom_id': inv.UOM_ID, 'qty': 10.0,
         'stock_status': status}
        for status in ALL_STATUSES
    ]

    first = svc.import_opening(rows, batch_no='OPEN-2026-11')
    second = svc.import_opening(rows, batch_no='OPEN-2026-11')

    assert first['created'] == 3
    assert second['created'] == 0 and len(second['existing']) == 3
    balances = _rows(conn, 'SELECT * FROM inventory_balances '
                           'ORDER BY stock_status')
    assert {row['stock_status'] for row in balances} == set(ALL_STATUSES)
    assert all(row['qty_on_hand'] == 10.0 for row in balances)
    txs = _rows(conn, "SELECT * FROM inventory_transactions "
                      "WHERE transaction_type_id = (SELECT id FROM "
                      "inventory_transaction_types WHERE code = 'OPENING')")
    assert len(txs) == 3


def test_opening_rolls_back_whole_batch_on_failure():
    conn = inv.seed()
    svc = inv.opening_service(conn)
    rows = [
        {'org_id': inv.ORG_ID, 'location_id': inv.LOCATION_ID,
         'item_id': inv.ITEM_ID, 'uom_id': inv.UOM_ID, 'qty': 10.0},
        {'org_id': inv.ORG_ID, 'location_id': inv.LOCATION_ID,
         'item_id': 999, 'uom_id': inv.UOM_ID, 'qty': 5.0},
    ]

    with pytest.raises(InventoryError):
        svc.import_opening(rows, batch_no='OPEN-BAD')

    assert _rows(conn, 'SELECT * FROM inventory_transactions') == []
    assert _rows(conn, 'SELECT * FROM inventory_balances') == []


# ---------------- 重建 / 对账 ----------------

def test_diff_report_detects_drift_and_rebuild_fixes_it():
    conn = inv.seed()
    svc = inv.posting_service(conn)
    svc.post([_entry(qty=10.0)], _source())

    conn.execute(
        'UPDATE inventory_balances SET qty_on_hand = 7 WHERE item_id = ?',
        [inv.ITEM_ID])
    report = svc.diff_report()

    assert report['ok'] is False
    assert report['diff_count'] == 1
    assert report['rows'][0]['account_qty'] == 10.0
    assert report['rows'][0]['balance_qty'] == 7.0
    assert report['rows'][0]['diff'] == 3.0

    rebuilt = svc.rebuild_balances()

    assert rebuilt['rows'] == 1
    balance = _rows(conn, 'SELECT * FROM inventory_balances')[0]
    assert balance['qty_on_hand'] == 10.0
    assert svc.diff_report()['ok'] is True


def test_diff_report_flags_orphan_balance():
    conn = inv.seed()
    svc = inv.posting_service(conn)
    conn.execute(
        'INSERT INTO inventory_balances (org_id, location_id, item_id, '
        'batch_id, stock_status, qty_on_hand, qty_reserved) '
        "VALUES (?, ?, ?, 0, 'unrestricted', 5, 0)",
        [inv.ORG_ID, inv.LOCATION_ID, inv.ITEM_ID])

    report = svc.diff_report()

    assert report['diff_count'] == 1
    assert report['rows'][0]['orphan_balance'] is True
    assert report['rows'][0]['account_qty'] == 0.0
