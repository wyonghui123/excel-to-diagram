import pytest

pytestmark = pytest.mark.integration

"""
后端测试套件 - 启动安全检查测试
测试 meta.core.startup_checks 模块
"""

import pytest
import os
from unittest.mock import patch, MagicMock


class TestCheckDebugMode:
    """DEBUG 模式检查测试"""

    def test_debug_mode_off_returns_ok(self):
        """TC-SC-001: FLASK_DEBUG=false 返回 OK"""
        from meta.core.startup_checks import _check_debug_mode

        with patch.dict(os.environ, {'FLASK_DEBUG': 'false'}):
            result = _check_debug_mode()
            assert result['level'] == 'OK'

    def test_debug_mode_true_returns_warning(self):
        """TC-SC-002: FLASK_DEBUG=true 返回 WARNING"""
        from meta.core.startup_checks import _check_debug_mode

        with patch.dict(os.environ, {'FLASK_DEBUG': 'true'}):
            result = _check_debug_mode()
            assert result['level'] == 'WARNING'
            assert 'DEBUG' in result['message']

    def test_debug_mode_1_returns_ok(self):
        """TC-SC-003: FLASK_DEBUG=1 被视为非标准值，返回 OK"""
        from meta.core.startup_checks import _check_debug_mode

        with patch.dict(os.environ, {'FLASK_DEBUG': '1'}, clear=False):
            result = _check_debug_mode()
            assert result['level'] == 'OK'


class TestCheckJwtSecret:
    """JWT 密钥检查测试"""

    def test_missing_jwt_secret_debug_returns_warning(self):
        """TC-SC-010: 缺失 JWT_SECRET_KEY（DEBUG模式）返回 WARNING"""
        from meta.core.startup_checks import _check_jwt_secret

        with patch.dict(os.environ, {'FLASK_DEBUG': 'true'}, clear=False):
            env = os.environ.copy()
            env.pop('JWT_SECRET_KEY', None)
            with patch.dict(os.environ, env, clear=True):
                os.environ.pop('JWT_SECRET_KEY', None)
                result = _check_jwt_secret()
                assert result['level'] == 'WARNING'

    def test_missing_jwt_secret_production_raises_error(self):
        """TC-SC-011: 缺失 JWT_SECRET_KEY（生产模式）返回 ERROR"""
        from meta.core.startup_checks import _check_jwt_secret

        with patch.dict(os.environ, {'FLASK_DEBUG': 'false', 'TESTING': 'false'}, clear=False):
            env = os.environ.copy()
            env.pop('JWT_SECRET_KEY', None)
            with patch.dict(os.environ, env, clear=True):
                os.environ.pop('JWT_SECRET_KEY', None)
                os.environ['FLASK_DEBUG'] = 'false'
                os.environ['TESTING'] = 'false'
                result = _check_jwt_secret()
                assert result['level'] == 'ERROR'

    def test_default_jwt_secret_production_raises_error(self):
        """TC-SC-012: 默认 JWT_SECRET_KEY（生产模式）返回 ERROR"""
        from meta.core.startup_checks import _check_jwt_secret

        with patch.dict(os.environ, {
            'FLASK_DEBUG': 'false',
            'TESTING': 'false',
            'JWT_SECRET_KEY': 'your-secret-key-change-in-production'
        }):
            result = _check_jwt_secret()
            assert result['level'] == 'ERROR'

    def test_short_jwt_secret_production_raises_error(self):
        """TC-SC-013: 过短的 JWT_SECRET_KEY（生产模式）返回 ERROR"""
        from meta.core.startup_checks import _check_jwt_secret

        with patch.dict(os.environ, {
            'FLASK_DEBUG': 'false',
            'TESTING': 'false',
            'JWT_SECRET_KEY': 'abc'
        }):
            result = _check_jwt_secret()
            assert result['level'] == 'ERROR'

    def test_valid_jwt_secret_returns_ok(self):
        """TC-SC-014: 合法的 JWT_SECRET_KEY 返回 OK"""
        from meta.core.startup_checks import _check_jwt_secret

        with patch.dict(os.environ, {
            'FLASK_DEBUG': 'false',
            'JWT_SECRET_KEY': 'a' * 32
        }):
            result = _check_jwt_secret()
            assert result['level'] == 'OK'


class TestCheckCorsConfig:
    """CORS 配置检查测试"""

    def test_empty_cors_debug_returns_warning(self):
        """TC-SC-020: 空 CORS_ALLOWED_ORIGINS（DEBUG模式）返回 WARNING"""
        from meta.core.startup_checks import _check_cors_config

        with patch.dict(os.environ, {'FLASK_DEBUG': 'true'}, clear=False):
            env = os.environ.copy()
            env.pop('CORS_ALLOWED_ORIGINS', None)
            with patch.dict(os.environ, env, clear=True):
                os.environ.pop('CORS_ALLOWED_ORIGINS', None)
                result = _check_cors_config()
                assert result['level'] == 'WARNING'

    def test_empty_cors_production_returns_error(self):
        """TC-SC-021: 空 CORS_ALLOWED_ORIGINS（生产模式）返回 ERROR"""
        from meta.core.startup_checks import _check_cors_config

        with patch.dict(os.environ, {'FLASK_DEBUG': 'false', 'TESTING': 'false'}, clear=False):
            env = os.environ.copy()
            env.pop('CORS_ALLOWED_ORIGINS', None)
            with patch.dict(os.environ, env, clear=True):
                os.environ.pop('CORS_ALLOWED_ORIGINS', None)
                os.environ['FLASK_DEBUG'] = 'false'
                os.environ['TESTING'] = 'false'
                result = _check_cors_config()
                assert result['level'] == 'ERROR'

    def test_configured_cors_returns_ok(self):
        """TC-SC-022: 配置了 CORS_ALLOWED_ORIGINS 返回 OK"""
        from meta.core.startup_checks import _check_cors_config

        with patch.dict(os.environ, {
            'CORS_ALLOWED_ORIGINS': 'https://example.com,https://app.example.com'
        }):
            result = _check_cors_config()
            assert result['level'] == 'OK'

    def test_single_origin_configured_returns_ok(self):
        """TC-SC-023: 配置了单个 CORS origin 返回 OK"""
        from meta.core.startup_checks import _check_cors_config

        with patch.dict(os.environ, {'CORS_ALLOWED_ORIGINS': 'https://example.com'}):
            result = _check_cors_config()
            assert result['level'] == 'OK'


