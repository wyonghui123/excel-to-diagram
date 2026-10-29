# -*- coding: utf-8 -*-
"""test_change_request_decision.py

M3 T6：审批决策链路（FR-008 / §5.3，D1/D2 任务复用）

覆盖：
  D1 approve handler：submitted → approved，回执 data.new_status == 'approved'，
     落 approved_by / approved_at
  D2 已 approved 再 approve ⇒ no-op success（幂等，approved_at 不变）
  D3 reject handler：submitted → rejected，comment 落 fail_reason
  D4 四眼原则：同一个人（任务 created_by == actor）自批被 decision_effect 拒绝，
     任务仍 waiting_approval（BO 未被调用）
  D5 重复决策同 effect_key ⇒ 返回首次结果（replayed=True，生效动作只调用 1 次）
  D6 入口错误：缺 change_request_id / 申请不存在 / 非法边（INVALID_TRANSITION 409）

设计取舍：
  - handler 的 _get_ds 指向临时 SQLite（monkeypatch），绝不碰 architecture.db；
  - D4/D5 走真实 DecisionEffectProtocol（§9.7 协议）+ 临时 bo_action_registry，
    approve 动作注册为真实 handler，验证「任务侧守卫 → BO 生效 → 任务归位」；
  - bo_action_registry 用例结束后恢复快照，避免污染其他测试。
"""
import json
import os
import sys
import uuid

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from meta.core.decision_effect import DecisionEffectError, DecisionEffectProtocol
from meta.core.sql_adapters import SQLiteAdapter
from meta.core.table_name_validator import register_table_name
from meta.services.change_request_decision import (
    change_request_approve_handler,
    change_request_reject_handler,
)
from meta.services.change_request_service import CR_TABLE, CRL_TABLE


DDL = {
    CR_TABLE: """
        CREATE TABLE IF NOT EXISTS change_requests (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            target_object_type  TEXT NOT NULL,
            target_object_id    TEXT NOT NULL,
            target_revision_no  INTEGER NOT NULL,
            status              TEXT NOT NULL DEFAULT 'draft',
            reason_code         TEXT NULL,
            summary             TEXT NULL,
            submitted_by        TEXT NULL,
            submitted_at        TEXT NULL,
            approved_by         TEXT NULL,
            approved_at         TEXT NULL,
            applied_at          TEXT NULL,
            applied_revision_no INTEGER NULL,
            fail_reason         TEXT NULL,
            change_set_id       TEXT NULL,
            created_by          TEXT NULL,
            created_at          TEXT NOT NULL,
            updated_by          TEXT NULL,
            updated_at          TEXT NULL
        )
    """,
    CRL_TABLE: """
        CREATE TABLE IF NOT EXISTS change_request_lines (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            change_request_id INTEGER NOT NULL,
            line_key          TEXT NULL,
            field_name        TEXT NOT NULL,
            old_value         TEXT NULL,
            new_value         TEXT NULL
        )
    """,
}


@pytest.fixture
def ds(tmp_path):
    """临时平台库：变更申请两表 + 任务/事件/幂等账。"""
    from meta.core.task_event_schema import ensure_task_event_tables
    from meta.core.task_idempotency import ensure_idempotency_table
    from meta.core.task_schema import ensure_task_tables

    data_source = SQLiteAdapter()
    data_source.connect(path=str(tmp_path / 'm3_decision.db'))
    for name, ddl in DDL.items():
        data_source.execute(ddl)
        register_table_name(name)
    register_table_name('tasks')
    ensure_task_tables(data_source)
    ensure_task_event_tables(data_source)
    ensure_idempotency_table(data_source)
    yield data_source
    data_source.disconnect()


@pytest.fixture(autouse=True)
def patch_data_source(monkeypatch, ds):
    """approve / reject handler 的 _get_ds 指向临时库。"""
    import meta.services.change_request_decision as mod
    monkeypatch.setattr(mod, '_get_ds', lambda: ds)
    return ds


@pytest.fixture
def action_registry():
    """快照-恢复全局 BO 注册表，避免污染其他用例。"""
    from meta.core.bo_action_registry import bo_action_registry

    saved = dict(bo_action_registry._actions)
    bo_action_registry.clear()
    yield bo_action_registry
    bo_action_registry._actions.clear()
    bo_action_registry._actions.update(saved)


def _make_cr(ds, *, status='submitted', **extra):
    row = {
        'target_object_type': 'sales_order',
        'target_object_id': '1',
        'target_revision_no': 1,
        'status': status,
        'created_at': '2026-10-29 00:00:00',
    }
    row.update(extra)
    return ds.insert(CR_TABLE, row)


def _insert_task(ds, cr_id, *, created_by='u-sub', attempt=1,
                 approve='change_request.approve',
                 reject='change_request.reject'):
    task_id = uuid.uuid4().hex
    ds.insert('tasks', {
        'id': task_id,
        'code': None,
        'title': '变更申请审批 #%s' % cr_id,
        'type': 'approval',
        'status': 'waiting_approval',
        'priority': 'P1',
        'app_id': '',
        'executor_type': 'human',
        'assign_policy': 'claim',
        'executor_candidates': json.dumps([], ensure_ascii=False),
        'executor_config': json.dumps({
            'decision_actions': {'approve': approve, 'reject': reject},
        }, ensure_ascii=False),
        'inputs': json.dumps({
            'change_request_id': cr_id,
            'target_object_type': 'sales_order',
            'target_object_id': '1',
            'target_revision_no': 1,
        }, ensure_ascii=False),
        'doc_ref': str(cr_id),
        'created_by': created_by,
        'created_at': '2026-10-29 00:00:00',
        'attempt': attempt,
    })
    return task_id


