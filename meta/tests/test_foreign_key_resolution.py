import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
外键解析功能测试

测试 _resolve_foreign_keys 方法的各种场景
"""

import os
import sys
import tempfile
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta import get_meta_object, registry
from meta.core.datasource import DataSource
from meta.core.sql_adapters import SQLiteAdapter
from meta.core.action_executor import ActionExecutor, ActionRegistry
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
            name TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER,
            code TEXT,
            name TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE sub_domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER,
            domain_id INTEGER,
            code TEXT,
            name TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE service_modules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER,
            sub_domain_id INTEGER,
            code TEXT,
            name TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE business_objects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER,
            service_module_id INTEGER,
            code TEXT,
            name TEXT
        )
    ''')

    conn.commit()
    conn.close()

    return db_file


def test_01_resolve_parent_by_business_key():
    """测试通过业务键解析父对象"""
    print("\n[TEST 01] 测试通过业务键解析父对象")

    db_file = setup_test_db()
    try:
        ds = SQLiteAdapter()
        ds.connect(path=db_file)
        executor = ActionExecutor(ds)

        # 创建版本
        ds.insert('versions', {'id': 1, 'code': 'V1', 'name': '版本1'})

        # 创建领域
        ds.insert('domains', {'id': 1, 'version_id': 1, 'code': 'FINANCE', 'name': '财务'})

        # 创建子领域，使用 domain_code 而非 domain_id
        sub_domain = get_meta_object('sub_domain')
        assert sub_domain is not None, "sub_domain meta object not found in registry"
        data = {
            'version_id': 1,
            'domain_code': 'FINANCE',
            'code': 'ACCOUNTING',
            'name': '会计'
        }

        result = executor._resolve_foreign_keys(sub_domain, data)

        assert 'domain_id' in result, "domain_id 应该被解析"
        assert result['domain_id'] == 1, f"domain_id 应该为 1，实际为 {result.get('domain_id')}"
        print("  [OK] 通过业务键解析父对象成功")

        ds.disconnect()

    finally:
        try:
            os.unlink(db_file)
        except:
            pass


def test_02_resolve_parent_not_found():
    """测试父对象不存在时的错误处理"""
    print("\n[TEST 02] 测试父对象不存在时的错误处理")

    db_file = setup_test_db()
    try:
        ds = SQLiteAdapter()
        ds.connect(path=db_file)
        executor = ActionExecutor(ds)

        # 创建版本
        ds.insert('versions', {'id': 1, 'code': 'V1', 'name': '版本1'})

        # 创建子领域，使用不存在的 domain_code
        sub_domain = get_meta_object('sub_domain')
        assert sub_domain is not None, "sub_domain meta object not found in registry"
        data = {
            'version_id': 1,
            'domain_code': 'NON_EXISTENT',
            'code': 'ACCOUNTING',
            'name': '会计'
        }

        try:
            executor._resolve_foreign_keys(sub_domain, data)
            assert False, "应该抛出 ValueError"
        except ValueError as e:
            assert '领域' in str(e), f"错误信息应包含 '领域'，实际为: {e}"
            assert 'NON_EXISTENT' in str(e), f"错误信息应包含业务键，实际为: {e}"
            print(f"  [OK] 正确抛出错误: {e}")

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
        executor = ActionExecutor(ds)

        # 创建两个版本
        ds.insert('versions', {'id': 1, 'code': 'V1', 'name': '版本1'})
        ds.insert('versions', {'id': 2, 'code': 'V2', 'name': '版本2'})

        # 在版本1创建领域
        ds.insert('domains', {'id': 1, 'version_id': 1, 'code': 'FINANCE', 'name': '财务'})

        # 在版本2创建同名领域
        ds.insert('domains', {'id': 2, 'version_id': 2, 'code': 'FINANCE', 'name': '财务2'})

        # 在版本1创建子领域，应该解析到版本1的领域
        sub_domain = get_meta_object('sub_domain')
        assert sub_domain is not None, "sub_domain meta object not found in registry"
        data = {
            'version_id': 1,
            'domain_code': 'FINANCE',
            'code': 'ACCOUNTING',
            'name': '会计'
        }

        result = executor._resolve_foreign_keys(sub_domain, data)
        assert result['domain_id'] == 1, f"版本1应该解析到 domain_id=1，实际为 {result.get('domain_id')}"
        print("  [OK] 版本隔离正确，解析到正确版本的父对象")

        # 在版本2创建子领域，应该解析到版本2的领域
        data2 = {
            'version_id': 2,
            'domain_code': 'FINANCE',
            'code': 'ACCOUNTING',
            'name': '会计'
        }

        result2 = executor._resolve_foreign_keys(sub_domain, data2)
        assert result2['domain_id'] == 2, f"版本2应该解析到 domain_id=2，实际为 {result2.get('domain_id')}"
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
        executor = ActionExecutor(ds)

        # 创建版本
        ds.insert('versions', {'id': 1, 'code': 'V1', 'name': '版本1'})

        # 创建领域
        ds.insert('domains', {'id': 1, 'version_id': 1, 'code': 'FINANCE', 'name': '财务'})

        # 创建子领域
        ds.insert('sub_domains', {'id': 1, 'version_id': 1, 'domain_id': 1, 'code': 'ACCOUNTING', 'name': '会计'})

        # 创建服务模块，使用 sub_domain_code
        service_module = get_meta_object('service_module')
        assert service_module is not None, "service_module meta object not found in registry"
        data = {
            'version_id': 1,
            'sub_domain_code': 'ACCOUNTING',
            'code': 'GL',
            'name': '总账'
        }

        result = executor._resolve_foreign_keys(service_module, data)
        assert result['sub_domain_id'] == 1, f"sub_domain_id 应该为 1，实际为 {result.get('sub_domain_id')}"
        print("  [OK] 多层级外键解析成功")

        ds.disconnect()

    finally:
        try:
            os.unlink(db_file)
        except:
            pass


def test_05_resolve_with_existing_id():
    """测试已有ID时不覆盖"""
    print("\n[TEST 05] 测试已有ID时不覆盖")

    db_file = setup_test_db()
    try:
        ds = SQLiteAdapter()
        ds.connect(path=db_file)
        executor = ActionExecutor(ds)

        # 创建版本
        ds.insert('versions', {'id': 1, 'code': 'V1', 'name': '版本1'})

        # 创建两个领域
        ds.insert('domains', {'id': 1, 'version_id': 1, 'code': 'FINANCE', 'name': '财务'})
        ds.insert('domains', {'id': 2, 'version_id': 1, 'code': 'HR', 'name': '人力资源'})

        # 创建子领域，同时提供 domain_id 和 domain_code
        # 应该保留已有的 domain_id，不覆盖
        sub_domain = get_meta_object('sub_domain')
        assert sub_domain is not None, "sub_domain meta object not found in registry"
        data = {
            'version_id': 1,
            'domain_id': 2,  # 已有ID
            'domain_code': 'FINANCE',  # 不同的业务键
            'code': 'ACCOUNTING',
            'name': '会计'
        }

        result = executor._resolve_foreign_keys(sub_domain, data)
        # 已有ID时不应该被覆盖
        assert result['domain_id'] == 2, f"已有ID不应该被覆盖，实际为 {result.get('domain_id')}"
        print("  [OK] 已有ID正确保留，未被覆盖")

        ds.disconnect()

    finally:
        try:
            os.unlink(db_file)
        except:
            pass


def test_06_schema_has_resolve_semantics():
    """测试 Schema 包含外键解析语义"""
    print("\n[TEST 06] 测试 Schema 包含外键解析语义")

    # 检查 domain.yaml
    domain = get_meta_object('domain')
    assert domain is not None, "domain not found in registry"
    version_id_field = domain.get_field('version_id')
    assert version_id_field is not None, "field not found on domain"
    resolve_from = getattr(version_id_field.semantics, 'resolve_from_field', None)
    resolve_to = getattr(version_id_field.semantics, 'resolve_to_object', None)
    assert resolve_from == 'version_code', f"version_id.resolve_from_field 应为 'version_code'，实际为 {resolve_from}"
    assert resolve_to == 'version', f"version_id.resolve_to_object 应为 'version'，实际为 {resolve_to}"
    print("  [OK] domain.yaml 包含正确的外键解析语义")

    # 检查 sub_domain.yaml
    sub_domain = get_meta_object('sub_domain')
    assert sub_domain is not None, "sub_domain not found in registry"
    domain_id_field = sub_domain.get_field('domain_id')
    assert domain_id_field is not None, "field not found on sub_domain"
    resolve_from = getattr(domain_id_field.semantics, 'resolve_from_field', None)
    resolve_to = getattr(domain_id_field.semantics, 'resolve_to_object', None)
    assert resolve_from == 'domain_code', f"domain_id.resolve_from_field 应为 'domain_code'，实际为 {resolve_from}"
    assert resolve_to == 'domain', f"domain_id.resolve_to_object 应为 'domain'，实际为 {resolve_to}"
    print("  [OK] sub_domain.yaml 包含正确的外键解析语义")

    # 检查 service_module.yaml
    service_module = get_meta_object('service_module')
    assert service_module is not None, "service_module not found in registry"
    sub_domain_id_field = service_module.get_field('sub_domain_id')
    assert sub_domain_id_field is not None, "field not found on service_module"
    resolve_from = getattr(sub_domain_id_field.semantics, 'resolve_from_field', None)
    resolve_to = getattr(sub_domain_id_field.semantics, 'resolve_to_object', None)
    assert resolve_from == 'sub_domain_code', f"sub_domain_id.resolve_from_field 应为 'sub_domain_code'，实际为 {resolve_from}"
    assert resolve_to == 'sub_domain', f"sub_domain_id.resolve_to_object 应为 'sub_domain'，实际为 {resolve_to}"
    print("  [OK] service_module.yaml 包含正确的外键解析语义")

    # 检查 business_object.yaml
    business_object = get_meta_object('business_object')
    assert business_object is not None, "business_object not found in registry"
    service_module_id_field = business_object.get_field('service_module_id')
    assert service_module_id_field is not None, "field not found on business_object"
    resolve_from = getattr(service_module_id_field.semantics, 'resolve_from_field', None)
    resolve_to = getattr(service_module_id_field.semantics, 'resolve_to_object', None)
    assert resolve_from == 'service_module_code', f"service_module_id.resolve_from_field 应为 'service_module_code'，实际为 {resolve_from}"
    assert resolve_to == 'service_module', f"service_module_id.resolve_to_object 应为 'service_module'，实际为 {resolve_to}"
    print("  [OK] business_object.yaml 包含正确的外键解析语义")


def test_07_schema_has_parent_code_fields():
    """测试 Schema 包含父对象业务键字段"""
    print("\n[TEST 07] 测试 Schema 包含父对象业务键字段")

    # 检查 domain.yaml 有 version_code 字段
    domain = get_meta_object('domain')
    assert domain is not None, "domain not found in registry"
    version_code_field = domain.get_field('version_code')
    assert version_code_field is not None, "field not found on domain"
    print("  [OK] domain.yaml 包含 version_code 字段")

    # 检查 sub_domain.yaml 有 domain_code 字段
    sub_domain = get_meta_object('sub_domain')
    assert sub_domain is not None, "sub_domain not found in registry"
    domain_code_field = sub_domain.get_field('domain_code')
    assert domain_code_field is not None, "field not found on sub_domain"
    print("  [OK] sub_domain.yaml 包含 domain_code 字段")

    # 检查 service_module.yaml 有 sub_domain_code 字段
    service_module = get_meta_object('service_module')
    assert service_module is not None, "service_module not found in registry"
    sub_domain_code_field = service_module.get_field('sub_domain_code')
    assert sub_domain_code_field is not None, "field not found on service_module"
    print("  [OK] service_module.yaml 包含 sub_domain_code 字段")

    # 检查 business_object.yaml 有 service_module_code 字段
    business_object = get_meta_object('business_object')
    assert business_object is not None, "business_object not found in registry"
    service_module_code_field = business_object.get_field('service_module_code')
    assert service_module_code_field is not None, "field not found on business_object"
    print("  [OK] business_object.yaml 包含 service_module_code 字段")


def run_all_tests():
    """运行所有测试"""
    print("=" * 70)
    print("  外键解析功能测试")
    print("=" * 70)

    import meta
    meta._yaml_loaded = False
    meta._load_from_yaml()

    tests = [
        test_01_resolve_parent_by_business_key,
        test_02_resolve_parent_not_found,
        test_03_resolve_with_version_isolation,
        test_04_resolve_multiple_levels,
        test_05_resolve_with_existing_id,
        test_06_schema_has_resolve_semantics,
        test_07_schema_has_parent_code_fields,
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
