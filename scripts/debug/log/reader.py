#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
实时日志跟踪（tail -f 模式）- 调试基础设施 P1 (v2026.06.21)

背景：调试拦截器时，Agent 反复操作 → 切换到 Read backend.out 看日志 → 反复 Read
     这种"触发操作 → 看日志"循环浪费大量时间。

核心功能：
- 实时跟踪 backend.out / backend.err 新增行
- 关键字过滤（仅显示匹配的）
- 错误高亮（ERROR/FATAL 红色）
- 集成 agent_bootstrap 心跳（避免长连接掉线）

用法：
    # 实时跟踪 backend.out
    python scripts/debug/log/reader.py follow --source out

    # 实时跟踪 + 过滤 [WriteScope]
    python scripts/debug/log/reader.py follow --source out --pattern WriteScope

    # 实时跟踪 backend.err
    python scripts/debug/log/reader.py follow --source err --level ERROR

    # 监控特定文件大小（避免读巨型文件）
    python scripts/debug/log/reader.py follow --source out --max-file-size 50MB
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path
from typing import List, Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_LOG_DIR = PROJECT_ROOT / "scripts" / "logs"

LOG_SOURCES = {
    "out": DEFAULT_LOG_DIR / "backend.out",
    "err": DEFAULT_LOG_DIR / "backend.err",
}

MAX_FILE_SIZE_DEFAULT = 100 * 1024 * 1024  # 100MB


def _log(msg: str, level: str = "INFO"):
    icons = {"OK": "[OK]", "FAIL": "[X]", "WARN": "[!]", "INFO": "[i]"}
    if level != "INFO":  # 跟踪模式只输出 WARN+
        print(f"{icons.get(level, '[?]}')} {msg}", file=sys.stderr)


def colorize(line: str) -> str:
    """ANSI 颜色"""
    if not sys.stdout.isatty():
        return line.rstrip()

    if "ERROR" in line or "Traceback" in line or "FATAL" in line:
        return f"\033[91m{line.rstrip()}\033[0m"  # 红
    if "WARN" in line:
        return f"\033[93m{line.rstrip()}\033[0m"  # 黄
    if "WriteScope" in line:
        return f"\033[96m{line.rstrip()}\033[0m"  # 青
    return line.rstrip()


def get_file_size(path: Path) -> int:
    """获取文件大小"""
    try:
        return path.stat().st_size
    except OSError:
        return 0


def follow_log(log_path: Path, pattern: Optional[str], level: Optional[str],
               max_file_size: int, max_lines: int = 500):
    """实时跟踪日志"""
    if not log_path.exists():
        _log(f"日志文件不存在: {log_path}", "FAIL")
        return 1

    # 检查文件大小
    size = get_file_size(log_path)
    if size > max_file_size:
        _log(f"日志文件过大: {size // (1024*1024)}MB > {max_file_size // (1024*1024)}MB", "FAIL")
        _log("提示: 用 extractor.py --tail 取最近 N 条，或轮转日志", "INFO")
        return 1

    # 编译 pattern
    pattern_re = None
    if pattern:
        pattern_re = re.compile(pattern, re.IGNORECASE)

    level_patterns = {
        "ERROR": re.compile(r'\b(ERROR|FATAL|CRITICAL|Traceback|Exception)\b', re.IGNORECASE),
        "WARN": re.compile(r'\b(WARN|WARNING)\b', re.IGNORECASE),
        "INFO": re.compile(r'\b(INFO)\b', re.IGNORECASE),
    }

    print(f"--- 跟踪 {log_path.name}（Ctrl+C 退出）---")
    if pattern:
        print(f"--- Pattern: {pattern} ---")
    if level:
        print(f"--- Level: {level} ---")
    print()

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            # 跳到末尾（只跟踪新行）
            f.seek(0, 2)

            buffer: List[str] = []
            heartbeat_counter = 0

            while True:
                line = f.readline()

                if not line:
                    # 无新行，sleep 后继续
                    time.sleep(0.5)
                    heartbeat_counter += 1

                    # 每 60 秒输出一行提示（避免看起来卡死）
                    if heartbeat_counter >= 120:  # 60s
                        print(f"[i] ... still watching {log_path.name} ({time.strftime('%H:%M:%S')})",
                              file=sys.stderr)
                        heartbeat_counter = 0
                    continue

                heartbeat_counter = 0

                # 过滤
                if pattern_re and not pattern_re.search(line):
                    continue
                if level and level.upper() in level_patterns:
                    if not level_patterns[level.upper()].search(line):
                        continue

                # 输出
                print(colorize(line))
                sys.stdout.flush()

    except KeyboardInterrupt:
        print("\n--- 停止跟踪 ---")
        return 0
    except Exception as e:
        _log(f"跟踪失败: {e}", "FAIL")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="实时日志跟踪 - V1 调试基础设施 P1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("cmd", choices=["follow"], help="子命令")
    parser.add_argument("--source", choices=list(LOG_SOURCES.keys()),
                        default="out", help="日志来源（out/err）")
    parser.add_argument("--pattern", help="关键字过滤（正则）")
    parser.add_argument("--level", choices=["ERROR", "WARN", "INFO"],
                        help="日志级别过滤")
    parser.add_argument("--max-file-size", type=int, default=MAX_FILE_SIZE_DEFAULT,
                        help="最大文件大小（字节，默认 100MB）")

    args = parser.parse_args()

    if args.cmd == "follow":
        log_path = LOG_SOURCES[args.source]
        return follow_log(log_path, args.pattern, args.level, args.max_file_size)

    return 1


if __name__ == "__main__":
    sys.exit(main() or 0)