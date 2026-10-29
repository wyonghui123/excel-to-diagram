# -*- coding: utf-8 -*-
"""文档版本 API 契约测试 — IF-001 / IF-002

依据: docs/superpowers/specs/*文档版本* M2 spec §8
      meta/api/bo_api.py  v2_list_object_revisions / v2_object_revision_diff

**只测契约，不重复测业务**：版本数据正确性由 `test_revision_service.py` 覆盖。
本文件断言四件事：

  1. 两条路由的 URL 与状态码（200 / 404 / 401）
  2. 响应字段名字（`data` 的键集合 / `header` `lines` 原样透传）
  3. 启用性闸门：未配置策略 / 未知名对象 → 404 REVISION_NOT_ENABLED
  4. 服务异常映射：RevisionError → 404 + 业务错误码
"""
import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import sys
from types import SimpleNamespace

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import meta.api.bo_api as bo_api  # noqa: E402
import meta.services.auth_middleware as auth_mw  # noqa: E402
from meta.services.revision_service import RevisionError  # noqa: E402

AUTH = {"Authorization": "Bearer test-token", "Content-Type": "application/json"}

REVISION_KEYS = {
    'revision_no', 'created_at', 'created_by',
    'reason_code', 'change_set_id', 'summary',
}

LIST_URL = '/api/v2/bo/{ot}/{oid}/revisions'
DIFF_URL = '/api/v2/bo/{ot}/{oid}/revisions/{a}/diff/{b}'


# ----------------------------------------------------------------------
# 认证替身（与 test_configuration_api 同口径）
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
# 元模型 / 服务替身：只验证"接口把什么传给了服务"
# ----------------------------------------------------------------------
class _FakeRegistry:
    """只实现 get(object_type) —— 隔离全局注册表"""

    def __init__(self, objects=None):
        self._objects = objects or {}

    def get(self, object_type):
        return self._objects.get(object_type)


class _FakeRevisionService:
    def __init__(self):
        self.list_result = []
        self.diff_result = {'header': [], 'lines': []}
        self.diff_error = None
        self.calls = {}

    def list_revisions(self, ds, object_type, object_id):
        self.calls['list_revisions'] = {
            'ds': ds, 'object_type': object_type, 'object_id': object_id,
        }
        return self.list_result

    def diff(self, ds, object_type, object_id, rev_a, rev_b):
        self.calls['diff'] = {
            'ds': ds, 'object_type': object_type, 'object_id': object_id,
            'rev_a': rev_a, 'rev_b': rev_b,
        }
        if self.diff_error is not None:
            raise self.diff_error
        if rev_a == rev_b:
            return {'header': [], 'lines': []}
        return self.diff_result


def _obj(enabled=True):
    """造一个带 revision_policy 的元对象"""
    return SimpleNamespace(
        id='sales_order',
        revision_policy=SimpleNamespace(enabled=enabled),
    )


@pytest.fixture()
def env(monkeypatch):
    """隔离全局注册表 / 数据源 / 版本服务"""
    from flask import Flask

    monkeypatch.setattr(auth_mw, "token_blacklist_service", _FakeBlacklist())
    monkeypatch.setattr(auth_mw, "TokenService", _FakeTokenService)
    monkeypatch.setattr(bo_api, '_get_data_source', lambda: object())

    reg = _FakeRegistry({'sales_order': _obj(enabled=True)})
    monkeypatch.setattr(bo_api, 'registry', reg)

    service = _FakeRevisionService()
    monkeypatch.setattr(bo_api.revision_service, 'list_revisions',
                        service.list_revisions)
    monkeypatch.setattr(bo_api.revision_service, 'diff', service.diff)

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(bo_api.bo_bp)
    client = app.test_client()

    return SimpleNamespace(
        client=client, registry=reg, service=service, monkeypatch=monkeypatch,
    )


