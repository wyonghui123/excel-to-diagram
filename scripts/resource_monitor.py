# -*- coding: utf-8 -*-
"""
资源监控器 - 检查系统资源是否足够启动 Agent

功能：
1. CPU 使用率
2. 内存可用量
3. 磁盘空间
4. 端口占用
5. 智能体健康状态
"""

import psutil
import json
import time
import argparse
from pathlib import Path
from datetime import datetime

STATE_FILE = Path(r"d:\filework\.agent_registry\state.json")
THRESHOLDS = {
    'cpu_max_percent': 80,          # 超过 80% 不启动新测试
    'memory_max_percent': 85,        # 超过 85% 不启动
    'memory_min_free_gb': 2,         # 至少 2GB 空闲
    'disk_min_free_gb': 5,           # 至少 5GB 空闲
    'max_concurrent_agents': 5,      # 最多 5 个 Agent
}


def get_resources():
    """获取当前资源状态"""
    cpu = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('d:\\')

    return {
        'cpu_percent': cpu,
        'memory_percent': memory.percent,
        'memory_available_gb': memory.available / (1024**3),
        'memory_used_gb': memory.used / (1024**3),
        'memory_total_gb': memory.total / (1024**3),
        'disk_free_gb': disk.free / (1024**3),
        'disk_percent': disk.percent,
        'timestamp': datetime.now().isoformat()
    }


def can_start_new_agent():
    """检查是否可以启动新 Agent"""
    res = get_resources()
    issues = []

    if res['cpu_percent'] > THRESHOLDS['cpu_max_percent']:
        issues.append(f"CPU 占用 {res['cpu_percent']}% > {THRESHOLDS['cpu_max_percent']}%")

    if res['memory_percent'] > THRESHOLDS['memory_max_percent']:
        issues.append(f"内存占用 {res['memory_percent']}% > {THRESHOLDS['memory_max_percent']}%")

    if res['memory_available_gb'] < THRESHOLDS['memory_min_free_gb']:
        issues.append(f"可用内存 {res['memory_available_gb']:.1f}GB < {THRESHOLDS['memory_min_free_gb']}GB")

    if res['disk_free_gb'] < THRESHOLDS['disk_min_free_gb']:
        issues.append(f"磁盘空闲 {res['disk_free_gb']:.1f}GB < {THRESHOLDS['disk_min_free_gb']}GB")

    # 检查活跃 Agent 数量
    active_agents = count_active_agents()
    if active_agents >= THRESHOLDS['max_concurrent_agents']:
        issues.append(f"活跃 Agent 数 {active_agents} >= {THRESHOLDS['max_concurrent_agents']}")

    return len(issues) == 0, issues, res


def count_active_agents():
    """统计活跃 Agent 数量"""
    if not STATE_FILE.exists():
        return 0

    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)
        return len(state.get('agents', {}))
    except (json.JSONDecodeError, IOError):
        return 0


def print_status():
    """打印资源状态"""
    res = get_resources()
    can_start, issues, _ = can_start_new_agent()

    print("\n=== 系统资源状态 ===\n")
    print(f"  CPU:        {res['cpu_percent']:5.1f}%")
    print(f"  内存:       {res['memory_percent']:5.1f}% ({res['memory_used_gb']:.1f}/{res['memory_total_gb']:.1f} GB)")
    print(f"  内存空闲:   {res['memory_available_gb']:.1f} GB")
    print(f"  磁盘空闲:   {res['disk_free_gb']:.1f} GB")
    print(f"  活跃 Agent: {count_active_agents()}")

    print()
    if can_start:
        print("  [OK] 可以启动新 Agent")
    else:
        print("  [BLOCKED] 不能启动新 Agent：")
        for issue in issues:
            print(f"    - {issue}")


def wait_until_available(timeout=300, check_interval=10):
    """等待直到资源可用"""
    start = time.time()
    while time.time() - start < timeout:
        can_start, _, _ = can_start_new_agent()
        if can_start:
            return True
        print(f"[WAIT] 资源不足，{check_interval}秒后重试...")
        time.sleep(check_interval)
    return False


def main():
    parser = argparse.ArgumentParser(
        description='资源监控器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python resource_monitor.py status
    python resource_monitor.py check
    python resource_monitor.py wait
        """
    )
    subparsers = parser.add_subparsers(dest='command', help='子命令')

    subparsers.add_parser('status', help='显示资源状态')
    subparsers.add_parser('check', help='检查是否可以启动新 Agent')
    wait_parser = subparsers.add_parser('wait', help='等待资源可用')
    wait_parser.add_argument('--timeout', type=int, default=300, help='超时时间（秒）')

    args = parser.parse_args()

    if args.command == 'status':
        print_status()
    elif args.command == 'check':
        can_start, issues, res = can_start_new_agent()
        if can_start:
            print("[OK] 资源充足，可以启动新 Agent")
            sys.exit(0)
        else:
            print("[BLOCKED] 资源不足：")
            for issue in issues:
                print(f"  - {issue}")
            sys.exit(1)
    elif args.command == 'wait':
        if wait_until_available(args.timeout):
            print("[OK] 资源已可用")
            sys.exit(0)
        else:
            print(f"[TIMEOUT] 等待 {args.timeout} 秒后仍不可用")
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    import sys
    main()
