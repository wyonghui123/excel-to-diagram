# -*- coding: utf-8 -*-
"""P8 库存库龄（入库日期投影）测试 T1-T18。

依据: docs/specs/p8-inventory-aging-model/spec.md §5 / §7 / §8
"""

import io
import os
import sqlite3
from contextlib import redirect_stdout

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.migrations import v201__inventory_foundation as v201
from meta.migrations import v224__inventory_balance_received_date as v224
from meta.migrations.v205__inventory_segment_reservation import (
    apply_segment_schema,
)
from meta.migrations.v218__reservation_closed_status import (
    apply_closed_status,
)
from meta.services.inventory_aging_service import (
    ERROR_DATE_INVALID, ERROR_ORG_REQUIRED, InventoryAgingService,
)
from meta.services.inventory_guard_service import InventoryError
from meta.tests import inventory_test_doubles as inv

import meta.api.inventory_aging_api as aging_api
import meta.services.auth_middleware as auth_mw


def _entry(**extra):
    entry = {
        'transaction_type': 'RCV_PO',
        'transaction_date': '2026-11-01',
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
        'transaction_date': '2026-11-01',
    }
    source.update(extra)
    return source


def _rows(conn, sql, params=None):
    return inv.MemDS(conn).query(sql, params or [])


def _balance(conn, item_id=None):
    sql = ('SELECT qty_on_hand, first_received_date FROM inventory_balances '
           'WHERE org_id = ? AND item_id = ? AND location_id = ?')
    rows = _rows(conn, sql, [inv.ORG_ID,
                             item_id or inv.ITEM_ID, inv.LOCATION_ID])
    return rows[0] if rows else None


def _aging(conn):
    return InventoryAgingService(inv.MemDS(conn))


def _file_db(tmp_path):
    """建立缺 first_received_date 的文件库（v201 + v205 + v218）。"""
    path = str(tmp_path / 'aging.db')
    conn = sqlite3.connect(path)
    conn.executescript(inv.SCHEMA)
    for _table, ddl in v201.TABLES:
        conn.execute(ddl)
    for _name, _table, ddl in v201.INDEXES:
        conn.execute(ddl)
    with redirect_stdout(io.StringIO()):
        apply_segment_schema(conn)
        apply_closed_status(conn)
    conn.commit()
    conn.close()
    return path


# ---------------- 迁移 ----------------

def test_t1_migration_adds_nullable_column_and_is_idempotent(tmp_path):
    path = _file_db(tmp_path)

    assert v224.migrate(path) is True
    info = _rows(sqlite3.connect(path), 'PRAGMA table_info(inventory_balances)')
    column = [row for row in info if row['name'] == 'first_received_date']
    assert column and int(column[0]['notnull']) == 0

    # 重复执行不报错，列仍只有一列
    assert v224.migrate(path) is True
    check = v224.verify(path)
    assert check['ok'] is True and check['checks']['nullable'] is True


def test_t18_migration_rejects_old_sqlite(monkeypatch, tmp_path):
    path = _file_db(tmp_path)
    monkeypatch.setattr(v224.sqlite3, 'sqlite_version_info', (3, 32, 0))
    with pytest.raises(RuntimeError) as exc:
        v224.migrate(path)
    assert '3.33' in str(exc.value)


# ---------------- 写入路径（T2-T9） ----------------

def test_t2_receipt_sets_first_received_date():
    conn = inv.seed()
    svc = inv.posting_service(conn)

    svc.post([_entry()], _source())

    balance = _balance(conn)
    assert balance['qty_on_hand'] == 10.0
    assert balance['first_received_date'] == '2026-11-01'


def test_t3_later_receipt_does_not_move_date_forward():
    conn = inv.seed()
    svc = inv.posting_service(conn)
    svc.post([_entry()], _source())
    svc.post([_entry(transaction_date='2026-11-05', qty=5.0,
                     source_line_id=2)],
             _source(source_event_key='receipt:1:post:2',
                     transaction_date='2026-11-05'))

    balance = _balance(conn)
    assert balance['qty_on_hand'] == 15.0
    assert balance['first_received_date'] == '2026-11-01'


