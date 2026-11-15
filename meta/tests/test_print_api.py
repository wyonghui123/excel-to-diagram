# -*- coding: utf-8 -*-
"""[打印平台 M4] `/api/print/*` 契约测试：鉴权、入参、错误码、流式响应。

服务层全部 monkeypatch，不触真实 DB / 浏览器 / 附件存储。
"""

import pytest
from flask import Flask

from meta.api import print_api
from meta.services import auth_middleware
from meta.services import print_capability as capability
from meta.services import print_repository as repo
from meta.services import print_service
from meta.services import print_template_service as templates

pytestmark = pytest.mark.unit

USER = {'id': 7, 'user_id': 7, 'username': 'printer', 'name': 'printer',
        'permissions': ['*'], 'token_version': 0}


@pytest.fixture
def app():
    application = Flask(__name__)
    application.config['TESTING'] = True
    application.register_blueprint(print_api.print_bp)
    return application


@pytest.fixture
def client(app, monkeypatch):
    monkeypatch.setattr(auth_middleware.token_blacklist_service, 'is_blacklisted',
                        lambda token: False)
    monkeypatch.setattr(auth_middleware.TokenService, 'verify_token',
                        staticmethod(lambda token: dict(USER)))
    test_client = app.test_client()
    test_client.environ_base['HTTP_AUTHORIZATION'] = 'Bearer test-token'
    return test_client


def _template_row(**over):
    row = {'id': 11, 'bo_code': 'sales_order', 'type_code': '', 'code': 'so_default',
           'name': '销售订单', 'version': 1, 'status': 'draft',
           'html': '<p>{{ doc.code }}</p>', 'css': '',
           'variables_json': '{"root": "doc", "fields": {}}',
           'paper_size': 'A4', 'orientation': 'portrait',
           'margin_top': 10, 'margin_right': 10, 'margin_bottom': 10,
           'margin_left': 10, 'scope_type': 'system', 'scope_id': None,
           'effective_from': None, 'effective_to': None,
           'created_by': 'admin', 'created_at': '2026-11-15 10:00:00',
           'published_at': None, 'archived_at': None}
    row.update(over)
    return row


def _binding_row(**over):
    row = {'id': 3, 'bo_code': 'sales_order', 'type_code': '', 'template_id': 11,
           'condition_json': '{"status": "draft"}', 'priority': 10,
           'is_default': 1, 'is_active': 1, 'scope_type': 'system',
           'scope_id': None, 'created_at': '2026-11-15 10:00:00',
           'updated_at': None}
    row.update(over)
    return row


def _run_row(**over):
    row = {'id': 21, 'bo_code': 'sales_order', 'type_code': '', 'doc_id': 'SO-1',
           'doc_no': 'SO-2026-0001', 'doc_rev': 'rev-1', 'template_id': 11,
           'template_version': 1, 'trigger': 'print', 'is_formal': 1,
           'is_reprint': 0, 'print_seq': 1, 'watermark': 'NONE',
           'status': 'succeeded', 'attachment_id': 55, 'payload_hash': 'abc',
           'job_run_id': None, 'error_code': None, 'error_message': None,
           'operator_id': '7', 'operator_name': 'printer',
           'created_at': '2026-11-15 10:00:00', 'finished_at': None}
    row.update(over)
    return row


def test_unauthorized_without_token(app):
    assert app.test_client().get('/api/print/printable').status_code == 401


def test_printable_filters_unreadable_bo(client, monkeypatch):
    monkeypatch.setattr(capability, 'list_printable_bo_types', lambda: [
        {'bo_code': 'sales_order', 'type_code': 'header', 'name': '销售订单'},
        {'bo_code': 'secret_doc', 'type_code': 'header', 'name': '机密'},
    ])
    monkeypatch.setattr(repo, 'list_bindings', lambda bo_code, **kw: (
        [_binding_row()] if bo_code == 'sales_order' else []))
    monkeypatch.setattr(print_api, 'evaluate', lambda user, bo, action: (
        type('D', (), {'allowed': bo == 'sales_order'})()))

    body = client.get('/api/print/printable').get_json()
    items = body['data']['items']
    assert [item['bo_code'] for item in items] == ['sales_order']
    assert items[0]['binding_count'] == 1
    assert items[0]['bindings'][0]['condition'] == {'status': 'draft'}


