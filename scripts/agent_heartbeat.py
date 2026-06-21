#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Agent Status 心跳维护脚本 (V2 新增)

基于 2026-06-20 多 Agent 通信缺失事故：
- Agent A 改类，Agent B 写测试，Agent C 错误诊断，无人知全局

提供：
- init: 初始化 agent status
- heartbeat: 更新心跳
- update: 更新状态
- list: 列出所有 agent status
- check: 检查超时未更新的 agent
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


AGENTS_DIR = Path('.trae/agents')
HEARTBEAT_TIMEOUT_MINUTES = 5


def get_status_path(agent_name: str) -> Path:
    """获取 agent status 文件路径"""
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    return AGENTS_DIR / f'{agent_name}.json'


def load_status(agent_name: str) -> dict:
    """加载 agent status"""
    path = get_status_path(agent_name)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding='utf-8'))


def save_status(agent_name: str, status: dict) -> None:
    """保存 agent status"""
    path = get_status_path(agent_name)
    path.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding='utf-8')


def init_status(
    agent_name: str,
    task: str,
    worktree: Optional[str] = None,
    port: Optional[int] = None,
    locked_files: Optional[list] = None,
    sandbox_status: str = 'healthy',
) -> dict:
    """初始化 agent status"""
    now = datetime.now().isoformat()
    status = {
        'agent_name': agent_name,
        'task': task,
        'worktree': worktree or f'../{agent_name}-worktree',
        'port': port,
        'locked_files': locked_files or [],
        'sandbox_status': sandbox_status,
        'status': 'starting',
        'started_at': now,
        'last_heartbeat': now,
        'last_action': 'initialized',
        'blocked_reason': None,
    }
    save_status(agent_name, status)
    return status


def update_heartbeat(agent_name: str, action: Optional[str] = None, status: Optional[str] = None) -> dict:
    """更新心跳"""
    current = load_status(agent_name)
    if not current:
        raise ValueError(f"Agent status not found: {agent_name}")

    current['last_heartbeat'] = datetime.now().isoformat()
    if action:
        current['last_action'] = action
    if status:
        current['status'] = status

    save_status(agent_name, current)
    return current


def update_status(agent_name: str, **kwargs) -> dict:
    """更新任意字段"""
    current = load_status(agent_name)
    if not current:
        raise ValueError(f"Agent status not found: {agent_name}")

    for key, value in kwargs.items():
        if key in current:
            current[key] = value

    current['last_heartbeat'] = datetime.now().isoformat()
    save_status(agent_name, current)
    return current


def list_all_agents() -> list:
    """列出所有 agent status"""
    if not AGENTS_DIR.exists():
        return []

    agents = []
    for path in sorted(AGENTS_DIR.glob('*.json')):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            agents.append(data)
        except Exception as e:
            print(f'[WARN] 读取 {path} 失败: {e}')

    return agents


def check_timeouts(timeout_minutes: int = HEARTBEAT_TIMEOUT_MINUTES) -> list:
    """检查超时的 agent"""
    agents = list_all_agents()
    now = datetime.now()
    timed_out = []

    for agent in agents:
        last_hb = agent.get('last_heartbeat')
        if not last_hb:
            timed_out.append({
                'agent': agent['agent_name'],
                'reason': 'no_heartbeat',
            })
            continue

        last_hb_dt = datetime.fromisoformat(last_hb)
        age = (now - last_hb_dt).total_seconds() / 60

        if age > timeout_minutes:
            timed_out.append({
                'agent': agent['agent_name'],
                'reason': f'heartbeat_timeout_{age:.1f}min',
                'last_action': agent.get('last_action'),
            })

    return timed_out


def detect_conflicts(my_agent: str, my_locked_files: list) -> list:
    """检测文件锁定冲突"""
    agents = list_all_agents()
    conflicts = []

    my_files = set(my_locked_files)
    for agent in agents:
        if agent['agent_name'] == my_agent:
            continue

        other_files = set(agent.get('locked_files', []))
        overlap = my_files & other_files
        if overlap:
            conflicts.append({
                'agent': agent['agent_name'],
                'conflicting_files': list(overlap),
            })

    return conflicts


