# -*- coding: utf-8 -*-
"""
认证服务测试

合并以下测试文件:
- test_auth_provider.py (认证提供者)
- test_token_blacklist_service.py (Token 黑名单服务)
- test_rate_limiter.py (限流器)

测试范围:
- 密码哈希与验证
- Token 黑名单管理
- 限流防护机制
"""

import pytest
import os
import tempfile
import sqlite3
import hashlib
import time
from datetime import datetime, timedelta

pytestmark = pytest.mark.integration


# ==================== 认证提供者测试 ====================

class TestAuthProvider:
    """认证提供者测试 - 密码哈希与验证"""

    def test_generate_salt_length(self):
        """Salt 生成长度验证"""
        from meta.services.auth_provider import _generate_salt
        salt = _generate_salt(16)
        assert len(salt) == 32

    def test_generate_salt_randomness(self):
        """Salt 生成随机性"""
        from meta.services.auth_provider import _generate_salt
        salt1 = _generate_salt()
        salt2 = _generate_salt()
        assert salt1 != salt2

    def test_hash_password_pbdkdf2_format(self):
        """PBKDF2 哈希格式"""
        from meta.services.auth_provider import _hash_password_pbdkdf2
        hashed = _hash_password_pbdkdf2('testpassword')
        parts = hashed.split('$')
        assert parts[0] == 'PBKDF2'
        assert len(parts) == 4
        assert parts[1] == '100000'

    def test_hash_password_pbdkdf2_with_salt(self):
        """PBKDF2 自定义 Salt"""
        from meta.services.auth_provider import _hash_password_pbdkdf2
        salt = 'customsalt123'
        hashed = _hash_password_pbdkdf2('testpassword', salt=salt)
        parts = hashed.split('$')
        assert parts[2] == salt

    def test_verify_password_pbdkdf2_correct(self):
        """正确密码验证"""
        from meta.services.auth_provider import _hash_password_pbdkdf2, _verify_password
        hashed = _hash_password_pbdkdf2('mypassword')
        assert _verify_password('mypassword', hashed) is True

    def test_verify_password_pbdkdf2_wrong(self):
        """错误密码验证"""
        from meta.services.auth_provider import _hash_password_pbdkdf2, _verify_password
        hashed = _hash_password_pbdkdf2('mypassword')
        assert _verify_password('wrongpassword', hashed) is False

    def test_verify_password_sha256_legacy(self):
        """SHA256 遗留密码验证"""
        from meta.services.auth_provider import _verify_password
        password = 'legacypassword'
        legacy_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
        assert _verify_password(password, legacy_hash) is True

    def test_validate_password_strength_valid(self):
        """密码强度验证 - 有效密码"""
        from meta.services.auth_provider import validate_password_strength
        is_valid, error_msg = validate_password_strength('Password1')
        assert is_valid is True
        assert error_msg == ''

    def test_validate_password_strength_too_short(self):
        """密码强度验证 - 太短"""
        from meta.services.auth_provider import validate_password_strength
        is_valid, error_msg = validate_password_strength('Pwd1')
        assert is_valid is False
        assert '长度' in error_msg

    def test_validate_password_strength_no_digit(self):
        """密码强度验证 - 无数字"""
        from meta.services.auth_provider import validate_password_strength
        is_valid, error_msg = validate_password_strength('Password')
        assert is_valid is False
        assert '数字' in error_msg


# ==================== Token 黑名单服务测试 ====================