def test_t4_backdated_receipt_moves_date_earlier():
    conn = inv.seed()
    svc = inv.posting_service(conn)
    svc.post([_entry()], _source())
    svc.post([_entry(transaction_date='2026-10-20', qty=2.0,
                     source_line_id=2)],
             _source(source_event_key='receipt:1:post:2',
                     transaction_date='2026-10-20'))

    balance = _balance(conn)
    assert balance['qty_on_hand'] == 12.0
    assert balance['first_received_date'] == '2026-10-20'


def test_t5_outbound_does_not_change_date():
    conn = inv.seed()
    svc = inv.posting_service(conn)
    svc.post([_entry()], _source())
    svc.post([_entry(transaction_type='ISSUE_TO_SHIP', direction='out',
                     transaction_date='2026-11-03', qty=3.0,
                     source_line_id=2)],
             _source(source_event_key='issue:1:post',
                     transaction_date='2026-11-03'))

    balance = _balance(conn)
    assert balance['qty_on_hand'] == 7.0
    assert balance['first_received_date'] == '2026-11-01'


def test_t6_zeroed_balance_clears_date():
    conn = inv.seed()
    svc = inv.posting_service(conn)
    svc.post([_entry(qty=4.0)], _source())
    svc.post([_entry(transaction_type='ISSUE_TO_SHIP', direction='out',
                     qty=4.0, source_line_id=2)],
             _source(source_event_key='issue:1:post'))

    balance = _balance(conn)
    assert balance['qty_on_hand'] == 0.0
    assert balance['first_received_date'] is None


def test_t7_receipt_after_zero_restarts_date():
    conn = inv.seed()
    svc = inv.posting_service(conn)
    svc.post([_entry(qty=4.0)], _source())
    svc.post([_entry(transaction_type='ISSUE_TO_SHIP', direction='out',
                     qty=4.0, source_line_id=2)],
             _source(source_event_key='issue:1:post'))
    svc.post([_entry(transaction_date='2026-11-09', qty=4.0,
                     source_line_id=3)],
             _source(source_event_key='receipt:1:post:3',
                     transaction_date='2026-11-09'))

    balance = _balance(conn)
    assert balance['qty_on_hand'] == 4.0
    assert balance['first_received_date'] == '2026-11-09'


def test_t8_full_reversal_clears_date():
    conn = inv.seed()
    svc = inv.posting_service(conn)
    svc.post([_entry()], _source())
    original = _rows(conn, 'SELECT * FROM inventory_transactions')[0]

    svc.reverse([original['id']], _source(
        source_event_key='receipt:1:reverse'))

    balance = _balance(conn)
    assert balance['qty_on_hand'] == 0.0
    assert balance['first_received_date'] is None


def test_t9_reversal_of_outbound_does_not_form_new_layer():
    conn = inv.seed()
    svc = inv.posting_service(conn)
    svc.post([_entry()], _source())
    svc.post([_entry(transaction_type='ISSUE_TO_SHIP', direction='out',
                     transaction_date='2026-11-03', qty=5.0,
                     source_line_id=2)],
             _source(source_event_key='issue:1:post',
                     transaction_date='2026-11-03'))
    issue = _rows(
        conn, "SELECT * FROM inventory_transactions WHERE direction = 'out'")[0]

    svc.reverse([issue['id']], _source(
        source_event_key='issue:1:reverse', transaction_date='2026-11-04'))

    balance = _balance(conn)
    assert balance['qty_on_hand'] == 10.0
    assert balance['first_received_date'] == '2026-11-01'


# ---------------- 重建（T10） ----------------

def test_t10_rebuild_keeps_same_date():
    conn = inv.seed()
    svc = inv.posting_service(conn)
    svc.post([_entry()], _source())
    svc.post([_entry(transaction_date='2026-11-05', qty=5.0,
                     source_line_id=2)],
             _source(source_event_key='receipt:1:post:2',
                     transaction_date='2026-11-05'))
    svc.post([_entry(transaction_type='ISSUE_TO_SHIP', direction='out',
                     transaction_date='2026-11-06', qty=3.0,
                     source_line_id=3)],
             _source(source_event_key='issue:1:post',
                     transaction_date='2026-11-06'))
    before = _balance(conn)

    svc.rebuild_balances(inv.ORG_ID)

    after = _balance(conn)
    assert after['qty_on_hand'] == before['qty_on_hand'] == 12.0
    assert after['first_received_date'] == '2026-11-01'


# ---------------- 读模型（T11-T17） ----------------

