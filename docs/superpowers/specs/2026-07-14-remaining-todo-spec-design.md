# SPEC: 8 项未实现基础设施 TODO 细化设计

> **日期**: 2026-07-14
> **状态**: Draft → 待用户审阅
> **触发问题**: TODO_LONGTERM.md 8 项 P0/P1 todo 仍待实施，影响部署可观测性、健壮性、可恢复性
> **目标**: 把 L8.6 / L8.8 / L12 / L13.3 / L13.4 / L14 / L15 全部细化到可执行规格

---

## TL;DR

| # | TODO | 工作量 | 优先级 | 关联文件 |
|---|------|--------|--------|----------|
| L8.6 | unzip_safe 工具 | 0.5d | P1 | tools/unzip_safe.{py,sh} |
| L8.8 | /api/isolation_check 端点 | 0.5d | P1 | tools/core_service.py |
| L12 | /api/exec shell session | 1d | P1 | tools/core_service.py |
| L13.3 | audit_recovery HTTP API | 0.5d | **P0** | tools/dbops_service.py (新建) |
| L13.4 | audit_coverage_check.py | 0.5d | P1 | tools/audit_coverage_check.py |
| L14 | deploy_service 独立服务 | 3-5d | P1 | tools/deploy_service.py (新建) |
| L15 | monitor_prod.py 演进 | 0.5d | P1 | monitor_prod.py |

**总工作量**: 6.5-8.5d (含 L14)

---

## 一、L8.6 unzip_safe 工具 (P1, 0.5d)

### 1.1 问题

L8.5 multipart 污染导致 4 个文件被破坏:
- `deploy-v20260713_002.zip` (149 字节污染)
- `deploy-v20260713_007.zip` (149 字节污染)
- `monitor_prod.py` (140 字节污染)
- `verify_deployment.py` (145 字节污染)

**当前缺**: 上传后自动检测文件 magic number 的工具

### 1.2 方案

**核心**: 上传后立即检测文件 magic number, 不匹配则自动剥离 multipart 头或报警

**实现**: `tools/unzip_safe.py` + `tools/unzip_safe.sh`

**Magic Number 字典**:
| 文件类型 | Magic Number | 说明 |
|---------|-------------|------|
| zip | `PK\x03\x04` | 50 4B 03 04 |
| tar.gz | `\x1f\x8b\x08` | gzip header |
| .py | `"""` 或 `import` 或 `from` | 文本起始 |
| .sh | `#!/bin/bash` 或 `#!/usr/bin/env` | shebang |
| .js | `import` 或 `const` 或 `function` | 文本起始 |
| .md | `# ` | markdown 标题 |

### 1.3 接口

```bash
# 命令行
python tools/unzip_safe.py <file>          # 检测 + 自动修复
python tools/unzip_safe.py <file> --check  # 只检测, 不修改
python tools/unzip_safe.py <file> --json   # JSON 输出
python tools/unzip_safe.py <dir> --recursive  # 递归检测

# 编程接口
from unzip_safe import detect_pollution, auto_strip_multipart
is_polluted, expected_type = detect_pollution("monitor_prod.py")
if is_polluted:
    clean_content = auto_strip_multipart(open("monitor_prod.py", "rb").read())
    open("monitor_prod.py", "wb").write(clean_content)
```

### 1.4 自动剥离 multipart 头算法

```python
def auto_strip_multipart(data: bytes) -> bytes:
    """如果文件被 multipart 头污染, 自动剥离并返回干净内容"""
    # 检测 multipart boundary
    import re
    m = re.search(rb'--[A-Za-z0-9_-]{8,}\r?\n', data[:200])
    if not m:
        return data  # 不是 multipart, 返回原数据

    boundary = m.group(0).rstrip(b'\r\n')
    parts = data.split(boundary)
    # 找最长且 magic number 匹配的部分
    candidates = []
    for part in parts:
        # 跳过分隔行, 找 Content-Disposition 后的内容
        header_end = part.find(b'\r\n\r\n')
        if header_end == -1:
            continue
        body = part[header_end+4:].rstrip(b'\r\n')
        if len(body) > 100:  # 至少 100 字节
            candidates.append(body)
    if not candidates:
        return data
    # 返回最长的 (假设最长的是真实文件)
    return max(candidates, key=len)
```

### 1.5 集成点

**deploy.sh PHASE 0.5** (deploy.sh L169-263):
```bash
# smart_extract 后立即检查
python3 $SCRIPT_DIR/unzip_safe.py $DEPLOYMENTS_DIR --recursive --json
# 如果发现污染, 立即 abort
```

**core_service /api/upload** (core_service.py L336+):
```bash
# upload 完成后立即验证 magic number
python3 -c "
import magic
with open('$target', 'rb') as f:
    head = f.read(8)
    if not is_valid_magic(head, expected_type='$expected_ext'):
        raise ValueError('magic number mismatch, possible multipart pollution')
"
```