class TestTokenBlacklistService:
    """Token 黑名单服务测试"""

    @pytest.fixture(autouse=True)
    def setup_temp_db(self):
        """设置临时数据库"""
        from meta.services.token_blacklist_service import TokenBlacklistService
        TokenBlacklistService.reset()
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        os.environ['TOKEN_BLACKLIST_DB'] = db_path
        TokenBlacklistService.reset()
        yield db_path
        TokenBlacklistService.reset()
        os.environ.pop('TOKEN_BLACKLIST_DB', None)
        if os.path.exists(db_path):
            os.unlink(db_path)

    def test_singleton_pattern(self):
        """单例模式验证"""
        from meta.services.token_blacklist_service import TokenBlacklistService
        svc1 = TokenBlacklistService()
        svc2 = TokenBlacklistService()
        assert svc1 is svc2

    def test_add_to_blacklist(self, setup_temp_db):
        """添加 Token 到黑名单"""
        from meta.services.token_blacklist_service import TokenBlacklistService
        svc = TokenBlacklistService()
        token = 'test-token-123'
        expires_at = datetime.utcnow() + timedelta(hours=1)
        svc.add_to_blacklist(token, expires_at)
        conn = sqlite3.connect(setup_temp_db)
        cursor = conn.execute("SELECT COUNT(*) FROM token_blacklist")
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 1

    def test_is_blacklisted_true(self):
        """Token 在黑名单中"""
        from meta.services.token_blacklist_service import TokenBlacklistService
        svc = TokenBlacklistService()
        token = 'test-token-456'
        expires_at = datetime.utcnow() + timedelta(hours=1)
        svc.add_to_blacklist(token, expires_at)
        assert svc.is_blacklisted(token) is True

    def test_is_blacklisted_false(self):
        """Token 不在黑名单中"""
        from meta.services.token_blacklist_service import TokenBlacklistService
        svc = TokenBlacklistService()
        assert svc.is_blacklisted('nonexistent-token') is False

    def test_add_and_check_blacklisted(self):
        """添加并检查黑名单"""
        from meta.services.token_blacklist_service import TokenBlacklistService
        svc = TokenBlacklistService()
        token = 'test-token-789'
        expires_at = datetime.utcnow() + timedelta(hours=1)
        svc.add_to_blacklist(token, expires_at)
        assert svc.is_blacklisted(token) is True
        assert svc.is_blacklisted('other-token') is False

    def test_expired_tokens_auto_cleanup(self):
        """过期 Token 自动清理"""
        from meta.services.token_blacklist_service import TokenBlacklistService
        svc = TokenBlacklistService()
        token = 'expired-token'
        expires_at = datetime.utcnow() - timedelta(hours=1)
        svc.add_to_blacklist(token, expires_at)
        assert svc.is_blacklisted(token) is False

    def test_token_hashed_not_stored_plaintext(self, setup_temp_db):
        """Token 哈希存储"""
        from meta.services.token_blacklist_service import TokenBlacklistService
        svc = TokenBlacklistService()
        token = 'plaintext-token-value'
        expires_at = datetime.utcnow() + timedelta(hours=1)
        svc.add_to_blacklist(token, expires_at)
        conn = sqlite3.connect(setup_temp_db)
        cursor = conn.execute("SELECT token_hash FROM token_blacklist")
        row = cursor.fetchone()
        conn.close()
        assert row is not None
        assert row[0] != token
        assert len(row[0]) == 64

    def test_reset_singleton(self):
        """重置单例"""
        from meta.services.token_blacklist_service import TokenBlacklistService
        svc1 = TokenBlacklistService()
        TokenBlacklistService.reset()
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path2 = f.name
        old_db = os.environ.get('TOKEN_BLACKLIST_DB')
        os.environ['TOKEN_BLACKLIST_DB'] = db_path2
        svc2 = TokenBlacklistService()
        assert svc1 is not svc2
        os.environ.pop('TOKEN_BLACKLIST_DB', None)
        if old_db:
            os.environ['TOKEN_BLACKLIST_DB'] = old_db
        if os.path.exists(db_path2):
            os.unlink(db_path2)


# ==================== 限流器测试 ====================

