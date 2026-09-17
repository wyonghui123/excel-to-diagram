#!/usr/bin/env python3
"""修复: 恢复 observability_service 并运行完整验证"""
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

def call_obs(path):
    try:
        r = urllib.request.urlopen(OBS + path, timeout=5)
        return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return 0, str(e)

def call_log(path):
    try:
        r = urllib.request.urlopen(LOG + path, timeout=5)
        return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return 0, str(e)

PASS = FAIL = 0
def check(name, ok, detail=""):
    global PASS, FAIL
    icon = "[OK]" if ok else "[FAIL]"
    print(f"  {icon} {name}{(': ' + detail) if detail else ''}")
    if ok:
        PASS += 1
    else:
        FAIL += 1

t = token("admin")

# ═══════════════════════════════════════════════════════════
print("=" * 60)
print("  FIX: 恢复 observability_service")
print("=" * 60)

# 1. 先写启动脚本到 yonaa
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

code, body = call_core("POST", "/api/upload",
    {"path": "/tmp/start_obs.sh", "token": t},
    body=startup_script.encode())
check("upload start_obs.sh", code == 200, f"code={code}")

# 2. chmod + x
code, body = call_core("GET", "/api/exec",
    {"cmd": "chmod +x /tmp/start_obs.sh", "token": t})
check("chmod start_obs.sh", code == 200, f"code={code}")

# 3. 执行启动
code, body = call_core("GET", "/api/exec",
    {"cmd": "bash /tmp/start_obs.sh", "token": t, "bg": "true"})
check("exec start_obs.sh", code == 200, f"code={code}")

time.sleep(4)

# 4. 验证 obs 恢复
code, body = call_obs("/api/health")
check("obs health restored", code == 200 and "alive" in body, f"code={code}")

code, body = call_obs("/api/ready")
check("obs ready restored", code == 200, f"code={code}")

# ═══════════════════════════════════════════════════════════
print()
print("=" * 60)
print("  PHASE 1: 元能力服务状态验证 (全量)")
print("=" * 60)

code, body = call_core("GET", "/api")
check("core_service v2.0", code == 200 and "v2.0" in body, f"code={code}")

code, body = call_obs("/api/health")
check("obs health", code == 200 and "alive" in body, f"code={code}")

code, body = call_obs("/api/ready")
check("obs ready (core reachable)", code == 200, f"code={code}")

code, body = call_log("/api/health")
check("log_service health", code == 200, f"code={code}")

# ═══════════════════════════════════════════════════════════
print()
print("=" * 60)
print("  PHASE 2: core_service upload→exec 闭环验证")
print("=" * 60)

# upload
test_content = f"meta-capability test at {int(time.time())}\n".encode()
code, body = call_core("POST", "/api/upload",
    {"path": "/tmp/meta_test_v2.txt", "token": t},
    body=test_content)
check("upload 200", code == 200, f"code={code}")

# exec 读回
code, body = call_core("GET", "/api/exec",
    {"cmd": "cat /tmp/meta_test_v2.txt", "token": t})
check("exec read-back 200", code == 200)
check("upload→exec content match", "meta-capability test" in body)

# exec 查看部署目录
code, body = call_core("GET", "/api/exec",
    {"cmd": "ls /opt/app/deployments/", "token": t})
check("ls deployments", code == 200)
if code == 200:
    try:
        d = json.loads(body)
        print(f"    deployments: {d.get('stdout', '')[:200]}")
    except:
        print(f"    raw: {body[:200]}")

# exec 检查当前版本
code, body = call_core("GET", "/api/exec",
    {"cmd": "cat /opt/app/deployments/current/VERSION 2>/dev/null || echo NO_VERSION", "token": t})
check("read VERSION", code == 200)
if code == 200:
    try:
        d = json.loads(body)
        ver = d.get("stdout", "").strip()
        print(f"    current version: {ver}")
    except:
        pass

# ═══════════════════════════════════════════════════════════
print()
print("=" * 60)
print("  PHASE 3: 解耦验证 (obs 重启不影响 core)")
print("=" * 60)

code, _ = call_core("GET", "/api")
check("core online before obs stop", code == 200)

# 写停止脚本
stop_script = "#!/bin/bash\npkill -f observability_service.py\necho 'obs stopped'\n"
code, body = call_core("POST", "/api/upload",
    {"path": "/tmp/stop_obs.sh", "token": t},
    body=stop_script.encode())
code, body = call_core("GET", "/api/exec",
    {"cmd": "chmod +x /tmp/stop_obs.sh; bash /tmp/stop_obs.sh", "token": t})
check("stop obs via script", code == 200, f"code={code}")

