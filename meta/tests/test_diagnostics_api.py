# -*- coding: utf-8 -*-
"""
GAP-020: diagnostics_api 单测 (8 用例)

[NEW] 2026-06-07 批次: 补齐 diagnostics_api 工具函数测试
- 覆盖 build_diagnostics() 纯函数 (无 Flask)
- 验证返回结构: health / recent_errors / error_codes / recovery_suggestions / generated_at / trace_id
- 验证 FIX_HINTS 错误码覆盖
- 验证 trace_id 注入
"""
import json
import pytest

pytestmark = pytest.mark.unit


class TestBuildDiagnostics:
    """diagnostics_api.build_diagnostics() 单元测试 (GAP-020)"""

    def test_build_diagnostics_returns_success(self):
        """build_diagnostics() 返回 success=True"""
        from meta.api.diagnostics_api import build_diagnostics
        result = build_diagnostics()
        assert result.get('success') is True
        assert 'data' in result

    def test_build_diagnostics_data_structure(self):
        """data 字段含 health / recent_errors / error_codes / recovery_suggestions / generated_at / trace_id"""
        from meta.api.diagnostics_api import build_diagnostics
        result = build_diagnostics()
        data = result['data']
        assert 'health' in data
        assert 'recent_errors' in data
        assert 'error_codes' in data
        assert 'recovery_suggestions' in data
        assert 'generated_at' in data
        assert 'trace_id' in data

    def test_health_simple_has_required_fields(self):
        """health 含 status / integrity / db_size / wal_size / pool_active / backup_count"""
        from meta.api.diagnostics_api import build_diagnostics
        result = build_diagnostics()
        health = result['data']['health']
        # 6 关键字段
        for key in ('status', 'integrity', 'db_size', 'wal_size', 'pool_active', 'backup_count'):
            assert key in health, f"Missing health key: {key}"

    def test_error_codes_contains_fix_hints(self):
        """error_codes 含所有 FIX_HINTS 条目"""
        from meta.api.diagnostics_api import build_diagnostics
        from meta.core.error_fix_hints import FIX_HINTS
        result = build_diagnostics()
        codes = result['data']['error_codes']
        assert isinstance(codes, list)
        # error_codes 数量应等于 FIX_HINTS 长度
        assert len(codes) == len(FIX_HINTS)
        # 每个 code 含 code / fix_hint / see_also
        for c in codes:
            assert 'code' in c
            assert 'fix_hint' in c
            assert 'see_also' in c

    def test_recent_errors_is_list(self):
        """recent_errors 是 list (即使空)"""
        from meta.api.diagnostics_api import build_diagnostics
        result = build_diagnostics()
        assert isinstance(result['data']['recent_errors'], list)

    def test_recovery_suggestions_structure(self):
        """recovery_suggestions 元素含 level / action / auto_fix"""
        from meta.api.diagnostics_api import build_diagnostics
        result = build_diagnostics()
        suggestions = result['data']['recovery_suggestions']
        assert isinstance(suggestions, list)
        for s in suggestions:
            assert 'level' in s
            assert 'action' in s
            assert 'auto_fix' in s
            # level ∈ {info, warn, critical, error}
            assert s['level'] in ('info', 'warn', 'critical', 'error')

    def test_trace_id_in_data(self):
        """data 含 trace_id (UUID 32 字符)"""
        from meta.api.diagnostics_api import build_diagnostics
        result = build_diagnostics()
        tid = result['data']['trace_id']
        assert isinstance(tid, str)
        assert len(tid) >= 16  # 至少 16 字符

    def test_generated_at_is_iso_format(self):
        """generated_at 是 ISO 8601 UTC 时间"""
        from meta.api.diagnostics_api import build_diagnostics
        result = build_diagnostics()
        ts = result['data']['generated_at']
        # 验证 ISO 8601 格式 (含 T 分隔 + Z 结尾)
        assert 'T' in ts
        assert ts.endswith('Z') or ts.endswith('+00:00')
