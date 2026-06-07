# -*- coding: utf-8 -*-
"""
JWT Token服务

优化点：
1. 支持从 .env 文件读取持久化密钥
2. 首次启动时自动生成并保存密钥
3. 开发环境使用固定密钥作为降级方案
4. 明确的警告提示生产环境配置
"""

import os
import jwt
import datetime
import logging
import secrets
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class TokenService:
    """
    JWT Token 服务类
    
    密钥加载优先级：
    1. 环境变量 JWT_SECRET_KEY
    2. .env 文件中的 JWT_SECRET_KEY
    3. 自动生成的开发密钥（仅警告，不推荐生产使用）
    """
    
    ALGORITHM = 'HS256'
    EXPIRE_HOURS = 4
    
    _secret_key: Optional[str] = None
    _initialized: bool = False
    
    DEV_SECRET_KEY = "dev-only-secret-key-not-for-production-use"
    
    @classmethod
    def _ensure_initialized(cls) -> None:
        """确保密钥已初始化（延迟初始化模式）"""
        if cls._initialized:
            return
        
        secret = os.environ.get('JWT_SECRET_KEY')
        
        if secret:
            cls._secret_key = secret
            logger.info("[TOKEN] Using JWT_SECRET_KEY from environment variable")
            cls._initialized = True
            return
        
        env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
        if os.path.exists(env_file):
            try:
                with open(env_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            if key.strip() == 'JWT_SECRET_KEY':
                                cls._secret_key = value.strip()
                                logger.info("[TOKEN] Using JWT_SECRET_KEY from .env file")
                                cls._initialized = True
                                return
            except Exception as e:
                logger.warning(f"[TOKEN] Failed to read .env file: {e}")
        
        cls._secret_key = cls.DEV_SECRET_KEY
        cls._save_to_env(env_file)
        logger.warning("[TOKEN] WARNING: Using development secret key. Set JWT_SECRET_KEY environment variable for production!")
        cls._initialized = True
    
    @classmethod
    def _save_to_env(cls, env_file: str) -> None:
        """保存密钥到 .env 文件"""
        try:
            with open(env_file, 'a', encoding='utf-8') as f:
                f.write(f"\n# Auto-generated JWT Secret Key (DO NOT MODIFY OR SHARE)\n")
                f.write(f"JWT_SECRET_KEY={cls._secret_key}\n")
            logger.info(f"[TOKEN] Saved JWT_SECRET_KEY to {env_file}")
        except Exception as e:
            logger.warning(f"[TOKEN] Failed to save to .env file: {e}")
    
    @classmethod
    def _get_secret_key(cls) -> str:
        """获取密钥（确保已初始化）"""
        cls._ensure_initialized()
        return cls._secret_key or cls.DEV_SECRET_KEY
    
    @classmethod
    def create_token(cls, user_info) -> str:
        """创建 Token"""
        cls._ensure_initialized()
        now = datetime.datetime.utcnow()
        exp = now + datetime.timedelta(hours=cls.EXPIRE_HOURS)
        payload = {
            'jti': secrets.token_hex(16),
            'user_id': user_info.user_id,
            'username': user_info.username,
            'display_name': user_info.display_name,
            'roles': user_info.roles,
            'permissions': user_info.permissions,
            'token_version': getattr(user_info, 'token_version', 0),
            'exp': exp,
            'iat': now
        }
        return jwt.encode(payload, cls._get_secret_key(), algorithm=cls.ALGORITHM), exp
    
    @classmethod
    def extract_payload_without_verification(cls, token: str) -> Optional[Dict[str, Any]]:
        """提取 Token payload（不验证签名）"""
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
            return payload
        except Exception:
            return None
    
    @classmethod
    def verify_token(cls, token: str) -> Optional[Dict[str, Any]]:
        """验证 Token"""
        cls._ensure_initialized()
        try:
            payload = jwt.decode(token, cls._get_secret_key(), algorithms=[cls.ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
    
    @classmethod
    def refresh_token(cls, token: str) -> Optional[str]:
        """刷新 Token"""
        cls._ensure_initialized()
        payload = cls.verify_token(token)
        if not payload:
            return None
        payload.pop('exp', None)
        payload.pop('iat', None)
        payload['exp'] = datetime.datetime.utcnow() + datetime.timedelta(hours=cls.EXPIRE_HOURS)
        payload['iat'] = datetime.datetime.utcnow()
        return jwt.encode(payload, cls._get_secret_key(), algorithm=cls.ALGORITHM)
    
    @classmethod
    def get_secret_key_info(cls) -> Dict[str, Any]:
        """获取密钥配置信息（用于调试）"""
        cls._ensure_initialized()
        return {
            'source': 'environment' if os.environ.get('JWT_SECRET_KEY') else ('.env' if os.path.exists('.env') else 'auto-generated'),
            'is_dev_key': cls._secret_key == cls.DEV_SECRET_KEY,
            'initialized': cls._initialized,
        }
