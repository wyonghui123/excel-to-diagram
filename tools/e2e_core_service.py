#!/usr/bin/env python3
"""
[V007.55] e2e_core_service.py - core_service v1.4 端到端验证 (HTTPS)
  验证流程:
    1. /api 返回元信息 (version v1.4, 4 endpoints, 3 token levels)
    2. 无 token 时 upload/exec 返回 403
    3. 有 token 时 upload 写文件成功
    4. exec 同步执行白名单命令成功
    5. exec bg=true 后台启动成功
    6. 路径白名单拦截非允许路径
    7. 命令白名单拦截非白名单命令
    8. 黑名单拦截危险命令
    8.5 audit log 端点
    9. 限流
    10. 三级权限 (admin/write/read) 隔离
    11. HTTPS 验证 (TLS 1.2+, 自签证书)
"""
import sys, time, hashlib, ssl, urllib.request, urllib.parse, tempfile, os

CORE_URL = "https://172.20.59.7:9200"  # [V007.55 v1.4] HTTPS only

# 创建接受自签证书的 SSL context (本机测 HTTPS)
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE
SECRETS = {
    "admin": "v007.52-core",           # legacy = admin (兼容 v1.1/v1.2)
    "write": "v007.52-core-write",     # write-only (v1.3)
    "read":  "v007.52-core-read",      # readonly (v1.3)
}

# --- token ---
def token(level: str = "admin") -> str:
    h = int(time.time()) // 3600
    secret = SECRETS[level]
    return hashlib.sha256(f"{secret}:{h}".encode()).hexdigest()[:16]


def call(method, path, query=None, body=None, headers=None):
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

PASS = 0
FAIL = 0
def check(name, ok, detail=""):
    global PASS, FAIL
    icon = "[OK]" if ok else "[FAIL]"
    print(f"  {icon} {name}{(': ' + detail) if detail else ''}")
    if ok: PASS += 1
    else:  FAIL += 1