def test_template_list_hides_content_without_template_read(client, monkeypatch):
    monkeypatch.setattr(repo, 'list_templates', lambda **kw: [_template_row()])
    monkeypatch.setattr(print_api, 'evaluate', lambda user, bo, action: (
        type('D', (), {'allowed': True})()))
    monkeypatch.setattr(print_api, 'evaluate_code', lambda user, code: False)

    items = client.get('/api/print/templates?bo_code=sales_order').get_json()['data']['items']
    assert items and 'html' not in items[0]


def test_template_list_includes_content_with_template_read(client, monkeypatch):
    monkeypatch.setattr(repo, 'list_templates', lambda **kw: [_template_row()])
    monkeypatch.setattr(print_api, 'evaluate', lambda user, bo, action: (
        type('D', (), {'allowed': True})()))
    monkeypatch.setattr(print_api, 'evaluate_code', lambda user, code: True)

    items = client.get('/api/print/templates').get_json()['data']['items']
    assert items[0]['html'] == '<p>{{ doc.code }}</p>'


def test_template_create_requires_manage_permission(client, monkeypatch):
    monkeypatch.setattr(print_api, 'evaluate_code', lambda user, code: False)
    called = []
    monkeypatch.setattr(templates, 'create_draft', lambda *a, **kw: called.append(a))

    response = client.post('/api/print/templates', json={'bo_code': 'sales_order'})
    assert response.status_code == 403
    assert response.get_json()['error_code'] == 'forbidden'
    assert called == []


def test_template_create_reports_missing_fields(client, monkeypatch):
    monkeypatch.setattr(print_api, 'evaluate_code', lambda user, code: True)
    response = client.post('/api/print/templates', json={'bo_code': 'sales_order'})
    assert response.status_code == 400
    fields = {item['field'] for item in response.get_json()['errors']}
    assert {'code', 'name', 'html'} <= fields


def test_template_validate_returns_variable_errors(client, monkeypatch):
    monkeypatch.setattr(repo, 'get_template', lambda tid: _template_row(
        html='<p>{{ doc.amount }} {{ foo.bar }}</p>'))
    monkeypatch.setattr(templates, 'derive_variables', lambda bo: {
        'root': 'doc', 'fields': {'amount': {'label': '金额', 'type': 'decimal',
                                             'readable': True}},
        'collections': {}})
    monkeypatch.setattr(print_api, 'evaluate_code', lambda user, code: True)

    body = client.post('/api/print/templates/11/validate', json={}).get_json()['data']
    assert body['valid'] is False
    codes = {item['code'] for item in body['errors']}
    assert codes == {'unknown_variable'}


def test_fork_default_delegates_to_service(client, monkeypatch):
    captured = {}

    def fake_fork(bo_code, **kwargs):
        captured['bo_code'] = bo_code
        captured['kwargs'] = kwargs
        return _template_row(bo_code=bo_code, code='default', name='默认版式')

    monkeypatch.setattr(templates, 'fork_default', fake_fork)
    monkeypatch.setattr(print_api, 'evaluate_code', lambda user, code: True)

    response = client.post('/api/print/templates/0/fork-default',
                           json={'bo_code': 'sales_order', 'type_code': 'header'})
    assert response.status_code == 200
    assert captured['bo_code'] == 'sales_order'
    assert captured['kwargs']['type_code'] == 'header'
    assert response.get_json()['data']['template']['code'] == 'default'


def test_binding_create_rejects_unknown_condition_field(client, monkeypatch):
    monkeypatch.setattr(print_api, 'evaluate_code', lambda user, code: True)
    monkeypatch.setattr(templates, 'derive_variables', lambda bo: {
        'root': 'doc', 'fields': {'status': {'label': '状态', 'type': 'enum',
                                             'readable': True}}, 'collections': {}})
    monkeypatch.setattr(repo, 'get_template', lambda tid: _template_row())
    inserted = []
    monkeypatch.setattr(repo, 'insert_binding', lambda data: inserted.append(data))

    response = client.post('/api/print/bindings', json={
        'bo_code': 'sales_order', 'template_id': 11,
        'condition': {'unknown_field': 'x'}})
    assert response.status_code == 400
    assert {item['code'] for item in response.get_json()['errors']} == {
        'unknown_condition_field'}
    assert inserted == []


