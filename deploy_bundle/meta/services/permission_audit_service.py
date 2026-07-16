# -*- coding: utf-8 -*-
"""
权限审计服务

支持：
1. 权限变更记录
2. 权限使用分析
3. 权限一致性检查报告
"""

from typing import List, Dict, Any, Optional
from datetime import datetime


class PermissionAuditService:

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

    def get_permission_change_history(
        self, user_id: Optional[int] = None,
        resource_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取权限变更历史
        
        注意：这需要audit_logs表支持
        """
        try:
            query = """
                SELECT * FROM audit_logs
                WHERE action IN ('data_permission_add', 'data_permission_remove',
                                'role_permission_add', 'role_permission_remove',
                                'user_role_add', 'user_role_remove')
            """
            params = []
            
            if user_id:
                query += " AND JSON_EXTRACT(new_values, '$.user_id') = ?"
                params.append(user_id)
            
            if resource_type:
                query += " AND JSON_EXTRACT(new_values, '$.resource_type') = ?"
                params.append(resource_type)
            
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            
            cursor = self.ds.execute(query, params)
            return self._rows_to_dicts(cursor)
        except Exception as e:
            print(f"[AuditService] 获取变更历史失败: {e}")
            return []

    def get_user_permission_summary(self, user_id: int) -> Dict[str, Any]:
        """
        获取用户权限摘要
        
        返回：
        {
            'user_id': int,
            'roles': List[Dict],
            'function_permissions': List[str],
            'data_permissions': List[Dict],
            'menu_access': List[Dict],
            'consistency_warnings': List[str]
        }
        """
        summary = {
            'user_id': user_id,
            'roles': [],
            'function_permissions': [],
            'data_permissions': [],
            'menu_access': [],
            'consistency_warnings': []
        }
        
        # 1. 获取用户角色
        cursor = self.ds.execute("""
            SELECT r.* FROM roles r
            INNER JOIN user_roles ur ON r.id = ur.role_id
            WHERE ur.user_id = ?
        """, [user_id])
        summary['roles'] = self._rows_to_dicts(cursor)
        
        # 2. 获取功能权限
        cursor = self.ds.execute("""
            SELECT DISTINCT p.code, p.name
            FROM permissions p
            INNER JOIN role_permissions rp ON p.id = rp.permission_id
            INNER JOIN user_roles ur ON rp.role_id = ur.role_id
            WHERE ur.user_id = ?
        """, [user_id])
        summary['function_permissions'] = [
            {'code': row[0], 'name': row[1]} for row in cursor.fetchall()
        ]
        
        # 3. 获取数据权限
        if self.data_permission_service:
            summary['data_permissions'] = self.data_permission_service.get_user_data_permissions(user_id)
        
        # 4. 获取菜单访问权限
        if self.menu_permission_service:
            summary['menu_access'] = self.menu_permission_service.get_user_accessible_menus(user_id)
        
        # 5. 一致性检查
        if self.menu_permission_service:
            report = self.menu_permission_service.get_user_permission_report(user_id)
            summary['consistency_warnings'] = [
                inc['warnings'] for inc in report.get('inconsistencies', [])
            ]
        
        return summary

    def get_permission_usage_stats(self, days: int = 30) -> Dict[str, Any]:
        """
        获取权限使用统计
        
        返回：
        {
            'total_users': int,
            'total_roles': int,
            'total_data_permissions': int,
            'permissions_by_type': Dict,
            'recent_changes': int
        }
        """
        stats = {
            'total_users': 0,
            'total_roles': 0,
            'total_data_permissions': 0,
            'permissions_by_type': {},
            'recent_changes': 0
        }
        
        # 总用户数
        cursor = self.ds.execute("SELECT COUNT(*) FROM users")
        stats['total_users'] = cursor.fetchone()[0]
        
        # 总角色数
        cursor = self.ds.execute("SELECT COUNT(*) FROM roles")
        stats['total_roles'] = cursor.fetchone()[0]
        
        # 总数据权限数
        cursor = self.ds.execute("SELECT COUNT(*) FROM data_permissions")
        stats['total_data_permissions'] = cursor.fetchone()[0]
        
        # 按资源类型统计
        cursor = self.ds.execute("""
            SELECT resource_type, COUNT(*) as count
            FROM data_permissions
            GROUP BY resource_type
        """)
        stats['permissions_by_type'] = {row[0]: row[1] for row in cursor.fetchall()}
        
        # 近期变更数
        try:
            cursor = self.ds.execute(f"""
                SELECT COUNT(*) FROM audit_logs
                WHERE action LIKE '%permission%'
                AND created_at >= datetime('now', '-{days} days')
            """)
            stats['recent_changes'] = cursor.fetchone()[0]
        except Exception:
            stats['recent_changes'] = 0
        
        return stats

    def find_orphan_permissions(self) -> List[Dict[str, Any]]:
        """
        查找孤立权限（分配给不存在的用户或资源）
        """
        orphans = []
        
        # 检查数据权限中的孤立记录
        cursor = self.ds.execute("""
            SELECT dp.* FROM data_permissions dp
            LEFT JOIN users u ON dp.user_id = u.id
            WHERE u.id IS NULL
        """)
        user_orphans = self._rows_to_dicts(cursor)
        for o in user_orphans:
            o['reason'] = '用户不存在'
            orphans.append(o)
        
        return orphans

    def find_excessive_permissions(self) -> List[Dict[str, Any]]:
        """
        查找过度权限（用户拥有过多权限）
        """
        excessive = []
        
        # 查找拥有admin权限的非admin用户
        cursor = self.ds.execute("""
            SELECT u.id, u.username, u.display_name, COUNT(dp.id) as perm_count
            FROM users u
            LEFT JOIN data_permissions dp ON u.id = dp.user_id
            WHERE u.id NOT IN (SELECT user_id FROM user_roles WHERE role_id = 1)
            GROUP BY u.id
            HAVING perm_count > 10
        """)
        
        for row in cursor.fetchall():
            excessive.append({
                'user_id': row[0],
                'username': row[1],
                'display_name': row[2],
                'perm_count': row[3],
                'reason': f'非管理员用户拥有 {row[3]} 个数据权限'
            })
        
        return excessive

    def generate_audit_report(self) -> Dict[str, Any]:
        """
        生成权限审计报告
        """
        report = {
            'generated_at': datetime.now().isoformat(),
            'stats': self.get_permission_usage_stats(),
            'orphan_permissions': self.find_orphan_permissions(),
            'excessive_permissions': self.find_excessive_permissions(),
            'recommendations': []
        }
        
        # 生成建议
        if report['orphan_permissions']:
            report['recommendations'].append({
                'type': 'cleanup',
                'message': f"发现 {len(report['orphan_permissions'])} 条孤立权限记录，建议清理"
            })
        
        if report['excessive_permissions']:
            report['recommendations'].append({
                'type': 'review',
                'message': f"发现 {len(report['excessive_permissions'])} 个用户拥有过多权限，建议审查"
            })
        
        return report
