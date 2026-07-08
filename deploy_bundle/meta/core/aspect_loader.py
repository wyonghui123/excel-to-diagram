# -*- coding: utf-8 -*-
r"""
Aspect Loader — aspects.yaml 加载器

【背景 2026-06-04】
Spec v1.3 FR-009/010: 读 aspects.yaml 中 aspect 的 authorization 配置
用于 owner_aspect scope 表达式求值。
"""
import os
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _get_schemas_dir() -> str:
    """获取 schemas 目录路径"""
    current = os.path.abspath(__file__)
    for _ in range(2):
        current = os.path.dirname(current)
    return os.path.join(current, 'schemas')


class AspectLoader:
    """aspects.yaml 加载器（FR-009/010 真正应用）

    支持：
    - get_aspect(aspect_id): 获取整个 aspect 配置
    - get_authorization_scope(aspect_id): 获取 authorization.scope 表达式
    - get_field(aspect_id, field_id): 获取 aspect 中的字段定义
    - has_field(aspect_id, field_id): 检查 aspect 是否包含某字段
    """

    def __init__(self, schemas_dir: Optional[str] = None):
        self._schemas_dir = schemas_dir or _get_schemas_dir()
        self._cache: Optional[Dict[str, Any]] = None

    def _load(self) -> Dict[str, Any]:
        """加载 aspects.yaml（LRU 缓存）"""
        if self._cache is not None:
            return self._cache
        path = os.path.join(self._schemas_dir, 'aspects.yaml')
        if not os.path.exists(path):
            logger.warning(f"aspects.yaml not found: {path}")
            self._cache = {}
            return self._cache
        try:
            import yaml
            with open(path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            self._cache = data
            return data
        except Exception as e:  # noqa: BLE001
            logger.error(f"Failed to load aspects.yaml: {e}")
            self._cache = {}
            return self._cache

    def clear_cache(self) -> None:
        """清空缓存"""
        self._cache = None

    def get_aspect(self, aspect_id: str) -> Optional[Dict[str, Any]]:
        """获取整个 aspect 配置"""
        data = self._load()
        return data.get(aspect_id)

    def get_authorization_scope(
        self, aspect_id: str,
    ) -> Optional[str]:
        """获取 authorization.scope 表达式

        例：owner_aspect → "visibility = 'public' OR owner_id = $user.id"
        """
        aspect = self.get_aspect(aspect_id)
        if not aspect:
            return None
        return aspect.get('authorization', {}).get('scope')

    def get_actions(self, aspect_id: str) -> List[Dict[str, Any]]:
        """获取 aspect 的 actions 列表"""
        aspect = self.get_aspect(aspect_id)
        if not aspect:
            return []
        return aspect.get('actions', []) or []

    def get_field(
        self, aspect_id: str, field_id: str,
    ) -> Optional[Dict[str, Any]]:
        """获取 aspect 中的字段定义"""
        aspect = self.get_aspect(aspect_id)
        if not aspect:
            return None
        for f in aspect.get('fields', []) or []:
            if isinstance(f, dict) and f.get('id') == field_id:
                return f
        return None

    def has_field(self, aspect_id: str, field_id: str) -> bool:
        """检查 aspect 是否包含某字段"""
        return self.get_field(aspect_id, field_id) is not None

    def get_authorization_config(
        self, aspect_id: str,
    ) -> Optional[Dict[str, Any]]:
        """获取整个 authorization 配置"""
        aspect = self.get_aspect(aspect_id)
        if not aspect:
            return None
        return aspect.get('authorization')


# 单例
_aspect_loader_instance: Optional[AspectLoader] = None


def get_aspect_loader() -> AspectLoader:
    """获取全局单例"""
    global _aspect_loader_instance
    if _aspect_loader_instance is None:
        _aspect_loader_instance = AspectLoader()
    return _aspect_loader_instance
