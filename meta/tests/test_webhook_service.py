import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
Webhook 服务测试

测试 Webhook 投递、签名和重试功能。
"""

import pytest
import sys
import os
import json
import hashlib
import hmac

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.services.webhook_service import (
    WebhookService,
    WebhookConfig,
    WebhookPayload,
    WebhookResult
)


class TestWebhookConfig:
    """Webhook 配置测试"""

    def test_config_creation(self):
        """测试配置创建"""
        config = WebhookConfig(
            url="https://example.com/webhook",
            secret="my-secret",
            retry_count=3
        )
        
        assert config.url == "https://example.com/webhook"
        assert config.secret == "my-secret"
        assert config.retry_count == 3

    def test_config_defaults(self):
        """测试配置默认值"""
        config = WebhookConfig(url="https://example.com/webhook")
        
        assert config.secret == ""
        assert config.retry_count == 3
        assert config.timeout == 30


class TestWebhookPayload:
    """Webhook 载荷测试"""

    def test_payload_creation(self):
        """测试载荷创建"""
        payload = WebhookPayload(
            event_id=1,
            object_type="business_object",
            object_id=123,
            event_type="created",
            changed_fields=["name", "status"],
            old_values={},
            new_values={"name": "Test", "status": "active"}
        )
        
        assert payload.event_id == 1
        assert payload.object_type == "business_object"
        assert payload.event_type == "created"

    def test_payload_to_dict(self):
        """测试载荷转换为字典"""
        payload = WebhookPayload(
            event_id=1,
            object_type="business_object",
            object_id=123,
            event_type="created",
            changed_fields=["name"],
            old_values={},
            new_values={"name": "Test"}
        )
        
        result = payload.to_dict()
        
        assert result['event_id'] == 1
        assert result['object_type'] == "business_object"
        assert result['event_type'] == "created"
        assert result['changed_fields'] == ["name"]
        assert 'timestamp' in result


class TestWebhookService:
    """Webhook 服务测试"""

    def test_signature_generation(self):
        """测试签名生成"""
        service = WebhookService()
        payload = '{"event_id": 1}'
        secret = "my-secret"
        
        signature = service._generate_signature(payload, secret)
        
        assert signature.startswith("sha256=")
        
        expected_sig = hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        assert signature == f"sha256={expected_sig}"

    def test_signature_verification(self):
        """测试签名验证"""
        service = WebhookService()
        payload = '{"event_id": 1}'
        secret = "my-secret"
        
        signature = service._generate_signature(payload, secret)
        
        assert service.verify_signature(payload, signature, secret) is True
        assert service.verify_signature(payload, "sha256=invalid", secret) is False
        assert service.verify_signature(payload, signature, "wrong-secret") is False

    def test_signature_verification_invalid_format(self):
        """测试签名验证无效格式"""
        service = WebhookService()
        
        assert service.verify_signature("{}", "invalid", "secret") is False
        assert service.verify_signature("{}", "", "secret") is False

    def test_retry_delay_calculation(self):
        """测试重试延迟计算"""
        service = WebhookService()
        
        assert service._calculate_retry_delay(0) == 1
        assert service._calculate_retry_delay(1) == 2
        assert service._calculate_retry_delay(2) == 4
        assert service._calculate_retry_delay(3) == 8
        assert service._calculate_retry_delay(10) == service.MAX_RETRY_DELAY

    def test_deliver_invalid_url(self):
        """测试无效 URL 投递"""
        service = WebhookService()
        config = WebhookConfig(url="not-a-valid-url")
        payload = WebhookPayload(
            event_id=1,
            object_type="test",
            object_id=1,
            event_type="created"
        )
        
        result = service.deliver(config, payload)
        
        assert result.success is False
        assert result.error != ""

    def test_deliver_nonexistent_host(self):
        """测试不存在主机投递"""
        service = WebhookService()
        config = WebhookConfig(
            url="https://nonexistent-host-12345.example/webhook",
            timeout=5
        )
        payload = WebhookPayload(
            event_id=1,
            object_type="test",
            object_id=1,
            event_type="created"
        )
        
        result = service.deliver(config, payload)
        
        assert result.success is False

    def test_queue_event(self):
        """测试事件入队"""
        service = WebhookService()
        
        service.queue_event({'id': 1, 'event_type': 'created'})
        service.queue_event({'id': 2, 'event_type': 'updated'})
        
        assert len(service._pending_queue) == 2


class TestWebhookResult:
    """Webhook 结果测试"""

    def test_success_result(self):
        """测试成功结果"""
        result = WebhookResult(
            success=True,
            status_code=200,
            response='{"status": "ok"}'
        )
        
        assert result.success is True
        assert result.status_code == 200
        assert result.error == ""

    def test_failure_result(self):
        """测试失败结果"""
        result = WebhookResult(
            success=False,
            status_code=500,
            error="Internal Server Error"
        )
        
        assert result.success is False
        assert result.status_code == 500
        assert result.error == "Internal Server Error"

    def test_default_values(self):
        """测试默认值"""
        result = WebhookResult(success=False)
        
        assert result.status_code == 0
        assert result.response == ""
        assert result.error == ""
        assert result.retry_count == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
