# -*- coding: utf-8 -*-
"""配置域 API 契约测试 — price / match / solve

依据: docs/superpowers/specs/2026-10-25-configuration-and-structure-spec.p4.tasks.md §1 / §6
      meta/api/configuration_api.py

**只测契约，不重复测业务**：业务正确性由 `test_configuration_price.py` /
`test_configuration_match.py` / `test_item_structure_config.py` 覆盖。
本文件断言四件事：

  1. 路由与状态码（200 / 400 / 404 / 409 / 422 / 401）
  2. 响应字段**名字与类型**
  3. 非法请求在**入口**被拦下（不落到服务层）
  4. `solve → match` 的串接顺序与 `match=false` 的短路

另有一条真实服务接线用例：确认 `init_services` 构造三服务后 `/match`
能读库返回（防止蓝图注册与服务注入脱节）。
"""
import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import sqlite3
import sys
from contextlib import contextmanager

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import meta.api.configuration_api as config_api  # noqa: E402
import meta.services.auth_middleware as auth_mw  # noqa: E402

from meta.services.item_structure_config_service import (  # noqa: E402
    ItemStructureConfigError,
)
from meta.tests.factories._raw_sql_bridge import insert  # noqa: E402

AUTH = {"Authorization": "Bearer test-token", "Content-Type": "application/json"}


# ----------------------------------------------------------------------
# 认证替身（与 test_pricing_api 同口径）
# ----------------------------------------------------------------------
class _FakeBlacklist:
    @staticmethod
    def is_blacklisted(token):
        return False


class _FakeTokenService:
    @staticmethod
    def verify_token(token):
        return {"user_id": "1", "username": "admin", "token_version": 0,
                "permissions": ["*"]}


# ----------------------------------------------------------------------
# 服务替身：只验证"接口把什么传给了服务"
# ----------------------------------------------------------------------
class _FakePrice:
    def __init__(self):
        self.calls = []

    def price(self, configuration_id, price_source=None,
              pricing_context=None, resolved=None):
        self.calls.append({
            'configuration_id': configuration_id,
            'price_source': price_source,
            'pricing_context': pricing_context,
            'resolved': resolved,
        })
        return {
            'contract_version': '1.0',
            'configuration_id': configuration_id,
            'config_hash': 'H-AAA',
            'price_source': price_source or 'none',
            'currency_code': 'CNY',
            'lines': [{'component_no': 'root', 'unit_price': 10.0,
                       'net_amount': 10.0, 'pricing_trace': {}}],
            'total': 10.0,
            'cached': False,
        }


class _FakeMatch:
    def __init__(self):
        self.calls = []

    def match(self, configuration_id):
        self.calls.append(configuration_id)
        return {
            'configuration_id': configuration_id,
            'reused': False,
            'source_id': None,
            'revision': 1,
            'config_hash': 'H-AAA',
            'status': 'solved',
        }


class _FakeConfig:
    def __init__(self):
        self.calls = []

    def solve(self, structure_id, **kwargs):
        self.calls.append({'structure_id': structure_id, **kwargs})
        return {
            'configuration_id': 200,
            'config_hash': 'H-AAA',
            'model_item_id': 1,
            'model_code': 'MODEL-A',
            'structure_id': structure_id,
            'model_version': 'A',
            'status': 'solved',
            'status_out': 'solved',
            'revision': 1,
            'values': [],
            'components': [],
            'warnings': [],
        }


@pytest.fixture()
def fakes(monkeypatch):
    price, match, config = _FakePrice(), _FakeMatch(), _FakeConfig()
    monkeypatch.setattr(config_api, '_get_price_service', lambda: price)
    monkeypatch.setattr(config_api, '_get_match_service', lambda: match)
    monkeypatch.setattr(config_api, '_get_config_service', lambda: config)
    return {'price': price, 'match': match, 'config': config}


@pytest.fixture()
def client(fakes, monkeypatch):
    from flask import Flask
    monkeypatch.setattr(auth_mw, "token_blacklist_service", _FakeBlacklist())
    monkeypatch.setattr(auth_mw, "TokenService", _FakeTokenService)
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(config_api.configuration_bp)
    return app.test_client()


