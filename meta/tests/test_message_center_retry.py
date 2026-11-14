# -*- coding: utf-8 -*-
"""消息中心 P1-c：投递状态语义 + 幂等重试

覆盖 spec §11 P1-c 验收：
- A8  手动 retry：仅重置 failed/skipped；delivered 不动；attempts 单调；重复点击只产生一次新尝试
- A9  投递状态可解释：status_reason = no_subscriber / partial / all_failed / all_skipped
- 自动重试退避：1m / 5m / 15m / 1h，5 次后终态
- 发布幂等：change_events.idempotency_key 唯一
"""

import os
import sys
import tempfile
from datetime import datetime, timedelta

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from meta.core.sql_adapters import SQLiteAdapter
from meta.services.change_event_dispatcher import (
    ChangeEventDispatcher,
    MAX_DELIVERY_ATTEMPTS,
    STATUS_REASON_ALL_FAILED,
    STATUS_REASON_NO_SUBSCRIBER,
    STATUS_REASON_PARTIAL,
)
from meta.services.change_notification_service import (
    ChangeEventRequest,
    ChangeNotificationService,
)

pytestmark = pytest.mark.integration

NOTIF_URL = '/api/v1/notifications'

_MIGRATION_SQL = os.path.join(
    _PROJECT_ROOT, 'meta', 'migrations', 'add_notification_inbox_tables.sql'
)

_CHANGE_EVENTS_DDL = """
    CREATE TABLE IF NOT EXISTS change_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        object_type TEXT NOT NULL,
        object_id INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        changed_fields TEXT,
        old_values TEXT,
        new_values TEXT,
        payload TEXT,
        channels TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        status_reason TEXT,
        idempotency_key TEXT,
        retry_count INTEGER DEFAULT 0,
        created_at TEXT,
        delivered_at TEXT,
        audit_log_id INTEGER,
        retention_until TEXT
    )
"""

_CHANGE_SUBSCRIPTIONS_DDL = """
    CREATE TABLE IF NOT EXISTS change_subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        object_type TEXT NOT NULL,
        event_types TEXT,
        channel TEXT DEFAULT 'in_app',
        filter_condition TEXT,
        webhook_url TEXT,
        webhook_secret TEXT,
        enabled INTEGER DEFAULT 1,
        created_at TEXT
    )
"""


def _execute_sql_file(adapter, path):
    with open(path, encoding='utf-8') as f:
        content = f.read()
    for statement in content.split(';'):
        lines = [ln for ln in statement.splitlines() if not ln.strip().startswith('--')]
        sql = '\n'.join(lines).strip()
        if sql:
            adapter.execute(sql)


def _make_ds(subscriptions=None):
    db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db_file.close()
    adapter = SQLiteAdapter()
    adapter.connect(path=db_file.name)
    adapter.execute(_CHANGE_EVENTS_DDL)
    adapter.execute(_CHANGE_SUBSCRIPTIONS_DDL)
    _execute_sql_file(adapter, _MIGRATION_SQL)
    for sub in subscriptions or []:
        adapter.insert('change_subscriptions', sub)
    return adapter, db_file.name


def _cleanup(ds, db_path):
    try:
        ds.disconnect()
    except Exception:
        pass
    try:
        os.unlink(db_path)
    except OSError:
        pass


def _sub(user_id=7, channel='in_app', webhook_url=None):
    return {
        'user_id': user_id,
        'object_type': 'work_order',
        'event_types': '["state_changed"]',
        'channel': channel,
        'webhook_url': webhook_url,
        'webhook_secret': None,
        'filter_condition': '{}',
        'enabled': 1,
        'created_at': '2026-11-14T10:00:00',
    }


def _seed_event(ds, event_id=101):
    ds.insert('change_events', {
        'id': event_id,
        'object_type': 'work_order',
        'object_id': 5,
        'event_type': 'state_changed',
        'changed_fields': '["status"]',
        'old_values': '{"status": "draft"}',
        'new_values': '{"status": "released"}',
        'payload': '{"status": "released"}',
        'channels': '["in_app"]',
        'status': 'pending',
        'retry_count': 0,
        'created_at': '2026-11-14T10:00:00',
        'retention_until': '2027-11-14T10:00:00',
    })