# ======================================================================
# IF-001: GET /bo/{object_type}/{obj_id}/revisions
# ======================================================================
class TestListRevisions:

    def test_enabled_object_returns_row_keys(self, env):
        env.service.list_result = [{
            'revision_no': 1,
            'created_at': '2026-10-29 09:00:00',
            'created_by': 'admin',
            'reason_code': 'price_change',
            'change_set_id': 'CS-1',
            'summary': '3 个字段变更',
        }]
        resp = env.client.get(
            LIST_URL.format(ot='sales_order', oid=7), headers=AUTH)

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload['success'] is True
        assert isinstance(payload['data'], list)
        assert len(payload['data']) == 1
        assert set(payload['data'][0]) == REVISION_KEYS

        # 接口把 URL 参数原样传给服务
        call = env.service.calls['list_revisions']
        assert call['object_type'] == 'sales_order'
        assert call['object_id'] == 7

    def test_policy_disabled_returns_404(self, env):
        env.registry._objects['sales_order'] = _obj(enabled=False)

        resp = env.client.get(
            LIST_URL.format(ot='sales_order', oid=7), headers=AUTH)

        assert resp.status_code == 404
        payload = resp.get_json()
        assert payload['success'] is False
        assert payload['code'] == 'REVISION_NOT_ENABLED'
        # 闸门在服务之前，未落库
        assert 'list_revisions' not in env.service.calls

    def test_unknown_object_returns_404(self, env):
        resp = env.client.get(
            LIST_URL.format(ot='not_exists', oid=7), headers=AUTH)

        assert resp.status_code == 404
        payload = resp.get_json()
        assert payload['success'] is False
        assert payload['code'] == 'REVISION_NOT_ENABLED'
        assert 'list_revisions' not in env.service.calls


# ======================================================================
# IF-002: GET /bo/{object_type}/{obj_id}/revisions/{a}/diff/{b}
# ======================================================================
class TestRevisionDiff:

    def test_diff_passes_header_and_lines_through(self, env):
        env.service.diff_result = {
            'header': [{'field_name': 'total_amount', 'old_value': '10', 'new_value': '20'}],
            'lines': [{'line_key': 'L1', 'field_name': 'qty', 'old_value': '1', 'new_value': '2'}],
        }
        resp = env.client.get(
            DIFF_URL.format(ot='sales_order', oid=7, a=1, b=2), headers=AUTH)

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload['success'] is True
        assert payload['data']['header'] == env.service.diff_result['header']
        assert payload['data']['lines'] == env.service.diff_result['lines']

        call = env.service.calls['diff']
        assert call['rev_a'] == 1
        assert call['rev_b'] == 2
        assert call['object_type'] == 'sales_order'
        assert call['object_id'] == 7

    def test_revision_not_found_returns_404_with_code(self, env):
        env.service.diff_error = RevisionError('REVISION_NOT_FOUND', '版本 9 不存在')

        resp = env.client.get(
            DIFF_URL.format(ot='sales_order', oid=7, a=1, b=9), headers=AUTH)

        assert resp.status_code == 404
        payload = resp.get_json()
        assert payload['success'] is False
        assert payload['code'] == 'REVISION_NOT_FOUND'
        assert payload['message'] == '版本 9 不存在'

    def test_same_revision_returns_empty_diff(self, env):
        resp = env.client.get(
            DIFF_URL.format(ot='sales_order', oid=7, a=3, b=3), headers=AUTH)

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload['success'] is True
        assert payload['data'] == {'header': [], 'lines': []}

    def test_disabled_policy_returns_404(self, env):
        env.registry._objects['sales_order'] = _obj(enabled=False)

        resp = env.client.get(
            DIFF_URL.format(ot='sales_order', oid=7, a=1, b=2), headers=AUTH)

        assert resp.status_code == 404
        payload = resp.get_json()
        assert payload['code'] == 'REVISION_NOT_ENABLED'
        assert 'diff' not in env.service.calls


# ======================================================================
# 鉴权（login_required）
# ======================================================================
class TestAuth:

    @pytest.mark.parametrize('url', [
        LIST_URL.format(ot='sales_order', oid=7),
        DIFF_URL.format(ot='sales_order', oid=7, a=1, b=2),
    ])
    def test_missing_authorization_header(self, env, url):
        resp = env.client.get(url)

        assert resp.status_code == 401
        payload = resp.get_json()
        assert payload['code'] == 'UNAUTHORIZED'
        assert 'list_revisions' not in env.service.calls
        assert 'diff' not in env.service.calls
