# -*- coding: utf-8 -*-
"""
测试 ManageService 与 ChangeNotificationService 的集成
"""

import sys
import os
import tempfile
import json
import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from meta.core.sql_adapters import SQLiteAdapter
from meta.core.table_name_validator import register_table_name
from meta.core.models import (
    MetaObject, MetaField, FieldType, ActionType, MetaAction,
    UIViewConfig, ChangeNotificationConfig, ChangeEventConfig, registry
)
from meta.services.manage_service import (
    ManageService, CreateRequest, UpdateRequest, DeleteRequest
)
from meta.services.change_notification_service import ChangeEventRequest

pytestmark = pytest.mark.integration

# 夹具自建的表不在 YAML schema 里，须显式登记到 table_name_validator，否则
# ActionExecutor / SQLAdapter 的 validate_table_name() 会拒绝写入。
# 注意 registry.register() **不会**让 table_name_validator 的缓存失效，因此
# 若缓存已被别处预热，仅注册 MetaObject 不足以让表名生效 —— 必须走这里。
register_table_name('test_products')
register_table_name('simple_objects')


# [补 2026-10-07] audit_logs DDL 与平台 v2 schema 对齐
# 原夹具缺 log_category / log_level / outcome / retention_until /
# cascade_root_id / cascade_root_action 等列，导致 AuditService.log() 的
# 27 列 INSERT 静默失败（仅 logger.warning），审计与事件关联无从验证。
# 列清单权威来源：meta/core/audit_async_queue.py:205-211（27 列）+
# meta/migrations/v2_001_audit_log_v2.sql；参考完整版：
# meta/tests/test_audit_service_comprehensive.py:176-208。
_AUDIT_LOGS_DDL = """
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        object_type TEXT,
        object_id TEXT,
        action TEXT,
        field_name TEXT,
        old_value TEXT,
        new_value TEXT,
        user_id TEXT,
        user_name TEXT,
        ip_address TEXT,
        user_agent TEXT,
        created_at TEXT,
        trace_id TEXT,
        transaction_id TEXT,
        status TEXT DEFAULT 'written',
        retry_count INTEGER DEFAULT 0,
        error_message TEXT,
        log_category TEXT,
        log_level TEXT,
        extra_data TEXT,
        parent_object_type TEXT,
        parent_object_id TEXT,
        agent_id TEXT,
        agent_session_id TEXT,
        tool_call_id TEXT,
        agent_reasoning TEXT,
        action_kind TEXT,
        outcome TEXT DEFAULT 'success',
        parent_action_id INTEGER,
        retention_until TEXT,
        cascade_root_id TEXT,
        cascade_root_action TEXT
    )
"""

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
        retry_count INTEGER DEFAULT 0,
        created_at TEXT,
        delivered_at TEXT,
        audit_log_id INTEGER
    )
"""

_TEST_PRODUCTS_DDL = """
    CREATE TABLE IF NOT EXISTS test_products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        status TEXT,
        price REAL,
        created_at TEXT,
        updated_at TEXT,
        created_by TEXT,
        updated_by TEXT
    )
