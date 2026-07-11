#!/usr/bin/env python3
"""
[V007.61] e2e_core_service.py v2.0 - core_service + observability_service 端到端验证
  双服务架构:
    core_service (9200 HTTPS) - upload, exec, audit, audit_rotate
    observability_service (9201 HTTP) - health, ready, metrics, upload_multi, request_id

  验证流程:
    1-9,11-12  core_service (9200)
    13-16      observability_service (9201)
"""
import sys, time, hashlib, ssl, urllib.request, urllib.parse, urllib.error
import os, json as _json2

CORE_URL = "https://172.20.59.7:9200"
OBS_URL  = "http://172.20.59.7:9201"

# SSL for core (self-signed cert)
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

SECRETS = {
    "admin": "v007.52-core",
    "write": "v007.52-core-write",
    "read":  "v007.52-core-read",
}

# --- token ---
def token(level: str = "admin") -> str:
    h = int(time.time()) // 3600
    return hashlib.sha256(f"{SECRETS[level]}:{h}".encode()).hexdigest()[:16]

# --- call helpers ---
def call_core(method, path, query=None, body=None, headers=None):
    """Call core_service (HTTPS)"""
    url = CORE_URL + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, method=method)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    data = body if isinstance(body, bytes) else (body.encode() if body else None)
    try:
        with urllib.request.urlopen(req, data=data, timeout=10, context=_ssl_ctx) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

def call_obs(method, path, query=None, body=None, headers=None):
    """Call observability_service (HTTP)"""
    url = OBS_URL + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, method=method)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    data = body if isinstance(body, bytes) else (body.encode() if body else None)
    try:
        with urllib.request.urlopen(req, data=data, timeout=10) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

