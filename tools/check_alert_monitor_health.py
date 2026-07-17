#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_alert_monitor_health.py - 检查 alert_monitor 自身健康 (V007.86g Layer 1)

V007.86f 教训 (Layer 1):
- alert_monitor_v0760.py 监控远程服务, 但不监控自己
- 任务跑成功 = 任务跑成功 != "监控在工作"
- silent failure: 永远返回 OK 但实际没监控

V007.86g 解决:
- alert_monitor_v0760.py 每次跑在 log 写一行 [HEARTBEAT-V00786F]
- check_alert_monitor_health.py 5 分钟跑一次, 检查 log 有这个标记
- 异常 -> 飞书告警"监控自身异常"

检查项:
1. log 文件最近 5 min 有新行 (监控在跑)
2. log 最新行有 [HEARTBEAT-V00786F] 标记 (V007.86f 加)
3. log 没有异常模式 (e.g. "Traceback", "ERROR")
4. log 长度在合理范围 (太长 = 重复, 太短 = 跳步)
5. alert_monitor_config_state.json last_run_ts < 10 min

退出码:
    0 - 健康
    1 - 异常 (发飞书告警)
    2 - 脚本错误
"""
import os
import sys
import time
import json
import argparse
from pathlib import Path
from typing import List, Dict, Optional, Tuple


# ====== 配置 ======
DEFAULT_LOG = r'D:\filework\worktrees\release-prep\tools\alert_monitor_v0760.log'
DEFAULT_STATE = r'D:\filework\worktrees\release-prep\tools\alert_monitor_config_state.json'
DEFAULT_CONFIG = r'D:\filework\worktrees\release-prep\tools\alert_monitor_config.json'

# 健康阈值
LOG_STALE_SEC = 600          # log 超过 10 min 没新行 = 异常
HEARTBEAT_STALE_SEC = 600    # 心跳标记超过 10 min 没出现 = 异常
STATE_STALE_SEC = 900        # state last_run 超过 15 min = 异常
LOG_SIZE_MIN = 200           # log 太小 (< 200 bytes) = 异常
LOG_SIZE_MAX = 10_000_000    # log 太大 (> 10 MB) = 异常

# 异常模式
ERROR_PATTERNS = [
    'Traceback (most recent call last):',
    'ERROR:',
    'CRITICAL:',
    'FATAL:',
    'JSONDecodeError',
    'ConnectionRefusedError',
]


def read_log_tail(log_path: str, max_bytes: int = 50000) -> str:
    """Read last N bytes of log file"""
    if not os.path.exists(log_path):
        return ''
    size = os.path.getsize(log_path)
    if size == 0:
        return ''
    with open(log_path, 'rb') as f:
        if size > max_bytes:
            f.seek(size - max_bytes)
        data = f.read()
    return data.decode('utf-8', errors='replace')


def parse_log_timestamp(line: str) -> Optional[float]:
    """Parse timestamp from log line: [2026-07-17 12:00:01] ..."""
    import re
    m = re.match(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]', line)
    if not m:
        return None
    try:
        from datetime import datetime
        dt = datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S')
        return dt.timestamp()
    except Exception:
        return None


def check_log_exists(log_path: str) -> Tuple[bool, str]:
    """Check 1: log file exists and is non-empty"""
    if not os.path.exists(log_path):
        return False, f'log 文件不存在: {log_path}'
    size = os.path.getsize(log_path)
    if size < LOG_SIZE_MIN:
        return False, f'log 文件太小: {size} bytes (< {LOG_SIZE_MIN})'
    if size > LOG_SIZE_MAX:
        return False, f'log 文件太大: {size} bytes (> {LOG_SIZE_MAX})'
    return True, f'log 大小: {size} bytes'


def check_log_recent(log_path: str, now: float) -> Tuple[bool, str]:
    """Check 2: log has recent timestamp (within LOG_STALE_SEC)"""
    tail = read_log_tail(log_path, max_bytes=10000)
    if not tail:
        return False, 'log 文件为空'
    lines = [l for l in tail.split('\n') if l.strip()]
    if not lines:
        return False, 'log 无有效行'
    last_line = lines[-1]
    ts = parse_log_timestamp(last_line)
    if ts is None:
        return False, f'最后一行无时间戳: {last_line[:80]!r}'
    age = int(now - ts)
    if age > LOG_STALE_SEC:
        return False, f'log 滞后: 最后一行 {age}s 前 (> {LOG_STALE_SEC}s)'
    return True, f'log 最新: {age}s 前'


def check_heartbeat_present(log_path: str, now: float) -> Tuple[bool, str]:
    """Check 3: [HEARTBEAT-V00786F] line within HEARTBEAT_STALE_SEC"""
    tail = read_log_tail(log_path, max_bytes=100000)
    if not tail:
        return False, 'log 为空'
    # Find last HEARTBEAT-V00786F line
    last_heartbeat_ts = None
    last_heartbeat_line = None
    for line in tail.split('\n'):
        if '[HEARTBEAT-V00786F]' in line:
            ts = parse_log_timestamp(line)
            if ts:
                last_heartbeat_ts = ts
                last_heartbeat_line = line
    if last_heartbeat_ts is None:
        return False, 'log 中无 [HEARTBEAT-V00786F] 标记 (V007.86g 必须有)'
    age = int(now - last_heartbeat_ts)
    if age > HEARTBEAT_STALE_SEC:
        return False, f'HEARTBEAT 滞后: {age}s 前 (> {HEARTBEAT_STALE_SEC}s)'
    return True, f'HEARTBEAT 最新: {age}s 前'


def check_no_error_patterns(log_path: str) -> Tuple[bool, str]:
    """Check 4: log 没有异常模式"""
    tail = read_log_tail(log_path, max_bytes=100000)
    for pattern in ERROR_PATTERNS:
        if pattern in tail:
            return False, f'log 含异常模式: {pattern!r}'
    return True, 'log 无异常模式'


def check_state_recent(state_path: str, now: float) -> Tuple[bool, str]:
    """Check 5: state 文件 check_last_run 最新项在 STATE_STALE_SEC 内"""
    if not os.path.exists(state_path):
        return False, f'state 文件不存在: {state_path}'
    try:
        with open(state_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return False, f'state 文件读失败: {e}'
    # alert_monitor_v0760 uses check_last_run (per-check dict) + last_heartbeat_ts
    # Use last_heartbeat_ts as the most recent run indicator
    last_run = data.get('last_heartbeat_ts', 0)
    if last_run == 0:
        # Fallback: check check_last_run max
        check_last_run = data.get('check_last_run', {})
        if check_last_run:
            last_run = max(check_last_run.values())
    if last_run == 0:
        return False, 'state 无 last_run (last_heartbeat_ts / check_last_run 都空)'
    age = int(now - last_run)
    if age > STATE_STALE_SEC:
        return False, f'state 滞后: last_run {age}s 前 (> {STATE_STALE_SEC}s)'
    return True, f'state 最新: {age}s 前'


def send_lark_alert(cfg_path: str, title: str, content: str) -> bool:
    """Send alert to Lark (reuses alert_monitor's send_im)"""
    try:
        # Add script's parent to path for import
        script_dir = os.path.dirname(os.path.abspath(__file__))
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
        from alert_monitor_v0760 import send_im
        import json
        with open(cfg_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        im_type = cfg.get('im', {}).get('default', 'lark_app')
        ok, body = send_im(im_type, cfg, title, content, at_all=True)
        return ok
    except Exception as e:
        print(f'  [WARN] Failed to send Lark alert: {e}', file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description='V007.86g Layer 1 - Check alert_monitor health (heartbeat)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
V007.86g 故事:
  V007.86f 治"调度者"和"自愈" (Dev Agent 自身 + 任务系统自愈)
  V007.86g 实施 P0:
    - Layer 1: check_alert_monitor_health.py (心跳, 5 min 一次)
    - Layer 2: auto_heal_scheduler.py (任务自愈, 5 min 一次)
  V007.86g 加 2 个计划任务 (心跳 + 自愈), NO cmd 弹窗 (V007.86e)

V007.86g 检查项 (5 项, 失败 -> 飞书告警):
  1. log 文件存在 + 大小合理 (200B - 10MB)
  2. log 最新 10 min 有新行
  3. [HEARTBEAT-V00786F] 标记最新 10 min
  4. log 无异常模式 (Traceback / ERROR / FATAL)
  5. state.last_run_ts 最新 15 min
        '''
    )
    parser.add_argument('--log', default=DEFAULT_LOG, help='alert_monitor log file path')
    parser.add_argument('--state', default=DEFAULT_STATE, help='alert_monitor state file path')
    parser.add_argument('--config', default=DEFAULT_CONFIG, help='alert_monitor config file path')
    parser.add_argument('--no-alert', action='store_true', help='Skip Lark alert (for testing)')
    parser.add_argument('--quiet', action='store_true', help='Only output issues, skip OK')
    args = parser.parse_args()

    print('=' * 60)
    print('V007.86g Layer 1: alert_monitor_health Check')
    print('=' * 60)
    print()

    now = time.time()

    checks = [
        ('log_exists', check_log_exists, (args.log,)),
        ('log_recent', check_log_recent, (args.log, now)),
        ('heartbeat_present', check_heartbeat_present, (args.log, now)),
        ('no_error_patterns', check_no_error_patterns, (args.log,)),
        ('state_recent', check_state_recent, (args.state, now)),
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
        print('[OK] alert_monitor 健康, 全部检查通过')
        sys.exit(0)
    else:
        print(f'[FAIL] alert_monitor 异常, {len(failed_checks)} 项失败')
        for name, msg in failed_checks:
            print(f'  - {name}: {msg}')

        # Send Lark alert
        if not args.no_alert:
            title = f'[V007.86g] alert_monitor 异常 ({len(failed_checks)} 项)'
            content_lines = [
                f'时间: {time.strftime("%Y-%m-%d %H:%M:%S")}',
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
