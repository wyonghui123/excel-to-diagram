# -*- coding: utf-8 -*-
"""
元模型驱动的通用删除服务

支持声明式删除策略：
- RESTRICT: 存在强依赖时拒绝删除
- CASCADE: 自动清理关联记录
- SOFT_DELETE: 软删除模式
- POLYMORPHIC_CASCADE: 多态关联反向级联删除
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DeletionService:
    """
    通用删除服务 - 基于元模型策略自动执行删除
    
    使用方式:
        service = DeletionService(data_source, schema_registry)
        result = service.delete('user', 21, operator_id=1, operator_name='admin')
    """
    
    def __init__(self, data_source, schema_registry=None):
        self.data_source = data_source
        self.schema_registry = schema_registry
        from meta.services.audit_interceptor import AuditInterceptor
        self.audit_interceptor = AuditInterceptor(data_source)
    
    def get_deletion_policy(self, entity_type: str) -> Optional[Any]:
        """从 schema registry 获取实体的删除策略"""
        if not self.schema_registry:
            return None
        
        obj = None
        if hasattr(self.schema_registry, 'get'):
            try:
                obj = self.schema_registry.get(entity_type)
            except Exception:
                pass
        
        if obj and hasattr(obj, '_deletion_policy'):
            return obj._deletion_policy
        return None
    
    def get_table_name(self, entity_type: str) -> str:
        """获取实体对应的数据库表名"""
        if self.schema_registry and hasattr(self.schema_registry, 'get'):
            try:
                obj = self.schema_registry.get(entity_type)
                if obj and hasattr(obj, 'table_name') and obj.table_name:
                    return obj.table_name
            except Exception:
                pass
        return f"{entity_type}s"
    
    def check_restrict_rules(self, entity_type: str, entity_id: int, policy) -> List[Dict]:
        """
        检查 RESTRICT 规则
        
        Returns:
            违规列表，每个元素包含 {table, foreign_key, message, count}
        """
        violations = []
        
        if not policy or not getattr(policy, 'restrict_on', None):
            return violations
        
        for rule in policy.restrict_on:
            sql = f"SELECT COUNT(*) as cnt FROM {rule.table} WHERE {rule.foreign_key} = ?"
            
            if rule.custom_check_sql:
                sql = rule.custom_check_sql.format(entity_id=entity_id)
            
            cursor = self.data_source.execute(sql, [entity_id])
            row = cursor.fetchone()
            count = row['cnt'] if row else 0
            
            if count > 0:
                violations.append({
                    'table': rule.table,
                    'foreign_key': rule.foreign_key,
                    'message': rule.message,
                    'count': count,
                })
        
        return violations
    
    def _get_foreign_key_column(self, table_name: str, entity_type: str, entity_id: int) -> str:
        """智能检测外键列名"""
        possible_names = [
            f"{entity_type}_id",
            f"{entity_type.replace('_', '')}_id",
            "group_id",
            "user_id",
            "role_id",
            "id",
        ]
        
        try:
            cursor = self.data_source.execute(f"PRAGMA table_info({table_name})")
            columns = [row[1] for row in cursor.fetchall()]
            
            for name in possible_names:
                if name in columns:
                    return name
        except Exception:
            pass
        
        return f"{entity_type}_id"
    
    def execute_polymorphic_cascade(self, parent_type: str, parent_id: int,
                                    operator_id: int = 0, operator_name: str = "system") -> List[Dict]:
        """
        执行多态 Composition 反向级联删除
        
        当父对象删除时，查找所有通过多态关联绑定到它的子对象并删除。
        
        Args:
            parent_type: 父对象类型
            parent_id: 父对象 ID
            operator_id: 操作人 ID
            operator_name: 操作人名称
            
        Returns:
            删除的子对象列表
        """
        deleted = []
        
        from meta.core.models import registry
        
        for child_meta in registry.get_all():
            associations = getattr(child_meta, 'associations', None)
            if not associations:
                continue
            
            if isinstance(associations, dict):
                assoc_list = associations.values()
            elif isinstance(associations, list):
                assoc_list = associations
            else:
                continue
            
            for assoc in assoc_list:
                if not self._is_polymorphic_cascade(assoc, parent_type):
                    continue
                
                type_field = getattr(assoc, 'polymorphic_type_field', None)
                id_field = getattr(assoc, 'polymorphic_id_field', None)
                
                if not type_field or not id_field:
                    continue
                
                table_name = child_meta.table_name
                async_delete = getattr(assoc, 'async_delete', False)
                
                try:
                    query = f"SELECT id FROM {table_name} WHERE {type_field} = ? AND {id_field} = ?"
                    cursor = self.data_source.execute(query, [parent_type, parent_id])
                    child_ids = [row[0] if not isinstance(row, dict) else row['id'] for row in cursor.fetchall()]
                except Exception as e:
                    logger.error(f"[Deletion] Failed to query polymorphic children for {child_meta.id}: {e}")
                    continue
                
                if not child_ids:
                    continue
                
                if async_delete:
                    self._schedule_async_delete(child_meta.id, child_ids, operator_id, operator_name)
                    deleted.append({
                        'object_type': child_meta.id,
                        'ids': child_ids,
                        'async': True,
                        'status': 'scheduled',
                    })
                else:
                    self._delete_polymorphic_children_sync(
                        child_meta.id, table_name, child_ids,
                        operator_id, operator_name
                    )
                    deleted.append({
                        'object_type': child_meta.id,
                        'ids': child_ids,
                        'async': False,
                        'status': 'deleted',
                    })
        
        return deleted
    
    def _is_polymorphic_cascade(self, assoc, parent_type: str) -> bool:
        """检查关联是否为多态 Composition 且需要级联删除"""
        if not getattr(assoc, 'cascade_delete', False):
            return False
        
        target_entity = getattr(assoc, 'target_entity', '') or getattr(assoc, 'target_type', '')
        if target_entity != 'polymorphic':
            return False
        
        polymorphic_type_field = getattr(assoc, 'polymorphic_type_field', None)
        if not polymorphic_type_field:
            return False
        
        return True
    
    def _delete_polymorphic_children_sync(self, child_type: str, table_name: str,
                                           child_ids: List[int],
                                           operator_id: int, operator_name: str):
        """同步删除多态子对象"""
        if not child_ids:
            return
        
        try:
            placeholders = ','.join(['?'] * len(child_ids))
            self.data_source.execute(
                f"DELETE FROM {table_name} WHERE id IN ({placeholders})",
                child_ids
            )
            logger.info(f"[Deletion] Polymorphic cascade deleted {len(child_ids)} {child_type}")
            
            for child_id in child_ids:
                try:
                    self.audit_interceptor.log_delete(
                        object_type=child_type,
                        object_id=child_id,
                        data={'id': child_id, '_cascade_reason': 'polymorphic_composition'},
                        user_id=str(operator_id) if operator_id else None,
                        user_name=operator_name,
                    )
                except Exception:
                    pass
                    
        except Exception as e:
            logger.error(f"[Deletion] Failed to polymorphic cascade delete {child_type}: {e}")
            raise
    
    def _schedule_async_delete(self, child_type: str, child_ids: List[int],
                                operator_id: int, operator_name: str):
        """异步删除多态子对象（创建后台任务）"""
        try:
            task_data = {
                'task_type': 'polymorphic_cascade_delete',
                'object_type': child_type,
                'object_ids': ','.join(str(i) for i in child_ids),
                'operator_id': operator_id,
                'operator_name': operator_name,
                'status': 'pending',
            }
            
            self.data_source.execute(
                "INSERT INTO background_tasks (task_type, task_data, status, created_at) VALUES (?, ?, 'pending', ?)",
                [task_data['task_type'], str(task_data), datetime.now().isoformat()]
            )
            logger.info(f"[Deletion] Scheduled async delete for {len(child_ids)} {child_type}")
        except Exception as e:
            logger.warning(f"[Deletion] Failed to schedule async delete, falling back to sync: {e}")
            from meta.core.models import registry
            child_meta = registry.get(child_type)
            table_name = child_meta.table_name if child_meta else f"{child_type}s"
            self._delete_polymorphic_children_sync(child_type, table_name, child_ids, operator_id, operator_name)
    
    def hard_delete(self, entity_type: str, entity_id: int, policy, 
                   operator_id: int, operator_name: str, old_record: Dict) -> Dict:
        """物理删除（含级联清理 + 多态 Composition 反向级联）"""
        table_name = self.get_table_name(entity_type)
        
        with self.data_source.transaction():
            cascade_tables = getattr(policy, 'cascade_delete', []) or []
            for tbl in cascade_tables:
                fk_col = self._get_foreign_key_column(tbl, entity_type, entity_id)
                try:
                    self.data_source.execute(
                        f"DELETE FROM {tbl} WHERE {fk_col} = ?",
                        [entity_id]
                    )
                    logger.info(f"[Deletion] Cascade deleted from {tbl} where {fk_col}={entity_id}")
                except Exception as e:
                    logger.warning(f"[Deletion] Failed to cascade delete from {tbl}: {e}")
            
            polymorphic_deleted = self.execute_polymorphic_cascade(
                entity_type, entity_id, operator_id, operator_name
            )
            
            self.data_source.execute(
                f"DELETE FROM {table_name} WHERE id = ?",
                [entity_id]
            )
        
        result_msg = '删除成功'
        if polymorphic_deleted:
            total = sum(len(d['ids']) for d in polymorphic_deleted)
            result_msg += f'，级联删除 {total} 条多态关联记录'
        
        logger.info(f"[Deletion] Hard deleted {entity_type} id={entity_id}")
        return {'success': True, 'message': result_msg, 'polymorphic_deleted': polymorphic_deleted}
    
    def delete(self, entity_type: str, entity_id: int,
               operator_id: int = 0, operator_name: str = "system") -> Dict:
        """
        通用删除入口
        
        Args:
            entity_type: 实体类型 (如 'user', 'role')
            entity_id: 要删除的记录 ID
            operator_id: 操作人 ID
            operator_name: 操作人名称
            
        Returns:
            {'success': bool, 'message': str, 'errors'?: list, 'details'?: list}
        """
        policy = self.get_deletion_policy(entity_type)
        
        old_record = self._get_record(entity_type, entity_id)
        if not old_record:
            return {'success': False, 'message': '记录不存在'}
        
        violations = self.check_restrict_rules(entity_type, entity_id, policy)
        if violations:
            return {
                'success': False,
                'message': '删除被拒绝',
                'errors': [v['message'] for v in violations],
                'details': violations,
            }
        
        result = self.hard_delete(entity_type, entity_id, policy,
                                    operator_id, operator_name, old_record)
        
        self._write_audit_log(entity_type, entity_id, result, old_record,
                             operator_id, operator_name)
        
        return result
    
    def _get_record(self, entity_type: str, entity_id: int) -> Optional[Dict]:
        """获取当前记录快照"""
        table_name = self.get_table_name(entity_type)
        try:
            cursor = self.data_source.execute(
                f"SELECT * FROM {table_name} WHERE id = ?",
                [entity_id]
            )
            row = cursor.fetchone()
            if row:
                if isinstance(row, dict):
                    return row
                cols = [desc[0] for desc in cursor.description]
                return dict(zip(cols, row))
        except Exception as e:
            logger.warning(f"[Deletion] Failed to get record: {e}")
        return None
    
    def _write_audit_log(self, entity_type: str, entity_id: int, 
                        result: Dict, old_record: Dict,
                        operator_id: int, operator_name: str):
        """写入审计日志"""
        try:
            self.audit_interceptor.log_delete(
                object_type=entity_type,
                object_id=entity_id,
                data=old_record,
                user_id=str(operator_id) if operator_id else None,
                user_name=operator_name,
            )
            logger.info(f"[Audit] Logged DELETE on {entity_type}/{entity_id}")
        except Exception as e:
            logger.error(f"[Audit] Failed to write log: {e}")
