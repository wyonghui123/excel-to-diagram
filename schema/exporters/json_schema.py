"""
schema/exporters/json_schema.py - M13 v1.1.0 JSON Schema 导出器

从 M9 ENTITY_SCHEMAS 派生 JSON Schema (draft-07)。

用法：
    from schema.exporters.json_schema import (
        export_json_schema,
        export_json_schema_all,
    )

    # 单个 entity
    schema = export_json_schema('User')
    # schema = {'$schema': '...', 'type': 'object', 'properties': {...}}

    # 所有 entity
    all_schemas = export_json_schema_all()
    # all_schemas = {'User': {...}, 'Order': {...}, ...}
"""
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


# Python → JSON Schema 类型映射
PYTHON_TO_JSON_TYPE = {
    'str': 'string',
    'string': 'string',
    'int': 'integer',
    'integer': 'integer',
    'float': 'number',
    'double': 'number',
    'number': 'number',
    'bool': 'boolean',
    'boolean': 'boolean',
    'list': 'array',
    'array': 'array',
    'dict': 'object',
    'object': 'object',
    'datetime': 'string',
    'date': 'string',
    'time': 'string',
}


def _to_json_property(py_type: str, field_meta: dict) -> Dict:
    """Python 类型 + 字段元数据 → JSON Schema property"""
    mapping = {
        'datetime': {'type': 'string', 'format': 'date-time'},
        'date': {'type': 'string', 'format': 'date'},
        'time': {'type': 'string'},
        'int': {'type': 'integer'},
        'float': {'type': 'number'},
        'bool': {'type': 'boolean'},
    }
    if py_type in mapping:
        prop = mapping[py_type]
    else:
        prop = {'type': PYTHON_TO_JSON_TYPE.get(py_type, 'string')}

    # 添加 description
    if field_meta.get('description'):
        prop['description'] = field_meta['description']

    # 添加 deprecated 标记
    if field_meta.get('deprecated'):
        prop['deprecated'] = True

    # 添加 enum
    if field_meta.get('enum'):
        prop['enum'] = field_meta['enum']

    # nullable
    if field_meta.get('nullable'):
        if 'type' in prop:
            original_type = prop['type']
            prop['type'] = [original_type, 'null']

    return prop


def export_json_schema(entity_name: str) -> Dict:
    """导出单个 entity 的 JSON Schema

    Args:
        entity_name: entity 名（如 'User'）

    Returns:
        dict: JSON Schema (draft-07)
    """
    from meta.graphql import ENTITY_SCHEMAS
    if entity_name not in ENTITY_SCHEMAS:
        raise ValueError(f"Unknown entity: {entity_name}")
    entity_def = ENTITY_SCHEMAS[entity_name]

    properties = {}
    required = []
    for field in entity_def.get('fields', []):
        field_meta = entity_def.get('field_metadata', {}).get(field, {})
        py_type = field_meta.get('type', 'string')
        properties[field] = _to_json_property(py_type, field_meta)
        if field_meta.get('required'):
            required.append(field)

    schema = {
        '$schema': 'http://json-schema.org/draft-07/schema#',
        'title': entity_name,
        'type': 'object',
        'properties': properties,
    }
    if required:
        schema['required'] = required
    return schema


def export_json_schema_all() -> Dict[str, Dict]:
    """导出所有 entity 的 JSON Schema

    Returns:
        dict: {entity_name: schema_dict}
    """
    from meta.graphql import ENTITY_SCHEMAS
    return {
        entity_name: export_json_schema(entity_name)
        for entity_name in ENTITY_SCHEMAS.keys()
    }
