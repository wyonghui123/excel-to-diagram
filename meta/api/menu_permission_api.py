# -*- coding: utf-8 -*-
"""
菜单权限API

提供菜单权限检查和管理的REST API
"""

from flask import Blueprint, request, jsonify, g
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meta.core.datasource import get_data_source
from meta.services.menu_permission_service import MenuPermissionService
from meta.api.user_api import login_required
from meta.services.auth_middleware import is_admin
from functools import wraps

def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        from meta.api.user_api import get_current_user
        user = get_current_user()
        if not user or not is_admin(user):
            return jsonify({"success": False, "message": "需要管理员权限"}), 403
        return f(*args, **kwargs)
    return decorated

menu_permission_bp = Blueprint('menu_permission', __name__, url_prefix='/api/v1/menu-permission')

_data_source = None


def _get_data_source():
    global _data_source
    if _data_source is None:
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
        _data_source = get_data_source("sqlite", database=db_path)
    return _data_source


def _get_menu_service():
    ds = _get_data_source()
    return MenuPermissionService(ds)


def _safe_parse_json_list(raw):
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            import json
            val = json.loads(raw)
            return val if isinstance(val, list) else []
        except Exception:
            return []
    return []


def _safe_parse_json_obj(raw):
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            import json
            val = json.loads(raw)
            return val if isinstance(val, dict) else {}
        except Exception:
            return {}
    return {}


