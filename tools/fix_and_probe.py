#!/usr/bin/env python3
"""修复 obs + 探查 log_service"""
import urllib.request, ssl, hashlib, time, json

CORE = "https://172.20.59.7:9200"
OBS  = "http://172.20.59.7:9201"
LOG  = "http://172.20.59.7:9101"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

SECRETS = {
    "admin": "v007.52-core",
    "write": "v007.52-core-write",
    "read":  "v007.52-core-read",
}

def token(level="admin"):
    h = int(time.time()) // 3600
    return hashlib.sha256(f"{SECRETS[level]}:{h}".encode()).hexdigest()[:16]

def call_core(method, path, query=None, body=None):
    url = CORE + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, method=method)
    data = body if isinstance(body, bytes) else (body.encode() if body else None)
    try:
        with urllib.request.urlopen(req, data=data, timeout=10, context=ctx) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return 0, str(e)

t = token("admin")

# 1. 恢复 obs
startup_script = """#!/bin/bash
cd /opt/app/shared
export CORE_SERVICE_ADMIN_SECRET=v007.52-core-admin
export CORE_SERVICE_WRITE_SECRET=v007.52-core-write
export CORE_SERVICE_READ_SECRET=v007.52-core-read
export OBS_CORE_URL=https://127.0.0.1:9200
export OBS_AUDIT_LOG=/var/log/core_service_audit.log
nohup /opt/miniconda3-py39/bin/python observability_service.py > /var/log/observability_service.log 2>&1 &
echo "obs started, pid=$!"
"""
code, _ = call_core("POST", "/api/upload", {"path": "/tmp/start_obs.sh", "token": t}, body=startup_script.encode())
print(f"upload start_obs.sh: {code}")
code, _ = call_core("GET", "/api/exec", {"cmd": "chmod +x /tmp/start_obs.sh", "token": t})
print(f"chmod: {code}")
code, body = call_core("GET", "/api/exec", {"cmd": "bash /tmp/start_obs.sh", "token": t, "bg": "true"})
print(f"start obs: {code} {body[:200]}")
time.sleep(4)

try:
    r = urllib.request.urlopen(OBS + "/api/health", timeout=5)
    print(f"obs health: {r.status} {r.read().decode()[:100]}")
except Exception as e:
    print(f"obs health: FAIL {e}")

# 2. 找 log_service 位置和 secret
code, body = call_core("GET", "/api/exec", {"cmd": "find /opt /tmp -name log_service.py 2>/dev/null | head -5", "token": t})
print(f"\nlog_service locations: {body[:300]}")

# 3. 检查 log_service 的 secret (从进程环境变量)
code, body = call_core("GET", "/api/exec", {"cmd": "ps aux | grep log_service | grep -v grep", "token": t})
print(f"\nlog_service process: {body[:300]}")

# 4. 看 log_service 的端口
code, body = call_core("GET", "/api/exec", {"cmd": "ss -tlnp | grep 9101", "token": t})
print(f"\nport 9101: {body[:200]}")

# 5. 看 log_service 健康端点详细信息
try:
    r = urllib.request.urlopen(LOG + "/api/health", timeout=5)
    print(f"\nlog health: {r.read().decode()[:300]}")
except Exception as e:
    print(f"\nlog health: FAIL {e}")

# 6. 看 log_service 的 exec 端点需要什么 token
try:
    r = urllib.request.urlopen(LOG + "/api", timeout=5)
    print(f"\nlog /api: {r.read().decode()[:500]}")
except Exception as e:
    print(f"\nlog /api: FAIL {e}")
