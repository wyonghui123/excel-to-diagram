# -*- coding: utf-8 -*-
"""M1 audit_log 收敛契约测试

覆盖 docs/specs/spec-meta-driven-ui-2026-11-16.md §4.8：
- `audit_log.yaml` 声明 v1 端点 `/api/v1/audit/logs`（items_path=data / total_path=total）；
- ui-meta 原样下发 data_source / actions / columns；
- 死列 log_category / log_level 不再出现在列表声明中；
- 默认视图生效（effective_view=default）。
"""

import os

import pytest
import yaml

pytestmark = pytest.mark.integration

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_SCHEMA_DIR = os.path.join(_TESTS_DIR, '..', '..', 'schemas')
_SCHEMA_FILE = os.path.join(_SCHEMA_DIR, 'audit_log.yaml')

_EXPECTED_COLUMNS = [
    'id', 'created_at', 'user_name', 'action', 'object_type', 'object_id',
    'field_name', 'old_value', 'new_value', 'ip_address', 'trace_id',
]


def _raw_ui_view_config():
    with open(_SCHEMA_FILE, encoding='utf-8') as handle:
        return yaml.safe_load(handle)['ui_view_config']


def _ui_meta(client, object_type='audit_log'):
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

def test_yaml_declares_v1_data_source():
    config = _raw_ui_view_config()
    assert config['version'] == 2
    data_source = config['list']['data_source']
    assert data_source['url'] == '/api/v1/audit/logs'
    assert data_source['method'] == 'get'
    assert data_source['items_path'] == 'data'
    assert data_source['total_path'] == 'total'
    assert data_source['params_map']['start_date'] == 'created_at_start'
    assert data_source['params_map']['end_date'] == 'created_at_end'


def test_yaml_columns_drop_dead_fields():
    fields = [column['field'] for column in _raw_ui_view_config()['list']['columns']]
    assert fields == _EXPECTED_COLUMNS
    assert 'log_category' not in fields
    assert 'log_level' not in fields


def test_yaml_actions_include_export_toolbar():
    actions = {action['id']: action for action in _raw_ui_view_config()['list']['actions']}
    # audit_log 非 persistent → 行级动作 fail-closed，只声明工具栏导出（§4.8 A10）
    assert set(actions) == {'export'}
    assert actions['export']['position'] == 'toolbar'


# ── ui-meta 下发 ─────────────────────────────────────────────────

def test_ui_meta_returns_data_source(api_client):
    payload = _ui_meta(api_client)['list']['data_source']
    assert payload['url'] == '/api/v1/audit/logs'
    assert payload['items_path'] == 'data'
    assert payload['total_path'] == 'total'
    assert payload['params_map']['page_size'] == 'pageSize'


def test_ui_meta_returns_columns_without_dead_fields(api_client):
    columns = _ui_meta(api_client)['list']['columns']
    fields = [column['field'] for column in columns]
    assert fields == _EXPECTED_COLUMNS


def test_ui_meta_returns_actions(api_client):
    actions = _ui_meta(api_client)['list']['actions']
    assert [action['id'] for action in actions] == ['export']


def test_ui_meta_default_view(api_client):
    meta = _ui_meta(api_client)['meta']
    assert meta['effective_view'] == 'default'
    assert isinstance(meta['warnings'], list)
