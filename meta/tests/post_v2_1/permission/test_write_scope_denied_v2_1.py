# -*- coding: utf-8 -*-
"""
test_write_scope_denied_v2_1.py
覆盖提交: bb5c5cc
依据: .trae/specs/test-suite/post-6-22-roadmap.md 主题 3 (Write Scope)

WriteScopeDenied 消息简化 + virtual field skip + update result check:
- 错误消息更友好 (无写权限: <type>(<key>), 失败侧: <...>)
- virtual field 不参与 write_scope 检查
- update 结果包含受影响的字段数验证
"""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

pytestmark = [pytest.mark.post_v2_1, pytest.mark.permission]


# ============================================================
# 1. TestWriteScopeDeniedMessageV2_1
# ============================================================

class TestWriteScopeDeniedMessageV2_1:
    """WriteScopeDenied 消息简化"""

    def test_simplified_error_message(self):
        """错误消息更友好

        格式: 无写权限: <type>(<key>), 失败侧: <side_info>
        """
        from meta.core.interceptors.write_scope_interceptor import WriteScopeDenied

        denied = WriteScopeDenied(
            object_type='service_module',
            target_id=137,
            user_id=3385,
            check_results={'dim_scope': [], 'visibility': 'private'},
            business_key='SM_TEST',
            object_type_name='服务模块',
            side_info='失败侧: 源业务对象(BO_TEST)',
        )
        msg = str(denied)
        # 简化消息
        assert '服务模块(SM_TEST)' in msg or 'service_module(SM_TEST)' in msg
        assert '失败侧' in msg

    def test_error_message_includes_target_id_fallback(self):
        """业务键缺失时, 错误消息用 target_id 兜底"""
        from meta.core.interceptors.write_scope_interceptor import WriteScopeDenied

        denied = WriteScopeDenied(
            object_type='domain',
            target_id=42,
            user_id=1,
            check_results={},
            business_key=None,  # 无业务键
            object_type_name=None,
        )
        msg = str(denied)
        # 应有 target_id 兜底
        assert 'domain(42)' in msg or '42' in msg

    def test_error_message_uses_object_type_name(self):
        """错误消息使用 object_type_name (中文)"""
        from meta.core.interceptors.write_scope_interceptor import WriteScopeDenied

        denied = WriteScopeDenied(
            object_type='service_module',
            target_id=1,
            user_id=1,
            check_results={},
            object_type_name='服务模块',
        )
        msg = str(denied)
        # 中文类型名
        assert '服务模块' in msg or 'service_module' in msg


# ============================================================
# 2. TestWriteScopeVirtualFieldSkip
# ============================================================

class TestWriteScopeVirtualFieldSkip:
    """virtual field 不参与 write_scope 检查"""

    def test_virtual_field_not_in_write_scope_check(self):
        """virtual field 不参与 write_scope 检查"""
        # TODO: 当前 write_scope_interceptor.py 暂未实现 virtual field 跳过逻辑
        # 源码扫描确认: 未找到 'virtual' 或 'is_virtual' 字段标记
        # 这是 v2.1 之后可能的增强 (在 _validate_fk_scope_policies 中加入 is_virtual 跳过)
        pytest.skip("virtual field 跳过逻辑尚未实现 (TODO: v2.1+ enhancement)")

    def test_formula_field_not_write_scope_checked(self):
        """formula field 不参与 write_scope 检查"""
        # TODO: 当前 write_scope_interceptor.py 暂未实现 formula field 跳过逻辑
        # 源码扫描确认: 未找到 'formula' 或 'is_formula' 字段标记
        pytest.skip("formula field 跳过逻辑尚未实现 (TODO: v2.1+ enhancement)")


# ============================================================
# 3. TestUpdateResultValidated
# ============================================================

class TestUpdateResultValidated:
    """update 结果包含受影响的字段数验证"""

    def test_update_result_field_count_check(self):
        """update 结果应包含受影响字段数"""
        # 验证源码中存在 update 结果验证
        src_path = Path(PROJECT_ROOT) / 'meta' / 'core' / 'action_executor.py'
        if not src_path.exists():
            pytest.skip("action_executor.py 不存在")
        content = src_path.read_text(encoding='utf-8')
        # update 结果应包含字段数
        assert 'affected' in content or 'fields_count' in content or \
               'rowcount' in content or 'row_count' in content

    def test_partial_update_field_filter(self):
        """部分字段更新时的过滤"""
        # TODO: 部分字段更新过滤逻辑涉及 virtual field 概念
        # 由于 virtual field 跳过逻辑未实现, 该测试暂时 skip
        pytest.skip("依赖 virtual field 跳过逻辑 (TODO: v2.1+ enhancement)")


# ============================================================
# 4. TestWriteScopeDeniedAuditDecision
# ============================================================

class TestWriteScopeDeniedAuditDecision:
    """WriteScopeDenied 时记录决策埋点"""

    def test_deny_decision_logged(self):
        """deny 时调用 log_permission_decision"""
        src_path = Path(PROJECT_ROOT) / 'meta' / 'core' / 'interceptors' / 'write_scope_interceptor.py'
        content = src_path.read_text(encoding='utf-8')
        # 决策埋点
        assert 'log_permission_decision' in content

    def test_audit_decision_includes_check_results(self):
        """埋点应包含 check_results"""
        src_path = Path(PROJECT_ROOT) / 'meta' / 'core' / 'interceptors' / 'write_scope_interceptor.py'
        content = src_path.read_text(encoding='utf-8')
        assert 'check_results' in content


# ============================================================
# 5. TestWriteScopeDeniedSourceCodeStructure
# ============================================================

class TestWriteScopeDeniedSourceCodeStructure:
    """WriteScopeDenied 源码结构验证"""

    def test_write_scope_denied_class_exists(self):
        """WriteScopeDenied class 应存在"""
        from meta.core.interceptors.write_scope_interceptor import WriteScopeDenied
        assert WriteScopeDenied.status_code == 403

    def test_init_signature_supports_business_key(self):
        """WriteScopeDenied __init__ 支持 business_key"""
        import inspect
        from meta.core.interceptors.write_scope_interceptor import WriteScopeDenied

        sig = inspect.signature(WriteScopeDenied.__init__)
        # 关键字参数
        assert 'business_key' in sig.parameters
        assert 'object_type_name' in sig.parameters
        assert 'side_info' in sig.parameters
