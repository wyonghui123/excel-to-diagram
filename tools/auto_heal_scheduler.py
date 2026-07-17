#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""auto_heal_scheduler.py - 任务自愈 (V007.86g Layer 2)

V007.86f 教训 (Layer 2):
- 计划任务失败, 没人重启
- 13.5 小时 162 次失败 (V007.83 教训)
- V007.86 daemon 临时方案靠人工

V007.86g 解决:
- auto_heal_scheduler.py 5 分钟跑一次
- 检查计划任务 yonaa_alert_monitor 的"上次结果"
- 如果 != 0:
  - 自动 schtasks /Run /TN 强制跑一次
  - 飞书告警"任务自动重启"
  - 写 [HEAL] log
- 如果 3 次都失败:
  - 飞书告警"任务无法自愈, 需人工介入"
  - 自动启动 daemon 备份方案 (V007.86 daemon)
- 限制: 1 小时内最多自愈 6 次 (防无限循环)

V007.86g 跟 V007.86 daemon 区别:
- V007.86 daemon: 监控任务的备份, 跑 --daemon 持续 (跟主任务并行)
- V007.86g auto_heal: 监控任务状态, 不健康时自动重启
- V007.86g 是"诊断 + 治疗", V007.86 daemon 是"备份" (双保险)

退出码:
    0 - 自愈成功 / 一切正常
    1 - 自愈失败 / 状态异常
    2 - 脚本错误
