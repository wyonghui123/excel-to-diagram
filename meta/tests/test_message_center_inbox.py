# -*- coding: utf-8 -*-
"""消息中心 P1-b：投递记录（notification_deliveries）+ 站内收件箱（notification_inbox）

覆盖 spec §11 P1-b 验收：
- A2  in_app 投递同时落收件箱行（离线补偿），投递记录状态为 delivered
- A3  收件箱幂等：同一事件重复派发不产生重复行
- A13 已读 / 忽略 / 未读数语义，且不能操作他人收件箱
"""

import os
import sys
import tempfile
import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from meta.core.sql_adapters import SQLiteAdapter
from meta.services.notification_inbox_service import NotificationInboxService
from meta.services.change_event_dispatcher import ChangeEventDispatcher

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
    """执行多语句迁移脚本（去掉行注释后按分号拆分）。"""
    with open(path, encoding='utf-8') as f:
        content = f.read()
    for statement in content.split(';'):
        lines = [ln for ln in statement.splitlines() if not ln.strip().startswith('--')]
        sql = '\n'.join(lines).strip()
        if sql:
            adapter.execute(sql)


def _make_ds():
    db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db_file.close()
    adapter = SQLiteAdapter()
    adapter.connect(path=db_file.name)
    adapter.execute(_CHANGE_EVENTS_DDL)
    adapter.execute(_CHANGE_SUBSCRIPTIONS_DDL)
    _execute_sql_file(adapter, _MIGRATION_SQL)
    adapter.insert('change_subscriptions', {
        'user_id': 7,
        'object_type': 'work_order',
        'event_types': '["state_changed"]',
        'channel': 'in_app',
        'enabled': 1,
        'created_at': '2026-11-14T10:00:00',
    })
    adapter.commit()
    return adapter, db_file.name


def _cleanup(ds, db_path):
    """先释放连接池再删文件，否则 Windows 上 WinError 32。"""
    try:
        ds.disconnect()
    except Exception:
        pass
    try:
        os.unlink(db_path)
    except OSError:
        pass


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
        'created_at': '2026-11-14T10:00:00',
        'retention_until': '2027-11-14T10:00:00',
    }


@pytest.mark.parametrize('_', [0])
def test_in_app_delivery_creates_inbox_row(_):
    ds, db_path = _make_ds()
    try:
        result = ChangeEventDispatcher(ds).dispatch(101, _event())
        assert result['matched'] == 1
        assert result['delivered'] == 1

        deliveries = ds.find(
            'notification_deliveries', filters={'event_id': 101, 'channel': 'in_app'}
        )
        assert len(deliveries) == 1
        delivery = deliveries[0]
        assert delivery['status'] == 'delivered'
        assert delivery['attempts'] == 1
        assert delivery['user_id'] == 7

        inbox = NotificationInboxService(ds)
        rows, total = inbox.list(7)
        assert total == 1
        assert rows[0]['delivery_id'] == delivery['id']
        assert rows[0]['event_id'] == 101
        assert rows[0]['event_type'] == 'state_changed'
        assert 'draft → released' in rows[0]['body']
        assert inbox.unread_count(7) == 1
    finally:
        _cleanup(ds, db_path)


@pytest.mark.parametrize('_', [0])
def test_inbox_text_uses_metadata_labels(_):
    """通知文案的对象名 / 字段名取自元数据注册表（单一事实来源）"""
    from meta.core.models import FieldType, MetaField, MetaObject, registry

    obj = MetaObject(
        id='inbox_label_test_obj',
        name='演示单据',
        table_name='demo_docs',
        fields=[MetaField(
            id='status', name='单据状态',
            field_type=FieldType.STRING, db_column='status',
        )],
    )
    registry.register(obj)
    ds, db_path = _make_ds()
    try:
        event = {
            'id': 601,
            'object_type': obj.id,
            'object_id': 9,
            'event_type': 'state_changed',
            'changed_fields': ['status'],
            'old_values': {'status': 'draft'},
            'new_values': {'status': 'released'},
            'payload': {},
            'created_at': '2026-11-14T10:00:00',
        }
        service = NotificationInboxService(ds)
        service.create_for_event(7, _seed_delivery(ds, 601), event)

        rows, total = service.list(7)
        assert total == 1
        assert '演示单据' in rows[0]['title']
        assert '单据状态: draft → released' in rows[0]['body']
    finally:
        registry.unregister(obj.id)
        _cleanup(ds, db_path)


@pytest.mark.parametrize('_', [0])
def test_dispatch_twice_is_idempotent(_):
    ds, db_path = _make_ds()
    try:
        dispatcher = ChangeEventDispatcher(ds)
        dispatcher.dispatch(101, _event())
        dispatcher.dispatch(101, _event())

        deliveries = ds.find(
            'notification_deliveries', filters={'event_id': 101}
        )
        assert len(deliveries) == 1

        rows, total = NotificationInboxService(ds).list(7)
        assert total == 1
    finally:
        _cleanup(ds, db_path)


