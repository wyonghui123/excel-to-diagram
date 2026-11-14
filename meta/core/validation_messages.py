# -*- coding: utf-8 -*-
"""
校验消息与校验明细（i18n）。

文案单一真源已迁至 ``meta/core/message_registry.py``；本模块保留
``ValidationMessageRegistry`` 兼容门面（既有导入无需改动）。

消息 key 格式：validation.{category}.{rule}
默认 locale 为 zh_CN。
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional

from meta.core.message_registry import MessageRegistry


@dataclass
class ValidationDetail:
    field_id: str = ""
    field_name: str = ""
    rule: str = ""
    message: str = ""
    i18n_key: str = ""
    params: Dict[str, Any] = None
    error_code: str = "data_invalid"

    def __post_init__(self):
        if self.params is None:
            self.params = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_id": self.field_id,
            "field_name": self.field_name,
            "rule": self.rule,
            "message": self.message,
            "error_code": self.error_code or "data_invalid",
            "i18n_key": self.i18n_key,
            "params": self.params,
        }


class ValidationMessageRegistry:
    """兼容门面：委托 ``MessageRegistry``（单一真源）。"""

    @classmethod
    def get(cls, key: str, locale: Optional[str] = None, **params) -> str:
        return MessageRegistry.get(key, locale=locale, **params)

    @classmethod
    def register_messages(cls, locale: str, messages: Dict[str, str]):
        MessageRegistry.register(locale, messages)

    @classmethod
    def set_locale(cls, locale: str):
        MessageRegistry.set_locale(locale)

    @classmethod
    def get_locale(cls) -> str:
        return MessageRegistry.get_locale()