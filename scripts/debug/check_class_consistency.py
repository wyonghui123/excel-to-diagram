#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
类一致性检测工具 - V3 调试基础设施 (v2026.06.21)

背景：2026-06-21 复盘调试事故发现：
     ActionResult 类在多个文件定义（action_executor.py:416 局部类，
     action_context.py:26 dataclass），导致 v1.2.21/v1.2.23 反复修复。

核心功能：
- 检测任意类的多处定义不一致
- 比较每个定义的字段、方法、签名
- 默认检测 ActionResult（可通过 --class 配置）
- 输出"应该统一"的建议

用法：
    # 默认检测 ActionResult
    python scripts/debug/check_class_consistency.py

    # 检测其他类
    python scripts/debug/check_class_consistency.py --class MetaObject

    # 多类检测
    python scripts/debug/check_class_consistency.py --class ActionResult ActionResult MetaObject

    # JSON 输出
    python scripts/debug/check_class_consistency.py --json

    # 扫描特定目录
    python scripts/debug/check_class_consistency.py --dirs meta/core
"""

import argparse
import ast
import json
import sys
from datetime import datetime
from pathlib import Path

# Import safe-io helper
try:
    from scripts.debug.utils.safe_io import emit_safe_output
except ImportError:
    def emit_safe_output(data, prefix, output_dir=None, also_stdout=True):
        out_dir = Path(output_dir) if output_dir else (Path(__file__).resolve().parent.parent.parent / ".trae" / "debug" / "queries")
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        out_file = out_dir / f"{prefix}_{ts}.json"
        out_file.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        if also_stdout:
            print(f"[SAFE_OUTPUT] {out_file}")
        return out_file
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# 修复 Windows GBK 编码问题
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


DEFAULT_SCAN_DIRS = [
    "meta/core",
    "meta/services",
    "meta/api",
    "meta/utils",
    "scripts",
]

DEFAULT_CLASSES = ["ActionResult"]


def _log(msg: str, level: str = "INFO"):
    icons = {"OK": "[OK]", "FAIL": "[X]", "WARN": "[!]", "INFO": "[i]"}
    print(f"{icons.get(level, '[?]}')} {msg}")


def parse_class_def(node: ast.ClassDef, source: str) -> Dict[str, Any]:
    """解析类定义，返回字段和方法列表

    Returns:
        {
            "name": "ActionResult",
            "bases": [...],
            "fields": [{"name": "success", "annotation": "bool"}, ...],
            "methods": [{"name": "fail", "is_classmethod": True, "args": [...]}],
            "decorators": [...],
            "is_dataclass": bool,
            "source": "class ActionResult:",
        }
    """
    fields = []
    methods = []

    # 检测是否为 @dataclass
    is_dataclass = False
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Name) and decorator.id == "dataclass":
            is_dataclass = True

    # 解析 bases
    bases = []
    for base in node.bases:
        if isinstance(base, ast.Name):
            bases.append(base.id)
        elif isinstance(base, ast.Attribute):
            bases.append(base.attr)

    # 遍历类体
    for item in node.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            # 字段注解: success: bool = True
            field_name = item.target.id
            annotation = ast.unparse(item.annotation) if item.annotation else None
            fields.append({
                "name": field_name,
                "annotation": annotation,
            })
        elif isinstance(item, ast.FunctionDef):
            # 方法
            is_classmethod = False
            for decorator in item.decorator_list:
                if isinstance(decorator, ast.Name) and decorator.id == "classmethod":
                    is_classmethod = True

            args = [arg.arg for arg in item.args.args]
            returns = ast.unparse(item.returns) if item.returns else None

            methods.append({
                "name": item.name,
                "is_classmethod": is_classmethod,
                "args": args,
                "returns": returns,
            })

    return {
        "name": node.name,
        "bases": bases,
        "fields": fields,
        "methods": methods,
        "is_dataclass": is_dataclass,
        "decorators": [ast.unparse(d) if hasattr(ast, "unparse") else str(d)
                       for d in node.decorator_list],
    }


def find_class_definitions(class_name: str, scan_dirs: List[str]) -> List[Dict[str, Any]]:
    """查找指定类的所有定义"""
    results = []

    for scan_dir in scan_dirs:
        scan_path = PROJECT_ROOT / scan_dir
        if not scan_path.exists():
            continue

        for f in scan_path.rglob("*.py"):
            if "__pycache__" in str(f):
                continue

            try:
                with open(f, "r", encoding="utf-8", errors="replace") as fp:
                    source = fp.read()
            except (OSError, UnicodeDecodeError):
                continue

            try:
                tree = ast.parse(source, filename=str(f))
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == class_name:
                    info = parse_class_def(node, source)
                    info["file"] = str(f.relative_to(PROJECT_ROOT))
                    info["line"] = node.lineno
                    results.append(info)

    return results


def find_class_imports(class_name: str, scan_dirs: List[str]) -> List[Dict[str, Any]]:
    """查找所有 import 该类的位置"""
    results = []

    for scan_dir in scan_dirs:
        scan_path = PROJECT_ROOT / scan_dir
        if not scan_path.exists():
            continue

        for f in scan_path.rglob("*.py"):
            if "__pycache__" in str(f):
                continue

            try:
                with open(f, "r", encoding="utf-8", errors="replace") as fp:
                    source = fp.read()
            except (OSError, UnicodeDecodeError):
                continue

            try:
                tree = ast.parse(source, filename=str(f))
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        if alias.name == class_name:
                            results.append({
                                "file": str(f.relative_to(PROJECT_ROOT)),
                                "line": node.lineno,
                                "module": node.module or "",
                                "alias": alias.asname or alias.name,
                            })
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == class_name:
                            results.append({
                                "file": str(f.relative_to(PROJECT_ROOT)),
                                "line": node.lineno,
                                "module": alias.name,
                                "alias": alias.asname or alias.name,
                            })

    return results


def compare_definitions(definitions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """比较所有定义，输出差异"""
    if len(definitions) < 2:
        return {
            "consistent": True,
            "message": "只有一个定义，无需比较",
            "differences": [],
        }

    # 以第一个为基准
    base = definitions[0]
    differences = []

    for other in definitions[1:]:
        # 比较字段
        base_fields = {f["name"] for f in base["fields"]}
        other_fields = {f["name"] for f in other["fields"]}

        if base_fields != other_fields:
            only_base = base_fields - other_fields
            only_other = other_fields - base_fields
            differences.append({
                "type": "FIELDS_DIFFER",
                "base": base["file"],
                "other": other["file"],
                "only_in_base": list(only_base),
                "only_in_other": list(only_other),
            })

        # 比较方法签名
        base_methods = {m["name"]: m for m in base["methods"]}
        other_methods = {m["name"]: m for m in other["methods"]}

        # 共同方法
        common = set(base_methods.keys()) & set(other_methods.keys())
        for m in common:
            if base_methods[m]["args"] != other_methods[m]["args"]:
                differences.append({
                    "type": "METHOD_ARGS_DIFFER",
                    "method": m,
                    "base": {"file": base["file"], "args": base_methods[m]["args"]},
                    "other": {"file": other["file"], "args": other_methods[m]["args"]},
                })
            if base_methods[m]["is_classmethod"] != other_methods[m]["is_classmethod"]:
                differences.append({
                    "type": "METHOD_DECORATOR_DIFFER",
                    "method": m,
                    "base": {"file": base["file"], "is_classmethod": base_methods[m]["is_classmethod"]},
                    "other": {"file": other["file"], "is_classmethod": other_methods[m]["is_classmethod"]},
                })

        # 仅一方有的方法
        only_base_methods = set(base_methods.keys()) - set(other_methods.keys())
        only_other_methods = set(other_methods.keys()) - set(base_methods.keys())
        if only_base_methods or only_other_methods:
            differences.append({
                "type": "METHODS_DIFFER",
                "base": base["file"],
                "other": other["file"],
                "only_in_base": list(only_base_methods),
                "only_in_other": list(only_other_methods),
            })

        # 比较是否为 dataclass
        if base["is_dataclass"] != other["is_dataclass"]:
            differences.append({
                "type": "DECORATOR_DIFFER",
                "field": "is_dataclass",
                "base": {"file": base["file"], "is_dataclass": base["is_dataclass"]},
                "other": {"file": other["file"], "is_dataclass": other["is_dataclass"]},
            })

    return {
        "consistent": len(differences) == 0,
        "message": f"{len(definitions)} 处定义",
        "differences": differences,
    }


def main():
    parser = argparse.ArgumentParser(
        description="类一致性检测 - V3 调试基础设施",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--class", dest="classes", nargs="+",
                        default=DEFAULT_CLASSES,
                        help=f"要检查的类名（默认: {DEFAULT_CLASSES}）")
    parser.add_argument("--dirs", nargs="+", default=DEFAULT_SCAN_DIRS,
                        help="要扫描的目录")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--safe-output", action="store_true",
                        help="V3.5: 写入 .trae/debug/queries/ 文件（sandbox-safe）")
    parser.add_argument("--safe-output-dir", metavar="DIR",
                        help="V3.5: 自定义 sandbox-safe 输出目录")

    args = parser.parse_args()

    results = {}
    for cls in args.classes:
        definitions = find_class_definitions(cls, args.dirs)
        imports = find_class_imports(cls, args.dirs)
        comparison = compare_definitions(definitions)
        results[cls] = {
            "definitions": definitions,
            "imports": imports,
            "comparison": comparison,
        }

    if args.json:
        if getattr(args, "safe_output", False):
            emit_safe_output(results, prefix="check_class_consistency", output_dir=getattr(args, "safe_output_dir", None))
        else:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    # 格式化输出
    has_inconsistency = False

    for cls, data in results.items():
        print("=" * 70)
        print(f"类: {cls}")
        print("=" * 70)

        n_defs = len(data["definitions"])
        n_imports = len(data["imports"])

        print(f"  定义: {n_defs} 处")
        print(f"  引用: {n_imports} 处")
        print()

        # 列出所有定义
        if n_defs > 0:
            print(f"## {cls} 定义位置（{n_defs} 处）")
            for d in data["definitions"]:
                cls_type = "dataclass" if d["is_dataclass"] else "普通类"
                print(f"  L{d['line']:<5} | {d['file']:<50} ({cls_type})")
                if d["fields"]:
                    print(f"    字段 ({len(d['fields'])}): {', '.join(f['name'] for f in d['fields'])}")
                if d["methods"]:
                    print(f"    方法 ({len(d['methods'])}): {', '.join(m['name'] for m in d['methods'])}")
            print()

        # 不一致警告
        comp = data["comparison"]
        if n_defs > 1 and not comp["consistent"]:
            has_inconsistency = True
            _log(f"[!] {cls} 存在 {len(comp['differences'])} 处不一致", "WARN")
            for diff in comp["differences"]:
                print(f"    - {diff['type']}: {diff.get('method', diff.get('field', ''))}")
                if "only_in_base" in diff:
                    print(f"      only_in_base: {diff['only_in_base']}")
                    print(f"      only_in_other: {diff['only_in_other']}")
                if "base" in diff and isinstance(diff["base"], dict):
                    print(f"      base: {diff['base'].get('file', '')}")
                    print(f"      other: {diff['other'].get('file', '')}")
            print()
        elif n_defs == 0:
            _log(f"[i] {cls} 没有找到定义", "INFO")
        elif n_defs == 1:
            _log(f"[OK] {cls} 只有 1 处定义", "OK")
        else:
            _log(f"[OK] {cls} {n_defs} 处定义一致", "OK")

    print()

    if has_inconsistency:
        _log("存在类定义不一致，必须修复", "FAIL")
        return 1
    else:
        _log("所有类定义一致", "OK")
        return 0


if __name__ == "__main__":
    sys.exit(main() or 0)