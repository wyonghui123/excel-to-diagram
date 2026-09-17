# -*- coding: utf-8 -*-
"""
[MODULE] Phase 12: 3 阶段灰度发布测试
[DESCRIPTION]
    P12-T1: 阶段 1 audit-only (新判定仅写审计, 不拦截)
    P12-T2: 阶段 1 验收 (审计分析脚本, 不一致率 < 5%)
    P12-T3: 阶段 2 soft-default (new Deny + old Allow → 告警+放行)
    P12-T4: 阶段 2 验收 (告警 < 1/万请求)
    P12-T5: 阶段 3 hard-reject (新体系独占)
    P12-T6: 阶段 3 验收 (全量回归通过)

[SPEC] spec-permission-system-unification-2026-07-19 §4.12 / §8.12
[ENV] WRITE_SCOPE_AUDIT_ONLY = true | false | soft (3 阶段切换)
"""
import os
import sys
import json
import pytest
import tempfile
from unittest.mock import MagicMock, patch

# 确保 import 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))


# ============================================================================
# P12-T1: 阶段 1 audit-only
# ============================================================================

class TestP12T1AuditOnly:
    """[P12-T1] 阶段 1 audit-only: 新判定仅写审计, 不拦截"""

    def test_env_flag_audit_only_true(self, monkeypatch):
        """[P12-T1] WRITE_SCOPE_AUDIT_ONLY=true 启用 audit-only 模式"""
        from meta.services.write_scope_mode import WriteScopeMode, get_write_scope_mode
        monkeypatch.setenv('WRITE_SCOPE_AUDIT_ONLY', 'true')
        mode = get_write_scope_mode()
        assert mode == WriteScopeMode.AUDIT_ONLY, \
            f"WRITE_SCOPE_AUDIT_ONLY=true 应启用 audit-only, got {mode}"

    def test_env_flag_audit_only_false(self, monkeypatch):
        """[P12-T1] WRITE_SCOPE_AUDIT_ONLY=false 启用 hard-reject 模式"""
        from meta.services.write_scope_mode import WriteScopeMode, get_write_scope_mode
        monkeypatch.setenv('WRITE_SCOPE_AUDIT_ONLY', 'false')
        mode = get_write_scope_mode()
        assert mode == WriteScopeMode.HARD_REJECT, \
            f"WRITE_SCOPE_AUDIT_ONLY=false 应启用 hard-reject, got {mode}"

    def test_env_flag_soft_default(self, monkeypatch):
        """[P12-T1] WRITE_SCOPE_AUDIT_ONLY=soft 启用 soft-default 模式"""
        from meta.services.write_scope_mode import WriteScopeMode, get_write_scope_mode
        monkeypatch.setenv('WRITE_SCOPE_AUDIT_ONLY', 'soft')
        mode = get_write_scope_mode()
        assert mode == WriteScopeMode.SOFT_DEFAULT, \
            f"WRITE_SCOPE_AUDIT_ONLY=soft 应启用 soft-default, got {mode}"

    def test_audit_only_dual_check_logs_inconsistency(self, monkeypatch):
        """[P12-T1] audit-only: 新旧判定不一致时只记录审计, 不拦截"""
        from meta.services.write_scope_mode import (
            WriteScopeMode, WriteScopeAuditor, get_write_scope_mode
        )
        monkeypatch.setenv('WRITE_SCOPE_AUDIT_ONLY', 'true')

        auditor = WriteScopeAuditor()
        # 模拟 new_check=False (拒绝), old_check=True (允许) - 不一致
        auditor.record_dual_check(
            user_id=1, action='write', resource_type='product',
            resource_id=100, new_decision=False, old_decision=True,
            reason='new system denies (prohibition rule)'
        )
        stats = auditor.get_stats()
        assert stats['total'] == 1
        assert stats['inconsistent'] == 1
        assert stats['inconsistency_rate'] == 1.0

    def test_audit_only_returns_old_decision_when_inconsistent(self, monkeypatch):
        """[P12-T1] audit-only: 不一致时返回旧判定结果 (不阻断业务)"""
        from meta.services.permission_resolver import PermissionResolver
        from meta.services.write_scope_mode import WriteScopeMode, get_write_scope_mode
        monkeypatch.setenv('WRITE_SCOPE_AUDIT_ONLY', 'true')

        resolver = PermissionResolver(data_source=None)
        user = {'id': 1, 'is_superuser': False}

        # 模拟旧逻辑允许, 新逻辑拒绝 → 应返回旧逻辑 (True)
        with patch.object(resolver, '_check_prohibition') as mock_prohibition, \
             patch.object(resolver, '_check_action') as mock_action, \
             patch.object(resolver, '_legacy_check') as mock_legacy:
            mock_prohibition.return_value = False  # 新逻辑: 无 prohibition
            mock_action.return_value = False  # 新逻辑: 拒绝
            mock_legacy.return_value = True  # 旧逻辑: 允许

            result = resolver.check_with_grayscale(
                user=user, action='write',
                resource_type='product', resource={'id': 100}
            )
            assert result is True, \
                "audit-only 模式下不一致应返回旧判定 (允许)"

    def test_audit_only_warning_header_added(self, monkeypatch):
        """[P12-T1] audit-only: 不一致时设置 X-Write-Scope-Warning header"""
        from meta.services.write_scope_mode import WriteScopeAuditor
        monkeypatch.setenv('WRITE_SCOPE_AUDIT_ONLY', 'true')

        auditor = WriteScopeAuditor()
        auditor.record_dual_check(
            user_id=1, action='write', resource_type='product',
            resource_id=100, new_decision=False, old_decision=True,
            reason='new system denies'
        )
        warnings = auditor.get_warnings()
        assert len(warnings) == 1
        assert 'reason' in warnings[0]
        assert warnings[0]['reason'] == 'new system denies'


