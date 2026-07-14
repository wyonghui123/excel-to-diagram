"""[V3 修复] remote_helper.py 单元测试 (L1+L2+L5)

只测本地逻辑 (http_exec 实际调 yonaa 跳过, 用 monkeypatch 模拟)
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from remote_helper import (
    get_token,
    http_exec,
    http_upload,
    http_script,
    DEFAULT_SECRET,
)


# ─── Test 1: get_token 格式正确 ─────────────────────────────────────

def test_get_token_format():
    """token 是 16 字符 hex (sha256[:16])"""
    t = get_token("test-secret")
    assert len(t) == 16
    assert all(c in "0123456789abcdef" for c in t)


def test_get_token_hourly_changes():
    """token 基于小时, 同小时相同"""
    import time
    t1 = get_token("test")
    time.sleep(0.1)
    t2 = get_token("test")
    # 同小时内 token 应相同
    assert t1 == t2


def test_get_token_different_secret_different_token():
    """不同 secret 生成不同 token"""
    t1 = get_token("secret-A")
    t2 = get_token("secret-B")
    assert t1 != t2


# ─── Test 2: http_exec 输入校验 (L3 简化) ─────────────────────

def test_http_exec_rejects_empty_cmd():
    """空命令应拒绝"""
    r = http_exec("")
    assert r["success"] is False
    assert "cmd" in r["stderr"].lower() or "non-empty" in r["stderr"].lower()


def test_http_exec_rejects_multiline_cmd():
    """多行命令应拒绝 (L3 简化)"""
    r = http_exec("line1\nline2")
    assert r["success"] is False
    assert "multi-line" in r["stderr"].lower() or "http_script" in r["stderr"].lower()


# ─── Test 3: http_exec 远端调用 (mock) ─────────────────────────

def test_http_exec_success_mocked():
    """模拟 HTTP 200 返回"""
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"stdout": "hello", "stderr": "", "exit_code": 0, "success": true}'
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        r = http_exec("ls -la /tmp")
        assert r["stdout"] == "hello"
        assert r["exit_code"] == 0


def test_http_exec_403_handled():
    """403 token 错误不应 crash, 返回失败 dict"""
    import urllib.error
    err = urllib.error.HTTPError(
        url="http://x", code=403, msg="Forbidden", hdrs={}, fp=MagicMock()
    )
    err.read = MagicMock(return_value=b'{"error": "token required"}')

    with patch("urllib.request.urlopen", side_effect=err):
        r = http_exec("ls")
        assert r["success"] is False
        assert "403" in r["stderr"]


# ─── Test 4: http_upload 校验 (mock) ───────────────────────────

def test_http_upload_file_not_found():
    """本地文件不存在应返回失败"""
    ok, msg = http_upload("/nonexistent/path.py", "/tmp/x.py")
    assert ok is False
    assert "not found" in msg.lower() or "filenotfounderror" in msg.lower()


def test_http_upload_success_mocked(tmp_path):
    """模拟成功上传"""
    local = tmp_path / "test.py"
    local.write_text("print('hi')")

    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"ok": true}'
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        ok, msg = http_upload(str(local), "/tmp/test.py")
        assert ok is True


# ─── Test 5: http_script 完整流程 (mock) ──────────────────────

def test_http_script_uploads_and_runs(tmp_path):
    """http_script 应: 上传 -> 执行 -> (cleanup) rm"""
    local = tmp_path / "health.py"
    local.write_text("print('healthy')")

    # Mock both upload and exec
    mock_upload = MagicMock()
    mock_upload.read.return_value = b'{"ok": true}'
    mock_upload.__enter__ = MagicMock(return_value=mock_upload)
    mock_upload.__exit__ = MagicMock(return_value=False)

    mock_exec = MagicMock()
    mock_exec.read.return_value = b'{"stdout": "healthy", "stderr": "", "exit_code": 0, "success": true}'
    mock_exec.__enter__ = MagicMock(return_value=mock_exec)
    mock_exec.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", side_effect=[mock_upload, mock_exec]):
        r = http_script(str(local), cleanup=True)
        assert r["stdout"] == "healthy"
        assert r["exit_code"] == 0


# ─── Test 6: 安全检查 (L2/L5 反模式) ──────────────────────────

def test_no_base64_in_remote_helper():
    """L2 禁止: remote_helper.py 不应使用 base64 (代码, 非 docstring)"""
    src = Path("tools/remote_helper.py").read_text(encoding="utf-8")
    # 排除 docstring 和注释
    code_lines = []
    in_docstring = False
    for line in src.split("\n"):
        if '"""' in line:
            in_docstring = not in_docstring
            continue
        if in_docstring or line.strip().startswith("#"):
            continue
        code_lines.append(line)
    code = "\n".join(code_lines)
    assert "base64" not in code, "L2 禁止: remote_helper.py 代码不应使用 base64"
    assert "bash -c" not in code, "L5 禁止: remote_helper.py 代码不应使用 bash -c"
    assert "127.0.0.1" not in code, "L1 禁止: remote_helper.py 代码不应连接 127.0.0.1"


def test_no_ssh_in_remote_helper():
    """V3 修正: yonaa 无 SSH, remote_helper 不应 import 或调用 ssh"""
    import re
    src = Path("tools/remote_helper.py").read_text(encoding="utf-8")
    # 排除 docstring/注释 (查找 import / 函数定义 / 调用)
    code_lines = []
    in_docstring = False
    for line in src.split("\n"):
        if '"""' in line:
            in_docstring = not in_docstring
            continue
        if in_docstring or line.strip().startswith("#"):
            continue
        code_lines.append(line)
    code = "\n".join(code_lines)
    assert "import paramiko" not in code, "V3 禁止 import paramiko"
    assert "import ssh" not in code
    # 调用检查
    assert "ssh.connect" not in code
    assert "sshpass" not in code


if __name__ == "__main__":
    # Allow running directly
    pytest.main([__file__, "-v"])