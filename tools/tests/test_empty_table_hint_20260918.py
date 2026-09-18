"""
[2026-09-18 P1-4] 测试 prod-verify 端点 FAIL 时自动判 list 端点是否空.

场景:
  1. /api/v1/roles/1/permissions 失败, /api/v1/roles total=0 → 提示"表空"
  2. /api/v1/roles/1/permissions 失败, /api/v1/roles total>0 → 不提示
  3. login 失败 → 不提示 (避免嵌套错误)
  4. 不带数字 id 的路径 → 不提示 (regex 不匹配)
  5. stage != 'probe' (login-parse) → 不提示
"""
import sys
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tools'))
import staging_round as sr  # noqa: E402


def _make_exc(stage='probe', raw=''):
    return sr.ProdVerifyError(stage, '/api/v1/roles/1/permissions', raw=raw)


def test_hint_when_list_empty():
    """场景 1: list 端点 total=0 → 提示."""
    fake_login = {'stdout': '{"data":{"token":"abc123"}}', 'error': None}
    fake_list = {'stdout': '{"success":true,"data":{"items":[],"total":0}}', 'error': None}

    with mock.patch.object(sr, 'remote_exec', side_effect=[fake_login, fake_list]):
        hint = sr._hint_empty_table_for_failed_endpoint('/api/v1/roles/1/permissions', _make_exc())
    assert hint is not None
    assert '表空' in hint or 'total=0' in hint


def test_no_hint_when_list_has_data():
    """场景 2: list 端点 total=5 → 不提示 (代码问题, 不是数据问题)."""
    fake_login = {'stdout': '{"data":{"token":"abc123"}}', 'error': None}
    fake_list = {'stdout': '{"success":true,"data":{"items":[{"id":1}],"total":5}}', 'error': None}

    with mock.patch.object(sr, 'remote_exec', side_effect=[fake_login, fake_list]):
        hint = sr._hint_empty_table_for_failed_endpoint('/api/v1/roles/1/permissions', _make_exc())
    assert hint is None, 'list 有数据时应不提示 (代码 bug, 非数据问题)'


def test_no_hint_when_login_fails():
    """场景 3: login 失败 → 不提示 (避免嵌套报错)."""
    fake_login = {'error': True, 'reason': 'connection refused'}

    with mock.patch.object(sr, 'remote_exec', side_effect=[fake_login]):
        hint = sr._hint_empty_table_for_failed_endpoint('/api/v1/roles/1/permissions', _make_exc())
    assert hint is None


def test_no_hint_for_non_id_path():
    """场景 4: 路径不含 /<int_id> → regex 不匹配, 不提示."""
    fake_login = {'stdout': '{"data":{"token":"abc"}}', 'error': None}
    fake_list = {'stdout': '{"success":true,"data":{"total":0}}', 'error': None}

    with mock.patch.object(sr, 'remote_exec', side_effect=[fake_login, fake_list]):
        hint = sr._hint_empty_table_for_failed_endpoint('/api/v1/roles', _make_exc())
    # /api/v1/roles 没数字 id → _guess_list_endpoint 返回 None → 不调用 list 端点
    assert hint is None


def test_no_hint_for_non_probe_stage():
    """场景 5: stage != 'probe' (例如 login-parse) → 不提示."""
    exc = _make_exc(stage='login-parse', raw='bad json')
    fake_login = {'stdout': '{"data":{"token":"abc"}}', 'error': None}
    fake_list = {'stdout': '{"success":true,"data":{"total":0}}', 'error': None}

    with mock.patch.object(sr, 'remote_exec', side_effect=[fake_login, fake_list]):
        hint = sr._hint_empty_table_for_failed_endpoint('/api/v1/roles/1/permissions', exc)
    assert hint is None


def test_guess_list_endpoint_patterns():
    """测试 _guess_list_endpoint 的 regex 覆盖常见格式."""
    cases = [
        ('/api/v1/roles/1/permissions', '/api/v1/roles'),
        ('/api/v2/bo/user/123', '/api/v2/bo/user'),
        ('/api/v2/bo/permission_set/5', '/api/v2/bo/permission_set'),
        ('/api/v1/roles', None),  # 无数字 id
        ('/health', None),                     # 不匹配 /api/
    ]
    for path, expected in cases:
        got = sr._guess_list_endpoint(path)
        assert got == expected, f'{path} → expected {expected}, got {got}'


if __name__ == '__main__':
    test_hint_when_list_empty()
    test_no_hint_when_list_has_data()
    test_no_hint_when_login_fails()
    test_no_hint_for_non_id_path()
    test_no_hint_for_non_probe_stage()
    test_guess_list_endpoint_patterns()
    print('OK: 6/6 empty-table-hint tests passed')