# -*- coding: utf-8 -*-
"""R-MM-03「状态 × 字段」矩阵元模型测试（Spec §5 验收 A-03-1/3/4/5）。

覆盖：
  · A-03-1：lint 披露事实单据覆盖率 + 未覆盖清单（不臆造声明）；
  · A-03-3：顶层 field_policies 声明数 ≥ 3；
  · A-03-4：确认态写入被拒 → 400 + field_not_writable_in_state；
  · A-03-5：矩阵生成幂等（两次字节一致，且与磁盘产物一致）。
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import yaml  # noqa: E402

from meta.core.exceptions import FieldPolicyViolationError  # noqa: E402
from meta.core.models import (  # noqa: E402
    MetaField,
    MetaObject,
    MetaStateDefinition,
    MetaStateFieldPolicy,
    MetaStateTransition,
)
from meta.services.field_policy_validation import (  # noqa: E402
    FieldPolicyValidationInterceptor,
)
from meta.tools.gen_state_field_matrix import (  # noqa: E402
    OUT_PATH as MATRIX_PATH,
    _build_payload,
    _collect,
    _render,
)
from meta.tools.lint_metamodel import (  # noqa: E402
    SCHEMAS_DIR,
    _seed_role_codes,
    lint_field_policies,
)


def _f(field_id, name):
    return MetaField(id=field_id, name=name, field_type="number", db_column=field_id)


def _build_object():
    return MetaObject(
        id="po_state_test",
        name="状态矩阵测试",
        table_name="po_state_test",
        fields=[_f("amount", "金额"), _f("remark", "备注")],
        rules=[
            MetaStateTransition(
                id="po_confirm", name="确认", state_field="status",
                from_states=["draft"], to_state="confirmed",
            ),
        ],
        states=[
            MetaStateDefinition(code="draft", label="草稿", category="initial", seq=1),
            MetaStateDefinition(code="confirmed", label="已确认", seq=2),
        ],
        state_field_policies={
            "confirmed": MetaStateFieldPolicy(readonly=["amount"]),
        },
    )


class _DataSource:
    """最小数据源：load 返回旧行，让 validate_update 不退化到创建分支。"""

    def __init__(self, row):
        self._row = dict(row)

    def load(self, object_id):
        return dict(self._row)


def _load_schema(name):
    return yaml.safe_load((SCHEMAS_DIR / name).read_text(encoding="utf-8")) or {}


def test_a_03_1_lint_reports_full_fact_coverage_disclosure():
    violations, _scanned, report = lint_field_policies(_seed_role_codes())
    assert violations == []
    assert report["total"] == 15

    matrix = (_build_payload(*_collect()))
    # lint 覆盖度与生成物 coverage 必须同口径（同一套事实单据判定）
    assert report["covered"] == matrix["coverage"]["covered"]
    assert report["uncovered"] == matrix["coverage"]["uncovered"]


def test_a_03_3_field_policies_declared_at_least_three():
    declared = []
    for path in sorted(SCHEMAS_DIR.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(raw, dict) and isinstance(raw.get("field_policies"), dict):
            declared.append(raw.get("id") or path.stem)
    assert len(declared) >= 3, "顶层 field_policies 声明数不足：%s" % declared


def test_a_03_4_write_rejected_in_confirmed_state():
    interceptor = FieldPolicyValidationInterceptor(
        meta_object=_build_object(),
        data_source=_DataSource({"status": "confirmed", "amount": 100}),
    )
    result = interceptor.validate_update(1, {"amount": 200})
    assert result.valid is False
    codes = [e.error_code for e in result.errors]
    assert "field_not_writable_in_state" in codes


def test_a_03_4_rejection_error_carries_400():
    err = FieldPolicyViolationError("x", code="field_not_writable_in_state")
    assert err.code == "field_not_writable_in_state"
    assert err.status_code == 400


def test_a_03_4_purchase_order_declares_posting_lock():
    raw = _load_schema("purchase_order.yaml")
    document = raw.get("document") or {}
    assert document.get("posting_state") == "confirmed"
    readonly = (raw.get("state_field_policies") or {}).get("confirmed", {}).get(
        "readonly") or []
    # 过账锁：编号 / 业务日期 / 单据类型在已确认态必须一起锁死
    for key in ("number_field", "business_date_field", "document_type_field"):
        assert document.get(key) in readonly


def test_a_03_5_matrix_generation_is_idempotent():
    first = _render(_build_payload(*_collect()))
    second = _render(_build_payload(*_collect()))
    assert first == second

    assert MATRIX_PATH.exists()
    on_disk = MATRIX_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert on_disk == first


_ASPECT_YAML = """\
doc_type_aspect:
  fields:
    - id: doc_type_id
      name: 单据类型
      type: string
      db_column: doc_type_id
