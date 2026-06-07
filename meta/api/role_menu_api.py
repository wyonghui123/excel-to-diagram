# -*- coding: utf-8 -*-
"""
角色菜单权限API

提供角色与菜单权限关联的REST API
"""

from flask import Blueprint, request, jsonify, g
import os
import json

from meta.core.datasource import get_data_source
from meta.core.models import registry
from meta.api.user_api import login_required
from meta.services.auth_middleware import is_admin, get_current_user
from functools import wraps

role_menu_bp = Blueprint('role_menu', __name__, url_prefix='/api/v1/roles')

_data_source = None


def _get_data_source():
    global _data_source
    if _data_source is None:
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
        _data_source = get_data_source("sqlite", database=db_path)
    return _data_source


def _get_permission_label(perm_code):
    """从MetaRegistry动态获取权限标签（零硬编码）"""
    if perm_code == '*':
        return '\u8d85\u7ea7\u6743\u9650'
    parts = perm_code.split(':')
    if len(parts) != 2:
        return perm_code
    resource_type, suffix = parts
    meta_obj = registry.get(resource_type)
    if meta_obj:
        return meta_obj.get_permission_label(suffix)
    return perm_code


def _safe_parse_json_list(raw):
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            val = json.loads(raw)
            return val if isinstance(val, list) else []
        except Exception:
            return []
    return []


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user or not is_admin(user):
            return jsonify({"success": False, "message": "需要管理员权限"}), 403
        return f(*args, **kwargs)
    return decorated


