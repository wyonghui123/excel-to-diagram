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

`log_service.py` 现在混在 `worktrees/integration` 根目录。建议:
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

文件: `D:\filework\worktrees/integration\tests\test_log_service_v3_5.py`

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
#    从 D:\filework\worktrees/integration\log_service.py

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
cd D:\filework\worktrees/integration
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