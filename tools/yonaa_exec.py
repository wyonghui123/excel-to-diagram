"""yonaa_exec.py - 通用 yonaa 远端执行客户端

封装:
  - 限流 (sleep_between 1.2s, 适配 20 req/s 限制)
  - 跨小时 token 重试 (current + previous 2 hours)
  - 错误分类 (403=auth / 0=network / 429=rate / 4xx=logic / 5xx=server)
  - 自动 secret 探测 (env > config > fallback)
  - 简单 retry (transient 错误重试 2 次)

API:
  yexec(cmd, port=19200, secret=None, timeout=60) -> dict
  yupload(local_path, remote_path, port=19200, secret=None) -> dict
  yuploaderun(local_path, remote_path='/tmp/agent.py', port=19200) -> dict
  sleep_between() -> None

用法:
  from tools.yonaa_exec import yexec, yuploaderun
  r = yexec('ls -la /opt/app/staging')
  print(r['stdout'])

  r = yuploaderun('./my_health_check.py')
  print(r['stdout'])
"""
import hashlib
import http.client
import os
import time
import urllib.parse

HOST = '172.20.59.7'

# 已知 secret 列表 (按优先级: prod 优先于 staging)
KNOWN_SECRETS = {
    'prod_write':  'v007.52-core-write',
    'prod_admin':  'v007.52-core-admin',
    'prod_read':   'v007.52-core-read',
    'prod_single': 'v007.52-core',           # 单 secret 模式
    'infra':       'v007.35-infra',          # log_service
    'staging':     'staging-v007.49-d',      # staging 启动脚本里写的
}

# 已知端口 (按用途)
KNOWN_PORTS = {
    'observability': 9201,    # 探活 + upload (无 exec)
    'core_prod':     9200,    # prod core_service
    'core_staging':  19200,   # staging core_service
    'log_prod':      9101,    # prod log_service
    'log_staging':   19101,   # staging log_service
    'frontend':      8081,    # 前端 (无 token)
    'backend':       3011,    # backend (无 token)
}


def _gen_tokens(secret, count=3):
    """生成跨小时 token 列表: 当前 + 前 N-1 小时"""
    now = int(time.time())
    tokens = []
    for off in range(count):
        h = (now - off * 3600) // 3600
        tokens.append(hashlib.sha256(f"{secret}:{h}".encode()).hexdigest()[:16])
    return tokens


def _http_get(host, port, path, timeout):
    """底层 HTTP GET"""
    conn = http.client.HTTPConnection(host, port, timeout=timeout+5)
    try:
        conn.request('GET', path)
        resp = conn.getresponse()
        body = resp.read().decode('utf-8', errors='replace')
        return resp.status, body
    except Exception as e:
        return 0, str(e)
    finally:
        conn.close()


def _http_post(host, port, path, data, content_type='application/octet-stream', timeout=60):
    """底层 HTTP POST"""
    conn = http.client.HTTPConnection(host, port, timeout=timeout+5)
    try:
        conn.request('POST', path, body=data, headers={'Content-Type': content_type})
        resp = conn.getresponse()
        body = resp.read().decode('utf-8', errors='replace')
        return resp.status, body
    except Exception as e:
        return 0, str(e)
    finally:
        conn.close()


def _classify_error(status, body):
    """错误分类 (统一返回 dict)"""
    if status == 200:
        return None  # 无错误
    if status == 0:
        return {'error_class': 'network', 'reason': body[:200]}
    if status == 403:
        return {'error_class': 'auth', 'reason': 'token 全部 403, 检查 secret/小时窗口'}
    if status == 429:
        return {'error_class': 'rate_limit', 'reason': '触发限流, sleep 2s 后重试'}
    if 400 <= status < 500:
        return {'error_class': 'logic', 'status': status, 'reason': body[:200]}
    if 500 <= status < 600:
        return {'error_class': 'server', 'status': status, 'reason': body[:200]}
    return {'error_class': 'unknown', 'status': status, 'reason': body[:200]}


def _resolve_secret(secret):
    """解析 secret: alias → 实际值; env 覆盖; None → 报错"""
    if secret is None:
        # 优先 env
        for env_name in ('YONAA_SECRET', 'CORE_SERVICE_SECRET'):
            v = os.environ.get(env_name)
            if v:
                return v
        # fallback 到 known dict
        return KNOWN_SECRETS['prod_write']
    if secret in KNOWN_SECRETS:
        return KNOWN_SECRETS[secret]
    return secret  # 当作明文 secret


def sleep_between(sec=None):
    """限流: 默认 1.2s 间隔 (兼容 20 req/s)"""
    if sec is None:
        sec = 1.2
    time.sleep(sec)


