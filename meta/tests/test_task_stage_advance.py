# -*- coding: utf-8 -*-
"""阶段推进测试（M5-3 / spec §9.8）

覆盖：两阶段推进（stage_no / 候选人 / 参与流水 / SLA 重开）、末阶段回落
原有完成语义、重复推进幂等（SLA 不重复开单）。
"""

import json
import os
from datetime import datetime

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.core.task_participation import seed_participants
from meta.core.task_sla import open_sla
from meta.services.task_participation import decide_with_participation
from meta.services.task_stage import advance_stage, next_stage

T0 = datetime(2026, 11, 15, 9, 0, 0)


@pytest.fixture()
def ds(tmp_path):
    from meta.core.datasource import get_data_source
    from meta.core.task_event_schema import ensure_task_event_tables
    from meta.core.task_participation import ensure_participation_tables
    from meta.core.task_schema import ensure_task_tables
    from meta.core.task_sla import ensure_sla_tables

    source = get_data_source('sqlite', database=str(tmp_path / 'stage.db'))
    with source.transaction():
        ensure_task_tables(source)
        ensure_task_event_tables(source)
        ensure_sla_tables(source)
        ensure_participation_tables(source)
    yield source


def _snapshot(stages):
    return {'policy_code': 'PO_TWO_STAGE', 'task_type': 'approval',
            'steps': [{'step_no': 1, 'stage_no': stage, 'approver_type': 'user',
                       'approver_ref': ref, 'approve_mode': 'any',
                       'action_type': 'approve', 'routing_json': None,
                       'sla_hours': hours, 'min_amount': None,
                       'max_amount': None}
                      for stage, ref, hours in stages]}


def _seed_task(ds, snapshot, *, candidates=('alice',), stage_no=1,
               task_type='work_order', sla_hours=None):
    ts = T0.isoformat(timespec='seconds')
    ds.execute(
        'INSERT INTO tasks (id, title, type, status, executor_type, priority, '
        'executor_candidates, executor_config, inputs, doc_ref_type, doc_ref_id, '
        'created_by, stage_no, created_at, updated_at, attempt) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        ['T-1', '两阶段任务', task_type, 'waiting_approval', 'human', 'P2',
         json.dumps(list(candidates)),
         json.dumps({'completion_mode': 'any'}), json.dumps(
             {'policy_snapshot': snapshot}),
         'transfer_order', '1', 'alice', stage_no, ts, ts, 0])
    seed_participants(ds, 'T-1', list(candidates), role='required',
                      created_by='alice')
    if sla_hours:
        open_sla(ds, task_id='T-1', sla_key='resolution', name='首阶段',
                 target_seconds=sla_hours * 3600, start_at=T0)
    return 'T-1'


def test_next_stage():
    snapshot = _snapshot([(1, 'alice', None), (2, 'bob', None),
                          (3, 'carol', None)])
    assert next_stage(snapshot, 1) == 2
    assert next_stage(snapshot, 3) is None
    assert next_stage({}, 1) is None


def test_advance_moves_to_next_stage(ds):
    snapshot = _snapshot([(1, 'alice', 24), (2, 'bob', 48)])
    _seed_task(ds, snapshot, sla_hours=24)

    result = decide_with_participation(ds, 'T-1', decision='approve',
                                       actor='alice', now=T0)

    assert result['status'] == 'stage_advanced'
    assert result['stage_no'] == 2
    assert result['candidates'] == ['bob']

    row = ds.query('SELECT stage_no, executor_candidates, executor_config '
                   'FROM tasks WHERE id = ?', ['T-1'])[0]
    assert row['stage_no'] == 2
    assert json.loads(row['executor_candidates']) == ['bob']
    assert json.loads(row['executor_config'])['stage'] == 2

    pending = ds.query("SELECT participant FROM task_participations "
                       "WHERE task_id = ? AND outcome = 'pending'", ['T-1'])
    assert [r['participant'] for r in pending] == ['bob']

    slas = ds.query('SELECT sla_key, stage FROM task_slas WHERE task_id = ? '
                    'ORDER BY created_at', ['T-1'])
    keys = {r['sla_key']: r['stage'] for r in slas}
    assert keys['stage-2'] == 'in_progress'
    assert keys['resolution'] == 'cancelled'


def test_advance_is_idempotent_for_sla(ds):
    snapshot = _snapshot([(1, 'alice', 24), (2, 'bob', 48)])
    _seed_task(ds, snapshot)
    assert decide_with_participation(ds, 'T-1', decision='approve',
                                     actor='alice', now=T0)['status'] == \
        'stage_advanced'
    reloaded = ds.query('SELECT * FROM tasks WHERE id = ?', ['T-1'])[0]
    assert advance_stage(ds, reloaded, actor='bob', now=T0) is None
    rows = ds.query("SELECT id FROM task_slas WHERE task_id = ? "
                    "AND sla_key = 'stage-2'", ['T-1'])
    assert len(rows) == 1


