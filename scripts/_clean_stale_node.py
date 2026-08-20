#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""清理僵尸 node.exe 进程

保护规则:
  - 占用已知活跃端口 (3006, 3007) 的 vite 保留
  - 内存 > 150MB 的活跃 vite 保留
  - 其余全部杀掉
"""
import subprocess
import sys

PROTECTED_PORTS = {3006, 3007}
MEM_THRESHOLD_MB = 150


def get_node_processes():
    """获取所有 node.exe 进程的 PID 和内存"""
    r = subprocess.run(
        ['tasklist', '/FI', 'IMAGENAME eq node.exe', '/FO', 'CSV'],
        capture_output=True, text=True, timeout=10
    )
    procs = []
    for line in r.stdout.split('\n'):
        if 'node.exe' not in line:
            continue
        parts = line.strip().split('","')
        if len(parts) >= 5:
            pid = int(parts[1].strip('"'))
            mem_str = parts[4].strip('"').replace(',', '').replace(' K', '').strip()
            try:
                mem_kb = int(mem_str)
            except ValueError:
                mem_kb = 0
            procs.append((pid, mem_kb))
    return procs


def get_ports_for_pid(pid):
    """获取进程监听的端口"""
    r = subprocess.run(
        ['netstat', '-ano'],
        capture_output=True, text=True, timeout=10
    )
    ports = set()
    for line in r.stdout.split('\n'):
        if f' {pid}' in line and 'LISTEN' in line:
            # 格式: TCP  0.0.0.0:3005  0.0.0.0:0  LISTENING  12345
            parts = line.strip().split()
            if len(parts) >= 2 and ':' in parts[1]:
                try:
                    port = int(parts[1].split(':')[-1])
                    ports.add(port)
                except ValueError:
                    pass
    return ports


def main():
    dry_run = '--apply' not in sys.argv
    procs = get_node_processes()
    print(f"Total node.exe processes: {len(procs)}")

    kill_pids = []
    protect_pids = []

    for pid, mem_kb in procs:
        mem_mb = mem_kb / 1024

        # 保护: 大内存活跃 vite
        if mem_mb > MEM_THRESHOLD_MB:
            protect_pids.append((pid, mem_mb, 'large memory'))
            continue

        # 保护: 占用已知端口
        ports = get_ports_for_pid(pid)
        if ports & PROTECTED_PORTS:
            protect_pids.append((pid, mem_mb, f'port {ports & PROTECTED_PORTS}'))
            continue

        kill_pids.append((pid, mem_mb))

    print(f"\nProtected ({len(protect_pids)}):")
    for pid, mem, reason in protect_pids:
        print(f"  PID={pid}  mem={mem:.0f}MB  reason={reason}")

    print(f"\nTo kill ({len(kill_pids)}):")
    for pid, mem in kill_pids:
        print(f"  PID={pid}  mem={mem:.0f}MB")

    if dry_run:
        print(f"\n[DRY-RUN] Use --apply to actually kill {len(kill_pids)} processes")
        return

    killed = 0
    for pid, mem in kill_pids:
        try:
            subprocess.run(['taskkill', '/F', '/PID', str(pid)],
                         capture_output=True, timeout=5)
            killed += 1
        except Exception:
            pass

    print(f"\nKilled {killed}/{len(kill_pids)} orphan node.exe processes")

    # 验证
    remaining = get_node_processes()
    print(f"Remaining node.exe: {len(remaining)}")


if __name__ == '__main__':
    main()