"""


def _create_tables(adapter):
    adapter.execute(_TEST_PRODUCTS_DDL)
    adapter.execute(_AUDIT_LOGS_DDL)
    adapter.execute(_CHANGE_EVENTS_DDL)
    adapter.commit()


def _create_tables_without_change_events(adapter):
    """建表但**不建** change_events —— 用于验证事件发布失败不影响主业务。"""
    adapter.execute(_TEST_PRODUCTS_DDL)
    adapter.execute(_AUDIT_LOGS_DDL)
    adapter.commit()


def _register_test_object():
    change_notification = ChangeNotificationConfig(
        enabled=True,
        events=[
            ChangeEventConfig(
                type='create',
                channels=['in_app'],
                track_fields=['name', 'status', 'price'],
                payload=['name', 'status', 'price']
            ),
            ChangeEventConfig(
                type='update',
                channels=['in_app', 'webhook'],
                track_fields=['name', 'status', 'price'],
                payload=['name', 'status', 'price']
            ),
            ChangeEventConfig(
                type='delete',
                channels=['webhook'],
                track_fields=['name', 'status'],
                payload=['name', 'status']
            )
        ]
    )

    ui_view_config = UIViewConfig(
        change_notification=change_notification
    )

    meta_object = MetaObject(
        id='test_product',
        name='测试产品',
        table_name='test_products',
        ui_view_config=ui_view_config,
        fields=[
            MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id"),
            MetaField(id="name", name="名称", field_type=FieldType.STRING, db_column="name", required=True),
            MetaField(id="status", name="状态", field_type=FieldType.STRING, db_column="status"),
            MetaField(id="price", name="价格", field_type=FieldType.FLOAT, db_column="price"),
            MetaField(id="created_at", name="创建时间", field_type=FieldType.DATETIME, db_column="created_at"),
            MetaField(id="updated_at", name="更新时间", field_type=FieldType.DATETIME, db_column="updated_at"),
            MetaField(id="created_by", name="创建人", field_type=FieldType.STRING, db_column="created_by"),
            MetaField(id="updated_by", name="更新人", field_type=FieldType.STRING, db_column="updated_by"),
        ],
        actions=[
            MetaAction(id="crud_create", name="创建", action_type=ActionType.CRUD, method="POST", path="/api/test_products"),
            MetaAction(id="crud_update", name="更新", action_type=ActionType.CRUD, method="PUT", path="/api/test_products/{id}"),
            MetaAction(id="crud_delete", name="删除", action_type=ActionType.CRUD, method="DELETE", path="/api/test_products/{id}"),
        ]
    )

    registry.register(meta_object)


@pytest.fixture(scope='class')
def _change_notification_registry():
    original_objects = dict(registry._objects)
    yield
    registry._objects = original_objects


def _make_test_db(create_tables):
    db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db_path = db_file.name
    db_file.close()

    adapter = SQLiteAdapter()
    adapter.connect(path=db_path)

    create_tables(adapter)
    _register_test_object()

    return adapter, ManageService(adapter), db_path


@pytest.fixture
def _enable_sync_audit_path(monkeypatch):
    """把审计写入强制到「同步 + 本夹具临时库」分支，让断言可确定复现。

    conftest 的 session 级 fixture 会 create_app()，而 create_app 内部调用
    `async_audit_writer.set_data_source(平台库)`，审计写入随之变成
    「异步 + 写平台库」——临时库里的 audit_logs 永远收不到行，
    `ManageService._get_latest_audit_log_id()` 恒为 None。置空 `_ds` 后走
    `with audit_ds.transaction(): audit_fn(...)` 同步分支。

    注意：还有第二重障碍 `ActionExecutor._write_audit_log_v2()` 开头的
    `if os.environ.get('PYTEST_CURRENT_TEST') is not None: return`
    （action_executor.py:2414）。该变量由 pytest 在 **call 阶段开始前** 重设
    （_pytest/runner.py:pytest_runtest_call → _update_current_test_var），
    因此只能在用例体内移除，放在夹具里会被覆盖 —— 见
    test_audit_log_id_association 首行的 delenv。
    """
    from meta.services import async_audit_writer as aaw
    original = aaw.async_audit_writer._ds
    aaw.async_audit_writer.set_data_source(None)
    yield
    aaw.async_audit_writer.set_data_source(original)


@pytest.fixture
def change_notification_test(_enable_sync_audit_path):
    adapter, manage_service, db_path = _make_test_db(_create_tables)

    yield adapter, manage_service, db_path

    adapter.disconnect()
    try:
        os.unlink(db_path)
    except Exception:
        pass


@pytest.fixture
def event_publish_failure_test(_enable_sync_audit_path):
    """有 change_notification 配置、但缺 change_events 表 —— 事件持久化必失败。"""
    adapter, manage_service, db_path = _make_test_db(_create_tables_without_change_events)

    yield adapter, manage_service, db_path

    adapter.disconnect()
    try:
        os.unlink(db_path)
    except Exception:
        pass


@pytest.mark.usefixtures('_change_notification_registry')
class TestChangeNotificationIntegration:
    """test_product 声明了 change_notification：每个成功写操作应发布对应事件。"""

    def test_create_publishes_event(self, change_notification_test):
        adapter, manage_service, db_path = change_notification_test

        result = manage_service.create(CreateRequest(
            object_type='test_product',
            data={'name': 'P1', 'status': 'active', 'price': 10.0}
        ))

        assert result.success
        events = adapter.find('change_events', filters={'object_type': 'test_product'})
        assert len(events) == 1
        assert events[0]['event_type'] == 'create'
        assert events[0]['object_id'] == result.last_insert_id
        assert json.loads(events[0]['changed_fields']) == ['name', 'status', 'price']

    def test_update_publishes_event_with_changes(self, change_notification_test):
        adapter, manage_service, db_path = change_notification_test
        created = manage_service.create(CreateRequest(
            object_type='test_product',
            data={'name': 'P1', 'status': 'active', 'price': 10.0}
        ))
        assert created.success

        result = manage_service.update(UpdateRequest(
            object_type='test_product',
            id=created.last_insert_id,
            data={'price': 20.0}
        ))

        assert result.success
        events = adapter.find(
            'change_events',
            filters={'object_type': 'test_product', 'event_type': 'update'}
        )
        assert len(events) == 1
        assert json.loads(events[0]['changed_fields']) == ['price']
        assert json.loads(events[0]['new_values']) == {'price': 20.0}

    def test_update_no_tracked_changes_no_event(self, change_notification_test):
        adapter, manage_service, db_path = change_notification_test
        created = manage_service.create(CreateRequest(
            object_type='test_product',
            data={'name': 'P1', 'status': 'active', 'price': 10.0}
        ))
        assert created.success

        # 同值更新：track_fields 无变化 → changed_fields 为空 → 不发事件
        result = manage_service.update(UpdateRequest(
            object_type='test_product',
            id=created.last_insert_id,
            data={'name': 'P1', 'status': 'active', 'price': 10.0}
        ))

        assert result.success
        assert adapter.find(
            'change_events',
            filters={'object_type': 'test_product', 'event_type': 'update'}
        ) == []

    def test_delete_publishes_event(self, change_notification_test):
        adapter, manage_service, db_path = change_notification_test
        created = manage_service.create(CreateRequest(
            object_type='test_product',
            data={'name': 'P1', 'status': 'active', 'price': 10.0}
        ))
        assert created.success

        result = manage_service.delete(DeleteRequest(
            object_type='test_product',
            id=created.last_insert_id
        ))

        assert result.success
        events = adapter.find(
            'change_events',
            filters={'object_type': 'test_product', 'event_type': 'delete'}
        )
        assert len(events) == 1
        assert json.loads(events[0]['changed_fields']) == ['name', 'status']

    def test_create_failure_no_event(self, change_notification_test):
        adapter, manage_service, db_path = change_notification_test

        # 缺必填 name → 创建失败
        result = manage_service.create(CreateRequest(
            object_type='test_product',
            data={'status': 'active'}
        ))

        assert not result.success
        assert adapter.find('change_events', filters={'object_type': 'test_product'}) == []

    def test_update_missing_record_no_event(self, change_notification_test):
        adapter, manage_service, db_path = change_notification_test

        # 不存在的 id：executor 的 UPDATE 不报错（SQLite 影响 0 行仍算成功），
        # 真正拦住事件发布的是 update() 的 `result.success and old_data` 守卫
        # —— 查不到旧数据即不发布。
        result = manage_service.update(UpdateRequest(
            object_type='test_product',
            id=99999,
            data={'name': 'X'}
        ))

        assert result.success  # 无行可改仍返回成功（无副作用）
        assert adapter.find('change_events', filters={'object_type': 'test_product'}) == []
        assert adapter.find('test_products', filters={'id': 99999}) == []

    def test_delete_failure_no_event(self, change_notification_test):
        adapter, manage_service, db_path = change_notification_test

        result = manage_service.delete(DeleteRequest(
            object_type='test_product',
            id=99999
        ))

        assert not result.success
        assert result.error == 'NOT_FOUND'
        assert adapter.find('change_events', filters={'object_type': 'test_product'}) == []

    def test_audit_log_id_association(self, change_notification_test, monkeypatch):
        adapter, manage_service, db_path = change_notification_test

        # pytest 会在 call 阶段开始前重设该变量（_pytest/runner.py:169），
        # 只能在用例体内移除，否则 ActionExecutor 审计链被静默跳过。
        monkeypatch.delenv('PYTEST_CURRENT_TEST', raising=False)

        result = manage_service.create(CreateRequest(
            object_type='test_product',
            data={'name': 'P1', 'status': 'active', 'price': 10.0}
        ))
        assert result.success

        events = adapter.find(
            'change_events',
            filters={'object_type': 'test_product', 'event_type': 'create'}
        )
        assert len(events) == 1

        audit_log_id = events[0]['audit_log_id']
        assert audit_log_id is not None

        audits = adapter.find('audit_logs', filters={'id': audit_log_id})
        assert len(audits) == 1
        assert audits[0]['object_type'] == 'test_product'
        assert audits[0]['action'] == 'CREATE'


def _create_simple_tables(adapter):
    adapter.execute("""
        CREATE TABLE IF NOT EXISTS simple_objects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TEXT
        )
    """)
    adapter.execute(_AUDIT_LOGS_DDL)
    adapter.execute(_CHANGE_EVENTS_DDL)
    adapter.commit()


def _register_simple_object():
    meta_object = MetaObject(
        id='simple_object',
        name='简单对象',
        table_name='simple_objects',
        fields=[
            MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id"),
            MetaField(id="name", name="名称", field_type=FieldType.STRING, db_column="name", required=True),
            MetaField(id="created_at", name="创建时间", field_type=FieldType.DATETIME, db_column="created_at"),
        ],
        actions=[
            MetaAction(id="crud_create", name="创建", action_type=ActionType.CRUD, method="POST", path="/api/simple_objects"),
            MetaAction(id="crud_update", name="更新", action_type=ActionType.CRUD, method="PUT", path="/api/simple_objects/{id}"),
            MetaAction(id="crud_delete", name="删除", action_type=ActionType.CRUD, method="DELETE", path="/api/simple_objects/{id}"),
        ]
    )
    registry.register(meta_object)


@pytest.fixture
def simple_notification_test():
    db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db_path = db_file.name
    db_file.close()

    adapter = SQLiteAdapter()
    adapter.connect(path=db_path)

    _create_simple_tables(adapter)
    _register_simple_object()

    manage_service = ManageService(adapter)

    yield adapter, manage_service, db_path

    adapter.disconnect()
    try:
        os.unlink(db_path)
    except Exception:
        pass


@pytest.mark.usefixtures('_change_notification_registry')
class TestChangeNotificationDisabled:
    """simple_object 无 change_notification 配置：写操作正常，且不产生任何事件。"""

    def test_create_without_notification_config(self, simple_notification_test):
        adapter, manage_service, db_path = simple_notification_test

        result = manage_service.create(CreateRequest(
            object_type='simple_object',
            data={'name': 'S1'}
        ))

        assert result.success
        assert adapter.find('change_events', filters={'object_type': 'simple_object'}) == []

    def test_update_without_notification_config(self, simple_notification_test):
        adapter, manage_service, db_path = simple_notification_test
        created = manage_service.create(CreateRequest(
            object_type='simple_object',
            data={'name': 'S1'}
        ))
        assert created.success

        result = manage_service.update(UpdateRequest(
            object_type='simple_object',
            id=created.last_insert_id,
            data={'name': 'S2'}
        ))

        assert result.success
        assert adapter.find('change_events', filters={'object_type': 'simple_object'}) == []

    def test_delete_without_notification_config(self, simple_notification_test):
        adapter, manage_service, db_path = simple_notification_test
        created = manage_service.create(CreateRequest(
            object_type='simple_object',
            data={'name': 'S1'}
        ))
        assert created.success

        result = manage_service.delete(DeleteRequest(
            object_type='simple_object',
            id=created.last_insert_id
        ))

        assert result.success
        assert adapter.find('change_events', filters={'object_type': 'simple_object'}) == []


@pytest.mark.usefixtures('_change_notification_registry')
class TestEventPublishFailureHandling:
    """事件持久化失败（change_events 表缺失）时，主业务仍须成功返回。"""

    def _assert_publish_fails(self, manage_service):
        """直接调用通知服务，确认「发布失败」路径确实被触发（而非静默跳过）。"""
        probe = manage_service.notification_service.publish_event(ChangeEventRequest(
            object_type='test_product',
            object_id=1,
            event_type='create',
            new_data={'name': 'probe', 'status': 'active', 'price': 1.0}
        ))
        assert probe.success is False

    def test_create_succeeds_even_when_event_publish_fails(self, event_publish_failure_test):
        adapter, manage_service, db_path = event_publish_failure_test

        result = manage_service.create(CreateRequest(
            object_type='test_product',
            data={'name': 'P1', 'status': 'active', 'price': 10.0}
        ))

        assert result.success
        self._assert_publish_fails(manage_service)

    def test_update_succeeds_even_when_event_publish_fails(self, event_publish_failure_test):
        adapter, manage_service, db_path = event_publish_failure_test
        created = manage_service.create(CreateRequest(
            object_type='test_product',
            data={'name': 'P1', 'status': 'active', 'price': 10.0}
        ))
        assert created.success

        result = manage_service.update(UpdateRequest(
            object_type='test_product',
            id=created.last_insert_id,
            data={'price': 20.0}
        ))

        assert result.success
        self._assert_publish_fails(manage_service)

    def test_delete_succeeds_even_when_event_publish_fails(self, event_publish_failure_test):
        adapter, manage_service, db_path = event_publish_failure_test
        created = manage_service.create(CreateRequest(
            object_type='test_product',
            data={'name': 'P1', 'status': 'active', 'price': 10.0}
        ))
        assert created.success

        result = manage_service.delete(DeleteRequest(
            object_type='test_product',
            id=created.last_insert_id
        ))

        assert result.success
        self._assert_publish_fails(manage_service)