def test_resolve_reports_default_layout_sentinel(client, monkeypatch):
    monkeypatch.setattr(print_api, 'evaluate', lambda user, bo, action: (
        type('D', (), {'allowed': True})()))
    monkeypatch.setattr(print_service, 'load_document', lambda bo, doc: {
        'bo_code': bo, 'values': {}, 'collections': {}, 'doc_no': 'SO-1',
        'doc_rev': 'rev-1', 'state': 'draft', 'meta': object()})
    monkeypatch.setattr(print_service, 'resolve_template', lambda *a, **kw: {
        'template': None, 'binding': None, 'reason': 'no_binding',
        'candidates': 0, 'rejected': []})

    body = client.post('/api/print/resolve',
                       json={'bo_code': 'sales_order', 'doc_id': 'SO-1'}).get_json()
    assert body['data']['uses_default_layout'] is True
    assert body['data']['reason'] == 'no_binding'


def test_render_streams_preview_pdf(client, monkeypatch):
    monkeypatch.setattr(print_api, 'evaluate', lambda user, bo, action: (
        type('D', (), {'allowed': True})()))
    monkeypatch.setattr(print_service, 'render_document', lambda *a, **kw: {
        'pdf': b'%PDF-1.4 preview', 'doc_no': 'SO-2026-0001',
        'template_id': 11, 'template_version': 1, 'watermark': 'PREVIEW',
        'payload_hash': 'hash'})

    response = client.post('/api/print/render',
                           json={'bo_code': 'sales_order', 'doc_id': 'SO-1'})
    assert response.status_code == 200
    assert response.mimetype == 'application/pdf'
    assert response.data.startswith(b'%PDF')
    assert response.headers['X-Print-Watermark'] == 'PREVIEW'

    bad = client.post('/api/print/render',
                      json={'bo_code': 'sales_order', 'doc_id': 'SO-1', 'mode': 'print'})
    assert bad.status_code == 400
    assert bad.get_json()['error_code'] == 'invalid_mode'


def test_run_passes_operator_and_trigger(client, monkeypatch):
    captured = {}

    def fake_print(bo_code, type_code, doc_id, **kwargs):
        captured.update(kwargs)
        return {'run': _run_row(trigger=kwargs['trigger']), 'attachment_id': 55}

    monkeypatch.setattr(print_api, 'evaluate', lambda user, bo, action: (
        type('D', (), {'allowed': True})()))
    monkeypatch.setattr(print_service, 'print_document', fake_print)

    body = client.post('/api/print/run', json={
        'bo_code': 'sales_order', 'doc_id': 'SO-1', 'trigger': 'download'}).get_json()
    assert body['data']['attachment_id'] == 55
    assert captured['trigger'] == 'download'
    assert captured['operator']['username'] == 'printer'


def test_reprint_streams_archived_bytes_with_degradation_header(client, monkeypatch):
    monkeypatch.setattr(print_api, 'evaluate', lambda user, bo, action: (
        type('D', (), {'allowed': True})()))
    monkeypatch.setattr(repo, 'get_run', lambda rid: _run_row(id=rid))
    monkeypatch.setattr(print_service, 'reprint_document', lambda rid, **kw: {
        'run': _run_row(id=22, trigger='reprint', is_reprint=1, watermark='REPRINT'),
        'pdf': b'%PDF-1.4 archived', 'source_run_id': rid, 'attachment_id': 55,
        'watermark': 'REPRINT', 'watermark_applied': False})

    response = client.post('/api/print/reprint', json={'print_run_id': 21})
    assert response.status_code == 200
    assert response.data.startswith(b'%PDF')
    assert response.headers['X-Print-Watermark'] == 'REPRINT'
    assert response.headers['X-Print-Watermark-Applied'] == 'false'
    assert response.headers['X-Print-Source-Run-Id'] == '21'


