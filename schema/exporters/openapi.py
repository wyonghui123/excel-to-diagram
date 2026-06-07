"""
schema/exporters/openapi.py - M13 v1.1.0 OpenAPI 3.0 导出器

从 M9 ENTITY_SCHEMAS 派生 OpenAPI 3.0 spec。

用法：
    from schema.exporters.openapi import export_openapi, export_entity_openapi

    # 导出完整 spec
    spec = export_openapi()
    # spec = {'openapi': '3.0.0', 'info': {...}, 'paths': {...}, 'components': {...}}

    # 导出单个 entity 的 schema
    entity_schema = export_entity_openapi('User')
    # entity_schema = {'type': 'object', 'properties': {...}, 'required': [...]}
"""
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# Python → OpenAPI 类型映射
PYTHON_TO_OPENAPI_TYPE = {
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


def _to_openapi_type(python_type: str) -> Dict:
    """Python 类型 → OpenAPI schema 片段

    返回：{'type': 'string', 'format': 'date-time'} 等
    """
    mapping = {
        'datetime': {'type': 'string', 'format': 'date-time'},
        'date': {'type': 'string', 'format': 'date'},
        'time': {'type': 'string'},
        'int': {'type': 'integer', 'format': 'int64'},
        'float': {'type': 'number', 'format': 'double'},
        'bool': {'type': 'boolean'},
    }
    if python_type in mapping:
        return mapping[python_type]
    return {'type': PYTHON_TO_OPENAPI_TYPE.get(python_type, 'string')}


def _to_openapi_schema(entity_name: str, entity_def: dict) -> Dict:
    """单个 entity → OpenAPI schema dict"""
    properties = {}
    required = []
    for field in entity_def.get('fields', []):
        field_meta = entity_def.get('field_metadata', {}).get(field, {})
        py_type = field_meta.get('type', 'string')
        properties[field] = _to_openapi_type(py_type)
        if field_meta.get('description'):
            properties[field]['description'] = field_meta['description']
        if field_meta.get('deprecated'):
            properties[field]['deprecated'] = True
        if field_meta.get('required'):
            required.append(field)
    schema = {
        'type': 'object',
        'properties': properties,
    }
    if required:
        schema['required'] = required
    return schema


def _to_openapi_paths(entity_name: str, entity_def: dict) -> Dict:
    """生成 /api/v1/{entity_name}/* 路径"""
    object_type = entity_def.get('object_type', entity_name.lower())
    return {
        f'/api/v1/{object_type}': {
            'get': {
                'summary': f'List {entity_name}',
                'operationId': f'list_{object_type}',
                'responses': {
                    '200': {
                        'description': f'Success',
                        'content': {
                            'application/json': {
                                'schema': {
                                    'type': 'array',
                                    'items': {'$ref': f'#/components/schemas/{entity_name}'},
                                },
                            },
                        },
                    },
                },
            },
        },
        f'/api/v1/{object_type}/{{id}}': {
            'get': {
                'summary': f'Get {entity_name} by id',
                'operationId': f'get_{object_type}_by_id',
                'parameters': [
                    {
                        'name': 'id',
                        'in': 'path',
                        'required': True,
                        'schema': {'type': 'integer'},
                    },
                ],
                'responses': {
                    '200': {
                        'description': 'Success',
                        'content': {
                            'application/json': {
                                'schema': {'$ref': f'#/components/schemas/{entity_name}'},
                            },
                        },
                    },
                },
            },
        },
    }


def export_entity_openapi(entity_name: str) -> Dict:
    """导出单个 entity 的 OpenAPI schema

    Args:
        entity_name: entity 名（如 'User'）

    Returns:
        dict: OpenAPI schema 片段
    """
    from meta.graphql import ENTITY_SCHEMAS
    if entity_name not in ENTITY_SCHEMAS:
        raise ValueError(f"Unknown entity: {entity_name}")
    return _to_openapi_schema(entity_name, ENTITY_SCHEMAS[entity_name])


def export_openapi() -> Dict:
    """导出完整 OpenAPI 3.0 spec（从 M9 ENTITY_SCHEMAS）

    Returns:
        dict: 完整 OpenAPI 3.0 spec
            {
                'openapi': '3.0.0',
                'info': {...},
                'paths': {...},
                'components': {'schemas': {...}},
            }
    """
    from meta.graphql import ENTITY_SCHEMAS

    spec = {
        'openapi': '3.0.0',
        'info': {
            'title': 'v3 Engine API',
            'version': '3.0.0',
            'description': 'Auto-generated from M9 ENTITY_SCHEMAS via M13 Schema Governance',
        },
        'paths': {},
        'components': {'schemas': {}},
    }

    for entity_name, entity_def in ENTITY_SCHEMAS.items():
        spec['components']['schemas'][entity_name] = _to_openapi_schema(
            entity_name, entity_def
        )
        spec['paths'].update(_to_openapi_paths(entity_name, entity_def))

    return spec
