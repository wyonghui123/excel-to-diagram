# -*- coding: utf-8 -*-
"""
审计日志写入拦截器

参考 SAP V2 Update 模式：
- 业务事务提交后，审计日志通过 AsyncAuditWriter 异步写入
- 审计写入失败不影响业务结果
- 支持完整上下文（user_id, user_name, ip_address, user_agent, trace_id）
"""

from functools import wraps
from flask import g, request
from datetime import datetime
import json
import logging
from typing import Callable, Optional, Dict, Any

logger = logging.getLogger(__name__)


def audit_log(object_type: str):
    """
    审计日志装饰器
    
    自动记录业务操作到 audit_logs（V2 异步写入模式）
    
    用法：
    @audit_log(object_type='user_group')
    def create_group(self, name, code, ...):
        ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            from meta.services.async_audit_writer import async_audit_writer
            from meta.services.audit_service import AuditService

            user_id = getattr(g, 'user_id', None)
            user_name = getattr(g, 'user_name', None)
            trace_id = getattr(g, 'trace_id', None)
            transaction_id = getattr(g, 'transaction_id', None)

            func_name = func.__name__.lower()
            if 'create' in func_name:
                action = 'CREATE'
            elif 'update' in func_name:
                action = 'UPDATE'
            elif 'delete' in func_name:
                action = 'DELETE'
            else:
                action = 'UNKNOWN'

            old_data = None
            if action in ['UPDATE', 'DELETE']:
                # v1.4 增强：支持位置参数（args[0] 通常是 id/group_id/role_id/user_id）
                # 优先从 kwargs 取，回退到 args[0]
                object_id = (
                    kwargs.get('id') or kwargs.get('group_id')
                    or kwargs.get('role_id') or kwargs.get('user_id')
                )
                if not object_id and args:
                    # 假设第一个位置参数是 object_id
                    object_id = args[0]
                if object_id and hasattr(self, '_get_object'):
                    try:
                        old_data = self._get_object(object_id)
                    except Exception as e:
                        logger.warning("Failed to get old data for audit: %s", str(e))
            
            result = func(self, *args, **kwargs)
            
            new_data = None
            object_id = None
            if result:
                if isinstance(result, int):
                    object_id = result
                    if action == 'CREATE' and hasattr(self, '_get_object'):
                        try:
                            new_data = self._get_object(object_id)
                        except Exception as e:
                            logger.warning("Failed to get new data for audit: %s", str(e))
                elif isinstance(result, dict):
                    object_id = result.get('id')
                    new_data = result
            
            if object_id:
                try:
                    audit_service = AuditService(getattr(self, 'ds', None))
                    
                    def write_audit_log(trace_id=None, transaction_id=None, **kwargs):
                        # v1.4 增强：request 可能在 service context 中不可用
                        try:
                            ip_addr = request.remote_addr if request else None
                            ua = request.headers.get('User-Agent', '') if request else ''
                        except RuntimeError:
                            # Working outside of request context
                            ip_addr = None
                            ua = ''
                        # [FIX 2026-06-13] 允许 async_audit_writer.submit 透传 user_id/user_name/ip/user_agent
                        # 解决 'got an unexpected keyword argument user_id' TypeError
                        eff_user_id = kwargs.get('user_id', user_id)
                        eff_user_name = kwargs.get('user_name', user_name)
                        eff_ip = kwargs.get('ip_address', ip_addr)
                        eff_ua = kwargs.get('user_agent', ua)
                        audit_service.log(
                            object_type=object_type,
                            object_id=object_id,
                            action=action,
                            user_id=eff_user_id,
                            user_name=eff_user_name,
                            old_data=old_data,
                            new_data=new_data,
                            ip_address=eff_ip,
                            user_agent=eff_ua,
                            trace_id=trace_id,
                            transaction_id=transaction_id,
                        )
                    
                    async_audit_writer.submit(
                        write_audit_log,
                        trace_id=trace_id,
                        transaction_id=transaction_id
                    )
                except Exception as e:
                    logger.warning("Failed to submit audit log: %s", str(e))
            
            return result
        return wrapper
    return decorator


class AuditInterceptor:
    """
    审计日志拦截器
    
    提供更灵活的审计日志记录方式，支持：
    - 手动记录审计日志
    - 批量记录审计日志
    - 自定义审计数据
    """
    
    def __init__(self, data_source=None):
        from meta.services.async_audit_writer import async_audit_writer
        from meta.services.audit_service import AuditService
        
        self.ds = data_source
        self.audit_service = AuditService(data_source)
        self.async_writer = async_audit_writer
        
        # 确保异步写入器有数据源
        if data_source and self.async_writer._ds is None:
            self.async_writer.set_data_source(data_source)
    
    def log_create(self, object_type: str, object_id: int, data: Dict[str, Any],
                   user_id: Optional[str] = None, user_name: Optional[str] = None,
                   trace_id: Optional[str] = None, transaction_id: Optional[str] = None):
        """记录创建操作"""
        # 在应用上下文中捕获所有需要的值
        try:
            from flask import g, request
            captured_user_id = user_id or getattr(g, 'user_id', None)
            captured_user_name = user_name or getattr(g, 'user_name', None)
            captured_trace_id = trace_id or getattr(g, 'trace_id', None)
            captured_transaction_id = transaction_id or getattr(g, 'transaction_id', None)
            captured_ip = request.remote_addr if request else None
            captured_ua = request.headers.get('User-Agent', '') if request else None
        except RuntimeError:
            # 不在应用上下文中，使用传入的值
            captured_user_id = user_id
            captured_user_name = user_name
            captured_trace_id = trace_id
            captured_transaction_id = transaction_id
            captured_ip = None
            captured_ua = None

        # [FIX 2026-06-20 P2 v1] 自动生成 transaction_id (如果都没有)
        if not captured_transaction_id:
            import uuid as _uuid
            captured_transaction_id = f"tx_{_uuid.uuid4().hex[:16]}"
            try:
                from flask import g
                g.transaction_id = captured_transaction_id
            except RuntimeError:
                pass
        # [FIX 2026-06-20 P2 v1] 自动生成 trace_id (如果都没有)
        if not captured_trace_id:
            import uuid as _uuid
            captured_trace_id = f"tr_{_uuid.uuid4().hex[:16]}"
            try:
                from flask import g
                g.trace_id = captured_trace_id
            except RuntimeError:
                pass
        
        def write_audit_log(trace_id=None, transaction_id=None, **kwargs):
            # [FIX 2026-06-13] 允许 async_audit_writer.submit 透传 user_id/user_name/ip/user_agent
            eff_user_id = kwargs.get('user_id', captured_user_id)
            eff_user_name = kwargs.get('user_name', captured_user_name)
            eff_ip = kwargs.get('ip_address', captured_ip)
            eff_ua = kwargs.get('user_agent', captured_ua)
            self.audit_service.log(
                object_type=object_type,
                object_id=object_id,
                action='CREATE',
                user_id=eff_user_id,
                user_name=eff_user_name,
                new_data=data,
                ip_address=eff_ip,
                user_agent=eff_ua,
                trace_id=trace_id or captured_trace_id,
                transaction_id=transaction_id or captured_transaction_id,
            )

        self.async_writer.submit(
            write_audit_log,
            trace_id=captured_trace_id,
            transaction_id=captured_transaction_id
        )

    def log_update(self, object_type: str, object_id: int,
                   old_data: Dict[str, Any], new_data: Dict[str, Any],
                   user_id: Optional[str] = None, user_name: Optional[str] = None,
                   trace_id: Optional[str] = None, transaction_id: Optional[str] = None):
        """记录更新操作"""
        try:
            from flask import g, request
            captured_user_id = user_id or getattr(g, 'user_id', None)
            captured_user_name = user_name or getattr(g, 'user_name', None)
            captured_trace_id = trace_id or getattr(g, 'trace_id', None)
            captured_transaction_id = transaction_id or getattr(g, 'transaction_id', None)
            captured_ip = request.remote_addr if request else None
            captured_ua = request.headers.get('User-Agent', '') if request else None
        except RuntimeError:
            captured_user_id = user_id
            captured_user_name = user_name
            captured_trace_id = trace_id
            captured_transaction_id = transaction_id
            captured_ip = None
            captured_ua = None

        # [FIX 2026-06-20 P2 v1] 自动生成 transaction_id
        if not captured_transaction_id:
            import uuid as _uuid
            captured_transaction_id = f"tx_{_uuid.uuid4().hex[:16]}"
            try:
                from flask import g
                g.transaction_id = captured_transaction_id
            except RuntimeError:
                pass
        # [FIX 2026-06-20 P2 v1] 自动生成 trace_id
        if not captured_trace_id:
            import uuid as _uuid
            captured_trace_id = f"tr_{_uuid.uuid4().hex[:16]}"
            try:
                from flask import g
                g.trace_id = captured_trace_id
            except RuntimeError:
                pass
        
        def write_audit_log(trace_id=None, transaction_id=None, **kwargs):
            # [FIX 2026-06-13] 允许 async_audit_writer.submit 透传 user_id/user_name/ip/user_agent
            eff_user_id = kwargs.get('user_id', captured_user_id)
            eff_user_name = kwargs.get('user_name', captured_user_name)
            eff_ip = kwargs.get('ip_address', captured_ip)
            eff_ua = kwargs.get('user_agent', captured_ua)
            self.audit_service.log(
                object_type=object_type,
                object_id=object_id,
                action='UPDATE',
                user_id=eff_user_id,
                user_name=eff_user_name,
                old_data=old_data,
                new_data=new_data,
                ip_address=eff_ip,
                user_agent=eff_ua,
                trace_id=trace_id or captured_trace_id,
                transaction_id=transaction_id or captured_transaction_id,
            )

        self.async_writer.submit(
            write_audit_log,
            trace_id=captured_trace_id,
            transaction_id=captured_transaction_id
        )

    def log_delete(self, object_type: str, object_id: int, data: Dict[str, Any],
                   user_id: Optional[str] = None, user_name: Optional[str] = None,
                   trace_id: Optional[str] = None, transaction_id: Optional[str] = None):
        """记录删除操作"""
        try:
            from flask import g, request
            captured_user_id = user_id or getattr(g, 'user_id', None)
            captured_user_name = user_name or getattr(g, 'user_name', None)
            captured_trace_id = trace_id or getattr(g, 'trace_id', None)
            captured_transaction_id = transaction_id or getattr(g, 'transaction_id', None)
            captured_ip = request.remote_addr if request else None
            captured_ua = request.headers.get('User-Agent', '') if request else None
        except RuntimeError:
            captured_user_id = user_id
            captured_user_name = user_name
            captured_trace_id = trace_id
            captured_transaction_id = transaction_id
            captured_ip = None
            captured_ua = None

        # [FIX 2026-06-20 P2 v1] 自动生成 transaction_id
        if not captured_transaction_id:
            import uuid as _uuid
            captured_transaction_id = f"tx_{_uuid.uuid4().hex[:16]}"
            try:
                from flask import g
                g.transaction_id = captured_transaction_id
            except RuntimeError:
                pass
        # [FIX 2026-06-20 P2 v1] 自动生成 trace_id
        if not captured_trace_id:
            import uuid as _uuid
            captured_trace_id = f"tr_{_uuid.uuid4().hex[:16]}"
            try:
                from flask import g
                g.trace_id = captured_trace_id
            except RuntimeError:
                pass
        
        def write_audit_log(trace_id=None, transaction_id=None, **kwargs):
            # [FIX 2026-06-13] 允许 async_audit_writer.submit 透传 user_id/user_name/ip/user_agent
            eff_user_id = kwargs.get('user_id', captured_user_id)
            eff_user_name = kwargs.get('user_name', captured_user_name)
            eff_ip = kwargs.get('ip_address', captured_ip)
            eff_ua = kwargs.get('user_agent', captured_ua)
            self.audit_service.log(
                object_type=object_type,
                object_id=object_id,
                action='DELETE',
                user_id=eff_user_id,
                user_name=eff_user_name,
                old_data=data,
                ip_address=eff_ip,
                user_agent=eff_ua,
                trace_id=trace_id or captured_trace_id,
                transaction_id=transaction_id or captured_transaction_id,
            )

        self.async_writer.submit(
            write_audit_log,
            trace_id=captured_trace_id,
            transaction_id=captured_transaction_id
        )

    def log_batch(self, operations: list):
        """
        批量记录审计日志
        
        Args:
            operations: 操作列表，每个操作包含：
                - object_type: 对象类型
                - object_id: 对象ID
                - action: 操作类型（CREATE/UPDATE/DELETE/ASSOCIATE/DISSOCIATE）
                - old_data: 旧数据（可选）
                - new_data: 新数据（可选）
        """
        for op in operations:
            if op['action'] == 'CREATE':
                self.log_create(
                    object_type=op['object_type'],
                    object_id=op['object_id'],
                    data=op.get('new_data', {}),
                    trace_id=op.get('trace_id'),
                    transaction_id=op.get('transaction_id')
                )
            elif op['action'] == 'UPDATE':
                self.log_update(
                    object_type=op['object_type'],
                    object_id=op['object_id'],
                    old_data=op.get('old_data', {}),
                    new_data=op.get('new_data', {}),
                    trace_id=op.get('trace_id'),
                    transaction_id=op.get('transaction_id')
                )
            elif op['action'] == 'DELETE':
                self.log_delete(
                    object_type=op['object_type'],
                    object_id=op['object_id'],
                    data=op.get('old_data', {}),
                    trace_id=op.get('trace_id'),
                    transaction_id=op.get('transaction_id')
                )
            elif op['action'] == 'ASSOCIATE':
                self.log_associate(
                    object_type=op['object_type'],
                    object_id=op['object_id'],
                    tgt_type=op.get('tgt_type', ''),
                    tgt_id=op.get('tgt_id', ''),
                    association_name=op.get('association_name', ''),
                    user_id=op.get('user_id'),
                    user_name=op.get('user_name'),
                    trace_id=op.get('trace_id'),
                    transaction_id=op.get('transaction_id')
                )
            elif op['action'] == 'DISSOCIATE':
                self.log_dissociate(
                    object_type=op['object_type'],
                    object_id=op['object_id'],
                    tgt_type=op.get('tgt_type', ''),
                    tgt_id=op.get('tgt_id', ''),
                    association_name=op.get('association_name', ''),
                    user_id=op.get('user_id'),
                    user_name=op.get('user_name'),
                    trace_id=op.get('trace_id'),
                    transaction_id=op.get('transaction_id')
                )

    def log_associate(self, object_type, object_id, tgt_type, tgt_id,
                      association_name, user_id=None, user_name=None,
                      trace_id=None, transaction_id=None):
        """记录关联操作 -> action='ASSOCIATE'"""
        try:
            from flask import g, request
            current_user = getattr(g, 'current_user', None) or {}
            # [FIX 2026-06-12] 从 g.current_user 提取 user_id 和带 display_name 的 user_name
            # 之前用 getattr(g, 'user_name', None) 拿不到 display_name,
            # 且 _set_user_context 只传了 username, 导致日志 user_name 一直是 "admin"
            captured_user_id = user_id or current_user.get('user_id') or current_user.get('id')
            _display = current_user.get('display_name') or ''
            _username = current_user.get('username') or ''
            if user_name:
                captured_user_name = user_name
            elif _display and _username and _display != _username:
                captured_user_name = f"{_display} ({_username})"
            else:
                captured_user_name = _display or _username or ''
            captured_trace_id = trace_id or getattr(g, 'trace_id', None)
            captured_transaction_id = transaction_id or getattr(g, 'transaction_id', None)
            captured_ip = request.remote_addr if request else None
            captured_ua = request.headers.get('User-Agent', '') if request else None
        except RuntimeError:
            captured_user_id = user_id
            captured_user_name = user_name
            captured_trace_id = trace_id
            captured_transaction_id = transaction_id
            captured_ip = None
            captured_ua = None

        tgt_display = self._get_target_display(tgt_type, tgt_id)

        def write_audit_log(trace_id=None, transaction_id=None, **kwargs):
            # [FIX 2026-06-13] 允许 async_audit_writer.submit 透传 user_id/user_name/ip/user_agent
            eff_user_id = kwargs.get('user_id', captured_user_id)
            eff_user_name = kwargs.get('user_name', captured_user_name)
            eff_ip = kwargs.get('ip_address', captured_ip)
            eff_ua = kwargs.get('user_agent', captured_ua)
            self.audit_service.log(
                object_type=object_type,
                object_id=object_id,
                action='ASSOCIATE',
                user_id=eff_user_id,
                user_name=eff_user_name,
                field_name=association_name,
                new_data={
                    'target_type': tgt_type,
                    'target_id': tgt_id,
                    'target_display': tgt_display,
                },
                ip_address=eff_ip,
                user_agent=eff_ua,
                trace_id=trace_id or captured_trace_id,
                transaction_id=transaction_id or captured_transaction_id,
                parent_object_type=tgt_type,
                parent_object_id=tgt_id,
            )

        self.async_writer.submit(
            write_audit_log,
            trace_id=captured_trace_id,
            transaction_id=captured_transaction_id
        )

    def log_dissociate(self, object_type, object_id, tgt_type, tgt_id,
                       association_name, user_id=None, user_name=None,
                       trace_id=None, transaction_id=None):
        """记录解除关联操作 -> action='DISSOCIATE'"""
        try:
            from flask import g, request
            current_user = getattr(g, 'current_user', None) or {}
            # [FIX 2026-06-12] 同 log_associate, 从 g.current_user 提取带 display_name 的 user_name
            captured_user_id = user_id or current_user.get('user_id') or current_user.get('id')
            _display = current_user.get('display_name') or ''
            _username = current_user.get('username') or ''
            if user_name:
                captured_user_name = user_name
            elif _display and _username and _display != _username:
                captured_user_name = f"{_display} ({_username})"
            else:
                captured_user_name = _display or _username or ''
            captured_trace_id = trace_id or getattr(g, 'trace_id', None)
            captured_transaction_id = transaction_id or getattr(g, 'transaction_id', None)
            captured_ip = request.remote_addr if request else None
            captured_ua = request.headers.get('User-Agent', '') if request else None
        except RuntimeError:
            captured_user_id = user_id
            captured_user_name = user_name
            captured_trace_id = trace_id
            captured_transaction_id = transaction_id
            captured_ip = None
            captured_ua = None

        tgt_display = self._get_target_display(tgt_type, tgt_id)

        def write_audit_log(trace_id=None, transaction_id=None, **kwargs):
            # [FIX 2026-06-13] 允许 async_audit_writer.submit 透传 user_id/user_name/ip/user_agent
            eff_user_id = kwargs.get('user_id', captured_user_id)
            eff_user_name = kwargs.get('user_name', captured_user_name)
            eff_ip = kwargs.get('ip_address', captured_ip)
            eff_ua = kwargs.get('user_agent', captured_ua)
            self.audit_service.log(
                object_type=object_type,
                object_id=object_id,
                action='DISSOCIATE',
                user_id=eff_user_id,
                user_name=eff_user_name,
                field_name=association_name,
                old_data={
                    'target_type': tgt_type,
                    'target_id': tgt_id,
                    'target_display': tgt_display,
                },
                ip_address=eff_ip,
                user_agent=eff_ua,
                trace_id=trace_id or captured_trace_id,
                transaction_id=transaction_id or captured_transaction_id,
                parent_object_type=tgt_type,
                parent_object_id=tgt_id,
            )

        self.async_writer.submit(
            write_audit_log,
            trace_id=captured_trace_id,
            transaction_id=captured_transaction_id
        )

    def _get_target_display(self, tgt_type, tgt_id):
        """获取目标对象的显示名称"""
        if not tgt_type or not tgt_id:
            return None
        try:
            from meta.core.models import registry
            from meta.core.datasource import get_data_source
            import os

            meta = registry.get(tgt_type)
            if not meta:
                return None

            table_name = getattr(meta, 'table_name', None)
            if not table_name:
                return None

            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
            ds = get_data_source('sqlite', database=db_path)

            cursor = ds.execute(f"SELECT * FROM {table_name} WHERE id = ? LIMIT 1", [int(tgt_id)])
            row = cursor.fetchone()
            if not row:
                return None

            if isinstance(row, dict):
                record = row
            else:
                cols = [desc[0] for desc in cursor.description]
                record = dict(zip(cols, row))

            display_field = getattr(meta, 'display_name_field', None)
            if display_field and display_field in record and record[display_field] not in (None, ''):
                return str(record[display_field])

            # [FIX Bug3 2026-06-09] 避免 target_display=null: 多级回退
            for fb in ('username', 'code', 'name', 'display_name', 'identifier', 'title'):
                val = record.get(fb)
                if val not in (None, ''):
                    return str(val)
            return str(tgt_id)
        except Exception as e:
            logger.debug(f"[Audit] Failed to get target display: {e}")
            return None
