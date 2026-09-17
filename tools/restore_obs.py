#!/usr/bin/env python3
"""恢复 obs 并确认最终状态"""
import urllib.request, ssl, hashlib, time, json

CORE = "https://172.20.59.7:9200"
OBS  = "http://172.20.59.7:9201"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

SECRETS = {"admin": "v007.52-core"}
def token():
    h = int(time.time()) // 3600
    return hashlib.sha256(f"{SECRETS['admin']}:{h}".encode()).hexdigest()[:16]

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

t = token()

# 1. 检查 obs 进程
code, body = call_core("GET", "/api/exec", {"cmd": "ps aux | grep observability | grep -v grep", "token": t})
print(f"obs process: {body[:200]}")

# 2. 检查 obs 日志
code, body = call_core("GET", "/api/exec", {"cmd": "tail -5 /var/log/observability_service.log 2>/dev/null || echo NO_LOG", "token": t})
print(f"obs log: {body[:300]}")

# 3. 写启动脚本
start_script = """#!/bin/bash
cd /opt/app/shared
export CORE_SERVICE_ADMIN_SECRET=v007.52-core-admin
export CORE_SERVICE_WRITE_SECRET=v007.52-core-write
export CORE_SERVICE_READ_SECRET=v007.52-core-read
export OBS_CORE_URL=https://127.0.0.1:9200
export OBS_AUDIT_LOG=/var/log/core_service_audit.log
nohup /opt/miniconda3-py39/bin/python observability_service.py > /var/log/observability_service.log 2>&1 &
echo "obs started pid=$!"
"""
code, _ = call_core("POST", "/api/upload",
    {"path": "/tmp/start_obs.sh", "token": t}, body=start_script.encode())
print(f"upload: {code}")

# 4. 执行启动
code, body = call_core("GET", "/api/exec",
    {"cmd": "bash /tmp/start_obs.sh", "token": t})
print(f"start: {code} {body[:200]}")

time.sleep(5)

# 5. 验证
code, body = call_core("GET", "/api/exec", {"cmd": "ps aux | grep observability | grep -v grep", "token": t})
print(f"obs process after: {body[:200]}")

try:
    r = urllib.request.urlopen(OBS + "/api/health", timeout=5)
    print(f"obs health: {r.status} {r.read().decode()[:200]}")
except Exception as e:
    print(f"obs health: FAIL {e}")

# 6. 核心验证: core 仍在线
code, body = call_core("GET", "/api")
print(f"core_service: {code}, version={'v2.0' if 'v2.0' in body else 'unknown'}")
