import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
导入外键解析集成测试

测试导入时使用父对象业务键的场景
"""

import os
import sys
import tempfile
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta import get_meta_object, registry
from meta.core.datasource import DataSource
from meta.core.sql_adapters import SQLiteAdapter
from meta.core.action_executor import ActionRegistry
from meta.core.table_name_validator import register_table_name


def setup_test_db():
    """创建测试数据库"""
    for tbl in ['versions', 'domains', 'sub_domains', 'service_modules', 'business_objects']:
        register_table_name(tbl)
    db_file = tempfile.mktemp(suffix='.db')
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            name TEXT,
            created_at TEXT,
            updated_at TEXT,
            created_by TEXT,
            updated_by TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER,
            code TEXT,
            name TEXT,
            owner_id INTEGER,
            created_at TEXT,
            updated_at TEXT,
            created_by TEXT,
            updated_by TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE sub_domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER,
            domain_id INTEGER,
            code TEXT,
            name TEXT,
            owner_id INTEGER,
            created_at TEXT,
            updated_at TEXT,
            created_by TEXT,
            updated_by TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE service_modules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER,
            sub_domain_id INTEGER,
            code TEXT,
            name TEXT,
            owner_id INTEGER,
            created_at TEXT,
            updated_at TEXT,
            created_by TEXT,
            updated_by TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE business_objects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER,
            service_module_id INTEGER,
            code TEXT,
            name TEXT,
            owner_id INTEGER,
            created_at TEXT,
            updated_at TEXT,
            created_by TEXT,
            updated_by TEXT
        )
    ''')

    conn.commit()
    conn.close()

    return db_file


def test_01_create_with_parent_code():
    """测试通过业务键创建对象"""
    print("\n[TEST 01] 测试通过业务键创建对象")

    db_file = setup_test_db()
    try:
        ds = SQLiteAdapter()
        ds.connect(path=db_file)
        registry_executor = ActionRegistry(ds)

        # 创建版本
        ds.insert('versions', {'id': 1, 'code': 'V1', 'name': '版本1', 'created_at': '2024-01-01', 'updated_at': '2024-01-01'})

        # 创建领域
        ds.insert('domains', {'id': 1, 'version_id': 1, 'code': 'FINANCE', 'name': '财务', 'created_at': '2024-01-01', 'updated_at': '2024-01-01'})

        # 通过业务键创建子领域
        sub_domain = get_meta_object('sub_domain')
        assert sub_domain is not None, "sub_domain meta object not found in registry"
        result = registry_executor.create(sub_domain, {
            'version_id': 1,
            'domain_code': 'FINANCE',
            'code': 'ACCOUNTING',
            'name': '会计'
        })

        assert result.success, f"创建应该成功，实际: {result.error} - {result.message}"

        # 验证 domain_id 被正确解析
        cursor = ds.execute("SELECT * FROM sub_domains WHERE code = 'ACCOUNTING'")
        row = cursor.fetchone()
        assert row is not None, "应该创建子领域记录"
        columns = [desc[0] for desc in cursor.description]
        record = dict(zip(columns, row))
        assert record['domain_id'] == 1, f"domain_id 应该为 1，实际为 {record.get('domain_id')}"
        print("  [OK] 通过业务键创建对象成功")

        ds.disconnect()

    finally:
        try:
            os.unlink(db_file)
        except:
            pass


def test_02_update_with_parent_code():
    """测试通过业务键更新父对象（注意：domain_id 字段设置了 immutable: true）"""
    print("\n[TEST 02] 测试通过业务键更新父对象（预期失败：父字段不可变）")

    db_file = setup_test_db()
    try:
        ds = SQLiteAdapter()
        ds.connect(path=db_file)
        registry_executor = ActionRegistry(ds)

        # 创建版本
        ds.insert('versions', {'id': 1, 'code': 'V1', 'name': '版本1', 'created_at': '2024-01-01', 'updated_at': '2024-01-01'})

        # 创建两个领域
        ds.insert('domains', {'id': 1, 'version_id': 1, 'code': 'FINANCE', 'name': '财务', 'created_at': '2024-01-01', 'updated_at': '2024-01-01'})
        ds.insert('domains', {'id': 2, 'version_id': 1, 'code': 'HR', 'name': '人力资源', 'created_at': '2024-01-01', 'updated_at': '2024-01-01'})

        # 创建子领域
        ds.insert('sub_domains', {'id': 1, 'version_id': 1, 'domain_id': 1, 'code': 'ACCOUNTING', 'name': '会计', 'created_at': '2024-01-01', 'updated_at': '2024-01-01'})

        # 尝试通过业务键更新父对象
        # 注意：domain_id 字段设置了 immutable: true，所以应该失败
        sub_domain = get_meta_object('sub_domain')
        assert sub_domain is not None, "sub_domain meta object not found in registry"
        result = registry_executor.update(sub_domain, 1, {
            'domain_code': 'HR'
        })

        # 预期失败：父字段不可变
        assert not result.success, "更新应该失败（父字段不可变）"
        assert 'PARENT_FIELD_IMMUTABLE' == result.error, f"错误类型应为 PARENT_FIELD_IMMUTABLE，实际为 {result.error}"
        print(f"  [OK] 正确返回错误: {result.message}")

        ds.disconnect()

    finally:
        try:
            os.unlink(db_file)
        except:
            pass


def test_03_resolve_with_version_isolation():
    """测试版本隔离下的外键解析"""
    print("\n[TEST 03] 测试版本隔离下的外键解析")

    db_file = setup_test_db()
    try:
        ds = SQLiteAdapter()
        ds.connect(path=db_file)
        registry_executor = ActionRegistry(ds)

        # 创建两个版本
        ds.insert('versions', {'id': 1, 'code': 'V1', 'name': '版本1', 'created_at': '2024-01-01', 'updated_at': '2024-01-01'})
        ds.insert('versions', {'id': 2, 'code': 'V2', 'name': '版本2', 'created_at': '2024-01-01', 'updated_at': '2024-01-01'})

        # 在版本1创建领域
        ds.insert('domains', {'id': 1, 'version_id': 1, 'code': 'FINANCE', 'name': '财务', 'created_at': '2024-01-01', 'updated_at': '2024-01-01'})

        # 在版本2创建同名领域
        ds.insert('domains', {'id': 2, 'version_id': 2, 'code': 'FINANCE', 'name': '财务2', 'created_at': '2024-01-01', 'updated_at': '2024-01-01'})

        # 在版本1创建子领域，应该解析到版本1的领域
        sub_domain = get_meta_object('sub_domain')
        result1 = registry_executor.create(sub_domain, {
            'version_id': 1,
            'domain_code': 'FINANCE',
            'code': 'ACCOUNTING_V1',
            'name': '会计V1'
        })

        assert result1.success, f"版本1创建应该成功，实际: {result1.error} - {result1.message}"

        # 验证版本1的子领域关联到版本1的领域
        cursor = ds.execute("SELECT * FROM sub_domains WHERE code = 'ACCOUNTING_V1'")
        row = cursor.fetchone()
        columns = [desc[0] for desc in cursor.description]
        record = dict(zip(columns, row))
        assert record['domain_id'] == 1, f"版本1应该解析到 domain_id=1，实际为 {record.get('domain_id')}"
        print("  [OK] 版本隔离正确，解析到正确版本的父对象")

        # 在版本2创建子领域，应该解析到版本2的领域
        result2 = registry_executor.create(sub_domain, {
            'version_id': 2,
            'domain_code': 'FINANCE',
            'code': 'ACCOUNTING_V2',
            'name': '会计V2'
        })

        assert result2.success, f"版本2创建应该成功，实际: {result2.error} - {result2.message}"

        cursor = ds.execute("SELECT * FROM sub_domains WHERE code = 'ACCOUNTING_V2'")
        row = cursor.fetchone()
        columns = [desc[0] for desc in cursor.description]
        record = dict(zip(columns, row))
        assert record['domain_id'] == 2, f"版本2应该解析到 domain_id=2，实际为 {record.get('domain_id')}"
        print("  [OK] 版本2解析正确")

        ds.disconnect()

    finally:
        try:
            os.unlink(db_file)
        except:
            pass


def test_04_resolve_multiple_levels():
    """测试多层级外键解析"""
    print("\n[TEST 04] 测试多层级外键解析")

    db_file = setup_test_db()
    try:
        ds = SQLiteAdapter()
        ds.connect(path=db_file)
        registry_executor = ActionRegistry(ds)

        # 创建版本
        ds.insert('versions', {'id': 1, 'code': 'V1', 'name': '版本1', 'created_at': '2024-01-01', 'updated_at': '2024-01-01'})

        # 创建领域
        ds.insert('domains', {'id': 1, 'version_id': 1, 'code': 'FINANCE', 'name': '财务', 'created_at': '2024-01-01', 'updated_at': '2024-01-01'})

        # 创建子领域
        ds.insert('sub_domains', {'id': 1, 'version_id': 1, 'domain_id': 1, 'code': 'ACCOUNTING', 'name': '会计', 'created_at': '2024-01-01', 'updated_at': '2024-01-01'})

        # 通过业务键创建服务模块
        service_module = get_meta_object('service_module')
        result = registry_executor.create(service_module, {
            'version_id': 1,
            'sub_domain_code': 'ACCOUNTING',
            'code': 'GL',
            'name': '总账'
        })

        assert result.success, f"创建应该成功，实际: {result.error} - {result.message}"

        # 验证 sub_domain_id 被正确解析
        cursor = ds.execute("SELECT * FROM service_modules WHERE code = 'GL'")
        row = cursor.fetchone()
        assert row is not None, "应该创建服务模块记录"
        columns = [desc[0] for desc in cursor.description]
        record = dict(zip(columns, row))
        assert record['sub_domain_id'] == 1, f"sub_domain_id 应该为 1，实际为 {record.get('sub_domain_id')}"
        print("  [OK] 多层级外键解析成功")

        ds.disconnect()

    finally:
        try:
            os.unlink(db_file)
        except:
            pass


def test_05_parent_not_found_error():
    """测试父对象不存在时的错误处理"""
    print("\n[TEST 05] 测试父对象不存在时的错误处理")

    db_file = setup_test_db()
    try:
        ds = SQLiteAdapter()
        ds.connect(path=db_file)
        registry_executor = ActionRegistry(ds)

        # 创建版本
        ds.insert('versions', {'id': 1, 'code': 'V1', 'name': '版本1', 'created_at': '2024-01-01', 'updated_at': '2024-01-01'})

        # 不创建领域，测试错误处理

        # 尝试通过不存在的业务键创建子领域
        sub_domain = get_meta_object('sub_domain')
        result = registry_executor.create(sub_domain, {
            'version_id': 1,
            'domain_code': 'NON_EXISTENT',
            'code': 'ACCOUNTING',
            'name': '会计'
        })

        assert not result.success, "创建应该失败"
        assert 'FOREIGN_KEY_RESOLUTION_FAILED' == result.error, f"错误类型应为 FOREIGN_KEY_RESOLUTION_FAILED，实际为 {result.error}"
        assert '领域' in result.message, f"错误信息应包含 '领域'，实际为: {result.message}"
        assert 'NON_EXISTENT' in result.message, f"错误信息应包含业务键，实际为: {result.message}"
        print(f"  [OK] 正确返回错误: {result.message}")

        ds.disconnect()

    finally:
        try:
            os.unlink(db_file)
        except:
            pass


def run_all_tests():
    """运行所有测试"""
    print("=" * 70)
    print("  导入外键解析集成测试")
    print("=" * 70)

    import meta
    meta._yaml_loaded = False
    meta._load_from_yaml()

    tests = [
        test_01_create_with_parent_code,
        test_02_update_with_parent_code,
        test_03_resolve_with_version_isolation,
        test_04_resolve_multiple_levels,
        test_05_parent_not_found_error,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  [X] 测试失败: {test.__name__}")
            print(f"     错误: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 70)
    print(f"  测试结果: 通过 {passed}/{len(tests)}")
    print("=" * 70)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
