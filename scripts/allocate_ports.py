# -*- coding: utf-8 -*-
"""
端口分配器 - 多 Agent 端口管理

功能：
1. 分配新端口给新 Agent
2. 检测端口冲突
3. 注册表管理
"""

import json
import socket
import argparse
import sys
from pathlib import Path
from datetime import datetime

REGISTRY_DIR = Path(r"d:\filework\.agent_registry")
REGISTRY_FILE = REGISTRY_DIR / "ports.json"

FRONTEND_START = 3004
BACKEND_START = 3010
PORT_STEP = 10


def ensure_registry():
    """确保注册表存在"""
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    if not REGISTRY_FILE.exists():
        with open(REGISTRY_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "agents": {},
                "next_available": {
                    "frontend": FRONTEND_START,
                    "backend": BACKEND_START
                }
            }, f, indent=2)


def load_registry():
    """加载注册表"""
    ensure_registry()
    with open(REGISTRY_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_registry(registry):
    """保存注册表"""
    with open(REGISTRY_FILE, 'w', encoding='utf-8') as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)


def is_port_free(port):
    """检查端口是否空闲"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('localhost', port))
            return True
    except OSError:
        return False


def find_free_port(start, step=10, max_attempts=100):
    """找下一个空闲端口"""
    port = start
    for _ in range(max_attempts):
        if is_port_free(port):
            return port
        port += step
    raise RuntimeError(f"在 {start} 起始的 {max_attempts} 个端口中未找到空闲端口")


def allocate_ports(agent_id, worktree_path=None):
    """
    为 Agent 分配新端口

    Args:
        agent_id: Agent 标识（如 "agent_C"）
        worktree_path: worktree 路径

    Returns:
        dict: {frontend, backend, worktree}
    """
    registry = load_registry()

    # 检查 Agent 是否已分配
    if agent_id in registry['agents']:
        existing = registry['agents'][agent_id]
        print(f"[!] Agent {agent_id} 已分配端口：")
        print(f"    Frontend: {existing['frontend']}")
        print(f"    Backend:  {existing['backend']}")
        return existing

    # 找空闲端口
    frontend = find_free_port(registry['next_available']['frontend'])
    backend = find_free_port(registry['next_available']['backend'])

    # 记录
    worktree = worktree_path or f"d:\\worktrees\\{agent_id}"
    registry['agents'][agent_id] = {
        "frontend": frontend,
        "backend": backend,
        "worktree": worktree,
        "allocated_at": datetime.now().isoformat()
    }
    registry['next_available']['frontend'] = frontend + PORT_STEP
    registry['next_available']['backend'] = backend + PORT_STEP

    save_registry(registry)

    print(f"[OK] Agent {agent_id} 分配端口成功：")
    print(f"    Frontend: {frontend}")
    print(f"    Backend:  {backend}")
    print(f"    Worktree: {worktree}")

    return registry['agents'][agent_id]


def release_ports(agent_id):
    """释放 Agent 的端口"""
    registry = load_registry()

    if agent_id not in registry['agents']:
        print(f"[!] Agent {agent_id} 未分配端口")
        return False

    del registry['agents'][agent_id]
    save_registry(registry)

    print(f"[OK] Agent {agent_id} 端口已释放")
    return True


def list_agents():
    """列出所有 Agent 的端口分配"""
    registry = load_registry()

    if not registry['agents']:
        print("暂无 Agent 分配")
        return

    print("\n=== Agent 端口分配表 ===\n")
    print(f"{'Agent':<15} {'Frontend':<10} {'Backend':<10} {'Worktree':<30}")
    print("-" * 70)
    for agent_id, ports in registry['agents'].items():
        print(f"{agent_id:<15} {ports['frontend']:<10} {ports['backend']:<10} {ports['worktree']:<30}")


def check_conflicts():
    """检查所有已分配端口是否被占用"""
    registry = load_registry()

    if not registry['agents']:
        print("暂无 Agent 分配")
        return

    print("\n=== 端口冲突检查 ===\n")
    conflicts = []

    for agent_id, ports in registry['agents'].items():
        for service, port in [('frontend', ports['frontend']), ('backend', ports['backend'])]:
            if is_port_free(port):
                print(f"  [OK] Agent {agent_id} {service} ({port}): 空闲")
            else:
                print(f"  [X] Agent {agent_id} {service} ({port}): 被占用")
                conflicts.append((agent_id, service, port))

    if conflicts:
        print(f"\n[!] 发现 {len(conflicts)} 个端口冲突")
        return False
    else:
        print("\n[OK] 所有端口都空闲（Agent 启动后会占用）")
        return True


def main():
    parser = argparse.ArgumentParser(
        description='多 Agent 端口分配器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python allocate_ports.py allocate --agent agent_C
    python allocate_ports.py release --agent agent_C
    python allocate_ports.py list
    python allocate_ports.py check
        """
    )
    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # allocate
    alloc_parser = subparsers.add_parser('allocate', help='分配端口')
    alloc_parser.add_argument('--agent', required=True, help='Agent ID')
    alloc_parser.add_argument('--worktree', help='worktree 路径')

    # release
    rel_parser = subparsers.add_parser('release', help='释放端口')
    rel_parser.add_argument('--agent', required=True, help='Agent ID')

    # list
    subparsers.add_parser('list', help='列出所有分配')

    # check
    subparsers.add_parser('check', help='检查端口冲突')

    args = parser.parse_args()

    if args.command == 'allocate':
        allocate_ports(args.agent, args.worktree)
    elif args.command == 'release':
        release_ports(args.agent)
    elif args.command == 'list':
        list_agents()
    elif args.command == 'check':
        check_conflicts()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
