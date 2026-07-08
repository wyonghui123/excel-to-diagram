# -*- coding: utf-8 -*-
import re
import logging
from flask import Blueprint, request, jsonify, g
from meta.services.auth_middleware import login_required

from meta.core.models import registry
from meta.core.key_template_engine import KeyTemplateEngine, KeyTemplateConfig, SequenceConfig

logger = logging.getLogger(__name__)

key_template_bp = Blueprint('key_template', __name__, url_prefix='/api/v2/key-template')

_engine = None


def set_engine(engine: KeyTemplateEngine):
    global _engine
    _engine = engine


def _resolve_parent_fields_for_preview(config, field_values, parent_params):
    """
    解析 key_template 模式中引用的父级字段值。
    从 parent_params 中的父级 ID 查找对应的 code/name 值。
    """
    field_refs = re.findall(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}', config.pattern)
    ds = _engine._data_source if _engine else None
    if not ds:
        return

    for ref in field_refs:
        if ref.upper().startswith('SEQ'):
            continue
        if ref in field_values and field_values[ref]:
            continue

        parent_field = f"{ref}_id"
        if parent_field not in parent_params:
            parent_field = ref.replace('_code', '_id')
            if parent_field not in parent_params:
                parent_field = ref.removesuffix('_no')
                parent_field = f"{parent_field}_id"
                if parent_field not in parent_params:
                    # [FIXED 2026-06-11] 兼容 _bo_id 后缀（如 source_bo_id / target_bo_id）
                    # ref 可能是 source_code/target_code，但前端传的是 source_bo_id/target_bo_id
                    # 与 KeyTemplateInterceptor._resolve_parent_fields 保持一致
                    bo_id_field = f"{ref.replace('_code', '')}_bo_id"
                    if bo_id_field in parent_params:
                        parent_field = bo_id_field

        if parent_field in parent_params and parent_params[parent_field]:
            parent_id = parent_params[parent_field]
            base_type = ref.replace('_code', '').replace('_no', '')
            candidate_tables = [base_type, base_type + 's', base_type + 'es']
            # [FIXED 2026-06-11] source_bo_id/target_bo_id 直接查 business_objects
            if parent_field in ('source_bo_id', 'target_bo_id'):
                candidate_tables = ['business_objects']

            try:
                existing_tables = set()
                tables_result = ds.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
                for t in tables_result:
                    existing_tables.add(
                        t[0] if isinstance(t, tuple) else (t.get('name', '') if isinstance(t, dict) else '')
                    )

                object_type_table = base_type
                for ct in candidate_tables:
                    if ct in existing_tables:
                        object_type_table = ct
                        break

                table_cols = ds.execute(
                    f"PRAGMA table_info({object_type_table})"
                ).fetchall()
                col_names = [
                    c[1] if isinstance(c, tuple) else (c.get('name', '') if isinstance(c, dict) else '')
                    for c in table_cols
                ]
                code_col = 'code' if 'code' in col_names else 'name'

                result = ds.execute(
                    f"SELECT {code_col} FROM {object_type_table} WHERE id = ?",
                    (parent_id,)
                ).fetchone()
                if result:
                    val = result[0] if isinstance(result, tuple) else (
                        result.get(code_col) if isinstance(result, dict) else result
                    )
                    if val:
                        field_values[ref] = val
                        logger.info(
                            f"[KeyTemplateAPI] Resolved {ref}={val} "
                            f"from {object_type_table}.id={parent_id}"
                        )
            except Exception as e:
                logger.debug(
                    f"[KeyTemplateAPI] Could not resolve {ref}: {e}"
                )


def _get_missing_parent_fields(config, field_values):
    """
    [NEW 2026-06-11] 返回 config.segments 中 parent_field.source 在 field_values 中缺失的字段名列表。
    用于在 API 层返回清晰的 422 错误。
    """
    missing = []
    for seg in config.segments:
        if seg.get("type") == "parent_field":
            source = seg.get("source", seg.get("name", ""))
            if not field_values.get(source):
                missing.append(source)
    return missing


def _resolve_physical_table_name(object_type):
    """
    [NEW 2026-06-11] 将逻辑对象名解析为物理表名。

    例如 'business_object' → 'business_objects'（SQLite 中实际表名带复数 s）。
    使用 candidate_tables 策略：依次尝试单数形式、+s、+es。
    """
    if not _engine or not _engine._data_source:
        return object_type

    ds = _engine._data_source
    try:
        existing_tables = set()
        tables_result = ds.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        for t in tables_result:
            existing_tables.add(
                t[0] if isinstance(t, tuple) else (t.get('name', '') if isinstance(t, dict) else '')
            )

        candidate_tables = [object_type, object_type + 's', object_type + 'es']
        for ct in candidate_tables:
            if ct in existing_tables:
                logger.debug(
                    f"[KeyTemplateAPI] Resolved table name: {object_type} → {ct}"
                )
                return ct
    except Exception as e:
        logger.debug(f"[KeyTemplateAPI] _resolve_physical_table_name fallback: {e}")

    return object_type


