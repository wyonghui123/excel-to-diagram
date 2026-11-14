# -*- coding: utf-8 -*-
"""`task_runs.progress`、进度上报与导入状态投影单元测试。

覆盖 spec-unified-async-job-2026-11-14:
  · FR-004：`update_progress` 仅 claimed/running 可写 + ≥1s 节流；
  · FR-004：`update_result` 只写结果不改状态；
  · FR-004：`JobContext.report_progress` 委托 store，缺失时 no-op；
  · FR-006：`_run_to_task_status` 把 run 投影为 `/import/status` 旧结构。

时间全部显式传入（UTC epoch 秒），不依赖真实时钟。
"""

import os
import sqlite3
import threading

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.api.export_import_api import _run_to_task_status
from meta.core.job_executor_registry import JobContext
from meta.core.job_run_store import JobRunStore
from meta.migrations import v246__background_job_infrastructure as v246
from meta.migrations.v270__task_runs_progress import (
    _add_progress_column, _seed_import_job,
)
from meta.tests import inventory_test_doubles as inv

T0 = 1_800_000_000.0


@pytest.fixture()
def conn():
    c = sqlite3.connect(':memory:', isolation_level=None)
    v246._do_tables(c)
    v246._do_indexes(c)
    v246._do_job_definitions(c)
    v246._do_triggers(c)
    _add_progress_column(c)
    _seed_import_job(c)
    try:
        yield c
    finally:
        c.close()


def _store(conn):
    return JobRunStore(inv.MemDS(conn))


def _running(store, now=T0):
    rid = store.create_run(
        'import_cascade', now=now, run_key='t:%s' % now,
        params={'file_path': 'demo.xlsx'})
    assert store.claim(rid, 'w1', now=now) is True
    assert store.start(rid, 'w1', now=now) is True
    return rid


def test_update_progress_requires_active_run_and_throttles(conn):
    store = _store(conn)
    rid = _running(store)

    assert store.update_progress(rid, {'percent': 10}, now=T0) is True
    assert store.get_run(rid)['progress']['percent'] == 10

    # 1s 内被节流，不落库
    assert store.update_progress(rid, {'percent': 20}, now=T0 + 0.5) is False
    assert store.get_run(rid)['progress']['percent'] == 10

    assert store.update_progress(
        rid, {'percent': 30, 'stage': 'domain'}, now=T0 + 1) is True
    progress = store.get_run(rid)['progress']
    assert progress['percent'] == 30
    assert progress['stage'] == 'domain'
    assert progress['ts'] == pytest.approx(T0 + 1)

    # 终态后不再接受进度
    store.finish(rid, 'w1', True, now=T0 + 2)
    assert store.update_progress(rid, {'percent': 99}, now=T0 + 3) is False


def test_update_result_only_while_active(conn):
    store = _store(conn)
    rid = _running(store)

    assert store.update_result(rid, {'success': True}) is True
    assert store.get_run(rid)['result'] == '{"success": true}'

    store.finish(rid, 'w1', True, result={'success': True}, now=T0 + 2)
    assert store.update_result(rid, {'success': False}) is False


def test_job_context_report_progress_and_cancel(conn):
    store = _store(conn)
    rid = _running(store)
    ctx = JobContext(
        run_id=rid, job_code='import_cascade', params={}, attempt=1,
        deadline_monotonic=0.0, cancel_event=threading.Event(),
        store=store, worker_id='w1')

    assert ctx.should_cancel is False
    ctx.cancel_event.set()
    assert ctx.should_cancel is True

    assert ctx.report_progress({'percent': 5}) is True
    assert store.get_run(rid)['progress']['percent'] == 5

    bare = JobContext(
        run_id=rid, job_code='import_cascade', params={}, attempt=1,
        deadline_monotonic=0.0, cancel_event=threading.Event())
    assert bare.report_progress({'percent': 6}) is False


def test_run_to_task_status_projection(conn):
    base = {
        'progress': {
            'percent': 42, 'stage': 'domain', 'stage_name': '领域',
            'total': 3, 'current': 2, 'message': '正在导入领域',
        },
        'result': None, 'error': None,
    }

    running = _run_to_task_status(dict(base, status='running'))
    assert running['status'] == 'processing'
    assert running['progress'] == 42
    assert running['current_type'] == 'domain'
    assert running['current_type_name'] == '领域'
    assert running['total_types'] == 3
    assert running['current_index'] == 2
    assert running['message'] == '正在导入领域'

    succeeded = _run_to_task_status(dict(
        base, status='succeeded', result='{"success": true}'))
    assert succeeded['status'] == 'completed'
    assert succeeded['progress'] == 100
    assert succeeded['result'] == {'success': True}

    failed = _run_to_task_status(dict(base, status='failed', error='boom'))
    assert failed['status'] == 'failed'
    assert failed['error'] == 'boom'
    assert failed['message'] == '导入失败: boom'

    cancelled = _run_to_task_status(dict(base, status='cancelled'))
    assert cancelled['status'] == 'failed'
    assert cancelled['error'] == '已取消'
    assert cancelled['message'] == '导入已取消'

    pending = _run_to_task_status({'status': 'pending'})
    assert pending['status'] == 'processing'
    assert pending['message'] == '准备中...'
    assert pending['total_types'] == 0