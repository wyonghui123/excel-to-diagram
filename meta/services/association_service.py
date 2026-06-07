# -*- coding: utf-8 -*-
"""
元模型驱动的通用关联操作服务

提供标准化的 ASSIGN/REVOKE/LIST 操作，对齐 OData 标准：
- assign: POST /$links/nav (创建关联)
- unassign: DELETE /$links/nav (移除关联)
- list: GET /$expand=nav (查询成员)
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

# [DECORATIVE] v3.18: trace_id 支持
try:
    from meta.core.trace_id import TraceId
    _trace_id_available = True
except ImportError:
    _trace_id_available = False

logger = logging.getLogger(__name__)


class AssociationService:
    """
    通用关联操作服务

    支持多对多和一对多/多对一关系的统一管理。
    """

    def __init__(self, data_source, schema_registry=None):
        self.data_source = data_source
        self.schema_registry = schema_registry
        from meta.services.audit_interceptor import AuditInterceptor
        self.audit_interceptor = AuditInterceptor(data_source)

    def get_association(self, source_type: str, association_name: str) -> Optional[Any]:
        """从元模型获取关联定义"""
        # [DECORATIVE] v3.18: 记录 trace_id 到日志
        if _trace_id_available:
            logger.debug(f"[AssociationService] get_association trace_id={TraceId.get()} type={source_type}")

        if not self.schema_registry:
            return None

        obj = None
        if hasattr(self.schema_registry, 'get'):
            try:
                obj = self.schema_registry.get(source_type)
            except Exception:
                pass

        if obj:
            associations = getattr(obj, 'associations', None) or getattr(obj, '_associations', None)
            if associations and association_name in associations:
                return associations[association_name]
        return None

    def get_table_name(self, entity_type: str) -> str:
        """获取实体表名"""
        if self.schema_registry and hasattr(self.schema_registry, 'get'):
            try:
                obj = self.schema_registry.get(entity_type)
                if obj and hasattr(obj, 'table_name') and obj.table_name:
                    return obj.table_name
            except Exception:
                pass
        return f"{entity_type}s"

    def association_exists(self, source_type: str, source_id: int,
                          target_type: str, target_id: int,
                          association) -> bool:
        """检查关联是否已存在"""
        if not association:
            return False

        assoc_type = getattr(association, 'type', 'many_to_many')

        if assoc_type == 'many_to_many':
            through = getattr(association, 'through', None)
            if not through:
                return False
            source_key = getattr(association, 'source_key', f'{source_type}_id')
            target_key = getattr(association, 'target_key', f'{target_type}_id')

            sql = f"SELECT 1 FROM {through} WHERE {source_key} = ? AND {target_key} = ? LIMIT 1"
            cursor = self.data_source.execute(sql, [source_id, target_id])
            return cursor.fetchone() is not None

        elif assoc_type in ('one_to_many', 'many_to_one'):
            target_table = self.get_table_name(target_type)
            target_key = getattr(association, 'target_key', f'{source_type}_id')

            sql = f"SELECT 1 FROM {target_table} WHERE id = ? AND {target_key} = ? LIMIT 1"
            cursor = self.data_source.execute(sql, [target_id, source_id])
            return cursor.fetchone() is not None

        return False

    def create_association(self, source_type: str, source_id: int,
                          target_type: str, target_id: int,
                          association) -> bool:
        """创建关联记录"""
        if not association:
            return False

        assoc_type = getattr(association, 'type', 'many_to_many')

        if assoc_type == 'many_to_many':
            through = getattr(association, 'through', None)
            if not through:
                return False
            source_key = getattr(association, 'source_key', f'{source_type}_id')
            target_key = getattr(association, 'target_key', f'{target_type}_id')

            self.data_source.execute(
                f"INSERT INTO {through} ({source_key}, {target_key}) VALUES (?, ?)",
                [source_id, target_id]
            )
            return True

        elif assoc_type in ('one_to_many', 'many_to_one'):
            target_table = self.get_table_name(target_type)
            target_key = getattr(association, 'target_key', f'{source_type}_id')

            self.data_source.execute(
                f"UPDATE {target_table} SET {target_key} = ? WHERE id = ?",
                [source_id, target_id]
            )
            return True

        return False

    def delete_association(self, source_type: str, source_id: int,
                          target_type: str, target_id: int,
                          association) -> bool:
        """删除关联记录"""
        if not association:
            return False

        assoc_type = getattr(association, 'type', 'many_to_many')

        if assoc_type == 'many_to_many':
            through = getattr(association, 'through', None)
            if not through:
                return False
            source_key = getattr(association, 'source_key', f'{source_type}_id')
            target_key = getattr(association, 'target_key', f'{target_type}_id')

            self.data_source.execute(
                f"DELETE FROM {through} WHERE {source_key} = ? AND {target_key} = ?",
                [source_id, target_id]
            )
            return True

        elif assoc_type in ('one_to_many', 'many_to_one'):
            target_table = self.get_table_name(target_type)
            target_key = getattr(association, 'target_key', f'{source_type}_id')

            self.data_source.execute(
                f"UPDATE {target_table} SET {target_key} = NULL WHERE id = ?",
                [target_id]
            )
            return True

        return False

    def assign(self, source_type: str, source_id: int,
               target_type: str, target_id: int,
               operator_id: int = 0, operator_name: str = "system",
               association_name: str = None) -> Dict[str, Any]:
        """
        分配/创建关联操作

        对应 OData: POST /Entity(id)/$links/NavigationProperty
        """
        association = self.get_association(source_type, association_name)

        if not association:
            return {'success': False, 'message': f'未找到关联定义: {association_name}'}

        # 检查是否已存在
        if self.association_exists(source_type, source_id, target_type, target_id, association):
            return {'success': False, 'message': '关联已存在'}

        # 创建关联
        if not self.create_association(source_type, source_id, target_type, target_id, association):
            return {'success': False, 'message': '创建关联失败'}

        # 写入审计日志
        self._write_audit_log('ASSOCIATE', source_type, source_id,
                             target_type, target_id, operator_id, operator_name,
                             association_name=association_name)

        logger.info(f"[Association] Assigned {target_type}/{target_id} to {source_type}/{source_id}")
        return {'success': True, 'message': '分配成功'}

    def unassign(self, source_type: str, source_id: int,
                 target_type: str, target_id: int,
                 operator_id: int = 0, operator_name: str = "system",
                 association_name: str = None) -> Dict[str, Any]:
        """
        取消关联操作

        对应 OData: DELETE /Entity(id)/$links/NavigationProperty
        """
        association = self.get_association(source_type, association_name)

        if not association:
            return {'success': False, 'message': f'未找到关联定义: {association_name}'}

        # 检查关联是否存在
        if not self.association_exists(source_type, source_id, target_type, target_id, association):
            return {'success': False, 'message': '关联不存在'}

        # 删除关联
        if not self.delete_association(source_type, source_id, target_type, target_id, association):
            return {'success': False, 'message': '取消关联失败'}

        # 写入审计日志
        self._write_audit_log('DISSOCIATE', source_type, source_id,
                             target_type, target_id, operator_id, operator_name,
                             association_name=association_name)

        logger.info(f"[Association] Unassigned {target_type}/{target_id} from {source_type}/{source_id}")
        return {'success': True, 'message': '已取消分配'}

    def list_members(self, source_type: str, source_id: int,
                     association_name: str = None,
                     page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """
        查询关联成员列表

        对应 OData: GET /Entity(id)/$expand=NavigationProperty
        """
        association = self.get_association(source_type, association_name)

        if not association:
            return {'success': False, 'message': f'未找到关联定义: {association_name}', 'data': []}

        assoc_type = getattr(association, 'type', 'many_to_many')
        target_entity = getattr(association, 'target_entity', '')

        if not target_entity:
            return {'success': False, 'message': '关联定义缺少目标实体', 'data': []}

        target_table = self.get_table_name(target_entity)
        offset = (page - 1) * page_size

        if assoc_type == 'many_to_many':
            through = getattr(association, 'through', '')
            source_key = getattr(association, 'source_key', f'{source_type}_id')
            target_key = getattr(association, 'target_key', f'{target_entity}_id')

            count_sql = f"""
                SELECT COUNT(*) as cnt FROM {target_table} t
                INNER JOIN {through} j ON t.id = j.{target_key}
                WHERE j.{source_key} = ?
            """
            data_sql = f"""
                SELECT t.* FROM {target_table} t
                INNER JOIN {through} j ON t.id = j.{target_key}
                WHERE j.{source_key} = ?
                ORDER BY t.id
                LIMIT ? OFFSET ?
            """

            count_cursor = self.data_source.execute(count_sql, [source_id])
            count_result = count_cursor.fetchone()
            total = count_result[0] if count_result else 0

            data_cursor = self.data_source.execute(data_sql, [source_id, page_size, offset])
            members = [dict(r) for r in data_cursor.fetchall()]

            return {
                'success': True,
                'data': members,
                'total': total,
                'page': page,
                'page_size': page_size,
            }

        elif assoc_type in ('one_to_many', 'many_to_one'):
            target_key = getattr(association, 'target_key', f'{source_type}_id')

            count_sql = f"SELECT COUNT(*) as cnt FROM {target_table} WHERE {target_key} = ?"
            data_sql = f"SELECT * FROM {target_table} WHERE {target_key} = ? ORDER BY id LIMIT ? OFFSET ?"

            count_cursor = self.data_source.execute(count_sql, [source_id])
            total_row = count_cursor.fetchone()
            total = total_row['cnt'] if total_row else 0

            data_cursor = self.data_source.execute(data_sql, [source_id, page_size, offset])
            members = [dict(r) for r in data_cursor.fetchall()]

            return {
                'success': True,
                'data': members,
                'total': total,
                'page': page,
                'page_size': page_size,
            }

        return {'success': True, 'data': [], 'total': 0, 'page': page, 'page_size': page_size}

    def _write_audit_log(self, action: str, source_type: str, source_id: int,
                        target_type: str, target_id: int,
                        operator_id: int, operator_name: str,
                        association_name: str = None):
        """写入审计日志，使用正确的 ASSOCIATE/DISSOCIATE action"""
        try:
            assoc_name = association_name or source_type
            if action == 'ASSOCIATE':
                self.audit_interceptor.log_associate(
                    object_type=source_type,
                    object_id=source_id,
                    tgt_type=target_type,
                    tgt_id=target_id,
                    association_name=assoc_name,
                    user_id=str(operator_id) if operator_id else None,
                    user_name=operator_name,
                )
            elif action == 'DISSOCIATE':
                self.audit_interceptor.log_dissociate(
                    object_type=source_type,
                    object_id=source_id,
                    tgt_type=target_type,
                    tgt_id=target_id,
                    association_name=assoc_name,
                    user_id=str(operator_id) if operator_id else None,
                    user_name=operator_name,
                )
            else:
                logger.warning(f"[Audit] Unknown audit action: {action}")
            logger.info(f"[Audit] Logged {action}: {source_type}/{source_id} -> {target_type}/{target_id} via {assoc_name}")
        except Exception as e:
            logger.error(f"[Audit] Failed to write association log: {e}")
