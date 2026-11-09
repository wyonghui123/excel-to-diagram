# -*- coding: utf-8 -*-
"""应用启动/注册契约测试（AppBuilder FR-5 开关 / 跨归属冲突守卫）。

[TEST-EFF P2-1] 由两个同域（应用装配与注册，纯内存）的 <=5 用例小文件合并：
- test_app_builder_fr5_extras.py        (COV-006 FR-5.* enable 标志)
- test_arch_startup_collision_guard.py   ([ARCH-V3 §0.4.5] 不变量 5/6)
合并后统一 unit marker（原 arch 文件未标 marker，用例本身为纯单元）。
"""

import tempfile

import pytest

from meta.core.app_registry import (
    AppRegistrationError,
    _assert_app_registration_safe,
)

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


def test_bo_id_clash_with_platform_raises():
    with pytest.raises(AppRegistrationError, match="BO id 'items'"):
        _assert_app_registration_safe(
            {"demo": ["items"]},
            {"demo": []},
            platform_bo_ids=["items"],
            platform_table_names=[],
        )


def test_table_name_clash_with_platform_raises():
    with pytest.raises(AppRegistrationError, match="table_name 'items'"):
        _assert_app_registration_safe(
            {"demo": ["demo_item"]},
            {"demo": ["items"]},
            platform_bo_ids=[],
            platform_table_names=["items"],
        )


def test_table_name_clash_between_apps_raises():
    with pytest.raises(AppRegistrationError, match="table_name 'shared'"):
        _assert_app_registration_safe(
            {"a": ["a_bo"], "b": ["b_bo"]},
            {"a": ["shared"], "b": ["shared"]},
            platform_bo_ids=[],
            platform_table_names=[],
        )


def test_same_owner_duplicate_table_allowed():
    """同归属（同一应用内部）重复不拦，避免误伤历史同名。"""
    _assert_app_registration_safe(
        {"a": ["a1", "a2"]},
        {"a": ["t1", "t1"]},
        platform_bo_ids=["items"],
        platform_table_names=["items"],
    )


def test_no_conflict_passes():
    _assert_app_registration_safe(
        {"a": ["a_bo"]},
        {"a": ["a_table"]},
        platform_bo_ids=["items"],
        platform_table_names=["items"],
    )
