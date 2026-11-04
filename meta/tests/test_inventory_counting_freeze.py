# -*- coding: utf-8 -*-
"""INV-4 盘点冻结（posting block）测试（spec FR-007）。

覆盖:
  · posting_block=1 + counting 时日常入库/出库被 INV_COUNT_BLOCKED 拦截；
  · 盘点差异 post 自身 bypass_posting_block=True 豁免；
  · posting_block=0 不拦截；
  · 指定库位只冻结本库位；
  · cancel 后恢复、显式 bypass 放行、手工调整单过账仍被冻结拦截。
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import itertools

import pytest

pytestmark = pytest.mark.unit

from meta.services.inventory_guard_service import (
    INV_COUNT_BLOCKED, InventoryError,
)
from meta.tests import inventory_adjustment_doubles as adj
from meta.tests import inventory_test_doubles as inv

_seq = itertools.count(1)


def _rows(conn, sql, params=None):
    return inv.MemDS(conn).query(sql, params or [])


def _create_count(conn, posting_block=1, location_id=inv.LOCATION_ID,
                  tolerance_qty_abs=10):
    service = adj.count_service(conn)
    data = service.prepare_create({
        'org_id': inv.ORG_ID,
        'location_id': location_id,
        'posting_block': posting_block,
        'tolerance_qty_abs': tolerance_qty_abs,
    })
    return adj.insert_count(conn, data), data, service


def _daily(conn, direction='in', qty=5,
           location_id=inv.LOCATION_ID, bypass=False):
    service = inv.posting_service(conn)
    entry = {
        'transaction_type': 'RCV_PO' if direction == 'in' else 'ISSUE_TO_SHIP',
        'transaction_date': adj.DEFAULT_DATE,
        'org_id': inv.ORG_ID,
        'location_id': location_id,
        'item_id': inv.ITEM_ID,
        'uom_id': inv.UOM_ID,
        'qty': qty,
        'direction': direction,
        'batch_id': None,
        'stock_status': 'unrestricted',
        'source_line_id': '1',
    }
    return service.post([entry], {
        'source_doc_type': 'receipt',
        'source_doc_id': 1,
        'source_event_key': 'daily:%d' % next(_seq),
        'transaction_date': adj.DEFAULT_DATE,
    }, bypass_posting_block=bypass)


def _tx_count(conn):
    return conn.execute('SELECT COUNT(*) FROM inventory_transactions'
                        ).fetchone()[0]


def test_posting_block_blocks_daily_in_and_out():
    conn = adj.build_adjustment_db()
    adj.post_balance(conn, 10)
    count_id, _data, service = _create_count(conn)
    assert service.start(count_id)['status'] == 'counting'

    before = _tx_count(conn)
    with pytest.raises(InventoryError) as exc:
        _daily(conn, direction='in')
    assert exc.value.code == INV_COUNT_BLOCKED
    with pytest.raises(InventoryError) as exc:
        _daily(conn, direction='out', qty=4)
    assert exc.value.code == INV_COUNT_BLOCKED
    assert _tx_count(conn) == before
    assert adj.balance_qty(conn) == 10.0


def test_count_post_bypasses_own_freeze():
    conn = adj.build_adjustment_db()
    adj.post_balance(conn, 10)
    count_id, _data, service = _create_count(conn)
    service.start(count_id)

    # 冻结生效：日常入库被拦
    with pytest.raises(InventoryError) as exc:
        _daily(conn, direction='in')
    assert exc.value.code == INV_COUNT_BLOCKED

    line = _rows(conn, 'SELECT id FROM inventory_count_lines WHERE count_id=?',
                 [count_id])[0]
    conn.execute('UPDATE inventory_count_lines SET counted_qty=? WHERE id=?',
                 [8, line['id']])
    conn.commit()
    service.submit(count_id)
    result = service.post(count_id)

    assert result['status'] == 'posted'
    assert adj.balance_qty(conn) == 8.0
    tx = _rows(conn, 'SELECT source_doc_type FROM inventory_transactions '
                     'WHERE source_event_key=?',
               ['count:%s' % _data['count_no']])
    assert tx and tx[0]['source_doc_type'] == 'inventory_count'


def test_posting_block_zero_does_not_block():
    conn = adj.build_adjustment_db()
    adj.post_balance(conn, 10)
    count_id, _data, service = _create_count(conn, posting_block=0)
    service.start(count_id)

    assert _daily(conn, direction='in', qty=5)['created'] == 1
    assert adj.balance_qty(conn) == 15.0


def test_freeze_is_scoped_to_header_location():
    conn = adj.build_adjustment_db()
    conn.execute(
        "INSERT INTO locations (id, code, name, status, org_id) "
        "VALUES (9, 'LOC9', '库位9', 'active', ?)", [inv.ORG_ID])
    conn.commit()
    adj.post_balance(conn, 10)

    count_id, _data, service = _create_count(conn, location_id=inv.LOCATION_ID)
    service.start(count_id)

    # 同组织另一库位不受冻结影响
    assert _daily(conn, location_id=9)['created'] == 1
    assert adj.balance_qty(conn, location_id=9) == 5.0

    with pytest.raises(InventoryError) as exc:
        _daily(conn, location_id=inv.LOCATION_ID)
    assert exc.value.code == INV_COUNT_BLOCKED


def test_cancel_lifts_freeze():
    conn = adj.build_adjustment_db()
    adj.post_balance(conn, 10)
    count_id, _data, service = _create_count(conn)
    service.start(count_id)
    with pytest.raises(InventoryError) as exc:
        _daily(conn, direction='in')
    assert exc.value.code == INV_COUNT_BLOCKED

    assert service.cancel(count_id)['status'] == 'cancelled'
    assert _daily(conn, direction='in', qty=3)['created'] == 1
    assert adj.balance_qty(conn) == 13.0


def test_bypass_posting_block_flag_allows_daily_posting():
    conn = adj.build_adjustment_db()
    adj.post_balance(conn, 10)
    count_id, _data, service = _create_count(conn)
    service.start(count_id)

    assert _daily(conn, direction='in', qty=2, bypass=True)['created'] == 1
    assert adj.balance_qty(conn) == 12.0


def test_manual_adjustment_posting_is_blocked_by_freeze():
    conn = adj.build_adjustment_db()
    count_id, _data, count_service = _create_count(conn)
    count_service.start(count_id)

    adjustment_service = adj.adjustment_service(conn)
    header = adjustment_service.prepare_create({
        'adjustment_type': 'qty_increase',
        'org_id': inv.ORG_ID,
        'location_id': inv.LOCATION_ID,
        'posting_date': adj.DEFAULT_DATE,
        'reason_code': 'correction',
    })
    header_id = adj.insert_adjustment(conn, header)
    adj.add_adjustment_line(conn, header_id, qty=5,
                            to_stock_status='unrestricted')
    adjustment_service.release(header_id)

    with pytest.raises(InventoryError) as exc:
        adjustment_service.post(header_id)
    assert exc.value.code == INV_COUNT_BLOCKED
    assert _tx_count(conn) == 0
