# OPS_MANUAL — yonaa 远程运维服务智能体使用手册

> **面向**: AI Agent / 自动化运维工具
> **目的**: 让智能体快速了解 yonaa 生产服务器上所有运维服务的功能、端点、token、典型使用场景
> **更新**: 2026-07-16 — 加 §十一 告警与监控 (V007.58-V007.61)
> **适用版本**: log_service v4.11 / alert_monitor_v0760 / Windows Task Scheduler

---

## 〇、TL;DR — 智能体快速参考

**yonaa 服务器**: `172.20.59.7` (CentOS 7.5, 无 SSH 访问)

### 0.1 完整端口架构 (2026-07-14 实测)

**生产环境 (prod)** — 用户/AI 真实使用:

| 服务 | 端口 | 进程 | 核心用途 | 备注 |
|------|------|------|---------|------|
| **unified_8081** | 8081 | /tmp/unified_8081.py | 前端代理 (HTML + 静态 + API 代理) | ★ 浏览器入口 |
| **server.py** | 3011 | /opt/app/deployments/meta/server.py | 后端 Flask API | cwd=/opt/app/deployments/meta |
| **log_service** | 9101 | log_service.py | 部署/上传/命令执行/磁盘监控/日志 | ★ 运维主入口 |
| **core_service** | 9200 | core_service.py | 纯 JSON API (HTTPS 自签) | 数据 CRUD |

**staging 环境** — 测试/演练:

| 服务 | 端口 | 进程 | 核心用途 | 备注 |
|------|------|------|---------|------|
| **unified_18081** | 18081 | /opt/app/staging/bin/unified_18081.py | 前端代理 | ★ staging 浏览器入口 |
| **server.py** | 13011 | /opt/app/staging/deploy/current/server.py | 后端 Flask API | cwd=/opt/app/staging/deploy/current |
| **log_service** | 19101 | log_service.py (staging) | staging 运维 | 与 prod 隔离 |
| **core_service** | 19200 | core_service.py (staging) | staging 数据 CRUD | 与 prod 隔离 |

**其他服务** (可能未运行，需确认):

| 服务 | 端口 | 核心用途 | 默认 Token Secret | 状态 |
|------|------|---------|-----------------|------|
| observability_service | 9201 | 上传/指标/告警 | `v007.52-core-write` | ⚠️ 2026-07-14 未检测到监听 |
| ops_scheduler | 9202 | 定时任务调度 | `v007.61-ops` | ⚠️ 2026-07-14 未检测到监听 |
| health_supervisor | 9206 | 服务健康监控 + 自愈 | `v007.62-supervisor` | ⚠️ 2026-07-14 未检测到监听 |

### 0.2 DB 路径

| 环境 | db 路径 | 说明 |
|------|---------|------|
| prod | `/opt/app/deployments/meta/architecture.db` | 直接文件 |
| staging | `/opt/app/staging/meta/architecture.db` | V007.50: deploy/current/architecture.db 是 symlink 指向这里 |

### 0.3 Token 生成公式
```python
import hashlib, time
h = int(time.time()) // 3600
token = hashlib.sha256(f"{SECRET}:{h}".encode()).hexdigest()[:16]
# 或 ±1 小时偏移容错: for off in [-1, 0, 1]
```

---

## 一、log_service (端口 9101) — ★ 运维主入口

### 1.1 服务定位

`log_service` 是 yonaa 上**功能最全**的运维服务，承担:
- 远程命令执行 (`/api/exec`)
- 远程文件上传 (`/api/upload`)
- 数据库查询 (`/api/db/query`, `/api/sqlite`)
- 磁盘 I/O 健康 (`/api/disk/check`, `/api/disk/errors`)
- 日志查询 (`/api/log`, `/api/log/range`)
- 部署检查 (`/api/deploy/*`)
- 服务监督 (`/api/service/supervisor`)

### 1.2 鉴权

- **默认 secret**: `v007.35-infra` (环境变量 `LOG_SERVICE_SECRET`)
- **算法**: `SHA256(secret:hour)[:16]`
- **容错**: ±1 小时窗口 (3 个有效 token)

