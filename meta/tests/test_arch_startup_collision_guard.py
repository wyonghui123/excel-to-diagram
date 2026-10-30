# -*- coding: utf-8 -*-
"""[ARCH-V3 §0.4.5 不变量 5/6] 应用注册的跨归属冲突守卫。

覆盖：BO id 跨归属重复、table_name 跨归属重复、同归属重复放行。
"""

import pytest

from meta.core.app_registry import (
    AppRegistrationError,
    _assert_app_registration_safe,
)


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
