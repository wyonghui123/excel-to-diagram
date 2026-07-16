# -*- coding: utf-8 -*-
"""
BO Action (v3.5 P1 + v3.18 enum-mgmt-spec): enum_type.create / enum_type.update / enum_type.delete
===================================================================================================

业务枚举类型的 CRUD。

【v3.18 更新】
- mutability 值空间规范化为 3 档：fullEditable / extensible / locked
- 校验改用 ErrorCode 错误码（与 API 路径保持一致）
- 系统枚举保护 + 字段必填 + mutability 值校验，由本服务和 EnumProtectionInterceptor 共同保障
  （拦截器跑在 BO Action 路径，防御纵深）

注：业务逻辑与 enum_api.py:331-503 类似但独立维护（API 直连路径不走 BO Action）。
"""
import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict

from flask import g, request

logger = logging.getLogger(__name__)


def _get_ds():
    from meta.core.datasource import get_data_source
    db_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'architecture.db',
    )
    return get_data_source("sqlite", database=db_path)


def _set_bo_context(user_id, user_name):
    """设置 BO framework 用户上下文 (审计用)"""
    try:
        from meta.core.bo_framework import bo_framework
        bo_framework.set_user_context(
            user_id=user_id,
            user_name=user_name or 'unknown',
            ip_address=request.remote_addr,
        )
    except Exception as e:
        logger.warning(f"[enum_type] Failed to set BO context: {e}")


def _get_admin_info(context):
    """从 context 取 admin 信息"""
    return {
        'user_id': context.get('user_id'),
        'user_name': context.get('user_name') or 'system',
    }


