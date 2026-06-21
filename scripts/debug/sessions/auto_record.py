#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
调试会话自动记录 - 调试基础设施 P1 (v2026.06.21)

背景：调试会话需要"可追溯"，但手动写 YAML 太繁琐。
     Agent 经常"调试完忘了记录"。

核心功能：
- 自动启动会话（start）
- 记录关键事件（log）
- 关联代码修改（link-commit）
- 标记完成（end）
- 列出所有会话（list）

会话存储：
- 默认: .trae/debug/sessions/session-YYYYMMDD-NNN.yaml
- 可通过 --session-id 指定

用法：
    # 启动新会话
    python scripts/debug/sessions/auto_record.py start \
        --agent agent-X \
        --task "修复 write_scope_interceptor 字段映射错误"

    # 记录调查步骤
    python scripts/debug/sessions/auto_record.py log \
        --session-id session-20260621-001 \
        --step "检查 relationships 表字段映射" \
        --finding "source_bo_code 全 NULL，应该用 source_code"

    # 关联代码修改
    python scripts/debug/sessions/auto_record.py link-commit \
        --session-id session-20260621-001 \
        --commit-hash a15a61c \
        --files "meta/core/action_executor.py,meta/core/interceptors/write_scope_interceptor.py"

    # 记录验证结果
    python scripts/debug/sessions/auto_record.py verify \
        --session-id session-20260621-001 \
        --method "scripts/debug/restart/restart_safe.py verify" \
        --result PASS

    # 结束会话
    python scripts/debug/sessions/auto_record.py end \
        --session-id session-20260621-001 \
        --status completed \
        --lesson "字段映射错误：代码用 NULL 字段"

    # 列出所有会话
    python scripts/debug/sessions/auto_record.py list

    # 显示会话详情
    python scripts/debug/sessions/auto_record.py show --session-id session-20260621-001
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# 修复 Windows GBK 编码问题
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SESSIONS_DIR = PROJECT_ROOT / ".trae" / "debug" / "sessions"


def _log(msg: str, level: str = "INFO"):
    icons = {"OK": "[OK]", "FAIL": "[X]", "WARN": "[!]", "INFO": "[i]"}
    print(f"{icons.get(level, '[?]}')} {msg}")


def ensure_sessions_dir():
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def get_session_path(session_id: str) -> Path:
    """获取会话文件路径"""
    return SESSIONS_DIR / f"{session_id}.yaml"


def load_session(session_id: str) -> Dict[str, Any]:
    """加载会话（用 PyYAML）"""
    path = get_session_path(session_id)
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        _log(f"YAML 解析失败: {e}", "FAIL")
        return {}


def save_session(session: Dict[str, Any]):
    """保存会话（用 PyYAML）"""
    ensure_sessions_dir()
    session_id = session.get("session_id", "unknown")
    path = get_session_path(session_id)

    # 默认使用 utf-8 + 中文友好
    class _IndentDumper(yaml.SafeDumper):
        def increase_indent(self, flow=False, indentless=False):
            return super().increase_indent(flow, False)

    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(session, f, Dumper=_IndentDumper,
                  default_flow_style=False,
                  allow_unicode=True,
                  sort_keys=False,
                  indent=2,
                  width=120)


def cmd_start(args):
    """启动新会话"""
    ensure_sessions_dir()

    # 自动生成 session_id
    today = datetime.now().strftime("%Y%m%d")
    existing = list(SESSIONS_DIR.glob(f"session-{today}-*.yaml"))
    next_num = len(existing) + 1
    session_id = f"session-{today}-{next_num:03d}"

    session = {
        "session_id": session_id,
        "started_at": datetime.now().isoformat() + "Z",
        "agent": args.agent,
        "task": args.task,
        "environment": {
            "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "head_commit": _git("rev-parse", "--short", "HEAD"),
            "test_user": args.test_user or "N/A",
        },
        "investigation": [],
        "fixes": [],
        "verification": [],
        "lessons": [],
        "status": "in_progress",
    }

    save_session(session)
    _log(f"会话已启动: {session_id}", "OK")
    print()
    print(f"下一步:")
    print(f"  python scripts/debug/sessions/auto_record.py log --session-id {session_id} --step '...'")
    print(f"  python scripts/debug/sessions/auto_record.py end --session-id {session_id}")
    return 0


def cmd_log(args):
    """记录调查步骤"""
    session = load_session(args.session_id)
    if not session:
        _log(f"会话不存在: {args.session_id}", "FAIL")
        return 1

    step_num = len(session.get("investigation", [])) + 1
    entry = {
        "step": step_num,
        "action": args.step,
        "finding": args.finding or "",
    }
    if "tool_used" in args and args.tool_used:
        entry["tool_used"] = args.tool_used

    session.setdefault("investigation", []).append(entry)
    save_session(session)
    _log(f"已记录 step {step_num}: {args.step[:60]}{'...' if len(args.step) > 60 else ''}", "OK")
    return 0


def cmd_link_commit(args):
    """关联 commit"""
    session = load_session(args.session_id)
    if not session:
        return 1

    files = [f.strip() for f in args.files.split(",") if f.strip()]
    session.setdefault("fixes", []).append({
        "commit": args.commit_hash,
        "files": files,
    })
    save_session(session)
    _log(f"已关联 commit {args.commit_hash[:8]}", "OK")
    return 0


def cmd_verify(args):
    """记录验证结果"""
    session = load_session(args.session_id)
    if not session:
        return 1

    session.setdefault("verification", []).append({
        "method": args.method,
        "result": args.result,
    })
    save_session(session)
    _log(f"已记录验证: {args.method} → {args.result}", "OK")
    return 0