def main():
    parser = argparse.ArgumentParser(description='Agent Status 心跳维护 (V2)')
    subparsers = parser.add_subparsers(dest='action', help='子命令')

    # init
    init_p = subparsers.add_parser('init', help='初始化 agent status')
    init_p.add_argument('--agent', required=True, help='Agent 名称')
    init_p.add_argument('--task', required=True, help='当前任务')
    init_p.add_argument('--worktree', help='Worktree 路径')
    init_p.add_argument('--port', type=int, help='端口号')
    init_p.add_argument('--lock', action='append', default=[], help='锁定的文件（可多次指定）')
    init_p.add_argument('--sandbox', default='healthy', help='沙箱状态')

    # heartbeat
    hb_p = subparsers.add_parser('heartbeat', help='更新心跳')
    hb_p.add_argument('--agent', required=True, help='Agent 名称')
    hb_p.add_argument('--action', help='当前动作')
    hb_p.add_argument('--status', help='当前状态')

    # update
    upd_p = subparsers.add_parser('update', help='更新字段')
    upd_p.add_argument('--agent', required=True, help='Agent 名称')
    upd_p.add_argument('--status', help='status 字段')
    upd_p.add_argument('--action', help='last_action 字段')
    upd_p.add_argument('--blocked', help='blocked_reason 字段')
    upd_p.add_argument('--sandbox', help='sandbox_status 字段')

    # list
    subparsers.add_parser('list', help='列出所有 agent')

    # check
    check_p = subparsers.add_parser('check', help='检查超时')
    check_p.add_argument('--timeout', type=int, default=HEARTBEAT_TIMEOUT_MINUTES, help='超时阈值（分钟）')

    # detect-conflicts
    conf_p = subparsers.add_parser('detect-conflicts', help='检测文件冲突')
    conf_p.add_argument('--agent', required=True, help='我的 Agent 名称')
    conf_p.add_argument('--lock', action='append', default=[], help='我锁定的文件（可多次指定）')

    args = parser.parse_args()

    if args.action == 'init':
        status = init_status(
            agent_name=args.agent,
            task=args.task,
            worktree=args.worktree,
            port=args.port,
            locked_files=args.lock,
            sandbox_status=args.sandbox,
        )
        print(f'[OK] Agent status 初始化: {args.agent}')
        print(json.dumps(status, indent=2, ensure_ascii=False))

    elif args.action == 'heartbeat':
        status = update_heartbeat(args.agent, action=args.action_str if hasattr(args, 'action_str') else args.action, status=args.status)
        print(f'[OK] Heartbeat 更新: {args.agent}')

    elif args.action == 'update':
        kwargs = {}
        if args.status:
            kwargs['status'] = args.status
        if args.action:
            kwargs['last_action'] = args.action
        if args.blocked:
            kwargs['blocked_reason'] = args.blocked
        if args.sandbox:
            kwargs['sandbox_status'] = args.sandbox
        status = update_status(args.agent, **kwargs)
        print(f'[OK] Status 更新: {args.agent}')
        print(json.dumps(status, indent=2, ensure_ascii=False))

    elif args.action == 'list':
        agents = list_all_agents()
        if not agents:
            print('[INFO] 没有 agent status')
            return
        for agent in agents:
            print(f'\n[{agent["agent_name"]}]')
            print(f'  task: {agent.get("task")}')
            print(f'  status: {agent.get("status")}')
            print(f'  sandbox: {agent.get("sandbox_status")}')
            print(f'  last_action: {agent.get("last_action")}')
            print(f'  last_heartbeat: {agent.get("last_heartbeat")}')

    elif args.action == 'check':
        timed_out = check_timeouts(args.timeout)
        if timed_out:
            print(f'[WARN] 发现 {len(timed_out)} 个超时 agent:')
            for t in timed_out:
                print(f'  - {t["agent"]}: {t["reason"]}')
            sys.exit(1)
        else:
            print(f'[OK] 所有 agent 心跳正常（阈值 {args.timeout} 分钟）')

    elif args.action == 'detect-conflicts':
        conflicts = detect_conflicts(args.agent, args.lock)
        if conflicts:
            print(f'[FAIL] 发现 {len(conflicts)} 个文件冲突:')
            for c in conflicts:
                print(f'  - 与 {c["agent"]} 冲突: {c["conflicting_files"]}')
            sys.exit(1)
        else:
            print(f'[OK] 无文件冲突')

    else:
        parser.print_help()


if __name__ == '__main__':
    main()