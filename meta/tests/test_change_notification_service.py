import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
测试变更通知服务
"""

import pytest
import tempfile
import json
import os

sys_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys
sys.path.insert(0, sys_path)

from meta.core.sql_adapters import SQLiteAdapter
from meta.core.models import (
    MetaObject, MetaField, FieldType, UIViewConfig,
    ChangeNotificationConfig, ChangeEventConfig, registry
)
from meta.services.change_notification_service import (
    ChangeNotificationService,
    ChangeEventRequest,
    ChangeEventResult,
    FieldChange,
    NotificationConfig
)


@pytest.fixture(scope='class')
def adapter():
    db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db_path = db_file.name
    db_file.close()

    adp = SQLiteAdapter()
    adp.connect(path=db_path)

    adp.execute("""
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
            retry_count INTEGER DEFAULT 0,
            created_at TEXT,
            delivered_at TEXT,
            audit_log_id INTEGER
        )
    """)
    adp.commit()

    yield adp

    adp.disconnect()
    try:
        os.unlink(db_path)
    except:
        pass


@pytest.fixture
def service(adapter):
    original_objects = dict(registry._objects)
    svc = ChangeNotificationService(adapter)
    yield svc
    registry._objects = original_objects


def _register_test_object(svc, object_id, config_enabled=False, events=None):
    events = events or []

    change_notification = None
    if config_enabled:
        change_notification = ChangeNotificationConfig(
            enabled=True,
            events=[
                ChangeEventConfig(
                    type=e['type'],
                    channels=e.get('channels', ['in_app']),
                    track_fields=e.get('track_fields', []),
                    payload=e.get('payload', [])
                ) for e in events
            ]
        )

    ui_view_config = UIViewConfig(change_notification=change_notification)

    meta_object = MetaObject(
        id=object_id,
        name=f"Test Object {object_id}",
        table_name=f"test_{object_id}",
        ui_view_config=ui_view_config,
        fields=[
            MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id"),
            MetaField(id="name", name="Name", field_type=FieldType.STRING, db_column="name"),
            MetaField(id="status", name="Status", field_type=FieldType.STRING, db_column="status"),
            MetaField(id="description", name="Description", field_type=FieldType.TEXT, db_column="description"),
        ]
    )
    registry.register(meta_object)


class TestChangeNotificationService:
    """变更通知服务测试"""

    def test_publish_event_not_configured(self, service):
        """测试对象未配置变更通知"""
        _register_test_object(service, 'test_no_config', config_enabled=False)
        request = ChangeEventRequest(
            object_type='test_no_config', object_id=1,
            event_type='create', new_data={'name': 'Test'}
        )
        result = service.publish_event(request)
        assert result.success is True
        assert result.event_id is None
        assert 'not configured' in result.message

    def test_publish_event_event_type_not_matched(self, service):
        """测试事件类型未配置"""
        _register_test_object(service, 'test_no_event', config_enabled=True, events=[
            {'type': 'create', 'track_fields': ['name']}
        ])
        request = ChangeEventRequest(
            object_type='test_no_event', object_id=1,
            event_type='update',
            old_data={'name': 'Old'},
            new_data={'name': 'New'}
        )
        result = service.publish_event(request)
        assert result.success is True
        assert result.event_id is None
        assert 'not configured' in result.message

    def test_publish_event_create(self, service, adapter):
        """测试创建事件发布"""
        _register_test_object(service, 'test_create', config_enabled=True, events=[{
            'type': 'create', 'channels': ['in_app', 'email'],
            'track_fields': ['name', 'status'], 'payload': ['name', 'status', 'description']
        }])
        request = ChangeEventRequest(
            object_type='test_create', object_id=1, event_type='create',
            new_data={'name': 'Test Name', 'status': 'active', 'description': 'Test Description'},
            audit_log_id=100
        )
        result = service.publish_event(request)
        assert result.success is True
        assert result.event_id is not None
        assert 'name' in result.payload
        assert 'status' in result.payload
        event = adapter.find_by_id('change_events', result.event_id)
        assert event is not None
        assert event['object_type'] == 'test_create'
        assert event['audit_log_id'] == 100

    def test_publish_event_update_with_changes(self, service, adapter):
        """测试更新事件发布（有变更）"""
        _register_test_object(service, 'test_update', config_enabled=True, events=[{
            'type': 'update', 'channels': ['in_app'],
            'track_fields': ['name', 'status'], 'payload': ['name', 'status']
        }])
        request = ChangeEventRequest(
            object_type='test_update', object_id=1, event_type='update',
            old_data={'name': 'Old Name', 'status': 'inactive', 'description': 'Old Description'},
            new_data={'name': 'New Name', 'status': 'active', 'description': 'New Description'}
        )
        result = service.publish_event(request)
        assert result.success is True
        assert result.event_id is not None
        assert set(result.changed_fields) == {'name', 'status'}

    def test_publish_event_update_no_tracked_changes(self, service):
        """测试更新事件发布（无追踪字段变更）"""
        _register_test_object(service, 'test_no_change', config_enabled=True, events=[{
            'type': 'update', 'track_fields': ['name', 'status'], 'payload': ['name']
        }])
        request = ChangeEventRequest(
            object_type='test_no_change', object_id=1, event_type='update',
            old_data={'name': 'Same Name', 'status': 'active', 'description': 'Old Description'},
            new_data={'name': 'Same Name', 'status': 'active', 'description': 'New Description'}
        )
        result = service.publish_event(request)
        assert result.success is True
        assert result.event_id is None
        assert 'No tracked fields changed' in result.message

    def test_publish_event_delete(self, service):
        """测试删除事件发布"""
        _register_test_object(service, 'test_delete', config_enabled=True, events=[{
            'type': 'delete', 'channels': ['webhook'], 'track_fields': ['name'], 'payload': ['name', 'status']
        }])
        request = ChangeEventRequest(
            object_type='test_delete', object_id=1, event_type='delete',
            old_data={'name': 'Deleted Object', 'status': 'active'}
        )
        result = service.publish_event(request)
        assert result.success is True
        assert result.event_id is not None
        assert result.changed_fields == ['name']

    def test_detect_changes_basic(self, service):
        """测试基本变更检测"""
        track_fields = ['name', 'status', 'count']
        old_data = {'name': 'Old', 'status': 'inactive', 'count': 10, 'description': 'Ignored'}
        new_data = {'name': 'New', 'status': 'inactive', 'count': 20, 'description': 'Also Ignored'}
        changes = service._detect_changes(track_fields, old_data, new_data)
        assert set(changes) == {'name', 'count'}

    def test_detect_changes_no_track_fields(self, service):
        """测试无追踪字段时的变更检测"""
        assert service._detect_changes([], {'a': 1}, {'a': 2}) == []

    def test_detect_changes_none_data(self, service):
        """测试空数据时的变更检测"""
        track_fields = ['name']
        assert service._detect_changes(track_fields, None, None) == []
        assert service._detect_changes(track_fields, None, {'name': 'New'}) == ['name']
        assert service._detect_changes(track_fields, {'name': 'Old'}, None) == ['name']

    def test_detect_changes_field_not_in_new_data(self, service):
        """测试字段不在新数据中"""
        track_fields = ['name', 'status']
        changes = service._detect_changes(track_fields, {'name': 'Old', 'status': 'active'}, {'name': 'New'})
        assert changes == ['name']

    def test_values_differ(self, service):
        """测试值比较"""
        assert service._values_differ(None, 'value') is True
        assert service._values_differ('value', None) is True
        assert service._values_differ(None, None) is False
        assert service._values_differ('same', 'same') is False
        assert service._values_differ('old', 'new') is True
        assert service._values_differ({'a': 1}, {'a': 2}) is True
        assert service._values_differ({'a': 1}, {'a': 1}) is False
        assert service._values_differ([1, 2], [1, 3]) is True
        assert service._values_differ([1, 2], [1, 2]) is False
        assert service._values_differ(123, '123') is False

    def test_build_payload_with_config(self, service):
        """测试根据配置构建载荷"""
        event_config = ChangeEventConfig(
            type='create', track_fields=['name'], payload=['name', 'status']
        )
        data = {'name': 'Test', 'status': 'active', 'description': 'Ignored', 'id': 1, 'created_at': '2024-01-01'}
        payload = service._build_payload(event_config, data)
        assert payload == {'name': 'Test', 'status': 'active'}

    def test_build_payload_without_config(self, service):
        """测试无配置时构建载荷"""
        event_config = ChangeEventConfig(type='create', track_fields=['name'], payload=[])
        data = {'name': 'Test', 'status': 'active', 'description': 'Description', 'id': 1, 'created_at': '2024-01-01', 'created_by': 'admin'}
        payload = service._build_payload(event_config, data)
        assert 'name' in payload
        assert 'status' in payload
        assert 'description' in payload
        assert 'id' not in payload

    def test_build_payload_none_data(self, service):
        """测试空数据构建载荷"""
        event_config = ChangeEventConfig(type='create', payload=['name'])
        assert service._build_payload(event_config, None) == {}

    def test_get_pending_events(self, service, adapter):
        """测试获取待处理事件"""
        adapter.execute("DELETE FROM change_events")
        _register_test_object(service, 'test_pending', config_enabled=True, events=[
            {'type': 'create', 'track_fields': ['name']}
        ])
        service.publish_event(ChangeEventRequest(
            object_type='test_pending', object_id=1,
            event_type='create', new_data={'name': 'Test'}
        ))
        pending = service.get_pending_events()
        assert len(pending) >= 1
        assert any(e['status'] == 'pending' for e in pending)

    def test_update_event_status(self, service, adapter):
        """测试更新事件状态"""
        _register_test_object(service, 'test_status', config_enabled=True, events=[
            {'type': 'create', 'track_fields': ['name']}
        ])
        result = service.publish_event(ChangeEventRequest(
            object_type='test_status', object_id=1,
            event_type='create', new_data={'name': 'Test'}
        ))
        success = service.update_event_status(result.event_id, 'delivered', delivered_at='2024-01-01T12:00:00')
        assert success is True
        event = adapter.find_by_id('change_events', result.event_id)
        assert event['status'] == 'delivered'
        assert event['delivered_at'] == '2024-01-01T12:00:00'

    def test_increment_retry_count(self, service, adapter):
        """测试增加重试次数"""
        _register_test_object(service, 'test_retry', config_enabled=True, events=[
            {'type': 'create', 'track_fields': ['name']}
        ])
        result = service.publish_event(ChangeEventRequest(
            object_type='test_retry', object_id=1,
            event_type='create', new_data={'name': 'Test'}
        ))
        service.increment_retry_count(result.event_id)
        service.increment_retry_count(result.event_id)
        event = adapter.find_by_id('change_events', result.event_id)
        assert event['retry_count'] == 2

    def test_get_events_by_object(self, service):
        """测试获取对象的变更事件列表"""
        _register_test_object(service, 'test_by_obj', config_enabled=True, events=[
            {'type': 'create', 'track_fields': ['name']},
            {'type': 'update', 'track_fields': ['name']}
        ])
        service.publish_event(ChangeEventRequest(
            object_type='test_by_obj', object_id=1, event_type='create',
            new_data={'name': 'Test1'}
        ))
        service.publish_event(ChangeEventRequest(
            object_type='test_by_obj', object_id=1, event_type='update',
            old_data={'name': 'Test1'}, new_data={'name': 'Test2'}
        ))
        service.publish_event(ChangeEventRequest(
            object_type='test_by_obj', object_id=2, event_type='create',
            new_data={'name': 'Test3'}
        ))
        events = service.get_events_by_object('test_by_obj', 1)
        assert len(events) == 2

    def test_publish_event_exception_handling(self, service):
        """测试异常处理"""
        result = service.publish_event(ChangeEventRequest(
            object_type='non_existent', object_id=1, event_type='create'
        ))
        assert result.success is True
        assert 'not configured' in result.message


class TestChangeEventRequest:
    """变更事件请求测试"""

    def test_request_creation(self):
        request = ChangeEventRequest(
            object_type='product', object_id=1, event_type='create',
            new_data={'name': 'Test'}, audit_log_id=100
        )
        assert request.object_type == 'product'
        assert request.object_id == 1
        assert request.event_type == 'create'
        assert request.new_data == {'name': 'Test'}
        assert request.audit_log_id == 100
        assert request.old_data is None


class TestChangeEventResult:
    """变更事件结果测试"""

    def test_result_success(self):
        result = ChangeEventResult(
            success=True, event_id=1, message='Success',
            changed_fields=['name'], payload={'name': 'Test'}
        )
        assert result.success is True
        assert result.event_id == 1
        assert result.changed_fields == ['name']

    def test_result_failure(self):
        result = ChangeEventResult(success=False, message='Error occurred')
        assert result.success is False
        assert result.event_id is None


class TestFieldChange:
    """字段变更记录测试"""

    def test_field_change_creation(self):
        change = FieldChange(field_name='status', old_value='inactive', new_value='active')
        assert change.field_name == 'status'
        assert change.old_value == 'inactive'
        assert change.new_value == 'active'
