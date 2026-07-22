# -*- coding: utf-8 -*-
"""
角色维度范围API

提供角色维度范围声明的 CRUD 和推导预览
"""

from flask import Blueprint, request, jsonify
import os
import logging

from meta.core.datasource import get_data_source
from meta.api.user_api import login_required
from meta.services.auth_middleware import is_admin, get_current_user
from meta.services.dimension_scope_engine import get_dimension_scope_engine
from meta.api._audit_helper import write_permission_config_audit
from functools import wraps
import json

logger = logging.getLogger(__name__)

role_dim_bp = Blueprint('role_dim', __name__, url_prefix='/api/v1/roles')

_data_source = None


# ============================================================================
# [Spec 08] FR-005/007/009/010 辅助函数
# ============================================================================

WILDCARD_MARKER = '*'


def _is_wildcard_values(values):
    """检测 dimension_values 是否包含通配符 '*'"""
    if not values:
        return False
    return WILDCARD_MARKER in values


def _load_scopes_raw(ds, role_id):
    """[FR-007] 读取角色当前所有 dim scope (原始 dict 格式, 用于审计比较)

    Returns:
        list of dict: [{dimension_code, dimension_values (list), inherit_children, scope_mode}, ...]
    """
    try:
        cursor = ds.execute(
            "SELECT dimension_code, dimension_values, inherit_children, scope_mode "
            "FROM role_dimension_scopes WHERE role_id = ?",
            [role_id]
        )
        rows = []
        for row in cursor.fetchall():
            raw_values = row[1] or '[]'
            try:
                values = json.loads(raw_values)
            except (json.JSONDecodeError, TypeError):
                values = []
            rows.append({
                'dimension_code': row[0],
                'dimension_values': values,
                'inherit_children': bool(row[2]),
                'scope_mode': row[3] or 'include',
            })
        return rows
    except Exception as e:
        logger.warning(f'[FR-007] _load_scopes_raw failed: {e}')
        return []


def _get_role_users(ds, role_id):
    """[FR-005] 查询该角色绑定的所有用户 ID (通过 user_group_members → group_roles 链路)

    Returns:
        list of int: user_ids
    """
    try:
        cursor = ds.execute(
            "SELECT DISTINCT ugm.user_id "
            "FROM group_roles gr "
            "JOIN user_group_members ugm ON gr.group_id = ugm.group_id "
            "WHERE gr.role_id = ?",
            [role_id]
        )
        return [row[0] for row in cursor.fetchall()]
    except Exception as e:
        logger.warning(f'[FR-005] _get_role_users failed: {e}')
        return []


def _get_user_other_roles(ds, user_id, exclude_role_id):
    """[FR-005] 查询用户的其他角色 (排除当前 role_id)

    Returns:
        list of int: role_ids
    """
    try:
        cursor = ds.execute(
            "SELECT DISTINCT gr.role_id "
            "FROM group_roles gr "
            "JOIN user_group_members ugm ON gr.group_id = ugm.group_id "
            "WHERE ugm.user_id = ? AND gr.role_id != ?",
            [user_id, exclude_role_id]
        )
        return [row[0] for row in cursor.fetchall()]
    except Exception as e:
        logger.warning(f'[FR-005] _get_user_other_roles failed: {e}')
        return []


class DimScopeConflictError(Exception):
    """[FR-005] 多角色 wildcard + exclude 冲突"""
    def __init__(self, message, conflict_user_ids=None):
        super().__init__(message)
        self.conflict_user_ids = conflict_user_ids or []


class DimScopePermissionError(Exception):
    """[FR-010] 权限不足, 不允许配置 wildcard/exclude"""
    pass


