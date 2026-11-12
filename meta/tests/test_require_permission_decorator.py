# -*- coding: utf-8 -*-
"""后端测试套件 - @require_permission 装饰器测试

覆盖 meta.api.decorators.require_permission 的当前实现:
  - 未登录（g.current_user 缺失）→ 401 UNAUTHORIZED
  - 有权限 → 正常放行
  - 无权限 → 403 FORBIDDEN，拒绝日志含请求路径
  - 权限判定抛异常 → TESTING 下向上传播（不做兜底转换）
"""
import pytest
from unittest.mock import patch
from flask import Flask, g

pytestmark = pytest.mark.integration


@pytest.fixture
def app():
    """创建测试用 Flask 应用（未注入登录态）"""
    app = Flask(__name__)
    app.config['TESTING'] = True
    return app


@pytest.fixture
def authed_app(app):
    """在 app 上注入已登录用户（g.current_user）"""
    @app.before_request
    def _inject_current_user():
        g.current_user = {'user_id': 1, 'permissions': []}

    return app


class TestRequirePermissionDecorator:
    """@require_permission 装饰器测试"""

    def test_missing_user_returns_401(self, app):
        """TC-DEC-001: 无 current_user 返回 401"""
        from meta.api.decorators import require_permission

        @app.route('/test')
        @require_permission('user_read')
        def test_endpoint():
            return {'success': True}

        with app.test_client() as client:
            response = client.get('/test')

        assert response.status_code == 401
        assert response.get_json()['error'] == 'UNAUTHORIZED'

    def test_has_permission_passes(self, authed_app):
        """TC-DEC-002: 有权限时正常访问"""
        from meta.api.decorators import require_permission

        @authed_app.route('/test')
        @require_permission('user_read')
        def test_endpoint():
            return {'success': True}

        with patch('meta.api.decorators.evaluate_code', return_value=True):
            with authed_app.test_client() as client:
                response = client.get('/test')

        assert response.status_code == 200
        assert response.get_json()['success'] is True

    def test_missing_permission_returns_403(self, authed_app):
        """TC-DEC-003: 无权限时返回 403"""
        from meta.api.decorators import require_permission

        @authed_app.route('/test')
        @require_permission('user_delete')
        def test_endpoint():
            return {'success': True}

        with patch('meta.api.decorators.evaluate_code', return_value=False):
            with authed_app.test_client() as client:
                response = client.get('/test')

        assert response.status_code == 403
        data = response.get_json()
        assert data['error'] == 'FORBIDDEN'
        assert 'Permission denied' in data['message']

    def test_permission_check_exception_propagates(self, authed_app):
        """TC-DEC-004: 权限判定抛异常时在 TESTING 下向上传播"""
        from meta.api.decorators import require_permission

        @authed_app.route('/test')
        @require_permission('user_read')
        def test_endpoint():
            return {'success': True}

        with patch('meta.api.decorators.evaluate_code',
                   side_effect=RuntimeError('boom')):
            with authed_app.test_client() as client:
                with pytest.raises(RuntimeError):
                    client.get('/test')

    def test_decorator_preserves_function_metadata(self):
        """TC-DEC-005: 装饰器保留原函数元数据"""
        from meta.api.decorators import require_permission

        @require_permission('user_read')
        def sample_endpoint():
            """This is a docstring."""
            return {'success': True}

        assert sample_endpoint.__name__ == 'sample_endpoint'
        assert sample_endpoint.__doc__ == 'This is a docstring.'

    def test_different_permission_codes(self, authed_app):
        """TC-DEC-006: 不同权限码分别检查"""
        from meta.api.decorators import require_permission

        @authed_app.route('/test1')
        @require_permission('product_create')
        def test1():
            return {'success': True}

        @authed_app.route('/test2')
        @require_permission('product_read')
        def test2():
            return {'success': True}

        def _evaluate(user, code):
            return code == 'product_create'

        with patch('meta.api.decorators.evaluate_code', side_effect=_evaluate):
            with authed_app.test_client() as client:
                r1 = client.get('/test1')
                r2 = client.get('/test2')

        assert r1.status_code == 200
        assert r2.status_code == 403

    def test_path_in_warning_log(self, authed_app):
        """TC-DEC-007: 拒绝日志包含路径信息"""
        from meta.api.decorators import require_permission

        @authed_app.route('/api/v1/sensitive-data')
        @require_permission('admin_delete')
        def test_endpoint():
            return {'success': True}

        with patch('meta.api.decorators.evaluate_code', return_value=False):
            with patch('meta.api.decorators.logger') as mock_logger:
                with authed_app.test_client() as client:
                    client.get('/api/v1/sensitive-data')

                mock_logger.warning.assert_called_once()
                assert '/api/v1/sensitive-data' in str(mock_logger.warning.call_args[0])