def _event(event_id=101):
    return {
        'id': event_id,
        'object_type': 'work_order',
        'object_id': 5,
        'event_type': 'state_changed',
        'changed_fields': ['status'],
        'old_values': {'status': 'draft'},
        'new_values': {'status': 'released'},
        'payload': {'status': 'released'},
        'channels': ['in_app'],
        'created_at': '2026-11-14T10:00:00',
        'retention_until': '2027-11-14T10:00:00',
    }


def _get_event(ds, event_id=101):
    return ds.find_by_id('change_events', event_id)


def _get_deliveries(ds, event_id=101):
    return ds.find('notification_deliveries', filters={'event_id': event_id}) or []


def _seed_failed_delivery(ds, event_id=101, user_id=7, attempts=1, next_retry_at=None):
    subscription = ds.find('change_subscriptions', filters={'user_id': user_id}, limit=1)
    subscription_id = subscription[0]['id'] if subscription else 1
    return ds.insert('notification_deliveries', {
        'event_id': event_id,
        'subscription_id': subscription_id,
        'user_id': user_id,
        'channel': 'webhook',
        'target': 'https://example.com/hook',
        'status': 'failed',
        'attempts': attempts,
        'last_error': 'boom',
        'next_retry_at': next_retry_at,
        'delivered_at': None,
        'created_at': '2026-11-14T10:00:00',
    })


# ---------------------------------------------------------------- 状态语义

@pytest.mark.parametrize('_', [0])
def test_no_subscriber_marks_delivered_with_reason(_):
    ds, db_path = _make_ds(subscriptions=[])
    try:
        _seed_event(ds)
        result = ChangeEventDispatcher(ds).dispatch(101, _event())
        assert result['matched'] == 0
        event = _get_event(ds)
        assert event['status'] == 'delivered'
        assert event['status_reason'] == STATUS_REASON_NO_SUBSCRIBER
    finally:
        _cleanup(ds, db_path)


@pytest.mark.parametrize('_', [0])
def test_partial_delivery_marks_delivered_partial(_, monkeypatch):
    ds, db_path = _make_ds(subscriptions=[
        _sub(user_id=7, channel='in_app'),
        _sub(user_id=8, channel='webhook', webhook_url='https://example.com/hook'),
    ])
    try:
        _seed_event(ds)
        monkeypatch.setattr(
            ChangeEventDispatcher, '_deliver_webhook',
            lambda self, sub, event: 'failed',
        )
        result = ChangeEventDispatcher(ds).dispatch(101, _event())
        assert result['delivered'] == 1
        assert result['failed'] == 1

        event = _get_event(ds)
        assert event['status'] == 'delivered'
        assert event['status_reason'] == STATUS_REASON_PARTIAL

        failed = [d for d in _get_deliveries(ds) if d['channel'] == 'webhook'][0]
        assert failed['status'] == 'failed'
        assert failed['attempts'] == 1
        assert failed['next_retry_at']
    finally:
        _cleanup(ds, db_path)


@pytest.mark.parametrize('_', [0])
def test_all_failed_marks_failed_and_schedules_backoff(_, monkeypatch):
    ds, db_path = _make_ds(subscriptions=[
        _sub(user_id=8, channel='webhook', webhook_url='https://example.com/hook'),
    ])
    try:
        _seed_event(ds)
        monkeypatch.setattr(
            ChangeEventDispatcher, '_deliver_webhook',
            lambda self, sub, event: 'failed',
        )
        before = datetime.now()
        ChangeEventDispatcher(ds).dispatch(101, _event())

        event = _get_event(ds)
        assert event['status'] == 'failed'
        assert event['status_reason'] == STATUS_REASON_ALL_FAILED
        assert event['retry_count'] == 1

        delivery = _get_deliveries(ds)[0]
        assert delivery['status'] == 'failed'
        assert delivery['attempts'] == 1
        assert delivery['last_error']
        scheduled = datetime.fromisoformat(delivery['next_retry_at'])
        delta = (scheduled - before).total_seconds()
        assert 50 <= delta <= 70, f'首次重试应约 60 秒后，实际 {delta}'
    finally:
        _cleanup(ds, db_path)