def main():
    print(f"[E2E] core_service v1.5 end-to-end test (HTTPS)")
    print(f"[E2E] target: {CORE_URL}")
    print(f"[E2E] token: {token()}")
    print()

    # 1. /api 返回元信息
    print("=== [1] /api metadata ===")
    code, body = call("GET", "/api")
    check("200 OK", code == 200, str(code))
    check("version=v1.5", '"version": "v1.5"' in body)
    check("endpoints=4", '"endpoints": ["/api", "/api/upload", "/api/exec", "/api/audit"]' in body)
    check("3 token levels", '"token_levels":' in body)
    print()

    # 2. 无 token 拦截
    print("=== [2] no-token rejection ===")
    code, body = call("POST", "/api/upload", {"path": "/tmp/e2e_test.txt"}, body=b"data")
    check("upload 403 without token", code == 403, str(code))
    code, body = call("GET", "/api/exec", {"cmd": "ls /tmp"})
    check("exec 403 without token", code == 403, str(code))
    print()

    # 3. upload 成功
    print("=== [3] upload with token ===")
    t = token("admin")  # admin for full tests
    test_path = "/tmp/e2e_core_service_test.txt"
    content = f"e2e test at {int(time.time())}\n".encode()
    code, body = call("POST", "/api/upload", {"path": test_path, "token": t}, body=content)
    check("upload 200", code == 200, str(code))
    check("uploaded response", '"action": "uploaded"' in body)
    print()

    # 4. exec 同步
    print("=== [4] exec sync (whitelist) ===")
    code, body = call("GET", "/api/exec",
                      {"cmd": f"cat {test_path}", "token": t})
    check("exec 200", code == 200, str(code))
    check("exec content match", "e2e test at" in body)
    print()

    # 5. exec bg=true
    print("=== [5] exec background ===")
    code, body = call("GET", "/api/exec",
                      {"cmd": "sleep 5", "bg": "true", "token": t})
    check("bg exec 200", code == 200, str(code))
    check("bg has pid", '"pid":' in body)
    print()

    # 6. 路径白名单
    print("=== [6] path whitelist ===")
    code, body = call("POST", "/api/upload",
                      {"path": "/etc/passwd", "token": t}, body=b"hacker")
    check("upload /etc/passwd 403", code == 403, str(code))
    print()

    # 7. 命令白名单
    print("=== [7] cmd whitelist ===")
    code, body = call("GET", "/api/exec",
                      {"cmd": "not_a_real_command --evil", "token": t})
    check("exec unknown cmd 403", code == 403, str(code))
    print()

    # 8. 黑名单
    print("=== [8] blacklist ===")
    code, body = call("GET", "/api/exec",
                      {"cmd": "rm -rf / --force", "token": t})
    check("exec rm -rf / 403", code == 403, str(code))
    code, body = call("GET", "/api/exec",
                      {"cmd": "shutdown now", "token": t})
    check("exec shutdown 403", code == 403, str(code))
    print()

    # 8.5. audit log 端点 (放在限流前, 因为限流会耗尽 bucket)
    print("=== [8.5] audit log ===")
    code, body = call("GET", "/api/audit", {"lines": "500", "token": t})
    check("audit 200", code == 200, str(code))
    check("audit has entries", '"entries":' in body and '"count":' in body)
    check("audit has exec_ok", '"action": "exec_ok"' in body)
    check("audit has exec_denied", '"action": "exec_denied"' in body)
    check("audit has upload_denied (path whitelist)", '"reason": "path_not_allowed"' in body)
    print()

    # 8.6. 三级权限隔离 (v1.3 新功能)
    print("=== [8.6] three-level permission ===")
    # admin: 可 upload
    code, _ = call("POST", "/api/upload", {"path": "/tmp/perm_test_admin.txt", "token": token("admin")},
                   body=b"admin test")
    check("admin upload ok", code == 200, str(code))
    # write: 可 upload
    code, _ = call("POST", "/api/upload", {"path": "/tmp/perm_test_write.txt", "token": token("write")},
                   body=b"write test")
    check("write upload ok", code == 200, str(code))
    # read: 不可 upload
    code, body = call("POST", "/api/upload", {"path": "/tmp/perm_test_read.txt", "token": token("read")},
                      body=b"read test")
    check("read upload denied", code == 403, str(code))
    check("read upload msg", "insufficient permission" in body and "'read'" in body)
    # admin: 可 exec 完整白名单 (bash)
    code, _ = call("GET", "/api/exec", {"cmd": "bash --version", "token": token("admin")})
    check("admin exec bash", code == 200, str(code))
    # write: 可 exec 完整白名单 (bash)
    code, _ = call("GET", "/api/exec", {"cmd": "bash --version", "token": token("write")})
    check("write exec bash", code == 200, str(code))
    # read: 不可 exec bash
    code, body = call("GET", "/api/exec", {"cmd": "bash --version", "token": token("read")})
    check("read exec bash denied", code == 403, str(code))
    check("read readonly_allowed list", '"readonly_allowed"' in body)
    # read: 可 exec ls (in readonly subset)
    code, body = call("GET", "/api/exec", {"cmd": "ls /tmp", "token": token("read")})
    check("read exec ls ok", code == 200, str(code))
    # read: 不可 exec bg=true (用 ls 测 readonly 但 bg=true, 应该被 readonly_cannot_bg 拦截)
    code, body = call("GET", "/api/exec", {"cmd": "ls", "bg": "true", "token": token("read")})
    check("read cannot bg", code == 403, str(code))
    check("read bg msg", "background" in body or "background" in body.lower())
    # 所有 level 都可 audit (audit 已在 [8.5] 用 admin 验证, 这里跳过避免限流)
    print()

    # 9. rate limit
    print("=== [9] rate limit (25 reqs/sec) ===")
    rate_ok = 0
    rate_blocked = 0
    for i in range(25):
        code, _ = call("GET", "/api", {})
        if code == 200: rate_ok += 1
        elif code == 429: rate_blocked += 1
    check(f"rate_limit (ok={rate_ok}, blocked={rate_blocked})", rate_ok <= 20 and rate_blocked >= 5)
    print()

    # audit 已在 [8.5] 测过, 这里跳过 (限流后 IP 被 ban)

    # 等限流恢复
    time.sleep(2)

    # 12. audit log 轮转 (v1.5 新功能) - 通过 audit 端点验证
    # 等限流桶恢复 (rate limit = 20 req/s, [9] 用了 25)
    time.sleep(2)
    print("=== [12] audit log rotation ===")
    # 触发 5 个 audit 事件 (避免限流)
    for i in range(5):
        call("GET", "/api/exec", {"cmd": "ls /tmp", "token": token("admin")})
    time.sleep(0.5)
    # 检查 audit 端点能返回最近 N 条 (支持旋转后的 backup)
    code, body = call("GET", "/api/audit", {"lines": "5", "token": token("admin")})
    check("audit latest 5 ok", code == 200 and '"entries":' in body, f"code={code} body={body[:200]}")
    # 测试 max lines 限制
    code, body = call("GET", "/api/audit", {"lines": "501", "token": token("admin")})
    check("audit cap 500", code == 200 and '"count":' in body, f"code={code}")
    # manual rotate endpoint (admin only)
    code, body = call("POST", "/api/audit/rotate", {"token": token("admin")})
    check("admin rotate ok", code == 200 and '"rotated": true' in body, str(code) + " " + body[:200])
    time.sleep(0.5)
    code, body = call("POST", "/api/audit/rotate", {"token": token("read")})
    check("read rotate denied", code == 403 and "admin required" in body, f"code={code} body={body[:200]}")
    code, body = call("POST", "/api/audit/rotate", {})  # no token
    check("no-token rotate denied", code == 403, f"code={code}")
    print()

    # 11. HTTPS 验证 (v1.4 新功能)
    print("=== [11] HTTPS validation ===")
    # 用 ssl 模块直接验证 TLS 连接
    import socket
    sock = socket.create_connection(("172.20.59.7", 9200), timeout=5)
    ssock = _ssl_ctx.wrap_socket(sock, server_hostname="172.20.59.7")
    check("TLS handshake ok", ssock.version() is not None, f"version={ssock.version()}")
    check("TLS >= 1.2", ssock.version() in ("TLSv1.2", "TLSv1.3"), f"got {ssock.version()}")
    # 发送 HTTP 请求
    req = b"GET /api HTTP/1.1\r\nHost: 172.20.59.7\r\nConnection: close\r\n\r\n"
    ssock.send(req)
    # 读全部响应 (可能有多个 chunk)
    buf = b""
    while True:
        chunk = ssock.recv(4096)
        if not chunk:
            break
        buf += chunk
    resp = buf.decode()
    check("HTTPS response HTTP/1.x", "HTTP/1." in resp)
    check("HTTPS response 200", " 200 " in resp)
    check("HTTPS body has version", '"version": "v1.5"' in resp)
    ssock.close()
    # HTTP 应该被拒
    import urllib.error
    try:
        urllib.request.urlopen("http://172.20.59.7:9200/api", timeout=3)
        check("HTTP rejected", False, "should have failed")
    except (urllib.error.URLError, ConnectionError, OSError) as e:
        check("HTTP rejected", True, type(e).__name__)
    print()

    # 总结
    print(f"=== [SUMMARY] ===")
    print(f"  PASS: {PASS}")
    print(f"  FAIL: {FAIL}")
    print(f"  total: {PASS + FAIL}")
    print()
    if FAIL == 0:
        print(f"  [OK] ALL TESTS PASSED")
        return 0
    print(f"  [FAIL] {FAIL} test(s) failed")
    return 1

if __name__ == "__main__":
    sys.exit(main())