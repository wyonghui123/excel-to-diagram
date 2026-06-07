# -*- coding: utf-8 -*-
"""
COV-006: AppBuilder FR-5.* enable 标志 + with_auto_schema 5 个新单元测试

[NEW] v1.2 / FR-5.3 ~ FR-5.7: 显式启用标志 + M7.4 with_auto_schema
"""
import os
import tempfile
import pytest

pytestmark = pytest.mark.unit


class TestAppBuilderExtras:
    """AppBuilder FR-5 enable 标志测试 (COV-006)"""

    def _make_builder(self):
        from meta.core.app_builder import ApplicationBuilder
        # 用临时 DB 避免污染主库
        f = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        f.close()
        return ApplicationBuilder(db_path=f.name)

    def test_with_preflight_checks_enables_flag(self):
        """with_preflight_checks() 启用 _enable_preflight 标志"""
        b = self._make_builder()
        assert b._enable_preflight is False
        result = b.with_preflight_checks()
        assert result is b  # 链式调用返回 self
        assert b._enable_preflight is True

    def test_with_telemetry_enables_flag(self):
        """with_telemetry() 启用 _enable_telemetry 标志"""
        b = self._make_builder()
        assert b._enable_telemetry is False
        result = b.with_telemetry()
        assert result is b
        assert b._enable_telemetry is True

    def test_with_auth_init_enables_flag(self):
        """with_auth_init() 启用 _enable_auth_init 标志"""
        b = self._make_builder()
        assert b._enable_auth_init is False
        result = b.with_auth_init()
        assert result is b
        assert b._enable_auth_init is True

    def test_with_menu_init_enables_flag(self):
        """with_menu_init() 启用 _enable_menu_init 标志"""
        b = self._make_builder()
        assert b._enable_menu_init is False
        result = b.with_menu_init()
        assert result is b
        assert b._enable_menu_init is True

    def test_with_auto_schema_returns_builder(self):
        """with_auto_schema() 返回 builder 自身（链式）"""
        b = self._make_builder()
        result = b.with_data_source().with_auto_schema()
        assert result is b
