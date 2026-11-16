# -*- coding: utf-8 -*-
"""
元数据 API

提供元数据和视图配置的 REST API。
"""

import os
import re
import logging
from flask import Blueprint, request, jsonify
from dataclasses import asdict
from typing import Any

from meta.api._response_contract import ok, ok_message, error_response
from meta.core.models import registry
from meta.services.view_config_service import view_config_service
from meta.services.i18n_service import i18n_service
from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir
from meta.core.state_side_effects import validate_schema_dir_side_effects
from meta.core.ui_config.value_help_formatter import value_help_to_dict

logger = logging.getLogger(__name__)

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
            # reload 只用平台目录重建 _objects，必须重放应用 schema，
            # 否则 /api/v2/bo/<app_bo> 会报 Unknown object type（multi-app 模式）
            from meta.core.app_registry import reapply_app_schemas
            reapply_app_schemas()
            _last_version = registry.get_version()
        _last_reload_time = now
    return _last_version




# [FIX BUG-V048 2026-07-06 dev agent] 加 /<object_type>/ui-config endpoint
# 背景: V046 fix 在 schema_loader.py 暴露了 audit_history_excluded_child_object_types,
#       但后端没有任何 API endpoint 调用 SchemaLoader.load_schema()。
#       前端 HistorySection 通过 metaService.getUIConfig() 调 /meta/<type>/ui-config,
#       但 meta_api.py 只有 /view-config/... 路由, /ui-config 返回 404。
# 修法: 调 SchemaLoader.load_schema() 返回 dict (含 audit_history_excluded_child_object_types)
#       并作为 /<object_type>/ui-config endpoint 的响应。
from meta.schemas.schema_loader import SchemaLoader
import os as _os
from meta.core.db_path import get_meta_db_path
_ui_config_schema_dir = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "schemas")
_ui_config_loader = SchemaLoader(_ui_config_schema_dir)


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


def _strip_party_detail_section(config: dict) -> None:
    """party 模块关闭时移除 org 详情的「往来关系」分区（就地修改）。

    只在 BIP 应用架构管理部署（DISABLED_PLATFORM_MODULES=party）时生效：
    该部署的 org 是应用架构节点、不具备 BU/LE 业务职能 ⇒ 无 party 内部表示，
    分区恒空。取数端点本身空集安全，这里只收敛无效入口。
    """
    detail = (config.get('ui_view_config') or {}).get('detail')
    if not isinstance(detail, dict):
        return
    tabs = detail.get('tabs')
    if isinstance(tabs, list):
        detail['tabs'] = [
            tab for tab in tabs
            if not (isinstance(tab, dict) and tab.get('id') == 'party_relations')
        ]


@meta_bp.route('/objects', methods=['GET'])
def list_objects():
    """获取所有对象类型列表"""
    version = _ensure_fresh_meta()
    objects = []

    for obj_id in registry.list_objects():
        obj = registry.get(obj_id)
        # [G7 2026-11-02] 平台机制对象不对外暴露通用对象元数据入口
        if obj and obj.persistent and not getattr(obj, 'skip_generic_api', False):
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
            # [R-MM-02 A-02-3] 完整动作声明可直接读取，前端「动作详情」不再硬编码
            'instance_scope': action.instance_scope.value,
            'object_types': list(action.object_types),
            'params': list(action.params),
            'preconditions': dict(action.preconditions),
            'effects': list(action.effects),
            'emits': list(action.emits),
            'audit': action.audit,
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


@meta_bp.route('/<object_type>/ui-config', methods=['GET'])
def get_ui_config(object_type: str):
    """[FIX BUG-V048 2026-07-06 dev agent] 获取对象类型的 UI 配置 (含 audit_history_excluded_child_object_types)
    """
    try:
        config = _ui_config_loader.load_schema(object_type)
        if not config:
            return jsonify({
                'success': False,
                'error': f'UI config not found for: {object_type}',
            }), 404
        # [模块门控] party 关闭（BIP 应用架构管理部署）时 org 无「往来关系」分区
        from meta.core.platform_modules import is_module_enabled
        if object_type == 'org' and not is_module_enabled('party'):
            _strip_party_detail_section(config)
        return jsonify({
            'success': True,
            'data': config,
            'object_type': object_type,
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'object_type': object_type,
        }), 500


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


