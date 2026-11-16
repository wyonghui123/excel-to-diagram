# -*- coding: utf-8 -*-
"""集成连接服务（M2）。

依据: docs/specs/spec-integration-module-2026-11-15.md
  §4 数据模型（integration_connection）/ §6 FR-1 / §10 AC-1

职责边界:
  · 只管理**配置对象** `integration_connection`（渠道 / 方向 / 端点 / 认证）；
  · `secret_ref` 只存引用（`env:` / `vault:`），不接受明文，读取侧也不解析；
  · 不写投递事实（`notification_deliveries` 归消息中心），删除前只做引用检查；
  · 删除被订阅/投递引用的连接 → 409，由调用方先解绑。
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

TABLE = 'integration_connection'
SUBSCRIPTION_TABLE = 'change_subscriptions'
DELIVERY_TABLE = 'notification_deliveries'

#: 与 spec §4 / §6 FR-2 一致
CHANNEL_TYPES = ('webhook', 'rest', 'file', 'b2b')
DIRECTIONS = ('outbound', 'inbound', 'both')
AUTH_TYPES = ('none', 'api_key', 'basic', 'bearer', 'oauth2_cc', 'hmac')

#: 重试上限与既有 `attempts < 5` 退避策略对齐，超过 10 直接拒绝
RETRY_MAX_LIMIT = 10
DEFAULT_RETRY_MAX = 5
DEFAULT_TIMEOUT_MS = 15000
TIMEOUT_MS_MIN = 1000
TIMEOUT_MS_MAX = 300000

SECRET_REF_PREFIXES = ('env:', 'vault:')

_CODE_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_.:-]{1,199}$')


class IntegrationConnectionError(ValueError):
    """字段校验失败 / 状态不允许（API 映射 400）。"""


class IntegrationConnectionConflict(Exception):
    """编码重复或被引用（API 映射 409）。"""

    def __init__(self, message: str, refs: Optional[Dict[str, int]] = None):
        super().__init__(message)
        self.refs = refs or {}


def resolve_secret(secret_ref: Optional[str]) -> str:
    """把引用解析为明文，仅用于测试连通性；未配置时返回空串。"""
    if not secret_ref:
        return ''
    if secret_ref.startswith('env:'):
        return os.environ.get(secret_ref[len('env:'):], '')
    # vault: 等外部引用在 M2 不做解析，避免伪造可用性
    return ''


def _now() -> str:
    return datetime.now().isoformat()


def _text(value: Any, field: str, required: bool = False,
          max_len: int = 200) -> Optional[str]:
    if value is None:
        if required:
            raise IntegrationConnectionError('%s 不能为空' % field)
        return None
    if not isinstance(value, str):
        raise IntegrationConnectionError('%s 必须是字符串' % field)
    text = value.strip()
    if required and not text:
        raise IntegrationConnectionError('%s 不能为空' % field)
    if len(text) > max_len:
        raise IntegrationConnectionError('%s 长度不能超过 %d' % (field, max_len))
    return text


def _enum(value: Any, field: str, allowed, default: Optional[str] = None) -> str:
    if value is None or value == '':
        if default is not None:
            return default
        raise IntegrationConnectionError('%s 不能为空' % field)
    if not isinstance(value, str) or value not in allowed:
        raise IntegrationConnectionError(
            '%s 必须是 %s 之一' % (field, '/'.join(allowed)))
    return value


def _int(value: Any, field: str, minimum: int, maximum: int,
         default: Optional[int] = None) -> Optional[int]:
    if value is None or value == '':
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise IntegrationConnectionError('%s 必须是整数' % field)
    if number < minimum or number > maximum:
        raise IntegrationConnectionError(
            '%s 必须在 %d~%d 之间' % (field, minimum, maximum))
    return number


def _bool_flag(value: Any, field: str, default: Optional[int] = None) -> Optional[int]:
    if value is None:
        return default
    if isinstance(value, str):
        return 1 if value.strip().lower() in ('1', 'true', 'yes', 'on') else 0
    return 1 if value else 0


def _json_object(value: Any, field: str) -> Optional[str]:
    """header_template 统一落库为 JSON 文本（dict 或 JSON 字符串入参）。"""
    if value is None or value == '':
        return None
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            raise IntegrationConnectionError('%s 必须是合法 JSON' % field)
    else:
        parsed = value
    if not isinstance(parsed, dict):
        raise IntegrationConnectionError('%s 必须是 JSON 对象' % field)
    return json.dumps(parsed, ensure_ascii=False)


class IntegrationConnectionService:
    """连接配置的 CRUD + 连通性测试 + 删除前引用检查。"""

    def __init__(self, datasource):
        self.ds = datasource
        self._column_cache: Dict[str, set] = {}

    # ------------------------------------------------------------- 读取
    def list_connections(self, enabled: Optional[bool] = None,
                         channel_type: Optional[str] = None,
                         keyword: Optional[str] = None) -> List[Dict[str, Any]]:
        filters: Dict[str, Any] = {}
        if enabled is not None:
            filters['enabled'] = 1 if enabled else 0
        if channel_type:
            filters['channel_type'] = channel_type
        rows = self.ds.find(
            TABLE, filters=filters or None, order_by='updated_at DESC') or []
        if keyword:
            needle = keyword.strip().lower()
            rows = [
                row for row in rows
                if needle in str(row.get('code') or '').lower()
                or needle in str(row.get('name') or '').lower()
                or needle in str(row.get('endpoint') or '').lower()
            ]
        return [self._public(row) for row in rows]

    def get_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        rows = self.ds.find(TABLE, filters={'code': code}, limit=1) or []
        return rows[0] if rows else None

    # ------------------------------------------------------------- 写入
    def create(self, payload: Dict[str, Any],
               user_id: Optional[int] = None) -> Dict[str, Any]:
        data = self._clean(payload, partial=False)
        if self.get_by_code(data['code']):
            raise IntegrationConnectionConflict(
                '连接编码已存在: %s' % data['code'], {'code': 1})
        now = _now()
        if not data.get('owner_user_id'):
            data['owner_user_id'] = user_id
        data['created_at'] = now
        data['updated_at'] = now
        new_id = self.ds.insert(TABLE, data)
        logger.info('integration_connection created: id=%s code=%s user=%s',
                    new_id, data['code'], user_id)
        return self._public(self.ds.find_by_id(TABLE, new_id))

    def update(self, code: str,
               payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        existing = self.get_by_code(code)
        if not existing:
            return None
        changes = self._clean(payload, partial=True)
        changes.pop('code', None)
        if not changes:
            return self._public(existing)
        changes['updated_at'] = _now()
        self.ds.update(TABLE, existing['id'], changes)
        logger.info('integration_connection updated: id=%s code=%s fields=%s',
                    existing['id'], code, sorted(changes))
        return self._public(self.ds.find_by_id(TABLE, existing['id']))

    def delete(self, code: str) -> Optional[Dict[str, Any]]:
        existing = self.get_by_code(code)
        if not existing:
            return None
        refs = self.references(existing['id'])
        if refs.get('subscriptions') or refs.get('deliveries'):
            raise IntegrationConnectionConflict(
                '连接仍被引用，不能删除（订阅 %d 条 / 投递 %d 条）'
                % (refs.get('subscriptions', 0), refs.get('deliveries', 0)),
                refs)
        self.ds.delete(TABLE, existing['id'])
        logger.info('integration_connection deleted: id=%s code=%s',
                    existing['id'], code)
        return {'deleted': True, 'code': code}

    def references(self, connection_id: int) -> Dict[str, int]:
        """统计引用该连接的订阅与投递行数。"""
        return {
            'subscriptions': self._count(SUBSCRIPTION_TABLE,
                                         'connection_id', connection_id),
            'deliveries': self._count(DELIVERY_TABLE,
                                      'connection_id', connection_id),
        }

    # ------------------------------------------------------- 连通性测试
    def test_connection(self, code: str) -> Optional[Dict[str, Any]]:
        connection = self.get_by_code(code)
        if not connection:
            return None
        channel_type = connection.get('channel_type')
        endpoint = connection.get('endpoint') or ''

        if channel_type == 'file':
            path = Path(endpoint)
            exists = path.exists()
            return {
                'valid': exists,
                'status_code': None,
                'elapsed_ms': 0,
                'message': '目标目录存在' if exists else '目标目录不存在',
            }
        if channel_type == 'b2b':
            raise IntegrationConnectionError('b2b 连接暂不支持连通性测试')
        if channel_type not in ('webhook', 'rest'):
            raise IntegrationConnectionError(
                '不支持的渠道类型: %s' % channel_type)
        if not endpoint.lower().startswith(('http://', 'https://')):
            raise IntegrationConnectionError('端点必须是 http:// 或 https://')

        timeout = max(int(connection.get('timeout_ms')
                          or DEFAULT_TIMEOUT_MS), TIMEOUT_MS_MIN) / 1000.0
        headers = self._headers(connection)
        started = time.monotonic()
        try:
            if channel_type == 'rest':
                response = requests.request(
                    'HEAD', endpoint, headers=headers, timeout=timeout,
                    allow_redirects=False)
            else:
                response = requests.request(
                    'POST', endpoint, headers=headers, json={},
                    timeout=timeout, allow_redirects=False)
        except requests.RequestException as exc:
            return {
                'valid': False,
                'status_code': None,
                'elapsed_ms': int((time.monotonic() - started) * 1000),
                'message': str(exc),
            }

        elapsed = int((time.monotonic() - started) * 1000)
        valid = 200 <= response.status_code < 400
        return {
            'valid': valid,
            'status_code': response.status_code,
            'elapsed_ms': elapsed,
            'message': '端点可达' if valid
                       else '端点返回 %s' % response.status_code,
        }

    # ------------------------------------------------------------- 内部
    def has_delivery_facts(self) -> bool:
        """投递事实列是否就绪（v279 未执行时为 False）。"""
        columns = self._columns(DELIVERY_TABLE)
        return all(name in columns
                   for name in ('connection_id', 'target_type', 'direction'))

    def _public(self, row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not row:
            return None
        item = dict(row)
        # AC-1: 不返回任何密钥明文，只回引用（env:/vault:）与「是否已配置」
        item['has_secret'] = bool(item.get('secret_ref'))
        item['enabled'] = bool(item.get('enabled'))
        return item

    def _clean(self, payload: Dict[str, Any],
               partial: bool) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise IntegrationConnectionError('请求体必须是 JSON 对象')
        data: Dict[str, Any] = {}

        if not partial or 'code' in payload:
            code = _text(payload.get('code'), 'code', required=True)
            if not _CODE_RE.match(code):
                raise IntegrationConnectionError(
                    'code 必须以字母开头，且只含字母/数字/_.:- ')
            data['code'] = code

        if not partial or 'name' in payload:
            data['name'] = _text(payload.get('name'), 'name', required=True)

        if not partial or 'channel_type' in payload:
            data['channel_type'] = _enum(
                payload.get('channel_type'), 'channel_type', CHANNEL_TYPES)

        if not partial or 'direction' in payload:
            data['direction'] = _enum(
                payload.get('direction'), 'direction', DIRECTIONS, 'outbound')

        if not partial or 'endpoint' in payload:
            data['endpoint'] = _text(
                payload.get('endpoint'), 'endpoint', required=True, max_len=500)

        if not partial or 'auth_type' in payload:
            auth_type = _enum(
                payload.get('auth_type'), 'auth_type', AUTH_TYPES, 'none')
            data['auth_type'] = auth_type

        if 'secret_ref' in payload or not partial:
            secret_ref = _text(payload.get('secret_ref'), 'secret_ref',
                               max_len=500)
            if secret_ref and not secret_ref.startswith(SECRET_REF_PREFIXES):
                raise IntegrationConnectionError(
                    'secret_ref 只接受引用（env: / vault:），不接受明文密钥')
            data['secret_ref'] = secret_ref

        if 'header_template' in payload or not partial:
            data['header_template'] = _json_object(
                payload.get('header_template'), 'header_template')

        if 'timeout_ms' in payload or not partial:
            data['timeout_ms'] = _int(
                payload.get('timeout_ms'), 'timeout_ms',
                TIMEOUT_MS_MIN, TIMEOUT_MS_MAX, DEFAULT_TIMEOUT_MS)

        if 'retry_max' in payload or not partial:
            data['retry_max'] = _int(
                payload.get('retry_max'), 'retry_max',
                0, RETRY_MAX_LIMIT, DEFAULT_RETRY_MAX)

        if 'enabled' in payload or not partial:
            data['enabled'] = _bool_flag(payload.get('enabled'), 'enabled', 1)

        if 'owner_user_id' in payload:
            data['owner_user_id'] = _int(
                payload.get('owner_user_id'), 'owner_user_id', 1, 2 ** 31 - 1)

        return data

    def _headers(self, connection: Dict[str, Any]) -> Dict[str, str]:
        headers = {'Content-Type': 'application/json'}
        template = connection.get('header_template')
        if isinstance(template, str) and template.strip():
            try:
                template = json.loads(template)
            except ValueError:
                template = None
        if isinstance(template, dict):
            secret = resolve_secret(connection.get('secret_ref'))
            for key, value in template.items():
                if isinstance(value, str):
                    value = value.replace('${secret}', secret)
                headers[str(key)] = str(value)
        auth_type = connection.get('auth_type')
        secret = resolve_secret(connection.get('secret_ref'))
        if auth_type == 'bearer' and secret:
            headers['Authorization'] = 'Bearer %s' % secret
        elif auth_type == 'api_key' and secret:
            headers.setdefault('X-API-Key', secret)
        elif auth_type == 'hmac' and secret:
            headers['X-Integration-Secret'] = secret
        return headers

    def _columns(self, table: str) -> set:
        if table in self._column_cache:
            return self._column_cache[table]
        try:
            rows = self.ds.execute('PRAGMA table_info(%s)' % table).fetchall()
            columns = {row[1] for row in rows}
        except Exception:
            columns = set()
        self._column_cache[table] = columns
        return columns

    def _count(self, table: str, column: str, value: Any) -> int:
        if column not in self._columns(table):
            return 0
        row = self.ds.execute(
            'SELECT COUNT(*) FROM %s WHERE %s = ?' % (table, column),
            (value,)).fetchone()
        return int(row[0]) if row else 0