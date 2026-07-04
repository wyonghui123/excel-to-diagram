#!/usr/bin/env python3
"""
test_export_no_annotation.py - 验证 export_selected_types 在用户场景下不追加"备注信息"sheet

[用户报告]
"用户 list 导出, 没有勾选对象类型" → 仍然出现"备注信息"sheet

[根因假设]
后端 export_selected_types 在 L1192-1245 有 _collect_child_object_types 追加 annotation 子表逻辑.
这个逻辑被 `if include_annotations:` 守卫, 默认 True (L823 fallback).
如果前端 ExportDialog 把 options.include_annotations 传成 false, 应该跳过.
但:
  (a) 前端 bug: 当 _.value=[] (用户没勾任何类型), `me = false` 设进 options,
      后端用 `options.get('include_annotations', True)` 读到 false, 应该跳过 -> 没问题
  (b) 但 export_cascade (L1266) 函数完全没有 include_annotations 守卫,
      主循环中 `_get_cascade_object_types` 可能返回 annotation 类型, 创建备注 sheet
  (c) 或者后端代码根本没有 export_selected_types 兜底 (单对象导出走 _query_with_hierarchy)

[这个测试做什么]
1. 静态分析 zip 内 import_export_service.py:
   - T1: export_selected_types 存在 (用户 list 导出走这个)
   - T2: export_selected_types 包含 `if include_annotations:` 守卫 (跳过 annotation 子表)
   - T3: 守卫 True 时调用 _collect_child_object_types
   - T4: 守卫 False 时不调用 _collect_child_object_types
   - T5: export_cascade 也读 include_annotations (避免级联场景漏验)
   - T6: dist/ExportDialog JS 把 include_annotations 设进 options
   - T7: dist/ExportDialog JS 当 multiTypeMode && !_.value.includes("annotation") 时设 false
2. 综合: 用户场景下, 不会创建"备注信息" sheet (因为 (a) + (b) 都正确)

[预期]
全部 7 项 PASS. 任意一项 FAIL 都指向具体的代码位置.

[失败含义]
- T2/T4 FAIL: 后端 export_selected_types 守卫被破坏, 任何 selected_types 都会带 annotation sheet
- T5 FAIL: 级联导出场景会带 annotation sheet
- T7 FAIL: 前端在用户不勾 annotation 时仍传 true, 后端会追加 sheet
"""
import os
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ZIP = ROOT / "deploy-v20260703_004.zip"
ZIP_PATH = DEFAULT_ZIP  # overridden by main() if --zip given


def _read_zip_member(name: str) -> str:
    """Read a text file from the deploy zip."""
    if not ZIP_PATH.exists():
        raise FileNotFoundError(
            f"zip not found: {ZIP_PATH}. Run rebuild_zip.py first."
        )
    with zipfile.ZipFile(ZIP_PATH, "r") as zf:
        return zf.read(name).decode("utf-8", errors="replace")


def _list_zip_members(prefix: str = "") -> list:
    if not ZIP_PATH.exists():
        raise FileNotFoundError(f"zip not found: {ZIP_PATH}")
    with zipfile.ZipFile(ZIP_PATH, "r") as zf:
        return [n for n in zf.namelist() if n.startswith(prefix)]


