# -*- coding: utf-8 -*-
"""规则挂起（holds）API 契约测试 —— spec-rule-model §12.4 M7-3。

覆盖：
  1. 路由注册 + 未登录 401；
  2. GET /api/holds 列表（ok_list 契约、record_id 字符串归一为 int、rule_key 透传）；
  3. GET /api/holds 缺 object_type → 400 OBJECT_TYPE_REQUIRED；
  4. POST /api/holds/<id>/release：404 HOLD_NOT_FOUND / 409 HOLD_NOT_ACTIVE / 200；
  5. 释放人缺省取当前登录用户名。

认证说明：`require_permission` 内部已套 `login_required`，视图函数被两层包装；
本文件与 test_doc_flow_api.py 一致，业务断言在 test_request_context 内直调原始
视图函数（双层 __wrapped__），不绕真实权限链路。
"""

import pytest
from flask import Flask, g

import meta.api.rule_hold_api as hold_api
from meta.api.rule_hold_api import rule_hold_bp


class _FakeHoldService:
    """内存替身：不连库，只记录调用与返回预置行。"""

    def __init__(self, rows=None, release_result=1):
        self.rows = list(rows or [])
        self.release_result = release_result
        self.calls = []

    def active_holds(self, object_type, record_id, rule_key=None):
        self.calls.append(('active_holds', object_type, record_id, rule_key))
        return [dict(row) for row in self.rows
                if row['object_type'] == object_type
                and (record_id is None or row['record_id'] == record_id)
                and (rule_key is None or row['rule_key'] == rule_key)]

    def get(self, hold_id):
        for row in self.rows:
            if str(row['id']) == str(hold_id):
                return dict(row)
        return None

    def release(self, object_type, record_id=None, rule_key=None,
                released_by=None):
        self.calls.append(
            ('release', object_type, record_id, rule_key, released_by))
        return self.release_result


def _hold(hold_id=1, object_type='inventory_count_line', record_id=10,
          rule_key='bo_yaml:inventory_count.line_tolerance'):
    return {
        'id': hold_id, 'object_type': object_type, 'record_id': record_id,
        'rule_key': rule_key, 'code': 'OVER_TOLERANCE',
        'reason': '偏差超限', 'applied_by': 'tester',
        'applied_at': '2026-11-12 10:00:00',
    }


def _payload(result):
    """视图直调返回 Response 或 (Response, status)，统一成 (body, status)。"""
    if isinstance(result, tuple):
        return result[0].get_json(), result[1]
    return result.get_json(), 200


@pytest.fixture()
def api_app(monkeypatch):
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(rule_hold_bp)
    service = _FakeHoldService(rows=[_hold()])
    monkeypatch.setattr(hold_api, 'get_rule_hold_service', lambda: service)
    app.hold_service = service
    return app


def test_routes_registered(api_app):
    rules = {r.rule for r in api_app.url_map.iter_rules()}
    assert '/api/holds' in rules
    assert '/api/holds/<hold_id>/release' in rules


def test_list_requires_login(api_app):
    resp = api_app.test_client().get('/api/holds?object_type=inventory_count_line')
    assert resp.status_code == 401
    assert resp.get_json()['code'] == 'unauthorized'


def test_list_returns_ok_list(api_app):
    with api_app.test_request_context(
            '/api/holds?object_type=inventory_count_line&record_id=10'):
        body, status = _payload(hold_api.list_holds.__wrapped__.__wrapped__())

    assert status == 200
    assert body['success'] is True
    assert body['data']['total'] == 1
    assert body['data']['items'][0]['rule_key'] == _hold()['rule_key']


def test_list_coerces_record_id_to_int(api_app):
    with api_app.test_request_context(
            '/api/holds?object_type=inventory_count_line&record_id=10'):
        hold_api.list_holds.__wrapped__.__wrapped__()

    _, object_type, record_id, _ = api_app.hold_service.calls[0]
    assert object_type == 'inventory_count_line'
    assert record_id == 10
    assert isinstance(record_id, int)


def test_list_passes_rule_key(api_app):
    with api_app.test_request_context(
            '/api/holds?object_type=inventory_count_line&rule_key=bo_yaml:r1'):
        hold_api.list_holds.__wrapped__.__wrapped__()

    assert api_app.hold_service.calls[0][3] == 'bo_yaml:r1'


def test_list_requires_object_type(api_app):
    with api_app.test_request_context('/api/holds'):
        body, status = _payload(hold_api.list_holds.__wrapped__.__wrapped__())

    assert status == 400
    assert body['success'] is False
    assert body['code'] == 'OBJECT_TYPE_REQUIRED'


def test_release_unknown_hold_returns_404(api_app):
    with api_app.test_request_context('/api/holds/999/release', method='POST',
                                      json={}):
        body, status = _payload(
            hold_api.release_hold.__wrapped__.__wrapped__('999'))

    assert status == 404
    assert body['error_code'] == 'HOLD_NOT_FOUND'
    assert body['details']['hold_id'] == '999'


def test_release_already_released_returns_409(api_app):
    api_app.hold_service.release_result = 0
    with api_app.test_request_context('/api/holds/1/release', method='POST',
                                      json={}):
        body, status = _payload(
            hold_api.release_hold.__wrapped__.__wrapped__('1'))

    assert status == 409
    assert body['error_code'] == 'HOLD_NOT_ACTIVE'


def test_release_uses_payload_released_by(api_app):
    with api_app.test_request_context('/api/holds/1/release', method='POST',
                                      json={'released_by': 'pm'}):
        body, status = _payload(
            hold_api.release_hold.__wrapped__.__wrapped__('1'))

    assert status == 200
    assert body['data']['released'] == 1
    assert body['data']['released_by'] == 'pm'
    assert api_app.hold_service.calls[-1][-1] == 'pm'


def test_release_defaults_to_current_username(api_app):
    with api_app.test_request_context('/api/holds/1/release', method='POST',
                                      json={}):
        g.current_user = {'username': 'admin', 'user_id': 1}
        body, status = _payload(
            hold_api.release_hold.__wrapped__.__wrapped__('1'))

    assert status == 200
    assert body['data']['released_by'] == 'admin'
    _, object_type, record_id, _, _ = api_app.hold_service.calls[-1]
    assert object_type == 'inventory_count_line'
    assert record_id == 10