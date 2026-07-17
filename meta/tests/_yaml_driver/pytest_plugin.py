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


# v1.1 新增: 9 个 constraint_type 的列表, 用于 pytest_generate_tests 展开
_V11_CONSTRAINT_TYPES = [
    "ASPECT_REFERENCED_MUST_EXIST",
    "ASPECT_FIELDS_APPLIED",
    "AUDIT_ASPECT_HAS_AUDIT_CONFIG",
    "RLS_FILE_EXISTS_FOR_OBJECT",
    "RLS_ENTITY_FIELD_VALID",
    "RLS_APPLIES_TO_ROLE_VALID",
    "FACTORY_DEFAULTS_COVER_REQUIRED",
    "FACTORY_OBJECT_TYPE_REGISTERED",
    "FACTORY_DEFAULTS_NOT_EMPTY",
    "FACTORY_UNIQUE_ID_DETERMINISTIC",  # [FIX 2026-07-17 P2]
]


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
    """
    参数化 fixture:
    - meta_object_id: 每个 yaml 一条 case (v1.0)
    - v11_spec: v1.1 每条 spec 一条 case (按 constraint_type 展开)
    """
    # v1.0: meta_object fixture -> parametrize meta_object_id
    if "meta_object_id" in metafunc.fixturenames:
        from .loader import load_schemas
        from .discoverer import _is_testable

        only = metafunc.config.getoption("--yaml-driver-only")
        skip = metafunc.config.getoption("--yaml-driver-skip")
        only_set = {s.strip() for s in (only or "").split(",") if s.strip()}
        skip_set = {s.strip() for s in (skip or "").split(",") if s.strip()}

        objects = load_schemas()
        ids = sorted(
            obj_id for obj_id in objects
            if obj_id
            and _is_testable(obj_id, objects[obj_id])
            and (not only_set or obj_id in only_set)
            and (not skip_set or obj_id not in skip_set)
        )
        metafunc.parametrize("meta_object_id", ids, ids=ids)
        return

    # v1.1: v11_spec fixture -> parametrize by constraint_type
    if "v11_spec" in metafunc.fixturenames:
        # 通过函数名检测具体约束类型
        fname = metafunc.function.__name__
        target_type = None
        for ctype in _V11_CONSTRAINT_TYPES:
            if fname.endswith(f"_{ctype.lower()}"):
                target_type = ctype
                break

        from .loader import (
            load_schemas, load_aspects, load_rls_rules, load_factories,
        )
        from .discoverer import discover_v11_constraints

        objs = load_schemas()
        specs = discover_v11_constraints(
            objs,
            aspects=load_aspects(),
            rls_rules=load_rls_rules(),
            factories=load_factories(),
        )
        matched = [s for s in specs if s.constraint == target_type]
        ids = [s.test_id for s in matched]
        metafunc.parametrize("v11_spec", matched, ids=ids)


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


# ============================================================
# v1.1 新增 fixtures (aspects_registry / rls_registry / factories_registry / v11_specs)
#   实现在 _yaml_driver/conftest.py 里
# ============================================================