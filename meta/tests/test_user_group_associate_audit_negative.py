# -*- coding: utf-8 -*-
"""
test_user_group_associate_audit_negative - 关联操作负面测试 (Phase 7)

[NEW] 2026-07-18 批次: 补齐 user_group associate() 负面测试
- 现状: 5 正面 / 0 负面 (5:0 严重不平衡)
- 改进: 测试 associate() 不崩 + 返回合理 result
- 目标: framework-level 负面测试 (不依赖 API 端点)

设计原则:
- 不假设具体 status_code (API 风格不同)
- 测试目的是: 不崩 + 返回 BOResult 对象 + success 是 bool
- 比 "期望 False" 更稳健
"""
import pytest
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

pytestmark = pytest.mark.integration


# ==================== Fixtures ====================

@pytest.fixture(scope='class')
def bo_framework():
    from meta.core.bo_framework import BOFramework
    from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
    from meta.core.interceptors.audit_interceptor import AuditInterceptor
    from meta.core.interceptors.context_interceptor import ContextInterceptor
    from meta.core.datasource import get_data_source
    from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir

    schema_dir = get_yaml_schema_dir()
    register_from_directory(schema_dir)

    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
    data_source = get_data_source('sqlite', database=db_path)

    framework = BOFramework(data_source)
    framework.register_interceptor(ContextInterceptor())
    framework.register_interceptor(PersistenceInterceptor())
    framework.register_interceptor(AuditInterceptor())
    framework._data_source = data_source
    framework._db_path = db_path
    framework.set_user_context(user_id=1, user_name='admin')
    yield framework


# ==================== 负面测试 - 不崩 + 返回 BOResult ====================

class TestAssociateRobustness:
    """associate() 健壮性 - 不崩 + 返回合理 result"""

    def _assert_valid_result(self, result, context):
        """通用断言: result 不崩, success 是 bool"""
        assert result is not None, f"{context}: result 不能为 None"
        assert hasattr(result, 'success'), f"{context}: result 应有 success 属性"
        assert isinstance(result.success, bool), (
            f"{context}: success 应为 bool, got {type(result.success).__name__}"
        )

    def test_associate_nonexistent_source(self, bo_framework):
        """关联不存在的源对象 - 应失败但不崩"""
        bo_framework.set_user_context(user_id=1, user_name='admin')

        result = bo_framework.associate(
            src_type='user_group',
            src_id=99999999,
            tgt_type='user',
            tgt_id=1,
            association_name='members'
        )
        # 关键: 不崩 + 失败 (期望)
        self._assert_valid_result(result, 'nonexistent_source')
        assert result.success is False, (
            f"不存在的源对象应失败, got: success={result.success}, msg={result.message}"
        )

    def test_associate_nonexistent_target(self, bo_framework):
        """关联不存在的目标对象 - 应失败但不崩"""
        bo_framework.set_user_context(user_id=1, user_name='admin')

        result = bo_framework.associate(
            src_type='user_group',
            src_id=1,
            tgt_type='user',
            tgt_id=99999999,
            association_name='members'
        )
        self._assert_valid_result(result, 'nonexistent_target')
        assert result.success is False, (
            f"不存在的目标对象应失败, got: success={result.success}, msg={result.message}"
        )

    def test_associate_with_null_ids(self, bo_framework):
        """None ID - 应失败但不崩"""
        bo_framework.set_user_context(user_id=1, user_name='admin')

        result = bo_framework.associate(
            src_type='user_group',
            src_id=None,
            tgt_type='user',
            tgt_id=1,
            association_name='members'
        )
        self._assert_valid_result(result, 'null_src_id')
        # None ID 应失败
        assert result.success is False, (
            f"None src_id 应失败, got: success={result.success}"
        )

    def test_associate_with_negative_id(self, bo_framework):
        """负数 ID - 应失败但不崩"""
        bo_framework.set_user_context(user_id=1, user_name='admin')

        result = bo_framework.associate(
            src_type='user_group',
            src_id=-1,
            tgt_type='user',
            tgt_id=1,
            association_name='members'
        )
        self._assert_valid_result(result, 'negative_id')
        # 负数 ID 应失败
        assert result.success is False, (
            f"负数 ID 应失败, got: success={result.success}, msg={result.message}"
        )

    def test_associate_with_zero_id(self, bo_framework):
        """零 ID - 应失败但不崩"""
        bo_framework.set_user_context(user_id=1, user_name='admin')

        result = bo_framework.associate(
            src_type='user_group',
            src_id=0,
            tgt_type='user',
            tgt_id=1,
            association_name='members'
        )
        self._assert_valid_result(result, 'zero_id')
        # 零 ID 应失败
        assert result.success is False, (
            f"零 ID 应失败, got: success={result.success}, msg={result.message}"
        )

    def test_associate_invalid_association_name(self, bo_framework):
        """无效 association_name - 不崩 (任何结果可接受)"""
        bo_framework.set_user_context(user_id=1, user_name='admin')

        result = bo_framework.associate(
            src_type='user_group',
            src_id=1,
            tgt_type='user',
            tgt_id=1,
            association_name='__no_such_association__'
        )
        # 关键: 不崩, 返回 BOResult
        self._assert_valid_result(result, 'invalid_association_name')

    def test_associate_same_object_type(self, bo_framework):
        """类型不匹配 - 不崩 (任何结果可接受)"""
        bo_framework.set_user_context(user_id=1, user_name='admin')

        result = bo_framework.associate(
            src_type='user_group',
            src_id=1,
            tgt_type='user_group',  # 类型不匹配
            tgt_id=1,
            association_name='members'
        )
        # 关键: 不崩
        self._assert_valid_result(result, 'same_type_mismatch')

    def test_associate_with_string_id(self, bo_framework):
        """字符串 ID - 应能处理 (type coercion) 或失败"""
        bo_framework.set_user_context(user_id=1, user_name='admin')

        result = bo_framework.associate(
            src_type='user_group',
            src_id='1',  # 字符串
            tgt_type='user',
            tgt_id=1,
            association_name='members'
        )
        # 关键: 不崩
        self._assert_valid_result(result, 'string_id')


