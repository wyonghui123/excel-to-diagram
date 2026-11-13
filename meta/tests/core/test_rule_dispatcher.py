# -*- coding: utf-8 -*-
"""规则处置动作分发器测试 —— spec-rule-model §12.4 / M7-3。

覆盖:
  · 7 个处置动作各自的分派结果（block / warn_ack / hold / route / notify /
    default / lock）；
  · 未知动作抛 DispatchError（封闭词表）；
  · 命中但未声明 disposition：有 fallback_action 用之，否则记 no_action_declared；
  · hold 幂等：apply 返回 False 时归入 skipped(already_held)；
  · 未命中 + release_unmatched：释放旧挂起（action=release），无 active 行则 skipped；
  · 注入通道缺失（notify / default）时不臆造，记 skipped。
"""

import pytest

pytestmark = pytest.mark.unit

from meta.core.exceptions import ValidationFailedError
from meta.core.rule_action_matrix import (
    BLOCK, DEFAULT, HOLD, LOCK, NOTIFY, ROUTE, WARN_ACK,
)
from meta.core.rule_dispatcher import (
    NO_ACTION, RELEASE, DispatchError, dispatch,
)


class _Decision:
    """约束判定替身：只暴露分发器读取的字段。"""

    def __init__(self, action='', matched=True, severity='warning',
                 rule_key='bo_yaml:bo.R1', explain_rows=None):
        self.action = action
        self.matched = matched
        self.severity = severity
        self.rule_key = rule_key
        self._explain = explain_rows or []

    def explain(self):
        return list(self._explain)


class _Holds:
    """RuleHoldService 替身：记录调用并按预设返回。"""

    def __init__(self, apply_result=True, release_result=1):
        self.apply_result = apply_result
        self.release_result = release_result
        self.applied = []
        self.released = []

    def apply(self, object_type, record_id, rule_key, code=None, reason=None,
              applied_by=None):
        self.applied.append((object_type, record_id, rule_key, code, reason,
                             applied_by))
        return self.apply_result

    def release(self, object_type, record_id=None, rule_key=None,
                released_by=None):
        self.released.append((object_type, record_id, rule_key, released_by))
        return self.release_result


# ---------------- block ----------------

def test_block_raises_validation_error_with_rule_key():
    decision = _Decision(action=BLOCK, severity='error')
    with pytest.raises(ValidationFailedError) as exc:
        dispatch(decision, {'rule_key': 'bo_yaml:bo.R1'})
    details = exc.value.details[0]
    assert details['action'] == BLOCK
    assert details['rule_key'] == 'bo_yaml:bo.R1'
    assert details['severity'] == 'error'


def test_block_uses_injected_message():
    with pytest.raises(ValidationFailedError, match='库存不足'):
        dispatch(_Decision(action=BLOCK), {'message': '库存不足'})


# ---------------- warn_ack ----------------

def test_warn_ack_returns_ack_entry():
    result = dispatch(_Decision(action=WARN_ACK),
                      {'rule_key': 'k1', 'message': '请确认'})
    assert result.action == WARN_ACK
    assert result.matched is True
    entry = result.applied[0]
    assert entry['requires_ack'] is True
    assert entry['rule_key'] == 'k1'
    assert entry['message'] == '请确认'


# ---------------- hold ----------------

def test_hold_applies_and_reports_entry():
    holds = _Holds(apply_result=True)
    result = dispatch(_Decision(action=HOLD), {
        'holds': holds, 'object_type': 'inventory_count_line',
        'record_id': 7, 'rule_key': 'r1', 'code': 'C1',
        'reason': '盘亏', 'applied_by': 'alice'})
    entry = result.applied[0]
    assert entry['action'] == HOLD
    assert entry['record_id'] == 7
    assert entry['code'] == 'C1'
    assert result.held == result.applied
    assert holds.applied == [
        ('inventory_count_line', 7, 'r1', 'C1', '盘亏', 'alice')]


def test_hold_idempotent_reports_already_held():
    result = dispatch(_Decision(action=HOLD), {
        'holds': _Holds(apply_result=False), 'object_type': 'inventory_count_line',
        'record_id': 7, 'rule_key': 'r1'})
    assert result.applied == []
    assert result.skipped[0]['reason'] == 'already_held'


def test_hold_without_record_id_raises():
    with pytest.raises(DispatchError, match='record_id'):
        dispatch(_Decision(action=HOLD), {'holds': _Holds()})


# ---------------- route ----------------

