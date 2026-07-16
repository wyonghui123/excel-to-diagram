# -*- coding: utf-8 -*-
"""
登录限流防护服务

防止暴力破解攻击：
- 基于IP的限流：同一IP在时间窗口内失败次数超限则封禁
- 基于用户名的限流：同一用户名在时间窗口内失败次数超限则封禁
- 支持环境变量配置阈值和时间窗口
"""

import os
import time
import threading
from collections import defaultdict
from datetime import datetime, timedelta

MAX_LOGIN_ATTEMPTS_PER_IP = int(os.environ.get('MAX_LOGIN_ATTEMPTS_PER_IP', '10'))
LOGIN_LOCKOUT_DURATION_MINUTES = int(os.environ.get('LOGIN_LOCKOUT_DURATION_MINUTES', '15'))
LOGIN_ATTEMPT_WINDOW_MINUTES = int(os.environ.get('LOGIN_ATTEMPT_WINDOW_MINUTES', '5'))

class RateLimiter:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        self._ip_attempts = defaultdict(list)
        self._username_attempts = defaultdict(list)
        self._ip_lockouts = {}
        self._username_lockouts = {}
        self._cleanup_lock = threading.Lock()

    def _cleanup_expired(self, attempts_dict, lockouts_dict, now):
        expired_keys = []
        for key in attempts_dict:
            attempts_dict[key] = [t for t in attempts_dict[key] if now - t < LOGIN_ATTEMPT_WINDOW_MINUTES * 60]
            if not attempts_dict[key]:
                expired_keys.append(key)
        for key in expired_keys:
            del attempts_dict[key]

        expired_lockouts = []
        for key, unlock_time in lockouts_dict.items():
            if now >= unlock_time:
                expired_lockouts.append(key)
        for key in expired_lockouts:
            del lockouts_dict[key]

    def _auto_cleanup(self):
        with self._cleanup_lock:
            now = time.time()
            self._cleanup_expired(self._ip_attempts, self._ip_lockouts, now)
            self._cleanup_expired(self._username_attempts, self._username_lockouts, now)

    def _is_locked_out(self, ip, username, now):
        if ip in self._ip_lockouts:
            if now < self._ip_lockouts[ip]:
                return True, f"IP已被封禁，请{self._get_remaining_minutes(self._ip_lockouts[ip])}分钟后重试"
        if username in self._username_lockouts:
            if now < self._username_lockouts[username]:
                return True, f"账号已被封禁，请{self._get_remaining_minutes(self._username_lockouts[username])}分钟后重试"
        return False, None

    def _get_remaining_minutes(self, unlock_time):
        remaining = unlock_time - time.time()
        return max(1, int(remaining / 60) + 1)

    def record_failed_attempt(self, ip, username):
        if os.environ.get('DISABLE_RATE_LIMIT', '').lower() in ('1', 'true', 'yes'):
            return False, None
        self._auto_cleanup()
        now = time.time()

        self._ip_attempts[ip].append(now)
        self._username_attempts[username].append(now)

        ip_count = len(self._ip_attempts[ip])
        username_count = len(self._username_attempts[username])

        lockout_until = now + LOGIN_LOCKOUT_DURATION_MINUTES * 60

        if ip_count >= MAX_LOGIN_ATTEMPTS_PER_IP:
            self._ip_lockouts[ip] = lockout_until
            return True, f"失败次数过多，IP已被封禁{LOGIN_LOCKOUT_DURATION_MINUTES}分钟"

        if username_count >= MAX_LOGIN_ATTEMPTS_PER_IP:
            self._username_lockouts[username] = lockout_until
            return True, f"失败次数过多，账号已被封禁{LOGIN_LOCKOUT_DURATION_MINUTES}分钟"

        remaining_ip = MAX_LOGIN_ATTEMPTS_PER_IP - ip_count
        remaining_username = MAX_LOGIN_ATTEMPTS_PER_IP - username_count
        return False, f"还剩{min(remaining_ip, remaining_username)}次尝试机会"

    def record_successful_attempt(self, ip, username):
        if os.environ.get('DISABLE_RATE_LIMIT', '').lower() in ('1', 'true', 'yes'):
            return
        self._ip_attempts.pop(ip, None)
        self._username_attempts.pop(username, None)

    def check_rate_limit(self, ip, username):
        if os.environ.get('DISABLE_RATE_LIMIT', '').lower() in ('1', 'true', 'yes'):
            return False, None
        self._auto_cleanup()
        now = time.time()
        return self._is_locked_out(ip, username, now)

    def clear(self):
        """清除所有速率限制状态（保持单例引用）"""
        with self._cleanup_lock:
            self._ip_attempts.clear()
            self._username_attempts.clear()
            self._ip_lockouts.clear()
            self._username_lockouts.clear()

    @classmethod
    def reset(cls):
        """重置速率限制器（清除所有状态）"""
        if cls._instance is not None:
            cls._instance.clear()


rate_limiter = RateLimiter()