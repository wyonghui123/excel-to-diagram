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
from meta.api._audit_helper import write_permission_config_audit
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


# [FIX v1.0.2] 权限代码快速存在性检查 (缓存)
_permission_exists_cache = {}

def _permission_exists_in_db(perm_code: str) -> bool:
    """检查 permissions 表中是否有该 code 的权限 (用于 bo_bindings 派生校验)"""
    if perm_code in _permission_exists_cache:
        return _permission_exists_cache[perm_code]
    try:
        ds = _get_data_source()
        cursor = ds.execute("SELECT 1 FROM permissions WHERE code = ? LIMIT 1", [perm_code])
        exists = cursor.fetchone() is not None
        _permission_exists_cache[perm_code] = exists
        return exists
    except Exception:
        return False




# 动作分组常量 (与 bo_api.py ACTION_GROUPS 保持一致)
_ACTION_GROUPS_DEF = {
    'view':   {'label': '查看', 'actions': ['read', 'list']},
    'edit':   {'label': '编辑', 'actions': ['read', 'list', 'create', 'update']},
    'manage': {'label': '管理', 'actions': ['read', 'list', 'create', 'update', 'delete']},
}

# 独立动作列表 (与 bo_api.py STANDALONE_ACTIONS 保持一致)
_STANDALONE_ACTIONS_DEF = ['export', 'import', 'assign', 'unassign',
                          'associate', 'dissociate', 'grant', 'revoke']

# 动作标签映射
_ACTION_LABELS_DEF = {
    'read': '查看', 'create': '创建', 'update': '编辑',
    'delete': '删除', 'list': '列表', 'manage': '管理',
    'export': '导出', 'import': '导入', 'assign': '分配',
    'unassign': '取消分配', 'associate': '关联', 'dissociate': '取消关联',
    'grant': '授权', 'revoke': '撤销',
}


