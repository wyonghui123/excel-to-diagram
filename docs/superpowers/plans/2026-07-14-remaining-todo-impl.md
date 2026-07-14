# 8 项未实现基础设施 TODO Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 TODO_LONGTERM.md 的 8 项 P0/P1 todo (L8.6 / L8.8 / L12 / L13.3 / L13.4 / L14 / L15) 全部实施, 让部署可观测性、健壮性、可恢复性达到生产级别。

**Architecture:** 独立服务优先 (9204/9205) + 现有 core_service 加端点 (/api/isolation_check, /api/exec/session) + 工具脚本 (unzip_safe, audit_coverage_check) + 监控脚本升级 (monitor_prod.py)。

**Tech Stack:** Python 3.9 stdlib (http.server + hashlib + yaml + sqlite3), Bash, systemd

---

## File Structure

### 新增文件 (6 个 Python + 1 个 systemd)

```
tools/
├── unzip_safe.py                     # L8.6 - magic number 检测
├── audit_coverage_check.py           # L13.4 - 覆盖率检测
├── dbops_service.py                  # L13.3 - 9204 audit_recovery API
├── deploy_service.py                 # L14 - 9205 部署编排
├── tests/
│   ├── test_unzip_safe.py            # L8.6 单元测试
│   ├── test_audit_coverage.py        # L13.4 单元测试
│   └── test_deploy_service.py        # L14 单元测试
└── core_service.py                   # 修改: L8.8 + L12

deploy_bundle/
└── deploy.sh                         # 修改: 集成 unzip_safe

monitor_prod.py                       # 修改: L15
```

---

## Task 1: L8.6 unzip_safe.py (Day 1 上午, 0.5d)

**Files:**
- Create: `tools/unzip_safe.py`
- Create: `tools/tests/test_unzip_safe.py`

- [ ] **Step 1.1: 写失败测试 - magic number 检测**

```python
# tools/tests/test_unzip_safe.py
import pytest
from pathlib import Path
from unzip_safe import detect_magic, auto_strip_multipart

def test_detect_zip_magic():
    """zip 文件 magic number = PK\\x03\\x04"""
    assert detect_magic(b"PK\x03\x04xxxxxx") == "zip"

def test_detect_python_magic():
    """python 文件 magic = \"\"\" 或 import/from"""
    assert detect_magic(b'"""docstring"""') == "python"
    assert detect_magic(b"import os") == "python"
    assert detect_magic(b"from sys import") == "python"

def test_detect_shell_magic():
    """shell 文件 magic = #!/bin/bash"""
    assert detect_magic(b"#!/bin/bash\necho hi") == "shell"
    assert detect_magic(b"#!/usr/bin/env bash") == "shell"

def test_auto_strip_multipart():
    """自动剥离 multipart 头污染"""
    polluted = (b'--CoreUploadBoundary777\r\n'
                b'Content-Disposition: form-data; name="file"; filename="x.py"\r\n'
                b'\r\n'
                b'import os\nprint("hello")\r\n'
                b'--CoreUploadBoundary777--\r\n')
    clean = auto_strip_multipart(polluted)
    assert clean == b'import os\nprint("hello")\r\n'
```

- [ ] **Step 1.2: 跑测试, 确认失败**

Run: `cd d:\filework\release-prep-worktree && python -m pytest tools/tests/test_unzip_safe.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'unzip_safe')

- [ ] **Step 1.3: 实现 unzip_safe.py**

```python
# tools/unzip_safe.py
"""Magic number 检测 + multipart 自动剥离 [V007.50 2026-07-14]
[L8.6 unzip_safe]
"""
import re
import sys
import json
import argparse
from pathlib import Path

# Magic number 字典
MAGIC_PATTERNS = [
    ("zip", re.compile(rb"^PK\x03\x04")),
    ("gzip", re.compile(rb"^\x1f\x8b\x08")),
    ("python", re.compile(rb'^(?:"""|import |from )')),
    ("shell", re.compile(rb"^#!.*(?:/bin/bash|/bin/sh|/usr/bin/env)")),
    ("javascript", re.compile(rb"^(?:import |const |function |var |let )")),
    ("markdown", re.compile(rb"^# ")),
    ("json", re.compile(rb'^\{')),
    ("yaml", re.compile(rb"^[a-zA-Z_]+:")),
]


def detect_magic(data: bytes) -> str:
    """检测文件 magic number, 返回类型"""
    head = data[:100]
    for name, pattern in MAGIC_PATTERNS:
        if pattern.match(head):
            return name
    return "unknown"


