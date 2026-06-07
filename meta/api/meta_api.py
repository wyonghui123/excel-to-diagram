# -*- coding: utf-8 -*-
"""
元数据 API

提供元数据和视图配置的 REST API。
"""

import os
from flask import Blueprint, request, jsonify
from dataclasses import asdict
from typing import Any

from meta.core.models import registry
from meta.services.view_config_service import view_config_service
from meta.services.i18n_service import i18n_service
from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir

meta_bp = Blueprint('meta', __name__, url_prefix='/api/v1/meta')

DEV_MODE = os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes') or os.environ.get('DEV_MODE', '').lower() in ('1', 'true', 'yes')

_last_reload_time = 0
_RELOAD_INTERVAL = 2
_last_version = ''


def _ensure_fresh_meta():
    """开发模式下确保元数据是最新的"""
    global _last_reload_time, _last_version
    if not DEV_MODE:
        return _last_version
    import time
    now = time.time()
    if now - _last_reload_time > _RELOAD_INTERVAL:
        schema_dir = get_yaml_schema_dir()
        if schema_dir:
            registry._schema_dir = schema_dir
            registry.reload(schema_dir)
            _last_version = registry.get_version()
        _last_reload_time = now
    return _last_version


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


@meta_bp.route('/objects', methods=['GET'])
def list_objects():
    """获取所有对象类型列表"""
    version = _ensure_fresh_meta()
    objects = []

    for obj_id in registry.list_objects():
        obj = registry.get(obj_id)
        if obj and obj.persistent:
            objects.append({
                'id': obj.id,
                'name': obj.name,
                'description': obj.description,
                'object_type': obj.object_type.value,
                'parent_object': obj.parent_object,
                'hierarchy_level': obj.semantics.hierarchy_level,
            })

    return jsonify({
        'success': True,
        'data': objects,
        'total': len(objects),
        'meta_version': version,
    })


@meta_bp.route('/objects/<object_type>', methods=['GET'])
def get_object(object_type: str):
    """获取对象类型详情"""
    _ensure_fresh_meta()
    obj = registry.get(object_type)

    if not obj:
        return jsonify({
            'success': False,
            'error': f'Object type not found: {object_type}',
        }), 404

    fields = []
    for field in obj.fields:
        fields.append({
            'id': field.id,
            'name': field.name,
            'type': field.field_type.value,
            'required': field.required,
            'unique': field.unique,
            'default': field.default,
            'description': field.description,
            'storage': field.storage.value if hasattr(field.storage, 'value') else str(field.storage),
            'computed': field.computed,
            'ui': _dataclass_to_dict(field.ui),
            'permission': _dataclass_to_dict(field.permission),
            'semantics': _dataclass_to_dict(field.semantics),
        })

    relations = []
    for rel in obj.relations:
        relations.append({
            'id': rel.id,
            'name': rel.name,
            'type': rel.relation_type.value,
            'target_object': rel.target_object,
            'cardinality': rel.cardinality,
        })

    actions = []
    for action in obj.actions:
        actions.append({
            'id': action.id,
            'name': action.name,
            'type': action.action_type.value,
            'method': action.method,
            'path': action.path,
            'description': action.description,
            'parameters': _dataclass_to_dict(action.parameters),
        })

    version = _ensure_fresh_meta()
    
    # 获取显示名称字段和业务标识字段
    display_name_field = obj.get_display_name_field()
    business_key_field = obj.get_business_key_field()
    
    return jsonify({
        'success': True,
        'data': {
            'id': obj.id,
            'name': obj.name,
            'description': obj.description,
            'object_type': obj.object_type.value,
            'table_name': obj.table_name,
            'parent_object': obj.parent_object,
            'fields': fields,
            'relations': relations,
            'actions': actions,
            'analytical_model': obj.analytical_model,
            'available_views': view_config_service.get_available_views(object_type),
            'display_name_field': display_name_field.id if display_name_field else None,
            'business_key_field': business_key_field.id if business_key_field else None,
        },
        'meta_version': version,
    })