def test_retry_backoff_schedule():
    assert ChangeEventDispatcher.retry_delay_seconds(1) == 60
    assert ChangeEventDispatcher.retry_delay_seconds(2) == 300
    assert ChangeEventDispatcher.retry_delay_seconds(3) == 900
    assert ChangeEventDispatcher.retry_delay_seconds(4) == 3600
    assert ChangeEventDispatcher.retry_delay_seconds(MAX_DELIVERY_ATTEMPTS) is None
    assert ChangeEventDispatcher.retry_delay_seconds(0) is None


# ---------------------------------------------------------------- 手动重试

@pytest.mark.parametrize('_', [0])
def test_manual_retry_only_resets_failed_part(_, monkeypatch):
    ds, db_path = _make_ds(subscriptions=[
        _sub(user_id=7, channel='in_app'),
        _sub(user_id=8, channel='webhook', webhook_url='https://example.com/hook'),
    ])
    try:
        _seed_event(ds)
        monkeypatch.setattr(
            ChangeEventDispatcher, '_deliver_webhook',
            lambda self, sub, event: 'failed',
        )
        dispatcher = ChangeEventDispatcher(ds)
        dispatcher.dispatch(101, _event())

        monkeypatch.setattr(
            ChangeEventDispatcher, '_deliver_webhook',
            lambda self, sub, event: 'delivered',
        )
        assert dispatcher.prepare_retry(101) == 1

        inbox_delivery = [d for d in _get_deliveries(ds) if d['channel'] == 'in_app'][0]
        webhook_delivery = [d for d in _get_deliveries(ds) if d['channel'] == 'webhook'][0]
        assert inbox_delivery['status'] == 'delivered'
        assert webhook_delivery['status'] == 'pending'

        stats = dispatcher.redeliver_pending(101, _get_event(ds), force=True)
        assert stats['attempted'] == 1
        assert stats['delivered'] == 1

        webhook_delivery = [d for d in _get_deliveries(ds) if d['channel'] == 'webhook'][0]
        assert webhook_delivery['status'] == 'delivered'
        assert webhook_delivery['attempts'] == 2
        event = _get_event(ds)
        assert event['status'] == 'delivered'
        assert event['status_reason'] is None
    finally:
        _cleanup(ds, db_path)


@pytest.mark.parametrize('_', [0])
def test_manual_retry_attempts_monotonic(_, monkeypatch):
    ds, db_path = _make_ds(subscriptions=[
        _sub(user_id=8, channel='webhook', webhook_url='https://example.com/hook'),
    ])
    try:
        _seed_event(ds)
        monkeypatch.setattr(
            ChangeEventDispatcher, '_deliver_webhook',
            lambda self, sub, event: 'failed',
        )
        dispatcher = ChangeEventDispatcher(ds)
        dispatcher.dispatch(101, _event())
        assert _get_deliveries(ds)[0]['attempts'] == 1

        for expected in (2, 3):
            dispatcher.prepare_retry(101)
            dispatcher.redeliver_pending(101, _get_event(ds), force=True)
            assert _get_deliveries(ds)[0]['attempts'] == expected
    finally:
        _cleanup(ds, db_path)


@pytest.mark.parametrize('_', [0])
def test_auto_retry_due_deliveries(_, monkeypatch):
    ds, db_path = _make_ds(subscriptions=[
        _sub(user_id=8, channel='webhook', webhook_url='https://example.com/hook'),
    ])
    try:
        _seed_event(ds)
        past = (datetime.now() - timedelta(minutes=1)).isoformat()
        delivery_id = _seed_failed_delivery(ds, attempts=1, next_retry_at=past)

        monkeypatch.setattr(
            ChangeEventDispatcher, '_deliver_webhook',
            lambda self, sub, event: 'delivered',
        )
        stats = ChangeEventDispatcher(ds).retry_due_deliveries()
        assert stats['events'] == 1
        assert stats['attempted'] == 1
        assert stats['delivered'] == 1

        delivery = ds.find_by_id('notification_deliveries', delivery_id)
        assert delivery['status'] == 'delivered'
        assert delivery['attempts'] == 2
    finally:
        _cleanup(ds, db_path)


