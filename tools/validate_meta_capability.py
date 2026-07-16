#!/usr/bin/env python3
"""
元能力基础设施实战验证 - 通过 core_service upload/exec 部署运营 yonaa
验证闭环: 元能力服务 → upload 部署包 → exec 解压/迁移/重启 → 健康检查
"""
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
print("  PHASE 1: 元能力服务状态验证")
print("=" * 60)

code, body = call_core("GET", "/api")
check("core_service v2.0", code == 200 and "v2.0" in body, f"code={code}")
check("core endpoints", '"/api/upload"' in body and '"/api/exec"' in body)

code, body = call_obs("/api/health")
check("obs_service health", code == 200 and "alive" in body, f"code={code}")

code, body = call_obs("/api/ready")
check("obs_service ready", code == 200, f"code={code}")

code, body = call_log("/api/health")
check("log_service health", code == 200 and "ok" in body, f"code={code}")

# ═══════════════════════════════════════════════════════════
print()
print("=" * 60)
print("  PHASE 2: core_service 元能力功能验证")
print("=" * 60)

# upload + exec 闭环
test_content = f"meta-capability test at {int(time.time())}\n".encode()
code, body = call_core("POST", "/api/upload", {"path": "/tmp/meta_test.txt", "token": t}, body=test_content)
check("upload 200", code == 200, f"code={code}")

code, body = call_core("GET", "/api/exec", {"cmd": "cat /tmp/meta_test.txt", "token": t})
check("exec cat 200", code == 200)
check("upload→exec content match", "meta-capability test" in body)

# 查看当前部署状态
code, body = call_core("GET", "/api/exec", {"cmd": "ls -la /opt/app/deployments/current/ 2>/dev/null | head -5", "token": t})
check("ls current deployment", code == 200)
print(f"    current: {body[:200]}")

code, body = call_core("GET", "/api/exec", {"cmd": "cat /opt/app/deployments/current/MANIFEST 2>/dev/null || echo NO_MANIFEST", "token": t})
check("read MANIFEST", code == 200)
if "NO_MANIFEST" not in body:
    print(f"    MANIFEST: {body[:300]}")

# 查看 backend 进程
code, body = call_core("GET", "/api/exec", {"cmd": "ps aux | grep -E 'unified_server|waitress' | grep -v grep | head -3", "token": t})
check("backend process check", code == 200)
print(f"    backend: {body[:200]}")

# 查看前端进程
code, body = call_core("GET", "/api/exec", {"cmd": "ps aux | grep -E 'nginx|http-server' | grep -v grep | head -3", "token": t})
check("frontend process check", code == 200)
print(f"    frontend: {body[:200]}")

# ═══════════════════════════════════════════════════════════
print()
print("=" * 60)
print("  PHASE 3: 解耦验证 (obs 重启不影响 core)")
print("=" * 60)

code, _ = call_core("GET", "/api")
check("core online before obs restart", code == 200)

# 通过 core exec 重启 obs
code, body = call_core("GET", "/api/exec", {
    "cmd": "pkill -f observability_service.py",
    "token": t
})
check("stop obs via exec", code == 200, f"code={code}")
time.sleep(2)

# core 仍在线
code, _ = call_core("GET", "/api")
check("core online after obs stopped", code == 200)

# obs 已下线
code, _ = call_obs("/api/health")
check("obs down confirmed", code == 200, f"still up? code={code}")

# 通过 core exec 重启 obs
code, body = call_core("GET", "/api/exec", {
    "cmd": "cd /opt/app/shared && nohup /opt/miniconda3-py39/bin/python observability_service.py > /var/log/observability_service.log 2>&1 &",
    "token": t, "bg": "true"
})
check("restart obs via core exec", code == 200)
time.sleep(3)

code, body = call_obs("/api/health")
check("obs back online", code == 200, f"code={code}")
code, _ = call_core("GET", "/api")
check("core still online", code == 200)

# ═══════════════════════════════════════════════════════════
print()
print("=" * 60)
print("  PHASE 4: audit 审计日志验证")
print("=" * 60)

code, body = call_core("GET", "/api/audit", {"lines": "5", "token": t})
check("audit 200", code == 200)
if code == 200:
    try:
        audit = json.loads(body)
        check("audit has entries", audit.get("count", 0) > 0, f"count={audit.get('count', 0)}")
        # 检查审计中是否记录了我们的操作
        actions = [e.get("action", "") for e in audit.get("entries", [])]
        has_exec = any("exec" in a for a in actions)
        has_upload = any("upload" in a for a in actions)
        check("audit records exec", has_exec, str(actions[:5]))
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
    has_core_upload = "core_upload" in body
    has_core_exec = "core_exec" in body
    check("metrics has core_upload", has_core_upload)
    check("metrics has core_exec", has_core_exec)

code, body = call_obs("/api/ready")
check("readiness probe", code == 200, f"code={code}")

# ═══════════════════════════════════════════════════════════
print()
print("=" * 60)
print("  PHASE 6: log_service 备份 exec 通道验证")
print("=" * 60)

code, body = call_log("/api/exec?cmd=echo+log_service_exec_test&token=" + token("admin"))
check("log exec 200", code == 200, f"code={code}")
if code == 200:
    check("log exec output", "log_service_exec_test" in body, body[:100])

# ═══════════════════════════════════════════════════════════
print()
print("=" * 60)
total = PASS + FAIL
print(f"  RESULT: {PASS}/{total} PASS ({FAIL} FAIL)")
print("=" * 60)
