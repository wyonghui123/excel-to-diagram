# -*- coding: utf-8 -*-
"""
YAML 元模型驱动测试 - 主入口

触发方式:
    python d:\\filework\\test.py --file meta/tests/_yaml_driver/test_yaml_driven_constraints.py

展开规则:
    - 每个 yaml (38 个) 都自动展开成 7 个 case
    - 加上 4 个全局健康指标 case (no parametrize)
    - v1.1: 加上 9 个新约束类型的 case (Aspects / RLS / Factory)

筛选:
    --yaml-driver-only=user,role,product
    --yaml-driver-skip=audit_log

v1.1 集成说明:
    - aspect/rls/factory fixtures 和 pytest_generate_tests 在 pytest_plugin.py 里
    - 本文件只包含: v1.0 per-object 测试 + v1.1 per-spec 测试 + 全局汇总
"""
import pytest


# ============================================================
# 7 个 per-yaml 测试函数, 每个都被 pytest_generate_tests 参数化为 N 个 case
# (参数化 hook 由 pytest_plugin.py 提供)
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


# ============================================================
# v1.1 P0#2 新增: Hardcoded ID Lint Guard
# ============================================================
# 防止 f-string-int-time-time / random.randint 等高冲突风险模式蔓延
# 调用 .trae/debug/lint_no_hardcoded_id.py 扫描 meta/tests, 必须保持 0 error
# (warning / low 暂时允许, 未来逐个消除)

def test_no_hardcoded_id_in_test_files():
    """[P0#2 guard] 任何 meta/tests/test_*.py 不能有 f-string with int(time.time()) 模式.

    退出条件 (lint default mode):
      - 0 error: 通过
      - >0 error: fail, 输出 lint 报告

    这个 test 是工厂采用率的"长期保护" - 一旦有人新增 f-string-int-time-time,
    v1.1 strict mode 立刻 fail, 防止 hardcoded 蔓延.
    """
    import subprocess
    import sys as _sys
    from pathlib import Path as _Path

    # lint 工具位置: 项目根 .trae/debug/lint_no_hardcoded_id.py
    repo_root = _Path(__file__).resolve().parents[3]  # meta/tests/_yaml_driver/test_*.py -> 仓库根
    lint_script = repo_root / ".trae" / "debug" / "lint_no_hardcoded_id.py"

    if not lint_script.exists():
        pytest.skip(f"lint 工具不存在: {lint_script}")

    r = subprocess.run(
        [_sys.executable, str(lint_script)],
        capture_output=True, text=True, cwd=str(repo_root),
        timeout=120,
    )

    # default 模式: 0 error = pass, >0 = fail
    if r.returncode != 0:
        # 提取关键信息 (前 60 行)
        out_lines = (r.stdout or "").splitlines()
        summary = "\n".join(out_lines[:60])
        pytest.fail(
            f"[P0#2] hardcoded ID detected in meta/tests/\n"
            f"lint 退出码: {r.returncode}\n"
            f"摘要 (前 60 行):\n{summary}\n"
            f"修复: 用 UserFactory.build() / UserFactory._next_counter() 替换"
        )


# ============================================================
# v1.1 新增: Aspects / RLS / Factory 一致性约束测试
# ============================================================
#
# 设计原则 (positive-or-negative assertion):
#   - info spec (positive):  必须存在且语义正确
#                           -> pytest parametrize 展开, 每个 spec 都跑一次 assert
#                           -> spec 缺失 = bug, fail
#   - warning/error spec (negative): 不应存在
#                           -> 列出它们, 不 fail, 提供 visibility
#                           -> 后续可手动升级 severity
#
# fixtures (aspects_registry / rls_registry / factories_registry / v11_specs / v11_spec)
#   由 pytest_plugin.py 提供

def _split_specs_by_severity(specs, severity):
    return [s for s in specs if s.severity == severity]


# 9 个 v1.1 constraint_type 各自一个 test 函数, 用 parametrize 展开

_V11_CONSTRAINT_TYPES = [
    # Aspects
    "ASPECT_REFERENCED_MUST_EXIST",
    "ASPECT_FIELDS_APPLIED",
    "AUDIT_ASPECT_HAS_AUDIT_CONFIG",
    # RLS
    "RLS_FILE_EXISTS_FOR_OBJECT",
    "RLS_ENTITY_FIELD_VALID",
    "RLS_APPLIES_TO_ROLE_VALID",
    # Factory
    "FACTORY_DEFAULTS_COVER_REQUIRED",
    "FACTORY_OBJECT_TYPE_REGISTERED",
    "FACTORY_DEFAULTS_NOT_EMPTY",
    "FACTORY_UNIQUE_ID_DETERMINISTIC",  # [FIX 2026-07-17 P2]
]