def _insert_balance(conn, item_id, qty, received, location_id=None,
                    org_id=None):
    conn.execute(
        'INSERT INTO inventory_balances (org_id, location_id, item_id, '
        'batch_id, stock_status, stock_segment_type, project_id, '
        'project_task_id, sales_order_line_id, owner_party_id, qty_on_hand, '
        'qty_reserved, first_received_date) '
        'VALUES (?, ?, ?, 0, ?, ?, 0, 0, 0, 0, ?, 0, ?)',
        [org_id or inv.ORG_ID, location_id or inv.LOCATION_ID, item_id,
         'unrestricted', 'owned', qty, received])


def test_t11_bucket_boundaries_are_closed_intervals():
    conn = inv.seed()
    for index, days in enumerate((30, 31, 60, 61, 90, 91, 180, 181)):
        _insert_balance(
            conn, inv.ITEM_ID + index, 1.0,
            '2026-11-06' if days == 0 else None)
    # 用 as_of 反推日期，保证边界值稳定
    for index, days in enumerate((30, 31, 60, 61, 90, 91, 180, 181)):
        conn.execute(
            'UPDATE inventory_balances SET first_received_date = '
            "date('2026-11-06', ?) WHERE item_id = ?",
            ['-%d days' % days, inv.ITEM_ID + index])
    conn.commit()

    report = _aging(conn).report(org_id=inv.ORG_ID, as_of='2026-11-06')

    buckets = {row['item_id']: row['age_bucket'] for row in report['rows']}
    assert buckets[inv.ITEM_ID] == '0-30'          # 30 天属 0-30
    assert buckets[inv.ITEM_ID + 1] == '31-60'     # 31
    assert buckets[inv.ITEM_ID + 2] == '31-60'     # 60
    assert buckets[inv.ITEM_ID + 3] == '61-90'     # 61
    assert buckets[inv.ITEM_ID + 4] == '61-90'     # 90
    assert buckets[inv.ITEM_ID + 5] == '91-180'    # 91
    assert buckets[inv.ITEM_ID + 6] == '91-180'    # 180
    assert buckets[inv.ITEM_ID + 7] == '>180'      # 181


def test_t12_negative_qty_goes_unassigned_and_sums_stay_equal():
    conn = inv.seed()
    _insert_balance(conn, inv.ITEM_ID, -2.0, None)
    conn.commit()

    report = _aging(conn).report(org_id=inv.ORG_ID, as_of='2026-11-06')

    row = report['rows'][0]
    assert row['age_bucket'] == 'UNASSIGNED'
    assert report['unassigned_qty'] == -2.0
    assert report['total_qty'] == -2.0
    summary = {s['bucket']: s['qty'] for s in report['summary']}
    assert summary['UNASSIGNED'] == -2.0
    assert sum(s['qty'] for s in report['summary']) == -2.0


def test_t13_detail_replays_layers_and_reconciles():
    conn = inv.seed()
    svc = inv.posting_service(conn)
    svc.post([_entry(qty=10.0)], _source())
    svc.post([_entry(transaction_type='ISSUE_TO_SHIP', direction='out',
                     transaction_date='2026-11-03', qty=4.0,
                     source_line_id=2)],
             _source(source_event_key='issue:1:post',
                     transaction_date='2026-11-03'))
    svc.post([_entry(transaction_date='2026-11-05', qty=6.0,
                     source_line_id=3)],
             _source(source_event_key='receipt:1:post:3',
                     transaction_date='2026-11-05'))

    detail = _aging(conn).detail(
        org_id=inv.ORG_ID, location_id=inv.LOCATION_ID,
        item_id=inv.ITEM_ID, as_of='2026-11-06')

    assert detail['qty_on_hand'] == 12.0
    assert detail['layers_total'] == 12.0
    assert detail['reconciled'] is True
    assert [layer['receipt_date'] for layer in detail['layers']] == [
        '2026-11-01', '2026-11-05']
    assert [layer['remaining_qty'] for layer in detail['layers']] == [6.0, 6.0]


def test_t14_transaction_date_is_truncated_to_day():
    conn = inv.seed()
    svc = inv.posting_service(conn)

    svc.post([_entry(transaction_date='2026-11-01 14:30:00')],
             _source(transaction_date='2026-11-01 14:30:00'))

    balance = _balance(conn)
    assert balance['first_received_date'] == '2026-11-01'


