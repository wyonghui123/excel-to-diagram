# -*- coding: utf-8 -*-
"""
认证提供者

支持本地认证和SSO集成（预留）
"""

import hashlib
import os
import re
import json
import secrets
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field


def _generate_salt(length: int = 16) -> str:
    return secrets.token_hex(length)


def _hash_password_pbdkdf2(password: str, salt: str = None, iterations: int = 100000) -> str:
    """使用 PBKDF2-SHA256 哈希密码（OWASP 推荐）"""
    if salt is None:
        salt = _generate_salt(16)
    stored = "PBKDF2${0}${1}${2}".format(
        iterations,
        salt,
        hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), iterations).hex()
    )
    return stored


def _verify_password(password: str, password_hash: str) -> bool:
    """验证密码 — 支持 PBKDF2（新版）和 SHA-256（旧版迁移）"""
    if not password_hash:
        return False
    if password_hash.startswith("PBKDF2$"):
        try:
            parts = password_hash.split("$")
            iterations = int(parts[1])
            salt = parts[2]
            stored_hash = parts[3]
            computed = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), iterations).hex()
            return secrets.compare_digest(computed, stored_hash)
        except Exception:
            return False
    else:
        legacy_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
        return secrets.compare_digest(legacy_hash, password_hash)


PASSWORD_MIN_LENGTH = 8
PASSWORD_HISTORY_SIZE = 3


def validate_password_strength(password: str) -> Tuple[bool, str]:
    """
    校验密码复杂度

    规则:
    - 长度 >= 8 位
    - 必须包含字母
    - 必须包含数字

    Returns:
        (is_valid, error_message)
    """
    if len(password) < PASSWORD_MIN_LENGTH:
        return False, f"密码长度不能少于{PASSWORD_MIN_LENGTH}位"
    if not re.search(r'[a-zA-Z]', password):
        return False, "密码必须包含字母"
    if not re.search(r'\d', password):
        return False, "密码必须包含数字"
    return True, ""


def check_password_history(new_password: str, password_history_json: Optional[str]) -> Tuple[bool, str]:
    """
    检查新密码是否与历史密码重复

    Args:
        new_password: 新密码（明文）
        password_history_json: 历史密码 hash 列表的 JSON 字符串

    Returns:
        (is_ok, error_message)
    """
    if not password_history_json:
        return True, ""
    try:
        history_hashes = json.loads(password_history_json)
    except (json.JSONDecodeError, TypeError):
        return True, ""
    for old_hash in history_hashes:
        if _verify_password(new_password, old_hash):
            return False, f"新密码不能与最近{PASSWORD_HISTORY_SIZE}次使用的密码相同"
    return True, ""


def update_password_history(new_password_hash: str, password_history_json: Optional[str]) -> str:
    """
    更新密码历史记录，保留最近 N 个 hash

    Args:
        new_password_hash: 新密码的 hash
        password_history_json: 当前历史记录 JSON

    Returns:
        更新后的 JSON 字符串
    """
    if password_history_json:
        try:
            history = json.loads(password_history_json)
        except (json.JSONDecodeError, TypeError):
            history = []
    else:
        history = []
    history.append(new_password_hash)
    if len(history) > PASSWORD_HISTORY_SIZE:
        history = history[-PASSWORD_HISTORY_SIZE:]
    return json.dumps(history)


@dataclass
class UserInfo:
    user_id: int
    username: str
    display_name: str
    email: str
    roles: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    token_version: int = 0


class AuthProvider(ABC):
    @abstractmethod
    def authenticate(self, credentials: Dict[str, Any]) -> Optional[UserInfo]:
        pass

    @abstractmethod
    def get_user_by_id(self, user_id: int) -> Optional[UserInfo]:
        pass