def _task_row(ds, task_id):
    rows = ds.find('tasks', {'id': task_id})
    return rows[0] if rows else None


def _register(registry, action_id, handler):
    registry.register(
        action_id, handler,
        description='M3 测试 action',
        object_type='change_request',
        category='business',
        input_schema={'type': 'object', 'properties': {}},
    )


# ---------------------------------------------------------------- D1~D3 handler

class TestDecisionHandlers:
    def test_d1_approve_writes_audit_columns(self, ds):
        cr_id = _make_cr(ds, status='submitted')

        res = change_request_approve_handler(
            {'change_request_id': cr_id}, {'actor': 'u-appr'})

        assert res['success'] is True
        assert res['data']['new_status'] == 'approved'
        row = ds.find_by_id(CR_TABLE, cr_id)
        assert row['status'] == 'approved'
        assert row['approved_by'] == 'u-appr'
        assert row['approved_at']

    def test_d2_approve_again_is_noop(self, ds):
        cr_id = _make_cr(ds, status='approved', approved_by='u-appr',
                         approved_at='2026-10-29 01:00:00')

        res = change_request_approve_handler(
            {'id': cr_id}, {'actor': 'u-other'})

        assert res['success'] is True
        assert res['data']['new_status'] == 'approved'
        row = ds.find_by_id(CR_TABLE, cr_id)
        assert row['approved_at'] == '2026-10-29 01:00:00'
        assert row['approved_by'] == 'u-appr'

    def test_d3_reject_writes_fail_reason(self, ds):
        cr_id = _make_cr(ds, status='submitted')

        res = change_request_reject_handler(
            {'change_request_id': cr_id, 'comment': '金额不符'},
            {'actor': 'u-appr'})

        assert res['success'] is True
        assert res['data']['new_status'] == 'rejected'
        row = ds.find_by_id(CR_TABLE, cr_id)
        assert row['status'] == 'rejected'
        assert row['fail_reason'] == '金额不符'

    def test_d6_missing_id(self, ds):
        res = change_request_approve_handler({}, {'actor': 'u-1'})
        assert res['success'] is False
        assert 'change_request_id' in res['message']

    def test_d6_not_found(self, ds):
        res = change_request_approve_handler(
            {'change_request_id': 99999}, {'actor': 'u-1'})
        assert res['success'] is False
        assert res['code'] == 'CHANGE_REQUEST_NOT_FOUND'
        assert res['status_code'] == 404

    def test_d6_invalid_transition(self, ds):
        cr_id = _make_cr(ds, status='draft')

        res = change_request_approve_handler(
            {'change_request_id': cr_id}, {'actor': 'u-1'})

        assert res['success'] is False
        assert res['code'] == 'INVALID_TRANSITION'
        assert res['status_code'] == 409
        assert ds.find_by_id(CR_TABLE, cr_id)['status'] == 'draft'


# ---------------------------------------------------------------- D4 四眼原则

class TestFourEyes:
    def test_d4_self_approval_blocked(self, ds, action_registry):
        """提交人 == 审批人 ⇒ 任务侧守卫拒绝，BO 未被调用。"""
        cr_id = _make_cr(ds, status='submitted')
        task_id = _insert_task(ds, cr_id, created_by='u-same')

        with pytest.raises(DecisionEffectError):
            DecisionEffectProtocol(action_registry).decide(
                ds, task_id, decision='approve', actor='u-same',
                reviewer_permission=True,
            )

        assert _task_row(ds, task_id)['status'] == 'waiting_approval'
        assert ds.find_by_id(CR_TABLE, cr_id)['status'] == 'submitted'

    def test_d4_other_approver_passes_and_effect_applied(self, ds, action_registry):
        """不同审批人 ⇒ 守卫放行 → 真实 approve handler 生效 → 任务 done。"""
        cr_id = _make_cr(ds, status='submitted')
        task_id = _insert_task(ds, cr_id, created_by='u-sub')
        _register(action_registry, 'change_request.approve',
                  change_request_approve_handler)

        outcome = DecisionEffectProtocol(action_registry).decide(
            ds, task_id, decision='approve', actor='u-appr',
            reviewer_permission=True,
        )

        assert outcome['task_status'] == 'done'
        assert outcome['receipt']['new_status'] == 'approved'
        assert _task_row(ds, task_id)['status'] == 'done'
        assert ds.find_by_id(CR_TABLE, cr_id)['status'] == 'approved'


# ---------------------------------------------------------------- D5 幂等重放

class TestReplay:
    def test_d5_same_effect_key_returns_first_result(self, ds, action_registry):
        cr_id = _make_cr(ds, status='submitted')
        task_id = _insert_task(ds, cr_id, created_by='u-sub')

        calls = []

        def wrapped(params, context):
            calls.append(dict(context))
            return change_request_approve_handler(params, context)

        _register(action_registry, 'change_request.approve', wrapped)
        protocol = DecisionEffectProtocol(action_registry)

        first = protocol.decide(ds, task_id, decision='approve',
                                actor='u-appr', reviewer_permission=True)
        second = protocol.decide(ds, task_id, decision='approve',
                                 actor='u-appr', reviewer_permission=True)

        assert first['replayed'] is False
        assert second['replayed'] is True
        assert first['effect_key'] == '%s:1' % task_id
        assert second['effect_key'] == '%s:1' % task_id
        assert len(calls) == 1
        assert second['receipt'] == first['receipt']
        # 单据只推进一次
        assert ds.find_by_id(CR_TABLE, cr_id)['approved_at']
