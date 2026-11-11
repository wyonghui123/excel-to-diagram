# -*- coding: utf-8 -*-
"""[E3 2026-11-11] BO Action 治理（写审计 + 组织范围）回归

覆盖 spec-bo-metadata-single-source-2026-11-11 §16.4 E3 验收口径：
  1. 写类 action 成功调用 → `audit_logs` 恰新增 1 行（status=ok）
  2. 同 `(trace_id, action_id)` 重复调用 → 不重复落审计（去重）
  3. strict 下越权 org → `code=ORG_SCOPE_DENIED`，审计 `status=denied`，handler 未执行
  4. warn 下越权 org → 放行（业务调用），审计 `status=ok`
  5. `governance='none'` 只读 action → 不产生审计行
  6. 真实注册表契约零违规（warn / strict 双口径）
"""
import sqlite3

# 审计落库点单测需要最小 audit_logs 库，按 test.py 约定显式放行 raw SQL
import os
os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

from meta.core import bo_action_contract
from meta.core.bo_action_contract import report_registry_contracts
from meta.core.bo_action_registry import BoActionRegistry
from meta.services.org_scope_service import OrgScopeService
from meta.tests.shared.db_schema import create_audit_logs


# ─────────────────────────────────────────────────────────────────────────────
# 夹具
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def audit_ds():
    """最小 audit_logs 库 + DataSource 替身（仅覆盖审计写入所需方法）。"""
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    create_audit_logs(conn)

    class MockDS:
        in_transaction = False

        def execute(self, sql, params=None):
            cur = conn.cursor()
            cur.execute(sql, params or [])
            return cur

        def insert(self, table, record):
            cols = list(record.keys())
            cur = conn.cursor()
            cur.execute(
                f"INSERT INTO {table} ({', '.join(cols)}) "
                f"VALUES ({', '.join(['?'] * len(cols))})",
                [record[c] for c in cols],
            )
            conn.commit()
            return cur.lastrowid

        def find(self, table, filters=None, order_by=None):
            cur = conn.cursor()
            try:
                cur.execute(f"SELECT * FROM {table}")
            except sqlite3.OperationalError:
                return []
            names = [d[0] for d in cur.description]
            return [dict(zip(names, row)) for row in cur.fetchall()]

        def commit(self):
            conn.commit()

    yield MockDS()
    conn.close()


def _audit_rows(ds):
    return ds.find('audit_logs')


def _register_write_action(registry, action_id='demo.write', governance='audit',
                           org_scope=None, calls=None):
    payload = {'success': True, 'data': {'ok': True}, 'message': 'ok'}

    def handler(params, context):
        if calls is not None:
            calls.append(dict(params or {}))
        return dict(payload)

    registry.register(
        action_id,
        handler,
        governance=governance,
        org_scope=org_scope,
        description='治理测试 action',
        object_type='demo',
        category='business',
        input_schema={
            'type': 'object',
            'properties': {'demo_id': {'type': 'integer'},
                           'org_id': {'type': 'integer'}},
        },
        requires_auth=True,
    )
    return handler


# ─────────────────────────────────────────────────────────────────────────────
# 审计落库
# ─────────────────────────────────────────────────────────────────────────────

class TestActionAudit:
    def test_write_action_logs_once(self, audit_ds):
        """写类 action 成功调用 → audit_logs 恰 1 行，status=ok。"""
        registry = BoActionRegistry()
        _register_write_action(registry)

        result = registry.call('demo.write', {'demo_id': 42},
                               {'user_id': 7, 'data_source': audit_ds,
                                'trace_id': 'trace-ok'})

        assert result['success'] is True
        rows = _audit_rows(audit_ds)
        assert len(rows) == 1
        assert rows[0]['action'] == 'demo.write'
        assert rows[0]['object_id'] == 42
        assert rows[0]['status'] == 'ok'
        assert rows[0]['trace_id'] == 'trace-ok'

    def test_duplicate_trace_not_audited_twice(self, audit_ds):
        """同 (trace_id, action_id) 重试 → 只落一行。"""
        registry = BoActionRegistry()
        _register_write_action(registry)
        ctx = {'user_id': 7, 'data_source': audit_ds, 'trace_id': 'trace-dup'}

        registry.call('demo.write', {'demo_id': 1}, ctx)
        registry.call('demo.write', {'demo_id': 1}, ctx)

        assert len(_audit_rows(audit_ds)) == 1

    def test_none_governance_no_audit(self, audit_ds):
        """governance='none' 只读 action → 不产生审计行。"""
        registry = BoActionRegistry()
        _register_write_action(registry, action_id='demo.read', governance='none')

        result = registry.call('demo.read', {'demo_id': 1},
                               {'user_id': 7, 'data_source': audit_ds,
                                'trace_id': 'trace-read'})

        assert result['success'] is True
        assert _audit_rows(audit_ds) == []


# ─────────────────────────────────────────────────────────────────────────────
# 组织范围（audit_scope）
# ─────────────────────────────────────────────────────────────────────────────

class TestOrgScope:
    def test_strict_denied(self, audit_ds, monkeypatch):
        """strict：越权 org → ORG_SCOPE_DENIED + 审计 denied + handler 未执行。"""
        monkeypatch.setattr('meta.core.bo_action_registry._governance_enforce',
                            lambda: True)
        monkeypatch.setattr(OrgScopeService, 'visible_org_ids',
                            lambda self, user_id, is_admin=False: {1})

        registry = BoActionRegistry()
        calls = []
        _register_write_action(registry, action_id='demo.scoped',
                               governance='audit_scope',
                               org_scope={'param_field': 'org_id'},
                               calls=calls)

        result = registry.call('demo.scoped', {'org_id': 999},
                               {'user_id': 7, 'data_source': audit_ds,
                                'trace_id': 'trace-denied'})

        assert result['success'] is False
        assert result['code'] == 'ORG_SCOPE_DENIED'
        assert calls == []
        rows = _audit_rows(audit_ds)
        assert len(rows) == 1
        assert rows[0]['status'] == 'denied'

    def test_warn_allows(self, audit_ds, monkeypatch):
        """warn：越权 org 放行（灰度），审计 status=ok。"""
        monkeypatch.setattr('meta.core.bo_action_registry._governance_enforce',
                            lambda: False)
        monkeypatch.setattr(OrgScopeService, 'visible_org_ids',
                            lambda self, user_id, is_admin=False: {1})

        registry = BoActionRegistry()
        _register_write_action(registry, action_id='demo.scoped',
                               governance='audit_scope',
                               org_scope={'param_field': 'org_id'})

        result = registry.call('demo.scoped', {'org_id': 999},
                               {'user_id': 7, 'data_source': audit_ds,
                                'trace_id': 'trace-warn'})

        assert result['success'] is True
        rows = _audit_rows(audit_ds)
        assert len(rows) == 1
        assert rows[0]['status'] == 'ok'


# ─────────────────────────────────────────────────────────────────────────────
# 真实注册表契约
# ─────────────────────────────────────────────────────────────────────────────

class TestRegistryContract:
    def test_real_registry_zero_violations(self, monkeypatch):
        """全部注册项（含 5 个 audit_scope）契约零违规；strict 下同样零违规。"""
        from meta.services.bo_action_registrations import register_all_bo_actions

        registry = BoActionRegistry()
        register_all_bo_actions(registry)

        assert report_registry_contracts(registry, level='error') == 0

        monkeypatch.setattr(bo_action_contract, '_GOVERNANCE_MODE', 'strict')
        assert report_registry_contracts(registry, level='error') == 0