```python
import urllib.request, urllib.parse, hashlib, time

h = int(time.time()) // 3600
token = hashlib.sha256(f"v007.35-infra:{h}".encode()).hexdigest()[:16]
url = f'http://172.20.59.7:9101/api/exec?cmd=ls&token={token}'
```

### 1.3 核心端点 (智能体最常用)

| 端点 | 用途 | 调用示例 |
|------|------|---------|
| `GET /api` | 服务自描述 (43 个端点) | `curl 9101/api` |
| `GET /api/health` | 服务健康 | `curl 9101/api/health` |
| `GET /api/exec?cmd=...&token=...` | 远程命令执行 (白名单) | `cmd=ls+-la+/tmp` |
| `POST /api/exec` | 同上 (body 传 cmd, 适合长命令) | `{"cmd": "...", "timeout": 30}` |
| `GET /api/disk/check?quick=true` | SQLite 4 信号健康检查 | score 0-100 |
| `GET /api/disk/errors?hours=24` | dmesg I/O 错误扫描 | 返回错误列表 |
| `GET /api/log/range?file=...&start=...&end=...` | 按行范围读日志 | 远程日志分析 |
| `GET /api/db/query?sql=...` | 只读 SQL 查询 (白名单表) | 元模型元数据 |
| `GET /api/upload` | 上传文件说明 (POST 才是上传) | multipart/form-data |
| `GET /api/service/supervisor?action=status&token=...` | 服务状态 | 列出 meta_server/unified |
| `GET /api/service/supervisor?action=restart&name=meta_server&token=...` | 重启后端 | ⚠ 慎用, 见 1.4 |

### 1.4 ⚠ 已知陷阱

**陷阱 1: `/api/service/supervisor?action=restart` 会误杀 Python**

```python
# log_service.py:1766
subprocess.run(["pkill", "-9", "-f", svc["cmd"].split()[0]], capture_output=True, timeout=5)
# svc["cmd"] = "/opt/miniconda3-py39/bin/python -u /opt/app/deployments/meta/server.py"
# cmd.split()[0] = "/opt/miniconda3-py39/bin/python"
# pkill -9 -f /opt/miniconda3-py39/bin/python → 杀掉所有 conda python 进程！
```

**包括 log_service 自己！** 会导致:
- log_service 9101 端口丢失
- core_service 9200 端口丢失
- ops_scheduler 9202 也丢失 (基于 stdlib 不影响)

**恢复方式**: watchdog cron 会自动拉起 (约 1-5 分钟)。

**推荐做法**: 用 `/api/exec` 直接 kill 特定 PID:
```bash
# 找到 meta_server 的 PID
ps -ef | grep server.py | grep -v grep | awk '{print $2}'
# 然后用 pkill -9 -f server.py (精准匹配命令行)
pkill -9 -f "deployments/meta/server.py"
# 然后启动新的
nohup /opt/miniconda3-py39/bin/python -u /opt/app/deployments/meta/server.py > /tmp/server.log 2>&1 &
```

**陷阱 2: `/api/exec` 命令白名单**

```python
EXEC_WHITELIST = [
    "ls", "cat", "head", "tail", "wc", "find", "grep", "du", "df",
    "ps", "top", "ss", "netstat", "curl", "wget",
    "systemctl", "journalctl", "dmesg", "iostat", "vmstat", "free",
    "echo", "date", "whoami", "id", "uname", "hostname",
    "chmod", "chown", "mkdir", "cp", "mv", "ln", "touch",
    "python3", "python", "pip3", "pip",
    "sqlite3", "md5sum", "sha256sum",
    "pkill", "kill", "killall",
    "bash", "sh", "unzip", "tar", "nohup",
    "sed", "awk", "sort", "uniq", "tr", "cut", "tee",
    "test", "true", "false", "sleep",
    "source", ".",
]
```

不在白名单的命令返回 403。`systemctl` 在白名单但生产环境可能无权限。

**陷阱 3: `/api/db/query` 只读 + 表白名单**

只能查询以下表 (来自历史代码):
- `architecture.db` 中部分只读元数据表

