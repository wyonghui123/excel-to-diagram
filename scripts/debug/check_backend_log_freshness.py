#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检查后端日志新鲜度 - V3.7 调试基础设施 (v2026.06.21)

背景：2026-06-21 调试事故复盘发现：
     Agent 用 `python -u waitress_server.py` 手动启动后端（不用 restart_safe.py）
     → 后端 stdout/stderr 没重定向到 scripts/logs/backend.out
     → 后端"看似健康"（health 200），但日志停在 14 小时前
     → Agent 在调试基于 14 小时前的旧日志！浪费 10+ 分钟

核心功能：
- 检查 scripts/logs/backend.out 最后写入时间
- 对比后端进程启动时间
- 如果后端在跑但日志没更新 → FAIL（关键 BUG）
- 如果日志 > 5 分钟没更新 → WARN

用法：
    python scripts/debug/check_backend_log_freshness.py
    python scripts/debug/check_backend_log_freshness.py --max-age-minutes 5
"""

import argparse
import json
import sys
import time
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


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOG_FILES = [
    PROJECT_ROOT / "scripts" / "logs" / "backend.out",
    PROJECT_ROOT / "scripts" / "logs" / "backend.err",
]


def _log(msg: str, level: str = "INFO"):
    icons = {"OK": "[OK]", "FAIL": "[X]", "WARN": "[!]", "INFO": "[i]"}
    print(f"{icons.get(level, '[?]}')} {msg}", flush=True)


def check_backend_process() -> dict:
    """检查后端进程是否在跑"""
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        port_ok = (s.connect_ex(("127.0.0.1", 3010)) == 0)
        s.close()
        return {"running": port_ok, "port": 3010}
    except Exception as e:
        return {"running": False, "error": str(e)}


def check_log_freshness(log_path: Path, max_age_seconds: int) -> dict:
    """检查日志文件新鲜度"""
    if not log_path.exists():
        return {
            "exists": False,
            "fresh": False,
            "age_seconds": None,
            "last_write": None,
            "size": 0,
            "reason": "file not found",
        }

    stat = log_path.stat()
    last_write = datetime.fromtimestamp(stat.st_mtime)
    age_seconds = (datetime.now() - last_write).total_seconds()

    return {
        "exists": True,
        "fresh": age_seconds < max_age_seconds,
        "age_seconds": int(age_seconds),
        "last_write": last_write.isoformat(),
        "size": stat.st_size,
        "reason": (
            f"last write {int(age_seconds)}s ago (max {max_age_seconds}s)"
            if age_seconds >= max_age_seconds else "fresh"
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description="检查后端日志新鲜度 - V3.7 调试基础设施",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--max-age-minutes", type=int, default=5,
                        help="最大日志过期时间（分钟），默认 5")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--safe-output", action="store_true",
                        help="V3.5: 写入 .trae/debug/queries/ 文件（sandbox-safe）")
    parser.add_argument("--safe-output-dir", metavar="DIR",
                        help="V3.5: 自定义 sandbox-safe 输出目录")

    args = parser.parse_args()
    max_age_seconds = args.max_age_minutes * 60

    if args.json:
        result = {
            "process": check_backend_process(),
            "logs": {
                str(p.relative_to(PROJECT_ROOT)): check_log_freshness(p, max_age_seconds)
                for p in LOG_FILES
            },
            "timestamp": datetime.now().isoformat(),
        }
        if getattr(args, "safe_output", False):
            emit_safe_output(result, prefix="check_backend_log_freshness", output_dir=getattr(args, "safe_output_dir", None))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print("=" * 70)
    print("后端日志新鲜度检查 - V3.7 调试基础设施")
    print("=" * 70)

    # 1. 检查后端进程
    proc = check_backend_process()
    if proc["running"]:
        _log(f"后端进程: 端口 {proc['port']} 监听中", "OK")
    else:
        _log(f"后端进程: 未运行", "FAIL")
        return 1

    # 2. 检查日志文件
    all_fresh = True
    critical_issue = False

    for log_path in LOG_FILES:
        rel = log_path.relative_to(PROJECT_ROOT)
        freshness = check_log_freshness(log_path, max_age_seconds)

        if not freshness["exists"]:
            _log(f"{rel}: 文件不存在 (FAIL - 后端 stdout 未重定向)", "FAIL")
            critical_issue = True
            continue

        if freshness["fresh"]:
            _log(
                f"{rel}: 写入 {freshness['age_seconds']}s 前 "
                f"(size={freshness['size']:,}B)",
                "OK",
            )
        else:
            # V3.7.2 修复：区分空文件(0 bytes)和有内容的文件
            # .err 文件通常为空(waitress 不用 stderr),空文件未更新不算 bug
            # .out 文件必须有写入,否则就是 stdout 未重定向
            is_err_file = "err" in str(rel).lower()
            is_empty = freshness["size"] == 0

            if is_err_file and is_empty:
                _log(
                    f"{rel}: 写入 {freshness['age_seconds']}s 前 "
                    f"(size=0B, 空文件 - waitress 未使用 stderr,正常)",
                    "OK",
                )
                continue

            age_min = freshness["age_seconds"] // 60
            _log(
                f"{rel}: 最后写入 {age_min} 分钟前 - 严重 BUG",
                "FAIL",
            )
            _log(f"       size={freshness['size']:,}B, last_write={freshness['last_write']}", "INFO")
            _log(f"       后端在跑但日志不更新,可能 stdout 没重定向到此文件", "WARN")
            critical_issue = True

    print()
    print("=" * 70)
    if critical_issue:
        _log("检测到严重问题: 后端日志未写入", "FAIL")
        print()
        print("原因: Agent 可能用了以下方式启动后端:")
        print("  [X] python -u waitress_server.py          (stdout 不重定向)")
        print("  [X] python waitress_server.py > NUL       (Windows NUL 吞掉)")
        print("  [X] python waitress_server.py             (buffered)")
        print()
        print("正确方式 (用 restart_safe.py 自动写日志):")
        print("  [OK] python scripts/debug/restart/restart_safe.py restart")
        print()
        print("或者手动启动时必须重定向:")
        print("  [OK] python -u waitress_server.py > scripts/logs/backend.out 2> scripts/logs/backend.err")
        return 1
    else:
        _log("后端日志正常更新", "OK")
        return 0


if __name__ == "__main__":
    sys.exit(main() or 0)