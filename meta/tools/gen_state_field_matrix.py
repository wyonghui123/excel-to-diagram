# -*- coding: utf-8 -*-
"""生成「状态 × 字段」矩阵（Spec §5 R-MM-03 R10/R11/R14）。

产物：`meta/generated/state_field_matrix.yaml`

约定：
- **只读生成物，不是判定源**。运行期判定仍走 `FieldPolicyEngine`：
  `state_field_policies`（显式声明）→ `document_invariants.derive_default_state_policy`
  （过账只读兜底）。本文件只用于覆盖度 diff 与前端版本失效。
- `version` = 内容哈希前 12 位；内容不变则字节一致（R11 幂等）。
- 过渡态（非 `category: initial`）的 `writable_fields` 默认 `[]`；初始态才展开可写字段。
- `--check`：产物与磁盘不一致时退出 1，供 lint / CI 使用。

用法：
    python -m meta.tools.gen_state_field_matrix            # 重新生成
    python -m meta.tools.gen_state_field_matrix --check    # 只校验
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml as _pyyaml  # noqa: E402  # 写盘用 PyYAML

SCHEMAS_DIR = ROOT / "meta" / "schemas"
OUT_PATH = ROOT / "meta" / "generated" / "state_field_matrix.yaml"

#: 过账后不可再改的单据头部字段（按 document: 段声明推导，无声明则为空）。
POSTING_LOCK_KEYS = ("number_field", "business_date_field", "document_type_field")


def _own_fields(raw) -> list:
    """对象自身字段 id（不含切面注入字段）。"""
    names = []
    for item in raw.get("fields") or ():
        if isinstance(item, dict) and item.get("id"):
            names.append(str(item["id"]))
    return names


def _state_categories(raw) -> dict:
    """states[] -> {code: category}。"""
    mapping = {}
    for item in raw.get("states") or ():
        if isinstance(item, dict) and item.get("code"):
            mapping[str(item["code"])] = str(item.get("category") or "")
    return mapping


def _as_list(value) -> list:
    return [str(v) for v in value] if isinstance(value, (list, tuple)) else []


def _policy_entry(state, policy, fields, categories) -> dict:
    policy = policy if isinstance(policy, dict) else {}
    readonly = sorted(set(_as_list(policy.get("readonly"))))
    hidden = sorted(set(_as_list(policy.get("hidden"))))
    required = sorted(set(_as_list(policy.get("required"))))
    if categories.get(state) == "initial":
        blocked = set(readonly) | set(hidden)
        writable = sorted(f for f in fields if f not in blocked)
    else:
        # R11：过渡态默认不可写，避免「没声明 = 可写」的隐式放行。
        writable = []
    return {
        "readonly": readonly,
        "hidden": hidden,
        "required": required,
        "writable_fields": writable,
    }


def _collect():
    objects = {}
    fact_ids = []
    declared_ids = []
    errors = []

    for path in sorted(SCHEMAS_DIR.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        try:
            raw = _pyyaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # noqa: BLE001
            errors.append({"file": path.name, "error": str(exc)})
            continue
        if not isinstance(raw, dict):
            continue
        object_id = str(raw.get("id") or path.stem)
        document = raw.get("document") if isinstance(raw.get("document"), dict) else {}
        declared = raw.get("state_field_policies") if isinstance(
            raw.get("state_field_policies"), dict) else {}

        # 事实单据 = 声明了单据画像，或已声明状态字段矩阵（spec §5.2 的 15 张口径）。
        if not document and not declared:
            continue

        fact_ids.append(object_id)
        fields = _own_fields(raw)
        categories = _state_categories(raw)
        state_field = str(document.get("state_field") or "")
        posting_state = str(document.get("posting_state") or "")

        states = {}
        for state in sorted(declared):
            states[str(state)] = _policy_entry(str(state), declared.get(state), fields, categories)

        source = "declared" if declared else "none"
        if posting_state and posting_state not in states:
            locked = [str(document.get(k)) for k in POSTING_LOCK_KEYS if document.get(k)]
            states[posting_state] = _policy_entry(
                posting_state, {"readonly": locked}, fields, categories)
            source = "derived" if source == "none" else source
        if not states:
            source = "none"

        if declared:
            declared_ids.append(object_id)

        objects[object_id] = {
            "schema": path.name,
            "state_field": state_field,
            "posting_state": posting_state,
            "source": source,
            "states": {k: states[k] for k in sorted(states)},
        }

    coverage = {
        "total": len(fact_ids),
        "covered": len(declared_ids),
        "uncovered": sorted(set(fact_ids) - set(declared_ids)),
    }
    return objects, coverage, errors


def _content_hash(objects, coverage) -> str:
    blob = json.dumps({"objects": objects, "coverage": coverage},
                      ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def _build_payload(objects, coverage, errors) -> dict:
    return {
        "version": _content_hash(objects, coverage),
        "generated_by": "meta/tools/gen_state_field_matrix.py",
        "note": "派生只读产物：不是判定源，判定走 state_field_policies + FieldPolicyEngine",
        "coverage": coverage,
        "objects": objects,
        "errors": errors,
    }


def _render(payload) -> str:
    header = (
        "# 由 meta/tools/gen_state_field_matrix.py 生成，请勿手工编辑（Spec §5 R10）。\n"
        "# 只读派生：判定源是 state_field_policies / field_policies；本文件仅用于覆盖度 diff\n"
        "# 与前端版本失效。重新生成：python -m meta.tools.gen_state_field_matrix\n"
    )
    return header + _pyyaml.safe_dump(payload, allow_unicode=True, sort_keys=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="只校验产物是否与磁盘一致，不一致退出 1")
    args = parser.parse_args()

    objects, coverage, errors = _collect()
    payload = _build_payload(objects, coverage, errors)
    text = _render(payload)

    if args.check:
        current = (OUT_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
                   if OUT_PATH.exists() else "")
        problems = []
        if not OUT_PATH.exists():
            problems.append("产物不存在：%s" % OUT_PATH)
        elif current != text:
            problems.append("产物与当前 schema 不一致，请重新生成")
        for item in problems:
            print("[FAIL] %s" % item)
        if problems:
            return 1
        print("[OK] state_field_matrix 一致（version=%s，覆盖 %d/%d）" % (
            payload["version"], coverage["covered"], coverage["total"]))
        return 0

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # 固定 LF：避免 Windows 文本模式写出 CRLF，导致 --check 与 git diff 噪音
    with open(OUT_PATH, "w", encoding="utf-8", newline="\n") as fp:
        fp.write(text)
    print("[OK] 生成 %s（version=%s，覆盖 %d/%d，未覆盖 %d 个）" % (
        OUT_PATH, payload["version"], coverage["covered"], coverage["total"],
        len(coverage["uncovered"])))
    if coverage["uncovered"]:
        print("[INFO] 未覆盖清单：%s" % ", ".join(coverage["uncovered"]))
    if errors:
        print("[WARN] 装载失败 %d 个：%s" % (
            len(errors), ", ".join(e["file"] for e in errors)))
    return 0


if __name__ == "__main__":
    sys.exit(main())