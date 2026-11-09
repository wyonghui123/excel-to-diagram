# -*- coding: utf-8 -*-
"""下游取消 → 释放上游占用（release_target_edges）。"""

import contextlib

import pytest

from meta.core.doc_flow_reversal import release_target_edges


class _Cursor:
    def __init__(self, rows=None):
        self._rows = rows or []
        self.rowcount = 0

    def fetchall(self):
        return self._rows


class _ReversalResult:
    def __init__(self, replay=False):
        self.replay = replay


class FakeDS:
    def __init__(self, edge_rows=None, line_rows=None):
        self._edge_rows = edge_rows or []
        self._line_rows = line_rows or []
        self.sql = []
        self.transactions = 0

    def execute(self, sql, params=()):
        self.sql.append(('execute', sql, tuple(params)))
        return _Cursor(self._edge_rows)

    def query(self, sql, params=()):
        self.sql.append(('query', sql, tuple(params)))
        return self._line_rows

    @contextlib.contextmanager
    def transaction(self):
        self.transactions += 1
        yield


def test_release_requires_target_bo_and_ids():
    assert release_target_edges(FakeDS(), '', ['1']) == {'released': [], 'replay': []}
    assert release_target_edges(FakeDS(), 'shipment_line', []) == \
        {'released': [], 'replay': []}


def test_release_queries_active_normal_edges(monkeypatch):
    calls = []

    def fake_reverse(ds, edge_id, **kwargs):
        calls.append((edge_id, kwargs))
        return _ReversalResult(replay=False)

    monkeypatch.setattr('meta.core.doc_flow_reversal.reverse_edge', fake_reverse)
    ds = FakeDS(edge_rows=[{'id': 'e1'}, {'id': 'e2'}])
    result = release_target_edges(ds, 'shipment_line', [11, 12],
                                  reversed_by='shipment_service.cancel')
    assert result['released'] == ['e1', 'e2']
    assert result['replay'] == []
    assert [call[0] for call in calls] == ['e1', 'e2']
    sql = ds.sql[0][1]
    assert "target_bo" in sql and "status='active'" in sql \
        and "quantity_sign='normal'" in sql


def test_release_collects_replay(monkeypatch):
    monkeypatch.setattr(
        'meta.core.doc_flow_reversal.reverse_edge',
        lambda ds, edge_id, **kw: _ReversalResult(replay=True))
    ds = FakeDS(edge_rows=[{'id': 'e1'}])
    result = release_target_edges(ds, 'receipt_line', [1], reversed_by='test')
    assert result == {'released': [], 'replay': ['e1']}


def test_release_runs_in_one_transaction(monkeypatch):
    monkeypatch.setattr(
        'meta.core.doc_flow_reversal.reverse_edge',
        lambda ds, edge_id, **kw: _ReversalResult(replay=False))
    ds = FakeDS()
    release_target_edges(ds, 'receipt_line', [1], reversed_by='test')
    assert ds.transactions == 1


def test_shipment_cancel_releases_lines(monkeypatch):
    released = []
    monkeypatch.setattr(
        'meta.services.shipment_service.release_target_edges',
        lambda ds, bo, ids, **kw: released.append((bo, list(ids))))
    from meta.services.shipment_service import ShipmentService

    service = ShipmentService(data_source=FakeDS(line_rows=[{'id': 11}, {'id': 12}]))
    monkeypatch.setattr(service, '_require_header',
                        lambda _id: {'id': _id, 'status': 'draft'})
    service.cancel(7)
    assert released == [('shipment_line', [11, 12])]