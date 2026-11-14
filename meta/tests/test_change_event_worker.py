# -*- coding: utf-8 -*-
"""消息中心 P1-d：异步派发 worker + 通道限速

覆盖 spec §11 P1-d 验收：
- A10 发布只写库：publish_event 后事件仍为 pending，由 worker 轮询派发
- A10 worker 按 id 升序处理 pending 事件；空闲退避到 idle_interval
- A10 自动重试：到期 failed 投递由 worker 周期推进
- A12 外部通道限速：webhook/im 同通道串行 + 每秒最多 5 条
"""

import os
import sys
import tempfile
import time
from datetime import datetime, timedelta

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from meta.core.sql_adapters import SQLiteAdapter
from meta.services.change_event_dispatcher import (
    ChannelRateLimiter,
    ChangeEventDispatcher,
)
from meta.services.change_event_worker import (
    ChangeEventWorker,
    is_worker_enabled,
    notify_pending,
)
from meta.services.change_notification_service import (
    ChangeEventRequest,
    ChangeNotificationService,
)

pytestmark = pytest.mark.integration

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


def _seed_event(ds, event_id=101, status='pending'):
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
        'status': status,
        'retry_count': 0,
        'created_at': '2026-11-14T10:00:00',
        'retention_until': '2027-11-14T10:00:00',
    })


def _get_event(ds, event_id=101):
    return ds.find_by_id('change_events', event_id)


def _inbox(ds, event_id=101):
    return ds.find('notification_inbox', filters={'event_id': event_id}) or []


def _seed_failed_delivery(ds, event_id=101, user_id=7, attempts=1,
                          channel='in_app', next_retry_at='2026-11-14T09:00:00'):
    subscription = ds.find('change_subscriptions', filters={'user_id': user_id}, limit=1)
    subscription_id = subscription[0]['id'] if subscription else 1
    return ds.insert('notification_deliveries', {
        'event_id': event_id,
        'subscription_id': subscription_id,
        'user_id': user_id,
        'channel': channel,
        'target': 'u:%s' % user_id if channel == 'in_app' else 'https://example.com/hook',
        'status': 'failed',
        'attempts': attempts,
        'last_error': 'boom',
        'next_retry_at': next_retry_at,
        'delivered_at': None,
        'created_at': '2026-11-14T10:00:00',
    })


class _RecordingDispatcher:
    """只记录派发顺序的假 dispatcher。"""

    def __init__(self):
        self.seen = []

    def normalize_event(self, row):
        return dict(row)

    def dispatch(self, event_id, event):
        self.seen.append(event_id)
        return {'matched': 0, 'delivered': 0, 'failed': 0, 'skipped': 0}

    def retry_due_deliveries(self, limit=50, now=None):
        return {'events': 0, 'attempted': 0, 'delivered': 0, 'failed': 0, 'skipped': 0}


class _FakeClock:
    """可注入的单调时钟：sleep 即推进时间。"""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += max(float(seconds), 0.0)


# ------------------------------------------------------------------ worker 开关

@pytest.mark.parametrize('value,expected', [
    ('1', True),
    ('on', True),
    ('off', False),
    ('0', False),
    ('false', False),
    ('disabled', False),
])
def test_is_worker_enabled(value, expected):
    assert is_worker_enabled(value) is expected


def test_is_worker_enabled_defaults_on_when_unset(monkeypatch):
    # 测试态由 env_flags 注入 off；生产默认未设置时启用
    monkeypatch.delenv('META_CHANGE_EVENT_WORKER', raising=False)
    assert is_worker_enabled() is True


def test_notify_pending_is_noop_without_worker():
    # 测试态不启动进程级 worker，发布侧唤醒必须是静默 no-op（fail-open）
    assert notify_pending(101) is False


# ------------------------------------------------------------------ 轮询派发

def test_process_pending_dispatches_in_id_order():
    ds, db_path = _make_ds()
    try:
        _seed_event(ds, 102)
        _seed_event(ds, 101)
        dispatcher = _RecordingDispatcher()
        worker = ChangeEventWorker(ds, dispatcher=dispatcher, batch_size=10)

        assert worker.process_pending() == 2
        assert dispatcher.seen == [101, 102]
    finally:
        _cleanup(ds, db_path)


