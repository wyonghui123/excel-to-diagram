#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检测未使用的返回值 - V3.5 调试基础设施 (v2026.06.21)

背景：2026-06-21 调试事故复盘发现：
     _update_record 返回 ActionResult，但 caller 在 manage_service.py:1882 / 2643 没检查 result.success
     → 失败也当作成功（success_count += 1）！
     → 用户看不到失败明细

核心功能：
- 扫描函数定义，找出返回 ActionResult / dataclass 的函数
- 扫描 caller，检查是否检查了 .success / .error / .message
- 报告未检查返回值的 caller（potential bug）

用法：
    # 默认扫描 meta/
    python scripts/debug/check_unused_return.py

    # 指定目录
    python scripts/debug/check_unused_return.py --dirs meta/core meta/services

    # JSON 输出
    python scripts/debug/check_unused_return.py --json

    # 检测特定函数
    python scripts/debug/check_unused_return.py --function _update_record
"""

import argparse
import ast
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

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


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULT_SCAN_DIRS = [
    "meta/core",
    "meta/services",
    "meta/api",
]


def _log(msg: str, level: str = "INFO"):
    icons = {"OK": "[OK]", "FAIL": "[X]", "WARN": "[!]", "INFO": "[i]"}
    print(f"{icons.get(level, '[?]}')} {msg}")


# 模式 1: def xxx() -> ActionResult
# 模式 2: def xxx() -> Optional[ActionResult]
# 模式 3: return ActionResult(...)
RETURN_TYPE_PATTERNS = [
    r"->\s*ActionResult\b",
    r"->\s*Optional\[ActionResult\]",
    r"->\s*Tuple\[.*ActionResult.*\]",
    r"->\s*dict\[.*ActionResult.*\]",
]


def find_functions_returning_action_result(scan_dirs: List[str]) -> Dict[str, List[Dict]]:
    """找出所有返回 ActionResult 的函数"""
    functions = {}  # {func_name: [{file, line, code}]}

    for scan_dir in scan_dirs:
        scan_path = PROJECT_ROOT / scan_dir
        if not scan_path.exists():
            continue

        for f in scan_path.rglob("*.py"):
            if "__pycache__" in str(f):
                continue

            try:
                content = f.read_text(encoding="utf-8")
                lines = content.split("\n")

                for i, line in enumerate(lines):
                    # 查找函数定义包含返回类型 ActionResult
                    if not re.match(r"^\s*(async\s+)?def\s+\w+", line):
                        continue

                    func_name_match = re.search(r"def\s+(\w+)", line)
                    if not func_name_match:
                        continue

                    func_name = func_name_match.group(1)

                    # 检查返回类型
                    if not any(re.search(p, line) for p in RETURN_TYPE_PATTERNS):
                        continue

                    # 检查函数体内是否有 return ActionResult
                    has_return = False
                    for j in range(i + 1, min(i + 100, len(lines))):
                        if re.search(r"return\s+(ActionResult\(|self\.\w+\(|result\.|response\.)", lines[j]):
                            has_return = True
                            break
                        if re.match(r"^\s*(def|class)\s+", lines[j]):
                            break

                    if has_return:
                        functions.setdefault(func_name, []).append({
                            "file": str(f.relative_to(PROJECT_ROOT)),
                            "line": i + 1,
                            "def_line": line.strip()[:150],
                        })

            except (OSError, UnicodeDecodeError):
                continue

    return functions


def find_callers(func_name: str, scan_dirs: List[str]) -> List[Dict[str, Any]]:
    """找调用指定函数的位置（排除常见误报）"""
    callers = []
    # 更精确的 pattern: self.xxx() 或 xxx() 在赋值时
    pattern = re.compile(rf"\bself\.{func_name}\s*\(|\bresult\s*=\s*self\.{func_name}\s*\(|\bupdate_result\s*=\s*self\.{func_name}\s*\(|\bcreate_result\s*=\s*self\.{func_name}\s*\(")

    # 排除常见误报
    EXCLUDE_PATTERNS = [
        r"\bAuditRecord\(.*\.create",  # AuditRecord 不是 ActionResult
        r"\bDataSourceFactory\.\w+",    # 工厂方法
        r"\.read\(\)",                   # 文件读取
        r"response\.\w+\(\)",            # HTTP response
        r"file\.\w+\(\)",                # 文件对象
        r"f\.\w+\(\)",                   # 通用 file object
        r"cursor\.\w+\(\)",              # DB cursor
        r"\.create\([^)]*\)#",          # 注释中的 create
    ]

    for scan_dir in scan_dirs:
        scan_path = PROJECT_ROOT / scan_dir
        if not scan_path.exists():
            continue

        for f in scan_path.rglob("*.py"):
            if "__pycache__" in str(f):
                continue

            try:
                content = f.read_text(encoding="utf-8")
                lines = content.split("\n")

                for i, line in enumerate(lines):
                    # 跳过注释行
                    stripped = line.strip()
                    if stripped.startswith("#") or stripped.startswith('"""'):
                        continue

                    if pattern.search(line):
                        # 应用排除规则
                        if any(re.search(p, line) for p in EXCLUDE_PATTERNS):
                            continue

                        callers.append({
                            "file": str(f.relative_to(PROJECT_ROOT)),
                            "line": i + 1,
                            "code": line.strip()[:200],
                        })
            except (OSError, UnicodeDecodeError):
                continue

    return callers


