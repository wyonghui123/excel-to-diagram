# -*- coding: utf-8 -*-
"""test_change_request_cancel.py

M3 G3：审批任务终止回写变更申请 cancelled + 对账方向 4

覆盖：
  T-A  经事件账唯一入口 record_transition 把 waiting_approval 任务置 failed
       ⇒ 仍停在 submitted 的 CR 自动 cancelled，fail_reason = 传入 reason
  T-A2 in_progress → cancelled ⇒ 默认 fail_reason「审批任务 cancelled，变更申请自动取消」
  T-B  CR 已是 approved / rejected（正常通过、驳回链路先 BO 生效后任务归位）
       ⇒ 回写为 no-op，不误写 cancelled
  T-C  非审批类任务（type=story）终止 ⇒ 不碰 CR
  T-D  对账方向 4：submitted 且无活跃审批任务 ⇒ change_request_without_approval_task
  T-E  有活跃审批任务（成对 decision_actions）⇒ 无方向 4 / 无方向 0 噪音

设计取舍：
  - 临时 SQLite（SQLiteAdapter）+ 显式建表：change_request_service._ensure_tables 的
    _TABLES_READY 是模块级缓存，跨用例会跳过建表，测试自带建表避免顺序依赖；
  - monkeypatch meta.core.models.registry 为 stub，阻断真实元模型扫描；
  - 绝不动 meta/architecture.db。
"""
import json
import os
import sys
from datetime import datetime

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from meta.core.decision_effect import reconcile_effects
from meta.core.sql_adapters import SQLiteAdapter
from meta.core.table_name_validator import register_table_name
from meta.core.task_event_schema import ensure_task_event_tables, record_transition
from meta.core.task_schema import ensure_task_tables
from meta.services.change_request_service import CRL_TABLE, CR_TABLE


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


class RegistryStub:
    """替代 meta.core.models.registry：不回真实元模型。"""

    def get(self, object_id):
        return None

    def all(self):
        return []


@pytest.fixture
def ds(tmp_path):
    data_source = SQLiteAdapter()
    data_source.connect(path=str(tmp_path / 'm3_cancel.db'))
    for name, ddl in DDL.items():
        data_source.execute(ddl)
        register_table_name(name)
    register_table_name('tasks')
    ensure_task_tables(data_source)
    ensure_task_event_tables(data_source)
    yield data_source
    data_source.disconnect()


@pytest.fixture(autouse=True)
def empty_registry(monkeypatch):
    monkeypatch.setattr('meta.core.models.registry', RegistryStub())


def _make_cr(ds, *, status='submitted', target_type='sales_order', target_id='1',
             target_revision_no=1, submitted_at='2026-10-29 00:00:00', **extra):
    row = {
        'target_object_type': target_type,
        'target_object_id': str(target_id),
        'target_revision_no': target_revision_no,
        'status': status,
        'submitted_by': 'u-sub',
        'submitted_at': submitted_at if status != 'draft' else None,
        'created_at': '2026-10-29 00:00:00',
        'change_set_id': 'cs_m3cancel0000',
    }
    row.update(extra)
    return ds.insert(CR_TABLE, row)


def _insert_approval_task(ds, cr_id, *, task_id='task-cr-1', status='waiting_approval',
                          type_='approval', with_decision_config=True, doc_ref=None):
    config = {}
    if with_decision_config:
        config['decision_actions'] = {
            'approve': 'change_request.approve',
            'reject': 'change_request.reject',
        }
    ds.insert('tasks', {
        'id': task_id,
        'title': '变更申请审批 #%s' % cr_id,
        'type': type_,
        'status': status,
        'priority': 'P1',
        'executor_type': 'human',
        'assign_policy': 'claim',
        'executor_config': json.dumps(config, ensure_ascii=False),
        'inputs': json.dumps({'change_request_id': cr_id}, ensure_ascii=False),
        'doc_ref': str(cr_id) if doc_ref is None else doc_ref,
        'created_at': '2026-10-29 00:00:00',
        'attempt': 1,
    })


def _terminal(ds, task_id, from_status, to_status, reason=''):
    """模拟引擎：在事务内经事件账唯一入口完成一次任务迁移。"""
    with ds.transaction():
        record_transition(
            ds, task_id=task_id, from_status=from_status,
            to_status=to_status, actor='system', reason=reason,
        )


class TestTerminalWritesBack:
    def test_t_a_failed_task_cancels_submitted_cr(self, ds):
        cr_id = _make_cr(ds)
        _insert_approval_task(ds, cr_id)

        _terminal(ds, 'task-cr-1', 'waiting_approval', 'failed', '审批任务超时')

        cr = ds.find_by_id(CR_TABLE, cr_id)
        assert cr['status'] == 'cancelled'
        assert cr['fail_reason'] == '审批任务超时'

    def test_t_a2_cancelled_task_uses_default_reason(self, ds):
        cr_id = _make_cr(ds)
        _insert_approval_task(ds, cr_id)

        _terminal(ds, 'task-cr-1', 'in_progress', 'cancelled')

        cr = ds.find_by_id(CR_TABLE, cr_id)
        assert cr['status'] == 'cancelled'
        assert cr['fail_reason'] == '审批任务 cancelled，变更申请自动取消'

    def test_t_b_normal_decision_is_noop(self, ds):
        for status in ('approved', 'rejected'):
            cr_id = _make_cr(ds, status=status)
            task_id = 'task-%s' % status
            _insert_approval_task(ds, cr_id, task_id=task_id)

            _terminal(ds, task_id, 'waiting_approval', 'failed', '不应回写')

            cr = ds.find_by_id(CR_TABLE, cr_id)
            assert cr['status'] == status
            assert cr['fail_reason'] is None

    def test_t_c_non_approval_task_does_not_touch_cr(self, ds):
        cr_id = _make_cr(ds)
        _insert_approval_task(ds, cr_id, task_id='task-story', type_='story')

        _terminal(ds, 'task-story', 'waiting_approval', 'failed', 'story failed')

        assert ds.find_by_id(CR_TABLE, cr_id)['status'] == 'submitted'


class TestReconcileDirection4:
    def test_t_d_submitted_without_task_is_reported(self, ds):
        cr_id = _make_cr(ds, submitted_at='2026-10-27 00:00:00')

        findings = reconcile_effects(ds, now=datetime(2026, 10, 29, 12, 0, 0))

        orphans = [f for f in findings
                   if f['kind'] == 'change_request_without_approval_task']
        assert len(orphans) == 1
        assert orphans[0]['doc_ref'] == str(cr_id)

    def test_t_e_active_task_suppresses_finding(self, ds):
        cr_id = _make_cr(ds, submitted_at='2026-10-27 00:00:00')
        _insert_approval_task(ds, cr_id, task_id='task-live')

        findings = reconcile_effects(ds, now=datetime(2026, 10, 29, 12, 0, 0))

        assert [f for f in findings
                if f['kind'] == 'change_request_without_approval_task'] == []
        # 成对 decision_actions 已配置 ⇒ 也不该出现方向 0 噪音
        assert [f for f in findings
                if f['kind'] == 'approval_without_decision_config'] == []
