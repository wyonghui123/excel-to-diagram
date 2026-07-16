# -*- coding: utf-8 -*-
"""模型注册表 — 管理所有已加载的 Schema。"""

import logging

logger = logging.getLogger(__name__)


class ModelRegistry:
    """全局 Schema 注册表。"""
    _schemas: dict = {}

    @classmethod
    def register(cls, schema: dict):
        name = schema.get('id', '') or schema.get('name', '')
        if name:
            cls._schemas[name] = schema

    @classmethod
    def get(cls, name: str) -> dict:
        return cls._schemas.get(name, {})

    @classmethod
    def get_all(cls) -> dict:
        return dict(cls._schemas)

    @classmethod
    def clear(cls):
        cls._schemas.clear()