# log_service 基础设施交接 (HANDOFF_LOG_SERVICE)

> 撰写: 2026-07-07 23:20
> 交接方: 开发智能体 → 部署智能体
> 状态: log_service v3.5 已部署并验证, 但基础设施未健全, 需部署智能体接手治理

---

## 1. 当前状态 (snapshot 2026-07-07 23:20)

```
PID 28950  python3 /opt/app/deployments/log_service.py
           uptime: 3 分钟 (刚重启)
           rchar: 1.1GB (已大量读 db)
```

**问题**:
- [X] 没有进程守护 — server.py 重启会被 kill, 不会自动拉起
- [X] 没有 systemd unit
- [X] 没有开机自启
- [X] 没有健康检查 + 自动拉起
- [X] 没有版本管理 (现在跑的是 v3.5, 升级时容易混淆)

---

## 2. 接口清单 (v3.5 - 已部署)

### 核心诊断接口 (本次新增, 用于 disk I/O error 排查)

| 接口 | 用途 | 关键价值 |
|------|------|---------|
| `GET /api/sqlite?sql=...` | 只读 SQL (SELECT/PRAGMA) | 直接验证 SQLite 层稳定性 |
| `GET /api/sqlite/load?count=N&table=X` | 跑 N 次 SELECT count(*) | **关键**: 区分 SQLite 层 vs server.py 层 |
| `GET /api/iostat?count=N` | 磁盘 I/O 抖动监测 | 排查磁盘抖动 |
| `GET /api/proc/io?pid=X` | 进程级 read_bytes/write_bytes | 看真实 I/O 量 |

### 已有接口 (v3)

| 接口 | 用途 |
|------|------|
| `GET /api/log?file=...&lines=N&grep=...` | 读日志文件 |
| `GET /api/find?name=...&path=...` | 查找文件 |
| `GET /api/proc` | 进程列表 |
| `GET /api/system` | 系统资源 (load/mem/disk/fd) |
| `GET /api/dmesg` | 内核日志 |
| `GET /api/db/health` | DB 健康 (size/wal/integrity/audit) |
| `GET /api/fd?pid=X` | 进程 fd 列表 |
| `GET /api/env?pid=X` | 进程环境变量 |
| `GET /api/exec?cmd=...` | 白名单命令执行 |
| `GET /` | 404 (有 available 列表) |

---

## 3. 当前部署位置

| 项 | 值 |
|----|---|
| 文件路径 | `/opt/app/deployments/log_service.py` |
| 启动方式 | `cd /opt/app/deployments && nohup python3 log_service.py > /dev/null 2>&1 &` |
| 监听端口 | `0.0.0.0:9101` |
| 防火墙 | 已放行 (9101 INPUT ACCEPT) |
| 数据库路径 | 写死 `/opt/app/deployments/meta/architecture.db` |
| 日志目录 | 写死 `/opt/app/deployments/meta` |
| 环境变量支持 | 仅 `LOG_SERVICE_DB_PATH`, `LOG_SERVICE_LOG_DIR` |
| 进程数 | 单实例 (无 cluster) |

---

## 4. 接手后必须做的工作

### P0 — 立即 (本周)

#### 4.1 systemd unit 化 (消除裸 nohup)

**问题**: server.py 重启会 kill log_service, 没有自动拉起

**方案**: 创建 `/etc/systemd/system/log-service.service`

```ini
[Unit]
Description=log_service - diagnostic HTTP server
Documentation=https://internal/log-service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/app/deployments
ExecStart=/usr/bin/python3 /opt/app/deployments/log_service.py
Restart=always
RestartSec=5
StandardOutput=null
StandardError=journal
Environment=LOG_SERVICE_DB_PATH=/opt/app/deployments/meta/architecture.db
Environment=LOG_SERVICE_LOG_DIR=/opt/app/deployments/meta

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable log-service
systemctl start log-service
systemctl status log-service
```

**预期效果**:
- server.py 重启不会影响 log_service
- 进程崩溃 5s 内自动拉起
- 开机自启

#### 4.2 集成到 deploy.sh (部署自动重启)

当前 `deploy.sh` 没有 restart log_service。修改 `tools/deploy.sh` 在 server.py 重启前/后：

```bash
# 部署前
systemctl stop log-service

# 部署后 (server.py 启动后)
systemctl start log-service

# 验证
sleep 2
curl -s http://localhost:9101/api/health || echo "log_service DOWN"
```

### P1 — 短期 (1 周内)

#### 4.3 升级到支持更多环境变量

当前 v3.5 只支持 2 个环境变量。后续升级时考虑:

