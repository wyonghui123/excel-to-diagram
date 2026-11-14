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
    v246._do_triggers(c)
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
    from meta.api import job_admin_api
    job_admin_api.set_job_registry(None)
    job_admin_api.set_job_dispatcher(None)


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


# ── 作业列表 / 详情 / 更新（IF-002 / IF-007）───────────────────────────

def test_list_jobs_projects_capabilities_and_overview(client):
    body = client.get('/api/v2/jobs', headers=AUTH).get_json()
    data = body['data']
    assert data['total'] == len(v246.JOB_SEEDS)
    job = next(item for item in data['items'] if item['code'] == 'db_analyze')
    assert job['available'] is True
    assert job['capabilities']['can_run'] is True
    assert job['trigger_count'] == 1


def test_job_detail_includes_triggers_and_redacts_default_params(client, conn):
    conn.execute(
        "UPDATE job_definitions SET default_params=? WHERE code='db_analyze'",
        ['{"password": "p", "account": "alice"}'])
    conn.commit()

    data = client.get('/api/v2/jobs/db_analyze', headers=AUTH).get_json()['data']
    assert [t['trigger_type'] for t in data['triggers']] == ['cron']
    assert data['default_params'] == {'password': '***', 'account': 'alice'}


def test_job_update_pauses_and_blocks_run_now(client):
    resp = client.patch('/api/v2/jobs/db_analyze', headers=AUTH,
                        json={'status': 'paused'})
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['status'] == 'paused'
    assert data['capabilities']['can_run'] is False

    resp = client.post('/api/v2/jobs/db_analyze/run-now', headers=AUTH, json={})
    assert resp.status_code == 409
    assert resp.get_json()['code'] == 'job_paused'


def test_job_update_rejects_readonly_field_and_bad_status(client):
    assert client.patch('/api/v2/jobs/db_analyze', headers=AUTH,
                        json={'handler': 'evil'}).status_code == 400
    assert client.patch('/api/v2/jobs/db_analyze', headers=AUTH,
                        json={'status': 'zombie'}).status_code == 400


def test_run_now_requires_registered_executor(client):
    from meta.api import job_admin_api
    from meta.core.job_executor_registry import ExecutorRegistry

    job_admin_api.set_job_registry(ExecutorRegistry())
    resp = client.post('/api/v2/jobs/db_analyze/run-now', headers=AUTH, json={})
    assert resp.status_code == 409
    assert resp.get_json()['code'] == 'job_unavailable'


# ── 触发器 CRUD（IF-009）───────────────────────────────────────────────

def test_trigger_create_update_delete_flow(client):
    resp = client.post('/api/v2/jobs/db_analyze/triggers', headers=AUTH,
                       json={'trigger_type': 'interval', 'interval_seconds': 600})
    assert resp.status_code == 201
    trigger = resp.get_json()['data']
    assert trigger['trigger_type'] == 'interval'
    trigger_id = trigger['trigger_id']

    resp = client.patch('/api/v2/jobs/triggers/%d' % trigger_id, headers=AUTH,
                        json={'enabled': False, 'interval_seconds': 900})
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['enabled'] is False
    assert data['interval_seconds'] == 900

    resp = client.delete('/api/v2/jobs/triggers/%d' % trigger_id, headers=AUTH)
    assert resp.status_code == 200
    assert client.patch('/api/v2/jobs/triggers/%d' % trigger_id, headers=AUTH,
                        json={'enabled': True}).status_code == 404


def test_trigger_create_validates_schedule(client):
    resp = client.post('/api/v2/jobs/db_analyze/triggers', headers=AUTH,
                       json={'trigger_type': 'cron', 'cron_expr': 'bad cron'})
    assert resp.status_code == 400
    assert resp.get_json()['code'] == 'invalid_cron_expr'

    resp = client.post('/api/v2/jobs/db_analyze/triggers', headers=AUTH,
                       json={'trigger_type': 'once', 'run_at': 1})
    assert resp.status_code == 400
    assert resp.get_json()['code'] == 'run_at_in_past'

    resp = client.post('/api/v2/jobs/db_analyze/triggers', headers=AUTH,
                       json={'trigger_type': 'interval', 'interval_seconds': 0})
    assert resp.status_code == 400
    assert resp.get_json()['code'] == 'invalid_interval'


# ── 执行记录（IF-011 / IF-012）─────────────────────────────────────────

