#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
日志文件检测工具 - V3.1 调试基础设施 (v2026.06.21)

背景：2026-06-21 调试事故复盘发现：
     - backend.log (3MB, 6/20 21:02:46, 根目录)
     - backend.out (1.2KB, 6/21 11:24:49, 根目录)
     - backend.err (62B, 6/21 11:21:21, 根目录)
     - scripts/logs/backend.out (6.4MB, 6/21 1:27:34, 正确位置)
     - scripts/logs/backend.err (0B, 6/20 23:43:49)
     - .service_manager_3010.log (1.3MB, 6/20 23:43:56)

     Agent 不知道该看哪个！日志文件位置分散、命名混乱。

核心功能：
- 自动扫描所有 backend.* / service_manager_*.log 文件
- 按大小 + 时间排序
- 识别哪个是"活跃的"（按 PID 时间 + 文件大小变化）
- 推荐用哪个文件

用法：
    # 扫描所有日志文件
    python scripts/debug/check_log_files.py

    # JSON 输出
    python scripts/debug/check_log_files.py --json

    # 只显示 backend 相关
    python scripts/debug/check_log_files.py --filter backend
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# 修复 Windows GBK 编码问题
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


DEFAULT_PATTERNS = [
    "backend.out",
    "backend.err",
    "backend.log",
    ".service_manager_*.log",
    "scripts/logs/backend.out",
    "scripts/logs/backend.err",
    "scripts/logs/frontend.out",
    "scripts/logs/frontend.err",
]


def _log(msg: str, level: str = "INFO"):
    icons = {"OK": "[OK]", "FAIL": "[X]", "WARN": "[!]", "INFO": "[i]"}
    print(f"{icons.get(level, '[?]}')} {msg}")


def find_log_files() -> List[Dict[str, Any]]:
    """查找所有日志文件"""
    results = []

    # 扫描根目录（用 glob）
    for pattern in DEFAULT_PATTERNS:
        for f in PROJECT_ROOT.glob(pattern):
            if f.is_file():
                stat = f.stat()
                results.append({
                    "path": str(f.relative_to(PROJECT_ROOT)),
                    "abs_path": str(f),
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "mtime_iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(stat.st_mtime)),
                    "age_seconds": time.time() - stat.st_mtime,
                })

    # 扫描 scripts/logs/ 目录下所有 .out/.err 文件
    scripts_logs = PROJECT_ROOT / "scripts" / "logs"
    if scripts_logs.exists():
        for f in scripts_logs.iterdir():
            if f.is_file() and (f.suffix in (".out", ".err", ".log")):
                if any(r["abs_path"] == str(f) for r in results):
                    continue
                stat = f.stat()
                results.append({
                    "path": str(f.relative_to(PROJECT_ROOT)),
                    "abs_path": str(f),
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "mtime_iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(stat.st_mtime)),
                    "age_seconds": time.time() - stat.st_mtime,
                })

    # 去重（绝对路径）
    seen = set()
    unique = []
    for r in results:
        if r["abs_path"] not in seen:
            seen.add(r["abs_path"])
            unique.append(r)

    # 按 mtime 降序
    unique.sort(key=lambda r: -r["mtime"])
    return unique


def detect_active_backend_pid() -> Optional[int]:
    """检测当前 backend 进程 PID（从 .service_status.json）"""
    for f in [".service_status.json", ".service_status_3010.json"]:
        path = PROJECT_ROOT / f
        if not path.exists():
            continue
        try:
            for enc in ("utf-8-sig", "utf-8"):
                try:
                    with open(path, encoding=enc) as fp:
                        data = json.load(fp)
                    backend = data.get("backend", {})
                    return backend.get("pid")
                except UnicodeDecodeError:
                    continue
        except Exception:
            continue
    return None


def print_results(files: List[Dict[str, Any]], filter_str: Optional[str] = None):
    """格式化输出"""
    if not files:
        _log("没有找到日志文件", "FAIL")
        return

    # 过滤
    if filter_str:
        files = [f for f in files if filter_str.lower() in f["path"].lower()]

    _log(f"找到 {len(files)} 个日志文件", "OK")
    print()

    # 当前时间
    now = time.time()

    # 输出表格
    print(f"  {'状态':<6} {'路径':<55} {'大小':>12} {'最后修改':<20} {'年龄'}")
    print(f"  {'-'*6} {'-'*55} {'-'*12} {'-'*20} {'-'*10}")

    for f in files:
        size_str = f"{f['size']:,}"

        # 活跃度判断
        age = f["age_seconds"]
        if age < 60:
            status = "[OK]"
            age_str = f"{int(age)}秒"
        elif age < 3600:
            status = "[OK]"
            age_str = f"{int(age/60)}分钟"
        elif age < 86400:
            status = "[!]"
            age_str = f"{int(age/3600)}小时"
        else:
            status = "[X]"
            age_str = f"{int(age/86400)}天"

        path_display = f["path"][:55]
        mtime_str = f["mtime_iso"][:19]

        print(f"  {status:<6} {path_display:<55} {size_str:>12} {mtime_str:<20} {age_str}")

    # 推荐
    print()
    print("=" * 70)
    print("💡 推荐（按优先级）：")
    print("=" * 70)

    # 找最大的 .out 文件（最有可能是主日志）
    candidates = [f for f in files if f["path"].endswith(".out") and f["size"] > 1000]
    candidates.sort(key=lambda f: -f["size"])

    if candidates:
        best = candidates[0]
        print(f"  [1] {best['path']}  ({best['size']:,} 字节, {best['mtime_iso'][:19]})")
        print(f"      extractor.py --source out --pattern <key> --tail 50")
        print()

    # 警告
    if any(f["size"] == 0 for f in files):
        print(f"  ⚠️ 发现空日志文件（可能 service_manager DEVNULL bug）：")
        for f in files:
            if f["size"] == 0:
                print(f"    - {f['path']}")


def main():
    parser = argparse.ArgumentParser(
        description="日志文件检测 - V3.1 调试基础设施",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--filter", help="只显示包含此字符串的文件")
    parser.add_argument("--json", action="store_true", help="JSON 输出")

    args = parser.parse_args()

    files = find_log_files()

    if args.json:
        result = {
            "backend_pid": detect_active_backend_pid(),
            "files": files,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print_results(files, args.filter)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)