### 1.6 验收标准

- [ ] 工具可检测 zip/python/sh 文件类型
- [ ] 检测 4 种已知污染文件全部 PASS
- [ ] 错误文件不修改 (--check 模式)
- [ ] JSON 输出含 file/expected_type/actual_type/is_polluted 字段
- [ ] 集成到 deploy.sh PHASE 0.5 末尾

---

## 二、L8.8 /api/isolation_check 端点 (P1, 0.5d)

### 2.1 问题

L8.7 修复了 systemd PrivateTmp 隔离问题, 但**没有验证手段**:
- 怎么知道当前服务跑在隔离区？
- 隔离区清空后怎么发现？
- 其他服务是否也被隔离？

### 2.2 方案

**新增端点**: `core_service /api/isolation_check` (L226 路由表附近)

**实现**:
```python
def _isolation_check(self, q):
    level = _check_token(q)
    if not level:
        return self._json(403, {"error": "token required"})

    import subprocess
    # 1. 检查 /tmp 是否隔离
    tmp_inode = os.stat("/tmp").st_ino
    parent_inode = os.stat("/").st_ino
    is_isolated = (tmp_inode != parent_inode)

    # 2. 检查 systemd PrivateTmp 配置
    service_name = os.environ.get("INVOCATION_ID", "unknown")
    systemd_isolated = False
    try:
        # systemctl show core_service.service -p PrivateTmp
        out = subprocess.run(
            ["systemctl", "show", "core_service.service", "-p", "PrivateTmp"],
            capture_output=True, text=True, timeout=5
        ).stdout
        systemd_isolated = "yes" in out.lower()
    except Exception:
        pass

    # 3. 检查实际写入位置
    test_file = "/tmp/_isolation_test_$$"
    open(test_file, "w").write("test")
    real_path = os.path.realpath(test_file)
    os.remove(test_file)

    # 4. 检查所有重要目录隔离状态
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
        "tmp_isolated": is_isolated,
        "systemd_private_tmp": systemd_isolated,
        "test_file_real_path": real_path,
        "isolation_warning": is_isolated and systemd_isolated,
        "dirs": isolation_status,
    })
```

**注册路由** (L226 附近):
```python
if route == "/api/isolation_check":
    return self._isolation_check(q)
```

### 2.3 集成点

**monitor_prod.py** 加调用:
```python
code, body = http(f'http://{YONAA}:9200/api/isolation_check?token={token}')
section("isolation_check", ok=code == 200, detail=body[:200].decode())
```

**deploy.sh PHASE 0.5 前**:
```bash
# 部署前检测是否在隔离区
python3 -c "
import urllib.request
import json
r = urllib.request.urlopen('http://localhost:9200/api/isolation_check?token=...', timeout=5)
data = json.loads(r.read())
if data.get('isolation_warning'):
    print('WARNING: 部署在 PrivateTmp 隔离区, 上传的文件可能不可见')
"
```

### 2.4 验收标准

- [ ] GET /api/isolation_check 返回 200 + 完整 JSON
- [ ] tmp_isolated / systemd_private_tmp 字段正确
- [ ] 部署前自动检测, 输出告警
- [ ] monitor_prod.py 集成

---

## 三、L12 /api/exec shell session (P1, 1d)

### 3.1 问题

当前 `/api/exec` 每次请求独立执行, 不能:
- 持久化 cd 工作目录
- 保留环境变量
- 维持 shell aliases / functions
- 维护 session 状态 (e.g., 登录后的 token)

**实际影响**:
- 每次发命令都要写完整路径
- 多步操作 (cd X && Y && Z) 要分 3 次请求
- 容易出现 race condition

### 3.2 方案

**新增端点**: `/api/exec/session` 系列

**API**:
```
POST /api/exec/session     → 创建 session, 返回 session_id
GET  /api/exec/session/:id → 在 session 中执行命令
GET  /api/exec/session/:id/state  → 查 session 状态 (cwd, env, history)
DELETE /api/exec/session/:id  → 销毁 session
```

