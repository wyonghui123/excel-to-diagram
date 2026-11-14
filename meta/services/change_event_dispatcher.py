# -*- coding: utf-8 -*-
"""变更事件订阅派发器。

职责边界：
    ChangeNotificationService  ── 发布事实（写 change_events + 广播 + 聚合刷新）
    ChangeEventDispatcher      ── 按 change_subscriptions 派发 + 推进事件状态

通道（本期）：
    in_app  → WebSocket 定向推送到订阅用户（离线视为已投递，P1 再补收件箱表）
    webhook → WebhookService.deliver（复用既有 HMAC 签名与超时设置）
    webhook 且 URL 为飞书群机器人 → 转飞书消息体 {msg_type, content} 后直投
    webhook 且 URL 为 feishu://chat/<chat_id> → 走应用 IM（tenant_access_token）
    email / sms → 本期跳过（无模板与网关），仅 debug 日志

设计约束（见 spec-message-platform-change-event-2026-11-14.md）：
    - fail-open：任何异常不得影响业务写入
    - 幂等：一次发布内每个订阅最多投递一次
    - 事件词表统一走 change_event_types.normalize
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

from meta.core.change_event_types import EVENT_TYPE_LABELS, normalize

logger = logging.getLogger(__name__)

SUBSCRIPTIONS_TABLE = 'change_subscriptions'
EVENTS_TABLE = 'change_events'
DELIVERIES_TABLE = 'notification_deliveries'

STATUS_PENDING = 'pending'
STATUS_SENDING = 'sending'
STATUS_DELIVERED = 'delivered'
STATUS_FAILED = 'failed'
STATUS_SKIPPED = 'skipped'

#: 事件级 status_reason（投递集合聚合推导，不新增 status 枚举）
STATUS_REASON_NO_SUBSCRIBER = 'no_subscriber'
STATUS_REASON_PARTIAL = 'partial'
STATUS_REASON_ALL_FAILED = 'all_failed'
STATUS_REASON_ALL_SKIPPED = 'all_skipped'

#: 自动重试退避：1m / 5m / 15m / 1h / 6h
RETRY_BACKOFF_SECONDS = (60, 300, 900, 3600, 21600)
#: 自动重试上限；到达后终态 failed
MAX_DELIVERY_ATTEMPTS = 5
#: last_error 截断长度（脱敏由调用方保证）
LAST_ERROR_LIMIT = 500

#: notification_deliveries.channel CHECK 允许值
DELIVERY_CHANNELS = ('in_app', 'webhook', 'im', 'email', 'sms')
_CHANNEL_ALIASES = {'mail': 'email', 'websocket': 'in_app'}

#: P1-d 通道限速：外部通道同通道串行 + 每秒最多 N 条；in_app 不限速
RATE_LIMIT_CHANNELS = ('webhook', 'im')
RATE_LIMIT_MAX_PER_SECOND = 5
RATE_LIMIT_WINDOW_SECONDS = 1.0


class ChannelRateLimiter:
    """外部通道限速器（同通道串行 + 滑动窗口 1s 内最多 N 条）。

    说明：
        - 仅对 webhook / im 生效；in_app 走本地收件箱与 WebSocket，不限速。
        - 同一通道的等待在通道锁内完成，因此天然串行，避免 webhook 风暴。
        - clock / sleep 可注入，便于测试不真正 sleep。
    """

    def __init__(
        self,
        max_per_second: int = RATE_LIMIT_MAX_PER_SECOND,
        channels: Iterable[str] = RATE_LIMIT_CHANNELS,
        clock=time.monotonic,
        sleep=time.sleep,
    ):
        self._max = max(int(max_per_second), 1)
        self._clock = clock
        self._sleep = sleep
        self._states: Dict[str, Any] = {
            channel: (threading.Lock(), deque()) for channel in channels
        }

    def acquire(self, channel: str) -> float:
        """阻塞直到该通道获得一个发送配额；返回累计等待秒数。"""
        state = self._states.get(channel)
        if state is None:
            return 0.0
        lock, stamps = state
        waited = 0.0
        with lock:
            while True:
                now = self._clock()
                while stamps and now - stamps[0] >= RATE_LIMIT_WINDOW_SECONDS:
                    stamps.popleft()
                if len(stamps) < self._max:
                    stamps.append(now)
                    return waited
                delay = RATE_LIMIT_WINDOW_SECONDS - (now - stamps[0])
                if delay <= 0:
                    delay = RATE_LIMIT_WINDOW_SECONDS
                self._sleep(delay)
                waited += delay


_DEFAULT_RATE_LIMITER = ChannelRateLimiter()


def get_default_rate_limiter() -> ChannelRateLimiter:
    """进程级默认限速器（worker / API 手动重试共享同一配额）。"""
    return _DEFAULT_RATE_LIMITER

# 飞书（Lark）自定义群机器人 Webhook 前缀；命中后按飞书消息体投递
FEISHU_BOT_MARKERS = (
    'open.feishu.cn/open-apis/bot/v2/hook/',
    'open.larksuite.com/open-apis/bot/v2/hook/',
)
FEISHU_BOT_TIMEOUT = 10


def is_feishu_bot_url(url: str) -> bool:
    """判断是否为飞书自定义群机器人 Webhook。"""
    text = (url or '').strip().lower()
    return any(marker in text for marker in FEISHU_BOT_MARKERS)


def feishu_bot_sign(timestamp: str, secret: str) -> str:
    """飞书群机器人签名：base64(HmacSHA256(key=timestamp\\nsecret, msg=''))。"""
    string_to_sign = f'{timestamp}\n{secret}'
    digest = hmac.new(
        string_to_sign.encode('utf-8'), b'', digestmod=hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode('utf-8')


def parse_feishu_im_target(url: str) -> Optional[str]:
    """解析应用 IM 目标：feishu://chat/<chat_id> 或 feishu://default。

    Returns:
        chat_id 字符串（'' 表示用环境变量里的默认群）；None 表示不是 IM scheme。
    """
    text = (url or '').strip()
    lowered = text.lower()
    for prefix in ('feishu://chat/', 'lark://chat/'):
        if lowered.startswith(prefix):
            return text[len(prefix):].strip()
    if lowered in ('feishu://default', 'lark://default'):
        return ''
    return None


class ChangeEventDispatcher:
    """把已落库的变更事件派发给匹配订阅。"""

    def __init__(
        self,
        data_source,
        rate_limiter: Optional[ChannelRateLimiter] = None,
    ):
        self.ds = data_source
        self.rate_limiter = rate_limiter or get_default_rate_limiter()
        self._last_error = ''

    # ---------------------------------------------------------------- public
    def dispatch(self, event_id: int, event: Dict[str, Any]) -> Dict[str, int]:
        """派发单个事件，并按投递集合聚合推进 change_events.status。

        Returns:
            {'matched': n, 'delivered': n, 'failed': n, 'skipped': n}
        """
        stats = {'matched': 0, 'delivered': 0, 'failed': 0, 'skipped': 0}
        try:
            subscriptions = self._match(event)
        except Exception as e:
            logger.warning("[change_event] match subscriptions failed: %s", e)
            return stats

        stats['matched'] = len(subscriptions)

        for sub in subscriptions:
            channel = self._channel(sub)
            existing = self._find_delivery(event_id, sub, channel)
            if existing is not None and existing.get('status') != STATUS_PENDING:
                # 已终态（含重复派发）：按原状态计入，不再新增尝试
                status = existing.get('status')
                if status == STATUS_DELIVERED:
                    stats['delivered'] += 1
                elif status == STATUS_FAILED:
                    stats['failed'] += 1
                else:
                    stats['skipped'] += 1
                continue

            if existing is None:
                delivery_id = self._create_delivery(sub, event, channel)
                attempts = 0
            else:
                delivery_id = existing.get('id')
                attempts = int(existing.get('attempts') or 0)

            outcome = self._run_attempt(delivery_id, attempts, sub, event)
            stats['delivered' if outcome == 'delivered'
                  else 'failed' if outcome == 'failed' else 'skipped'] += 1

        self._refresh_event_status(event_id)

        logger.info(
            "[change_event] dispatched: event_id=%s object_type=%s event_type=%s stats=%s",
            event_id, event.get('object_type'), event.get('event_type'), stats,
        )
        return stats

    # ------------------------------------------------------------ retry entry
    def prepare_retry(self, event_id: int, now: Optional[datetime] = None) -> int:
        """手动重试：把 failed/skipped 投递重置为 pending（delivered 不动）。

        Returns:
            被重置的投递条数（0 表示无需重试）。
        """
        if not event_id or self.ds is None:
            return 0
        current = (now or datetime.now()).isoformat()
        try:
            rows = self.ds.find(DELIVERIES_TABLE, filters={'event_id': event_id}) or []
        except Exception as e:
            logger.warning("[change_event] prepare_retry 查询失败: event=%s err=%s", event_id, e)
            return 0

        count = 0
        for row in rows:
            if row.get('status') not in (STATUS_FAILED, STATUS_SKIPPED):
                continue
            if self._update_delivery(row.get('id'), {
                'status': STATUS_PENDING,
                'next_retry_at': current,
            }):
                count += 1
        if count:
            self._refresh_event_status(event_id)
        return count

    def redeliver_pending(
        self, event_id: int, event: Dict[str, Any], force: bool = True
    ) -> Dict[str, int]:
        """重投该事件下 status=pending 的投递。

        Args:
            force: True（手动重试）允许超过自动重试上限；False（自动重试）遵守 attempts<5。
        """
        stats = {'attempted': 0, 'delivered': 0, 'failed': 0, 'skipped': 0}
        if not event_id or self.ds is None:
            return stats
        try:
            rows = self.ds.find(DELIVERIES_TABLE, filters={
                'event_id': event_id,
                'status': STATUS_PENDING,
            }) or []
        except Exception as e:
            logger.warning("[change_event] redeliver 查询失败: event=%s err=%s", event_id, e)
            return stats

        normalized = self.normalize_event(event)
        for row in rows:
            attempts = int(row.get('attempts') or 0)
            if not force and attempts >= MAX_DELIVERY_ATTEMPTS:
                continue
            sub = None
            if row.get('subscription_id') is not None:
                try:
                    sub = self.ds.find_by_id(SUBSCRIPTIONS_TABLE, int(row['subscription_id']))
                except Exception as e:
                    logger.warning(
                        "[change_event] 读取订阅失败: subscription=%s err=%s",
                        row.get('subscription_id'), e,
                    )
            if not sub:
                self._update_delivery(row.get('id'), {
                    'status': STATUS_SKIPPED,
                    'last_error': '订阅已删除',
                    'next_retry_at': None,
                })
                stats['skipped'] += 1
                continue

            outcome = self._run_attempt(row.get('id'), attempts, sub, normalized)
            stats['attempted'] += 1
            stats['delivered' if outcome == 'delivered'
                  else 'failed' if outcome == 'failed' else 'skipped'] += 1

        self._refresh_event_status(event_id)
        return stats

    def retry_due_deliveries(
        self, limit: int = 50, now: Optional[datetime] = None
    ) -> Dict[str, int]:
        """自动重试到期投递（供 P1-d worker 周期调用）。

        仅处理 failed 且 attempts<5、next_retry_at 已到期的投递；退避 1m/5m/15m/1h。
        """
        stats = {'events': 0, 'attempted': 0, 'delivered': 0, 'failed': 0, 'skipped': 0}
        if self.ds is None:
            return stats
        current_dt = now or datetime.now()
        current = current_dt.isoformat()
        try:
            rows = self.ds.find(
                DELIVERIES_TABLE,
                filters={'status': STATUS_FAILED},
                order_by='next_retry_at ASC',
                limit=max(limit * 4, limit),
            ) or []
        except Exception as e:
            logger.warning("[change_event] retry_due 查询失败: %s", e)
            return stats

        selected: List[Dict[str, Any]] = []
        for row in rows:
            if int(row.get('attempts') or 0) >= MAX_DELIVERY_ATTEMPTS:
                continue
            due = self._parse_time(row.get('next_retry_at'))
            if due is None or due > current_dt:
                continue
            selected.append(row)
            if len(selected) >= limit:
                break

        by_event: Dict[int, List[Dict[str, Any]]] = {}
        for row in selected:
            event_id = int(row.get('event_id') or 0)
            if not event_id:
                continue
            if not self._update_delivery(row.get('id'), {
                'status': STATUS_PENDING,
                'next_retry_at': current,
            }):
                continue
            by_event.setdefault(event_id, []).append(row)

        for event_id in by_event:
            event = None
            try:
                event = self.ds.find_by_id(EVENTS_TABLE, event_id)
            except Exception as e:
                logger.warning("[change_event] retry_due 读取事件失败: %s err=%s", event_id, e)
            if not event:
                continue
            result = self.redeliver_pending(event_id, event, force=False)
            stats['events'] += 1
            for key in ('attempted', 'delivered', 'failed', 'skipped'):
                stats[key] += result.get(key, 0)

        return stats

    # --------------------------------------------------------------- matching
    def _match(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        object_type = event.get('object_type')
        event_type = normalize(event.get('event_type'))
        if not object_type or not event_type:
            return []

        rows = self.ds.find(SUBSCRIPTIONS_TABLE, filters={'object_type': object_type}) or []
        matched: List[Dict[str, Any]] = []
        for row in rows:
            if not self._truthy(row.get('enabled')):
                continue
            if event_type not in self._event_types(row.get('event_types')):
                continue
            if not self._filter_ok(row.get('filter_condition'), event):
                continue
            matched.append(row)
        return matched

    @staticmethod
    def _truthy(value: Any) -> bool:
        if isinstance(value, str):
            return value.strip().lower() in ('1', 'true', 'yes', 'on')
        return bool(value)

    @staticmethod
    def _event_types(raw: Any) -> List[str]:
        if raw is None or raw == '':
            return []
        if isinstance(raw, (list, tuple)):
            items: Iterable[Any] = raw
        elif isinstance(raw, str):
            text = raw.strip()
            try:
                parsed = json.loads(text)
                items = parsed if isinstance(parsed, list) else [parsed]
            except Exception:
                items = [p for p in text.split(',')]
        else:
            items = [raw]
        return [t for t in (normalize(i) for i in items) if t]

    @staticmethod
    def _filter_ok(raw: Any, event: Dict[str, Any]) -> bool:
        """过滤条件（本期仅等值匹配）。

        条件形如 {"stage": "won"}；与事件合并后的行数据比较，缺失字段不判失败。
        """
        if not raw:
            return True
        cond = raw
        if isinstance(raw, str):
            text = raw.strip()
            if not text:
                return True
            try:
                cond = json.loads(text)
            except Exception:
                logger.debug("[change_event] filter_condition 非 JSON，按无过滤处理: %r", raw)
                return True
        if not isinstance(cond, dict):
            return True

        row: Dict[str, Any] = {}
        for key in ('old_values', 'new_values'):
            value = event.get(key)
            if isinstance(value, dict):
                row.update(value)
        payload = event.get('payload')
        if isinstance(payload, dict):
            for k, v in payload.items():
                row.setdefault(k, v)

        for field, expected in cond.items():
            if field in row and row[field] != expected:
                return False
        return True

    # --------------------------------------------------------------- delivery
    @staticmethod
    def _channel(sub: Dict[str, Any]) -> str:
        """订阅 channel 归一为 notification_deliveries 允许值。"""
        raw = str(sub.get('channel') or 'in_app').strip().lower()
        if 'webhook' in raw:
            return 'webhook'
        channel = _CHANNEL_ALIASES.get(raw, raw)
        return channel if channel in DELIVERY_CHANNELS else 'in_app'

    def _find_delivery(
        self, event_id: int, sub: Dict[str, Any], channel: str
    ) -> Optional[Dict[str, Any]]:
        """按 UNIQUE(event_id, subscription_id, channel) 取已有投递记录。"""
        if self.ds is None:
            return None
        subscription_id = sub.get('id')
        if not event_id or subscription_id is None:
            return None
        try:
            rows = self.ds.find(DELIVERIES_TABLE, filters={
                'event_id': event_id,
                'subscription_id': subscription_id,
                'channel': channel,
            }, limit=1)
        except Exception as e:
            logger.warning(
                "[change_event] 投递记录查询失败: event_id=%s subscription=%s err=%s",
                event_id, subscription_id, e,
            )
            return None
        return rows[0] if rows else None

    def _create_delivery(
        self, sub: Dict[str, Any], event: Dict[str, Any], channel: str
    ) -> Optional[int]:
        """新建 pending 投递记录，失败返回 None（fail-open）。"""
        if self.ds is None:
            return None
        event_id = int(event.get('id') or 0)
        subscription_id = sub.get('id')
        if not event_id or subscription_id is None:
            return None
        try:
            return self.ds.insert(DELIVERIES_TABLE, {
                'event_id': event_id,
                'subscription_id': int(subscription_id),
                'user_id': sub.get('user_id'),
                'channel': channel,
                'target': (sub.get('webhook_url') or None),
                'status': STATUS_PENDING,
                'attempts': 0,
                'last_error': None,
                'next_retry_at': None,
                'delivered_at': None,
                'created_at': datetime.now().isoformat(),
            })
        except Exception as e:
            logger.warning(
                "[change_event] 投递记录写入失败: event_id=%s subscription=%s err=%s",
                event_id, subscription_id, e,
            )
            return None

    def _run_attempt(
        self,
        delivery_id: Optional[int],
        attempts: int,
        sub: Dict[str, Any],
        event: Dict[str, Any],
    ) -> str:
        """执行一次投递尝试：attempts+1 → sending → deliver → close。"""
        attempt_no = int(attempts or 0) + 1
        if delivery_id is not None:
            self._update_delivery(delivery_id, {
                'status': STATUS_SENDING,
                'attempts': attempt_no,
            })
        self._last_error = ''
        outcome = self._deliver(sub, event, delivery_id)
        self._close_delivery(delivery_id, outcome, attempt_no)
        return outcome

    def _close_delivery(
        self, delivery_id: Optional[int], outcome: str, attempts: int = 1
    ) -> None:
        """回填投递状态；failed 按 attempts 计算下次重试时间。fail-open。"""
        if delivery_id is None or self.ds is None:
            return
        status = {
            'delivered': STATUS_DELIVERED,
            'failed': STATUS_FAILED,
        }.get(outcome, STATUS_SKIPPED)
        data: Dict[str, Any] = {'status': status}
        now = datetime.now()
        if status == STATUS_DELIVERED:
            data['delivered_at'] = now.isoformat()
            data['next_retry_at'] = None
            data['last_error'] = None
        elif status == STATUS_FAILED:
            delay = self.retry_delay_seconds(attempts)
            data['next_retry_at'] = (
                (now + timedelta(seconds=delay)).isoformat() if delay else None
            )
            data['last_error'] = (self._last_error or '投递失败')[:LAST_ERROR_LIMIT]
        else:
            data['next_retry_at'] = None
            data['last_error'] = (self._last_error or '通道未启用或缺少投递目标')[:LAST_ERROR_LIMIT]
        self._update_delivery(delivery_id, data)

    def _update_delivery(self, delivery_id: Optional[int], data: Dict[str, Any]) -> bool:
        if delivery_id is None or self.ds is None:
            return False
        try:
            self.ds.update(DELIVERIES_TABLE, delivery_id, data)
            return True
        except Exception as e:
            logger.warning(
                "[change_event] 投递状态回填失败: delivery=%s err=%s", delivery_id, e
            )
            return False

    @staticmethod
    def retry_delay_seconds(attempts: int) -> Optional[int]:
        """第 attempts 次失败后的退避秒数；None 表示不自动重试。"""
        if attempts < 1 or attempts >= MAX_DELIVERY_ATTEMPTS:
            return None
        return RETRY_BACKOFF_SECONDS[attempts - 1]

    @staticmethod
    def _parse_time(value: Any) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value).replace('Z', '+00:00')).replace(tzinfo=None)
        except Exception:
            return None

    @staticmethod
    def normalize_event(event: Dict[str, Any]) -> Dict[str, Any]:
        """把 DB 行里的 JSON 字符串字段还原为对象，供重投使用。"""
        if not event:
            return event
        normalized = dict(event)
        for key in ('changed_fields', 'old_values', 'new_values', 'payload', 'channels'):
            value = normalized.get(key)
            if isinstance(value, str):
                try:
                    normalized[key] = json.loads(value)
                except Exception:
                    pass
        return normalized

    def _deliver(
        self,
        sub: Dict[str, Any],
        event: Dict[str, Any],
        delivery_id: Optional[int] = None,
    ) -> str:
        channel = self._channel(sub)
        try:
            if channel == 'webhook':
                outcome = self._deliver_webhook(sub, event)
            elif channel in ('email', 'sms', 'im'):
                logger.debug(
                    "[change_event] channel=%s 本期未启用，跳过订阅 %s", channel, sub.get('id')
                )
                outcome = 'skipped'
            else:
                outcome = self._deliver_in_app(sub, event, delivery_id)
        except Exception as e:
            logger.warning(
                "[change_event] deliver failed: subscription=%s channel=%s err=%s",
                sub.get('id'), channel, e,
            )
            self._last_error = str(e)
            return 'failed'

        if outcome == 'failed' and not self._last_error:
            self._last_error = f'channel={channel} 投递失败'
        if outcome == 'skipped' and not self._last_error:
            self._last_error = f'channel={channel} 未启用或缺少投递目标'
        return outcome

    def _deliver_in_app(
        self,
        sub: Dict[str, Any],
        event: Dict[str, Any],
        delivery_id: Optional[int] = None,
    ) -> str:
        user_id = sub.get('user_id')
        if user_id is None:
            return 'skipped'

        # P1-b：先落收件箱（离线补偿），再推送在线连接
        inbox_id = None
        unread_count = 0
        if self.ds is not None and delivery_id is not None:
            try:
                from meta.services.notification_inbox_service import (
                    NotificationInboxService,
                )
                inbox = NotificationInboxService(self.ds)
                inbox_id = inbox.create_for_event(user_id, delivery_id, event)
                unread_count = inbox.unread_count(user_id)
            except Exception as e:
                logger.warning(
                    "[change_event] inbox 落库失败: event_id=%s user=%s err=%s",
                    event.get('id'), user_id, e,
                )

        from meta.services.websocket_manager import websocket_manager
        sent = websocket_manager.emit_to_user(user_id, 'change_event', {
            'inbox_id': inbox_id,
            'unread_count': unread_count,
            'object_type': event.get('object_type'),
            'object_id': event.get('object_id'),
            'event_type': event.get('event_type'),
            'changed_fields': event.get('changed_fields') or [],
            'old_values': event.get('old_values') or {},
            'new_values': event.get('new_values') or {},
            'payload': event.get('payload') or {},
            'subscription_id': sub.get('id'),
            'timestamp': event.get('created_at') or datetime.now().isoformat(),
        })
        logger.debug("[change_event] in_app user=%s sent_sids=%s", user_id, sent)
        return 'delivered'

    def _deliver_webhook(self, sub: Dict[str, Any], event: Dict[str, Any]) -> str:
        url = (sub.get('webhook_url') or '').strip()
        if not url:
            logger.debug("[change_event] subscription=%s 缺 webhook_url，跳过", sub.get('id'))
            return 'skipped'
        # P1-d 限速：外部通道（含飞书群机器人 / 应用 IM）同通道串行 + 每秒上限
        self.rate_limiter.acquire('webhook')
        im_chat_id = parse_feishu_im_target(url)
        if im_chat_id is not None:
            return self._deliver_feishu_im(sub, event, im_chat_id)
        if is_feishu_bot_url(url):
            return self._deliver_feishu_bot(sub, event, url)
        from meta.services.webhook_service import (
            WebhookConfig, WebhookPayload, WebhookService,
        )
        payload = WebhookPayload(
            event_id=int(event.get('id') or 0),
            object_type=event.get('object_type') or '',
            object_id=event.get('object_id'),
            event_type=event.get('event_type') or '',
            changed_fields=event.get('changed_fields') or [],
            old_values=event.get('old_values') or {},
            new_values=event.get('new_values') or {},
            timestamp=event.get('created_at') or '',
        )
        config = WebhookConfig(url=url, secret=sub.get('webhook_secret') or '')
        # 单次投递，不在此处叠加指数退避重试（重试由 POST /events/<id>/retry 触发）
        result = WebhookService(self.ds).deliver(config, payload)
        return 'delivered' if result.success else 'failed'

    def _deliver_feishu_im(
        self, sub: Dict[str, Any], event: Dict[str, Any], chat_id: str
    ) -> str:
        """走飞书应用 IM 发送到群（需 FEISHU_* / LARK_* 应用凭证）。"""
        from meta.services.integration_credential_service import (
            IntegrationConfigError,
            IntegrationUpstreamError,
            integration_credential_service,
        )

        target = chat_id or integration_credential_service.default_feishu_chat_id()
        if not target:
            logger.warning(
                "[change_event] feishu IM 缺 chat_id（订阅未指定且环境变量未配置）: "
                "subscription=%s", sub.get('id')
            )
            return 'skipped'

        body = {
            'receive_id': target,
            'msg_type': 'text',
            'content': json.dumps(
                {'text': self._feishu_text(event)}, ensure_ascii=False
            ),
        }
        try:
            payload = integration_credential_service.feishu_request(
                'POST',
                '/im/v1/messages',
                query={'receive_id_type': 'chat_id'},
                body=body,
            )
        except IntegrationConfigError as e:
            logger.warning("[change_event] feishu IM 未配置凭证: %s", e)
            return 'failed'
        except IntegrationUpstreamError as e:
            logger.warning("[change_event] feishu IM 上游失败: %s", e)
            return 'failed'

        if payload.get('code') != 0:
            logger.warning(
                "[change_event] feishu IM 拒绝投递: subscription=%s code=%s msg=%s",
                sub.get('id'), payload.get('code'), payload.get('msg'),
            )
            return 'failed'
        return 'delivered'

    def _deliver_feishu_bot(
        self, sub: Dict[str, Any], event: Dict[str, Any], url: str
    ) -> str:
        """投递到飞书自定义群机器人（无需应用凭证，仅需 webhook 地址）。"""
        body: Dict[str, Any] = {
            'msg_type': 'text',
            'content': {'text': self._feishu_text(event)},
        }
        secret = (sub.get('webhook_secret') or '').strip()
        if secret:
            timestamp = str(int(time.time()))
            body['timestamp'] = timestamp
            body['sign'] = feishu_bot_sign(timestamp, secret)

        request = urllib.request.Request(
            url,
            data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            with urllib.request.urlopen(request, timeout=FEISHU_BOT_TIMEOUT) as response:
                raw = response.read().decode('utf-8') or '{}'
        except urllib.error.HTTPError as e:
            logger.warning(
                "[change_event] feishu bot HTTP %s: subscription=%s err=%s",
                e.code, sub.get('id'), e.reason,
            )
            return 'failed'
        except Exception as e:
            logger.warning(
                "[change_event] feishu bot deliver failed: subscription=%s err=%s",
                sub.get('id'), e,
            )
            return 'failed'

        try:
            payload = json.loads(raw)
        except ValueError:
            logger.warning("[change_event] feishu bot 返回非 JSON: %r", raw[:200])
            return 'failed'

        # 新格式 {"code":0,"msg":"success"}；旧格式 {"StatusCode":0}
        code = payload.get('code', payload.get('StatusCode'))
        if code not in (0, None):
            logger.warning(
                "[change_event] feishu bot 拒绝投递: subscription=%s code=%s msg=%s",
                sub.get('id'), code, payload.get('msg') or payload.get('StatusMessage'),
            )
            return 'failed'
        return 'delivered'

    @staticmethod
    def _feishu_text(event: Dict[str, Any]) -> str:
        event_type = normalize(event.get('event_type'))
        label = EVENT_TYPE_LABELS.get(event_type, event_type or '变更')
        object_type = event.get('object_type') or '-'
        object_id = event.get('object_id')
        lines = [f'[变更事件] {object_type} {object_id} 已{label}']
        changed = event.get('changed_fields') or []
        if isinstance(changed, str):
            changed = [changed]
        if changed:
            lines.append('变更字段: ' + ', '.join(str(f) for f in changed))
        timestamp = event.get('created_at') or datetime.now().isoformat()
        lines.append(f'时间: {timestamp}')
        return '\n'.join(lines)

    # ----------------------------------------------------------------- status
    def _refresh_event_status(self, event_id: int) -> None:
        """按投递集合聚合事件状态（spec §8）：
        pending → delivered(全部成功) / delivered+partial / failed+all_failed /
        delivered+all_skipped / pending。
        """
        if not event_id or self.ds is None:
            return
        try:
            rows = self.ds.find(DELIVERIES_TABLE, filters={'event_id': event_id}) or []
        except Exception as e:
            logger.warning(
                "[change_event] 状态聚合查询失败: event_id=%s err=%s", event_id, e
            )
            # 兼容未建投递表的旧库：无投递记录可聚合，按无接收方完成
            if 'no such table' in str(e).lower():
                self._mark(event_id, STATUS_DELIVERED, STATUS_REASON_NO_SUBSCRIBER)
            return

        statuses = [row.get('status') for row in rows]
        if not statuses:
            self._mark(event_id, STATUS_DELIVERED, STATUS_REASON_NO_SUBSCRIBER)
        elif any(s in (STATUS_PENDING, STATUS_SENDING) for s in statuses):
            self._mark(event_id, STATUS_PENDING, None)
        elif all(s == STATUS_DELIVERED for s in statuses):
            self._mark(event_id, STATUS_DELIVERED, None)
        elif all(s == STATUS_SKIPPED for s in statuses):
            self._mark(event_id, STATUS_DELIVERED, STATUS_REASON_ALL_SKIPPED)
        elif all(s == STATUS_FAILED for s in statuses):
            self._mark(event_id, STATUS_FAILED, STATUS_REASON_ALL_FAILED)
        elif any(s == STATUS_DELIVERED for s in statuses):
            self._mark(event_id, STATUS_DELIVERED, STATUS_REASON_PARTIAL)
        else:
            # failed + skipped 混合且无成功：按失败处理，等待重试
            self._mark(event_id, STATUS_FAILED, STATUS_REASON_ALL_FAILED)

    def _mark(self, event_id: int, status: str, reason: Optional[str] = None) -> None:
        if not event_id or self.ds is None:
            return
        update: Dict[str, Any] = {'status': status, 'status_reason': reason}
        if status == STATUS_DELIVERED:
            update['delivered_at'] = datetime.now().isoformat()
        elif status == STATUS_FAILED:
            current = self.ds.find_by_id(EVENTS_TABLE, event_id) or {}
            update['retry_count'] = int(current.get('retry_count') or 0) + 1
        try:
            self.ds.update(EVENTS_TABLE, event_id, update)
        except Exception as e:
            # 兼容未执行 add_change_event_retry_columns.sql 的旧表：缺少 status_reason 时
            # 退化为只更新 status（delivered_at / retry_count 仍保留）。
            if 'status_reason' in str(e).lower():
                update.pop('status_reason', None)
                try:
                    self.ds.update(EVENTS_TABLE, event_id, update)
                    return
                except Exception as retry_err:
                    e = retry_err
            logger.warning("[change_event] mark status failed: event_id=%s err=%s", event_id, e)