---

## 二、core_service (端口 9200) — 数据 CRUD API

### 2.1 服务定位

- **协议**: HTTPS (自签证书, 需 `-k` 跳过验证)
- **功能**: 纯 JSON API 后端, 业务 CRUD
- **路径**: `/api/v1/*` 和 `/api/v2/*`

### 2.2 ⚠ 已知问题

**core_service 经常连接断开** (`WinError 10054` 远程主机强迫关闭)
- 原因: HTTPS 自签证书 + 长连接 keepalive 不稳定
- 解决: 单次请求, 不要复用连接; 或加 retry

```python
import urllib.request, ssl
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
# 但通过 unified_server:8081 代理访问更稳定
url = 'http://172.20.59.7:8081/api/v2/bo/...'  # 推荐
```

### 2.3 智能体调用建议

- **不要直接调 9200**, 走 **unified_server 8081** 代理 (`/api/*` 转发到 5001 后端)
- unified_server (8081) 也代理 core_service (9200), 但通常用 backend on 3011
- **生产 API 调用统一走 8081**

---

## 三、observability_service (端口 9201) — 上传主入口

### 3.1 服务定位

- **核心用途**: `POST /api/upload_multi` 远程部署文件上传 (替代 SSH scp)
- **其他**: `/api/health`, `/api/ready`, `/api/metrics`

### 3.2 鉴权

- **Secret**: `v007.52-core-write` (环境变量 `OBSERVABILITY_SECRET`)
- **Token**: 同样 SHA256[:16]

### 3.3 上传协议 (`POST /api/upload_multi`)

```python
import urllib.request, json

# 单文件上传 (base64 编码)
payload = {
    "files": [
        {
            "remote_path": "/opt/app/deployments/meta/scripts/init_menu_permissions.py",
            "content_b64": "<base64 encoded content>"
        }
    ]
}

req = urllib.request.Request(
    'http://172.20.59.7:9201/api/upload_multi',
    data=json.dumps(payload).encode('utf-8'),
    headers={
        'Content-Type': 'application/json',
        'Authorization': 'Bearer <token>'
    },
    method='POST'
)
```

**批量上传工具**: `tools/batch_upload.py`
- 前端文件按 10 个/批上传 (避免单请求过大)
- 后端 Python 文件单文件上传

### 3.4 ⚠ 已知陷阱

- **base64 编码大小**: 单请求 base64 解码后建议 < 5MB
- **路径必须以 `/` 开头**: `remote_path` 必须绝对路径
- **observability 端口经常挂掉**: 早些天发现 pkill 误杀, watchdog 拉起后可用

---

## 四、ops_scheduler (端口 9202) — 定时任务调度器

### 4.1 服务定位

- **核心用途**: 周期性运维任务调度 (8 个预置任务)
- **实现**: stdlib http.server, 单进程, 无外部依赖
- **可靠性**: ★★★★★ (无第三方依赖, 几乎不会挂)

### 4.2 鉴权

- **Secret**: `v007.61-ops`
- **算法**: 相同 SHA256[:16]

### 4.3 端点

| 端点 | 用途 |
|------|------|
| `GET /api` | 服务自描述 |
| `GET /api/tasks` | 列出 8 个任务及状态 |
| `GET /api/tasks/:name/run` | 立即执行指定任务 |
| `GET /api/tasks/:name/log` | 任务执行日志 |
| `GET /api/history?n=50` | 最近执行历史 |

### 4.4 预置任务清单

| 任务 | 间隔 | 命令 |
|------|------|------|
| `db_backup` | 6h | `/bin/bash /opt/app/shared/db_backup.sh` |
| `health_inspect` | 30m | `curl -sf http://127.0.0.1:9101/api/health/inspect` |
| `disk_forecast` | 1h | `curl -sf http://127.0.0.1:9101/api/disk/forecast` |
| `disk_io_check` | 5m | `curl -sf 'http://127.0.0.1:9101/api/disk/check?quick=true'` |
| `log_archive` | 1d | `curl -sf 'http://127.0.0.1:9101/api/log/archive?...'` |
| `db_vacuum` | 1w | VACUUM |
| `backup_cleanup` | 1d | 清理 7 天前备份 |
| `ssl_check` | 1d | SSL 证书过期检查 |

