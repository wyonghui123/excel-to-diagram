"""[L14] deploy_service.py 单元测试 (离线, 无 socket)"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from deploy_service import (
    DeployState,
    CURRENT_DEPLOY,
    DEPLOY_LOCK,
    check_token,
    deploy_worker,
    Handler,
)


def test_deploy_states_complete():
    """11 个状态完整定义"""
    states = {s.value for s in DeployState}
    assert len(states) == 11
    assert "idle" in states
    assert "done" in states
    assert "failed" in states


def test_check_token_valid():
    """时变 token 在同一小时内有效"""
    secret = "v007.65-deploy"
    h = int(time.time()) // 3600
    import hashlib
    token = hashlib.sha256(f"{secret}:{h}".encode()).hexdigest()[:16]
    assert check_token(token) is True


def test_check_token_invalid():
    """错误 token 拒绝"""
    assert check_token("") is False
    assert check_token("wrong") is False


def test_check_token_wrong_secret():
    """错误 secret 生成的 token 拒绝"""
    import hashlib
    h = int(time.time()) // 3600
    token = hashlib.sha256(f"wrong-secret:{h}".encode()).hexdigest()[:16]
    assert check_token(token) is False


def test_initial_state_idle():
    """初始状态 = idle"""
    assert CURRENT_DEPLOY["state"] == DeployState.IDLE.value


def test_deploy_worker_progression():
    """worker 完成后 state=done, exit_code=0"""
    # 重置
    CURRENT_DEPLOY.update({
        "state": DeployState.IDLE.value,
        "version": None,
        "started_at": None,
        "ended_at": None,
        "exit_code": None,
    })
    t = __import__("threading").Thread(
        target=deploy_worker,
        args=("test_version", "/tmp/test.zip", "full"),
        daemon=True,
    )
    t.start()
    t.join(timeout=15)  # 等待 worker 完成 (5 phases × 2s + 缓冲)
    assert CURRENT_DEPLOY["state"] == DeployState.DONE.value
    assert CURRENT_DEPLOY["exit_code"] == 0
    assert CURRENT_DEPLOY["version"] == "test_version"