def _check_wildcard_exclude_conflict(ds, role_id, new_scopes):
    """[FR-005] 多角色 Union 防冲突校验 (PM 决策: 选项 C)

    同一用户的所有角色不允许同时出现 '*' 通配 + 任何 exclude。

    校验逻辑:
    1. 检查 new_scopes 自身: 同一角色内不允许同时有 wildcard + exclude
    2. 检查与用户其他角色的冲突: 该 role 绑定的用户的其他 role 不能有相反配置

    Raises:
        DimScopeConflictError: 检测到冲突时
    """
    # 1. 检查 new_scopes 自身
    has_wildcard = any(
        _is_wildcard_values(s.get('dimension_values'))
        and s.get('scope_mode', 'include') == 'include'
        for s in new_scopes
    )
    has_exclude = any(s.get('scope_mode') == 'exclude' for s in new_scopes)
    if has_wildcard and has_exclude:
        raise DimScopeConflictError(
            "同一角色不允许同时配置 '*' 通配和 exclude "
            "(请改为 '*' 通配 + 显式 include 子集, 或全 exclude)"
        )

    # 2. 检查与用户其他角色的冲突
    # 查询该 role 绑定的所有用户 → 每个用户的其他 role → 其他 role 的 scopes
    user_ids = _get_role_users(ds, role_id)
    conflict_user_ids = []

    for user_id in user_ids:
        other_role_ids = _get_user_other_roles(ds, user_id, role_id)
        for other_role_id in other_role_ids:
            other_scopes = _load_scopes_raw(ds, other_role_id)
            other_has_wildcard = any(
                _is_wildcard_values(s.get('dimension_values'))
                and s.get('scope_mode', 'include') == 'include'
                for s in other_scopes
            )
            other_has_exclude = any(
                s.get('scope_mode') == 'exclude'
                for s in other_scopes
            )

            # 冲突条件: (new wildcard + other exclude) 或 (new exclude + other wildcard)
            if (has_wildcard and other_has_exclude) or (has_exclude and other_has_wildcard):
                conflict_user_ids.append(user_id)
                break  # 该用户已冲突, 不再检查其他 role

    if conflict_user_ids:
        conflict_type = 'wildcard' if has_exclude else 'exclude'
        opposite_type = 'exclude' if has_exclude else 'wildcard'
        raise DimScopeConflictError(
            f"用户 {conflict_user_ids} 已通过其他角色持有 "
            f"{conflict_type} 配置, 不允许再配 {opposite_type}",
            conflict_user_ids=conflict_user_ids
        )


def _check_wildcard_exclude_permission(new_scopes, user):
    """[FR-010] 权限限制: 仅 admin 可配置 '*' 通配和 exclude

    现有系统: is_admin(user) = 拥有 '*' 通配权限 = admin
    admin_required 装饰器已保证只有 admin 能调用 save 接口,
    此处显式校验以明确意图, 并为未来细粒度权限码预留扩展点。

    Raises:
        DimScopePermissionError: 非 admin 用户尝试配置 wildcard/exclude
    """
    has_wildcard = any(
        _is_wildcard_values(s.get('dimension_values'))
        and s.get('scope_mode', 'include') == 'include'
        for s in new_scopes
    )
    has_exclude = any(s.get('scope_mode') == 'exclude' for s in new_scopes)

    if has_wildcard or has_exclude:
        if not is_admin(user):
            raise DimScopePermissionError(
                "仅管理员可配置 '*' 通配或 exclude (需要 role:wildcard:configure / role:exclude:configure 权限)"
            )


def _log_dim_scope_changes(ds, role_id, old_scopes, new_scopes, user):
    """[FR-007] 审计日志: 检测新旧 scopes 变化, 写入高危操作审计

    审计事件:
    - dim_scope_wildcard_enabled: 启用 '*' 通配
    - dim_scope_wildcard_disabled: 关闭 '*' 通配
    - dim_scope_exclude_set: 切换为 exclude
    - dim_scope_exclude_unset: 切换回 include
    - high_risk_permission_change: 高危变更 (wildcard 启用时附加)
    """
    old_by_dim = {s['dimension_code']: s for s in old_scopes}
    new_by_dim = {s['dimension_code']: s for s in new_scopes}

    user_id = user.get('user_id') or user.get('id') if user else None
    all_dims = set(old_by_dim.keys()) | set(new_by_dim.keys())

    for dim_code in all_dims:
        old_scope = old_by_dim.get(dim_code, {})
        new_scope = new_by_dim.get(dim_code, {})

        old_vals = old_scope.get('dimension_values', []) or []
        new_vals = new_scope.get('dimension_values', []) or []
        old_mode = old_scope.get('scope_mode', 'include')
        new_mode = new_scope.get('scope_mode', 'include')

        old_is_wildcard = WILDCARD_MARKER in old_vals
        new_is_wildcard = WILDCARD_MARKER in new_vals

        # 检测 wildcard 启用
        if new_is_wildcard and not old_is_wildcard:
            write_permission_config_audit(
                action='UPDATE',
                object_type='role_dimension_scope',
                object_id=role_id,
                data={'event': 'dim_scope_wildcard_enabled',
                      'dimension_code': dim_code, 'role_id': role_id},
                parent_object_type='role',
                parent_object_id=role_id,
            )
            # 高危变更附加记录
            write_permission_config_audit(
                action='UPDATE',
                object_type='role_dimension_scope',
                object_id=role_id,
                data={'event': 'high_risk_permission_change',
                      'change': 'wildcard_enabled',
                      'role_id': role_id, 'dimension_code': dim_code},
                parent_object_type='role',
                parent_object_id=role_id,
            )

        # 检测 wildcard 关闭
        if old_is_wildcard and not new_is_wildcard:
            write_permission_config_audit(
                action='UPDATE',
                object_type='role_dimension_scope',
                object_id=role_id,
                data={'event': 'dim_scope_wildcard_disabled',
                      'dimension_code': dim_code, 'role_id': role_id},
                parent_object_type='role',
                parent_object_id=role_id,
            )

        # 检测 exclude 设置
        if new_mode == 'exclude' and old_mode != 'exclude':
            write_permission_config_audit(
                action='UPDATE',
                object_type='role_dimension_scope',
                object_id=role_id,
                data={'event': 'dim_scope_exclude_set',
                      'dimension_code': dim_code, 'role_id': role_id,
                      'excluded_ids': new_vals},
                parent_object_type='role',
                parent_object_id=role_id,
            )

        # 检测 exclude 取消
        if old_mode == 'exclude' and new_mode != 'exclude':
            write_permission_config_audit(
                action='UPDATE',
                object_type='role_dimension_scope',
                object_id=role_id,
                data={'event': 'dim_scope_exclude_unset',
                      'dimension_code': dim_code, 'role_id': role_id},
                parent_object_type='role',
                parent_object_id=role_id,
            )


