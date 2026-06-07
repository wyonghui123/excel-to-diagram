# -*- coding: utf-8 -*-
"""
[FR-023] dev-login 生产环境返回 404 测试
验证不同 FLASK_ENV / FLASK_PRODUCTION 配置下的 dev-login 行为
"""
import os
import sys
import pytest


class TestDevLoginProduction:
    """
    验证 dev-login 在生产环境返回 404,在开发环境可用
    """

    def test_is_production_helper_flask_env_prod(self, monkeypatch):
        """FLASK_ENV=production → _is_production() = True"""
        from meta.api import auth_api
        monkeypatch.setenv('FLASK_ENV', 'production')
        monkeypatch.delenv('FLASK_PRODUCTION', raising=False)
        assert auth_api._is_production() is True

    def test_is_production_helper_flask_env_staging(self, monkeypatch):
        """FLASK_ENV=staging → _is_production() = True"""
        from meta.api import auth_api
        monkeypatch.setenv('FLASK_ENV', 'staging')
        monkeypatch.delenv('FLASK_PRODUCTION', raising=False)
        assert auth_api._is_production() is True

    def test_is_production_helper_flask_production_true(self, monkeypatch):
        """FLASK_PRODUCTION=true → _is_production() = True"""
        from meta.api import auth_api
        monkeypatch.delenv('FLASK_ENV', raising=False)
        monkeypatch.setenv('FLASK_PRODUCTION', 'true')
        assert auth_api._is_production() is True

    def test_is_production_helper_dev(self, monkeypatch):
        """FLASK_ENV=development → _is_production() = False"""
        from meta.api import auth_api
        monkeypatch.setenv('FLASK_ENV', 'development')
        monkeypatch.delenv('FLASK_PRODUCTION', raising=False)
        assert auth_api._is_production() is False

    def test_is_production_helper_unset(self, monkeypatch):
        """FLASK_ENV 未设置 → _is_production() = False"""
        from meta.api import auth_api
        monkeypatch.delenv('FLASK_ENV', raising=False)
        monkeypatch.delenv('FLASK_PRODUCTION', raising=False)
        assert auth_api._is_production() is False

    def test_is_production_helper_dev_value(self, monkeypatch):
        """FLASK_ENV=dev → _is_production() = False"""
        from meta.api import auth_api
        monkeypatch.setenv('FLASK_ENV', 'dev')
        monkeypatch.delenv('FLASK_PRODUCTION', raising=False)
        assert auth_api._is_production() is False


class TestDevLoginEndpoint:
    """
    验证 /api/v1/auth/dev-login 端点行为
    需要 Flask test_client
    """

    @pytest.fixture
    def app(self, monkeypatch):
        """创建测试 app,使用临时 db"""
        # 设置开发环境
        monkeypatch.setenv('FLASK_ENV', 'development')
        monkeypatch.delenv('FLASK_PRODUCTION', raising=False)

        from flask import Flask
        from meta.api.auth_api import auth_bp

        app = Flask(__name__)
        app.config['TESTING'] = True
        # [TEST] dev-login 写 session 需要 secret_key
        app.secret_key = 'test-secret-key-for-dev-login-prod-test'
        app.register_blueprint(auth_bp)
        return app

    @pytest.fixture
    def client(self, app):
        return app.test_client()

    def test_dev_login_production_returns_404(self, app, monkeypatch):
        """FLASK_ENV=production → dev-login 返回 404"""
        # 重新设置生产环境
        monkeypatch.setenv('FLASK_ENV', 'production')
        # 重新注册路由(因为 _is_production 是在请求时检查)
        with app.test_client() as c:
            resp = c.get('/api/v1/auth/dev-login?username=admin')
            assert resp.status_code == 404, \
                f"生产环境 dev-login 应返回 404,实际 {resp.status_code}"

    def test_dev_login_staging_returns_404(self, app, monkeypatch):
        """FLASK_ENV=staging → dev-login 返回 404"""
        monkeypatch.setenv('FLASK_ENV', 'staging')
        with app.test_client() as c:
            resp = c.get('/api/v1/auth/dev-login?username=admin')
            assert resp.status_code == 404

    def test_dev_login_flask_production_flag(self, app, monkeypatch):
        """FLASK_PRODUCTION=true → dev-login 返回 404"""
        monkeypatch.delenv('FLASK_ENV', raising=False)
        monkeypatch.setenv('FLASK_PRODUCTION', 'true')
        with app.test_client() as c:
            resp = c.get('/api/v1/auth/dev-login?username=admin')
            assert resp.status_code == 404

    def test_dev_login_development_does_not_404(self, app, monkeypatch):
        """FLASK_ENV=development → dev-login 不应返回 404
        (可能返回 200, 404 用户不存在, 或 403 视具体配置而定)
        但绝不应返回 404 (因为 404 意味着端点隐藏)"""
        monkeypatch.setenv('FLASK_ENV', 'development')
        monkeypatch.delenv('FLASK_PRODUCTION', raising=False)
        with app.test_client() as c:
            resp = c.get('/api/v1/auth/dev-login?username=admin')
            # 关键是: 端点可达,不是 404
            # 实际可能 200 (用户存在), 404 (用户不存在), 500 (db 错) 等
            assert resp.status_code != 404 or 'Not Found' not in resp.get_data(as_text=True), \
                f"开发环境 dev-login 不应因生产阻断返回 404,实际 {resp.status_code}"