def test_process_pending_marks_event_delivered_and_writes_inbox():
    ds, db_path = _make_ds(subscriptions=[_sub(user_id=7)])
    try:
        _seed_event(ds, 101)
        worker = ChangeEventWorker(ds, batch_size=10)

        assert worker.process_pending() == 1
        assert _get_event(ds)['status'] == 'delivered'
        assert len(_inbox(ds)) == 1
    finally:
        _cleanup(ds, db_path)


def test_next_interval_backs_off_when_idle():
    worker = ChangeEventWorker(None, poll_interval=2.0, idle_interval=10.0)
    assert worker.next_interval(1) == 2.0
    assert worker.next_interval(0) == 10.0


def test_worker_start_stop_lifecycle():
    ds, db_path = _make_ds()
    try:
        worker = ChangeEventWorker(
            ds, dispatcher=_RecordingDispatcher(), poll_interval=0.05, idle_interval=0.05
        )
        worker.start()
        try:
            for _ in range(50):
                if worker.is_running:
                    break
                time.sleep(0.01)
            assert worker.is_running is True
        finally:
            worker.stop()
        assert worker.is_running is False
    finally:
        _cleanup(ds, db_path)


# ------------------------------------------------------------------ 自动重试

def test_process_due_retries_delivers_due_failed():
    ds, db_path = _make_ds(subscriptions=[_sub(user_id=7)])
    try:
        _seed_event(ds, 101, status='delivered')
        _seed_failed_delivery(ds, channel='in_app', attempts=1)
        worker = ChangeEventWorker(ds, batch_size=10)

        now = datetime(2026, 11, 14, 10, 0, 0)
        stats = worker.process_due_retries(now=now)
        assert stats['delivered'] == 1

        delivery = ds.find('notification_deliveries', filters={'event_id': 101})[0]
        assert delivery['status'] == 'delivered'
        assert delivery['attempts'] == 2
        assert len(_inbox(ds)) == 1
    finally:
        _cleanup(ds, db_path)


def test_process_due_retries_skips_not_due():
    ds, db_path = _make_ds(subscriptions=[_sub(user_id=7)])
    try:
        _seed_event(ds, 101, status='delivered')
        _seed_failed_delivery(
            ds, next_retry_at=(datetime.now() + timedelta(hours=1)).isoformat()
        )
        worker = ChangeEventWorker(ds, batch_size=10)

        stats = worker.process_due_retries()
        assert stats['attempted'] == 0
    finally:
        _cleanup(ds, db_path)


# ------------------------------------------------------------------ 通道限速

def test_rate_limiter_caps_external_channels_and_serializes():
    clock = _FakeClock()
    limiter = ChannelRateLimiter(
        max_per_second=2, clock=clock, sleep=clock.sleep
    )

    assert limiter.acquire('webhook') == 0.0
    assert limiter.acquire('webhook') == 0.0
    waited = limiter.acquire('webhook')
    assert waited >= 1.0
    assert clock.now >= 1.0


def test_rate_limiter_does_not_limit_in_app():
    clock = _FakeClock()
    limiter = ChannelRateLimiter(max_per_second=1, clock=clock, sleep=clock.sleep)
    for _ in range(10):
        assert limiter.acquire('in_app') == 0.0
    assert clock.now == 0.0


# ------------------------------------------------------------------ 发布异步化

def test_publish_writes_db_only_and_worker_dispatches():
    ds, db_path = _make_ds(subscriptions=[_sub(user_id=7)])
    try:
        service = ChangeNotificationService(ds)
        result = service.publish_event(ChangeEventRequest(
            object_type='work_order',
            object_id=5,
            event_type='state_changed',
            old_data={'status': 'draft'},
            new_data={'status': 'released'},
            force=True,
        ))
        assert result.success is True
        event_id = result.event_id

        # 发布侧不内联派发：事件仍 pending，且无投递记录
        assert _get_event(ds, event_id)['status'] == 'pending'
        assert ds.find('notification_deliveries', filters={'event_id': event_id}) == []

        worker = ChangeEventWorker(ds, batch_size=10)
        assert worker.process_pending() >= 1
        assert _get_event(ds, event_id)['status'] == 'delivered'
        assert len(_inbox(ds, event_id)) == 1
    finally:
        _cleanup(ds, db_path)