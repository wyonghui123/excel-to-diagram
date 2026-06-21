#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
字段映射通用检测工具 - V3 调试基础设施 (v2026.06.21)

背景：2026-06-21 调试发现字段映射错误：
     `_extract_business_key` 用了 source_bo_code（全 NULL），应该用 source_code（有值）。
     字段名错浪费 1+ 小时。

     V1 已实现 table_schema.py --check-code-fields，但只针对单一表：
     本工具做"代码 vs 表"通用映射检测。

核心功能：
- 扫描代码中 "row['xxx']" / "record.xxx" 的访问模式
- 对比数据库实际字段（自动获取 schema）
- 报告可能的字段映射错误

用法：
    # 扫描项目所有 .xxx 访问，匹配数据库 schema
    python scripts/debug/check_field_mapping.py

    # 只看特定字段
    python scripts/debug/check_field_mapping.py --field source_code

    # JSON 输出
    python scripts/debug/check_field_mapping.py --json
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Import safe-io helper for --safe-output
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


def _log(msg: str, level: str = "INFO"):
    icons = {"OK": "[OK]", "FAIL": "[X]", "WARN": "[!]", "INFO": "[i]"}
    print(f"{icons.get(level, '[?]}')} {msg}")


# 字段访问模式
ACCESS_PATTERNS = [
    # record.field_name
    (r"record\.(\w+)", "record.<field>"),
    # row['field_name'] / row["field_name"]
    (r"row\[['\"](\w+)['\"]\]", "row['<field>']"),
    # obj.field_name
    (r"obj\.(\w+)", "obj.<field>"),
    # item.field_name
    (r"item\.(\w+)", "item.<field>"),
    # .field_name (通用)
    (r"\.(\w+_code)\b", ".<field>_code"),
    (r"\.(\w+_id)\b", ".<field>_id"),
]


def scan_field_access(scan_dirs: List[str],
                      target_field: Optional[str] = None,
                      max_results: int = 200) -> List[Dict[str, Any]]:
    """扫描代码中字段访问模式"""
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
                    for line_no, line in enumerate(fp, start=1):
                        # 跳过注释
                        if line.lstrip().startswith("#"):
                            continue

                        for pattern, desc in ACCESS_PATTERNS:
                            matches = re.finditer(pattern, line)
                            for m in matches:
                                field = m.group(1)
                                if target_field and field != target_field:
                                    continue
                                results.append({
                                    "file": str(f.relative_to(PROJECT_ROOT)),
                                    "line": line_no,
                                    "col": m.start(),
                                    "field": field,
                                    "pattern": desc,
                                    "code": line.strip()[:200],
                                })
                                if len(results) >= max_results:
                                    return results
            except (OSError, UnicodeDecodeError):
                continue

    return results


def detect_numeric_field_issues(scan_dirs: List[str]) -> List[Dict[str, Any]]:
    """检测数字字段被 isdigit()/int() 等处理的潜在问题

    场景：service_module_id 是 int，但代码用 isdigit() 检查，会失效
    """
    issues = []

    patterns = [
        # isdigit() 应用在变量上
        (r"(\w+)\.isdigit\(\)", "isdigit() 检查 - 数字字段不能用"),
        # 数字比较 + str()
        (r"str\((\w+_id)\)\.isdigit", "str(<id>).isdigit - 数字字段不该用 isdigit"),
    ]

    for scan_dir in scan_dirs:
        scan_path = PROJECT_ROOT / scan_dir
        if not scan_path.exists():
            continue

        for f in scan_path.rglob("*.py"):
            if "__pycache__" in str(f):
                continue

            try:
                with open(f, "r", encoding="utf-8", errors="replace") as fp:
                    for line_no, line in enumerate(fp, start=1):
                        if line.lstrip().startswith("#"):
                            continue
                        for pattern, desc in patterns:
                            for m in re.finditer(pattern, line):
                                issues.append({
                                    "type": "NUMERIC_FIELD_PATTERN",
                                    "file": str(f.relative_to(PROJECT_ROOT)),
                                    "line": line_no,
                                    "field": m.group(1),
                                    "description": desc,
                                    "code": line.strip()[:200],
                                })
            except (OSError, UnicodeDecodeError):
                continue

    return issues


