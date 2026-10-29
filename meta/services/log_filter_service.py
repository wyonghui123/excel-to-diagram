# -*- coding: utf-8 -*-
"""
日志过滤器服务

屏蔽敏感信息：密码、Token、API密钥、身份证号、手机号等
"""

import re
import logging
from typing import Any


# [P1 2026-10-29] 敏感字段单一声明（PII 字段级安全域 Spec v0.1）
# 字段 id 部分来自 meta/core/security/sensitive_fields.py 的声明表，
# 非字段名的日志键（authorization/session/cookie/ssn/id_number 等）留在 EXTRA_LOG_KEYS。
from meta.core.security.sensitive_fields import LOG_TEXT_KEYS as SENSITIVE_KEYS  # noqa: E402

SENSITIVE_VALUE_PATTERNS = [
    (re.compile(r'Bearer\s+[a-zA-Z0-9\-_.~+/]+=*'), 'Bearer [TOKEN]'),
    (re.compile(r'eyJ[a-zA-Z0-9\-_]+\.eyJ[a-zA-Z0-9\-_]+\.[a-zA-Z0-9\-_]+'), '[JWT_TOKEN]'),
    (re.compile(r'PBKDF2\$\S+'), '[PASSWORD_HASH]'),
    (re.compile(r'sha256\$[\w\-]+'), '[PASSWORD_HASH]'),
    (re.compile(r'\b\d{15}\b'), '[ID_NUMBER]'),
    (re.compile(r'\b\d{18}\b'), '[ID_NUMBER]'),
    (re.compile(r'\b1[3-9]\d{9}\b'), '[PHONE]'),
]


def mask_sensitive_value(key: str, value: Any) -> Any:
    key_lower = key.lower()
    for sensitive_key in SENSITIVE_KEYS:
        if sensitive_key in key_lower:
            return '[REDACTED]'
    return value


def filter_dict(data: dict, parent_key: str = '') -> dict:
    if not isinstance(data, dict):
        return data
    result = {}
    for k, v in data.items():
        if isinstance(v, dict):
            result[k] = filter_dict(v, k)
        elif isinstance(v, list):
            result[k] = [
                filter_dict(item, k) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            result[k] = mask_sensitive_value(k, v)
    return result


def filter_log_message(message: str) -> str:
    for pattern, replacement in SENSITIVE_VALUE_PATTERNS:
        message = pattern.sub(replacement, message)
    return message


class SensitiveDataFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.msg, dict):
            record.msg = filter_dict(record.msg)
        elif isinstance(record.msg, str):
            record.msg = filter_log_message(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = filter_dict(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    filter_dict(arg) if isinstance(arg, dict) else
                    filter_log_message(str(arg)) if isinstance(arg, str) else arg
                    for arg in record.args
                )
        return True


def setup_log_filter():
    filter_instance = SensitiveDataFilter()
    for handler in logging.root.handlers:
        if filter_instance not in handler.filters:
            handler.addFilter(filter_instance)