# ---------------------------------------------------------------------------
# [T13-5 2026-11-13] UI 元数据聚合端点
#   只输出「声明态」UI 元数据（字段/分区/动作/筛选/字段策略声明），
#   不返回任何权限判定结果，不为 action 赋 enabled（启用态仍由 evaluate 决定）。
# ---------------------------------------------------------------------------

def _empty_block(name: str) -> Any:
    """block 构建失败时的空块（形状与正常块一致，前端可安全渲染）"""
    if name == 'list':
        return {'columns': [], 'actions': [], 'data_source': None, 'stats': None}
    if name == 'detail':
        return {'sections': [], 'tabs': []}
    if name == 'form':
        return {'sections': [], 'tabs': [], 'fields': []}
    if name == 'filters':
        return []
    if name == 'field_policies':
        return {}
    return {}


def _warn(warnings: list, code: str, where: str, message: str) -> None:
    """ui-meta 运行期降级警告（不抛错，页面继续可用）。"""
    if warnings is None:
        return
    warnings.append({'code': code, 'where': where, 'message': message})


#: M0 条件文法：只允许 {field, in|equals|not_empty} 单层（禁止嵌套/表达式）。
_CONDITION_OPS = ('in', 'equals', 'not_empty')


def _validate_condition(condition: Any, field_map: dict = None) -> str:
    """校验封闭条件文法；返回错误码（'' = 合法）。"""
    if not isinstance(condition, dict) or not condition:
        return 'UNKNOWN_CONDITION'
    field = condition.get('field')
    if not isinstance(field, str) or not field:
        return 'UNKNOWN_CONDITION'
    ops = [op for op in _CONDITION_OPS if op in condition]
    if len(ops) != 1:
        return 'UNKNOWN_CONDITION'
    if set(condition) - {'field', ops[0]}:
        return 'UNKNOWN_CONDITION'
    if ops[0] == 'in' and (not isinstance(condition['in'], list) or not condition['in']):
        return 'UNKNOWN_CONDITION'
    if ops[0] == 'not_empty' and not isinstance(condition['not_empty'], bool):
        return 'UNKNOWN_CONDITION'
    if field_map is not None and field not in field_map:
        return 'UNKNOWN_FIELD'
    return ''


def _valid_roles(roles: Any) -> bool:
    return isinstance(roles, list) and all(isinstance(r, str) and r for r in roles)


def _action_to_dict(action: Any, field_map: dict = None, warnings: list = None) -> dict:
    """动作声明统一成 dict（字符串形态保留 id/label），不注入 enabled。"""
    if isinstance(action, dict):
        item = dict(action)
    elif isinstance(action, str):
        item = {'id': action, 'label': action}
    else:
        return {}

    ident = item.get('id') or item.get('label') or ''
    if item.get('visible_when'):
        error = _validate_condition(item['visible_when'], field_map)
        if error:
            item.pop('visible_when', None)
            _warn(warnings, error, f'actions.{ident}.visible_when', '条件非法，已忽略 visible_when')
    if 'roles' in item:
        if not _valid_roles(item['roles']):
            item.pop('roles', None)
            _warn(warnings, 'UNKNOWN_CONDITION', f'actions.{ident}.roles', 'roles 必须是字符串数组，已忽略')
        elif not item['roles']:
            item.pop('roles')
    return item


def _section_columns(section) -> int:
    """表单分区栅格列数：columns 是既有的「行布局列」List，空则按 2 列。"""
    return len(section.columns) if section.columns else 2


def _form_section_dict(section) -> dict:
    return {
        'key': section.key or '',
        'label': section.title or section.i18n_key or '',
        'fields': list(section.fields),
        'columns': _section_columns(section),
        'col_span_map': dict(section.col_span_map or {}),
    }


def _tab_dict(tab) -> dict:
    return {
        'key': tab.key,
        'label': tab.label,
        'section_keys': list(tab.section_keys),
    }