**Session 存储**:
```python
SESSIONS = {}  # session_id -> {cwd, env, history, last_used, proc}

def _exec_session_create(self, q):
    """创建 shell session, 返回 session_id"""
    sid = hashlib.sha256(os.urandom(16)).hexdigest()[:16]
    SESSIONS[sid] = {
        "cwd": "/opt/app",
        "env": {},
        "history": [],
        "created_at": time.time(),
        "last_used": time.time(),
    }
    return self._json(200, {"session_id": sid, "cwd": "/opt/app"})

def _exec_session_run(self, q, sid):
    """在指定 session 中执行命令"""
    if sid not in SESSIONS:
        return self._json(404, {"error": "session not found"})

    s = SESSIONS[sid]
    cmd = q.get("cmd", [""])[0]
    if not cmd:
        return self._json(400, {"error": "cmd required"})

    # 合并 session env
    full_env = {**os.environ, **s["env"]}

    proc = subprocess.run(
        cmd, shell=True, cwd=s["cwd"], env=full_env,
        capture_output=True, text=True, timeout=30
    )

    # 更新 session 状态
    s["last_used"] = time.time()
    s["history"].append({
        "cmd": cmd, "exit_code": proc.returncode,
        "stdout": proc.stdout[:500], "stderr": proc.stderr[:500],
        "ts": time.time(),
    })
    # 更新 cwd (如果命令是 cd)
    if cmd.strip().startswith("cd "):
        s["cwd"] = os.path.abspath(os.path.join(s["cwd"], cmd[3:].strip()))

    return self._json(200, {
        "stdout": proc.stdout, "stderr": proc.stderr,
        "exit_code": proc.returncode, "cwd": s["cwd"],
    })

def _exec_session_state(self, q, sid):
    if sid not in SESSIONS:
        return self._json(404, {"error": "session not found"})
    s = SESSIONS[sid]
    return self._json(200, {
        "cwd": s["cwd"],
        "env_keys": list(s["env"].keys()),
        "history_count": len(s["history"]),
        "last_used": s["last_used"],
    })

def _exec_session_destroy(self, q, sid):
    if sid in SESSIONS:
        del SESSIONS[sid]
    return self._json(200, {"ok": True})
```

**Session TTL** (1h):
```python
def _cleanup_sessions():
    now = time.time()
    expired = [sid for sid, s in SESSIONS.items()
               if now - s["last_used"] > 3600]
    for sid in expired:
        del SESSIONS[sid]
# 在 _api_info 中触发清理
```

**路由注册** (L226 附近):
```python
if route == "/api/exec/session":
    return self._exec_session_create(q)
if route.startswith("/api/exec/session/"):
    parts = route.split("/")
    sid = parts[4]
    action = parts[5] if len(parts) > 5 else "run"
    if action == "state":
        return self._exec_session_state(q, sid)
    if route.endswith("/state"):
        return self._exec_session_state(q, sid)
    if q.get("_method") == "DELETE" or self.command == "DELETE":
        return self._exec_session_destroy(q, sid)
    return self._exec_session_run(q, sid)
```

### 3.3 客户端使用示例

```python
# 旧方式 (无 session): 3 次请求
exec("cd /opt/app")
exec("ls")
exec("cat foo")

# 新方式 (有 session): 1 次创建 + 多次复用
sid = create_session()
exec_in_session(sid, "cd /opt/app")
exec_in_session(sid, "ls")
exec_in_session(sid, "cat foo")
# 维护 cwd 状态
destroy_session(sid)
```

### 3.4 安全考虑

- Session TTL 1h (自动清理)
- 最多 50 个 session (内存保护)
- 每个 session 占用内存 < 10MB
- 不允许 `setuid` / `setgid` 命令

### 3.5 验收标准

- [ ] POST /api/exec/session 返回 session_id
- [ ] GET /api/exec/session/:id 在 session 中跑命令
- [ ] 第二次 cd 路径正确 (相对路径)
- [ ] DELETE /api/exec/session/:id 销毁
- [ ] TTL 1h 自动清理
- [ ] 路由优先级正确 (不与 /api/exec 冲突)

---

## 四、L13.3 audit_recovery HTTP API (P0, 0.5d)

### 4.1 问题

`tools/audit_recovery.py` 框架已写好 (find_recoverable / preview / restore), 但:
- 只能本地 Python 调用
- 没法从远端触发恢复
- dbops_service 没有集成

**实际影响**: 误删数据后, 只能登 yonaa 跑 Python 脚本, 紧急情况不友好

### 4.2 方案

**新增 `tools/dbops_service.py`** (端口 9204 已有空间):

