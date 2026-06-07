from flask import Blueprint, request, jsonify
from meta.services.cascade_service import HierarchyConfigLoader
from meta.core.models import registry

meta_util_bp = Blueprint('meta_util', __name__, url_prefix='/api/v1')


@meta_util_bp.route('/meta/objects', methods=['GET'])
def get_object_types():
    exclude_system = request.args.get('exclude_system', 'false').lower() == 'true'

    objects = []
    for obj_id in registry.list_types():
        obj = registry.get(obj_id)
        if not obj:
            continue

        semantics = getattr(obj, 'semantics', None) or {}
        category = getattr(semantics, 'category', '') if isinstance(semantics, object) else semantics.get('category', '')

        if exclude_system and category == 'system_entity':
            continue

        display_field = None
        df = obj.get_display_name_field()
        if df:
            ft = getattr(df, 'field_type', getattr(df, 'type', None))
            display_field = {
                'id': df.id,
                'name': df.name,
                'type': ft.value if hasattr(ft, 'value') else str(ft),
            }

        custom = getattr(obj, 'custom', None) or {}
        objects.append({
            'id': obj.id,
            'name': obj.name,
            'description': obj.description or '',
            'object_type': obj.object_type.value if hasattr(obj.object_type, 'value') else str(obj.object_type),
            'parent_object': getattr(obj, 'parent_object', None) or '',
            'table_name': getattr(obj, 'table_name', None) or '',
            'persistent': obj.persistent,
            'display_field': display_field,
            'icon': custom.get('icon', ''),
            'color_coding': custom.get('color_coding', ''),
            'aliases': getattr(obj, 'aliases', None) or [],
        })

    return jsonify({
        'success': True,
        'data': sorted(objects, key=lambda x: x['id'])
    })


@meta_util_bp.route('/meta/hierarchies', methods=['GET'])
def get_hierarchies():
    config = HierarchyConfigLoader.get_config()

    return jsonify({
        'success': True,
        'data': {
            'hierarchies': config.get('hierarchies', []),
            'dimensions': config.get('dimensions', []),
            'hierarchy_scopes': config.get('hierarchy_scopes', []),
            'api_mappings': config.get('api_mappings', {})
        }
    })


@meta_util_bp.route('/meta/hierarchies/<hierarchy_id>/levels', methods=['GET'])
def get_hierarchy_levels(hierarchy_id):
    levels = HierarchyConfigLoader.get_levels(hierarchy_id)

    if not levels:
        return jsonify({
            'success': False,
            'message': f'Hierarchy not found: {hierarchy_id}'
        }), 404

    return jsonify({
        'success': True,
        'data': levels
    })


@meta_util_bp.route('/meta/hierarchies/config', methods=['GET'])
def get_hierarchy_config():
    levels = HierarchyConfigLoader.get_levels('biz_hierarchy')

    hierarchy_levels = {}
    dimensions = []

    for level in levels:
        obj = level.get('object')
        if obj:
            dimensions.append(obj)
            hierarchy_levels[obj] = {
                'level': level.get('level', 0),
                'object': obj,
                'parent_object': level.get('parent_object', ''),
                'filter_param': level.get('foreign_key_field', 'id'),
                'display_name': level.get('display_name', obj),
                'table_name': level.get('table_name', ''),
                'ui': level.get('ui', {}),
                'delete_behavior': level.get('delete_behavior', {})
            }

    return jsonify({
        'success': True,
        'data': {
            'dimensions': dimensions,
            'hierarchy_levels': hierarchy_levels
        }
    })


@meta_util_bp.route('/meta/objects/<object_type>/field_controls', methods=['GET'])
def get_field_controls(object_type):
    meta = registry.get(object_type)
    if not meta:
        return jsonify({
            'success': False,
            'message': f'Object type not found: {object_type}'
        }), 404

    field_controls = {}
    for field in meta.fields:
        semantics = field.semantics or {}
        storage_value = getattr(field, 'storage', None)
        if hasattr(storage_value, 'value'):
            storage_value = storage_value.value
        field_controls[field.id] = {
            'business_key': getattr(semantics, 'business_key', False),
            'parent_key': getattr(semantics, 'parent_key', False),
            'immutable': getattr(semantics, 'immutable', False),
            'readonly_always': getattr(semantics, 'readonly_always', False),
            'mandatory': getattr(semantics, 'mandatory', False),
            'virtual': getattr(semantics, 'virtual', False),
            'context_field': getattr(semantics, 'context_field', False),
            'search_help_for': getattr(semantics, 'search_help_for', None),
            'storage': storage_value,
        }

    return jsonify({
        'success': True,
        'data': {
            'object_type': object_type,
            'field_controls': field_controls
        }
    })
