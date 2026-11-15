# -*- coding: utf-8 -*-
"""[M5-4 2026-11-15] 步骤动作三态（approve / auto / notify）验收用例。

对应 spec §9.4（阶段 × 动作）与 §9.8 M5-4：
  - auto  ：自动通过，不产生人工待办，直接推进（末阶段则走完）
  - notify：知会/抄送，进收件箱只读，不投票、不计入会签分母
  - approve：现行为不变（人工决策）
"""
import json
import os

import pytest

os.environ.setdefault('ALLOW_RAW_SQL', '1')

pytestmark = pytest.mark.unit

from meta.services import approval_task_service as svc
from meta.services.task_stage import (
    advance_stage,
    resolve_stage,
    settle_auto,
    stage_action,
)

FAKE_META = {
    'table': 'purchase_order',
    'title_field': None,
    'id_key': 'id',
    'title_prefix': '采购单',
    'app_id': 'test-app',
    'decision_actions': {'approve': {'action_id': 'noop'},
                         'reject': {'action_id': 'noop'}},
}


@pytest.fixture()
def ds(tmp_path):
    from meta.core.datasource import get_data_source
    from meta.core.task_event_schema import ensure_task_event_tables
    from meta.core.task_participation import ensure_participation_tables
    from meta.core.task_schema import ensure_task_tables
    from meta.core.task_sla import ensure_sla_tables

    source = get_data_source('sqlite', database=str(tmp_path / 'm5.db'))
    with source.transaction():
        ensure_task_tables(source)
        ensure_task_event_tables(source)
        ensure_sla_tables(source)
        ensure_participation_tables(source)
    yield source


@pytest.fixture()
def meta(monkeypatch):
    monkeypatch.setattr(svc, 'get_approval_meta', lambda _obj: dict(FAKE_META))
    return FAKE_META


def _step(stage, step, action, *, approver_type='user', ref='', **extra):
    row = {'stage_no': stage, 'step_no': step, 'action_type': action,
           'approver_type': approver_type, 'approver_ref': ref}
    row.update(extra)
    return row


def _snapshot(*steps, policy_code='P-ACT'):
    return {'policy_code': policy_code, 'task_type': 'approval',
            'steps': list(steps)}


def _insert_task(ds, task_id, snapshot, *, type_='work_order', stage=1,
                 candidates=(), config=None):
    now = '2026-11-15T09:00:00'
    columns = ['id', 'title', 'type', 'status', 'priority', 'executor_type',
               'assign_policy', 'executor_candidates', 'executor_config',
               'inputs', 'created_by', 'created_at', 'updated_at', 'stage_no']
    values = [task_id, '任务', type_, 'waiting_approval', 'P1', 'human',
              'claim', json.dumps(list(candidates)), json.dumps(config or {}),
              json.dumps({'policy_snapshot': snapshot}), 'alice', now, now, stage]
    ds.execute(
        'INSERT INTO tasks ({0}) VALUES ({1})'.format(
            ', '.join(columns), ', '.join(['?'] * len(columns))),
        values)
    return task_id


def _row(ds, task_id):
    rows = ds.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchall()
    assert rows, task_id
    return dict(zip([d[0] for d in ds.execute(
        'SELECT * FROM tasks WHERE id = ?', (task_id,)).description], rows[0]))


def _config(ds, task_id):
    return json.loads(_row(ds, task_id)['executor_config'])


def _participations(ds, task_id):
    rows = ds.execute(
        'SELECT participant, role, outcome FROM task_participations '
        'WHERE task_id = ? ORDER BY id', (task_id,)).fetchall()
    return {(r[0], r[1]): r[2] for r in rows}


# ─────────────────────────────────────────────────────────────────────────────
# 聚合规则
# ─────────────────────────────────────────────────────────────────────────────

def test_stage_action_aggregates_three_states():
    snapshot = {
        'steps': [
            _step(1, 1, 'auto'),
            _step(2, 1, 'notify', ref='carol'),
            _step(3, 1, 'approve', ref='bob'),
            _step(3, 2, 'notify', ref='carol'),
            _step(4, 1, 'auto'),
            _step(4, 2, 'auto'),
        ],
    }
    assert stage_action(snapshot, 1) == 'auto'
    assert stage_action(snapshot, 2) == 'notify'
    assert stage_action(snapshot, 3) == 'approve'
    assert stage_action(snapshot, 4) == 'auto'
    # 未知 / 缺失动作按 approve 兜底
    assert stage_action({'steps': [{'stage_no': 9, 'step_no': 1,
                                    'action_type': 'weird'}]}, 9) == 'approve'
    assert stage_action({'steps': []}, 1) == 'approve'