"""
import os
import sys
import time
import json
import argparse
import subprocess
from pathlib import Path
from typing import Optional, Dict, List, Tuple

# ====== 配置 ======
TASK_NAME = r'\yonaa_alert_monitor'
HEAL_LOG = r'D:\filework\worktrees\release-prep\tools\auto_heal.log'
HEAL_STATE = r'D:\filework\worktrees\release-prep\tools\auto_heal_state.json'
ALERT_MONITOR_DAEMON_CMD = [
    'python',
    r'D:\filework\worktrees\release-prep\tools\alert_monitor_v0760.py',
    '--config', r'D:\filework\worktrees\release-prep\tools\alert_monitor_config.json',
    '--daemon',
    '--log-file', r'D:\filework\worktrees\release-prep\tools\alert_monitor_v0760.log',
]
DEFAULT_CONFIG = r'D:\filework\worktrees\release-prep\tools\alert_monitor_config.json'

# 自愈策略
MAX_HEALS_PER_HOUR = 6         # 1 小时最多自愈 6 次 (防无限循环)
COOLDOWN_SEC = 600              # 自愈冷却 10 分钟 (防连续触发)
DAEMON_FALLBACK_AFTER = 3       # 连续 3 次自愈失败 -> 启动 daemon 备份
HEALTHY_EXIT_CODES = {0, 1}     # exit 0 = 全部 OK, exit 1 = 有 fail (但脚本在工作, 不算异常)


def log(msg: str):
    """Write to heal log file with timestamp"""
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}\n'
    try:
        with open(HEAL_LOG, 'a', encoding='utf-8') as f:
            f.write(line)
    except Exception:
        pass
    print(line, end='')


def get_task_status(task_name: str = TASK_NAME) -> Optional[Dict[str, str]]:
    """Get scheduled task status via schtasks /Query

    Returns:
        {'LastResult': '0', 'LastRunTime': '2026/7/17 12:00:00', ...} 或 None
    """
    try:
        result = subprocess.run(
            ['schtasks', '/Query', '/TN', task_name, '/V', '/FO', 'LIST'],
            capture_output=True, text=True, encoding='gbk', errors='replace', timeout=15
        )
    except Exception as e:
        log(f'  [ERROR] schtasks /Query failed: {e}')
        return None

    if result.returncode != 0:
        log(f'  [ERROR] schtasks returncode={result.returncode}: {result.stderr[:200]}')
        return None

    status = {}
    for line in result.stdout.split('\n'):
        line = line.strip()
        if ':' in line:
            key, _, value = line.partition(':')
            status[key.strip()] = value.strip()
    return status


def run_task(task_name: str = TASK_NAME) -> Tuple[bool, str]:
    """Force-run scheduled task via schtasks /Run"""
    try:
        result = subprocess.run(
            ['schtasks', '/Run', '/TN', task_name],
            capture_output=True, text=True, encoding='gbk', errors='replace', timeout=15
        )
    except Exception as e:
        return False, f'schtasks /Run exception: {e}'
    if result.returncode == 0:
        return True, 'OK'
    return False, f'schtasks /Run returncode={result.returncode}: {result.stderr[:200]}'


def start_daemon_fallback() -> bool:
    """Start alert_monitor --daemon as fallback (V007.86 daemon)"""
    try:
        result = subprocess.run(
            ALERT_MONITOR_DAEMON_CMD,
            capture_output=True, text=True, timeout=10
        )
        # daemon forks, returncode 0 means start OK
        return result.returncode == 0
    except Exception as e:
        log(f'  [ERROR] daemon start failed: {e}')
        return False


def load_heal_state() -> Dict:
    """Load heal state (heal history, cooldown)"""
    if not os.path.exists(HEAL_STATE):
        return {
            'heal_history': [],  # list of {ts, result: 'OK'|'FAIL', exit_code}
            'consecutive_fails': 0,
            'daemon_started_ts': 0,
        }
    try:
        with open(HEAL_STATE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log(f'  [WARN] state read failed: {e}, using empty')
        return {
            'heal_history': [],
            'consecutive_fails': 0,
            'daemon_started_ts': 0,
        }


def save_heal_state(state: Dict):
    """Save heal state"""
    try:
        with open(HEAL_STATE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        log(f'  [ERROR] state save failed: {e}')


def cleanup_old_heals(state: Dict, now: float) -> Dict:
    """Remove heal history older than 1 hour"""
    cutoff = now - 3600
    state['heal_history'] = [
        h for h in state['heal_history']
        if h.get('ts', 0) > cutoff
    ]
    return state


def is_in_cooldown(state: Dict, now: float) -> bool:
    """Check if last heal was within COOLDOWN_SEC"""
    history = state.get('heal_history', [])
    if not history:
        return False
    last = history[-1]
    return (now - last.get('ts', 0)) < COOLDOWN_SEC


def send_lark_alert(cfg_path: str, title: str, content: str) -> bool:
    """Send Lark alert (reuses alert_monitor send_im)"""
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
        log(f'  [WARN] Lark alert failed: {e}')
        return False


def main():
    parser = argparse.ArgumentParser(
        description='V007.86g Layer 2 - Auto-heal scheduled tasks',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
V007.86g Layer 2 自愈逻辑:
  1. 查 schtasks /Query /TN yonaa_alert_monitor /V /FO LIST
  2. 看 "上次结果" 字段
  3. 如果是 HEALTHY_EXIT_CODES (0 或 1) -> 一切正常, exit 0
  4. 如果不在 -> 自愈流程:
     a. 冷却检查: 距离上次自愈 < 10 min -> 跳过 (防抖)
     b. 频率检查: 1 小时内自愈 >= 6 次 -> 不自愈, 发飞书告警
     c. schtasks /Run 强制跑一次
     d. 等 30 秒, 再查上次结果
     e. 仍失败 -> 连续失败计数 +1
     f. 连续 3 次失败 -> 启动 daemon 备份, 飞书告警"任务无法自愈"
  5. 写 heal log + state (for next run)
        '''
    )
    parser.add_argument('--config', default=DEFAULT_CONFIG, help='alert_monitor config (for Lark)')
    parser.add_argument('--dry-run', action='store_true', help="Show what would do, don't actually heal")
    parser.add_argument('--no-alert', action='store_true', help='Skip Lark alert')
    args = parser.parse_args()

    print('=' * 60)
    print('V007.86g Layer 2: Auto-heal Scheduler')
    print('=' * 60)
    print()

    now = time.time()
    state = load_heal_state()
    state = cleanup_old_heals(state, now)

    # 1. Get task status
    print('--- Step 1: Get task status ---')
    status = get_task_status()
    if not status:
        log('[ERROR] failed to get task status, aborting')
        sys.exit(2)

    last_result = status.get('Last Result', status.get('LastResult', status.get('上次结果', ''))).strip()
    last_run_time = status.get('Last Run Time', status.get('LastRunTime', status.get('上次运行时间', ''))).strip()
    next_run_time = status.get('Next Run Time', status.get('NextRunTime', status.get('下次运行时间', ''))).strip()

    log(f'  Task: {TASK_NAME}')
    log(f'  Last Result: {last_result!r}')
    log(f'  Last Run: {last_run_time!r}')
    log(f'  Next Run: {next_run_time!r}')

    # 2. Check if healthy
    print()
    print('--- Step 2: Check health ---')
    try:
        exit_code = int(last_result, 16) if last_result else -1
    except ValueError:
        try:
            exit_code = int(last_result)
        except ValueError:
            exit_code = -1

    if exit_code in HEALTHY_EXIT_CODES:
        log(f'  [OK] Task healthy (exit {exit_code})')
        state['consecutive_fails'] = 0
        save_heal_state(state)
        sys.exit(0)

    log(f'  [FAIL] Task unhealthy (exit {exit_code})')

    # 3. Cooldown check
    if is_in_cooldown(state, now):
        log(f'  [SKIP] In cooldown (last heal < {COOLDOWN_SEC}s ago)')
        sys.exit(0)

    # 4. Frequency check
    history = state.get('heal_history', [])
    if len(history) >= MAX_HEALS_PER_HOUR:
        log(f'  [WARN] Too many heals ({len(history)} in last hour >= {MAX_HEALS_PER_HOUR})')
        if not args.no_alert:
            send_lark_alert(
                args.config,
                f'[V007.86g] 自愈频率过高 ({len(history)}/h)',
                f'任务 {TASK_NAME} 持续失败\n1 小时内自愈 {len(history)} 次\n需人工介入'
            )
        sys.exit(1)

    # 5. Heal
    if args.dry_run:
        log(f'  [DRY-RUN] Would run schtasks /Run /TN {TASK_NAME}')
        sys.exit(0)

    print()
    print('--- Step 3: Self-heal ---')
    log(f'  Running: schtasks /Run /TN {TASK_NAME}')
    ok, msg = run_task()
    if ok:
        log(f'  [OK] Task started')
    else:
        log(f'  [FAIL] {msg}')

    # 6. Wait + verify
    log(f'  Waiting 30s for task to complete...')
    time.sleep(30)

    status2 = get_task_status()
    if status2:
        last_result2 = status2.get('上次结果', status2.get('LastResult', '')).strip()
        try:
            exit_code2 = int(last_result2, 16)
        except ValueError:
            try:
                exit_code2 = int(last_result2)
            except ValueError:
                exit_code2 = -1

        if exit_code2 in HEALTHY_EXIT_CODES:
            log(f'  [OK] Heal success: exit {exit_code2}')
            state['consecutive_fails'] = 0
            state['heal_history'].append({'ts': now, 'result': 'OK', 'exit_before': exit_code, 'exit_after': exit_code2})
            save_heal_state(state)

            if not args.no_alert:
                send_lark_alert(
                    args.config,
                    f'[V007.86g] 自愈成功 (exit {exit_code} -> {exit_code2})',
                    f'任务 {TASK_NAME} 失败 {exit_code}, 自愈后 {exit_code2}'
                )
            sys.exit(0)

    # 7. Heal failed
    log(f'  [FAIL] Heal did not fix task')
    state['consecutive_fails'] = state.get('consecutive_fails', 0) + 1
    state['heal_history'].append({'ts': now, 'result': 'FAIL', 'exit_before': exit_code})
    save_heal_state(state)

    # 8. Daemon fallback after 3 consecutive fails
    if state['consecutive_fails'] >= DAEMON_FALLBACK_AFTER:
        log(f'  [WARN] {state["consecutive_fails"]} consecutive fails, starting daemon fallback')
        if start_daemon_fallback():
            log(f'  [OK] Daemon started')
            state['daemon_started_ts'] = now
            save_heal_state(state)
        if not args.no_alert:
            send_lark_alert(
                args.config,
                f'[V007.86g] 任务无法自愈, 启动 daemon 备份',
                f'任务 {TASK_NAME} 连续 {state["consecutive_fails"]} 次自愈失败\n'
                f'daemon 备份已启动, 需人工介入\n'
                f'heal log: {HEAL_LOG}'
            )

    if not args.no_alert:
        send_lark_alert(
            args.config,
            f'[V007.86g] 自愈失败 (连续 {state["consecutive_fails"]} 次)',
            f'任务 {TASK_NAME} 失败 exit {exit_code}\n'
            f'schtasks /Run 已触发, 30s 后仍失败\n'
            f'consecutive fails: {state["consecutive_fails"]}'
        )

    sys.exit(1)


if __name__ == '__main__':
    main()