class TestCheckAdminPassword:
    """管理员密码检查测试"""

    def test_missing_admin_password_debug_returns_ok(self):
        """TC-SC-030: 缺失 ADMIN_PASSWORD（DEBUG模式）返回 OK"""
        from meta.core.startup_checks import _check_admin_password

        with patch.dict(os.environ, {'FLASK_DEBUG': 'true'}, clear=False):
            env = os.environ.copy()
            env.pop('ADMIN_PASSWORD', None)
            with patch.dict(os.environ, env, clear=True):
                os.environ.pop('ADMIN_PASSWORD', None)
                result = _check_admin_password()
                assert result['level'] == 'OK'

    def test_missing_admin_password_production_returns_warning(self):
        """TC-SC-031: 缺失 ADMIN_PASSWORD（生产模式）返回 WARNING"""
        from meta.core.startup_checks import _check_admin_password

        with patch.dict(os.environ, {'FLASK_DEBUG': 'false', 'TESTING': 'false'}, clear=False):
            env = os.environ.copy()
            env.pop('ADMIN_PASSWORD', None)
            with patch.dict(os.environ, env, clear=True):
                os.environ.pop('ADMIN_PASSWORD', None)
                os.environ['FLASK_DEBUG'] = 'false'
                os.environ['TESTING'] = 'false'
                result = _check_admin_password()
                assert result['level'] == 'WARNING'

    def test_configured_admin_password_returns_ok(self):
        """TC-SC-032: 配置了 ADMIN_PASSWORD 返回 OK"""
        from meta.core.startup_checks import _check_admin_password

        with patch.dict(os.environ, {'ADMIN_PASSWORD': 'SecurePassword123!'}):
            result = _check_admin_password()
            assert result['level'] == 'OK'


class TestRunStartupChecks:
    """run_startup_checks 集成测试"""

    def test_all_checks_pass_debug_mode(self):
        """TC-SC-040: DEBUG 模式下所有检查通过不抛出异常"""
        from meta.core.startup_checks import run_startup_checks

        mock_app = MagicMock()

        with patch.dict(os.environ, {
            'FLASK_DEBUG': 'true',
            'JWT_SECRET_KEY': 'a' * 32,
            'CORS_ALLOWED_ORIGINS': 'http://localhost:3000',
            'ADMIN_PASSWORD': 'test',
        }):
            results = run_startup_checks(mock_app)
            # v3.18+: 新增 ADMIN_PASSWORD 检查，共 5 项
            assert len(results) == 5
            assert all(r['level'] in ('OK', 'WARNING') for r in results)

    def test_missing_cors_in_production_raises_runtime_error(self):
        """TC-SC-041: 生产模式缺少 CORS 配置应抛出 RuntimeError"""
        from meta.core.startup_checks import run_startup_checks

        mock_app = MagicMock()

        clean_env = {
            'FLASK_DEBUG': 'false',
            'JWT_SECRET_KEY': 'a' * 32,
        }
        with patch.dict(os.environ, clean_env, clear=True):
            with pytest.raises(RuntimeError) as excinfo:
                run_startup_checks(mock_app)
            assert 'Production mode requires all startup security checks to pass' in str(excinfo.value)

    def test_missing_jwt_in_production_raises_runtime_error(self):
        """TC-SC-042: 生产模式缺少 JWT 密钥应抛出 RuntimeError"""
        from meta.core.startup_checks import run_startup_checks

        mock_app = MagicMock()

        clean_env = {
            'FLASK_DEBUG': 'false',
            'CORS_ALLOWED_ORIGINS': 'https://example.com',
        }
        with patch.dict(os.environ, clean_env, clear=True):
            with pytest.raises(RuntimeError) as excinfo:
                run_startup_checks(mock_app)
            assert 'Production mode requires all startup security checks to pass' in str(excinfo.value)

    def test_debug_mode_all_warnings_no_exception(self):
        """TC-SC-043: DEBUG 模式下即使有 WARNING 也不抛出异常"""
        from meta.core.startup_checks import run_startup_checks

        mock_app = MagicMock()

        with patch.dict(os.environ, {
            'FLASK_DEBUG': 'true',
        }, clear=False):
            env = os.environ.copy()
            env.pop('JWT_SECRET_KEY', None)
            env.pop('CORS_ALLOWED_ORIGINS', None)
            env.pop('ADMIN_PASSWORD', None)
            with patch.dict(os.environ, env, clear=True):
                os.environ.pop('JWT_SECRET_KEY', None)
                os.environ.pop('CORS_ALLOWED_ORIGINS', None)
                os.environ.pop('ADMIN_PASSWORD', None)
                results = run_startup_checks(mock_app)
                warnings = [r for r in results if r['level'] == 'WARNING']
                assert len(warnings) > 0
