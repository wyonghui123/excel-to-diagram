# -*- coding: utf-8 -*-
"""通用 BO API 档位（P3 只读账本）单元测试。

覆盖:
  · `generic_api_mode_of` 归一：skip_generic_api 优先、未知值回落 full；
  · `generic_api_allows` 方法矩阵（read_only 仅放行读）；
  · `meta/schemas/task_run.yaml` 声明 read_only，且只生成读类动作。
"""

import os

import pytest

pytestmark = pytest.mark.unit

from meta.core.models import (
    MetaObject, generic_api_allows, generic_api_mode_of,
)
from meta.core.yaml_loader import load_yaml_file

SCHEMA = os.path.join(os.path.dirname(__file__), '..', 'schemas', 'task_run.yaml')


class _Obj:
    def __init__(self, skip=False, mode='full'):
        self.skip_generic_api = skip
        self.generic_api_mode = mode


# ── 归一 ──────────────────────────────────────────────────────────────

def test_mode_defaults_to_full():
    assert generic_api_mode_of(MetaObject(id='x', name='X', table_name='x')) == 'full'


def test_skip_switch_wins_over_mode():
    assert generic_api_mode_of(_Obj(skip=True, mode='read_only')) == 'disabled'


def test_unknown_mode_falls_back_to_full():
    assert generic_api_mode_of(_Obj(mode='nonsense')) == 'full'


def test_missing_object_is_disabled():
    assert generic_api_mode_of(None) == 'disabled'


# ── 方法矩阵 ──────────────────────────────────────────────────────────

@pytest.mark.parametrize('method,allowed', [
    ('GET', True), ('get', True), ('HEAD', True), ('OPTIONS', True),
    ('POST', False), ('PUT', False), ('PATCH', False), ('DELETE', False),
])
def test_read_only_blocks_writes(method, allowed):
    assert generic_api_allows('read_only', method) is allowed


def test_full_allows_everything():
    assert generic_api_allows('full', 'DELETE') is True
    assert generic_api_allows('full', 'GET') is True


def test_disabled_blocks_everything():
    assert generic_api_allows('disabled', 'GET') is False


# ── schema ────────────────────────────────────────────────────────────

def test_task_run_schema_is_read_only_with_read_actions():
    obj = load_yaml_file(SCHEMA)
    assert obj is not None
    assert obj.id == 'task_run'
    assert obj.table_name == 'task_runs'
    assert obj.generic_api_mode == 'read_only'
    assert obj.skip_generic_api is False

    action_ids = {a.id for a in obj.actions}
    assert action_ids == {'task_run_list', 'task_run_read'}


# ── read_only 对象的读权限 ────────────────────────────────────────────

def _register_task_run():
    from meta.core.models import registry
    if registry.get('task_run') is None:
        registry.register(load_yaml_file(SCHEMA))
    return registry.get('task_run')


def _strict_gate(monkeypatch):
    """强制 strict 档：默认即 strict，显式固定避免其他用例改动全局开关。"""
    from meta.core import permission_gate
    monkeypatch.setattr(permission_gate, 'permission_gate_mode',
                        lambda: permission_gate.STRICT)


def test_read_only_read_denied_without_permission(monkeypatch):
    """[P3] 只读 ≠ 免鉴权：无 task_run:read 的登录用户读列表应被拒。"""
    from flask import Flask, g
    from meta.services.auth_middleware import check_generic_read_permission

    _register_task_run()
    _strict_gate(monkeypatch)
    app = Flask(__name__)
    with app.test_request_context('/api/v2/bo/task_run'):
        g.current_user = {'id': 7, 'permissions': ['other:read']}
        denied = check_generic_read_permission('task_run')
        assert denied is not None
        assert denied.allowed is False
        assert denied.required == 'task_run:read'


def test_read_only_read_allowed_with_wildcard_or_code(monkeypatch):
    """[P3] 管理员（'*'）与持有 task_run:read 的用户可读。"""
    from flask import Flask, g
    from meta.services.auth_middleware import check_generic_read_permission

    _register_task_run()
    _strict_gate(monkeypatch)
    app = Flask(__name__)
    for user in ({'id': 1, 'permissions': ['*']},
                 {'id': 2, 'permissions': ['task_run:read']}):
        with app.test_request_context('/api/v2/bo/task_run'):
            g.current_user = user
            assert check_generic_read_permission('task_run') is None


def test_bo_before_request_returns_403_for_denied_read(monkeypatch):
    """[P3] 接线验证：GET /api/v2/bo/task_run 无权限时 403（而非 200 泄露）。"""
    from flask import Flask, g
    from meta.api.bo_api import _reject_skip_generic_api_objects

    _register_task_run()
    _strict_gate(monkeypatch)
    app = Flask(__name__)
    with app.test_request_context('/api/v2/bo/task_run', method='GET'):
        g.current_user = {'id': 7, 'permissions': []}
        resp = _reject_skip_generic_api_objects()
        assert resp is not None
        assert resp[1] == 403
        assert resp[0].get_json()['error_code'] == 'GENERIC_API_FORBIDDEN'

    with app.test_request_context('/api/v2/bo/task_run', method='GET'):
        g.current_user = {'id': 1, 'permissions': ['*']}
        assert _reject_skip_generic_api_objects() is None


def test_bo_before_request_keeps_write_404(monkeypatch):
    """[P3] read_only 的写入口仍是 404，不因加读权限而放开。"""
    from flask import Flask, g
    from meta.api.bo_api import _reject_skip_generic_api_objects

    _register_task_run()
    app = Flask(__name__)
    with app.test_request_context('/api/v2/bo/task_run', method='POST'):
        g.current_user = {'id': 1, 'permissions': ['*']}
        resp = _reject_skip_generic_api_objects()
        assert resp is not None
        assert resp[1] == 404
        assert resp[0].get_json()['error_code'] == 'GENERIC_API_READ_ONLY'