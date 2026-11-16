# -*- coding: utf-8 -*-
"""S8-1 声明式数据源 / 指标 / 动作副作用契约测试

覆盖 docs/specs/plan-integration-p1p2-2026-11-16.md §6.8 S8-1：
- 三个集成对象在 `list.data_source` 声明数据源，ui-meta 原样下发（含 items/total 点路径）；
- 未声明的对象下发 null（纯加性，旧对象行为不变）；
- `list.stats` / `actions[].http` 声明可被解析并下发；
- 非法声明在加载期 fail-fast（url 前缀 / method / 占位符 / position / dialog / 点路径）；
- 声明式资源页不注入默认动作（create/export/batch_delete）；
- 投递重试的 enabled_when 与运行时 RETRYABLE_STATUSES 一致（防漂移）。
"""

import os

import pytest
import yaml

pytestmark = pytest.mark.integration

from meta.api.integration_module_api import RETRYABLE_STATUSES
from meta.core.yaml_loader import parse_ui_list_view_config

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_SCHEMA_DIR = os.path.join(_TESTS_DIR, '..', '..', 'schemas')

# 对象 → (YAML 文件名, 预期数据源 url)
_INTEGRATION_RESOURCES = {
    'integration_connection': ('integration_connection.yaml',
                               '/api/v2/integrations/connections'),
    'notification_delivery': ('notification_delivery.yaml',
                              '/api/v2/integrations/deliveries'),
    'import_staging_rows': ('import_staging_rows.yaml',
                            '/api/v2/integrations/imports'),
}


def _raw_list(object_type):
    filename = _INTEGRATION_RESOURCES[object_type][0]
    with open(os.path.join(_SCHEMA_DIR, filename), encoding='utf-8') as handle:
        return yaml.safe_load(handle)['ui_view_config']['list']


def _ui_meta(client, object_type):
    resp = client.get(f'/api/v1/meta/{object_type}/ui-meta')
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body.get('success') is True
    return body['data']


@pytest.fixture(scope='module')
def api_client():
    from meta.tests.conftest import get_shared_app

    return get_shared_app()[1]


# ── 声明本身（YAML 单一事实）─────────────────────────────────────────

@pytest.mark.parametrize('object_type', sorted(_INTEGRATION_RESOURCES))
def test_yaml_declares_data_source(object_type):
    data_source = _raw_list(object_type)['data_source']
    assert data_source['url'] == _INTEGRATION_RESOURCES[object_type][1]
    assert data_source['items_path'] == 'data.items'
    assert data_source['total_path'] == 'data.total'
    assert data_source['params_map']['page_size'] == 'pageSize'


def test_delivery_stats_declared():
    stats = _raw_list('notification_delivery')['stats']
    assert stats['url'] == '/api/v2/integrations/deliveries/stats'
    assert stats['items_from'] == 'by_status'


def test_retry_enabled_when_matches_runtime():
    """YAML 的重试守卫不得与运行时 RETRYABLE_STATUSES 漂移。"""
    retry = next(a for a in _raw_list('notification_delivery')['actions']
                 if a['id'] == 'retry')
    assert retry['enabled_when']['field'] == 'status'
    assert list(retry['enabled_when']['in']) == list(RETRYABLE_STATUSES)


# ── ui-meta 下发（声明 → 前端契约）────────────────────────────────────

@pytest.mark.parametrize('object_type', sorted(_INTEGRATION_RESOURCES))
def test_ui_meta_returns_data_source(api_client, object_type):
    payload = _ui_meta(api_client, object_type)['list']['data_source']
    assert payload == {
        'url': _INTEGRATION_RESOURCES[object_type][1],
        'method': 'get',
        'items_path': 'data.items',
        'total_path': 'data.total',
        'params_map': payload['params_map'],
    }
    assert payload['params_map']['page_size'] == 'pageSize'


def test_ui_meta_returns_stats(api_client):
    stats = _ui_meta(api_client, 'notification_delivery')['list']['stats']
    assert stats['url'] == '/api/v2/integrations/deliveries/stats'
    assert stats['items_from'] == 'by_status'