### 4.5 智能体使用模式

```python
# 检查任务状态
import urllib.request, urllib.parse, hashlib, time

token = hashlib.sha256(f"v007.61-ops:{int(time.time())//3600}".encode()).hexdigest()[:16]
url = f'http://172.20.59.7:9202/api/tasks?token={token}'
data = json.loads(urllib.request.urlopen(url, timeout=10).read())
for name, info in data['tasks'].items():
    print(f"{name}: last_run={info['last_run']}, exit={info['last_exit']}")

# 手动触发 disk_io_check
url = f'http://172.20.59.7:9202/api/tasks/disk_io_check/run?token={token}'
urllib.request.urlopen(url, timeout=10)
```

**注意**: 没有"添加新任务"端点, 新增任务需修改 `tools/ops_scheduler_v1.1.py` 然后部署。

---

## 五、health_supervisor (端口 9206) — 服务健康监控 + 自愈

### 5.1 服务定位

- **监控**: 5 个核心服务 (frontend, backend, meta_server, unified, log_service)
- **自愈**: 检测到服务异常可触发 `/api/supervisor/heal`
- **数据收集**: heartbeat, slow, performance, latency

### 5.2 鉴权

- **Secret**: `v007.62-supervisor`

### 5.3 端点

| 端点 | 用途 |
|------|------|
| `GET /api/supervisor/services` | 列出被监控服务 |
| `GET /api/supervisor/heartbeat` | 服务心跳 |
| `GET /api/supervisor/slow` | 慢请求 |
| `GET /api/supervisor/performance` | 性能数据 |
| `GET /api/supervisor/latency` | 延迟数据 |
| `GET /api/supervisor/health` | 总健康状态 |
| `POST /api/supervisor/heal` | 触发自愈 |

### 5.4 ⚠ 已知陷阱

- **heal 端点 token 经常不匹配**: 历史日志中频繁 403, 真实 secret 待确认
- **推荐做法**: 用 `log_service /api/service/supervisor` 替代 (功能重叠)

---

## 六、典型运维任务的标准操作 (SOP)

### 6.1 部署代码到 yonaa

```python
# 1. 前端构建 (本地)
npm run build  # 生成 dist/

# 2. 后端上传
from tools.batch_upload import upload_batch
upload_batch('meta/core/interceptors/write_scope_interceptor.py', secret='v007.52-core-write')

# 3. 前端批量上传
upload_batch('dist/assets/index-*.js', secret='v007.52-core-write')

# 4. 重启后端 (用 exec 精准 kill)
import urllib.request, urllib.parse, hashlib, time
token = hashlib.sha256(f"v007.35-infra:{int(time.time())//3600}".encode()).hexdigest()[:16]
# 找 PID
cmd = "ps -ef | grep 'deployments/meta/server.py' | grep -v grep | awk '{print $2}'"
url = f'http://172.20.59.7:9101/api/exec?cmd={urllib.parse.quote(cmd)}&token={token}'
pids = urllib.request.urlopen(url).read().decode()
# 杀 + 启
cmd2 = f"kill -9 {pids}; nohup /opt/miniconda3-py39/bin/python -u /opt/app/deployments/meta/server.py > /tmp/server.log 2>&1 &"
url2 = f'http://172.20.59.7:9101/api/exec?cmd={urllib.parse.quote(cmd2)}&token={token}'
urllib.request.urlopen(url2)
```

### 6.2 数据库健康巡检

```python
# 4 信号健康检查
url = 'http://172.20.59.7:9101/api/disk/check?quick=true'
data = json.loads(urllib.request.urlopen(url).read())
print(f"Score: {data['score']}, Status: {data['status']}")

# 详细 I/O 错误
url = 'http://172.20.59.7:9101/api/disk/errors?hours=24'
data = json.loads(urllib.request.urlopen(url).read())
print(f"I/O errors in 24h: {len(data['errors'])}")
```

