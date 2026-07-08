# -*- coding: utf-8 -*-
"""
权限同步服务

系统启动时或YAML变更时，自动从 MetaRegistry 扫描所有 BO 的 actions
和 category_config，同步权限记录到 permissions 表。

功能：
1. sync_all(): 全量同步，从所有 YAML actions 同步到 permissions 表
2. sync_for_object(): 增量同步，同步单个 BO 的权限
3. validate_consistency(): 一致性校验，检查 YAML actions 与 permissions 表的一致性

Usage:
    from meta.services.permission_sync_service import get_permission_sync_service
    
    ds = get_data_source('sqlite', database=db_path)
    svc = get_permission_sync_service(ds)
    
    # 全量同步
    result = svc.sync_all()
    
    # 一致性校验
    validation = svc.validate_consistency()
"""

import logging
from typing import Dict, List, Set, Optional, Tuple
from datetime import datetime
from pathlib import Path

from meta.core.models import MetaObject, MetaAction, registry

logger = logging.getLogger(__name__)


class PermissionSyncService:

    _last_synced_mtime = None

    def __init__(self, data_source):
        self._ds = data_source

    def _is_connected(self) -> bool:
        """检查数据库连接是否有效"""
        try:
            if hasattr(self._ds, 'is_connected'):
                return self._ds.is_connected
            return True
        except Exception:
            return False

    def _schema_mtime_changed(self) -> bool:
        """检查 meta/schemas/ 目录下是否有任何 .yaml 文件的 mtime 晚于上次同步"""
        try:
            from meta.core.yaml_loader import get_yaml_schema_dir
            schema_dir = Path(get_yaml_schema_dir())
            if not schema_dir.exists():
                return True
            max_mtime = 0.0
            for yaml_file in schema_dir.glob("*.yaml"):
                try:
                    mtime = yaml_file.stat().st_mtime
                    if mtime > max_mtime:
                        max_mtime = mtime
                except Exception:
                    pass
            if max_mtime == 0.0:
                return True
            if self._last_synced_mtime is None or max_mtime > self._last_synced_mtime:
                self._last_synced_mtime = max_mtime
                return True
            return False
        except Exception:
            return True

    def mark_synced(self):
        """标记当前同步完成，记录最新 mtime"""
        try:
            from meta.core.yaml_loader import get_yaml_schema_dir
            schema_dir = Path(get_yaml_schema_dir())
            if not schema_dir.exists():
                return
            max_mtime = 0.0
            for yaml_file in schema_dir.glob("*.yaml"):
                try:
                    mtime = yaml_file.stat().st_mtime
                    if mtime > max_mtime:
                        max_mtime = mtime
                except Exception:
                    pass
            if max_mtime > 0.0:
                self._last_synced_mtime = max_mtime
        except Exception:
            pass

    def sync_all(self) -> Dict:
        """全量同步：从所有 YAML actions 同步到 permissions 表
        
        返回：
        - created: 新创建的权限编码列表
        - updated: 更新的权限编码列表
        - existing: 已存在且无需更新的权限编码列表
        - orphaned: 孤儿权限（在 DB 中但不在 YAML 中）
        - summary: 汇总信息
        """
        if not self._is_connected():
            logger.warning("[PermissionSync] Database not connected, skipping sync_all")
            return {
                'created': [],
                'updated': [],
                'existing': [],
                'orphaned': [],
                'summary': {
                    'total_expected': 0,
                    'total_existing': 0,
                    'created_count': 0,
                    'updated_count': 0,
                    'orphaned_count': 0,
                    'synced_at': datetime.now().isoformat(),
                    'skipped': True,
                }
            }
        
        expected = self._collect_all_permissions()
        existing = self._load_existing_permissions()

        to_create = expected - existing
        to_update = expected & existing
        orphaned = existing - expected

        existing_details = self._load_existing_details()

        created = []
        for code in to_create:
            resource_type, suffix = self._parse_code(code)
            name = self._generate_label(resource_type, suffix)
            try:
                if self._is_connected():
                    self._ds.execute(
                        "INSERT OR IGNORE INTO permissions (code, name, resource_type, action) "
                        "VALUES (?, ?, ?, ?)",
                        [code, name, resource_type, suffix]
                    )
                    created.append(code)
                    logger.info("[PermissionSync] created: %s", code)
            except Exception as e:
                if "closed database" not in str(e).lower():
                    logger.error("[PermissionSync] failed to create %s: %s", code, e)

        updated = []
        for code in to_update:
            resource_type, suffix = self._parse_code(code)
            name = self._generate_label(resource_type, suffix)
            db_row = existing_details.get(code)
            if db_row and (db_row[0] != name or db_row[1] != resource_type or db_row[2] != suffix):
                try:
                    if self._is_connected():
                        self._ds.execute(
                            "UPDATE permissions SET name = ?, resource_type = ?, action = ? WHERE code = ?",
                            [name, resource_type, suffix, code]
                        )
                        updated.append(code)
                except Exception as e:
                    if "closed database" not in str(e).lower():
                        logger.error("[PermissionSync] failed to update %s: %s", code, e)

        if orphaned:
            logger.warning("[PermissionSync] orphaned permissions detected: %s", orphaned)

        return {
            'created': created,
            'updated': updated,
            'existing': list(to_update - set(updated)),
            'orphaned': list(orphaned),
            'summary': {
                'total_expected': len(expected),
                'total_existing': len(existing),
                'created_count': len(created),
                'updated_count': len(updated),
                'orphaned_count': len(orphaned),
                'synced_at': datetime.now().isoformat(),
            }
        }
        self.mark_synced()
        return result

    def sync_for_object(self, object_id: str) -> Dict:
        """增量同步：同步单个 BO 的权限
        
        参数：
        - object_id: BO ID
        
        返回：
        - created: 新创建的权限编码列表
        - existing: 已存在的权限编码列表
        - total: 总权限数
        """
        meta_obj = registry.get(object_id)
        if not meta_obj:
            return {'error': f'Object not found: {object_id}', 'created': [], 'existing': [], 'total': 0}

        perms = self._derive_from_object(meta_obj)
        existing = self._load_existing_permissions()
        
        created = []
        already_exists = []
        
        for code in perms:
            resource_type, suffix = self._parse_code(code)
            name = self._generate_label(resource_type, suffix)
            
            if code in existing:
                already_exists.append(code)
            else:
                try:
                    if self._is_connected():
                        self._ds.execute(
                            "INSERT OR IGNORE INTO permissions (code, name, resource_type, action) "
                            "VALUES (?, ?, ?, ?)",
                            [code, name, resource_type, suffix]
                        )
                        created.append(code)
                        logger.info("[PermissionSync] created for %s: %s", object_id, code)
                except Exception as e:
                    if "closed database" not in str(e).lower():
                        logger.error("[PermissionSync] failed to create %s: %s", code, e)

        result = {
            'object_id': object_id,
            'created': created,
            'existing': already_exists,
            'total': len(perms),
            'summary': {
                'created_count': len(created),
                'existing_count': len(already_exists),
                'synced_at': datetime.now().isoformat(),
            }
        }
        self.mark_synced()
        return result

    def validate_consistency(self) -> Dict:
        """一致性校验：检查 YAML actions 与 permissions 表的一致性
        
        返回：
        - is_consistent: 是否一致
        - missing_permissions: 缺失的权限（在 YAML 中但不在 DB 中）
        - extra_permissions: 多余的权限（在 DB 中但不在 YAML 中）
        - expected_count: 期望的权限数
        - existing_count: 实际的权限数
        - details: 详细信息
        """
        expected = self._collect_all_permissions()
        existing = self._load_existing_permissions()

        missing = expected - existing
        extra = existing - expected

        is_consistent = len(missing) == 0

        details = {}
        if missing:
            details['missing_by_object'] = self._group_permissions_by_object(missing)
        if extra:
            details['extra_by_object'] = self._group_permissions_by_object(extra)

        return {
            'is_consistent': is_consistent,
            'missing_permissions': list(missing),
            'extra_permissions': list(extra),
            'expected_count': len(expected),
            'existing_count': len(existing),
            'missing_count': len(missing),
            'extra_count': len(extra),
            'details': details,
            'validated_at': datetime.now().isoformat(),
        }

    def get_permission_report(self) -> Dict:
        """获取权限报告：汇总所有 BO 的权限定义情况
        
        返回：
        - objects: 各 BO 的权限定义情况
        - total_actions: 总 action 数
        - total_permissions: 总权限数
        """
        objects = []
        total_actions = 0
        total_permissions = 0

        existing = self._load_existing_permissions()

        for obj_id, obj in registry.get_all().items():
            if obj_id.startswith('_'):
                continue

            perms = self._derive_from_object(obj)
            
            obj_report = {
                'object_id': obj_id,
                'object_name': obj.name,
                'action_count': len(obj.actions),
                'permission_codes': perms,
                'permissions_in_db': [p for p in perms if p in existing],
                'permissions_missing': [p for p in perms if p not in existing],
                'is_synced': all(p in existing for p in perms),
            }
            
            objects.append(obj_report)
            total_actions += len(obj.actions)
            total_permissions += len(perms)

        return {
            'objects': objects,
            'total_objects': len(objects),
            'total_actions': total_actions,
            'total_permissions': total_permissions,
            'generated_at': datetime.now().isoformat(),
        }

    def _load_existing_details(self) -> Dict[str, Tuple[str, str, str]]:
        """批量加载所有权限的详细信息 (code -> (name, resource_type, action))"""
        try:
            if not self._is_connected():
                return {}
            cursor = self._ds.execute(
                "SELECT code, name, resource_type, action FROM permissions"
            )
            return {row[0]: (row[1], row[2], row[3]) for row in cursor.fetchall()}
        except Exception as e:
            if "closed database" in str(e).lower():
                return {}
            logger.warning("[PermissionSync] Failed to load existing permission details: %s", e)
            return {}

    def _needs_update(self, code: str, name: str, resource_type: str, action: str) -> bool:
        """检查权限是否需要更新（已弃用，保留兼容）"""
        try:
            cursor = self._ds.execute(
                "SELECT name, resource_type, action FROM permissions WHERE code = ?",
                [code]
            )
            row = cursor.fetchone()
            if row:
                return row[0] != name or row[1] != resource_type or row[2] != action
        except Exception:
            pass
        return False

    def _group_permissions_by_object(self, permissions: Set[str]) -> Dict[str, List[str]]:
        """按对象分组权限"""
        grouped = {}
        for perm in permissions:
            if perm == '*':
                continue
            resource_type, _ = self._parse_code(perm)
            if resource_type not in grouped:
                grouped[resource_type] = []
            grouped[resource_type].append(perm)
        return grouped

    def _collect_all_permissions(self) -> Set[str]:
        all_perms = {'*'}
        for obj_id, obj in registry.get_all().items():
            if obj_id.startswith('_'):
                continue
            perms = self._derive_from_object(obj)
            all_perms.update(perms)
        return all_perms

    def _derive_from_object(self, obj: MetaObject) -> List[str]:
        perms = []
        for action in obj.actions:
            perms.append(action.get_permission_code(obj.id))
        return perms

    def _load_existing_permissions(self) -> Set[str]:
        try:
            if not self._is_connected():
                return set()
            cursor = self._ds.execute("SELECT code FROM permissions")
            return {row[0] for row in cursor.fetchall()}
        except Exception as e:
            if "closed database" in str(e).lower():
                return set()
            logger.warning("[PermissionSync] Failed to load existing permissions: %s", e)
            return set()

    @staticmethod
    def _parse_code(code: str) -> Tuple[str, str]:
        if code == '*':
            return '*', '*'
        parts = code.split(':')
        return (parts[0], parts[1]) if len(parts) > 1 else (code, 'all')

    def _generate_label(self, resource_type: str, suffix: str) -> str:
        if resource_type == '*':
            return '\u8d85\u7ea7\u6743\u9650'
        meta_obj = registry.get(resource_type)
        if meta_obj:
            return meta_obj.get_permission_label(suffix)
        return f"{resource_type}:{suffix}"


_instance = None


def get_permission_sync_service(data_source=None):
    global _instance
    if _instance is None and data_source:
        _instance = PermissionSyncService(data_source)
    return _instance
