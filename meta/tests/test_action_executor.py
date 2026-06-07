import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
ActionExecutor 集成测试

测试 ActionExecutor, AuditLogger, 层级路径自动计算
"""

import sys
import os
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.action_executor import ActionExecutor, AuditLogger, ActionResult
from meta.core.datasource import DataSource, DataSourceType
from meta.core.sql_adapters import SQLiteAdapter
from meta.core.rule_executor import RuleEngine
from meta.core.table_name_validator import register_table_name
from meta.core.models import (
    MetaObject, MetaField, MetaRelation, MetaAction, MetaIndex,
    MetaValidation, MetaComputation,
    FieldType, RelationType, ActionType, RuleType, RuleTrigger, ValidationSeverity
)


@pytest.fixture(scope='module')
def ds(tmp_path_factory):
    """创建测试数据源"""
    data_source = SQLiteAdapter()
    # v3.13+ :memory: 不支持，改用临时文件
    db_path = tmp_path_factory.mktemp("test_executor") / "test.db"
    data_source.connect(path=str(db_path))
    # 创建 audit_logs 表（所有测试都需要）
    audit_log_sql = """
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        object_type TEXT NOT NULL,
        object_id INTEGER,
        action TEXT NOT NULL,
        field_name TEXT,
        old_value TEXT,
        new_value TEXT,
        user_id INTEGER,
        user_name TEXT,
        ip_address TEXT,
        user_agent TEXT,
        created_at TEXT,
        extra_data TEXT,
        trace_id TEXT,
        transaction_id TEXT,
        status TEXT,
        retry_count INTEGER DEFAULT 0,
        agent_id TEXT,
        agent_session_id TEXT,
        tool_call_id TEXT,
        agent_reasoning TEXT
    )
    """
    data_source.execute(audit_log_sql)
    return data_source


@pytest.fixture(scope='module')
def executor_setup(ds):
    """设置ActionExecutor"""
    parent, child = create_test_objects()
    setup_database(ds, parent, child)
    rule_engine = RuleEngine(ds)
    executor = ActionExecutor(ds, rule_engine, audit_enabled=True)
    executor.set_audit_user(user_id=1, user_name="测试用户", ip_address="127.0.0.1")
    return ds, executor, parent


@pytest.fixture(scope='module')
def parent_id(executor_setup):
    """创建测试数据并返回ID"""
    ds, executor, parent = executor_setup
    result = executor.execute(parent, "crud_create", {
        "name": "测试父对象",
        "description": "描述",
        "created_by": "测试用户",
    })
    return result.last_insert_id


def create_test_objects():
    """创建测试对象"""
    parent = MetaObject(
        id="parent",
        name="父对象",
        table_name="parents",
        fields=[
            MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id", required=True, unique=True),
            MetaField(id="name", name="名称", field_type=FieldType.STRING, db_column="name", required=True),
            MetaField(id="description", name="描述", field_type=FieldType.TEXT, db_column="description"),
            MetaField(id="created_at", name="创建时间", field_type=FieldType.DATETIME, db_column="created_at"),
            MetaField(id="updated_at", name="更新时间", field_type=FieldType.DATETIME, db_column="updated_at"),
            MetaField(id="created_by", name="创建人", field_type=FieldType.STRING, db_column="created_by"),
            MetaField(id="updated_by", name="更新人", field_type=FieldType.STRING, db_column="updated_by"),
        ],
        actions=[
            MetaAction(id="crud_create", name="创建", action_type=ActionType.CRUD, method="POST", path="/api/parents"),
            MetaAction(id="crud_read", name="查询", action_type=ActionType.CRUD, method="GET", path="/api/parents/{id}"),
            MetaAction(id="crud_update", name="更新", action_type=ActionType.CRUD, method="PUT", path="/api/parents/{id}"),
            MetaAction(id="crud_delete", name="删除", action_type=ActionType.CRUD, method="DELETE", path="/api/parents/{id}"),
        ]
    )
    
    child = MetaObject(
        id="child",
        name="子对象",
        table_name="children",
        parent_object="parent",
        fields=[
            MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id", required=True, unique=True),
            MetaField(id="parent_id", name="父对象ID", field_type=FieldType.INTEGER, db_column="parent_id", required=True),
            MetaField(id="name", name="名称", field_type=FieldType.STRING, db_column="name", required=True),
            MetaField(id="hierarchy_path", name="层级路径", field_type=FieldType.STRING, db_column="hierarchy_path", computed=True, is_hierarchy_path=True, hierarchy_separator="/"),
            MetaField(id="hierarchy_depth", name="层级深度", field_type=FieldType.INTEGER, db_column="hierarchy_depth", computed=True),
            MetaField(id="created_at", name="创建时间", field_type=FieldType.DATETIME, db_column="created_at"),
            MetaField(id="updated_at", name="更新时间", field_type=FieldType.DATETIME, db_column="updated_at"),
            MetaField(id="created_by", name="创建人", field_type=FieldType.STRING, db_column="created_by"),
            MetaField(id="updated_by", name="更新人", field_type=FieldType.STRING, db_column="updated_by"),
        ],
        relations=[
            MetaRelation(
                id="rel1",
                name="关联父对象",
                relation_type=RelationType.PARENT_CHILD,
                target_object="parent",
                cardinality="N:1"
            )
        ],
        actions=[
            MetaAction(id="crud_create", name="创建", action_type=ActionType.CRUD, method="POST", path="/api/children"),
            MetaAction(id="crud_update", name="更新", action_type=ActionType.CRUD, method="PUT", path="/api/children/{id}"),
            MetaAction(id="crud_delete", name="删除", action_type=ActionType.CRUD, method="DELETE", path="/api/children/{id}"),
        ]
    )
    
    return parent, child


def setup_database(ds, parent, child):
    """初始化数据库表"""
    register_table_name(parent.table_name)
    register_table_name(child.table_name)
    
    generator_sql = """
    CREATE TABLE IF NOT EXISTS parents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        created_at TEXT,
        updated_at TEXT,
        created_by TEXT,
        updated_by TEXT
    )
    """
    ds.execute(generator_sql)
    
    child_sql = """
    CREATE TABLE IF NOT EXISTS children (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        parent_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        hierarchy_path TEXT,
        hierarchy_depth INTEGER DEFAULT 0,
        created_at TEXT,
        updated_at TEXT,
        created_by TEXT,
        updated_by TEXT,
        FOREIGN KEY (parent_id) REFERENCES parents(id)
    )
    """
    ds.execute(child_sql)
    
    audit_sql = """
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        object_type TEXT NOT NULL,
        object_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        field_name TEXT,
        old_value TEXT,
        new_value TEXT,
        user_id INTEGER,
        user_name TEXT,
        ip_address TEXT,
        user_agent TEXT,
        created_at TEXT,
        extra_data TEXT,
        trace_id TEXT,
        transaction_id TEXT,
        status TEXT,
        retry_count INTEGER,
        agent_id TEXT,
        agent_session_id TEXT,
        tool_call_id TEXT,
        agent_reasoning TEXT,
        parent_object_type TEXT,
        parent_object_id TEXT
    )
    """
    ds.execute(audit_sql)


def test_audit_logger(tmp_path):
    print("\n=== 测试 AuditLogger ===")
    
    ds = SQLiteAdapter()
    # v3.13+ :memory: 不支持，改用临时文件
    db_path = tmp_path / "test_audit.db"
    ds.connect(path=str(db_path))
    
    ds.execute("""
        CREATE TABLE audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_type TEXT,
            object_id INTEGER,
            action TEXT,
            field_name TEXT,
            old_value TEXT,
            new_value TEXT,
            user_id INTEGER,
            user_name TEXT,
            ip_address TEXT,
            user_agent TEXT,
            created_at TEXT,
            extra_data TEXT,
            trace_id TEXT,
            transaction_id TEXT,
            status TEXT,
            retry_count INTEGER,
            agent_id TEXT,
            agent_session_id TEXT,
            tool_call_id TEXT,
            agent_reasoning TEXT,
            parent_object_type TEXT,
            parent_object_id TEXT
        )
    """)
    
    logger = AuditLogger(ds, enabled=True)
    logger.set_user(user_id=1, user_name="测试用户", ip_address="127.0.0.1")
    
    result = logger.log_create("test_obj", 1, {"name": "测试"})
    assert result == True
    
    result = logger.log_update("test_obj", 1, {"name": "旧值"}, {"name": "新值"})
    assert result == True
    
    result = logger.log_delete("test_obj", 1, {"name": "测试"})
    assert result == True
    
    rows = ds.query("SELECT COUNT(*) as cnt FROM audit_logs")
    assert rows[0]["cnt"] >= 3, "应该有至少 3 条审计日志"
    
    print("  审计日志数量: {0}".format(rows[0]["cnt"]))
    print("[PASS] AuditLogger 测试通过")


def test_action_executor_create(tmp_path):
    """测试 ActionExecutor CRUD Create - 使用 fixture 设置"""
    print("\n=== 测试 ActionExecutor CRUD Create ===")
    
    ds = SQLiteAdapter()
    # v3.13+ :memory: 不支持，改用临时文件
    db_path = tmp_path / "test_executor_create.db"
    ds.connect(path=str(db_path))
    parent, child = create_test_objects()
    setup_database(ds, parent, child)
    
    rule_engine = RuleEngine(ds)
    executor = ActionExecutor(ds, rule_engine, audit_enabled=True)
    executor.set_audit_user(user_id=1, user_name="测试用户", ip_address="127.0.0.1")
    
    result = executor.execute(parent, "crud_create", {
        "name": "测试父对象",
        "description": "描述",
        "created_by": "测试用户",
    })
    
    assert result.success, "创建应该成功: {0}".format(result.message)
    assert result.last_insert_id is not None
    assert result.last_insert_id > 0
    
    print("  创建结果: {0}".format(result.message))
    print("  ID: {0}".format(result.last_insert_id))
    
    row = ds.find_by_id(parent.table_name, result.last_insert_id)
    assert row is not None
    assert row["name"] == "测试父对象"
    
    print("[PASS] ActionExecutor CRUD Create 测试通过")
    return ds, executor, result.last_insert_id


def test_action_executor_read(executor_setup, parent_id):
    """测试 ActionExecutor CRUD Read"""
    print("\n=== 测试 ActionExecutor CRUD Read ===")
    
    ds, executor, parent = executor_setup
    
    parent_obj = MetaObject(
        id="parent",
        name="父对象",
        table_name="parents",
        fields=[
            MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id", required=True, unique=True),
            MetaField(id="name", name="名称", field_type=FieldType.STRING, db_column="name", required=True),
            MetaField(id="description", name="描述", field_type=FieldType.TEXT, db_column="description"),
        ],
        actions=[
            MetaAction(id="crud_read", name="查询", action_type=ActionType.CRUD, method="GET", path="/api/parents/{id}"),
        ]
    )
    
    result = executor.execute(parent_obj, "crud_read", {"id": parent_id})
    
    assert result.success, "读取应该成功"
    assert result.data is not None
    assert result.data.get("name") == "测试父对象"
    
    print("  读取结果: {0}".format(result.data))
    print("[PASS] ActionExecutor CRUD Read 测试通过")


def test_action_executor_update(executor_setup, parent_id):
    """测试 ActionExecutor CRUD Update"""
    print("\n=== 测试 ActionExecutor CRUD Update ===")
    
    ds, executor, parent = executor_setup
    
    parent_obj = MetaObject(
        id="parent",
        name="父对象",
        table_name="parents",
        fields=[
            MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id", required=True, unique=True),
            MetaField(id="name", name="名称", field_type=FieldType.STRING, db_column="name", required=True),
            MetaField(id="description", name="描述", field_type=FieldType.TEXT, db_column="description"),
            MetaField(id="updated_at", name="更新时间", field_type=FieldType.DATETIME, db_column="updated_at"),
            MetaField(id="updated_by", name="更新人", field_type=FieldType.STRING, db_column="updated_by"),
        ],
        actions=[
            MetaAction(id="crud_update", name="更新", action_type=ActionType.CRUD, method="PUT", path="/api/parents/{id}"),
        ]
    )
    
    result = executor.execute(parent_obj, "crud_update", {
        "id": parent_id,
        "name": "更新后的父对象",
        "description": "更新后的描述",
        "updated_by": "测试用户",
    })
    
    assert result.success, "更新应该成功: {0}".format(result.message)
    
    row = ds.find_by_id(parent_obj.table_name, parent_id)
    assert row["name"] == "更新后的父对象"
    assert row["description"] == "更新后的描述"
    
    print("  更新结果: {0}".format(result.message))
    print("[PASS] ActionExecutor CRUD Update 测试通过")


def test_action_executor_delete(executor_setup, parent_id):
    """测试 ActionExecutor CRUD Delete"""
    print("\n=== 测试 ActionExecutor CRUD Delete ===")
    
    ds, executor, parent = executor_setup
    
    parent_obj = MetaObject(
        id="parent",
        name="父对象",
        table_name="parents",
        fields=[
            MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id", required=True, unique=True),
        ],
        actions=[
            MetaAction(id="crud_delete", name="删除", action_type=ActionType.CRUD, method="DELETE", path="/api/parents/{id}"),
        ]
    )
    
    result = executor.execute(parent_obj, "crud_delete", {"id": parent_id})
    
    assert result.success, "删除应该成功: {0}".format(result.message)
    
    row = ds.find_by_id(parent_obj.table_name, parent_id)
    assert row is None, "记录应该已被删除"
    
    print("  删除结果: {0}".format(result.message))
    print("[PASS] ActionExecutor CRUD Delete 测试通过")


def test_action_executor_audit_log(ds):
    """测试 ActionExecutor 审计日志"""
    print("\n=== 测试 ActionExecutor 审计日志 ===")
    
    logger = AuditLogger(ds, enabled=True)
    logger.set_user(user_id=1, user_name="测试用户", ip_address="127.0.0.1")
    
    logger.log_create("test_obj", 1, {"name": "测试创建"})
    logger.log_update("test_obj", 1, {"name": "旧值"}, {"name": "新值"})
    logger.log_delete("test_obj", 1, {"name": "测试删除"})
    
    rows = ds.query("SELECT * FROM audit_logs ORDER BY id")
    
    print("  审计日志数量: {0}".format(len(rows)))
    for row in rows:
        print("    {0}: {1} (object_type={2}, object_id={3})".format(
            row["action"], row.get("field_name", ""), row["object_type"], row["object_id"]
        ))
    
    assert len(rows) >= 3, "应该有至少 3 条审计日志 (create, update, delete)"
    
    print("[PASS] ActionExecutor 审计日志测试通过")


def run_all_tests():
    print("=" * 60)
    print("ActionExecutor 集成测试")
    print("=" * 60)
    
    test_audit_logger()
    
    ds, executor, parent_id = test_action_executor_create()
    test_action_executor_read(ds, executor, parent_id)
    test_action_executor_update(ds, executor, parent_id)
    test_action_executor_delete(ds, executor, parent_id)
    test_action_executor_audit_log(ds)
    
    print("\n" + "=" * 60)
    print("所有测试通过！")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
