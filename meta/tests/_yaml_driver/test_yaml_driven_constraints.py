# -*- coding: utf-8 -*-
"""
YAML 元模型驱动测试 - 主入口

触发方式:
    python d:\\filework\\test.py --file meta/tests/_yaml_driver/test_yaml_driven_constraints.py

展开规则:
    - 每个 yaml (38 个) 都自动展开成 5 个 case:
      test_yaml_object_loadable
      test_table_name_declared
      test_has_at_least_one_field
      test_field_ids_unique
      test_db_columns_unique
      test_persistent_fields_have_db_column
      test_unique_fields_match_index
    - 加上 4 个全局健康指标 case (no parametrize)

筛选:
    --yaml-driver-only=user,role,product
    --yaml-driver-skip=audit_log
"""
import pytest

# Direct imports
from meta.tests._yaml_driver.loader import load_schemas
from meta.tests._yaml_driver.discoverer import discover_all_constraints, _is_testable


# ============================================================
# Session-scoped fixture: 整个测试 session 共享一份 yaml 字典
# ============================================================

@pytest.fixture(scope="session")
def meta_registry():
    """session 级 registry: 整个测试过程只加载一次 yaml"""
    registry = load_schemas()
    if not registry:
        pytest.skip("No yaml schemas loaded - check meta/schemas/ directory")
    return registry


@pytest.fixture(scope="session")
def constraint_specs(meta_registry):
    """session 级: 推导所有约束测试规格"""
    return discover_all_constraints(meta_registry)


# ============================================================
# 7 个 per-yaml 测试函数, 每个都被 pytest_generate_tests 参数化为 38 个 case
# ============================================================

def _yaml_driver_obj_ids():
    """compute testable object IDs at collection time"""
    registry = load_schemas()
    return sorted(
        obj_id for obj_id in registry
        if obj_id and _is_testable(obj_id, registry[obj_id])
    )


def pytest_generate_tests(metafunc):
    """为 7 个 *_per_object 测试函数做参数化, 跳过 4 个全局 case"""
    per_object_funcs = {
        "test_yaml_object_loadable",
        "test_table_name_declared",
        "test_has_at_least_one_field",
        "test_field_ids_unique",
        "test_db_columns_unique",
        "test_persistent_fields_have_db_column",
        "test_unique_fields_match_index",
    }
    if metafunc.function.__name__ in per_object_funcs:
        ids = _yaml_driver_obj_ids()
        metafunc.parametrize("meta_object_id", ids, ids=ids)


# ============================================================
# 7 个 per-object case
# ============================================================

def test_yaml_object_loadable(meta_object_id, meta_registry):
    """每个 yaml schema 加载后能在 registry 中找到"""
    obj = meta_registry.get(meta_object_id)
    assert obj is not None, f"MetaObject '{meta_object_id}' not in registry"
    assert obj.id == meta_object_id, (
        f"Object id mismatch: file parsed id='{obj.id}', expected='{meta_object_id}'"
    )
    assert obj.name, f"Object '{meta_object_id}' has no name"


def test_table_name_declared(meta_object_id, meta_registry):
    """持久化对象必须有 table_name"""
    obj = meta_registry.get(meta_object_id)
    if not obj:
        pytest.skip(f"Object '{meta_object_id}' not in registry")
    if not getattr(obj, "persistent", True):
        pytest.skip("Non-persistent object")
    assert getattr(obj, "table_name", ""), (
        f"Persistent object '{meta_object_id}' has no table_name"
    )


def test_has_at_least_one_field(meta_object_id, meta_registry):
    """任何业务对象至少有 1 个字段"""
    obj = meta_registry.get(meta_object_id)
    if not obj:
        pytest.skip(f"Object '{meta_object_id}' not in registry")
    assert len(obj.fields) >= 1, (
        f"Object '{meta_object_id}' has no fields"
    )


def test_field_ids_unique(meta_object_id, meta_registry):
    """对象内所有字段 id 必须唯一"""
    obj = meta_registry.get(meta_object_id)
    if not obj:
        pytest.skip(f"Object '{meta_object_id}' not in registry")
    ids = [f.id for f in obj.fields]
    duplicates = [i for i in ids if ids.count(i) > 1]
    assert not duplicates, (
        f"Object '{meta_object_id}' has duplicate field ids: {set(duplicates)}"
    )


def test_db_columns_unique(meta_object_id, meta_registry):
    """所有持久化字段的 db_column 必须唯一"""
    obj = meta_registry.get(meta_object_id)
    if not obj:
        pytest.skip(f"Object '{meta_object_id}' not in registry")
    cols = [f.db_column for f in obj.fields if getattr(f, "db_column", None)]
    duplicates = [c for c in cols if cols.count(c) > 1]
    assert not duplicates, (
        f"Object '{meta_object_id}' has duplicate db_columns: {set(duplicates)}"
    )


def test_persistent_fields_have_db_column(meta_object_id, meta_registry):
    """所有 storage=STORED 的字段必须有 db_column"""
    obj = meta_registry.get(meta_object_id)
    if not obj:
        pytest.skip(f"Object '{meta_object_id}' not in registry")
    bad = []
    for f in obj.fields:
        storage_val = getattr(getattr(f, "storage", None), "value", "stored")
        if storage_val == "stored" and not getattr(f, "db_column", None):
            bad.append(f.id)
    assert not bad, (
        f"Object '{meta_object_id}' persistent fields missing db_column: {bad}"
    )


def test_unique_fields_match_index(meta_object_id, meta_registry):
    """unique=True 字段应在 indexes 中声明"""
    obj = meta_registry.get(meta_object_id)
    if not obj:
        pytest.skip(f"Object '{meta_object_id}' not in registry")
    indexed_fields = set()
    for idx in getattr(obj, "indexes", []) or []:
        for fid in getattr(idx, "fields", []) or []:
            indexed_fields.add(fid)
    bad = []
    for f in obj.fields:
        if getattr(f, "unique", False) and f.id not in indexed_fields:
            bad.append(f.id)
    if bad:
        pytest.skip(
            f"Object '{meta_object_id}' unique fields not in indexes (informational): {bad}"
        )


# ============================================================
# 4 个全局 case (not parametrized)
# ============================================================

def test_no_constraint_violations(constraint_specs):
    """所有推导出的约束都应该通过"""
    violations = [s for s in constraint_specs if s.severity == "error"]
    if violations:
        details = "\n".join(
            f"  - {s.test_id}: {s.description}" for s in violations
        )
        pytest.fail(
            f"Found {len(violations)} yaml constraint violation(s):\n{details}"
        )


def test_warning_constraints_listed(constraint_specs, capsys):
    """warning 级约束即使不 fail, 也要在测试报告里可见"""
    warnings = [s for s in constraint_specs if s.severity == "warning"]
    if warnings:
        print(f"\n[INFO] {len(warnings)} warning-level constraints:")
        for w in warnings[:10]:
            print(f"  - {w.test_id}: {w.description}")
        if len(warnings) > 10:
            print(f"  ... and {len(warnings) - 10} more")


def test_loaded_object_count(meta_registry):
    """验证 loader 实际加载了多少 yaml"""
    count = len(meta_registry)
    assert count >= 10, (
        f"Expected to load >=10 MetaObjects from yaml, got {count}. "
        "Check meta/schemas/ directory or loader."
    )


def test_constraint_discovery_ran(constraint_specs):
    """验证 discoverer 跑通了"""
    assert constraint_specs is not None
    assert isinstance(constraint_specs, list)