```python
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
DB_PATH = "/opt/app/deployments/meta/architecture.db"

# 引入 audit_recovery
sys.path.insert(0, "/opt/app/shared")
try:
    from audit_recovery import AuditRecovery
except ImportError:
    AuditRecovery = None


def check_token(token):
    expected = hashlib.sha256(f"{SECRET}:{int(time.time()) // 3600}".encode()).hexdigest()[:16]
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
                "endpoints": [
                    "/api", "/api/audit/recover/find",
                    "/api/audit/recover/preview",
                    "/api/audit/recover/restore",
                ],
            })

        # /api/audit/recover/find?object_type=role&object_id=1201
        if url.path == "/api/audit/recover/find":
            obj_type = qs.get("object_type", [""])[0]
            obj_id = int(qs.get("object_id", ["0"])[0])
            if not obj_type or not obj_id:
                return self._json(400, {"error": "object_type and object_id required"})
            if not AuditRecovery:
                return self._json(500, {"error": "audit_recovery module not available"})
            with AuditRecovery(DB_PATH) as ar:
                result = ar.find_recoverable(obj_type, obj_id)
            return self._json(200, result)

        # /api/audit/recover/preview?object_type=role&object_id=1201
        if url.path == "/api/audit/recover/preview":
            obj_type = qs.get("object_type", [""])[0]
            obj_id = int(qs.get("object_id", ["0"])[0])
            if not obj_type or not obj_id:
                return self._json(400, {"error": "object_type and object_id required"})
            if not AuditRecovery:
                return self._json(500, {"error": "audit_recovery module not available"})
            with AuditRecovery(DB_PATH) as ar:
                result = ar.find_recoverable(obj_type, obj_id)
                lines = ar.preview(obj_type, obj_id)
            return self._json(200, {"result": result, "preview": lines})

        # /api/audit/recover/restore?object_type=role&object_id=1201&dry_run=true
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
            with AuditRecovery(DB_PATH) as ar:
                result = ar.restore(obj_type, obj_id, dry_run=dry_run, skip_warnings=skip_warnings)
            return self._json(200, result)

        return self._json(404, {"error": "not found"})

    def log_message(self, format, *args):
        sys.stderr.write("%s - - %s\n" % (self.address_string(), format % args))


def main():
    print(f"[dbops_service] Starting on port {PORT}")
    print(f"[dbops_service] SECRET={'*' * 8}{SECRET[-4:]}")
    print(f"[dbops_service] DB_PATH={DB_PATH}")
    with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
```

**systemd unit** (`/etc/systemd/system/dbops_service.service`):
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
Environment="DBOPS_SERVICE_DB_PATH=/opt/app/deployments/meta/architecture.db"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 4.3 集成点

**monitor_prod.py** 加检查:
```python
code, body = http(f'http://{YONAA}:9204/api?token={get_token("v007.63-dbops")}')
section("dbops_service", ok=code == 200, detail="audit_recovery endpoints ready")
```

**HANDOFF_object_recovery.md** 加:
```markdown
## 远端调用方式
\`\`\`bash
TOKEN=$(python3 -c "import hashlib; print(hashlib.sha256('v007.63-dbops:$(date +\\%s | xargs -I{} echo $(( {} / 3600 )))'.encode()).hexdigest()[:16])")

# 1. 查找
curl "http://yonaa:9204/api/audit/recover/find?object_type=role&object_id=1201&token=$TOKEN"

# 2. 预览
curl "http://yonaa:9204/api/audit/recover/preview?object_type=role&object_id=1201&token=$TOKEN"

# 3. 恢复 (dry_run 默认 true)
curl "http://yonaa:9204/api/audit/recover/restore?object_type=role&object_id=1201&token=$TOKEN"

# 4. 真正恢复 (需要 confirm=yes-i-know)
curl "http://yonaa:9204/api/audit/recover/restore?object_type=role&object_id=1201&dry_run=false&confirm=yes-i-know&token=$TOKEN"
\`\`\`
```

### 4.4 验收标准

- [ ] GET /api 返回服务信息
- [ ] GET /api/audit/recover/find 返回主实体 + 关联 + audit_log_ids
- [ ] GET /api/audit/recover/preview 返回恢复步骤
- [ ] GET /api/audit/recover/restore 默认 dry_run=true
- [ ] dry_run=false 需要 confirm=yes-i-know
- [ ] L11.3 二次确认机制生效
- [ ] systemd unit 启动 OK
- [ ] 误删测试 (创建 + 删除 + 恢复) 全流程通过

---

## 五、L13.4 audit_coverage_check.py (P1, 0.5d)

### 5.1 问题

已知 4 个 audit 缺口:
- role_menu (0% 覆盖率)
- role_dim_scope (0% 覆盖率)
- role_permissions (2/28 缺)
- 无 audit_coverage 自动检测工具

**实际影响**: 每次新发现缺口都要手动加

### 5.2 方案

**新增 `tools/audit_coverage_check.py`**:

