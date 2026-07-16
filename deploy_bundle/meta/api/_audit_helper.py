# -*- coding: utf-8 -*-
"""
角色/权限配置审计日志统一 helper

[FIX 2026-06-11] 角色下权限配置编辑 (菜单/功能/数据权限) 之前没写 audit_logs,
导致 sysadmin 系统管理-审计日志页看不到操作记录. 本模块提供统一 helper:
- _audit_user_name(): 统一 combined 'display_name (username)' 格式
- write_permission_config_audit(): 简化调用方, 内部用 AuditLogger.log_create/log_update

[FIX 2026-06-12] 过滤 computed/derived 字段, 解析 ID→display_name:
- 不再传 count/*_count 给 log_create (避免每条 count 都被记为独立 field update)
- 解析 permission_ids → permission_names, menu_codes → menu_names

跟 bo_api._set_user_context + action_executor._write_audit_log_v2 保持格式一致.
"""
import logging
import os
from typing import Any, Dict, List, Optional

from flask import g, request

logger = logging.getLogger(__name__)

# 计算/派生字段 - 不会作为独立 field update 写入 audit_logs
# 跟 AuditLogger 内部 hardcoded skip list (updated_at/created_by 等) 类似,
# 但本模块的 skip list 是 caller 侧过滤, 避免在 audit log 里出现 1 行 + N 个 count 行的噪音
_DERIVED_FIELDS = frozenset({
    'count', 'menu_count', 'permission_count', 'synced_count',
    'item_count', 'rule_count', 'field_count', 'total_count',
})


def _audit_user_name() -> str:
    """统一 combined 'display_name (username)' 格式 (与 bo_api._set_user_context 一致)

    Returns:
        e.g. "V3.17 Test (admin)" 或 "admin" (只有 username 时) 或 "" (无 user)
    """
    cu = getattr(g, 'current_user', None) or {}
    _display = cu.get('display_name') or ''
    _username = cu.get('username') or ''
    # [FIX 2026-06-20 P1 v4] 修复残留的 "display (username)" 拼接格式
    return _display or _username or ''


def _audit_user_id() -> Any:
    cu = getattr(g, 'current_user', None) or {}
    return cu.get('user_id') or cu.get('id')


def _strip_derived(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """[FIX 2026-06-12] 过滤掉 count/*_count 等计算字段, 避免噪音行"""
    if not data:
        return {}
    return {k: v for k, v in data.items() if k not in _DERIVED_FIELDS}


def _resolve_permission_names(perm_ids: List[Any]) -> List[str]:
    """[FIX 2026-06-12] permission_id -> permission.code (技术字段 ID -> 业务字段 code)
    用 permission.code 作为"业务名", 因为 code 才是用户能看懂的 (e.g. 'user:read')
    """
    if not perm_ids:
        return []
    try:
        from meta.core.datasource import get_data_source
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'architecture.db'
        )
        ds = get_data_source('sqlite', database=db_path)
        placeholders = ','.join('?' * len(perm_ids))
        cursor = ds.execute(
            f"SELECT id, code, name FROM permissions WHERE id IN ({placeholders})",
            list(perm_ids)
        )
        id_to_name = {row[0]: (row[1] or row[2] or str(row[0])) for row in cursor.fetchall()}
        return [id_to_name.get(int(pid), f"#{pid}") for pid in perm_ids]
    except Exception as e:
        logger.warning(f"[AuditHelper] resolve_permission_names failed: {e}")
        return [str(pid) for pid in perm_ids]


def _resolve_menu_names(menu_codes: List[str]) -> Dict[str, str]:
    """[FIX 2026-06-12] menu_code -> menu.menu_name (code 是技术字段, menu_name 才是给用户看的)
    注: menus 表用 menu_code/menu_name 列名 (跟 permissions.code/permissions.name 不一致)
    Returns dict: {code: name, ...}
    """
    if not menu_codes:
        return {}
    try:
        from meta.core.datasource import get_data_source
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'architecture.db'
        )
        ds = get_data_source('sqlite', database=db_path)
        placeholders = ','.join('?' * len(menu_codes))
        # [FIX 2026-06-12] 修正: menus 表列名是 menu_code / menu_name (不是 code/name)
        cursor = ds.execute(
            f"SELECT menu_code, menu_name FROM menus WHERE menu_code IN ({placeholders})",
            list(menu_codes)
        )
        return {row[0]: (row[1] or row[0]) for row in cursor.fetchall()}
    except Exception as e:
        logger.warning(f"[AuditHelper] resolve_menu_names failed: {e}")
        return {c: c for c in menu_codes}