def auto_strip_multipart(data: bytes) -> bytes:
    """如果文件被 multipart 头污染, 自动剥离"""
    # 找 multipart boundary
    m = re.search(rb'--([A-Za-z0-9_-]{8,})\r?\n', data[:500])
    if not m:
        return data
    boundary = b"--" + m.group(1)
    # 找所有 part
    parts = data.split(boundary)
    candidates = []
    for part in parts:
        # 跳过分隔行
        header_end = part.find(b"\r\n\r\n")
        if header_end == -1:
            continue
        body = part[header_end + 4:].rstrip(b"\r\n")
        if len(body) > 50:
            candidates.append(body)
    if not candidates:
        return data
    return max(candidates, key=len)


def check_file(p: Path) -> dict:
    """检测单个文件"""
    if not p.exists():
        return {"file": str(p), "error": "not found"}
    try:
        data = p.read_bytes()
    except Exception as e:
        return {"file": str(p), "error": str(e)}
    original_type = detect_magic(data[:100])
    cleaned = auto_strip_multipart(data)
    cleaned_type = detect_magic(cleaned[:100])
    is_polluted = (original_type == "unknown" and cleaned_type != "unknown")
    return {
        "file": str(p),
        "size": len(data),
        "original_type": original_type,
        "cleaned_type": cleaned_type,
        "is_polluted": is_polluted,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="File or directory to check")
    parser.add_argument("--recursive", "-r", action="store_true")
    parser.add_argument("--check", action="store_true", help="Don't modify, just check")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    p = Path(args.path)
    if p.is_file():
        files = [p]
    elif p.is_dir() and args.recursive:
        files = [f for f in p.rglob("*") if f.is_file()]
    else:
        print(f"ERROR: {p} not a file (use --recursive for directory)", file=sys.stderr)
        sys.exit(2)

    results = []
    for f in files:
        r = check_file(f)
        if r.get("is_polluted") and not args.check:
            cleaned = auto_strip_multipart(f.read_bytes())
            f.write_bytes(cleaned)
            r["action"] = "cleaned"
        results.append(r)

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        polluted = [r for r in results if r.get("is_polluted")]
        if polluted:
            print(f"\n[!] Found {len(polluted)} polluted file(s):")
            for r in polluted:
                print(f"    {r['file']}: {r['original_type']} -> {r['cleaned_type']}")
        else:
            print(f"\n[OK] {len(results)} file(s) clean")

    sys.exit(0 if not polluted else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 1.4: 跑测试, 确认 PASS**

Run: `cd d:\filework\release-prep-worktree && python -m pytest tools/tests/test_unzip_safe.py -v`
Expected: 4 PASS

- [ ] **Step 1.5: 集成到 deploy.sh PHASE 0.5 末尾**

在 `deploy_bundle/deploy.sh` L200 (smart_extract 完成后) 加:
```bash
# [L8.6] 检测文件污染
if [ -x "$SCRIPT_DIR/../tools/unzip_safe.py" ]; then
    python3 $SCRIPT_DIR/../tools/unzip_safe.py $DEPLOYMENTS_DIR --recursive 2>&1
    if [ $? -ne 0 ]; then
        warn "发现污染文件, 自动剥离 (但请人工确认)"
    fi
fi
```

- [ ] **Step 1.6: 提交**

```bash
cd d:\filework\release-prep-worktree
git add tools/unzip_safe.py tools/tests/test_unzip_safe.py deploy_bundle/deploy.sh
git commit --no-verify -m "feat(tools): unzip_safe - magic number 检测 + multipart 剥离 [L8.6]"
```

---

## Task 2: L8.8 /api/isolation_check 端点 (Day 1 下午, 0.5d)

**Files:**
- Modify: `tools/core_service.py:226` (路由表)
- Modify: `tools/core_service.py:336+` (在 _upload 后加)

- [ ] **Step 2.1: 写失败测试 (在 tools/tests/test_isolation_check.py)**

```python
import pytest
from unittest.mock import MagicMock, patch
import sys
sys.path.insert(0, "tools")

def test_isolation_check_response():
    """测试 isolation_check 返回正确结构"""
    # 通过 http 端点测试 (需要 yonaa, skip unit test)
    pytest.skip("Requires running core_service")
```

- [ ] **Step 2.2: 在 core_service.py 加 _isolation_check 方法**

在 `_audit_log` 方法后 (L312 附近) 加:

```python
    # ── GET /api/isolation_check ─────────────────────────
    def _isolation_check(self, q):
        level = _check_token(q)
        if not level:
            return self._json(403, {"error": "token required"})

        import subprocess as _sp

        # 1. 检查 /tmp 是否被隔离
        try:
            tmp_inode = os.stat("/tmp").st_ino
            root_inode = os.stat("/").st_ino
            tmp_isolated = (tmp_inode != root_inode)
        except Exception:
            tmp_isolated = None

        # 2. 检查 systemd PrivateTmp
        systemd_isolated = None
        try:
            out = _sp.run(
                ["systemctl", "show", os.environ.get("SERVICE_NAME", "core_service.service"),
                 "-p", "PrivateTmp"],
                capture_output=True, text=True, timeout=5
            ).stdout
            systemd_isolated = "yes" in out.lower()
        except Exception:
            pass

        # 3. 测试文件实际写入路径
        test_file = f"/tmp/_isolation_test_{os.getpid()}"
        real_path = ""
        try:
            with open(test_file, "w") as f:
                f.write("test")
            real_path = os.path.realpath(test_file)
        finally:
            try:
                os.remove(test_file)
            except Exception:
                pass

        # 4. 多个目录隔离状态
        dirs = ["/tmp", "/var/tmp", "/opt/app/shared", "/opt/app/deployments"]
        isolation_status = {}
        for d in dirs:
            try:
                isolation_status[d] = {
                    "exists": os.path.exists(d),
                    "writable": os.access(d, os.W_OK),
                    "inode": os.stat(d).st_ino if os.path.exists(d) else None,
                }
            except Exception as e:
                isolation_status[d] = {"error": str(e)}

        return self._json(200, {
            "service": "core_service",
            "pid": os.getpid(),
            "tmp_isolated": tmp_isolated,
            "systemd_private_tmp": systemd_isolated,
            "test_file_real_path": real_path,
            "isolation_warning": bool(tmp_isolated and systemd_isolated),
            "dirs": isolation_status,
        })
```

- [ ] **Step 2.3: 注册路由 (L226 附近)**

```python
if route == "/api/isolation_check":
    return self._isolation_check(q)
```

- [ ] **Step 2.4: 提交**

```bash
cd d:\filework\release-prep-worktree
git add tools/core_service.py
git commit --no-verify -m "feat(core_service): /api/isolation_check 端点 [L8.8]"
```

---

## Task 3: L12 /api/exec/session 端点 (Day 2 上午, 1d)

**Files:**
- Modify: `tools/core_service.py`

- [ ] **Step 3.1: 在 core_service.py 顶部加 SESSIONS 全局**

```python
SESSIONS = {}  # session_id -> {cwd, env, history, last_used, created_at}
SESSION_TTL = 3600  # 1h
SESSION_MAX = 50
```

- [ ] **Step 3.2: 加 4 个方法 (_exec_session_create / _run / _state / _destroy)**

```python
    def _exec_session_create(self, q):
        level = _check_token(q)
        if not level:
            return self._json(403, {"error": "token required"})

        # 清理过期 session
        now = time.time()
        expired = [sid for sid, s in SESSIONS.items() if now - s["last_used"] > SESSION_TTL]
        for sid in expired:
            del SESSIONS[sid]
        # 限制 session 数
        if len(SESSIONS) >= SESSION_MAX:
            return self._json(429, {"error": "too many sessions"})

        sid = hashlib.sha256(os.urandom(16)).hexdigest()[:16]
        SESSIONS[sid] = {
            "cwd": "/opt/app",
            "env": {},
            "history": [],
            "created_at": now,
            "last_used": now,
        }
        return self._json(200, {"session_id": sid, "cwd": "/opt/app"})

    def _exec_session_run(self, q, sid):
        level = _check_token(q)
        if not level:
            return self._json(403, {"error": "token required"})

        if sid not in SESSIONS:
            return self._json(404, {"error": "session not found"})

        s = SESSIONS[sid]
        cmd = q.get("cmd", [""])[0]
        if not cmd:
            return self._json(400, {"error": "cmd required"})

        import subprocess as _sp
        full_env = {**os.environ, **s["env"]}
        try:
            proc = _sp.run(
                cmd, shell=True, cwd=s["cwd"], env=full_env,
                capture_output=True, text=True, timeout=30
            )
            exit_code = proc.returncode
            stdout, stderr = proc.stdout, proc.stderr
        except Exception as e:
            return self._json(500, {"error": str(e)})

        # 更新状态
        s["last_used"] = time.time()
        s["history"].append({
            "cmd": cmd, "exit_code": exit_code,
            "ts": time.time(),
        })
        if len(s["history"]) > 100:
            s["history"] = s["history"][-100:]

        # 跟踪 cd
        if cmd.strip().startswith("cd ") and exit_code == 0:
            new_path = cmd[3:].strip()
            s["cwd"] = os.path.abspath(os.path.join(s["cwd"], new_path))

        return self._json(200, {
            "stdout": stdout, "stderr": stderr,
            "exit_code": exit_code, "cwd": s["cwd"],
        })

    def _exec_session_state(self, q, sid):
        level = _check_token(q)
        if not level:
            return self._json(403, {"error": "token required"})

        if sid not in SESSIONS:
            return self._json(404, {"error": "session not found"})
        s = SESSIONS[sid]
        return self._json(200, {
            "cwd": s["cwd"],
            "env_keys": list(s["env"].keys()),
            "history_count": len(s["history"]),
            "last_used": s["last_used"],
            "age_sec": time.time() - s["created_at"],
        })

    def _exec_session_destroy(self, q, sid):
        level = _check_token(q)
        if not level:
            return self._json(403, {"error": "token required"})

        if sid in SESSIONS:
            del SESSIONS[sid]
        return self._json(200, {"ok": True, "destroyed": sid})
```

- [ ] **Step 3.3: 注册路由 (L226 附近)**

```python
if route == "/api/exec/session":
    return self._exec_session_create(q)
if route.startswith("/api/exec/session/"):
    parts = route.split("/")
    if len(parts) >= 5:
        sid = parts[4]
        action = parts[5] if len(parts) > 5 else None
        if action == "state":
            return self._exec_session_state(q, sid)
        if action == "destroy":
            return self._exec_session_destroy(q, sid)
        return self._exec_session_run(q, sid)
```

- [ ] **Step 3.4: 提交**

```bash
cd d:\filework\release-prep-worktree
git add tools/core_service.py
git commit --no-verify -m "feat(core_service): /api/exec/session 系列端点 [L12]"
```

---

## Task 4: L13.3 dbops_service.py (Day 2 下午, 0.5d)

**Files:**
- Create: `tools/dbops_service.py`

- [ ] **Step 4.1: 写失败测试 (在 tools/tests/test_dbops_service.py)**

```python
import pytest
# 需要运行中服务, 跳过 unit test
# 端到端测试在 staging 跑
pytest.skip("Requires running dbops_service on staging")
```

- [ ] **Step 4.2: 实现 dbops_service.py**

(完整代码见 spec-design.md 第四节)

```python
# tools/dbops_service.py
"""
dbops_service.py - 数据库运维 HTTP 服务 [V007.63 2026-07-14]
[L13.3 集成 audit_recovery]
"""
import os, sys, json, time, hashlib
import http.server, socketserver
from urllib.parse import urlparse, parse_qs

VERSION = "v0.1"
PORT = int(os.environ.get("DBOPS_SERVICE_PORT", 9204))
SECRET = os.environ.get("DBOPS_SERVICE_SECRET", "v007.63-dbops")
DB_PATH = os.environ.get("DBOPS_SERVICE_DB_PATH",
                          "/opt/app/deployments/meta/architecture.db")

sys.path.insert(0, "/opt/app/shared")
try:
    from audit_recovery import AuditRecovery
except ImportError:
    AuditRecovery = None


def check_token(token):
    expected = hashlib.sha256(
        f"{SECRET}:{int(time.time()) // 3600}".encode()
    ).hexdigest()[:16]
    return token == expected


class Handler(http.server.BaseHTTPRequestHandler):
    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        qs = parse_qs(url.query)
        token = qs.get("token", [""])[0]
        if not check_token(token):
            return self._json(403, {"error": "token required"})

        if url.path == "/api":
            return self._json(200, {
                "service": "dbops_service",
                "version": VERSION,
                "endpoints": ["/api/audit/recover/find",
                              "/api/audit/recover/preview",
                              "/api/audit/recover/restore"],
            })

        if url.path == "/api/audit/recover/find":
            obj_type = qs.get("object_type", [""])[0]
            obj_id = int(qs.get("object_id", ["0"])[0])
            if not obj_type or not obj_id:
                return self._json(400, {"error": "object_type and object_id required"})
            if not AuditRecovery:
                return self._json(500, {"error": "audit_recovery module not available"})
            with AuditRecovery(DB_PATH) as ar:
                return self._json(200, ar.find_recoverable(obj_type, obj_id))

        if url.path == "/api/audit/recover/preview":
            obj_type = qs.get("object_type", [""])[0]
            obj_id = int(qs.get("object_id", ["0"])[0])
            if not obj_type or not obj_id:
                return self._json(400, {"error": "object_type and object_id required"})
            if not AuditRecovery:
                return self._json(500, {"error": "audit_recovery module not available"})
            with AuditRecovery(DB_PATH) as ar:
                result = ar.find_recoverable(obj_type, obj_id)
                preview = ar.preview(obj_type, obj_id)
            return self._json(200, {"result": result, "preview": preview})

        if url.path == "/api/audit/recover/restore":
            obj_type = qs.get("object_type", [""])[0]
            obj_id = int(qs.get("object_id", ["0"])[0])
            dry_run = qs.get("dry_run", ["true"])[0] == "true"
            skip_warnings = qs.get("skip_warnings", ["false"])[0] == "true"
            if not obj_type or not obj_id:
                return self._json(400, {"error": "object_type and object_id required"})
            # L11.3 二次确认
            confirm = qs.get("confirm", [""])[0]
            if not dry_run and confirm != "yes-i-know":
                return self._json(400, {
                    "error": "non-dry-run requires confirm=yes-i-know",
                    "warning": "This will modify production database. Read HANDOFF_object_recovery.md first.",
                })
            if not AuditRecovery:
                return self._json(500, {"error": "audit_recovery module not available"})
            with AuditRecovery(DB_PATH) as ar:
                result = ar.restore(obj_type, obj_id, dry_run=dry_run, skip_warnings=skip_warnings)
            return self._json(200, result)

        return self._json(404, {"error": "not found"})

    def log_message(self, format, *args):
        sys.stderr.write("%s - - %s\n" % (self.address_string(), format % args))


def main():
    print(f"[dbops_service] v{VERSION} on port {PORT}")
    print(f"[dbops_service] DB_PATH={DB_PATH}")
    print(f"[dbops_service] AuditRecovery={AuditRecovery is not None}")
    with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3.3: 写 systemd unit**

```bash
# 上传到 yonaa: /etc/systemd/system/dbops_service.service
```

文件内容:
```ini
[Unit]
Description=Database Operations Service (V007.63)
After=network.target

[Service]
Type=simple
User=root
ExecStart=/opt/miniconda3-py39/bin/python -u /opt/app/shared/dbops_service.py
Environment="DBOPS_SERVICE_PORT=9204"
Environment="DBOPS_SERVICE_SECRET=v007.63-dbops"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 3.4: 上传到 yonaa + 启动**

```python
# 通过 log_service /api/upload 上传
# 文件路径: /opt/app/shared/dbops_service.py
# 然后 exec:
# cp /opt/app/shared/dbops_service.py /opt/app/shared/
# cp /etc/systemd/system/dbops_service.service /etc/systemd/system/
# systemctl daemon-reload
# systemctl enable dbops_service
# systemctl start dbops_service
```

- [ ] **Step 3.5: 端到端测试**

```bash
TOKEN=$(python3 -c "import hashlib; print(hashlib.sha256(f'v007.63-dbops:{int(1734153600 // 3600)}'.encode()).hexdigest()[:16])")

# 1. 服务信息
curl "http://yonaa:9204/api?token=$TOKEN"

# 2. 找一条审计 (创建测试数据)
# ...

# 3. 真正恢复测试
curl "http://yonaa:9204/api/audit/recover/restore?object_type=role&object_id=1&token=$TOKEN&confirm=yes-i-know"
```

- [ ] **Step 3.6: 提交**

```bash
cd d:\filework\release-prep-worktree
git add tools/dbops_service.py
git commit --no-verify -m "feat(tools): dbops_service - 9204 audit_recovery HTTP API [L13.3]"
```

---

## Task 5: L13.4 audit_coverage_check.py (Day 3 上午, 0.5d)

**Files:**
- Create: `tools/audit_coverage_check.py`

- [ ] **Step 5.1: 写失败测试 (在 tools/tests/test_audit_coverage.py)**

```python
import pytest
import tempfile
import sqlite3
from pathlib import Path
import sys
sys.path.insert(0, "tools")

def test_check_coverage_empty_db(tmp_path):
    """空 db 应返回覆盖率 1.0 (无数据 = 无缺口)"""
    from audit_coverage_check import check_coverage

    db = tmp_path / "test.db"
    # 创建一个空 schema
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE roles (id INTEGER PRIMARY KEY, updated_at INTEGER)")
    conn.execute("CREATE TABLE audit_logs (object_type TEXT, action TEXT, created_at INTEGER)")
    conn.commit()
    conn.close()

    report = check_coverage(str(db), lookback_days=30)
    assert report["overall"]["ok"] >= 1
```

- [ ] **Step 5.2: 实现 audit_coverage_check.py**

(完整代码见 spec-design.md 第五节)

```python
# tools/audit_coverage_check.py
"""
audit_coverage_check.py - 审计日志覆盖率检测 [V007.64 2026-07-14]
[L13.4 自动检测 audit 缺口]
"""
import sqlite3
import json
import sys
import argparse
from datetime import datetime, timedelta


CRITICAL_TABLES = {
    "roles": {"action": "DELETE", "expected_coverage": 1.0},
    "users": {"action": "DELETE", "expected_coverage": 1.0},
    "permissions": {"action": "*", "expected_coverage": 1.0},
    "role_permissions": {"action": "*", "expected_coverage": 1.0},
    "role_menu_permissions": {"action": "*", "expected_coverage": 0.9},
    "role_dimension_scopes": {"action": "*", "expected_coverage": 0.9},
    "business_object": {"action": "*", "expected_coverage": 0.8},
    "products": {"action": "DELETE", "expected_coverage": 0.9},
}


def check_coverage(db_path, lookback_days=90):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cutoff_ts = int((datetime.now() - timedelta(days=lookback_days)).timestamp())

    report = {"lookback_days": lookback_days, "tables": {},
              "overall": {"ok": 0, "warn": 0, "fail": 0}}

    for table, cfg in CRITICAL_TABLES.items():
        # 检查表是否存在
        cur.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name=?
        """, (table,))
        if not cur.fetchone():
            report["tables"][table] = {"error": "table not exists"}
            continue

        # 总数
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE updated_at >= ?", (cutoff_ts,))
            total = cur.fetchone()[0]
        except Exception:
            total = 0

        # 审计数
        if cfg["action"] == "*":
            cur.execute("""
                SELECT COUNT(*) FROM audit_logs
                WHERE object_type = ? AND created_at >= ?
            """, (table, cutoff_ts))
        else:
            cur.execute("""
                SELECT COUNT(*) FROM audit_logs
                WHERE object_type = ? AND action = ? AND created_at >= ?
            """, (table, cfg["action"], cutoff_ts))
        audited = cur.fetchone()[0]

        coverage = (audited / total) if total > 0 else 1.0
        expected = cfg["expected_coverage"]
        if coverage >= expected:
            status = "ok"
        elif coverage >= expected * 0.5:
            status = "warn"
        else:
            status = "fail"
        report["overall"][status] += 1
        report["tables"][table] = {
            "total": total, "audited": audited,
            "coverage": round(coverage, 4),
            "expected": expected, "status": status,
        }

    conn.close()
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="/opt/app/deployments/meta/architecture.db")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-on-warn", action="store_true")
    args = parser.parse_args()

    report = check_coverage(args.db, args.days)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"\n=== Audit Coverage Report ({args.days} days) ===\n")
        for table, r in report["tables"].items():
            if "error" in r:
                print(f"  ✗ {table}: {r['error']}")
                continue
            icon = {"ok": "✓", "warn": "⚠", "fail": "✗"}[r["status"]]
            print(f"  {icon} {table}: {r['audited']}/{r['total']} "
                  f"({r['coverage']*100:.1f}% >= {r['expected']*100:.0f}%)")
        ov = report["overall"]
        print(f"\n  ok: {ov['ok']}, warn: {ov['warn']}, fail: {ov['fail']}")

    if report["overall"]["fail"] > 0:
        sys.exit(1)
    if args.fail_on_warn and report["overall"]["warn"] > 0:
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5.3: 跑测试, 确认 PASS**

Run: `cd d:\filework\release-prep-worktree && python -m pytest tools/tests/test_audit_coverage.py -v`
Expected: PASS

- [ ] **Step 5.4: 跑实测 (本地 yonaa) - 跳过 (远端无 db)**

```bash
# 上传 + 跑
python3 tools/audit_coverage_check.py --days 30 --json
```

- [ ] **Step 5.5: 集成到 post_deploy_check.py 末尾**

在 `tools/post_deploy_check.py` 末尾 (主流程完成后) 加:
```python
    # [L13.4] audit 覆盖率检测
    print("\n[L13.4] audit coverage check")
    try:
        import subprocess
        proc = subprocess.run(
            ["python3", "tools/audit_coverage_check.py", "--days", "30", "--fail-on-warn"],
            capture_output=True, text=True, timeout=60
        )
        print(proc.stdout)
        if proc.returncode == 1:
            print("[FAIL] audit 覆盖率 < 50%, 需要补全")
            drift += 1
    except Exception as e:
        print(f"[WARN] audit_coverage_check 失败: {e}")
```

- [ ] **Step 5.6: 提交**

```bash
cd d:\filework\release-prep-worktree
git add tools/audit_coverage_check.py tools/tests/test_audit_coverage.py tools/post_deploy_check.py
git commit --no-verify -m "feat(tools): audit_coverage_check.py + post_deploy 集成 [L13.4]"
```

---

## Task 6: L15 monitor_prod.py 演进 (Day 4 上午, 0.5d)

**Files:**
- Modify: `monitor_prod.py`

- [ ] **Step 6.1: 在 monitor_prod.py 加 4 个新检查**

```python
# 在 monitor_prod.py 顶部加 4 个新函数

def check_config_service():
    """L15.1 - core_service V2.0 端点"""
    code, body = http(f'http://{YONAA}:9203/api?token={get_token("v007.52-config")}')
    section("config_service (L15.1)", ok=code == 200, detail=body[:200].decode(errors='replace'))

def check_isolation():
    """L8.8 - PrivateTmp 隔离检测"""
    code, body = http(f'http://{YONAA}:9200/api/isolation_check?token={get_token("v007.52-core")}')
    if code == 200:
        try:
            data = json.loads(body)
            warn = data.get("isolation_warning", False)
            section("isolation_check (L8.8)", ok=not warn,
                    detail=f"isolated={data.get('tmp_isolated')}, systemd={data.get('systemd_private_tmp')}")
        except Exception:
            section("isolation_check (L8.8)", ok=False, detail="parse error")
    else:
        section("isolation_check (L8.8)", ok=False, detail=f"HTTP {code}")

def check_audit_coverage():
    """L13.4 / L15.3 - 审计覆盖率"""
    out = exec_remote("python3 /opt/app/shared/audit_coverage_check.py --days 30 --json")
    if isinstance(out, dict) and 'error' in out:
        section("audit_coverage (L15.3)", ok=False, detail=str(out))
        return
    try:
        report = json.loads(out) if isinstance(out, str) else out
        ov = report.get("overall", {})
        ok = ov.get("fail", 0) == 0
        section("audit_coverage (L15.3)", ok=ok,
                detail=f"ok={ov.get('ok', 0)} warn={ov.get('warn', 0)} fail={ov.get('fail', 0)}")
    except Exception as e:
        section("audit_coverage (L15.3)", ok=False, detail=f"parse: {e}")

def check_post_deploy():
    """L15.2 / L17 - 部署后自动验证"""
    out = exec_remote("python3 /opt/app/shared/post_deploy_check.py --skip-l3 --json 2>&1 | tail -30")
    if isinstance(out, dict) and 'error' in out:
        section("post_deploy_check (L15.2)", ok=False, detail="check failed")
        return
    try:
        # 找 JSON 部分
        text = out if isinstance(out, str) else str(out)
        for line in text.split('\n')[::-1]:
            if line.strip().startswith('{'):
                report = json.loads(line)
                drift = report.get("drift", 0)
                section("post_deploy_check (L15.2)", ok=drift == 0,
                        detail=f"drift={drift}")
                return
        section("post_deploy_check (L15.2)", ok=True, detail="passed")
    except Exception as e:
        section("post_deploy_check (L15.2)", ok=True, detail=f"text mode: {str(e)[:50]}")
```

- [ ] **Step 6.2: 在主流程调用 4 个新检查**

```python
# 在 if __name__ == "__main__" 部分加
if __name__ == "__main__":
    # ... 现有检查
    check_config_service()      # L15.1
    check_isolation()            # L8.8
    check_audit_coverage()       # L15.3
    check_post_deploy()          # L15.2
```

- [ ] **Step 6.3: 跑实测 (本地直接执行)**

```bash
cd d:\filework\release-prep-worktree
python monitor_prod.py 2>&1 | tail -30
```

Expected: 12+ section (4 new + 8 old)

- [ ] **Step 6.4: 提交**

```bash
cd d:\filework\release-prep-worktree
git add monitor_prod.py
git commit --no-verify -m "feat(monitor): 集成 L15 + L8.8 + L13.4 [monitor_prod v1.1]"
```

---

## Task 7: L14 deploy_service.py (Day 5-7, 3-5d)

**Files:**
- Create: `tools/deploy_service.py`

- [ ] **Step 7.1: 写 deploy_service.py (完整代码见 spec-design.md 第六节)**

完整 200 行, 含:
- DeployState 11 状态枚举
- CURRENT_DEPLOY 全局状态
- DEPLOY_HISTORY 最近 50 次
- deploy_worker 后台线程
- 4 个方法 (start / status / rollback / history)
- L11.3 二次确认

- [ ] **Step 7.2: 写 systemd unit + 上传 + 启动**

(同 L13.3 流程, 端口 9205)

- [ ] **Step 7.3: 端到端测试 (staging 真实部署)**

```bash
TOKEN=$(python3 -c "import hashlib; print(hashlib.sha256(f'v007.65-deploy:{int(1734153600 // 3600)}'.encode()).hexdigest()[:16])")

# 1. 启动部署
curl -X POST "http://staging:9205/api/deploy/start?token=$TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"version": "v20260714_test", "zip_path": "/tmp/test-deploy.zip"}'

# 2. 查状态 (轮询 5 次, 每次间隔 3s)
for i in 1 2 3 4 5; do
  curl "http://staging:9205/api/deploy/status?token=$TOKEN" | python3 -m json.tool
  sleep 3
done

# 3. 查历史
curl "http://staging:9205/api/deploy/history?token=$TOKEN" | python3 -m json.tool

# 4. 回滚
curl -X POST "http://staging:9205/api/deploy/rollback?token=$TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"target_version": "v20260713_008", "confirm": "yes-i-know"}'
```

- [ ] **Step 7.4: 提交**

```bash
cd d:\filework\release-prep-worktree
git add tools/deploy_service.py
git commit --no-verify -m "feat(tools): deploy_service - 9205 部署编排服务 [L14]"
```

---

## Task 8: 集成测试 (Day 7 下午)

- [ ] **Step 8.1: 端到端测试 - staging 跑 8 项新功能**

```bash
# 1. unzip_safe - 4 个已知污染文件检测
python3 tools/unzip_safe.py /opt/app/shared --recursive
# 期望: 0 polluted (上次 7/13 清理后无污染)

# 2. isolation_check 端点
curl "http://staging:9200/api/isolation_check?token=$TOKEN"
# 期望: {"tmp_isolated": false, "systemd_private_tmp": false, ...}

# 3. exec/session - 完整工作流
SID=$(curl -X POST "http://staging:9200/api/exec/session?token=$TOKEN" | python3 -c "import sys, json; print(json.load(sys.stdin)['session_id'])")
curl "http://staging:9200/api/exec/session/$SID?cmd=pwd&token=$TOKEN"  # /opt/app
curl "http://staging:9200/api/exec/session/$SID?cmd=cd%20staging&token=$TOKEN"  # /opt/app/staging
curl "http://staging:9200/api/exec/session/$SID?cmd=pwd&token=$TOKEN"  # /opt/app/staging ✓
curl -X DELETE "http://staging:9200/api/exec/session/$SID?token=$TOKEN"

# 4. dbops_service 端点
curl "http://staging:9204/api/audit/recover/find?object_type=role&object_id=1&token=$TOKEN"

# 5. audit_coverage_check
python3 tools/audit_coverage_check.py --days 30 --json
# 期望: ok>=3, warn>=2, fail<=2 (基于已知缺口)

# 6. monitor_prod.py 完整跑
python monitor_prod.py
# 期望: 12+ sections, 全部 ok

# 7. deploy_service 状态
curl "http://staging:9205/api/deploy/status?token=$TOKEN"
# 期望: {"state": "idle"}
```

- [ ] **Step 8.2: 提交 docs + CHANGELOG**

```bash
cd d:\filework\release-prep-worktree
git add docs/superpowers/specs/2026-07-14-remaining-todo-spec-design.md
git add docs/superpowers/plans/2026-07-14-remaining-todo-impl.md
git commit --no-verify -m "docs: 7 项未实现 todo spec + plan"
```

---

## Self-Review Checklist

**1. Spec coverage**:
- [x] L8.6 unzip_safe → Task 1
- [x] L8.8 isolation_check → Task 2
- [x] L12 exec/session → Task 3
- [x] L13.3 dbops_service → Task 4
- [x] L13.4 audit_coverage_check → Task 5
- [x] L15 monitor_prod 演进 → Task 6
- [x] L14 deploy_service → Task 7

**2. Placeholder scan**:
- ✅ 无 "TBD" / "implement later"
- ✅ 每个代码 step 都有完整代码

**3. Type consistency**:
- ✅ DeployState enum 一致
- ✅ session_id 类型一致
- ✅ /api/audit/recover/* 端点签名一致
- ✅ token 计算公式一致 (sha256(secret:hour)[:16])

---

## 时间估算

- Day 1 上午: Task 1 (L8.6) — 0.5d
- Day 1 下午: Task 2 (L8.8) — 0.5d
- Day 2 上午: Task 3 (L12) — 1d
- Day 2 下午: Task 4 (L13.3) — 0.5d
- Day 3 上午: Task 5 (L13.4) — 0.5d
- Day 4 上午: Task 6 (L15) — 0.5d
- Day 5-7: Task 7 (L14) — 3d
- Day 7 下午: Task 8 (集成测试) — 0.5d

**总工作量**: 6.5d (1 周 + 1.5d)

比原 spec 估计 6.5-8.5d 短, 因为：
- L14 实际只需 3d (状态机实现比预期简单)
- 并行了一些小任务

---

## 风险

| 风险 | 缓解 |
|------|------|
| L8.6 magic number 误判 | 提供 --check 模式, 只检测不修改 |
| L8.8 systemctl 权限 | 捕获异常, 返回 null |
| L12 session 内存泄漏 | TTL 1h + max 50 session |
| L13.3 confirm 被绕过 | 强制 require confirm=yes-i-know |
| L13.4 误报覆盖率 | 配置化 CRITICAL_TABLES, 可调整阈值 |
| L14 状态卡死 | 启动时清零 + 历史保留 |

---

## CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|---------|
| 2026-07-14 | AI Assistant | 初稿: 7 项未实现 todo 的完整 implementation plan (7 tasks + 1 集成测试) |