def _build_ui_hint(dimension_values, scope_mode):
    """[FR-009] 构建 _ui_hint 字段 (向后兼容)

    老客户端忽略此字段; 新客户端据此显示警告。
    """
    is_wildcard = _is_wildcard_values(dimension_values)
    if is_wildcard or scope_mode == 'exclude':
        warning_parts = []
        if is_wildcard:
            warning_parts.append("此维度已配置全维度可见")
        if scope_mode == 'exclude':
            warning_parts.append("此维度已配置排除模式")
        warning_parts.append("老前端可能显示异常")
        return {
            'is_wildcard': is_wildcard,
            'is_exclude': scope_mode == 'exclude',
            'warning': '，'.join(warning_parts),
        }
    return None


def _ds():
    global _data_source
    if _data_source is None:
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'architecture.db'
        )
        _data_source = get_data_source("sqlite", database=db_path)
    return _data_source


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user or not is_admin(user):
            return jsonify({"success": False, "message": "\u9700\u8981\u7ba1\u7406\u5458\u6743\u9650"}), 403
        return f(*args, **kwargs)
    return decorated


@role_dim_bp.route('/<int:role_id>/dimension-scopes', methods=['GET'])
@login_required
def get_dimension_scopes(role_id):
    try:
        ds = _ds()
        cursor = ds.execute(
            "SELECT id, role_id, dimension_code, dimension_values, inherit_children, scope_mode FROM role_dimension_scopes WHERE role_id = ?", [role_id]
        )
        cols = [d[0] for d in (cursor.description or [])]
        rows = []
        for row in cursor.fetchall():
            item = dict(zip(cols, row))
            dimension_code = item.get('dimension_code')
            raw_values = item.get('dimension_values', '[]')
            dimension_values = json.loads(raw_values or '[]')
            scope_mode = item.get('scope_mode') or 'include'

            # [FR-009] 构建 _ui_hint (通配符/exclude 模式时返回警告)
            item['_ui_hint'] = _build_ui_hint(dimension_values, scope_mode)

            # [Spec 08] 通配符 ["*"] 跳过名称查询 (避免 SELECT ... WHERE id IN ('*'))
            is_wildcard = _is_wildcard_values(dimension_values)

            # 查询维度对象的名称
            if dimension_code and dimension_values and not is_wildcard:
                # 维度 code 对应的表名（product -> products, version -> versions 等）
                table_name = f"{dimension_code}s" if not dimension_code.endswith('s') else f"{dimension_code}"

                # 尝试查询名称（先查 name 字段，再查 code 字段）
                try:
                    value_list = ','.join(['?' for _ in dimension_values])
                    query = f"SELECT id, COALESCE(name, code, '') as name, code FROM {table_name} WHERE id IN ({value_list})"
                    name_cursor = ds.execute(query, dimension_values)
                    inner_cols = [d[0] for d in (name_cursor.description or [])]
                    name_map = {}
                    for inner_row in name_cursor.fetchall():
                        row_dict = dict(zip(inner_cols, inner_row))
                        name_map[str(row_dict.get('id'))] = {'id': row_dict.get('id'), 'name': row_dict.get('name', ''), 'code': row_dict.get('code') or ''}

                    # 构建完整对象列表
                    dimension_values_with_names = []
                    for vid in dimension_values:
                        vid_str = str(vid)
                        if vid_str in name_map:
                            dimension_values_with_names.append(name_map[vid_str])
                        else:
                            dimension_values_with_names.append({'id': vid, 'name': str(vid), 'code': ''})

                    item['dimension_values'] = dimension_values_with_names
                except Exception as table_error:
                    # 表不存在或查询失败，回退到简单对象
                    item['dimension_values'] = [{'id': vid, 'name': str(vid), 'code': ''} for vid in dimension_values]
            elif is_wildcard:
                # 通配符: 保留原始 ["*"] 值, 不做名称查询
                item['dimension_values'] = [{'id': '*', 'name': '全维度可见', 'code': '*'}]
            else:
                item['dimension_values'] = []

            rows.append(item)
        return jsonify({'success': True, 'data': rows})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@role_dim_bp.route('/<int:role_id>/dimension-scopes', methods=['POST'])