def yexec(cmd, port=19200, secret=None, timeout=60, retries=2):
    """GET /api/exec?cmd=...&token=...

    Args:
        cmd: 要执行的命令 (不要 'cd X &&', 应该用 'bash -c "cd X && ..."')
        port: 端口 (默认 19200 staging core_service)
        secret: secret 字符串 / alias / None (None 时从 env/KNOWN_SECRETS 取)
        timeout: 命令超时 (秒)
        retries: 重试次数 (transient 错误: 429 / network)

    Returns:
        dict: {'cmd': str, 'exit_code': int, 'stdout': str, 'stderr': str, 'elapsed_ms': float, ...}
        失败: {'error': True, 'error_class': str, 'reason': str, ...}
    """
    secret = _resolve_secret(secret)
    last_err = None
    for attempt in range(retries):
        for tk in _gen_tokens(secret):
            params = urllib.parse.urlencode({'cmd': cmd, 'timeout': str(timeout), 'token': tk})
            status, body = _http_get(HOST, port, f'/api/exec?{params}', timeout)
            if status == 200:
                try:
                    import json
                    return json.loads(body)
                except Exception:
                    return {'raw': body, 'stdout': body, 'stderr': '', 'exit_code': 0}
            err = _classify_error(status, body)
            last_err = err or {'error_class': 'http', 'status': status, 'body': body[:200]}
            if status == 403:
                continue  # 试下一个 token
            if status == 429:
                time.sleep(2.0)  # rate limited
                break  # 重试整个 attempt
            if status == 0:
                break  # network 错, 重试整个 attempt
            # 4xx/5xx 立即返回 (非 transient)
            return {'error': True, **err}
        time.sleep(1.0)  # 跨 attempt 间隔
    return {'error': True, **last_err}


def yupload(local_path, remote_path, port=19200, secret=None, timeout=120):
    """POST /api/upload?path=...&token=...

    Args:
        local_path: 本地文件路径
        remote_path: 远端路径 (受 ALLOWED_DIRS 限制)
        port: 端口
        secret: secret
        timeout: 超时

    Returns:
        dict: 成功 {'action': 'uploaded', 'path': str, 'size': int, 'md5': str, ...}
        失败: {'error': True, ...}
    """
    secret = _resolve_secret(secret)
    if not os.path.exists(local_path):
        return {'error': True, 'error_class': 'local', 'reason': f'file not found: {local_path}'}
    with open(local_path, 'rb') as f:
        data = f.read()
    for tk in _gen_tokens(secret):
        url = f'/api/upload?path={urllib.parse.quote(remote_path, safe="")}&token={tk}'
        status, body = _http_post(HOST, port, url, data, timeout=timeout)
        if status == 200:
            try:
                import json
                return json.loads(body)
            except Exception:
                return {'ok': True, 'raw': body}
        if status == 403:
            continue
        err = _classify_error(status, body)
        if err:
            return {'error': True, **err}
    return {'error': True, 'error_class': 'auth', 'reason': 'all tokens 403'}


def yuploaderun(local_path, remote_path='/tmp/agent.py', port=19200, secret=None, cleanup=True):
    """上传脚本 + 执行 + 清理 (一步到位)

    Returns:
        dict: yuploaderun 的执行结果 (含 stdout/stderr)
    """
    up = yupload(local_path, remote_path, port=port, secret=secret)
    if up.get('error'):
        return up
    # 用 PATH 中的 python3 (staging 是 /usr/bin/python3, prod 也是), 不用 miniconda 绝对路径
    cmd = f'python3 {remote_path}'
    if cleanup:
        cmd += f'; rm -f {remote_path}'
    return yexec(cmd, port=port, secret=secret, timeout=120)


# ============== 便捷入口 ==============

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print('Usage:')
        print('  python tools/yonaa_exec.py exec <cmd> [port=19200] [secret=prod_write]')
        print('  python tools/yonaa_exec.py upload <local> <remote> [port=19200]')
        print('  python tools/yonaa_exec.py probe <port>')
        sys.exit(1)
    op = sys.argv[1]
    if op == 'exec':
        cmd = sys.argv[2]
        port = int(sys.argv[3]) if len(sys.argv) > 3 else 19200
        secret = sys.argv[4] if len(sys.argv) > 4 else 'prod_write'
        print(yexec(cmd, port=port, secret=secret))
    elif op == 'upload':
        local, remote = sys.argv[2], sys.argv[3]
        port = int(sys.argv[4]) if len(sys.argv) > 4 else 19200
        print(yupload(local, remote, port=port))
    elif op == 'probe':
        port = int(sys.argv[2])
        status, body = _http_get(HOST, port, '/api', timeout=5)
        print(f'GET /api → {status} {body[:500]}')
    else:
        print(f'Unknown op: {op}')
        sys.exit(1)