def test_route_creates_task_via_approval_service(monkeypatch):
    from meta.services import approval_task_service as module

    calls = []

    def fake_create(self, object_type, record_id, *, policy_snapshot=None,
                    actor=''):
        calls.append((object_type, record_id, actor))
        return 'task-1'

    monkeypatch.setattr(module.ApprovalTaskService, 'create_task',
                        fake_create)
    result = dispatch(_Decision(action=ROUTE), {
        'data_source': object(), 'object_type': 'purchase_order',
        'record_id': 9, 'applied_by': 'bob'})
    assert result.applied[0]['task_id'] == 'task-1'
    assert calls == [('purchase_order', 9, 'bob')]


def test_route_without_task_reports_skipped(monkeypatch):
    from meta.services import approval_task_service as module

    monkeypatch.setattr(module.ApprovalTaskService, 'create_task',
                        lambda self, *a, **kw: None)
    result = dispatch(_Decision(action=ROUTE), {
        'data_source': object(), 'object_type': 'purchase_order', 'record_id': 9})
    assert result.applied == []
    assert result.skipped[0]['reason'] == 'route_not_applicable'


# ---------------- notify ----------------

def test_notify_calls_injected_channel():
    sent = []
    result = dispatch(_Decision(action=NOTIFY),
                      {'notify': sent.append, 'rule_key': 'k1',
                       'object_type': 'bo', 'record_id': 3, 'message': 'hi'})
    assert result.applied[0]['action'] == NOTIFY
    assert sent[0]['rule_key'] == 'k1'
    assert sent[0]['message'] == 'hi'


def test_notify_without_channel_is_skipped():
    result = dispatch(_Decision(action=NOTIFY), {'rule_key': 'k1'})
    assert result.applied == []
    assert result.skipped[0]['reason'] == 'no_notify_channel'


# ---------------- default ----------------

def test_default_writes_fields():
    written = {}
    result = dispatch(_Decision(action=DEFAULT),
                      {'fields': {'tolerance': 0.05},
                       'write_fields': written.update})
    assert written == {'tolerance': 0.05}
    assert result.applied[0]['fields'] == {'tolerance': 0.05}


def test_default_without_fields_is_skipped():
    result = dispatch(_Decision(action=DEFAULT), {})
    assert result.applied == []
    assert result.skipped[0]['reason'] == 'no_default_fields'


# ---------------- lock ----------------

def test_lock_reports_locked_fields():
    result = dispatch(_Decision(action=LOCK), {'fields': ['price', 'qty']})
    entry = result.applied[0]
    assert entry['locked'] is True
    assert entry['fields'] == ['price', 'qty']


# ---------------- 未命中 / release 分支 ----------------

def test_not_matched_does_not_touch_holds():
    holds = _Holds()
    result = dispatch(_Decision(action=HOLD, matched=False), {'holds': holds})
    assert result.matched is False
    assert result.skipped[0]['reason'] == 'not_matched'
    assert holds.applied == [] and holds.released == []


def test_not_matched_releases_stale_hold_when_requested():
    holds = _Holds(release_result=2)
    result = dispatch(_Decision(action=HOLD, matched=False), {
        'holds': holds, 'object_type': 'inventory_count_line', 'record_id': 5,
        'release_unmatched': True})
    assert result.action == RELEASE
    assert result.applied[0]['released'] == 2
    assert result.released == result.applied


def test_not_matched_release_without_active_hold_is_skipped():
    result = dispatch(_Decision(action=HOLD, matched=False), {
        'holds': _Holds(release_result=0), 'object_type': 'inventory_count_line',
        'record_id': 5, 'release_unmatched': True})
    assert result.applied == []
    assert result.skipped[0]['reason'] == 'no_active_hold'


# ---------------- 空动作 / 未知动作 ----------------

def test_matched_without_action_is_skipped():
    result = dispatch(_Decision(action=''), {'rule_key': 'k1'})
    assert result.applied == []
    assert result.skipped[0]['reason'] == NO_ACTION


def test_matched_without_action_uses_fallback():
    written = {}
    result = dispatch(_Decision(action=''), {
        'fallback_action': DEFAULT, 'fields': {'x': 1},
        'write_fields': written.update})
    assert result.action == DEFAULT
    assert written == {'x': 1}


def test_unknown_action_raises():
    with pytest.raises(DispatchError, match='未知处置动作'):
        dispatch(_Decision(action='explode'), {'rule_key': 'k1'})


def test_rule_key_prefers_context_over_decision():
    result = dispatch(_Decision(action=LOCK), {'rule_key': 'ctx-key'})
    assert result.applied[0]['rule_key'] == 'ctx-key'