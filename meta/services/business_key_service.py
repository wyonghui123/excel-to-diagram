# -*- coding: utf-8 -*-
"""
业务键转换服务

提供元数据驱动的 ID → Business Key 转换能力
"""

from typing import Dict, List, Tuple, Optional, Any
from functools import lru_cache
import logging

from meta.core.yaml_loader import registry

logger = logging.getLogger(__name__)


class BusinessKeyService:
    """
    业务键转换服务
    
    从元数据动态读取 business_key 字段定义，提供 ID 到业务键的转换能力
    """
    
    def __init__(self, data_source):
        """
        初始化业务键服务
        
        Args:
            data_source: 数据源对象，需提供 execute() 方法
        """
        self.data_source = data_source
        self._cache = {}
    
    def id_to_business_key(
        self,
        object_type: str,
        object_id: int,
        format: str = 'full'
    ) -> str:
        """
        将对象 ID 转换为业务键
        
        Args:
            object_type: 对象类型（如 'domain', 'sub_domain' 等）
            object_id: 对象 ID
            format: 输出格式
                - 'full': 完整格式（含层级）
                - 'short': 简短格式（名称 + 编码）
                - 'minimal': 最小格式（仅编码）
        
        Returns:
            业务键字符串
        """
        if not object_type or not object_id:
            return ''
        
        cache_key = f"{object_type}:{object_id}:{format}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        try:
            meta_obj = registry.get(object_type)
            if not meta_obj:
                logger.warning(f"Object type '{object_type}' not found in registry")
                return f"{object_type}:{object_id}"
            
            bk_fields = [
                f for f in meta_obj.fields 
                if f.semantics and f.semantics.business_key
            ]
            
            if not bk_fields:
                logger.warning(f"No business_key fields defined for '{object_type}'")
                return f"{object_type}:{object_id}"
            
            bk_fields_sorted = sorted(bk_fields, key=lambda f: f.semantics.import_order if f.semantics.import_order is not None else 100)
            
            field_names = []
            for f in bk_fields_sorted:
                if f.semantics and f.semantics.virtual:
                    continue
                if f.db_column:
                    field_names.append(f.db_column)
                else:
                    field_names.append(f.id)
            
            if not field_names:
                logger.warning(f"No non-virtual business_key fields for '{object_type}'")
                return f"{object_type}:{object_id}"
            
            fields_str = ', '.join(field_names)
            table_name = meta_obj.table_name
            
            query = f"SELECT {fields_str} FROM {table_name} WHERE id = ?"
            cursor = self.data_source.execute(query, (int(object_id),))
            row = cursor.fetchone()
            
            if not row:
                logger.warning(f"Record not found: {object_type}:{object_id}")
                return f"{object_type}:{object_id}"
            
            field_values = {}
            for i, field in enumerate(bk_fields_sorted):
                if field.semantics and field.semantics.virtual:
                    continue
                field_values[field.id] = row[i] if i < len(row) else ''
            
            result = self._format_business_key(field_values, bk_fields_sorted, format)
            
            self._cache[cache_key] = result
            return result
            
        except Exception as e:
            logger.error(f"Failed to convert {object_type}:{object_id} to business key: {e}")
            import traceback
            traceback.print_exc()
            return f"{object_type}:{object_id}"
    
    def _format_business_key(
        self,
        field_values: Dict[str, Any],
        bk_fields: List,
        format: str
    ) -> str:
        """
        格式化业务键
        
        Args:
            field_values: 字段值字典
            bk_fields: 业务键字段列表
            format: 输出格式
        
        Returns:
            格式化的业务键字符串
        """
        name_field = None
        code_field = None
        
        for f in bk_fields:
            if f.semantics:
                if f.semantics.display_name:
                    name_field = f
                if f.semantics.data_category == 'code':
                    code_field = f
        
        if not name_field:
            for f in bk_fields:
                if 'name' in f.id.lower():
                    name_field = f
                    break
        
        if not code_field:
            for f in bk_fields:
                if 'code' in f.id.lower():
                    code_field = f
                    break
        
        name_value = field_values.get(name_field.id, '') if name_field else ''
        code_value = field_values.get(code_field.id, '') if code_field else ''
        
        if format == 'minimal':
            return str(code_value) if code_value else str(name_value)
        
        elif format == 'short':
            if name_value and code_value:
                return f"{name_value} ({code_value})"
            elif name_value:
                return str(name_value)
            elif code_value:
                return str(code_value)
            else:
                return ''
        
        else:
            parts = []
            for f in bk_fields:
                if f.semantics and f.semantics.virtual:
                    continue
                value = field_values.get(f.id, '')
                if value:
                    parts.append(str(value))
            
            if parts:
                return ' → '.join(parts)
            else:
                return ''
    
    def batch_convert(
        self,
        requests: List[Tuple[str, int]],
        format: str = 'full'
    ) -> Dict[Tuple[str, int], str]:
        """
        批量转换 ID 到业务键
        
        Args:
            requests: 对象列表，格式为 [(object_type, object_id), ...]
            format: 输出格式
        
        Returns:
            映射字典，键为 (object_type, object_id)，值为业务键
        """
        results = {}
        
        grouped = {}
        for object_type, object_id in requests:
            if object_type not in grouped:
                grouped[object_type] = []
            grouped[object_type].append(object_id)
        
        for object_type, object_ids in grouped.items():
            meta_obj = registry.get(object_type)
            if not meta_obj:
                for object_id in object_ids:
                    results[(object_type, object_id)] = f"{object_type}:{object_id}"
                continue
            
            bk_fields = [
                f for f in meta_obj.fields 
                if f.semantics and f.semantics.business_key
            ]
            
            if not bk_fields:
                for object_id in object_ids:
                    results[(object_type, object_id)] = f"{object_type}:{object_id}"
                continue
            
            bk_fields_sorted = sorted(bk_fields, key=lambda f: f.semantics.import_order if f.semantics.import_order is not None else 100)
            
            field_names = []
            for f in bk_fields_sorted:
                if f.semantics and f.semantics.virtual:
                    continue
                if f.db_column:
                    field_names.append(f.db_column)
                else:
                    field_names.append(f.id)
            
            if not field_names:
                for object_id in object_ids:
                    results[(object_type, object_id)] = f"{object_type}:{object_id}"
                continue
            
            fields_str = ', '.join(field_names)
            table_name = meta_obj.table_name
            
            placeholders = ', '.join(['?' for _ in object_ids])
            query = f"SELECT id, {fields_str} FROM {table_name} WHERE id IN ({placeholders})"
            
            try:
                cursor = self.data_source.execute(query, tuple(object_ids))
                rows = cursor.fetchall()
                
                row_dict = {}
                for row in rows:
                    row_dict[row[0]] = row[1:]
                
                for object_id in object_ids:
                    if object_id in row_dict:
                        row = row_dict[object_id]
                        field_values = {}
                        for i, field in enumerate(bk_fields_sorted):
                            if field.semantics and field.semantics.virtual:
                                continue
                            field_values[field.id] = row[i] if i < len(row) else ''
                        
                        result = self._format_business_key(field_values, bk_fields_sorted, format)
                        results[(object_type, object_id)] = result
                    else:
                        results[(object_type, object_id)] = f"{object_type}:{object_id}"
            
            except Exception as e:
                logger.error(f"Failed to batch convert {object_type}: {e}")
                for object_id in object_ids:
                    results[(object_type, object_id)] = f"{object_type}:{object_id}"
        
        for key, value in results.items():
            cache_key = f"{key[0]}:{key[1]}:{format}"
            self._cache[cache_key] = value
        
        return results
    
    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
        logger.info("BusinessKeyService cache cleared")
