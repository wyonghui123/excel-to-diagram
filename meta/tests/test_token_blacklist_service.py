# -*- coding: utf-8 -*-
"""
SVC-006: token_blacklist_service 单元测试 (5 用例)

[NEW] 2026-06-07 批次: 补齐 TokenBlacklistService 单例测试
- add_to_blacklist: 插入 token
- is_blacklisted: True/False
- hash 一致性: 同 token → 同 hash
- 不同 token → 不同 hash
- 重置后不误判
"""
import os
import time
from datetime import datetime, timedelta
import pytest

pytestmark = pytest.mark.unit


class TestTokenBlacklistService:
    """TokenBlacklistService 单元测试 (SVC-006)"""

    def test_add_and_check_blacklist(self):
        """add + is_blacklisted 完整流程"""
        from meta.services.token_blacklist_service import TokenBlacklistService
        svc = TokenBlacklistService()
        token = f'test_token_{int(time.time())}'
        expires = datetime.utcnow() + timedelta(hours=1)
        # 添加到黑名单
        svc.add_to_blacklist(token, expires)
        # 验证
        assert svc.is_blacklisted(token) is True

    def test_token_not_in_blacklist(self):
        """未加入黑名单的 token 返回 False"""
        from meta.services.token_blacklist_service import TokenBlacklistService
        svc = TokenBlacklistService()
        random_token = f'random_{int(time.time() * 1000)}'
        assert svc.is_blacklisted(random_token) is False

    def test_hash_consistency(self):
        """同 token 多次 hash 一致"""
        from meta.services.token_blacklist_service import TokenBlacklistService
        svc = TokenBlacklistService()
        h1 = svc._hash_token('consistent_token')
        h2 = svc._hash_token('consistent_token')
        assert h1 == h2
        # SHA256 hex digest = 64 字符
        assert len(h1) == 64

    def test_different_tokens_have_different_hashes(self):
        """不同 token → 不同 hash"""
        from meta.services.token_blacklist_service import TokenBlacklistService
        svc = TokenBlacklistService()
        h1 = svc._hash_token('token_a')
        h2 = svc._hash_token('token_b')
        assert h1 != h2

    def test_expired_token_not_blacklisted(self):
        """过期 token 被自动清理, 不再黑名单"""
        from meta.services.token_blacklist_service import TokenBlacklistService
        svc = TokenBlacklistService()
        token = f'expired_{int(time.time())}'
        # 过期时间 = 1 小时前
        past = datetime.utcnow() - timedelta(hours=1)
        svc.add_to_blacklist(token, past)
        # 验证: is_blacklisted 内部会清理过期项, 应返回 False
        assert svc.is_blacklisted(token) is False