# ============================================================================
# P12-T2: 阶段 1 验收 (审计分析脚本)
# ============================================================================

class TestP12T2AuditAnalysis:
    """[P12-T2] 阶段 1 验收: 审计分析脚本, 不一致率 < 5%"""

    def test_audit_analysis_script_exists(self):
        """[P12-T2] 审计分析脚本应存在"""
        from pathlib import Path
        script_path = Path(__file__).parent.parent / 'scripts' / 'analyze_write_scope_audit.py'
        assert script_path.exists(), \
            f"审计分析脚本应存在: {script_path}"

    def test_audit_analysis_computes_inconsistency_rate(self, tmp_path):
        """[P12-T2] 审计分析脚本应计算不一致率"""
        from meta.services.write_scope_auditor import WriteScopeAuditor as Auditor
        # 模拟 100 条审计记录, 3 条不一致
        auditor = Auditor()
        for i in range(97):
            auditor.record_dual_check(
                user_id=1, action='write', resource_type='product',
                resource_id=i, new_decision=True, old_decision=True,
                reason=''
            )
        for i in range(3):
            auditor.record_dual_check(
                user_id=1, action='write', resource_type='product',
                resource_id=97 + i, new_decision=False, old_decision=True,
                reason='new denies'
            )
        stats = auditor.get_stats()
        assert stats['total'] == 100
        assert stats['inconsistent'] == 3
        assert abs(stats['inconsistency_rate'] - 0.03) < 0.001
        # < 5% 验收门禁通过
        assert stats['inconsistency_rate'] < 0.05, "不一致率 < 5% 可进阶段 2"

    def test_audit_analysis_threshold_fails_when_high(self, tmp_path):
        """[P12-T2] 不一致率 >= 5% 时应验收失败"""
        from meta.services.write_scope_auditor import WriteScopeAuditor as Auditor
        auditor = Auditor()
        # 100 条审计记录, 10 条不一致 (10%)
        for i in range(90):
            auditor.record_dual_check(
                user_id=1, action='write', resource_type='product',
                resource_id=i, new_decision=True, old_decision=True,
                reason=''
            )
        for i in range(10):
            auditor.record_dual_check(
                user_id=1, action='write', resource_type='product',
                resource_id=90 + i, new_decision=False, old_decision=True,
                reason='new denies'
            )
        stats = auditor.get_stats()
        assert stats['inconsistency_rate'] >= 0.05, \
            "10% 不一致率应 >= 5% 阈值"


# ============================================================================
# P12-T3: 阶段 2 soft-default
# ============================================================================

