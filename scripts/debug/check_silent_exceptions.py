#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
静默吞错检测工具 - V3 调试基础设施 (v2026.06.21)

背景：2026-06-21 复盘调试事故发现：
     write_scope_interceptor.py 第 912 行 `except Exception` 吞掉所有 RuntimeError，
     导致 flask.g 在 worker 线程中失败时静默放行。

核心功能：
- 扫描代码中"过宽 except 子句"（吞掉潜在错误）
- 检测"只 log 不 raise"的反模式
- 严重级别评分（基于文件位置 + 上下文）
- 支持配置（用户可以指定"严重"模式）

用法：
    # 扫描整个项目
    python scripts/debug/check_silent_exceptions.py

    # 只扫描特定目录
    python scripts/debug/check_silent_exceptions.py --dirs meta/core

    # 自定义严重模式
    python scripts/debug/check_silent_exceptions.py --strict

    # JSON 输出（用于 CI 集成）
    python scripts/debug/check_silent_exceptions.py --json

    # 显示严重问题（按评分排序）
    python scripts/debug/check_silent_exceptions.py --top 10
"""

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


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

# 严重程度模式
# CRITICAL: 必须修复（吞掉会掩盖 bug）
# WARNING: 建议修复（吞掉可能错过错误）
# INFO: 关注（上下文不危险）

DANGEROUS_PATTERNS = [
    # (pattern, level, description)
    (r"except\s+Exception\b", "WARNING", "except Exception 过于宽泛"),
    (r"except\s*:\s*$", "WARNING", "except 捕获所有异常（包括 KeyboardInterrupt）"),
    (r"except\s+BaseException\b", "WARNING", "except BaseException 过于宽泛"),
    (r"except\s+:\s*pass", "CRITICAL", "except 完全吞错（pass）"),
    (r"except\s+\w+.*:\s*pass", "WARNING", "except <Type> 完全吞错（pass）"),
    (r"except\s+.*:\s*return\s+None", "WARNING", "except 返回 None（可能掩盖错误）"),
]

# 严重上下文（特定文件 + 上下文 → CRITICAL）
CRITICAL_CONTEXTS = [
    # (file_glob, function_pattern, reason)
    ("**/interceptors/**/*.py", None, "拦截器吞错会破坏权限检查"),
    ("**/auth*/**", None, "认证吞错会破坏安全"),
    ("**/security/**", None, "安全吞错会破坏安全"),
    ("**/transaction*/**", None, "事务吞错会导致数据不一致"),
    ("**/permission*/**", None, "权限吞错会绕过权限"),
]


def _log(msg: str, level: str = "INFO"):
    icons = {"OK": "[OK]", "FAIL": "[X]", "WARN": "[!]", "INFO": "[i]"}
    print(f"{icons.get(level, '[?]}')} {msg}")


def scan_file(file_path: Path) -> List[Dict[str, Any]]:
    """扫描单个文件，返回所有可疑 except 子句

    Returns:
        List of {file, line, col, level, pattern, code, context, score}
    """
    results = []

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
            lines = source.split("\n")
    except (OSError, UnicodeDecodeError):
        return []

    # 用正则直接扫描每行（更可靠，比 AST 简单）
    rel_path = str(file_path.relative_to(PROJECT_ROOT))

    # 跟踪函数上下文（用于严重程度评分）
    current_func_stack = []
    indent_to_func = {}

    # 先用 AST 找出每个 except 行对应的函数
    try:
        tree = ast.parse(source, filename=str(file_path))
        line_to_func = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if hasattr(node, "lineno") and hasattr(node, "end_lineno"):
                    for ln in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                        line_to_func[ln] = node.name
            elif isinstance(node, ast.ExceptHandler):
                if hasattr(node, "lineno"):
                    # 找到最近的父函数
                    func_name = None
                    for parent in ast.walk(tree):
                        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            if (hasattr(parent, "lineno") and hasattr(parent, "end_lineno") and
                                parent.lineno <= node.lineno <= (parent.end_lineno or parent.lineno)):
                                func_name = parent.name
                    line_to_func[node.lineno] = func_name
    except SyntaxError:
        line_to_func = {}

    # 扫描每行
    for line_no, line in enumerate(lines, 1):
        # 检测 except 模式
        for pattern, base_level, desc in DANGEROUS_PATTERNS:
            if not re.search(pattern, line):
                continue

            # 计算评分
            score = 0
            context = []

            # 严重上下文加分
            for file_glob, func_pat, reason in CRITICAL_CONTEXTS:
                if Path(rel_path).match(file_glob):
                    score += 50
                    context.append(f"CRITICAL_CONTEXT: {reason}")
                    break

            # base level 决定基础分
            if base_level == "CRITICAL":
                score += 100
            elif base_level == "WARNING":
                score += 30
            else:
                score += 10

            # 找到包含此 except 的函数
            func_name = line_to_func.get(line_no, None)

            # 检查 except 体（body）— 看后续几行
            body_lines = []
            for j in range(line_no, min(len(lines), line_no + 5)):
                body_lines.append(lines[j])
            body_text = "\n".join(body_lines)

            if re.search(r"log", body_text, re.IGNORECASE) and "return" not in body_text and "raise" not in body_text:
                score += 5  # 只 log 不 raise
                context.append("只 log 不 raise（潜在静默吞错）")

            if re.search(r"\bpass\b", body_text):
                score += 20  # pass 是更严重的吞错
                context.append("完全吞错（pass）")

            # 上下文行（前后 2 行）
            start_line = max(0, line_no - 2)
            end_line = min(len(lines), line_no + 3)
            code_context = "\n".join(lines[start_line:end_line])

            results.append({
                "file": rel_path,
                "line": line_no,
                "col": 0,
                "level": base_level,
                "score": score,
                "pattern": pattern,
                "description": desc,
                "func_name": func_name,
                "context": context,
                "code": line.strip()[:200],
                "code_context": code_context,
            })

    return results


def scan_project(scan_dirs: List[str], strict: bool = False) -> List[Dict[str, Any]]:
    """扫描项目所有可疑 except"""
    all_results = []

    for scan_dir in scan_dirs:
        scan_path = PROJECT_ROOT / scan_dir
        if not scan_path.exists():
            continue

        for f in scan_path.rglob("*.py"):
            if "__pycache__" in str(f):
                continue
            results = scan_file(f)
            if strict:
                # 严格模式：所有 WARNING+ 都报
                results = [r for r in results if r["level"] != "INFO"]
            all_results.extend(results)

    # 按 score 降序排序
    all_results.sort(key=lambda r: -r["score"])
    return all_results


def print_results(results: List[Dict[str, Any]], top: Optional[int] = None):
    """格式化输出"""
    if not results:
        _log("没有发现可疑 except 子句 ✓", "OK")
        return 0

    n_total = len(results)
    n_critical = sum(1 for r in results if r["level"] == "CRITICAL")
    n_warning = sum(1 for r in results if r["level"] == "WARNING")
    n_info = sum(1 for r in results if r["level"] == "INFO")

    _log(f"发现 {n_total} 处可疑 except", "FAIL" if n_critical > 0 else "WARN")
    print(f"  CRITICAL: {n_critical}  WARNING: {n_warning}  INFO: {n_info}")
    print()

    # 显示 top N
    display = results[:top] if top else results

    for i, r in enumerate(display, 1):
        icon = {"CRITICAL": "[X]", "WARNING": "[!]", "INFO": "[i]"}.get(r["level"], "[?]")

        print(f"{icon} #{i} {r['file']}:{r['line']}  (score={r['score']}, {r['level']})")
        print(f"    描述: {r['description']}")

        if r["func_name"]:
            print(f"    函数: {r['func_name']}")

        if r["context"]:
            for ctx in r["context"]:
                print(f"    {ctx}")

        # 代码上下文
        code_lines = r["code_context"].split("\n")
        for j, line in enumerate(code_lines):
            line_no = r["line"] - 2 + j
            marker = " >>> " if line_no == r["line"] else "     "
            print(f"  {marker}L{line_no:<5} | {line}")
        print()

    return 1 if n_critical > 0 else 0


def main():
    parser = argparse.ArgumentParser(
        description="静默吞错检测 - V3 调试基础设施",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--dirs", nargs="+", default=DEFAULT_SCAN_DIRS,
                        help="要扫描的目录")
    parser.add_argument("--strict", action="store_true",
                        help="严格模式（所有 WARNING+ 都报）")
    parser.add_argument("--top", type=int, help="只显示 top N")
    parser.add_argument("--json", action="store_true", help="JSON 输出")

    args = parser.parse_args()

    results = scan_project(args.dirs, args.strict)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    return print_results(results, args.top)


if __name__ == "__main__":
    sys.exit(main() or 0)