def check_caller_checks_result(caller: Dict[str, Any], func_name: str) -> bool:
    """检查 caller 是否检查了返回值

    简化检测：
    - caller 行包含 `result.success`、`update_result.success`、`result.error`、`result.message` 等
    - 或 caller 在 if/for 条件中使用返回值
    - 或 caller 是 return 透传（直接 return func()） - 视为 OK
    - 或 caller 是 await / yield - 视为 OK
    """
    file_path = PROJECT_ROOT / caller["file"]
    if not file_path.exists():
        return True  # 无法判断，假设 OK

    try:
        content = file_path.read_text(encoding="utf-8")
        lines = content.split("\n")
    except (OSError, UnicodeDecodeError):
        return True

    caller_line = caller.get("code", "").strip()

    # return 透传：return self.xxx(...) - 合法（不视为 BUG）
    if re.match(r"^return\s+self\.\w+\s*\(", caller_line):
        return True
    # yield 透传
    if re.match(r"^yield\s+self\.\w+\s*\(", caller_line):
        return True

    caller_line_idx = caller["line"] - 1
    # 看 caller 后 5 行内是否有 .success / .error / .message / if xxx / raise xxx
    for offset in range(0, 5):
        idx = caller_line_idx + offset
        if idx >= len(lines):
            break
        line = lines[idx]
        if re.search(r"\.\s*(success|error|message|failure)\b", line):
            return True
        if re.match(r"^\s*(if|elif|raise)\b", line):
            return True

    return False


def main():
    parser = argparse.ArgumentParser(
        description="检测未使用的返回值 - V3.5 调试基础设施",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--dirs", nargs="+", default=DEFAULT_SCAN_DIRS)
    parser.add_argument("--function", help="只检测特定函数")
    parser.add_argument("--json", action="store_true")

    args = parser.parse_args()

    if args.json:
        # JSON 模式：直接输出
        funcs = find_functions_returning_action_result(args.dirs)
        if args.function:
            funcs = {args.function: funcs.get(args.function, [])}

        result = {}
        for func_name, defs in funcs.items():
            if not defs:
                continue
            callers = find_callers(func_name, args.dirs)
            bad_callers = []
            for c in callers:
                if not check_caller_checks_result(c, func_name):
                    bad_callers.append(c)
            result[func_name] = {
                "definitions": defs,
                "callers": callers,
                "bad_callers": bad_callers,
            }
        if args.safe_output:
            emit_safe_output(result, prefix="check_unused_return", output_dir=args.safe_output_dir)
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if not any(r["bad_callers"] for r in result.values()) else 1

    print("=" * 70)
    print("未使用返回值检测 - V3.5 调试基础设施")
    print("=" * 70)
    print()

    funcs = find_functions_returning_action_result(args.dirs)
    if args.function:
        funcs = {args.function: funcs.get(args.function, [])}

    if not funcs:
        _log("未找到返回 ActionResult 的函数", "INFO")
        return 0

    total_bad = 0
    for func_name, defs in funcs.items():
        if not defs:
            continue

        callers = find_callers(func_name, args.dirs)
        bad_callers = []

        for c in callers:
            if not check_caller_checks_result(c, func_name):
                bad_callers.append(c)

        status = "[X]" if bad_callers else "[OK]"
        _log(f"{func_name}: {len(defs)} def, {len(callers)} calls, {len(bad_callers)} not-checked", "FAIL" if bad_callers else "OK")
        print()

        # 显示定义
        if defs:
            print(f"  Definitions:")
            for d in defs:
                print(f"    {d['file']}:{d['line']}  {d['def_line']}")

        # 显示问题 caller
        if bad_callers:
            print(f"  Not-checked callers (BUG):")
            for bc in bad_callers:
                print(f"    [X] {bc['file']}:{bc['line']}")
                print(f"        {bc['code']}")
            total_bad += len(bad_callers)
            print()

        # 显示 OK caller
        good_callers = [c for c in callers if c not in bad_callers]
        if good_callers and len(good_callers) <= 3:
            print(f"  Checked callers (OK):")
            for gc in good_callers[:3]:
                print(f"    [OK] {gc['file']}:{gc['line']}")
                print(f"         {gc['code']}")

        print()

    print("=" * 70)
    if total_bad > 0:
        _log(f"发现 {total_bad} 处 caller 未检查返回值（潜在 BUG）", "FAIL")
        print()
        print("建议修复:")
        print("  caller = self._update_record(...)")
        print("  if caller and caller.success:")
        print("      success_count += 1")
        print("  else:")
        print("      failed_count += 1")
        print("      errors.append(caller.message if caller else '更新失败')")
        return 1
    else:
        _log("所有 caller 都正确检查了返回值", "OK")
        return 0


if __name__ == "__main__":
    sys.exit(main() or 0)