def _list_column_dict(col, field_map: dict, warnings: list = None) -> dict:
    """列表列下发（前端 MetaListPage 的唯一消费口径）。

    枚举标签/颜色按「列级声明 → 字段 ui.options → 字段 enum_values」回落，
    保证 payload / 状态这类字段只需在 YAML 字段上声明一次 `ui.options`，
    表格和下拉就都显示中文标签，不必再在前端维护映射。
    """
    meta_field = field_map.get(col.key)
    ui = getattr(meta_field, 'ui', None) if meta_field is not None else None
    options = list(col.enum_values or [])
    if not options and ui is not None:
        options = list(getattr(ui, 'options', None) or [])
    if not options and meta_field is not None:
        options = list(getattr(meta_field, 'enum_values', None) or [])

    # 展示类型：view_config_service 会用字段类型覆盖列的 type（如 switch 字段是
    # integer），这里按「两值 0/1 枚举」还原成 boolean，前端才会渲染成 启用/停用 徽标
    display_type = col.field_type or ''
    values = {str(opt.get('value')).lower() for opt in options if isinstance(opt, dict)}
    if values and len(values) <= 2 and values <= {'0', '1', 'true', 'false'}:
        display_type = 'boolean'

    badge_colors = {}
    for opt in options:
        if not isinstance(opt, dict) or not opt.get('color'):
            continue
        value = opt.get('value')
        # 键统一转成字符串：前端按 String(rawValue) 命中，0/1 与 true/false 都能对上
        badge_colors[str(value).lower()] = opt['color']
    filter_options = list(col.filter_options or []) or options
    payload = {
        'field': col.key,
        'label': col.title or (meta_field.name if meta_field is not None else '') or col.key,
        'type': display_type,
        'width': col.width,
        'position': col.position,
        'importance': col.importance,
        'sortable': bool(col.sortable),
        'filterable': bool(col.filterable),
        'filter_type': col.filter_type or '',
        'filter_options': filter_options,
        'filter_placeholder': col.filter_placeholder or '',
        'enum_type': col.enum_type or '',
        'tag_enum': col.enum_type or '',
        'enum_values': options,
        'badge_colors': badge_colors,
        'api_param_key': col.api_param_key or '',
        'format': col.format or '',
        'hidden_in_list': bool(col.hidden_in_list),
        'computed': bool(col.computed),
        'searchable': bool(getattr(col, 'searchable', True)),
    }
    # [M0 2026-11-16] 条件可见性 / 角色：仅非空时下发（未声明 ⇒ 输出不变）
    visible_when = getattr(col, 'visible_when', None) or {}
    if visible_when:
        error = _validate_condition(visible_when, field_map)
        if error:
            _warn(warnings, error, f'list.columns.{col.key}.visible_when',
                  '条件非法，已忽略 visible_when')
        else:
            payload['visible_when'] = dict(visible_when)
    roles = list(getattr(col, 'roles', None) or [])
    if roles:
        payload['roles'] = roles
    return payload


def _list_block(config, meta_obj, warnings: list = None) -> dict:
    lst = getattr(config, 'list', None)
    if not lst:
        return _empty_block('list')
    field_map = {f.id: f for f in getattr(meta_obj, 'fields', []) or []}
    # [S8] 声明式数据源/指标：未声明时下发 null（前端继续走既有 fetcher，行为不变）
    data_source = dict(getattr(lst, 'data_source', None) or {}) or None
    stats = dict(getattr(lst, 'stats', None) or {}) or None
    return {
        'columns': [_list_column_dict(col, field_map, warnings) for col in lst.columns],
        'actions': [_action_to_dict(a, field_map, warnings) for a in lst.actions],
        'data_source': data_source,
        'stats': stats,
    }


def _detail_block(config, meta_obj) -> dict:
    detail = getattr(config, 'detail', None)
    if not detail:
        return _empty_block('detail')
    return {
        'sections': [
            {
                'key': facet.key or facet.id or '',
                'label': facet.label or facet.title or facet.i18n_key or '',
                'fields': list(facet.fields),
                'columns': facet.columns or 2,
                'col_span_map': dict(facet.col_span_map or {}),
            }
            for facet in detail.facets
        ],
        'tabs': [_tab_dict(t) for t in getattr(detail, 'section_tabs', [])],
    }


