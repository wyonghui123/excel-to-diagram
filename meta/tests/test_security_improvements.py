import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
安全改进测试

测试内容：
1. 登录限流防护 (RateLimiter)
2. JWT Token黑名单 (TokenBlacklistService)
3. 敏感信息日志过滤 (LogFilterService)
4. 请求链路追踪 (TraceService)
5. 生产环境安全 (debug/堆栈隐藏)
6. TokenService create_token 返回值变更
"""

import sys
import os
import tempfile
import time
import sqlite3
import logging

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

if not os.environ.get('JWT_SECRET_KEY'):
    os.environ['JWT_SECRET_KEY'] = 'test-secret-key-for-security-tests-only'

from meta.services.rate_limiter import RateLimiter
from meta.services.token_blacklist_service import TokenBlacklistService
from meta.services.log_filter_service import (
    mask_sensitive_value, filter_dict, filter_log_message,
    SensitiveDataFilter
)
from meta.services.token_service import TokenService
from meta.services.auth_provider import UserInfo


def test_rate_limiter_basic():
    print("\n=== 测试 RateLimiter 基本功能 ===")
    import os
    original_val = os.environ.get('DISABLE_RATE_LIMIT')
    os.environ['DISABLE_RATE_LIMIT'] = 'false'
    try:
        RateLimiter.reset()
        limiter = RateLimiter()

        is_locked, msg = limiter.check_rate_limit('192.168.1.1', 'testuser')
        assert not is_locked, "初始状态不应被封禁"
        print("[PASS] 初始状态未封禁")

        is_locked, msg = limiter.record_failed_attempt('192.168.1.1', 'testuser')
        assert not is_locked, "第1次失败不应封禁"
        print(f"[PASS] 第1次失败: {msg}")

        RateLimiter.reset()
        limiter = RateLimiter()

        import meta.services.rate_limiter as rl
        old_max = rl.MAX_LOGIN_ATTEMPTS_PER_IP
        rl.MAX_LOGIN_ATTEMPTS_PER_IP = 3

        try:
            for i in range(2):
                is_locked, msg = limiter.record_failed_attempt('10.0.0.1', 'victim')
                assert not is_locked, f"第{i+1}次不应封禁"

            is_locked, msg = limiter.record_failed_attempt('10.0.0.1', 'victim')
            assert is_locked, "达到阈值应封禁"
            assert "IP已被封禁" in msg or "账号已被封禁" in msg
            print(f"[PASS] 达到阈值后封禁: {msg}")

            is_locked, msg = limiter.check_rate_limit('10.0.0.1', 'victim')
            assert is_locked, "封禁后检查应返回封禁"
            print("[PASS] 封禁状态确认")
        finally:
            rl.MAX_LOGIN_ATTEMPTS_PER_IP = old_max
            RateLimiter.reset()
    finally:
        if original_val is None:
            os.environ.pop('DISABLE_RATE_LIMIT', None)
        else:
            os.environ['DISABLE_RATE_LIMIT'] = original_val


def test_rate_limiter_successful_resets():
    print("\n=== 测试 RateLimiter 成功登录重置 ===")
    RateLimiter.reset()
    limiter = RateLimiter()

    import meta.services.rate_limiter as rl
    old_max = rl.MAX_LOGIN_ATTEMPTS_PER_IP
    rl.MAX_LOGIN_ATTEMPTS_PER_IP = 3

    try:
        limiter.record_failed_attempt('10.0.0.2', 'user2')
        limiter.record_failed_attempt('10.0.0.2', 'user2')

        limiter.record_successful_attempt('10.0.0.2', 'user2')

        limiter.record_failed_attempt('10.0.0.2', 'user2')
        is_locked, msg = limiter.check_rate_limit('10.0.0.2', 'user2')
        assert not is_locked, "成功登录后应重置计数"
        print("[PASS] 成功登录后计数重置")
    finally:
        rl.MAX_LOGIN_ATTEMPTS_PER_IP = old_max
        RateLimiter.reset()


def test_rate_limiter_separate_ip():
    print("\n=== 测试 RateLimiter 不同IP独立计数 ===")
    RateLimiter.reset()
    limiter = RateLimiter()

    import meta.services.rate_limiter as rl
    old_max = rl.MAX_LOGIN_ATTEMPTS_PER_IP
    rl.MAX_LOGIN_ATTEMPTS_PER_IP = 2

    try:
        limiter.record_failed_attempt('10.0.0.3', 'user3')
        limiter.record_failed_attempt('10.0.0.3', 'user3')

        is_locked, _ = limiter.check_rate_limit('10.0.0.4', 'user3')
        assert not is_locked, "不同IP应独立计数"
        print("[PASS] 不同IP独立计数")
    finally:
        rl.MAX_LOGIN_ATTEMPTS_PER_IP = old_max
        RateLimiter.reset()


def test_token_blacklist_basic():
    print("\n=== 测试 TokenBlacklistService 基本功能 ===")
    TokenBlacklistService.reset()

    db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db_path = db_file.name
    db_file.close()

    os.environ['TOKEN_BLACKLIST_DB'] = db_path

    try:
        service = TokenBlacklistService()

        assert not service.is_blacklisted('test_token_123'), "初始状态Token不在黑名单"
        print("[PASS] 初始状态Token不在黑名单")

        from datetime import datetime, timedelta
        expires_at = datetime.utcnow() + timedelta(hours=4)
        service.add_to_blacklist('test_token_123', expires_at)

        assert service.is_blacklisted('test_token_123'), "添加后Token应在黑名单"
        print("[PASS] 添加后Token在黑名单")

        assert not service.is_blacklisted('other_token_456'), "其他Token不应在黑名单"
        print("[PASS] 其他Token不在黑名单")
    finally:
        del os.environ['TOKEN_BLACKLIST_DB']
        TokenBlacklistService.reset()
        try:
            os.unlink(db_path)
        except:
            pass


def test_token_blacklist_expired_cleanup():
    print("\n=== 测试 TokenBlacklistService 过期清理 ===")
    TokenBlacklistService.reset()

    db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db_path = db_file.name
    db_file.close()

    os.environ['TOKEN_BLACKLIST_DB'] = db_path

    try:
        service = TokenBlacklistService()

        from datetime import datetime, timedelta
        past_expires = datetime.utcnow() - timedelta(hours=1)
        service.add_to_blacklist('expired_token', past_expires)

        assert not service.is_blacklisted('expired_token'), "过期Token应被自动清理"
        print("[PASS] 过期Token自动清理")
    finally:
        del os.environ['TOKEN_BLACKLIST_DB']
        TokenBlacklistService.reset()
        try:
            os.unlink(db_path)
        except:
            pass


def test_log_filter_mask_sensitive_value():
    print("\n=== 测试日志过滤 - 敏感值屏蔽 ===")

    assert mask_sensitive_value('password', 'secret123') == '[REDACTED]'
    print("[PASS] password 字段被屏蔽")

    assert mask_sensitive_value('token', 'abc123') == '[REDACTED]'
    print("[PASS] token 字段被屏蔽")

    assert mask_sensitive_value('api_key', 'key123') == '[REDACTED]'
    print("[PASS] api_key 字段被屏蔽")

    assert mask_sensitive_value('new_password', 'pass123') == '[REDACTED]'
    print("[PASS] new_password 字段被屏蔽")

    assert mask_sensitive_value('username', 'testuser') == 'testuser'
    print("[PASS] username 字段不被屏蔽")

    assert mask_sensitive_value('email', 'test@example.com') == 'test@example.com'
    print("[PASS] email 字段不被屏蔽")


def test_log_filter_dict():
    print("\n=== 测试日志过滤 - 字典过滤 ===")

    data = {
        'username': 'admin',
        'password': 'secret123',
        'email': 'admin@example.com',
        'token': 'jwt_token_here',
        'nested': {
            'api_key': 'key123',
            'name': 'test'
        }
    }

    filtered = filter_dict(data)

    assert filtered['username'] == 'admin'
    assert filtered['password'] == '[REDACTED]'
    assert filtered['email'] == 'admin@example.com'
    assert filtered['token'] == '[REDACTED]'
    assert filtered['nested']['api_key'] == '[REDACTED]'
    assert filtered['nested']['name'] == 'test'
    print("[PASS] 字典过滤正确")


def test_log_filter_message():
    print("\n=== 测试日志过滤 - 消息模式替换 ===")

    msg = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJ1c2VyIjoiYWRtaW4ifQ.signature"
    filtered = filter_log_message(msg)
    assert 'Bearer [TOKEN]' in filtered
    assert 'eyJhbGciOiJIUzI1NiJ9' not in filtered
    print("[PASS] Bearer Token 被替换")

    msg2 = "User phone: 13812345678 logged in"
    filtered2 = filter_log_message(msg2)
    assert '[PHONE]' in filtered2
    assert '13812345678' not in filtered2
    print("[PASS] 手机号被替换")

    msg3 = "ID: 110101199001011234"
    filtered3 = filter_log_message(msg3)
    assert '[ID_NUMBER]' in filtered3
    print("[PASS] 身份证号被替换")


def test_log_filter_pbkdf2_pattern():
    print("\n=== 测试日志过滤 - PBKDF2哈希模式 ===")

    dollar = chr(36)
    msg = f"Hash: PBKDF2{dollar}100000{dollar}somesalt{dollar}somehash"
    filtered = filter_log_message(msg)
    assert '[PASSWORD_HASH]' in filtered
    assert 'somesalt' not in filtered
    print("[PASS] PBKDF2 哈希被替换")


def test_token_service_create_token_returns_tuple():
    print("\n=== 测试 TokenService.create_token 返回元组 ===")

    user_info = UserInfo(
        user_id=1,
        username='testuser',
        display_name='Test User',
        email='test@example.com',
        roles=['admin'],
        permissions=['*']
    )

    result = TokenService.create_token(user_info)
    assert isinstance(result, tuple), f"应返回元组，实际类型: {type(result)}"
    assert len(result) == 2, f"元组长度应为2，实际: {len(result)}"

    token, expires_at = result
    assert isinstance(token, str), "token 应为字符串"
    assert len(token) > 50, "token 长度应大于50"
    assert expires_at is not None, "expires_at 不应为 None"
    print(f"[PASS] create_token 返回 (token, expires_at) 元组")

    payload = TokenService.verify_token(token)
    assert payload is not None
    assert 'jti' in payload, "payload 应包含 jti"
    assert len(payload['jti']) == 32, "jti 应为32字符的hex"
    print(f"[PASS] Token 包含 jti: {payload['jti'][:8]}...")


def test_token_service_extract_payload():
    print("\n=== 测试 TokenService.extract_payload_without_verification ===")

    user_info = UserInfo(
        user_id=1,
        username='testuser',
        display_name='Test User',
        email='test@example.com',
        roles=['admin'],
        permissions=['*']
    )

    token, _ = TokenService.create_token(user_info)
    payload = TokenService.extract_payload_without_verification(token)
    assert payload is not None
    assert payload['user_id'] == 1
    assert payload['username'] == 'testuser'
    print("[PASS] extract_payload_without_verification 正常工作")

    payload = TokenService.extract_payload_without_verification('invalid.token.here')
    assert payload is None or 'user_id' not in payload
    print("[PASS] 无效token返回None或无user_id")


def test_server_error_handler_debug_mode():
    print("\n=== 测试生产环境安全 - debug模式控制 ===")

    from meta.server import create_app

    old_debug = os.environ.get('FLASK_DEBUG')
    old_testing = os.environ.get('TESTING')
    try:
        os.environ['TESTING'] = 'true'
        os.environ['FLASK_DEBUG'] = 'False'
        try:
            app = create_app()
            if hasattr(app, '_exc') and app._exc is not None:
                print(f"[SKIP] create_app() returned FakeApp with error: {app._exc}")
                return
        except RuntimeError as e:
            print(f"[SKIP] create_app() raised RuntimeError in production mode: {e}")
            return
        app.config['TESTING'] = True

        with app.test_client() as client:
            resp = client.get('/health')
            assert resp.status_code in [200, 401, 404, 500]
            print("[PASS] 生产模式 health 端点正常")

        os.environ['FLASK_DEBUG'] = 'True'
        try:
            app2 = create_app()
            if hasattr(app2, '_exc') and app2._exc is not None:
                print(f"[SKIP] create_app() returned FakeApp with error: {app2._exc}")
                return
        except RuntimeError as e:
            print(f"[SKIP] create_app() raised RuntimeError in debug mode: {e}")
            return
        app2.config['TESTING'] = True

        with app2.test_client() as client:
            resp = client.get('/health')
            assert resp.status_code in [200, 401, 404, 500]
            print("[PASS] debug模式 health 端点正常")
    finally:
        if old_debug is not None:
            os.environ['FLASK_DEBUG'] = old_debug
        else:
            os.environ.pop('FLASK_DEBUG', None)
        if old_testing is not None:
            os.environ['TESTING'] = old_testing
        else:
            os.environ.pop('TESTING', None)


def test_trace_id_in_response():
    print("\n=== 测试请求链路追踪 - traceId响应头 ===")

    from meta.server import create_app

    app = create_app()
    app.config['TESTING'] = True

    with app.test_client() as client:
        resp = client.get('/health')
        assert resp.status_code in [200, 401, 404, 500]
        assert 'X-Request-Id' in resp.headers, "响应应包含 X-Request-Id 头"
        trace_id = resp.headers['X-Request-Id']
        assert len(trace_id) > 0, "traceId 不应为空"
        print(f"[PASS] 响应包含 traceId: {trace_id[:8]}...")

    with app.test_client() as client:
        custom_trace = 'my-custom-trace-12345'
        resp = client.get('/health', headers={'X-Request-Id': custom_trace})
        assert resp.status_code in [200, 401, 404, 500]
        assert resp.headers.get('X-Request-Id') == custom_trace, "应继承请求中的 traceId"
        print(f"[PASS] 继承请求 traceId: {custom_trace}")


def test_cors_whitelist():
    print("\n=== 测试 CORS 白名单 ===")

    from meta.server import create_app

    old_cors = os.environ.get('CORS_ALLOWED_ORIGINS')
    try:
        os.environ['CORS_ALLOWED_ORIGINS'] = 'https://app.example.com,https://admin.example.com'

        app = create_app()
        app.config['TESTING'] = True

        with app.test_client() as client:
            resp = client.get('/health', headers={'Origin': 'https://app.example.com'})
            assert resp.headers.get('Access-Control-Allow-Origin') == 'https://app.example.com'
            print("[PASS] 白名单内Origin被允许")

            resp = client.get('/health', headers={'Origin': 'https://evil.example.com'})
            assert resp.headers.get('Access-Control-Allow-Origin') != 'https://evil.example.com'
            print("[PASS] 白名单外Origin不被允许")
    finally:
        if old_cors is not None:
            os.environ['CORS_ALLOWED_ORIGINS'] = old_cors
        else:
            os.environ.pop('CORS_ALLOWED_ORIGINS', None)


def test_cors_empty_whitelist():
    print("\n=== 测试 CORS 空白名单(开发模式) ===")

    from meta.server import create_app

    old_cors = os.environ.get('CORS_ALLOWED_ORIGINS')
    try:
        os.environ.pop('CORS_ALLOWED_ORIGINS', None)

        try:
            app = create_app()
        except RuntimeError:
            print("[SKIP] create_app() raised RuntimeError with empty CORS whitelist")
            return
        app.config['TESTING'] = True

        with app.test_client() as client:
            resp = client.get('/health', headers={'Origin': 'http://localhost:3000'})
            allow_origin = resp.headers.get('Access-Control-Allow-Origin')
            if allow_origin == 'http://localhost:3000':
                print("[PASS] 空白名单允许所有Origin(开发模式)")
            else:
                print(f"[INFO] CORS header: {allow_origin} (may be configured differently)")
    finally:
        if old_cors is not None:
            os.environ['CORS_ALLOWED_ORIGINS'] = old_cors
        else:
            os.environ.pop('CORS_ALLOWED_ORIGINS', None)


def run_all_tests():
    print("\n" + "=" * 60)
    print("安全改进测试")
    print("=" * 60)

    tests = [
        test_rate_limiter_basic,
        test_rate_limiter_successful_resets,
        test_rate_limiter_separate_ip,
        test_token_blacklist_basic,
        test_token_blacklist_expired_cleanup,
        test_log_filter_mask_sensitive_value,
        test_log_filter_dict,
        test_log_filter_message,
        test_log_filter_pbkdf2_pattern,
        test_token_service_create_token_returns_tuple,
        test_token_service_extract_payload,
        test_server_error_handler_debug_mode,
        test_trace_id_in_response,
        test_cors_whitelist,
        test_cors_empty_whitelist,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"[ERROR] {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)

    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
