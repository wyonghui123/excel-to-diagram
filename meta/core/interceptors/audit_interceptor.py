# -*- coding: utf-8 -*-
"""
审计日志拦截器

元数据驱动的审计日志记录，根据 YAML 配置自动记录审计日志。
使用 StructuredLogger 提供统一的日志写入接口。
"""

import logging
from typing import Dict, Any, List, Set

from meta.core.interceptors.base import Interceptor
from meta.core.action_context import ActionContext
from meta.core.models import AuditActionConfig
from meta.services.audit_service import AuditService
from meta.services.structured_logger import StructuredLogger, LogEntry
from meta.enums.log_category import LogCategory
from meta.enums.log_level import LogLevel
from meta.core.model_utils import get_object_display

logger = logging.getLogger(__name__)

_TYPE_DISPLAY_MAP = {
    'user': '用户',
    'user_group': '用户组',
    'role': '角色',
    'permission': '权限',
}

_ASSOCIATION_DISPLAY_MAP = {
    'members': '成员',
    'roles': '角色',
    'permissions': '权限',
}


class AuditInterceptor(Interceptor):
    """
    审计日志拦截器
    
    注意：
    - CRUD 审计日志写入已统一由 ActionExecutor._write_audit_log_v2() 处理。
    - 关联操作（associate/dissociate）的审计日志由此拦截器处理。
    
    此拦截器功能：
    1. 在 before_action 中获取旧数据（用于 UPDATE/DELETE）
    2. 在 after_action 中写入 CRUD 审计日志（已禁用，由ActionExecutor处理）和关联操作审计日志（已启用）
    3. 触发其他后处理逻辑（如通知、缓存刷新等）
    
    优先级：90（在持久化之后执行）
    """
    
    AUDIT_CRUD_WRITE_DISABLED = True   # CRUD 审计日志由 ActionExecutor 统一处理
    AUDIT_ASSOC_WRITE_DISABLED = False  # 关联操作审计日志由此拦截器处理
    
    @property
    def priority(self) -> int:
        return 90
    
    def __init__(self, data_source=None, structured_logger: StructuredLogger = None):
        self._data_source = data_source
        self._audit_service = None
        self._structured_logger = structured_logger or StructuredLogger()
    
    def _get_audit_service(self, context: ActionContext) -> AuditService:
        """获取审计服务实例"""
        if self._audit_service is None:
            self._audit_service = AuditService(context.data_source)
        return self._audit_service
    
    def before_action(self, context: ActionContext) -> None:
        """动作执行前：获取旧数据（用于 UPDATE/DELETE）"""
        if not context.is_crud_action:
            return
        
        if context.is_update_action or context.is_delete_action:
            context.old_data = self._get_record(context)
    
    def after_action(self, context: ActionContext) -> None:
        """动作执行后：处理 CRUD 后处理逻辑和关联操作审计日志写入
        
        - CRUD 审计日志写入已由 ActionExecutor._write_audit_log_v2() 统一处理（跳过）
        - 关联操作（associate/dissociate）审计日志由此拦截器写入（启用）
        """
        if not context.is_crud_action and context.action not in ('associate', 'dissociate'):
            return
        
        if self.AUDIT_CRUD_WRITE_DISABLED and context.is_crud_action:
            logger.debug(f"[AuditInterceptor] CRUD audit write disabled, skipping. Action={context.action}")
            return
        
        if self.AUDIT_ASSOC_WRITE_DISABLED and context.action in ('associate', 'dissociate'):
            logger.debug(f"[AuditInterceptor] Assoc audit write disabled, skipping. Action={context.action}")
            return
        
        if not context.result or not context.result.success:
            return
        
        audit_config = context.meta_object.audit if context.meta_object else None
        
        if not audit_config or not audit_config.enabled:
            return
        
        action_config = audit_config.get_action_config(context.action)
        
        if not action_config.enabled:
            return
        
        try:
            if context.is_create_action:
                self._log_create(context, action_config)
            elif context.is_update_action:
                self._log_update(context, action_config)
            elif context.is_delete_action:
                self._log_delete(context, action_config)
            elif context.action == 'associate':
                self._log_association_event(context, action_config, 'ASSOCIATE')
            elif context.action == 'dissociate':
                self._log_association_event(context, action_config, 'DISSOCIATE')
        except Exception as e:
            logger.error(f"[AuditInterceptor] Error logging audit: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _get_record(self, context: ActionContext) -> Dict[str, Any]:
        """获取记录"""
        table_name = context.meta_object.table_name
        object_id = context.object_id
        
        cursor = context.data_source.execute(
            f"SELECT * FROM {table_name} WHERE id = ?",
            [object_id]
        )
        row = cursor.fetchone()
        
        if row:
            if isinstance(row, dict):
                return row
            cols = [desc[0] for desc in cursor.description]
            return dict(zip(cols, row))
        
        return {}
    
    def _log_create(self, context: ActionContext, config: AuditActionConfig) -> None:
        """记录创建审计日志"""
        new_data = context.result.data or {}
        
        fields_to_log = self._get_fields_to_log(
            context.meta_object,
            {},
            new_data,
            config,
        )
        
        for field in fields_to_log:
            self._structured_logger.log_business(
                action='CREATE',
                object_type=context.object_type,
                object_id=context.object_id,
                user_id=context.user_id,
                user_name=context.user_name,
                field_name=field,
                old_data=None,
                new_data={'value': new_data.get(field, '')},
                ip_address=getattr(context, 'ip_address', None),
                trace_id=context.trace_id,
                level='INFO'
            )
        
        logger.info(f"[AuditInterceptor] Logged CREATE on {context.object_type}/{context.object_id}")
    
    def _log_update(self, context: ActionContext, config: AuditActionConfig) -> None:
        """记录更新审计日志"""
        old_data = context.old_data or {}
        new_data = context.new_data or context.result.data or {}
        
        fields_to_log = self._get_fields_to_log(
            context.meta_object,
            old_data,
            new_data,
            config,
        )
        
        for field in fields_to_log:
            old_val = old_data.get(field)
            new_val = new_data.get(field)
            
            if not self._values_equal(old_val, new_val):
                self._structured_logger.log_business(
                    action='UPDATE',
                    object_type=context.object_type,
                    object_id=context.object_id,
                    user_id=context.user_id,
                    user_name=context.user_name,
                    field_name=field,
                    old_data={'value': old_val} if old_val is not None else None,
                    new_data={'value': new_val} if new_val is not None else None,
                    ip_address=getattr(context, 'ip_address', None),
                    trace_id=context.trace_id,
                    level='INFO'
                )
        
        logger.info(f"[AuditInterceptor] Logged UPDATE on {context.object_type}/{context.object_id}")
    
    def _values_equal(self, old_val: Any, new_val: Any) -> bool:
        """比较两个值是否相等"""
        if old_val is None and new_val is None:
            return True
        
        if old_val is None or new_val is None:
            return False
        
        if type(old_val) != type(new_val):
            return str(old_val) == str(new_val)
        
        return old_val == new_val
    
    def _log_delete(self, context: ActionContext, config: AuditActionConfig) -> None:
        """记录删除审计日志"""
        old_data = context.old_data or {}
        
        fields_to_log = self._get_fields_to_log(
            context.meta_object,
            old_data,
            {},
            config,
        )
        
        for field in fields_to_log:
            self._structured_logger.log_business(
                action='DELETE',
                object_type=context.object_type,
                object_id=context.object_id,
                user_id=context.user_id,
                user_name=context.user_name,
                field_name=field,
                old_data={'value': old_data.get(field, '')},
                new_data=None,
                ip_address=getattr(context, 'ip_address', None),
                trace_id=context.trace_id,
                level='INFO'
            )
        
        logger.info(f"[AuditInterceptor] Logged DELETE on {context.object_type}/{context.object_id}")
    
    def _log_association_event(self, context: ActionContext, config: AuditActionConfig, action: str) -> None:
        """统一的关联操作审计日志记录 — 合并 _log_associate/_log_dissociate 中 ~88% 的重复代码"""
        params = context.params
        tgt_type = params.get('tgt_type')
        tgt_id = params.get('tgt_id')
        association_name = params.get('association_name', 'members')

        src_display = get_object_display(context.object_type, context.object_id, context.data_source)
        tgt_display = get_object_display(tgt_type, tgt_id, context.data_source)

        src_type_name = _TYPE_DISPLAY_MAP.get(context.object_type, context.object_type)
        tgt_type_name = _TYPE_DISPLAY_MAP.get(tgt_type, tgt_type)
        association_display = _ASSOCIATION_DISPLAY_MAP.get(association_name, association_name)

        if action == 'ASSOCIATE':
            old_data_val = None
            new_data_val = {
                'target_type': tgt_type_name,
                'target_display': tgt_display,
                'target_id': tgt_id,
            }
        else:
            old_data_val = {
                'target_type': tgt_type_name,
                'target_display': tgt_display,
                'target_id': tgt_id,
            }
            new_data_val = None

        self._structured_logger.log_business(
            action=action,
            object_type=context.object_type,
            object_id=context.object_id,
            user_id=context.user_id,
            user_name=context.user_name,
            field_name=association_display,
            old_data=old_data_val,
            new_data=new_data_val,
            ip_address=getattr(context, 'ip_address', None),
            trace_id=context.trace_id,
            parent_object_type=tgt_type,
            parent_object_id=tgt_id,
            level='INFO'
        )

        logger.info(
            f"[AuditInterceptor] Logged {action} on "
            f"{context.object_type}/{context.object_id} -> {tgt_type}:{tgt_id}"
        )
    
    def _get_object_display(self, object_type: str, object_id: int, data_source) -> str:
        """获取业务对象的显示名称，委托给 model_utils.get_object_display"""
        return get_object_display(object_type, object_id, data_source)

    def _get_fields_to_log(self, meta_object, old_data: Dict, new_data: Dict, 
                          config: AuditActionConfig) -> List[str]:
        """获取需要记录的字段列表"""
        all_fields = [f.id for f in meta_object.fields]
        
        if config.fields == 'all':
            fields = all_fields
        elif config.fields == 'changed_only':
            fields = list(set(list(old_data.keys()) + list(new_data.keys())))
            fields = [f for f in fields if f in all_fields]
        elif config.fields == 'business_only':
            system_fields = {'id', 'created_at', 'updated_at', 'version', 'is_deleted'}
            fields = [f for f in all_fields if f not in system_fields]
        else:
            fields = all_fields
        
        if config.exclude:
            fields = [f for f in fields if f not in config.exclude]
        
        return fields
