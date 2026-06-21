#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
代码地图快速定位 - 调试基础设施 P0 (v2026.06.21)

背景：2026-06-21 两次调试事故，Agent 反复 Read 整个 write_scope_interceptor.py (600+ 行)
     反复 Read 整个 backend.out (28k+ 行) 找 [WriteScope]
     反复 grep + Read relationship.yaml 找 apply_target_permissions

核心功能：
- 给定主题（关键字），输出涉及的文件 + 行号
- 替代"反复 Read 整个文件" + "反复 grep"
- 类似 IDE "Go to Definition" 简化版

用法：
    # 找 [WriteScope] 相关的代码位置
    python scripts/debug/inspect/code_map.py --topic WriteScope

    # 找 _check_write_scope 的所有引用
    python scripts/debug/inspect/code_map.py --topic _check_write_scope

    # 找 apply_target_permissions 配置
    python scripts/debug/inspect/code_map.py --topic apply_target_permissions --type yaml

    # 找 WriteScopeDenied 异常的所有 raise site
    python scripts/debug/inspect/code_map.py --topic WriteScopeDenied --type raise

    # 多关键字
    python scripts/debug/inspect/code_map.py --topic "WriteScope|_check_ancestor"
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# 修复 Windows GBK 编码问题
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# 代码扫描默认目录
DEFAULT_SCAN_DIRS = [
    "meta/core",
    "meta/services",
    "meta/schemas",
    "tests",
]

# 默认忽略目录
IGNORE_PATTERNS = [
    r"__pycache__",
    r"\.git",
    r"node_modules",
    r"dist",
    r"build",
    r"\.venv",
    r"venv",
]


def _log(msg: str, level: str = "INFO"):
    icons = {"OK": "[OK]", "FAIL": "[X]", "WARN": "[!]", "INFO": "[i]"}
    print(f"{icons.get(level, '[?]}')} {msg}")


def build_ripgrep_args(pattern: str, scan_dirs: List[str],
                       file_types: Optional[List[str]] = None) -> List[str]:
    """构建 ripgrep 命令"""
    # 使用 git grep（避免 ripgrep 不存在）
    args = ["git", "grep", "-n", "--no-color", pattern, "--"]
    for d in scan_dirs:
        args.append(f"{PROJECT_ROOT / d}/")
    return args


def find_in_code(pattern: str, scan_dirs: List[str],
                  file_ext: Optional[str] = None,
                  max_results: int = 50) -> List[Tuple[str, int, str]]:
    """在代码中查找关键字

    Returns:
        List of (file_path, line_number, line_content)
    """
    # 用 Python 直接遍历文件（更可控）
    results = []
    pattern_re = re.compile(pattern, re.IGNORECASE)

    for scan_dir in scan_dirs:
        scan_path = PROJECT_ROOT / scan_dir
        if not scan_path.exists():
            continue

        for f in scan_path.rglob("*"):
            if not f.is_file():
                continue

            # 跳过 ignore 模式
            if any(re.search(p, str(f)) for p in IGNORE_PATTERNS):
                continue

            # 文件扩展名过滤
            if file_ext:
                if not str(f).endswith(file_ext):
                    continue
            else:
                # 默认扫描常见代码文件
                if not str(f).endswith((".py", ".yaml", ".yml", ".json", ".sh")):
                    continue

            try:
                with open(f, "r", encoding="utf-8", errors="replace") as fp:
                    for line_no, line in enumerate(fp, start=1):
                        if pattern_re.search(line):
                            rel_path = f.relative_to(PROJECT_ROOT)
                            results.append((str(rel_path), line_no, line.rstrip()))
                            if len(results) >= max_results:
                                return results
            except (OSError, UnicodeDecodeError):
                continue

    return results


def find_function_def(func_name: str, scan_dirs: List[str]) -> List[Tuple[str, int, str]]:
    """查找函数定义"""
    # 匹配 def func_name( 或 async def func_name(
    pattern = rf"(async\s+)?def\s+{re.escape(func_name)}\s*\("
    return find_in_code(pattern, scan_dirs)


def find_class_def(class_name: str, scan_dirs: List[str]) -> List[Tuple[str, int, str]]:
    """查找类定义"""
    pattern = rf"class\s+{re.escape(class_name)}\s*[\(:]"
    return find_in_code(pattern, scan_dirs)