def _validate_mutability_or_err(mutability: str):
    """v3.18: 校验 mutability 值合法性。返回 (ok: bool, err_msg: str)"""
    from meta.core.interceptors.enum_protection_interceptor import ALLOWED_MUTABILITY
    if mutability not in ALLOWED_MUTABILITY:
        return False, f'mutability 必须是 {sorted(ALLOWED_MUTABILITY)} 之一，当前值 "{mutability}"'
    return True, ''


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1️⃣ enum_type.create
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def enum_type_create_handler(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    enum_type.create Action 处理器

    Args:
        params: {
            'id': str (required),
            'name': str (required),
            'category': 'business' (default, 不允许 'system'),
            'mutability': 'extensible' | 'fullEditable' | 'locked' (default 'extensible'),
            'dimension_schema': object (optional),
            'description': str (default ''),
        }
    """
    enum_type_id = params.get('id')
    name = params.get('name')
    if not enum_type_id or not name:
        return {'success': False, 'data': None, 'message': 'id 和 name 必填', 'errors': ['ACTION_PARAMS_MISSING']}

    category = params.get('category', 'business')
    if category == 'system':
        return {'success': False, 'data': None, 'message': '系统枚举不可通过 BO Action 创建（请使用初始化脚本或 migrate_enums.py）', 'errors': ['SYSTEM_ENUM_IMMUTABLE']}
    mutability = params.get('mutability', 'extensible')

    # [v3.18 FR-001] mutability 值空间校验
    ok, err = _validate_mutability_or_err(mutability)
    if not ok:
        return {'success': False, 'data': None, 'message': err, 'errors': ['INVALID_MUTABILITY']}

    dimension_schema = params.get('dimension_schema')
    description = params.get('description', '')

    dimension_schema_str = json.dumps(dimension_schema) if dimension_schema else None

    try:
        ds = _get_ds()

        # 查重
        existing = ds.execute(
            "SELECT id FROM enum_types WHERE id = ?", [enum_type_id]
        ).fetchone()
        if existing:
            return {'success': False, 'data': None, 'message': f'枚举类型 {enum_type_id} 已存在', 'errors': ['DUPLICATE_CODE']}

        # 设置 BO 上下文 (审计)
        admin = _get_admin_info(context)
        _set_bo_context(admin['user_id'], admin['user_name'])

        # 写库
        ds.execute(
            """INSERT INTO enum_types (id, name, category, mutability, dimension_schema, description, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [enum_type_id, name, category, mutability, dimension_schema_str, description, datetime.now().isoformat()]
        )
        ds.commit()

        return {
            'success': True,
            'data': {'id': enum_type_id, 'name': name, 'category': category, 'mutability': mutability},
            'message': '枚举类型创建成功',
        }
    except Exception as e:
        logger.exception(f"[enum_type.create] failed: {e}")
        return {'success': False, 'data': None, 'message': f'创建失败: {e}', 'errors': ['CREATE_ENUM_TYPE_ERROR']}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2️⃣ enum_type.update
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def enum_type_update_handler(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    enum_type.update Action 处理器

    Args:
        params: {
            'id': str (required),
            'name': str (optional),
            'mutability': 'extensible' | 'fullEditable' | 'locked' (optional),
            'dimension_schema': object (optional),
            'description': str (optional),
        }
    """
    enum_type_id = params.get('id') or params.get('enum_type_id')
    if not enum_type_id:
        return {'success': False, 'data': None, 'message': 'id 必填', 'errors': ['ACTION_PARAMS_MISSING']}

    try:
        ds = _get_ds()

        existing = ds.execute(
            "SELECT id, name, category, mutability, dimension_schema, description FROM enum_types WHERE id = ?",
            [enum_type_id]
        ).fetchone()
        if not existing:
            return {'success': False, 'data': None, 'message': '枚举类型不存在', 'errors': ['DATA_NOT_FOUND']}

        # sqlite3.Row / tuple 都兼容
        if hasattr(existing, 'keys'):
            existing_dict = dict(existing)
        else:
            existing_dict = {
                'id': existing[0], 'name': existing[1], 'category': existing[2],
                'mutability': existing[3], 'dimension_schema': existing[4],
                'description': existing[5],
            }

        if existing_dict.get('category') == 'system':
            return {'success': False, 'data': None, 'message': '系统枚举不可修改', 'errors': ['SYSTEM_ENUM_IMMUTABLE']}

        # [v3.18 FR-001] mutability 值空间校验
        if 'mutability' in params:
            ok, err = _validate_mutability_or_err(params['mutability'])
            if not ok:
                return {'success': False, 'data': None, 'message': err, 'errors': ['INVALID_MUTABILITY']}

        name = params.get('name', existing_dict.get('name'))
        mutability = params.get('mutability', existing_dict.get('mutability'))
        description = params.get('description', existing_dict.get('description', ''))
        dimension_schema = params.get('dimension_schema')
        dimension_schema_str = (
            json.dumps(dimension_schema) if dimension_schema
            else existing_dict.get('dimension_schema')
        )

        # 设置 BO 上下文
        admin = _get_admin_info(context)
        _set_bo_context(admin['user_id'], admin['user_name'])

        ds.execute(
            """UPDATE enum_types
               SET name = ?, mutability = ?, dimension_schema = ?, description = ?
               WHERE id = ?""",
            [name, mutability, dimension_schema_str, description, enum_type_id]
        )
        ds.commit()

        return {
            'success': True,
            'data': {'id': enum_type_id, 'name': name, 'mutability': mutability},
            'message': '更新成功',
        }
    except Exception as e:
        logger.exception(f"[enum_type.update] failed: {e}")
        return {'success': False, 'data': None, 'message': f'更新失败: {e}', 'errors': ['UPDATE_ENUM_TYPE_ERROR']}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3️⃣ enum_type.delete
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def enum_type_delete_handler(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    enum_type.delete Action 处理器

    Args:
        params: {
            'id': str (required),
        }
    """
    enum_type_id = params.get('id') or params.get('enum_type_id')
    if not enum_type_id:
        return {'success': False, 'data': None, 'message': 'id 必填', 'errors': ['ACTION_PARAMS_MISSING']}

    try:
        ds = _get_ds()

        existing = ds.execute(
            "SELECT id, name, category FROM enum_types WHERE id = ?",
            [enum_type_id]
        ).fetchone()
        if not existing:
            return {'success': False, 'data': None, 'message': '枚举类型不存在', 'errors': ['DATA_NOT_FOUND']}

        if hasattr(existing, 'keys'):
            existing_dict = dict(existing)
        else:
            existing_dict = {'id': existing[0], 'name': existing[1], 'category': existing[2]}

        if existing_dict.get('category') == 'system':
            return {'success': False, 'data': None, 'message': '系统枚举不可删除', 'errors': ['SYSTEM_ENUM_IMMUTABLE']}

        # 检查 enum_values
        value_count = ds.execute(
            "SELECT COUNT(*) FROM enum_values WHERE enum_type_id = ?",
            [enum_type_id]
        ).fetchone()[0]
        if value_count > 0:
            return {
                'success': False, 'data': None,
                'message': f'该枚举类型下有 {value_count} 个枚举值, 无法删除',
                'errors': ['HAS_VALUES'],
            }

        # 设置 BO 上下文 (审计)
        admin = _get_admin_info(context)
        _set_bo_context(admin['user_id'], admin['user_name'])

        ds.execute("DELETE FROM enum_types WHERE id = ?", [enum_type_id])
        ds.commit()

        return {
            'success': True,
            'data': {'id': enum_type_id, 'name': existing_dict.get('name')},
            'message': '删除成功',
        }
    except Exception as e:
        logger.exception(f"[enum_type.delete] failed: {e}")
        return {'success': False, 'data': None, 'message': f'删除失败: {e}', 'errors': ['DELETE_ENUM_TYPE_ERROR']}
