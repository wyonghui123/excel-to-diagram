"""
多智能体浏览器资源隔离 - Session Manager

解决多智能体并行测试时的浏览器 Tab 冲突问题。

使用方式:
    # 声明一个 Page
    python session_manager.py claim --agent agent-001
    # 输出: Claimed page 9 (status: created)

    # 查看所有会话
    python session_manager.py list
    # 输出: {"sessions": {...}}

    # 释放
    python session_manager.py release --agent agent-001
"""

import json
import os
import sys
import fcntl
import time
import argparse
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

SESSION_DIR = Path(__file__).parent
SESSION_FILE = SESSION_DIR / 'session_manager.json'
LOCK_FILE = SESSION_DIR / '.lock'
SESSION_TIMEOUT = 5 * 60  # 5 分钟超时 (秒)


class BrowserSessionManager:
    """
    浏览器会话管理器

    解决多智能体并行测试时的 Page ID 冲突问题。
    通过文件锁确保并发安全，通过超时机制自动清理僵尸会话。
    """

    _local = threading.local()

    def __init__(self):
        SESSION_DIR.mkdir(exist_ok=True)

    def _acquire_lock(self) -> None:
        """获取文件锁"""
        self._lock_fd = open(LOCK_FILE, 'w')
        fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_EX)

    def _release_lock(self) -> None:
        """释放文件锁"""
        if hasattr(self, '_lock_fd') and self._lock_fd:
            try:
                fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_UN)
                self._lock_fd.close()
            except Exception:
                pass
            self._lock_fd = None

    def _read(self) -> Dict[str, Any]:
        """读取会话数据"""
        if SESSION_FILE.exists():
            try:
                return json.loads(SESSION_FILE.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, IOError):
                pass
        return {'sessions': {}}

    def _write(self, data: Dict[str, Any]) -> None:
        """写入会话数据"""
        SESSION_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )

    def _cleanup_timeout(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """清理超时会话"""
        now = datetime.now().timestamp()
        sessions = data.get('sessions', {})
        to_remove = []

        for agent_id, session in sessions.items():
            try:
                last_used = datetime.fromisoformat(session['lastUsed']).timestamp()
                if now - last_used > SESSION_TIMEOUT:
                    to_remove.append(agent_id)
            except (KeyError, ValueError):
                to_remove.append(agent_id)

        for agent_id in to_remove:
            print(f"[WARN] 清理超时会话: {agent_id} (Page {sessions[agent_id]['pageId']})")
            del sessions[agent_id]

        data['sessions'] = sessions
        return data

    def claim(self, agent_id: str) -> Dict[str, Any]:
        """
        声明一个 Page ID

        Args:
            agent_id: 智能体唯一标识

        Returns:
            {"pageId": int, "status": "created" | "reused"}

        Raises:
            RuntimeError: 获取锁失败
        """
        try:
            self._acquire_lock()

            data = self._read()
            data = self._cleanup_timeout(data)

            # 检查是否已有自己的 session
            sessions = data.get('sessions', {})
            if agent_id in sessions:
                page_id = sessions[agent_id]['pageId']
                sessions[agent_id]['lastUsed'] = datetime.now().isoformat()
                self._write(data)
                return {'pageId': page_id, 'status': 'reused'}

            # 找最小可用 pageId
            used_page_ids = {s['pageId'] for s in sessions.values()}
            page_id = 0
            while page_id in used_page_ids:
                page_id += 1

            # 分配
            sessions[agent_id] = {
                'pageId': page_id,
                'createdAt': datetime.now().isoformat(),
                'lastUsed': datetime.now().isoformat(),
                'status': 'active',
                'pid': os.getpid()
            }
            data['sessions'] = sessions
            self._write(data)

            return {'pageId': page_id, 'status': 'created'}

        except Exception as e:
            raise RuntimeError(f"Failed to claim session: {e}") from e
        finally:
            self._release_lock()

    def release(self, agent_id: str) -> bool:
        """
        释放 Page ID

        Args:
            agent_id: 智能体唯一标识

        Returns:
            True if released, False if not found
        """
        try:
            self._acquire_lock()

            data = self._read()
            sessions = data.get('sessions', {})

            if agent_id in sessions:
                page_id = sessions[agent_id]['pageId']
                del sessions[agent_id]
                data['sessions'] = sessions
                self._write(data)
                print(f"[INFO] 释放 Page {page_id} (agent: {agent_id})")
                return True

            return False

        except Exception as e:
            raise RuntimeError(f"Failed to release session: {e}") from e
        finally:
            self._release_lock()

    def heartbeat(self, agent_id: str) -> bool:
        """
        更新心跳（防止超时清理）

        Args:
            agent_id: 智能体唯一标识

        Returns:
            True if updated, False if not found
        """
        try:
            self._acquire_lock()

            data = self._read()
            sessions = data.get('sessions', {})

            if agent_id in sessions:
                sessions[agent_id]['lastUsed'] = datetime.now().isoformat()
                data['sessions'] = sessions
                self._write(data)
                return True

            return False

        except Exception as e:
            raise RuntimeError(f"Failed to update heartbeat: {e}") from e
        finally:
            self._release_lock()

    def list_sessions(self) -> Dict[str, Any]:
        """
        列出所有会话

        Returns:
            {"sessions": {agent_id: {...}, ...}}
        """
        try:
            self._acquire_lock()
            data = self._read()
            return data.get('sessions', {})
        finally:
            self._release_lock()

    def get_my_session(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """获取自己的会话信息"""
        sessions = self.list_sessions()
        return sessions.get(agent_id)

    def force_release_all(self) -> int:
        """强制释放所有会话（用于调试）"""
        try:
            self._acquire_lock()
            data = self._read()
            count = len(data.get('sessions', {}))
            data['sessions'] = {}
            self._write(data)
            return count
        finally:
            self._release_lock()


class BrowserSession:
    """
    上下文管理器，自动管理会话生命周期

    使用方式:
        with BrowserSession('agent-001') as session:
            page_id = session.page_id
            # ... 执行测试 ...
        # 自动释放
    """

    def __init__(self, agent_id: Optional[str] = None):
        self.agent_id = agent_id or f'agent-{os.getpid()}'
        self.page_id: Optional[int] = None
        self._manager = BrowserSessionManager()

    def __enter__(self) -> 'BrowserSession':
        result = self._manager.claim(self.agent_id)
        self.page_id = result['pageId']
        print(f"[SESSION] Agent {self.agent_id} 声明 Page {self.page_id} (status: {result['status']})")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self._manager.release(self.agent_id)
        print(f"[SESSION] Agent {self.agent_id} 释放 Page {self.page_id}")
        return False

    def heartbeat(self) -> None:
        """更新心跳"""
        self._manager.heartbeat(self.agent_id)


def main():
    """CLI 入口"""
    parser = argparse.ArgumentParser(
        description='浏览器会话管理器 - 多智能体资源隔离',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python session_manager.py claim --agent agent-001    # 声明 Page
  python session_manager.py release --agent agent-001 # 释放 Page
  python session_manager.py list                       # 查看所有会话
  python session_manager.py heartbeat --agent agent-001  # 更新心跳
  python session_manager.py force-clean              # 清理所有会话（调试用）
        """
    )

    subparsers = parser.add_subparsers(dest='action', help='操作')

    # claim
    claim_parser = subparsers.add_parser('claim', help='声明一个 Page')
    claim_parser.add_argument('--agent', default=f'agent-{os.getpid()}', help='智能体 ID')

    # release
    release_parser = subparsers.add_parser('release', help='释放 Page')
    release_parser.add_argument('--agent', default=f'agent-{os.getpid()}', help='智能体 ID')

    # heartbeat
    heartbeat_parser = subparsers.add_parser('heartbeat', help='更新心跳')
    heartbeat_parser.add_argument('--agent', default=f'agent-{os.getpid()}', help='智能体 ID')

    # list
    subparsers.add_parser('list', help='列出所有会话')

    # force-clean
    subparsers.add_parser('force-clean', help='强制清理所有会话（调试用）')

    args = parser.parse_args()

    if not args.action:
        parser.print_help()
        return 1

    sm = BrowserSessionManager()

    try:
        if args.action == 'claim':
            result = sm.claim(args.agent)
            print(f"Claimed page {result['pageId']} (status: {result['status']})")
            return 0

        elif args.action == 'release':
            if sm.release(args.agent):
                print(f"Released session for {args.agent}")
            else:
                print(f"No session found for {args.agent}")
            return 0

        elif args.action == 'heartbeat':
            if sm.heartbeat(args.agent):
                print(f"Heartbeat updated for {args.agent}")
            else:
                print(f"No session found for {args.agent}")
            return 0

        elif args.action == 'list':
            sessions = sm.list_sessions()
            print(json.dumps({'sessions': sessions}, indent=2, ensure_ascii=False))
            return 0

        elif args.action == 'force-clean':
            count = sm.force_release_all()
            print(f"已清理 {count} 个会话")
            return 0

    except RuntimeError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
