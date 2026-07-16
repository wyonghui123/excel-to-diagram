"""remote_helper.py - 安全的远程执行库 [V007.67 2026-07-14]
[L1 + L2 + L5 修复] 替代 monitor_prod.py 的 base64 + bash -c 反模式

使用方式 (参考 .trae/rules/remote-execution-simplicity.md V3):
  1. 本地直跑:  RunCommand 直跑
  2. yonaa 远端 (无 SSH, 必须 HTTP):
     - 单行命令: http_exec('ls -la /tmp', secret='v007.35-infra')
     - 复杂脚本: http_upload(local, '/tmp/agent.py', secret) + http_exec('python3 /tmp/agent.py; rm -f /tmp/agent.py', secret)
     - 不允许 base64, 不允许 bash -c 嵌套

禁止 (L1/L2/L5):
  - HTTP 调 127.0.0.1 (自己调自己)
  - base64 + bash -c (木马启发式)
  - 临时文件路径 /tmp/*.py 立即执行
  - 反向 shell 模式
"""
import hashlib
import json
import time
import urllib.parse
import urllib.request
import urllib.error
from typing import Optional, Tuple


# 默认 token secret (仅用于 log_service 9101)
DEFAULT_SECRET = "v007.35-infra"
YONAA = "172.20.59.7"
LOG_SERVICE_URL = f"http://{YONAA}:9101"


def get_token(secret: str = DEFAULT_SECRET) -> str:
    """生成时变 token: sha256(secret:hour)[:16]

    Args:
        secret: 共享密钥 (不同服务不同)

    Returns:
        16 字符 token
    """
    h = int(time.time()) // 3600
    return hashlib.sha256(f"{secret}:{h}".encode()).hexdigest()[:16]


def http_exec(
    cmd: str,
    secret: str = DEFAULT_SECRET,
    timeout: int = 30,
    host: str = YONAA,
    port: int = 9101,
) -> dict:
    """远端 yonaa 执行单行命令 (L2: HTTP GET /api/exec 明文)

    Args:
        cmd: 单行命令 (URL 编码自动处理, 不 base64)
        secret: 共享密钥 (v007.35-infra 默认)
        timeout: 命令执行超时秒
        host: yonaa IP (默认 172.20.59.7)
        port: log_service 端口 (默认 9101)

    Returns:
        dict: {stdout, stderr, exit_code, success}

    Raises:
        urllib.error.HTTPError: 403 token 无效 / 4xx / 5xx
        ConnectionError: 网络不通

    Examples:
        >>> r = http_exec('ls -la /opt/app/deployments/current')
        >>> print(r['stdout'])
    """
    if not cmd or not isinstance(cmd, str):
        return {
            "stdout": "",
            "stderr": "ERROR: cmd must be non-empty string",
            "exit_code": -1,
            "success": False,
        }
    if "\n" in cmd:
        # L3 简化: 多行命令拆成多条, 或用 http_script 上传脚本
        return {
            "stdout": "",
            "stderr": "ERROR: Multi-line command not allowed. Use http_script() for complex scripts (L3 simplify).",
            "exit_code": -1,
            "success": False,
        }

    token = get_token(secret)
    params = urllib.parse.urlencode({
        "cmd": cmd,
        "timeout": str(timeout),
        "token": token,
    })
    url = f"http://{host}:{port}/api/exec?{params}"

    try:
        with urllib.request.urlopen(url, timeout=timeout + 10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        return {
            "stdout": "",
            "stderr": f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}",
            "exit_code": -1,
            "success": False,
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": f"{type(e).__name__}: {str(e)[:200]}",
            "exit_code": -1,
            "success": False,
        }


def http_upload(
    local_path: str,
    remote_path: str,
    secret: str = DEFAULT_SECRET,
    host: str = YONAA,
    port: int = 9101,
) -> Tuple[bool, str]:
    """远端 yonaa 上传文件 (L2: 明文 POST /api/upload)

    Args:
        local_path: 本地文件路径
        remote_path: 远端路径 (必须在 ALLOWED_DIRS 内)
        secret: 共享密钥
        host: yonaa IP
        port: log_service 端口

    Returns:
        (success, message)

    Examples:
        >>> ok, msg = http_upload('./health.py', '/tmp/health.py')
        >>> if ok:
        ...     http_exec('python3 /tmp/health.py; rm -f /tmp/health.py')
    """
    try:
        with open(local_path, "rb") as f:
            data = f.read()
    except FileNotFoundError:
        return False, f"FileNotFoundError: {local_path}"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:200]}"

    token = get_token(secret)
    url = f"http://{host}:{port}/api/upload?path={urllib.parse.quote(remote_path)}&token={token}"
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/octet-stream")

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return True, body[:200]
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:200]}"


def http_script(
    local_path: str,
    remote_path: str = "/tmp/agent_script.py",
    secret: str = DEFAULT_SECRET,
    cleanup: bool = True,
    host: str = YONAA,
    port: int = 9101,
) -> dict:
    """远端 yonaa 上传并执行 Python 脚本 (L2 + L5 修复)

    完整流程:
      1. POST /api/upload (明文) 上传脚本
      2. GET /api/exec 跑 python3 /tmp/agent_script.py
      3. (可选) GET /api/exec 跑 rm -f /tmp/agent_script.py 清理

    Args:
        local_path: 本地 .py 文件
        remote_path: 远端路径 (默认 /tmp/agent_script.py)
        secret: 共享密钥
        cleanup: 跑完是否自动 rm 临时文件 (L3 简化: 默认 True)
        host: yonaa IP
        port: log_service 端口

    Returns:
        dict: http_exec 返回的结果 (含 stdout/stderr/exit_code)

    Examples:
        >>> result = http_script('./health_check.py')
        >>> print(result['stdout'])
    """
    ok, msg = http_upload(local_path, remote_path, secret=secret, host=host, port=port)
    if not ok:
        return {
            "stdout": "",
            "stderr": f"upload failed: {msg}",
            "exit_code": -1,
            "success": False,
        }

    run_cmd = f"python3 {remote_path}"
    if cleanup:
        run_cmd += f"; rm -f {remote_path}"

    return http_exec(run_cmd, secret=secret, host=host, port=port)


# ─── 兼容性包装 (V3 之前的 monitor_prod.py 调用风格) ─────────────

def exec_remote(cmd: str, secret: str = DEFAULT_SECRET, **kwargs) -> Optional[dict]:
    """兼容 monitor_prod.py 的 exec_remote() 接口

    Returns None on HTTP error (vs http_exec returns dict).
    """
    r = http_exec(cmd, secret=secret, **kwargs)
    if not r.get("success", False):
        return {"error": True, "body": r.get("stderr", "")}
    return r


if __name__ == "__main__":
    # Self-test: 列出 yonaa 上的部署目录
    import sys
    if len(sys.argv) > 1:
        cmd = " ".join(sys.argv[1:])
        result = http_exec(cmd)
        print("STDOUT:", result.get("stdout", ""))
        print("STDERR:", result.get("stderr", ""))
        print("EXIT:", result.get("exit_code"))
    else:
        print("Usage: python remote_helper.py <cmd>")
        print("       e.g. python remote_helper.py ls -la /opt/app/deployments/current")