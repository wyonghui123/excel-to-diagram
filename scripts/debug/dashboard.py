#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
调试控制台 Dashboard - V2 优化 (v2026.06.21)

背景：V1 调试基础设施已建立 7 个工具，但需要分别调用。
     调试时往往需要快速回答多个问题 → 调用多个工具 → 浪费时间。

本工具：整合所有 V1 工具到一个交互式控制台

核心功能：
- 一键运行 diagnose + 各工具的状态
- 显示调试环境快照
- 智能推荐下一步操作

用法：
    # 显示完整 dashboard
    python scripts/debug/dashboard.py

    # 启动调试会话（启动会话 + 显示 dashboard）
    python scripts/debug/dashboard.py start --task "修复 X"

    # 监控模式（每 30 秒刷新）
    python scripts/debug/dashboard.py monitor --interval 30

    # 仅显示关键状态（精简模式）
    python scripts/debug/dashboard.py --brief
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# 修复 Windows GBK 编码问题
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass



def _log(msg: str, level: str = "INFO"):
    icons = {"OK": "[OK]", "FAIL": "[X]", "WARN": "[!]", "INFO": "[i]"}
    print(f"{icons.get(level, '[?]}')} {msg}")


def run_subprocess(cmd, timeout: int = 15) -> Dict[str, Any]:
    """运行子命令并返回结构化结果"""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
            cwd=str(PROJECT_ROOT),
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "timeout", "stdout": "", "stderr": ""}
    except Exception as e:
        return {"success": False, "error": str(e), "stdout": "", "stderr": ""}


def section(title: str, char: str = "="):
    """打印分节标题"""
    print()
    print(char * 70)
    print(title)
    print(char * 70)


def quick_status() -> Dict[str, Any]:
    """快速状态检查（精简版）"""
    section("快速状态 - Quick Status")

    # 沙箱
    sandbox = run_subprocess(["python", "scripts/check_sandbox_status.py"], timeout=10)
    sandbox_status = "OK" if "HEALTHY" in sandbox["stdout"] else "FAIL"
    icon = "[OK]" if sandbox_status == "OK" else "[X]"
    print(f"  {icon} 沙箱: {sandbox_status}")

    # 后端
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    port_ok = (s.connect_ex(("127.0.0.1", 3010)) == 0)
    s.close()

    health = run_subprocess(
        ["curl.exe", "-s", "-o", "NUL", "-w", "%{http_code}",
         "http://localhost:3010/health"],
        timeout=5,
    )
    health_code = health["stdout"].strip() if health["success"] else "?"

    if port_ok and health_code in ("200", "204"):
        backend_status = "OK"
    elif port_ok:
        backend_status = f"WARN (health={health_code})"
    else:
        backend_status = "FAIL (port not listening)"

    icon = "[OK]" if backend_status == "OK" else "[X]" if "FAIL" in backend_status else "[!]"
    print(f"  {icon} 后端: {backend_status}")

    # HEAD
    head = run_subprocess(["git", "rev-parse", "--short", "HEAD"], timeout=5)
    head_hash = head["stdout"].strip() if head["success"] else "?"
    branch = run_subprocess(["git", "rev-parse", "--abbrev-ref", "HEAD"], timeout=5)
    branch_name = branch["stdout"].strip() if branch["success"] else "?"
    print(f"  [i] 分支: {branch_name}  HEAD: {head_hash}")

    # 工作树
    status = run_subprocess(["git", "status", "--short"], timeout=5)
    if status["success"]:
        n_files = len([l for l in status["stdout"].splitlines() if l.strip()])
        if n_files == 0:
            wt_status = "OK"
            icon = "[OK]"
        elif n_files <= 5:
            wt_status = f"OK ({n_files} files)"
            icon = "[OK]"
        else:
            wt_status = f"FAIL ({n_files} files > 5)"
            icon = "[X]"
        print(f"  {icon} 工作树: {wt_status}")

    # 最近错误
    extractor = run_subprocess([
        "python", "scripts/debug/log/extractor.py",
        "--level", "ERROR", "--tail", "20",
    ], timeout=10)
    if extractor["success"]:
        error_lines = [l for l in extractor["stdout"].splitlines()
                       if "ERROR" in l or "FATAL" in l]
        n_errors = len(error_lines)
        if n_errors == 0:
            icon = "[OK]"
            err_status = "OK"
        elif n_errors <= 5:
            icon = "[!]"
            err_status = f"WARN ({n_errors} errors)"
        else:
            icon = "[X]"
            err_status = f"FAIL ({n_errors} errors)"
        print(f"  {icon} 最近错误: {err_status}")

    # Sessions
    sessions_dir = PROJECT_ROOT / ".trae" / "debug" / "sessions"
    if sessions_dir.exists():
        sessions = [s for s in sessions_dir.glob("session-*.yaml")]
        n = len(sessions)
        if n > 0:
            sessions.sort(key=lambda s: s.stat().st_mtime, reverse=True)
            latest = sessions[0].stem
            print(f"  [i] 历史会话: {n} 个（最近: {latest}）")

    return {"sandbox": sandbox_status, "backend": backend_status, "head": head_hash}