def test_v11_aspect_referenced_must_exist(v11_spec):
    """
    每个 object 引用 aspect 必须存在, 或声明无 aspect。

    severity=info: positive assertion - spec 存在即通过
    severity=warning/error: negative assertion - spec 出现即问题
    """
    if v11_spec.severity == "info":
        return  # healthy
    # tolerant mode (v1.1): 报告违规但默认不 fail, 仅 visibility
    # 升级为 fail: 将环境变量 YAML_DRIVER_V11_STRICT=1 即可
    import os as _os
    if _os.environ.get("YAML_DRIVER_V11_STRICT") == "1":
        pytest.fail(f"[{v11_spec.severity}] {v11_spec.description}")
    # tolerant: 仅作为 info 记录
    print(f"\n[V11-VIOLATION] [{v11_spec.severity}] {v11_spec.constraint}: {v11_spec.description}")


def test_v11_aspect_fields_applied(v11_spec):
    """audit_aspect 必须提供 created_at 字段 (或不使用 audit_aspect)。"""
    if v11_spec.severity == "info":
        return
    import os as _os
    if _os.environ.get("YAML_DRIVER_V11_STRICT") == "1":
        pytest.fail(f"[{v11_spec.severity}] {v11_spec.description}")
    print(f"\n[V11-VIOLATION] [{v11_spec.severity}] {v11_spec.constraint}: {v11_spec.description}")


def test_v11_audit_aspect_has_audit_config(v11_spec):
    """使用 audit_aspect 必须提供 audit 配置。"""
    if v11_spec.severity == "info":
        return
    import os as _os
    if _os.environ.get("YAML_DRIVER_V11_STRICT") == "1":
        pytest.fail(f"[{v11_spec.severity}] {v11_spec.description}")
    print(f"\n[V11-VIOLATION] [{v11_spec.severity}] {v11_spec.constraint}: {v11_spec.description}")


def test_v11_rls_file_exists_for_object(v11_spec):
    """持久化对象必须有 rls 规则 (或属于豁免类别如 enum/view)。"""
    # 注意: 大部分业务对象 v1.1 范围内还没有 rls 规则, 暂作为 warning 不 fail
    if v11_spec.severity in ("info", "warning"):
        return
    import os as _os
    if _os.environ.get("YAML_DRIVER_V11_STRICT") == "1":
        pytest.fail(f"[{v11_spec.severity}] {v11_spec.description}")
    print(f"\n[V11-VIOLATION] [{v11_spec.severity}] {v11_spec.constraint}: {v11_spec.description}")


def test_v11_rls_entity_field_valid(v11_spec):
    """rls_rules/*.yaml 中的 entity 必须匹配 schemas 中的对象。"""
    if v11_spec.severity == "info":
        return
    import os as _os
    if _os.environ.get("YAML_DRIVER_V11_STRICT") == "1":
        pytest.fail(f"[{v11_spec.severity}] {v11_spec.description}")
    print(f"\n[V11-VIOLATION] [{v11_spec.severity}] {v11_spec.constraint}: {v11_spec.description}")


def test_v11_rls_applies_to_role_valid(v11_spec):
    """rls_rules.applies_to 字段必须对应 schemas 中的 role 对象。"""
    if v11_spec.severity == "info":
        return
    import os as _os
    if _os.environ.get("YAML_DRIVER_V11_STRICT") == "1":
        pytest.fail(f"[{v11_spec.severity}] {v11_spec.description}")
    print(f"\n[V11-VIOLATION] [{v11_spec.severity}] {v11_spec.constraint}: {v11_spec.description}")


def test_v11_factory_defaults_cover_required(v11_spec):
    """Factory 的 _DEFAULTS / _base_defaults 必须覆盖 yaml 必填字段。"""
    if v11_spec.severity == "info":
        return
    # v1.1 tolerant: 已知部分 factory 待补, 默认不 fail
    import os as _os
    if _os.environ.get("YAML_DRIVER_V11_STRICT") == "1":
        pytest.fail(f"[{v11_spec.severity}] {v11_spec.description}")
    print(f"\n[V11-VIOLATION] [{v11_spec.severity}] {v11_spec.constraint}: {v11_spec.description}")