@key_template_bp.route('/config/<object_type>', methods=['GET'])
@login_required
def get_config(object_type):
    meta_object = registry.get(object_type)
    if not meta_object:
        return jsonify({
            'success': False,
            'message': f'Unknown object type: {object_type}'
        }), 404

    # [DEBUG_MARK_20260615_1625] 用以验证后端是否使用最新代码
    import sys as _sys
    import os as _os
    _src_path = _os.path.abspath(__file__)
    _src_mtime = _os.path.getmtime(_src_path)
    logger.warning(f"[DEBUG_MARK_20260615] ENTERED preview/{object_type}, file={_src_path}, mtime={_src_mtime}, pid={_os.getpid()}, has_engine={_engine is not None}")
    key_template_raw = getattr(meta_object, 'key_template', None)
    if not key_template_raw:
        return jsonify({
            'success': True,
            'data': {'enabled': False},
            'message': 'No key_template configured for this object'
        })

    config = KeyTemplateConfig.from_dict(object_type, key_template_raw)

    result = {
        'object_type': object_type,
        'key_template': dict(key_template_raw)
    }

    if config.sequence:
        result['key_template']['sequence'] = config.sequence.to_dict()

    return jsonify({
        'success': True,
        'data': result
    })


@key_template_bp.route('/preview/<object_type>', methods=['POST'])
def preview_code(object_type):
    if not _engine:
        return jsonify({
            'success': False,
            'message': 'KeyTemplateEngine not available'
        }), 500

    meta_object = registry.get(object_type)
    if not meta_object:
        return jsonify({
            'success': False,
            'message': f'Unknown object type: {object_type}'
        }), 404

    key_template_raw = getattr(meta_object, 'key_template', None)
    if not key_template_raw or not key_template_raw.get('enabled'):
        return jsonify({
            'success': False,
            'message': f'No enabled key_template for {object_type}',
            'data': None
        }), 200

    body = request.get_json(silent=True) or {}
    field_values = dict(body.get('field_values', {}))
    parent_params = body.get('parent_params', {})
    generate = body.get('generate', False)

    config = KeyTemplateConfig.from_dict(object_type, key_template_raw)

    _resolve_parent_fields_for_preview(config, field_values, parent_params)

    # [FIXED 2026-06-11] 校验 parent_field 是否已解析
    missing = _get_missing_parent_fields(config, field_values)
    if missing:
        return jsonify({
            'success': False,
            'message': f'Missing parent field values: {", ".join(missing)}. '
                       f'Ensure the corresponding parent_id is provided in parent_params.',
            'code': 'MISSING_PARENT_FIELD',
            'missing_fields': missing,
        }), 422

    # [FIXED 2026-06-11] 解析物理表名和 prefix_filter 用于 auto_detect_start
    # 原 BUG: 引擎内部用 config.object_id = 'business_object'，但实际表是 'business_objects'
    # 导致 auto_detect_start SQL 报 "no such table: business_object" 退回 start=1
    physical_table = _resolve_physical_table_name(object_type)
    tokens = _engine._parser.parse(config.pattern)
    prefix_filter = _engine._parser.resolve_prefix(tokens, field_values)
    logger.debug(
        f"[KeyTemplateAPI] preview: object_type={object_type}, "
        f"table={physical_table}, prefix_filter={prefix_filter!r}"
    )

    if generate:
        code = _engine.generate_code(config, field_values, object_type,
                                     table_name=physical_table,
                                     prefix_filter=prefix_filter)
    else:
        code = _engine.preview_code(config, field_values,
                                    table_name=physical_table,
                                    prefix_filter=prefix_filter)

    if not code:
        return jsonify({
            'success': False,
            'message': 'Failed to generate code'
        }), 500

    return jsonify({
        'success': True,
        'data': {
            'code': code,
            'object_type': object_type,
            'generated': generate,
            # [NEW v1.1 2026-06-11] 返回 user_editable 等元信息，前端用于差异化 UI 提示
            'user_editable': config.user_editable,
            'pattern': config.pattern,
            'preview': config.preview or code,
        }
    })


@key_template_bp.route('/list-objects', methods=['GET'])
@login_required
def list_objects():
    objects_with_kt = []
    for obj_id, meta_object in registry.get_all().items():
        key_template_raw = getattr(meta_object, 'key_template', None)
        if key_template_raw and key_template_raw.get('enabled'):
            config = KeyTemplateConfig.from_dict(obj_id, key_template_raw)
            entry = {
                'object_type': obj_id,
                'name': meta_object.name,
                'pattern': key_template_raw.get('pattern', ''),
                'preview': key_template_raw.get('preview', ''),
                'auto_suggest': key_template_raw.get('auto_suggest', True)
            }
            if config.sequence:
                entry['sequence'] = config.sequence.to_dict()
            objects_with_kt.append(entry)

    return jsonify({
        'success': True,
        'data': objects_with_kt
    })