def _seed_delivery(ds, event_id, user_id=7):
    return ds.insert('notification_deliveries', {
        'event_id': event_id,
        'subscription_id': 1,
        'user_id': user_id,
        'channel': 'in_app',
        'target': None,
        'status': 'delivered',
        'attempts': 1,
        'last_error': None,
        'next_retry_at': None,
        'delivered_at': '2026-11-14T10:00:00',
        'created_at': '2026-11-14T10:00:00',
    })


@pytest.mark.parametrize('_', [0])
def test_read_flags_and_unread_count(_):
    ds, db_path = _make_ds()
    try:
        service = NotificationInboxService(ds)
        first = service.create_for_event(7, _seed_delivery(ds, 201), _event(201))
        second = service.create_for_event(7, _seed_delivery(ds, 202), _event(202))
        assert first and second
        assert service.unread_count(7) == 2

        # 单条已读
        row = service.mark_read(7, first)
        assert row is not None
        assert row['read_at']
        assert service.unread_count(7) == 1

        unread_rows, unread_total = service.list(7, unread_only=True)
        assert unread_total == 1
        assert unread_rows[0]['id'] == second

        # 全部已读
        affected = service.mark_all_read(7)
        assert affected == 1
        assert service.unread_count(7) == 0

        all_rows, all_total = service.list(7)
        assert all_total == 2
    finally:
        _cleanup(ds, db_path)


@pytest.mark.parametrize('_', [0])
def test_dismiss_excluded_from_unread_but_kept_in_all(_):
    ds, db_path = _make_ds()
    try:
        service = NotificationInboxService(ds)
        inbox_id = service.create_for_event(7, _seed_delivery(ds, 301), _event(301))
        assert service.unread_count(7) == 1

        row = service.dismiss(7, inbox_id)
        assert row is not None
        assert row['dismissed_at']
        assert service.unread_count(7) == 0

        rows, total = service.list(7)
        assert total == 1
        assert rows[0]['dismissed_at'] is not None
    finally:
        _cleanup(ds, db_path)


@pytest.mark.parametrize('_', [0])
def test_cannot_operate_other_users_inbox(_):
    ds, db_path = _make_ds()
    try:
        service = NotificationInboxService(ds)
        inbox_id = service.create_for_event(7, _seed_delivery(ds, 401), _event(401))
        assert service.mark_read(8, inbox_id) is None
        assert service.dismiss(8, inbox_id) is None
        assert service.unread_count(8) == 0
        assert service.unread_count(7) == 1
    finally:
        _cleanup(ds, db_path)


@pytest.fixture
def inbox_api(monkeypatch):
    """把通知 API 的数据源指向临时库（含一条 admin user_id=1 的私信）。"""
    from meta.api import notification_api

    ds, db_path = _make_ds()
    inbox_id = NotificationInboxService(ds).create_for_event(
        1, _seed_delivery(ds, 501, user_id=1), _event(501)
    )
    monkeypatch.setattr(notification_api, 'ds', ds)
    yield inbox_id
    _cleanup(ds, db_path)


class TestInboxAPI:
    """inbox 端点：鉴权 + 本人数据可见 + 未读语义。"""

    def test_get_inbox(self, api_client, admin_headers, inbox_api):
        resp = api_client.get(f'{NOTIF_URL}/inbox', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        assert isinstance(body.get('data'), list)
        assert len(body['data']) == 1
        assert body['data'][0]['id'] == inbox_api
        assert body['unread_count'] == 1
        assert body['pagination']['total'] == 1

    def test_get_unread_count(self, api_client, admin_headers, inbox_api):
        resp = api_client.get(f'{NOTIF_URL}/inbox/unread-count', headers=admin_headers)
        assert resp.status_code == 200
        assert resp.get_json()['data']['unread_count'] == 1

    def test_read_all(self, api_client, admin_headers, inbox_api):
        resp = api_client.post(f'{NOTIF_URL}/inbox/read-all', json={}, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['affected'] == 1
        assert data['unread_count'] == 0

    def test_read_item(self, api_client, admin_headers, inbox_api):
        resp = api_client.post(
            f'{NOTIF_URL}/inbox/{inbox_api}/read', json={}, headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.get_json()['data']['read_at']

    def test_read_missing_item_404(self, api_client, admin_headers, inbox_api):
        resp = api_client.post(
            f'{NOTIF_URL}/inbox/999999999/read', json={}, headers=admin_headers
        )
        assert resp.status_code == 404