# ======================================================================
# 鉴权
# ======================================================================
class TestAuth:

    @pytest.mark.parametrize("path,body", [
        ("/api/v1/config/price", {"configuration_id": 1}),
        ("/api/v1/config/match", {"configuration_id": 1}),
        ("/api/v1/config/solve", {"structure_id": 10}),
    ])
    def test_requires_login(self, client, path, body):
        resp = client.post(path, json=body)
        assert resp.status_code == 401


# ======================================================================
# POST /api/v1/config/price
# ======================================================================
class TestPriceContract:

    def test_success_returns_contracted_fields(self, client, fakes):
        resp = client.post("/api/v1/config/price",
                           json={'configuration_id': 200}, headers=AUTH)
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload['success'] is True
        data = payload['data']
        for key in ('contract_version', 'configuration_id', 'config_hash',
                    'price_source', 'currency_code', 'lines', 'total', 'cached'):
            assert key in data, f'响应缺字段 {key}'
        assert isinstance(data['total'], float)
        assert isinstance(data['lines'], list)
        assert isinstance(data['cached'], bool)
        assert data['price_source'] == 'none'
        assert fakes['price'].calls[0]['configuration_id'] == 200

    def test_passes_source_and_context(self, client, fakes):
        context = {'pricing_procedure_code': 'PROC_STD', 'rate_table_id': 1}
        resp = client.post("/api/v1/config/price", json={
            'configuration_id': 200,
            'price_source': 'component_price',
            'pricing_context': context,
            'resolved': [{'component_key': 'L1', 'qty': 1}],
        }, headers=AUTH)
        assert resp.status_code == 200
        call = fakes['price'].calls[0]
        assert call['price_source'] == 'component_price'
        assert call['pricing_context'] == context
        assert call['resolved'] == [{'component_key': 'L1', 'qty': 1}]

    def test_missing_configuration_id_is_400(self, client, fakes):
        resp = client.post("/api/v1/config/price", json={}, headers=AUTH)
        assert resp.status_code == 400
        payload = resp.get_json()
        assert payload['code'] == 'INVALID_PARAM'
        assert 'configuration_id' in payload['message']
        assert fakes['price'].calls == []

    def test_bool_is_not_accepted_as_int(self, client, fakes):
        resp = client.post("/api/v1/config/price",
                           json={'configuration_id': True}, headers=AUTH)
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'INVALID_PARAM'
        assert fakes['price'].calls == []

    def test_pricing_context_must_be_object(self, client, fakes):
        resp = client.post("/api/v1/config/price", json={
            'configuration_id': 200, 'pricing_context': [1, 2],
        }, headers=AUTH)
        assert resp.status_code == 400
        assert 'pricing_context' in resp.get_json()['message']

    def test_resolved_must_be_list_or_object(self, client, fakes):
        resp = client.post("/api/v1/config/price", json={
            'configuration_id': 200, 'resolved': 'L1',
        }, headers=AUTH)
        assert resp.status_code == 400
        assert 'resolved' in resp.get_json()['message']

    @pytest.mark.parametrize("code,rule,status", [
        ('CONFIG_PRICE_MISSING', 'price_not_found', 422),
        ('CONFIG_INCOMPLETE', 'matrix_dimension_missing', 422),
        ('CONFIG_CONFLICT', 'pricing_mode_mismatch', 422),
        ('CONFIG_INVALID_VALUE', 'currency_mismatch', 400),
        ('CONFIG_VERSION_MISMATCH', 'configuration_status_not_priceable', 409),
        ('CONFIG_VERSION_MISMATCH', 'configuration_not_found', 404),
    ])
    def test_domain_error_maps_to_status(self, client, fakes, monkeypatch,
                                         code, rule, status):
        def boom(*args, **kwargs):
            raise ItemStructureConfigError(
                '失败', code=code, rule=rule, field_name='x',
                configuration_id=200)

        monkeypatch.setattr(fakes['price'], 'price', boom)
        resp = client.post("/api/v1/config/price",
                           json={'configuration_id': 200}, headers=AUTH)
        assert resp.status_code == status
        payload = resp.get_json()
        assert payload['success'] is False
        assert payload['code'] == code
        assert payload['details']['rule'] == rule
        assert payload['details']['configuration_id'] == 200


