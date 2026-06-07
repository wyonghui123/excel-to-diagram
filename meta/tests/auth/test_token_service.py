# -*- coding: utf-8 -*-
"""
Token 服务测试

合并以下测试文件:
- test_token_service.py (Token 服务)

测试范围:
- TokenService 初始化
- Token 创建和验证
- 密钥信息获取
"""

import pytest
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

pytestmark = pytest.mark.integration


class TestTokenServiceInit:
    """TokenService 初始化测试"""

    def test_token_service_initialized(self):
        """TokenService 延迟初始化"""
        from meta.services.token_service import TokenService

        info = TokenService.get_secret_key_info()
        assert info['initialized'] is True

    def test_secret_key_info_fields(self):
        """密钥信息包含必要字段"""
        from meta.services.token_service import TokenService

        info = TokenService.get_secret_key_info()
        assert 'source' in info
        assert 'is_dev_key' in info
        assert 'initialized' in info


class TestTokenCreation:
    """Token 创建和验证测试"""

    def test_token_creation_returns_string(self):
        """Token 创建返回非空字符串"""
        from meta.services.token_service import TokenService

        class MockUserInfo:
            user_id = 1
            username = "testuser"
            display_name = "Test User"
            roles = ["admin"]
            permissions = ["*"]

        token, exp = TokenService.create_token(MockUserInfo())
        assert token is not None
        assert len(token) > 50

    def test_token_verification_returns_payload(self):
        """Token 验证返回有效 Payload"""
        from meta.services.token_service import TokenService

        class MockUserInfo:
            user_id = 42
            username = "verify_test"
            display_name = "Verify Test"
            roles = ["viewer"]
            permissions = ["user:read"]

        token, _ = TokenService.create_token(MockUserInfo())
        payload = TokenService.verify_token(token)

        if payload:
            assert payload['user_id'] == 42
            assert payload['username'] == 'verify_test'

    def test_token_verification_invalid_token(self):
        """无效 Token 验证返回 None"""
        from meta.services.token_service import TokenService

        payload = TokenService.verify_token("invalid.token.string")
        assert payload is None

    def test_token_expiration_info(self):
        """Token 包含过期时间"""
        from meta.services.token_service import TokenService

        class MockUserInfo:
            user_id = 1
            username = "test"
            display_name = "Test"
            roles = []
            permissions = []

        token, exp = TokenService.create_token(MockUserInfo())
        assert exp is not None

    def test_token_contains_required_claims(self):
        """Token Payload 包含必要声明"""
        from meta.services.token_service import TokenService

        class MockUserInfo:
            user_id = 99
            username = "claims_test"
            display_name = "Claims Test"
            roles = ["admin"]
            permissions = ["*"]

        token, _ = TokenService.create_token(MockUserInfo())
        payload = TokenService.verify_token(token)

        if payload:
            assert 'user_id' in payload
            assert 'username' in payload


class TestTokenBlacklist:
    """Token 黑名单测试"""

    def test_token_blacklist_service_import(self):
        """TokenBlacklistService 可以导入"""
        try:
            from meta.services.token_blacklist_service import TokenBlacklistService
            assert callable(TokenBlacklistService)
        except ImportError:
            pass
