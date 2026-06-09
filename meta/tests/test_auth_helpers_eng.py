# -*- coding: utf-8 -*-
"""
SVC-019: auth_helpers (4 测试) - Flask session 认证辅助

[MARKER] unit - 单元测试 (需要 Flask app context)
[FEATURE] is_authenticated / get_current_user_id / require_auth
"""
import json
import pytest

pytestmark = [pytest.mark.unit]


@pytest.fixture
def app():
    """最小 Flask app for session testing"""
    from flask import Flask
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test_secret'
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


class TestAuthHelpers:
    """auth_helpers 测试 (4 用例, 需要 Flask app context)"""

    def test_is_authenticated_no_session(self, app):
        """session 无 user_id → False"""
        with app.test_request_context('/'):
            from meta.core.auth_helpers import is_authenticated
            assert is_authenticated() is False

    def test_is_authenticated_with_user_id(self, app):
        """session 有 user_id → True"""
        from flask import session
        with app.test_request_context('/'):
            session['user_id'] = 42
            from meta.core.auth_helpers import is_authenticated
            assert is_authenticated() is True

    # ---------- is_authenticated 3 种 session key 合并 (3 → 1, 3 cases) ----------
    @pytest.mark.parametrize('session_key,session_value,expected,id_label', [
        pytest.param('user_id', 1, True, 'user_id', id='session_user_id'),
        pytest.param('user', {'id': 1, 'name': 'Alice'}, True, 'user_obj', id='session_user'),
        pytest.param('logged_in', True, True, 'logged_in_flag', id='session_logged_in'),
    ])
    def test_is_authenticated_session_keys(self, app, session_key, session_value, expected, id_label):
        """is_authenticated 支持 3 种 session key"""
        from flask import session
        with app.test_request_context('/'):
            session[session_key] = session_value
            from meta.core.auth_helpers import is_authenticated
            assert is_authenticated() is expected

    def test_require_auth_decorator_unauthenticated(self, app, client):
        """require_auth 装饰器: 未登录 → 401"""
        from meta.core.auth_helpers import require_auth

        @require_auth
        def protected_endpoint():
            return {'success': True}

        # 注册到 Flask app
        app.add_url_rule('/protected', 'protected', protected_endpoint, methods=['GET'])

        rv = client.get('/protected')
        assert rv.status_code == 401
        data = json.loads(rv.data)
        assert data['success'] is False
        assert '未登录' in data['error']

    def test_require_auth_decorator_authenticated(self, app, client):
        """require_auth 装饰器: 已登录 → 200, 调用原函数"""
        from flask import session
        from meta.core.auth_helpers import require_auth

        @require_auth
        def protected_endpoint():
            return {'success': True, 'data': 'secret'}

        app.add_url_rule('/protected2', 'protected2', protected_endpoint, methods=['GET'])

        with client.session_transaction() as sess:
            sess['user_id'] = 42
        rv = client.get('/protected2')
        assert rv.status_code == 200
        data = json.loads(rv.data)
        assert data['success'] is True
        assert data['data'] == 'secret'

    def test_get_current_user_id(self, app):
        """get_current_user_id: 已登录 → user_id, 未登录 → 0"""
        from flask import session
        with app.test_request_context('/'):
            from meta.core.auth_helpers import get_current_user_id
            assert get_current_user_id() == 0
            session['user_id'] = 99
            assert get_current_user_id() == 99