```python
"""
audit_coverage_check.py - 审计日志覆盖率检测 [V007.64 2026-07-14]
[L13.4 自动检测 audit 缺口]

CI 用: 部署后跑, 覆盖率 < 80% 报警
"""
import sqlite3
import json
import sys
import argparse
from datetime import datetime, timedelta


# 关键实体表 (覆盖率必须 100% 的)
CRITICAL_TABLES = {
    "roles": {"action": "DELETE", "expected_coverage": 1.0},
    "users": {"action": "DELETE", "expected_coverage": 1.0},
    "permissions": {"action": "*", "expected_coverage": 1.0},
    "role_permissions": {"action": "*", "expected_coverage": 1.0},
    "role_menu_permissions": {"action": "*", "expected_coverage": 0.9},  # 已知 0%
    "role_dimension_scopes": {"action": "*", "expected_coverage": 0.9},  # 已知 0%
    "business_object": {"action": "*", "expected_coverage": 0.8},
    "products": {"action": "DELETE", "expected_coverage": 0.9},
}

DB_PATH = "/opt/app/deployments/meta/architecture.db"


def check_coverage(db_path=DB_PATH, lookback_days=90):
    """检查关键实体的 audit 覆盖率"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cutoff_ts = int((datetime.now() - timedelta(days=lookback_days)).timestamp())
    report = {
        "lookback_days": lookback_days,
        "tables": {},
        "overall": {"ok": 0, "warn": 0, "fail": 0},
    }

    for table, cfg in CRITICAL_TABLES.items():
        # 统计该表 (lookback_days) 内的总操作数
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE updated_at >= ?", (cutoff_ts,))
        total = cur.fetchone()[0]

        # 统计 audit_logs 里有该表相关操作的数量
        cur.execute("""
            SELECT COUNT(*) FROM audit_logs
            WHERE object_type = ?
              AND action = ?
              AND created_at >= ?
        """, (table, cfg["action"], cutoff_ts))
        audited = cur.fetchone()[0]

        coverage = audited / total if total > 0 else 1.0
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
            "coverage": coverage, "expected": expected, "status": status,
        }

    conn.close()
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=DB_PATH)
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
            icon = {"ok": "✓", "warn": "⚠", "fail": "✗"}[r["status"]]
            print(f"  {icon} {table}: {r['audited']}/{r['total']} "
                  f"({r['coverage']*100:.1f}% >= {r['expected']*100:.0f}%)")
        ov = report["overall"]
        print(f"\n  ok: {ov['ok']}, warn: {ov['warn']}, fail: {ov['fail']}")

    # Exit code
    if ov["fail"] > 0:
        sys.exit(1)
    if args.fail_on_warn and ov["warn"] > 0:
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
```

### 5.3 集成点

**CI / post_deploy**:
```bash
# post_deploy_check.py 末尾
python3 tools/audit_coverage_check.py --days 30 --fail-on-warn
```

**monitor_prod.py** 集成:
```python
# 检查 audit 覆盖率
code, body = http(f'http://{YONAA}:9101/api/audit?lines=500&token=...')
# 解析 audit log + 算覆盖率
# 输出 section("audit_coverage", ok=...)
```

### 5.4 验收标准

- [ ] 脚本输出每个关键表覆盖率
- [ ] --json 输出完整报告
- [ ] --fail-on-warn 严格模式
- [ ] exit code: 0=ok, 1=fail, 2=warn
- [ ] 集成到 post_deploy_check.py 末尾

---

## 六、L14 deploy_service 独立服务 (P1, 3-5d)

### 6.1 问题

core_service 已 500+ 行, **不能**再加新端点。但部署相关功能需要:
- /api/deploy/start (接收 zip)
- /api/deploy/status (查 6 状态机)
- /api/deploy/rollback (一键回滚)
- /api/deploy/history
- /api/deploy/verify (集成 post_deploy_check)

### 6.2 方案

**新增 `tools/deploy_service.py`** (端口 9205):