def test_t15_opening_balance_stays_null_and_reports_unassigned():
    conn = inv.seed()
    _insert_balance(conn, inv.ITEM_ID, 5.0, None)
    conn.commit()

    report = _aging(conn).report(org_id=inv.ORG_ID, as_of='2026-11-06')
    assert report['rows'][0]['first_received_date'] is None
    assert report['rows'][0]['age_bucket'] == 'UNASSIGNED'
    assert report['unassigned_qty'] == 5.0
    assert v224._pending_count(conn) == 1


def test_t16_backfill_never_clears_existing_date(tmp_path):
    conn = inv.seed()
    _insert_balance(conn, inv.ITEM_ID, 5.0, '2026-08-01')
    conn.execute(
        "INSERT INTO inventory_transactions (transaction_no, "
        "transaction_type_id, transaction_date, org_id, location_id, item_id, "
        "uom_id, qty, base_qty, direction, batch_id, stock_status, "
        "stock_segment_type, project_id, project_task_id, sales_order_line_id, "
        "owner_party_id, source_doc_type, source_doc_id, source_line_id, "
        "source_event_key, reversal_of_transaction_id) "
        "VALUES ('INV-X1', 1, '2026-11-01', 1, 7, 900, 3, 10, 10, 'in', 0, "
        "'unrestricted', 'owned', 0, 0, 0, 0, 'receipt', 1, 1, 'x:1', NULL)")
    conn.execute(
        "INSERT INTO inventory_transactions (transaction_no, "
        "transaction_type_id, transaction_date, org_id, location_id, item_id, "
        "uom_id, qty, base_qty, direction, batch_id, stock_status, "
        "stock_segment_type, project_id, project_task_id, sales_order_line_id, "
        "owner_party_id, source_doc_type, source_doc_id, source_line_id, "
        "source_event_key, reversal_of_transaction_id) "
        "VALUES ('INV-X2', 1, '2026-11-02', 1, 7, 900, 3, 10, 10, 'out', 0, "
        "'unrestricted', 'owned', 0, 0, 0, 0, 'receipt', 1, 2, 'x:2', 1)")
    conn.commit()

    v224._backfill(conn)

    balance = _balance(conn)
    assert balance['qty_on_hand'] == 5.0
    assert balance['first_received_date'] == '2026-08-01'


def test_t17_group_by_item_buckets_rows_before_summing():
    conn = inv.seed()
    _insert_balance(conn, inv.ITEM_ID, 3.0, '2026-10-30',
                    location_id=inv.LOCATION_ID)
    _insert_balance(conn, inv.ITEM_ID, 3.0, '2026-05-01',
                    location_id=inv.OTHER_LOCATION_ID)
    conn.commit()

    report = _aging(conn).report(org_id=inv.ORG_ID, group_by='item',
                                 as_of='2026-11-06')

    summary = {s['bucket']: s['qty'] for s in report['summary']}
    assert summary['0-30'] == 3.0
    assert summary['>180'] == 3.0
    row = report['rows'][0]
    assert row['qty_on_hand'] == 6.0
    assert row['first_received_date'] == '2026-05-01'
    assert row['days_in_stock'] == 189


def test_backfill_script_is_idempotent(tmp_path):
    conn = inv.seed()
    _insert_balance(conn, inv.ITEM_ID, 5.0, None)
    conn.commit()
    path = str(tmp_path / 'script.db')
    target = sqlite3.connect(path)
    conn.backup(target)
    target.close()

    import importlib.util
    from pathlib import Path
    script = (Path(__file__).resolve().parents[2] / 'scripts'
              / 'backfill_first_received_date.py')
    spec = importlib.util.spec_from_file_location('bf_received', str(script))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.backfill(path, inv.ORG_ID, '2026-11-01') == 1
    assert module.backfill(path, inv.ORG_ID, '2026-11-01') == 0

    conn2 = sqlite3.connect(path)
    try:
        report = InventoryAgingService(inv.MemDS(conn2)).report(
            org_id=inv.ORG_ID, as_of='2026-11-06')
        assert report['unassigned_qty'] == 0
        assert report['rows'][0]['age_bucket'] == '0-30'
    finally:
        conn2.close()