@meta_bp.route('/<object_type>/view-config', methods=['GET'])
def get_view_config(object_type: str):
    """获取对象类型的默认视图配置"""
    _ensure_fresh_meta()
    view_name = request.args.get('view_name')

    config = view_config_service.get_or_build_view_config(object_type, view_name)

    if not config:
        return jsonify({
            'success': False,
            'error': f'View config not found for: {object_type}',
        }), 404

    # 获取显示名称字段和业务标识字段
    obj = registry.get(object_type)
    display_name_field = obj.get_display_name_field() if obj else None
    business_key_field = obj.get_business_key_field() if obj else None

    view_config_service._enrich_columns_with_field_meta(object_type, config)

    data = _dataclass_to_dict(config)
    data['display_name_field'] = display_name_field.id if display_name_field else None
    data['business_key_field'] = business_key_field.id if business_key_field else None

    return jsonify({
        'success': True,
        'data': data,
        'object_type': object_type,
        'view_name': view_name or 'default',
    })


@meta_bp.route('/<object_type>/view-config/<view_name>', methods=['GET'])
def get_named_view_config(object_type: str, view_name: str):
    """获取对象类型的指定视图配置"""
    config = view_config_service.get_or_build_view_config(object_type, view_name)

    if not config:
        return jsonify({
            'success': False,
            'error': f'View config not found: {object_type}/{view_name}',
        }), 404

    # 获取显示名称字段和业务标识字段
    obj = registry.get(object_type)
    display_name_field = obj.get_display_name_field() if obj else None
    business_key_field = obj.get_business_key_field() if obj else None

    view_config_service._enrich_columns_with_field_meta(object_type, config)

    data = _dataclass_to_dict(config)
    data['display_name_field'] = display_name_field.id if display_name_field else None
    data['business_key_field'] = business_key_field.id if business_key_field else None

    return jsonify({
        'success': True,
        'data': data,
        'object_type': object_type,
        'view_name': view_name,
    })


@meta_bp.route('/<object_type>/list-view', methods=['GET'])
def get_list_view_config(object_type: str):
    """获取列表视图配置"""
    _ensure_fresh_meta()
    view_name = request.args.get('view_name')

    config = view_config_service.get_list_view_config(object_type, view_name)

    if not config:
        config = view_config_service.build_list_view_from_fields(object_type)

    view_config_service._enrich_columns_with_field_meta(object_type, config)

    return jsonify({
        'success': True,
        'data': _dataclass_to_dict(config),
        'object_type': object_type,
        'view_name': view_name or 'default',
    })


@meta_bp.route('/<object_type>/detail-view', methods=['GET'])
def get_detail_view_config(object_type: str):
    """获取详情视图配置"""
    _ensure_fresh_meta()
    view_name = request.args.get('view_name')

    config = view_config_service.get_detail_view_config(object_type, view_name)

    if not config:
        config = view_config_service.build_detail_view_from_fields(object_type)

    return jsonify({
        'success': True,
        'data': _dataclass_to_dict(config),
        'object_type': object_type,
        'view_name': view_name or 'default',
    })


@meta_bp.route('/<object_type>/form-view', methods=['GET'])
def get_form_view_config(object_type: str):
    """获取表单视图配置"""
    _ensure_fresh_meta()
    view_name = request.args.get('view_name')

    config = view_config_service.get_form_view_config(object_type, view_name)

    if not config:
        config = view_config_service.build_form_view_from_fields(object_type)

    return jsonify({
        'success': True,
        'data': _dataclass_to_dict(config),
        'object_type': object_type,
        'view_name': view_name or 'default',
    })


