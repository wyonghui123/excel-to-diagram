# -*- coding: utf-8 -*-
"""规则中心单条 CRUD 与 health 契约（M7-4 / R-A10）。

覆盖：
  1. GET /api/v2/rules/health 契约（items / total / finding_total / severity）；
  2. POST /api/v2/rules 按 rule_key 写草稿（configurable 来源才开放）；
  3. PUT /api/v2/rules/<rule_key> 改草稿（命中同一行，不新增）；
  4. DELETE /api/v2/rules/<rule_key> 删草稿，再次删除返回 404；
  5. 非 configurable 来源（doc_flow）返回 400；
  6. POST 缺 rule_key 返回 400。

同库隔离：写路径用临时 SQLite（DDL 从主库复制），不碰主库。

ALLOW_RAW_SQL: 本文件仅在 tmp_path 临时库上执行 DDL 复制与种子插入，
不读写主库，故对 raw-SQL 守卫做文件级声明放行。
"""

import os
import sqlite3
import sys

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

import meta.api.rule_center_api as rule_center_api
from meta.core.datasource import get_data_source
from meta.core.db_path import get_meta_db_path
from meta.services.rule_config_publish_service import RuleConfigPublishService

pytestmark = pytest.mark.integration

RULE_KEY = 'control_parameter:payment_term'

_TABLES = (
    'control_parameter_defs', 'control_parameter_values', 'line_type_assignments',
    'type_definitions', 'item_groups', 'audit_logs',
    'orgs', 'enum_types', 'number_sequences',
)


def _build_publish_service(tmp_path):
    """临时库：复制主库 DDL + 一条生效的控制参数取值。"""
    db_path = tmp_path / 'rule_console.db'
    main = sqlite3.connect(str(get_meta_db_path()))
    conn = sqlite3.connect(str(db_path))
    try:
        for name in _TABLES:
            row = main.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (name,)).fetchone()
            assert row, f'主库缺少表 {name}'
            conn.execute(row[0])
        conn.executescript(
            "INSERT INTO control_parameter_defs "
            "(id, code, name, value_type, default_value, status) "
            "VALUES (1, 'payment_term', '付款条件', 'string', 'net30', 'active');"
            "INSERT INTO control_parameter_values "
            "(id, control_parameter_id, org_id, document_type_id, line_type_id, "
            " item_group_id, specificity_rank, value, status, created_at) "
            "VALUES (10, 1, NULL, NULL, NULL, NULL, 100, 'net30', "
            "'active', '2026-01-01T00:00:00');"
        )
        conn.commit()
    finally:
        conn.close()
        main.close()
    ds = get_data_source('sqlite', database=str(db_path))
    return RuleConfigPublishService(data_source=ds)


def _install_service(monkeypatch, tmp_path):
    service = _build_publish_service(tmp_path)
    monkeypatch.setattr(
        rule_center_api, 'get_rule_config_publish_service', lambda: service)
    return service


class TestRuleCenterCrudEndpoints:
    @classmethod
    def setup_class(cls):
        from meta.tests.conftest import get_shared_app

        _, cls.client = get_shared_app()
        cls.client.get('/api/v1/auth/dev-login?username=admin')

    def test_health_contract(self):
        resp = self.client.get('/api/v2/rules/health')

        assert resp.status_code == 200
        body = resp.get_json()
        assert body['success'] is True
        data = body['data']
        for key in ('items', 'total', 'finding_total', 'severity'):
            assert key in data
        assert isinstance(data['items'], list)
        assert data['total'] == len(data['items'])
        assert data['severity'] in ('error', 'warning')
        for item in data['items']:
            assert {'check_key', 'label', 'severity', 'finding_count', 'sample'} \
                <= set(item)

    def test_create_draft_from_rule_key(self, tmp_path, monkeypatch):
        _install_service(monkeypatch, tmp_path)

        resp = self.client.post('/api/v2/rules', json={
            'rule_key': RULE_KEY,
            'value': 'net60',
        })

        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['rule_key'] == RULE_KEY
        assert data['target'] == 'control_parameter_value'
        assert data['status'] == 'draft'
        assert isinstance(data['id'], int)
        assert data['row']['value'] == 'net60'

    def test_update_draft_keeps_same_row(self, tmp_path, monkeypatch):
        _install_service(monkeypatch, tmp_path)

        created = self.client.post('/api/v2/rules', json={
            'rule_key': RULE_KEY,
            'value': 'net60',
        }).get_json()['data']

        resp = self.client.put(f'/api/v2/rules/{RULE_KEY}', json={
            'value': 'net90',
        })

        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['id'] == created['id']
        assert data['status'] == 'draft'
        assert data['row']['value'] == 'net90'

    def test_discard_draft_then_not_found(self, tmp_path, monkeypatch):
        _install_service(monkeypatch, tmp_path)

        self.client.post('/api/v2/rules', json={
            'rule_key': RULE_KEY,
            'value': 'net60',
        })

        resp = self.client.delete(f'/api/v2/rules/{RULE_KEY}')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['rule_key'] == RULE_KEY
        assert data['status'] == 'discarded'

        resp = self.client.delete(f'/api/v2/rules/{RULE_KEY}')
        assert resp.status_code == 404
        assert resp.get_json()['code'] == 'NOT_FOUND'

    def test_non_configurable_source_rejected(self, tmp_path, monkeypatch):
        _install_service(monkeypatch, tmp_path)

        resp = self.client.post('/api/v2/rules', json={
            'rule_key': 'doc_flow:SO',
            'value': 'x',
        })

        assert resp.status_code == 400
        body = resp.get_json()
        assert body['success'] is False
        assert body['code'] == 'RULE_CONFIG_INVALID'

    def test_create_without_rule_key_400(self):
        resp = self.client.post('/api/v2/rules', json={'value': 'x'})

        assert resp.status_code == 400
        body = resp.get_json()
        assert body['success'] is False
        assert 'rule_key' in body['message']