### 6.3 服务健康检查

```python
services = {
    'log_service':      9101,
    'core_service':     9200,
    'observability':    9201,
    'ops_scheduler':    9202,
    'health_supervisor': 9206,
    'unified_server':   8081,
    'backend (via 8081)': 8081,  # /api/v1/auth/dev-login
}

for name, port in services.items():
    url = f'http://172.20.59.7:{port}/api' if port != 8081 else 'http://172.20.59.7:8081/api/v1/auth/dev-login?username=admin'
    try:
        resp = urllib.request.urlopen(url, timeout=5)
        print(f"  [OK] {name}: {resp.status}")
    except Exception as e:
        print(f"  [DOWN] {name}: {e}")
```

### 6.4 查看日志

```python
# 按行范围读日志 (推荐: 比 cat 高效)
url = 'http://172.20.59.7:9101/api/log/range?file=/tmp/server.log&start=-200&end='
data = json.loads(urllib.request.urlopen(url).read())
for line in data.get('lines', []):
    print(line)
```

### 6.5 数据迁移 (如 init_menu_permissions)

```python
# 1. 上传修复脚本到 /tmp
# 2. exec 执行
cmd = '/opt/miniconda3-py39/bin/python3 /tmp/fix_perm.py'
token = hashlib.sha256(f"v007.35-infra:{int(time.time())//3600}".encode()).hexdigest()[:16]
url = f'http://172.20.59.7:9101/api/exec?cmd={urllib.parse.quote(cmd)}&token={token}&timeout=30'
result = json.loads(urllib.request.urlopen(url).read())
print(result['stdout'])
```

---

## 七、智能体使用规则 (铁律)

### 7.1 严禁

- ✗ 不要 SSH 到 yonaa (无访问通道)
- ✗ 不要直接调 core_service 9200 (走 8081 代理)
- ✗ 不要用 `/api/service/supervisor?action=restart` (会误杀所有 python)
- ✗ 不要在 log_service 上执行 `systemctl` (无权限)
- ✗ 不要假设 obs_scheduler/log_service 一定在线 (可能被 watchdog 拉起中)

### 7.2 必须

- ✓ 所有 API 调用必须带 token (除 log_service 部分只读端点外)
- ✓ Token 必须支持 ±1 小时偏移 (避免边界 bug)
- ✓ 所有写操作 (上传/执行) 必须先备份
- ✓ 部署后必须用 `health_check.py` 验证 5 个核心服务

### 7.3 推荐工具

- `d:\filework\worktrees/release-prep\tools\batch_upload.py` — 批量上传
- `d:\filework\worktrees/release-prep\tools\log_service.py` — log_service 源码 (端点参考)
- `d:\filework\worktrees/release-prep\tools\ops_scheduler_v1.1.py` — 调度器源码

---

## 八、Token 速查表

| Secret | 用途 | 算法 |
|--------|------|------|
| `v007.35-infra` | log_service (9101) | SHA256(secret:hour)[:16] |
| `v007.52-core-write` | observability (9201) | 同上 |
| `v007.61-ops` | ops_scheduler (9202) | 同上 |
| `v007.62-supervisor` | health_supervisor (9206) | 同上 |

**Token 模板**:
```python
def get_token(secret: str) -> str:
    """获取当前小时有效 token, 含 ±1h 容错"""
    tokens = []
    h = int(time.time()) // 3600
    for off in [-1, 0, 1]:
        h2 = h + off
        tokens.append(hashlib.sha256(f"{secret}:{h2}".encode()).hexdigest()[:16])
    return tokens
```

---

## 九、文件位置速查

### 9.1 服务端 (yonaa `/opt/app/`)

```
/opt/app/
├── deployments/
│   ├── meta/                          # 后端代码
│   │   ├── server.py                  # 主入口
│   │   ├── architecture.db            # 主数据库
│   │   ├── core/interceptors/        # 拦截器 (BUG 修复集中地)
│   │   ├── scripts/init_*.py          # 初始化脚本
│   │   └── ...
│   └── frontend_dist_files/           # 前端 dist/
├── shared/
│   ├── ops_scheduler.py               # 调度器进程
│   ├── db_backup.sh                   # 数据库备份脚本
│   └── logs/scheduler.jsonl           # 调度日志
└── ...
```

