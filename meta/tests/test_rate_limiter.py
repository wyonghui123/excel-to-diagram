# -*- coding: utf-8 -*-
"""
SVC-005: rate_limiter 单元测试 (5 用例)

[NEW] 2026-06-07 批次: 补齐 RateLimiter 单例测试
- 单例模式
- record_failed_attempt: 累计失败次数, 达到阈值后封禁
- check_rate_limit: 封禁中返回 True
- record_successful_attempt: 重置计数
- clear / reset: 清空所有状态
"""
import os
import time
import pytest

pytestmark = pytest.mark.unit


class TestRateLimiter:
    """RateLimiter 单元测试 (SVC-005)"""

    def setup_method(self):
        """每个测试前清空 limiter 状态 + 移除可能影响测试的 env var"""
        import os
        os.environ.pop('DISABLE_RATE_LIMIT', None)
        from meta.services.rate_limiter import RateLimiter
        RateLimiter.reset()

    def test_singleton_pattern(self):
        """RateLimiter 是单例"""
        from meta.services.rate_limiter import RateLimiter
        s1 = RateLimiter()
        s2 = RateLimiter()
        assert s1 is s2

    def test_record_failed_attempt_no_lockout_under_threshold(self):
        """未达阈值前不封禁 (使用默认阈值 10, 失败 5 次)"""
        from meta.services.rate_limiter import RateLimiter
        rl = RateLimiter()
        rl.clear()
        # 失败 5 次 (默认阈值 10, 不会触发封禁)
        for _ in range(5):
            is_locked, msg = rl.record_failed_attempt('1.1.1.1', 'user_a')
            assert is_locked is False
        # 应有 5 次失败记录
        assert len(rl._ip_attempts['1.1.1.1']) == 5
        assert len(rl._username_attempts['user_a']) == 5

    def test_record_failed_attempt_locks_at_threshold(self):
        """达到默认阈值 (10) 后封禁 IP"""
        from meta.services.rate_limiter import RateLimiter
        rl = RateLimiter()
        rl.clear()
        # 失败 10 次 (默认阈值 MAX_LOGIN_ATTEMPTS_PER_IP=10)
        is_locked = False
        for _ in range(10):
            is_locked, _ = rl.record_failed_attempt('2.2.2.2', 'user_b')
        # 第 10 次触发封禁
        assert is_locked is True
        # 立即检查, 应在封禁中
        is_locked_now, msg = rl.check_rate_limit('2.2.2.2', 'user_b')
        assert is_locked_now is True
        assert '封禁' in msg
        # lockout 已记录
        assert '2.2.2.2' in rl._ip_lockouts

    def test_record_successful_attempt_resets_count(self):
        """record_successful_attempt 清空计数"""
        from meta.services.rate_limiter import RateLimiter
        rl = RateLimiter()
        rl.clear()
        # 失败 5 次
        for _ in range(5):
            rl.record_failed_attempt('3.3.3.3', 'user_c')
        assert len(rl._ip_attempts['3.3.3.3']) == 5
        # 成功 → 重置
        rl.record_successful_attempt('3.3.3.3', 'user_c')
        # 计数应清空
        assert '3.3.3.3' not in rl._ip_attempts
        assert 'user_c' not in rl._username_attempts

    def test_disable_rate_limit_via_env(self):
        """DISABLE_RATE_LIMIT=1 时 record_failed_attempt 不封禁"""
        from meta.services.rate_limiter import RateLimiter
        rl = RateLimiter()
        rl.clear()
        # 用 env 临时启用
        os.environ['DISABLE_RATE_LIMIT'] = '1'
        try:
            # 即使失败 15 次, DISABLE_RATE_LIMIT=1 时不封禁
            is_locked = False
            for _ in range(15):
                is_locked, _ = rl.record_failed_attempt('4.4.4.4', 'user_d')
            assert is_locked is False
            is_locked_now, _ = rl.check_rate_limit('4.4.4.4', 'user_d')
            assert is_locked_now is False
        finally:
            os.environ.pop('DISABLE_RATE_LIMIT', None)
