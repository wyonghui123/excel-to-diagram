# -*- coding: utf-8 -*-
"""
JWT Token黑名单服务

登出后Token失效 - 通过在数据库中存储Token哈希实现
"""

import hashlib
import sqlite3
import threading
import os
import logging
from datetime import datetime
from typing import Optional

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

    def _get_connection(self):
        return sqlite3.connect(self._db_path, check_same_thread=False)

    def _ensure_table(self):
        conn = self._get_connection()
        try:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS token_blacklist (
                    token_hash TEXT PRIMARY KEY,
                    blacklisted_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_expires_at ON token_blacklist(expires_at)')
            conn.commit()
        finally:
            conn.close()

    def _hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode('utf-8')).hexdigest()

    def _cleanup_expired(self):
        conn = self._get_connection()
        try:
            now = datetime.utcnow().isoformat()
            conn.execute('DELETE FROM token_blacklist WHERE expires_at < ?', (now,))
            conn.commit()
        finally:
            conn.close()

    def add_to_blacklist(self, token: str, expires_at: datetime):
        self._cleanup_expired()
        token_hash = self._hash_token(token)
        conn = self._get_connection()
        try:
            conn.execute(
                'INSERT OR REPLACE INTO token_blacklist (token_hash, blacklisted_at, expires_at) VALUES (?, ?, ?)',
                (token_hash, datetime.utcnow().isoformat(), expires_at.isoformat())
            )
            conn.commit()
        finally:
            conn.close()

    def is_blacklisted(self, token: str) -> bool:
        try:
            self._cleanup_expired()
            token_hash = self._hash_token(token)
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    'SELECT 1 FROM token_blacklist WHERE token_hash = ?',
                    (token_hash,)
                )
                return cursor.fetchone() is not None
            finally:
                conn.close()
        except Exception:
            return False

    @classmethod
    def reset(cls):
        with cls._lock:
            cls._instance = None


token_blacklist_service = TokenBlacklistService()