def cmd_end(args):
    """结束会话"""
    session = load_session(args.session_id)
    if not session:
        return 1

    session["status"] = args.status
    session["completed_at"] = datetime.now().isoformat() + "Z"

    if args.lesson:
        for lesson in args.lesson.split("|"):
            lesson = lesson.strip()
            if lesson:
                session.setdefault("lessons", []).append(lesson)

    save_session(session)
    _log(f"会话已结束: status={args.status}", "OK")
    return 0


def cmd_list(args):
    """列出所有会话"""
    ensure_sessions_dir()
    sessions = sorted(SESSIONS_DIR.glob("session-*.yaml"), reverse=True)

    if not sessions:
        print("没有会话")
        return 0

    print(f"调试会话（{len(sessions)} 个）")
    print()
    print(f"  {'会话ID':<30} {'状态':<12} {'任务':<40} {'开始时间'}")
    print(f"  {'-'*30} {'-'*12} {'-'*40} {'-'*20}")

    for s in sessions:
        sess = load_session(s.stem)
        task = sess.get("task", "?")[:40]
        status = sess.get("status", "?")
        started = sess.get("started_at", "?")[:19].replace("T", " ")
        print(f"  {s.stem:<30} {status:<12} {task:<40} {started}")


def cmd_show(args):
    """显示会话详情"""
    session = load_session(args.session_id)
    if not session:
        _log(f"会话不存在: {args.session_id}", "FAIL")
        return 1

    print("=" * 70)
    print(f"会话: {session.get('session_id', '?')}")
    print("=" * 70)
    print(f"任务: {session.get('task', '?')}")
    print(f"Agent: {session.get('agent', '?')}")
    print(f"状态: {session.get('status', '?')}")
    print(f"开始: {session.get('started_at', '?')}")
    print(f"结束: {session.get('completed_at', '-')}")
    print()

    env = session.get("environment", {})
    if env:
        print("## 环境")
        for k, v in env.items():
            print(f"  {k}: {v}")
        print()

    inv = session.get("investigation", [])
    if inv:
        print(f"## 调查步骤（{len(inv)}）")
        for step in inv:
            if isinstance(step, dict):
                print(f"  [{step.get('step', '?')}] {step.get('action', '?')}")
                if step.get('tool_used'):
                    print(f"      工具: {step['tool_used']}")
                if step.get('finding'):
                    print(f"      发现: {step['finding']}")
            else:
                print(f"  - {step}")
        print()

    fixes = session.get("fixes", [])
    if fixes:
        print(f"## 修复（{len(fixes)}）")
        for fix in fixes:
            if isinstance(fix, dict):
                print(f"  commit: {fix.get('commit', '?')}")
                files = fix.get('files', [])
                for f in files:
                    print(f"    - {f}")
            else:
                print(f"  - {fix}")
        print()

    verifications = session.get("verification", [])
    if verifications:
        print(f"## 验证（{len(verifications)}）")
        for v in verifications:
            if isinstance(v, dict):
                print(f"  [{v.get('result', '?')}] {v.get('method', '?')}")
            else:
                print(f"  - {v}")
        print()

    lessons = session.get("lessons", [])
    if lessons:
        print(f"## 教训（{len(lessons)}）")
        for i, lesson in enumerate(lessons, 1):
            print(f"  {i}. {lesson}")


def _git(*args):
    """运行 git 命令"""
    try:
        result = subprocess.run(
            ["git"] + list(args), capture_output=True, text=True, timeout=10,
            cwd=str(PROJECT_ROOT),
        )
        return result.stdout.strip() if result.returncode == 0 else "?"
    except Exception:
        return "?"


def main():
    parser = argparse.ArgumentParser(
        description="调试会话自动记录 - V1 调试基础设施 P1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # start
    start_p = sub.add_parser("start", help="启动新会话")
    start_p.add_argument("--agent", required=True, help="Agent 名称")
    start_p.add_argument("--task", required=True, help="任务描述")
    start_p.add_argument("--test-user", help="测试用户")

    # log
    log_p = sub.add_parser("log", help="记录调查步骤")
    log_p.add_argument("--session-id", required=True)
    log_p.add_argument("--step", required=True, help="做了什么")
    log_p.add_argument("--finding", help="发现")
    log_p.add_argument("--tool-used", help="使用的工具")

    # link-commit
    link_p = sub.add_parser("link-commit", help="关联 commit")
    link_p.add_argument("--session-id", required=True)
    link_p.add_argument("--commit-hash", required=True)
    link_p.add_argument("--files", required=True, help="修改的文件（逗号分隔）")

    # verify
    verify_p = sub.add_parser("verify", help="记录验证结果")
    verify_p.add_argument("--session-id", required=True)
    verify_p.add_argument("--method", required=True)
    verify_p.add_argument("--result", choices=["PASS", "FAIL", "WARN"], required=True)

    # end
    end_p = sub.add_parser("end", help="结束会话")
    end_p.add_argument("--session-id", required=True)
    end_p.add_argument("--status", choices=["completed", "failed", "abandoned"],
                       default="completed")
    end_p.add_argument("--lesson", help="教训（多个用 | 分隔）")

    # list
    sub.add_parser("list", help="列出所有会话")

    # show
    show_p = sub.add_parser("show", help="显示会话详情")
    show_p.add_argument("--session-id", required=True)

    args = parser.parse_args()

    if args.cmd == "start":
        return cmd_start(args)
    elif args.cmd == "log":
        return cmd_log(args)
    elif args.cmd == "link-commit":
        return cmd_link_commit(args)
    elif args.cmd == "verify":
        return cmd_verify(args)
    elif args.cmd == "end":
        return cmd_end(args)
    elif args.cmd == "list":
        return cmd_list(args)
    elif args.cmd == "show":
        return cmd_show(args)

    return 1


if __name__ == "__main__":
    sys.exit(main() or 0)