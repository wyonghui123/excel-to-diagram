#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检测根目录调试脚本 - V3.3 调试基础设施 (v2026.06.21)

背景：2026-06-21 调试事故复盘发现：
     Agent 在根目录写 `debug_data.py`（66+39 行），手动 SQL 查询。
     - 列名错了（sub_domain_name 不存在）→ 浪费时间
     - 直接连 sqlite3 → 跳过 ORM
     - 没记录调试上下文
     - 不在 scripts/debug/ 下 → 不会被基础设施捕获

     应该使用 scripts/debug/inspect/user_context.py + table_schema.py

核心功能：
- 检测根目录的调试脚本（debug_*.py / check_*.py / probe_*.py / _restart*.ps1）
- 检测未跟踪的临时调试文件
- 报告违规，建议使用 scripts/debug/ 下的工具

用法：
    # 默认检测
    python scripts/debug/check_debug_script_in_root.py

    # JSON 输出
    python scripts/debug/check_debug_script_in_root.py --json

    # 包括 backend.* 等临时日志
    python scripts/debug/check_debug_script_in_root.py --include-logs
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 调试脚本检测模式
DEBUG_SCRIPT_PATTERNS = [
    "debug_*.py",
    "debug_*.ps1",
    "debug_*.sh",
    "check_*.py",  # 注意：根目录的 check_*.py 已被 .gitignore 排除
    "check_*.ps1",
    "probe_*.py",
    "test_*.py",   # 注意：根目录的 test_*.py 通常不被推荐
    "_restart*.ps1",
    "_debug*.py",
    "_test*.py",
]

# 临时日志文件
TEMP_LOG_PATTERNS = [
    "backend.log.err",
    "backend.log.*",
    "*.dbg",
    "*.tmp",
    "*~",
    "*.bak",
    "*.swp",
]


def _log(msg: str, level: str = "INFO"):
    icons = {"OK": "[OK]", "FAIL": "[X]", "WARN": "[!]", "INFO": "[i]"}
    print(f"{icons.get(level, '[?]}')} {msg}")


def is_tracked(filename: str) -> bool:
    """检查文件是否被 git 跟踪"""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", filename],
            cwd=str(PROJECT_ROOT),
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def find_debug_scripts() -> List[Dict[str, Any]]:
    """查找根目录调试脚本"""
    results = []

    for pattern in DEBUG_SCRIPT_PATTERNS:
        for f in PROJECT_ROOT.glob(pattern):
            if not f.is_file():
                continue
            stat = f.stat()
            tracked = is_tracked(str(f.relative_to(PROJECT_ROOT)))
            results.append({
                "file": str(f.relative_to(PROJECT_ROOT)),
                "size": stat.st_size,
                "mtime": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(stat.st_mtime)),
                "tracked": tracked,
                "pattern": pattern,
            })

    return results


def find_temp_logs() -> List[Dict[str, Any]]:
    """查找临时日志文件"""
    results = []

    for pattern in TEMP_LOG_PATTERNS:
        for f in PROJECT_ROOT.glob(pattern):
            if not f.is_file():
                continue
            stat = f.stat()
            results.append({
                "file": str(f.relative_to(PROJECT_ROOT)),
                "size": stat.st_size,
                "mtime": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(stat.st_mtime)),
            })

    return results


def suggest_replacement(debug_script: Dict[str, Any]) -> List[str]:
    """根据调试脚本名推荐替换工具"""
    name = debug_script["file"].lower()
    suggestions = []

    # debug_data.py
    if "debug_data" in name:
        suggestions.extend([
            "→ python scripts/debug/inspect/user_context.py <username>  # 用户上下文",
            "→ python scripts/debug/inspect/table_schema.py <table>  # 表结构探索",
            "→ python scripts/debug/inspect/table_schema.py <table> --check-code-fields  # 字段映射检测",
        ])
    elif "check_" in name:
        suggestions.extend([
            "→ python scripts/debug/check_silent_exceptions.py  # 静默吞错检测",
            "→ python scripts/debug/check_class_consistency.py --class <ClassName>  # 类一致性",
            "→ python scripts/debug/check_field_mapping.py  # 字段映射错误",
        ])
    elif "_restart" in name:
        suggestions.extend([
            "→ python scripts/debug/restart/restart_safe.py restart  # 安全重启",
        ])
    else:
        suggestions.extend([
            "→ 使用 scripts/debug/ 下的工具（不要在根目录写临时脚本）",
        ])

    return suggestions


def main():
    parser = argparse.ArgumentParser(
        description="检测根目录调试脚本 - V3.3 调试基础设施",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--include-logs", action="store_true",
                        help="也检测临时日志文件")
    parser.add_argument("--json", action="store_true", help="JSON 输出")

    args = parser.parse_args()

    debug_scripts = find_debug_scripts()
    temp_logs = find_temp_logs() if args.include_logs else []

    if args.json:
        result = {
            "debug_scripts": debug_scripts,
            "temp_logs": temp_logs,
            "violations": len(debug_scripts) + len(temp_logs),
        }
        if args.safe_output:
            emit_safe_output(result, prefix="check_debug_script_in_root", output_dir=args.safe_output_dir)
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if not debug_scripts else 1

    # 输出
    print("=" * 70)
    print("根目录调试脚本检测 - V3.3 调试基础设施")
    print("=" * 70)
    print()

    # 调试脚本
    if debug_scripts:
        _log(f"发现 {len(debug_scripts)} 个根目录调试脚本（违规）", "FAIL")
        print()
        for ds in debug_scripts:
            tracked_mark = "已跟踪" if ds["tracked"] else "未跟踪"
            print(f"  [X] {ds['file']:<30} ({ds['size']:>6,} B, {tracked_mark})")
            print(f"      创建时间: {ds['mtime']}")
            for suggestion in suggest_replacement(ds):
                print(f"      -> {suggestion}")
            print()
    else:
        _log("根目录没有调试脚本（符合规范）", "OK")

    # 临时日志
    if args.include_logs and temp_logs:
        print()
        _log(f"发现 {len(temp_logs)} 个临时日志文件", "WARN")
        for tl in temp_logs:
            print(f"  [!] {tl['file']:<40} ({tl['size']:>8,} B)")

    # 建议
    if debug_scripts:
        print()
        print("=" * 70)
        print("💡 处理建议:")
        print("=" * 70)
        print()
        print("1. 删除根目录的调试脚本（如果已完成调试）:")
        print("   rm -f debug_data.py debug_*.py _restart*.ps1")
        print()
        print("2. 使用 scripts/debug/ 下的标准工具:")
        print("   ls scripts/debug/  # 查看所有工具")
        print()
        print("3. 调试会话记录到 .trae/debug/sessions/")
        print("   python scripts/debug/sessions/auto_record.py start --agent <your-name>")
        print()

    return 0 if not debug_scripts else 1


if __name__ == "__main__":
    sys.exit(main() or 0)