def full_dashboard():
    """完整 dashboard"""
    print()
    print("#" * 70)
    print("# 调试 Dashboard - V2 优化")
    print(f"# {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("#" * 70)

    # 1. 快速状态
    quick_status()

    # 2. 详细诊断
    section("详细诊断 - diagnose.py", char="-")
    diagnose = run_subprocess(["python", "scripts/debug/env/diagnose.py"], timeout=30)
    # diagnose 退出码可能非 0（有 FAIL 项时退出 1），不影响输出
    if diagnose["stdout"].strip():
        for line in diagnose["stdout"].splitlines():
            if line.strip():
                print(f"  {line}")
    elif diagnose["stderr"]:
        print(f"  [X] diagnose.py 失败: {diagnose['stderr'][:200]}")
    else:
        print(f"  [X] diagnose.py 失败: {diagnose.get('error', 'unknown')}")

    # 3. 工具清单
    section("可用工具 - V1 调试基础设施", char="-")
    tools = [
        ("log/extractor.py", "日志提取（关键字/级别/时间窗口）"),
        ("log/reader.py", "实时日志跟踪（tail -f）"),
        ("inspect/user_context.py", "用户上下文查询"),
        ("inspect/table_schema.py", "表结构 + 字段映射检测"),
        ("inspect/code_map.py", "代码地图快速定位"),
        ("restart/restart_safe.py", "安全重启（杀所有 waitress）"),
        ("env/diagnose.py", "综合诊断（10+ 检查）"),
        ("verify/run_interceptor_tests.sh", "一键验证"),
        ("sessions/auto_record.py", "调试会话自动记录"),
    ]
    for tool, desc in tools:
        path = PROJECT_ROOT / "scripts" / "debug" / tool
        exists = "[OK]" if path.exists() else "[X]"
        print(f"  {exists} {tool:<35} - {desc}")

    # 4. 推荐下一步
    section("推荐下一步", char="-")

    # 检查是否有未提交文件
    status = run_subprocess(["git", "status", "--short"], timeout=5)
    if status["success"]:
        n_files = len([l for l in status["stdout"].splitlines() if l.strip()])
        if n_files > 5:
            print(f"  [X] 工作树有 {n_files} 个未提交文件 - 必须先 commit（V2 铁律 4）")

    # 检查沙箱
    sandbox = run_subprocess(["python", "scripts/check_sandbox_status.py"], timeout=10)
    if "HEALTHY" not in sandbox["stdout"]:
        print(f"  [X] 沙箱异常 - 切 Read-First 工作流")

    # 检查 DEBUG 残留
    debug = run_subprocess(["git", "grep", "-l", r"#\s*\[DEBUG\]", "--", "*.py"], timeout=10)
    if debug["success"] and debug["stdout"].strip():
        n = len([l for l in debug["stdout"].splitlines() if l.strip()])
        print(f"  [!] 有 {n} 处 # [DEBUG] 标记遗留 - 调试后清理")

    print(f"  [i] 调试前: python scripts/debug/env/diagnose.py")
    print(f"  [i] 调试后: bash scripts/debug/verify/run_interceptor_tests.sh")


def cmd_start(args):
    """启动调试会话（开 dashboard + 开 session）"""
    # 启动 session
    record = run_subprocess([
        "python", "scripts/debug/sessions/auto_record.py", "start",
        "--agent", os.environ.get("AGENT_NAME", "agent"),
        "--task", args.task,
    ], timeout=10)
    print(record["stdout"])

    # 显示 dashboard
    full_dashboard()


def cmd_monitor(args):
    """监控模式（定时刷新）"""
    interval = args.interval
    print(f"监控模式（每 {interval} 秒刷新，Ctrl+C 退出）")
    try:
        while True:
            full_dashboard()
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n退出监控")


def export_markdown(output_path: Path):
    """导出 dashboard 为 markdown 报告"""
    # 收集所有状态
    section_lines = []

    section_lines.append("# 调试环境报告 (Debug Environment Report)")
    section_lines.append("")
    section_lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    section_lines.append("")

    # 1. 快速状态
    section_lines.append("## 1. 快速状态")
    section_lines.append("")

    # 沙箱
    sandbox = run_subprocess(["python", "scripts/check_sandbox_status.py"], timeout=10)
    sandbox_status = "OK" if "HEALTHY" in sandbox["stdout"] else "FAIL"
    section_lines.append(f"- **沙箱**: {sandbox_status}")

    # 后端
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    port_ok = (s.connect_ex(("127.0.0.1", 3010)) == 0)
    s.close()

    health = run_subprocess(
        ["curl.exe", "-s", "-o", "NUL", "-w", "%{http_code}",
         "http://localhost:3010/health"],
        timeout=5,
    )
    health_code = health["stdout"].strip() if health["success"] else "?"

    backend_status = "OK" if (port_ok and health_code in ("200", "204")) else "FAIL"
    section_lines.append(f"- **后端**: {backend_status} (port={port_ok}, /health={health_code})")

    # HEAD
    head = run_subprocess(["git", "rev-parse", "--short", "HEAD"], timeout=5)
    head_hash = head["stdout"].strip() if head["success"] else "?"
    branch = run_subprocess(["git", "rev-parse", "--abbrev-ref", "HEAD"], timeout=5)
    branch_name = branch["stdout"].strip() if branch["success"] else "?"
    section_lines.append(f"- **分支**: `{branch_name}`  HEAD: `{head_hash}`")

    # 工作树
    status = run_subprocess(["git", "status", "--short"], timeout=5)
    if status["success"]:
        n_files = len([l for l in status["stdout"].splitlines() if l.strip()])
        section_lines.append(f"- **工作树**: {n_files} 个未提交文件 (限制 5)")

    # 最近错误
    extractor = run_subprocess([
        "python", "scripts/debug/log/extractor.py",
        "--level", "ERROR", "--tail", "50",
    ], timeout=10)
    if extractor["success"]:
        error_lines = [l for l in extractor["stdout"].splitlines()
                       if "ERROR" in l or "FATAL" in l]
        n_errors = len(error_lines)
        section_lines.append(f"- **最近错误**: {n_errors} 条")

    section_lines.append("")

    # 2. diagnose 详细
    section_lines.append("## 2. 详细诊断")
    section_lines.append("")
    section_lines.append("```")
    diagnose = run_subprocess(["python", "scripts/debug/env/diagnose.py"], timeout=30)
    if diagnose["stdout"]:
        for line in diagnose["stdout"].splitlines():
            if line.strip():
                section_lines.append(line)
    section_lines.append("```")
    section_lines.append("")

    # 3. 工具清单
    section_lines.append("## 3. 可用工具")
    section_lines.append("")
    tools = [
        ("log/extractor.py", "日志提取（关键字/级别/时间窗口）"),
        ("log/reader.py", "实时日志跟踪（tail -f）"),
        ("inspect/user_context.py", "用户上下文查询"),
        ("inspect/table_schema.py", "表结构 + 字段映射错误检测"),
        ("inspect/code_map.py", "代码地图快速定位"),
        ("restart/restart_safe.py", "安全重启（杀所有 waitress）"),
        ("env/diagnose.py", "综合诊断（10+ 检查）"),
        ("verify/run_interceptor_tests.sh", "一键验证"),
        ("sessions/auto_record.py", "调试会话自动记录"),
    ]
    section_lines.append("| 工具 | 状态 | 用途 |")
    section_lines.append("|------|------|------|")
    for tool, desc in tools:
        path = PROJECT_ROOT / "scripts" / "debug" / tool
        status = "OK" if path.exists() else "MISSING"
        section_lines.append(f"| `{tool}` | {status} | {desc} |")
    section_lines.append("")

    # 4. 最近的调试会话
    sessions_dir = PROJECT_ROOT / ".trae" / "debug" / "sessions"
    if sessions_dir.exists():
        sessions = sorted(sessions_dir.glob("session-*.yaml"),
                         key=lambda s: s.stat().st_mtime, reverse=True)
        if sessions:
            section_lines.append("## 4. 最近调试会话")
            section_lines.append("")
            section_lines.append("| 会话ID | 任务 | 状态 | 开始时间 |")
            section_lines.append("|--------|------|------|----------|")
            for s in sessions[:10]:  # 最近 10 个
                session_data = {}
                try:
                    import yaml
                    with open(s, encoding="utf-8") as f:
                        session_data = yaml.safe_load(f) or {}
                except Exception:
                    pass
                task = session_data.get("task", "?")[:40]
                status = session_data.get("status", "?")
                started = session_data.get("started_at", "?")[:19].replace("T", " ")
                section_lines.append(f"| `{s.stem}` | {task} | {status} | {started} |")
            section_lines.append("")

    # 5. 推荐下一步
    section_lines.append("## 5. 推荐下一步")
    section_lines.append("")

    status = run_subprocess(["git", "status", "--short"], timeout=5)
    if status["success"]:
        n_files = len([l for l in status["stdout"].splitlines() if l.strip()])
        if n_files > 5:
            section_lines.append(f"- [ ] **必须先 commit** 工作树 {n_files} 个未提交文件（V2 铁律 4）")

    debug = run_subprocess(["git", "grep", "-l", r"#\s*\[DEBUG\]", "--", "*.py"], timeout=10)
    if debug["success"] and debug["stdout"].strip():
        n = len([l for l in debug["stdout"].splitlines() if l.strip()])
        section_lines.append(f"- [ ] 清理 {n} 处 # [DEBUG] 标记遗留")

    section_lines.append("- [ ] 调试前: `python scripts/debug/env/diagnose.py`")
    section_lines.append("- [ ] 调试后: `bash scripts/debug/verify/run_interceptor_tests.sh`")
    section_lines.append("")

    section_lines.append("---")
    section_lines.append(f"_Generated by scripts/debug/dashboard.py at {datetime.now().isoformat()}_")

    # 写入文件
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(section_lines))

    _log(f"已导出 markdown 报告: {output_path}", "OK")


