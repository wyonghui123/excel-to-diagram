#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
agent_exec.py — Sandbox CWD 劫持绕过 + 统一执行入口

解决问题:
  Trae Sandbox 在某些情况下强制劫持 shell CWD 到其他 agent 的目录,
  导致 `cd <worktree>` 后命令在错的目录执行。这是开发智能体在
  phase13-worktree 执行命令时遇到的根本性问题。

设计:
  - 显式指定 wt 路径, 不依赖 shell CWD
  - 通过 Python subprocess.Popen 用 cwd=<wt_path> 启动
  - 支持 --env 注入环境变量
  - 输出转发到 stdout (带 [wt-name] 前缀)

用法:
  # git 在指定 wt 执行
  python scripts/agent_exec.py --wt phase13-worktree -- git status

  # pytest 在指定 wt 执行
  python scripts/agent_exec.py --wt phase13-worktree -- python -m pytest meta/tests/test_foo.py -q

  # 注入 env 后执行
  python scripts/agent_exec.py --wt release-prep --env AGENT_PORT=3006 -- python scripts/_wt_service.py start-be release-prep
"""
import argparse
import os
import subprocess
import sys


def resolve_wt(wt_name: str) -> str:
    """解析 wt 名为绝对路径"""
    candidates = [
        rf"D:\filework\worktrees\{wt_name}",
        rf"D:\filework\{wt_name}",  # phase13-worktree 在 d:\filework 下
    ]
    for c in candidates:
        if os.path.exists(os.path.join(c, ".git")):
            return c
    raise FileNotFoundError(f"worktree '{wt_name}' not found in {candidates}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--wt", required=True, help="worktree 名称")
    p.add_argument("--env", action="append", default=[],
                   help="env 变量, 格式 KEY=VAL (可多次)")
    p.add_argument("--timeout", type=int, default=600, help="超时秒数")
    p.add_argument("rest", nargs=argparse.REMAINDER, help="要执行的命令")
    args = p.parse_args()

    # 消耗分隔符 '--'
    if args.rest and args.rest[0] == "--":
        args.rest = args.rest[1:]
    if not args.rest:
        print("Usage: agent_exec.py --wt <name> [--env KEY=VAL]... -- <command>")
        return 1

    try:
        wt_path = resolve_wt(args.wt)
    except FileNotFoundError as e:
        print(f"[ERR] {e}")
        return 1

    # 解析 env
    env = os.environ.copy()
    for kv in args.env:
        if "=" in kv:
            k, v = kv.split("=", 1)
            env[k] = v

    print(f"[agent_exec] cwd={wt_path} cmd={' '.join(args.rest)}")
    try:
        r = subprocess.run(
            args.rest,
            cwd=wt_path,
            env=env,
            timeout=args.timeout,
        )
        return r.returncode
    except subprocess.TimeoutExpired:
        print(f"[agent_exec] timeout after {args.timeout}s")
        return 124


if __name__ == "__main__":
    sys.exit(main() or 0)
