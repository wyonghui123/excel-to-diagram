# -*- coding: utf-8 -*-
"""
元数据解析器

从 YAML 元模型统一推导表名、字段名、图标等元数据。
遵循 SSOT（Single Source of Truth）原则：所有映射关系从 YAML 元模型推导。
"""

import logging
from typing import Optional, Dict, Tuple

from meta.core.models import registry

logger = logging.getLogger(__name__)


class MetadataResolver:
    """
    从 YAML 元模型统一推导元数据

    每个方法都有 fallback 逻辑确保健壮性。
    """

    _instance = None
    _cache: Dict[str, object] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ── 图标映射 ──

    @classmethod
    def get_entity_icon(cls, entity_name: str) -> str:
        """从 YAML 元模型获取实体图标"""
        if not entity_name:
            return 'Link'

        cache_key = f'icon:{entity_name}'
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        try:
            obj = registry.get(entity_name)
            if obj and hasattr(obj, 'ui') and obj.ui:
                icon = getattr(obj.ui, 'icon', None)
                if icon:
                    cls._cache[cache_key] = icon
                    return icon

                category = getattr(obj.ui, 'category', '')
                category_icons = {
                    'master_data': 'Database',
                    'transaction': 'Document',
                    'configuration': 'Setting',
                    'security': 'Lock',
                    'lookup': 'Collection',
                }
                for cat, default_icon in category_icons.items():
                    if cat in str(category).lower():
                        cls._cache[cache_key] = default_icon
                        return default_icon
        except Exception as e:
            logger.debug("Cannot resolve icon for '%s': %s", entity_name, e)

        entity_icon_map = {
            'user': 'User',
            'role': 'Key',
            'permission': 'Lock',
            'user_group': 'UserFilled',
            'enum_type': 'Collection',
            'domain': 'HomeFilled',
            'version': 'Document',
            'menu': 'Menu',
            'scheduled_task': 'Clock',
        }
        if entity_name in entity_icon_map:
            cls._cache[cache_key] = entity_icon_map[entity_name]
            return entity_icon_map[entity_name]

        return 'Link'

    # ── 外键列名映射 ──

    @classmethod
    def get_fk_column(cls, through_table: str, source_entity: str) -> Optional[Tuple[str, str]]:
        """从 YAML 关联定义推导外键列名，返回 (table_name, fk_column) 或 None"""
        if not through_table or not source_entity:
            return None

        cache_key = f'fk:{through_table}:{source_entity}'
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        try:
            obj = registry.get(source_entity)
            if obj and hasattr(obj, 'associations'):
                for assoc in obj.associations.values():
                    if getattr(assoc, 'through', '') == through_table:
                        source_key = getattr(assoc, 'source_key', f'{source_entity}_id')
                        result = (through_table, source_key)
                        cls._cache[cache_key] = result
                        return result

            for obj in registry.all():
                if not hasattr(obj, 'associations'):
                    continue
                for assoc in obj.associations.values():
                    assoc_type = getattr(assoc, 'type', '')
                    if assoc_type not in ('many_to_many', 'composition'):
                        continue
                    if getattr(assoc, 'through', '') == through_table:
                        target_entity = getattr(assoc, 'target_entity', '') or getattr(assoc, 'target', '')
                        if obj.id == source_entity:
                            source_key = getattr(assoc, 'source_key', f'{source_entity}_id')
                        elif target_entity == source_entity:
                            source_key = getattr(assoc, 'target_key', f'{source_entity}_id')
                        else:
                            continue
                        result = (through_table, source_key)
                        cls._cache[cache_key] = result
                        return result
        except Exception as e:
            logger.warning("Cannot resolve FK for '%s': %s", through_table, e)

        fallback = f'{source_entity}_id'
        result = (through_table, fallback)
        cls._cache[cache_key] = result
        return result

    # ── 目标类型推导 ──

    @classmethod
    def get_association_target(cls, source_entity: str, association_name: str) -> str:
        """从 YAML 关联定义推导关联的目标实体类型"""
        if not source_entity or not association_name:
            return ''

        cache_key = f'target:{source_entity}:{association_name}'
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        try:
            obj = registry.get(source_entity)
            if obj and hasattr(obj, 'associations'):
                assoc = obj.associations.get(association_name)
                if assoc:
                    target = getattr(assoc, 'target_entity', '') or getattr(assoc, 'target', '')
                    cls._cache[cache_key] = target
                    return target
        except Exception as e:
            logger.warning(
                "Cannot resolve target for '%s.%s': %s",
                source_entity, association_name, e
            )

        return ''

    # ── M2M Through 表信息 ──

    @classmethod
    def get_m2m_through_info(
        cls, source_entity: str, target_entity: str, association_name: str
    ) -> Optional[Tuple[str, str, str]]:
        """从 YAML M2M 关联推导 (through, source_key, target_key)"""
        if not all([source_entity, target_entity, association_name]):
            return None

        cache_key = f'm2m:{source_entity}:{target_entity}:{association_name}'
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        try:
            obj = registry.get(source_entity)
            if obj and hasattr(obj, 'associations'):
                assoc = obj.associations.get(association_name)
                if assoc:
                    through = getattr(assoc, 'through', f'{source_entity}_{association_name}')
                    source_key = getattr(assoc, 'source_key', f'{source_entity}_id')
                    target_key = getattr(assoc, 'target_key', f'{target_entity}_id')
                    result = (through, source_key, target_key)
                    cls._cache[cache_key] = result
                    return result
        except Exception as e:
            logger.warning(
                "Cannot resolve M2M info for '%s.%s': %s",
                source_entity, association_name, e
            )

        return None

    # ── 显示字段映射 ──

    @classmethod
    def get_display_field(cls, entity_name: str) -> str:
        """从 YAML 元模型获取实体的显示字段"""
        if not entity_name:
            return 'name'

        cache_key = f'display:{entity_name}'
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        try:
            obj = registry.get(entity_name)
            if obj:
                display = (
                    getattr(obj, 'display_field', None) or
                    getattr(obj, 'display_name_field', None)
                )
                if display:
                    cls._cache[cache_key] = display
                    return display
        except Exception as e:
            logger.debug("Cannot resolve display field for '%s': %s", entity_name, e)

        result = 'name'
        cls._cache[cache_key] = result
        return result

    # ── 表名映射 ──

    @classmethod
    def get_table_name(cls, entity_name: str) -> str:
        """从 YAML 元模型获取实体的表名"""
        if not entity_name:
            return entity_name

        cache_key = f'table:{entity_name}'
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        try:
            obj = registry.get(entity_name)
            if obj and hasattr(obj, 'table_name') and obj.table_name:
                cls._cache[cache_key] = obj.table_name
                return obj.table_name
        except Exception as e:
            logger.debug("Cannot resolve table name for '%s': %s", entity_name, e)

        cls._cache[cache_key] = entity_name
        return entity_name

    # ── 导航启用推断 ──

    @staticmethod
    def is_navigation_enabled(association_type: str) -> bool:
        """根据关联类型判断是否默认启用导航"""
        return association_type in ('many_to_many', 'composition', 'reverse_many_to_many')

    # ── 缓存管理 ──

    @classmethod
    def clear_cache(cls):
        """清除所有缓存（YAML 重载后调用）"""
        cls._cache.clear()
