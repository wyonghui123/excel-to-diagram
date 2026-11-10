# -*- coding: utf-8 -*-
"""作业执行器注册表 + dispatcher 执行路径单元测试。

覆盖（spec §7 / §10 P2 / §11）:
  · 注册 / 查找（函数与对象两种形态）、未知 handler 不抛异常；
  · 执行体异常 → `JobResult(success=False)`，错误信息保留类型；
  · 超时 → `failed` 且 `cancel_event` 被置位（不强杀线程）；
  · 协作式取消：`cancel_event` 生效；已置位的 context 直接失败不执行；
  · 返回值归一化（None / dict / JobResult）；
  · dispatcher 非 DRY_RUN：claim → running → executor → succeeded；
  · 执行失败 → retrying（按 `backoff_seconds` 排期）→ 到期 promote → 成功；
  · 未注册 handler / 作业定义非 active 的处理。

时间显式传入（UTC epoch 秒），不依赖真实时钟。
"""

import os
import sqlite3
import threading
import time

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.core.job_executor_registry import (
    ExecutorRegistry, JobContext, JobResult,
)
from meta.core.job_dispatcher import JobDispatcher
from meta.core.job_run_store import JobRunStore
from meta.migrations import v246__background_job_infrastructure as v246
from meta.tests import inventory_test_doubles as inv

T0 = 1_800_000_000.0


@pytest.fixture()
def conn():
    c = sqlite3.connect(':memory:', isolation_level=None)
    v246._do_tables(c)
    v246._do_indexes(c)
    v246._do_job_definitions(c)
    v246._do_triggers(c)
    try:
        yield c
    finally:
        c.close()


def _ctx(cancel_event=None, run_id=1, timeout=5.0):
    return JobContext(
        run_id=run_id, job_code='db_checkpoint', params={}, attempt=1,
        deadline_monotonic=time.monotonic() + timeout,
        cancel_event=cancel_event or threading.Event())


def _store(conn):
    return JobRunStore(inv.MemDS(conn), clock=lambda: T0)


def _enable(conn, job_code, *, next_run_at=T0):
    conn.execute(
        'UPDATE job_triggers SET enabled=1, next_run_at=? '
        'WHERE job_id=(SELECT id FROM job_definitions WHERE code=?)',
        [next_run_at, job_code])
    conn.commit()


def _runs(conn):
    return inv.MemDS(conn).query('SELECT * FROM task_runs ORDER BY id')


def _dispatcher(store, registry=None):
    return JobDispatcher(store, enabled=True, dry_run=False,
                         clock=lambda: T0, registry=registry)


# ── 注册表 ────────────────────────────────────────────────────────────

def test_register_function_and_object():
    registry = ExecutorRegistry()
    registry.register('fn', lambda ctx: None)

    class Executor:
        name = 'obj'
        supports_cancel = True

        def run(self, ctx):
            return JobResult(True)

    obj = Executor()
    registry.register(obj)

    assert registry.get('fn').name == 'fn'
    assert registry.get('obj') is obj
    assert registry.get('missing') is None
    assert registry.names() == ['fn', 'obj']
    assert registry.unregister('fn') is True
    assert registry.get('fn') is None


def test_register_requires_name_and_func():
    registry = ExecutorRegistry()
    with pytest.raises(ValueError):
        registry.register('no-func')
    with pytest.raises(ValueError):
        registry.register(object())


def test_unknown_handler_returns_failure_without_raising():
    result = ExecutorRegistry().execute('nope', _ctx())
    assert result.success is False
    assert 'nope' in result.error


def test_executor_exception_becomes_failed_result():
    registry = ExecutorRegistry()
    registry.register('boom', lambda ctx: 1 / 0)
    result = registry.execute('boom', _ctx())
    assert result.success is False
    assert 'ZeroDivisionError' in result.error


def test_timeout_returns_failure_and_sets_cancel_event():
    registry = ExecutorRegistry()

    def slow(ctx):
        ctx.cancel_event.wait(2.0)
        return None

    registry.register('slow', slow)
    ctx = _ctx()
    started = time.monotonic()
    result = registry.execute('slow', ctx, timeout=0.05)
    elapsed = time.monotonic() - started

    assert result.success is False
    assert 'timeout' in result.error
    assert ctx.cancel_event.is_set()
    assert elapsed < 1.0


def test_cooperative_handler_stops_on_cancel_event():
    registry = ExecutorRegistry()

    def cooperative(ctx):
        while not ctx.cancel_event.wait(0.005):
            pass
        return JobResult(False, error='cancelled')

    registry.register('coop', cooperative)
    ctx = _ctx()
    threading.Timer(0.05, ctx.cancel_event.set).start()

    result = registry.execute('coop', ctx, timeout=2.0)

    assert result.success is False
    assert result.error == 'cancelled'