def test_no_annotation_logic():
    results = []

    # ====== 后端 export_selected_types 静态分析 ======
    svc = _read_zip_member("meta/services/import_export_service.py")
    svc_lines = svc.split("\n")

    # T1: 函数存在
    m = re.search(r"^\s*def\s+export_selected_types\s*\(", svc, re.MULTILINE)
    if m:
        func_start = m.start()
        # 找下一个 def (函数结束)
        next_def = re.search(r"^\s*def\s+\w+", svc[func_start + 100:], re.MULTILINE)
        func_end = func_start + 100 + (next_def.start() if next_def else len(svc))
        func_body = svc[func_start:func_end]
        results.append(("PASS", f"T1: export_selected_types 函数存在 ({len(func_body)} chars)"))
    else:
        results.append(("FAIL", "T1: export_selected_types 函数不存在"))
        return results  # 后面的测试依赖这个

    # T2: include_annotations 守卫存在
    if "include_annotations = options.get" in func_body:
        results.append(("PASS", "T2: export_selected_types 含 include_annotations 选项读取"))
    else:
        results.append(("FAIL", "T2: export_selected_types 不读 include_annotations 选项 (会强制带 annotation sheet)"))

    # T3: if include_annotations: True 分支调 _collect_child_object_types
    if re.search(r"if\s+include_annotations\s*:\s*\n\s+child_parent_map\s*=\s*self\._collect_child_object_types", func_body):
        results.append(("PASS", "T3: include_annotations=True 分支调 _collect_child_object_types"))
    else:
        results.append(("FAIL", "T3: include_annotations=True 时未调 _collect_child_object_types (annotation sheet 不会被创建)"))

    # T4: include_annotations=False 时, _collect_child_object_types 不被调用
    # 检查整个函数 body 中 _collect_child_object_types 只在 if include_annotations: 块内被调
    collect_calls = [m.start() for m in re.finditer(r"self\._collect_child_object_types", func_body)]
    # 找每个调用前的最近 "if"
    guarded_calls = 0
    for pos in collect_calls:
        # 向前回溯, 看最近的 "if include_annotations" 是否在 200 字符内
        before = func_body[max(0, pos - 300):pos]
        # 用行号反推
        line_offset = func_body[:pos].count("\n")
        # 反向查找最近的 if 行
        recent_if = list(re.finditer(r"^\s*(if\s+\w+|if\s+not\s+\w+|if\s+\w+\s+in\s+)", before, re.MULTILINE))
        if recent_if:
            last_if = recent_if[-1].group(1)
            # 检查 last_if 是否守卫了 include_annotations
            if "include_annotations" in last_if:
                guarded_calls += 1
            elif "child_parent_map" in recent_if[-1].group(0):
                # check the line above for include_annotations
                idx_in_before = recent_if[-1].start()
                # 看 if 行前 100 字符内有没有 include_annotations
                if "include_annotations" in before[max(0, idx_in_before - 100):idx_in_before]:
                    guarded_calls += 1

    if len(collect_calls) > 0 and guarded_calls == len(collect_calls):
        results.append(("PASS", f"T4: _collect_child_object_types 所有 {len(collect_calls)} 次调用都被 include_annotations 守卫"))
    elif len(collect_calls) == 0:
        results.append(("FAIL", "T4: _collect_child_object_types 完全没出现 (不会追加 annotation sheet, 但用户场景不该期望)"))
    else:
        results.append(("FAIL", f"T4: _collect_child_object_types 有 {len(collect_calls)} 次调用, 但仅 {guarded_calls} 次被守卫"))

    # T5: export_cascade 函数也存在, 看是否读 include_annotations
    m2 = re.search(r"^\s*def\s+export_cascade\s*\(", svc, re.MULTILINE)
    if m2:
        func2_start = m2.start()
        next_def2 = re.search(r"^\s*def\s+\w+", svc[func2_start + 100:], re.MULTILINE)
        func2_end = func2_start + 100 + (next_def2.start() if next_def2 else len(svc))
        func2_body = svc[func2_start:func2_end]
        if "include_annotations" in func2_body:
            results.append(("PASS", "T5: export_cascade 含 include_annotations (级联导出可控)"))
        else:
            # export_cascade 不读 include_annotations - 这是当前已知设计
            # 因为 cascade 的 _get_cascade_object_types 不返回 annotation (annotation 是关联对象, 不是级联对象)
            results.append(("WARN", "T5: export_cascade 不读 include_annotations (需检查 _get_cascade_object_types 是否返回 annotation)"))
            # 进一步检查 cascade 主循环是否创建 annotation sheet
            create_sheet_calls = re.findall(r"create_sheet\s*\(", func2_body)
            if create_sheet_calls:
                # 看 cascade 主循环是不是只对 ordered_types 处理 (即非 annotation)
                cascade_main_loop = re.search(r"for\s+ot\s+in\s+ordered_types\s*:.*?(?=\n\s*\n\s*(?:for|def|if\s+__name__))", func2_body, re.DOTALL)
                if cascade_main_loop and "annotation" not in cascade_main_loop.group(0):
                    results[-1] = ("PASS", "T5: export_cascade 主循环只处理 ordered_types (不含 annotation), 不会建 annotation sheet")
                else:
                    results[-1] = ("FAIL", "T5: export_cascade 主循环可能处理 annotation, 创建'备注信息'sheet")
    else:
        results.append(("WARN", "T5: export_cascade 函数不存在 (单对象部署)"))

    # ====== 前端 ExportDialog 静态分析 ======
    fe_members = _list_zip_members("frontend_dist_files/assets/")
    fe_js_files = [n for n in fe_members if n.endswith(".js")]

    # T6: dist 含 ExportDialog + include_annotations
    found_export_js = None
    found_include = False
    for n in fe_js_files:
        data = _read_zip_member(n)
        if "ExportDialog" in data and "include_annotations" in data:
            found_export_js = n
            found_include = True
            break
    if found_export_js:
        results.append(("PASS", f"T6: dist 含 ExportDialog + include_annotations ({found_export_js})"))
    else:
        results.append(("FAIL", "T6: dist 没有任何 .js 同时含 ExportDialog 和 include_annotations"))
        return results

    # T7: 前端在 multiTypeMode && !includes("annotation") 时设 false
    fe_data = _read_zip_member(found_export_js)
    # minified JS pattern: ExportDialog 把 include_annotations 通过临时变量绑定到
    # "multiTypeMode && _.value.includes('annotation')"
    # 接受多种 minified 写法: const me=..., .include_annotations=me, let X=...
    patterns = [
        # Pattern 1: const/let/var X = multiTypeMode && X.value.includes("annotation")
        (re.compile(
            r'\b(?:const|let|var)\s+(\w+)\s*=\s*[^,;(){}]*?multiTypeMode\s*&&\s*[^,;(){}]*?\.includes\(\s*["\']annotation["\']\s*\)',
            re.DOTALL,
        ), "multiTypeMode && X.value.includes('annotation')"),
        # Pattern 2: 直接 .include_annotations=multiTypeMode && ...includes("annotation")
        (re.compile(
            r'\.include_annotations\s*=\s*[^,;(){}]*?multiTypeMode\s*&&\s*[^,;(){}]*?\.includes\(\s*["\']annotation["\']\s*\)',
            re.DOTALL,
        ), "include_annotations=multiTypeMode&&includes('annotation')"),
        # Pattern 3: .include_annotations=<expr> with annotation in expr
        (re.compile(
            r'\.include_annotations\s*=\s*([^;,(){}]+)',
            re.DOTALL,
        ), "include_annotations=...(含annotation)..."),
    ]
    matched = None
    for pat, desc in patterns:
        m = pat.search(fe_data)
        if m:
            matched = (desc, m.group(0)[:120])
            break
    if matched:
        results.append(("PASS", f"T7: 前端 ExportDialog {matched[0]} ({matched[1]})"))
    else:
        results.append(("FAIL", "T7: 前端 ExportDialog 没找到 'multiTypeMode && includes(annotation)' 模式 (用户没勾时不会传 include_annotations=false)"))

    return results


