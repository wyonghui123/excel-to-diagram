#!/usr/bin/env python3
"""
[V007.52] e2e_core_service.py - core_service v1.1 端到端验证
  验证流程:
    1. /api 返回元信息 (version v1.1, 3 endpoints)
    2. 无 token 时 upload/exec 返回 403
    3. 有 token 时 upload 写文件成功
    4. exec 同步执行白名单命令成功
    5. exec bg=true 后台启动成功
    6. 路径白名单拦截非允许路径
    7. 命令白名单拦截非白名单命令
    8. 黑名单拦截危险命令
"""
import sys, time, hashlib, urllib.request, urllib.parse, tempfile, os

CORE_URL = "http://172.20.59.7:9200"
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
        with urllib.request.urlopen(req, data=data, timeout=10) as r:
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
    print(f"[E2E] core_service v1.3 end-to-end test")
    print(f"[E2E] target: {CORE_URL}")
    print(f"[E2E] token: {token()}")
    print()

    # 1. /api 返回元信息
    print("=== [1] /api metadata ===")
    code, body = call("GET", "/api")
    check("200 OK", code == 200, str(code))
    check("version=v1.3", '"version": "v1.3"' in body)
    check("endpoints=4", '"endpoints": ["/api", "/api/upload", "/api/exec", "/api/audit"]' in body)
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
    code, body = call("GET", "/api/audit", {"lines": "30", "token": t})
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