import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
WebSocket 变更通知测试

测试 WebSocket 连接、订阅和事件推送功能。
"""

import pytest
import sys
import os
import json
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.services.websocket_manager import WebSocketManager, ConnectedClient, ClientSubscription


class TestWebSocketManager:
    """WebSocket 管理器测试"""

    def test_register_client(self):
        """测试客户端注册"""
        manager = WebSocketManager()
        manager.register_client("sid-1", user_id=1, username="test_user")
        
        client = manager.get_client("sid-1")
        assert client is not None
        assert client.user_id == 1
        assert client.username == "test_user"

    def test_unregister_client(self):
        """测试客户端注销"""
        manager = WebSocketManager()
        manager.register_client("sid-1", user_id=1)
        
        manager.unregister_client("sid-1")
        
        client = manager.get_client("sid-1")
        assert client is None

    def test_subscribe(self):
        """测试订阅"""
        manager = WebSocketManager()
        manager.register_client("sid-1", user_id=1)
        
        success = manager.subscribe("sid-1", "business_object", ["created", "updated"])
        
        assert success is True
        client = manager.get_client("sid-1")
        assert len(client.subscriptions) == 1
        assert client.subscriptions[0].object_type == "business_object"

    def test_subscribe_multiple_event_types(self):
        """测试订阅多种事件类型"""
        manager = WebSocketManager()
        manager.register_client("sid-1", user_id=1)
        
        manager.subscribe("sid-1", "business_object", ["created"])
        manager.subscribe("sid-1", "business_object", ["updated"])
        
        client = manager.get_client("sid-1")
        assert len(client.subscriptions) == 1
        assert set(client.subscriptions[0].event_types) == {"created", "updated"}

    def test_subscribe_multiple_object_types(self):
        """测试订阅多种对象类型"""
        manager = WebSocketManager()
        manager.register_client("sid-1", user_id=1)
        
        manager.subscribe("sid-1", "business_object", ["created"])
        manager.subscribe("sid-1", "domain", ["created", "updated"])
        
        client = manager.get_client("sid-1")
        assert len(client.subscriptions) == 2

    def test_unsubscribe_single_object_type(self):
        """测试取消单个对象类型订阅"""
        manager = WebSocketManager()
        manager.register_client("sid-1", user_id=1)
        manager.subscribe("sid-1", "business_object", ["created"])
        manager.subscribe("sid-1", "domain", ["created"])
        
        manager.unsubscribe("sid-1", "business_object")
        
        client = manager.get_client("sid-1")
        assert len(client.subscriptions) == 1
        assert client.subscriptions[0].object_type == "domain"

    def test_unsubscribe_all(self):
        """测试取消所有订阅"""
        manager = WebSocketManager()
        manager.register_client("sid-1", user_id=1)
        manager.subscribe("sid-1", "business_object", ["created"])
        manager.subscribe("sid-1", "domain", ["created"])
        
        manager.unsubscribe("sid-1")
        
        client = manager.get_client("sid-1")
        assert len(client.subscriptions) == 0

    def test_subscribe_nonexistent_client(self):
        """测试不存在的客户端订阅"""
        manager = WebSocketManager()
        
        success = manager.subscribe("nonexistent-sid", "business_object", ["created"])
        
        assert success is False

    def test_unregister_clears_subscriptions(self):
        """测试注销清除订阅"""
        manager = WebSocketManager()
        manager.register_client("sid-1", user_id=1)
        manager.subscribe("sid-1", "business_object", ["created"])
        
        manager.unregister_client("sid-1")
        
        stats = manager.get_stats()
        assert stats['total_subscriptions'] == 0

    def test_get_stats(self):
        """测试获取统计信息"""
        manager = WebSocketManager()
        manager.register_client("sid-1", user_id=1)
        manager.register_client("sid-2", user_id=2)
        manager.subscribe("sid-1", "business_object", ["created"])
        
        stats = manager.get_stats()
        
        assert stats['total_clients'] == 2
        assert stats['total_subscriptions'] == 1
        assert 'business_object' in stats['object_types_with_subscribers']

    def test_broadcast_event_no_socketio(self):
        """测试无 SocketIO 时广播"""
        manager = WebSocketManager()
        manager.register_client("sid-1", user_id=1)
        manager.subscribe("sid-1", "business_object", ["created"])
        
        manager.broadcast_event("business_object", "created", {"id": 1})
        
        assert True

    def test_thread_safety(self):
        """测试线程安全"""
        manager = WebSocketManager()
        errors = []
        
        def register_clients():
            try:
                for i in range(100):
                    manager.register_client(f"sid-{threading.current_thread().name}-{i}", user_id=i)
            except Exception as e:
                errors.append(e)
        
        threads = [
            threading.Thread(target=register_clients, name=f"t{i}")
            for i in range(5)
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        stats = manager.get_stats()
        assert stats['total_clients'] == 500


class TestClientSubscription:
    """客户端订阅数据类测试"""

    def test_subscription_creation(self):
        """测试订阅创建"""
        sub = ClientSubscription(
            sid="sid-1",
            user_id=1,
            object_type="business_object",
            event_types=["created", "updated"]
        )
        
        assert sub.sid == "sid-1"
        assert sub.user_id == 1
        assert sub.object_type == "business_object"
        assert sub.event_types == ["created", "updated"]

    def test_subscription_default_values(self):
        """测试订阅默认值"""
        sub = ClientSubscription(
            sid="sid-1",
            user_id=1,
            object_type="business_object",
            event_types=["created"]
        )
        
        assert sub.subscribed_at is not None


class TestConnectedClient:
    """已连接客户端数据类测试"""

    def test_client_creation(self):
        """测试客户端创建"""
        client = ConnectedClient(
            sid="sid-1",
            user_id=1,
            username="test_user"
        )
        
        assert client.sid == "sid-1"
        assert client.user_id == 1
        assert client.username == "test_user"
        assert client.subscriptions == []

    def test_client_default_values(self):
        """测试客户端默认值"""
        client = ConnectedClient(sid="sid-1", user_id=1)
        
        assert client.connected_at is not None
        assert client.subscriptions == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