### 9.2 本地工作区

```
d:\filework\worktrees/release-prep\
├── meta/                              # 后端代码 (源)
├── dist/                              # 前端构建产物
├── tools/
│   ├── batch_upload.py                # ★ 批量上传工具
│   ├── log_service.py                 # log_service 源码
│   ├── core_service.py                # core_service 源码
│   ├── observability_service.py       # observability 源码
│   ├── ops_scheduler_v1.1.py          # 调度器源码
│   └── ...
├── deploy_bundle/                     # 部署包 (上传用)
└── docs/
    ├── OPS_MANUAL.md                  # ★ 本文档
    ├── HANDOFF_*.md                   # 历史交付文档
    └── ...
```

---

## 十、变更日志

| 日期 | 变更 |
|------|------|
| 2026-07-12 | 创建本文档 (基于今日运维经验) |

---

**维护者**: AI Agent 协作时持续完善  
**反馈**: 发现新陷阱请更新本文档 §7

---

## 十一、告警与监控 (V007.58 ~ V007.61, 2026-07-16 新增)

> **重要**: 这台 Windows PC 是 Agent/运维服务机器 (有公网). yonaa 在阿里云 air-gapped 环境, 服务器本身无法直接推送 IM, 所以监控/告警架构是: yonaa ←(轮询)← Windows PC → 飞书 HAO 群.

### 11.1 整体架构

```
┌──────────────────────┐    每5min     ┌──────────────────────┐    HTTP    ┌──────────────┐
│  172.20.59.7 yonaa   │  ◄──poll──   │  这台 Windows PC     │ ──push──► │ 飞书 HAO 群  │
│  9101 log_service    │              │  yonaa_alert_monitor │  lark_app  │ (运维手机)   │
│  19101 staging log_s │              │  (Task Scheduler)   │            │              │
│  9200/19200 core     │              │  alert_monitor_v0760 │            │              │
│  9201 observability  │              │  + 9 项分层检查      │            │              │
│  8081 frontend       │              │  + HKCU 凭证回退     │            │              │
│  3011 backend        │              │                      │            │              │
└──────────────────────┘              └──────────────────────┘            └──────────────┘
```

### 11.2 9 项分层监控 (alert_monitor_v0760.py)

| 检查项 | 分层 | 监控什么 | 阈值 |
|--------|------|----------|------|
| `real_health` | L1 5min | log_service `/api/health` 业务 ok | `{"ok":true}` |
| `db_can_write` | L1 5min | SQLite 写权限 (锁/权限) | can_write=true |
| `journal_err` | L1 5min | journalctl ERROR/Traceback | >5 告警 |
| `backend_err` | L1 5min | backend.log HTTP 5xx + Traceback | **按接口+类型分组**, >3 告警 |
| `core_service_err` | L1 5min | core_service.log Traceback | **按类型分组**, >1 告警 |
| `db_health` | L2 15min | SQLite integrity + WAL | integrity=ok, WAL<100MB |
| `disk_errors` | L2 15min | dmesg + iostat | total_errors=0 |
| `disk_check` | L3 30min | 综合磁盘打分 | score>=80 |
| `disk_usage` | L3 30min | 磁盘使用率 | >85% warn, >95% fail |

### 11.3 飞书告警消息长什么样

**告警** (红色卡片, @全体):

```
[ALERT] yonaa 2 服务异常

✗ backend_err:prod: 7 errors in 5min (>2 threshold):
  POST /api/v2/bo/save -> 500 (3x)
  POST /api/v2/bo/import -> 502 (2x)
  sqlalchemy.exc.IntegrityError (1x)
  KeyError (1x)

✗ disk_usage:log_service:prod: WARNING used=85.3% free=7.2GB total=48.8GB

yonaa agent alert · 2026-07-16 12:18:30
```

**恢复** (蓝色卡片):