time.sleep(2)

# core 仍在线
code, _ = call_core("GET", "/api")
check("core online after obs stopped", code == 200)

# 重启 obs
code, body = call_core("GET", "/api/exec",
    {"cmd": "bash /tmp/start_obs.sh", "token": t, "bg": "true"})
check("restart obs via core exec", code == 200, f"code={code}")

time.sleep(4)

code, body = call_obs("/api/health")
check("obs back online", code == 200, f"code={code}")

code, _ = call_core("GET", "/api")
check("core still online", code == 200)

# ═══════════════════════════════════════════════════════════
print()
print("=" * 60)
print("  PHASE 4: audit 审计日志验证")
print("=" * 60)

code, body = call_core("GET", "/api/audit", {"lines": "10", "token": t})
check("audit 200", code == 200)
if code == 200:
    try:
        audit = json.loads(body)
        count = audit.get("count", 0)
        check("audit has entries", count > 0, f"count={count}")
        actions = [e.get("action", "") for e in audit.get("entries", [])]
        has_exec_ok = "exec_ok" in actions
        has_exec_denied = "exec_denied" in actions
        has_upload = any("upload" in a for a in actions)
        check("audit records exec_ok", has_exec_ok, str(actions[:5]))
        check("audit records upload", has_upload, str(actions[:5]))
    except json.JSONDecodeError:
        check("audit parse", False, "json error")

# ═══════════════════════════════════════════════════════════
print()
print("=" * 60)
print("  PHASE 5: observability 可观测性验证")
print("=" * 60)

code, body = call_obs("/api/metrics?token=" + token("admin"))
check("prometheus metrics", code == 200, f"code={code}")
if code == 200:
    check("metrics has core_upload", "core_upload" in body)
    check("metrics has core_exec", "core_exec" in body)

code, body = call_obs("/api/ready")
check("readiness probe", code == 200, f"code={code}")

code, body = call_obs("/api/live")
check("liveness probe", code == 200, f"code={code}")

# ═══════════════════════════════════════════════════════════
print()
print("=" * 60)
print("  PHASE 6: log_service 备份 exec 通道")
print("=" * 60)

# log_service 使用不同的 secret
LOG_SECRETS = {"admin": "log-svc-admin-v4.10"}
def log_token():
    h = int(time.time()) // 3600
    return hashlib.sha256(f"{LOG_SECRETS['admin']}:{h}".encode()).hexdigest()[:16]

code, body = call_log(f"/api/exec?cmd=echo+hello_log&token={log_token()}")
if code != 200:
    # 尝试不带 token
    code2, body2 = call_log("/api/health")
    print(f"    log health: code={code2}")
    # 查 log_service 的 token 机制
    code3, body3 = call_core("GET", "/api/exec",
        {"cmd": "head -50 /opt/app/shared/log_service.py | grep -i secret", "token": t})
    print(f"    log_service secrets: {body3[:300]}")

code, body = call_log(f"/api/exec?cmd=echo+hello_log&token={log_token()}")
check("log exec via token", code == 200, f"code={code}")

# ═══════════════════════════════════════════════════════════
print()
print("=" * 60)
print("  PHASE 7: 三级权限验证 (core_service)")
print("=" * 60)

# read 权限: 只能执行 readonly 命令
code, body = call_core("GET", "/api/exec",
    {"cmd": "ls /tmp", "token": token("read")})
check("read exec ls (allowed)", code == 200, f"code={code}")

code, body = call_core("GET", "/api/exec",
    {"cmd": "cat /tmp/meta_test_v2.txt", "token": token("read")})
check("read exec cat (allowed)", code == 200, f"code={code}")

code, body = call_core("POST", "/api/upload",
    {"path": "/tmp/read_test.txt", "token": token("read")},
    body=b"read test")
check("read upload denied", code == 403, f"code={code}")

code, body = call_core("GET", "/api/exec",
    {"cmd": "bash -c echo test", "token": token("read")})
check("read exec bash denied", code == 403, f"code={code}")

# write 权限: 可以 upload + exec
code, body = call_core("POST", "/api/upload",
    {"path": "/tmp/write_test.txt", "token": token("write")},
    body=b"write test")
check("write upload ok", code == 200, f"code={code}")

code, body = call_core("GET", "/api/exec",
    {"cmd": "cat /tmp/write_test.txt", "token": token("write")})
check("write exec ok", code == 200, f"code={code}")

# ═══════════════════════════════════════════════════════════
print()
print("=" * 60)
total = PASS + FAIL
print(f"  RESULT: {PASS}/{total} PASS ({FAIL} FAIL)")
print("=" * 60)
