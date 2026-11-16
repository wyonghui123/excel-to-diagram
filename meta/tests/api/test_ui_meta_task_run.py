# -*- coding: utf-8 -*-
"""M2 task_run 收敛契约测试

覆盖 docs/specs/spec-meta-driven-ui-2026-11-16.md §4.9：
- `task_run.yaml` 声明 `/api/v2/jobs/runs`（items_path=items / total_path=total）；
- ui-meta 原样下发 data_source（含 params_map）与 actions（cancel → retry）；
- 动作 enabled_when 与后端 capabilities 同源。
"""

import os

import pytest
import yaml

pytestmark = pytest.mark.integration

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_SCHEMA_FILE = os.path.join(_TESTS_DIR, '..', '..', 'schemas', 'task_run.yaml')

_CANCEL_STATUSES = ['pending', 'claimed', 'running']
_RETRY_STATUSES = ['failed', 'dead', 'cancelled']


def _raw_ui_view_config():
    with open(_SCHEMA_FILE, encoding='utf-8') as handle:
        return yaml.safe_load(handle)['ui_view_config']


def _ui_meta(client, object_type='task_run'):
    resp = client.get(f'/api/v1/meta/{object_type}/ui-meta')
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body.get('success') is True
    return body['data']


@pytest.fixture(scope='module')
def api_client():
    from meta.tests.conftest import get_shared_app

    return get_shared_app()[1]


# ── YAML 声明本身 ────────────────────────────────────────────────

def test_yaml_declares_v2_runs_data_source():
    data_source = _raw_ui_view_config()['list']['data_source']
    assert data_source['url'] == '/api/v2/jobs/runs'
    assert data_source['method'] == 'get'
    assert data_source['items_path'] == 'items'
    assert data_source['total_path'] == 'total'
    for key in ('page', 'page_size', 'job_code', 'status', 'source', 'from', 'to'):
        assert key in data_source['params_map']


def test_yaml_actions_cancel_then_retry():
    actions = _raw_ui_view_config()['list']['actions']
    assert [action['id'] for action in actions] == ['cancel', 'retry']
    cancel, retry = actions
    assert cancel['http']['url'] == '/api/v2/jobs/runs/{row.id}/cancel'
    assert retry['http']['url'] == '/api/v2/jobs/runs/{row.id}/retry'
    assert cancel['enabled_when']['in'] == _CANCEL_STATUSES
    assert retry['enabled_when']['in'] == _RETRY_STATUSES


# ── ui-meta 下发 ─────────────────────────────────────────────────

def test_ui_meta_returns_data_source(api_client):
    payload = _ui_meta(api_client)['list']['data_source']
    assert payload['url'] == '/api/v2/jobs/runs'
    assert payload['items_path'] == 'items'
    assert payload['total_path'] == 'total'
    assert payload['params_map']['job_code'] == 'job_code'


def test_ui_meta_returns_actions(api_client):
    actions = _ui_meta(api_client)['list']['actions']
    assert [action['id'] for action in actions] == ['cancel', 'retry']
    assert all(action['position'] == 'row' for action in actions)
    assert actions[0]['enabled_when']['in'] == _CANCEL_STATUSES
    assert actions[1]['enabled_when']['in'] == _RETRY_STATUSES
    assert actions[0]['success_message'] == '已提交取消'


def test_ui_meta_columns_unchanged(api_client):
    fields = [column['field'] for column in _ui_meta(api_client)['list']['columns']]
    assert fields == [
        'status', 'job_id', 'attempt', 'worker_id',
        'duration_ms', 'error', 'created_at',
    ]
