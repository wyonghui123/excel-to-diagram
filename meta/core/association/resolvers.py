# -*- coding: utf-8 -*-
from typing import Dict, Optional, List

from meta.core.models import registry


def resolve_assoc_meta(object_type: str, association_name: str) -> Optional[Dict]:
    """解析关联元数据"""
    meta_obj = registry.get(object_type)
    if meta_obj is None:
        return None

    associations = getattr(meta_obj, 'associations', None)
    if associations is None:
        return None

    if isinstance(associations, dict):
        assoc = associations.get(association_name)
        if assoc is None:
            return None
        return _to_dict(assoc)

    if isinstance(associations, list):
        for assoc in associations:
            name = _get_attr(assoc, 'name')
            if name == association_name:
                return _to_dict(assoc)

    return None


def _to_dict(obj) -> Dict:
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, '__dict__'):
        d = {}
        for key, value in obj.__dict__.items():
            if hasattr(value, '__dict__'):
                d[key] = _to_dict(value)
            elif isinstance(value, dict):
                d[key] = {k: _to_dict(v) if hasattr(v, '__dict__') else v for k, v in value.items()}
            else:
                d[key] = value
        return d
    return {}


def _get_attr(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def get_search_fields(target_meta) -> List[str]:
    """获取可用于搜索的文本字段"""
    if not target_meta:
        return []
    fields = getattr(target_meta, 'fields', [])
    result = []
    for f in fields:
        field_type = getattr(f, 'field_type', None)
        if field_type is not None:
            type_value = field_type.value if hasattr(field_type, 'value') else str(field_type)
        else:
            continue
        if type_value in ('string', 'text', 'varchar', 'email'):
            db_column = getattr(f, 'db_column', None) or getattr(f, 'name', '')
            if db_column:
                result.append(db_column)
    return result