# ======================================================================
# POST /api/v1/config/match
# ======================================================================
class TestMatchContract:

    def test_success_returns_contracted_fields(self, client, fakes):
        resp = client.post("/api/v1/config/match",
                           json={'configuration_id': 200}, headers=AUTH)
        assert resp.status_code == 200
        data = resp.get_json()['data']
        for key in ('configuration_id', 'reused', 'source_id', 'revision',
                    'config_hash', 'status'):
            assert key in data, f'响应缺字段 {key}'
        assert isinstance(data['reused'], bool)
        assert fakes['match'].calls == [200]

    def test_missing_id_is_400(self, client, fakes):
        resp = client.post("/api/v1/config/match", json={}, headers=AUTH)
        assert resp.status_code == 400
        assert fakes['match'].calls == []


# ======================================================================
# POST /api/v1/config/solve
# ======================================================================
class TestSolveContract:

    def test_solve_chains_match(self, client, fakes):
        resp = client.post("/api/v1/config/solve",
                           json={'structure_id': 10, 'qty': 2}, headers=AUTH)
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['configuration']['configuration_id'] == 200
        assert data['match']['configuration_id'] == 200
        # 串接顺序：先 solve 再 match，且 match 拿的是 solve 产物 id
        assert fakes['config'].calls[0]['structure_id'] == 10
        assert fakes['match'].calls == [200]

    def test_match_false_skips_reuse(self, client, fakes):
        resp = client.post("/api/v1/config/solve",
                           json={'structure_id': 10, 'match': False},
                           headers=AUTH)
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['match'] is None
        assert fakes['match'].calls == []

    def test_defaults_are_passed(self, client, fakes):
        client.post("/api/v1/config/solve", json={'structure_id': 10},
                    headers=AUTH)
        call = fakes['config'].calls[0]
        assert call['qty'] == 1.0
        assert call['max_depth'] == 20
        assert call['record_invalid'] is False
        assert call['selections'] is None
        assert call['attribute_values'] is None

    def test_missing_structure_id_is_400(self, client, fakes):
        resp = client.post("/api/v1/config/solve", json={}, headers=AUTH)
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'INVALID_PARAM'
        assert fakes['config'].calls == []

    def test_selections_must_be_object_or_array(self, client, fakes):
        resp = client.post("/api/v1/config/solve", json={
            'structure_id': 10, 'selections': 'L1',
        }, headers=AUTH)
        assert resp.status_code == 400
        assert 'selections' in resp.get_json()['message']

    def test_max_depth_must_be_positive(self, client, fakes):
        resp = client.post("/api/v1/config/solve", json={
            'structure_id': 10, 'max_depth': 0,
        }, headers=AUTH)
        assert resp.status_code == 400
        assert 'max_depth' in resp.get_json()['message']

    def test_record_invalid_must_be_boolean(self, client, fakes):
        resp = client.post("/api/v1/config/solve", json={
            'structure_id': 10, 'record_invalid': 'yes',
        }, headers=AUTH)
        assert resp.status_code == 400
        assert 'record_invalid' in resp.get_json()['message']


# ======================================================================
# 真实服务接线（防蓝图注册与服务注入脱节）
# ======================================================================
class _SqliteDS:
    """最小数据源：query / insert / update / transaction。"""

    def __init__(self, conn):
        self.conn = conn

    def query(self, sql, params=None):
        cur = self.conn.execute(sql, params or [])
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def execute(self, sql, params=None):
        return self.conn.execute(sql, params or [])

    def insert(self, table, data):
        columns = list(data.keys())
        sql = (f"INSERT INTO {table} ({', '.join(columns)}) "
               f"VALUES ({', '.join('?' for _ in columns)})")
        cur = self.conn.execute(sql, [data[col] for col in columns])
        return cur.lastrowid

    def update(self, table, row_id, data):
        assignments = ', '.join(f'{key} = ?' for key in data)
        self.conn.execute(
            f"UPDATE {table} SET {assignments} WHERE id = ?",
            [*data.values(), row_id])

    @contextmanager
    def transaction(self):
        try:
            yield self
        except Exception:
            self.conn.rollback()
            raise
        else:
            self.conn.commit()


