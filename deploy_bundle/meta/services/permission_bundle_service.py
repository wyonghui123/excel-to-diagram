# -*- coding: utf-8 -*-
"""
权限包服务

支持：
1. 权限包的CRUD
2. 权限包分配给用户
3. 权限一致性保障
"""

from typing import List, Dict, Any, Optional
import json


class PermissionBundleService:

    def __init__(self, data_source, data_permission_service=None, menu_permission_service=None):
        self.ds = data_source
        self.data_permission_service = data_permission_service
        self.menu_permission_service = menu_permission_service

    def _rows_to_dicts(self, cursor) -> List[Dict[str, Any]]:
        rows = cursor.fetchall()
        if not rows:
            return []
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    def get_all_bundles(self) -> List[Dict[str, Any]]:
        """获取所有权限包"""
        cursor = self.ds.execute(
            "SELECT * FROM permission_bundles WHERE is_active = 1 ORDER BY bundle_name"
        )
        bundles = self._rows_to_dicts(cursor)
        
        for bundle in bundles:
            self._parse_json_fields(bundle)
        
        return bundles

    def get_bundle_by_code(self, bundle_code: str) -> Optional[Dict[str, Any]]:
        """根据编码获取权限包"""
        cursor = self.ds.execute(
            "SELECT * FROM permission_bundles WHERE bundle_code = ?",
            [bundle_code]
        )
        rows = self._rows_to_dicts(cursor)
        if not rows:
            return None
        
        bundle = rows[0]
        self._parse_json_fields(bundle)
        return bundle

    def _parse_json_fields(self, bundle: Dict[str, Any]) -> None:
        """解析JSON字段"""
        for field in ['menu_permissions', 'function_permissions', 'data_permission_template']:
            if bundle.get(field):
                try:
                    bundle[field] = json.loads(bundle[field])
                except (json.JSONDecodeError, TypeError):
                    bundle[field] = [] if field != 'data_permission_template' else {}
            else:
                bundle[field] = [] if field != 'data_permission_template' else {}

    def assign_bundle_to_user(
        self, user_id: int, bundle_code: str,
        data_resource_ids: Optional[List[int]] = None,
        propagate_to_parents: bool = True
    ) -> Dict[str, Any]:
        """
        将权限包分配给用户
        
        参数：
        - user_id: 用户ID
        - bundle_code: 权限包编码
        - data_resource_ids: 数据权限资源ID列表（如果模板类型为select_on_assign）
        - propagate_to_parents: 是否向上传播父级权限
        
        返回：
        {
            'success': bool,
            'bundle': Dict,
            'assigned': {
                'menus': List,
                'functions': List,
                'data_permissions': List
            }
        }
        """
        result = {
            'success': False,
            'bundle': None,
            'assigned': {
                'menus': [],
                'functions': [],
                'data_permissions': []
            },
            'errors': []
        }
        
        bundle = self.get_bundle_by_code(bundle_code)
        if not bundle:
            result['errors'].append(f'权限包不存在: {bundle_code}')
            return result
        
        result['bundle'] = bundle
        
        # 1. 分配菜单权限（通过功能权限实现）
        # 菜单权限由功能权限驱动，不需要单独分配
        
        # 2. 分配功能权限
        function_perms = bundle.get('function_permissions', [])
        if function_perms and '*' in function_perms:
            # 超级权限，分配所有权限
            result['assigned']['functions'] = ['*']
        else:
            for perm_code in function_perms:
                assigned = self._assign_function_permission(user_id, perm_code)
                if assigned:
                    result['assigned']['functions'].append(perm_code)
        
        # 3. 分配数据权限
        data_template = bundle.get('data_permission_template', {})
        if data_template:
            assigned_data = self._assign_data_permissions(
                user_id, data_template, data_resource_ids, propagate_to_parents
            )
            result['assigned']['data_permissions'] = assigned_data
        
        result['success'] = True
        return result

    def _assign_function_permission(self, user_id: int, perm_code: str) -> bool:
        """分配功能权限给用户"""
        try:
            # 获取权限ID
            cursor = self.ds.execute(
                "SELECT id FROM permissions WHERE code = ?",
                [perm_code]
            )
            row = cursor.fetchone()
            if not row:
                return False
            
            perm_id = row[0]
            
            # 获取管理员角色ID
            cursor = self.ds.execute(
                "SELECT id FROM roles WHERE name = 'admin'"
            )
            row = cursor.fetchone()
            if row:
                admin_role_id = row[0]
                # 将用户添加到管理员角色
                self.ds.execute(
                    """INSERT OR IGNORE INTO user_roles (user_id, role_id)
                       VALUES (?, ?)""",
                    [user_id, admin_role_id]
                )
                return True
            
            return False
        except Exception as e:
            print(f"[BundleService] 分配功能权限失败: {e}")
            return False

    def _assign_data_permissions(
        self, user_id: int, template: Dict[str, Any],
        resource_ids: Optional[List[int]], propagate_to_parents: bool
    ) -> List[Dict[str, Any]]:
        """分配数据权限"""
        assigned = []
        
        if not self.data_permission_service:
            return assigned
        
        template_type = template.get('type', 'select_on_assign')
        resource_types = template.get('resource_types', ['domain'])
        default_level = template.get('default_level', 'read')
        
        if template_type == 'all_resources':
            # 所有资源权限 - 需要特殊处理
            if '*' in resource_types:
                # 分配所有资源类型的权限
                for rt in ['domain', 'sub_domain', 'service_module', 'business_object']:
                    result = self.data_permission_service.add_data_permission_with_propagation(
                        user_id, rt, 0,  # 0 表示所有资源
                        default_level, propagate_to_parents=propagate_to_parents
                    )
                    assigned.append({
                        'resource_type': rt,
                        'resource_id': 0,
                        'permission_level': default_level,
                        'propagated': result.get('propagated', [])
                    })
        
        elif template_type == 'select_on_assign' and resource_ids:
            # 选择性分配
            for rt in resource_types:
                for rid in resource_ids:
                    result = self.data_permission_service.add_data_permission_with_propagation(
                        user_id, rt, rid,
                        default_level, propagate_to_parents=propagate_to_parents
                    )
                    assigned.append({
                        'resource_type': rt,
                        'resource_id': rid,
                        'permission_level': default_level,
                        'propagated': result.get('propagated', [])
                    })
        
        return assigned

    def get_user_bundles(self, user_id: int) -> List[Dict[str, Any]]:
        """获取用户已分配的权限包（通过功能权限推断）"""
        # 这是一个简化实现，实际可能需要单独的分配记录表
        bundles = self.get_all_bundles()
        user_bundles = []
        
        # 获取用户的功能权限
        cursor = self.ds.execute("""
            SELECT DISTINCT p.code
            FROM permissions p
            INNER JOIN role_permissions rp ON p.id = rp.permission_id
            INNER JOIN user_roles ur ON rp.role_id = ur.role_id
            WHERE ur.user_id = ?
        """, [user_id])
        user_perms = set(row[0] for row in cursor.fetchall())
        
        for bundle in bundles:
            bundle_perms = set(bundle.get('function_permissions', []))
            if bundle_perms and bundle_perms.issubset(user_perms):
                user_bundles.append(bundle)
            elif '*' in user_perms:
                user_bundles.append(bundle)
        
        return user_bundles

    def create_bundle(self, bundle_data: Dict[str, Any]) -> Optional[int]:
        """创建权限包"""
        try:
            menu_perms = bundle_data.get('menu_permissions', [])
            if isinstance(menu_perms, list):
                menu_perms = json.dumps(menu_perms)
            
            func_perms = bundle_data.get('function_permissions', [])
            if isinstance(func_perms, list):
                func_perms = json.dumps(func_perms)
            
            data_template = bundle_data.get('data_permission_template', {})
            if isinstance(data_template, dict):
                data_template = json.dumps(data_template)
            
            cursor = self.ds.execute("""
                INSERT INTO permission_bundles 
                (bundle_code, bundle_name, description, menu_permissions, function_permissions,
                 data_permission_template, is_active, is_system)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                bundle_data['bundle_code'],
                bundle_data['bundle_name'],
                bundle_data.get('description'),
                menu_perms,
                func_perms,
                data_template,
                1 if bundle_data.get('is_active', True) else 0,
                0  # 用户创建的不是系统预置
            ])
            
            return cursor.lastrowid
        except Exception as e:
            print(f"[BundleService] 创建权限包失败: {e}")
            return None

    def update_bundle(self, bundle_code: str, bundle_data: Dict[str, Any]) -> bool:
        """更新权限包"""
        try:
            menu_perms = bundle_data.get('menu_permissions')
            if isinstance(menu_perms, list):
                menu_perms = json.dumps(menu_perms)
            
            func_perms = bundle_data.get('function_permissions')
            if isinstance(func_perms, list):
                func_perms = json.dumps(func_perms)
            
            data_template = bundle_data.get('data_permission_template')
            if isinstance(data_template, dict):
                data_template = json.dumps(data_template)
            
            cursor = self.ds.execute("""
                UPDATE permission_bundles SET
                    bundle_name = ?,
                    description = ?,
                    menu_permissions = ?,
                    function_permissions = ?,
                    data_permission_template = ?,
                    is_active = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE bundle_code = ? AND is_system = 0
            """, [
                bundle_data.get('bundle_name'),
                bundle_data.get('description'),
                menu_perms,
                func_perms,
                data_template,
                1 if bundle_data.get('is_active', True) else 0,
                bundle_code
            ])
            
            return cursor.rowcount > 0
        except Exception as e:
            print(f"[BundleService] 更新权限包失败: {e}")
            return False

    def delete_bundle(self, bundle_code: str) -> bool:
        """删除权限包（只能删除非系统预置的）"""
        try:
            cursor = self.ds.execute(
                "DELETE FROM permission_bundles WHERE bundle_code = ? AND is_system = 0",
                [bundle_code]
            )
            return cursor.rowcount > 0
        except Exception as e:
            print(f"[BundleService] 删除权限包失败: {e}")
            return False
