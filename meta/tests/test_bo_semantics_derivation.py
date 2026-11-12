# -*- coding: utf-8 -*-
"""R25 / R26 / R27 能力维度派生测试（Spec §12 验收 A-12-2/A-12-3/A-12-4）。

覆盖：
  · A-12-2：别名归一只在读取层发生，YAML 零改动；
  · A-12-3：`bo_category` 派生优先级 显式 > 模板 > 默认，矩阵标 `bo_category_source`；
  · A-12-4：矩阵可重建、`version` 为内容哈希、产物不在 schema 扫描路径内、
    生产代码不读取生成物（不作判定源）。
"""

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from meta.core import yaml_compat as yaml  # noqa: E402
from meta.core.models_enums import (  # noqa: E402
    ARCHETYPE_TO_BO_CATEGORY,
    BusinessObjectCategory,
    ObjectSemanticsCategory,
    SEMANTICS_CATEGORY_ALIASES,
)
from meta.core.yaml_loader import load_yaml_file, parse_meta_object  # noqa: E402
from meta.tools.gen_capability_matrix import (  # noqa: E402
    OUT_PATH as CAP_MATRIX_PATH,
    SCHEMAS_DIR,
    _build_payload,
    _collect,
    _content_hash,
    _render,
    _without_timestamp,
)


def _doc(**extra):
    base = {"id": "demo_bo", "name": "示例", "table_name": "demo_bo", "fields": []}
    base.update(extra)
    return base


def _find_record(records, object_id):
    for record in records:
        if record["id"] == object_id:
            return record
    return None


def test_a_12_2_alias_normalized_at_load_only():
    alias, expected = next(iter(SEMANTICS_CATEGORY_ALIASES.items()))
    obj = parse_meta_object(_doc(semantics={"category": alias}))
    assert obj.semantics.category == expected.value
    assert isinstance(obj.semantics.category, str)

    # 真实 YAML 零改动：allocation_result.yaml 仍写 transactional，装载后归一
    raw = yaml.safe_load(
        (SCHEMAS_DIR / "allocation_result.yaml").read_text(encoding="utf-8")) or {}
    assert (raw.get("semantics") or {}).get("category") == "transactional"
    loaded = load_yaml_file(str(SCHEMAS_DIR / "allocation_result.yaml"))
    assert loaded is not None
    assert loaded.semantics.category == ObjectSemanticsCategory.BUSINESS_DOCUMENT.value


def test_a_12_3_bo_category_priority_override_template_default():
    # 1) 显式 bo_category 覆盖模板映射
    override = parse_meta_object(_doc(
        semantics={"category": "business_document"}, bo_category="configuration"))
    assert override.bo_category is BusinessObjectCategory.CONFIGURATION

    # 2) 无显式声明 → 模板映射
    template = parse_meta_object(_doc(semantics={"category": "business_document"}))
    assert template.bo_category is ARCHETYPE_TO_BO_CATEGORY[
        ObjectSemanticsCategory.BUSINESS_DOCUMENT]

    # 3) 两者皆无 → dataclass 默认 MASTER_DATA
    absent = parse_meta_object(_doc())
    assert absent.bo_category is BusinessObjectCategory.MASTER_DATA


def test_a_12_3_matrix_records_bo_category_source():
    grouped, unclassified, _errors, _scanned = _collect()
    records = [r for items in grouped.values() for r in items] + unclassified
    sources = {r["bo_category_source"] for r in records}
    assert sources <= {"override", "template", "absent"}
    assert "override" in sources and "template" in sources

    purchase_order = _find_record(records, "purchase_order")
    assert purchase_order is not None
    assert purchase_order["bo_category_source"] == "template"
    assert purchase_order["bo_category"] == "transactional"

    menu = _find_record(records, "menu")
    assert menu is not None
    assert menu["bo_category_source"] == "override"
    assert menu["bo_category"] == "configuration"


def test_a_12_4_matrix_version_is_content_hash_and_reproducible():
    payload = _build_payload(*_collect())
    version = payload["version"]
    assert re.fullmatch(r"[0-9a-f]{12}", version)

    # 同等输入两次生成，version 与内容一致（可重建）
    assert _build_payload(*_collect())["version"] == version

    # 内容变化 → version 变化
    perturbed = dict(payload["archetypes"])
    perturbed["__probe__"] = {"objects": ["__probe__"]}
    assert _content_hash(perturbed, payload["unclassified_objects"]) != version

    # 磁盘产物与当前 schema 一致（忽略易变时间戳）
    assert CAP_MATRIX_PATH.exists()
    on_disk = CAP_MATRIX_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert _without_timestamp(on_disk) == _without_timestamp(_render(payload))


def test_a_12_4_generated_dir_outside_schema_scan():
    generated_dir = CAP_MATRIX_PATH.parent
    assert generated_dir.name == "generated"
    assert generated_dir != SCHEMAS_DIR
    assert SCHEMAS_DIR not in generated_dir.parents
    assert "请勿手工编辑" in CAP_MATRIX_PATH.read_text(encoding="utf-8")


def test_a_12_4_generated_matrix_not_used_as_decision_source():
    """生产代码（meta/ 下非 tools / 非 tests）不得读取生成物。"""
    offenders = []
    pattern = re.compile(r"meta/generated|generated/bo_capability_matrix"
                         r"|generated/state_field_matrix")
    for path in (PROJECT_ROOT / "meta").rglob("*.py"):
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        if rel.startswith("meta/tools/") or "/tests/" in rel:
            continue
        if pattern.search(path.read_text(encoding="utf-8")):
            offenders.append(rel)
    assert offenders == []