@meta_bp.route('/reload', methods=['POST'])
def reload_meta():
    """重新加载元数据"""
    try:
        schema_dir = get_yaml_schema_dir()
        registry._schema_dir = schema_dir
        count = registry.reload(schema_dir)
        view_config_service.invalidate_cache()

        return jsonify({
            'success': True,
            'message': f'Reloaded {count} meta objects',
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500


@meta_bp.route('/i18n/<locale>', methods=['GET'])
def get_i18n(locale: str):
    """获取多语言配置"""
    texts = i18n_service.get_all_texts(locale)

    return jsonify({
        'success': True,
        'data': texts,
        'locale': locale,
    })


@meta_bp.route('/i18n/text/<path:key>', methods=['GET'])
def get_i18n_text(key: str):
    """获取单个多语言文本"""
    locale = request.args.get('locale', i18n_service.get_current_locale())
    default = request.args.get('default', '')

    text = i18n_service.get_text_with_fallback(key, default, locale)

    return jsonify({
        'success': True,
        'data': {
            'key': key,
            'text': text,
            'locale': locale,
        },
    })


@meta_bp.route('/i18n/locales', methods=['GET'])
def list_locales():
    """获取可用语言列表"""
    locales = i18n_service.get_available_locales()

    return jsonify({
        'success': True,
        'data': locales,
        'current': i18n_service.get_current_locale(),
    })


@meta_bp.route('/enums/batch', methods=['GET'])
def get_enums_batch():
    """枚举批量预加载 API - 一次请求获取多种枚举类型的值

    Query params:
        - types: 逗号分隔的枚举类型ID列表（必填）

    示例: /api/v1/meta/enums/batch?types=relation_type,annotation_category
    """
    types_param = request.args.get('types', '')
    if not types_param:
        return jsonify({'success': False, 'message': 'types parameter required'}), 400

    enum_types = [t.strip() for t in types_param.split(',') if t.strip()]

    from meta.api.enum_api import _get_data_source as _get_enum_ds, _row_to_dict

    ds = _get_enum_ds()
    result = {}

    for enum_type in enum_types:
        try:
            # 检查枚举类型是否存在
            cursor = ds.execute("SELECT id FROM enum_types WHERE id = ?", [enum_type])
            if not cursor.fetchone():
                result[enum_type] = {
                    'success': False,
                    'message': f'枚举类型不存在: {enum_type}'
                }
                continue

            # 查询活跃的枚举值
            sql = (
                "SELECT code, name, name_en, sort_order, is_active, parent_code "
                "FROM enum_values WHERE enum_type_id = ? AND is_active = 1 "
                "ORDER BY sort_order, code"
            )
            cursor = ds.execute(sql, [enum_type])
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            values = [dict(zip(columns, row)) for row in rows]

            result[enum_type] = {
                'success': True,
                'data': values
            }
        except Exception as e:
            result[enum_type] = {
                'success': False,
                'message': str(e)
            }

    return jsonify({
        'success': True,
        'data': result
    })


@meta_bp.route('/<object_type>/filter-config', methods=['GET'])
def get_filter_config(object_type: str):
    """获取筛选器配置"""
    _ensure_fresh_meta()
    meta_object = registry.get(object_type)

    if not meta_object:
        return jsonify({
            'success': False,
            'error': f'Object type not found: {object_type}',
        }), 404

    view_config = meta_object.ui_view_config
    if not view_config or not hasattr(view_config, 'filter') or not view_config.filter:
        return jsonify({
            'success': True,
            'data': {'filters': []},
            'object_type': object_type,
        })

    filter_config = view_config.filter
    filters_data = []
    if hasattr(filter_config, 'filters'):
        for f in filter_config.filters:
            filter_item = {
                'key': f.key if hasattr(f, 'key') else f.get('key', ''),
                'title': f.title if hasattr(f, 'title') else f.get('title', ''),
                'type': f.type if hasattr(f, 'type') else f.get('type', ''),
                'position': f.position if hasattr(f, 'position') else f.get('position', 0),
            }
            if hasattr(f, 'default') and f.default is not None:
                filter_item['default'] = f.default
            elif isinstance(f, dict) and 'default' in f:
                filter_item['default'] = f['default']
            if hasattr(f, 'source') and f.source:
                filter_item['source'] = f.source
            if hasattr(f, 'display_field') and f.display_field:
                filter_item['display_field'] = f.display_field
            if hasattr(f, 'options') and f.options:
                filter_item['options'] = f.options if isinstance(f.options, list) else []
            if hasattr(f, 'required') and f.required:
                filter_item['required'] = f.required
            if hasattr(f, 'tree_structure') and f.tree_structure:
                filter_item['tree_structure'] = f.tree_structure
            if hasattr(f, 'tree_levels') and f.tree_levels:
                filter_item['tree_levels'] = f.tree_levels
            if hasattr(f, 'leaf_value_field') and f.leaf_value_field:
                filter_item['leaf_value_field'] = f.leaf_value_field
            if hasattr(f, 'show_count'):
                filter_item['show_count'] = f.show_count
            if hasattr(f, 'filter_by') and f.filter_by:
                filter_item['filter_by'] = f.filter_by
            filters_data.append(filter_item)

    filters_data.sort(key=lambda x: x.get('position', 0))

    layout = 'vertical'
    if hasattr(filter_config, 'layout') and filter_config.layout:
        layout = filter_config.layout

    return jsonify({
        'success': True,
        'data': {
            'filters': filters_data,
            'layout': layout,
        },
        'object_type': object_type,
    })


@meta_bp.route('/<object_type>/filter-tree/<filter_key>', methods=['GET'])
def get_filter_tree_data(object_type: str, filter_key: str):
    """获取树形筛选器数据"""
    _ensure_fresh_meta()
    meta_object = registry.get(object_type)

    if not meta_object:
        return jsonify({
            'success': False,
            'error': f'Object type not found: {object_type}',
        }), 404

    view_config = meta_object.ui_view_config
    if not view_config or not hasattr(view_config, 'filter'):
        return jsonify({
            'success': True,
            'data': [],
        })

    filter_config = view_config.filter
    target_filter = None
    if hasattr(filter_config, 'filters'):
        for f in filter_config.filters:
            if (f.key if hasattr(f, 'key') else f.get('key', '')) == filter_key:
                target_filter = f
                break

    if not target_filter:
        return jsonify({
            'success': True,
            'data': [],
        })

    tree_structure = target_filter.tree_structure if hasattr(target_filter, 'tree_structure') else ''
    tree_levels = target_filter.tree_levels if hasattr(target_filter, 'tree_levels') else []
    version_id = request.args.get('version_id', type=int)
    bo_ids_param = request.args.get('business_object_ids', '')
    business_object_ids = [int(x) for x in bo_ids_param.split(',') if x.strip().isdigit()] if bo_ids_param else []

    if tree_structure == 'hierarchy':
        tree_data = _build_hierarchy_tree(tree_levels, version_id)
    elif tree_structure == 'category':
        tree_data = _build_category_tree(object_type, version_id, business_object_ids)
    else:
        tree_data = []

    return jsonify({
        'success': True,
        'data': tree_data,
        'filter_key': filter_key,
    })


def _build_hierarchy_tree(levels: list, version_id: int = None) -> list:
    """构建层级树（领域->子领域->服务模块->业务对象）"""
    from meta.core.datasource import get_data_source
    import os

    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'architecture.db')
    ds = get_data_source("sqlite", database=db_path)

    if not levels or 'domain' not in levels:
        return []

    try:
        version_filter = "WHERE version_id = ?" if version_id else ""
        version_params = [version_id] if version_id else []

        relation_counts = _compute_tree_relation_counts(ds, version_id)

        cursor = ds.execute(f"SELECT id, name, code FROM domains {version_filter} ORDER BY name", version_params)
        domains = cursor.fetchall()

        tree = []
        for domain in domains:
            domain_node = {
                'id': f'domain_{domain[0]}',
                'key': domain[0],
                'name': domain[1],
                'code': domain[2],
                'level': 'domain',
                'relation_count': relation_counts.get(('domain', domain[0]), 0),
                'children': []
            }

            if 'sub_domain' in levels:
                if version_id:
                    cursor = ds.execute(
                        "SELECT id, name, code FROM sub_domains WHERE domain_id = ? AND version_id = ? ORDER BY name",
                        (domain[0], version_id)
                    )
                else:
                    cursor = ds.execute(
                        "SELECT id, name, code FROM sub_domains WHERE domain_id = ? ORDER BY name",
                        (domain[0],)
                    )
                sub_domains = cursor.fetchall()

                for sub_domain in sub_domains:
                    sub_domain_node = {
                        'id': f'sub_domain_{sub_domain[0]}',
                        'key': sub_domain[0],
                        'name': sub_domain[1],
                        'code': sub_domain[2],
                        'level': 'sub_domain',
                        'relation_count': relation_counts.get(('sub_domain', sub_domain[0]), 0),
                        'children': []
                    }

                    if 'service_module' in levels:
                        if version_id:
                            cursor = ds.execute(
                                "SELECT id, name, code FROM service_modules WHERE sub_domain_id = ? AND version_id = ? ORDER BY name",
                                (sub_domain[0], version_id)
                            )
                        else:
                            cursor = ds.execute(
                                "SELECT id, name, code FROM service_modules WHERE sub_domain_id = ? ORDER BY name",
                                (sub_domain[0],)
                            )
                        service_modules = cursor.fetchall()

                        for sm in service_modules:
                            sm_node = {
                                'id': f'service_module_{sm[0]}',
                                'key': sm[0],
                                'name': sm[1],
                                'code': sm[2],
                                'level': 'service_module',
                                'relation_count': relation_counts.get(('service_module', sm[0]), 0),
                                'children': []
                            }

                            if 'business_object' in levels:
                                if version_id:
                                    cursor = ds.execute(
                                        "SELECT id, name, code FROM business_objects WHERE service_module_id = ? AND version_id = ? ORDER BY name",
                                        (sm[0], version_id)
                                    )
                                else:
                                    cursor = ds.execute(
                                        "SELECT id, name, code FROM business_objects WHERE service_module_id = ? ORDER BY name",
                                        (sm[0],)
                                    )
                                business_objects = cursor.fetchall()

                                for bo in business_objects:
                                    bo_node = {
                                        'id': f'business_object_{bo[0]}',
                                        'key': bo[0],
                                        'name': bo[1],
                                        'code': bo[2],
                                        'level': 'business_object',
                                        'relation_count': relation_counts.get(('business_object', bo[0]), 0),
                                        'isLeaf': True,
                                    }
                                    sm_node['children'].append(bo_node)

                            if sm_node['children'] or 'business_object' not in levels:
                                sub_domain_node['children'].append(sm_node)

                    if sub_domain_node['children'] or 'service_module' not in levels:
                        domain_node['children'].append(sub_domain_node)

            if domain_node['children'] or 'sub_domain' not in levels:
                tree.append(domain_node)

        return tree
    except Exception as e:
        print(f"Error building hierarchy tree: {e}")
        return []


def _compute_tree_relation_counts(ds, version_id: int = None) -> dict:
    """批量计算树节点的关系数量"""
    counts = {}

    version_filter = "AND bo.version_id = ?" if version_id else ""
    version_params = [version_id] if version_id else []

    try:
        bo_sql = f"""
            SELECT bo.id, COUNT(DISTINCT r.id) as cnt
            FROM business_objects bo
            LEFT JOIN relationships r ON (r.source_bo_id = bo.id OR r.target_bo_id = bo.id)
            WHERE 1=1 {version_filter}
            GROUP BY bo.id
        """
        cursor = ds.execute(bo_sql, version_params)
        for row in cursor.fetchall():
            counts[('business_object', row[0])] = row[1]

        sm_sql = f"""
            SELECT sm.id, COUNT(DISTINCT r.id) as cnt
            FROM service_modules sm
            JOIN business_objects bo ON bo.service_module_id = sm.id
            LEFT JOIN relationships r ON (r.source_bo_id = bo.id OR r.target_bo_id = bo.id)
            WHERE 1=1 {version_filter}
            GROUP BY sm.id
        """
        cursor = ds.execute(sm_sql, version_params)
        for row in cursor.fetchall():
            counts[('service_module', row[0])] = row[1]

        sd_sql = f"""
            SELECT sd.id, COUNT(DISTINCT r.id) as cnt
            FROM sub_domains sd
            JOIN service_modules sm ON sm.sub_domain_id = sd.id
            JOIN business_objects bo ON bo.service_module_id = sm.id
            LEFT JOIN relationships r ON (r.source_bo_id = bo.id OR r.target_bo_id = bo.id)
            WHERE 1=1 {version_filter}
            GROUP BY sd.id
        """
        cursor = ds.execute(sd_sql, version_params)
        for row in cursor.fetchall():
            counts[('sub_domain', row[0])] = row[1]

        domain_sql = f"""
            SELECT d.id, COUNT(DISTINCT r.id) as cnt
            FROM domains d
            JOIN sub_domains sd ON sd.domain_id = d.id
            JOIN service_modules sm ON sm.sub_domain_id = sd.id
            JOIN business_objects bo ON bo.service_module_id = sm.id
            LEFT JOIN relationships r ON (r.source_bo_id = bo.id OR r.target_bo_id = bo.id)
            WHERE 1=1 {version_filter}
            GROUP BY d.id
        """
        cursor = ds.execute(domain_sql, version_params)
        for row in cursor.fetchall():
            counts[('domain', row[0])] = row[1]
    except Exception as e:
        print(f"Error computing relation counts: {e}")

    return counts


def _build_category_tree(object_type: str, version_id: int = None, business_object_ids: list = None) -> list:
    """构建分类树（中心范围内/外 -> 分类类型 -> 领域对/服务模块对）

    基于元数据模型中的衍生规则：
    - category_type: 基于源和目标业务对象的层级关系计算
    - is_in_scope: 基于用户选择的业务对象范围判断

    Args:
        version_id: 版本ID
        business_object_ids: 用户选择的业务对象ID列表
                             如果为空/None，表示用户选择了所有业务对象（只显示中心范围内）
                             如果有值，表示用户选择了部分业务对象（显示中心范围内和中心范围外）
    """
    from meta.core.datasource import get_data_source
    import os

    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'architecture.db')
    ds = get_data_source("sqlite", database=db_path)

    category_config = [
        {'key': 'cross_domain', 'name': '跨领域'},
        {'key': 'same_domain_cross_subdomain', 'name': '同领域跨子领域'},
        {'key': 'same_subdomain_cross_module', 'name': '同子领域跨服务模块'},
        {'key': 'same_module', 'name': '同服务模块'},
    ]

    version_filter = "AND r.version_id = ?" if version_id else ""
    version_params = [version_id] if version_id else []

    if business_object_ids:
        internal_category_data, internal_category_counts = _get_internal_category_data(
            ds, category_config, version_filter, version_params, business_object_ids
        )
        external_category_data, external_category_counts, external_total = _get_external_category_data(
            ds, category_config, version_filter, version_params, business_object_ids
        )
        internal_total = sum(internal_category_counts.values())
    else:
        internal_category_data, internal_category_counts = _get_all_category_data(
            ds, category_config, version_filter, version_params
        )
        internal_total = sum(internal_category_counts.values())
        external_category_data = {}
        external_category_counts = {}
        external_total = 0

    def build_category_children(scope_prefix, category_data, category_counts):
        children = []
        for cat in category_config:
            cat_id = f'{scope_prefix}-{cat["key"]}'
            pairs = category_data.get(cat['key'], [])
            cat_total = category_counts.get(cat['key'], 0)

            cat_node = {
                'id': cat_id,
                'key': cat['key'],
                'name': cat['name'],
                'level': 'category_type',
                'relation_count': cat_total,
                'children': []
            }

            for pair in pairs:
                pair_node = {
                    'id': f'{cat_id}-{pair["id"]}',
                    'key': pair['id'],
                    'name': pair['display_name'],
                    'level': 'pair',
                    'relation_count': pair['relation_count'],
                    'isLeaf': True,
                }
                cat_node['children'].append(pair_node)

            if not cat_node['children']:
                cat_node['isLeaf'] = True

            children.append(cat_node)
        return children

    tree = [
        {
            'id': 'internal',
            'key': 'internal',
            'name': '中心范围内',
            'level': 'scope_type',
            'relation_count': internal_total,
            'children': build_category_children('internal', internal_category_data, internal_category_counts)
        }
    ]

    if external_total > 0:
        tree.append({
            'id': 'external',
            'key': 'external',
            'name': '中心范围外',
            'level': 'scope_type',
            'relation_count': external_total,
            'children': build_category_children('external', external_category_data, external_category_counts)
        })

    return tree