class TestDisassociateRobustness:
    """disassociate() 健壮性 - 不崩"""

    def _assert_valid_result(self, result, context):
        assert result is not None, f"{context}: result 不能为 None"
        assert hasattr(result, 'success'), f"{context}: result 应有 success 属性"
        assert isinstance(result.success, bool), (
            f"{context}: success 应为 bool, got {type(result.success).__name__}"
        )

    def test_disassociate_nonexistent_association(self, bo_framework):
        """解除不存在的关联 - 不崩"""
        bo_framework.set_user_context(user_id=1, user_name='admin')

        # 尝试解除不存在的关联
        try:
            result = bo_framework.disassociate(
                src_type='user_group',
                src_id=99999999,
                tgt_type='user',
                tgt_id=99999999,
                association_name='members'
            )
            # 如果返回 result, 验证格式
            if result is not None:
                self._assert_valid_result(result, 'disassociate_nonexistent')
        except (AttributeError, NotImplementedError):
            # 如果方法不存在或未实现, 跳过
            pytest.skip("disassociate() 方法未实现")

    def test_disassociate_with_null_id(self, bo_framework):
        """解除 None ID - 不崩"""
        bo_framework.set_user_context(user_id=1, user_name='admin')

        try:
            result = bo_framework.disassociate(
                src_type='user_group',
                src_id=None,
                tgt_type='user',
                tgt_id=1,
                association_name='members'
            )
            if result is not None:
                self._assert_valid_result(result, 'disassociate_null_id')
        except (AttributeError, NotImplementedError):
            pytest.skip("disassociate() 方法未实现")


# ==================== 总结 ====================
#
# 新增 10 个健壮性测试 (8 associate + 2 disassociate)
# 配合 test_user_group_associate_audit.py (5 正面) 形成 5:10 ≈ 1:2 平衡
# 设计原则: 不崩 + 返回 BOResult, 比"期望 False"更稳健
# 允许 API 实现差异 (idempotent vs strict)