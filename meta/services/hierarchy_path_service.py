# -*- coding: utf-8 -*-
"""
层级路径计算服务

提供对象层级路径的计算能力，支持从根节点到当前对象的完整路径
"""

from typing import Dict, List, Tuple, Optional, Any
import yaml
import os
import logging

from meta.core.yaml_loader import registry

logger = logging.getLogger(__name__)


class HierarchyPathService:
    """
    层级路径计算服务
    
    解析层级定义，计算对象的完整层级路径
    """
    
    def __init__(self, data_source, hierarchies_file: str = None):
        """
        初始化层级路径服务
        
        Args:
            data_source: 数据源对象
            hierarchies_file: 层级定义文件路径（可选）
        """
        self.data_source = data_source
        self._hierarchies = None
        self._hierarchy_paths = None
        self._cache = {}
        
        if hierarchies_file:
            self._load_hierarchies(hierarchies_file)
        else:
            default_path = os.path.join(
                os.path.dirname(__file__),
                '..',
                'schemas',
                'hierarchies.yaml'
            )
            if os.path.exists(default_path):
                self._load_hierarchies(default_path)
    
    def _load_hierarchies(self, file_path: str):
        """
        加载层级定义文件
        
        Args:
            file_path: YAML 文件路径
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                
            self._hierarchies = {}
            for h in data.get('hierarchies', []):
                self._hierarchies[h['id']] = h
            
            self._hierarchy_paths = {}
            for p in data.get('hierarchy_paths', []):
                self._hierarchy_paths[p['id']] = p
            
            logger.info(f"Loaded {len(self._hierarchies)} hierarchies and {len(self._hierarchy_paths)} paths from {file_path}")
            
        except Exception as e:
            logger.error(f"Failed to load hierarchies from {file_path}: {e}")
            self._hierarchies = {}
            self._hierarchy_paths = {}
    
    def get_full_path(
        self,
        object_type: str,
        object_id: int,
        path_type: str = 'full_path',
        max_length: int = 80,
        separator: str = ' → ',
        include_root: bool = True
    ) -> Dict[str, Any]:
        """
        获取对象的完整层级路径
        
        Args:
            object_type: 对象类型
            object_id: 对象 ID
            path_type: 路径类型（对应 hierarchy_paths 中的 id）
            max_length: 最大长度（超过时截断）
            separator: 分隔符
            include_root: 是否包含根节点
        
        Returns:
            {
                'full': 'ERP产品 → V5 → 供应链云',
                'short': '供应链云 (V5)',
                'segments': [...],
                'depth': 3,
                'truncated': False
            }
        """
        if not object_type or not object_id:
            return {
                'full': '',
                'short': '',
                'segments': [],
                'depth': 0,
                'truncated': False
            }
        
        cache_key = f"{object_type}:{object_id}:{path_type}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        try:
            path_config = self._hierarchy_paths.get(path_type) if self._hierarchy_paths else None
            
            if path_config:
                result = self._calculate_path_from_config(object_type, object_id, path_config, separator, max_length)
            else:
                result = self._calculate_path_from_hierarchy(object_type, object_id, separator, max_length, include_root)
            
            self._cache[cache_key] = result
            return result
            
        except Exception as e:
            logger.error(f"Failed to get path for {object_type}:{object_id}: {e}")
            import traceback
            traceback.print_exc()
            return {
                'full': f"{object_type}:{object_id}",
                'short': f"{object_type}:{object_id}",
                'segments': [],
                'depth': 0,
                'truncated': False
            }
    
    def _calculate_path_from_config(
        self,
        object_type: str,
        object_id: int,
        path_config: Dict,
        separator: str,
        max_length: int
    ) -> Dict[str, Any]:
        """
        根据路径配置计算路径
        """
        hierarchy_id = path_config.get('hierarchy')
        hierarchy = self._hierarchies.get(hierarchy_id) if hierarchy_id and self._hierarchies else None
        
        if not hierarchy:
            logger.warning(f"Hierarchy '{hierarchy_id}' not found")
            return self._calculate_path_from_hierarchy(object_type, object_id, separator, max_length, True)
        
        segments_config = path_config.get('segments', [])
        
        path_chain = self._get_parent_chain(object_type, object_id, hierarchy)
        
        segments = []
        for seg_config in segments_config:
            seg_object = seg_config['object']
            seg_field = seg_config.get('field', 'name')
            
            found = None
            for item in path_chain:
                if item['object_type'] == seg_object:
                    found = item
                    break
            
            if found:
                field_value = found.get(seg_field, '')
                if not field_value:
                    meta_obj = registry.get(seg_object)
                    if meta_obj:
                        table_name = meta_obj.table_name
                        query = f"SELECT {seg_field} FROM {table_name} WHERE id = ?"
                        cursor = self.data_source.execute(query, (found['id'],))
                        row = cursor.fetchone()
                        if row:
                            field_value = row[0] or ''
                
                segments.append({
                    'object_type': seg_object,
                    'field': seg_field,
                    'value': str(field_value)
                })
        
        full_path = separator.join([s['value'] for s in segments if s['value']])
        
        truncated = False
        if len(full_path) > max_length:
            full_path = full_path[:max_length-3] + '...'
            truncated = True
        
        short_path = segments[-1]['value'] if segments else ''
        if len(segments) > 1:
            parent_value = segments[-2]['value'] if len(segments) >= 2 else ''
            if parent_value:
                short_path = f"{short_path} ({parent_value})"
        
        return {
            'full': full_path,
            'short': short_path,
            'segments': segments,
            'depth': len(segments),
            'truncated': truncated
        }
    
    def _calculate_path_from_hierarchy(
        self,
        object_type: str,
        object_id: int,
        separator: str,
        max_length: int,
        include_root: bool
    ) -> Dict[str, Any]:
        """
        根据层级定义计算路径
        """
        hierarchy = None
        if self._hierarchies:
            for h in self._hierarchies.values():
                for level in h.get('levels', []):
                    if level['object'] == object_type:
                        hierarchy = h
                        break
                if hierarchy:
                    break
        
        if not hierarchy:
            logger.warning(f"No hierarchy found for object type '{object_type}'")
            return {
                'full': f"{object_type}:{object_id}",
                'short': f"{object_type}:{object_id}",
                'segments': [],
                'depth': 0,
                'truncated': False
            }
        
        path_chain = self._get_parent_chain(object_type, object_id, hierarchy)
        
        if not include_root and path_chain:
            path_chain = path_chain[1:]
        
        segments = []
        for item in path_chain:
            name = item.get('name', '')
            if not name:
                name = item.get('code', '')
            
            segments.append({
                'object_type': item['object_type'],
                'id': item['id'],
                'value': str(name)
            })
        
        full_path = separator.join([s['value'] for s in segments if s['value']])
        
        truncated = False
        if len(full_path) > max_length:
            full_path = full_path[:max_length-3] + '...'
            truncated = True
        
        short_path = segments[-1]['value'] if segments else ''
        if len(segments) > 1:
            parent_value = segments[-2]['value'] if len(segments) >= 2 else ''
            if parent_value:
                short_path = f"{short_path} ({parent_value})"
        
        return {
            'full': full_path,
            'short': short_path,
            'segments': segments,
            'depth': len(segments),
            'truncated': truncated
        }
    
    def _get_parent_chain(
        self,
        object_type: str,
        object_id: int,
        hierarchy: Dict
    ) -> List[Dict]:
        """
        获取从根节点到当前对象的父级链
        
        Args:
            object_type: 对象类型
            object_id: 对象 ID
            hierarchy: 层级定义
        
        Returns:
            父级链列表，从根节点开始
        """
        chain = []
        
        levels = {level['object']: level for level in hierarchy.get('levels', [])}
        
        current_type = object_type
        current_id = object_id
        
        while current_type and current_id:
            level_config = levels.get(current_type)
            if not level_config:
                break
            
            meta_obj = registry.get(current_type)
            if not meta_obj:
                break
            
            table_name = meta_obj.table_name
            
            query = f"SELECT * FROM {table_name} WHERE id = ?"
            cursor = self.data_source.execute(query, (current_id,))
            row = cursor.fetchone()
            
            if not row:
                break
            
            columns = [desc[0] for desc in cursor.description]
            record = dict(zip(columns, row))
            
            chain.append({
                'object_type': current_type,
                'id': current_id,
                'name': record.get('name', ''),
                'code': record.get('code', ''),
                'record': record
            })
            
            parent_object = level_config.get('parent_object')
            if not parent_object:
                break
            
            fk_field = level_config.get('foreign_key_field')
            if not fk_field:
                break
            
            parent_id = record.get(fk_field)
            if not parent_id:
                break
            
            current_type = parent_object
            current_id = parent_id
        
        chain.reverse()
        return chain
    
    def batch_get_paths(
        self,
        requests: List[Tuple[str, int]],
        path_type: str = 'full_path',
        separator: str = ' → ',
        max_length: int = 80
    ) -> Dict[Tuple[str, int], Dict[str, Any]]:
        """
        批量获取层级路径
        
        Args:
            requests: 对象列表 [(object_type, object_id), ...]
            path_type: 路径类型
            separator: 分隔符
            max_length: 最大长度
        
        Returns:
            映射字典，键为 (object_type, object_id)，值为路径对象
        """
        results = {}
        
        for object_type, object_id in requests:
            result = self.get_full_path(object_type, object_id, path_type, max_length, separator)
            results[(object_type, object_id)] = result
        
        return results
    
    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
        logger.info("HierarchyPathService cache cleared")