@admin_required
def save_dimension_scopes(role_id):
    try:
        data = request.get_json()
        # [FIX 2026-06-15] 空 list 是合法操作 (用户清空维度范围), 不应 400
        # 之前用 `if not data` 把空 list 当 400, 导致"移除 dim value 后保存"必失败
        if data is None:
            return jsonify({'success': False, 'message': '请求体为空'}), 400
        if not isinstance(data, list):
            return jsonify({'success': False, 'message': '请求体必须为 list'}), 400

        ds = _ds()
        current_user = get_current_user()

        # [FR-010] 权限限制: 仅 admin 可配置 '*' 通配和 exclude
        # (admin_required 已保证 admin, 此处显式校验以明确意图 + 未来细粒度权限码扩展点)
        try:
            _check_wildcard_exclude_permission(data, current_user)
        except DimScopePermissionError as e:
            return jsonify({'success': False, 'error_code': 'DIM_SCOPE_PERMISSION_DENIED',
                            'message': str(e)}), 403

        # [FR-005] 多角色 Union 防冲突校验 (PM 决策: 选项 C)
        # 同一用户的所有角色不允许同时出现 '*' 通配 + 任何 exclude
        try:
            _check_wildcard_exclude_conflict(ds, role_id, data)
        except DimScopeConflictError as e:
            return jsonify({'success': False, 'error_code': 'DIM_SCOPE_CONFLICT',
                            'message': str(e),
                            'conflict_user_ids': e.conflict_user_ids}), 409

        # [FR-007] 保存前读取旧 scopes (用于审计比较)
        old_scopes = _load_scopes_raw(ds, role_id)

        with ds.transaction():
            ds.execute("DELETE FROM role_dimension_scopes WHERE role_id = ?", [role_id])
            for item in data:
                ds.execute(
                    "INSERT INTO role_dimension_scopes "
                    "(role_id, dimension_code, dimension_values, inherit_children, scope_mode) "
                    "VALUES (?, ?, ?, ?, ?)",
                    [
                        role_id,
                        item.get('dimension_code'),
                        json.dumps(item.get('dimension_values', [])),
                        1 if item.get('inherit_children', True) else 0,
                        item.get('scope_mode', 'include'),
                    ]
                )
        # [FIX 2026-06-12] 角色权限操作审计日志: 关联到角色对象
        # 之前这个 endpoint 没写 audit, 导致用户改管理维度后审计日志 tab 看不到记录
        write_permission_config_audit(
            action='UPDATE',
            object_type='role_dimension_scope',
            object_id=role_id,
            data={'scopes_count': len(data) if isinstance(data, list) else 0,
                  'dimension_codes': [item.get('dimension_code') for item in data] if isinstance(data, list) else []},
            parent_object_type='role',
            parent_object_id=role_id,
        )

        # [FR-007] 审计日志: 检测新旧 scopes 变化, 写入高危操作审计
        # (wildcard 启用/关闭, exclude 设置/取消, high_risk_permission_change)
        try:
            _log_dim_scope_changes(ds, role_id, old_scopes, data, current_user)
        except Exception as audit_err:
            logger.warning(f'[FR-007] _log_dim_scope_changes failed: {audit_err}')

        return jsonify({'success': True, 'message': '\u7ef4\u5ea6\u8303\u56f4\u5df2\u4fdd\u5b58'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@role_dim_bp.route('/<int:role_id>/derived-permissions', methods=['GET'])
@login_required
def get_derived_permissions(role_id):
    try:
        engine = get_dimension_scope_engine(_ds())
        result = engine.auto_sync_all(role_id)
        # [FIX 2026-06-12] 自动推导完成后也写 audit (跟手动 save 一致, 让操作日志完整)
        write_permission_config_audit(
            action='UPDATE',
            object_type='role_dimension_scope',
            object_id=role_id,
            data={'auto_derived': True,
                  'recommended_menus': len(result.get('recommended_menus', [])) if isinstance(result, dict) else 0,
                  'derived_permissions': len(result.get('derived_permissions', [])) if isinstance(result, dict) else 0},
            parent_object_type='role',
            parent_object_id=role_id,
        )
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
