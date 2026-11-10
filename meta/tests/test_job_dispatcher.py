# -*- coding: utf-8 -*-
"""后台作业 dispatcher（P1 影子模式）单元测试。

覆盖（spec §6 / §10 P1）:
  · `enabled=0` 时 tick 零动作（P0 播种默认关闭）；
  · DRY_RUN：建 run → 立即 `skipped`，触发器被乐观推进；
  · 推进后重放：旧 `next_run_at` 回拨时命中 `run_key` 幂等，只记 `duplicates`；
  · 非 DRY_RUN：run 留在 `pending`，供 P2 claim；
  · interval 触发器按 now + interval 推进；
  · 非法 cron 只记错误，不推进触发器；
  · `params_override` 落入 run.params；
  · 乐观推进失败（旧值不匹配）不产生 `advanced`；
  · start/stop 生命周期。

时间显式传入（UTC epoch 秒），不依赖真实时钟。
"""

import json
import os
import sqlite3

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

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


def _store(conn):
    return JobRunStore(inv.MemDS(conn))


def _enable(conn, job_code, *, next_run_at=T0, trigger_type=None,
            cron_expr=None, interval_seconds=None, params_override=None,
            enabled=1):
    """把播种的禁用触发器改成可触发（或按需换 trigger_type / cron）。"""
    conn.execute(
        'UPDATE job_triggers SET enabled=?, next_run_at=?, '
        'trigger_type=COALESCE(?, trigger_type), '
        'cron_expr=COALESCE(?, cron_expr), '
        'interval_seconds=COALESCE(?, interval_seconds), '
        'params_override=COALESCE(?, params_override) '
        'WHERE job_id=(SELECT id FROM job_definitions WHERE code=?)',
        [enabled, next_run_at, trigger_type, cron_expr, interval_seconds,
         params_override, job_code])
    conn.commit()


def _trigger(conn, job_code):
    return inv.MemDS(conn).query(
        'SELECT * FROM job_triggers WHERE job_id='
        '(SELECT id FROM job_definitions WHERE code=?)', [job_code])[0]


def _runs(conn):
    return inv.MemDS(conn).query('SELECT * FROM task_runs ORDER BY id')


def _dispatcher(store, *, enabled=True, dry_run=True, now=T0):
    return JobDispatcher(store, enabled=enabled, dry_run=dry_run,
                         clock=lambda: now)


# ── 开关 ──────────────────────────────────────────────────────────────

def test_disabled_tick_is_noop(conn):
    _enable(conn, 'db_checkpoint')
    summary = _dispatcher(_store(conn), enabled=False).tick(T0)
    assert summary['due'] == 0
    assert _runs(conn) == []
    assert _trigger(conn, 'db_checkpoint')['next_run_at'] == T0


def test_seeded_triggers_are_disabled_so_nothing_is_due(conn):
    summary = _dispatcher(_store(conn)).tick(T0)
    assert summary['due'] == 0
    assert _runs(conn) == []


# ── DRY_RUN 主路径 ────────────────────────────────────────────────────

def test_dry_run_records_then_skips_and_advances(conn):
    _enable(conn, 'db_checkpoint')
    store = _store(conn)

    summary = _dispatcher(store).tick(T0)

    assert summary == {'enabled': True, 'dry_run': True, 'due': 1,
                       'recorded': 1, 'skipped': 1, 'advanced': 1,
                       'duplicates': 0, 'errors': 0,
                       'promoted': 0, 'reclaimed': 0, 'claimed': 0,
                       'claim_conflicts': 0}
    run = _runs(conn)[0]
    assert run['status'] == 'skipped'
    assert run['run_key'] == '%d:%d' % (
        _trigger(conn, 'db_checkpoint')['id'], int(T0))
    assert run['scheduled_for'] == T0
    assert _trigger(conn, 'db_checkpoint')['next_run_at'] == T0 + 300


def test_replay_with_rewound_trigger_hits_run_key_unique(conn):
    _enable(conn, 'db_checkpoint')
    store = _store(conn)
    dispatcher = _dispatcher(store)
    dispatcher.tick(T0)
    first_id = _runs(conn)[0]['id']

    # 模拟「建 run 成功但推进丢失」：把 next_run_at 拨回，重新 tick
    conn.execute('UPDATE job_triggers SET next_run_at=?', [T0])
    conn.commit()
    summary = dispatcher.tick(T0)

    assert summary['due'] == 1
    assert summary['duplicates'] == 1
    assert summary['recorded'] == 0
    assert summary['skipped'] == 0
    assert summary['advanced'] == 1
    runs = _runs(conn)
    assert len(runs) == 1 and runs[0]['id'] == first_id


def test_non_dry_run_claims_and_executes_pending_run(conn):
    _enable(conn, 'db_checkpoint')
    dispatcher = _dispatcher(_store(conn), dry_run=False)
    dispatcher.registry.register('db_checkpoint', lambda ctx: {'ok': True})

    summary = dispatcher.tick(T0)

    assert summary['recorded'] == 1
    assert summary['skipped'] == 0
    assert summary['claimed'] == 1
    assert summary['claim_conflicts'] == 0
    run = _runs(conn)[0]
    assert run['status'] == 'succeeded'
    assert json.loads(run['result']) == {'ok': True}
    assert run['worker_id'] is None and run['lease_until'] is None


# ── 触发器类型 ────────────────────────────────────────────────────────

def test_interval_trigger_advances_by_interval(conn):
    _enable(conn, 'platform_tick', trigger_type='interval',
            interval_seconds=60)

    summary = _dispatcher(_store(conn)).tick(T0)

    assert summary['advanced'] == 1
    assert _trigger(conn, 'platform_tick')['next_run_at'] == T0 + 60


def test_invalid_cron_records_error_and_keeps_trigger(conn):
    _enable(conn, 'db_checkpoint', cron_expr='not-a-cron')
    summary = _dispatcher(_store(conn)).tick(T0)
    assert summary['recorded'] == 1
    assert summary['errors'] == 1
    assert summary['advanced'] == 0
    assert _trigger(conn, 'db_checkpoint')['next_run_at'] == T0


def test_params_override_is_snapshotted_into_run(conn):
    _enable(conn, 'import_queue_processor',
            params_override=json.dumps({'batch_size': 10}))
    _dispatcher(_store(conn)).tick(T0)
    run = _runs(conn)[0]
    assert json.loads(run['params']) == {'batch_size': 10}


def test_stale_trigger_row_cannot_advance(conn):
    _enable(conn, 'db_checkpoint')
    store = _store(conn)
    stale = _trigger(conn, 'db_checkpoint')
    # 另一 tick 先推进了触发器
    assert store.advance_trigger(stale['id'], T0, T0 + 300, now=T0) is True

    summary = {'enabled': True, 'dry_run': True, 'due': 0, 'recorded': 0,
               'skipped': 0, 'advanced': 0, 'duplicates': 0, 'errors': 0}
    _dispatcher(store)._process_trigger(stale, T0, summary)
    assert summary['advanced'] == 0
    assert summary['duplicates'] == 0
    assert summary['recorded'] == 1
    assert _trigger(conn, 'db_checkpoint')['next_run_at'] == T0 + 300


# ── 生命周期 ──────────────────────────────────────────────────────────

def test_start_stop_lifecycle(conn):
    store = _store(conn)
    disabled = _dispatcher(store, enabled=False)
    assert disabled.start() is False

    dispatcher = JobDispatcher(store, enabled=True, dry_run=True,
                              tick_interval=3600)
    assert dispatcher.start() is True
    dispatcher.stop(timeout=1.0)
    assert dispatcher._thread is None