```
[RECOVERY] yonaa 监控恢复

✓ 之前告警的服务已恢复正常:
  - backend_err:prod
  - disk_usage:log_service:prod

yonaa agent alert · 2026-07-16 12:20:15
```

### 11.4 日常运维命令 (Windows PC)

```powershell
# 查看任务计划状态
schtasks /query /tn "yonaa_alert_monitor" /fo LIST

# 手动跑一次 (测试用)
schtasks /run /tn "yonaa_alert_monitor"

# 查看最近运行日志
Get-Content d:\filework\worktrees/release-prep\tools\alert_monitor_v0760.log -Tail 30

# 列出所有 9 项检查
python d:\filework\worktrees/release-prep\tools\alert_monitor_v0760.py --list-checks

# 单跑一项检查
python d:\filework\worktrees/release-prep\tools\alert_monitor_v0760.py --check-one backend_err

# 强制跑全部 (不管 interval)
python d:\filework\worktrees/release-prep\tools\alert_monitor_v0760.py --check-now --force

# 停 / 启 / 卸载任务
schtasks /change /tn "yonaa_alert_monitor" /disable
schtasks /change /tn "yonaa_alert_monitor" /enable
schtasks /delete /tn "yonaa_alert_monitor" /f
```

### 11.5 重设飞书凭证 (写到 HKCU)

凭证写在 HKCU 环境变量 (`LARK_APP_ID` / `LARK_APP_SECRET` / `LARK_CHAT_ID`), Python 自动从注册表读. **不在 git 里, 不在 config 文件里**.

```powershell
# 编辑 _setup_lark_env.ps1, 替换 3 个值为新凭证, 然后:
powershell -ExecutionPolicy Bypass -File d:\filework\worktrees/release-prep\tools\_setup_lark_env.ps1
```

> 申请新飞书 App Bot 凭证的 7 步流程见 [INCIDENT_ALERT_SETUP.md](INCIDENT_ALERT_SETUP.md) §1.

### 11.6 故障排查速查

| 现象 | 排查 |
|------|------|
| 任务计划跑但飞书收不到 | 1) `schtasks /query` 看上次结果码; 2) `Get-Content alert_monitor_v0760.log -Tail 20` 看 [IM] 行; 3) `python ... --check-now --force` 手动跑 |
| 飞书推了但内容错乱 | 检查 `alert_monitor_config.json` 的 `default` 字段 (`lark_app`), 不是 `feishu`/`dingtalk` |
| 一直告警恢复不了 | 检查 state: `Get-Content alert_monitor_config_state.json`; failed_keys 是否还有; cooldown 默认 600s |
| V007.61 用户异常报 404 一堆 | 是的, 我们**故意过滤** 404/405/ConnectionReset — 它们是噪音, 不告警 |
| 想临时压低阈值 | `BACKEND_ERR_THRESHOLD=10 python ... --check-now --force` |

### 11.7 关键文件清单

| 文件 | 作用 |
|------|------|
| [alert_monitor_v0760.py](../../tools/alert_monitor_v0760.py) | 主监控 (9 项检查, 分层调度) |
| [alert_monitor_v0760.bat](../../tools/alert_monitor_v0760.bat) | Task Scheduler 入口 |
| [yonaa_alert_monitor_v0760.xml](../../tools/yonaa_alert_monitor_v0760.xml) | 任务定义 |
| [alert_monitor_config.json](../../tools/alert_monitor_config.json) | 配置 (含 lark_app 占位符) |
| [alert_monitor_config_state.json](../../tools/alert_monitor_config_state.json) | 状态 (失败追踪 + cooldown) |
| [alert_monitor_v0760.log](../../tools/alert_monitor_v0760.log) | 运行日志 |
| [_setup_lark_env.ps1](../../tools/_setup_lark_env.ps1) | 重设 HKCU 凭证 |

---

## 十二、变更日志

| 日期 | 变更 |
|------|------|
| 2026-07-12 | 创建本文档 (基于今日运维经验) |
| 2026-07-16 | 加 §十一 告警与监控 (V007.58-V007.61: 飞书应用机器人 + 9 项分层监控 + V007.61 用户异常分组) |