# -*- coding: utf-8 -*-
"""M0：`lint_metamodel.py --ui-config` R-UI-01..08 契约测试。"""

import pytest

from meta.tools.lint_metamodel import lint_ui_config

pytestmark = [pytest.mark.unit]


def _doc(ui_view_config=None, fields=None):
    raw = {
        'id': 'demo',
        'fields': fields or [{'id': 'code'}, {'id': 'status'}],
    }
    if ui_view_config is not None:
        raw['ui_view_config'] = ui_view_config
    return [('demo.yaml', raw)]


def _reasons(docs):
    violations, _scanned = lint_ui_config(docs)
    return violations, ' '.join(item[2] for item in violations)


def test_valid_v2_config_passes():
    violations, _ = _reasons(_doc({
        'version': 2,
        'list': {
            'data_source': {
                'url': '/api/v2/demo',
                'method': 'get',
                'items_path': 'data.items',
                'total_path': 'data.total',
                'params_map': {'page_size': 'pageSize'},
            },
            'columns': [
                {'field': 'code', 'filterable': True, 'filter_type': 'text',
                 'visible_when': {'field': 'status', 'equals': 'draft'}},
            ],
            'actions': [
                {'id': 'run', 'position': 'toolbar',
                 'http': {'url': '/api/v2/demo/{row.code}'}, 'roles': ['admin']},
            ],
        },
        'variants': {
            'docs': {'title': '单据', 'list': {'columns': [{'field': 'status'}]}},
        },
    }))
    assert violations == []


def test_rui_01_variants_require_version_2():
    _violations, text = _reasons(_doc({'variants': {'docs': {}}}))
    assert 'R-UI-01' in text


def test_rui_01_bad_version():
    _violations, text = _reasons(_doc({'version': 3}))
    assert 'R-UI-01' in text


def test_rui_02_data_source_url_and_paths():
    _violations, text = _reasons(_doc({
        'version': 2,
        'list': {'data_source': {'url': '/v2/demo', 'method': 'patch'}},
    }))
    assert 'R-UI-02' in text


def test_rui_03_params_map():
    _violations, text = _reasons(_doc({
        'version': 2,
        'list': {'data_source': {
            'url': '/api/v2/demo', 'items_path': 'data.items',
            'total_path': 'data.total', 'params_map': {'x': 'bogus'}}},
    }))
    assert 'R-UI-03' in text


def test_rui_04_duplicate_action_and_bad_position():
    _violations, text = _reasons(_doc({
        'version': 2,
        'list': {'actions': [
            {'id': 'run', 'position': 'menu', 'http': {'url': '/api/v2/x'}},
            {'id': 'run', 'position': 'row', 'http': {'url': '/api/v2/x'}},
        ]},
    }))
    assert 'R-UI-04' in text


def test_rui_05_placeholder():
    _violations, text = _reasons(_doc({
        'version': 2,
        'list': {'actions': [
            {'id': 'run', 'position': 'row', 'http': {'url': '/api/v2/x/{foo}'}},
        ]},
    }))
    assert 'R-UI-05' in text


def test_rui_06_unknown_column_and_filter_type():
    _violations, text = _reasons(_doc({
        'version': 2,
        'list': {'columns': [{'field': 'nope', 'filterable': True}]},
    }))
    assert 'R-UI-06' in text


def test_rui_07_variant_name_and_nesting():
    _violations, text = _reasons(_doc({
        'version': 2,
        'variants': {
            'Docs-1': {},
            'nested': {'variants': {'x': {}}},
        },
    }))
    assert 'R-UI-07' in text


def test_rui_08_condition_and_roles():
    _violations, text = _reasons(_doc({
        'version': 2,
        'list': {'columns': [
            {'field': 'code', 'visible_when': {'field': 'code', 'between': [1, 2]},
             'roles': 'admin'},
        ]},
    }))
    assert 'R-UI-08' in text


def test_field_level_readonly_when():
    _violations, text = _reasons(_doc(
        {'version': 2},
        fields=[{'id': 'code', 'ui': {'readonly_when': {'field': 'nope', 'equals': 1}}}],
    ))
    assert 'R-UI-08' in text


def test_existing_schemas_have_zero_violations():
    violations, scanned = lint_ui_config()
    assert scanned > 0
    assert violations == []