def _derive_bo_permission_groups(bo_bindings, req_perms_display, is_assigned):
    """
    从 bo_bindings + required_permissions 推导 bo_permission_groups

    Args:
        bo_bindings: list of {bo_id, include_actions, role}
            - 从 menus.bo_bindings JSON 字段解析
        req_perms_display: list of {code, label, granted, source}
            - 已有 granted 状态 (基于角色权限计算)
        is_assigned: bool - 菜单是否分配给角色

    Returns:
        list of {bo_id, bo_name, groups: {view, edit, manage}, standalone: [...]}
        格式与 MenuPermissionMatrix 前端期望一致

    [FIX v1.0.2] 当 required_permissions 与 bo_bindings 失同步时 (例: product-management
    之前 required_permissions 只有 product, bo_bindings 却声明了 version),
    此函数从 bo_bindings.include_actions 补全 actions_map, 让 version 也能出现在 UI。
    """
    if not bo_bindings:
        return []

    # 1. 收集 resource_perms: {bo_id: {action: {granted, source}}}
    #    主要数据源: required_permissions
    resource_perms = {}
    for p in (req_perms_display or []):
        code = p.get('code', '')
        parts = code.split(':')
        if len(parts) != 2:
            continue
        bo_id, action = parts[0], parts[1]
        if bo_id not in resource_perms:
            resource_perms[bo_id] = {}
        resource_perms[bo_id][action] = {
            'granted': p.get('granted', False),
            'source': p.get('source', 'auto' if is_assigned else 'manual'),
        }

    # 1.1 [FIX v1.0.2] 从 bo_bindings 补全 actions_map
    #   当 bo_bindings 声明某 bo_id 的 include_actions, 但 required_permissions 没配,
    #   默认 granted=False, source='unbound' (UI 可显示警告标记)
    for binding in bo_bindings:
        bo_id = binding.get('bo_id')
        include_actions = binding.get('include_actions', [])
        if not bo_id:
            continue
        if bo_id not in resource_perms:
            resource_perms[bo_id] = {}
        for action in include_actions:
            # v1.0.1: list 已合并到 read, 不需要单独存
            if action == 'list':
                continue
            if action not in resource_perms[bo_id]:
                resource_perms[bo_id][action] = {
                    'granted': False,
                    'source': 'unbound',  # bo_bindings 声明但 required_permissions 未配
                }

    # 2. 对每个 bo_binding 生成 bo_permission_group
    result = []
    for binding in bo_bindings:
        bo_id = binding.get('bo_id')
        if not bo_id:
            continue
        actions_map = resource_perms.get(bo_id, {})

        # 2.1 推导 ACTION_GROUPS (view/edit/manage)
        groups = {}
        for group_key, group_def in _ACTION_GROUPS_DEF.items():
            group_actions = group_def['actions']
            available_actions = [a for a in group_actions if a in actions_map]
            if not available_actions:
                continue  # 该 BO 没有此分组的动作

            # 分组 granted = 所有可用动作都 granted
            group_granted = all(actions_map[a]['granted'] for a in available_actions)

            # 分组 source 推导
            sources = set(actions_map[a]['source'] for a in available_actions)
            if 'exclude' in sources:
                group_source = 'exclude'
            elif 'include' in sources:
                group_source = 'include'
            elif 'auto' in sources:
                group_source = 'auto'
            else:
                group_source = ''

            groups[group_key] = {
                'granted': group_granted,
                'source': group_source,
            }

        # 2.2 推导 STANDALONE_ACTIONS
        standalone = []
        for action_key in _STANDALONE_ACTIONS_DEF:
            if action_key in actions_map:
                standalone.append({
                    'action': action_key,
                    'label': _ACTION_LABELS_DEF.get(action_key, action_key),
                    'granted': actions_map[action_key]['granted'],
                    'source': actions_map[action_key]['source'],
                })

        result.append({
            'bo_id': bo_id,
            'bo_name': bo_id.replace('_', ' ').title(),
            'groups': groups,
            'standalone': standalone,
        })

    return result


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
        
        # [FIX 2026-06-08 v2] 统一BO模型：菜单 = intent = bo + action
        # 权限配置页只展示 sidebar intent 菜单（与侧边栏/菜单API一致）
        # show_in_sidebar=1 自然排除所有独立 *-list CRUD 页面（show_in_sidebar=0）
        # 再排除 system（纯容器节点，无 required_permissions）
        cursor = ds.execute(
            "SELECT * FROM menus WHERE is_active = 1 "
            "AND show_in_sidebar = 1 "
            "AND menu_code != 'dashboard' "
            "AND menu_code != 'system' "
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
            if perm_code in role_function_perms:
                return True
            # [FIX 2026-06-08] 兼容 expanded 格式: scheduled_task:create -> scheduled_task:scheduled_task_create
            parts = perm_code.split(':')
            if len(parts) == 2:
                expanded = f"{parts[0]}:{parts[0]}_{parts[1]}"
                if expanded in role_function_perms:
                    return True
            return False
        
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

            # [FIX v1.0.2] 从 bo_bindings 派生额外的 crud 明细权限
            #   当 bo_bindings 声明某 bo_id 的 include_actions, 但 required_permissions 没配,
            #   自动追加到 req_perms_display (granted=False, source='unbound'),
            #   让前端 "详细权限" 列表能显示 version 等子 BO 的 crud 明细
            if bo_bindings:
                existing_codes = {p['code'] for p in req_perms_display}
                for binding in bo_bindings:
                    bind_bo_id = binding.get('bo_id')
                    include_actions = binding.get('include_actions', []) or []
                    if not bind_bo_id:
                        continue
                    for action in include_actions:
                        if action == 'list':
                            continue  # v1.0.1: list 已合并到 read
                        # code 格式: 'bo_id:action' (例 'version:create')
                        derived_code = f'{bind_bo_id}:{action}'
                        if derived_code in existing_codes:
                            continue  # 已有, 跳过
                        # 检查该 permission 是否真实存在 (避免脏数据)
                        if _is_perm_granted(derived_code) or _permission_exists_in_db(derived_code):
                            req_perms_display.append({
                                'code': derived_code,
                                'label': _get_permission_label(derived_code),
                                'granted': _is_perm_granted(derived_code),
                                'source': 'unbound',  # 标记: 从 bo_bindings 派生
                            })
                            existing_codes.add(derived_code)
            
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
                
                'required_permissions': req_perms_display,
                'required_permissions_raw': req_perms,
                'required_any': bool(menu.get('required_any_permission')),

                # [FIX-2026-06-08] 推导 bo_permission_groups (子区域 1: 功能权限分组)
                #   数据源: bo_bindings (bo_id + include_actions) + required_permissions
                #   推导 ACTION_GROUPS (view/edit/manage) + standalone
                #   解决 "菜单直接跟着 bo action" 的 UI bug:
                #     之前 result 字典没有这个字段, MenuPermissionMatrix 永远 v-if false,
                #     只显示 required_permissions 详细列表
                # [派生: 实现细节]
                #   - resource_perms: {bo_id: {action: {granted, source}}}
                #     从 required_permissions 收集, code 格式 "domain:read"
                #   - ACTION_GROUPS:
                #     view  = [read, list]
                #     edit  = [read, list, create, update]
                #     manage= [read, list, create, update, delete]
                #   - STANDALONE_ACTIONS:
                #     [export, import, assign, unassign,
                #      associate, dissociate, grant, revoke]
                'bo_permission_groups': _derive_bo_permission_groups(
                    bo_bindings, req_perms_display, is_assigned
                ),
                
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
        permissions = data.get('permissions', [])
        
        # [FIX 2026-06-08] 解析显式授予/拒绝的权限
        explicit_granted = set()
        explicit_denied = set()
        for p in permissions:
            code = p.get('code', '') if isinstance(p, dict) else str(p)
            if not code:
                continue
            if p.get('granted') if isinstance(p, dict) else False:
                explicit_granted.add(code)
            else:
                explicit_denied.add(code)
        
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
                # [FIX 2026-06-08] sqlite3.Row 支持索引但不一定有 .get()
                try:
                    mc = row[0] if isinstance(row, tuple) else (row[0] if not hasattr(row, 'get') else row.get('menu_code'))
                    raw = row[1] if isinstance(row, tuple) else (row[1] if not hasattr(row, 'get') else row.get('required_permissions'))
                except (TypeError, IndexError, AttributeError):
                    mc = str(row[0]) if hasattr(row, '__getitem__') else ''
                    raw = str(row[1]) if hasattr(row, '__getitem__') and len(row) > 1 else '[]'
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
                    # [FIX 2026-06-08] sqlite3.Row 支持索引但不一定有 .get()
                    try:
                        code = row[1] if isinstance(row, tuple) else (row[1] if not hasattr(row, 'get') else row.get('code'))
                        pid = row[0] if isinstance(row, tuple) else (row[0] if not hasattr(row, 'get') else row.get('id'))
                    except (TypeError, IndexError, AttributeError):
                        code = str(row[1])
                        pid = int(row[0])
                    perm_id_map[code] = pid

                # [FIX v1.0.2] 补全 explicit_granted/explicit_denied 中不在 menus.required_permissions 里的权限
                #   场景: 维度 scope 派生 (例 version:read) 不在 menus.required_permissions 中,
                #         但用户通过 applyDerived 显式 grant, 需要写入 role_permissions
                #   例: TEST60 点了"自动推导", derived_permissions 含 version:read,
                #       menus.required_permissions 只有 product:create/read/update/delete,
                #       → 旧逻辑会找不到 version:read 的 id, 静默忽略
                #   同样问题: 显式 deny version:read 时, perm_id_map 找不到 id, 不执行 DELETE
                missing_codes = [c for c in (explicit_granted | explicit_denied) if c not in perm_id_map]
                if missing_codes:
                    ph2 = ','.join('?' * len(missing_codes))
                    extra_cur = ds.execute(
                        f"SELECT id, code FROM permissions WHERE code IN ({ph2})",
                        missing_codes
                    )
                    for row in extra_cur.fetchall():
                        try:
                            code = row[1] if isinstance(row, tuple) else (row[1] if not hasattr(row, 'get') else row.get('code'))
                            pid = row[0] if isinstance(row, tuple) else (row[0] if not hasattr(row, 'get') else row.get('id'))
                        except (TypeError, IndexError, AttributeError):
                            code = str(row[1])
                            pid = int(row[0])
                        perm_id_map[code] = pid
                
                # [FIX 2026-06-08] 补充 expanded 格式映射: scheduled_task:create -> scheduled_task:scheduled_task_create
                expanded_codes = set()
                for code in auto_perm_codes:
                    if code not in perm_id_map:
                        parts = code.split(':')
                        if len(parts) == 2:
                            expanded = f"{parts[0]}:{parts[0]}_{parts[1]}"
                            expanded_codes.add(expanded)
                if expanded_codes:
                    e_placeholders = ','.join(['?' for _ in expanded_codes])
                    e_cursor = ds.execute(
                        f"SELECT id, code FROM permissions WHERE code IN ({e_placeholders})",
                        list(expanded_codes)
                    )
                    for row in e_cursor.fetchall():
                        try:
                            ec = row[1] if isinstance(row, tuple) else (row[1] if not hasattr(row, 'get') else row.get('code'))
                            epid = row[0] if isinstance(row, tuple) else (row[0] if not hasattr(row, 'get') else row.get('id'))
                        except (TypeError, IndexError, AttributeError):
                            ec = str(row[1])
                            epid = int(row[0])
                        # 映射回原始 code: scheduled_task:scheduled_task_create -> scheduled_task:create
                        ec_parts = ec.split(':')
                        if len(ec_parts) == 2:
                            ec_action_parts = ec_parts[1].rsplit('_', 1)
                            if len(ec_action_parts) == 2 and ec_action_parts[0] == ec_parts[0]:
                                original_code = f"{ec_parts[0]}:{ec_action_parts[1]}"
                                perm_id_map[original_code] = epid
                
                # [FIX 2026-06-08] 处理显式拒绝的权限：删除 role_permissions 条目
                for code in explicit_denied:
                    pid = perm_id_map.get(code)
                    if not pid:
                        # 尝试 expanded 格式
                        parts = code.split(':')
                        if len(parts) == 2:
                            expanded = f"{parts[0]}:{parts[0]}_{parts[1]}"
                            pid = perm_id_map.get(expanded)
                    if pid:
                        ds.execute(
                            "DELETE FROM role_permissions WHERE role_id = ? AND permission_id = ?",
                            [role_id, pid]
                        )
                
                # [FIX 2026-06-08] 处理显式授予的权限：确保存在
                for code in explicit_granted:
                    pid = perm_id_map.get(code)
                    if not pid:
                        # 尝试 expanded 格式
                        parts = code.split(':')
                        if len(parts) == 2:
                            expanded = f"{parts[0]}:{parts[0]}_{parts[1]}"
                            pid = perm_id_map.get(expanded)
                    if pid:
                        ds.execute(
                            """INSERT OR REPLACE INTO role_permissions 
                               (role_id, permission_id, created_at, granted) 
                               VALUES (?, ?, CURRENT_TIMESTAMP, 1)""",
                            [role_id, pid]
                        )
                        synced_permissions.append(code)
                
                # [FIX 2026-06-08] 自动同步：跳过已被显式拒绝的权限
                for mc, perms in menu_perm_map.items():
                    for code in perms:
                        if code in explicit_denied:
                            continue  # 用户显式拒绝，不自动添加
                        if code in explicit_granted:
                            continue  # 已在上面处理
                        pid = perm_id_map.get(code)
                        if not pid:
                            # 尝试 expanded 格式
                            parts = code.split(':')
                            if len(parts) == 2:
                                expanded = f"{parts[0]}:{parts[0]}_{parts[1]}"
                                pid = perm_id_map.get(expanded)
                        if pid:
                            try:
                                ds.execute(
                                    """INSERT OR IGNORE INTO role_permissions 
                                       (role_id, permission_id, created_at, granted) 
                                       VALUES (?, ?, CURRENT_TIMESTAMP, 1)""",
                                    [role_id, pid]
                                )
                                synced_permissions.append(code)
                            except Exception as e:
                                pass

        # [FIX 2026-06-12] 角色菜单权限 (PFCG) 审计日志: 关联到角色对象
        write_permission_config_audit(
            action='UPDATE',
            object_type='role_menu',
            object_id=role_id,
            data={'menu_codes': menu_codes, 'synced_permissions_count': len(set(synced_permissions))},
            parent_object_type='role',
            parent_object_id=role_id,
        )

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
