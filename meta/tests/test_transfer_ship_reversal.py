# -*- coding: utf-8 -*-
"""调拨发货侧红冲（D5）验收

依据: docs/specs/spec-reversal-platform-2026-11-06.md §12 阶段 D5

覆盖:
  T1 全链路：发货 → 红冲 → 库存回补、REVERSAL 分录、红字补偿边、
     头 reversed、行发货归零、履约回 open、幂等
  T2 守卫：已收货 / 未发货 / 草稿 / 取消 拒绝
  T3 编排路径：经 ReversalOrchestrator，透传 line_ids；已红冲 replay
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.core.doc_flow_rule_store import upsert_rules
from meta.migrations import v215__doc_flow_stage2_rules as v215
from meta.services.transfer_order_service import (
    TransferOrderError, TransferOrderService)
from meta.tests import inventory_test_doubles as inv

_ORDER_ID = 1
_LINE_ID = 100
_TO_ORDER_ID = 2
_TO_LINE_ID = 200

_TO_DDL = """
CREATE TABLE transfer_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transfer_order_no TEXT NOT NULL UNIQUE,
    document_type_id INTEGER,
    transfer_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    approval_status TEXT NOT NULL DEFAULT 'not_required',
    fulfillment_status TEXT,
    from_org_id INTEGER NOT NULL,
    to_org_id INTEGER NOT NULL,
    legal_entity_id INTEGER NOT NULL,
    from_location_id INTEGER,
    to_location_id INTEGER,
    project_id INTEGER,
    actual_ship_date TEXT,
    carrier_name TEXT,
    waybill_no TEXT,
    reversal_of_transfer_id INTEGER,
    remark TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE transfer_order_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transfer_order_id INTEGER NOT NULL,
    line_no INTEGER NOT NULL,
    line_type_id INTEGER,
    item_id INTEGER,
    uom_id INTEGER,
    qty REAL NOT NULL DEFAULT 0,
    qty_shipped REAL NOT NULL DEFAULT 0,
    qty_received REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'open',
    fulfillment_status TEXT,
    remark TEXT,
    created_by TEXT,
    updated_by TEXT,
    created_at TEXT,
    updated_at TEXT,
    UNIQUE (transfer_order_id, line_no)
);
"""


class _TransferDS(inv.MemDS):
    def insert(self, table, data):
        cols = list(data)
        cur = self.conn.execute(
            'INSERT INTO %s (%s) VALUES (%s)'
            % (table, ', '.join(cols), ', '.join('?' * len(cols))),
            [data[c] for c in cols])
        return cur.lastrowid


def _db(status='released', shipped=0.0, received=0.0):
    conn = inv.build_db()
    inv.seed(conn)
    conn.executescript(_TO_DDL)
    conn.execute(v215.RULE_TABLE_DDL)
    conn.execute(v215.EDGE_TABLE_DDL)
    for _, ddl in v215.EDGE_INDEXES:
        conn.execute(ddl)
    conn.execute(v215.CONSUMED_VIEW_DDL)
    ds = _TransferDS(conn)
    upsert_rules(ds, [dict(rule) for rule in v215.RULES
                      if rule['rule_id'] == 'transfer_order_line_to_issue_txn'])
    _seed_order(conn, status=status)
    _seed_line(conn, shipped=shipped, received=received)
    conn.commit()
    return conn


def _seed_order(conn, status='released'):
    conn.execute(
        'INSERT INTO transfer_orders (id, transfer_order_no, transfer_date, '
        'status, approval_status, fulfillment_status, from_org_id, to_org_id, '
        'legal_entity_id, from_location_id, to_location_id) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [_ORDER_ID, 'TO-0001', '2026-11-06', status, 'approved', 'open',
         inv.ORG_ID, inv.OTHER_ORG_ID, inv.ORG_ID, inv.LOCATION_ID,
         inv.OTHER_LOCATION_ID])


def _seed_line(conn, shipped=0.0, received=0.0):
    conn.execute(
        'INSERT INTO transfer_order_lines (id, transfer_order_id, line_no, '
        'item_id, uom_id, qty, qty_shipped, qty_received, status) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [_LINE_ID, _ORDER_ID, 10, inv.ITEM_ID, inv.UOM_ID, 100.0,
         shipped, received, 'open'])


def _service(conn):
    ds = _TransferDS(conn)
    return TransferOrderService(ds, platform_data_source=ds)


def _seed_balance(conn, qty=100.0):
    conn.execute(
        'INSERT INTO inventory_balances (org_id, location_id, item_id, batch_id, '
        'stock_status, stock_segment_type, project_id, project_task_id, '
        'sales_order_line_id, owner_party_id, qty_on_hand, qty_reserved) '
        "VALUES (?, ?, ?, 0, 'unrestricted', 'owned', 0, 0, 0, 0, ?, 0)",
        [inv.ORG_ID, inv.LOCATION_ID, inv.ITEM_ID, qty])


def _qty_on_hand(conn):
    return conn.execute(
        'SELECT qty_on_hand FROM inventory_balances WHERE org_id=? AND '
        'location_id=? AND item_id=?',
        [inv.ORG_ID, inv.LOCATION_ID, inv.ITEM_ID]).fetchone()[0]


def _txns(conn):
    return conn.execute(
        'SELECT tt.code, t.direction, t.qty, t.source_event_key, '
        't.reversal_of_transaction_id '
        'FROM inventory_transactions t JOIN inventory_transaction_types tt '
        'ON tt.id = t.transaction_type_id ORDER BY t.id').fetchall()


def _edges(conn):
    return conn.execute(
        'SELECT rule_id, quantity_sign, status, derive_key, reverses_edge_id, '
        'id FROM doc_flow_edges ORDER BY rowid').fetchall()


# ------------------------------------------------------------ T1 全链路

def test_reverse_shipment_restores_facts_and_is_idempotent():
    conn = _db()
    _seed_balance(conn, 100.0)
    svc = _service(conn)
    shipped = svc.ship(_ORDER_ID, [{'line_id': _LINE_ID, 'qty': 10.0}])
    assert shipped['status'] == 'released'
    assert _qty_on_hand(conn) == 90.0
    assert len(_txns(conn)) == 1
    assert len(_edges(conn)) == 1

    result = svc.reverse_shipment(_ORDER_ID, reason='发货数量录错')
    assert result['status'] == 'reversed'
    assert result['fulfillment_status'] == 'open'
    assert _qty_on_hand(conn) == 100.0

    txns = _txns(conn)
    assert len(txns) == 2
    assert txns[1][0] == 'REVERSAL' and txns[1][1] == 'in'
    assert txns[1][3] == 'transfer_order:1:ship:1:reverse'
    assert txns[1][4] == 1

    edges = _edges(conn)
    assert [e[0].split('#rev:')[0] for e in edges] == [
        'transfer_order_line_to_issue_txn',
        'transfer_order_line_to_issue_txn']
    assert edges[1][1] == 'red' and edges[1][2] == 'active'
    assert edges[1][0].endswith('#rev:%s' % _ORDER_ID)
    assert str(edges[1][3]).startswith('rev:')
    assert str(edges[1][4]) == str(edges[0][5])

    header = conn.execute(
        'SELECT status FROM transfer_orders WHERE id=?',
        [_ORDER_ID]).fetchone()
    assert header[0] == 'reversed'
    line = conn.execute(
        'SELECT qty_shipped, qty_received, fulfillment_status '
        'FROM transfer_order_lines WHERE id=?', [_LINE_ID]).fetchone()
    assert line[0] == 0.0 and line[1] == 0.0
    assert line[2] == 'open'

    again = svc.reverse_shipment(_ORDER_ID)
    assert again['idempotent'] is True
    assert len(_txns(conn)) == 2
    assert len(_edges(conn)) == 2


# ------------------------------------------------------------ T2 守卫

def test_reverse_shipment_guards_received_and_unshipped():
    received_conn = _db(shipped=10.0, received=2.0)
    with pytest.raises(TransferOrderError) as exc:
        _service(received_conn).reverse_shipment(_ORDER_ID)
    assert exc.value.rule == 'TO_RECEIVED_CANNOT_REVERSE'

    unshipped_conn = _db()
    with pytest.raises(TransferOrderError) as exc:
        _service(unshipped_conn).reverse_shipment(_ORDER_ID)
    assert exc.value.rule == 'TO_SHIP_NOT_FOUND'

    draft_conn = _db(status='draft', shipped=10.0)
    with pytest.raises(TransferOrderError) as exc:
        _service(draft_conn).reverse_shipment(_ORDER_ID)
    assert exc.value.rule == 'TO_STATE_INVALID'

    cancelled_conn = _db(status='cancelled', shipped=10.0)
    with pytest.raises(TransferOrderError) as exc:
        _service(cancelled_conn).reverse_shipment(_ORDER_ID)
    assert exc.value.rule == 'TO_TERMINAL_IMMUTABLE'


# ------------------------------------------------------------ T3 编排路径

class _Outcome(object):
    replay = False
    document = None


def test_reverse_shipment_goes_through_orchestrator(monkeypatch):
    conn = _db(shipped=10.0)
    seen = []

    def fake_execute(ds, **kwargs):
        seen.append((kwargs.get('schema_id'), kwargs.get('doc_id'),
                     (kwargs.get('params') or {}).get('line_ids')))
        return _Outcome()

    monkeypatch.setattr(
        'meta.core.reversal_orchestrator.execute', fake_execute)
    result = _service(conn).reverse_shipment(_ORDER_ID, reason='录错')
    assert seen == [('transfer_order', _ORDER_ID, [_LINE_ID])]
    assert result['idempotent'] is False

    conn.execute('UPDATE transfer_orders SET status=? WHERE id=?',
                 ['reversed', _ORDER_ID])
    replay = _service(conn).reverse_shipment(_ORDER_ID)
    assert replay['idempotent'] is True
    assert len(seen) == 1
