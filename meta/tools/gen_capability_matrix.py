# -*- coding: utf-8 -*-
"""生成 archetype × capability 矩阵（Spec §12.4 R27）。

产物：`meta/generated/bo_capability_matrix.yaml`

约定：
- **只读生成物，不是判定源**。运行期判定仍走 yaml_loader / 对象自身的显式声明；
  本文件只用于「哪些对象缺哪项能力」的可视化与缺口审计。
- `version` = 内容哈希前 12 位（受控枚举 + 别名 + archetype 映射 + 能力判定规则
  + 对象清单）；内容不变则哈希不变，可与磁盘产物直接比对。
- `--check`：产物与磁盘不一致，或存在不在受控枚举内的 archetype 时退出 1，
  供 CI / lint 使用（替代不存在的 lint_metamodel）。

用法：
    python -m meta.tools.gen_capability_matrix            # 重新生成
    python -m meta.tools.gen_capability_matrix --check    # 只校验
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 静音 yaml_loader 的逐文件 Loaded 输出（约 150 行），只影响本次进程
os.environ.setdefault("TEST_ENTRY", "1")

from meta.core import yaml_compat as yaml  # noqa: E402
import yaml as _pyyaml  # noqa: E402  # yaml_compat 只提供 safe_load，写盘用 PyYAML
from meta.core.models_enums import (  # noqa: E402
    ARCHETYPE_TO_BO_CATEGORY,
    SEMANTICS_CATEGORY_ALIASES,
    ObjectSemanticsCategory,
)
from meta.core.yaml_loader import load_yaml_file  # noqa: E402

SCHEMAS_DIR = ROOT / "meta" / "schemas"
OUT_PATH = ROOT / "meta" / "generated" / "bo_capability_matrix.yaml"

#: 能力名 → 判定规则说明（写进产物，变更即改哈希）
CAPABILITIES = {
    "audit": "audit.enabled（缺省 true = 平台基线审计）",
    "numbering": "numbering 段非空",
    "state_machine": "requires_state_machine 或 states 非空",
    "posting": "doc_effect 段非空",
    "soft_delete": "deletion_policy.soft_delete.enabled",
    "revision": "revision_policy 已声明",
}

#: 能力 → 对象 id → 理由：语义上「不适用」，不计入 gaps。
#: 必须落到单对象判定，不做 archetype 级白名单 —— 同一 archetype 内既有确需该能力的对象，
#: 也有台账行对象（过账由父单据的 doc_effect 真实执行，自身不该有 posting）。
NOT_APPLICABLE = {
    "posting": {
        "inventory_transaction": "库存台账行：过账由 inventory_adjustment / receipt / shipment 的 doc_effect 执行",
        "serial_transaction": "序列号台账行：过账随父单据执行",
        "hu_transaction": "包装单元台账行：过账随父单据执行",
    },
}

#: 能力名 → 该能力在 YAML 中的声明段（用于标注 source = declared / absent）
DECLARED_SECTIONS = {
    "audit": ("audit",),
    "numbering": ("numbering",),
    "state_machine": ("requires_state_machine", "states"),
    "posting": ("doc_effect",),
    "soft_delete": ("deletion_policy",),
    "revision": ("revision_policy",),
}


def _soft_delete_enabled(policy) -> bool:
    """deletion_policy.soft_delete 兼容 dataclass 与原始 dict 两种形态。"""
    if policy is None:
        return False
    soft = getattr(policy, "soft_delete", None)
    if soft is None and isinstance(policy, dict):
        soft = policy.get("soft_delete")
    if soft is None:
        return False
    if isinstance(soft, dict):
        return bool(soft.get("enabled", False))
    return bool(getattr(soft, "enabled", False))


def _capability_enabled(obj, cap: str) -> bool:
    """从装载后的对象读取能力开闭（不回落到 category_config，避免模板隐式扩散）。"""
    if cap == "audit":
        return bool(getattr(getattr(obj, "audit", None), "enabled", False))
    if cap == "numbering":
        return bool(getattr(obj, "numbering", None))
    if cap == "state_machine":
        return bool(getattr(obj, "state_machine_required", False)
                    or getattr(obj, "states", None))
    if cap == "posting":
        return bool(getattr(obj, "doc_effect", None))
    if cap == "soft_delete":
        return _soft_delete_enabled(getattr(obj, "deletion_policy", None))
    if cap == "revision":
        return getattr(obj, "revision_policy", None) is not None
    raise KeyError(cap)


def _collect():
    """扫描 meta/schemas 下的对象 YAML，返回 (按 archetype 分组的记录, 未分类, 错误)。"""
    grouped = {}
    unclassified = []
    errors = []
    scanned = 0

    for path in sorted(SCHEMAS_DIR.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # noqa: BLE001
            errors.append({"file": path.name, "error": "raw-yaml: %s" % exc})
            continue
        if not isinstance(raw, dict) or not raw.get("id"):
            continue

        try:
            obj = load_yaml_file(str(path))
        except Exception as exc:  # noqa: BLE001
            errors.append({"file": path.name, "error": "load: %s" % exc})
            continue
        if obj is None:
            continue

        scanned += 1
        archetype = getattr(getattr(obj, "semantics", None), "category", "") or ""
        explicit = raw.get("bo_category")
        if explicit:
            bo_source = "override"
        elif archetype:
            bo_source = "template"
        else:
            bo_source = "absent"

        caps = {}
        for cap in CAPABILITIES:
            enabled = _capability_enabled(obj, cap)
            declared = any(sec in raw for sec in DECLARED_SECTIONS[cap])
            caps[cap] = {
                "enabled": enabled,
                "source": "declared" if declared else ("default" if enabled else "absent"),
            }

        record = {
            "id": obj.id,
            "file": path.name,
            "bo_category": getattr(getattr(obj, "bo_category", None), "value", None),
            "bo_category_source": bo_source,
            "capabilities": caps,
        }
        if archetype:
            grouped.setdefault(archetype, []).append(record)
        else:
            unclassified.append(record)

    return grouped, unclassified, errors, scanned


def _build_payload(grouped, unclassified, errors, scanned):
    archetypes = {}
    for archetype in sorted(grouped):
        records = sorted(grouped[archetype], key=lambda r: r["id"])
        total = len(records)
        caps = {}
        for cap in CAPABILITIES:
            enabled = sum(1 for r in records if r["capabilities"][cap]["enabled"])
            declared = sum(1 for r in records
                           if r["capabilities"][cap]["source"] == "declared")
            caps[cap] = {
                "enabled": enabled,
                "declared": declared,
                "total": total,
                "coverage": "%d/%d" % (enabled, total),
            }
        # 缺口清单：逐对象枚举缺该能力的对象 id（剔除 NOT_APPLICABLE 的语义不适用对象）
        not_applicable = {}
        gaps = {}
        for cap in CAPABILITIES:
            na_ids = {r["id"]: NOT_APPLICABLE[cap][r["id"]]
                      for r in records if r["id"] in NOT_APPLICABLE.get(cap, {})}
            if na_ids:
                not_applicable[cap] = na_ids
            missing = [r["id"] for r in records
                       if not r["capabilities"][cap]["enabled"] and r["id"] not in na_ids]
            if missing:
                gaps[cap] = missing
        bo_categories = {}
        for r in records:
            key = r["bo_category"] or "absent"
            bo_categories[key] = bo_categories.get(key, 0) + 1
        archetypes[archetype] = {
            "bo_category": (
                ARCHETYPE_TO_BO_CATEGORY[ObjectSemanticsCategory(archetype)].value
                if archetype in {c.value for c in ObjectSemanticsCategory}
                else None
            ),
            "bo_category_breakdown": bo_categories,
            "objects": [r["id"] for r in records],
            "capabilities": caps,
            "gaps": gaps,
            "not_applicable": not_applicable,
        }

    return {
        "version": _content_hash(archetypes, unclassified),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scan": {
            "schemas_dir": "meta/schemas",
            "yaml_scanned": scanned,
            "classified": sum(len(v) for v in grouped.values()),
            "unclassified": len(unclassified),
            "errors": len(errors),
            "basis": "装载后对象属性；不读 category_config 模板（避免隐式能力扩散）",
        },
        "capability_rules": CAPABILITIES,
        "archetypes": archetypes,
        "unclassified_objects": sorted(r["id"] for r in unclassified),
        "errors": errors,
    }


def _content_hash(archetypes, unclassified) -> str:
    """内容哈希：枚举 + 别名 + 映射 + 判定规则 + 对象/能力结果。"""
    basis = {
        "enum": [c.value for c in ObjectSemanticsCategory],
        "aliases": {k: v.value for k, v in SEMANTICS_CATEGORY_ALIASES.items()},
        "archetype_map": {k.value: v.value for k, v in ARCHETYPE_TO_BO_CATEGORY.items()},
        "capabilities": CAPABILITIES,
        "archetypes": archetypes,
        "unclassified": sorted(r["id"] for r in unclassified),
    }
    blob = json.dumps(basis, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def _render(payload) -> str:
    header = (
        "# 由 meta/tools/gen_capability_matrix.py 生成，请勿手工编辑（Spec §12.4 R27）。\n"
        "# 只读生成物，不是运行期判定源；重新生成请执行 --check 之外的默认模式。\n"
    )
    return header + _pyyaml.safe_dump(payload, allow_unicode=True, sort_keys=False)


def _without_timestamp(text: str) -> str:
    """剔除易变的时间戳行，用于 --check 的稳定比对（version 已覆盖内容变化）。"""
    return "\n".join(line for line in text.splitlines()
                     if not line.startswith("generated_at:"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="只校验产物是否与磁盘一致，不一致退出 1")
    args = parser.parse_args()

    grouped, unclassified, errors, scanned = _collect()
    payload = _build_payload(grouped, unclassified, errors, scanned)
    text = _render(payload)

    unknown = sorted(k for k in grouped if k not in {c.value for c in ObjectSemanticsCategory})

    if args.check:
        exists = OUT_PATH.exists()
        current = (OUT_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
                   if exists else "")
        problems = []
        if not exists:
            problems.append("产物不存在：%s" % OUT_PATH)
        elif _without_timestamp(current) != _without_timestamp(text):
            problems.append("产物与当前 schema 不一致，请重新生成")
        if unknown:
            problems.append("未知 semantics.category：%s" % ", ".join(unknown))
        if errors:
            problems.append("装载失败 %d 个：%s" % (
                len(errors), ", ".join(e["file"] for e in errors)))
        for item in problems:
            print("[FAIL] %s" % item)
        if problems:
            return 1
        print("[OK] capability matrix 一致（version=%s）" % payload["version"])
        return 0

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # 固定 LF：避免 Windows 文本模式写出 CRLF，导致 --check 与 git diff 噪音
    with open(OUT_PATH, "w", encoding="utf-8", newline="\n") as fp:
        fp.write(text)
    print("[OK] 生成 %s（version=%s，对象 %d 个，archetype %d 类，未分类 %d 个）" % (
        OUT_PATH, payload["version"], payload["scan"]["classified"],
        len(payload["archetypes"]), payload["scan"]["unclassified"]))
    if unknown:
        print("[WARN] 未知 semantics.category：%s" % ", ".join(unknown))
    if errors:
        print("[WARN] 装载失败 %d 个：%s" % (
            len(errors), ", ".join(e["file"] for e in errors)))
    return 0


if __name__ == "__main__":
    sys.exit(main())