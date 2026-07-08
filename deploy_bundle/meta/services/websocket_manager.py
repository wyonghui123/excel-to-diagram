# -*- coding: utf-8 -*-
"""
WebSocket 连接管理器

管理 WebSocket 连接、订阅关系和事件广播。
"""

import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any
from datetime import datetime
import json

logger = logging.getLogger(__name__)


@dataclass
class ClientSubscription:
    """客户端订阅信息"""
    sid: str
    user_id: int
    object_type: str
    event_types: List[str]
    subscribed_at: datetime = field(default_factory=datetime.now)


@dataclass
class ConnectedClient:
    """已连接的客户端"""
    sid: str
    user_id: int
    username: str = ""
    connected_at: datetime = field(default_factory=datetime.now)
    subscriptions: List[ClientSubscription] = field(default_factory=list)


class WebSocketManager:
    """WebSocket 连接管理器"""
    
    def __init__(self):
        self._lock = threading.RLock()
        self._clients: Dict[str, ConnectedClient] = {}
        self._object_subscribers: Dict[str, Set[str]] = {}
        self._socketio = None
    
    def init_socketio(self, socketio):
        """初始化 SocketIO 实例"""
        self._socketio = socketio
    
    def register_client(self, sid: str, user_id: int, username: str = ""):
        """注册新客户端连接"""
        with self._lock:
            self._clients[sid] = ConnectedClient(
                sid=sid,
                user_id=user_id,
                username=username
            )
            logger.info(f"Client registered: sid={sid}, user_id={user_id}")
    
    def unregister_client(self, sid: str):
        """注销客户端连接"""
        with self._lock:
            client = self._clients.pop(sid, None)
            if client:
                for sub in client.subscriptions:
                    if sub.object_type in self._object_subscribers:
                        self._object_subscribers[sub.object_type].discard(sid)
                        if not self._object_subscribers[sub.object_type]:
                            del self._object_subscribers[sub.object_type]
                logger.info(f"Client unregistered: sid={sid}, user_id={client.user_id}")
    
    def subscribe(self, sid: str, object_type: str, event_types: List[str]) -> bool:
        """订阅对象变更事件"""
        with self._lock:
            client = self._clients.get(sid)
            if not client:
                logger.warning(f"Subscribe failed: client not found sid={sid}")
                return False
            
            existing_sub = next(
                (s for s in client.subscriptions if s.object_type == object_type),
                None
            )
            
            if existing_sub:
                existing_sub.event_types = list(set(existing_sub.event_types + event_types))
                logger.info(f"Updated subscription: sid={sid}, object_type={object_type}, events={event_types}")
            else:
                subscription = ClientSubscription(
                    sid=sid,
                    user_id=client.user_id,
                    object_type=object_type,
                    event_types=event_types
                )
                client.subscriptions.append(subscription)
                
                if object_type not in self._object_subscribers:
                    self._object_subscribers[object_type] = set()
                self._object_subscribers[object_type].add(sid)
                logger.info(f"New subscription: sid={sid}, object_type={object_type}, events={event_types}")
            
            return True
    
    def unsubscribe(self, sid: str, object_type: str = None) -> bool:
        """取消订阅"""
        with self._lock:
            client = self._clients.get(sid)
            if not client:
                return False
            
            if object_type:
                client.subscriptions = [
                    s for s in client.subscriptions if s.object_type != object_type
                ]
                if object_type in self._object_subscribers:
                    self._object_subscribers[object_type].discard(sid)
                logger.info(f"Unsubscribed: sid={sid}, object_type={object_type}")
            else:
                for sub in client.subscriptions:
                    if sub.object_type in self._object_subscribers:
                        self._object_subscribers[sub.object_type].discard(sid)
                client.subscriptions = []
                logger.info(f"Unsubscribed all: sid={sid}")
            
            return True
    
    def broadcast_event(self, object_type: str, event_type: str, event_data: Dict[str, Any]):
        """广播变更事件到订阅者"""
        if not self._socketio:
            logger.warning("SocketIO not initialized, cannot broadcast")
            return
        
        with self._lock:
            subscriber_sids = self._object_subscribers.get(object_type, set())
            
            for sid in subscriber_sids:
                client = self._clients.get(sid)
                if not client:
                    continue
                
                subscription = next(
                    (s for s in client.subscriptions if s.object_type == object_type),
                    None
                )
                
                if subscription and event_type in subscription.event_types:
                    try:
                        self._socketio.emit(
                            'change_event',
                            {
                                'object_type': object_type,
                                'event_type': event_type,
                                'data': event_data,
                                'timestamp': datetime.now().isoformat()
                            },
                            room=sid
                        )
                        logger.debug(f"Event sent: sid={sid}, type={event_type}, object={object_type}")
                    except Exception as e:
                        logger.error(f"Failed to send event to sid={sid}: {e}")
    
    def get_client(self, sid: str) -> Optional[ConnectedClient]:
        """获取客户端信息"""
        return self._clients.get(sid)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                'total_clients': len(self._clients),
                'total_subscriptions': sum(len(c.subscriptions) for c in self._clients.values()),
                'object_types_with_subscribers': list(self._object_subscribers.keys()),
                'clients': [
                    {
                        'sid': c.sid,
                        'user_id': c.user_id,
                        'username': c.username,
                        'subscriptions': len(c.subscriptions)
                    }
                    for c in self._clients.values()
                ]
            }


websocket_manager = WebSocketManager()