def test_resolve_stage_splits_notify_from_voting(ds):
    snapshot = _snapshot(_step(1, 1, 'approve', ref='bob'),
                         _step(1, 2, 'notify', ref='carol'),
                         _step(1, 3, 'auto'))
    stage = resolve_stage(snapshot, 1, {'data_source': ds})
    assert stage['action'] == 'approve'
    assert stage['candidates'] == ['bob']
    assert stage['notify'] == ['carol']
    assert {e.get('step_no') for e in stage['explain']} == {1, 2, 3}


# ─────────────────────────────────────────────────────────────────────────────
# auto：不产生人工待办
# ─────────────────────────────────────────────────────────────────────────────

def test_create_task_skips_auto_stage(ds, meta):
    snapshot = _snapshot(_step(1, 1, 'auto'),
                         _step(2, 1, 'approve', ref='bob'))
    task_id = svc.ApprovalTaskService(ds).create_task(
        'purchase_order', 'PO-1', policy_snapshot=snapshot, actor='alice')

    assert task_id
    row = _row(ds, task_id)
    assert row['status'] == 'waiting_approval'
    assert int(row['stage_no']) == 2
    assert json.loads(row['executor_candidates']) == ['bob']
    config = _config(ds, task_id)
    assert config['action_type'] == 'approve'
    assert _participations(ds, task_id) == {('bob', 'required'): 'pending'}


def test_advance_skips_intermediate_auto_stage(ds):
    snapshot = _snapshot(_step(1, 1, 'approve', ref='bob'),
                         _step(2, 1, 'auto'),
                         _step(3, 1, 'approve', ref='carol'))
    _insert_task(ds, 'T-AUTO', snapshot, candidates=['bob'])

    result = advance_stage(ds, {'id': 'T-AUTO'}, actor='bob')

    assert result['status'] == 'stage_advanced'
    assert result['stage_no'] == 3
    assert result['candidates'] == ['carol']
    assert int(_row(ds, 'T-AUTO')['stage_no']) == 3


def test_last_auto_stage_completes_without_effect(ds):
    snapshot = _snapshot(_step(1, 1, 'auto'))
    _insert_task(ds, 'T-DONE', snapshot, type_='work_order')

    result = settle_auto(ds, 'T-DONE')

    assert result['status'] == 'completed'
    assert result['auto_completed'] is True
    assert _row(ds, 'T-DONE')['status'] == 'done'


# ─────────────────────────────────────────────────────────────────────────────
# notify：只读知会
# ─────────────────────────────────────────────────────────────────────────────

def test_create_task_seeds_notify_rows(ds, meta):
    snapshot = _snapshot(_step(1, 1, 'approve', ref='bob'),
                         _step(1, 2, 'notify', ref='carol'))
    task_id = svc.ApprovalTaskService(ds).create_task(
        'purchase_order', 'PO-2', policy_snapshot=snapshot, actor='alice')

    config = _config(ds, task_id)
    assert config['action_type'] == 'approve'
    assert config['notify_candidates'] == ['carol']
    # 知会行 pending 但不计入会签分母
    assert _participations(ds, task_id) == {
        ('bob', 'required'): 'pending',
        ('carol', 'notify'): 'pending',
    }
    assert json.loads(_row(ds, task_id)['executor_candidates']) == ['bob']


def test_notify_participant_cannot_vote(ds):
    from meta.services.task_participation import (
        ParticipationConflictError,
        decide_with_participation,
    )
    from meta.core.task_participation import seed_participants

    snapshot = _snapshot(_step(1, 1, 'approve', ref='bob'),
                         _step(1, 2, 'notify', ref='carol'))
    _insert_task(ds, 'T-NOTIFY', snapshot, candidates=['bob'])
    seed_participants(ds, 'T-NOTIFY', ['bob'], role='required')
    seed_participants(ds, 'T-NOTIFY', ['carol'], role='notify')

    with pytest.raises(ParticipationConflictError):
        decide_with_participation(ds, 'T-NOTIFY', decision='approve',
                                  actor='carol')


def test_notify_only_stage_does_not_block_completion(ds):
    snapshot = _snapshot(_step(1, 1, 'notify', ref='carol'))
    _insert_task(ds, 'T-CC', snapshot, type_='work_order')

    result = settle_auto(ds, 'T-CC')

    assert result['status'] == 'completed'
    assert _row(ds, 'T-CC')['status'] == 'done'