def test_ui_meta_returns_action_http(api_client):
    actions = _ui_meta(api_client, 'integration_connection')['list']['actions']
    by_id = {action['id']: action for action in actions}

    delete = by_id['delete']
    assert delete['position'] == 'row'
    assert delete['http'] == {
        'method': 'delete',
        'url': '/api/v2/integrations/connections/{row.code}',
    }
    assert delete['refresh'] is True
    assert delete['confirm'].startswith('删除连接')

    create = by_id['create']
    assert create['dialog'] == 'form'
    assert create['http']['method'] == 'post'


def test_ui_meta_action_list_is_declaration_only(api_client):
    """声明式资源页不得被注入默认动作（create/export/batch_delete）。"""
    actions = _ui_meta(api_client, 'notification_delivery')['list']['actions']
    assert [action['id'] for action in actions] == ['retry']


def test_non_resource_object_returns_null(api_client):
    """未声明 data_source 的对象保持旧行为：下发 null。"""
    payload = _ui_meta(api_client, 'enum_type')['list']
    assert payload['data_source'] is None
    assert payload['stats'] is None


# ── 加载期校验（fail-fast，不静默降级）───────────────────────────────

def _parse(list_data):
    return parse_ui_list_view_config({'data_source': {'url': '/api/v2/x'},
                                      **list_data})


def test_parse_normalizes_declarations():
    config = _parse({
        'data_source': {'url': '/api/v2/x', 'method': 'GET',
                        'params_map': {'page_size': 'pageSize'}},
        'actions': [{'id': 'run'},
                    {'id': 'rm', 'position': 'row', 'dialog': 'form',
                     'http': {'method': 'DELETE', 'url': '/api/v2/x/{id}'},
                     'refresh': 1}],
    })
    assert config.data_source['method'] == 'get'
    assert config.actions[0] == {'id': 'run', 'position': 'toolbar', 'dialog': 'none'}
    assert config.actions[1]['http']['method'] == 'delete'
    assert config.actions[1]['refresh'] is True


@pytest.mark.parametrize('list_data, fragment', [
    ({'data_source': {'url': '/v2/x'}}, 'url 必须以 /api/ 开头'),
    ({'data_source': {'url': '/api/v2/x', 'method': 'patch'}}, 'method'),
    ({'data_source': {'url': '/api/v2/x', 'items_path': 'data..items'}}, '点路径'),
    ({'data_source': {'url': '/api/v2/x', 'params_map': ['page']}}, 'params_map'),
    ({'actions': [{'id': 'x', 'position': 'menu'}]}, 'position'),
    ({'actions': [{'id': 'x', 'dialog': 'wizard'}]}, 'dialog'),
    ({'actions': [{'position': 'row'}]}, '缺少 id'),
    ({'actions': [{'id': 'x', 'http': {'url': '/api/v2/x/{row.code!}'}}]},
     '占位符'),
    ({'actions': [{'id': 'x', 'http': {'url': '/api/v2/x/{foo}'}}]}, '占位符'),
    ({'actions': [{'id': 'x', 'http': {'method': 'get', 'url': '/api/v2/x'},
                   'enabled_when': {'field': 'status'}}]}, 'enabled_when.in'),
])
def test_invalid_declarations_fail_fast(list_data, fragment):
    with pytest.raises(ValueError) as excinfo:
        _parse(list_data)
    assert fragment in str(excinfo.value)


def test_no_data_source_keeps_legacy_actions():
    """未声明 data_source 时 actions 原样透传（不被新校验改写）。"""
    legacy = [{'id': 'create', 'label': '新建', 'position': 'batch'}]
    config = parse_ui_list_view_config({'actions': legacy})
    assert config.actions == legacy
    assert config.data_source == {}
    assert config.stats == {}


def test_resource_page_skips_default_actions():
    """声明式资源页的动作完全由 YAML 拥有，不注入 create / batch_delete。"""
    from types import SimpleNamespace

    from meta.core.models_ui_config import UIListViewConfig
    from meta.services.view_config_service import view_config_service

    config = UIListViewConfig(
        actions=[{'id': 'retry'}],
        data_source={'url': '/api/v2/integrations/deliveries'},
    )
    view_config_service._merge_default_actions(
        config, SimpleNamespace(persistent=True))
    assert config.actions == [{'id': 'retry'}]
    assert config.batch_actions == []