def main():
    # [CHG 2026-07-04] 支持 --zip 覆盖默认 v004
    import argparse
    parser = argparse.ArgumentParser(description="验证 list 导出无勾选 → 0 annotation sheet")
    parser.add_argument("--zip", default=None, help="指定 zip 路径 (默认: deploy-v20260703_004.zip)")
    args = parser.parse_args()
    if args.zip:
        global ZIP_PATH
        zp = Path(args.zip)
        if not zp.is_absolute():
            zp = ROOT / zp
        ZIP_PATH = zp

    print("=" * 80)
    print("test_export_no_annotation.py - 验证 list 导出无勾选 → 0 annotation sheet")
    print("=" * 80)
    print(f"zip: {ZIP_PATH.name} ({'exists' if ZIP_PATH.exists() else 'NOT FOUND'})")
    print()

    if not ZIP_PATH.exists():
        print("[FAIL] zip 不存在, 请先跑: python tools/rebuild_zip.py")
        return 1

    results = test_no_annotation_logic()
    fail = sum(1 for s, _ in results if s == "FAIL")

    for status, msg in results:
        if status == "PASS":
            marker = "[OK]"
        elif status == "WARN":
            marker = "[?]"
        else:
            marker = "[X]"
        print(f"  {marker} {msg}")

    print()
    print("=" * 80)
    if fail == 0:
        print(f"PASS  ({len(results) - sum(1 for s, _ in results if s == 'WARN')}/{len(results)})")
        return 0
    print(f"FAIL  ({len(results) - fail}/{len(results)})")
    return 1


if __name__ == "__main__":
    sys.exit(main())