def _get_all_category_data(ds, category_config, version_filter, version_params):
    """获取所有关系的分类数据（用户选择所有业务对象时）"""
    category_data = {}
    category_counts = {}
    
    for cat in category_config:
        pairs, cat_count = _get_category_pairs(ds, cat['key'], version_filter, version_params, "", [])
        category_data[cat['key']] = pairs
        category_counts[cat['key']] = cat_count
    
    return category_data, category_counts


def _get_internal_category_data(ds, category_config, version_filter, version_params, business_object_ids):
    """获取中心范围内的分类数据（源和目标都在选择范围内）"""
    category_data = {}
    category_counts = {}
    
    placeholders = ','.join(['?' for _ in business_object_ids])
    internal_filter = f"AND r.source_bo_id IN ({placeholders}) AND r.target_bo_id IN ({placeholders})"
    internal_params = business_object_ids + business_object_ids
    
    for cat in category_config:
        pairs, cat_count = _get_category_pairs(ds, cat['key'], version_filter, version_params, internal_filter, internal_params)
        category_data[cat['key']] = pairs
        category_counts[cat['key']] = cat_count
    
    return category_data, category_counts


def _get_external_category_data(ds, category_config, version_filter, version_params, business_object_ids):
    """获取中心范围外的分类数据（源或目标有任意一个不在选择范围内）"""
    category_data = {}
    category_counts = {}
    
    placeholders = ','.join(['?' for _ in business_object_ids])
    external_filter = f"AND ((r.source_bo_id IN ({placeholders}) AND r.target_bo_id NOT IN ({placeholders})) OR (r.source_bo_id NOT IN ({placeholders}) AND r.target_bo_id IN ({placeholders})))"
    external_params = business_object_ids + business_object_ids + business_object_ids + business_object_ids
    
    total_count = 0
    for cat in category_config:
        pairs, cat_count = _get_category_pairs(ds, cat['key'], version_filter, version_params, external_filter, external_params)
        category_data[cat['key']] = pairs
        category_counts[cat['key']] = cat_count
        total_count += cat_count
    
    return category_data, category_counts, total_count


