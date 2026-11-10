# -*- coding: utf-8 -*-
"""后台作业管理端点（`meta/api/job_admin_api.py`）单元测试。

覆盖 spec §8.2 / §10.1 第 5 项：
  · `job_admin` 权限门禁（未认证 401）；
  · run-now：未知作业 404 / 非法 params 400 / 正常建 `manual:` run；
  · retry：未知 run 404 / `dead` → `pending`；
  · cancel：未知 run 404 / `pending` → `cancelled`。
"""

import os
import sqlite3

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.core.job_run_store import JobRunStore
from meta.migrations import v246__background_job_infrastructure as v246
from meta.tests import inventory_test_doubles as inv

AUTH = {'Authorization': 'Bearer test-token'}


@pytest.fixture()
def conn():
    c = sqlite3.connect(':memory:', isolation_level=None)
    v246._do_tables(c)
    v246._do_indexes(c)
    v246._do_job_definitions(c)
    try:
        yield c
    finally:
        c.close()


@pytest.fixture()
def store(conn):
    return JobRunStore(inv.MemDS(conn))


@pytest.fixture()
def client(store, monkeypatch):
    from flask import Flask
    from meta.api.job_admin_api import job_admin_bp, set_job_store

    monkeypatch.setattr(
        'meta.services.auth_middleware.TokenService.verify_token',
        lambda token: {'user_id': 1, 'permissions': ['*']})
    monkeypatch.setattr(
        'meta.services.auth_middleware.token_blacklist_service.is_blacklisted',
        lambda token: False)
    monkeypatch.setattr(
        'meta.services.auth_middleware.evaluate_code',
        lambda user, code: True)

    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(job_admin_bp)
    set_job_store(store)
    yield app.test_client()
    set_job_store(None)


def test_run_now_requires_auth(client):
    resp = client.post('/api/v2/jobs/db_analyze/run-now')
    assert resp.status_code == 401


def test_run_now_unknown_job_returns_404(client):
    resp = client.post('/api/v2/jobs/nope/run-now', headers=AUTH, json={})
    assert resp.status_code == 404


def test_run_now_creates_manual_run(client, conn):
    resp = client.post('/api/v2/jobs/db_analyze/run-now', headers=AUTH, json={})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert body['data']['run_key'].startswith('manual:')

    rows = inv.MemDS(conn).query('SELECT * FROM task_runs')
    assert len(rows) == 1
    assert rows[0]['status'] == 'pending'
    assert rows[0]['trigger_id'] is None


def test_run_now_rejects_non_object_params(client):
    resp = client.post('/api/v2/jobs/db_analyze/run-now', headers=AUTH,
                       json={'params': ['x']})
    assert resp.status_code == 400


def test_retry_unknown_run_returns_404(client):
    resp = client.post('/api/v2/jobs/runs/999/retry', headers=AUTH)
    assert resp.status_code == 404


def test_retry_dead_run_becomes_pending(client, store, conn):
    run_id = store.create_run('db_analyze')
    conn.execute("UPDATE task_runs SET status='dead' WHERE id=?", [run_id])

    resp = client.post('/api/v2/jobs/runs/%d/retry' % run_id, headers=AUTH)

    assert resp.status_code == 200
    assert store.get_run(run_id)['status'] == 'pending'


def test_retry_non_retryable_status_returns_409(client, store):
    run_id = store.create_run('db_analyze')
    resp = client.post('/api/v2/jobs/runs/%d/retry' % run_id, headers=AUTH)
    assert resp.status_code == 409


def test_cancel_pending_run(client, store):
    run_id = store.create_run('db_analyze')
    resp = client.post('/api/v2/jobs/runs/%d/cancel' % run_id, headers=AUTH)
    assert resp.status_code == 200
    assert store.get_run(run_id)['status'] == 'cancelled'


def test_cancel_unknown_run_returns_404(client):
    resp = client.post('/api/v2/jobs/runs/999/cancel', headers=AUTH)
    assert resp.status_code == 404