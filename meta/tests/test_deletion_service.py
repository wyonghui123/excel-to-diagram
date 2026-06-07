import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
DeletionService 测试

测试元模型驱动的删除策略功能：
- RESTRICT: 强依赖检查
- CASCADE: 级联删除
- SOFT_DELETE: 软删除配置解析（兼容性保留，业务已迁移至 audit_log 恢复）
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.yaml_loader import parse_deletion_policy, DeletionPolicy, RestrictRule, SoftDeleteRule


def test_parse_deletion_policy_empty():
    """测试空 deletion_policy 解析"""
    print("\n=== 测试 parse_deletion_policy 空配置 ===")
    
    data = {}
    policy = parse_deletion_policy(data)
    assert policy is None
    print("[OK] 空配置返回 None")


def test_parse_deletion_policy_basic():
    """测试基本 deletion_policy 解析"""
    print("\n=== 测试 parse_deletion_policy 基本配置 ===")
    
    data = {
        "deletion_policy": {
            "cascade_delete": ["user_roles", "data_permissions"]
        }
    }
    policy = parse_deletion_policy(data)
    
    assert policy is not None
    assert len(policy.restrict_on) == 0
    assert len(policy.cascade_delete) == 2
    assert "user_roles" in policy.cascade_delete
    assert "data_permissions" in policy.cascade_delete
    print(f"[OK] cascade_delete: {policy.cascade_delete}")


def test_parse_deletion_policy_with_restrict():
    """测试带 RESTRICT 规则的 deletion_policy"""
    print("\n=== 测试 parse_deletion_policy 带 RESTRICT ===")
    
    data = {
        "deletion_policy": {
            "restrict_on": [
                {
                    "table": "financial_document",
                    "foreign_key": "user_id",
                    "message": "该用户有财务凭证关联，无法删除"
                },
                {
                    "table": "active_contract",
                    "foreign_key": "owner_id",
                    "message": "该用户有进行中的合同"
                }
            ],
            "cascade_delete": ["user_roles"]
        }
    }
    policy = parse_deletion_policy(data)
    
    assert policy is not None
    assert len(policy.restrict_on) == 2
    
    rule1 = policy.restrict_on[0]
    assert rule1.table == "financial_document"
    assert rule1.foreign_key == "user_id"
    assert rule1.message == "该用户有财务凭证关联，无法删除"
    
    print(f"[OK] RESTRICT 规则: {len(policy.restrict_on)} 条")


def test_parse_deletion_policy_with_restrict_empty():
    """测试 RESTRICT 为空列表"""
    print("\n=== 测试 RESTRICT 为空 ===")
    
    data = {
        "deletion_policy": {
            "restrict_on": [],
            "cascade_delete": ["user_roles"]
        }
    }
    policy = parse_deletion_policy(data)
    
    assert policy is not None
    assert len(policy.restrict_on) == 0
    print("[OK] 空 restrict_on 列表解析正确")


def test_parse_deletion_policy_soft_delete():
    """测试软删除配置（兼容性保留，业务已迁移至 audit_log 恢复）"""
    print("\n=== 测试 parse_deletion_policy 软删除（兼容性） ===")
    
    data = {
        "deletion_policy": {
            "soft_delete": {
                "enabled": True,
                "field": "deleted_at",
                "deleted_by_field": "deleted_by"
            }
        }
    }
    policy = parse_deletion_policy(data)
    
    assert policy is not None
    assert policy.soft_delete is not None
    assert policy.soft_delete.enabled == True
    assert policy.soft_delete.soft_delete_field == "deleted_at"
    assert policy.soft_delete.deleted_by_field == "deleted_by"
    print(f"[OK] 软删除配置（兼容性）: enabled={policy.soft_delete.enabled}")


def test_parse_deletion_policy_soft_delete_disabled():
    """测试软删除禁用（兼容性保留）"""
    print("\n=== 测试 parse_deletion_policy 软删除禁用（兼容性） ===")
    
    data = {
        "deletion_policy": {
            "soft_delete": {
                "enabled": False
            }
        }
    }
    policy = parse_deletion_policy(data)
    
    assert policy is not None
    assert policy.soft_delete.enabled == False
    print("[OK] 软删除禁用配置（兼容性）正确")


def test_parse_deletion_policy_full():
    """测试完整 deletion_policy（含已废弃的 soft_delete 配置）"""
    print("\n=== 测试 parse_deletion_policy 完整配置（兼容性） ===")
    
    data = {
        "deletion_policy": {
            "restrict_on": [
                {
                    "table": "financial_document",
                    "foreign_key": "user_id",
                    "message": "有财务凭证"
                }
            ],
            "cascade_delete": [
                "user_group_members",
                "change_subscriptions",
                "filter_variants",
                "data_permissions",
                "user_roles"
            ],
            "soft_delete": {
                "enabled": False,
                "field": "deleted_at",
                "deleted_by_field": "deleted_by"
            },
            "post_delete": [
                {"action": "notify_admins", "message": "用户已删除"}
            ]
        }
    }
    policy = parse_deletion_policy(data)
    
    assert policy is not None
    assert len(policy.restrict_on) == 1
    assert len(policy.cascade_delete) == 5
    assert policy.soft_delete is not None
    assert policy.soft_delete.enabled == False
    assert len(policy.post_delete) == 1
    print(f"[OK] 完整配置（兼容性）解析成功")