def detect_undefined_field_usage(scan_dirs: List[str]) -> List[Dict[str, Any]]:
    """检测代码中访问的可能不存在的字段

    通过 grep 找常见字段名（如 *_code）访问，对比标准 ORM 模型字段
    """
    # 暂时不做（需要 ORM 模型 schema）
    return []


def main():
    parser = argparse.ArgumentParser(
        description="字段映射通用检测 - V3 调试基础设施",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--dirs", nargs="+", default=DEFAULT_SCAN_DIRS,
                        help="要扫描的目录")
    parser.add_argument("--field", help="只查找指定字段")
    parser.add_argument("--check-numeric", action="store_true",
                        help="检测数字字段被 isdigit() 等处理")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--max-results", type=int, default=200,
                        help="最大结果数")
    parser.add_argument("--safe-output", action="store_true",
                        help="V3.5: 写入 .trae/debug/queries/ 文件（sandbox-safe）")
    parser.add_argument("--safe-output-dir", metavar="DIR",
                        help="V3.5: 自定义 sandbox-safe 输出目录")

    args = parser.parse_args()

    all_issues = []

    # 1. 字段访问扫描
    _log(f"扫描字段访问（pattern: {args.field or '*'}）...", "INFO")
    field_access = scan_field_access(args.dirs, args.field, args.max_results)
    _log(f"找到 {len(field_access)} 处字段访问", "OK" if field_access else "INFO")

    # 2. 数字字段问题
    if args.check_numeric:
        _log("检测数字字段被 isdigit() 等处理...", "INFO")
        numeric_issues = detect_numeric_field_issues(args.dirs)
        all_issues.extend(numeric_issues)
        _log(f"找到 {len(numeric_issues)} 处数字字段问题", "WARN" if numeric_issues else "OK")

    if args.json:
        result = {
            "field_access_count": len(field_access),
            "field_access_samples": field_access[:50],
            "issues": all_issues,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    # 按字段分组
    by_field: Dict[str, List[Dict[str, Any]]] = {}
    for fa in field_access:
        field = fa["field"]
        if field not in by_field:
            by_field[field] = []
        by_field[field].append(fa)

    print()
    print("=" * 70)
    print(f"字段访问统计（共 {len(field_access)} 处，{len(by_field)} 个不同字段）")
    print("=" * 70)
    print()

    # 列出 top 字段
    sorted_fields = sorted(by_field.items(), key=lambda x: -len(x[1]))
    for field, accesses in sorted_fields[:30]:  # top 30
        n = len(accesses)
        flag = "[OK]" if n < 5 else "[!]" if n < 20 else "[X]"
        print(f"  {flag} .{field:<30} : {n} 处访问")

        # 显示前 3 个
        for fa in accesses[:3]:
            print(f"        L{fa['line']:<5} | {fa['file']:<40} | {fa['code'][:60]}")

    if len(sorted_fields) > 30:
        print(f"  ... 还有 {len(sorted_fields) - 30} 个字段")

    # 数字字段问题
    if all_issues:
        print()
        print("=" * 70)
        print(f"数字字段问题（{len(all_issues)} 处）")
        print("=" * 70)
        for issue in all_issues[:20]:
            print(f"  [!] {issue['file']}:{issue['line']}")
            print(f"      描述: {issue['description']}")
            print(f"      代码: {issue['code'][:80]}")

    # 提示
    if not args.json:
        print()
        print("💡 提示：检查字段映射错误请配合使用:")
        print("   python scripts/debug/inspect/table_schema.py <table> --check-code-fields")

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)