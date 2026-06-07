# -*- coding: utf-8 -*-
"""
Webhook 投递服务

提供 Webhook 事件投递功能，支持：
- HTTP POST 投递
- HMAC-SHA256 签名
- 指数退避重试
- 投递状态追踪
"""

import logging
import hashlib
import hmac
import json
import time
import threading
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)


@dataclass
class WebhookConfig:
    """Webhook 配置"""
    url: str
    secret: str = ""
    retry_count: int = 3
    timeout: int = 30


@dataclass
class WebhookPayload:
    """Webhook 载荷"""
    event_id: int
    object_type: str
    object_id: Any
    event_type: str
    changed_fields: List[str] = field(default_factory=list)
    old_values: Dict[str, Any] = field(default_factory=dict)
    new_values: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'event_id': self.event_id,
            'object_type': self.object_type,
            'object_id': self.object_id,
            'event_type': self.event_type,
            'changed_fields': self.changed_fields,
            'old_values': self.old_values,
            'new_values': self.new_values,
            'timestamp': self.timestamp or datetime.now().isoformat()
        }


@dataclass
class WebhookResult:
    """Webhook 投递结果"""
    success: bool
    status_code: int = 0
    response: str = ""
    error: str = ""
    retry_count: int = 0


class WebhookService:
    """
    Webhook 投递服务
    
    负责：
    - 发送 HTTP POST 请求
    - 生成 HMAC-SHA256 签名
    - 实现指数退避重试
    - 更新事件投递状态
    """
    
    SIGNATURE_HEADER = "X-Webhook-Signature"
    EVENT_TYPE_HEADER = "X-Event-Type"
    OBJECT_TYPE_HEADER = "X-Object-Type"
    
    MAX_RETRY_DELAY = 300  # 最大重试延迟 5 分钟
    INITIAL_RETRY_DELAY = 1  # 初始重试延迟 1 秒
    
    def __init__(self, datasource=None):
        self.ds = datasource
        self._pending_queue: List[Dict[str, Any]] = []
        self._processing = False
        self._lock = threading.Lock()
    
    def deliver(
        self,
        config: WebhookConfig,
        payload: WebhookPayload
    ) -> WebhookResult:
        """
        投递 Webhook
        
        Args:
            config: Webhook 配置
            payload: 事件载荷
            
        Returns:
            WebhookResult: 投递结果
        """
        payload_dict = payload.to_dict()
        payload_json = json.dumps(payload_dict, ensure_ascii=False)
        
        headers = {
            'Content-Type': 'application/json',
            self.EVENT_TYPE_HEADER: payload.event_type,
            self.OBJECT_TYPE_HEADER: payload.object_type,
        }
        
        if config.secret:
            signature = self._generate_signature(payload_json, config.secret)
            headers[self.SIGNATURE_HEADER] = signature
        
        result = self._send_request(
            url=config.url,
            data=payload_json,
            headers=headers,
            timeout=config.timeout
        )
        
        return result
    
    def deliver_with_retry(
        self,
        config: WebhookConfig,
        payload: WebhookPayload,
        max_retries: int = None
    ) -> WebhookResult:
        """
        带重试的投递
        
        Args:
            config: Webhook 配置
            payload: 事件载荷
            max_retries: 最大重试次数
            
        Returns:
            WebhookResult: 投递结果
        """
        max_retries = max_retries or config.retry_count
        last_result = None
        
        for attempt in range(max_retries + 1):
            result = self.deliver(config, payload)
            result.retry_count = attempt
            
            if result.success:
                return result
            
            last_result = result
            
            if attempt < max_retries:
                delay = self._calculate_retry_delay(attempt)
                logger.info(
                    "Webhook delivery failed, retrying in %ds (attempt %d/%d)",
                    delay,
                    attempt + 1,
                    max_retries
                )
                time.sleep(delay)
        
        return last_result
    
    def _send_request(
        self,
        url: str,
        data: str,
        headers: Dict[str, str],
        timeout: int
    ) -> WebhookResult:
        """
        发送 HTTP 请求
        
        Args:
            url: 目标 URL
            data: 请求体
            headers: 请求头
            timeout: 超时时间
            
        Returns:
            WebhookResult: 投递结果
        """
        try:
            req = urllib.request.Request(
                url,
                data=data.encode('utf-8'),
                headers=headers,
                method='POST'
            )
            
            with urllib.request.urlopen(req, timeout=timeout) as response:
                status_code = response.status
                response_body = response.read().decode('utf-8')
                
                logger.info(
                    "Webhook delivered successfully: url=%s, status=%d",
                    url,
                    status_code
                )
                
                return WebhookResult(
                    success=True,
                    status_code=status_code,
                    response=response_body
                )
                
        except urllib.error.HTTPError as e:
            error_msg = f"HTTP Error {e.code}: {e.reason}"
            logger.warning(
                "Webhook delivery failed: url=%s, error=%s",
                url,
                error_msg
            )
            return WebhookResult(
                success=False,
                status_code=e.code,
                error=error_msg
            )
            
        except urllib.error.URLError as e:
            error_msg = f"URL Error: {e.reason}"
            logger.warning(
                "Webhook delivery failed: url=%s, error=%s",
                url,
                error_msg
            )
            return WebhookResult(
                success=False,
                error=error_msg
            )
            
        except Exception as e:
            error_msg = str(e)
            logger.error(
                "Webhook delivery error: url=%s, error=%s",
                url,
                error_msg,
                exc_info=True
            )
            return WebhookResult(
                success=False,
                error=error_msg
            )
    
    def _generate_signature(self, payload: str, secret: str) -> str:
        """
        生成 HMAC-SHA256 签名
        
        Args:
            payload: 请求体
            secret: 密钥
            
        Returns:
            签名字符串
        """
        signature = hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return f"sha256={signature}"
    
    def _calculate_retry_delay(self, attempt: int) -> int:
        """
        计算重试延迟（指数退避）
        
        Args:
            attempt: 当前尝试次数
            
        Returns:
            延迟秒数
        """
        delay = self.INITIAL_RETRY_DELAY * (2 ** attempt)
        return min(delay, self.MAX_RETRY_DELAY)
    
    def verify_signature(
        self,
        payload: str,
        signature: str,
        secret: str
    ) -> bool:
        """
        验证签名
        
        Args:
            payload: 请求体
            signature: 签名
            secret: 密钥
            
        Returns:
            是否验证通过
        """
        if not signature or not secret:
            return False
        
        if not signature.startswith("sha256="):
            return False
        
        expected = self._generate_signature(payload, secret)
        return hmac.compare_digest(signature, expected)
    
    def queue_event(self, event: Dict[str, Any]):
        """
        将事件加入投递队列
        
        Args:
            event: 事件数据
        """
        with self._lock:
            self._pending_queue.append(event)
    
    def process_queue(self, subscription_getter: Callable):
        """
        处理投递队列
        
        Args:
            subscription_getter: 获取订阅的函数
        """
        with self._lock:
            events = self._pending_queue.copy()
            self._pending_queue.clear()
        
        for event in events:
            self._process_event(event, subscription_getter)
    
    def _process_event(
        self,
        event: Dict[str, Any],
        subscription_getter: Callable
    ):
        """
        处理单个事件
        
        Args:
            event: 事件数据
            subscription_getter: 获取订阅的函数
        """
        object_type = event.get('object_type')
        event_type = event.get('event_type')
        
        subscriptions = subscription_getter(
            object_type=object_type,
            channel='webhook'
        )
        
        for sub in subscriptions:
            if event_type not in sub.get('event_types', []):
                continue
            
            config = WebhookConfig(
                url=sub.get('webhook_url', ''),
                secret=sub.get('webhook_secret', ''),
                retry_count=3
            )
            
            if not config.url:
                continue
            
            payload = WebhookPayload(
                event_id=event.get('id'),
                object_type=object_type,
                object_id=event.get('object_id'),
                event_type=event_type,
                changed_fields=event.get('changed_fields', []),
                old_values=event.get('old_values', {}),
                new_values=event.get('new_values', {})
            )
            
            result = self.deliver_with_retry(config, payload)
            
            if self.ds:
                self._update_event_status(event, result)
    
    def _update_event_status(
        self,
        event: Dict[str, Any],
        result: WebhookResult
    ):
        """
        更新事件状态
        
        Args:
            event: 事件数据
            result: 投递结果
        """
        try:
            event_id = event.get('id')
            if not event_id:
                return
            
            status = 'delivered' if result.success else 'failed'
            delivered_at = datetime.now().isoformat() if result.success else None
            
            self.ds.update(
                'change_events',
                event_id,
                {
                    'status': status,
                    'delivered_at': delivered_at,
                    'retry_count': result.retry_count
                }
            )
        except Exception as e:
            logger.error("Failed to update event status: %s", e)


webhook_service = WebhookService()
