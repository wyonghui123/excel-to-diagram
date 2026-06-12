# -*- coding: utf-8 -*-
"""
动作执行上下文

在拦截器链中传递的上下文对象，包含执行所需的所有信息。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from enum import Enum
import uuid
from datetime import datetime

if TYPE_CHECKING:
    from meta.core.models import MetaObject
    from meta.core.datasource import DataSource


class LockType(Enum):
    """锁类型"""
    NONE = 'none'
    OPTIMISTIC = 'optimistic'
    PESSIMISTIC = 'pessimistic'


@dataclass
class ActionResult:
    """动作执行结果"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    errors: Optional[list] = None
    total: Optional[int] = None
    status_code: Optional[int] = None


@dataclass
class ActionContext:
    """
    动作执行上下文
    
    在拦截器链中传递，包含执行所需的所有信息。
    
    Attributes:
        meta_object: 元模型对象
        action: 动作名称（如 crud_create, crud_update, activate 等）
        params: 动作参数
        data_source: 数据源
        
        user_id: 用户 ID
        user_name: 用户名
        ip_address: IP 地址
        trace_id: 追踪 ID
        
        old_data: 更新/删除前的数据
        new_data: 更新后的数据
        result: 执行结果
        
        transaction_id: 事务 ID
        is_nested_transaction: 是否嵌套事务
        
        lock_type: 锁类型
        lock_timeout: 锁超时时间（秒）
        
        extra: 扩展数据
    """
    
    meta_object: 'MetaObject'
    action: str
    params: Dict[str, Any]
    data_source: 'DataSource'
    
    user_id: Optional[int] = None
    user_name: Optional[str] = None
    ip_address: Optional[str] = None
    trace_id: Optional[str] = None
    
    old_data: Optional[Dict[str, Any]] = None
    new_data: Optional[Dict[str, Any]] = None
    result: Optional[ActionResult] = None
    
    transaction_id: Optional[str] = None
    is_nested_transaction: bool = False
    
    lock_type: LockType = LockType.NONE
    lock_timeout: int = 30
    
    extra: Dict[str, Any] = field(default_factory=dict)
    
    # [审计延迟写入 2026-06-09]
    # 在事务中执行 associate/dissociate 时，审计写入会与业务写入发生 SQLite 锁冲突。
    # 解决方案：在事务内缓存审计记录，事务提交后再写入。
    # [SPR-07 T-S09-01] 仍为私有字段, 但通过 add_pending_audit / drain_pending_audits 方法访问.
    _pending_audit_records: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        if self.trace_id is None:
            self.trace_id = str(uuid.uuid4())[:8]

    def add_pending_audit(self, audit_params: Dict[str, Any]) -> None:
        """[SPR-07 T-S09-01] 在事务中缓存审计记录, 等待事务提交后 flush.

        替代直接访问 _pending_audit_records 字段, 集中审计 API 入口.
        """
        self._pending_audit_records.append(audit_params)

    def drain_pending_audits(self) -> List[Dict[str, Any]]:
        """[SPR-07 T-S09-01] 原子获取并清空缓存的审计记录 (事务提交后调用).

        原子性: 返回列表 + 同步清空, 避免调用方先 getattr 再 clear 之间的 race condition.
        """
        pending = list(self._pending_audit_records)
        self._pending_audit_records.clear()
        return pending
    
    @property
    def object_type(self) -> str:
        """对象类型"""
        return self.meta_object.id
    
    @property
    def object_id(self) -> Optional[int]:
        """对象 ID"""
        # [FIX 2026-06-12] 关联操作 (associate/dissociate/assign/unassign/batch_*) 的源 ID
        # 都从 src_id 读取, 否则日志 object_id 为空
        if self.action in (
            'associate', 'dissociate',
            'assign', 'unassign',
            'batch_assign', 'batch_unassign',
        ):
            return self.params.get('src_id')
        return self.params.get('id')
    
    @property
    def is_crud_action(self) -> bool:
        """是否为 CRUD 动作"""
        return self.action.startswith('crud_')
    
    @property
    def is_create_action(self) -> bool:
        """是否为创建动作"""
        return self.action == 'crud_create'
    
    @property
    def is_read_action(self) -> bool:
        """是否为读取动作"""
        return self.action == 'crud_read'
    
    @property
    def is_update_action(self) -> bool:
        """是否为更新动作"""
        return self.action == 'crud_update'
    
    @property
    def is_delete_action(self) -> bool:
        """是否为删除动作"""
        return self.action == 'crud_delete'

    @property
    def is_query_action(self) -> bool:
        """是否为查询动作"""
        return self.action in ('crud_query', 'crud_read', 'query', 'list')
    
    def get_param(self, key: str, default: Any = None) -> Any:
        """获取参数"""
        return self.params.get(key, default)
    
    def set_result(self, success: bool, data: Optional[Dict] = None, 
                   message: Optional[str] = None, errors: Optional[list] = None):
        """设置执行结果"""
        self.result = ActionResult(
            success=success,
            data=data,
            message=message,
            errors=errors,
        )