# ---------------------------------------------------------------- HTTP 端点

def _headers_for(user_id, permissions=()):
    from meta.services.auth_provider import UserInfo
    from meta.services.token_service import TokenService

    user = UserInfo(
        user_id=str(user_id),
        username=f'user{user_id}',
        display_name=f'User {user_id}',
        email=f'user{user_id}@test.com',
        roles=[],
        permissions=list(permissions),
    )
    token, _ = TokenService.create_token(user)
    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
        'X-User-Id': str(user_id),
        'X-User-Name': f'user{user_id}',
    }


@pytest.fixture
def retry_api(monkeypatch):
    from meta.api import notification_api

    ds, db_path = _make_ds(subscriptions=[
        _sub(user_id=7, channel='webhook', webhook_url='https://example.com/hook'),
    ])
    _seed_event(ds)
    _seed_failed_delivery(ds, user_id=7, attempts=1, next_retry_at=None)
    monkeypatch.setattr(notification_api, 'ds', ds)
    monkeypatch.setattr(notification_api, '_retry_debounce', {})
    yield ds
    _cleanup(ds, db_path)


class TestRetryAPI:
    """POST /events/<id>/retry：归属校验 + 幂等 + 状态重置。"""

    def test_admin_retry_then_debounced(self, api_client, admin_headers, retry_api, monkeypatch):
        monkeypatch.setattr(
            ChangeEventDispatcher, '_deliver_webhook',
            lambda self, sub, event: 'delivered',
        )
        resp = api_client.post(f'{NOTIF_URL}/events/101/retry', json={}, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['reset'] == 1
        assert data['attempted'] == 1
        assert data['delivered'] == 1
        assert data['debounced'] is False

        delivery = _get_deliveries(retry_api)[0]
        assert delivery['status'] == 'delivered'
        assert delivery['attempts'] == 2

        again = api_client.post(f'{NOTIF_URL}/events/101/retry', json={}, headers=admin_headers)
        assert again.status_code == 200
        second = again.get_json()['data']
        assert second['debounced'] is True
        assert second['attempted'] == 0
        assert _get_deliveries(retry_api)[0]['attempts'] == 2

    def test_non_owner_forbidden(self, api_client, retry_api):
        resp = api_client.post(
            f'{NOTIF_URL}/events/101/retry', json={}, headers=_headers_for(8)
        )
        assert resp.status_code == 403

    def test_retry_all_permission_allowed(self, api_client, retry_api, monkeypatch):
        monkeypatch.setattr(
            ChangeEventDispatcher, '_deliver_webhook',
            lambda self, sub, event: 'delivered',
        )
        resp = api_client.post(
            f'{NOTIF_URL}/events/101/retry', json={},
            headers=_headers_for(9, permissions=['notification:retry:all']),
        )
        assert resp.status_code == 200
        assert resp.get_json()['data']['attempted'] == 1

    def test_missing_event_404(self, api_client, admin_headers, retry_api):
        resp = api_client.post(f'{NOTIF_URL}/events/999999/retry', json={}, headers=admin_headers)
        assert resp.status_code == 404


# ---------------------------------------------------------------- 发布幂等

@pytest.mark.parametrize('_', [0])
def test_publish_idempotency_key_dedupes_events(_):
    ds, db_path = _make_ds(subscriptions=[])
    try:
        service = ChangeNotificationService(ds)
        request = ChangeEventRequest(
            object_type='work_order',
            object_id=5,
            event_type='state_changed',
            force=True,
            new_data={'status': 'released'},
            idempotency_key='evt-unique-1',
        )
        first = service.publish_event(request)
        second = service.publish_event(request)

        assert first.success is True
        assert second.success is True
        assert first.event_id == second.event_id == 1
        assert len(ds.find('change_events')) == 1
    finally:
        _cleanup(ds, db_path)