def _form_block(config, meta_obj, warnings: list = None) -> dict:
    form = getattr(config, 'form', None)
    if not form:
        return _empty_block('form')
    field_map = {f.id: f for f in getattr(meta_obj, 'fields', []) or []}
    fields = []
    for section in form.sections:
        field_ids = list(section.fields or [])
        if not field_ids:
            # 分区用 columns 声明布局时（集成模块三张表均如此），字段在各列里
            for column in getattr(section, 'columns', []) or []:
                field_ids.extend(getattr(column, 'fields', []) or [])
        for field_id in field_ids:
            meta_field = field_map.get(field_id)
            if not meta_field:
                continue
            ui = meta_field.ui
            item = {
                'key': field_id,
                'label': meta_field.name,
                'widget': ui.widget or meta_field.field_type.value,
                # 字段原始类型（string/integer/json/...）：自定义表单据此做
                # JSON 文本与对象的互转等控件级处理
                'field_type': meta_field.field_type.value,
                'required': bool(meta_field.required),
                'readonly': bool(ui.readonly),
                'visible': bool(ui.visible),
                'enum_type': meta_field.enum_type or '',
                # 字段级取值域与默认值：自定义表单（如集成模块抽屉）直接用这两项
                # 渲染下拉与初始值，不再在前端复制一份常量表 / emptyForm。
                'options': [dict(opt) for opt in (ui.options or [])],
                'default': meta_field.default,
            }
            if ui.placeholder:
                item['placeholder'] = ui.placeholder
            help_text = getattr(ui, 'help_text', '')
            if help_text:
                item['help_text'] = help_text
            if ui.visible_when:
                item['visible_when'] = ui.visible_when
            # [M0 2026-11-16] 条件只读 + 字段级角色：仅非空时下发
            readonly_when = getattr(ui, 'readonly_when', None)
            if readonly_when:
                error = _validate_condition(readonly_when, field_map)
                if error:
                    _warn(warnings, error, f'form.fields.{field_id}.readonly_when',
                          '条件非法，已忽略 readonly_when')
                else:
                    item['readonly_when'] = dict(readonly_when)
            field_roles = list(getattr(ui, 'roles', None) or [])
            if field_roles:
                item['roles'] = field_roles
            if ui.col_span:
                item['col_span'] = ui.col_span
            if ui.depends_on:
                item['depends_on'] = [ui.depends_on]
            if ui.value_help:
                item['value_help'] = value_help_to_dict(ui.value_help)
            fields.append(item)
    return {
        'layout': form.layout,
        'sections': [_form_section_dict(s) for s in form.sections],
        'tabs': [_tab_dict(t) for t in form.tabs],
        'fields': fields,
    }


def _filters_block(config, meta_obj) -> Any:
    filters = getattr(getattr(config, 'filter', None), 'filters', None)
    if not filters:
        return []
    return [_dataclass_to_dict(f) for f in filters]


def _policies_block(meta_obj) -> dict:
    """字段级策略声明（只输出非默认声明，空对象表示全部按默认口径）。

    [M0 2026-11-16] 纳入条件只读与字段级 roles：permission 优先，roles 取并集。
    """
    result = {}
    for meta_field in getattr(meta_obj, 'fields', []) or []:
        perm = getattr(meta_field, 'permission', None)
        ui = getattr(meta_field, 'ui', None)
        ui_roles = list(getattr(ui, 'roles', None) or [])
        readonly_when = getattr(ui, 'readonly_when', None)
        has_permission_decl = bool(perm) and (
            perm.readable is False or perm.writable is False or bool(perm.roles)
        )
        if not (has_permission_decl or ui_roles or readonly_when):
            continue
        roles = list(perm.roles or []) if perm else []
        for role in ui_roles:
            if role not in roles:
                roles.append(role)
        entry = {
            'readable': bool(perm.readable) if perm else True,
            'writable': bool(perm.writable) if perm else True,
            'roles': roles,
        }
        if isinstance(readonly_when, dict) and not _validate_condition(readonly_when):
            entry['readonly_when'] = dict(readonly_when)
        result[meta_field.id] = entry
    return result