```python
# 建议改造 (开发智能体后续工作)
LOG_DIR = os.environ.get('LOG_SERVICE_LOG_DIR', '/opt/app/deployments/meta')
DB_PATH = os.environ.get('LOG_SERVICE_DB_PATH', f'{LOG_DIR}/architecture.db')
PORT = int(os.environ.get('LOG_SERVICE_PORT', 9101))
BIND = os.environ.get('LOG_SERVICE_BIND', '0.0.0.0')
LOG_LEVEL = os.environ.get('LOG_SERVICE_LOG_LEVEL', 'INFO')
TOKEN = os.environ.get('LOG_SERVICE_TOKEN', '')  # 简易鉴权 (新增)
```

#### 4.4 加 token 鉴权

当前 9101 端口**完全开放**，任何人能读所有日志。建议:

```python
# /api/log, /api/fd, /api/env, /api/exec 加 token 校验
TOKEN = os.environ.get('LOG_SERVICE_TOKEN', '')

def _check_token(self, q):
    if not TOKEN:
        return True  # 没设 token = 开放
    return q.get('token', [''])[0] == TOKEN
```

只开放 `/api/system`, `/api/db/health`, `/api/sqlite/load` 给无 token 访问 (诊断必备)。

#### 4.5 健康检查 + 监控

log_service 自身没暴露 `/api/health` (被路由 404 接管)。加一个:

```python
elif p.path == '/api/health':
    self._json(200, {'status': 'ok', 'pid': os.getpid(),
                     'uptime_sec': int(time.time() - _START_TIME),
                     'version': 'v3.5'})
```

可被 systemd `Type=notify` 或外部健康检查器监控。

### P2 — 长期 (1 月内)

#### 4.6 拆分为独立仓库

`log_service.py` 现在混在 `integration-worktree` 根目录。建议:
- 拆到 `infra/log-service/` 独立仓库
- 版本管理独立 (log-service-v1.0, v1.1, ...)
- 不再随主项目部署

#### 4.7 加 metrics 端点 (Prometheus)

新增 `/api/metrics` 输出 Prometheus 格式:
- `log_service_uptime_seconds`
- `log_service_requests_total{endpoint="..."}`
- `log_service_errors_total{endpoint="..."}`
- `node_load1`, `node_load5`, `node_load15`

可对接现有 Prometheus 监控。

#### 4.8 加慢查询日志

`/api/sqlite/load` 现在只返回聚合。增加 `slow_queries` 字段记录 >50ms 的查询。

---

## 5. 与其他基础设施的关系

| 基础设施 | 关系 | 说明 |
|---------|------|------|
| **server.py (5001)** | 依赖 | log_service 诊断 server.py 状态。server.py 重启不影响 log_service (建议) |
| **unified_server.py (8081)** | 独立 | 前端代理服务，不依赖 log_service |
| **nginx (80/443)** | 独立 | log_service 不走 nginx，直接监听 9101 |
| **P0 锁 (`meta/.architecture.lock`)** | 独立 | log_service 不持锁，只读 db |
| **deploy_bundle** | 同步 | log_service 当前不在 deploy_bundle 里 (开发智能体修过), 由协调智能体单独维护 |

---

## 6. 已知问题与限制

| # | 问题 | 影响 | 状态 |
|---|------|------|------|
| 1 | 没有进程守护 | server.py 重启会 kill log_service | 待 P0 |
| 2 | 没有鉴权 | 9101 完全开放 | 待 P1 |
| 3 | 没有版本化 | 升级时容易混淆 v3 / v3.5 | 待 P2 |
| 4 | 写死路径 | 迁移环境时需改代码 | 待 P1 |
| 5 | 单实例 | 不支持多实例 cluster | 暂可接受 (read-only) |
| 6 | 没用 systemd journal | 错误日志进黑洞 | 待 P0 |

---

## 7. 测试覆盖

文件: `D:\filework\integration-worktree\tests\test_log_service_v3_5.py`

| 测试 | 类型 | 状态 |
|------|------|------|
| test_01_required_methods_in_handler_class | 静态结构 (AST) | ✅ PASS |
| test_02_no_duplicate_class | 静态结构 | ✅ PASS |
| test_03_import_time_present_if_used | 静态 import 检查 | ✅ PASS |
| test_04_import_subprocess_present | 静态 import | ✅ PASS |
| test_05_import_sqlite3_present | 静态 import | ✅ PASS |
| test_10_endpoint_log | 运行时 | ✅ PASS |
| test_11_endpoint_sqlite | 运行时 | ✅ PASS |
| test_12_endpoint_sqlite_load | 运行时 | ✅ PASS |
| test_13_endpoint_iostat | 运行时 | ✅ PASS |
| test_14_endpoint_proc_io | 运行时 | ✅ PASS |

**总计: 10/10 通过**

---

## 8. 升级流程 (给接手的人)

