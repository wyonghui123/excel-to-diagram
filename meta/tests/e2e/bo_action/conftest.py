# -*- coding: utf-8 -*-
"""
[MODULE] BO Action 测试本地 conftest.py
[DESCRIPTION] 提供 BO Action 7 模块的共享 fixtures

所有 BO Action 测试:
- 走 HTTP server (localhost:3010, 或 AGENT_PORT), 用 cookie 认证
- 不在 xdist 并行下跑 (需要 server + 顺序)
- 用 TEST_ENTRY=1 (test.py 自动设置)

[DECORATIVE] v3.18 新增:
- bo_action_server_or_start (D.3): server 不在时自动启
- bo_action_server_check 保持兼容 (skip if down)
- per-port 支持 (AGENT_PORT env)
- admin_cookie 不变

合规:
- [OK] 走 test.py 入口 (不用 pytest)
- [OK] 不用 Bearer token, 用 cookie (跟 SESSION_REMINDER 一致)
- [OK] 不直接读写 meta/architecture.db (走 test.py 快照)
- [OK] AGENT_PORT 支持 (D.7 多 agent 隔离)
"""
import os
import sys
import socket
import subprocess
import time
import pytest

# BO Action 测试在 meta/tests/e2e/bo_action/
# fixtures 在 tests/fixtures/ (项目根下, 跨目录)
_HERE = os.path.dirname(os.path.abspath(__file__))  # .../meta/tests/e2e/bo_action
_E2E_DIR = os.path.dirname(_HERE)                    # .../meta/tests/e2e
_TESTS_DIR = os.path.dirname(_E2E_DIR)               # .../meta/tests
_META_DIR = os.path.dirname(_TESTS_DIR)              # .../meta
_PROJECT_ROOT = os.path.dirname(_META_DIR)           # d:/filework/excel-to-diagram
_FIXTURES_DIR = os.path.join(_PROJECT_ROOT, 'tests', 'fixtures')
sys.path.insert(0, _FIXTURES_DIR)

# [DECORATIVE] v3.18: 多 agent 端口 (AGENT_PORT, 默认 3010)
DEFAULT_PORT = int(os.environ.get('AGENT_PORT', '3010'))


def _check_server(host='localhost', port=None, timeout=2):
    """快速检查 server 端口是否在监听"""
    if port is None:
        port = DEFAULT_PORT
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


def _start_server_if_needed(port=None):
    """[DECORATIVE] D.3: 通过 service_manager.ps1 启动 server (幂等)"""
    if port is None:
        port = DEFAULT_PORT
    if _check_server(port):
        return True

    # 调 service_manager.ps1 start -Port <port>
    sm_path = os.path.join(_PROJECT_ROOT, 'scripts', 'service_manager.ps1')
    if not os.path.exists(sm_path):
        return False

    try:
        subprocess.run(
            ['powershell', '-File', sm_path, 'start', '-Port', str(port)],
            capture_output=True, text=True, timeout=30,
        )
        # 等 server 起来
        for _ in range(15):
            time.sleep(1)
            if _check_server(port):
                return True
    except Exception:
        pass
    return False


@pytest.fixture(scope='session')
def bo_action_server_check():
    """检查 server 是否在跑, 不在则 skip 整个 module (v3.17 兼容)"""
    if not _check_server():
        pytest.skip(f'BO Action 测试需 server 在 localhost:{DEFAULT_PORT} 跑, '
                    f'请用 service_manager.ps1 start -Port {DEFAULT_PORT}')


@pytest.fixture(autouse=True)
def _bo_action_server_autouse(request):
    """[DECORATIVE] v3.18: autouse fixture, 强制所有 bo_action 测试在 server 不在时 skip

    避免出现 ConnectionRefusedError 导致 failed 而不是 skip
    """
    # 仅对 BO Action 测试生效
    if 'bo_action' not in str(request.fspath).replace('\\', '/'):
        return

    if not _check_server():
        pytest.skip(f'BO Action 测试需 server 在 localhost:{DEFAULT_PORT} 跑, '
                    f'请用 service_manager.ps1 start -Port {DEFAULT_PORT}')


@pytest.fixture(scope='session')
def bo_action_server_or_start():
    """[DECORATIVE] D.3: server 不在时自动启动"""
    if not _check_server():
        if not _start_server_if_needed():
            pytest.skip(f'无法启动 server 在 localhost:{DEFAULT_PORT}, '
                        f'请用 service_manager.ps1 start -Port {DEFAULT_PORT}')


@pytest.fixture(scope='session')
def admin_cookie():
    """获取 admin 登录 cookie (session scope, 1 次登录即可)"""
    from admin_token import get_admin_cookie
    return get_admin_cookie()


def pytest_collection_modifyitems(config, items):
    """
    [HOOK] 给所有 BO Action 测试加:
    - pytest.mark.e2e
    - pytest.mark.bo_action
    - pytest.mark.requires_server (跳过 xdist)
    """
    for item in items:
        item.add_marker(pytest.mark.e2e)
        item.add_marker(pytest.mark.bo_action)
        # 不在 xdist 下跑
        if hasattr(item, 'pytestmark'):
            item.pytestmark.append(pytest.mark.requires_server)