"""

_PO_TEMPLATE = """\
id: {object_id}
name: 演示单据
table_name: {object_id}
aspects: {aspects}
fields:
  - id: status
    name: 状态
    type: string
states:
  - code: draft
    label: 草稿
    category: initial
  - code: confirmed
    label: 已确认
state_field_policies:
  confirmed:
    readonly:
      - doc_type_id
"""


def test_s1_state_matrix_accepts_aspect_injected_fields(tmp_path):
    """P0 回归：state_field_policies 可引用本对象 aspects 注入的字段。"""
    from meta.core.yaml_loader import parse_meta_object

    (tmp_path / "aspects.yaml").write_text(_ASPECT_YAML, encoding="utf-8")
    data = yaml.safe_load(_PO_TEMPLATE.format(
        object_id="demo_with_aspect", aspects="[doc_type_aspect]"))
    obj = parse_meta_object(data, str(tmp_path / "demo_with_aspect.yaml"))

    # 切面字段不并入 obj.fields（装载语义不变），但 S1 ⑤ 校验接纳
    assert "doc_type_id" not in {f.id for f in obj.fields}
    assert obj.state_field_policies["confirmed"].readonly == ["doc_type_id"]


def test_s1_state_matrix_rejects_undeclared_aspect_field(tmp_path):
    """反向夹具：未声明 aspects 却引用切面字段 → S1 fail-fast。"""
    from meta.core.yaml_loader import parse_meta_object

    (tmp_path / "aspects.yaml").write_text(_ASPECT_YAML, encoding="utf-8")
    data = yaml.safe_load(_PO_TEMPLATE.format(
        object_id="demo_without_aspect", aspects="[]"))

    try:
        parse_meta_object(data, str(tmp_path / "demo_without_aspect.yaml"))
    except ValueError as exc:
        assert "不存在的字段" in str(exc) and "doc_type_id" in str(exc)
    else:
        raise AssertionError("未声明 aspects 时引用切面字段应触发 S1 校验失败")


def test_a_03_1_purchase_order_loads_after_aspect_policy(tmp_path):
    """P0 回归：真实 purchase_order.yaml 必须可装载（document_type_id 过账锁合法）。"""
    from meta.core.yaml_loader import load_yaml_file

    obj = load_yaml_file(str(SCHEMAS_DIR / "purchase_order.yaml"))
    assert obj is not None, "purchase_order.yaml 装载失败（S1 校验回归）"
    assert obj.id == "purchase_order"


def test_lint_field_policies_scopes_aspect_fields_per_object(tmp_path, monkeypatch):
    """lint 不得用切面字段全局并集：未声明 aspects 的对象引用切面字段须报违规。"""
    import meta.tools.lint_metamodel as lint_metamodel

    (tmp_path / "aspects.yaml").write_text(_ASPECT_YAML, encoding="utf-8")
    (tmp_path / "with_aspect.yaml").write_text(_PO_TEMPLATE.format(
        object_id="with_aspect", aspects="[doc_type_aspect]"), encoding="utf-8")
    (tmp_path / "without_aspect.yaml").write_text(_PO_TEMPLATE.format(
        object_id="without_aspect", aspects="[]"), encoding="utf-8")

    monkeypatch.setattr(lint_metamodel, "SCHEMAS_DIR", tmp_path)
    violations, _scanned, _report = lint_field_policies(_seed_role_codes())

    labels = {v[0] for v in violations}
    assert "with_aspect.yaml" not in labels
    assert "without_aspect.yaml" in labels