def _ui_view_sources(object_type: str, view: str = None) -> list:
    """[M0] explain=1：定位 ui_view_config 所在 YAML 与近似行号（仅诊断用）。"""
    try:
        schema_dir = get_yaml_schema_dir()
        if not schema_dir or not os.path.isdir(schema_dir):
            return []
        id_pattern = re.compile(r'^id:\s*' + re.escape(object_type) + r'\s*$')
        sources = []
        for name in sorted(os.listdir(schema_dir)):
            if not name.endswith(('.yaml', '.yml')):
                continue
            path = os.path.join(schema_dir, name)
            try:
                with open(path, encoding='utf-8') as handle:
                    lines = handle.read().splitlines()
            except OSError:
                continue
            if not any(id_pattern.match(line) for line in lines):
                continue
            anchors = [
                ('ui_view_config', re.compile(r'^ui_view_config:\s*$')),
                ('list.columns', re.compile(r'^ {4}columns:\s*$')),
                ('list.actions', re.compile(r'^ {4}actions:\s*$')),
                ('variants', re.compile(r'^ {2}variants:\s*$')),
            ]
            if view:
                anchors.append(
                    ('variants.' + view, re.compile(r'^ {4}' + re.escape(view) + r':\s*$')))
            for key, pattern in anchors:
                for index, line in enumerate(lines, start=1):
                    if pattern.match(line):
                        sources.append({'file': path, 'key': key, 'line': index})
                        break
            break
        return sources
    except Exception:  # noqa: BLE001 —— 诊断信息缺失不影响正常响应
        logger.warning('[ui-meta] explain 来源定位失败: %s', object_type, exc_info=True)
        return []


@meta_bp.route('/<object_type>/ui-meta', methods=['GET'])
def get_ui_meta(object_type: str):
    """[T13-5 2026-11-13] 聚合 UI 元数据（单请求取齐 list/detail/form/filters）。

    鉴权口径与相邻 view-config / form-view 一致（蓝图内无额外装饰器，沿用既有口径）。
    任一 block 构建失败只降级该块并置 partial=True，不影响其余块。

    [M0 2026-11-16] 支持 `?view=<variant>`；顶层 `meta` 下发 warnings /
    effective_view；`?explain=1` 附 sources（YAML 文件 + 近似行号）。
    """
    _ensure_fresh_meta()
    view = request.args.get('view') or None
    explain = request.args.get('explain') == '1'
    warnings: list = []

    effective_view = view or 'default'
    if view:
        available = view_config_service.get_available_views(object_type)
        if view not in available:
            _warn(warnings, 'UNKNOWN_VIEW', f'view.{view}',
                  f'未声明的视图变体，已回退 default（可用: {", ".join(available)}）')
            effective_view = 'default'

    config = view_config_service.get_or_build_view_config(
        object_type, view if effective_view != 'default' else None)
    meta_obj = registry.get(object_type)

    data: dict = {
        'schema_version': getattr(config, 'schema_version', '') if config else '',
    }
    partial = False

    builders = (
        ('list', lambda: _list_block(config, meta_obj, warnings)),
        ('detail', lambda: _detail_block(config, meta_obj)),
        ('form', lambda: _form_block(config, meta_obj, warnings)),
        ('filters', lambda: _filters_block(config, meta_obj)),
        ('field_policies', lambda: _policies_block(meta_obj)),
    )
    for name, builder in builders:
        try:
            data[name] = builder()
        except Exception:  # noqa: BLE001 —— 单块失败不拖垮聚合端点
            logger.exception("[ui-meta] block 构建失败: %s/%s", object_type, name)
            data[name] = _empty_block(name)
            partial = True

    # 动作合并：list 动作 + detail 动作，按 id 去重（先到先得）
    field_map = {f.id: f for f in getattr(meta_obj, 'fields', []) or []}
    merged_actions = []
    seen_action_ids = set()
    for action in (
        list((data.get('list') or {}).get('actions') or [])
        + list((data.get('detail') or {}).get('actions') or [])
    ):
        item = _action_to_dict(action, field_map, warnings)
        action_id = item.get('id') or item.get('label') or ''
        if action_id in seen_action_ids:
            continue
        seen_action_ids.add(action_id)
        merged_actions.append(item)

    meta_block = {
        'warnings': warnings,
        'effective_view': effective_view,
        'schema_version': data.get('schema_version', ''),
    }
    if explain:
        meta_block['sources'] = _ui_view_sources(
            object_type, view if effective_view != 'default' else None)

    data.update({
        'object_type': object_type,
        'label': (meta_obj.name if meta_obj else '') or object_type,
        'partial': partial,
        'actions': merged_actions,
        'meta': meta_block,
    })

    return jsonify({'success': True, 'data': data})


