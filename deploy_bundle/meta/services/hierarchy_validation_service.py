# -*- coding: utf-8 -*-
"""
层级校验服务

提供层级关系的校验规则：
1. 编辑时父元素不可变校验 - 防止变更父级关联字段
2. 删除时子元素存在校验 - 防止删除有子元素的记录
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

from meta.core.datasource import DataSource
from meta.core.models import registry
from meta.services.cascade_service import CascadeService, HierarchyConfigLoader
from meta.core.validation_messages import ValidationMessageRegistry


@dataclass
class ValidationResult:
    """校验结果"""
    valid: bool
    error_code: str = ""
    message: str = ""
    details: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.details is None:
            self.details = {}


def _get_parent_fields_by_object() -> Dict[str, List[str]]:
    """从配置获取每个对象的父字段列表"""
    result = {}
    levels = HierarchyConfigLoader.get_levels('biz_hierarchy')
    
    for level in levels:
        obj = level.get('object')
        parent = level.get('parent_object')
        fk = level.get('foreign_key_field')
        
        if obj and parent and fk:
            if obj not in result:
                result[obj] = []
            result[obj].append(fk)
    
    if 'version' not in result:
        result['version'] = ['product_id']
    
    return result


def _get_immutable_parent_fields() -> Dict[str, List[str]]:
    """获取不可变的父字段列表"""
    return _get_parent_fields_by_object()


class HierarchyValidationService:
    """层级校验服务"""
    
    def __init__(self, datasource: DataSource):
        self.ds = datasource
        self.cascade_service = CascadeService(datasource)
        self._parent_fields_cache = None
        self._immutable_fields_cache = None
    
    def _get_parent_fields(self) -> Dict[str, List[str]]:
        """获取父字段映射（缓存）"""
        if self._parent_fields_cache is None:
            self._parent_fields_cache = _get_parent_fields_by_object()
        return self._parent_fields_cache
    
    def _get_immutable_fields(self) -> Dict[str, List[str]]:
        """获取不可变字段映射（缓存）"""
        if self._immutable_fields_cache is None:
            self._immutable_fields_cache = _get_immutable_parent_fields()
        return self._immutable_fields_cache
    
    def validate_parent_field_immutable(self, object_type: str, 
                                         original_data: Dict[str, Any],
                                         new_data: Dict[str, Any]) -> ValidationResult:
        """
        校验父元素字段不可变
        
        Args:
            object_type: 对象类型
            original_data: 原始数据
            new_data: 新数据
            
        Returns:
            ValidationResult
        """
        immutable_fields = self._get_immutable_fields().get(object_type, [])
        
        for field in immutable_fields:
            if field in new_data:
                original_value = original_data.get(field)
                new_value = new_data.get(field)
                
                if original_value is not None and new_value is not None:
                    if str(original_value) != str(new_value):
                        field_name = self._get_field_display_name(object_type, field)
                        return ValidationResult(
                            valid=False,
                            error_code="PARENT_FIELD_IMMUTABLE",
                            message=ValidationMessageRegistry.get("validation.object.parent_field_immutable",
                                                                     field_name=field_name),
                            details={
                                "field": field,
                                "original_value": original_value,
                                "new_value": new_value
                            }
                        )
        
        return ValidationResult(valid=True)
    
    def validate_no_children_before_delete(self, object_type: str, 
                                            object_id: Any) -> ValidationResult:
        """
        校验删除前没有子元素
        
        Args:
            object_type: 对象类型
            object_id: 对象ID
            
        Returns:
            ValidationResult
        """
        child_types = HierarchyConfigLoader.get_child_types(object_type)
        
        if not child_types:
            return ValidationResult(valid=True)
        
        children_info = {}
        total_children = 0
        
        for child_type in child_types:
            count = self._count_children(object_type, child_type, object_id)
            if count > 0:
                children_info[child_type] = count
                total_children += count
        
        if total_children > 0:
            child_names = self._get_object_display_names(list(children_info.keys()))
            details = ", ".join([f"{name}: {count}" for name, count in zip(child_names, children_info.values())])
            
            return ValidationResult(
                valid=False,
                error_code="HAS_CHILDREN",
                message=ValidationMessageRegistry.get("validation.object.has_children",
                                                       count=total_children),
                details={
                    "total_children": total_children,
                    "children_by_type": children_info
                }
            )
        
        return ValidationResult(valid=True)
    
    def _count_children(self, parent_type: str, child_type: str, parent_id: Any) -> int:
        """统计子元素数量"""
        child_meta = registry.get(child_type)
        if not child_meta:
            return 0
        
        table = child_meta.table_name
        
        if parent_type == "business_object" and child_type == "relationship":
            fk1 = "source_bo_id"
            fk2 = "target_bo_id"
            sql = f"SELECT COUNT(*) as cnt FROM {table} WHERE {fk1} = ? OR {fk2} = ?"
            cursor = self.ds.execute(sql, (parent_id, parent_id))
            row = cursor.fetchone()
            return row[0] if row else 0
        else:
            fk = HierarchyConfigLoader.get_foreign_key(child_type) or f"{parent_type}_id"
            sql = f"SELECT COUNT(*) as cnt FROM {table} WHERE {fk} = ?"
            cursor = self.ds.execute(sql, (parent_id,))
            row = cursor.fetchone()
            return row[0] if row else 0
    
    def _get_field_display_name(self, object_type: str, field_id: str) -> str:
        """获取字段显示名称"""
        meta = registry.get(object_type)
        if meta:
            for field in meta.fields:
                if field.id == field_id:
                    return field.name or field_id
        return field_id
    
    def _get_object_display_names(self, object_types: List[str]) -> List[str]:
        """获取对象类型显示名称"""
        names = []
        for obj_type in object_types:
            meta = registry.get(obj_type)
            if meta:
                names.append(meta.name or obj_type)
            else:
                names.append(obj_type)
        return names


def validate_update(object_type: str, original_data: Dict[str, Any],
                    new_data: Dict[str, Any], datasource: DataSource) -> ValidationResult:
    """
    校验更新操作
    
    Args:
        object_type: 对象类型
        original_data: 原始数据
        new_data: 新数据
        datasource: 数据源
        
    Returns:
        ValidationResult
    """
    service = HierarchyValidationService(datasource)
    return service.validate_parent_field_immutable(object_type, original_data, new_data)


def validate_delete(object_type: str, object_id: Any, 
                    datasource: DataSource) -> ValidationResult:
    """
    校验删除操作
    
    Args:
        object_type: 对象类型
        object_id: 对象ID
        datasource: 数据源
        
    Returns:
        ValidationResult
    """
    service = HierarchyValidationService(datasource)
    return service.validate_no_children_before_delete(object_type, object_id)