@role_menu_bp.route('/<int:role_id>/menu-permissions', methods=['GET'])
@login_required
def get_role_menu_permissions(role_id):
    """获取角色的菜单权限配置"""
    try:
        ds = _get_data_source()
        
        cursor = ds.execute(
            "SELECT * FROM menus WHERE is_active = 1 AND show_in_sidebar = 1 "
            "AND menu_code != 'dashboard' "
            "AND menu_code NOT IN ("
            "  SELECT DISTINCT parent_menu FROM menus "
            "  WHERE parent_menu IS NOT NULL AND parent_menu != '' "
            "    AND is_active = 1 AND show_in_sidebar = 1"
            ") "
            "AND menu_path IS NOT NULL AND menu_path != '' "
            "AND (parent_menu IS NULL OR parent_menu = '' "
            "     OR parent_menu NOT IN ("
            "       SELECT menu_code FROM menus "
            "       WHERE page_type = 'multi_object_hub' AND is_active = 1"
            "     )"
            ") "
            "ORDER BY sort_order"
        )
        columns = [desc[0] for desc in cursor.description]
        all_menus = [dict(zip(columns, row)) for row in cursor.fetchall()]

        cursor = ds.execute(
            "SELECT menu_code FROM role_menu_permissions WHERE role_id = ?",
            [role_id]
        )
        assigned_menus = set(row[0] for row in cursor.fetchall())
        
        result = []
        for menu in all_menus:
            menu['assigned'] = menu['menu_code'] in assigned_menus
            if menu.get('required_permissions'):
                try:
                    menu['required_permissions'] = json.loads(menu['required_permissions'])
                except:
                    pass
            if menu.get('data_permission_hint'):
                try:
                    menu['data_permission_hint'] = json.loads(menu['data_permission_hint'])
                except:
                    pass
            result.append(menu)
        
        return jsonify({
            'success': True,
            'data': result
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@role_menu_bp.route('/<int:role_id>/unified-permissions', methods=['GET'])
@login_required
def get_role_unified_permissions(role_id):
    """获取角色统一权限视图 (SAP PFCG 风格)
    
    返回菜单-功能权限-数据权限三层联动视图：
    - 菜单是入口层（Entry）
    - required_permissions 是能力层（Capability），自动关联
    - 数据权限是约束层（Scope），可选配置
    
    参考 SAP SU24 的设计：选 Tcode 自动带入 Auth Object

    [单一事实源] 主数据源为 menus 表，与 LandingPage/侧边栏菜单一致
    """
    try:
        ds = _get_data_source()
        
        cursor = ds.execute(
            "SELECT * FROM menus WHERE is_active = 1 AND show_in_sidebar = 1 "
            "AND menu_code != 'dashboard' "
            "AND menu_code NOT IN ("
            "  SELECT DISTINCT parent_menu FROM menus "
            "  WHERE parent_menu IS NOT NULL AND parent_menu != '' "
            "    AND is_active = 1 AND show_in_sidebar = 1"
            ") "
            "AND menu_path IS NOT NULL AND menu_path != '' "
            "AND (parent_menu IS NULL OR parent_menu = '' "
            "     OR parent_menu NOT IN ("
            "       SELECT menu_code FROM menus "
            "       WHERE page_type = 'multi_object_hub' AND is_active = 1"
            "     )"
            ") "
            "ORDER BY sort_order"
        )
        columns = [desc[0] for desc in cursor.description]
        all_menus = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        cursor = ds.execute(
            "SELECT menu_code FROM role_menu_permissions WHERE role_id = ?", [role_id]
        )
        assigned_menus = set(row[0] for row in cursor.fetchall())
        
        cursor = ds.execute(
            "SELECT resource_type, resource_id, permission_level "
            "FROM role_data_permissions WHERE role_id = ?",
            [role_id]
        )
        data_perms = {}
        for row in cursor.fetchall():
            rt, rid, pl = row
            if rt not in data_perms:
                data_perms[rt] = []
            data_perms[rt].append({'resource_id': rid, 'level': pl})
        
        cursor = ds.execute(
            """SELECT p.code, p.name, p.resource_type, p.action 
               FROM permissions p
               JOIN role_permissions rp ON p.id = rp.permission_id
               WHERE rp.role_id = ?""",
            [role_id]
        )
        role_function_perms = set()
        role_function_perm_details = {}
        has_super_permission = False
        for row in cursor.fetchall():
            code, name, resource_type, action = row
            role_function_perms.add(code)
            if code == '*':
                has_super_permission = True
            role_function_perm_details[code] = {
                'code': code, 'name': name,
                'resource_type': resource_type, 'action': action
            }
        
        def _is_perm_granted(perm_code):
            if has_super_permission:
                return True
            return perm_code in role_function_perms
        
        result = []
        for menu in all_menus:
            code = menu['menu_code']
            is_assigned = code in assigned_menus
            
            bo_bindings = _safe_parse_json_list(menu.get('bo_bindings'))
            
            req_perms_raw = menu.get('required_permissions') or '[]'
            try:
                req_perms = json.loads(req_perms_raw) if isinstance(req_perms_raw, str) else req_perms_raw
            except:
                req_perms = []
            
            req_perms_display = []
            for p in req_perms:
                is_granted = _is_perm_granted(p)
                req_perms_display.append({
                    'code': p,
                    'label': _get_permission_label(p),
                    'granted': is_granted,
                    'source': 'auto' if is_assigned else 'manual',
                })
            
            hint_raw = menu.get('data_permission_hint') or '{}'
            try:
                hint = json.loads(hint_raw) if isinstance(hint_raw, str) else hint_raw
            except:
                hint = {}
            
            related_data_perms = []
            hint_resource_types = hint.get('resource_types') or []
            
            if hint_resource_types:
                for rt in hint_resource_types:
                    perms_for_type = data_perms.get(rt, [])
                    if perms_for_type:
                        related_data_perms.append({
                            'resource_type': rt,
                            'permissions': perms_for_type,
                        })
            
            has_data_scope = len(related_data_perms) > 0

            result.append({
                'menu_code': code,
                'display_name': menu.get('menu_name', code),
                'menu_path': menu.get('menu_path', ''),
                'icon': menu.get('icon', ''),
                'sort_order': menu.get('sort_order', 0),
                'parent_menu': menu.get('parent_menu', ''),
                'page_type': menu.get('page_type', 'object_list'),
                'primary_object_type': menu.get('primary_object_type', ''),
                'object_types': _safe_parse_json_list(menu.get('object_types')),
                'bo_bindings': bo_bindings,
                'auto_generated': menu.get('auto_generated', False),
                'color': menu.get('color', ''),
                'description': menu.get('description', ''),
                
                'assigned': is_assigned,
                
                'required_permissions': req_perms,
                'required_permissions_display': req_perms_display,
                'required_any': bool(menu.get('required_any_permission')),
                
                'data_permission_hint': hint,
                'has_data_scope': has_data_scope,
                'data_scope': related_data_perms,
            })
        
        all_resource_types_with_data = list(data_perms.keys())
        
        return jsonify({
            'success': True,
            'data': {
                'role_id': role_id,
                'menus': result,
                'role_function_permissions': list(role_function_perms),
                'role_function_permission_details': role_function_perm_details,
                'summary': {
                    'total_menus': len(all_menus),
                    'assigned_menus': len(assigned_menus),
                    'total_data_scopes': sum(len(v) for v in data_perms.values()),
                    'data_resource_types': all_resource_types_with_data,
                    'total_function_permissions': len(role_function_perms),
                }
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@role_menu_bp.route('/<int:role_id>/menu-permissions', methods=['PUT'])
@admin_required
def update_role_menu_permissions(role_id):
    """更新角色的菜单权限配置，并自动同步关联的功能权限
    
    SAP PFCG 风格：选中菜单时自动授予所需功能权限
    
    新增功能：
    - 记录权限来源（source: auto_menu）
    - 记录来源菜单编码（source_menu_code）
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': '请求体不能为空'
            }), 400
        
        menu_codes = data.get('menu_codes', [])
        
        ds = _get_data_source()
        
        synced_permissions = []
        
        with ds.transaction():
            ds.execute(
                "DELETE FROM role_menu_permissions WHERE role_id = ?",
                [role_id]
            )
            
            for menu_code in menu_codes:
                ds.execute(
                    "INSERT INTO role_menu_permissions (role_id, menu_code) VALUES (?, ?)",
                    [role_id, menu_code]
                )
            
            cursor = ds.execute(
                "SELECT menu_code, required_permissions FROM menus WHERE is_active = 1 AND menu_code IN (%s)"
                % ','.join(['?' for _ in menu_codes]),
                menu_codes
            )
            
            menu_perm_map = {}
            for row in cursor.fetchall():
                mc = row[0] if isinstance(row, tuple) else row.get('menu_code')
                raw = row[1] if isinstance(row, tuple) else row.get('required_permissions')
                raw = raw or '[]'
                try:
                    perms = json.loads(raw) if isinstance(raw, str) else raw
                    menu_perm_map[mc] = perms
                except:
                    menu_perm_map[mc] = []
            
            auto_perm_codes = set()
            for mc, perms in menu_perm_map.items():
                auto_perm_codes.update(perms)
            
            if auto_perm_codes:
                placeholders = ','.join(['?' for _ in auto_perm_codes])
                cursor = ds.execute(
                    f"SELECT id, code FROM permissions WHERE code IN ({placeholders})",
                    list(auto_perm_codes)
                )
                perm_id_map = {}
                for row in cursor.fetchall():
                    code = row[1] if isinstance(row, tuple) else row.get('code')
                    pid = row[0] if isinstance(row, tuple) else row.get('id')
                    perm_id_map[code] = pid
                
                for mc, perms in menu_perm_map.items():
                    for code in perms:
                        pid = perm_id_map.get(code)
                        if pid:
                            try:
                                ds.execute(
                                    """INSERT OR IGNORE INTO role_permissions 
                                       (role_id, permission_id, source, source_menu_code, granted_at) 
                                       VALUES (?, ?, 'auto_menu', ?, CURRENT_TIMESTAMP)""",
                                    [role_id, pid, mc]
                                )
                                synced_permissions.append(code)
                            except Exception as e:
                                pass
        
        return jsonify({
            'success': True,
            'message': f'菜单权限配置已保存，已同步 {len(set(synced_permissions))} 项功能权限',
            'synced_permissions': list(set(synced_permissions)),
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