@pytest.fixture()
def wired_client(monkeypatch):
    """真实 `init_services` + 最小配置三表：验证 /match 读库路径。"""
    conn = sqlite3.connect(':memory:')
    conn.executescript(
        """
        CREATE TABLE items (id INTEGER PRIMARY KEY, code TEXT, name TEXT,
            structure_role TEXT, item_type TEXT, status TEXT, base_uom INTEGER,
            config_match_policy TEXT, config_materialize_policy TEXT);
        CREATE TABLE item_structures (id INTEGER PRIMARY KEY, item_id INTEGER,
            usage TEXT, alternative_no INTEGER, revision TEXT, status TEXT,
            base_qty REAL, base_uom_code TEXT);
        CREATE TABLE configurations (id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_item_id INTEGER, structure_id INTEGER, status TEXT,
            config_hash TEXT, revision INTEGER, reused_from_id INTEGER,
            match_policy_used TEXT, source_level TEXT, context_json TEXT,
            validation_result_json TEXT, solved_at TEXT, frozen_at TEXT,
            variant_item_id INTEGER);
        CREATE TABLE configuration_values (id INTEGER PRIMARY KEY AUTOINCREMENT,
            configuration_id INTEGER, attribute_code TEXT, seq INTEGER,
            value_text TEXT, value_number REAL, value_boolean INTEGER,
            source TEXT, source_rule_id INTEGER);
        CREATE TABLE configuration_components (id INTEGER PRIMARY KEY AUTOINCREMENT,
            configuration_id INTEGER, component_key TEXT, structure_line_id INTEGER,
            component_item_id INTEGER, qty REAL, uom_code TEXT,
            parent_component_key TEXT, selection_source TEXT, source_rule_id INTEGER,
            substitute_for_key TEXT, child_configuration_id INTEGER, seq INTEGER);
        """
    )
    ds = _SqliteDS(conn)
    now = '2026-10-25 00:00:00'
    insert(ds, 'items', id=1, code='MODEL-A', name='模型A',
           structure_role='model', item_type='goods', status='active',
           base_uom=1, config_match_policy='one_time_standard',
           config_materialize_policy='off')
    insert(ds, 'item_structures', id=10, item_id=1, usage='production',
           alternative_no=1, revision='A', status='active', base_qty=1,
           base_uom_code='EA')
    insert(ds, 'configurations', id=200, model_item_id=1, structure_id=10,
           status='solved', config_hash='H-AAA', revision=1,
           reused_from_id=None, match_policy_used='one_time_standard',
           source_level='L2', context_json=None, validation_result_json=None,
           solved_at=now, frozen_at=None, variant_item_id=None)

    config_api.init_services(ds)
    monkeypatch.setattr(auth_mw, "token_blacklist_service", _FakeBlacklist())
    monkeypatch.setattr(auth_mw, "TokenService", _FakeTokenService)
    from flask import Flask
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(config_api.configuration_bp)
    yield app.test_client()
    conn.close()
    config_api._price_service = None
    config_api._match_service = None
    config_api._config_service = None


class TestWiring:

    def test_match_reads_real_store(self, wired_client):
        resp = wired_client.post("/api/v1/config/match",
                                 json={'configuration_id': 200}, headers=AUTH)
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['configuration_id'] == 200
        assert data['reused'] is False
        assert data['status'] == 'solved'

    def test_missing_instance_is_404(self, wired_client):
        resp = wired_client.post("/api/v1/config/match",
                                 json={'configuration_id': 999}, headers=AUTH)
        assert resp.status_code == 404
        assert resp.get_json()['code'] == 'CONFIG_VERSION_MISMATCH'
