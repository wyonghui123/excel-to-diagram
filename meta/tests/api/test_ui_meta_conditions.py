# -*- coding: utf-8 -*-
"""M0：ui-meta 条件可见性 / 降级 warning / explain 契约测试。"""

import pytest

from meta.api.meta_api import _action_to_dict, _list_column_dict, _validate_condition
from meta.core.models_ui_config import UIListViewColumn

pytestmark = [pytest.mark.unit]


class _Field:
    def __init__(self, field_id):
        self.id = field_id
        self.name = field_id
        self.ui = None
        self.enum_values = []


_FIELD_MAP = {'status': _Field('status'), 'code': _Field('code')}


def test_validate_condition_accepts_closed_grammar():
    assert _validate_condition({'field': 'status', 'in': ['draft', 'submitted']}, _FIELD_MAP) == ''
    assert _validate_condition({'field': 'status', 'equals': 'draft'}, _FIELD_MAP) == ''
    assert _validate_condition({'field': 'status', 'not_empty': True}, _FIELD_MAP) == ''


@pytest.mark.parametrize('condition, code', [
    ({'field': 'status', 'in': []}, 'UNKNOWN_CONDITION'),
    ({'field': 'status', 'equals': 'x', 'in': ['x']}, 'UNKNOWN_CONDITION'),
    ({'field': 'status', 'and': [{'field': 'code'}]}, 'UNKNOWN_CONDITION'),
    ({'field': 'nope', 'equals': 'x'}, 'UNKNOWN_FIELD'),
])
def test_validate_condition_rejects_unknown_forms(condition, code):
    assert _validate_condition(condition, _FIELD_MAP) == code


def test_column_visible_when_passthrough_and_degrade():
    warnings = []
    valid = _list_column_dict(
        UIListViewColumn(key='status', visible_when={'field': 'status', 'equals': 'draft'}),
        _FIELD_MAP, warnings)
    assert valid['visible_when'] == {'field': 'status', 'equals': 'draft'}
    assert warnings == []

    invalid = _list_column_dict(
        UIListViewColumn(key='status', visible_when={'field': 'status', 'and': []}),
        _FIELD_MAP, warnings)
    assert 'visible_when' not in invalid
    assert warnings[-1]['code'] == 'UNKNOWN_CONDITION'


def test_column_without_declaration_keeps_payload_shape():
    payload = _list_column_dict(UIListViewColumn(key='code'), _FIELD_MAP, [])
    assert 'visible_when' not in payload
    assert 'roles' not in payload


def test_action_visible_when_and_roles_degrade():
    warnings = []
    payload = _action_to_dict(
        {'id': 'retry', 'visible_when': {'field': 'status', 'and': []}, 'roles': 'admin'},
        _FIELD_MAP, warnings)
    assert 'visible_when' not in payload
    assert 'roles' not in payload
    assert {warning['code'] for warning in warnings} == {'UNKNOWN_CONDITION'}


def test_action_visible_when_valid_passthrough():
    payload = _action_to_dict(
        {'id': 'retry', 'visible_when': {'field': 'status', 'in': ['failed']},
         'roles': ['admin']},
        _FIELD_MAP, [])
    assert payload['visible_when'] == {'field': 'status', 'in': ['failed']}
    assert payload['roles'] == ['admin']


def test_ui_meta_explain_reports_sources(api_client):
    resp = api_client.get(
        '/api/v1/meta/notification_delivery/ui-meta?explain=1')
    assert resp.status_code == 200
    meta = resp.get_json()['data']['meta']
    assert meta['effective_view'] == 'default'
    assert isinstance(meta['warnings'], list)
    sources = meta['sources']
    assert sources and sources[0]['key'] == 'ui_view_config'
    assert sources[0]['file'].endswith('notification_delivery.yaml')
    assert sources[0]['line'] > 0


def test_ui_meta_unknown_view_falls_back(api_client):
    resp = api_client.get('/api/v1/meta/notification_delivery/ui-meta?view=__nope__')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['meta']['effective_view'] == 'default'
    assert data['meta']['warnings'][0]['code'] == 'UNKNOWN_VIEW'


@pytest.fixture(scope='module')
def api_client():
    from meta.tests.conftest import get_shared_app

    return get_shared_app()[1]