@menu_permission_bp.route('/menus', methods=['GET'])
@login_required
def get_accessible_menus():
    """获取当前用户可访问的菜单列表"""
    try:
        user_id = g.current_user['user_id']
        service = _get_menu_service()
        menus = service.get_user_accessible_menus(user_id)
        
        return jsonify({
            'success': True,
            'data': menus
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@menu_permission_bp.route('/menus/all', methods=['GET'])
@admin_required
def get_all_menus():
    """获取所有菜单配置（管理员）"""
    try:
        service = _get_menu_service()
        menus = service.get_all_menu_permissions()
        
        return jsonify({
            'success': True,
            'data': menus
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@menu_permission_bp.route('/menus/<menu_code>', methods=['GET'])
@login_required
def check_menu_visibility(menu_code):
    """检查当前用户是否可以访问指定菜单"""
    try:
        user_id = g.current_user['user_id']
        service = _get_menu_service()
        result = service.check_menu_visibility(user_id, menu_code)
        
        return jsonify({
            'success': True,
            'data': result
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@menu_permission_bp.route('/menus/<menu_code>/consistency', methods=['GET'])
@login_required
def check_menu_consistency(menu_code):
    """检查菜单权限一致性"""
    try:
        user_id = g.current_user['user_id']
        service = _get_menu_service()
        result = service.check_menu_consistency(user_id, menu_code)
        
        return jsonify({
            'success': True,
            'data': result
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@menu_permission_bp.route('/menus/report', methods=['GET'])
@login_required
def get_permission_report():
    """获取当前用户的权限一致性报告"""
    try:
        user_id = g.current_user['user_id']
        service = _get_menu_service()
        report = service.get_user_permission_report(user_id)
        
        return jsonify({
            'success': True,
            'data': report
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@menu_permission_bp.route('/menus', methods=['POST'])
@admin_required
def create_menu_permission():
    """创建菜单权限配置（管理员）"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': '请求体不能为空'
            }), 400
        
        required_fields = ['menu_code', 'menu_name', 'menu_path']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'缺少必填字段: {field}'
                }), 400
        
        service = _get_menu_service()
        menu_id = service.add_menu_permission(data)
        
        if menu_id:
            return jsonify({
                'success': True,
                'data': {'id': menu_id}
            })
        else:
            return jsonify({
                'success': False,
                'error': '创建菜单权限失败'
            }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@menu_permission_bp.route('/menus/<menu_code>', methods=['PUT'])
@admin_required
def update_menu_permission(menu_code):
    """更新菜单权限配置（管理员）"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': '请求体不能为空'
            }), 400
        
        service = _get_menu_service()
        success = service.update_menu_permission(menu_code, data)
        
        if success:
            return jsonify({
                'success': True,
                'message': '更新成功'
            })
        else:
            return jsonify({
                'success': False,
                'error': '更新菜单权限失败或菜单不存在'
            }), 404
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@menu_permission_bp.route('/menus/<menu_code>', methods=['DELETE'])
@admin_required
def delete_menu_permission(menu_code):
    """删除菜单权限配置（管理员）"""
    try:
        service = _get_menu_service()
        success = service.delete_menu_permission(menu_code)
        
        if success:
            return jsonify({
                'success': True,
                'message': '删除成功'
            })
        else:
            return jsonify({
                'success': False,
                'error': '删除菜单权限失败或菜单不存在'
            }), 404
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@menu_permission_bp.route('/visible', methods=['GET'])
@login_required
def get_visible_menu_tree():
    """获取当前用户可见的完整菜单树（含层级结构、icon/color/description）"""
    try:
        import json as _json
        from meta.api.role_menu_api import _get_data_source as _role_ds
        
        user = g.current_user
        user_id = user.get('user_id') or user.get('id')
        ds = _role_ds() if callable(_role_ds) else _get_data_source()
        
        role_rows = ds.execute(
            """SELECT DISTINCT gr.role_id FROM group_roles gr
               JOIN user_group_members ugm ON gr.group_id = ugm.group_id
               WHERE ugm.user_id = ?""", [user_id]
        ).fetchall()
        role_ids = [r[0] for r in role_rows]
        
        user_perms = set()
        if role_ids:
            ph = ','.join('?' * len(role_ids))
            perm_rows = ds.execute(
                f"SELECT p.code FROM role_permissions rp "
                f"JOIN permissions p ON rp.permission_id = p.id "
                f"WHERE rp.role_id IN ({ph})", role_ids
            ).fetchall()
            user_perms = {r[0] for r in perm_rows}
        
        has_super = '*' in user_perms
        
        # [FIX 2026-06-08] 查询用户通过 role_menu_permissions 直接被授予的菜单
        granted_menu_codes = set()
        if role_ids:
            mh = ','.join('?' * len(role_ids))
            menu_grant_rows = ds.execute(
                f"SELECT DISTINCT rmp.menu_code FROM role_menu_permissions rmp "
                f"WHERE rmp.role_id IN ({mh})", role_ids
            ).fetchall()
            granted_menu_codes = {r[0] for r in menu_grant_rows}
        
        menu_rows = ds.execute(
            "SELECT * FROM menus WHERE is_active = 1 AND show_in_sidebar = 1 ORDER BY sort_order"
        ).fetchall()
        menu_cols = [d[0] for d in ds.execute("SELECT * FROM menus WHERE 1=0").description] \
            if menu_rows else []
        if not menu_cols:
            menu_rows = ds.execute(
                "SELECT * FROM menu_permissions WHERE is_active = 1 ORDER BY sort_order"
            ).fetchall()
            if menu_rows:
                menu_cols = [d[0] for d in ds.execute(
                    "SELECT * FROM menu_permissions WHERE 1=0"
                ).description]
        
        flat = []
        for row in menu_rows:
            m = dict(zip(menu_cols, row)) if menu_cols else {
                'menu_code': row[0] if len(row) > 0 else '',
                'menu_name': row[1] if len(row) > 1 else '',
                'menu_path': row[2] if len(row) > 2 else '',
                'parent_menu': row[3] if len(row) > 3 else '',
                'sort_order': row[4] if len(row) > 4 else 0,
            }
            code = m.get('menu_code', '')
            req_raw = m.get('required_permissions')
            if isinstance(req_raw, str):
                try:
                    req_raw = _json.loads(req_raw)
                except Exception:
                    req_raw = []
            required = req_raw if isinstance(req_raw, list) else []
            
            # [FIX 2026-06-08] 检查菜单可见性：超级权限 OR 无权限要求 OR 有权限 OR 通过 role_menu_permissions 直接授予
            visible = has_super or not required or any(p in user_perms for p in required) or (code in granted_menu_codes)
            if not visible:
                continue
            
            flat.append({
                'menu_code': code,
                'menu_name': m.get('menu_name', code),
                'menu_path': m.get('menu_path', ''),
                'icon': m.get('icon', ''),
                'color': m.get('color') or 'warm-orange',
                'description': m.get('description', ''),
                'page_type': m.get('page_type', 'object_list'),
                'primary_object_type': m.get('primary_object_type', ''),
                'object_types': _safe_parse_json_list(m.get('object_types')),
                'bo_bindings': _safe_parse_json_list(m.get('bo_bindings')),
                'required_permissions': required,
                'required_any_permission': m.get('required_any_permission', False),
                'data_permission_hint': _safe_parse_json_obj(m.get('data_permission_hint')),
                'page_config': _safe_parse_json_obj(m.get('page_config')),
                'sort_order': m.get('sort_order', 0),
                'parent_menu': m.get('parent_menu', ''),
                'auto_generated': m.get('auto_generated', False),
            })
        
        visible_codes = {m['menu_code'] for m in flat}
        
        if visible_codes and menu_cols:
            child_rows = ds.execute(
                "SELECT * FROM menus WHERE is_active = 1 AND show_in_sidebar = 0 "
                "AND parent_menu IN (%s) ORDER BY sort_order" % ','.join(['?' for _ in visible_codes]),
                list(visible_codes)
            ).fetchall()
            for row in child_rows:
                m = dict(zip(menu_cols, row))
                code = m.get('menu_code', '')
                flat.append({
                    'menu_code': code,
                    'menu_name': m.get('menu_name', code),
                    'menu_path': m.get('menu_path', ''),
                    'icon': m.get('icon', ''),
                    'color': m.get('color', ''),
                    'description': m.get('description', ''),
                    'page_type': m.get('page_type', 'object_list'),
                    'primary_object_type': m.get('primary_object_type', ''),
                    'object_types': _safe_parse_json_list(m.get('object_types')),
                    'bo_bindings': _safe_parse_json_list(m.get('bo_bindings')),
                    'required_permissions': _safe_parse_json_list(m.get('required_permissions')),
                    'required_any_permission': m.get('required_any_permission', False),
                    'data_permission_hint': _safe_parse_json_obj(m.get('data_permission_hint')),
                    'page_config': _safe_parse_json_obj(m.get('page_config')),
                    'sort_order': m.get('sort_order', 0),
                    'parent_menu': m.get('parent_menu', ''),
                    'auto_generated': m.get('auto_generated', False),
                })
        
        menu_map = {}
        tree = []
        for m in flat:
            m['children'] = []
            menu_map[m['menu_code']] = m
        
        for m in flat:
            parent = m.get('parent_menu')
            if parent and parent in menu_map:
                menu_map[parent]['children'].append(m)
            else:
                if not parent:
                    tree.append(m)
                else:
                    tree.append(m)

        # [FIX 2026-06-14] 后置清理: 空 children 的 custom_page 父菜单 (分组节点/无内容页) 应当隐藏
        #   否则 TEST888 这类没有 system 子菜单权限的用户会看到空的"系统管理"分组
        #   判定条件: page_type='custom_page' + 没有可见 children → 隐藏
        #   保留: 自身有 menu_path 且 page_type 不是 'custom_page' (如 'object_list' / 'multi_object_hub') 仍可点击
        def _prune_empty_groups(nodes):
            keep = []
            for n in nodes:
                if n.get('children'):
                    n['children'] = _prune_empty_groups(n['children'])
                # custom_page + 没有 children → 内容为空, 隐藏
                if n.get('page_type') == 'custom_page' and not n.get('children'):
                    continue
                keep.append(n)
            return keep

        tree = _prune_empty_groups(tree)
        
        # Build leaf_menus: leaf nodes excluding hub children and dashboard
        hub_parent_codes = set()
        parent_codes = set()
        for m in flat:
            if m.get('page_type') == 'multi_object_hub':
                hub_parent_codes.add(m['menu_code'])
            if m.get('children'):
                parent_codes.add(m['menu_code'])

        leaf_menus = []
        for m in flat:
            if not m.get('menu_code') or m['menu_code'] == 'dashboard':
                continue
            if not m.get('menu_path'):
                continue
            # [FIX 2026-06-15 H12] 跳过 group 容器节点 (page_type='custom_page')
            #   之前 v1.0.5 的 parent_codes 判定用 m.get('children'), 但 line 410-418 的
            #   children 填充是 in-place 改 menu_map[parent] 引用, 跟 flat 共享 dict 引用.
            #   多数场景下 parent_codes 能正确判定, 但 group 节点 (如 system) 实际没 children
            #   (因为子菜单是不同 perm scope, line 317 SQL 没把它们的子加到 flat),
            #   导致 system 误进 leaf_menus, 在 landing page 出现"系统管理"分组节点.
            #
            #   改判定: page_type='custom_page' 即视为 group 容器, 不应作为 leaf
            #   (这类菜单通常 menu_path 指向 generic container page 而非真实功能页)
            if m.get('page_type') == 'custom_page':
                continue
            if m['menu_code'] in parent_codes:
                continue
            if m.get('parent_menu') and m['parent_menu'] in hub_parent_codes:
                continue
            leaf_menus.append({
                'menu_code': m['menu_code'],
                'menu_name': m.get('menu_name', ''),
                'menu_path': m.get('menu_path', ''),
                'icon': m.get('icon', ''),
                'color': m.get('color', ''),
                'description': m.get('description', ''),
                'page_type': m.get('page_type', 'object_list'),
                'primary_object_type': m.get('primary_object_type', ''),
                'object_types': m.get('object_types', []),
                'bo_bindings': m.get('bo_bindings', []),
                'sort_order': m.get('sort_order', 0),
                'parent_menu': m.get('parent_menu', ''),
            })

        # Build object_type_route_map: objectType → route
        object_type_route_map = {}
        def _build_ot_map(nodes, parent_path=''):
            for node in nodes:
                path = node.get('menu_path') or parent_path or '/' + node.get('menu_code', '')
                if node.get('primary_object_type'):
                    object_type_route_map[node['primary_object_type']] = path
                if node.get('object_types'):
                    for ot in node['object_types']:
                        object_type_route_map[ot] = path
                if node.get('children'):
                    _build_ot_map(node['children'], path)
        _build_ot_map(tree)

        return jsonify({
            'success': True,
            'menus': tree,
            'leaf_menus': leaf_menus,
            'object_type_route_map': object_type_route_map,
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