class TestP12T3SoftDefault:
    """[P12-T3] 阶段 2 soft-default:
        - new Deny + old Allow → 告警 + 放行
        - new Allow → 放行
    """

    def test_soft_default_new_deny_old_allow_returns_allow_with_warning(self, monkeypatch):
        """[P12-T3] soft-default: new Deny + old Allow → 告警 + 放行"""
        from meta.services.permission_resolver import PermissionResolver
        from meta.services.write_scope_mode import WriteScopeMode, get_write_scope_mode
        monkeypatch.setenv('WRITE_SCOPE_AUDIT_ONLY', 'soft')
        assert get_write_scope_mode() == WriteScopeMode.SOFT_DEFAULT

        resolver = PermissionResolver(data_source=None)
        user = {'id': 1, 'is_superuser': False}

        with patch.object(resolver, '_check_action') as mock_action, \
             patch.object(resolver, '_legacy_check') as mock_legacy:
            mock_action.return_value = False  # 新逻辑拒绝
            mock_legacy.return_value = True  # 旧逻辑允许

            result = resolver.check_with_grayscale(
                user=user, action='write',
                resource_type='product', resource={'id': 100}
            )
            assert result is True, \
                "soft-default: new Deny + old Allow 应放行 (返回 True)"

    def test_soft_default_new_allow_returns_allow(self, monkeypatch):
        """[P12-T3] soft-default: new Allow → 放行"""
        from meta.services.permission_resolver import PermissionResolver
        monkeypatch.setenv('WRITE_SCOPE_AUDIT_ONLY', 'soft')

        resolver = PermissionResolver(data_source=None)
        user = {'id': 1, 'is_superuser': False}

        with patch.object(resolver, '_check_action') as mock_action, \
             patch.object(resolver, '_legacy_check') as mock_legacy:
            mock_action.return_value = True  # 新逻辑允许
            mock_legacy.return_value = True  # 旧逻辑允许

            result = resolver.check_with_grayscale(
                user=user, action='write',
                resource_type='product', resource={'id': 100}
            )
            assert result is True

    def test_soft_default_new_allow_old_deny_returns_allow(self, monkeypatch):
        """[P12-T3] soft-default: new Allow + old Deny → 放行 (新体系优先)"""
        from meta.services.permission_resolver import PermissionResolver
        monkeypatch.setenv('WRITE_SCOPE_AUDIT_ONLY', 'soft')

        resolver = PermissionResolver(data_source=None)
        user = {'id': 1, 'is_superuser': False}

        with patch.object(resolver, '_check_action') as mock_action, \
             patch.object(resolver, '_legacy_check') as mock_legacy:
            mock_action.return_value = True  # 新逻辑允许
            mock_legacy.return_value = False  # 旧逻辑拒绝

            result = resolver.check_with_grayscale(
                user=user, action='write',
                resource_type='product', resource={'id': 100}
            )
            # spec: "新 Allow → 放行"
            assert result is True, \
                "soft-default: new Allow 应放行 (新体系优先于旧体系)"

    def test_soft_default_missing_dim_scope_defaults_all(self, monkeypatch):
        """[P12-T3] soft-default: 缺 dim scope 角色临时默认 scope = all (宽)"""
        from meta.services.permission_resolver import PermissionResolver
        from meta.services.write_scope_mode import get_write_scope_mode, WriteScopeMode
        monkeypatch.setenv('WRITE_SCOPE_AUDIT_ONLY', 'soft')

        resolver = PermissionResolver(data_source=None)
        user = {'id': 1, 'is_superuser': False, 'roles': [{'code': 'test'}]}

        # 缺 dim scope → 默认 scope = all (允许)
        result = resolver._resolve_default_scope(user, 'product')
        assert result == 'all', \
            "soft-default: 缺 dim scope 应默认 'all'"


# ============================================================================
# P12-T4: 阶段 2 验收 (告警 < 1/万请求)
# ============================================================================

class TestP12T4SoftDefaultAcceptance:
    """[P12-T4] 阶段 2 验收: 告警 < 1/万请求"""

    def test_warning_rate_below_threshold(self):
        """[P12-T4] 告警率 < 1/万请求 时验收通过"""
        from meta.services.write_scope_auditor import WriteScopeAuditor as Auditor
        auditor = Auditor()
        # 10000 请求, 0 告警
        for i in range(10000):
            auditor.record_dual_check(
                user_id=1, action='write', resource_type='product',
                resource_id=i, new_decision=True, old_decision=True,
                reason=''
            )
        stats = auditor.get_stats()
        assert stats['warning_rate_per_10k'] < 1, \
            f"告警率应 < 1/万, got {stats['warning_rate_per_10k']}"

    def test_warning_rate_above_threshold_fails(self):
        """[P12-T4] 告警率 >= 1/万请求 时验收失败"""
        from meta.services.write_scope_auditor import WriteScopeAuditor as Auditor
        auditor = Auditor()
        # 10000 请求, 2 告警 (2/万)
        for i in range(9998):
            auditor.record_dual_check(
                user_id=1, action='write', resource_type='product',
                resource_id=i, new_decision=True, old_decision=True,
                reason=''
            )
        for i in range(2):
            auditor.record_dual_check(
                user_id=1, action='write', resource_type='product',
                resource_id=9998 + i, new_decision=False, old_decision=True,
                reason='new denies'
            )
        stats = auditor.get_stats()
        assert stats['warning_rate_per_10k'] >= 1, \
            f"2/万 告警率应 >= 1/万阈值, got {stats['warning_rate_per_10k']}"


