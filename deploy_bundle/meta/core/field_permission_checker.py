# -*- coding: utf-8 -*-
"""
字段级权限校验服务

基于 MetaField.permission (PermissionAnnotation) 实现细粒度字段权限控制：
- readable: 字段是否可读（影响列表/详情返回）
- writable: 字段是否可写（影响创建/更新请求）
- roles: 允许访问的角色列表（空列表表示所有角色）

设计参考：
- Salesforce Field-Level Security (FLS)
- SAP Authorization Objects for fields
"""

from typing import Dict, List, Any, Optional, Set
from meta.core.models import registry, MetaObject, MetaField


class FieldPermissionChecker:
    """字段级权限校验器"""

    def __init__(self, user_roles: Optional[List[str]] = None):
        self._user_roles: Set[str] = set(user_roles or [])

    def set_user_roles(self, roles: List[str]):
        self._user_roles = set(roles)

    def filter_readable_fields(self, object_type: str, record: Dict[str, Any]) -> Dict[str, Any]:
        """过滤不可读字段，返回仅包含可读字段的记录"""
        meta_obj = registry.get(object_type)
        if not meta_obj:
            return record

        readable_keys = set()
        for field in meta_obj.fields:
            if self._is_field_readable(field):
                readable_keys.add(field.db_column or field.id)
                if field.id != (field.db_column or field.id):
                    readable_keys.add(field.id)

        return {k: v for k, v in record.items() if k in readable_keys}

    def filter_writable_fields(self, object_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """过滤不可写字段，返回仅包含可写字段的数据"""
        meta_obj = registry.get(object_type)
        if not meta_obj:
            return data

        writable_keys = set()
        for field in meta_obj.fields:
            if self._is_field_writable(field):
                writable_keys.add(field.db_column or field.id)
                if field.id != (field.db_column or field.id):
                    writable_keys.add(field.id)

        return {k: v for k, v in data.items() if k in writable_keys}

    def get_hidden_fields(self, object_type: str) -> List[str]:
        """获取对当前用户隐藏的字段列表"""
        meta_obj = registry.get(object_type)
        if not meta_obj:
            return []

        hidden = []
        for field in meta_obj.fields:
            if not self._is_field_readable(field):
                hidden.append(field.id)
        return hidden

    def get_readonly_fields(self, object_type: str) -> List[str]:
        """获取对当前用户只读的字段列表"""
        meta_obj = registry.get(object_type)
        if not meta_obj:
            return []

        readonly = []
        for field in meta_obj.fields:
            if self._is_field_readable(field) and not self._is_field_writable(field):
                readonly.append(field.id)
        return readonly

    def _is_field_readable(self, field: MetaField) -> bool:
        perm = getattr(field, 'permission', None)
        if perm is None:
            return True

        if not perm.readable:
            return False

        if perm.roles and not self._user_roles.intersection(perm.roles):
            return False

        return True

    def _is_field_writable(self, field: MetaField) -> bool:
        perm = getattr(field, 'permission', None)
        if perm is None:
            return True

        if not perm.writable:
            return False

        if perm.roles and not self._user_roles.intersection(perm.roles):
            return False

        return True


_field_permission_checker: Optional[FieldPermissionChecker] = None


def get_field_permission_checker() -> FieldPermissionChecker:
    global _field_permission_checker
    if _field_permission_checker is None:
        _field_permission_checker = FieldPermissionChecker()
    return _field_permission_checker


def init_field_permission_checker(user_roles: Optional[List[str]] = None) -> FieldPermissionChecker:
    global _field_permission_checker
    _field_permission_checker = FieldPermissionChecker(user_roles)
    return _field_permission_checker
