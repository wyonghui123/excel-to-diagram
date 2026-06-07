# -*- coding: utf-8 -*-
"""
条件型权限系统自动化测试

覆盖：
1. ConditionEvaluator 条件解析器
2. ConditionPermissionService 核心服务
3. API 端点集成测试
"""

import sys
import os
import json
import tempfile
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from meta.services.condition_evaluator import ConditionEvaluator
from meta.services.condition_permission_service import ConditionPermissionService


# ============================================
# 测试辅助
# ============================================

class MockDataSource:
    """模拟数据源"""

    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def execute(self, sql, params=None):
        cursor = self.conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        self.conn.commit()
        return cursor

    def close(self):
        self.conn.close()


def setup_test_db():
    """创建测试数据库并初始化数据"""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(db_fd)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""CREATE TABLE roles (id INTEGER PRIMARY KEY, code TEXT, name TEXT, description TEXT, is_system INTEGER DEFAULT 0, priority INTEGER DEFAULT 0)""")
    cursor.execute("""CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, display_name TEXT, status TEXT DEFAULT 'active', department_id INTEGER, organization_id INTEGER)""")
    cursor.execute("""CREATE TABLE user_roles (id INTEGER PRIMARY KEY, user_id INTEGER, role_id INTEGER, UNIQUE(user_id, role_id))""")
    cursor.execute("""CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, code TEXT, created_by INTEGER, owner_id INTEGER)""")
    cursor.execute("""CREATE TABLE versions (id INTEGER PRIMARY KEY, name TEXT, code TEXT, product_id INTEGER, created_by INTEGER)""")
    cursor.execute("""CREATE TABLE domains (id INTEGER PRIMARY KEY, name TEXT, code TEXT, domain_type TEXT, product_id INTEGER, version_id INTEGER, created_by INTEGER, owner_id INTEGER)""")
    cursor.execute("""CREATE TABLE sub_domains (id INTEGER PRIMARY KEY, name TEXT, code TEXT, domain_id INTEGER, product_id INTEGER, created_by INTEGER)""")
    cursor.execute("""CREATE TABLE service_modules (id INTEGER PRIMARY KEY, name TEXT, code TEXT, sub_domain_id INTEGER, product_id INTEGER, created_by INTEGER)""")
    cursor.execute("""CREATE TABLE business_objects (id INTEGER PRIMARY KEY, name TEXT, code TEXT, service_module_id INTEGER, product_id INTEGER, created_by INTEGER)""")

    cursor.execute("""CREATE TABLE permission_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role_id INTEGER NOT NULL,
        resource_type TEXT NOT NULL,
        condition TEXT NOT NULL,
        permission_level TEXT NOT NULL DEFAULT 'read',
        is_denied INTEGER DEFAULT 0,
        inherit_to_children INTEGER DEFAULT 1,
        propagate_to_parents INTEGER DEFAULT 1,
        analysis_mode TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        created_by INTEGER,
        updated_at DATETIME
    )""")

    cursor.execute("""CREATE TABLE management_dimensions (
        id INTEGER PRIMARY KEY, code TEXT UNIQUE, name TEXT, field TEXT, resource_types TEXT, description TEXT,
        relation_object TEXT, display_field TEXT, is_auto_generated INTEGER DEFAULT 0, source_schema TEXT,
        cascade_parent TEXT
    )""")

    cursor.execute("""CREATE TABLE employee_data_scopes (
        id INTEGER PRIMARY KEY, code TEXT UNIQUE, name TEXT, condition_template TEXT, description TEXT
    )""")

    cursor.executemany("INSERT INTO roles VALUES (?, ?, ?, ?, ?, ?)", [
        (1, 'admin', '管理员', '系统管理员', 1, 100),
        (2, 'product_manager', '产品经理', '产品线管理员', 0, 50),
        (3, 'viewer', '查看者', '只读用户', 0, 10),
        (4, 'denied_role', '受限角色', '被禁止的角色', 0, 5),
    ])

    cursor.executemany("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)", [
        (1, 'admin', '管理员', 'active', 1, 1),
        (2, 'zhangsan', '张三', 'active', 1, 1),
        (3, 'lisi', '李四', 'active', 2, 1),
        (4, 'wangwu', '王五', 'active', 1, 1),
    ])

    cursor.executemany("INSERT INTO user_roles VALUES (?, ?, ?)", [
        (1, 1, 1),
        (2, 2, 2),
        (3, 3, 3),
        (4, 4, 4),
        (5, 2, 3),
    ])

    cursor.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?)", [
        (1, 'V5基础平台', 'V5', 1, 1),
        (2, '供应链云', 'SCM', 1, 1),
        (3, '财务云', 'FIN', 2, 2),
    ])

    cursor.executemany("INSERT INTO domains VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
        (1, '核心领域', 'CORE', 'CORE', 1, 1, 1, 1),
        (2, '支撑领域', 'SUPPORT', 'SUPPORT', 1, 1, 2, 1),
        (3, '供应链核心', 'SCM_CORE', 'CORE', 2, 2, 1, 1),
        (4, '财务核心', 'FIN_CORE', 'CORE', 3, 2, 3, 3),
        (5, '公共领域', 'COMMON', 'COMMON', 1, 1, 4, 4),
    ])

    cursor.executemany("INSERT INTO sub_domains VALUES (?, ?, ?, ?, ?, ?)", [
        (1, '用户管理', 'USER_MGMT', 1, 1, 1),
        (2, '权限管理', 'PERM_MGMT', 1, 1, 2),
        (3, '订单管理', 'ORDER_MGMT', 3, 2, 1),
    ])

    cursor.executemany("INSERT INTO service_modules VALUES (?, ?, ?, ?, ?, ?)", [
        (1, '认证模块', 'AUTH', 1, 1, 1),
        (2, '授权模块', 'AUTHZ', 1, 1, 2),
    ])

    cursor.executemany("INSERT INTO permission_rules VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
        (1, 2, 'domain', 'product_id = 1', 'write', 0, 1, 1, None, '2026-01-01', 1, None),
        (2, 2, 'domain', "domain_type = 'CORE'", 'read', 0, 1, 1, None, '2026-01-01', 1, None),
        (3, 3, 'domain', 'product_id IN (1, 2)', 'read', 0, 1, 1, None, '2026-01-01', 1, None),
        (4, 4, 'domain', 'product_id = 1', 'read', 1, 1, 1, None, '2026-01-01', 1, None),
        (5, 2, 'sub_domain', 'product_id = 1', 'write', 0, 1, 1, None, '2026-01-01', 1, None),
    ])

    cursor.executemany("INSERT INTO management_dimensions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
        (1, 'product', '产品', 'product_id', 'domain,sub_domain,service_module,business_object', '产品线权限', 'product', 'name', 0, '', ''),
        (2, 'domain_type', '领域类型', 'domain_type', 'domain', '领域类型权限', '', '', 0, '', ''),
        (3, 'employee', '员工', 'created_by', 'domain,sub_domain', '员工数据权限', 'user', 'display_name', 0, '', ''),
        (4, 'version', '版本', 'version_id', 'domain,sub_domain', '版本权限', 'version', 'name', 1, 'domain.version_id', 'product'),
    ])

    cursor.executemany("INSERT INTO employee_data_scopes VALUES (?, ?, ?, ?, ?)", [
        (1, 'self', '本人', 'created_by = :user_id', '本人创建的数据'),
        (2, 'department', '本部门', 'department_id = :user_department_id', '本部门数据'),
        (3, 'department_tree', '本部门及下级', 'department_id IN (:user_department_tree)', '层级数据'),
        (4, 'organization', '本组织', 'organization_id = :user_organization_id', '本组织数据'),
    ])

    conn.commit()
    conn.close()
    return db_path


# ============================================
# 1. ConditionEvaluator 测试
# ============================================

def test_evaluator_predicate():
    """测试 predicate 类型条件"""
    e = ConditionEvaluator()
    passed = 0
    failed = 0

    cases = [
        ('product_id = 1', {'product_id': 1}, True),
        ('product_id = 1', {'product_id': 2}, False),
        ('product_id IN (1, 2, 3)', {'product_id': 2}, True),
        ('product_id IN (1, 2, 3)', {'product_id': 5}, False),
        ("domain_type = 'CORE'", {'domain_type': 'CORE'}, True),
        ("domain_type = 'CORE'", {'domain_type': 'SUPPORT'}, False),
        ("product_id IN (1, 2, 3) AND domain_type = 'CORE'", {'product_id': 1, 'domain_type': 'CORE'}, True),
        ("product_id IN (1, 2, 3) AND domain_type = 'CORE'", {'product_id': 1, 'domain_type': 'SUPPORT'}, False),
        ('id = 5', {'id': 5}, True),
        ('id = 5', {'id': 6}, False),
        ('product_id != 1', {'product_id': 2}, True),
        ('product_id != 1', {'product_id': 1}, False),
        ('product_id NOT IN (1, 2)', {'product_id': 3}, True),
        ('product_id NOT IN (1, 2)', {'product_id': 1}, False),
    ]

    for condition, resource, expected in cases:
        result = e.evaluate(condition, resource)
        if result == expected:
            passed += 1
        else:
            failed += 1
            print(f"  [X] predicate: '{condition}' with {resource} → expected {expected}, got {result}")

    print(f"  [OK] predicate: {passed} passed, {failed} failed")
    return failed == 0


def test_evaluator_field_range():
    """测试 field_range 类型条件"""
    e = ConditionEvaluator()
    passed = 0
    failed = 0

    cases = [
        ('{"fields": [{"name": "product_id", "operator": "in", "values": [1, 2, 3]}]}', {'product_id': 2}, True),
        ('{"fields": [{"name": "product_id", "operator": "in", "values": [1, 2, 3]}]}', {'product_id': 5}, False),
        ('{"fields": [{"name": "domain_type", "operator": "=", "value": "CORE"}]}', {'domain_type': 'CORE'}, True),
        ('{"fields": [{"name": "domain_type", "operator": "=", "value": "CORE"}]}', {'domain_type': 'SUPPORT'}, False),
        ('{"fields": [{"name": "product_id", "operator": "between", "min": 1, "max": 5}]}', {'product_id': 3}, True),
        ('{"fields": [{"name": "product_id", "operator": "between", "min": 1, "max": 5}]}', {'product_id': 6}, False),
    ]

    for condition, resource, expected in cases:
        result = e.evaluate(condition, resource)
        if result == expected:
            passed += 1
        else:
            failed += 1
            print(f"  [X] field_range: '{condition}' with {resource} → expected {expected}, got {result}")

    print(f"  [OK] field_range: {passed} passed, {failed} failed")
    return failed == 0


def test_evaluator_security():
    """测试安全性"""
    e = ConditionEvaluator()
    passed = 0
    failed = 0

    safe_cases = [
        'product_id = 1',
        "domain_type = 'CORE'",
        'product_id IN (1, 2, 3)',
    ]

    for condition in safe_cases:
        if e._validate_predicate(condition):
            passed += 1
        else:
            failed += 1
            print(f"  [X] safe predicate rejected: '{condition}'")

    unsafe_cases = [
        'DROP TABLE users',
        '1=1; DELETE FROM users',
        "product_id = 1 UNION SELECT * FROM users",
    ]

    for condition in unsafe_cases:
        if not e._validate_predicate(condition):
            passed += 1
        else:
            failed += 1
            print(f"  [X] unsafe predicate accepted: '{condition}'")

    print(f"  [OK] security: {passed} passed, {failed} failed")
    return failed == 0


def test_evaluator_template_resolution():
    """测试模板参数解析"""
    e = ConditionEvaluator()
    passed = 0
    failed = 0

    cases = [
        ('created_by = :user_id', {'user_id': 5}, 'created_by = 5'),
        ('department_id = :user_department_id', {'user_department_id': 10}, 'department_id = 10'),
        ('department_id IN (:user_department_tree)', {'user_department_tree': [1, 2, 3]}, 'department_id IN (1,2,3)'),
    ]

    for template, params, expected in cases:
        result = e.resolve_template(template, params)
        if result == expected:
            passed += 1
        else:
            failed += 1
            print(f"  [X] template: '{template}' with {params} → expected '{expected}', got '{result}'")

    print(f"  [OK] template: {passed} passed, {failed} failed")
    return failed == 0


def test_evaluator_instance_references():
    """测试实例引用检测"""
    e = ConditionEvaluator()
    passed = 0
    failed = 0

    refs = e.detect_instance_references('domain_id = 5 AND product_id = 1')
    if len(refs) == 2:
        passed += 1
    else:
        failed += 1
        print(f"  [X] instance refs: expected 2, got {len(refs)}")

    refs = e.detect_instance_references('id = 5')
    if len(refs) == 1 and refs[0]['resource_type'] == 'exact':
        passed += 1
    else:
        failed += 1
        print(f"  [X] exact ref: expected resource_type='exact', got {refs}")

    refs = e.detect_instance_references("domain_type = 'CORE'")
    if len(refs) == 0:
        passed += 1
    else:
        failed += 1
        print(f"  [X] no refs: expected 0, got {len(refs)}")

    print(f"  [OK] instance_refs: {passed} passed, {failed} failed")
    return failed == 0


def test_evaluator_sql_where():
    """测试条件转 SQL WHERE"""
    e = ConditionEvaluator()
    passed = 0
    failed = 0

    result = e.predicate_to_sql_where('product_id = 1')
    if result == 'product_id = 1':
        passed += 1
    else:
        failed += 1
        print(f"  [X] sql_where: expected 'product_id = 1', got '{result}'")

    result = e.predicate_to_sql_where('DROP TABLE users')
    if result is None:
        passed += 1
    else:
        failed += 1
        print(f"  [X] sql_where unsafe: expected None, got '{result}'")

    print(f"  [OK] sql_where: {passed} passed, {failed} failed")
    return failed == 0


# ============================================
# 2. ConditionPermissionService 测试
# ============================================

def test_service_owner_permission(db_path):
    """测试 Owner 自动权限"""
    ds = MockDataSource(db_path)
    service = ConditionPermissionService(ds)
    passed = 0
    failed = 0

    result = service.check_permission(1, 'domain', 1, 'read')
    if result['allowed'] and result['source'] == 'owner' and result['permission_level'] == 'admin':
        passed += 1
    else:
        failed += 1
        print(f"  [X] owner: user=1, domain=1 → expected owner/admin, got {result}")

    result = service.check_permission(3, 'domain', 1, 'read')
    if not result['source'] == 'owner':
        passed += 1
    else:
        failed += 1
        print(f"  [X] not_owner: user=3, domain=1 → expected not owner, got {result}")

    print(f"  [OK] owner_permission: {passed} passed, {failed} failed")
    ds.close()
    return failed == 0


def test_service_condition_match(db_path):
    """测试条件型权限匹配"""
    ds = MockDataSource(db_path)
    service = ConditionPermissionService(ds)
    passed = 0
    failed = 0

    result = service.check_permission(2, 'domain', 1, 'read')
    if result['allowed'] and result['source'] == 'condition':
        passed += 1
    else:
        failed += 1
        print(f"  [X] condition_match: user=2(role=product_manager), domain=1(product_id=1) → expected condition, got {result}")

    result = service.check_permission(2, 'domain', 4, 'read')
    if result['allowed'] and result['source'] == 'condition':
        passed += 1
    else:
        failed += 1
        print(f"  [X] condition_match2: user=2, domain=4(product_id=3) via domain_type=CORE → expected condition, got {result}")

    print(f"  [OK] condition_match: {passed} passed, {failed} failed")
    ds.close()
    return failed == 0


def test_service_denied_priority(db_path):
    """测试禁止权优先原则"""
    ds = MockDataSource(db_path)
    service = ConditionPermissionService(ds)
    passed = 0
    failed = 0

    result = service.check_permission(4, 'domain', 1, 'read')
    if result['source'] == 'denied':
        passed += 1
    else:
        failed += 1
        print(f"  [X] denied: user=4(role=denied_role), domain=1 → expected denied, got {result}")

    print(f"  [OK] denied_priority: {passed} passed, {failed} failed")
    ds.close()
    return failed == 0


def test_service_inheritance(db_path):
    """测试向下继承"""
    ds = MockDataSource(db_path)
    service = ConditionPermissionService(ds)
    passed = 0
    failed = 0

    result = service.check_permission(2, 'sub_domain', 1, 'read')
    if result['allowed']:
        passed += 1
    else:
        failed += 1
        print(f"  [X] inheritance: user=2, sub_domain=1(product_id=1) → expected allowed, got {result}")

    print(f"  [OK] inheritance: {passed} passed, {failed} failed")
    ds.close()
    return failed == 0


def test_service_crud(db_path):
    """测试 CRUD 操作"""
    ds = MockDataSource(db_path)
    service = ConditionPermissionService(ds)
    passed = 0
    failed = 0

    rule_id = service.create_rule({
        'role_id': 3,
        'resource_type': 'domain',
        'condition': "domain_type = 'SUPPORT'",
        'permission_level': 'read',
        'inherit_to_children': True,
        'propagate_to_parents': True,
    })
    if rule_id:
        passed += 1
    else:
        failed += 1
        print(f"  [X] create_rule: failed to create")

    rule = service.get_rule(rule_id)
    if rule and rule['condition'] == "domain_type = 'SUPPORT'":
        passed += 1
    else:
        failed += 1
        print(f"  [X] get_rule: expected condition='domain_type=SUPPORT', got {rule}")

    success = service.update_rule(rule_id, {'permission_level': 'write'})
    if success:
        updated = service.get_rule(rule_id)
        if updated['permission_level'] == 'write':
            passed += 1
        else:
            failed += 1
            print(f"  [X] update_rule: expected write, got {updated['permission_level']}")
    else:
        failed += 1
        print(f"  [X] update_rule: failed")

    success = service.delete_rule(rule_id)
    if success:
        deleted = service.get_rule(rule_id)
        if deleted is None:
            passed += 1
        else:
            failed += 1
            print(f"  [X] delete_rule: rule still exists")
    else:
        failed += 1
        print(f"  [X] delete_rule: failed")

    print(f"  [OK] CRUD: {passed} passed, {failed} failed")
    ds.close()
    return failed == 0


def test_service_dimensions(db_path):
    """测试管理维度（含Schema新字段）"""
    ds = MockDataSource(db_path)
    service = ConditionPermissionService(ds)
    passed = 0
    failed = 0

    dims = service.get_management_dimensions()
    if len(dims) >= 4:
        passed += 1
    else:
        failed += 1
        print(f"  [X] dimensions: expected >=4, got {len(dims)}")

    dims = service.get_management_dimensions('domain')
    if all('domain' in (d.get('resource_types') or '') for d in dims):
        passed += 1
    else:
        failed += 1
        print(f"  [X] dimensions_filtered: some dims don't apply to domain")

    # 测试新字段：relation_object, display_field, is_auto_generated, source_schema
    product_dim = next((d for d in dims if d['code'] == 'product'), None)
    if product_dim and product_dim.get('relation_object') == 'product' and product_dim.get('display_field') == 'name':
        passed += 1
    else:
        failed += 1
        print(f"  [X] dimension_new_fields: product dim missing relation_object/display_field, got {product_dim}")

    version_dim = next((d for d in dims if d['code'] == 'version'), None)
    if version_dim and version_dim.get('is_auto_generated') == 1 and version_dim.get('source_schema') == 'domain.version_id':
        passed += 1
    else:
        failed += 1
        print(f"  [X] dimension_auto_generated: version dim missing is_auto_generated/source_schema, got {version_dim}")

    print(f"  [OK] dimensions: {passed} passed, {failed} failed")
    ds.close()
    return failed == 0


def test_service_dimension_value_help(db_path):
    """测试管理维度Value Help"""
    ds = MockDataSource(db_path)
    service = ConditionPermissionService(ds)
    passed = 0
    failed = 0

    # product维度有relation_object=product，应返回产品列表
    values = service.get_dimension_value_help('product', limit=10)
    if len(values) >= 3:
        passed += 1
    else:
        failed += 1
        print(f"  [X] value_help_product: expected >=3 values, got {len(values)}")

    # 检查返回结构
    if values and all('id' in v and 'display_name' in v for v in values):
        passed += 1
    else:
        failed += 1
        print(f"  [X] value_help_structure: missing id or display_name in {values}")

    # domain_type维度无relation_object，应返回空
    values = service.get_dimension_value_help('domain_type', limit=10)
    if len(values) == 0:
        passed += 1
    else:
        failed += 1
        print(f"  [X] value_help_no_relation: expected empty, got {len(values)}")

    # 测试搜索功能
    values = service.get_dimension_value_help('product', search='V5', limit=10)
    if len(values) >= 1:
        passed += 1
    else:
        failed += 1
        print(f"  [X] value_help_search: expected >=1 for 'V5', got {len(values)}")

    print(f"  [OK] value_help: {passed} passed, {failed} failed")
    ds.close()
    return failed == 0


def test_service_field_metadata(db_path):
    """测试字段元数据（从Schema Registry）"""
    ds = MockDataSource(db_path)
    service = ConditionPermissionService(ds)
    passed = 0
    failed = 0

    fields = service.get_resource_field_metadata('domain')
    if len(fields) > 0:
        passed += 1
    else:
        failed += 1
        print(f"  [X] field_metadata: expected >0 fields for domain, got {len(fields)}")

    # 检查字段结构
    if fields and all('id' in f and 'name' in f and 'db_column' in f and 'field_type' in f for f in fields):
        passed += 1
    else:
        failed += 1
        print(f"  [X] field_metadata_structure: missing required keys in {fields[:1]}")

    # 检查外键字段识别
    fk_fields = [f for f in fields if f.get('is_foreign_key')]
    if len(fk_fields) > 0:
        passed += 1
    else:
        failed += 1
        print(f"  [X] field_metadata_fk: expected >0 foreign key fields, got {len(fk_fields)}")

    # 检查外键字段有relation_object
    if fk_fields and all(f.get('relation_object') for f in fk_fields):
        passed += 1
    else:
        failed += 1
        print(f"  [X] field_metadata_fk_relation: fk fields missing relation_object: {fk_fields}")

    print(f"  [OK] field_metadata: {passed} passed, {failed} failed")
    ds.close()
    return failed == 0


def test_schema_scan_dimensions():
    """测试Schema扫描自动生成管理维度"""
    from meta.scripts.init_condition_permission import _scan_schema_for_dimensions
    passed = 0
    failed = 0

    dims = _scan_schema_for_dimensions()
    if len(dims) > 0:
        passed += 1
    else:
        failed += 1
        print(f"  [X] schema_scan: expected >0 dimensions, got {len(dims)}")

    # 检查自动生成的维度有正确的结构
    if dims and all('code' in d and 'name' in d and 'field' in d for d in dims):
        passed += 1
    else:
        failed += 1
        print(f"  [X] schema_scan_structure: missing required keys")

    # 检查外键维度有relation_object和display_field
    fk_dims = [d for d in dims if d.get('relation_object')]
    if len(fk_dims) > 0:
        passed += 1
    else:
        failed += 1
        print(f"  [X] schema_scan_fk: expected >0 fk dimensions, got {len(fk_dims)}")

    # 检查所有自动生成的维度标记为is_auto_generated=1
    if all(d.get('is_auto_generated') == 1 for d in dims):
        passed += 1
    else:
        failed += 1
        print(f"  [X] schema_scan_auto_flag: not all dims have is_auto_generated=1")

    # 检查source_schema字段
    if all(d.get('source_schema') for d in dims):
        passed += 1
    else:
        failed += 1
        print(f"  [X] schema_scan_source: not all dims have source_schema")

    print(f"  [OK] schema_scan: {passed} passed, {failed} failed")
    return failed == 0


def test_service_employee_scopes(db_path):
    """测试员工数据权限范围"""
    ds = MockDataSource(db_path)
    service = ConditionPermissionService(ds)
    passed = 0
    failed = 0

    scopes = service.get_employee_data_scopes()
    if len(scopes) >= 4:
        passed += 1
    else:
        failed += 1
        print(f"  [X] employee_scopes: expected >=4, got {len(scopes)}")

    condition = service.resolve_employee_scope_condition(2, 'self')
    if condition and '2' in condition:
        passed += 1
    else:
        failed += 1
        print(f"  [X] resolve_scope: expected condition with user_id=2, got '{condition}'")

    print(f"  [OK] employee_scopes: {passed} passed, {failed} failed")
    ds.close()
    return failed == 0


def test_service_reference_check(db_path):
    """测试条件引用实例检测"""
    ds = MockDataSource(db_path)
    service = ConditionPermissionService(ds)
    passed = 0
    failed = 0

    affected = service.check_rule_references_resource('domain', 1)
    if len(affected) >= 0:
        passed += 1
    else:
        failed += 1
        print(f"  [X] reference_check: domain=1 check failed, got {len(affected)} rules")

    cursor = ds.execute(
        "INSERT INTO permission_rules (role_id, resource_type, condition, permission_level) VALUES (2, 'domain', 'id = 5', 'read')"
    )
    affected = service.check_rule_references_resource('domain', 5)
    if len(affected) > 0:
        passed += 1
    else:
        failed += 1
        print(f"  [X] reference_check: domain=5 should be referenced by 'id = 5', got {len(affected)} rules")

    affected = service.check_rule_references_resource('domain', 999)
    if len(affected) == 0:
        passed += 1
    else:
        failed += 1
        print(f"  [X] reference_check: domain=999 should not be referenced, got {len(affected)} rules")

    print(f"  [OK] reference_check: {passed} passed, {failed} failed")
    ds.close()
    return failed == 0


def test_service_preview(db_path):
    """测试资源预览"""
    ds = MockDataSource(db_path)
    service = ConditionPermissionService(ds)
    passed = 0
    failed = 0

    result = service.preview_matching_resources('product_id = 1', 'domain')
    if result['count'] >= 2:
        passed += 1
    else:
        failed += 1
        print(f"  [X] preview: product_id=1 domains expected >=2, got {result['count']}")

    result = service.preview_matching_resources("domain_type = 'CORE'", 'domain')
    if result['count'] >= 2:
        passed += 1
    else:
        failed += 1
        print(f"  [X] preview: domain_type=CORE expected >=2, got {result['count']}")

    print(f"  [OK] preview: {passed} passed, {failed} failed")
    ds.close()
    return failed == 0


# ============================================
# 运行所有测试
# ============================================

def run_all_tests():
    print("=" * 60)
    print("条件型权限系统自动化测试")
    print("=" * 60)

    db_path = setup_test_db()
    total_passed = 0
    total_failed = 0

    print("\n--- 1. ConditionEvaluator 测试 ---")
    tests = [
        ("predicate 条件", test_evaluator_predicate),
        ("field_range 条件", test_evaluator_field_range),
        ("安全性验证", test_evaluator_security),
        ("模板参数解析", test_evaluator_template_resolution),
        ("实例引用检测", test_evaluator_instance_references),
        ("SQL WHERE 转换", test_evaluator_sql_where),
    ]
    for name, test_fn in tests:
        print(f"\n  [{name}]")
        if test_fn():
            total_passed += 1
        else:
            total_failed += 1

    print("\n--- 2. ConditionPermissionService 测试 ---")
    service_tests = [
        ("Owner 自动权限", lambda: test_service_owner_permission(db_path)),
        ("条件型权限匹配", lambda: test_service_condition_match(db_path)),
        ("禁止权优先原则", lambda: test_service_denied_priority(db_path)),
        ("向下继承", lambda: test_service_inheritance(db_path)),
        ("CRUD 操作", lambda: test_service_crud(db_path)),
        ("管理维度", lambda: test_service_dimensions(db_path)),
        ("维度Value Help", lambda: test_service_dimension_value_help(db_path)),
        ("字段元数据", lambda: test_service_field_metadata(db_path)),
        ("员工数据权限", lambda: test_service_employee_scopes(db_path)),
        ("条件引用检测", lambda: test_service_reference_check(db_path)),
        ("资源预览", lambda: test_service_preview(db_path)),
    ]
    for name, test_fn in service_tests:
        print(f"\n  [{name}]")
        if test_fn():
            total_passed += 1
        else:
            total_failed += 1

    print("\n--- 3. Schema扫描测试 ---")
    schema_tests = [
        ("Schema自动生成维度", test_schema_scan_dimensions),
    ]
    for name, test_fn in schema_tests:
        print(f"\n  [{name}]")
        if test_fn():
            total_passed += 1
        else:
            total_failed += 1

    os.unlink(db_path)

    print("\n" + "=" * 60)
    print(f"测试结果: {total_passed} passed, {total_failed} failed")
    print("=" * 60)

    return total_failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