@meta_bp.route('/<object_type>/defaults-preview', methods=['POST'])
def preview_object_defaults(object_type: str):
    """属性确定规则 dry-run 预演（不落库，仅返回判定日志）

    [规则模型 二期 2026-10-03] 供规则配置 / 表单联动"试算"：
    传入一份**未保存**的单据草稿，返回会被自动带出的字段与逐条判定日志。

    Body: ``{"data": {...}, "original_data": {...}?}``
    """
    _ensure_fresh_meta()
    meta_obj = registry.get(object_type)
    if not meta_obj:
        return jsonify({
            'success': False,
            'error': f'Object type not found: {object_type}',
        }), 404

    payload = request.get_json(silent=True) or {}
    data = payload.get('data') or {}
    original_data = payload.get('original_data') or None

    from meta.core.datasource import get_data_source
    from meta.core.rule_executor import RuleEngine
    from meta.core.action_executor import ActionExecutor
    from meta.services.auth_middleware import get_current_user

    ds = get_data_source()
    executor = ActionExecutor(ds, RuleEngine(ds))
    user = get_current_user() or {}
    if user:
        executor.set_audit_user(
            user_id=user.get('user_id') or user.get('id'),
            user_name=user.get('username') or user.get('user_name') or '',
        )

    result = executor.dry_run_defaults(meta_obj, data, original_data=original_data)
    return jsonify({'success': result.get('success', False), 'data': result})


@meta_bp.route('/reload', methods=['POST'])
def reload_meta():
    """重新加载元数据"""
    try:
        schema_dir = get_yaml_schema_dir()
        # side_effects 声明预校验：非法表达式在 registry.reload 之前失败，
        # 保证 reload 报错时内存中的元模型仍是旧的（不留半截状态）。
        validate_schema_dir_side_effects(schema_dir)
        registry._schema_dir = schema_dir
        count = registry.reload(schema_dir)
        # 同上：单目录 reload 会丢弃 apps/* 的 BO，需重放应用 schema
        from meta.core.app_registry import reapply_app_schemas
        reapply_app_schemas()
        view_config_service.invalidate_cache()

        return ok_message(f'Reloaded {count} meta objects')
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

    return ok({
        'key': key,
        'text': text,
        'locale': locale,
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
        return error_response('types parameter required')

    enum_types = [t.strip() for t in types_param.split(',') if t.strip()]

    from meta.api.enum_api import _get_data_source as _get_enum_ds, _row_to_dict

    ds = _get_enum_ds()
    result = {}

    # [FR-006] 批量查询替代逐类型查询, 避免 N+1
    if not enum_types:
        return ok(result)

    # 批量存在性检查
    placeholders = ','.join(['?'] * len(enum_types))
    cursor = ds.execute(
        f"SELECT id FROM enum_types WHERE id IN ({placeholders})",
        enum_types
    )
    existing_ids = {row[0] for row in cursor.fetchall()}

    # 批量获取所有枚举值
    cursor = ds.execute(
        f"SELECT enum_type_id, code, name, name_en, sort_order, is_active, parent_code "
        f"FROM enum_values WHERE enum_type_id IN ({placeholders}) AND is_active = 1 "
        f"ORDER BY enum_type_id, sort_order, code",
        enum_types
    )
    columns = ['code', 'name', 'name_en', 'sort_order', 'is_active', 'parent_code']
    values_by_type = {}
    for row in cursor.fetchall():
        tid = row[0]
        if tid not in values_by_type:
            values_by_type[tid] = []
        values_by_type[tid].append(dict(zip(columns, row[1:])))

    for enum_type in enum_types:
        if enum_type not in existing_ids:
            result[enum_type] = {
                'success': False,
                'message': f'枚举类型不存在: {enum_type}'
            }
        else:
            result[enum_type] = {
                'success': True,
                'data': values_by_type.get(enum_type, [])
            }

    return ok(result)


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
        return ok([])

    filter_config = view_config.filter
    target_filter = None
    if hasattr(filter_config, 'filters'):
        for f in filter_config.filters:
            if (f.key if hasattr(f, 'key') else f.get('key', '')) == filter_key:
                target_filter = f
                break

    if not target_filter:
        return ok([])

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

    db_path = get_meta_db_path()
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

    db_path = get_meta_db_path()
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

