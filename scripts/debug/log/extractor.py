#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
后端日志提取工具 - 调试基础设施 P0 (v2026.06.21)

背景：2026-06-21 复盘两次调试事故（SM/BO 误拦 + 字段映射错误），
     Agent 反复 Read 整个 backend.out/err (28k+ 行) 找关键字。
     每次手动 grep + Read 浪费时间，且有 UnicodeDecodeError 风险。

核心功能：
- 强制 UTF-8 编码（避免 gb2312 错误）
- 关键字过滤（避免读整个文件）
- 错误级别过滤（INFO/WARN/ERROR）
- tail/head 模式（取最近/最早 N 条）
- 时间窗口过滤
- 上下文行（ContextLines）

用法：
    # 取最近 100 条 [WriteScope] 日志
    python scripts/debug/log/extractor.py --pattern "WriteScope" --tail 100

    # 取最近 50 条 ERROR 日志
    python scripts/debug/log/extractor.py --level ERROR --tail 50

    # 取最近 200 行 backend.out
    python scripts/debug/log/extractor.py --source out --tail 200

    # 取包含 [WriteScope] 的所有日志 + 前后 3 行上下文
    python scripts/debug/log/extractor.py --pattern "WriteScope" --context 3

    # 时间窗口：2026-06-21 02:00 - 03:00
    python scripts/debug/log/extractor.py --since 2026-06-21T02:00 --until 2026-06-21T03:00

    # 多个关键字（OR）
    python scripts/debug/log/extractor.py --pattern "WriteScope|SideInfo|FATAL"
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_LOG_DIR = PROJECT_ROOT / "scripts" / "logs"

LOG_SOURCES = {
    "out": DEFAULT_LOG_DIR / "backend.out",
    "err": DEFAULT_LOG_DIR / "backend.err",
}

LEVEL_PATTERNS = {
    "ERROR": re.compile(r'\b(ERROR|FATAL|CRITICAL|Traceback|Exception)\b', re.IGNORECASE),
    "WARN": re.compile(r'\b(WARN|WARNING)\b', re.IGNORECASE),
    "INFO": re.compile(r'\b(INFO)\b', re.IGNORECASE),
    "DEBUG": re.compile(r'\b(DEBUG)\b', re.IGNORECASE),
}


def _log(msg: str, level: str = "INFO"):
    icons = {"OK": "[OK]", "FAIL": "[X]", "WARN": "[!]", "INFO": "[i]"}
    print(f"{icons.get(level, '[?]}')} {msg}", file=sys.stderr)


def read_log_safe(log_path: Path, max_lines: int = 100000) -> List[str]:
    """强制 UTF-8 + errors='replace' 读取日志

    避免 Python 启动报 UnicodeDecodeError（gb2312/gbk）
    """
    if not log_path.exists():
        _log(f"日志文件不存在: {log_path}", "FAIL")
        return []

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        _log(f"读取 {log_path.name}: {len(lines)} 行", "INFO")
        # 截断（避免内存爆炸）
        if len(lines) > max_lines:
            _log(f"日志超过 {max_lines} 行，只保留最后 {max_lines} 行", "WARN")
            lines = lines[-max_lines:]
        return lines
    except Exception as e:
        _log(f"读取日志失败: {e}", "FAIL")
        return []


def filter_by_pattern(lines: List[str], pattern: str, context: int = 0) -> List[str]:
    """根据正则模式过滤行"""
    regex = re.compile(pattern, re.IGNORECASE)
    result = []
    for i, line in enumerate(lines):
        if regex.search(line):
            start = max(0, i - context)
            end = min(len(lines), i + context + 1)
            for j in range(start, end):
                if j not in [r_idx for r_line, r_idx in result]:
                    result.append((lines[j], j))
    # 去重保持顺序
    return [line for line, _ in result]


def filter_by_level(lines: List[str], level: str) -> List[str]:
    """根据日志级别过滤"""
    if level.upper() not in LEVEL_PATTERNS:
        _log(f"未知级别: {level}，可用: {list(LEVEL_PATTERNS.keys())}", "FAIL")
        return []

    regex = LEVEL_PATTERNS[level.upper()]
    return [line for line in lines if regex.search(line)]