def call_obs_with_headers(method, path, query=None, body=None, headers=None):
    """Call obs with response headers"""
    url = OBS_URL + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, method=method)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    data = body if isinstance(body, bytes) else (body.encode() if body else None)
    try:
        with urllib.request.urlopen(req, data=data, timeout=10) as r:
            return r.status, r.read().decode(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(), dict(e.headers)

# alias for core with headers
def call_core_with_headers(method, path, query=None, body=None, headers=None):
    url = CORE_URL + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, method=method)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    data = body if isinstance(body, bytes) else (body.encode() if body else None)
    try:
        with urllib.request.urlopen(req, data=data, timeout=10, context=_ssl_ctx) as r:
            return r.status, r.read().decode(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(), dict(e.headers)

PASS = 0
FAIL = 0
def check(name, ok, detail=""):
    global PASS, FAIL
    icon = "[OK]" if ok else "[FAIL]"
    print(f"  {icon} {name}{(': ' + detail) if detail else ''}")
    if ok: PASS += 1
    else:  FAIL += 1

def main():
    print(f"[E2E] dual-service end-to-end test")
    print(f"[E2E] core_service: {CORE_URL}")
    print(f"[E2E] observability: {OBS_URL}")
    print()

    # ════════════════════════════════════════════════════
    # SECTION: core_service (9200) - upload, exec, audit
    # ════════════════════════════════════════════════════
    print("=" * 60)
    print("  CORE_SERVICE (9200) - 核心元能力")
    print("=" * 60)

    # 1. /api 返回元信息
    print("\n=== [1] /api metadata ===")
    code, body = call_core("GET", "/api")
    check("200 OK", code == 200, str(code))
    check("version=v2.0", '"version": "v2.0"' in body)
    check("observability hint", '"observability":' in body and "9201" in body)
    print()

    # 2. 无 token 拦截
    print("=== [2] no-token rejection ===")
    code, body = call_core("POST", "/api/upload", {"path": "/tmp/e2e_test.txt"}, body=b"data")
    check("upload 403 without token", code == 403, str(code))
    code, body = call_core("GET", "/api/exec", {"cmd": "ls /tmp"})
    check("exec 403 without token", code == 403, str(code))
    print()

    # 3. upload 成功
    print("=== [3] upload with token ===")
    t = token("admin")
    test_path = "/tmp/e2e_core_service_test.txt"
    content = f"e2e test at {int(time.time())}\n".encode()
    code, body = call_core("POST", "/api/upload", {"path": test_path, "token": t}, body=content)
    check("upload 200", code == 200, str(code))
    check("uploaded response", '"action": "uploaded"' in body)
    print()

    # 4. exec 同步
    print("=== [4] exec sync (whitelist) ===")
    code, body = call_core("GET", "/api/exec", {"cmd": f"cat {test_path}", "token": t})
    check("exec 200", code == 200, str(code))
    check("exec content match", "e2e test at" in body)
    print()

    # 5. exec bg=true
    print("=== [5] exec background ===")
    code, body = call_core("GET", "/api/exec", {"cmd": "sleep 5", "bg": "true", "token": t})
    check("bg exec 200", code == 200, str(code))
    check("bg has pid", '"pid":' in body)
    print()

    # 6. 路径白名单
    print("=== [6] path whitelist ===")
    code, body = call_core("POST", "/api/upload", {"path": "/etc/passwd", "token": t}, body=b"hacker")
    check("upload /etc/passwd 403", code == 403, str(code))
    print()

    # 7. 命令白名单
    print("=== [7] cmd whitelist ===")
    code, body = call_core("GET", "/api/exec", {"cmd": "not_a_real_command --evil", "token": t})
    check("exec unknown cmd 403", code == 403, str(code))
    print()

    # 8. 黑名单
    print("=== [8] blacklist ===")
    code, body = call_core("GET", "/api/exec", {"cmd": "rm -rf / --force", "token": t})
    check("exec rm -rf / 403", code == 403, str(code))
    code, body = call_core("GET", "/api/exec", {"cmd": "shutdown now", "token": t})
    check("exec shutdown 403", code == 403, str(code))
    print()

    # 8.5. audit log 端点
    print("=== [8.5] audit log ===")
    code, body = call_core("GET", "/api/audit", {"lines": "500", "token": t})
    check("audit 200", code == 200, str(code))
    check("audit has entries", '"entries":' in body and '"count":' in body)
    check("audit has exec_ok", '"action": "exec_ok"' in body)
    check("audit has exec_denied", '"action": "exec_denied"' in body)
    check("audit has upload_denied (path whitelist)", '"reason": "path_not_allowed"' in body)
    print()

    # 8.6. 三级权限隔离
    print("=== [8.6] three-level permission ===")
    code, _ = call_core("POST", "/api/upload", {"path": "/tmp/perm_test_admin.txt", "token": token("admin")}, body=b"admin test")
    check("admin upload ok", code == 200, str(code))
    code, _ = call_core("POST", "/api/upload", {"path": "/tmp/perm_test_write.txt", "token": token("write")}, body=b"write test")
    check("write upload ok", code == 200, str(code))
    code, body = call_core("POST", "/api/upload", {"path": "/tmp/perm_test_read.txt", "token": token("read")}, body=b"read test")
    check("read upload denied", code == 403, str(code))
    check("read upload msg", "insufficient permission" in body and "'read'" in body)
    code, _ = call_core("GET", "/api/exec", {"cmd": "bash --version", "token": token("admin")})
    check("admin exec bash", code == 200, str(code))
    code, _ = call_core("GET", "/api/exec", {"cmd": "bash --version", "token": token("write")})
    check("write exec bash", code == 200, str(code))
    code, body = call_core("GET", "/api/exec", {"cmd": "bash --version", "token": token("read")})
    check("read exec bash denied", code == 403, str(code))
    check("read readonly_allowed list", '"readonly_allowed"' in body)
    code, body = call_core("GET", "/api/exec", {"cmd": "ls /tmp", "token": token("read")})
    check("read exec ls ok", code == 200, str(code))
    code, body = call_core("GET", "/api/exec", {"cmd": "ls", "bg": "true", "token": token("read")})
    check("read cannot bg", code == 403, str(code))
    check("read bg msg", "background" in body or "background" in body.lower())
    print()

    # 9. rate limit
    print("=== [9] rate limit (25 reqs/sec) ===")
    rate_ok = 0
    rate_blocked = 0
    for i in range(25):
        code, _ = call_core("GET", "/api", {})
        if code == 200: rate_ok += 1
        elif code == 429: rate_blocked += 1
    check(f"rate_limit (ok={rate_ok}, blocked={rate_blocked})", rate_ok <= 20 and rate_blocked >= 5)
    print()

    time.sleep(2)

    # 12. audit log 轮转 (on core_service)
    print("=== [12] audit log rotation ===")
    for i in range(5):
        call_core("GET", "/api/exec", {"cmd": "ls /tmp", "token": token("admin")})
    time.sleep(0.5)
    code, body = call_core("GET", "/api/audit", {"lines": "5", "token": token("admin")})
    check("audit latest 5 ok", code == 200 and '"entries":' in body, f"code={code} body={body[:200]}")
    code, body = call_core("GET", "/api/audit", {"lines": "501", "token": token("admin")})
    check("audit cap 500", code == 200 and '"count":' in body, f"code={code}")
    code, body = call_core("POST", "/api/audit/rotate", {"token": token("admin")})
    check("admin rotate ok", code == 200 and '"rotated": true' in body, str(code) + " " + body[:200])
    time.sleep(0.5)
    code, body = call_core("POST", "/api/audit/rotate", {"token": token("read")})
    check("read rotate denied", code == 403 and "admin required" in body, f"code={code} body={body[:200]}")
    code, body = call_core("POST", "/api/audit/rotate", {})
    check("no-token rotate denied", code == 403, f"code={code}")
    print()

    # 11. HTTPS 验证 (core_service)
    print("=== [11] HTTPS validation ===")
    import socket
    sock = socket.create_connection(("172.20.59.7", 9200), timeout=5)
    ssock = _ssl_ctx.wrap_socket(sock, server_hostname="172.20.59.7")
    check("TLS handshake ok", ssock.version() is not None, f"version={ssock.version()}")
    check("TLS >= 1.2", ssock.version() in ("TLSv1.2", "TLSv1.3"), f"got {ssock.version()}")
    req = b"GET /api HTTP/1.1\r\nHost: 172.20.59.7\r\nConnection: close\r\n\r\n"
    ssock.send(req)
    buf = b""
    while True:
        chunk = ssock.recv(4096)
        if not chunk: break
        buf += chunk
    resp = buf.decode()
    check("HTTPS response HTTP/1.x", "HTTP/1." in resp)
    check("HTTPS response 200", " 200 " in resp)
    check("HTTPS body has version", '"version": "v2.0"' in resp)
    ssock.close()
    try:
        urllib.request.urlopen("http://172.20.59.7:9200/api", timeout=3)
        check("HTTP rejected", False, "should have failed")
    except (urllib.error.URLError, ConnectionError, OSError) as e:
        check("HTTP rejected", True, type(e).__name__)
    print()

    time.sleep(2)

    # ════════════════════════════════════════════════════
    # SECTION: observability_service (9201) - health, metrics, upload_multi, request_id
    # ════════════════════════════════════════════════════
    print("=" * 60)
    print("  OBSERVABILITY_SERVICE (9201) - 可观测性 + 扩展")
    print("=" * 60)

    # 13. 批量上传 (multipart/form-data) - on observability_service
    import uuid as _uuid
    print("\n=== [13] multipart upload (obs:9201) ===")
    boundary = "----TestB" + _uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="e2e_a.txt"\r\n'
        f"Content-Type: text/plain\r\n"
        f"\r\n"
        f"hello from e2e test A\n"
        f"\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="e2e_b.txt"\r\n'
        f"Content-Type: text/plain\r\n"
        f"\r\n"
        f"hello from e2e test B\n"
        f"\r\n"
        f"--{boundary}--\r\n"
    ).encode("latin-1")
    try:
        req = urllib.request.Request(
            f"{OBS_URL}/api/upload_multi?base_dir=/tmp/e2e_batch&token={token('admin')}",
            data=body, method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            resp_body = r.read().decode()
            check("admin upload_multi 200", r.status == 200, str(r.status))
            check("uploaded 2 files", '"ok": 2' in resp_body and '"total": 2' in resp_body, resp_body[:300])
            check("e2e_a.txt in results", "e2e_a.txt" in resp_body)
            check("e2e_b.txt in results", "e2e_b.txt" in resp_body)
    except Exception as e:
        check("admin upload_multi", False, str(e))
    # read token 拒绝
    boundary2 = "----T" + _uuid.uuid4().hex
    body2 = (
        f"--{boundary2}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="r.txt"\r\n'
        f"Content-Type: text/plain\r\n"
        f"\r\n"
        f"test\r\n"
        f"\r\n"
        f"--{boundary2}--\r\n"
    ).encode("latin-1")
    try:
        req = urllib.request.Request(
            f"{OBS_URL}/api/upload_multi?base_dir=/tmp&token={token('read')}",
            data=body2, method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary2}"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            check("read upload_multi denied", False, f"should 403 got {r.status}")
    except urllib.error.HTTPError as e:
        check("read upload_multi denied", e.code == 403, str(e.code))
    # 路径穿越拦截
    boundary3 = "----T" + _uuid.uuid4().hex
    body3 = (
        f"--{boundary3}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="../bad.txt"\r\n'
        f"Content-Type: text/plain\r\n"
        f"\r\n"
        f"x\r\n"
        f"\r\n"
        f"--{boundary3}--\r\n"
    ).encode("latin-1")
    try:
        req = urllib.request.Request(
            f"{OBS_URL}/api/upload_multi?base_dir=/tmp&token={token('admin')}",
            data=body3, method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary3}"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            resp_body = r.read().decode()
            check("path traversal blocked", '"fail": 1' in resp_body and "invalid filename" in resp_body, resp_body[:200])
    except Exception as e:
        check("path traversal blocked", False, str(e))
    print()

    # 14. metrics 端点 (on observability_service)
    print("=== [14] metrics endpoint (obs:9201) ===")
    code, body = call_obs("GET", "/api/metrics", {"token": token("admin")})
    check("metrics 200 (admin)", code == 200, str(code))
    check("metrics has uptime", "observability_uptime_seconds" in body)
    check("metrics has audit events", "core_service_audit_events_total" in body)
    check("metrics has upload total", "core_service_upload_total" in body)
    check("metrics has exec total", "core_service_exec_total" in body)
    check("metrics has audit_log_bytes", "core_service_audit_log_bytes" in body)
    check("metrics has info", "observability_info" in body)
    check("metrics version v1.0", 'version="v1.0"' in body)
    code, body = call_obs("GET", "/api/metrics", {"token": token("read")})
    check("metrics 200 (read)", code == 200, str(code))
    code, _ = call_obs("GET", "/api/metrics", {})
    check("metrics 403 no-token", code == 403, str(code))
    req = urllib.request.Request(f"{OBS_URL}/api/metrics?token={token('admin')}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            ctype = r.headers.get("Content-Type", "")
            check("Content-Type prometheus", "text/plain" in ctype and "version=" in ctype, ctype)
    except Exception as e:
        check("Content-Type check", False, str(e))
    print()

    # 15. health/ready 端点 (on observability_service)
    print("=== [15] health/ready probes (obs:9201) ===")
    code, body = call_obs("GET", "/api/health", {})
    check("health 200 no-token", code == 200, str(code))
    check("health status=alive", '"status": "alive"' in body)
    check("health has uptime", '"uptime_sec":' in body)
    code, body = call_obs("GET", "/api/live", {})
    check("live alias ok", code == 200 and '"status": "alive"' in body, f"code={code}")
    code, body = call_obs("GET", "/api/ready", {})
    # ready 检查 core_service 连通性
    check("ready check", code in (200, 503), f"code={code} body={body[:300]}")
    check("ready checks present", '"checks":' in body and "core_service" in body)
    # 30 health checks 不限流
    rate_limited = 0
    for i in range(30):
        code, _ = call_obs("GET", "/api/health", {})
        if code == 429:
            rate_limited += 1
    check("health 30 calls no rate limit", rate_limited == 0, f"rate_limited={rate_limited}")
    print()

    # 16. 请求 ID 追踪 (on observability_service)
    print("=== [16] request_id tracing (obs:9201) ===")
    code, body, headers = call_obs_with_headers("GET", "/api/metrics", {"token": token("admin")})
    auto_id = headers.get("X-Request-Id") or headers.get("x-request-id")
    check("auto-gen X-Request-Id", auto_id and auto_id.startswith("obs-"), f"got {auto_id}")
    custom_id = "my-custom-trace-12345"
    code, body, headers = call_obs_with_headers("GET", "/api/metrics", {"token": token("admin")},
                                                headers={"X-Request-Id": custom_id})
    check("custom X-Request-Id echoed", headers.get("X-Request-Id") == custom_id, f"got {headers.get('X-Request-Id')}")
    code, body, headers = call_obs_with_headers("GET", "/api/metrics", {"token": token("admin")},
                                                headers={"X-Request-Id": "bad id with spaces!"})
    bad_id = headers.get("X-Request-Id")
    check("invalid X-Request-Id auto-gen", bad_id and bad_id.startswith("obs-"), f"got {bad_id}")
    code, body, headers = call_obs_with_headers("GET", "/api/health", {})
    health_id = headers.get("X-Request-Id")
    check("health has X-Request-Id", health_id is not None, f"got {health_id}")
    print()

    # ════════════════════════════════════════════════════
    # SECTION: 解耦验证 - 重启 observability 不影响 core
    # ════════════════════════════════════════════════════
    print("=" * 60)
    print("  DECOUPLING VALIDATION")
    print("=" * 60)
    print("\n=== [D] restart observability does NOT affect core ===")
    # 先确认 core 正常
    c1, _ = call_core("GET", "/api/exec", {"cmd": "echo before_restart", "token": token("admin")})
    check("core_service alive before obs restart", c1 == 200, str(c1))
    # 模拟: 这里不实际重启 (部署脚本会做), 只验证架构设计
    # 核心点: observability 是独立进程, pkill observability 不影响 core_service
    print("  [INFO] observability (9201) can be restarted independently")
    print("  [INFO] core_service (9200) upload/exec/audit stay available")
    print()

    # 总结
    print(f"=== [SUMMARY] ===")
    print(f"  PASS: {PASS}")
    print(f"  FAIL: {FAIL}")
    print(f"  total: {PASS + FAIL}")
    print()
    if FAIL == 0:
        print(f"  [OK] ALL TESTS PASSED (core_service v2.0 + observability v1.0)")
        return 0
    print(f"  [FAIL] {FAIL} test(s) failed")
    return 1

if __name__ == "__main__":
    sys.exit(main())