def main():
    parser = argparse.ArgumentParser(
        description="调试控制台 Dashboard - V2 优化",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--brief", action="store_true", help="精简模式")

    sub = parser.add_subparsers(dest="cmd")

    # start
    start_p = sub.add_parser("start", help="启动调试会话 + 显示 dashboard")
    start_p.add_argument("--task", required=True, help="任务描述")

    # monitor
    monitor_p = sub.add_parser("monitor", help="定时刷新 dashboard")
    monitor_p.add_argument("--interval", type=int, default=30, help="刷新间隔（秒）")

    # export
    export_p = sub.add_parser("export", help="导出 markdown 报告")
    export_p.add_argument("--output", type=Path, required=True,
                          help="输出路径（如 .trae/debug/reports/report.md）")

    # progress
    progress_p = sub.add_parser("progress", help="显示调试进度（轮次 + 步骤）")
    progress_p.add_argument("--task", required=True, help="调试任务")
    progress_p.add_argument("--step", help="当前步骤名")
    progress_p.add_argument("--total-steps", type=int, default=5,
                            help="总步骤数（用于显示进度）")

    args = parser.parse_args()

    if args.cmd == "start":
        return cmd_start(args)
    elif args.cmd == "monitor":
        return cmd_monitor(args)
    elif args.cmd == "export":
        export_markdown(args.output)
        return 0
    elif args.cmd == "progress":
        return cmd_progress(args)
    else:
        full_dashboard()
        return 0


PROGRESS_FILE = PROJECT_ROOT / ".trae" / "debug" / ".progress.json"


def cmd_progress(args):
    """显示调试进度（轮次 + 步骤）"""
    # 读取或初始化进度文件
    progress = {}
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE, encoding="utf-8") as f:
                progress = json.load(f)
        except (json.JSONDecodeError, OSError):
            progress = {}

    if args.step:
        # 记录一步
        progress.setdefault("steps", []).append({
            "task": args.task,
            "step": args.step,
            "timestamp": datetime.now().isoformat(),
        })
        progress["current_step"] = args.step
        progress["updated_at"] = datetime.now().isoformat()

        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)

    # 显示进度
    print("=" * 70)
    print(f"调试进度 - V3 调试基础设施 D")
    print("=" * 70)
    print(f"任务: {args.task}")
    print()

    steps = progress.get("steps", [])
    if not steps:
        print("  (无记录步骤)")
        print()
        print("💡 用法:")
        print("  python scripts/debug/dashboard.py progress --task '...' --step '重启后端'")
        print("  python scripts/debug/dashboard.py progress --task '...' --step '验证修复'")
        print()
        return 0

    # 找到当前任务的所有步骤
    task_steps = [s for s in steps if s["task"] == args.task]

    if not task_steps:
        # 显示所有任务
        print(f"  任务 '{args.task}' 没有记录步骤")
        print(f"  共有 {len(set(s['task'] for s in steps))} 个任务的记录")
        return 0

    # 显示步骤
    print(f"## 任务 '{args.task}' 的步骤（共 {len(task_steps)} 步）")
    print()
    for i, step in enumerate(task_steps, 1):
        ts = step["timestamp"][:19].replace("T", " ")
        print(f"  [{i}] {ts} | {step['step']}")

    # 检测"重启-验证循环"（重复出现的步骤）
    step_counts: Dict[str, int] = {}
    for s in task_steps:
        s_name = s["step"].lower()
        step_counts[s_name] = step_counts.get(s_name, 0) + 1

    repeated = {k: v for k, v in step_counts.items() if v >= 3}
    if repeated:
        print()
        print(f"## ⚠️ 检测到重复步骤（>= 3 次）")
        for k, v in repeated.items():
            print(f"  - '{k}': 出现 {v} 次（可能是调试循环，建议停下来评估）")

    # 进度可视化
    if args.total_steps:
        print()
        print(f"## 进度: [{len(task_steps)}/{args.total_steps}]")
        ratio = min(len(task_steps) / args.total_steps, 1.0)
        bar = "█" * int(ratio * 30) + "░" * (30 - int(ratio * 30))
        print(f"  [{bar}] {ratio*100:.0f}%")

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)