# -*- coding: utf-8 -*-
"""
JWT Token黑名单服务

登出后Token失效 - 通过在数据库中存储Token哈希实现
"""

import hashlib
import threading
import os
import logging
from datetime import datetime
from typing import Optional

from meta.core.safe_connect import safe_connect_for_read, safe_connect_for_write

logger = logging.getLogger(__name__)

class TokenBlacklistService:
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
        self._db_path = os.environ.get('TOKEN_BLACKLIST_DB')
        if not self._db_path:
            schema_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self._db_path = os.path.join(schema_dir, 'token_blacklist.db')
        self._ensure_table()

    def _ensure_table(self):
        # [V007.41 BUG-FIX] 用 safe_connect_for_write 统一 L0 入口
        with safe_connect_for_write(self._db_path, force_no_tx=True) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS token_blacklist (
                    token_hash TEXT PRIMARY KEY,
                    blacklisted_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_expires_at ON token_blacklist(expires_at)')
            conn.commit()

    def _hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode('utf-8')).hexdigest()

    def _cleanup_expired(self):
        # [V007.41 BUG-FIX] 用 safe_connect_for_write 统一 L0 入口
        # 注意: cleanup 每次请求都触发, 用 force_no_tx=True 保持独立轻量事务
        now = datetime.utcnow().isoformat()
        with safe_connect_for_write(self._db_path, force_no_tx=True) as conn:
            conn.execute('DELETE FROM token_blacklist WHERE expires_at < ?', (now,))
            conn.commit()

    def add_to_blacklist(self, token: str, expires_at: datetime):
        self._cleanup_expired()
        token_hash = self._hash_token(token)
        # [V007.41 BUG-FIX] 用 safe_connect_for_write 统一 L0 入口
        with safe_connect_for_write(self._db_path, force_no_tx=True) as conn:
            conn.execute(
                'INSERT OR REPLACE INTO token_blacklist (token_hash, blacklisted_at, expires_at) VALUES (?, ?, ?)',
                (token_hash, datetime.utcnow().isoformat(), expires_at.isoformat())
            )
            conn.commit()

    def is_blacklisted(self, token: str) -> bool:
        # [V007.41 BUG-FIX] 包裹 retry 处理 disk I/O error
        # 背景: 这是最高频热路径, 每条 API 请求都调.
        # 修法: 5 次 retry + 指数 backoff, 跟 V007.40 一致.
        import time as _time
        import random as _random
        last_err = None
        for attempt in range(5):
            try:
                self._cleanup_expired()
                token_hash = self._hash_token(token)
                # [V007.41] 用 safe_connect_for_read 统一 L0 入口
                with safe_connect_for_read(self._db_path) as conn:
                    cursor = conn.execute(
                        'SELECT 1 FROM token_blacklist WHERE token_hash = ?',
                        (token_hash,)
                    )
                    return cursor.fetchone() is not None
            except Exception as e:
                last_err = e
                err_str = str(e).lower()
                is_retryable = (
                    'disk i/o' in err_str or
                    'database is locked' in err_str or
                    'database is busy' in err_str
                )
                if not is_retryable:
                    # [V007.41] 不可重试错误: 降级为"未黑名单"(不要 500)
                    logger.warning(
                        "[V007.41] is_blacklisted non-retryable error: %s | "
                        "fallback to False (not blacklisted)", e
                    )
                    return False
                if attempt < 4:
                    delay = 0.05 * (2 ** attempt) + _random.uniform(0, 0.02)
                    logger.warning(
                        "[V007.41] is_blacklisted retry %d/5 sleep %.3fs: %s",
                        attempt + 1, 5, delay, e
                    )
                    _time.sleep(delay)
                    continue
        # 重试耗尽: 降级为"未黑名单", 避免 500
        logger.error(
            "[V007.41] is_blacklisted retry exhausted: %s | fallback to False", last_err
        )
        return False

    @classmethod
    def reset(cls):
        with cls._lock:
            cls._instance = None


token_blacklist_service = TokenBlacklistService()