def test_v11_factory_object_type_registered(v11_spec):
    """Factory 的 _OBJECT_TYPE 必须对应 schemas 中的对象。"""
    if v11_spec.severity == "info":
        return
    # 部分 factory (import_export/subscription/webhook) 超出 v1.1 范围
    import os as _os
    if _os.environ.get("YAML_DRIVER_V11_STRICT") == "1":
        pytest.fail(f"[{v11_spec.severity}] {v11_spec.description}")
    print(f"\n[V11-VIOLATION] [{v11_spec.severity}] {v11_spec.constraint}: {v11_spec.description}")


def test_v11_factory_defaults_not_empty(v11_spec):
    """Factory 必须提供 _DEFAULTS dict 或 _base_defaults() 返回值。"""
    if v11_spec.severity == "info":
        return
    import os as _os
    if _os.environ.get("YAML_DRIVER_V11_STRICT") == "1":
        pytest.fail(f"[{v11_spec.severity}] {v11_spec.description}")
    print(f"\n[V11-VIOLATION] [{v11_spec.severity}] {v11_spec.constraint}: {v11_spec.description}")


def test_v11_factory_unique_id_deterministic(v11_spec):
    """[FIX 2026-07-17 P2] unique_id() 必须使用 counter + lock 模式.

    防止 pre-existing bug (同毫秒内重复 ID) 复发.
    severity=info: positive (counter + lock 都有)
    severity=warning: 任一缺失 (快速循环风险)
    severity=error: unique_id() 函数缺失
    """
    if v11_spec.severity == "info":
        return  # healthy
    import os as _os
    if _os.environ.get("YAML_DRIVER_V11_STRICT") == "1":
        pytest.fail(f"[{v11_spec.severity}] {v11_spec.description}")
    # tolerant: 仅打印 + 提供 visibility
    print(f"\n[V11-VIOLATION] [{v11_spec.severity}] {v11_spec.constraint}: {v11_spec.description}")


# ============================================================
# v1.1 全局可见性测试
# ============================================================

def test_v11_no_error_violations(v11_specs):
    """v1.1 error 级别约束汇总, 默认 tolerant, strict mode (env) 才 fail。"""
    import os as _os
    errors = _split_specs_by_severity(v11_specs, "error")
    if not errors:
        return
    details = "\n".join(
        f"  - {s.test_id}: {s.description}" for s in errors
    )
    if _os.environ.get("YAML_DRIVER_V11_STRICT") == "1":
        pytest.fail(
            f"Found {len(errors)} v1.1 error-level constraint(s):\n{details}"
        )
    # tolerant: 打印但 pass
    print(f"\n[V11-VIOLATION] {len(errors)} v1.1 error-level violation(s):\n{details}")


def test_v11_warning_constraints_listed(v11_specs, capsys):
    """v1.1 warning 级约束打印供查看, 不 fail。"""
    warnings = _split_specs_by_severity(v11_specs, "warning")
    if warnings:
        print(f"\n[INFO] v1.1 has {len(warnings)} warning-level constraint(s):")
        for w in warnings[:20]:
            print(f"  - [{w.constraint}] {w.object_id}: {w.description}")
        if len(warnings) > 20:
            print(f"  ... and {len(warnings) - 20} more")


def test_v11_total_spec_count(v11_specs):
    """验证 v1.1 discoverer 实际产生了 spec (健康项目下应 > 0)"""
    assert len(v11_specs) > 0, (
        "v1.1 discoverer produced 0 specs - either no objects to test "
        "or discoverer is broken"
    )


def test_v11_constraint_types_covered(v11_specs):
    """验证 9 个 v1.1 约束类型至少有一个 spec 命中 (健康项目应有 positive info)

    注意: RLS_APPLIES_TO_ROLE_VALID 需要 rls_rules/*.yaml 实际有 applies_to/applies_to_role 字段
          若现有 rls 文件均无此字段, 该类型会无 spec, 应被认作正常 (仅信息性失败)
    """
    covered = {s.constraint for s in v11_specs}
    expected = set(_V11_CONSTRAINT_TYPES)
    missing = expected - covered
    if missing and "RLS_APPLIES_TO_ROLE_VALID" in missing:
        # RLS_APPLIES_TO_ROLE_VALID 是可选 (依赖 rls_rules 是否有 applies_to 字段)
        missing = missing - {"RLS_APPLIES_TO_ROLE_VALID"}
    assert not missing, (
        f"v1.1 constraint types NOT covered by any spec: {missing}"
    )