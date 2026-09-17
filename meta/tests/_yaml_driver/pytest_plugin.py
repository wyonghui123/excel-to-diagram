# -*- coding: utf-8 -*-
"""
pytest 插件: 把 MetaObject 作为 fixture 暴露给测试函数

使用方式 (conftest.py 或测试文件):
    from meta.tests._yaml_driver.pytest_plugin import (
        yaml_driver,        # pytest_plugin 入口
        meta_registry,      # session 级别 fixture: {obj_id: MetaObject}
        meta_object,        # function 级别 fixture: 单个 MetaObject (参数化)
    )

或直接在测试文件顶部:
    pytest_plugins = ["meta.tests._yaml_driver.pytest_plugin"]
"""
import pytest


def pytest_addoption(parser):
    """注册 CLI 选项"""
    group = parser.getgroup("yaml_driver")
    group.addoption(
        "--yaml-driver-only",
        action="store",
        default=None,
        help="只跑指定对象 id 的 yaml 驱动测试 (逗号分隔, e.g. user,role,product)",
    )
    group.addoption(
        "--yaml-driver-skip",
        action="store",
        default=None,
        help="跳过指定对象 id (逗号分隔)",
    )


def pytest_generate_tests(metafunc):
    """参数化 meta_object fixture - 拆出每个 yaml 为独立 case"""
    if "meta_object" not in metafunc.fixturenames:
        return

    if "meta_object_id" not in metafunc.fixturenames:
        return

    # 只在参数化测试函数上展开
    from .loader import load_schemas
    from .discoverer import discover_all_constraints

    only = metafunc.config.getoption("--yaml-driver-only")
    skip = metafunc.config.getoption("--yaml-driver-skip")
    only_set = {s.strip() for s in (only or "").split(",") if s.strip()}
    skip_set = {s.strip() for s in (skip or "").split(",") if s.strip()}

    objects = load_schemas()
    from .discoverer import _is_testable
    ids = sorted(
        obj_id for obj_id in objects
        if obj_id  # skip empty-id infra yamls (e.g. _template)
        and _is_testable(obj_id, objects[obj_id])
        and (not only_set or obj_id in only_set)
        and (not skip_set or obj_id not in skip_set)
    )
    metafunc.parametrize(
        "meta_object_id",
        ids,
        ids=ids,
    )


@pytest.fixture(scope="session")
def meta_registry():
    """session-scoped: 整个测试 session 共享一份 yaml 字典"""
    from .loader import load_schemas
    registry = load_schemas()
    if not registry:
        pytest.skip("No yaml schemas loaded - check meta/schemas/ directory")
    return registry


@pytest.fixture
def meta_object(meta_object_id, meta_registry):
    """function-scoped: 取出单个 MetaObject"""
    try:
        obj = meta_registry.get(meta_object_id)
    except Exception as e:
        pytest.skip(f"Failed to get MetaObject '{meta_object_id}': {e}")
    if obj is None:
        pytest.skip(f"MetaObject '{meta_object_id}' not found")
    return obj


@pytest.fixture(scope="session")
def constraint_specs(meta_registry):
    """session-scoped: 推导所有约束测试规格"""
    from .discoverer import discover_all_constraints
    return discover_all_constraints(meta_registry)