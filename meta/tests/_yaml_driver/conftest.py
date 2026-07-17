# -*- coding: utf-8 -*-
"""
yaml_driver 包的 conftest.py

注册 pytest fixture + hook, 让 test_*.py 自动获得:
    - meta_object_id (参数化)
    - meta_object (单对象)
    - meta_registry (整个 registry)
    - constraint_specs (推导出的约束)
    - v11_* (v1.1 新增: aspects/rls/factories/v11_specs/v11_spec)
"""
import pytest

from meta.tests._yaml_driver.pytest_plugin import (
    pytest_addoption,
    pytest_generate_tests,
    meta_registry,
    meta_object,
    constraint_specs,
)


# ============================================================
# v1.1 新增 fixtures
# ============================================================

@pytest.fixture(scope="session")
def aspects_registry():
    """v1.1 session 级 aspects 字典"""
    from meta.tests._yaml_driver.loader import load_aspects
    return load_aspects()


@pytest.fixture(scope="session")
def rls_registry():
    """v1.1 session 级 rls 规则字典"""
    from meta.tests._yaml_driver.loader import load_rls_rules
    return load_rls_rules()


@pytest.fixture(scope="session")
def factories_registry():
    """v1.1 session 级 factory 字典"""
    from meta.tests._yaml_driver.loader import load_factories
    return load_factories()


@pytest.fixture(scope="session")
def v11_specs(
    meta_registry, aspects_registry, rls_registry, factories_registry,
):
    """v1.1 session 级约束测试规格 (aspects + rls + factory 合并)"""
    from meta.tests._yaml_driver.discoverer import discover_v11_constraints
    return discover_v11_constraints(
        meta_registry,
        aspects=aspects_registry,
        rls_rules=rls_registry,
        factories=factories_registry,
    )