def test_report_validation_error_codes():
    conn = inv.seed()
    aging = _aging(conn)

    with pytest.raises(InventoryError) as exc:
        aging.report(as_of='2026-11-06')
    assert exc.value.code == ERROR_ORG_REQUIRED

    with pytest.raises(InventoryError) as exc:
        aging.report(org_id=inv.ORG_ID, as_of='not-a-date')
    assert exc.value.code == ERROR_DATE_INVALID


# ---------------- 只读 API（薄路由） ----------------

AUTH = {'Authorization': 'Bearer test-token',
        'Content-Type': 'application/json'}


class _FakeBlacklist:
    @staticmethod
    def is_blacklisted(token):
        return False


class _FakeTokenService:
    @staticmethod
    def verify_token(token):
        return {'user_id': '1', 'username': 'admin', 'token_version': 0,
                'permissions': ['*']}


def _api_client(monkeypatch, conn):
    from flask import Flask
    aging_api.init_service(inv.MemDS(conn))
    monkeypatch.setattr(auth_mw, 'token_blacklist_service', _FakeBlacklist())
    monkeypatch.setattr(auth_mw, 'TokenService', _FakeTokenService)
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(aging_api.inventory_aging_bp)
    return app.test_client()


def _api_conn():
    conn = inv.seed()
    svc = inv.posting_service(conn)
    svc.post([_entry(qty=10.0)], _source())
    svc.post([_entry(transaction_type='ISSUE_TO_SHIP', direction='out',
                     transaction_date='2026-11-03', qty=4.0,
                     source_line_id=2)],
             _source(source_event_key='issue:1:post',
                     transaction_date='2026-11-03'))
    return conn


def test_api_report_returns_summary_and_rows(monkeypatch):
    conn = _api_conn()
    client = _api_client(monkeypatch, conn)
    try:
        resp = client.get(
            '/api/v1/inventory-aging/report?org_id=1&as_of=2026-11-06',
            headers=AUTH)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['success'] is True
        data = body['data']
        assert data['as_of'] == '2026-11-06'
        assert data['rows'][0]['age_bucket'] == '0-30'
        assert data['rows'][0]['qty_on_hand'] == 6.0
        assert sum(item['qty'] for item in data['summary']) == 6.0
    finally:
        conn.close()
        aging_api._service = None


def test_api_report_requires_org(monkeypatch):
    conn = inv.seed()
    client = _api_client(monkeypatch, conn)
    try:
        resp = client.get('/api/v1/inventory-aging/report', headers=AUTH)
        assert resp.status_code == 400
        body = resp.get_json()
        assert body['success'] is False
        assert body['code'] == ERROR_ORG_REQUIRED
    finally:
        conn.close()
        aging_api._service = None


def test_api_report_rejects_bad_date_and_edges(monkeypatch):
    conn = inv.seed()
    client = _api_client(monkeypatch, conn)
    try:
        bad_date = client.get(
            '/api/v1/inventory-aging/report?org_id=1&as_of=2026-13-99',
            headers=AUTH)
        assert bad_date.status_code == 400
        assert bad_date.get_json()['code'] == ERROR_DATE_INVALID

        bad_edges = client.get(
            '/api/v1/inventory-aging/report?org_id=1&bucket_edges=30,x',
            headers=AUTH)
        assert bad_edges.status_code == 400
        assert bad_edges.get_json()['code'] == ERROR_DATE_INVALID

        bad_int = client.get(
            '/api/v1/inventory-aging/report?org_id=abc', headers=AUTH)
        assert bad_int.status_code == 400
        assert bad_int.get_json()['code'] == 'INV_AGING_PARAM_INVALID'
    finally:
        conn.close()
        aging_api._service = None


def test_api_detail_reconciles(monkeypatch):
    conn = _api_conn()
    client = _api_client(monkeypatch, conn)
    try:
        resp = client.get(
            '/api/v1/inventory-aging/detail?org_id=1&location_id=7'
            '&item_id=900&as_of=2026-11-06', headers=AUTH)
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['reconciled'] is True
        assert data['qty_on_hand'] == 6.0
        assert data['layers_total'] == 6.0
        assert data['layers'][0]['receipt_date'] == '2026-11-01'
    finally:
        conn.close()
        aging_api._service = None


def test_api_requires_authentication(monkeypatch):
    conn = inv.seed()
    client = _api_client(monkeypatch, conn)
    try:
        resp = client.get('/api/v1/inventory-aging/report?org_id=1')
        assert resp.status_code == 401
    finally:
        conn.close()
        aging_api._service = None