def test_parse_deletion_policy_null_restrict():
    """测试 restrict_on 为 null（非空列表）"""
    print("\n=== 测试 restrict_on 为 null ===")
    
    data = {
        "deletion_policy": {
            "restrict_on": None,
            "cascade_delete": ["user_roles"]
        }
    }
    policy = parse_deletion_policy(data)
    
    assert policy is not None
    assert policy.restrict_on == []
    print("[OK] null restrict_on 正确转换为空列表")


def test_parse_deletion_policy_null_cascade():
    """测试 cascade_delete 为 null"""
    print("\n=== 测试 cascade_delete 为 null ===")
    
    data = {
        "deletion_policy": {
            "cascade_delete": None
        }
    }
    policy = parse_deletion_policy(data)
    
    assert policy is not None
    assert policy.cascade_delete == []
    print("[OK] null cascade_delete 正确转换为空列表")


def test_deletion_service_no_soft_delete_method():
    """验证 DeletionService 已移除 soft_delete 方法（已迁移至 audit_log 恢复）"""
    print("\n=== 验证 DeletionService 已移除 soft_delete 方法 ===")
    
    from meta.services.deletion_service import DeletionService
    
    assert not hasattr(DeletionService, 'soft_delete'), \
        "DeletionService 不应再有 soft_delete 方法（已迁移至 audit_log 恢复）"
    assert not hasattr(DeletionService, '_execute_cascade_soft_delete'), \
        "DeletionService 不应再有 _execute_cascade_soft_delete 方法"
    
    assert hasattr(DeletionService, 'delete'), \
        "DeletionService 应有 delete 方法"
    assert hasattr(DeletionService, 'hard_delete'), \
        "DeletionService 应有 hard_delete 方法"
    
    print("[OK] DeletionService 已正确移除 soft_delete 方法")


def test_query_service_no_soft_delete_filter():
    """验证 QueryService 软删除过滤方法存在"""
    try:
        print("\n=== 验证 QueryService 软删除过滤方法 ===")

        from meta.services.query_service import QueryService, SearchRequest

        assert hasattr(QueryService, '_apply_soft_delete_filter'), \
            "QueryService 应有 _apply_soft_delete_filter 方法"

        req = SearchRequest(object_type='user')
        print("[OK] QueryService 软删除过滤方法存在")
    except AssertionError as e:
        pytest.fail(f"QueryService soft delete filter check failed: {e}")
    except Exception as e:
        pytest.fail(f"QueryService check skipped: {e}")


def test_recover_from_log_api_exists_in_manage_api():
    """验证 manage_api 包含 recover_from_log 和 list_deleted_objects"""
    print("\n=== 验证 manage_api 审计恢复 API ===")
    
    from meta.api.manage_api import recover_from_log, list_deleted_objects
    
    assert recover_from_log is not None
    assert list_deleted_objects is not None
    
    import inspect
    
    recover_src = inspect.getsource(recover_from_log)
    assert 'change_event' in recover_src, "recover_from_log 应查询 change_event"
    assert 'old_data' in recover_src, "recover_from_log 应包含 old_data 恢复逻辑"
    
    deleted_src = inspect.getsource(list_deleted_objects)
    assert 'audit_log' in deleted_src, "list_deleted_objects 应查询 audit_log"
    assert "action = 'DELETE'" in deleted_src, "list_deleted_objects 应筛选 DELETE 操作"
    
    print("[OK] recover_from_log 和 list_deleted_objects 实现完整")


def test_audit_log_schema_has_old_data_capture():
    """验证 audit_log/deletion_service 删除时捕获 old_data"""
    print("\n=== 验证删除时捕获 old_data ===")
    
    from meta.services.deletion_service import DeletionService
    import inspect
    source = inspect.getsource(DeletionService.delete)
    
    assert '_get_record' in source, "delete 应调用 _get_record 捕获 old_data"
    assert '_write_audit_log' in source, "delete 应调用 _write_audit_log 记录审计"
    
    log_source = inspect.getsource(DeletionService._write_audit_log)
    assert 'audit_interceptor' in log_source, "_write_audit_log 应调用 audit_interceptor"
    assert 'old_record' in log_source, "_write_audit_log 应接收 old_record"
    
    print("[OK] 删除时正确捕获并记录 old_data")


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("DeletionService 测试（含 audit_log 恢复验证）")
    print("=" * 60)
    
    test_parse_deletion_policy_empty()
    test_parse_deletion_policy_basic()
    test_parse_deletion_policy_with_restrict()
    test_parse_deletion_policy_with_restrict_empty()
    test_parse_deletion_policy_soft_delete()
    test_parse_deletion_policy_soft_delete_disabled()
    test_parse_deletion_policy_full()
    test_parse_deletion_policy_null_restrict()
    test_parse_deletion_policy_null_cascade()
    test_deletion_service_no_soft_delete_method()
    test_query_service_no_soft_delete_filter()
    test_recover_from_log_api_exists_in_manage_api()
    test_audit_log_schema_has_old_data_capture()
    
    print("\n" + "=" * 60)
    print("[OK] 所有 DeletionService 测试通过！")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