class LocalAuthProvider(AuthProvider):
    def __init__(self, data_source):
        self.ds = data_source

    def authenticate(self, credentials: Dict[str, Any]) -> Optional[UserInfo]:
        username = credentials.get('username')
        password = credentials.get('password')

        if not username or not password:
            return None

        cursor = self.ds.execute(
            "SELECT id, username, email, password_hash, display_name, status FROM users WHERE username = ?",
            [username]
        )
        row = cursor.fetchone()
        if not row:
            return None

        user = {'id': row[0], 'username': row[1], 'email': row[2], 'password_hash': row[3], 'display_name': row[4], 'status': row[5], 'token_version': 0}

        if user.get('status') != 'active':
            return None

        if not self._verify_password(password, user['password_hash']):
            return None

        if not (user['password_hash'] or '').startswith('PBKDF2$'):
            self._upgrade_password_hash(user['id'], password)

        self.ds.execute(
            "UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?",
            [user['id']]
        )

        roles = self._get_user_roles(user['id'])
        permissions = self._get_user_permissions(user['id'])

        return UserInfo(
            user_id=user['id'],
            username=user['username'],
            display_name=user.get('display_name') or user['username'],
            email=user.get('email') or '',
            roles=roles,
            permissions=permissions,
            token_version=user.get('token_version', 0)
        )

    def get_user_by_id(self, user_id: int) -> Optional[UserInfo]:
        cursor = self.ds.execute(
            "SELECT id, username, email, display_name, status FROM users WHERE id = ?",
            [user_id]
        )
        row = cursor.fetchone()
        if not row:
            return None

        user = {'id': row[0], 'username': row[1], 'email': row[2], 'display_name': row[3], 'status': row[4], 'token_version': 0}

        if user.get('status') != 'active':
            return None

        roles = self._get_user_roles(user['id'])
        permissions = self._get_user_permissions(user['id'])

        return UserInfo(
            user_id=user['id'],
            username=user['username'],
            display_name=user.get('display_name') or user['username'],
            email=user.get('email') or '',
            roles=roles,
            permissions=permissions,
            token_version=user.get('token_version', 0)
        )

    def _verify_password(self, password: str, password_hash: str) -> bool:
        return _verify_password(password, password_hash)

    def _upgrade_password_hash(self, user_id: int, password: str) -> None:
        """首次登录时将旧 SHA-256 密码升级为 PBKDF2"""
        new_hash = _hash_password_pbdkdf2(password)
        self.ds.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            [new_hash, user_id]
        )

    def _get_user_roles(self, user_id: int) -> List[Dict]:
        cursor = self.ds.execute(
            """SELECT r.id, r.code, r.name FROM roles r
               JOIN group_roles gr ON r.id = gr.role_id
               JOIN user_group_members ugm ON gr.group_id = ugm.group_id
               WHERE ugm.user_id = ?""",
            [user_id]
        )
        roles = []
        seen = set()
        for row in cursor.fetchall():
            role_id = row[0] if isinstance(row, (list, tuple)) else row['id']
            if role_id in seen:
                continue
            seen.add(role_id)
            if isinstance(row, (list, tuple)):
                roles.append({
                    'id': row[0],
                    'code': row[1],
                    'name': row[2],
                })
            else:
                roles.append({
                    'id': row['id'],
                    'code': row['code'],
                    'name': row['name'],
                })
        return roles

    def _get_user_permissions(self, user_id: int) -> List[str]:
        cursor = self.ds.execute(
            """SELECT DISTINCT p.code FROM permissions p
               JOIN role_permissions rp ON p.id = rp.permission_id
               JOIN group_roles gr ON rp.role_id = gr.role_id
               JOIN user_group_members ugm ON gr.group_id = ugm.group_id
               WHERE ugm.user_id = ?""",
            [user_id]
        )
        return [row[0] if isinstance(row, (list, tuple)) else row['code'] for row in cursor.fetchall()]


class SSOAuthProvider(AuthProvider):
    def __init__(self, data_source, sso_config=None):
        self.ds = data_source
        self.sso_config = sso_config or {}

    def authenticate(self, credentials: Dict[str, Any]) -> Optional[UserInfo]:
        return None

    def get_user_by_id(self, user_id: int) -> Optional[UserInfo]:
        return None