def _enrich_data(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """[FIX 2026-06-12] 在写 audit 前 enrich data:
    1. 去掉 count/*_count 等派生字段
    2. 解析 permission_ids → permission_names
    3. 解析 menu_codes → menu_names
    """
    data = _strip_derived(data)
    if not data:
        return {}

    # permission_ids (list of int) → permission_names (list of str)
    perm_ids = data.get('permission_ids')
    if isinstance(perm_ids, list) and perm_ids and isinstance(perm_ids[0], (int, str)):
        try:
            int_ids = [int(p) for p in perm_ids if str(p).isdigit()]
            names = _resolve_permission_names(int_ids)
            if names:
                data['permission_names'] = names
        except Exception:
            pass

    # menu_codes (list of str) → menu_names (dict {code: name})
    menu_codes = data.get('menu_codes')
    if isinstance(menu_codes, list) and menu_codes:
        names_map = _resolve_menu_names(menu_codes)
        if names_map:
            # 用 list 而不是 dict, 跟 permission_names 风格一致
            data['menu_names'] = [names_map.get(c, c) for c in menu_codes]

    return data


def write_permission_config_audit(
    action: str,
    object_type: str,
    object_id: Any,
    data: Optional[Dict[str, Any]] = None,
    old_data: Optional[Dict[str, Any]] = None,
    audit_logger=None,
    parent_object_type: Optional[str] = None,
    parent_object_id: Optional[Any] = None,
) -> bool:
    """写角色/权限配置审计日志 (CREATE/UPDATE/DELETE)

    [FIX 2026-06-12] 自动 _enrich_data: 过滤派生字段, 解析 ID→display_name

    [FIX 2026-06-12] 支持 parent_object_type/parent_object_id, 让 RoleDetailDrawer
    通过 "parent_object_type='role' AND parent_object_id=2" 过滤, 把角色相关的
    5 种 object_type (role_permissions/role_data_permission/role_v2_menu_permissions/
    role_menu/permission_rule) 全部归集到角色详情页"操作日志" tab.

    Args:
        action: 'CREATE' / 'UPDATE' / 'DELETE'
        object_type: e.g. 'role_permissions', 'role_menu', 'role_data_permission'
        object_id: 角色ID 或 规则ID (str/int 都行)
        data: 新数据
        old_data: 旧数据 (UPDATE/DELETE 用)
        audit_logger: 可选, 传入 AuditLogger 实例; 不传则自动 new
        parent_object_type: 父对象 type, e.g. 'role' (让 audit_log 可按父对象查)
        parent_object_id: 父对象 id, e.g. role_id=2

    Returns:
        True if written, False on error
    """
    try:
        from meta.core.action_executor import AuditLogger
        from meta.core.datasource import get_data_source

        if audit_logger is None:
            db_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'architecture.db'
            )
            audit_logger = AuditLogger(get_data_source('sqlite', database=db_path))

        user_id = _audit_user_id()
        user_name = _audit_user_name()
        ip = request.remote_addr if request else None

        # Enrich 双方: 新数据 (new_data) 和旧数据 (old_data)
        enriched_data = _enrich_data(data)
        enriched_old = _enrich_data(old_data) if old_data else None

        if action == 'CREATE':
            return audit_logger.log_create(
                object_type=object_type,
                object_id=str(object_id) if object_id else '',
                data=enriched_data,
                user_id=user_id,
                user_name=user_name,
                ip_address=ip,
                parent_object_type=parent_object_type,
                parent_object_id=parent_object_id,
            )
        elif action == 'UPDATE':
            if not enriched_old:
                # 没有旧数据就当 CREATE (兼容调用方)
                return audit_logger.log_create(
                    object_type=object_type,
                    object_id=str(object_id) if object_id else '',
                    data=enriched_data,
                    user_id=user_id,
                    user_name=user_name,
                    ip_address=ip,
                    parent_object_type=parent_object_type,
                    parent_object_id=parent_object_id,
                )
            return audit_logger.log_update(
                object_type=object_type,
                object_id=str(object_id) if object_id else '',
                old_data=enriched_old,
                new_data=enriched_data,
                user_id=user_id,
                user_name=user_name,
                ip_address=ip,
                parent_object_type=parent_object_type,
                parent_object_id=parent_object_id,
            )
        elif action == 'DELETE':
            return audit_logger.log_delete(
                object_type=object_type,
                object_id=str(object_id) if object_id else '',
                data=enriched_data or enriched_old or {},
                user_id=user_id,
                user_name=user_name,
                ip_address=ip,
                parent_object_type=parent_object_type,
                parent_object_id=parent_object_id,
            )
        else:
            logger.warning(f"[AuditHelper] Unknown action: {action}")
            return False
    except Exception as e:
        logger.warning(f"[AuditHelper] Failed to write {action} {object_type}/{object_id}: {e}")
        return False
