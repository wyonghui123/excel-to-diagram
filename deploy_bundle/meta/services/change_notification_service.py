# -*- coding: utf-8 -*-
"""
变更通知服务

提供变更事件的发布和管理功能，支持：
- 基于配置的事件发布
- 字段变更追踪
- 事件持久化
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime

from meta.core.datasource import DataSource
from meta.core.models import registry, ChangeNotificationConfig, ChangeEventConfig

logger = logging.getLogger(__name__)


@dataclass
class ChangeEventRequest:
    """变更事件请求"""
    object_type: str
    object_id: Any
    event_type: str
    old_data: Optional[Dict[str, Any]] = None
    new_data: Optional[Dict[str, Any]] = None
    audit_log_id: Optional[int] = None


@dataclass
class FieldChange:
    """字段变更记录"""
    field_name: str
    old_value: Any
    new_value: Any


@dataclass
class ChangeEventResult:
    """变更事件结果"""
    success: bool
    event_id: Optional[int] = None
    message: str = ""
    changed_fields: List[str] = field(default_factory=list)
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NotificationConfig:
    """通知配置"""
    enabled: bool = False
    events: List[ChangeEventConfig] = field(default_factory=list)
    channels: List[str] = field(default_factory=list)


class ChangeNotificationService:
    """
    变更通知服务
    
    负责：
    - 检查对象是否配置了 change_notification
    - 根据 event_type 匹配配置的事件
    - 追踪指定字段的变更
    - 构建事件载荷
    - 持久化事件到数据库
    """
    
    CHANGE_EVENTS_TABLE = "change_events"
    
    SYSTEM_FIELDS = {'id', 'created_at', 'created_by', 'updated_at', 'updated_by'}
    
    def __init__(self, data_source: DataSource):
        self.ds = data_source
    
    def publish_event(self, request: ChangeEventRequest) -> ChangeEventResult:
        """
        发布变更事件
        
        Args:
            request: 变更事件请求
            
        Returns:
            ChangeEventResult: 事件发布结果
        """
        try:
            config = self._get_notification_config(request.object_type)
            
            if not config or not config.enabled:
                logger.debug(
                    "Change notification not enabled for object_type: %s",
                    request.object_type
                )
                return ChangeEventResult(
                    success=True,
                    message="Change notification not configured or disabled"
                )
            
            event_config = self._find_event_config(config, request.event_type)
            
            if not event_config:
                logger.debug(
                    "Event type %s not configured for object_type: %s",
                    request.event_type,
                    request.object_type
                )
                return ChangeEventResult(
                    success=True,
                    message=f"Event type {request.event_type} not configured"
                )
            
            changed_fields = self._detect_changes(
                event_config.track_fields,
                request.old_data,
                request.new_data
            )
            
            if request.event_type == 'update' and not changed_fields:
                logger.debug(
                    "No tracked fields changed for object_type: %s, object_id: %s",
                    request.object_type,
                    request.object_id
                )
                return ChangeEventResult(
                    success=True,
                    message="No tracked fields changed"
                )
            
            payload = self._build_payload(event_config, request.new_data or request.old_data)
            
            old_values = {}
            new_values = {}
            if request.old_data and request.new_data:
                for f in changed_fields:
                    old_values[f] = request.old_data.get(f)
                    new_values[f] = request.new_data.get(f)
            
            event_data = {
                'object_type': request.object_type,
                'object_id': request.object_id,
                'event_type': request.event_type,
                'changed_fields': changed_fields,
                'old_values': old_values,
                'new_values': new_values,
                'payload': payload,
                'channels': event_config.channels,
                'status': 'pending',
                'retry_count': 0,
                'created_at': datetime.now().isoformat(),
                'audit_log_id': request.audit_log_id
            }
            
            event_id = self._save_event(event_data)
            
            self._broadcast_event(
                request.object_type,
                request.event_type,
                {
                    'event_id': event_id,
                    'object_id': request.object_id,
                    'changed_fields': changed_fields,
                    'old_values': old_values,
                    'new_values': new_values,
                    'payload': payload
                }
            )
            
            self._trigger_aggregate_refresh(
                request.object_type,
                request.object_id,
                request.event_type,
                changed_fields
            )
            
            logger.info(
                "Change event published: id=%s, object_type=%s, object_id=%s, event_type=%s",
                event_id,
                request.object_type,
                request.object_id,
                request.event_type
            )
            
            return ChangeEventResult(
                success=True,
                event_id=event_id,
                message="Event published successfully",
                changed_fields=changed_fields,
                payload=payload
            )
            
        except Exception as e:
            logger.error(
                "Failed to publish change event: object_type=%s, object_id=%s, error=%s",
                request.object_type,
                request.object_id,
                str(e),
                exc_info=True
            )
            return ChangeEventResult(
                success=False,
                message=f"Failed to publish event: {str(e)}"
            )
    
    def _build_payload(
        self,
        config: ChangeEventConfig,
        data: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        构建事件载荷
        
        Args:
            config: 事件配置
            data: 数据字典
            
        Returns:
            载荷字典
        """
        if not data:
            return {}
        
        payload = {}
        
        if not config.payload:
            payload = dict(data)
            for sys_field in self.SYSTEM_FIELDS:
                payload.pop(sys_field, None)
            return payload
        
        for field_name in config.payload:
            if field_name in data:
                payload[field_name] = data[field_name]
        
        return payload
    
    def _detect_changes(
        self,
        track_fields: List[str],
        old_data: Optional[Dict[str, Any]],
        new_data: Optional[Dict[str, Any]]
    ) -> List[str]:
        """
        检测字段变更
        
        Args:
            track_fields: 需要追踪的字段列表
            old_data: 旧数据
            new_data: 新数据
            
        Returns:
            变更的字段名列表
        """
        if not track_fields:
            return []
        
        if old_data is None and new_data is None:
            return []
        
        changed_fields = []
        
        if old_data is None:
            for f in track_fields:
                if f in new_data:
                    changed_fields.append(f)
            return changed_fields
        
        if new_data is None:
            for f in track_fields:
                if f in old_data:
                    changed_fields.append(f)
            return changed_fields
        
        for field_name in track_fields:
            if field_name not in new_data:
                continue
            
            old_value = old_data.get(field_name)
            new_value = new_data.get(field_name)
            
            if self._values_differ(old_value, new_value):
                changed_fields.append(field_name)
        
        return changed_fields
    
    def _values_differ(self, old_value: Any, new_value: Any) -> bool:
        """
        比较两个值是否不同
        
        Args:
            old_value: 旧值
            new_value: 新值
            
        Returns:
            是否不同
        """
        if old_value is None and new_value is None:
            return False
        
        if old_value is None or new_value is None:
            return True
        
        if isinstance(old_value, dict) and isinstance(new_value, dict):
            return old_value != new_value
        
        if isinstance(old_value, list) and isinstance(new_value, list):
            return old_value != new_value
        
        return str(old_value) != str(new_value)
    
    def _get_notification_config(self, object_type: str) -> Optional[ChangeNotificationConfig]:
        """
        获取对象的通知配置
        
        Args:
            object_type: 对象类型
            
        Returns:
            变更通知配置，如果不存在返回 None
        """
        meta_object = registry.get(object_type)
        
        if not meta_object:
            logger.warning("Object type not found in registry: %s", object_type)
            return None
        
        if not meta_object.ui_view_config:
            return None
        
        return meta_object.ui_view_config.change_notification
    
    def _find_event_config(
        self,
        config: ChangeNotificationConfig,
        event_type: str
    ) -> Optional[ChangeEventConfig]:
        """
        查找事件配置
        
        Args:
            config: 变更通知配置
            event_type: 事件类型
            
        Returns:
            事件配置，如果不存在返回 None
        """
        if not config.events:
            return None
        
        for event_config in config.events:
            if event_config.type == event_type:
                return event_config
        
        return None
    
    def _save_event(self, event_data: Dict[str, Any]) -> int:
        """
        持久化事件到数据库
        
        Args:
            event_data: 事件数据
            
        Returns:
            插入的事件 ID
        """
        import json
        
        record = {
            'object_type': event_data.get('object_type'),
            'object_id': event_data.get('object_id'),
            'event_type': event_data.get('event_type'),
            'changed_fields': json.dumps(event_data.get('changed_fields', [])),
            'old_values': json.dumps(event_data.get('old_values', {})),
            'new_values': json.dumps(event_data.get('new_values', {})),
            'payload': json.dumps(event_data.get('payload', {})),
            'channels': json.dumps(event_data.get('channels', [])),
            'status': event_data.get('status', 'pending'),
            'retry_count': event_data.get('retry_count', 0),
            'created_at': event_data.get('created_at'),
            'delivered_at': event_data.get('delivered_at'),
            'audit_log_id': event_data.get('audit_log_id')
        }
        
        event_id = self.ds.insert(self.CHANGE_EVENTS_TABLE, record)
        
        return event_id
    
    def get_pending_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取待处理的事件列表
        
        Args:
            limit: 返回数量限制
            
        Returns:
            待处理事件列表
        """
        return self.ds.find(
            self.CHANGE_EVENTS_TABLE,
            filters={'status': 'pending'},
            order_by='created_at ASC',
            limit=limit
        )
    
    def update_event_status(
        self,
        event_id: int,
        status: str,
        delivered_at: Optional[str] = None
    ) -> bool:
        """
        更新事件状态
        
        Args:
            event_id: 事件 ID
            status: 新状态
            delivered_at: 投递时间
            
        Returns:
            是否更新成功
        """
        data = {'status': status}
        if delivered_at:
            data['delivered_at'] = delivered_at
        
        return self.ds.update(self.CHANGE_EVENTS_TABLE, event_id, data)
    
    def increment_retry_count(self, event_id: int) -> bool:
        """
        增加重试次数
        
        Args:
            event_id: 事件 ID
            
        Returns:
            是否更新成功
        """
        event = self.ds.find_by_id(self.CHANGE_EVENTS_TABLE, event_id)
        if not event:
            return False
        
        new_count = event.get('retry_count', 0) + 1
        return self.ds.update(
            self.CHANGE_EVENTS_TABLE,
            event_id,
            {'retry_count': new_count}
        )
    
    def get_events_by_object(
        self,
        object_type: str,
        object_id: Any,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        获取对象的变更事件列表
        
        Args:
            object_type: 对象类型
            object_id: 对象 ID
            limit: 返回数量限制
            
        Returns:
            事件列表
        """
        return self.ds.find(
            self.CHANGE_EVENTS_TABLE,
            filters={
                'object_type': object_type,
                'object_id': object_id
            },
            order_by='created_at DESC',
            limit=limit
        )
    
    def _broadcast_event(
        self,
        object_type: str,
        event_type: str,
        event_data: Dict[str, Any]
    ):
        """
        广播事件到 WebSocket 订阅者
        
        Args:
            object_type: 对象类型
            event_type: 事件类型
            event_data: 事件数据
        """
        try:
            from meta.services.websocket_manager import websocket_manager
            
            websocket_manager.broadcast_event(
                object_type=object_type,
                event_type=event_type,
                event_data=event_data
            )
            
            logger.debug(
                "Event broadcasted: object_type=%s, event_type=%s",
                object_type,
                event_type
            )
        except Exception as e:
            logger.warning(
                "Failed to broadcast event: object_type=%s, event_type=%s, error=%s",
                object_type,
                event_type,
                str(e)
            )
    
    def _trigger_aggregate_refresh(
        self,
        object_type: str,
        object_id: Any,
        event_type: str,
        changed_fields: List[str]
    ):
        """触发聚合刷新
        
        当数据变更时，检查是否有物化聚合需要刷新。
        """
        try:
            from meta.core.aggregate_manager import get_aggregate_manager
            from meta.core.aggregate_refresh_handler import AggregateRefreshHandler
            
            manager = get_aggregate_manager()
            if not manager:
                return
            
            handler = AggregateRefreshHandler(manager)
            refreshed = handler.on_data_changed(
                object_type, object_id, event_type
            )
            
            if refreshed > 0:
                logger.info(
                    "Aggregate refresh triggered by change event: object_type=%s, object_id=%s, refreshed=%d",
                    object_type, object_id, refreshed
                )
                
        except Exception as e:
            logger.warning(
                "Failed to trigger aggregate refresh: object_type=%s, object_id=%s, error=%s",
                object_type, object_id, str(e)
            )
