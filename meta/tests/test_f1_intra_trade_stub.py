# -*- coding: utf-8 -*-
"""F1 §9.2 桩验收：intra_trade 受控放行入口位（PartyScopeService）

依据: docs/superpowers/specs/2026-10-04-f1-governance-domain-design.md §6 / §7.2-6 / §9.2

覆盖（步 2 只验「接口位 + 门禁 + 审计」，不验解析体）：
1. 缺功能码 → IntraTradeGateError（不放行、不审计）
2. 有功能码但单据上下文组织域不可见 → IntraTradeGateError（不放行、不审计）
3. 双门禁通过 → 到达桩（NotImplementedError）+ 审计收集器被调用
4. 公开入口签名的 keyword-only 约束（user_id / doc_context）

说明: 通过覆写三个私有钩子注入行为，`data_source` 传 None，
     全程无裸 SQL（避免 conftest raw-SQL 守卫误 skip）。
"""
import os
import sys

import pytest

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _PROJECT_ROOT)

from meta.services.party_scope_service import (
    IntraTradeGateError,
    PartyScopeService,
)

pytestmark = pytest.mark.unit


class _StubScopeService(PartyScopeService):
    """行为注入桩：把三道门禁/审计替换为可控结果。"""

    def __init__(self, *, has_key=True, context_visible=True):
        super().__init__(data_source=None)
        self._has_key = has_key
        self._context_visible_result = context_visible
        self.audited = []

    def _has_function_key(self, user_id):
        return self._has_key

    def _context_visible(self, user_id, target_org_id):
        return self._context_visible_result

    def _audit(self, party_id, user_id, doc_context):
        self.audited.append((party_id, user_id, doc_context))


class TestIntraTradeGate:
    def test_missing_function_key_rejected_without_audit(self):
        """门禁一未过：缺功能码 → 拒放行，且不写审计。"""
        svc = _StubScopeService(has_key=False)
        with pytest.raises(IntraTradeGateError):
            svc.resolve_party_for_intra_trade(
                101, user_id=7, doc_context={'org_id': 2})
        assert svc.audited == []

    def test_invisible_doc_context_rejected_without_audit(self):
        """门禁二未过：有功能码但单据组织域不可见 → 拒放行，且不写审计。"""
        svc = _StubScopeService(has_key=True, context_visible=False)
        with pytest.raises(IntraTradeGateError):
            svc.resolve_party_for_intra_trade(
                101, user_id=7, doc_context={'org_id': 2})
        assert svc.audited == []

    def test_missing_org_id_rejected(self):
        """doc_context 缺 org_id → 门禁二 fail-closed。"""
        svc = _StubScopeService(has_key=True, context_visible=False)
        with pytest.raises(IntraTradeGateError):
            svc.resolve_party_for_intra_trade(101, user_id=7, doc_context={})
        assert svc.audited == []

    def test_double_gate_pass_reaches_stub_and_audits(self):
        """双门禁通过 → 到达桩（NotImplementedError），审计留痕已发生。"""
        svc = _StubScopeService(has_key=True, context_visible=True)
        with pytest.raises(NotImplementedError):
            svc.resolve_party_for_intra_trade(
                101, user_id=7, doc_context={'org_id': 2})
        assert svc.audited == [(101, 7, {'org_id': 2})]


class TestIntraTradeSignature:
    def test_user_id_and_doc_context_are_keyword_only(self):
        """公开入口签名：user_id / doc_context 必须 keyword-only（防位置误传）。"""
        import inspect

        sig = inspect.signature(
            PartyScopeService.resolve_party_for_intra_trade)
        assert sig.parameters['user_id'].kind is inspect.Parameter.KEYWORD_ONLY
        assert sig.parameters['doc_context'].kind is inspect.Parameter.KEYWORD_ONLY
        assert sig.parameters['party_id'].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD

    def test_function_keys_placeholder_registered(self):
        """门禁一占位码常量存在（F2 校准锚点，防止静默改名）。"""
        assert PartyScopeService.FUNCTION_KEYS == (
            'internal_trade:read', 'internal_invoice:read')
        assert issubclass(IntraTradeGateError, PermissionError)