def _get_category_pairs(ds, category_key, version_filter, version_params, scope_filter, scope_params):
    """获取指定分类类型下的领域对/服务模块对列表及总数量"""
    pair_sqls = _get_category_pair_sqls()
    
    sql = pair_sqls.get(category_key, "")
    if not sql:
        return [], 0
    
    extra_conditions = ""
    if version_filter:
        extra_conditions += " " + version_filter
    if scope_filter:
        extra_conditions += " " + scope_filter
    
    full_sql = f"{sql}{extra_conditions} GROUP BY pair_id, source_name, target_name ORDER BY source_name, target_name"
    
    try:
        params = version_params + scope_params
        cursor = ds.execute(full_sql, params)
        rows = cursor.fetchall()
        
        pairs = []
        total_count = 0
        for row in rows:
            pairs.append({
                'id': row[0],
                'source_name': row[1],
                'target_name': row[2],
                'relation_count': row[3],
                'display_name': f"{row[1]}-{row[2]}"
            })
            total_count += row[3]
        
        return pairs, total_count
    except Exception as e:
        print(f"Error getting category pairs for {category_key}: {e}")
        return [], 0


def _get_category_pair_sqls():
    """返回各分类类型的SQL查询模板"""
    return {
        'cross_domain': """
            SELECT d1.id || '-' || d2.id as pair_id, d1.name as source_name, d2.name as target_name, COUNT(DISTINCT r.id) as relation_count
            FROM relationships r
            JOIN business_objects bo1 ON r.source_bo_id = bo1.id
            JOIN business_objects bo2 ON r.target_bo_id = bo2.id
            JOIN service_modules sm1 ON bo1.service_module_id = sm1.id
            JOIN service_modules sm2 ON bo2.service_module_id = sm2.id
            JOIN sub_domains sd1 ON sm1.sub_domain_id = sd1.id
            JOIN sub_domains sd2 ON sm2.sub_domain_id = sd2.id
            JOIN domains d1 ON sd1.domain_id = d1.id
            JOIN domains d2 ON sd2.domain_id = d2.id
            WHERE d1.id != d2.id
        """,
        'same_domain_cross_subdomain': """
            SELECT sd1.id || '-' || sd2.id as pair_id, sd1.name as source_name, sd2.name as target_name, COUNT(DISTINCT r.id) as relation_count
            FROM relationships r
            JOIN business_objects bo1 ON r.source_bo_id = bo1.id
            JOIN business_objects bo2 ON r.target_bo_id = bo2.id
            JOIN service_modules sm1 ON bo1.service_module_id = sm1.id
            JOIN service_modules sm2 ON bo2.service_module_id = sm2.id
            JOIN sub_domains sd1 ON sm1.sub_domain_id = sd1.id
            JOIN sub_domains sd2 ON sm2.sub_domain_id = sd2.id
            JOIN domains d1 ON sd1.domain_id = d1.id
            JOIN domains d2 ON sd2.domain_id = d2.id
            WHERE d1.id = d2.id AND sd1.id != sd2.id
        """,
        'same_subdomain_cross_module': """
            SELECT sm1.id || '-' || sm2.id as pair_id, sm1.name as source_name, sm2.name as target_name, COUNT(DISTINCT r.id) as relation_count
            FROM relationships r
            JOIN business_objects bo1 ON r.source_bo_id = bo1.id
            JOIN business_objects bo2 ON r.target_bo_id = bo2.id
            JOIN service_modules sm1 ON bo1.service_module_id = sm1.id
            JOIN service_modules sm2 ON bo2.service_module_id = sm2.id
            JOIN sub_domains sd1 ON sm1.sub_domain_id = sd1.id
            JOIN sub_domains sd2 ON sm2.sub_domain_id = sd2.id
            WHERE sd1.id = sd2.id AND sm1.id != sm2.id
        """,
        'same_module': """
            SELECT sm1.id || '-' || sm2.id as pair_id, sm1.name as source_name, sm2.name as target_name, COUNT(DISTINCT r.id) as relation_count
            FROM relationships r
            JOIN business_objects bo1 ON r.source_bo_id = bo1.id
            JOIN business_objects bo2 ON r.target_bo_id = bo2.id
            JOIN service_modules sm1 ON bo1.service_module_id = sm1.id
            JOIN service_modules sm2 ON bo2.service_module_id = sm2.id
            WHERE sm1.id = sm2.id
        """
    }