def filter_by_time(lines: List[str], since: Optional[str], until: Optional[str]) -> List[str]:
    """根据时间窗口过滤（支持 ISO 格式 + 本地时间）

    自动转换：
    - "11:08" → 当天的 11:08:00
    - "2026-06-21T11:08" → 2026-06-21 11:08:00
    - 自动处理 UTC vs 本地时间
    """
    if not since and not until:
        return lines

    def parse_line_time(line: str) -> Optional[datetime]:
        # 尝试多种时间格式
        patterns = [
            # 完整 ISO: 2026-06-21T11:08:23
            r'(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)',
            # 短 ISO: 2026-06-21T11:08
            r'(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2})',
            # 短时间: 11:08:23 或 11:08
            r'\b(\d{2}:\d{2}(?::\d{2})?)\b',
        ]
        for p in patterns:
            m = re.search(p, line)
            if m:
                try:
                    s = m.group(1).replace(' ', 'T').replace('/', '-').rstrip('.,')
                    # 处理短时间格式（HH:MM 或 HH:MM:SS）
                    if len(s) <= 5 or (len(s) <= 8 and ':' in s and 'T' not in s):
                        # 短时间：补全为今天
                        today = datetime.now().strftime("%Y-%m-%d")
                        s = f"{today}T{s}:00" if s.count(':') == 1 else f"{today}T{s}"
                    if '.' in s or ',' in s:
                        s = s.replace(',', '.').split('.')[0]  # 移除毫秒
                    dt = datetime.fromisoformat(s)
                    return dt
                except ValueError:
                    continue
        return None

    since_dt = None
    until_dt = None
    if since:
        try:
            s = since.replace(' ', 'T').replace('/', '-')
            # 短时间补全
            if len(s) <= 5 or (len(s) <= 8 and ':' in s and 'T' not in s):
                today = datetime.now().strftime("%Y-%m-%d")
                s = f"{today}T{s}:00" if s.count(':') == 1 else f"{today}T{s}"
            since_dt = datetime.fromisoformat(s)
        except ValueError:
            _log(f"无效 since 时间: {since}", "FAIL")
            return lines
    if until:
        try:
            s = until.replace(' ', 'T').replace('/', '-')
            if len(s) <= 5 or (len(s) <= 8 and ':' in s and 'T' not in s):
                today = datetime.now().strftime("%Y-%m-%d")
                s = f"{today}T{s}:00" if s.count(':') == 1 else f"{today}T{s}"
            until_dt = datetime.fromisoformat(s)
        except ValueError:
            _log(f"无效 until 时间: {until}", "FAIL")
            return lines

    result = []
    for line in lines:
        dt = parse_line_time(line)
        if dt is None:
            continue  # 没有时间戳的行跳过
        if since_dt and dt < since_dt:
            continue
        if until_dt and dt > until_dt:
            continue
        result.append(line)

    return result


def take_tail(lines: List[str], n: int) -> List[str]:
    """取最后 N 条"""
    return lines[-n:] if len(lines) > n else lines


def take_head(lines: List[str], n: int) -> List[str]:
    """取最前 N 条"""
    return lines[:n]


def colorize(line: str, level: Optional[str] = None) -> str:
    """给日志加上 ANSI 颜色（如果支持）"""
    # Windows ANSI 支持检测（Windows 10+ 启用 VT 模式）
    if not sys.stdout.isatty():
        return line.rstrip()

    if level == "ERROR" or "ERROR" in line or "Traceback" in line:
        return f"\033[91m{line.rstrip()}\033[0m"  # 红色
    if level == "WARN" or "WARN" in line:
        return f"\033[93m{line.rstrip()}\033[0m"  # 黄色
    if "WriteScope" in line:
        return f"\033[96m{line.rstrip()}\033[0m"  # 青色
    return line.rstrip()


def main():
    parser = argparse.ArgumentParser(
        description="后端日志提取工具 - V2.1 调试基础设施 P0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--source", choices=list(LOG_SOURCES.keys()),
                        default="out", help="日志来源（out/err）")
    parser.add_argument("--pattern", help="正则模式过滤（可多个，用 | 分隔）")
    parser.add_argument("--level", choices=list(LEVEL_PATTERNS.keys()),
                        help="日志级别过滤")
    parser.add_argument("--context", type=int, default=0,
                        help="匹配行的前后上下文行数")
    parser.add_argument("--tail", type=int, help="取最后 N 行")
    parser.add_argument("--head", type=int, help="取最前 N 行")
    parser.add_argument("--since", help="起始时间（ISO 格式，如 2026-06-21T02:00）")
    parser.add_argument("--until", help="结束时间（ISO 格式）")
    parser.add_argument("--no-color", action="store_true", help="禁用颜色")
    parser.add_argument("--max-lines", type=int, default=100000,
                        help="最大读取行数（防内存爆炸）")

    args = parser.parse_args()

    # Step 1: 读取日志
    log_path = LOG_SOURCES[args.source]
    lines = read_log_safe(log_path, args.max_lines)

    if not lines:
        return 1

    # Step 2: 时间窗口过滤（最先做，缩小范围）
    if args.since or args.until:
        lines = filter_by_time(lines, args.since, args.until)
        _log(f"时间窗口过滤后: {len(lines)} 行", "INFO")

    # Step 3: pattern 过滤
    if args.pattern:
        lines = filter_by_pattern(lines, args.pattern, args.context)
        _log(f"Pattern '{args.pattern}' 过滤后: {len(lines)} 行", "INFO")

    # Step 4: level 过滤
    if args.level:
        lines = filter_by_level(lines, args.level)
        _log(f"Level {args.level} 过滤后: {len(lines)} 行", "INFO")

    # Step 5: head/tail
    if args.head:
        lines = take_head(lines, args.head)
    elif args.tail:
        lines = take_tail(lines, args.tail)

    if not lines:
        _log("没有匹配的行", "WARN")
        return 0

    # Step 6: 输出
    print(f"--- 输出 {len(lines)} 行 ---")
    if args.no_color:
        for line in lines:
            print(line.rstrip())
    else:
        for line in lines:
            print(colorize(line))

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)