class TestRateLimiter:
    """限流器测试"""

    @pytest.fixture(autouse=True)
    def reset_limiter(self):
        """重置限流器"""
        from meta.services.rate_limiter import RateLimiter
        RateLimiter.reset()
        yield
        RateLimiter.reset()
        os.environ.pop('DISABLE_RATE_LIMIT', None)

    def test_singleton_pattern(self):
        """单例模式验证"""
        from meta.services.rate_limiter import RateLimiter
        limiter1 = RateLimiter()
        limiter2 = RateLimiter()
        assert limiter1 is limiter2

    def test_record_failed_attempt_under_limit(self):
        """失败尝试未超过限制"""
        from meta.services.rate_limiter import RateLimiter
        limiter = RateLimiter()
        is_locked, message = limiter.record_failed_attempt('127.0.0.1', 'testuser')
        assert is_locked is False
        assert message is not None

    def test_record_failed_attempt_exceeds_limit_triggers_lockout(self):
        """失败尝试超过限制触发封禁"""
        from meta.services.rate_limiter import RateLimiter
        limiter = RateLimiter()
        for i in range(9):
            limiter.record_failed_attempt('127.0.0.1', 'testuser')
        is_locked, message = limiter.record_failed_attempt('127.0.0.1', 'testuser')
        assert is_locked is True
        assert '封禁' in message

    def test_record_successful_attempt_clears_records(self):
        """成功登录清除失败记录"""
        from meta.services.rate_limiter import RateLimiter
        limiter = RateLimiter()
        limiter.record_failed_attempt('127.0.0.1', 'testuser')
        limiter.record_successful_attempt('127.0.0.1', 'testuser')
        for i in range(9):
            limiter.record_failed_attempt('127.0.0.1', 'testuser')
        is_locked, message = limiter.record_failed_attempt('127.0.0.1', 'testuser')
        assert is_locked is True

    def test_check_rate_limit_not_locked(self):
        """检查限流 - 未锁定"""
        from meta.services.rate_limiter import RateLimiter
        limiter = RateLimiter()
        is_locked, message = limiter.check_rate_limit('127.0.0.1', 'testuser')
        assert is_locked is False
        assert message is None

    def test_check_rate_limit_locked_out(self):
        """检查限流 - 已锁定"""
        from meta.services.rate_limiter import RateLimiter
        limiter = RateLimiter()
        for i in range(10):
            limiter.record_failed_attempt('127.0.0.1', 'testuser')
        is_locked, message = limiter.check_rate_limit('127.0.0.1', 'testuser')
        assert is_locked is True
        assert message is not None

    def test_different_ips_independent(self):
        """不同 IP 独立计数"""
        from meta.services.rate_limiter import RateLimiter
        limiter = RateLimiter()
        for i in range(10):
            limiter.record_failed_attempt('192.168.1.1', f'user_{i}')
        is_locked, message = limiter.check_rate_limit('192.168.1.2', 'other_user')
        assert is_locked is False

    def test_different_usernames_independent(self):
        """不同用户名独立计数"""
        from meta.services.rate_limiter import RateLimiter
        limiter = RateLimiter()
        for i in range(10):
            limiter.record_failed_attempt(f'10.0.0.{i}', 'same_user')
        is_locked, message = limiter.check_rate_limit('10.0.0.100', 'different_user')
        assert is_locked is False

    def test_auto_cleanup_expired_records(self):
        """自动清理过期记录"""
        from meta.services.rate_limiter import RateLimiter
        limiter = RateLimiter()
        now = time.time()
        limiter._ip_attempts['127.0.0.1'] = [now - 400]
        limiter._auto_cleanup()
        assert '127.0.0.1' not in limiter._ip_attempts

    def test_disable_rate_limit_env(self):
        """禁用限流环境变量"""
        from meta.services.rate_limiter import RateLimiter
        os.environ['DISABLE_RATE_LIMIT'] = 'true'
        limiter = RateLimiter()
        is_locked, message = limiter.record_failed_attempt('127.0.0.1', 'testuser')
        assert is_locked is False
        assert message is None
        is_locked, message = limiter.check_rate_limit('127.0.0.1', 'testuser')
        assert is_locked is False
        assert message is None