```python
"""
deploy_service.py - 部署编排服务 [V007.65 2026-07-14]
[L14 独立服务, 架构铁律: core_service 不再加新端点]

端点:
  POST /api/deploy/start       接收 deploy_id + zip 路径, 启动部署状态机
  GET  /api/deploy/status      查询当前 deploy 状态
  POST /api/deploy/rollback    回滚到指定版本
  GET  /api/deploy/history     部署历史
  GET  /api/deploy/verify      调用 post_deploy_check.py
"""
import os, sys, json, time, hashlib, threading, subprocess
import http.server, socketserver
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from enum import Enum

VERSION = "v0.1"
PORT = int(os.environ.get("DEPLOY_SERVICE_PORT", 9205))
SECRET = os.environ.get("DEPLOY_SERVICE_SECRET", "v007.65-deploy")
LOG_DIR = "/opt/app/deployments/logs"
DEPLOY_ROOT = "/opt/app/deployments"


class DeployState(Enum):
    IDLE = "idle"
    RECEIVED = "received"
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    SWITCHING = "switching"
    SWITCHED = "switched"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


# 全局状态
CURRENT_DEPLOY = {
    "deploy_id": "",
    "version": "",
    "state": DeployState.IDLE.value,
    "started_at": 0,
    "logs": [],
    "zip_path": "",
    "deploy_root": DEPLOY_ROOT,
}
DEPLOY_HISTORY = []  # 最近 50 次部署


def check_token(token):
    expected = hashlib.sha256(f"{SECRET}:{int(time.time()) // 3600}".encode()).hexdigest()[:16]
    return token == expected


def log(msg):
    """记录到内存 + 日志文件"""
    ts = datetime.now().isoformat(timespec="seconds")
    line = f"[{ts}] {msg}"
    CURRENT_DEPLOY["logs"].append(line)
    print(line, flush=True)


def transition(new_state):
    """状态机转换"""
    old = CURRENT_DEPLOY["state"]
    CURRENT_DEPLOY["state"] = new_state.value if isinstance(new_state, DeployState) else new_state
    log(f"state: {old} → {CURRENT_DEPLOY['state']}")


def deploy_worker(deploy_id, version, zip_path):
    """部署状态机后台线程"""
    CURRENT_DEPLOY["deploy_id"] = deploy_id
    CURRENT_DEPLOY["version"] = version
    CURRENT_DEPLOY["zip_path"] = zip_path
    CURRENT_DEPLOY["started_at"] = time.time()

    try:
        # 1. 上传校验
        transition(DeployState.UPLOADED)
        if not os.path.exists(zip_path):
            raise FileNotFoundError(f"zip not found: {zip_path}")

        # 2. 解压
        transition(DeployState.EXTRACTING)
        subprocess.run(["unzip", "-o", zip_path, "-d", DEPLOY_ROOT], check=True, timeout=300)
        transition(DeployState.EXTRACTED)

        # 3. 验证
        transition(DeployState.VERIFYING)
        proc = subprocess.run(
            ["python3", "/opt/app/shared/post_deploy_check.py", "--skip-l3"],
            capture_output=True, text=True, timeout=120
        )
        if proc.returncode != 0:
            raise RuntimeError(f"verify failed: {proc.stderr}")
        transition(DeployState.VERIFIED)

        # 4. 切 current 链接
        transition(DeployState.SWITCHING)
        version_path = f"{DEPLOY_ROOT}/{version}"
        current_link = f"{DEPLOY_ROOT}/current"
        if os.path.exists(current_link) or os.path.islink(current_link):
            os.remove(current_link)
        os.symlink(version_path, current_link)
        transition(DeployState.SWITCHED)

        log(f"deploy {deploy_id} SUCCESS")
    except Exception as e:
        log(f"deploy {deploy_id} FAILED: {e}")
        transition(DeployState.FAILED)
    finally:
        # 记录到历史
        DEPLOY_HISTORY.append({
            "deploy_id": deploy_id,
            "version": version,
            "started_at": CURRENT_DEPLOY["started_at"],
            "duration_sec": time.time() - CURRENT_DEPLOY["started_at"],
            "final_state": CURRENT_DEPLOY["state"],
        })
        if len(DEPLOY_HISTORY) > 50:
            DEPLOY_HISTORY.pop(0)


class Handler(http.server.BaseHTTPRequestHandler):
    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _check_token(self, qs):
        token = qs.get("token", [""])[0]
        return check_token(token)

    def do_POST(self):
        url = urlparse(self.path)
        qs = parse_qs(url.query)
        if not self._check_token(qs):
            return self._json(403, {"error": "token required"})

        if url.path == "/api/deploy/start":
            # 读取 body
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode() or "{}")
            deploy_id = body.get("deploy_id") or f"deploy-{int(time.time())}"
            version = body.get("version", "")
            zip_path = body.get("zip_path", "")
            if not version or not zip_path:
                return self._json(400, {"error": "version and zip_path required"})
            if CURRENT_DEPLOY["state"] not in ("idle", "failed", "rolled_back"):
                return self._json(409, {
                    "error": "another deploy in progress",
                    "current": CURRENT_DEPLOY["state"],
                })
            # 后台线程
            t = threading.Thread(target=deploy_worker, args=(deploy_id, version, zip_path))
            t.daemon = True
            t.start()
            return self._json(202, {"deploy_id": deploy_id, "accepted": True})

        if url.path == "/api/deploy/rollback":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode() or "{}")
            target_version = body.get("target_version", "")
            if not target_version:
                return self._json(400, {"error": "target_version required"})
            # L11.3 二次确认
            confirm = body.get("confirm", "")
            if confirm != "yes-i-know":
                return self._json(400, {
                    "error": "rollback requires confirm=yes-i-know",
                })
            # 切链接
            current_link = f"{DEPLOY_ROOT}/current"
            if os.path.exists(current_link) or os.path.islink(current_link):
                os.remove(current_link)
            os.symlink(f"{DEPLOY_ROOT}/{target_version}", current_link)
            CURRENT_DEPLOY["state"] = DeployState.ROLLED_BACK.value
            return self._json(200, {"rolled_back_to": target_version})

        return self._json(404, {"error": "not found"})

    def do_GET(self):
        url = urlparse(self.path)
        qs = parse_qs(url.query)
        if not self._check_token(qs):
            return self._json(403, {"error": "token required"})

        if url.path == "/api":
            return self._json(200, {
                "service": "deploy_service",
                "version": VERSION,
                "endpoints": ["/api/deploy/start", "/api/deploy/status",
                              "/api/deploy/rollback", "/api/deploy/history"],
            })

        if url.path == "/api/deploy/status":
            return self._json(200, CURRENT_DEPLOY)

        if url.path == "/api/deploy/history":
            return self._json(200, {"history": DEPLOY_HISTORY[-20:]})

        return self._json(404, {"error": "not found"})


def main():
    print(f"[deploy_service] Starting on port {PORT}")
    with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
```

