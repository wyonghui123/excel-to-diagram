# -*- coding: utf-8 -*-
"""单据流 API 契约测试（路由存在性 + 视图函数行为 + 未登录 401）。"""

import pytest
from flask import Flask

from meta.api.doc_flow_api import doc_flow_bp
from meta.services.doc_flow_service import DocFlowServiceError, init_doc_flow_service


class FakeDocFlowService:
    def __init__(self):
        self.calls = []

    def list_rules(self, source_bo=None, target_bo=None):
        return {'rules': [{'rule_id': 'r1', 'source_bo': source_bo,
                           'target_bo': target_bo}], 'total': 1}

    def list_sources(self, rule_id, filters=None, include_zero_open=False,
                     page=1, page_size=20, source_item=''):
        self.calls.append(('list_sources', rule_id, filters, page, page_size))
        return {'rows': [{'source_id': '1', 'open_qty': 40}], 'total': 1,
                'page': page, 'page_size': page_size}

    def derive(self, payload, derived_by='', trace_id=''):
        self.calls.append(('derive', payload, derived_by))
        if payload.get('rule_id') == 'boom':
            raise DocFlowServiceError('DOC_FLOW_RULE_NOT_FOUND', '规则不存在', 404)
        return {'created': [{'target_id': 'T1'}], 'replayed': [],
                'total_edges': 1}

    def list_edges(self, **kwargs):
        return {'edges': [{'id': 'e1', 'quantity': 10.0}], 'total': 1}


@pytest.fixture()
def api_app():
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(doc_flow_bp)
    init_doc_flow_service(FakeDocFlowService())
    return app


def test_routes_registered(api_app):
    rules = {r.rule for r in api_app.url_map.iter_rules()}
    assert '/api/v2/doc-flow/rules' in rules
    assert '/api/v2/doc-flow/sources' in rules
    assert '/api/v2/doc-flow/derive' in rules
    assert '/api/v2/doc-flow/edges' in rules


def test_rules_requires_login(api_app):
    resp = api_app.test_client().get('/api/v2/doc-flow/rules')
    assert resp.status_code == 401
    assert resp.get_json()


def test_rules_view_filters_by_source_bo(api_app):
    from meta.api.doc_flow_api import _rules_view
    with api_app.test_request_context('/api/v2/doc-flow/rules?source_bo=shipment'):
        body, status = _rules_view()
    assert status == 200
    assert body['success'] is True
    assert body['data']['rules'][0]['source_bo'] == 'shipment'


def test_sources_view_passes_paging(api_app):
    from meta.api.doc_flow_api import _sources_view
    with api_app.test_request_context(
            '/api/v2/doc-flow/sources?rule_id=r1&page=2&page_size=5'):
        body, status = _sources_view()
    assert status == 200
    assert body['data']['page'] == 2
    assert body['data']['page_size'] == 5


def test_derive_view_requires_rule_id(api_app):
    from meta.api.doc_flow_api import _derive_view
    with api_app.test_request_context('/api/v2/doc-flow/derive', method='POST',
                                      json={'sources': []}):
        body, status = _derive_view()
    assert status == 400
    assert body['code'] == 'DOC_FLOW_QTY_INVALID'


def test_derive_view_maps_service_error(api_app):
    from meta.api.doc_flow_api import _derive_view
    with api_app.test_request_context('/api/v2/doc-flow/derive', method='POST',
                                      json={'rule_id': 'boom', 'sources': []}):
        resp, status = _derive_view()
    assert status == 404
    assert resp['code'] == 'DOC_FLOW_RULE_NOT_FOUND'


def test_edges_view_requires_a_filter(api_app):
    from meta.api.doc_flow_api import _edges_view
    with api_app.test_request_context('/api/v2/doc-flow/edges'):
        body, status = _edges_view()
    assert status == 400
    assert body['code'] == 'DOC_FLOW_EDGE_FILTER_REQUIRED'