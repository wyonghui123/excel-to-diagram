# -*- coding: utf-8 -*-
"""
数据权限自动生成服务

从 BO YAML 元数据读取 data_permission_hints 和 authorization，
自动创建数据权限记录。

功能：
1. generate_on_create(): 创建记录后自动授予创建者权限
2. generate_default_permissions(): 从 YAML 推导默认权限
3. sync_all(): 批量同步数据权限
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime

from meta.core.models import registry

logger = logging.getLogger(__name__)


class DataPermissionGenerator:

    def __init__(self, data_source):
        self._ds = data_source

    def generate_on_create(self, meta_obj, resource_id: int, user_id: int) -> int:
        """创建记录后自动授予创建者权限
        
        参数：
        - meta_obj: BO 元数据对象
        - resource_id: 记录 ID
        - user_id: 创建者 user_id
        
        返回：
        - 创建的权限记录数
        """
        permissions = self.generate_default_permissions(meta_obj, user_id)
        if not permissions:
            return 0

        count = 0
        try:
            self._ds.execute(
                "ALTER TABLE data_permissions ADD COLUMN auto_generated INTEGER DEFAULT 0"
            )
        except Exception:
            pass

        existing = set()
        try:
            cursor = self._ds.execute(
                "SELECT user_id, resource_type, resource_id FROM data_permissions"
            )
            for row in cursor.fetchall():
                uid = row[0] if isinstance(row, tuple) else row.get('user_id')
                rtype = row[1] if isinstance(row, tuple) else row.get('resource_type')
                rid = row[2] if isinstance(row, tuple) else row.get('resource_id')
                existing.add((uid, rtype, rid))
        except Exception:
            pass

        for perm in permissions:
            pk = (perm['user_id'], perm['resource_type'], perm['resource_id'])
            if pk in existing:
                continue

            try:
                self._ds.execute(
                    """INSERT OR IGNORE INTO data_permissions
                       (user_id, resource_type, resource_id, permission_level,
                        inherit_to_children, auto_generated, created_at)
                       VALUES (?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)""",
                    [
                        perm['user_id'],
                        perm['resource_type'],
                        resource_id,
                        perm.get('permission_level', 'admin'),
                        perm.get('inherit_to_children', True)
                    ]
                )
                count += 1
            except Exception as e:
                logger.warning(f"[DataPermGen] insert failed for {perm}: {e}")

        if count > 0:
            logger.info(f"[DataPermGen] created {count} auto_permissions for user={user_id} on {meta_obj.id}:{resource_id}")

        return count

    def generate_default_permissions(self, meta_obj, user_id: int) -> List[Dict]:
        """从 BO YAML 元数据推导默认数据权限
        
        读取优先级：
        1. authorization.auto_permission - 主授权配置
        2. data_permission_hints.auto_grant - 隐式权限提示
        
        参数：
        - meta_obj: BO 元数据对象
        - user_id: 授予用户 ID
        
        返回：
        - 权限记录列表
        """
        permissions = []

        auto_perm = None
        inherit = True

        auth_config = None
        if isinstance(meta_obj.authorization, dict):
            auth_config = meta_obj.authorization
        elif hasattr(meta_obj, 'authorization') and meta_obj.authorization:
            auth_config = meta_obj.authorization

        if auth_config:
            auto_perm = auth_config.get('auto_permission') or ''
            inherit = auth_config.get('inherit_to_children', True)

        if not auto_perm:
            hints = getattr(meta_obj, 'data_permission_hints', None)
            if isinstance(hints, dict):
                auto_perm = hints.get('auto_permission', '')

        if not auto_perm:
            return permissions

        resource_types = [meta_obj.id]

        hints = getattr(meta_obj, 'data_permission_hints', None)
        if isinstance(hints, dict):
            hint_types = hints.get('resource_types')
            if hint_types:
                resource_types = hint_types

        for rt in resource_types:
            permissions.append({
                'user_id': user_id,
                'resource_type': rt,
                'resource_id': None,
                'permission_level': auto_perm,
                'inherit_to_children': inherit,
                'auto_generated': True,
                'reason': f"auto_permission from {meta_obj.id}.yaml"
            })

        return permissions

    def sync_all(self, user_id: int = None) -> Dict:
        """批量同步所有 BO 的数据权限定义
        
        参数：
        - user_id: 仅为此用户同步（可选）

        返回：
        - synced: 同步的 BO 数
        - total: 总 BO 数
        - skipped: 跳过的 BO 数（无 auto_permission 声明）
        """
        synced = []
        skipped = []
        errors = []

        for obj_id, obj in registry.get_all().items():
            if obj_id.startswith('_'):
                continue

            has_auto = False
            auth_config = None
            if isinstance(obj.authorization, dict):
                auth_config = obj.authorization
            elif hasattr(obj, 'authorization') and obj.authorization:
                auth_config = obj.authorization

            if auth_config and auth_config.get('auto_permission'):
                has_auto = True

            if not has_auto:
                hints = getattr(obj, 'data_permission_hints', None)
                if isinstance(hints, dict) and hints.get('auto_permission'):
                    has_auto = True

            if has_auto:
                synced.append({
                    'object_id': obj_id,
                    'object_name': obj.name,
                    'auto_permission': auth_config.get('auto_permission') if auth_config else 'admin',
                    'inherit_to_children': auth_config.get('inherit_to_children', True) if auth_config else True,
                })
            else:
                skipped.append(obj_id)

        return {
            'synced': synced,
            'synced_count': len(synced),
            'skipped': skipped,
            'skipped_count': len(skipped),
            'total': len(synced) + len(skipped),
            'generated_at': datetime.now().isoformat(),
        }
