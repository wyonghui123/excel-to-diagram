import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
StructuredLogger 与 AuditInterceptor 集成测试

验证元数据驱动的审计日志系统完整流程。
"""

import sys
import os
import tempfile
import sqlite3

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)


def test_structured_logger_import():
    """测试 StructuredLogger 可以正确导入"""
    print("\n=== test_structured_logger_import ===")
    
    try:
        from meta.services.structured_logger import StructuredLogger, LogEntry
        from meta.enums.log_category import LogCategory
        from meta.enums.log_level import LogLevel
        print("[PASS] StructuredLogger 和相关模块可以正确导入")
    except ImportError as e:
        print(f"[FAIL] 导入失败: {e}")
        raise


def test_audit_interceptor_with_structured_logger():
    """测试 AuditInterceptor 使用 StructuredLogger"""
    print("\n=== test_audit_interceptor_with_structured_logger ===")
    
    from meta.core.interceptors.audit_interceptor import AuditInterceptor
    from meta.services.structured_logger import StructuredLogger
    
    structured_logger = StructuredLogger()
    interceptor = AuditInterceptor(structured_logger=structured_logger)
    
    assert interceptor._structured_logger is structured_logger
    print("[PASS] AuditInterceptor 正确使用 StructuredLogger")


def test_log_entry_creation():
    """测试 LogEntry 创建"""
    print("\n=== test_log_entry_creation ===")
    
    from meta.services.structured_logger import LogEntry
    from meta.enums.log_category import LogCategory
    from meta.enums.log_level import LogLevel
    
    entry = LogEntry(
        category=LogCategory.BUSINESS,
        level=LogLevel.INFO,
        action='CREATE',
        object_type='user',
        object_id=123,
        user_id=1,
        user_name='admin'
    )
    
    assert entry.category == LogCategory.BUSINESS
    assert entry.level == LogLevel.INFO
    assert entry.action == 'CREATE'
    assert entry.object_type == 'user'
    assert entry.object_id == 123
    print("[PASS] LogEntry 创建正确")


def test_structured_logger_log_business():
    """测试 StructuredLogger.log_business 方法"""
    print("\n=== test_structured_logger_log_business ===")
    
    from meta.services.structured_logger import StructuredLogger
    
    logger = StructuredLogger()
    
    result = logger.log_business(
        action='UPDATE',
        object_type='user',
        object_id=123,
        user_id=1,
        user_name='admin',
        old_data={'email': 'old@example.com'},
        new_data={'email': 'new@example.com'},
        field_name='email'
    )
    
    stats = logger.get_stats()
    assert stats['total_submitted'] == 1
    print(f"[PASS] StructuredLogger.log_business 工作正常，统计: {stats}")


def test_log_category_enum():
    """测试 LogCategory 枚举"""
    print("\n=== test_log_category_enum ===")
    
    from meta.enums.log_category import LogCategory
    
    assert LogCategory.BUSINESS.value == 'business'
    assert LogCategory.SECURITY.value == 'security'
    assert LogCategory.OPERATION.value == 'operation'
    assert LogCategory.PERFORMANCE.value == 'performance'
    assert LogCategory.SYSTEM.value == 'system'
    
    assert LogCategory.from_string('business') == LogCategory.BUSINESS
    assert LogCategory.from_string('SECURITY') == LogCategory.SECURITY
    print("[PASS] LogCategory 枚举工作正常")


def test_log_level_enum():
    """测试 LogLevel 枚举"""
    print("\n=== test_log_level_enum ===")
    
    from meta.enums.log_level import LogLevel
    
    assert LogLevel.DEBUG.value == 'DEBUG'
    assert LogLevel.INFO.value == 'INFO'
    assert LogLevel.WARNING.value == 'WARNING'
    assert LogLevel.ERROR.value == 'ERROR'
    assert LogLevel.CRITICAL.value == 'CRITICAL'
    
    assert LogLevel.from_string('info') == LogLevel.INFO
    assert LogLevel.from_string('WARNING') == LogLevel.WARNING
    print("[PASS] LogLevel 枚举工作正常")


def test_audit_log_yaml_ui_config():
    """测试 audit_log.yaml UI 配置"""
    print("\n=== test_audit_log_yaml_ui_config ===")
    
    import yaml
    
    yaml_path = os.path.join(PROJECT_ROOT, 'meta', 'schemas', 'audit_log.yaml')
    
    with open(yaml_path, 'r', encoding='utf-8') as f:
        schema = yaml.safe_load(f)
    
    assert 'ui_view_config' in schema, "缺少 ui_view_config"
    assert 'list' in schema['ui_view_config'], "缺少 list 配置"
    assert 'columns' in schema['ui_view_config']['list'], "缺少 columns 配置"
    
    columns = schema['ui_view_config']['list']['columns']
    column_fields = [col['field'] for col in columns]
    
    assert 'log_category' in column_fields, "缺少 log_category 列"
    assert 'log_level' in column_fields, "缺少 log_level 列"
    
    for col in columns:
        if col['field'] == 'log_category':
            assert col.get('filterable') == True, "log_category 应该可过滤"
            assert col.get('sortable') == True, "log_category 应该可排序"
            assert 'filter_options' in col, "log_category 应该有 filter_options"
        if col['field'] == 'log_level':
            assert col.get('filterable') == True, "log_level 应该可过滤"
            assert col.get('sortable') == True, "log_level 应该可排序"
            assert 'filter_options' in col, "log_level 应该有 filter_options"
    
    print("[PASS] audit_log.yaml UI 配置正确，过滤和排序在列配置中定义")


def test_metadata_driven_filtering():
    """测试元数据驱动的过滤配置"""
    print("\n=== test_metadata_driven_filtering ===")
    
    import yaml
    
    yaml_path = os.path.join(PROJECT_ROOT, 'meta', 'schemas', 'audit_log.yaml')
    
    with open(yaml_path, 'r', encoding='utf-8') as f:
        schema = yaml.safe_load(f)
    
    ui_config = schema['ui_view_config']
    
    assert 'filter' not in ui_config or not ui_config.get('filter'), \
        "不应该有单独的 filter 区域配置"
    
    list_config = ui_config['list']
    columns = list_config['columns']
    
    filterable_columns = [col for col in columns if col.get('filterable')]
    assert len(filterable_columns) > 0, "应该有可过滤的列"
    
    sortable_columns = [col for col in columns if col.get('sortable')]
    assert len(sortable_columns) > 0, "应该有可排序的列"
    
    print(f"[PASS] 元数据驱动过滤配置正确，{len(filterable_columns)} 个可过滤列，{len(sortable_columns)} 个可排序列")


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("StructuredLogger 与 AuditInterceptor 集成测试")
    print("=" * 60)
    
    tests = [
        test_structured_logger_import,
        test_audit_interceptor_with_structured_logger,
        test_log_entry_creation,
        test_structured_logger_log_business,
        test_log_category_enum,
        test_log_level_enum,
        test_audit_log_yaml_ui_config,
        test_metadata_driven_filtering,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"[ERROR] {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"结果: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
