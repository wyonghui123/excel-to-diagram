# -*- coding: utf-8 -*-
"""ChangeEventInterceptor 单元测试。

覆盖 v2 BO 写出口（/api/v2/bo）→ change_events 的发布链路：
  1. 未配置 change_notification 的对象 → should_execute 短路
  2. 非 CRUD action → 不执行
  3. create → 词表归一为 created，object_id 取自 result.data
  4. update → 读取写后行，按 track_fields 计算变更
  5. delete → 行已删除时回落到 old_data
  6. change_events 表缺失 → fail-open，不向调用方抛异常
"""
import os
import tempfile
from types import SimpleNamespace

import pytest

from meta.core.action_context import ActionContext, ActionResult
from meta.core.interceptors.change_event_interceptor import ChangeEventInterceptor
from meta.core.models import (
    MetaObject, MetaField, FieldType, UIViewConfig,
    ChangeNotificationConfig, ChangeEventConfig, registry
)
from meta.core.sql_adapters import SQLiteAdapter
from meta.core.table_name_validator import register_table_name
from meta.tests.factories import _raw_sql_bridge as bridge

pytestmark = pytest.mark.unit

TABLE = 'test_ce_products'
register_table_name(TABLE)

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

_PRODUCTS_DDL = f"""
    CREATE TABLE IF NOT EXISTS {TABLE} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        status TEXT,
        price REAL
    )
"""


def _make_adapter(with_events=True):
    db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db_path = db_file.name
    db_file.close()

    adp = SQLiteAdapter()
    adp.connect(path=db_path)
    adp.execute(_PRODUCTS_DDL)
    if with_events:
        adp.execute(_CHANGE_EVENTS_DDL)
        adp.execute(_CHANGE_SUBSCRIPTIONS_DDL)
    adp.commit()
    return adp, db_path


def _register_object(object_type, enabled=True):
    change_notification = ChangeNotificationConfig(
        enabled=enabled,
        events=[
            ChangeEventConfig(
                type='create', channels=['in_app'],
                track_fields=['name', 'status', 'price'],
                payload=['name', 'status', 'price'],
            ),
            ChangeEventConfig(
                type='update', channels=['in_app'],
                track_fields=['name', 'status', 'price'],
                payload=['name', 'status', 'price'],
            ),
            ChangeEventConfig(
                type='delete', channels=['in_app'],
                track_fields=['name', 'status'],
                payload=['name', 'status'],
            ),
        ],
    )
    registry.register(MetaObject(
        id=object_type,
        name='测试产品',
        table_name=TABLE,
        ui_view_config=UIViewConfig(change_notification=change_notification),
        fields=[
            MetaField(id='id', name='ID', field_type=FieldType.INTEGER, db_column='id'),
            MetaField(id='name', name='名称', field_type=FieldType.STRING, db_column='name'),
            MetaField(id='status', name='状态', field_type=FieldType.STRING, db_column='status'),
            MetaField(id='price', name='价格', field_type=FieldType.FLOAT, db_column='price'),
        ],
    ))


@pytest.fixture
def adapter():
    original_objects = dict(registry._objects)
    adp, db_path = _make_adapter()
    _register_object('test_ce_product')
    yield adp
    adp.disconnect()
    registry._objects = original_objects
    try:
        os.unlink(db_path)
    except OSError:
        pass


def _ctx(ds, *, action, params=None, old_data=None, result=None,
         object_type='test_ce_product'):
    return ActionContext(
        meta_object=registry.get(object_type) or SimpleNamespace(
            id=object_type, table_name=TABLE),
        action=action,
        params=params or {},
        data_source=ds,
        old_data=old_data,
        result=result,
        transaction_id='txn-ce',
    )


def _events(ds, event_type=None):
    sql = "SELECT * FROM change_events"
    args = []
    if event_type:
        sql += " WHERE event_type = ?"
        args.append(event_type)
    cursor = ds.execute(sql, args)
    columns = [d[0] for d in (cursor.description or [])]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


class TestChangeEventInterceptor:

    def test_should_execute_short_circuits_without_config(self, adapter):
        _register_object('test_ce_off', enabled=False)
        ctx = _ctx(adapter, action='crud_update',
                   object_type='test_ce_off', result=ActionResult(success=True))
        assert ChangeEventInterceptor().should_execute(ctx) is False

    def test_should_execute_false_for_read_action(self, adapter):
        ctx = _ctx(adapter, action='custom_query', result=ActionResult(success=True))
        assert ChangeEventInterceptor().should_execute(ctx) is False

    def test_create_publishes_canonical_event(self, adapter):
        ctx = _ctx(
            adapter,
            action='crud_create',
            result=ActionResult(success=True, data={
                'id': 7, 'name': 'A', 'status': 'active', 'price': 1.5,
            }),
        )
        ChangeEventInterceptor().after_action(ctx)

        events = _events(adapter, 'created')
        assert len(events) == 1
        assert events[0]['object_id'] == 7
        assert events[0]['object_type'] == 'test_ce_product'
        # P1-d：发布只写库（异步 worker 负责派发），此处显式派发验证链路
        assert events[0]['status'] == 'pending'
        from meta.services.change_event_dispatcher import ChangeEventDispatcher
        ChangeEventDispatcher(adapter).dispatch(
            events[0]['id'], ChangeEventDispatcher.normalize_event(events[0])
        )
        # 无订阅 → 派发器应把事件推进到 delivered
        assert _events(adapter, 'created')[0]['status'] == 'delivered'

    def test_update_uses_post_write_row(self, adapter):
        bridge.insert(adapter, TABLE, id=1, name='old', status='active', price=1.0)
        adapter.commit()

        ctx = _ctx(
            adapter,
            action='crud_update',
            params={'id': 1},
            old_data={'id': 1, 'name': 'old', 'status': 'active', 'price': 1.0},
            result=ActionResult(success=True),
        )
        bridge.update(adapter, TABLE, {'id': 1}, name='new', price=2.0)
        adapter.commit()

        ChangeEventInterceptor().after_action(ctx)

        events = _events(adapter, 'updated')
        assert len(events) == 1
        assert events[0]['object_id'] == 1
        assert events[0]['changed_fields'] == '["name", "price"]'

    def test_delete_falls_back_to_old_data(self, adapter):
        ctx = _ctx(
            adapter,
            action='crud_delete',
            params={'id': 9},
            old_data={'id': 9, 'name': 'gone', 'status': 'active'},
            result=ActionResult(success=True),
        )
        ChangeEventInterceptor().after_action(ctx)

        events = _events(adapter, 'deleted')
        assert len(events) == 1
        assert events[0]['object_id'] == 9

    def test_publish_failure_is_fail_open(self, adapter):
        adp, db_path = _make_adapter(with_events=False)
        _register_object('test_ce_product')
        try:
            ctx = _ctx(
                adp,
                action='crud_create',
                result=ActionResult(success=True, data={'id': 1, 'name': 'A'}),
            )
            # 不存在 change_events 表，也不允许异常冒泡
            ChangeEventInterceptor().after_action(ctx)
        finally:
            adp.disconnect()
            try:
                os.unlink(db_path)
            except OSError:
                pass