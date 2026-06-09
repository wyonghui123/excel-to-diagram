# -*- coding: utf-8 -*-
"""
结构化日志记录器

提供统一的日志写入接口，支持多种日志类型路由。
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List
from datetime import datetime
import json
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from enums.log_category import LogCategory
from enums.log_level import LogLevel


@dataclass
class LogEntry:
    """
    日志条目数据类
    
    表示一条结构化的日志记录，包含所有必要的信息用于审计、追踪和分析。
    
    Attributes:
        category: 日志类型 (必填)
        level: 日志级别 (必填)
        action: 操作类型 (必填)，如 CREATE/UPDATE/DELETE/LOGIN 等
        object_type: 对象类型，如 user/role/user_group 等
        object_id: 对象ID
        user_id: 执行操作的用户ID
        user_name: 执行操作的用户名
        ip_address: 客户端IP地址
        user_agent: 客户端User-Agent
        old_data: 变更前的数据 (用于UPDATE操作)
        new_data: 变更后的数据 (用于UPDATE/CREATE操作)
        field_name: 变更的字段名 (用于字段级别追踪)
        trace_id: 链路追踪ID，用于分布式追踪
        transaction_id: 事务ID，用于关联同一事务的多个操作
        agent_id: AI Agent标识
        agent_session_id: AI Agent会话ID
        tool_call_id: 工具调用ID (用于幂等性检查)
        agent_reasoning: AI Agent推理上下文
        extra_data: 附加数据，用于存储自定义信息
        created_at: 创建时间 (自动生成)
    """
    
    # 必填字段
    category: LogCategory
    level: LogLevel
    action: str
    
    # 对象信息
    object_type: Optional[str] = None
    object_id: Optional[int] = None
    
    # 用户上下文
    user_id: Optional[int] = None
    user_name: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    # 变更数据
    old_data: Optional[Dict[str, Any]] = None
    new_data: Optional[Dict[str, Any]] = None
    field_name: Optional[str] = None
    
    # 追踪信息
    trace_id: Optional[str] = None
    transaction_id: Optional[str] = None
    
    # AI Agent 追踪
    agent_id: Optional[str] = None
    agent_session_id: Optional[str] = None
    tool_call_id: Optional[str] = None
    agent_reasoning: Optional[str] = None
    
    # 父对象关联（用于级联审计查询）
    parent_object_type: Optional[str] = None
    parent_object_id: Optional[str] = None
    
    # 附加数据
    extra_data: Optional[Dict[str, Any]] = None
    
    # 自动生成字段
    created_at: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        """
        初始化后处理
        
        验证必填字段，设置默认值
        """
        # 验证必填字段
        if not self.action:
            raise ValueError("action is required")
        
        # 确保 category 是 LogCategory 类型
        if isinstance(self.category, str):
            self.category = LogCategory.from_string(self.category)
        
        # 确保 level 是 LogLevel 类型
        if isinstance(self.level, str):
            self.level = LogLevel.from_string(self.level)
    
    def validate(self) -> List[str]:
        """
        验证日志条目的有效性
        
        Returns:
            List[str]: 验证错误列表，空列表表示验证通过
        """
        errors = []
        
        # 必填字段检查
        if not self.action:
            errors.append("action is required")
        
        # 业务日志必须有对象信息
        if self.category == LogCategory.BUSINESS:
            if not self.object_type:
                errors.append("object_type is required for business logs")
            if not self.object_id:
                errors.append("object_id is required for business logs")
        
        # UPDATE 操作应该有变更数据
        if self.action == "UPDATE":
            if not self.old_data and not self.new_data:
                errors.append("old_data or new_data is required for UPDATE action")
        
        return errors
    
    def is_valid(self) -> bool:
        """
        检查日志条目是否有效
        
        Returns:
            bool: True 表示有效，False 表示无效
        """
        return len(self.validate()) == 0
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典格式
        
        Returns:
            Dict[str, Any]: 字典表示
        """
        data = asdict(self)
        
        # 转换枚举为字符串
        data['category'] = self.category.value
        data['level'] = self.level.value
        
        # 转换 datetime 为 ISO 格式字符串
        data['created_at'] = self.created_at.isoformat()
        
        # 移除 None 值
        return {k: v for k, v in data.items() if v is not None}
    
    def to_json(self) -> str:
        """
        转换为 JSON 字符串
        
        Returns:
            str: JSON 字符串
        """
        return json.dumps(self.to_dict(), ensure_ascii=False)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LogEntry':
        """
        从字典创建 LogEntry 实例
        
        Args:
            data: 字典数据
            
        Returns:
            LogEntry: 日志条目实例
        """
        # 处理枚举字段
        if 'category' in data and isinstance(data['category'], str):
            data['category'] = LogCategory.from_string(data['category'])
        
        if 'level' in data and isinstance(data['level'], str):
            data['level'] = LogLevel.from_string(data['level'])
        
        # 处理 datetime 字段
        if 'created_at' in data and isinstance(data['created_at'], str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        
        return cls(**data)
    
    def get_business_key(self) -> Optional[str]:
        """
        获取业务键 (用于前端展示)
        
        格式: object_type:object_id 或 user_name(user_id)
        
        Returns:
            Optional[str]: 业务键字符串
        """
        if self.object_type and self.object_id:
            return f"{self.object_type}:{self.object_id}"
        elif self.user_name and self.user_id:
            return f"{self.user_name}({self.user_id})"
        return None
    
    def __str__(self) -> str:
        """字符串表示"""
        return (f"LogEntry(category={self.category.value}, "
                f"level={self.level.value}, action={self.action}, "
                f"object_type={self.object_type}, object_id={self.object_id})")
    
    def __repr__(self) -> str:
        """详细字符串表示"""
        return self.__str__()


class StructuredLogger:
    """
    结构化日志记录器
    
    提供统一的日志写入接口，支持多种日志类型路由到不同的存储后端。
    
    Features:
        - 统一日志接口 (log_business, log_security 等)
        - 异步写入支持
        - 多存储后端适配
        - 统计功能
    
    Usage:
        # 直接使用快捷方法
        structured_logger.log_business(
            action='UPDATE',
            object_type='user',
            object_id=123,
            user_id=1,
            old_data={'email': 'old@example.com'},
            new_data={'email': 'new@example.com'}
        )
        
        # 使用统一入口
        entry = LogEntry(
            category=LogCategory.BUSINESS,
            level=LogLevel.INFO,
            action='UPDATE',
            object_type='user',
            object_id=123
        )
        structured_logger.log(entry)
    """
    
    def __init__(self, async_writer=None):
        """
        初始化 StructuredLogger
        
        Args:
            async_writer: 异步写入器实例，用于异步写入审计日志
        """
        self._async_writer = async_writer
        self._stats = {
            'total_submitted': 0,
            'total_written': 0,
            'total_failed': 0,
            'by_category': {},
            'by_level': {},
            'by_action': {}
        }
    
    def log(self, entry: LogEntry) -> bool:
        """
        统一日志入口方法
        
        根据日志条目的 category 路由到对应的处理器。
        
        Args:
            entry: 日志条目
            
        Returns:
            bool: 写入是否成功
        """
        if not entry.is_valid():
            errors = entry.validate()
            print(f"[ERROR] Invalid log entry: {errors}")
            self._stats['total_failed'] += 1
            return False
        
        self._stats['total_submitted'] += 1
        
        try:
            if entry.category == LogCategory.BUSINESS:
                return self._log_business(entry)
            elif entry.category == LogCategory.SECURITY:
                return self._log_security(entry)
            elif entry.category == LogCategory.OPERATION:
                return self._log_operation(entry)
            elif entry.category == LogCategory.PERFORMANCE:
                return self._log_performance(entry)
            elif entry.category == LogCategory.SYSTEM:
                return self._log_system(entry)
            else:
                # 默认作为业务日志处理
                return self._log_business(entry)
        except Exception as e:
            print(f"[ERROR] Failed to log entry: {e}")
            self._stats['total_failed'] += 1
            return False
    
    def log_business(self, action: str, object_type: str = None, object_id: int = None,
                     user_id: int = None, user_name: str = None,
                     old_data: Dict = None, new_data: Dict = None,
                     field_name: str = None, ip_address: str = None,
                     trace_id: str = None, transaction_id: str = None,
                     parent_object_type: str = None, parent_object_id: Any = None,
                     level: str = "INFO", **kwargs) -> bool:
        """
        记录业务审计日志
        
        用于记录业务对象的 CRUD 操作，如创建、更新、删除等。
        
        Args:
            action: 操作类型 (CREATE/UPDATE/DELETE/ASSIGN/REVOKE)
            object_type: 对象类型 (user/role/user_group 等)
            object_id: 对象ID
            user_id: 执行操作的用户ID
            user_name: 执行操作的用户名
            old_data: 变更前数据
            new_data: 变更后数据
            field_name: 变更的字段名
            ip_address: 客户端IP
            trace_id: 链路追踪ID
            transaction_id: 事务ID
            level: 日志级别 (默认 INFO)
            
        Returns:
            bool: 写入是否成功
            
        Example:
            structured_logger.log_business(
                action='UPDATE',
                object_type='user',
                object_id=123,
                user_id=1,
                user_name='admin',
                old_data={'email': 'old@example.com'},
                new_data={'email': 'new@example.com'},
                field_name='email'
            )
        """
        entry = LogEntry(
            category=LogCategory.BUSINESS,
            level=LogLevel.from_string(level),
            action=action,
            object_type=object_type,
            object_id=object_id,
            user_id=user_id,
            user_name=user_name,
            old_data=old_data,
            new_data=new_data,
            field_name=field_name,
            ip_address=ip_address,
            trace_id=trace_id,
            transaction_id=transaction_id,
            parent_object_type=parent_object_type,
            parent_object_id=str(parent_object_id) if parent_object_id is not None else None,
            extra_data=kwargs
        )
        
        return self.log(entry)
    
    def log_security(self, event_type: str, severity: str = "INFO",
                    user_id: int = None, user_name: str = None,
                    source_ip: str = None, target_user_id: int = None,
                    details: Dict = None, trace_id: str = None,
                    transaction_id: str = None, **kwargs) -> bool:
        """
        记录安全日志
        
        用于记录登录、登出、权限变更等安全相关事件。
        
        Args:
            event_type: 事件类型 (LOGIN/LOGOUT/LOGIN_FAILED/PERMISSION_DENIED 等)
            severity: 严重程度 (DEBUG/INFO/WARNING/ERROR/CRITICAL)
            user_id: 用户ID
            user_name: 用户名
            source_ip: 源IP地址
            target_user_id: 目标用户ID
            details: 详细信息
            trace_id: 链路追踪ID
            transaction_id: 事务ID
            
        Returns:
            bool: 写入是否成功
            
        Example:
            structured_logger.log_security(
                event_type='LOGIN_FAILED',
                severity='WARNING',
                user_name='admin',
                source_ip='192.168.1.100',
                details={'reason': 'wrong_password', 'attempts': 3}
            )
        """
        entry = LogEntry(
            category=LogCategory.SECURITY,
            level=LogLevel.from_string(severity),
            action=event_type,
            user_id=user_id,
            user_name=user_name,
            ip_address=source_ip,
            object_id=target_user_id,
            trace_id=trace_id,
            transaction_id=transaction_id,
            extra_data=details,
            **kwargs
        )
        
        return self.log(entry)
    
    def log_operation(self, operation: str, level: str = "INFO",
                     message: str = None, source: str = None,
                     error: str = None, trace_id: str = None, **kwargs) -> bool:
        """
        记录运营日志
        
        用于记录系统运行状态、错误等信息。
        
        Args:
            operation: 操作名称
            level: 日志级别
            message: 消息内容
            source: 来源 (service/module name)
            error: 错误信息
            trace_id: 链路追踪ID
        """
        # [FIX Bug 2026-06-09] 把 kwargs 里的 object_type/object_id/user_id/user_name/ip_address
        # 提到 LogEntry 字段, 否则 audit_logs 表 NOT NULL 约束会 fallback 到 "_unknown" / ""
        # 详见: 75927-75935 audit log 中 object_type='_unknown' 现象
        object_type = kwargs.pop('object_type', None)
        object_id = kwargs.pop('object_id', None)
        user_id = kwargs.pop('user_id', None)
        user_name = kwargs.pop('user_name', None)
        ip_address = kwargs.pop('ip_address', None)
        user_agent = kwargs.pop('user_agent', None)
        transaction_id = kwargs.pop('transaction_id', None)

        extra_data = {
            'message': message,
            'source': source,
            'error': error,
            **kwargs
        }
        
        entry = LogEntry(
            category=LogCategory.OPERATION,
            level=LogLevel.from_string(level),
            action=operation,
            trace_id=trace_id,
            object_type=object_type,
            object_id=object_id,
            user_id=user_id,
            user_name=user_name,
            ip_address=ip_address,
            user_agent=user_agent,
            transaction_id=transaction_id,
            extra_data=extra_data
        )
        
        return self.log(entry)
    
    def log_performance(self, metric_name: str, metric_value: float,
                       unit: str = "ms", tags: Dict = None,
                       threshold: float = None, trace_id: str = None, **kwargs) -> bool:
        """
        记录性能日志
        
        用于记录性能指标、慢查询等信息。
        
        Args:
            metric_name: 指标名称 (如 api_response_time, db_query_time)
            metric_value: 指标值
            unit: 单位 (ms/s/bytes 等)
            tags: 标签 (endpoint/method 等)
            threshold: 阈值 (超过此值记录 WARNING)
            trace_id: 链路追踪ID
            
        Returns:
            bool: 写入是否成功
        """
        level = LogLevel.INFO
        if threshold and metric_value > threshold:
            level = LogLevel.WARNING
        
        extra_data = {
            'metric_name': metric_name,
            'metric_value': metric_value,
            'unit': unit,
            'threshold': threshold,
            'tags': tags,
            **kwargs
        }
        
        entry = LogEntry(
            category=LogCategory.PERFORMANCE,
            level=level,
            action=metric_name,
            trace_id=trace_id,
            extra_data=extra_data
        )
        
        return self.log(entry)
    
    def log_system(self, event: str, level: str = "INFO",
                   details: Dict = None, **kwargs) -> bool:
        """
        记录系统日志
        
        用于记录系统启动、关闭、配置变更等系统级事件。
        
        Args:
            event: 事件名称 (STARTUP/SHUTDOWN/CONFIG_CHANGE 等)
            level: 日志级别
            details: 详细信息
            
        Returns:
            bool: 写入是否成功
        """
        entry = LogEntry(
            category=LogCategory.SYSTEM,
            level=LogLevel.from_string(level),
            action=event,
            extra_data=details,
            **kwargs
        )
        
        return self.log(entry)
    
    def _log_business(self, entry: LogEntry) -> bool:
        """内部方法：处理业务日志写入"""
        self._update_stats(entry, 'business')
        
        if self._async_writer:
            def write_task(trace_id=None, transaction_id=None):
                self._write_to_audit_logs(entry)
            self._async_writer.submit(write_task)
            return True
        else:
            return self._write_to_audit_logs(entry)
    
    def _log_security(self, entry: LogEntry) -> bool:
        """内部方法：处理安全日志写入"""
        self._update_stats(entry, 'security')
        
        if self._async_writer:
            def write_task(trace_id=None, transaction_id=None):
                self._write_to_audit_logs(entry)
            self._async_writer.submit(write_task)
            return True
        else:
            return self._write_to_audit_logs(entry)
    
    def _log_operation(self, entry: LogEntry) -> bool:
        """内部方法：处理运营日志写入"""
        self._update_stats(entry, 'operation')
        
        return self._write_to_audit_logs(entry)
    
    def _log_performance(self, entry: LogEntry) -> bool:
        """内部方法：处理性能日志写入"""
        self._update_stats(entry, 'performance')
        
        return self._write_to_audit_logs(entry)
    
    def _log_system(self, entry: LogEntry) -> bool:
        """内部方法：处理系统日志写入"""
        self._update_stats(entry, 'system')
        
        return self._write_to_audit_logs(entry)
    
    def _write_to_audit_logs(self, entry: LogEntry) -> bool:
        try:
            from meta.services.async_audit_writer import async_audit_writer
            ds = getattr(async_audit_writer, '_ds', None)
            if ds is None:
                try:
                    from meta.core.bo_framework import bo_framework
                    ds = getattr(bo_framework, '_data_source', None)
                except Exception:
                    pass
            if ds is None:
                from meta.core.datasource import get_data_source
                import os
                db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
                ds = get_data_source('sqlite', database=db_path)
            from meta.services.audit_service import AuditService
            audit_service = AuditService(ds)

            # [FIX Bug2 2026-06-09] OperationLogInterceptor 调用 log_operation() 时,
            # object_type/user_name/user_id/object_id/ip_address 是通过 **kwargs 传入的,
            # log_operation() 把它们塞进 extra_data 而不是 LogEntry 顶层字段。
            # 这里在写审计日志前从 extra_data 提取回顶层, 避免 audit_service.log() 兜底 '_unknown'。
            entry_object_type = entry.object_type
            entry_object_id = entry.object_id
            entry_user_id = entry.user_id
            entry_user_name = entry.user_name
            entry_ip_address = entry.ip_address

            if entry.extra_data and isinstance(entry.extra_data, dict):
                if entry_object_type is None and entry.extra_data.get('object_type') is not None:
                    entry_object_type = entry.extra_data.get('object_type')
                if entry_object_id is None and entry.extra_data.get('object_id') is not None:
                    entry_object_id = entry.extra_data.get('object_id')
                if entry_user_id is None and entry.extra_data.get('user_id') is not None:
                    entry_user_id = entry.extra_data.get('user_id')
                if entry_user_name is None and entry.extra_data.get('user_name') is not None:
                    entry_user_name = entry.extra_data.get('user_name')
                if entry_ip_address is None and entry.extra_data.get('ip_address') is not None:
                    entry_ip_address = entry.extra_data.get('ip_address')

            old_value = None
            new_value = None

            if entry.old_data:
                old_value = json.dumps(entry.old_data, ensure_ascii=False)
            if entry.new_data:
                new_value = json.dumps(entry.new_data, ensure_ascii=False)

            # [FIX Bug1 2026-06-09] 同时传递 old_data/new_data (dict) 和 old_value/new_value (JSON str)
            # - 当 entry.field_name 为 None (CRUD 走 BusinessLogInterceptor) 时, AuditService.log
            #   走 elif 分支, 需要 old_data/new_data 是 dict 才能展开为多行字段
            # - 当 entry.field_name 有值 (ASSOCIATE/DISSOCIATE) 时, AuditService.log 走 if field_name
            #   分支, 使用 old_value/new_value (JSON 字符串), old_data/new_data 被忽略
            # 同时传两个是兼容两种调用场景, 避免业务侧日志退化为 fallback `_record` 行
            audit_service.log(
                object_type=entry_object_type,
                object_id=entry_object_id,
                action=entry.action,
                user_id=entry_user_id,
                user_name=entry_user_name,
                old_data=entry.old_data,
                new_data=entry.new_data,
                old_value=old_value,
                new_value=new_value,
                field_name=entry.field_name,
                ip_address=entry_ip_address,
                trace_id=entry.trace_id,
                transaction_id=entry.transaction_id,
                extra_data=entry.extra_data,
                parent_object_type=entry.parent_object_type,
                parent_object_id=entry.parent_object_id,
            )

            self._stats['total_written'] += 1
            return True

        except Exception as e:
            print(f"[ERROR] Failed to write audit log: {e}")
            self._stats['total_failed'] += 1
            return False
    
    def _update_stats(self, entry: LogEntry, category: str):
        """更新统计信息"""
        self._stats['by_category'][category] = self._stats['by_category'].get(category, 0) + 1
        self._stats['by_level'][entry.level.value] = self._stats['by_level'].get(entry.level.value, 0) + 1
        self._stats['by_action'][entry.action] = self._stats['by_action'].get(entry.action, 0) + 1
    
    def get_stats(self) -> Dict:
        """
        获取统计信息
        
        Returns:
            Dict: 统计信息字典
        """
        return {
            'total_submitted': self._stats['total_submitted'],
            'total_written': self._stats['total_written'],
            'total_failed': self._stats['total_failed'],
            'success_rate': (
                self._stats['total_written'] / self._stats['total_submitted'] * 100
                if self._stats['total_submitted'] > 0 else 0
            ),
            'by_category': self._stats['by_category'],
            'by_level': self._stats['by_level'],
            'by_action': self._stats['by_action']
        }
    
    def reset_stats(self):
        """重置统计信息"""
        self._stats = {
            'total_submitted': 0,
            'total_written': 0,
            'total_failed': 0,
            'by_category': {},
            'by_level': {},
            'by_action': {}
        }


# 全局实例
structured_logger = StructuredLogger()