def test_runs_requires_bo_code(client):
    response = client.get('/api/print/runs')
    assert response.status_code == 400
    assert response.get_json()['error_code'] == 'data_invalid'


def test_run_rejects_batch_trigger(client, monkeypatch):
    monkeypatch.setattr(print_api, 'evaluate', lambda user, bo, action: (
        type('D', (), {'allowed': True})()))
    response = client.post('/api/print/run', json={
        'bo_code': 'sales_order', 'doc_id': 'SO-1', 'trigger': 'batch'})
    assert response.status_code == 400
    assert response.get_json()['error_code'] == 'invalid_trigger'


# ------------------------------------------------------------------ 批量 (M5)

class _FakeStore:
    def __init__(self, run_id=42):
        self.run_id = run_id
        self.created = []

    def create_run(self, job_code, **kwargs):
        self.created.append((job_code, kwargs))
        return self.run_id


def test_batch_requires_bo_read(client, monkeypatch):
    monkeypatch.setattr(print_api, 'evaluate', lambda user, bo, action: (
        type('D', (), {'allowed': False})()))
    response = client.post('/api/print/batch', json={
        'bo_code': 'secret_doc', 'doc_ids': ['1']})
    assert response.status_code == 403


def test_batch_rejects_empty_doc_ids(client, monkeypatch):
    monkeypatch.setattr(print_api, 'evaluate', lambda user, bo, action: (
        type('D', (), {'allowed': True})()))
    response = client.post('/api/print/batch', json={
        'bo_code': 'sales_order', 'doc_ids': []})
    assert response.status_code == 400
    assert response.get_json()['error_code'] == 'invalid_doc_ids'


def test_batch_rejects_too_many_docs(client, monkeypatch):
    monkeypatch.setattr(print_api, 'evaluate', lambda user, bo, action: (
        type('D', (), {'allowed': True})()))
    monkeypatch.setattr(print_service, 'batch_limit', lambda: 2)
    response = client.post('/api/print/batch', json={
        'bo_code': 'sales_order', 'doc_ids': ['1', '2', '3']})
    assert response.status_code == 400
    assert response.get_json()['error_code'] == 'batch_too_large'


def test_batch_enqueues_job_and_starts_execution(client, monkeypatch):
    monkeypatch.setattr(print_api, 'evaluate', lambda user, bo, action: (
        type('D', (), {'allowed': True})()))
    monkeypatch.setattr(print_service, 'batch_limit', lambda: 200)
    store = _FakeStore()
    started = {}
    monkeypatch.setattr(print_api, '_get_job_store', lambda: store)
    monkeypatch.setattr(print_api, '_start_batch', lambda s, run_id, params: (
        started.update({'store': s, 'run_id': run_id, 'params': params})))

    response = client.post('/api/print/batch', json={
        'bo_code': 'sales_order', 'type_code': 'header',
        'doc_ids': ['SO-1', 'SO-2'], 'template_id': 11})
    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['task_run_id'] == 42
    assert data['run_id'] == 42

    job_code, kwargs = store.created[-1]
    assert job_code == 'print_document'
    assert kwargs['params']['doc_ids'] == ['SO-1', 'SO-2']
    assert kwargs['params']['template_id'] == 11
    assert kwargs['params']['operator']['username'] == 'printer'
    assert kwargs['run_key'].startswith('print:')
    assert kwargs['max_attempts'] == 1
    assert started['run_id'] == 42
    assert started['params']['type_code'] == 'header'


def test_batch_reports_missing_job_definition(client, monkeypatch):
    monkeypatch.setattr(print_api, 'evaluate', lambda user, bo, action: (
        type('D', (), {'allowed': True})()))
    monkeypatch.setattr(print_api, '_get_job_store', lambda: _FakeStore(run_id=None))
    monkeypatch.setattr(print_api, '_start_batch', lambda *args: None)

    response = client.post('/api/print/batch', json={
        'bo_code': 'sales_order', 'doc_ids': ['SO-1']})
    assert response.status_code == 503
    assert response.get_json()['error_code'] == 'job_not_registered'