def test_pre_cancelled_context_never_invokes_handler():
    registry = ExecutorRegistry()
    called = []
    registry.register('never', lambda ctx: called.append(1))
    ctx = _ctx()
    ctx.cancel_event.set()

    result = registry.execute('never', ctx)

    assert result.success is False
    assert result.error == 'cancelled'
    assert called == []


def test_result_normalization():
    registry = ExecutorRegistry()
    registry.register('none', lambda ctx: None)
    registry.register('dict', lambda ctx: {'rows': 3})
    registry.register('direct', lambda ctx: JobResult(True, data={'x': 1}))
    registry.register('bad', lambda ctx: 42)

    assert registry.execute('none', _ctx()).success is True
    assert registry.execute('dict', _ctx()).data == {'rows': 3}
    assert registry.execute('direct', _ctx()).data == {'x': 1}
    bad = registry.execute('bad', _ctx())
    assert bad.success is False and 'int' in bad.error


# ── dispatcher 执行路径 ───────────────────────────────────────────────

def test_successful_execution_marks_run_succeeded(conn):
    _enable(conn, 'db_checkpoint')
    registry = ExecutorRegistry()
    seen = {}

    def handler(ctx):
        seen['run_id'] = ctx.run_id
        seen['attempt'] = ctx.attempt
        return JobResult(True, data={'rows': 3})

    registry.register('db_checkpoint', handler)
    summary = _dispatcher(_store(conn), registry).tick(T0)

    assert summary['claimed'] == 1
    assert summary['reclaimed'] == 0
    run = _runs(conn)[0]
    assert run['status'] == 'succeeded'
    assert run['result'] == '{"rows": 3}'
    assert run['finished_at'] == T0
    assert run['duration_ms'] == 0
    assert run['worker_id'] is None and run['lease_until'] is None
    assert seen == {'run_id': run['id'], 'attempt': 1}


def test_failed_execution_schedules_retry_with_backoff(conn):
    _enable(conn, 'db_checkpoint')          # max_attempts=2, backoff=60
    registry = ExecutorRegistry()

    def handler(ctx):
        raise RuntimeError('boom')

    registry.register('db_checkpoint', handler)

    summary = _dispatcher(_store(conn), registry).tick(T0)

    assert summary['claimed'] == 1
    run = _runs(conn)[0]
    assert run['status'] == 'retrying'
    assert run['attempt'] == 1
    assert run['next_retry_at'] == T0 + 60
    assert 'RuntimeError: boom' in run['error']
    assert run['worker_id'] is None


def test_due_retry_is_promoted_then_succeeds(conn):
    _enable(conn, 'db_checkpoint')
    registry = ExecutorRegistry()
    attempts = []

    def flaky(ctx):
        attempts.append(ctx.attempt)
        if ctx.attempt == 1:
            raise RuntimeError('first attempt fails')
        return JobResult(True)

    registry.register('db_checkpoint', flaky)
    dispatcher = _dispatcher(_store(conn), registry)
    dispatcher.tick(T0)
    assert _runs(conn)[0]['status'] == 'retrying'

    summary = dispatcher.tick(T0 + 60)

    assert summary['promoted'] == 1
    assert summary['claimed'] == 1
    run = _runs(conn)[0]
    assert run['status'] == 'succeeded'
    assert run['attempt'] == 2
    assert attempts == [1, 2]


def test_unregistered_handler_fails_run(conn):
    _enable(conn, 'db_checkpoint')
    summary = _dispatcher(_store(conn), ExecutorRegistry()).tick(T0)

    assert summary['claimed'] == 1
    run = _runs(conn)[0]
    assert run['status'] == 'retrying'
    assert 'db_checkpoint' in run['error']


def test_inactive_job_is_skipped_without_execution(conn):
    _enable(conn, 'db_checkpoint')
    conn.execute(
        "UPDATE job_definitions SET status='disabled' WHERE code=?",
        ['db_checkpoint'])
    conn.commit()
    registry = ExecutorRegistry()
    called = []
    registry.register('db_checkpoint', lambda ctx: called.append(1))

    summary = _dispatcher(_store(conn), registry).tick(T0)

    assert summary['skipped'] == 1
    assert summary['claimed'] == 0
    run = _runs(conn)[0]
    assert run['status'] == 'skipped'
    assert run['result'] == 'job_inactive'
    assert called == []


def test_claim_is_exclusive_across_workers(conn):
    """双 worker 竞争同一 run：只有第一个 worker 能领走（spec §10 P2）。"""
    store = _store(conn)
    run_id = store.create_run(
        'db_checkpoint', run_key='t:1', scheduled_for=T0, now=T0)

    assert store.claim(run_id, 'worker-a', now=T0) is True
    assert store.claim(run_id, 'worker-b', now=T0) is False
    assert store.get_run(run_id)['worker_id'] == 'worker-a'