# -*- coding: utf-8 -*-
"""DOC_FLOW 阶段 3 冲销统一验收

依据: docs/specs/spec-doc-flow-end-to-end-2026-11-05.md §3.4 / §5.4 / §6 阶段 3 / AC-13

覆盖:
  · 收货整单红冲：原「收货行 → 入库事务」边置 reversed，红字边落库（业务锚 = 红字单）
  · 边表缺失时红冲降级：不阻断收货红冲
  · reverse_edges_by_source：全部冲销后消耗视图归零；二次调用 0 新增（幂等）
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.core.doc_flow_attach import reverse_edges_by_source
from meta.migrations import v215__doc_flow_stage2_rules as v215
from meta.services.receipt_service import ReceiptError, ReceiptService
from meta.tests.receipt_test_doubles import MemDS, seeded_db

DOC_TYPE_STD = 1
RULE_ID = 'receipt_line_to_inventory_txn'


class _DS(MemDS):
    """补 insert：红字冲销引擎写边走 DataSource.insert。"""

    def insert(self, table, data):
        cols = list(data)
        cur = self.conn.execute(
            'INSERT INTO %s (%s) VALUES (%s)'
            % (table, ', '.join(cols), ', '.join('?' * len(cols))),
            [data[c] for c in cols])
        return cur.lastrowid


def _flow_tables(conn):
    conn.execute(v215.EDGE_TABLE_DDL)
    for _, ddl in v215.EDGE_INDEXES:
        conn.execute(ddl)
    conn.execute(v215.CONSUMED_VIEW_DDL)


def _post_receipt(conn, qty=100.0):
    svc = _DS(conn)
    receipt = ReceiptService(svc).create_receipt(
        {'document_type_id': DOC_TYPE_STD, 'receipt_date': '2026-11-01',
         'source_doc_id': 1}, [{'schedule_id': 1, 'qty_received': qty}])
    ReceiptService(svc).post(receipt['id'])
    return receipt


def _insert_edge(conn, edge_id, source_id, target_id, qty,
                 status='active', sign='normal', rule_id=RULE_ID):
    conn.execute(
        'INSERT INTO doc_flow_edges (id, source_bo, source_id, source_item, '
        'target_bo, target_id, target_item, quantity, amount, currency, unit, '
        'quantity_sign, rule_id, derived_at, derived_by, status, pool, '
        'source_instance_id, target_instance_id, derive_key) VALUES '
        '(?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [edge_id, 'receipt_line', str(source_id), '', 'inventory_transaction',
         str(target_id), str(source_id), qty, '', '3', sign, rule_id,
         '2026-11-01', 'tester', status, 'inventory_receipt', '', '', ''])


def _edge_rows(conn):
    return _DS(conn).query('SELECT * FROM doc_flow_edges ORDER BY id')


def _consumed(conn, source_id):
    rows = _DS(conn).query(
        'SELECT consumed_qty FROM v_doc_flow_consumed_qty '
        "WHERE source_bo='receipt_line' AND source_id=? AND source_item='' "
        "AND pool='inventory_receipt'", [str(source_id)])
    return float(rows[0]['consumed_qty']) if rows else 0.0


def test_reverse_marks_edge_reversed_and_writes_red_edge():
    conn = seeded_db()
    _flow_tables(conn)
    original = _post_receipt(conn)
    line_id = _DS(conn).query(
        'SELECT id FROM receipt_lines WHERE receipt_id = ?',
        [original['id']])[0]['id']
    _insert_edge(conn, 'edge-1', line_id, 900, 100.0)

    result = ReceiptService(_DS(conn)).reverse(original['id'])
    red_id = result['reversal_receipt_id']

    rows = _edge_rows(conn)
    assert len(rows) == 2
    by_id = {row['id']: row for row in rows}
    assert by_id['edge-1']['status'] == 'reversed'

    red = [row for row in rows if row['quantity_sign'] == 'red']
    assert len(red) == 1
    assert red[0]['rule_id'] == '%s#red:%s' % (RULE_ID, red_id)
    assert red[0]['derive_key'] == 'red:edge-1:%s' % red_id
    assert red[0]['quantity'] == pytest.approx(100.0)
    # A 档反转级联红字子边（防负聚合）
    assert red[0]['status'] == 'reversed'
    assert _consumed(conn, line_id) == 0.0

    # 原单已置 reversed：状态守卫先于红字单守卫拒绝重复冲销
    with pytest.raises(ReceiptError) as exc:
        ReceiptService(_DS(conn)).reverse(original['id'])
    assert exc.value.rule == 'RC_STATE_INVALID'


def test_reverse_degrades_without_edge_table():
    conn = seeded_db()
    original = _post_receipt(conn)

    result = ReceiptService(_DS(conn)).reverse(original['id'])

    assert result['status'] == 'reversed'


def test_reverse_edges_by_source_is_idempotent_and_resets_view():
    conn = seeded_db()
    _flow_tables(conn)
    _insert_edge(conn, 'edge-a', 7, 900, 10.0)
    _insert_edge(conn, 'edge-b', 7, 901, 20.0)
    assert _consumed(conn, 7) == pytest.approx(30.0)

    count = reverse_edges_by_source(
        _DS(conn), RULE_ID, 'receipt_line', 7, ref_id='RED-1',
        derived_by='receipt_service')

    assert count == 2
    assert _consumed(conn, 7) == 0.0
    assert len(_edge_rows(conn)) == 4
    assert all(row['status'] == 'reversed' for row in _edge_rows(conn))

    # 无 active 正向边 → 0 新增、0 变更
    assert reverse_edges_by_source(
        _DS(conn), RULE_ID, 'receipt_line', 7, ref_id='RED-1') == 0
    assert len(_edge_rows(conn)) == 4
