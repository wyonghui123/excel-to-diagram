# -*- coding: utf-8 -*-
"""
层级树服务

基于 hierarchies.yaml 配置，动态构建层级树结构。
替代 meta_api.py 中硬编码的 _build_hierarchy_tree() 函数。
"""

import logging
from typing import Any, Dict, List, Optional

from meta.core.yaml_loader import load_yaml_directory
from meta.core.models import registry

logger = logging.getLogger(__name__)


class HierarchyService:
    """
    配置驱动的层级树服务

    基于 hierarchies.yaml 中定义的层级结构，动态构建嵌套树。
    支持从任意层级开始构建子树，支持版本上下文过滤。
    """

    def __init__(self, schema_dir: str = None):
        self._hierarchy_config = None
        self._schema_dir = schema_dir
        self._load_config()

    def _load_config(self):
        if self._schema_dir:
            objects = load_yaml_directory(self._schema_dir)
            for obj in objects:
                if obj.id == 'hierarchies':
                    self._hierarchy_config = obj
                    break

        if not self._hierarchy_config:
            from meta.core.models import registry
            self._hierarchy_config = registry.get('hierarchies')

    def get_hierarchy(self, hierarchy_id: str = 'biz_hierarchy') -> Optional[Dict]:
        if not self._hierarchy_config:
            return None
        hierarchies = getattr(self._hierarchy_config, 'fields', [])
        for h in hierarchies:
            if h.id == hierarchy_id:
                return {
                    'id': h.id,
                    'name': h.name,
                    'levels': getattr(h, 'enum_values', [])
                }
        return None

    def get_levels(self, hierarchy_id: str = 'biz_hierarchy') -> List[Dict]:
        from meta.services.cascade_service import HierarchyConfigLoader
        loader = HierarchyConfigLoader()
        return loader.get_levels(hierarchy_id)

    def build_tree(
        self,
        object_type: str = None,
        parent_id: int = None,
        version_id: int = None,
        levels: List[str] = None,
        include_relation_counts: bool = True,
        data_source=None
    ) -> List[Dict[str, Any]]:
        if not data_source:
            from meta.core.datasource import get_data_source
            import os
            db_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), '..', 'architecture.db'
            )
            data_source = get_data_source("sqlite", database=db_path)

        hierarchy_levels = self.get_levels()
        if not hierarchy_levels:
            logger.warning("[HierarchyService] No hierarchy levels found, falling back")
            return []

        if not levels:
            levels = [lv['object'] for lv in hierarchy_levels]

        start_level_idx = 0
        if object_type:
            for i, lv in enumerate(hierarchy_levels):
                if lv['object'] == object_type:
                    start_level_idx = i
                    break

        relation_counts = {}
        if include_relation_counts:
            relation_counts = self._compute_relation_counts(data_source, version_id)

        if object_type and parent_id:
            return self._build_subtree(
                data_source, hierarchy_levels, levels,
                start_level_idx, parent_id, version_id,
                relation_counts
            )

        return self._build_full_tree(
            data_source, hierarchy_levels, levels,
            start_level_idx, version_id,
            relation_counts
        )

    def _build_full_tree(
        self, ds, hierarchy_levels, levels,
        start_idx, version_id, relation_counts
    ) -> List[Dict]:
        if start_idx >= len(hierarchy_levels):
            return []

        root_level = hierarchy_levels[start_idx]
        root_object = root_level['object']
        root_table = root_level.get('table_name', f"{root_object}s")

        meta_obj = registry.get(root_object)
        display_field = 'name'
        if meta_obj and meta_obj.display_name_field:
            display_field = meta_obj.display_name_field

        where_clause = ""
        params = []
        if version_id and root_object not in ('product',):
            where_clause = "WHERE version_id = ?"
            params = [version_id]

        try:
            cursor = ds.execute(
                f"SELECT id, {display_field}, code FROM {root_table} {where_clause} ORDER BY {display_field}",
                params
            )
            rows = cursor.fetchall()
        except Exception as e:
            logger.error(f"[HierarchyService] Error querying {root_table}: {e}")
            return []

        tree = []
        for row in rows:
            node = {
                'id': f'{root_object}_{row[0]}',
                'key': row[0],
                'name': row[1],
                'code': row[2] if len(row) > 2 else '',
                'level': root_object,
                'relation_count': relation_counts.get((root_object, row[0]), 0),
                'children': []
            }

            if start_idx + 1 < len(hierarchy_levels) and hierarchy_levels[start_idx + 1]['object'] in levels:
                child_nodes = self._build_subtree(
                    ds, hierarchy_levels, levels,
                    start_idx + 1, row[0], version_id,
                    relation_counts
                )
                node['children'] = child_nodes

            next_level_obj = hierarchy_levels[start_idx + 1]['object'] if start_idx + 1 < len(hierarchy_levels) else None
            if node['children'] or next_level_obj not in levels:
                tree.append(node)

        return tree

    def _build_subtree(
        self, ds, hierarchy_levels, levels,
        level_idx, parent_id, version_id,
        relation_counts
    ) -> List[Dict]:
        if level_idx >= len(hierarchy_levels):
            return []

        level = hierarchy_levels[level_idx]
        obj_type = level['object']
        table_name = level.get('table_name', f"{obj_type}s")
        fk_field = level.get('foreign_key_field', '')

        meta_obj = registry.get(obj_type)
        display_field = 'name'
        if meta_obj and meta_obj.display_name_field:
            display_field = meta_obj.display_name_field

        where_parts = []
        params = []

        if fk_field:
            where_parts.append(f"{fk_field} = ?")
            params.append(parent_id)

        if version_id and obj_type not in ('product',):
            where_parts.append("version_id = ?")
            params.append(version_id)

        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        try:
            cursor = ds.execute(
                f"SELECT id, {display_field}, code FROM {table_name} {where_clause} ORDER BY {display_field}",
                params
            )
            rows = cursor.fetchall()
        except Exception as e:
            logger.error(f"[HierarchyService] Error querying {table_name}: {e}")
            return []

        nodes = []
        for row in rows:
            node = {
                'id': f'{obj_type}_{row[0]}',
                'key': row[0],
                'name': row[1],
                'code': row[2] if len(row) > 2 else '',
                'level': obj_type,
                'relation_count': relation_counts.get((obj_type, row[0]), 0),
            }

            is_leaf = level_idx + 1 >= len(hierarchy_levels) or hierarchy_levels[level_idx + 1]['object'] not in levels
            if is_leaf:
                node['isLeaf'] = True
            else:
                child_nodes = self._build_subtree(
                    ds, hierarchy_levels, levels,
                    level_idx + 1, row[0], version_id,
                    relation_counts
                )
                node['children'] = child_nodes

            nodes.append(node)

        return nodes

    def _compute_relation_counts(self, ds, version_id: int = None) -> Dict:
        from meta.api.meta_api import _compute_tree_relation_counts
        return _compute_tree_relation_counts(ds, version_id)