**systemd unit** (`/etc/systemd/system/deploy_service.service`):
```ini
[Unit]
Description=Deploy Service (V007.65)
After=network.target

[Service]
Type=simple
User=root
ExecStart=/opt/miniconda3-py39/bin/python -u /opt/app/shared/deploy_service.py
Environment="DEPLOY_SERVICE_PORT=9205"
Environment="DEPLOY_SERVICE_SECRET=v007.65-deploy"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 6.3 6 状态机流程

```
idle → received (POST /api/deploy/start)
     → uploading (开始接收 zip)
     → uploaded (zip MD5 验证)
     → extracting (解压)
     → extracted (解压完成)
     → verifying (post_deploy_check)
     → verified (验证通过)
     → switching (切 current 链接)
     → switched (切完成, 部署成功)

任何一步失败:
     → failed (终止)

rollback 流程:
     → rolling_back
     → rolled_back
```

### 6.4 集成点

**post_deploy_check.py 集成**:
```bash
# 部署后自动调用
curl -X POST "http://yonaa:9205/api/deploy/verify?token=..."
```

**AI 客户端使用**:
```python
# 1. 启动部署
requests.post("http://yonaa:9205/api/deploy/start?token=...",
              json={"version": "v20260714_001", "zip_path": "/opt/app/deploy-v*.zip"})
# 2. 查状态
requests.get("http://yonaa:9205/api/deploy/status?token=...")
# 3. 回滚
requests.post("http://yonaa:9205/api/deploy/rollback?token=...",
              json={"target_version": "v20260713_008", "confirm": "yes-i-know"})
```

### 6.5 验收标准

- [ ] 9205 端口监听
- [ ] POST /api/deploy/start 启动后台线程
- [ ] 状态机 11 状态正确转换
- [ ] GET /api/deploy/status 实时状态
- [ ] POST /api/deploy/rollback 需 confirm=yes-i-know
- [ ] GET /api/deploy/history 最近 20 条
- [ ] systemd unit 启动 OK
- [ ] 真实部署测试 (start → status → 完成)

---

## 七、L15 monitor_prod.py 演进 (P1, 0.5d)

### 7.1 问题

`monitor_prod.py` 还在用 `/api/services/status` (旧端点), 但:
- core_service V2.0 已拆分到 config_service (端口 9203)
- L8.8 isolation_check 端点未集成
- L13.4 audit 覆盖率未集成
- L17 部署后自动监控未集成

### 7.2 方案

**升级 monitor_prod.py** 集成:

```python
# 新增 section
def check_config_service():
    code, body = http(f'http://{YONAA}:9203/api?token={get_token("v007.52-config")}')
    section("config_service (L15.1)", ok=code == 200, detail=body[:200].decode())

def check_isolation():
    """L8.8 集成"""
    code, body = http(f'http://{YONAA}:9200/api/isolation_check?token={get_token("v007.52-core")}')
    if code == 200:
        data = json.loads(body)
        warn = data.get("isolation_warning", False)
        section("isolation_check (L8.8)", ok=not warn,
                detail=f"isolated={data.get('tmp_isolated')}, systemd={data.get('systemd_private_tmp')}")
    else:
        section("isolation_check (L8.8)", ok=False, detail=f"HTTP {code}")

def check_audit_coverage():
    """L13.4 集成"""
    # 通过 SSH/scp 调用 audit_coverage_check.py
    # 或通过 dbops_service /api/audit_coverage (L13.4 升级)
    out = exec_remote("python3 /opt/app/shared/audit_coverage_check.py --days 30 --json")
    if 'error' in out:
        section("audit_coverage (L13.4)", ok=False, detail=str(out))
        return
    try:
        report = json.loads(out)
        ov = report.get("overall", {})
        ok = ov.get("fail", 0) == 0
        section("audit_coverage (L13.4)", ok=ok,
                detail=f"ok={ov.get('ok', 0)} warn={ov.get('warn', 0)} fail={ov.get('fail', 0)}")
    except Exception as e:
        section("audit_coverage (L13.4)", ok=False, detail=str(e))

def check_post_deploy():
    """L17 集成 - 跑 post_deploy_check"""
    out = exec_remote("python3 /opt/app/shared/post_deploy_check.py --skip-l3 --json 2>&1 | tail -30")
    if 'error' in out:
        section("post_deploy_check (L17)", ok=False, detail="check failed")
    else:
        # 解析 JSON
        try:
            # 找 json 部分
            for line in out.split('\n')[::-1]:
                if line.strip().startswith('{'):
                    report = json.loads(line)
                    break
            drift = report.get("drift", 0)
            section("post_deploy_check (L17)", ok=drift == 0,
                    detail=f"drift={drift}")
        except Exception as e:
            section("post_deploy_check (L17)", ok=True, detail="passed (text mode)")

