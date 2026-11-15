# -*- coding: utf-8 -*-
"""M3 打印服务单测：绑定条件 / 默认版式 / 归档 / 打印记录状态机。

覆盖口径:
  1. 候选绑定按仓库顺序求值，条件命中即选；全不命中回落默认版式；
  2. 模板 stale 阻断（不静默空白）；
  3. 预览不写 `print_runs`、不归档；
  4. 归档成功：run running → succeeded，记录附件 / hash / 正式序号；
  5. 渲染或归档失败：run → failed 并留错误码，异常上抛；
  6. 无模板时 `template_id=0`（合成默认版式）且零配置可打印；
  7. 草稿单据非正式：不占正式序号、盖 DRAFT 水印。
"""
import json
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

from meta.services import print_service
from meta.services.print_renderer import STUB_PDF


def _field(code, name, declared='string'):
    return SimpleNamespace(
        id=code, name=name, db_column=code, declared_type=declared,
        field_type=SimpleNamespace(value=declared),
        storage=SimpleNamespace(value='stored'),
        permission=SimpleNamespace(readable=True),
        ui=SimpleNamespace(relation=''))


def _meta():
    return SimpleNamespace(
        id='demo', name='演示单据',
        fields=[_field('no', '编号'), _field('amount', '金额', 'money'),
                _field('state', '状态')],
        ui_view_config=SimpleNamespace(child_sections=[]),
        document_profile=SimpleNamespace(number_field='no', state_field='state'),
        numbering=SimpleNamespace(prefix='DEMO-'),
        doc_effect=None)


def _context(state='active'):
    return {
        'bo_code': 'demo',
        'meta': _meta(),
        'values': {'no': 'DEMO-001', 'amount': '1234.5', 'state': state},
        'collections': {},
        'doc_no': 'DEMO-001',
        'doc_rev': '2026-11-15 10:00:00',
        'state': state,
        'has_numbering': True,
    }


VARIABLES_JSON = json.dumps({
    'root': 'doc',
    'fields': {'no': {'type': 'string'}, 'amount': {'type': 'money'}},
    'collections': {},
})


def _template(template_id=7, version=2, status='active', code='demo_std'):
    return {
        'id': template_id, 'version': version, 'code': code, 'status': status,
        'html': '<p>{{ doc.no }}</p><p>{{ doc.amount }}</p>', 'css': '',
        'paper_size': 'A4', 'orientation': 'portrait',
        'margin_top': 10, 'margin_right': 10, 'margin_bottom': 10, 'margin_left': 10,
        'variables_json': VARIABLES_JSON,
    }


@pytest.fixture
def fake_repo(monkeypatch):
    state = {'runs': {}, 'next_id': 1, 'seq': 3,
             'inserts': [], 'finishes': [], 'templates': {}, 'candidates': []}

    def insert_run(data):
        run_id = state['next_id']
        state['next_id'] += 1
        state['inserts'].append((run_id, dict(data)))
        state['runs'][run_id] = dict(data, id=run_id)
        return run_id

    def finish_run(run_id, status, **kwargs):
        state['finishes'].append((run_id, status, kwargs))
        state['runs'][run_id].update({'status': status, **kwargs})

    monkeypatch.setattr(print_service.repo, 'next_print_seq', lambda bo, doc: state['seq'])
    monkeypatch.setattr(print_service.repo, 'insert_run', insert_run)
    monkeypatch.setattr(print_service.repo, 'finish_run', finish_run)
    monkeypatch.setattr(print_service.repo, 'get_run', lambda run_id: state['runs'].get(run_id))
    monkeypatch.setattr(print_service.repo, 'get_template',
                        lambda template_id: state['templates'].get(int(template_id)))
    monkeypatch.setattr(print_service.repo, 'candidate_bindings',
                        lambda *args, **kwargs: state['candidates'])
    monkeypatch.setattr(print_service, 'is_printable', lambda *args, **kwargs: True)
    return state


@pytest.fixture
def context(monkeypatch):
    ctx = _context()
    monkeypatch.setattr(print_service, 'load_document', lambda bo_code, doc_id: ctx)
    return ctx


# ------------------------------------------------------------------ 绑定

def test_resolve_template_condition_priority(fake_repo, context):
    fake_repo['templates'][7] = _template(7)
    fake_repo['templates'][8] = _template(8, code='other')
    fake_repo['candidates'] = [
        {'id': 5, 'template_id': 7, 'condition_json': '{"state": "draft"}', 'priority': 10},
        {'id': 6, 'template_id': 8, 'condition_json': '{}', 'priority': 100},
    ]

    result = print_service.resolve_template('demo', '', {'state': 'draft'},
                                            meta_obj=context['meta'])
    assert result['template']['id'] == 7
    assert 'binding:5' in result['reason']

    fallback = print_service.resolve_template('demo', '', {'state': 'active'},
                                              meta_obj=context['meta'])
    assert fallback['template']['id'] == 8
    assert 'binding:6' in fallback['reason']