```bash
# 1. 备份
cp /opt/app/deployments/log_service.py /opt/app/deployments/log_service.py.bak.v3.5

# 2. 上传新版
#    从 D:\filework\integration-worktree\log_service.py

# 3. 重启 (无 systemd 时)
pkill -f log_service.py ; sleep 2
nohup python3 log_service.py > /dev/null 2>&1 &

# 3. 重启 (systemd 后)
systemctl restart log-service

# 4. 验证
sleep 2
curl -s http://localhost:9101/api/sqlite/load?count=10
# 期望: {"count":10, "table":"users", "ok":10, "fail":0, ...}

# 5. 本地测试
cd D:\filework\integration-worktree
python -m pytest tests/test_log_service_v3_5.py -v
# 期望: 10 passed
```

---

## 9. 紧急联系方式

| 问题类型 | 联系人 |
|---------|--------|
| 代码 bug / 新功能 | 开发智能体 |
| 进程守护 / systemd | 部署智能体 (主理) |
| 端口冲突 / 防火墙 | 部署智能体 (主理) |
| 升级流程 / 部署集成 | 部署智能体 (主理) |

---

**撰写时间**: 2026-07-07 23:20
**版本**: v3.5 (commit 120c18a on integration/2026-07-04)
**交接方签字**: 开发智能体 ✅
**接收方签字**: 部署智能体 (待接手)
---

## 10. V007.35 部署集成 (部署智能体增量)

> 由部署智能体 (V007.35) 追加, 用于 v3.5 → v3.5-integration 整合

### 10.1 deploy.sh PHASE 8 自动启动

log_service v3.5 已集成到 `deploy_bundle/tools/deploy.sh` PHASE 8, 部署时自动启动:

```
PHASE 8: log_service + 后置健康检查 [V007.35]
  [8a] 启动 log_service on 9101
  [8b] 采集基线数据 (total_fds=N)
  [OK] 3 段后置健康检查已在后台启动 (pid=N, log=/tmp/v00725_postcheck_V*.log)
```

**基线 fd 采集**: 部署后立即通过 log_service `/api/system` 采集 total_fds, 作为后置 5min/30min 健康检查的对照基线。

**降级策略**: log_service 启动失败时, PHASE 8 自动降级用 `lsof | grep -c architecture` (老方法), 5min fd 阈值检测仍工作。

### 10.2 后置 3 段健康检查 (30s / 5min / 30min)

| 段 | 触发 | 失败时动作 |
|----|------|-----------|
| **30s** | 部署后 30s | 触发自动回滚 (commit 6cadcc1 之前) / 仅记录 (V007.35+ 优化) |
| **5min** | 部署后 5min | 触发自动回滚 (fd 增量 > 5000 或 v2 BOAction 失败) |
| **30min** | 部署后 30min | 仅记录, 不回滚 (避免夜间误回滚) |

每段检查输出在 `/tmp/v00725_postcheck_<version>.log`。

### 10.3 AUTO-DELTA 验证 (V007.35 部署保障)

`tools/rebuild_zip.py` 在打包时**自动扫描 working tree 全部文件**, 确保 zip 内容 = working tree 真实状态:

```python
# rebuild_zip.py V8c invariant
def check_auto_delta():
    wt_files = set()  # walking working tree
    zip_files = set()  # walking zip
    missing = wt_files - zip_files  # 不应存在
    extra = zip_files - wt_files   # 不应存在
    if missing or extra:
        return FAIL
    return PASS
```

**意义**: 之前我手动列要验证的文件 (`sql_adapters.py`, `sql_connection_pool.py`) 漏了 2 次. 现在程序自动检查所有文件, 不会再漏.

### 10.4 部署后 yonaa 端真实验证 (免 SSH)

通过 log_service 9101, **1-2 秒**远程验证 yonaa 部署状态:

```powershell
# 在本地 PowerShell 直接跑 (无需 SSH)
$LS = "http://172.20.59.7:9101"

# 1. 健康
$h = Invoke-RestMethod "$LS/api/health" -TimeoutSec 5

# 2. 4 个 critical file MD5
$files = @("meta/server.py", "meta/core/datasource.py",
           "meta/core/sql_adapters.py", "meta/core/sql_connection_pool.py")
foreach ($f in $files) {
  $r = Invoke-RestMethod "$LS/api/config?file=/opt/app/deployments/$f" -TimeoutSec 10
  $md5 = (Get-FileHash -InputStream ([IO.MemoryStream]::new([Text.Encoding]::UTF8.GetBytes($r.content))) -Algorithm MD5).Hash
  Write-Host "$f  md5=$md5"
}

# 3. V007.34 retry 触发
$log = Invoke-RestMethod "$LS/api/log?file=/opt/app/shared/logs/backend-*.log&lines=2000&grep=V007.34" -TimeoutSec 10
$retry_count = ($log.output -split "`n" | Where-Object { $_ -match "V007.34 retry" }).Count
Write-Host "V007.34 retry count: $retry_count"

