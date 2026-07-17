#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_agent_health.py - Dev Agent 自身健康检查 (V007.86h Layer 3)

V007.86f 教训 (Layer 3):
- Dev Agent 自己挂掉 / 失忆, 没人知道
- V007.76 教训: Agent 之前失忆, 不知道自己是谁 / 在哪个 worktree
- V007.80 §0.6 加身份检查 SOP (人工), 但 Agent 不强制执行

V007.86h 解决:
- check_agent_health.py 5 分钟跑一次 (新计划任务)
- 检查:
  1. git 状态: 无未提交改动 > 30 min
  2. git 同步: 不比 origin 早 > 24h
  3. 计划任务健康: 3 个 yonaa_* 任务都 exit 0/1
  4. 清单同步: infra_manifest.json 里的 script 路径都存在
  5. Agent 身份: V007.80 §0.6 SOP (worktree / HEAD / 最近 3 commit)
- 异常 -> 飞书告警"Agent 健康异常"

退出码:
    0 - 健康
    1 - 异常
    2 - 脚本错误
"""
import os
import sys
import time
import json
import argparse
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Tuple


# ====== 配置 ======
DEFAULT_MANIFEST = r'D:\filework\worktrees\release-prep\infra_manifest.json'
DEFAULT_CONFIG = r'D:\filework\worktrees\release-prep\tools\alert_monitor_config.json'
DEFAULT_STATE = r'D:\filework\worktrees\release-prep\tools\check_agent_health_state.json'

# 阈值
GIT_STALE_SEC = 1800          # git 未提交改动 > 30 min = 异常
GIT_BEHIND_SEC = 86400        # 比 origin 早 > 24h = 异常
TASK_RESULT_HEALTHY = {0, 1}  # exit 0/1 = 健康
MANIFEST_MISSING_SCRIPT_THRESHOLD = 0  # 0 个 script 不存在 = 正常
IDENTITY_CHECK_SCRIPT = r'D:\filework\worktrees\release-prep\tools\alert_monitor_v0760.py'

# 关键计划任务名 (从 infra_manifest 读)
TASK_NAMES = [
    r'\yonaa_alert_monitor',
    r'\yonaa_alert_monitor_health',
    r'\yonaa_auto_heal',
    r'\yonaa_agent_health',  # self
]

# 没跑过的任务默认 exit code (0x267011 = ERROR_FILE_NOT_FOUND 来自 schtasks)
# 也算正常, 等首次跑
TASK_NEVER_RUN_CODES = {267011, 0}


def run_cmd(cmd: List[str], timeout: int = 10) -> Tuple[bool, str, str]:
    """Run shell command, return (ok, stdout, stderr)"""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding='gbk', errors='replace', timeout=timeout
        )
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, '', str(e)


def check_git_clean(worktree: str) -> Tuple[bool, str]:
    """Check 1: git 状态 (无未提交改动 > 30 min)"""
    ok, stdout, stderr = run_cmd(['git', '-C', worktree, 'status', '--porcelain'])
    if not ok:
        return False, f'git status failed: {stderr[:200]}'
    if stdout.strip():
        # Has uncommitted changes
        # Get age of last change
        ok2, stdout2, _ = run_cmd(['git', '-C', worktree, 'log', '-1', '--format=%ct'])
        if ok2 and stdout2.strip():
            try:
                last_ts = int(stdout2.strip())
                age = int(time.time() - last_ts)
                if age > GIT_STALE_SEC:
                    return False, f'{len(stdout.strip().split(chr(10)))} uncommitted changes, last commit {age}s ago (> {GIT_STALE_SEC}s)'
            except ValueError:
                pass
        return False, f'{len(stdout.strip().split(chr(10)))} uncommitted changes'
    return True, 'git 干净'


def check_git_synced(worktree: str) -> Tuple[bool, str]:
    """Check 2: git 同步 (不比 origin 早 > 24h)"""
    # Get local HEAD commit time
    ok, stdout, _ = run_cmd(['git', '-C', worktree, 'log', '-1', '--format=%ct'])
    if not ok:
        return False, f'git log failed: {stdout[:200]}'
    try:
        local_ts = int(stdout.strip())
    except ValueError:
        return False, f'git log output not int: {stdout[:100]}'

    # Get origin HEAD commit time (best effort, may fail due to network)
    ok, stdout, _ = run_cmd(['git', '-C', worktree, 'log', 'origin/release/pre-2026-06-29', '-1', '--format=%ct'])
    if not ok or not stdout.strip():
        return True, f'origin 不可达, 跳过同步检查 (local HEAD {int(time.time() - local_ts)}s ago)'

    try:
        origin_ts = int(stdout.strip())
    except ValueError:
        return True, f'origin log not int, 跳过同步检查'

    diff = local_ts - origin_ts
    if diff > GIT_BEHIND_SEC:
        return False, f'local HEAD 早 origin {diff}s (> {GIT_BEHIND_SEC}s)'
    if diff < -300:  # local 5 min later than origin = ahead of origin (normal)
        return True, f'local 领先 origin {-diff}s (正常, ahead)'
    return True, f'local 跟 origin 同步 (diff {diff}s)'


def check_plan_tasks(manifest: Dict) -> Tuple[bool, str]:
    """Check 3: 3 个 yonaa_* 计划任务都健康"""
    bad_tasks = []
    for task_name in TASK_NAMES:
        ok, stdout, _ = run_cmd(['schtasks', '/Query', '/TN', task_name, '/V', '/FO', 'LIST'])
        if not ok:
            bad_tasks.append(f'{task_name}: schtasks failed')
            continue
        # Parse Last Result
        last_result = None
        for line in stdout.split('\n'):
            if line.startswith('Last Result:'):
                last_result = line.partition(':')[2].strip()
                break
        if last_result is None:
            bad_tasks.append(f'{task_name}: no Last Result')
            continue
        try:
            exit_code = int(last_result, 16)
        except ValueError:
            try:
                exit_code = int(last_result)
            except ValueError:
                bad_tasks.append(f'{task_name}: unparseable result {last_result!r}')
                continue
        if exit_code not in TASK_RESULT_HEALTHY and exit_code not in TASK_NEVER_RUN_CODES:
            bad_tasks.append(f'{task_name}: exit {exit_code}')

    if bad_tasks:
        return False, f'{len(bad_tasks)} 个任务不健康: ' + '; '.join(bad_tasks)
    return True, f'{len(TASK_NAMES)} 个任务健康'


def check_manifest_in_sync(worktree: str, manifest: Dict) -> Tuple[bool, str]:
    """Check 4: infra_manifest.json 里的 script 路径都存在"""
    components = manifest.get('components', {})
    missing = []
    for comp_id, comp in components.items():
        script_rel = comp.get('script', '')
        if not script_rel:
            continue
        # Resolve relative to worktree
        script_abs = os.path.join(worktree, script_rel.replace('/', os.sep))
        if not os.path.exists(script_abs):
            missing.append(f'{comp_id}: {script_rel}')

    if missing:
        return False, f'{len(missing)} 个 manifest script 不存在: ' + ', '.join(missing)
    return True, f'{len(components)} 个 manifest script 都存在'


def check_agent_identity(worktree: str) -> Tuple[bool, str]:
    """Check 5: V007.80 §0.6 身份检查 SOP"""
    # V007.80: Agent 必知: worktree / HEAD SHA / 最近 3 commit
    # 这里只检查能自动验证的: worktree 存在 + HEAD SHA 长度
    if not os.path.isdir(worktree):
        return False, f'worktree 不存在: {worktree}'

    ok, stdout, _ = run_cmd(['git', '-C', worktree, 'rev-parse', 'HEAD'])
    if not ok:
        return False, f'git rev-parse HEAD failed: {stdout[:200]}'
    head_sha = stdout.strip()
    if len(head_sha) < 7:
        return False, f'HEAD SHA 异常: {head_sha!r}'

    ok, stdout, _ = run_cmd(['git', '-C', worktree, 'log', '--oneline', '-3'])
    if not ok:
        return False, f'git log failed: {stdout[:200]}'
    last3 = stdout.strip().split('\n')

    return True, f'worktree {os.path.basename(worktree)} 存在, HEAD {head_sha[:7]}, 最近 {len(last3)} commits'


def send_lark_alert(cfg_path: str, title: str, content: str) -> bool:
    """Send Lark alert"""
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
        from alert_monitor_v0760 import send_im
        with open(cfg_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        im_type = cfg.get('im', {}).get('default', 'lark_app')
        ok, body = send_im(im_type, cfg, title, content, at_all=True)
        return ok
    except Exception as e:
        print(f'  [WARN] Lark alert failed: {e}', file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description='V007.86h Layer 3 - Check Dev Agent health',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
V007.86h 故事:
  V007.86f 治"调度者"和"自愈" (Dev Agent 自身 + 任务系统自愈)
  V007.86g 实施 P0: Layer 1 (心跳) + Layer 2 (自愈)
  V007.86h 实施 P1: Layer 3 (Agent 健康) + Layer 4 (manifest)

V007.86h 检查项 (5 项, 失败 -> 飞书告警):
  1. git_clean: 无未提交改动 > 30 min
  2. git_synced: 不比 origin 早 > 24h
  3. plan_tasks_healthy: 3 个 yonaa_* 任务都 exit 0/1
  4. manifest_in_sync: infra_manifest.json 里 script 都存在
  5. agent_identity: V007.80 §0.6 身份检查 (worktree / HEAD / 最近 3 commit)
        '''
    )
    parser.add_argument('--manifest', default=DEFAULT_MANIFEST, help='infra_manifest.json path')
    parser.add_argument('--config', default=DEFAULT_CONFIG, help='alert_monitor config (for Lark)')
    parser.add_argument('--no-alert', action='store_true', help='Skip Lark alert')
    parser.add_argument('--quiet', action='store_true', help='Only output issues, skip OK')
    args = parser.parse_args()

    print('=' * 60)
    print('V007.86h Layer 3: Agent Health Check')
    print('=' * 60)
    print()

    # Load manifest
    if not os.path.exists(args.manifest):
        print(f'[FAIL] manifest not found: {args.manifest}')
        sys.exit(2)

    try:
        with open(args.manifest, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
    except Exception as e:
        print(f'[FAIL] manifest read failed: {e}')
        sys.exit(2)

    worktree = manifest.get('worktree', {}).get('root', os.path.dirname(args.manifest))
    print(f'Worktree: {worktree}')
    print()

    checks = [
        ('git_clean', check_git_clean, (worktree,)),
        ('git_synced', check_git_synced, (worktree,)),
        ('plan_tasks_healthy', check_plan_tasks, (manifest,)),
        ('manifest_in_sync', check_manifest_in_sync, (worktree, manifest)),
        ('agent_identity', check_agent_identity, (worktree,)),
    ]

    all_ok = True
    failed_checks = []
    for name, check_fn, check_args in checks:
        try:
            ok, msg = check_fn(*check_args)
        except Exception as e:
            ok, msg = False, f'check exception: {e}'
        if ok:
            if not args.quiet:
                print(f'  [OK] {name}: {msg}')
        else:
            print(f'  [FAIL] {name}: {msg}')
            failed_checks.append((name, msg))
            all_ok = False

    print()
    print('=' * 60)
    if all_ok:
        print('[OK] Agent 健康, 全部检查通过')
        sys.exit(0)
    else:
        print(f'[FAIL] Agent 异常, {len(failed_checks)} 项失败')
        for name, msg in failed_checks:
            print(f'  - {name}: {msg}')

        # Send Lark alert
        if not args.no_alert:
            title = f'[V007.86h] Agent 健康异常 ({len(failed_checks)} 项)'
            content_lines = [
                f'时间: {time.strftime("%Y-%m-%d %H:%M:%S")}',
                f'Worktree: {worktree}',
                f'失败项: {len(failed_checks)}',
                '',
            ]
            for name, msg in failed_checks:
                content_lines.append(f'- {name}: {msg}')
            content = '\n'.join(content_lines)
            print()
            print('--- Sending Lark alert ---')
            if send_lark_alert(args.config, title, content):
                print('  [OK] Lark alert sent')
            else:
                print('  [FAIL] Lark alert failed')

        sys.exit(1)


if __name__ == '__main__':
    main()
