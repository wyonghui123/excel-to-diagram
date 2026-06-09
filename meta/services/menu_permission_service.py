# -*- coding: utf-8 -*-
"""
菜单权限服务

支持：
1. 菜单权限配置管理
2. 用户菜单可见性检查
3. 菜单-功能权限一致性检查
"""

from typing import List, Dict, Any, Optional, Set
import json


class MenuPermissionService:

    def __init__(self, data_source):
        self.ds = data_source

    def _rows_to_dicts(self, cursor) -> List[Dict[str, Any]]:
        rows = cursor.fetchall()
        if not rows:
            return []
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    def get_all_menu_permissions(self) -> List[Dict[str, Any]]:
        """获取所有菜单权限配置"""
        cursor = self.ds.execute(
            "SELECT * FROM menu_permissions WHERE is_active = 1 ORDER BY sort_order"
        )
        menus = self._rows_to_dicts(cursor)
        
        for menu in menus:
            if menu.get('required_permissions'):
                try:
                    menu['required_permissions'] = json.loads(menu['required_permissions'])
                except (json.JSONDecodeError, TypeError):
                    menu['required_permissions'] = []
            else:
                menu['required_permissions'] = []
            
            if menu.get('data_permission_hint'):
                try:
                    menu['data_permission_hint'] = json.loads(menu['data_permission_hint'])
                except (json.JSONDecodeError, TypeError):
                    menu['data_permission_hint'] = None
        
        return menus

    def get_menu_permission_by_code(self, menu_code: str) -> Optional[Dict[str, Any]]:
        """根据菜单编码获取菜单权限配置"""
        cursor = self.ds.execute(
            "SELECT * FROM menu_permissions WHERE menu_code = ?",
            [menu_code]
        )
        rows = self._rows_to_dicts(cursor)
        if not rows:
            return None
        
        menu = rows[0]
        if menu.get('required_permissions'):
            try:
                menu['required_permissions'] = json.loads(menu['required_permissions'])
            except (json.JSONDecodeError, TypeError):
                menu['required_permissions'] = []
        else:
            menu['required_permissions'] = []
        
        if menu.get('data_permission_hint'):
            try:
                menu['data_permission_hint'] = json.loads(menu['data_permission_hint'])
            except (json.JSONDecodeError, TypeError):
                menu['data_permission_hint'] = None
        
        return menu

    def check_menu_visibility(self, user_id: int, menu_code: str) -> Dict[str, Any]:
        """
        检查用户是否能看到某个菜单
        
        返回：
        {
            'visible': bool,
            'reason': str,
            'missing_permissions': List[str]
        }
        """
        result = {
            'visible': False,
            'reason': '',
            'missing_permissions': []
        }
        
        menu = self.get_menu_permission_by_code(menu_code)
        if not menu:
            result['reason'] = f'菜单配置不存在: {menu_code}'
            return result
        
        if not menu.get('is_active'):
            result['reason'] = f'菜单已禁用: {menu_code}'
            return result
        
        required_perms = menu.get('required_permissions', [])

        if not required_perms:
            result['visible'] = True
            result['reason'] = '无需权限检查'
            return result

        # [FIX 2026-06-08] 快速通道：如果用户通过 role_menu_permissions 直接被授予了此菜单
        # 路径：user → user_group_members → group_roles → role_menu_permissions
        # 这符合"admin 在 UI 上给角色勾选菜单"的直觉，无需确保 role_permissions 已同步
        try:
            cursor = self.ds.execute("""
                SELECT 1
                FROM role_menu_permissions rmp
                INNER JOIN group_roles gr ON rmp.role_id = gr.role_id
                INNER JOIN user_group_members ugm ON gr.group_id = ugm.group_id
                WHERE ugm.user_id = ? AND rmp.menu_code = ?
                LIMIT 1
            """, [user_id, menu_code])
            if cursor.fetchone():
                result['visible'] = True
                result['reason'] = '通过角色菜单权限直接授予'
                return result
        except Exception as _e:
            logger.warning(f"[check_menu_visibility] role_menu_permissions 快捷检查失败: {_e}")

        user_perms = self._get_user_permission_codes(user_id)
        
        # 检查是否有超级权限
        if '*' in user_perms:
            result['visible'] = True
            result['reason'] = '拥有超级权限'
            return result
        
        if menu.get('required_any_permission'):
            has_any = any(perm in user_perms for perm in required_perms)
            if has_any:
                result['visible'] = True
                result['reason'] = '满足任一所需权限'
            else:
                result['visible'] = False
                result['reason'] = '缺少所有所需权限'
                result['missing_permissions'] = required_perms
        else:
            has_all = all(perm in user_perms for perm in required_perms)
            if has_all:
                result['visible'] = True
                result['reason'] = '满足所有所需权限'
            else:
                result['visible'] = False
                result['reason'] = '缺少部分所需权限'
                result['missing_permissions'] = [p for p in required_perms if p not in user_perms]
        
        return result

    def get_user_accessible_menus(self, user_id: int) -> List[Dict[str, Any]]:
        """
        获取用户可访问的菜单列表
        
        返回菜单列表，包含可见性信息
        """
        all_menus = self.get_all_menu_permissions()
        accessible_menus = []
        
        for menu in all_menus:
            check_result = self.check_menu_visibility(user_id, menu['menu_code'])
            if check_result['visible']:
                menu['visibility_reason'] = check_result['reason']
                accessible_menus.append(menu)
        
        return accessible_menus

    def check_menu_consistency(self, user_id: int, menu_code: str) -> Dict[str, Any]:
        """
        检查用户菜单权限的一致性
        
        返回：
        {
            'has_menu_permission': bool,
            'has_function_permission': bool,
            'has_data_permission': bool,
            'warnings': List[str],
            'suggestions': List[str]
        }
        """
        result = {
            'has_menu_permission': False,
            'has_function_permission': False,
            'has_data_permission': False,
            'warnings': [],
            'suggestions': []
        }
        
        menu = self.get_menu_permission_by_code(menu_code)
        if not menu:
            result['warnings'].append(f'菜单配置不存在: {menu_code}')
            return result
        
        visibility_check = self.check_menu_visibility(user_id, menu_code)
        result['has_menu_permission'] = visibility_check['visible']
        result['has_function_permission'] = visibility_check['visible']
        
        if not visibility_check['visible']:
            result['warnings'].append(f"菜单权限不足: {visibility_check['reason']}")
            if visibility_check['missing_permissions']:
                result['suggestions'].append(f"建议分配权限: {visibility_check['missing_permissions']}")
            return result
        
        data_hint = menu.get('data_permission_hint')
        if data_hint:
            resource_types = data_hint.get('resource_types', [])
            has_data = self._check_user_has_data_permission(user_id, resource_types)
            result['has_data_permission'] = has_data
            
            if not has_data:
                message = data_hint.get('message', '缺少数据权限')
                result['warnings'].append(message)
                result['suggestions'].append(f"建议分配以下资源类型的数据权限: {resource_types}")
        else:
            result['has_data_permission'] = True
        
        return result

    def get_user_permission_report(self, user_id: int) -> Dict[str, Any]:
        """
        生成用户权限一致性报告
        """
        report = {
            'user_id': user_id,
            'menus': [],
            'inconsistencies': [],
            'recommendations': []
        }
        
        all_menus = self.get_all_menu_permissions()
        
        for menu in all_menus:
            check_result = self.check_menu_consistency(user_id, menu['menu_code'])
            report['menus'].append({
                'menu_code': menu['menu_code'],
                'menu_name': menu['menu_name'],
                **check_result
            })
            
            if check_result['warnings']:
                report['inconsistencies'].append({
                    'menu': menu['menu_name'],
                    'warnings': check_result['warnings'],
                    'suggestions': check_result['suggestions']
                })
        
        return report

    def _get_user_permission_codes(self, user_id: int) -> Set[str]:
        """获取用户的所有功能权限编码"""
        result = set()

        # [FIX 2026-06-08] 路径1：用户-角色直连（user_roles）
        cursor = self.ds.execute("""
            SELECT DISTINCT p.code
            FROM permissions p
            INNER JOIN role_permissions rp ON p.id = rp.permission_id
            INNER JOIN user_roles ur ON rp.role_id = ur.role_id
            WHERE ur.user_id = ?
        """, [user_id])

        for row in cursor.fetchall():
            result.add(row[0])

        # [FIX 2026-06-08] 路径2：用户-用户组-角色（user_group_members → group_roles）
        # 这是当前系统的实际授权路径（assign_role 通过 _get_or_create_personal_group）
        cursor = self.ds.execute("""
            SELECT DISTINCT p.code
            FROM permissions p
            INNER JOIN role_permissions rp ON p.id = rp.permission_id
            INNER JOIN group_roles gr ON rp.role_id = gr.role_id
            INNER JOIN user_group_members ugm ON gr.group_id = ugm.group_id
            WHERE ugm.user_id = ?
        """, [user_id])

        for row in cursor.fetchall():
            result.add(row[0])

        return result

    def _check_user_has_data_permission(self, user_id: int, resource_types: List[str]) -> bool:
        """检查用户是否有指定资源类型的数据权限"""
        if not resource_types:
            return True
        
        for rt in resource_types:
            cursor = self.ds.execute("""
                SELECT COUNT(*) FROM (
                    SELECT 1 FROM data_permissions 
                    WHERE user_id = ? AND resource_type = ?
                    UNION
                    SELECT 1 FROM role_data_permissions rdp
                    INNER JOIN user_roles ur ON rdp.role_id = ur.role_id
                    WHERE ur.user_id = ? AND rdp.resource_type = ?
                    UNION
                    SELECT 1 FROM group_data_permissions gdp
                    INNER JOIN user_group_members ugm ON gdp.group_id = ugm.group_id
                    WHERE ugm.user_id = ? AND gdp.resource_type = ?
                )
            """, [user_id, rt, user_id, rt, user_id, rt])
            
            count = cursor.fetchone()[0]
            if count > 0:
                return True
        
        return False

    def add_menu_permission(self, menu_data: Dict[str, Any]) -> Optional[int]:
        """添加菜单权限配置"""
        try:
            required_perms = menu_data.get('required_permissions', [])
            if isinstance(required_perms, list):
                required_perms = json.dumps(required_perms)
            
            data_hint = menu_data.get('data_permission_hint')
            if isinstance(data_hint, dict):
                data_hint = json.dumps(data_hint)
            
            cursor = self.ds.execute("""
                INSERT INTO menu_permissions 
                (menu_code, menu_name, menu_path, required_permissions, required_any_permission,
                 parent_menu, icon, sort_order, is_active, data_permission_hint)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                menu_data['menu_code'],
                menu_data['menu_name'],
                menu_data['menu_path'],
                required_perms,
                1 if menu_data.get('required_any_permission', False) else 0,
                menu_data.get('parent_menu'),
                menu_data.get('icon'),
                menu_data.get('sort_order', 0),
                1 if menu_data.get('is_active', True) else 0,
                data_hint
            ])
            
            return cursor.lastrowid
        except Exception as e:
            print(f"[MenuPermService] 添加菜单权限失败: {e}")
            return None

    def update_menu_permission(self, menu_code: str, menu_data: Dict[str, Any]) -> bool:
        """更新菜单权限配置"""
        try:
            required_perms = menu_data.get('required_permissions')
            if isinstance(required_perms, list):
                required_perms = json.dumps(required_perms)
            
            data_hint = menu_data.get('data_permission_hint')
            if isinstance(data_hint, dict):
                data_hint = json.dumps(data_hint)
            
            cursor = self.ds.execute("""
                UPDATE menu_permissions SET
                    menu_name = ?,
                    menu_path = ?,
                    required_permissions = ?,
                    required_any_permission = ?,
                    parent_menu = ?,
                    icon = ?,
                    sort_order = ?,
                    is_active = ?,
                    data_permission_hint = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE menu_code = ?
            """, [
                menu_data.get('menu_name'),
                menu_data.get('menu_path'),
                required_perms,
                1 if menu_data.get('required_any_permission', False) else 0,
                menu_data.get('parent_menu'),
                menu_data.get('icon'),
                menu_data.get('sort_order', 0),
                1 if menu_data.get('is_active', True) else 0,
                data_hint,
                menu_code
            ])
            
            return cursor.rowcount > 0
        except Exception as e:
            print(f"[MenuPermService] 更新菜单权限失败: {e}")
            return False

    def delete_menu_permission(self, menu_code: str) -> bool:
        """删除菜单权限配置"""
        try:
            cursor = self.ds.execute(
                "DELETE FROM menu_permissions WHERE menu_code = ?",
                [menu_code]
            )
            return cursor.rowcount > 0
        except Exception as e:
            print(f"[MenuPermService] 删除菜单权限失败: {e}")
            return False