def test_runs_list_exposes_filters_and_capabilities(client):
    client.post('/api/v2/jobs/db_analyze/run-now', headers=AUTH, json={})
    data = client.get('/api/v2/jobs/runs', headers=AUTH).get_json()['data']

    assert data['total'] == 1
    item = data['items'][0]
    assert item['source'] == 'manual'
    assert item['capabilities']['is_terminal'] is False
    assert item['capabilities']['can_cancel'] is True
    assert item['capabilities']['can_retry'] is False
    assert 'params' not in item and 'params_excerpt' in item

    filters = data['meta']['filters']
    assert 'manual' in filters['sources']
    assert 'pending' in filters['statuses']
    assert any(j['code'] == 'db_analyze' for j in filters['job_codes'])

    assert client.get('/api/v2/jobs/runs?source=bogus',
                      headers=AUTH).status_code == 400
    assert client.get('/api/v2/jobs/runs?status=bogus',
                      headers=AUTH).status_code == 400


def test_run_detail_includes_params_timeline_and_links(client):
    run_id = client.post('/api/v2/jobs/db_analyze/run-now', headers=AUTH,
                         json={}).get_json()['data']['run_id']
    data = client.get('/api/v2/jobs/runs/%d' % run_id,
                      headers=AUTH).get_json()['data']

    assert data['params'] == {}
    assert data['timeline'][0]['status'] == 'pending'
    assert data['capabilities']['can_cancel'] is True
    assert data['links']['job'].endswith('job=db_analyze')


def test_dispatcher_status_falls_back_without_instance(client):
    data = client.get('/api/v2/jobs/dispatcher/status',
                      headers=AUTH).get_json()['data']
    assert data['enabled'] is False
    assert data['running'] is False
    assert data['backlog'] == {'pending': 0, 'due_triggers': 0}


# ── 审计与脱敏（FR-020 / NFR-006）─────────────────────────────────────

def test_audit_covers_run_trigger_and_definition(client, conn, monkeypatch):
    from meta.api import job_admin_api

    calls = []
    monkeypatch.setattr(
        job_admin_api, '_write_audit',
        lambda *args, **kwargs: calls.append((args, kwargs)))

    conn.execute(
        "UPDATE job_definitions SET default_params=?, params_schema=? "
        "WHERE code='db_analyze'",
        ['{"password": "p", "account": "alice"}',
         '{"properties": {"password": {"type": "string"}, '
         '"account": {"type": "string"}}}'])
    conn.commit()

    run_id = client.post('/api/v2/jobs/db_analyze/run-now',
                         headers=AUTH, json={}).get_json()['data']['run_id']
    action, obj_type, obj_id = calls[-1][0]
    assert (action, obj_type, obj_id) == ('CREATE', 'job_run', run_id)
    assert calls[-1][1]['data']['params'] == {
        'password': '***', 'account': 'alice'}

    trigger_id = client.post(
        '/api/v2/jobs/db_analyze/triggers', headers=AUTH,
        json={'trigger_type': 'interval', 'interval_seconds': 600,
              'params_override': {'password': 'secret', 'account': 'bob'}}
    ).get_json()['data']['trigger_id']
    action, obj_type, obj_id = calls[-1][0]
    assert (action, obj_type, obj_id) == ('CREATE', 'job_trigger', trigger_id)
    assert calls[-1][1]['data']['params_override'] == {
        'password': '***', 'account': 'bob'}

    resp = client.patch('/api/v2/jobs/db_analyze', headers=AUTH,
                        json={'description': '仅用于审计测试'})
    assert resp.status_code == 200
    action, obj_type, obj_id = calls[-1][0]
    assert (action, obj_type, obj_id) == (
        'UPDATE', 'job_definition', 'db_analyze')
    assert calls[-1][1]['data']['description'] == '仅用于审计测试'
    assert calls[-1][1]['old_data']['description'] is None
    assert 'description' in calls[-1][1]['old_data']

    client.post('/api/v2/jobs/runs/%d/cancel' % run_id, headers=AUTH)
    action, obj_type, _ = calls[-1][0]
    assert (action, obj_type) == ('UPDATE', 'job_run')
    assert calls[-1][1]['old_data']['status'] == 'pending'
    assert calls[-1][1]['data']['status'] == 'cancelled'

    assert client.delete('/api/v2/jobs/triggers/%d' % trigger_id,
                         headers=AUTH).status_code == 200
    action, obj_type, obj_id = calls[-1][0]
    assert (action, obj_type, obj_id) == ('DELETE', 'job_trigger', trigger_id)
    assert calls[-1][1]['data']['job_code'] == 'db_analyze'
    assert calls[-1][1]['data']['params_override'] == {
        'password': '***', 'account': 'bob'}