# -*- coding: utf-8 -*-
"""第三方集成凭证与代理服务（P0-1：密钥不进前端产物）

密钥唯一来源 = 后端环境变量，前端只拿到 masked 状态：
  DEEPSEEK_API_KEY / ZHIPU_API_KEY / FEISHU_APP_ID / FEISHU_APP_SECRET
飞书兼容历史命名（tools/_setup_lark_env.ps1 写入的用户级变量）：
  LARK_APP_ID / LARK_APP_SECRET / LARK_CHAT_ID；FEISHU_* 存在时优先
可选：
  AI_PROVIDER（deepseek | zhipu，默认按已配置的 key 推导）

对外能力：
  - get_settings()      集成配置脱敏视图
  - validate_ai()       代理 AI 校验调用（前端不接触 key）
  - feishu_request()    持 tenant_access_token 缓存代理飞书接口
  - feishu_test()       连通性自检
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

DEEPSEEK_API_URL = 'https://api.deepseek.com/v1/chat/completions'
ZHIPU_API_URL = 'https://open.bigmodel.cn/api/paas/v4/chat/completions'
FEISHU_BASE_URL = 'https://open.feishu.cn/open-apis'

# 仅允许代理业务需要的飞书接口前缀，避免变成任意 URL 代理（SSRF）
FEISHU_ALLOWED_PREFIXES = ('/im/', '/contact/', '/sheets/', '/bot/')

DEFAULT_MODELS = {
    'deepseek': 'deepseek-chat',
    'zhipu': 'glm-4-flash',
}

# 飞书 token 失效错误码，命中后强制刷新一次
FEISHU_TOKEN_INVALID_CODES = (99991661, 99991663, 99991668)

MASKED_SECRET = '******'


class IntegrationConfigError(Exception):
    """配置缺失或请求参数非法。"""


class IntegrationUpstreamError(Exception):
    """上游服务调用失败。"""


def _env(name: str) -> str:
    return (os.environ.get(name) or '').strip()


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')


def build_zhipu_token(api_key: str) -> str:
    """按智谱开放平台规则生成 HS256 JWT（不引入 PyJWT 依赖）。"""
    try:
        key_id, secret = api_key.split('.', 1)
    except ValueError as exc:
        raise IntegrationConfigError('ZHIPU_API_KEY 格式不正确（应为 id.secret）') from exc
    if not key_id or not secret:
        raise IntegrationConfigError('ZHIPU_API_KEY 格式不正确（应为 id.secret）')

    now = int(time.time())
    header = {'alg': 'HS256', 'typ': 'JWT', 'sign_type': 'SIGN'}
    payload = {'api_key': key_id, 'exp': now + 3600, 'timestamp': now}
    header_part = _b64url(json.dumps(header, separators=(',', ':')).encode('utf-8'))
    payload_part = _b64url(json.dumps(payload, separators=(',', ':')).encode('utf-8'))
    signing_input = f'{header_part}.{payload_part}'
    signature = hmac.new(
        secret.encode('utf-8'), signing_input.encode('utf-8'), hashlib.sha256
    ).digest()
    return f'{signing_input}.{_b64url(signature)}'


class IntegrationCredentialService:
    """集成凭证读取 + 上游代理（进程内单例）。"""

    def __init__(self) -> None:
        self._token_lock = threading.Lock()
        self._tenant_token = ''
        self._tenant_token_expires_at = 0.0

    # ---------------------------------------------------------------- settings
    def _ai_provider(self) -> str:
        explicit = _env('AI_PROVIDER').lower()
        if explicit in DEFAULT_MODELS:
            return explicit
        if _env('DEEPSEEK_API_KEY'):
            return 'deepseek'
        return 'zhipu'

    def _ai_key(self, provider: str) -> str:
        if provider == 'deepseek':
            return _env('DEEPSEEK_API_KEY')
        if provider == 'zhipu':
            return _env('ZHIPU_API_KEY')
        return ''

    def get_settings(self) -> Dict[str, Any]:
        """返回脱敏后的集成配置，secret 永不出后端。"""
        provider = self._ai_provider()
        app_id, app_secret, chat_id = self._feishu_identity()
        return {
            'feishu': {
                'app_id': app_id,
                'has_secret': bool(app_secret),
                'app_secret_masked': MASKED_SECRET if app_secret else '',
                'has_chat_id': bool(chat_id),
            },
            'ai': {
                'provider': provider,
                'has_key': bool(self._ai_key(provider)),
            },
        }

    # --------------------------------------------------------------------- ai
    def validate_ai(
        self,
        provider: str,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """代理 AI 校验调用，返回 {valid, content, provider, issues}。

        valid 表示"调用成功"，业务结论由前端解析 content 得出。
        """
        provider = (provider or '').strip().lower()
        if provider not in DEFAULT_MODELS:
            raise IntegrationConfigError(f'不支持的 AI 提供方: {provider or "(空)"}')
        if not isinstance(messages, list) or not messages:
            raise IntegrationConfigError('messages 不能为空')

        api_key = self._ai_key(provider)
        if not api_key:
            raise IntegrationConfigError(f'{provider} API Key 未配置（后端环境变量）')

        model_name = (model or '').strip() or DEFAULT_MODELS[provider]
        timeout = int(_env('INTEGRATION_HTTP_TIMEOUT') or 60)

        if provider == 'deepseek':
            url = DEEPSEEK_API_URL
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}',
            }
        else:
            url = ZHIPU_API_URL
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {build_zhipu_token(api_key)}',
            }

        request_body: Dict[str, Any] = {
            'model': model_name,
            'messages': messages,
            'temperature': 0.3,
        }
        if isinstance(max_tokens, int) and max_tokens > 0:
            request_body['max_tokens'] = max_tokens

        try:
            response = requests.post(
                url,
                headers=headers,
                json=request_body,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            logger.warning('[integration] AI 调用失败 provider=%s: %s', provider, exc)
            raise IntegrationUpstreamError(f'{provider} 服务暂时不可用') from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise IntegrationUpstreamError(f'{provider} 返回了非 JSON 响应') from exc

        if response.status_code >= 400:
            message = ''
            error = payload.get('error') if isinstance(payload, dict) else None
            if isinstance(error, dict):
                message = error.get('message') or ''
            message = message or payload.get('message') or f'HTTP {response.status_code}'
            raise IntegrationUpstreamError(f'{provider} 调用失败: {message}')

        try:
            content = payload['choices'][0]['message']['content']
        except (KeyError, IndexError, TypeError) as exc:
            raise IntegrationUpstreamError(f'{provider} 响应结构异常') from exc

        return {
            'valid': True,
            'provider': provider,
            'model': model_name,
            'content': content,
            'issues': [],
        }

    # ----------------------------------------------------------------- feishu
    def _feishu_identity(self) -> tuple:
        """飞书凭证解析：FEISHU_* 优先，回退历史用户级 LARK_* 变量。"""
        return (
            _env('FEISHU_APP_ID') or _env('LARK_APP_ID'),
            _env('FEISHU_APP_SECRET') or _env('LARK_APP_SECRET'),
            _env('FEISHU_CHAT_ID') or _env('LARK_CHAT_ID'),
        )

    def _feishu_credentials(self) -> tuple:
        app_id, app_secret, _ = self._feishu_identity()
        if not app_id or not app_secret:
            raise IntegrationConfigError(
                '飞书 App ID / App Secret 未配置（后端环境变量 FEISHU_* 或 LARK_*）'
            )
        return app_id, app_secret

    def default_feishu_chat_id(self) -> str:
        """默认飞书群 chat_id（FEISHU_CHAT_ID / LARK_CHAT_ID）。"""
        return self._feishu_identity()[2]

    def _fetch_tenant_token(self, app_id: str, app_secret: str) -> tuple:
        timeout = int(_env('INTEGRATION_HTTP_TIMEOUT') or 60)
        try:
            response = requests.post(
                f'{FEISHU_BASE_URL}/auth/v3/tenant_access_token/internal',
                json={'app_id': app_id, 'app_secret': app_secret},
                timeout=timeout,
            )
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise IntegrationUpstreamError('飞书令牌服务不可用') from exc

        if payload.get('code') != 0 or not payload.get('tenant_access_token'):
            raise IntegrationUpstreamError(
                payload.get('msg') or '获取飞书 tenant_access_token 失败'
            )
        expires_in = int(payload.get('expire') or 7200)
        return payload['tenant_access_token'], time.time() + expires_in

    def get_tenant_token(self, force_refresh: bool = False) -> str:
        app_id, app_secret = self._feishu_credentials()
        with self._token_lock:
            if (
                not force_refresh
                and self._tenant_token
                and self._tenant_token_expires_at - 60 > time.time()
            ):
                return self._tenant_token
            token, expires_at = self._fetch_tenant_token(app_id, app_secret)
            self._tenant_token = token
            self._tenant_token_expires_at = expires_at
            return token

    def _validate_feishu_path(self, path: str) -> str:
        path = (path or '').strip()
        if not path.startswith('/') or '://' in path or '..' in path:
            raise IntegrationConfigError('飞书接口路径非法')
        if not any(path.startswith(prefix) for prefix in FEISHU_ALLOWED_PREFIXES):
            raise IntegrationConfigError(f'不允许代理该飞书接口: {path}')
        return path

    def feishu_request(
        self,
        method: str,
        path: str,
        query: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
        file_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """代理飞书 OpenAPI 调用。返回上游原始 JSON（含 code/msg/data）。"""
        method = (method or 'GET').strip().upper()
        if method not in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE'):
            raise IntegrationConfigError(f'不支持的 HTTP 方法: {method}')
        path = self._validate_feishu_path(path)
        timeout = int(_env('INTEGRATION_HTTP_TIMEOUT') or 60)

        def _do(token: str) -> tuple:
            headers = {'Authorization': f'Bearer {token}'}
            kwargs: Dict[str, Any] = {
                'headers': headers,
                'params': query or None,
                'timeout': timeout,
            }
            files = None
            data = None
            if file_payload:
                name = (file_payload.get('name') or 'upload.bin').strip()
                content_type = (
                    file_payload.get('content_type') or 'application/octet-stream'
                )
                try:
                    raw = base64.b64decode(file_payload.get('content_base64') or '')
                except Exception as exc:  # noqa: BLE001 - 边界输入
                    raise IntegrationConfigError('file.content_base64 解码失败') from exc
                files = {'image': (name, raw, content_type)}
                data = dict(body or {})
            else:
                kwargs['json'] = body
            if files:
                kwargs['files'] = files
                kwargs['data'] = data
            response = requests.request(
                method, f'{FEISHU_BASE_URL}{path}', **kwargs
            )
            try:
                return response, response.json()
            except ValueError as exc:
                raise IntegrationUpstreamError('飞书返回了非 JSON 响应') from exc

        try:
            token = self.get_tenant_token()
            response, payload = _do(token)
        except requests.RequestException as exc:
            raise IntegrationUpstreamError('飞书服务暂时不可用') from exc

        if isinstance(payload, dict) and payload.get('code') in FEISHU_TOKEN_INVALID_CODES:
            try:
                token = self.get_tenant_token(force_refresh=True)
                response, payload = _do(token)
            except requests.RequestException as exc:
                raise IntegrationUpstreamError('飞书服务暂时不可用') from exc

        if response.status_code >= 500:
            raise IntegrationUpstreamError(f'飞书服务异常: HTTP {response.status_code}')
        return payload

    def feishu_test(self) -> Dict[str, Any]:
        """连通性自检：只验证能否换到 tenant_access_token。"""
        app_id, _ = self._feishu_credentials()
        self.get_tenant_token(force_refresh=True)
        return {'valid': True, 'app_id': app_id, 'message': '飞书凭证有效'}


integration_credential_service = IntegrationCredentialService()