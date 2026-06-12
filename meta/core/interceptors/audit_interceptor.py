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
from meta.core.association.resolvers import resolve_assoc_meta as _resolve_assoc_meta

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
        - 关联操作（associate/dissociate/batch_*/assign/unassign）审计日志由此拦截器写入
        """
        # [DEBUG 2026-06-12] 诊断 batch_unassign 不写 DISSOCIATE 日志
        try:
            with open(r'd:\filework\_audit_debug.log', 'a', encoding='utf-8') as _f:
                _f.write(f"[{context.action}] is_crud={context.is_crud_action} "
                         f"object_id={context.object_id} result={context.result.success if context.result else 'None'} "
                         f"params_keys={list(context.params.keys()) if context.params else 'None'}\n")
        except Exception:
            pass

        # [FIX 2026-06-12] 之前只处理 associate/dissociate, 导致 batch_assign/batch_unassign
        # 不产生审计日志. 用户在用户详情页多选删除用户组时, 走的是 batch_unassign 路径,
        # 所以看不到 DISSOCIATE 日志. 现在把 assign/unassign/batch_assign/batch_unassign
        # 也纳入审计拦截器, 统一在 _log_association_event 中处理.
        _ASSOC_ACTIONS = {
            'associate', 'dissociate',
            'assign', 'unassign',
            'batch_assign', 'batch_unassign',
        }
        if not context.is_crud_action and context.action not in _ASSOC_ACTIONS:
            try:
                with open(r'd:\filework\_audit_debug.log', 'a', encoding='utf-8') as _f:
                    _f.write(f"  -> SKIP (not assoc action)\n")
            except Exception: pass
            return

        # [DEBUG]
        logger.error(f"[FIX 2026-06-12] AuditInterceptor.after_action called: action={context.action}, object_id={context.object_id}, params={context.params}, has_result={context.result is not None and context.result.success if context.result else 'None'}")
        
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
            try:
                with open(r'd:\filework\_audit_debug.log', 'a', encoding='utf-8') as _f:
                    _f.write(f"  -> SKIP (action_config disabled for {context.action})\n")
            except Exception: pass
            return

        try:
            if context.is_create_action:
                self._log_create(context, action_config)
            elif context.is_update_action:
                self._log_update(context, action_config)
            elif context.is_delete_action:
                self._log_delete(context, action_config)
            elif context.action in ('associate', 'assign', 'batch_assign'):
                try:
                    with open(r'd:\filework\_audit_debug.log', 'a', encoding='utf-8') as _f:
                        _f.write(f"  -> CALLING _log_association_event(action=ASSOCIATE)\n")
                except Exception: pass
                self._log_association_event(context, action_config, 'ASSOCIATE')
            elif context.action in ('dissociate', 'unassign', 'batch_unassign'):
                try:
                    with open(r'd:\filework\_audit_debug.log', 'a', encoding='utf-8') as _f:
                        _f.write(f"  -> CALLING _log_association_event(action=DISSOCIATE)\n")
                except Exception: pass
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
        """统一的关联操作审计日志记录 — 合并 _log_associate/_log_dissociate 中 ~88% 的重复代码

        [审计延迟写入 2026-06-09]
        在事务中执行时，审计写入会与业务写入发生 SQLite 锁冲突。
        解决方案：在事务内缓存审计记录，事务提交后再写入。
        """
        # [DEBUG 2026-06-12] 诊断
        try:
            with open(r'd:\filework\_audit_debug.log', 'a', encoding='utf-8') as _f:
                _f.write(f"    _log_association_event ENTER: action={action}\n")
        except Exception: pass
        # [FIX 2026-06-12] context.user_name 只是 'admin', 从 g.current_user 提取带 display_name 的格式
        try:
            from flask import g
            _cu = getattr(g, 'current_user', None) or {}
            _display = _cu.get('display_name') or ''
            _username = _cu.get('username') or ''
            if _display and _username and _display != _username:
                formatted_user_name = f"{_display} ({_username})"
            else:
                formatted_user_name = _display or _username or context.user_name or ''
        except RuntimeError:
            formatted_user_name = context.user_name

        params = context.params
        tgt_type = params.get('tgt_type')
        association_name = params.get('association_name', 'members')

        # [FIX 2026-06-12] 批量操作 (batch_assign/batch_unassign) 可能传 target_ids 列表
        _raw_tgt_ids = params.get('target_ids') or params.get('tgt_id')
        if isinstance(_raw_tgt_ids, (list, tuple)):
            tgt_ids = list(_raw_tgt_ids)
        elif _raw_tgt_ids is not None:
            tgt_ids = [_raw_tgt_ids]
        else:
            tgt_ids = []

        src_display = get_object_display(context.object_type, context.object_id, context.data_source)

        src_type_name = _TYPE_DISPLAY_MAP.get(context.object_type, context.object_type)
        tgt_type_name = _TYPE_DISPLAY_MAP.get(tgt_type, tgt_type)
        association_display = _ASSOCIATION_DISPLAY_MAP.get(association_name, association_name)

        # [FIX 2026-06-12] 批量操作为每个 target_id 产生一条审计记录
        # [FIX 2026-06-12] 只对实际存在关联的 target_id 产生审计, 避免"未删除也记日志"
        # [FIX 2026-06-12] 优先用 context.extra['_assoc_effective_ids'] (AssociationEngine._try_bulk_m2m
        # 在 DELETE 前 SELECT 并存入的), 因为 AuditInterceptor 是在 PersistenceInterceptor 之后
        # 执行, 此时 SQLite WAL 模式下不同连接 SELECT 看不到未提交的 DELETE.
        pre_computed_effective_ids = (context.extra or {}).get('_assoc_effective_ids')
        if pre_computed_effective_ids is not None:
            try:
                with open(r'd:\filework\_audit_debug.log', 'a', encoding='utf-8') as _f:
                    _f.write(f"    batch: using pre-computed effective_ids={pre_computed_effective_ids} from context.extra\n")
            except Exception: pass
            effective_ids = list(pre_computed_effective_ids)
        elif len(tgt_ids) > 1:
            # 批量场景: 先查询当前实际存在的关联, 只对存在的写 audit
            assoc_meta = _resolve_assoc_meta(context.object_type, association_name)
            try:
                with open(r'd:\filework\_audit_debug.log', 'a', encoding='utf-8') as _f:
                    _f.write(f"    batch: tgt_ids={tgt_ids} assoc_meta={assoc_meta}\n")
            except Exception: pass
            if assoc_meta and assoc_meta.get('type') == 'many_to_many':
                through = assoc_meta.get('through')
                source_key = assoc_meta.get('source_key')
                target_key = assoc_meta.get('target_key')
                try:
                    with open(r'd:\filework\_audit_debug.log', 'a', encoding='utf-8') as _f:
                        _f.write(f"    batch: through={through} src_key={source_key} tgt_key={target_key}\n")
                except Exception: pass
                if through and source_key and target_key:
                    src_id = context.object_id
                    placeholders = ','.join('?' for _ in tgt_ids)
                    if action == 'ASSOCIATE':
                        # ASSOCIATE: 检查 _try_bulk_m2m 是否实际创建了关联
                        sql = (f"SELECT {target_key} FROM {through} "
                               f"WHERE {source_key}=? AND {target_key} IN ({placeholders})")
                        existing = set(r[0] for r in context.data_source.execute(
                            sql, tuple([src_id] + tgt_ids)
                        ).fetchall() or [])
                        # 只有新增的才记
                        # 但 _try_bulk_m2m 用了 INSERT OR IGNORE, 所以 existing 包含已存在的
                        # 这里简化: 都记 (审计完整性优先)
                        effective_ids = tgt_ids
                    else:
                        # DISSOCIATE: 删除前先查存在, 只对存在的记
                        sql = (f"SELECT {target_key} FROM {through} "
                               f"WHERE {source_key}=? AND {target_key} IN ({placeholders})")
                        existing = set(r[0] for r in context.data_source.execute(
                            sql, tuple([src_id] + tgt_ids)
                        ).fetchall() or [])
                        effective_ids = [tid for tid in tgt_ids if tid in existing]
                        try:
                            with open(r'd:\filework\_audit_debug.log', 'a', encoding='utf-8') as _f:
                                _f.write(f"    batch DISSOCIATE: src_id={src_id} sql={sql} existing={existing} effective_ids={effective_ids}\n")
                        except Exception: pass
                else:
                    effective_ids = tgt_ids
            else:
                effective_ids = tgt_ids
        else:
            # 单条场景, 后续代码会处理 (tgt_ids == 1 走单条路径)
            effective_ids = tgt_ids

        try:
            with open(r'd:\filework\_audit_debug.log', 'a', encoding='utf-8') as _f:
                _f.write(f"    batch: effective_ids={effective_ids} about_to_write={len(effective_ids)}\n")
        except Exception: pass

        # [FIX 2026-06-12] 批量场景: 循环写所有 effective_ids, 写完直接 return
        if len(tgt_ids) > 1:
            if not effective_ids:
                logger.info(
                    f"[AuditInterceptor] batch {action}: no effective_ids, "
                    f"skipping {len(tgt_ids)} non-existing associations"
                )
                return
            for tid in effective_ids:
                self._write_single_association_audit(
                    context=context, action=action,
                    tgt_type=tgt_type, tgt_id=tid,
                    tgt_type_name=tgt_type_name,
                    association_display=association_display,
                    formatted_user_name=formatted_user_name,
                )
            if len(effective_ids) < len(tgt_ids):
                logger.info(
                    f"[AuditInterceptor] batch {action}: "
                    f"wrote {len(effective_ids)}/{len(tgt_ids)} audit records "
                    f"(skipped {len(tgt_ids) - len(effective_ids)} non-existing)"
                )
            return
        elif len(tgt_ids) == 1:
            tgt_id = effective_ids[0] if effective_ids else tgt_ids[0]
        else:
            logger.warning(f"[AuditInterceptor] _log_association_event: no tgt_id found, skipping")
            return

        tgt_display = get_object_display(tgt_type, tgt_id, context.data_source)

        # [FIX 2026-06-12] 委托给 _write_single_association_audit 统一处理
        # [审计延迟写入] 检测是否在事务中
        # [FIX Test Bug 2026-06-09] 严格用 `is True` 判断, 避免 MagicMock 默认 truthy 导致
        # dissociate/associate 测试用 MagicMock() 作 data_source 时误判 in_transaction=True 而走 defer 路径
        # (真实 DataSource.in_transaction 签名: bool, 见 meta/core/datasource.py:273)
        self._write_single_association_audit(
            context=context, action=action,
            tgt_type=tgt_type, tgt_id=tgt_id,
            tgt_type_name=tgt_type_name,
            tgt_display=tgt_display,
            association_display=association_display,
            formatted_user_name=formatted_user_name,
        )

    def _write_single_association_audit(self, context, action: str,
                                         tgt_type, tgt_id,
                                         tgt_type_name: str,
                                         association_display: str,
                                         formatted_user_name: str,
                                         tgt_display: str = None) -> None:
        """写入单条关联审计记录 (用于单条和批量操作)"""
        if tgt_display is None:
            tgt_display = get_object_display(tgt_type, tgt_id, context.data_source)

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

        audit_params = {
            'action': action,
            'object_type': context.object_type,
            'object_id': context.object_id,
            'user_id': context.user_id,
            'user_name': formatted_user_name,
            'field_name': association_display,
            'old_data': old_data_val,
            'new_data': new_data_val,
            'ip_address': getattr(context, 'ip_address', None),
            'trace_id': context.trace_id,
            'parent_object_type': tgt_type,
            'parent_object_id': tgt_id,
            'level': 'INFO'
        }

        in_transaction = getattr(context.data_source, 'in_transaction', False) is True

        if in_transaction:
            context.add_pending_audit(audit_params)
            logger.info(
                f"[AuditInterceptor] DEFERRED {action} on "
                f"{context.object_type}/{context.object_id} -> {tgt_type}:{tgt_id} "
                f"(pending flush after transaction commit)"
            )
        else:
            self._structured_logger.log_business(**audit_params)
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
