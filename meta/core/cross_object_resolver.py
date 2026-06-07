# -*- coding: utf-8 -*-
"""
跨对象引用解析器

支持在 Formula 表达式中通过路径语法访问关联对象的字段：
- self.customer.name → 单层引用
- self.customer.region.name → 多层嵌套引用
- parent.field → 引用父对象字段

设计原则：
1. 空安全：引用链中任何一环为 None 则返回 None，不抛异常
2. 惰性加载：仅在访问时查询数据源
3. 缓存友好：同一对象在一次求值中仅查询一次
"""

from typing import Any, Optional, Dict
import logging

logger = logging.getLogger(__name__)


class CrossObjectResolver:
    """
    跨对象引用解析器

    在 Formula 表达式中以 `self` 或 `parent` 前缀访问关联对象字段。

    示例:
        self.customer.name
        self.customer.region.name
        parent.field_name
    """

    def __init__(self, data_source: Any = None, meta_object: Any = None,
                 data: Optional[Dict[str, Any]] = None):
        self._data_source = data_source
        self._meta_object = meta_object
        self._data = data or {}
        self._cache: Dict[str, Any] = {}

    def __getattr__(self, name: str) -> Any:
        if name.startswith('_'):
            raise AttributeError(name)
        return _LazyRef(self, [name])

    def resolve_path(self, parts: list) -> Any:
        cache_key = ".".join(parts)
        if cache_key in self._cache:
            return self._cache[cache_key]

        result = self._do_resolve(parts)
        self._cache[cache_key] = result
        return result

    def _do_resolve(self, parts: list) -> Any:
        if not parts:
            return None

        current_data = self._data
        current_meta = self._meta_object

        for i, part in enumerate(parts):
            if current_data is None:
                return None

            if isinstance(current_data, dict) and part in current_data:
                value = current_data[part]
                if i < len(parts) - 1:
                    if isinstance(value, dict):
                        current_data = value
                        continue
                    current_data = self._try_load_related(
                        current_meta, part, value
                    )
                    if current_data is None:
                        return None
                    current_meta = self._get_target_meta(current_meta, part)
                    continue
                return value

            related = self._try_load_related(current_meta, part, None)
            if related is not None:
                if i < len(parts) - 1:
                    current_data = related
                    current_meta = self._get_target_meta(current_meta, part)
                    continue
                return related

            return None

        return current_data

    def _try_load_related(self, current_meta: Any, relation_name: str,
                          foreign_key_value: Any) -> Optional[Dict[str, Any]]:
        if self._data_source is None or current_meta is None:
            return None

        relation = self._find_relation(current_meta, relation_name)
        if relation is None:
            return None

        fk_value = foreign_key_value
        if fk_value is None and isinstance(self._data, dict):
            fk_value = self._data.get(relation.source_field)

        if fk_value is None:
            return None

        target_meta = self._get_target_meta(current_meta, relation_name)
        if target_meta is None:
            return None

        try:
            record = self._data_source.find_by_id(
                target_meta.table_name, fk_value
            )
            return record
        except Exception as e:
            logger.debug(
                "CrossObjectResolver failed to load %s.%s (fk=%s): %s",
                relation_name, relation.target_field, fk_value, e
            )
            return None

    def _find_relation(self, current_meta: Any, name: str) -> Any:
        if current_meta is None:
            return None
        for rel in getattr(current_meta, 'relations', []):
            if rel.id == name or rel.name == name:
                return rel
            if rel.target_object == name:
                return rel
        return None

    def _get_target_meta(self, current_meta: Any, relation_name: str) -> Any:
        relation = self._find_relation(current_meta, relation_name)
        if relation is None:
            return None

        from meta.core.models import registry
        target_id = relation.target_object
        return registry.get(target_id)


class ParentResolver:
    """
    父对象引用解析器

    通过 parent.field_name 语法访问父对象字段。
    """

    def __init__(self, data_source: Any = None, meta_object: Any = None,
                 data: Optional[Dict[str, Any]] = None):
        self._data_source = data_source
        self._meta_object = meta_object
        self._data = data or {}
        self._parent_data: Optional[Dict[str, Any]] = None
        self._parent_loaded = False

    def __getattr__(self, name: str) -> Any:
        if name.startswith('_'):
            raise AttributeError(name)
        parent_data = self._load_parent()
        if parent_data is None:
            return None
        return parent_data.get(name)

    def _load_parent(self) -> Optional[Dict[str, Any]]:
        if self._parent_loaded:
            return self._parent_data

        self._parent_loaded = True

        if self._meta_object is None or self._data_source is None:
            return None

        parent_rel = None
        for rel in getattr(self._meta_object, 'relations', []):
            if rel.relation_type.value in ('parent_child',) and rel.cardinality in ('N:1',):
                parent_rel = rel
                break

        if parent_rel is None:
            return None

        fk_value = self._data.get(parent_rel.source_field)
        if fk_value is None:
            return None

        from meta.core.models import registry
        parent_meta = registry.get(parent_rel.target_object)
        if parent_meta is None:
            return None

        try:
            self._parent_data = self._data_source.find_by_id(
                parent_meta.table_name, fk_value
            )
        except Exception as e:
            logger.debug("ParentResolver failed to load parent: %s", e)

        return self._parent_data


class _LazyRef:
    """
    惰性引用对象

    支持链式属性访问，仅在最终取值时触发解析。
    """

    def __init__(self, resolver: CrossObjectResolver, parts: list):
        self._resolver = resolver
        self._parts = parts

    def __getattr__(self, name: str) -> Any:
        if name.startswith('_'):
            raise AttributeError(name)
        new_parts = self._parts + [name]
        return _LazyRef(self._resolver, new_parts)

    def __bool__(self) -> bool:
        value = self._resolve()
        return value is not None

    def __str__(self) -> str:
        value = self._resolve()
        return str(value) if value is not None else ""

    def __eq__(self, other: Any) -> bool:
        return self._resolve() == other

    def __ne__(self, other: Any) -> bool:
        return self._resolve() != other

    def __hash__(self) -> int:
        return hash(tuple(self._parts))

    def _resolve(self) -> Any:
        return self._resolver.resolve_path(self._parts)


def build_cross_object_locals(data_source: Any, meta_object: Any,
                               data: Dict[str, Any]) -> Dict[str, Any]:
    """
    构建跨对象引用的 locals 字典

    Returns:
        包含 self 和 parent 引用的字典
    """
    result = {}
    result["self"] = CrossObjectResolver(data_source, meta_object, data)
    result["parent"] = ParentResolver(data_source, meta_object, data)
    return result
