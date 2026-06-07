import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
Change Notification 配置解析测试
"""

import pytest
import os

sys_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sys
sys.path.insert(0, sys_path)

from meta.core.models import (
    ChangeEventConfig,
    WebhookConfig,
    ChangeNotificationConfig,
    UIViewConfig,
)
from meta.core.yaml_loader import (
    parse_change_event_config,
    parse_webhook_config,
    parse_change_notification_config,
    parse_ui_view_config,
)


class TestChangeEventConfig:
    """ChangeEventConfig 数据类测试"""

    def test_defaults(self):
        event = ChangeEventConfig()
        assert event.type == ""
        assert event.channels == []
        assert event.track_fields == []
        assert event.payload == []

    def test_with_values(self):
        event = ChangeEventConfig(
            type="create",
            channels=["email", "webhook"],
            track_fields=["name", "status"],
            payload=["id", "name", "created_at"]
        )
        assert event.type == "create"
        assert event.channels == ["email", "webhook"]
        assert event.track_fields == ["name", "status"]
        assert event.payload == ["id", "name", "created_at"]


class TestWebhookConfig:
    """WebhookConfig 数据类测试"""

    def test_defaults(self):
        webhook = WebhookConfig()
        assert webhook.url == ""
        assert webhook.secret == ""
        assert webhook.retry_count == 3

    def test_with_values(self):
        webhook = WebhookConfig(
            url="https://example.com/webhook",
            secret="my-secret-key",
            retry_count=5
        )
        assert webhook.url == "https://example.com/webhook"
        assert webhook.secret == "my-secret-key"
        assert webhook.retry_count == 5


class TestChangeNotificationConfig:
    """ChangeNotificationConfig 数据类测试"""

    def test_defaults(self):
        config = ChangeNotificationConfig()
        assert config.enabled is False
        assert config.events == []
        assert config.webhook_config is None

    def test_with_values(self):
        event1 = ChangeEventConfig(type="create", channels=["email"])
        event2 = ChangeEventConfig(type="update", channels=["webhook"])
        webhook = WebhookConfig(url="https://example.com/hook")

        config = ChangeNotificationConfig(
            enabled=True,
            events=[event1, event2],
            webhook_config=webhook
        )

        assert config.enabled is True
        assert len(config.events) == 2
        assert config.events[0].type == "create"
        assert config.events[1].type == "update"
        assert config.webhook_config.url == "https://example.com/hook"


class TestParseChangeEventConfig:
    """parse_change_event_config 解析测试"""

    def test_parse_with_values(self):
        data = {
            "type": "update",
            "channels": ["email", "sms"],
            "track_fields": ["status", "priority"],
            "payload": ["id", "status", "updated_at"]
        }
        event = parse_change_event_config(data)
        assert event.type == "update"
        assert event.channels == ["email", "sms"]
        assert event.track_fields == ["status", "priority"]
        assert event.payload == ["id", "status", "updated_at"]

    def test_parse_empty(self):
        event = parse_change_event_config({})
        assert event.type == ""
        assert event.channels == []
        assert event.track_fields == []
        assert event.payload == []


class TestParseWebhookConfig:
    """parse_webhook_config 解析测试"""

    def test_parse_with_values(self):
        data = {
            "url": "https://api.example.com/notify",
            "secret": "super-secret",
            "retry_count": 10
        }
        webhook = parse_webhook_config(data)
        assert webhook.url == "https://api.example.com/notify"
        assert webhook.secret == "super-secret"
        assert webhook.retry_count == 10

    def test_parse_defaults(self):
        webhook = parse_webhook_config({})
        assert webhook.url == ""
        assert webhook.secret == ""
        assert webhook.retry_count == 3


class TestParseChangeNotificationConfig:
    """parse_change_notification_config 解析测试"""

    def test_parse_with_values(self):
        data = {
            "enabled": True,
            "events": [
                {"type": "create", "channels": ["email"], "track_fields": ["name"], "payload": ["id", "name"]},
                {"type": "delete", "channels": ["webhook"], "track_fields": ["id"], "payload": ["id"]}
            ],
            "webhook_config": {
                "url": "https://example.com/webhook",
                "secret": "webhook-secret",
                "retry_count": 5
            }
        }
        config = parse_change_notification_config(data)
        assert config.enabled is True
        assert len(config.events) == 2
        assert config.events[0].type == "create"
        assert config.events[0].channels == ["email"]
        assert config.events[1].type == "delete"
        assert config.events[1].channels == ["webhook"]
        assert config.webhook_config is not None
        assert config.webhook_config.url == "https://example.com/webhook"
        assert config.webhook_config.retry_count == 5

    def test_parse_empty(self):
        config = parse_change_notification_config({})
        assert config.enabled is False
        assert config.events == []
        assert config.webhook_config is None

    def test_parse_no_webhook(self):
        data = {
            "enabled": True,
            "events": [{"type": "create", "channels": ["email"]}]
        }
        config = parse_change_notification_config(data)
        assert config.enabled is True
        assert len(config.events) == 1
        assert config.webhook_config is None


class TestParseUIViewConfig:
    """parse_ui_view_config 解析测试"""

    def test_parse_with_change_notification(self):
        data = {
            "list": {"columns": [{"key": "name", "title": "名称"}]},
            "change_notification": {
                "enabled": True,
                "events": [{"type": "update", "channels": ["webhook"], "track_fields": ["status"], "payload": ["id", "status"]}],
                "webhook_config": {"url": "https://notify.example.com/hook", "secret": "test-secret"}
            }
        }
        view_config = parse_ui_view_config(data)
        assert view_config.change_notification is not None
        assert view_config.change_notification.enabled is True
        assert len(view_config.change_notification.events) == 1
        assert view_config.change_notification.events[0].type == "update"
        assert view_config.change_notification.webhook_config is not None
        assert view_config.change_notification.webhook_config.url == "https://notify.example.com/hook"

    def test_parse_without_change_notification(self):
        data = {"list": {"columns": [{"key": "name", "title": "名称"}]}}
        view_config = parse_ui_view_config(data)
        assert view_config.change_notification is None


class TestUIViewConfigIntegration:
    """UIViewConfig 集成测试"""

    def test_integration(self):
        event = ChangeEventConfig(type="create", channels=["email"])
        webhook = WebhookConfig(url="https://example.com/hook")
        notification = ChangeNotificationConfig(enabled=True, events=[event], webhook_config=webhook)
        view_config = UIViewConfig(change_notification=notification)

        assert view_config.change_notification is not None
        assert view_config.change_notification.enabled is True
        assert len(view_config.change_notification.events) == 1
        assert view_config.change_notification.webhook_config.url == "https://example.com/hook"
