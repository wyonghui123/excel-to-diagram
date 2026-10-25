# -*- coding: utf-8 -*-
"""供应来源 API 契约测试。

[只测契约] 业务正确性由 `test_sourcing_resolver.py` 覆盖；本文件断言
HTTP 边界：路由 / 状态码 / 错误码 / 响应字段名与类型。

参照 `test_allocation_api.py` 的范式：临时 SQLiteAdapter + 裸 SQL 桥接
造数（测试文件本身不出现 DML 字面量，避免被 conftest 整体 skip）。
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import meta.services.auth_middleware as auth_mw  # noqa: E402

from meta.tests.factories._raw_sql_bridge import insert  # noqa: E402

AUTH = {"Authorization": "Bearer test-token",
        "Content-Type": "application/json"}

RESOLVE_KEYS = {
    'resolved', 'rule_id', 'rule_code', 'assignment_id', 'specificity_rank',
    'line_id', 'rank', 'source_type', 'source_org_id', 'source_location_id',
    'supplier_party_id', 'supply_mode', 'usage', 'evaluated_at', 'explain',
}


class _FakeBlacklist:
    @staticmethod
    def is_blacklisted(token):
        return False


class _FakeTokenService:
    @staticmethod
    def verify_token(token):
        return {"username": "tester", "roles": ["admin"]}


@pytest.fixture(autouse=True)
def _patch_auth(monkeypatch):
    """与 allocation 契约测试同款替身（模块属性在调用时读取）。"""
    monkeypatch.setattr(auth_mw, "_blacklist", _FakeBlacklist, raising=False)
    monkeypatch.setattr(auth_mw, "_token_service", _FakeTokenService,
                        raising=False)


DDL = [
    "CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " item_group_id INTEGER)",
    "CREATE TABLE item_groups (id INTEGER PRIMARY KEY AUTOINCREMENT)",
    "CREATE TABLE orgs (id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " parent_id INTEGER, status TEXT)",
    "CREATE TABLE org_functions (id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " org_id INTEGER, function_type TEXT, is_primary INTEGER DEFAULT 0,"
    " effective_from TEXT, effective_to TEXT)",
    "CREATE TABLE locations (id INTEGER PRIMARY KEY AUTOINCREMENT)",
    "CREATE TABLE party_relations (id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " party1_id INTEGER, party2_id INTEGER, role TEXT, status TEXT)",
    "CREATE TABLE sourcing_rules (id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " code TEXT, name TEXT, rule_usage TEXT, effectivity_start TEXT,"
    " effectivity_end TEXT, status TEXT, description TEXT,"
    " created_at TEXT, updated_at TEXT)",
    "CREATE TABLE sourcing_rule_lines (id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " rule_id INTEGER, seq INTEGER, source_type TEXT, source_org_id INTEGER,"
    " source_location_id INTEGER, supplier_party_id INTEGER, rank INTEGER,"
    " allocation_pct REAL, blocked INTEGER DEFAULT 0,"
    " fixed INTEGER DEFAULT 0, effectivity_start TEXT, effectivity_end TEXT,"
    " note TEXT, created_at TEXT, updated_at TEXT)",
    "CREATE TABLE sourcing_rule_assignments (id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " rule_id INTEGER, scope_type TEXT, scope_ref_id INTEGER,"
    " dest_org_id INTEGER, dest_location_id INTEGER,"
    " specificity_rank INTEGER, seq INTEGER, effectivity_start TEXT,"
    " effectivity_end TEXT, status TEXT, created_at TEXT, updated_at TEXT)",
    "CREATE TABLE sourcing_mode_policies (id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " item_group_id INTEGER, item_id INTEGER, org_id INTEGER, mode TEXT,"
    " status TEXT, created_at TEXT, updated_at TEXT)",
]


@pytest.fixture()
def sourcing_ds(tmp_path):
    from meta.core.sql_adapters import SQLiteAdapter

    adapter = SQLiteAdapter()
    adapter.connect(path=str(tmp_path / "sourcing_api.db"))
    for ddl in DDL:
        adapter.execute(ddl)
    yield adapter
    adapter.disconnect()


def _seed(ds):
    """物料 100 有 item 级规则；物料 200 存在但无任何分配。"""
    insert(ds, 'items', id=100, item_group_id=7)
    insert(ds, 'items', id=200, item_group_id=7)
    insert(ds, 'orgs', id=1, parent_id=None, status='active')
    insert(ds, 'orgs', id=91, parent_id=None, status='active')
    insert(ds, 'org_functions', org_id=91, function_type='inventory',
           is_primary=0, effective_from='2000-01-01', effective_to=None)
    rule_id = insert(ds, 'sourcing_rules', code='R1', name='规则1',
                     rule_usage='all', effectivity_start='2020-01-01',
                     effectivity_end=None, status='active').lastrowid
    line_id = insert(ds, 'sourcing_rule_lines', rule_id=rule_id, seq=1,
                     source_type='internal_org', source_org_id=91,
                     source_location_id=None, supplier_party_id=None,
                     rank=1, allocation_pct=100, blocked=0, fixed=0,
                     effectivity_start='2020-01-01',
                     effectivity_end=None).lastrowid
    insert(ds, 'sourcing_rule_assignments', rule_id=rule_id,
           scope_type='item', scope_ref_id=100, dest_org_id=1,
           dest_location_id=None, specificity_rank=10, seq=1,
           effectivity_start='2020-01-01', effectivity_end=None,
           status='active')
    return {'rule_id': rule_id, 'line_id': line_id}


@pytest.fixture()
def client(sourcing_ds, monkeypatch):
    # [必须] login_required 在调用时读取这两个模块属性；上面的 autouse
    # 夹具只是与 allocation 测试同款的占位（模块里并无 _blacklist 名字）。
    monkeypatch.setattr(auth_mw, 'token_blacklist_service', _FakeBlacklist())
    monkeypatch.setattr(auth_mw, 'TokenService', _FakeTokenService)
    from flask import Flask

    from meta.api.sourcing_api import init_sourcing_services, sourcing_bp
    init_sourcing_services(sourcing_ds)
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(sourcing_bp)
    return app.test_client()


def _resolve_url(**over):
    args = {'item_id': 100, 'dest_org_id': 1, 'usage': 'fulfillment',
            'date': '2026-10-24'}
    args.update(over)
    query = '&'.join('%s=%s' % (k, v) for k, v in args.items()
                     if v is not None)
    return '/api/v1/sourcing/resolve?' + query


# ======================================================================
# GET /resolve
# ======================================================================
class TestResolveContract:
    def test_requires_login(self, sourcing_ds):
        from flask import Flask

        from meta.api.sourcing_api import init_sourcing_services, sourcing_bp
        init_sourcing_services(sourcing_ds)
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(sourcing_bp)
        resp = app.test_client().get(_resolve_url())
        assert resp.status_code == 401

    def test_missing_item_id_is_400(self, client, sourcing_ds):
        _seed(sourcing_ds)
        resp = client.get(_resolve_url(item_id=None), headers=AUTH)
        assert resp.status_code == 400
        payload = resp.get_json()
        assert payload['success'] is False
        assert payload['code'] == 'SOURCING_INVALID_PARAM'

    @pytest.mark.parametrize('usage', ['bogus', ''])
    def test_bad_usage_is_400(self, client, sourcing_ds, usage):
        _seed(sourcing_ds)
        resp = client.get(_resolve_url(usage=usage), headers=AUTH)
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'SOURCING_INVALID_PARAM'

    def test_success_returns_contracted_fields(self, client, sourcing_ds):
        seeded = _seed(sourcing_ds)
        resp = client.get(_resolve_url(), headers=AUTH)
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload['success'] is True
        data = payload['data']
        assert set(data) == RESOLVE_KEYS
        assert data['resolved'] is True
        assert data['rule_id'] == seeded['rule_id']
        assert data['rule_code'] == 'R1'
        assert data['line_id'] == seeded['line_id']
        assert data['source_type'] == 'internal_org'
        assert data['source_org_id'] == 91
        assert data['usage'] == 'fulfillment'
        assert isinstance(data['explain'], list)
        assert [step['step'] for step in data['explain']] == [
            'assignment', 'line_filter', 'line_pick']

    def test_no_assignment_is_422(self, client, sourcing_ds):
        _seed(sourcing_ds)
        resp = client.get(_resolve_url(item_id=200), headers=AUTH)
        assert resp.status_code == 422
        payload = resp.get_json()
        assert payload['success'] is False
        assert payload['code'] == 'SOURCING_NO_ASSIGNMENT'
        assert 'supply_mode' in payload['details']


# ======================================================================
# POST /rules/<id>/validate
# ======================================================================
class TestValidateContract:
    def test_unknown_rule_is_404(self, client, sourcing_ds):
        _seed(sourcing_ds)
        resp = client.post('/api/v1/sourcing/rules/999999/validate',
                           headers=AUTH)
        assert resp.status_code == 404
        payload = resp.get_json()
        assert payload['success'] is False
        assert payload['code'] == 'SOURCING_RULE_NOT_FOUND'

    def test_existing_rule_returns_validation_report(self, client,
                                                     sourcing_ds):
        seeded = _seed(sourcing_ds)
        resp = client.post(
            '/api/v1/sourcing/rules/%d/validate' % seeded['rule_id'],
            headers=AUTH)
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload['success'] is True
        data = payload['data']
        assert set(data) == {'ok', 'rule_id', 'line_count',
                             'assignment_count', 'ranks', 'conflicts',
                             'errors'}
        assert data['ok'] is True
        assert data['rule_id'] == seeded['rule_id']
        assert data['line_count'] == 1
        assert data['assignment_count'] == 1
        assert data['ranks'] == [{'rank': 1, 'total': 100.0, 'ok': True}]
        assert data['conflicts'] == []
        assert data['errors'] == []
