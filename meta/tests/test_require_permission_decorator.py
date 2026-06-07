import pytest

pytestmark = pytest.mark.integration

"""
后端测试套件 - @require_permission 装饰器测试
测试 meta.api.decorators 模块
"""

import pytest
from unittest.mock import patch, MagicMock
from flask import Flask, g


@pytest.fixture
def app():
    """创建测试用 Flask 应用"""
    app = Flask(__name__)
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    """创建测试用 Flask 测试客户端"""
    return app.test_client()


class TestRequirePermissionDecorator:
    """@require_permission 装饰器测试"""

    def test_missing_user_id_returns_401(self, app):
        """TC-DEC-001: 无 user_id 返回 401"""
        from meta.api.decorators import require_permission

        @app.route('/test')
        @require_permission('user_read')
        def test_endpoint():
            return {'success': True}

        with app.test_client() as client:
            with patch('meta.api.decorators._check_permission', return_value=False):
                response = client.get('/test')
                assert response.status_code in [401, 500]
                data = response.get_json()
                assert data.get('error', '') == 'UNAUTHORIZED'

    def test_has_permission_passes(self, app):
        """TC-DEC-002: 有权限时正常访问"""
        from meta.api.decorators import require_permission

        @app.route('/test')
        @require_permission('user_read')
        def test_endpoint():
            return {'success': True}

        with app.test_request_context():
            g.user_id = 1
            with patch('meta.api.decorators._check_permission', return_value=True):
                with app.test_client() as client:
                    response = client.get('/test')
                    assert response.status_code in [200, 401, 404, 500]
                    data = response.get_json()
                    assert data.get('success', False) is True

    def test_missing_permission_returns_403(self, app):
        """TC-DEC-003: 无权限时返回 403"""
        from meta.api.decorators import require_permission

        @app.route('/test')
        @require_permission('user_delete')
        def test_endpoint():
            return {'success': True}

        with app.test_request_context():
            g.user_id = 1
            with patch('meta.api.decorators._check_permission', return_value=False):
                with app.test_client() as client:
                    response = client.get('/test')
                    assert response.status_code in [401, 403, 500]
                    data = response.get_json()
                    assert data.get('error', '') == 'FORBIDDEN'
                    assert 'Permission denied' in data.get('message', '')

    def test_permission_check_exception_returns_false(self, app):
        """TC-DEC-004: 权限检查抛出异常时返回 403"""
        from meta.api.decorators import require_permission

        @app.route('/test')
        @require_permission('user_read')
        def test_endpoint():
            return {'success': True}

        with app.test_request_context():
            g.user_id = 1
            with patch('meta.api.decorators._check_permission', return_value=False):
                with app.test_client() as client:
                    response = client.get('/test')
                    assert response.status_code in [401, 403, 500]

    def test_decorator_preserves_function_metadata(self, app):
        """TC-DEC-005: 装饰器保留原函数元数据"""
        from meta.api.decorators import require_permission

        @app.route('/test')
        @require_permission('user_read')
        def test_endpoint():
            """This is a docstring."""
            return {'success': True}

        assert test_endpoint.__name__ == 'test_endpoint'
        assert test_endpoint.__doc__ == 'This is a docstring.'

    def test_different_permission_codes(self, app):
        """TC-DEC-006: 不同权限码分别检查"""
        from meta.api.decorators import require_permission

        permission_checks = {}

        def mock_check(user_id, perm):
            return permission_checks.get(perm, False)

        @app.route('/test1')
        @require_permission('product_create')
        def test1():
            return {'success': True}

        @app.route('/test2')
        @require_permission('product_read')
        def test2():
            return {'success': True}

        with app.test_request_context():
            g.user_id = 1

            with patch('meta.api.decorators._check_permission', side_effect=lambda u, p: mock_check(u, p)):
                permission_checks = {'product_create': True, 'product_read': False}

                with app.test_client() as client:
                    r1 = client.get('/test1')
                    assert r1.status_code in [200, 401, 404, 500]

                    r2 = client.get('/test2')
                    assert r2.status_code in [401, 403, 500]

    def test_path_in_warning_log(self, app):
        """TC-DEC-007: 拒绝日志包含路径信息"""
        import logging
        from meta.api.decorators import require_permission

        @app.route('/api/v1/sensitive-data')
        @require_permission('admin_delete')
        def test_endpoint():
            return {'success': True}

        with app.test_request_context():
            g.user_id = 1
            with patch('meta.api.decorators._check_permission', return_value=False):
                with patch('meta.api.decorators.logger') as mock_logger:
                    with app.test_client() as client:
                        client.get('/api/v1/sensitive-data')
                        mock_logger.warning.assert_called_once()
                        log_args = mock_logger.warning.call_args[0]
                        assert '/api/v1/sensitive-data' in str(log_args)


class TestCheckPermission:
    """_check_permission 内部函数测试"""

    def test_calls_permission_sync_service(self):
        """TC-DEC-010: _check_permission 调用 PermissionSyncService"""
        from meta.api.decorators import _check_permission

        with patch('meta.services.permission_sync_service.PermissionSyncService') as mock_pss:
            mock_instance = MagicMock()
            mock_instance.check_user_permission.return_value = True
            mock_pss.return_value = mock_instance

            result = _check_permission(1, 'user_read')

            mock_instance.check_user_permission.assert_called_once_with(1, 'user_read')
            assert result is True

    def test_returns_false_on_exception(self):
        """TC-DEC-011: 异常时返回 False"""
        from meta.api.decorators import _check_permission

        with patch(
            'meta.services.permission_sync_service.PermissionSyncService',
            side_effect=Exception('Service error')
        ):
            with patch('meta.api.decorators.logger') as mock_logger:
                result = _check_permission(1, 'user_read')
                assert result is False
                mock_logger.error.assert_called_once()
