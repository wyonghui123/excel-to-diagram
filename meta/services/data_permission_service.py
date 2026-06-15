# -*- coding: utf-8 -*-
"""
数据权限服务

支持：
1. 数据权限的CRUD
2. 权限继承计算（父级权限自动传播到子级）
3. 关系可见性判定
"""

from typing import List, Dict, Any, Optional, Set, Tuple
import logging

from meta.services.cascade_service import HierarchyConfigLoader
from meta.core.models import registry

logger = logging.getLogger(__name__)


class DataPermissionService:

    def __init__(self, data_source):
        self.ds = data_source
        self._hierarchy_loader = HierarchyConfigLoader

    @property
    def HIERARCHY_ORDER(self):
        return self._hierarchy_loader.get_type_order()

    def _rows_to_dicts(self, cursor) -> List[Dict[str, Any]]:
        rows = cursor.fetchall()
        if not rows:
            return []
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    def _is_owner(self, user_id: int, resource_type: str, resource_id: int) -> bool:
        """Check if user is the owner of a resource

        P12 修复: 与 ConditionPermissionService._is_owner 保持一致
        之前只查 owner_id，不查 created_by，导致 created_by 是 user 但 owner_id 是 None 时返回 False
        """
        table = self._get_table_name(resource_type)
        if not table:
            return False
        try:
            cursor = self.ds.execute(
                f"SELECT created_by, owner_id FROM {table} WHERE id = ?", [resource_id]
            )
            row = cursor.fetchone()
            if row:
                created_by, owner_id = row
                return user_id == created_by or user_id == owner_id
        except Exception:
            return False
        return False

    def get_permission_level(self, user_id: int, resource_type: str, resource_id: int) -> str:
        """Get user's permission level for a resource (Owner returns 'admin')"""
        if self._is_owner(user_id, resource_type, resource_id):
            return 'admin'
        return self.get_effective_permission_level(user_id, resource_type, resource_id)

    def has_access(self, user_id: int, resource_type: str, resource_id: int, action: str = 'read') -> bool:
        """
        Check if user has permission to access a resource
        
        Priority:
        1. Check if user is Owner
        2. Check explicit data permissions
        """
        if self._is_owner(user_id, resource_type, resource_id):
            return True
        level = self.get_permission_level(user_id, resource_type, resource_id)
        if level == 'none':
            return False
        if level == 'admin':
            return True
        if level == 'write':
            return action in ['read', 'write']
        if level == 'read':
            return action == 'read'
        return False

    def get_user_data_permissions(self, user_id: int) -> List[Dict[str, Any]]:
        cursor = self.ds.execute(
            "SELECT * FROM data_permissions WHERE user_id = ? ORDER BY resource_type, resource_id",
            [user_id]
        )
        return self._rows_to_dicts(cursor)

    def add_data_permission(self, user_id: int, resource_type: str, resource_id: int,
                            permission_level: str, inherit_to_children: bool = True) -> Optional[int]:
        try:
            cursor = self.ds.execute(
                """INSERT OR REPLACE INTO data_permissions
                   (user_id, resource_type, resource_id, permission_level, inherit_to_children)
                   VALUES (?, ?, ?, ?, ?)""",
                [user_id, resource_type, resource_id, permission_level, 1 if inherit_to_children else 0]
            )
            return cursor.lastrowid
        except Exception:
            return None

    def add_data_permission_with_propagation(
        self, user_id: int, resource_type: str, resource_id: int,
        permission_level: str, inherit_to_children: bool = True,
        propagate_to_parents: bool = True
    ) -> Dict[str, Any]:
        """
        添加数据权限，支持向上传播到父级
        
        示例：
        - 赋予"供应链云"领域 write 权限
        - 自动赋予父级"V5"版本 read 权限
        - 自动赋予父级"BIP"产品 read 权限
        
        返回：
        {
            'direct': int,  # 直接权限ID
            'propagated': List[Dict]  # 向上传播的权限列表
        }
        """
        result = {
            'direct': None,
            'propagated': []
        }
        
        # 1. 添加直接权限
        perm_id = self.add_data_permission(
            user_id, resource_type, resource_id,
            permission_level, inherit_to_children
        )
        result['direct'] = perm_id
        
        if not perm_id:
            return result
        
        # 2. 向上传播权限
        if propagate_to_parents:
            propagated = self._propagate_permission_to_parents(
                user_id, resource_type, resource_id, permission_level
            )
            result['propagated'] = propagated
        
        return result

    def _propagate_permission_to_parents(
        self, user_id: int, resource_type: str,
        resource_id: int, permission_level: str
    ) -> List[Dict[str, Any]]:
        """
        向上传播权限到所有父级
        
        规则：
        - 父级权限级别 = 'read'（导航权限）
        - 避免权限提升风险
        - 只在父级没有更高权限时才分配
        """
        propagated = []
        current_type = resource_type
        current_id = resource_id
        
        level_order = {'none': 0, 'read': 1, 'write': 2, 'admin': 3}
        
        while True:
            parent_type, parent_id = self._get_parent_resource(current_type, current_id)
            if not parent_type or not parent_id:
                break
            
            # 检查是否已有更高权限
            existing_level = self._get_direct_permission_level(user_id, parent_type, parent_id)
            
            # 向上传播时，权限级别为 read（导航权限）
            propagate_level = 'read'
            
            # 只有当现有权限低于传播权限时才分配
            if not existing_level or level_order.get(existing_level, 0) < level_order.get(propagate_level, 0):
                self.add_data_permission(
                    user_id, parent_type, parent_id,
                    propagate_level, inherit_to_children=False
                )
                propagated.append({
                    'resource_type': parent_type,
                    'resource_id': parent_id,
                    'permission_level': propagate_level,
                    'reason': 'auto_propagated_from_child'
                })
                logger.debug("Propagated: %s(%s) -> read (from %s(%s))", parent_type, parent_id, current_type, current_id)
            
            current_type = parent_type
            current_id = parent_id
        
        return propagated

    def _get_parent_resource(self, resource_type: str, resource_id: int) -> tuple:
        """获取父级资源 (parent_type, parent_id)"""
        parent_map = {
            'version': ('product', 'product_id'),
            'domain': ('version', 'version_id'),
            'sub_domain': ('domain', 'domain_id'),
            'service_module': ('sub_domain', 'sub_domain_id'),
            'business_object': ('service_module', 'service_module_id'),
        }
        
        if resource_type not in parent_map:
            return None, None
        
        parent_type, fk_field = parent_map[resource_type]
        table_name = self._get_table_name(resource_type)
        
        if not table_name:
            return None, None
        
        try:
            cursor = self.ds.execute(
                f"SELECT {fk_field} FROM {table_name} WHERE id = ?",
                [resource_id]
            )
            row = cursor.fetchone()
            if row and row[0]:
                return parent_type, row[0]
        except Exception:
            pass
        
        return None, None

    def remove_data_permission(self, perm_id: int) -> bool:
        try:
            self.ds.execute("DELETE FROM data_permissions WHERE id = ?", [perm_id])
            return True
        except Exception:
            return False

    def remove_data_permissions_by_user(self, user_id: int) -> bool:
        try:
            self.ds.execute("DELETE FROM data_permissions WHERE user_id = ?", [user_id])
            return True
        except Exception:
            return False

    def get_effective_permission_level(self, user_id: int, resource_type: str,
                                        resource_id: int) -> str:
        try:
            from meta.services.condition_permission_service import ConditionPermissionService
            cps = ConditionPermissionService(self.ds)
            level = cps.get_effective_permission_level(user_id, resource_type, resource_id)
            if level != 'none':
                return level
        except Exception:
            pass

        direct = self._get_direct_permission_level(user_id, resource_type, resource_id)
        if direct:
            return direct

        # P12 修复: 先查当前层级的 role/group 直接权限（之前只查父级继承）
        role_direct = self._get_role_direct_permission_level(user_id, resource_type, resource_id)
        if role_direct:
            return role_direct

        group_direct = self._get_group_direct_permission_level(user_id, resource_type, resource_id)
        if group_direct:
            return group_direct

        inherited = self._get_inherited_permission_level(user_id, resource_type, resource_id)
        if inherited:
            return inherited

        role_inherited = self._get_role_inherited_permission_level(user_id, resource_type, resource_id)
        if role_inherited:
            return role_inherited

        group_inherited = self._get_group_inherited_permission_level(user_id, resource_type, resource_id)
        if group_inherited:
            return group_inherited
        
        parent_visibility = self._get_parent_visibility_permission_level(user_id, resource_type, resource_id)
        if parent_visibility:
            return parent_visibility

        return 'none'

    def get_allowed_resource_ids(self, user_id: int, resource_type: str) -> List[int]:
        effective = self._get_all_effective_permissions(user_id)
        result = set()
        for perm in effective:
            if perm['resource_type'] == resource_type:
                result.add(perm['resource_id'])

            if perm.get('inherit_to_children'):
                inherited = self._get_inherited_resource_ids(
                    perm['resource_type'], perm['resource_id'], resource_type
                )
                result.update(inherited)

        parent_ids = self._get_visible_parent_ids(user_id, resource_type)
        result.update(parent_ids)

        return list(result)

    def _get_visible_parent_ids(self, user_id: int, resource_type: str) -> Set[int]:
        """获取向上可见的父级资源ID（导航权限）"""
        result = set()

        resource_idx = self._get_level_index(resource_type)
        if resource_idx < 0:
            return result

        child_types = self.HIERARCHY_ORDER[resource_idx + 1:]

        if not child_types:
            return result

        effective = self._get_all_effective_permissions(user_id)
        for perm in effective:
            perm_idx = self._get_level_index(perm['resource_type'])
            if perm_idx > resource_idx:
                parent_id = self._find_parent_id(perm['resource_type'], perm['resource_id'], resource_type)
                if parent_id:
                    logger.debug("Upward visibility: %s(%s) -> %s(%s)", perm['resource_type'], perm['resource_id'], resource_type, parent_id)
                    result.add(parent_id)

        if result:
            logger.debug("Upward visible %s IDs: %s", resource_type, result)
        return result

    def _get_parent_visibility_permission_level(self, user_id: int, resource_type: str,
                                                 resource_id: int) -> Optional[str]:
        """
        检查是否因子级权限而获得父级的权限级别
        
        规则：
        - 如果用户有任一子级资源的权限，则获得父级的 read 权限
        - 这是导航权限，用于让用户能够浏览到子级资源
        
        示例：
        - 用户有"订单管理"服务模块 write 权限
        - 则用户获得"供应链云"领域的 read 权限（用于导航）
        """
        resource_idx = self._get_level_index(resource_type)
        if resource_idx < 0:
            return None
        
        child_types = self.HIERARCHY_ORDER[resource_idx + 1:]
        if not child_types:
            return None
        
        for child_type in child_types:
            child_ids = self._get_child_resource_ids_for_parent(resource_type, resource_id, child_type)
            for child_id in child_ids:
                child_level = self._get_direct_permission_level(user_id, child_type, child_id)
                if child_level:
                    logger.debug("Parent visibility: %s(%s) -> read (from child %s(%s))", resource_type, resource_id, child_type, child_id)
                    return 'read'
                
                child_inherited = self._get_inherited_permission_level(user_id, child_type, child_id)
                if child_inherited:
                    logger.debug("Parent visibility: %s(%s) -> read (from inherited child %s(%s))", resource_type, resource_id, child_type, child_id)
                    return 'read'
        
        return None

    def _get_child_resource_ids_for_parent(self, parent_type: str, parent_id: int,
                                            child_type: str) -> List[int]:
        """获取指定父级资源的所有子级资源ID"""
        fk_field = self._get_parent_fk_field(child_type, parent_type)
        if not fk_field:
            return []
        
        table_name = self._get_table_name(child_type)
        try:
            cursor = self.ds.execute(
                f"SELECT id FROM {table_name} WHERE {fk_field} = ?",
                [parent_id]
            )
            return [row[0] for row in cursor.fetchall()]
        except Exception:
            return []

    def get_allowed_business_object_ids(self, user_id: int) -> List[int]:
        return self.get_allowed_resource_ids(user_id, 'business_object')

    def add_batch_user_data_permissions(self, user_ids: List[int], resource_type: str,
                                        resource_id: int, permission_level: str,
                                        inherit_to_children: bool = True) -> Dict[str, Any]:
        """批量为多个用户添加数据权限"""
        success_count = 0
        failed = []
        for user_id in user_ids:
            result = self.add_data_permission(user_id, resource_type, resource_id,
                                              permission_level, inherit_to_children)
            if result:
                success_count += 1
            else:
                failed.append(user_id)
        return {
            'success_count': success_count,
            'total': len(user_ids),
            'failed': failed
        }

    def _get_direct_permission_level(self, user_id: int, resource_type: str,
                                      resource_id: int) -> Optional[str]:
        cursor = self.ds.execute(
            "SELECT permission_level FROM data_permissions WHERE user_id = ? AND resource_type = ? AND resource_id = ?",
            [user_id, resource_type, resource_id]
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def _get_inherited_permission_level(self, user_id: int, resource_type: str,
                                         resource_id: int) -> Optional[str]:
        level_idx = self._get_level_index(resource_type)
        if level_idx <= 0:
            return None

        parent_types = self.HIERARCHY_ORDER[:level_idx]
        best_level = None
        level_order = {'read': 1, 'write': 2, 'admin': 3}

        for parent_type in parent_types:
            parent_id = self._find_parent_id(resource_type, resource_id, parent_type)
            if parent_id is None:
                continue

            cursor = self.ds.execute(
                "SELECT permission_level, inherit_to_children FROM data_permissions WHERE user_id = ? AND resource_type = ? AND resource_id = ?",
                [user_id, parent_type, parent_id]
            )
            row = cursor.fetchone()
            if row and row[1]:
                perm_level = row[0]
                if best_level is None or level_order.get(perm_level, 0) > level_order.get(best_level, 0):
                    best_level = perm_level

        return best_level

    def _get_role_direct_permission_level(self, user_id: int, resource_type: str,
                                             resource_id: int) -> Optional[str]:
        """P12 新增: 查用户当前层级通过 role 获得的直接权限

        修复: 之前 _get_role_inherited_permission_level 只查父级的 role_data_perm,
        导致当前层级的 role 权限无法被检测到
        """
        role_ids = self._get_user_role_ids(user_id)
        if not role_ids:
            return None
        placeholders = ','.join(['?'] * len(role_ids))
        cursor = self.ds.execute(
            f"SELECT permission_level, inherit_to_children FROM role_data_permissions WHERE role_id IN ({placeholders}) AND resource_type = ? AND resource_id = ?",
            role_ids + [resource_type, resource_id]
        )
        level_order = {'read': 1, 'write': 2, 'admin': 3}
        best_level = None
        for row in cursor.fetchall():
            perm_level = row[0]
            if best_level is None or level_order.get(perm_level, 0) > level_order.get(best_level, 0):
                best_level = perm_level
        return best_level

    def _get_group_direct_permission_level(self, user_id: int, resource_type: str,
                                              resource_id: int) -> Optional[str]:
        """P12 新增: 查用户当前层级通过 user_group 获得的直接权限"""
        group_ids = self._get_user_group_ids(user_id)
        if not group_ids:
            return None
        placeholders = ','.join(['?'] * len(group_ids))
        cursor = self.ds.execute(
            f"SELECT permission_level, inherit_to_children FROM group_data_permissions WHERE group_id IN ({placeholders}) AND resource_type = ? AND resource_id = ?",
            group_ids + [resource_type, resource_id]
        )
        level_order = {'read': 1, 'write': 2, 'admin': 3}
        best_level = None
        for row in cursor.fetchall():
            perm_level = row[0]
            if best_level is None or level_order.get(perm_level, 0) > level_order.get(best_level, 0):
                best_level = perm_level
        return best_level

    def _get_role_inherited_permission_level(self, user_id: int, resource_type: str,
                                               resource_id: int) -> Optional[str]:
        level_idx = self._get_level_index(resource_type)
        if level_idx <= 0:
            return None

        parent_types = self.HIERARCHY_ORDER[:level_idx]
        best_level = None
        level_order = {'read': 1, 'write': 2, 'admin': 3}

        role_ids = self._get_user_role_ids(user_id)
        if not role_ids:
            return None

        for parent_type in parent_types:
            parent_id = self._find_parent_id(resource_type, resource_id, parent_type)
            if parent_id is None:
                continue

            placeholders = ','.join(['?'] * len(role_ids))
            cursor = self.ds.execute(
                f"SELECT permission_level, inherit_to_children FROM role_data_permissions WHERE role_id IN ({placeholders}) AND resource_type = ? AND resource_id = ?",
                role_ids + [parent_type, parent_id]
            )
            for row in cursor.fetchall():
                if row[1]:
                    perm_level = row[0]
                    if best_level is None or level_order.get(perm_level, 0) > level_order.get(best_level, 0):
                        best_level = perm_level

        return best_level

    def _get_group_inherited_permission_level(self, user_id: int, resource_type: str,
                                                resource_id: int) -> Optional[str]:
        level_idx = self._get_level_index(resource_type)
        if level_idx <= 0:
            return None

        parent_types = self.HIERARCHY_ORDER[:level_idx]
        best_level = None
        level_order = {'read': 1, 'write': 2, 'admin': 3}

        group_ids = self._get_user_group_ids(user_id)
        if not group_ids:
            return None

        for parent_type in parent_types:
            parent_id = self._find_parent_id(resource_type, resource_id, parent_type)
            if parent_id is None:
                continue

            placeholders = ','.join(['?'] * len(group_ids))
            cursor = self.ds.execute(
                f"SELECT permission_level, inherit_to_children FROM group_data_permissions WHERE group_id IN ({placeholders}) AND resource_type = ? AND resource_id = ?",
                group_ids + [parent_type, parent_id]
            )
            for row in cursor.fetchall():
                if row[1]:
                    perm_level = row[0]
                    if best_level is None or level_order.get(perm_level, 0) > level_order.get(best_level, 0):
                        best_level = perm_level

        return best_level

    def _get_user_role_ids(self, user_id: int) -> List[int]:
        """通过用户组间接获取用户的所有角色 ID"""
        try:
            cursor = self.ds.execute(
                """SELECT DISTINCT gr.role_id FROM group_roles gr
                   JOIN user_group_members ugm ON gr.group_id = ugm.group_id
                   WHERE ugm.user_id = ?""",
                [user_id]
            )
            return [row[0] for row in cursor.fetchall()]
        except Exception:
            return []

    def _get_user_group_ids(self, user_id: int) -> List[int]:
        try:
            cursor = self.ds.execute(
                "SELECT group_id FROM user_group_members WHERE user_id = ?",
                [user_id]
            )
            return [row[0] for row in cursor.fetchall()]
        except Exception:
            return []

    def _get_all_effective_permissions(self, user_id: int) -> List[Dict[str, Any]]:
        """获取用户所有有效权限（包括直接权限和通过用户组→角色继承的权限）
        
        [重构后] 权限解析路径：User → UserGroup → Role → DataPermission
        不再直接查询 group_data_permissions（已废弃）
        """
        result = []

        # 1. 直接权限
        cursor = self.ds.execute(
            "SELECT * FROM data_permissions WHERE user_id = ?",
            [user_id]
        )
        direct_perms = self._rows_to_dicts(cursor)
        for perm in direct_perms:
            perm['source'] = 'direct'
            result.append(perm)
        logger.debug("User %s direct permissions: %s", user_id, len(direct_perms))

        # 2. 通过用户组→角色获得的权限
        cursor = self.ds.execute("""
            SELECT rdp.*, r.name as role_name, g.name as group_name
            FROM role_data_permissions rdp
            JOIN group_roles gr ON gr.role_id = rdp.role_id
            JOIN user_group_members ugm ON ugm.group_id = gr.group_id
            JOIN roles r ON r.id = rdp.role_id
            JOIN user_groups g ON g.id = gr.group_id
            WHERE ugm.user_id = ?
        """, [user_id])
        group_role_perms = self._rows_to_dicts(cursor)
        for perm in group_role_perms:
            perm['source'] = 'group_role'
            result.append(perm)
        logger.debug("User %s group-role permissions: %s", user_id, len(group_role_perms))
        logger.debug("User %s total effective permissions: %s", user_id, len(result))

        return result

    def _get_inherited_resource_ids(self, source_type: str, source_id: int,
                                     target_type: str) -> List[int]:
        source_idx = self._get_level_index(source_type)
        target_idx = self._get_level_index(target_type)

        if source_idx >= target_idx:
            return []

        ids = [source_id]
        current_type = source_type

        for i in range(source_idx, target_idx):
            next_type = self.HIERARCHY_ORDER[i + 1]
            fk_field = self._get_parent_fk_field(next_type, current_type)
            if not fk_field:
                break

            new_ids = []
            for rid in ids:
                cursor = self.ds.execute(
                    f"SELECT id FROM {self._get_table_name(next_type)} WHERE {fk_field} = ?",
                    [rid]
                )
                new_ids.extend([row[0] for row in cursor.fetchall()])

            ids = new_ids
            current_type = next_type

        return ids if current_type == target_type else []

    def _find_parent_id(self, resource_type: str, resource_id: int,
                        parent_type: str) -> Optional[int]:
        parent_idx = self._get_level_index(parent_type)
        resource_idx = self._get_level_index(resource_type)

        logger.debug("_find_parent_id: %s(%s) -> %s, indices: %s -> %s", resource_type, resource_id, parent_type, resource_idx, parent_idx)

        if parent_idx >= resource_idx:
            return None

        current_id = resource_id
        current_type = resource_type

        for i in range(resource_idx - 1, parent_idx - 1, -1):
            parent_type_step = self.HIERARCHY_ORDER[i]
            fk_field = self._get_parent_fk_field(current_type, parent_type_step)
            table_name = self._get_table_name(current_type)
            
            logger.debug("  Step: %s(%s) -> %s, FK: %s, Table: %s", current_type, current_id, parent_type_step, fk_field, table_name)
            
            if not fk_field:
                return None

            cursor = self.ds.execute(
                f"SELECT {fk_field} FROM {table_name} WHERE id = ?",
                [current_id]
            )
            row = cursor.fetchone()
            if not row:
                logger.debug("  No row found!")
                return None

            current_id = row[0]
            current_type = parent_type_step
            logger.debug("  Result: parent_id = %s", current_id)

        return current_id

    def _get_level_index(self, resource_type: str) -> int:
        normalized = resource_type.rstrip('s')
        hierarchy_order = self._hierarchy_loader.get_type_order()
        for i, level in enumerate(hierarchy_order):
            if level == normalized or level.rstrip('s') == normalized:
                return i
        return -1

    def _get_parent_fk_field(self, child_type: str, parent_type: str) -> Optional[str]:
        child_norm = child_type.rstrip('s')
        fk = self._hierarchy_loader.get_foreign_key(child_norm)
        return fk

    def _get_table_name(self, resource_type: str) -> str:
        # 优先从层级配置获取表名（hierarchies.yaml 中的 table_name 更可靠）
        hierarchy_table = self._hierarchy_loader.get_table_name(resource_type)
        if hierarchy_table:
            return hierarchy_table
        # Fallback: 从 registry 获取
        normalized = resource_type.rstrip('s')
        meta_obj = registry.get(normalized)
        if meta_obj and meta_obj.table_name:
            return meta_obj.table_name
        return resource_type

    def get_role_data_permissions(self, role_id: int) -> List[Dict[str, Any]]:
        """获取角色的数据权限，包含资源详情和路径"""
        cursor = self.ds.execute(
            "SELECT * FROM role_data_permissions WHERE role_id = ? ORDER BY resource_type, resource_id",
            [role_id]
        )
        perms = self._rows_to_dicts(cursor)

        for perm in perms:
            perm['resource_detail'] = self._get_resource_detail(perm['resource_type'], perm['resource_id'])
            perm['resource_path'] = self._build_resource_path(perm['resource_type'], perm['resource_id'])

        return perms

    def add_role_data_permission(self, role_id: int, resource_type: str, resource_id: int,
                                  permission_level: str, inherit_to_children: bool = True,
                                  created_by: int = None) -> Optional[int]:
        try:
            cursor = self.ds.execute(
                """INSERT OR REPLACE INTO role_data_permissions
                   (role_id, resource_type, resource_id, permission_level, inherit_to_children, created_by)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [role_id, resource_type, resource_id, permission_level,
                 1 if inherit_to_children else 0, created_by]
            )
            cursor = self.ds.execute("SELECT last_insert_rowid()")
            result = cursor.fetchone()
            if result and result[0]:
                return result[0]
            cursor = self.ds.execute(
                "SELECT id FROM role_data_permissions WHERE role_id=? AND resource_type=? AND resource_id=?",
                [role_id, resource_type, resource_id]
            )
            row = cursor.fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.error("add_role_data_permission error: %s", e)
            return None

    def remove_role_data_permission(self, perm_id: int) -> bool:
        try:
            self.ds.execute("DELETE FROM role_data_permissions WHERE id = ?", [perm_id])
            return True
        except Exception:
            return False

    def get_roles_with_data_permissions(self) -> List[Dict[str, Any]]:
        """获取所有有数据权限配置的角色"""
        cursor = self.ds.execute("""
            SELECT DISTINCT r.*,
                   (SELECT COUNT(*) FROM role_data_permissions WHERE role_id = r.id) as perm_count
            FROM roles r
            WHERE r.id IN (SELECT DISTINCT role_id FROM role_data_permissions)
            ORDER BY r.id
        """)
        return self._rows_to_dicts(cursor)

    def get_user_data_permissions_from_roles(self, user_id: int) -> List[Dict[str, Any]]:
        """获取用户通过用户组→角色获得的数据权限"""
        cursor = self.ds.execute("""
            SELECT rdp.* FROM role_data_permissions rdp
            INNER JOIN group_roles gr ON rdp.role_id = gr.role_id
            INNER JOIN user_group_members ugm ON gr.group_id = ugm.group_id
            WHERE ugm.user_id = ?
            ORDER BY rdp.resource_type, rdp.resource_id
        """, [user_id])
        return self._rows_to_dicts(cursor)

    def get_all_user_data_permissions(self, user_id: int) -> List[Dict[str, Any]]:
        """获取用户所有数据权限（直接+角色），取并集"""
        direct = self.get_user_data_permissions(user_id)
        from_roles = self.get_user_data_permissions_from_roles(user_id)

        combined = {}
        for p in direct + from_roles:
            key = (p['resource_type'], p['resource_id'])
            if key not in combined:
                combined[key] = p
            else:
                level_order = {'read': 1, 'write': 2, 'admin': 3}
                existing_level = combined[key].get('permission_level', 'read')
                new_level = p.get('permission_level', 'read')
                if level_order.get(new_level, 0) > level_order.get(existing_level, 0):
                    combined[key] = p

        return list(combined.values())

    def get_group_data_permissions(self, group_id: int) -> List[Dict[str, Any]]:
        """获取用户组的数据权限，包含资源详情和路径"""
        cursor = self.ds.execute(
            "SELECT * FROM group_data_permissions WHERE group_id = ? ORDER BY resource_type, resource_id",
            [group_id]
        )
        perms = self._rows_to_dicts(cursor)

        for perm in perms:
            perm['resource_detail'] = self._get_resource_detail(perm['resource_type'], perm['resource_id'])
            perm['resource_path'] = self._build_resource_path(perm['resource_type'], perm['resource_id'])

        return perms

    def _get_resource_detail(self, resource_type: str, resource_id: int) -> Dict:
        """获取资源详情（名称、编码）"""
        table_map = {
            'product': 'products',
            'version': 'versions',
            'domain': 'domains',
            'sub_domain': 'sub_domains',
            'service_module': 'service_modules',
            'business_object': 'business_objects',
            'relationship': 'relationships',
            'annotation': 'annotations',
        }
        table_name = table_map.get(resource_type)
        if not table_name:
            return {}

        try:
            cursor = self.ds.execute(f"SELECT name, code FROM {table_name} WHERE id = ?", [resource_id])
            row = cursor.fetchone()
            if row:
                return {'name': row[0], 'code': row[1]}
        except Exception as e:
            logger.error("_get_resource_detail error: %s", e)
        return {}

    def _build_resource_path(self, resource_type: str, resource_id: int) -> List[Dict]:
        """构建资源的父级路径"""
        path_chain = []

        type_labels = {
            'product': '产品',
            'version': '版本',
            'domain': '领域',
            'sub_domain': '子领域',
            'service_module': '服务模块',
            'business_object': '业务对象',
        }

        table_map = {
            'product': ('products', None, None),
            'version': ('versions', 'product_id', 'product'),
            'domain': ('domains', 'version_id', 'version'),
            'sub_domain': ('sub_domains', 'domain_id', 'domain'),
            'service_module': ('service_modules', 'sub_domain_id', 'sub_domain'),
            'business_object': ('business_objects', 'service_module_id', 'service_module'),
        }

        current_type = resource_type
        current_id = resource_id

        while current_type and current_id:
            config = table_map.get(current_type)
            if not config:
                break

            table_name, fk_field, parent_type = config

            try:
                if fk_field:
                    cursor = self.ds.execute(
                        f"SELECT name, code, {fk_field} FROM {table_name} WHERE id = ?",
                        [current_id]
                    )
                else:
                    cursor = self.ds.execute(
                        f"SELECT name, code FROM {table_name} WHERE id = ?",
                        [current_id]
                    )
                row = cursor.fetchone()
                if not row:
                    break

                path_chain.insert(0, {
                    'type': current_type,
                    'label': type_labels.get(current_type, current_type),
                    'name': row[0],
                    'code': row[1],
                    'id': current_id,
                })

                if fk_field and len(row) > 2 and row[2]:
                    current_id = row[2]
                    current_type = parent_type
                else:
                    break

            except Exception as e:
                logger.error("_build_resource_path error: %s", e)
                break

        return path_chain

    def add_group_data_permission(self, group_id: int, resource_type: str, resource_id: int,
                                   permission_level: str, inherit_to_children: bool = True) -> Optional[int]:
        """为用户组添加数据权限"""
        try:
            cursor = self.ds.execute(
                """INSERT OR REPLACE INTO group_data_permissions
                   (group_id, resource_type, resource_id, permission_level, inherit_to_children)
                   VALUES (?, ?, ?, ?, ?)""",
                [group_id, resource_type, resource_id, permission_level, 1 if inherit_to_children else 0]
            )
            cursor = self.ds.execute("SELECT last_insert_rowid()")
            result = cursor.fetchone()
            if result and result[0]:
                return result[0]
            cursor = self.ds.execute(
                "SELECT id FROM group_data_permissions WHERE group_id=? AND resource_type=? AND resource_id=?",
                [group_id, resource_type, resource_id]
            )
            row = cursor.fetchone()
            return row[0] if row else None
        except Exception:
            return None

    def remove_group_data_permission(self, perm_id: int) -> bool:
        """删除用户组数据权限"""
        try:
            self.ds.execute("DELETE FROM group_data_permissions WHERE id = ?", [perm_id])
            return True
        except Exception:
            return False

    def get_user_data_permissions_from_groups(self, user_id: int) -> List[Dict[str, Any]]:
        """
        获取用户通过用户组获得的数据权限

        [重构后] 权限解析路径：User → UserGroup → Role → DataPermission
        不再直接查询 group_data_permissions（已废弃）
        """
        cursor = self.ds.execute("""
            SELECT DISTINCT rdp.* FROM role_data_permissions rdp
            INNER JOIN group_roles gr ON rdp.role_id = gr.role_id
            INNER JOIN user_group_members ugm ON gr.group_id = ugm.group_id
            WHERE ugm.user_id = ?
            ORDER BY rdp.resource_type, rdp.resource_id
        """, [user_id])
        return self._rows_to_dicts(cursor)

    def get_user_data_permissions_from_groups_legacy(self, user_id: int) -> List[Dict[str, Any]]:
        """[已废弃] 旧版：直接从 group_data_permissions 获取用户组数据权限"""
        cursor = self.ds.execute("""
            SELECT gdp.* FROM group_data_permissions gdp
            INNER JOIN user_group_members ugm ON gdp.group_id = ugm.group_id
            WHERE ugm.user_id = ?
            ORDER BY gdp.resource_type, gdp.resource_id
        """, [user_id])
        return self._rows_to_dicts(cursor)

    def get_all_user_data_permissions_with_groups(self, user_id: int) -> List[Dict[str, Any]]:
        """
        获取用户所有数据权限（直接+角色+用户组→角色），取并集

        [重构后] 用户组权限现在通过角色间接获取：
        - 直接权限: data_permissions (user直接分配)
        - 角色权限: role_data_permissions (用户直接关联角色)
        - 用户组权限: 通过 group_roles → role_data_permissions 链路获取
        """
        direct = self.get_user_data_permissions(user_id)
        from_roles = self.get_user_data_permissions_from_roles(user_id)
        from_group_roles = self.get_user_data_permissions_from_groups(user_id)

        combined = {}
        level_order = {'read': 1, 'write': 2, 'admin': 3}

        for p in direct + from_roles + from_group_roles:
            key = (p['resource_type'], p['resource_id'])
            if key not in combined:
                combined[key] = p
            else:
                existing_level = combined[key].get('permission_level', 'read')
                new_level = p.get('permission_level', 'read')
                if level_order.get(new_level, 0) > level_order.get(existing_level, 0):
                    combined[key] = p

        return list(combined.values())

    def get_role_priority(self, role_id: int) -> int:
        """获取角色优先级"""
        cursor = self.ds.execute("SELECT priority FROM roles WHERE id = ?", [role_id])
        row = cursor.fetchone()
        return row[0] if row else 0

    def get_user_max_role_priority(self, user_id: int) -> int:
        """获取用户的最高角色优先级（通过用户组间接获取）"""
        cursor = self.ds.execute("""
            SELECT MAX(r.priority) FROM roles r
            INNER JOIN group_roles gr ON r.id = gr.role_id
            INNER JOIN user_group_members ugm ON gr.group_id = ugm.group_id
            WHERE ugm.user_id = ?
        """, [user_id])
        row = cursor.fetchone()
        return row[0] if row and row[0] is not None else 0

    def can_assign_role(self, operator_id: int, role_id: int) -> bool:
        """检查操作者是否可以分配该角色（防止权限提升）"""
        operator_priority = self.get_user_max_role_priority(operator_id)
        target_priority = self.get_role_priority(role_id)
        return operator_priority >= target_priority
