#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
沙箱状态检测脚本 (V2 新增)

基于 2026-06-20 沙箱 terminal 死锁 2.5 小时事故，提供 3 重检测：
1. Write + Read 反向验证（最可靠）
2. RunCommand 退出码 + stdout
3. sbox_sdk 日志监控

返回状态：
- healthy: 正常（exit 0 + stdout 正常）
- isolated: 隔离（exit 7 / stdout 空 / 文件不创建）
- deadlock: 死锁（ptyHost heartbeat 丢失）
- unknown: 未知（无法检测）
"""

import os
import sys
import subprocess
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Literal

SandboxStatus = Literal['healthy', 'isolated', 'deadlock', 'unknown']


def check_sandbox_write_read(test_dir: str = 'd:/filework') -> SandboxStatus:
    """
    检测 1: Write + Read 反向验证（最可靠）

    写测试文件 → 立刻读取 → 如果内容不一致 → 沙箱隔离
    """
    test_file = Path(test_dir) / f'.sandbox_check_{os.getpid()}_{int(datetime.now().timestamp())}.txt'
    test_content = f'sandbox-test-{datetime.now().isoformat()}'

    try:
        # 写测试文件
        test_file.write_text(test_content, encoding='utf-8')
    except Exception as e:
        print(f'[DETECT-1] [WARN] 写入失败: {e}')
        return 'isolated'

    # 反向读取验证
    if not test_file.exists():
        print(f'[DETECT-1] [FAIL] 写入后文件不存在 → 沙箱隔离')
        return 'isolated'

    try:
        actual_content = test_file.read_text(encoding='utf-8')
    except Exception as e:
        print(f'[DETECT-1] [WARN] 读取失败: {e}')
        return 'isolated'

    # 清理
    try:
        test_file.unlink()
    except Exception:
        pass

    if actual_content != test_content:
        print(f'[DETECT-1] [FAIL] 内容不一致 → 沙箱隔离')
        return 'isolated'

    return 'healthy'


def check_sandbox_runcommand() -> SandboxStatus:
    """
    检测 2: RunCommand 退出码 + stdout

    执行 echo test，如果 stdout 为空但 exit_code=0 → 假成功 → 隔离
    """
    try:
        result = subprocess.run(
            ['powershell.exe', '-NoProfile', '-Command', 'echo test'],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        print(f'[DETECT-2] [FAIL] 命令超时 → 沙箱隔离/死锁')
        return 'isolated'
    except Exception as e:
        print(f'[DETECT-2] [WARN] 命令执行失败: {e}')
        return 'isolated'

    # 退出码 7 = trae-sandbox 拦截
    if result.returncode == 7:
        print(f'[DETECT-2] [FAIL] exit code 7 → 沙箱隔离')
        return 'isolated'

    # exit 0 但 stdout 空 = 假成功
    if result.returncode == 0 and not result.stdout.strip():
        print(f'[DETECT-2] [FAIL] exit 0 但 stdout 空 → 沙箱隔离')
        return 'isolated'

    if result.returncode == 0 and 'test' in result.stdout:
        return 'healthy'

    return 'unknown'


def check_sandbox_logs(log_root: str = r'C:\Users\Administrator\AppData\Roaming\Trae CN\logs') -> SandboxStatus:
    """
    检测 3: sbox_sdk 日志监控

    读取最新的 sbox_sdk log，检查 exit code
    """
    log_path = Path(log_root)
    if not log_path.exists():
        print(f'[DETECT-3] [WARN] 日志目录不存在: {log_root}')
        return 'unknown'

    # 找最新的日期目录（按目录名解析为时间戳排序）
    def get_dir_timestamp(d: Path) -> str:
        """从目录名提取时间戳，格式: 20260620T202327"""
        match = re.match(r'(\d{8}T\d{6})', d.name)
        return match.group(1) if match else ''

    date_dirs = sorted(
        [d for d in log_path.iterdir() if d.is_dir()],
        key=get_dir_timestamp,
        reverse=True,
    )
    if not date_dirs:
        print(f'[DETECT-3] [WARN] 没有日期目录')
        return 'unknown'

    latest_date_dir = date_dirs[0]
    modular_dir = latest_date_dir / 'Modular'
    if not modular_dir.exists():
        return 'unknown'

    # 找最近的 sbox_sdk 日志
    sbox_logs = sorted(modular_dir.glob('sbox_sdk_*.log'), reverse=True)
    if not sbox_logs:
        return 'unknown'

    # 检查最近 5 条
    recent_logs = sbox_logs[:5]
    isolated_count = 0
    healthy_count = 0

    for log_file in recent_logs:
        try:
            content = log_file.read_text(encoding='utf-8', errors='ignore')
            # 检查 exit code
            if 'exit code 7' in content:
                isolated_count += 1
            elif 'exit code 0' in content:
                healthy_count += 1
        except Exception:
            continue

    # 检测 deadlock（ptyHost heartbeat 丢失）
    main_log = latest_date_dir / 'main.log'
    if main_log.exists():
        try:
            main_content = main_log.read_text(encoding='utf-8', errors='ignore')
            if 'No ptyHost heartbeat after' in main_content:
                # 检查是否在最近 10 分钟
                lines = main_content.splitlines()
                for line in reversed(lines[-50:]):
                    if 'No ptyHost heartbeat' in line:
                        # 提取时间戳
                        match = re.match(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', line)
                        if match:
                            ts = datetime.fromisoformat(match.group(1))
                            age_minutes = (datetime.now() - ts).total_seconds() / 60
                            if age_minutes < 10:
                                print(f'[DETECT-3] [FAIL] ptyHost heartbeat 丢失 {age_minutes:.1f} 分钟前 → 沙箱死锁')
                                return 'deadlock'
                        break
        except Exception:
            pass

    # 多数判定
    if isolated_count > healthy_count:
        print(f'[DETECT-3] [FAIL] 最近 5 条日志中 {isolated_count} 条 exit 7 → 沙箱隔离')
        return 'isolated'

    if healthy_count > 0:
        return 'healthy'

    return 'unknown'


def check_sandbox(
    test_dir: str = 'd:/filework',
    log_root: str = r'C:\Users\Administrator\AppData\Roaming\Trae CN\logs',
) -> dict:
    """
    综合检测：3 重验证 + 取最严格的判定

    返回：
    {
        'status': 'healthy' | 'isolated' | 'deadlock' | 'unknown',
        'details': {
            'write_read': SandboxStatus,
            'runcommand': SandboxStatus,
            'logs': SandboxStatus,
        },
        'recommendation': str,
    }
    """
    results = {
        'write_read': check_sandbox_write_read(test_dir),
        'runcommand': check_sandbox_runcommand(),
        'logs': check_sandbox_logs(log_root),
    }

    # 取最严格的判定（deadlock > isolated > unknown > healthy）
    if 'deadlock' in results.values():
        final_status = 'deadlock'
        recommendation = '沙箱死锁，必须重启 Trae IDE'
    elif 'isolated' in results.values():
        final_status = 'isolated'
        recommendation = '沙箱隔离，切 Read-First 工作流（禁用 RunCommand / Glob / LS）'
    elif all(v == 'healthy' for v in results.values()):
        final_status = 'healthy'
        recommendation = '沙箱正常，全部工具可用'
    else:
        final_status = 'unknown'
        recommendation = '沙箱状态未知，建议手动验证后再继续'

    return {
        'status': final_status,
        'details': results,
        'recommendation': recommendation,
        'timestamp': datetime.now().isoformat(),
    }


def main():
    """CLI 入口"""
    result = check_sandbox()

    print('=' * 60)
    print('沙箱状态检测 (V2 新增)')
    print('=' * 60)
    print(f'  write_read: {result["details"]["write_read"]}')
    print(f'  runcommand: {result["details"]["runcommand"]}')
    print(f'  logs:       {result["details"]["logs"]}')
    print()
    print(f'最终状态: {result["status"].upper()}')
    print(f'建议: {result["recommendation"]}')
    print('=' * 60)

    # 同时输出 JSON（便于其他脚本调用）
    if '--json' in sys.argv:
        print()
        print(json.dumps(result, indent=2, ensure_ascii=False))

    # 设置退出码（CI/CD 用）
    if result['status'] == 'healthy':
        sys.exit(0)
    elif result['status'] == 'isolated':
        sys.exit(2)
    elif result['status'] == 'deadlock':
        sys.exit(3)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()