# -*- coding: utf-8 -*-
"""
Agent API（预留接口）

提供 AI Agent 集成的 REST API。
支持：
- 获取所有 Tool Schema
- 获取对象上下文
"""

from flask import Blueprint, jsonify
from typing import Any, Dict, List
from dataclasses import asdict

from meta.core.models import registry, MetaAction
from meta.services.view_config_service import view_config_service

agent_bp = Blueprint('agent', __name__, url_prefix='/api/v1/agent')


def _dataclass_to_dict(obj: Any) -> Any:
    """递归转换 dataclass 为 dict"""
    if hasattr(obj, '__dataclass_fields__'):
        return {k: _dataclass_to_dict(v) for k, v in asdict(obj).items()}
    elif isinstance(obj, list):
        return [_dataclass_to_dict(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: _dataclass_to_dict(v) for k, v in obj.items()}
    else:
        return obj


@agent_bp.route('/tools', methods=['GET'])
def get_tools():
    """
    获取所有 Tool Schema
    
    返回所有对象类型的 CRUD 操作和自定义操作作为 Tool Schema。
    格式兼容 OpenAI Function Calling。
    """
    tools = []
    
    for obj_id in registry.list_objects():
        obj = registry.get(obj_id)
        if not obj or not obj.persistent:
            continue
        
        for action in obj.actions:
            tool_schema = action.to_tool_schema()
            tools.append(tool_schema)
        
        tools.extend(_generate_crud_tools(obj_id, obj.name))
    
    return jsonify({
        'success': True,
        'data': tools,
        'total': len(tools),
    })


def _generate_crud_tools(object_type: str, object_name: str) -> List[Dict[str, Any]]:
    """生成 CRUD 工具 Schema"""
    tools = []
    
    tools.append({
        'name': f'list_{object_type}',
        'description': f'获取{object_name}列表',
        'parameters': {
            'type': 'object',
            'properties': {
                'page': {
                    'type': 'integer',
                    'description': '页码，从1开始',
                },
                'page_size': {
                    'type': 'integer',
                    'description': '每页数量',
                },
                'keyword': {
                    'type': 'string',
                    'description': '搜索关键词',
                },
            },
        },
    })
    
    tools.append({
        'name': f'get_{object_type}',
        'description': f'获取单个{object_name}详情',
        'parameters': {
            'type': 'object',
            'properties': {
                'id': {
                    'type': 'integer',
                    'description': f'{object_name}ID',
                },
            },
            'required': ['id'],
        },
    })
    
    tools.append({
        'name': f'create_{object_type}',
        'description': f'创建新的{object_name}',
        'parameters': {
            'type': 'object',
            'properties': {
                'data': {
                    'type': 'object',
                    'description': f'{object_name}数据',
                },
            },
            'required': ['data'],
        },
    })
    
    tools.append({
        'name': f'update_{object_type}',
        'description': f'更新{object_name}',
        'parameters': {
            'type': 'object',
            'properties': {
                'id': {
                    'type': 'integer',
                    'description': f'{object_name}ID',
                },
                'data': {
                    'type': 'object',
                    'description': f'{object_name}更新数据',
                },
            },
            'required': ['id', 'data'],
        },
    })
    
    tools.append({
        'name': f'delete_{object_type}',
        'description': f'删除{object_name}',
        'parameters': {
            'type': 'object',
            'properties': {
                'id': {
                    'type': 'integer',
                    'description': f'{object_name}ID',
                },
            },
            'required': ['id'],
        },
    })
    
    return tools


@agent_bp.route('/context/<object_type>', methods=['GET'])
def get_object_context(object_type: str):
    """
    获取对象上下文
    
    返回对象的完整语义信息，包括：
    - 字段定义和语义
    - 关联关系
    - 可用操作
    - 视图配置
    """
    obj = registry.get(object_type)
    
    if not obj:
        return jsonify({
            'success': False,
            'error': f'Object type not found: {object_type}',
        }), 404
    
    fields_context = []
    for field in obj.fields:
        field_context = {
            'id': field.id,
            'name': field.name,
            'type': field.field_type.value,
            'description': field.description,
            'required': field.required,
            'unique': field.unique,
            'semantics': {
                'meaning': field.semantics.meaning,
                'business_key': field.semantics.business_key,
                'display_name': field.semantics.display_name,
                'category': field.semantics.category,
                'hierarchy_level': field.semantics.hierarchy_level,
            },
            'ui': {
                'widget': field.ui.widget,
                'visible': field.ui.visible,
                'editable': field.ui.editable,
            },
        }
        fields_context.append(field_context)
    
    relations_context = []
    for rel in obj.relations:
        rel_context = {
            'id': rel.id,
            'name': rel.name,
            'type': rel.relation_type.value,
            'target_object': rel.target_object,
            'cardinality': rel.cardinality,
            'description': rel.description,
        }
        relations_context.append(rel_context)
    
    actions_context = []
    for action in obj.actions:
        action_context = {
            'id': action.id,
            'name': action.name,
            'type': action.action_type.value,
            'description': action.description,
            'tool_schema': action.to_tool_schema(),
        }
        actions_context.append(action_context)
    
    view_config = view_config_service.get_or_build_view_config(object_type)
    
    return jsonify({
        'success': True,
        'data': {
            'object_type': object_type,
            'name': obj.name,
            'description': obj.description,
            'parent_object': obj.parent_object,
            'hierarchy_level': obj.semantics.hierarchy_level,
            'fields': fields_context,
            'relations': relations_context,
            'actions': actions_context,
            'view_config': _dataclass_to_dict(view_config),
        },
    })


@agent_bp.route('/schema', methods=['GET'])
def get_full_schema():
    """
    获取完整元数据 Schema
    
    返回所有对象类型的完整定义，供 Agent 理解整个数据模型。
    """
    schema = {
        'objects': {},
        'relations': [],
    }
    
    for obj_id in registry.list_objects():
        try:
            obj = registry.get(obj_id)
            if not obj:
                continue
            
            obj_schema = {
                'name': obj.name,
                'description': obj.description,
                'parent_object': obj.parent_object,
                'fields': [],
                'actions': [],
            }
            
            for f in (obj.fields or []):
                try:
                    field_type = f.field_type.value if f.field_type else 'unknown'
                except Exception:
                    field_type = 'unknown'
                obj_schema['fields'].append({
                    'id': f.id,
                    'name': f.name,
                    'type': field_type,
                    'description': f.description,
                    'required': f.required,
                })
            
            for a in (obj.actions or []):
                try:
                    action_type = a.action_type.value if a.action_type else 'unknown'
                except Exception:
                    action_type = 'unknown'
                obj_schema['actions'].append({
                    'id': a.id,
                    'name': a.name,
                    'type': action_type,
                    'description': a.description,
                })
            
            schema['objects'][obj_id] = obj_schema
            
            for rel in (obj.relations or []):
                try:
                    rel_type = rel.relation_type.value if rel.relation_type else 'unknown'
                except Exception:
                    rel_type = 'unknown'
                schema['relations'].append({
                    'source': obj_id,
                    'target': rel.target_object,
                    'type': rel_type,
                    'name': rel.name,
                })
        except Exception:
            continue
    
    return jsonify({
        'success': True,
        'data': schema,
    })