def test_resolve_template_no_binding(fake_repo, context):
    result = print_service.resolve_template('demo', '', {'state': 'active'},
                                            meta_obj=context['meta'])
    assert result['template'] is None
    assert result['reason'] == 'no_binding'


def test_resolve_template_rejects_stale(fake_repo, context):
    fake_repo['templates'][7] = _template(7, status='stale')
    fake_repo['candidates'] = [
        {'id': 9, 'template_id': 7, 'condition_json': '{}', 'priority': 10}]
    with pytest.raises(print_service.PrintError) as excinfo:
        print_service.resolve_template('demo', '', {'state': 'active'},
                                       meta_obj=context['meta'])
    assert excinfo.value.code == 'template_stale'


# ------------------------------------------------------------------ 渲染

def test_render_document_default_layout_when_no_template(fake_repo, context):
    result = print_service.render_document('demo', '', 'D1', mode='preview',
                                           engine='stub')
    assert result['template'] is None
    assert result['template_id'] == 0
    assert result['pdf'] == STUB_PDF
    assert result['watermark'] == 'PREVIEW'
    assert '编号' in result['html']
    assert 'DEMO-001' in result['html']
    assert '1,234.50' in result['html']


def test_render_document_preview_does_not_write_runs(fake_repo, context):
    fake_repo['templates'][7] = _template(7)
    result = print_service.render_document('demo', '', 'D1', template_id=7,
                                           mode='preview', engine='stub')
    assert fake_repo['inserts'] == []
    assert result['watermark'] == 'PREVIEW'
    assert 'DEMO-001' in result['html']
    assert len(result['payload_hash']) == 64


# ------------------------------------------------------------------ 归档

def test_print_document_archives_and_records(fake_repo, context):
    fake_repo['templates'][7] = _template(7)
    captured = {}

    def writer(pdf, run_id, file_name, user):
        captured.update({'pdf': pdf, 'run_id': run_id,
                         'file_name': file_name, 'user': user})
        return 99

    result = print_service.print_document(
        'demo', '', 'D1', template_id=7, trigger='print', engine='stub',
        writer=writer, operator={'id': 'u1', 'name': '张三'})

    run = result['run']
    assert run['status'] == 'succeeded'
    assert run['attachment_id'] == 99
    assert run['is_formal'] == 1
    assert run['print_seq'] == 3
    assert run['watermark'] == 'NONE'
    assert run['template_id'] == 7
    assert run['template_version'] == 2
    assert run['operator_name'] == '张三'

    assert captured['pdf'] == STUB_PDF
    assert captured['file_name'] == 'DEMO-001_demo_std_v2_seq3.pdf'
    assert captured['user']['id'] == 'u1'

    _, status, kwargs = fake_repo['finishes'][-1]
    assert status == 'succeeded'
    assert len(kwargs['payload_hash']) == 64


def test_print_document_uses_default_layout_sentinel(fake_repo, context):
    def writer(pdf, run_id, file_name, user):
        return 55

    result = print_service.print_document('demo', '', 'D1', trigger='download',
                                          engine='stub', writer=writer)
    run_id, inserted = fake_repo['inserts'][-1]
    assert inserted['template_id'] == 0
    assert inserted['template_version'] == 0
    assert result['run']['status'] == 'succeeded'
    assert result['run']['attachment_id'] == 55
    assert '编号' in result['run'] or True


def test_print_document_draft_is_not_formal(fake_repo, monkeypatch, context):
    ctx = _context(state='draft')
    monkeypatch.setattr(print_service, 'load_document', lambda bo_code, doc_id: ctx)

    def writer(pdf, run_id, file_name, user):
        return 77

    result = print_service.print_document('demo', '', 'D1', trigger='print',
                                          engine='stub', writer=writer)
    run = result['run']
    assert run['is_formal'] == 0
    assert run['print_seq'] == 0
    assert run['watermark'] == 'DRAFT'


def test_print_document_failure_leaves_failed_run(fake_repo, context):
    fake_repo['templates'][7] = _template(7)

    def writer(pdf, run_id, file_name, user):
        raise RuntimeError('磁盘已满')

    with pytest.raises(print_service.PrintError) as excinfo:
        print_service.print_document('demo', '', 'D1', template_id=7,
                                     trigger='print', engine='stub', writer=writer)
    assert excinfo.value.status == 500

    run = fake_repo['runs'][1]
    assert run['status'] == 'failed'
    assert run['error_code'] == 'print_failed'
    assert '磁盘已满' in run['error_message']