def find_exception_raise(exc_name: str, scan_dirs: List[str]) -> List[Tuple[str, int, str]]:
    """查找异常 raise 位置"""
    pattern = rf"raise\s+{re.escape(exc_name)}"
    return find_in_code(pattern, scan_dirs)


def find_yaml_config(config_key: str, scan_dirs: List[str]) -> List[Tuple[str, int, str]]:
    """查找 YAML 配置项"""
    pattern = rf"\b{re.escape(config_key)}\s*:"
    return find_in_code(pattern, scan_dirs, file_ext=".yaml")


def find_imports(module_name: str, scan_dirs: List[str]) -> List[Tuple[str, int, str]]:
    """查找所有 import 模块的位置

    支持:
    - `import x`
    - `from x import y`
    - `from x.y import z`
    """
    pattern = rf"^(?:from\s+{re.escape(module_name)}|import\s+{re.escape(module_name)})\b"
    return find_in_code(pattern, scan_dirs, file_ext=".py")


def find_references(symbol: str, scan_dirs: List[str]) -> List[Tuple[str, int, str]]:
    """查找符号的所有引用（反向查找）

    用于：
    - 找所有调用某函数的地方
    - 找所有引用某类的地方
    """
    # 单词边界匹配
    pattern = rf"\b{re.escape(symbol)}\b"
    return find_in_code(pattern, scan_dirs, file_ext=".py", max_results=200)


def format_results(topic: str, results: List[Tuple[str, int, str]],
                   group_by_file: bool = True) -> None:
    """格式化输出"""
    if not results:
        _log(f"未找到 '{topic}' 的引用", "WARN")
        return

    _log(f"找到 {len(results)} 处 '{topic}' 的引用", "OK")
    print()

    if group_by_file:
        # 按文件分组
        by_file: Dict[str, List[Tuple[int, str]]] = {}
        for fpath, line_no, content in results:
            if fpath not in by_file:
                by_file[fpath] = []
            by_file[fpath].append((line_no, content))

        # 按引用数量排序
        for fpath, entries in sorted(by_file.items(), key=lambda x: -len(x[1])):
            print(f"## {fpath}  ({len(entries)} 处)")
            for line_no, content in entries[:20]:  # 每个文件最多显示 20 条
                content_short = content[:120] + ("..." if len(content) > 120 else "")
                print(f"  L{line_no:<5} | {content_short}")
            if len(entries) > 20:
                print(f"  ... 还有 {len(entries) - 20} 处")
            print()
    else:
        for fpath, line_no, content in results[:50]:
            content_short = content[:120]
            print(f"  {fpath}:{line_no} | {content_short}")
        if len(results) > 50:
            print(f"  ... 还有 {len(results) - 50} 处")


def main():
    parser = argparse.ArgumentParser(
        description="代码地图快速定位 - V1 调试基础设施 P0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--topic", required=True,
                        help="要查找的关键字（正则）")
    parser.add_argument("--type", choices=["code", "function", "class",
                                            "raise", "yaml", "import",
                                            "reference", "any"],
                        default="code", help="查找类型")
    parser.add_argument("--dirs", nargs="+", default=DEFAULT_SCAN_DIRS,
                        help="要扫描的目录")
    parser.add_argument("--max-results", type=int, default=100,
                        help="最大结果数")
    parser.add_argument("--flat", action="store_true",
                        help="不按文件分组")

    args = parser.parse_args()

    if args.type == "function":
        results = find_function_def(args.topic, args.dirs)
    elif args.type == "class":
        results = find_class_def(args.topic, args.dirs)
    elif args.type == "raise":
        results = find_exception_raise(args.topic, args.dirs)
    elif args.type == "yaml":
        results = find_yaml_config(args.topic, args.dirs)
    elif args.type == "import":
        results = find_imports(args.topic, args.dirs)
    elif args.type == "reference":
        results = find_references(args.topic, args.dirs)
    else:
        # code 或 any：通用搜索
        results = find_in_code(args.topic, args.dirs, max_results=args.max_results)

    format_results(args.topic, results, group_by_file=not args.flat)

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)