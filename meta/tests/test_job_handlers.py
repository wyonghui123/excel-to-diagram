# -*- coding: utf-8 -*-
"""默认作业执行器注册（`meta/handlers/job_handlers.py`）单元测试。

覆盖 spec §7.1 / §7.3 / §10.1 第 1-2 项：
  · `build_default_job_registry` 只注册白名单内的 5 个运维 handler + `bo_action`；
  · `bo_action` 桥接：成功 / 未知 action / 缺 action_id / action 失败；
  · 运维 handler 适配：TaskResult → JobResult 的双向映射。
"""

import threading
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

from meta.core.job_executor_registry import JobResult
from meta.handlers.job_handlers import (
    DEFAULT_OPS_HANDLERS, _make_ops_executor, build_default_job_registry,
    make_bo_action_executor, make_print_document_executor,
)


class _Ctx:
    def __init__(self, params, cancel_event=None):
        self.run_id = 7
        self.job_code = 'inspection_daily'
        self.params = params
        self.attempt = 1
        self.cancel_event = cancel_event or threading.Event()


class _FakeActionRegistry:
    def __init__(self, result=None, known=('inspection.run',)):
        self._result = result if result is not None else {
            'success': True, 'data': {'checked': 3}}
        self._known = set(known)
        self.calls = []

    def has(self, action_id):
        return action_id in self._known

    def call(self, action_id, payload, context):
        self.calls.append((action_id, payload, context))
        return self._result


def test_default_registry_names_are_whitelisted():
    registry = build_default_job_registry(data_source=object())
    expected = [code for code, _target in DEFAULT_OPS_HANDLERS] + ['bo_action']
    assert registry.names() == sorted(expected)


def test_bo_action_bridge_success():
    fake = _FakeActionRegistry()
    result = make_bo_action_executor(fake)(_Ctx({
        'action_id': 'inspection.run', 'payload': {'scope': 'all'},
        'permissions': ['*'],
    }))
    assert isinstance(result, JobResult) and result.success is True
    assert result.data['action_id'] == 'inspection.run'
    assert fake.calls[0][1] == {'scope': 'all'}
    assert fake.calls[0][2]['source'] == 'job_dispatcher'


def test_bo_action_bridge_unknown_action():
    result = make_bo_action_executor(_FakeActionRegistry(known=()))(
        _Ctx({'action_id': 'nope'}))
    assert result.success is False
    assert '未知 action_id' in result.error


def test_bo_action_bridge_requires_action_id():
    result = make_bo_action_executor(_FakeActionRegistry())(_Ctx({}))
    assert result.success is False
    assert 'action_id' in result.error


def test_bo_action_bridge_propagates_action_failure():
    fake = _FakeActionRegistry(result={'success': False, 'message': '库存锁定'})
    result = make_bo_action_executor(fake)(_Ctx({'action_id': 'inspection.run'}))
    assert result.success is False
    assert result.error == '库存锁定'


def test_ops_executor_maps_task_result_success():
    handler = SimpleNamespace(execute=lambda params, context: SimpleNamespace(
        success=True, data={'analyzed': 1}, error=None))
    result = _make_ops_executor('db_analyze', handler, object())(
        _Ctx({'batch_size': 5}))
    assert result.success is True
    assert result.data == {'analyzed': 1}


def test_ops_executor_maps_task_result_failure():
    handler = SimpleNamespace(execute=lambda params, context: SimpleNamespace(
        success=False, data=None, error='db locked'))
    result = _make_ops_executor('db_analyze', handler, object())(_Ctx({}))
    assert result.success is False
    assert result.error == 'db locked'


def test_ops_executor_short_circuits_on_cancel():
    event = threading.Event()
    event.set()
    handler = SimpleNamespace(execute=lambda params, context: SimpleNamespace(
        success=True, data={}, error=None))
    result = _make_ops_executor('db_analyze', handler, object())(
        _Ctx({}, cancel_event=event))
    assert result.success is False and result.error == 'cancelled'


# ---------------------------------------------------------- 批量打印执行器 (M5)

class _PrintCtx:
    def __init__(self, params, cancel=False):
        self.run_id = 88
        self.job_code = 'print_document'
        self.params = params
        self.attempt = 1
        self.cancel_event = threading.Event()
        if cancel:
            self.cancel_event.set()
        self.progress = []

    @property
    def should_cancel(self):
        return self.cancel_event.is_set()

    def report_progress(self, payload):
        self.progress.append(payload)
        return True


def test_print_document_executor_delegates_batch(monkeypatch):
    from meta.services import print_service
    captured = {}

    def fake_batch(bo_code, type_code, doc_ids, **kwargs):
        captured.update({'bo_code': bo_code, 'type_code': type_code,
                         'doc_ids': doc_ids, **kwargs})
        kwargs['progress_callback']({'total': 2, 'completed': 1, 'failed': 0})
        return {'total': 2, 'completed': 2, 'failed': 0, 'cancelled': False,
                'failures': [], 'runs': []}

    monkeypatch.setattr(print_service, 'batch_print_documents', fake_batch)
    ctx = _PrintCtx({'bo_code': 'demo', 'type_code': 'header',
                     'doc_ids': ['D1', 'D2'], 'template_id': 3,
                     'operator': {'id': 'u1'}})
    result = make_print_document_executor()(ctx)
    assert result.success is True
    assert result.data['completed'] == 2
    assert captured['job_run_id'] == '88'
    assert captured['operator'] == {'id': 'u1'}
    assert captured['template_id'] == 3
    assert ctx.progress == [{'total': 2, 'completed': 1, 'failed': 0}]


def test_print_document_executor_requires_doc_ids():
    result = make_print_document_executor()(_PrintCtx({'bo_code': 'demo'}))
    assert result.success is False
    assert 'doc_ids' in result.error


def test_print_document_executor_reports_cancelled(monkeypatch):
    from meta.services import print_service
    monkeypatch.setattr(print_service, 'batch_print_documents',
                        lambda *a, **kw: {'total': 2, 'completed': 1,
                                          'failed': 0, 'cancelled': True,
                                          'failures': [], 'runs': []})
    result = make_print_document_executor()(
        _PrintCtx({'bo_code': 'demo', 'doc_ids': ['D1', 'D2']}))
    assert result.success is False
    assert result.error == 'cancelled'