# 主流程改为:
if __name__ == "__main__":
    # ... 现有检查
    check_config_service()      # L15.1
    check_isolation()            # L8.8
    check_audit_coverage()       # L15.3 (L13.4 集成)
    check_post_deploy()          # L15.2 (L17 集成)
```

### 7.3 8 项核心检查 (升级后)

| # | 检查项 | 端点 | 优先级 |
|---|--------|------|--------|
| 1 | log_service 健康 | 9101 /api/health | P0 |
| 2 | core_service HTTPS | 9200 /api | P0 |
| 3 | **config_service** (L15.1) | 9203 /api | P0 |
| 4 | **dbops_service** (L13.3) | 9204 /api | P0 |
| 5 | **isolation_check** (L8.8) | 9200 /api/isolation_check | P1 |
| 6 | **audit_coverage** (L15.3) | dbops_service + audit_coverage_check.py | P1 |
| 7 | **post_deploy_check** (L15.2) | L17 部署后自动 | P1 |
| 8 | ops_scheduler 任务状态 | 9202 /api/tasks | P1 |

### 7.4 验收标准

- [ ] 监控脚本默认包含 8 项检查
- [ ] L15.1 config_service 集成
- [ ] L15.2 post_deploy_check 集成
- [ ] L15.3 audit 覆盖率集成
- [ ] L8.8 isolation_check 集成
- [ ] 输出报告含每项 ok/fail + 详情

---

## 八、文件结构总结

### 新增文件 (7 个)

```
tools/
├── unzip_safe.py                     # [L8.6] magic number 检测
├── audit_coverage_check.py           # [L13.4] 覆盖率检测
├── dbops_service.py                  # [L13.3] 9204 audit_recovery API
├── deploy_service.py                 # [L14] 9205 部署编排
├── core_service.py                   # [L8.8] 加 /api/isolation_check
│                                     # [L12] 加 /api/exec/session/*
└── tests/
    └── test_*.py                     # 单元测试

deploy_bundle/
└── lib/
    └── (deploy.sh 集成 unzip_safe)

monitor_prod.py                       # [L15] 演进
```

### 修改文件 (4 个)

```
tools/core_service.py                # L8.8 + L12
deploy_bundle/deploy.sh              # L8.6 集成
tools/post_deploy_check.py           # L13.4 集成
monitor_prod.py                      # L15
```

---

## 九、实施顺序 (按依赖关系)

| Day | 任务 | 关联 |
|-----|------|------|
| **Day 1 上午** | L8.6 unzip_safe.py | 独立 |
| **Day 1 下午** | L8.8 /api/isolation_check | 依赖 core_service |
| **Day 2 上午** | L12 /api/exec/session | 依赖 core_service |
| **Day 2 下午** | L13.3 dbops_service.py | 依赖 audit_recovery (已有) |
| **Day 3** | L13.4 audit_coverage_check.py | 独立 |
| **Day 4** | L15 monitor_prod.py 演进 | 依赖 L8.8/L13.4 |
| **Day 5-7** | L14 deploy_service.py | 依赖所有其他 |

**总工作量**: 6.5-8.5d (含 L14)

---

## 十、关联文档

- [TODO_LONGTERM.md](../../TODO_LONGTERM.md) - 长期 todo 列表
- [rebuild_zip.py](../../../tools/rebuild_zip.py) - 打包工具
- [core_service.py](../../../tools/core_service.py) - 核心服务 (L8.8/L12 改造点)
- [audit_recovery.py](../../../tools/audit_recovery.py) - 恢复框架 (L13.3 集成)
- [post_deploy_check.py](../../../tools/post_deploy_check.py) - 部署验证 (L13.4 集成点)
- [monitor_prod.py](../../../../monitor_prod.py) - 监控脚本 (L15 演进)
- [smart-delta-deploy-design.md](./2026-07-14-smart-delta-deploy-design.md) - 关联 spec

---

## 十一、CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|---------|
| 2026-07-14 | AI Assistant | 初稿: 7 项未实现 todo 的细化 spec (基于 TODO_LONGTERM.md + 实际代码上下文) |

---

## 十二、待用户决策

| # | 问题 | 建议 |
|---|------|------|
| 1 | 实施顺序 (按依赖 vs 按优先级) | ✅ 按依赖 (Day 1-7 顺序) |
| 2 | L14 deploy_service 是否拆分 2 个 PR | ✅ 拆: PR1 = 接口 + 状态机, PR2 = 集成 |
| 3 | L13.3 dbops_service 用 9204 (现有) 还是新端口 | ✅ 用 9204 (不增端口) |
| 4 | L15 监控输出格式 (text vs json) | ✅ 兼容两者 (--json) |
| 5 | 是否同时实现多个 (并行) | 串行更稳 (前 4 项互相独立可并行) |

**请回复后开始实施。**
