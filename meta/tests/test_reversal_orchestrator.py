# -*- coding: utf-8 -*-
"""冲销编排层：档位分派 + 按源整体冲销（复用 doc_flow 边引擎）。"""

import pytest

from meta.core.datasource import (
    _clear_data_source_cache_for_testing,
    get_data_source,
)
from meta.core.doc_flow_schema import ensure_doc_flow_edge_tables
from meta.core.reversal_orchestrator import (
    resolve_mode,
    reverse_document,
    reverse_document_edges,
)

RULE_ID = 'receipt_line_to_inventory_txn'


@pytest.fixture
def app_ds(tmp_path, monkeypatch):
    monkeypatch.setenv('SQLITE_DB_DIR', str(tmp_path / 'db'))
    _clear_data_source_cache_for_testing()
    ds = get_data_source('sqlite', database=str(tmp_path / 'biz.db'))
    ensure_doc_flow_edge_tables(ds)
    yield ds
    _clear_data_source_cache_for_testing()


def _edge(ds, edge_id, source_id='L1', qty=10):
    ds.insert('doc_flow_edges', {
        'id': edge_id,
        'source_bo': 'receipt_line',
        'source_id': str(source_id),
        'source_item': '',
        'target_bo': 'inventory_txn',
        'target_id': 'T-' + edge_id,
        'target_item': '',
        'quantity': qty,
        'rule_id': RULE_ID,
        'quantity_sign': 'normal',
        'status': 'active',
        'pool': 'default',
    })


def _rows(ds):
    return {row['id']: row for row in
            ds.query('SELECT id, quantity_sign, status FROM doc_flow_edges')}


def test_resolve_mode_uses_profile():
    assert resolve_mode('receipt') == 'red_reverse'
    assert resolve_mode('shipment') == 'counter'


def test_unknown_document_raises():
    with pytest.raises(KeyError):
        resolve_mode('no_such_doc')


def test_reason_required_before_touching_edges(app_ds):
    _edge(app_ds, 'e1')
    with pytest.raises(ValueError):
        reverse_document(app_ds, app_ds, 'receipt', edge_id='e1',
                         reason='  ', ref_id='RED-1', quantity=10)
    assert _rows(app_ds)['e1']['status'] == 'active'


def test_red_reverse_writes_red_edge_and_flips_original(app_ds):
    _edge(app_ds, 'e1', qty=10)
    reverse_document(app_ds, app_ds, 'receipt', edge_id='e1',
                     reason='供应商错发', ref_id='RED-1', quantity=10)
    rows = _rows(app_ds)
    assert rows['e1']['status'] == 'reversed'
    reds = [r for r in rows.values() if r['quantity_sign'] == 'red']
    assert len(reds) == 1
    # 整单冲销后 reverse_edge 级联反转红字子边，红字痕迹保留但不再计入
    assert reds[0]['status'] == 'reversed'


def test_reverse_document_edges_only_touches_given_source(app_ds):
    _edge(app_ds, 'e1', source_id='L1', qty=5)
    _edge(app_ds, 'e2', source_id='L1', qty=7)
    _edge(app_ds, 'e3', source_id='L2', qty=9)

    count = reverse_document_edges(app_ds, app_ds, 'receipt', 'L1',
                                   ref_id='RED-2', reason='供应商错发')

    assert count == 2
    rows = _rows(app_ds)
    assert rows['e1']['status'] == 'reversed'
    assert rows['e2']['status'] == 'reversed'
    assert rows['e3']['status'] == 'active'


def test_reverse_document_edges_is_idempotent(app_ds):
    _edge(app_ds, 'e1', source_id='L1', qty=5)
    reverse_document_edges(app_ds, app_ds, 'receipt', 'L1',
                           ref_id='RED-3', reason='错发')
    before = len(_rows(app_ds))
    reverse_document_edges(app_ds, app_ds, 'receipt', 'L1',
                           ref_id='RED-3', reason='错发')
    assert len(_rows(app_ds)) == before


def test_source_level_reversal_rejects_non_red_reverse_mode(app_ds):
    with pytest.raises(ValueError):
        reverse_document_edges(app_ds, app_ds, 'shipment', 'L1',
                               ref_id='R-1', reason='客户退货')