def test_last_stage_completes_normally(ds):
    snapshot = _snapshot([(1, 'alice', None), (2, 'bob', None)])
    _seed_task(ds, snapshot)
    decide_with_participation(ds, 'T-1', decision='approve', actor='alice',
                              now=T0)
    result = decide_with_participation(ds, 'T-1', decision='approve',
                                       actor='bob', now=T0)
    assert result['status'] == 'completed'
    row = ds.query('SELECT stage_no FROM tasks WHERE id = ?', ['T-1'])[0]
    assert row['stage_no'] == 2


def test_empty_next_stage_pool_keeps_stage_with_reason(ds):
    snapshot = _snapshot([(1, 'alice', None),
                          (2, None, None)])  # 第二阶段无取人来源
    _seed_task(ds, snapshot)
    result = decide_with_participation(ds, 'T-1', decision='approve',
                                       actor='alice', now=T0)
    assert result['status'] == 'stage_advanced'
    assert result['candidates'] == []
    assert result['assign_reason'] == 'no_member'


def _multi_snapshot(steps):
    """steps = [(step_no, stage_no, ref, hours, approve_mode)]"""
    return {'policy_code': 'PO_MULTI_STAGE', 'task_type': 'approval',
            'steps': [{'step_no': step_no, 'stage_no': stage_no,
                       'approver_type': 'user', 'approver_ref': ref,
                       'approve_mode': mode, 'action_type': 'approve',
                       'routing_json': None, 'sla_hours': hours,
                       'min_amount': None, 'max_amount': None}
                      for step_no, stage_no, ref, hours, mode in steps]}


def test_stage_sla_uses_min_hours_across_steps(ds):
    """阶段 SLA = 同阶段各步 sla_hours 最小值（spec §9.4 阶段聚合）。"""
    snapshot = _multi_snapshot([
        (1, 1, 'alice', None, 'any'),
        (2, 2, 'bob', 48, 'any'),
        (3, 2, 'carol', 12, 'any'),
    ])
    _seed_task(ds, snapshot)

    result = advance_stage(ds, ds.query('SELECT * FROM tasks WHERE id = ?',
                                        ['T-1'])[0], actor='alice', now=T0)

    assert result['status'] == 'stage_advanced'
    sla = ds.query("SELECT target_seconds, due_at FROM task_slas "
                   "WHERE task_id = ? AND sla_key = 'stage-2'", ['T-1'])[0]
    assert sla['target_seconds'] == 12 * 3600
    assert sla['due_at'] == '2026-11-15T21:00:00'


def test_stage_completion_mode_all_if_any_step_all(ds):
    """阶段会签口径：任一步 all ⇒ 整阶段 all。"""
    snapshot = _multi_snapshot([
        (1, 1, 'alice', None, 'any'),
        (2, 2, 'bob', None, 'any'),
        (3, 2, 'carol', None, 'all'),
    ])
    _seed_task(ds, snapshot)

    advance_stage(ds, ds.query('SELECT * FROM tasks WHERE id = ?', ['T-1'])[0],
                  actor='alice', now=T0)

    row = ds.query('SELECT executor_config FROM tasks WHERE id = ?',
                   ['T-1'])[0]
    assert json.loads(row['executor_config'])['completion_mode'] == 'all'


def test_advance_cas_skips_when_stage_moved(ds, monkeypatch):
    """CAS：取人期间阶段已被并发推进 ⇒ 放弃本次 UPDATE（返回 None）。"""
    snapshot = _multi_snapshot([
        (1, 1, 'alice', None, 'any'),
        (2, 2, 'bob', None, 'any'),
        (3, 3, 'carol', None, 'any'),
    ])
    _seed_task(ds, snapshot)
    loaded = ds.query('SELECT * FROM tasks WHERE id = ?', ['T-1'])[0]

    def _resolve_after_concurrent_move(snapshot_arg, stage_arg, ctx):
        ds.execute('UPDATE tasks SET stage_no = 2 WHERE id = ?', ['T-1'])
        return {'action': 'approve', 'candidates': ['bob'], 'notify': [],
                'explain': [], 'reason': None, 'source': '', 'ctx': ctx}

    monkeypatch.setattr('meta.services.task_stage.resolve_stage',
                        _resolve_after_concurrent_move)

    assert advance_stage(ds, loaded, actor='alice', now=T0) is None
    row = ds.query('SELECT stage_no FROM tasks WHERE id = ?', ['T-1'])[0]
    assert row['stage_no'] == 2     # 未被二次推进到 3