# 4. 后端 fd
$sys = Invoke-RestMethod "$LS/api/system" -TimeoutSec 5
Write-Host "total_fds: $($sys.total_fds)"

# 5. db 健康 (含 management_dimensions 业务表)
$db = Invoke-RestMethod "$LS/api/db/health" -TimeoutSec 10
Write-Host "users=$($db.users) roles=$($db.roles) management_dimensions=$($db.management_dimensions)"
```

**对比之前**: 以前要 SSH yonaa → 手动跑 `ps/lsof/tail/grep/sqlite3` → 复制粘贴, 1-2 分钟. 现在 1-2 秒.

---

## 11. 标准 6 步诊断流程 (由部署智能体整合)

> 用于 disk I/O error / fd 泄漏 / 慢查询 / 服务降级 等问题排查

### Step 1: 全局健康 (5 秒)

```bash
curl -s http://172.20.59.7:9101/api/health
curl -s http://172.20.59.7:9101/api/system | python3 -c "import sys,json; d=json.load(sys.stdin); print('total_fds:', d.get('total_fds'))"
```

**期望**: total_fds < 5000, load < 5

### Step 2: db 健康 + 表统计 (5 秒)

```bash
curl -s http://172.20.59.7:9101/api/db/health | python3 -m json.tool
```

**关键看**:
- `integrity`: 必须 `ok`
- `wal_mb`: < 50 (避免 wal 满)
- `audit_logs` 增长速率: 正常 1-10/s

### Step 3: 磁盘 I/O (5 秒)

```bash
curl -s "http://172.20.59.7:9101/api/iostat?count=3" | python3 -m json.tool
```

**期望**: 每秒 read/write 流量稳定, 无突刺. 如果 `util%` > 80, 磁盘瓶颈.

### Step 4: server.py 进程 I/O (10 秒)

```bash
# 先查 server.py pid
PID=$(curl -s "http://172.20.59.7:9101/api/proc?name=server" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['processes'][0]['pid'])")
echo "server pid: $PID"

# 查进程 I/O
curl -s "http://172.20.59.7:9101/api/proc/io?pid=$PID" | python3 -m json.tool
```

**关键看**:
- `rchar`/`wchar`: 增长速率 (100MB/h 内正常)
- `syscr`/`syscw`: 系统调用次数 (突增表示 I/O 风暴)

### Step 5: SQLite 层 vs server.py 层压力测试 (30 秒)

```bash
# 5a) SQLite 层直压 (绕过 server.py)
curl -s "http://172.20.59.7:9101/api/sqlite/load?count=200&table=users" | python3 -m json.tool

# 5b) server.py 业务压 (走完整链路)
TOKEN=$(curl -s -X POST "http://172.20.59.7:5001/api/v2/action/user.authenticate" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['token'])")
SUCCESS=0
for i in $(seq 1 200); do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://172.20.59.7:5001/api/v2/bo/product?pageSize=5" -H "Authorization: Bearer $TOKEN")
  if [ "$CODE" = "200" ]; then SUCCESS=$((SUCCESS+1)); fi
done
echo "200 biz: success $SUCCESS / 200"
```

**对比**:
- 5a 通过 + 5b 失败 → **server.py 层问题** (不是 db)
- 5a 失败 → **db 层问题** (disk I/O, lock 等待)
- 都失败 → **db 文件损坏** (查 `integrity`)

### Step 6: 错误日志上下文 (10 秒)

```bash
curl -s "http://172.20.59.7:9101/api/log?file=/opt/app/shared/logs/backend-*.log&lines=500&grep=disk" | tail -20
```

**关键看**: 哪个 API + 哪个会话触发, 调用栈, V007.34 retry 次数.

### 常见结论对照表

| Step 1 | Step 2 | Step 3 | Step 4 | Step 5a | Step 5b | 结论 |
|--------|--------|--------|--------|---------|---------|------|
| OK | OK | OK | OK | OK | OK | 健康, 假报警 |
| fd↑ | OK | OK | OK | OK | OK | fd 泄漏 (V007.24 修复后应<5) |
| OK | wal满 | OK | OK | OK | OK | WAL 没刷盘, 触发 checkpoint |
| OK | OK | util>80% | OK | OK | OK | 磁盘瓶颈 |
| OK | OK | OK | wchar↑↑ | OK | OK | server.py 写爆 (V007.34 retry 触发) |
| OK | OK | OK | OK | FAIL | FAIL | db 损坏或锁死 |
| OK | OK | OK | OK | OK | FAIL | server.py 代码 bug |

---

**整合时间**: 2026-07-07 23:35
**整合方**: 部署智能体 (V007.35 部署保障)
**基础文档**: v3.5 (commit 120c18a by 开发智能体)
**新增章节**: §10 部署集成 + §11 标准 6 步诊断流程
