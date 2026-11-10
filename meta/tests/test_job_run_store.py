# -*- coding: utf-8 -*-
"""后台作业执行账本（`task_runs`）单元测试。

覆盖（spec §5 / §6 / §11）:
  · v246 三表 + 索引 + 作业定义播种；
  · `run_key` 幂等（重复 tick 不产生重复 run）；
  · claim 条件更新：同一 run 只能被一个 worker 领走；
  · start / 续租（仅持有者可续）/ finish 成功与失败分支；
  · 失败 → retrying（按 backoff 排期）→ 到期 promote → pending；
  · attempt 耗尽 → dead；人工 retry 重开；
  · 租约过期回收幂等；取消语义；
  · 触发器乐观推进与到期扫描。

时间全部显式传入（UTC epoch 秒），不依赖真实时钟。
"""

import os
import sqlite3

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.core.job_run_store import (
    RUN_STATUSES, JobRunStore,
)
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


def _run(store, now=T0, job_code='audit_failure_retry', **kwargs):
    kwargs.setdefault('run_key', 't:%s' % now)
    kwargs.setdefault('scheduled_for', now)
    return store.create_run(job_code, now=now, **kwargs)


# ── 迁移 ──────────────────────────────────────────────────────────────

def test_v246_installs_tables_indexes_and_seeds(conn):
    ds = inv.MemDS(conn)
    tables = {r['name'] for r in ds.query(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {'job_definitions', 'job_triggers', 'task_runs'} <= tables

    indexes = {r['name'] for r in ds.query(
        "SELECT name FROM sqlite_master WHERE type='index'")}
    assert {'ix_job_triggers_due', 'ix_task_runs_status_lease',
            'ix_task_runs_job_time'} <= indexes

    assert ds.query('SELECT COUNT(*) c FROM job_definitions')[0]['c'] == \
        len(v246.JOB_SEEDS)
    assert ds.query(
        'SELECT COUNT(*) c FROM job_triggers '
        'WHERE enabled=0 AND next_run_at IS NULL')[0]['c'] == len(v246.JOB_SEEDS)


def test_v246_is_idempotent(conn):
    # 再跑一遍 DDL + 播种不应报错，也不应产生重复行
    v246._do_tables(conn)
    v246._do_indexes(conn)
    v246._do_job_definitions(conn)
    v246._do_triggers(conn)
    ds = inv.MemDS(conn)
    assert ds.query('SELECT COUNT(*) c FROM job_definitions')[0]['c'] == \
        len(v246.JOB_SEEDS)


# ── 创建 ──────────────────────────────────────────────────────────────

def test_create_run_is_idempotent_by_run_key(conn):
    store = _store(conn)
    first = _run(store, run_key='9:%s' % T0)
    second = _run(store, run_key='9:%s' % T0)
    assert first == second
    assert inv.MemDS(conn).query(
        'SELECT COUNT(*) c FROM task_runs')[0]['c'] == 1

    run = store.get_run(first)
    assert run['status'] == 'pending'
    assert run['attempt'] == 1
    assert run['params'] == {}


def test_create_run_unknown_job_returns_none(conn):
    assert _store(conn).create_run('no_such_job', now=T0) is None


def test_create_run_snapshots_params(conn):
    store = _store(conn)
    rid = _run(store, params={'batch': 3, 'note': '测试'})
    assert store.get_run(rid)['params'] == {'batch': 3, 'note': '测试'}
    assert store.list_runs()[0]['params']['batch'] == 3


# ── claim / lease ────────────────────────────────────────────────────

def test_claim_only_once(conn):
    store = _store(conn)
    rid = _run(store)
    assert store.claim(rid, 'w1', now=T0) is True
    assert store.claim(rid, 'w2', now=T0) is False

    run = store.get_run(rid)
    assert run['status'] == 'claimed'
    assert run['worker_id'] == 'w1'
    assert run['lease_until'] == pytest.approx(T0 + 60)


def test_start_requires_claim_owner(conn):
    store = _store(conn)
    rid = _run(store)
    assert store.start(rid, 'w1', now=T0) is False
    store.claim(rid, 'w1', now=T0)
    assert store.start(rid, 'w2', now=T0) is False
    assert store.start(rid, 'w1', now=T0) is True
    assert store.get_run(rid)['status'] == 'running'


def test_renew_lease_only_owner(conn):
    store = _store(conn)
    rid = _run(store)
    store.claim(rid, 'w1', lease_seconds=60, now=T0)
    store.start(rid, 'w1', now=T0)

    assert store.renew_lease(rid, 'w2', lease_seconds=60, now=T0 + 30) is False
    assert store.renew_lease(rid, 'w1', lease_seconds=60, now=T0 + 30) is True
    assert store.get_run(rid)['lease_until'] == pytest.approx(T0 + 90)


# ── finish ────────────────────────────────────────────────────────────

def test_finish_success(conn):
    store = _store(conn)
    rid = _run(store)
    store.claim(rid, 'w1', now=T0)
    store.start(rid, 'w1', now=T0)

    assert store.finish(rid, 'w2', True, now=T0 + 5) is None   # 非持有人
    assert store.finish(rid, 'w1', True, result={'rows': 2},
                        now=T0 + 5) == 'succeeded'

    run = store.get_run(rid)
    assert run['status'] == 'succeeded'
    assert run['duration_ms'] == 5000
    assert run['worker_id'] is None
    assert run['lease_until'] is None


def test_finish_failure_schedules_retry_then_dead(conn):
    store = _store(conn)
    rid = _run(store, job_code='db_analyze')          # max_attempts=2, backoff=300
    store.claim(rid, 'w1', now=T0)
    store.start(rid, 'w1', now=T0)

    assert store.finish(rid, 'w1', False, error='boom',
                        now=T0 + 1) == 'retrying'
    run = store.get_run(rid)
    assert run['attempt'] == 1
    assert run['next_retry_at'] == pytest.approx(T0 + 1 + 300)

    # 未到期不放行，到期后转 pending
    assert store.promote_retries(now=T0 + 300) == []
    assert store.promote_retries(now=T0 + 301) == [rid]
    run = store.get_run(rid)
    assert run['status'] == 'pending'
    assert run['attempt'] == 2                       # promote 时递增 attempt

    # 第二次尝试失败 → dead
    store.claim(rid, 'w2', now=T0 + 302)
    store.start(rid, 'w2', now=T0 + 302)
    assert store.finish(rid, 'w2', False, error='boom again',
                        now=T0 + 303) == 'dead'
    run = store.get_run(rid)
    assert run['next_retry_at'] is None
    assert run['attempt'] == 2


def test_manual_retry_reopens_dead_run(conn):
    store = _store(conn)
    rid = _run(store, job_code='db_vacuum')           # max_attempts=1
    store.claim(rid, 'w1', now=T0)
    store.start(rid, 'w1', now=T0)
    assert store.finish(rid, 'w1', False, now=T0 + 1) == 'dead'

    assert store.retry(rid, now=T0 + 2) is True
    run = store.get_run(rid)
    assert run['status'] == 'pending'
    assert run['attempt'] == 2
    assert run['max_attempts'] == 2
    assert run['error'] is None
    assert store.retry(rid, now=T0 + 3) is False       # pending 不可再 retry


def test_cancel_blocks_claim_and_finish(conn):
    store = _store(conn)
    rid = _run(store)
    assert store.cancel(rid, now=T0) is True
    assert store.get_run(rid)['status'] == 'cancelled'
    assert store.claim(rid, 'w1', now=T0) is False

    rid2 = _run(store, run_key='t2', scheduled_for=T0)
    store.claim(rid2, 'w1', now=T0)
    store.start(rid2, 'w1', now=T0)
    assert store.cancel(rid2, now=T0 + 1) is True
    assert store.get_run(rid2)['status'] == 'cancelled'
    assert store.finish(rid2, 'w1', True, now=T0 + 2) is None


# ── 租约回收 ──────────────────────────────────────────────────────────

def test_reclaim_expired_moves_to_retrying_once(conn):
    store = _store(conn)
    rid = _run(store, job_code='db_analyze')
    store.claim(rid, 'w1', lease_seconds=60, now=T0)
    store.start(rid, 'w1', now=T0)

    assert store.reclaim_expired(now=T0 + 59) == []
    assert store.reclaim_expired(now=T0 + 61) == [rid]
    run = store.get_run(rid)
    assert run['status'] == 'retrying'
    assert run['attempt'] == 1                       # 下一 attempt 号在 promote 时递增
    assert run['error'] == 'lease expired'

    # 放行下一个 attempt
    assert store.promote_retries(now=T0 + 61) == [rid]
    assert store.get_run(rid)['attempt'] == 2

    # 幂等：再次回收不会重复自增
    assert store.reclaim_expired(now=T0 + 120) == []
    assert store.get_run(rid)['attempt'] == 2


def test_reclaim_expired_dead_when_attempts_exhausted(conn):
    store = _store(conn)
    rid = _run(store, job_code='db_vacuum')           # max_attempts=1
    store.claim(rid, 'w1', lease_seconds=60, now=T0)
    store.start(rid, 'w1', now=T0)

    assert store.reclaim_expired(now=T0 + 61) == [rid]
    run = store.get_run(rid)
    assert run['status'] == 'dead'
    assert run['attempt'] == 1


# ── 触发器 / 扫描 ────────────────────────────────────────────────────

def test_advance_trigger_is_optimistic(conn):
    store = _store(conn)
    ds = inv.MemDS(conn)
    tid = ds.query('SELECT id FROM job_triggers ORDER BY id')[0]['id']
    ds.execute(
        'UPDATE job_triggers SET enabled=1, next_run_at=? WHERE id=?',
        [T0, tid])
    ds.commit()

    assert [t['id'] for t in store.due_triggers(now=T0)] == [tid]
    assert store.advance_trigger(tid, T0, T0 + 60, now=T0) is True

    # 旧值已过期：不推进、不覆盖
    assert store.advance_trigger(tid, T0, T0 + 120, now=T0 + 1) is False
    row = ds.query('SELECT next_run_at, last_run_at FROM job_triggers '
                   'WHERE id=?', [tid])[0]
    assert row['next_run_at'] == pytest.approx(T0 + 60)
    assert row['last_run_at'] == pytest.approx(T0)


def test_pending_runs_filters_by_schedule(conn):
    store = _store(conn)
    rid = _run(store, scheduled_for=T0 + 100)
    assert store.pending_runs(now=T0) == []
    assert [r['id'] for r in store.pending_runs(now=T0 + 100)] == [rid]


def test_list_runs_filters_and_validates(conn):
    store = _store(conn)
    _run(store, run_key='a', job_code='db_analyze')
    _run(store, run_key='b', job_code='db_vacuum')

    assert len(store.list_runs(job_code='db_analyze')) == 1
    assert len(store.list_runs(status='pending')) == 2
    with pytest.raises(ValueError):
        store.list_runs(status='bogus')
    assert 'skipped' in RUN_STATUSES


def test_v246_migrate_and_verify_on_file_db(tmp_path):
    """migration_runner 的真实入口：文件库上 migrate + verify，且可重复执行。"""
    db = tmp_path / 'job.db'
    sqlite3.connect(str(db)).close()

    assert v246.migrate(str(db)) is True
    assert v246.verify(str(db)) is True
    assert v246.migrate(str(db)) is True      # 幂等
    assert v246.verify(str(db)) is True


def test_v246_migrate_skips_missing_db(tmp_path):
    assert v246.migrate(str(tmp_path / 'missing.db')) is False