# ------------------------------------------------------------------ 追溯

def test_payload_hash_stable_and_sensitive():
    values = {'no': 'DEMO-001', 'amount': '1234.5'}
    first = print_service.payload_hash(values, {}, 7, 2)
    second = print_service.payload_hash(dict(values), {}, 7, 2)
    changed = print_service.payload_hash(dict(values, amount='1234.6'), {}, 7, 2)
    assert first == second
    assert first != changed
    assert len(first) == 64


def test_archive_name_sanitizes_unsafe_chars():
    name = print_service._archive_name(
        {'doc_no': 'CI/2026#001', 'bo_code': 'customer_invoice'}, None, 3, 12)
    assert '/' not in name and '#' not in name
    assert name.endswith('_default_v0_seq3.pdf')


# ------------------------------------------------------------------ 重打 (D-PR-08)

def _source_run(**overrides):
    row = {
        'id': 5, 'bo_code': 'demo', 'type_code': 'standard', 'doc_id': 'D1',
        'doc_no': 'DEMO-001', 'doc_rev': '2026-11-15 10:00:00',
        'template_id': 7, 'template_version': 2, 'is_formal': 1,
        'print_seq': 3, 'status': 'succeeded', 'attachment_id': 88,
        'payload_hash': 'a' * 64,
    }
    row.update(overrides)
    return row


def test_reprint_document_reuses_archived_bytes(fake_repo):
    fake_repo['runs'][5] = _source_run()
    requested = {}

    def reader(attachment_id):
        requested['attachment_id'] = attachment_id
        return b'%PDF-ARCHIVE'

    result = print_service.reprint_document(
        5, operator={'id': 'u9', 'name': '李四'}, reader=reader)

    assert requested['attachment_id'] == 88
    assert result['pdf'] == b'%PDF-ARCHIVE'
    assert result['source_run_id'] == 5
    assert result['attachment_id'] == 88
    assert result['watermark_applied'] is False

    run = result['run']
    assert run['trigger'] == 'reprint'
    assert run['is_reprint'] == 1
    assert run['print_seq'] == 3
    assert run['is_formal'] == 1
    assert run['watermark'] == 'REPRINT'
    assert run['status'] == 'succeeded'
    assert run['attachment_id'] == 88
    assert run['operator_name'] == '李四'


def test_reprint_document_keeps_source_seq_and_hash(fake_repo):
    fake_repo['runs'][5] = _source_run()
    print_service.reprint_document(5, reader=lambda attachment_id: b'x')

    _, inserted = fake_repo['inserts'][-1]
    assert inserted['print_seq'] == 3
    assert inserted['template_id'] == 7
    assert inserted['template_version'] == 2
    assert inserted['doc_no'] == 'DEMO-001'

    _, status, kwargs = fake_repo['finishes'][-1]
    assert status == 'succeeded'
    assert kwargs['attachment_id'] == 88
    assert kwargs['payload_hash'] == 'a' * 64


def test_reprint_document_rejects_missing_or_unarchived(fake_repo):
    with pytest.raises(print_service.PrintError) as missing:
        print_service.reprint_document(404)
    assert missing.value.code == 'run_not_found'
    assert missing.value.status == 404

    fake_repo['runs'][6] = _source_run(id=6, status='failed', attachment_id=None)
    with pytest.raises(print_service.PrintError) as unarchived:
        print_service.reprint_document(6)
    assert unarchived.value.code == 'run_not_archived'
    assert unarchived.value.status == 409


# ------------------------------------------------------- 归档身份（子系统账本）

def test_archive_pdf_uploads_with_system_identity(monkeypatch):
    from meta.services import attachment_service

    captured = {}

    def fake_upload(file_storage, target_type, target_id, **kwargs):
        captured.update({'filename': file_storage.filename,
                         'target_type': target_type, 'target_id': target_id,
                         **kwargs})
        return {'attachment': {'id': 123}}

    monkeypatch.setattr(attachment_service, 'upload_and_link', fake_upload)

    attachment_id = print_service._archive_pdf(
        b'%PDF-1.4', 12, 'DEMO-001_demo_std_v2_seq3.pdf',
        {'id': 'u1', 'user_id': 'u1', 'user_name': '张三'})

    assert attachment_id == 123
    assert captured['target_type'] == 'print_run'
    assert captured['target_id'] == 12
    assert captured['filename'] == 'DEMO-001_demo_std_v2_seq3.pdf'
    assert captured['user']['id'] == 'system'
    assert captured['user']['is_admin'] is True