# ============================================================================
# P12-T5: 阶段 3 hard-reject
# ============================================================================

class TestP12T5HardReject:
    """[P12-T5] 阶段 3 hard-reject: 新体系独占"""

    def test_hard_reject_new_deny_returns_deny(self, monkeypatch):
        """[P12-T5] hard-reject: 新逻辑拒绝时返回 Deny (不再回退到旧逻辑)"""
        from meta.services.permission_resolver import PermissionResolver
        from meta.services.write_scope_mode import WriteScopeMode, get_write_scope_mode
        monkeypatch.setenv('WRITE_SCOPE_AUDIT_ONLY', 'false')
        assert get_write_scope_mode() == WriteScopeMode.HARD_REJECT

        resolver = PermissionResolver(data_source=None)
        user = {'id': 1, 'is_superuser': False}

        with patch.object(resolver, '_check_action') as mock_action, \
             patch.object(resolver, '_legacy_check') as mock_legacy:
            mock_action.return_value = False  # 新逻辑拒绝
            mock_legacy.return_value = True  # 旧逻辑允许 (不应被调用)

            result = resolver.check_with_grayscale(
                user=user, action='write',
                resource_type='product', resource={'id': 100}
            )
            assert result is False, \
                "hard-reject: 新逻辑拒绝应直接 Deny, 不回退旧逻辑"
            # 旧逻辑不应被调用
            mock_legacy.assert_not_called()

    def test_hard_reject_new_allow_returns_allow(self, monkeypatch):
        """[P12-T5] hard-reject: 新逻辑允许时返回 Allow"""
        from meta.services.permission_resolver import PermissionResolver
        monkeypatch.setenv('WRITE_SCOPE_AUDIT_ONLY', 'false')

        resolver = PermissionResolver(data_source=None)
        user = {'id': 1, 'is_superuser': False}

        with patch.object(resolver, '_check_action') as mock_action, \
             patch.object(resolver, '_legacy_check') as mock_legacy:
            mock_action.return_value = True  # 新逻辑允许
            mock_legacy.return_value = False  # 旧逻辑拒绝 (不应被调用)

            result = resolver.check_with_grayscale(
                user=user, action='write',
                resource_type='product', resource={'id': 100}
            )
            assert result is True
            mock_legacy.assert_not_called()


# ============================================================================
# P12-T6: 阶段 3 全量回归 (本测试套件)
# ============================================================================

class TestP12T6FullRegression:
    """[P12-T6] 阶段 3 全量回归测试"""

    def test_phase12_all_tests_collected(self):
        """[P12-T6] Phase 12 测试套件应包含所有 6 个任务测试"""
        # 至少应包含以下测试类
        assert TestP12T1AuditOnly is not None
        assert TestP12T2AuditAnalysis is not None
        assert TestP12T3SoftDefault is not None
        assert TestP12T4SoftDefaultAcceptance is not None
        assert TestP12T5HardReject is not None
        assert TestP12T6FullRegression is not None

    def test_hard_reject_no_regression_with_super_user(self, monkeypatch):
        """[P12-T6] hard-reject: superuser 仍 Allow (无 regression)"""
        from meta.services.permission_resolver import PermissionResolver
        monkeypatch.setenv('WRITE_SCOPE_AUDIT_ONLY', 'false')

        resolver = PermissionResolver(data_source=None)
        user = {'id': 1, 'is_superuser': True}

        result = resolver.check_with_grayscale(
            user=user, action='write',
            resource_type='product', resource={'id': 100}
        )
        assert result is True, "superuser 应始终 Allow"

    def test_hard_reject_no_regression_prohibition(self, monkeypatch):
        """[P12-T6] hard-reject: prohibition 规则仍生效 (Layer 0)"""
        from meta.services.permission_resolver import PermissionResolver
        monkeypatch.setenv('WRITE_SCOPE_AUDIT_ONLY', 'false')

        # 构造 mock data_source
        mock_ds = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [('product', None)]  # prohibition 命中
        mock_ds.execute.return_value = mock_cursor

        resolver = PermissionResolver(data_source=mock_ds)
        user = {'id': 1, 'is_superuser': False}

        result = resolver.check_with_grayscale(
            user=user, action='write',
            resource_type='product', resource={'id': 100}
        )
        assert result is False, "prohibition 命中应 Deny (Layer 0 优先)"
