# -*- coding: utf-8 -*-
"""
Owner 转移服务

Salesforce 对标：Change Record Owner

功能：
1. transfer_ownership(): 单记录 Owner 转移
2. bulk_transfer(): 批量转移（人员离职/转岗场景）
3. get_transfer_history(): 获取转移历史
4. validate_transfer(): 转移前校验

设计原则：
- YAML 驱动：仅 allow_transfer: true 的对象支持转移
- 权限保留：transfer_keep_permissions 控制旧 Owner 权限去留
- 审计追溯：所有转移记录写入 owner_transfer_log 表
- 原子操作：转移在一个事务内完成

Usage:
    from meta.services.owner_transfer_service import OwnerTransferService
    
    ds = get_data_source('sqlite', database=db_path)
    svc = OwnerTransferService(ds)
    
    result = svc.transfer_ownership(
        resource_type='product', resource_id=42,
        from_user_id=1, to_user_id=2,
        admin_user_id=3
    )
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from meta.core.models import registry

logger = logging.getLogger(__name__)


class OwnerTransferService:

    def __init__(self, data_source):
        self._ds = data_source

    def validate_transfer(self, resource_type: str, resource_id: int,
                          from_user_id: int, to_user_id: int) -> Dict:
        """转移前校验
        
        返回：
        - is_valid: 是否允许转移
        - errors: 错误列表
        - warnings: 警告列表
        """
        errors = []
        warnings = []

        meta_obj = registry.get(resource_type)
        if not meta_obj:
            errors.append(f'BO {resource_type} 不存在')
            return {'is_valid': False, 'errors': errors, 'warnings': warnings}

        auth_config = meta_obj.authorization
        allow_transfer = True
        if isinstance(auth_config, dict):
            allow_transfer = auth_config.get('allow_transfer', False)
        elif hasattr(auth_config, 'allow_transfer'):
            allow_transfer = auth_config.allow_transfer

        if not allow_transfer:
            errors.append(f'BO {resource_type} 不支持 Owner 转移')
            return {'is_valid': False, 'errors': errors, 'warnings': warnings}

        if from_user_id == to_user_id:
            errors.append('源用户和目标用户相同')
            return {'is_valid': False, 'errors': errors, 'warnings': warnings}

        table = self._get_table_name(resource_type)
        if not table:
            errors.append(f'无法找到表 {resource_type}')
            return {'is_valid': False, 'errors': errors, 'warnings': warnings}

        try:
            cursor = self._ds.execute(
                f"SELECT id, owner_id FROM {table} WHERE id = ?", [resource_id]
            )
            row = cursor.fetchone()
            if not row:
                errors.append(f'记录 {resource_id} 不存在')
                return {'is_valid': False, 'errors': errors, 'warnings': warnings}

            current_owner = row[1] if isinstance(row, tuple) else row.get('owner_id')
            if current_owner != from_user_id:
                warnings.append(f'当前 owner_id={current_owner} 与传入 from_user_id={from_user_id} 不一致')
        except Exception as e:
            errors.append(f'查询记录失败: {e}')
            return {'is_valid': False, 'errors': errors, 'warnings': warnings}

        try:
            cursor = self._ds.execute(
                "SELECT id FROM users WHERE id = ?", [to_user_id]
            )
            if not cursor.fetchone():
                errors.append(f'目标用户 {to_user_id} 不存在')
                return {'is_valid': False, 'errors': errors, 'warnings': warnings}
        except Exception:
            pass

        return {
            'is_valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
        }

    def transfer_ownership(self, resource_type: str, resource_id: int,
                           from_user_id: int, to_user_id: int,
                           admin_user_id: int = None,
                           keep_original_permissions: bool = None) -> Dict:
        """单记录 Owner 转移
        
        Salesforce 对标：Change Record Owner
        
        参数：
        - resource_type: BO ID
        - resource_id: 记录 ID
        - from_user_id: 原 Owner
        - to_user_id: 新 Owner
        - admin_user_id: 操作人（审计用）
        - keep_original_permissions: 是否保留原 Owner 权限（None=读取 YAML 配置）
        
        返回：
        - success: 是否成功
        - transfer_id: 转移记录 ID
        - old_owner: 原 Owner 信息
        - new_owner: 新 Owner 信息
        - permissions_kept: 保留的旧权限数
        """
        validation = self.validate_transfer(
            resource_type, resource_id, from_user_id, to_user_id
        )
        if not validation['is_valid']:
            return {
                'success': False,
                'error': '; '.join(validation['errors']),
                'validation': validation,
            }

        meta_obj = registry.get(resource_type)
        if keep_original_permissions is None:
            auth_config = meta_obj.authorization if meta_obj else None
            if isinstance(auth_config, dict):
                keep_original_permissions = auth_config.get('transfer_keep_permissions', True)
            elif hasattr(auth_config, 'transfer_keep_permissions'):
                keep_original_permissions = auth_config.transfer_keep_permissions
            else:
                keep_original_permissions = True

        table = self._get_table_name(resource_type)

        with self._ds.transaction():
            self._ds.execute(
                f"UPDATE {table} SET owner_id = ? WHERE id = ?",
                [to_user_id, resource_id]
            )

            auto_source_ids = self._revoke_auto_permissions(
                from_user_id, resource_type, resource_id
            )

            self._grant_owner_permissions(
                to_user_id, resource_type, resource_id, meta_obj
            )

            permissions_kept = 0
            if keep_original_permissions and auto_source_ids:
                permissions_kept = self._keep_read_write_permissions(
                    auto_source_ids, resource_type, resource_id
                )

            log_id = self._log_transfer(
                resource_type, resource_id,
                from_user_id, to_user_id, admin_user_id,
                permissions_kept
            )

        return {
            'success': True,
            'transfer_id': log_id,
            'old_owner': {'user_id': from_user_id, 'permissions_revoked': len(auto_source_ids)},
            'new_owner': {'user_id': to_user_id, 'permissions_granted': 'admin'},
            'permissions_kept': permissions_kept,
            'message': f'Owner 已从 {from_user_id} 转移到 {to_user_id}',
        }

    def bulk_transfer(self, resource_type: str, from_user_id: int,
                      to_user_id: int, admin_user_id: int = None) -> Dict:
        """批量转移（人员离职/转岗场景）
        
        参数：
        - resource_type: BO ID
        - from_user_id: 原 Owner
        - to_user_id: 新 Owner
        - admin_user_id: 操作人
        
        返回：
        - total: 总记录数
        - transferred: 转移成功数
        - failed: 失败数
        - details: 详情列表
        """
        table = self._get_table_name(resource_type)
        if not table:
            return {'success': False, 'error': f'无法找到表 {resource_type}'}

        try:
            cursor = self._ds.execute(
                f"SELECT id FROM {table} WHERE owner_id = ?", [from_user_id]
            )
            resource_ids = [row[0] if isinstance(row, tuple) else row['id'] 
                           for row in cursor.fetchall()]
        except Exception as e:
            return {'success': False, 'error': f'查询记录失败: {e}'}

        transferred = []
        failed = []

        for rid in resource_ids:
            result = self.transfer_ownership(
                resource_type, rid, from_user_id, to_user_id, admin_user_id
            )
            if result['success']:
                transferred.append({'resource_id': rid, 'transfer_id': result['transfer_id']})
            else:
                failed.append({'resource_id': rid, 'error': result.get('error')})

        return {
            'success': True,
            'total': len(resource_ids),
            'transferred': len(transferred),
            'failed': len(failed),
            'details': {'transferred': transferred, 'failed': failed},
        }

    def get_transfer_history(self, resource_type: str = None,
                              resource_id: int = None,
                              user_id: int = None,
                              limit: int = 50) -> List[Dict]:
        """获取转移历史
        
        参数：
        - resource_type: 按 BO 过滤（可选）
        - resource_id: 按记录过滤（可选）
        - user_id: 按用户过滤（可选，包含 from_user 和 to_user）
        - limit: 返回数量
        
        返回：
        - transfers: 转移记录列表
        """
        query = "SELECT * FROM owner_transfer_log WHERE 1=1"
        params = []

        if resource_type:
            query += " AND resource_type = ?"
            params.append(resource_type)
        if resource_id:
            query += " AND resource_id = ?"
            params.append(resource_id)
        if user_id:
            query += " AND (from_user_id = ? OR to_user_id = ?)"
            params.extend([user_id, user_id])

        query += " ORDER BY transferred_at DESC LIMIT ?"
        params.append(limit)

        try:
            cursor = self._ds.execute(query, params)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.warning(f'OwnerTransfer: get_transfer_history failed: {e}')
            return []

    def _ensure_transfer_log_table(self):
        """确保转移日志表存在"""
        try:
            self._ds.execute("""
                CREATE TABLE IF NOT EXISTS owner_transfer_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    resource_type VARCHAR(100) NOT NULL,
                    resource_id INTEGER NOT NULL,
                    from_user_id INTEGER NOT NULL,
                    to_user_id INTEGER NOT NULL,
                    admin_user_id INTEGER,
                    permissions_kept INTEGER DEFAULT 0,
                    transferred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        except Exception as e:
            logger.warning(f'OwnerTransfer: create log table failed: {e}')

    def _get_table_name(self, resource_type: str) -> Optional[str]:
        meta_obj = registry.get(resource_type)
        if meta_obj and getattr(meta_obj, 'table_name', None):
            return meta_obj.table_name
        return resource_type

    def _revoke_auto_permissions(self, user_id: int, resource_type: str,
                                  resource_id: int) -> List[int]:
        """撤销自动生成的权限"""
        try:
            cursor = self._ds.execute(
                """SELECT id FROM data_permissions 
                   WHERE user_id = ? AND resource_type = ? 
                   AND resource_id = ? AND auto_generated = 1""",
                [user_id, resource_type, resource_id]
            )
            ids = [row[0] if isinstance(row, tuple) else row['id'] 
                   for row in cursor.fetchall()]
            
            if ids:
                placeholders = ','.join(['?' for _ in ids])
                self._ds.execute(
                    f"DELETE FROM data_permissions WHERE id IN ({placeholders})",
                    ids
                )
            
            return ids
        except Exception as e:
            logger.warning(f'OwnerTransfer: revoke failed: {e}')
            return []

    def _grant_owner_permissions(self, user_id: int, resource_type: str,
                                  resource_id: int, meta_obj) -> None:
        """授予新 Owner admin 权限"""
        inherit = True
        auth_config = meta_obj.authorization if meta_obj else None
        if isinstance(auth_config, dict):
            inherit = auth_config.get('inherit_to_children', True)
        elif hasattr(auth_config, 'inherit_to_children'):
            inherit = auth_config.inherit_to_children

        try:
            self._ds.execute(
                """INSERT OR REPLACE INTO data_permissions 
                   (user_id, resource_type, resource_id, permission_level, 
                    inherit_to_children, auto_generated, created_at) 
                   VALUES (?, ?, ?, 'admin', ?, 1, CURRENT_TIMESTAMP)""",
                [user_id, resource_type, resource_id, inherit]
            )
        except Exception as e:
            logger.error(f'OwnerTransfer: grant failed: {e}')

    def _keep_read_write_permissions(self, auto_source_ids: List[int],
                                      resource_type: str,
                                      resource_id: int) -> int:
        """保留原 Owner 的 read 权限（从 admin 降级）"""
        count = 0
        try:
            for pid in auto_source_ids:
                cursor = self._ds.execute(
                    "SELECT user_id FROM data_permissions WHERE id = ?", [pid]
                )
                row = cursor.fetchone()
                if not row:
                    continue
                
                old_user_id = row[0] if isinstance(row, tuple) else row['user_id']
                
                self._ds.execute(
                    """INSERT OR IGNORE INTO data_permissions 
                       (user_id, resource_type, resource_id, permission_level,
                        inherit_to_children, auto_generated, created_at)
                       VALUES (?, ?, ?, 'read', 0, 0, CURRENT_TIMESTAMP)""",
                    [old_user_id, resource_type, resource_id]
                )
                count += 1
        except Exception as e:
            logger.warning(f'OwnerTransfer: keep permissions failed: {e}')

        return count

    def _log_transfer(self, resource_type: str, resource_id: int,
                      from_user_id: int, to_user_id: int,
                      admin_user_id: int, permissions_kept: int) -> int:
        self._ensure_transfer_log_table()
        try:
            cursor = self._ds.execute(
                """INSERT INTO owner_transfer_log 
                   (resource_type, resource_id, from_user_id, to_user_id, 
                    admin_user_id, permissions_kept, transferred_at) 
                   VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                [resource_type, resource_id, from_user_id, to_user_id,
                 admin_user_id, permissions_kept]
            )
            return cursor.lastrowid
        except Exception as e:
            logger.error(f'OwnerTransfer: log failed: {e}')
            return 0
