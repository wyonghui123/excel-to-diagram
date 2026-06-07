---
title: 十、部署与运维
version: 3.0.2
date: 2026-06-07
status: 活跃
parent: ARCHITECTURE_V2.md
---

# 十、部署与运维

> 本章节从 [ARCHITECTURE_V2.md §十](../ARCHITECTURE_V2.md#十-部署与运维) 提取（2026-06-07 v3.0.2 拆分）
>
> **拆分原因**：原章节 318 行/9.3KB，独立成文便于维护
>
> **同步说明**：本文件为单一事实源，主文档 §十 仅保留链接

---

# 运行前端测试
npm run test

# 运行 E2E 测试
npx playwright test

# 运行性能测试
pytest meta/tests/performance/ -v
```

---

## 十、部署与运维

### 10.1 开发环境启动

**推荐方式**：一键启动脚本

```powershell
# Windows PowerShell
.\scripts\start-dev.ps1

# 变体参数
.\scripts\start-dev.ps1 -BackendOnly   # 仅启动后端
.\scripts\start-dev.ps1 -Stop         # 停止所有服务
```

**npm 命令（备选）**：

```bash
npm run dev:full     # concurrently 启动前后端
npm run dev          # 仅前端（需要后端已运行）
npm run dev:python   # 仅后端
```

### 10.2 服务架构

| 服务 | 端口 | 启动命令 | 说明 |
|------|------|---------|------|
| **Vite 前端** | 3004 | `npm run dev` | 开发服务器，代理 `/api/*` 到后端 |
| **Flask 后端** | 5000 | `python meta/server.py` | REST API + WebSocket |
| **健康检查** | 5000/api/v1/health | GET | 后端就绪返回 `{status: "ok"}` |

### 10.3 故障排查速查

**场景1：启动后页面空白 / API 报错**
```powershell
# 确认两个服务都在运行
netstat -ano | findstr ":3000..3010"
netstat -ano | findstr ":4999..5001"

# 如果缺少某个服务
.\scripts\start-dev.ps1 -Stop
.\scripts\start-dev.ps1
```

**场景2：修改了 meta/schemas/*.yaml 但没生效**
- 前端热刷新会调用 `/api/v1/meta/reload`
- 如果 reload 失败，重启后端

**场景3：数据库被锁 (SQLite)**
```powershell
# SQLite 不支持多写，确保只有一个 Python 进程
Get-Process python | Measure-Object
# 如果 > 1，说明有僵尸进程
.\scripts\start-dev.ps1 -Stop   # 清理后重试
```

### 10.4 环境配置

**环境变量文件**: [.env.example](../.env.example)

#### 前端环境变量（Vite / Node.js）

```env
# ============================================
# 服务端口配置
# ============================================

# 前端开发服务器端口
VITE_DEV_PORT=3004

# Node.js Mock API 服务器端口（可选）
MOCK_API_PORT=3001

# Python Flask 后端端口
FLASK_PORT=5000

# E2E 测试服务器端口
E2E_PORT=3004

# ============================================
# API 代理配置
# ============================================

# API 代理指向 Python 后端（vite.config.js 使用）
VITE_API_PROXY=http://localhost:5000

# Mock API 代理配置（可选）
VITE_MOCK_API_PROXY=http://localhost:3001

# ============================================
# 第三方 AI 服务配置（敏感信息）
# ============================================
# 注意：以下配置需复制到 .env 文件中填写真实值
# .env 文件已在 .gitignore 中，不会被提交

# DeepSeek AI API 配置
VITE_DEEPSEEK_API_KEY=your_deepseek_api_key_here

# 智谱 AI API 配置
VITE_ZHIPU_API_KEY=your_zhipu_api_key_here

# 飞书开放平台配置
VITE_FEISHU_APP_ID=your_feishu_app_id_here
VITE_FEISHU_APP_SECRET=your_feishu_app_secret_here
VITE_FEISHU_ACCESS_TOKEN=your_feishu_access_token_here
```

#### 后端环境变量（Flask / Python）

```env
# ============================================
# 数据库配置
# ============================================

# SQLite 数据库路径（默认：meta/architecture.db）
SQLITE_DB_PATH=./data/app.db

# ============================================
# 安全配置
# ============================================

# JWT 密钥（必须设置，用于 Token 签名）
JWT_SECRET_KEY=your-secret-key-change-in-production

# ============================================
# 服务器配置
# ============================================

# Flask 监听端口（默认：3010）
PORT=5000

# Flask 调试模式（默认：True，生产环境设为 False）
FLASK_DEBUG=True

# CORS 允许的源（逗号分隔，留空则允许所有）
CORS_ALLOWED_ORIGINS=http://localhost:3004,http://127.0.0.1:3004

# ============================================
# 日志配置（可选）
# ============================================

# 日志级别（DEBUG/INFO/WARNING/ERROR）
LOG_LEVEL=INFO

# 是否启用请求追踪 ID
ENABLE_TRACE_ID=True
```

#### 服务架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                     开发环境服务架构                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  浏览器                                                      │
│    │                                                         │
│    ▼                                                         │
│  ┌─────────────────┐                                        │
│  │ Vite Dev Server │ ← port 3004                           │
│  │ (Vue.js + HMR)  │                                        │
│  └────────┬────────┘                                        │
│           │                                                  │
│           │ Proxy Rules (vite.config.js)                    │
│           │                                                  │
│    ┌──────┴──────┬──────────┐                               │
│    ▼             ▼          ▼                               │
│  /api/deepseek  /api/v1   /api/v2                            │
│  /api/zhipu     └───┬──────┘                                │
│                      │                                       │
│                      ▼                                       │
│            ┌─────────────────┐                               │
│            │  Flask Backend  │ ← port 5000                  │
│            │  (Python)       │                                │
│            │                 │                                │
│            │  - SQLite DB   │                                │
│            │  - BO Framework│                                │
│            │  - WebSocket   │                                │
│            └─────────────────┘                               │
│                                                             │
│  健康检查: GET http://localhost:5000/health                  │
│  返回: {"status": "ok", "service": "arch-data-manage-api"}  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### Vite 代理规则详解

**文件位置**: [vite.config.js](../vite.config.js)

```javascript
server: {
  host: true,              // 允许局域网访问
  port: 3004,             // 前端开发端口
  proxy: {
    '/api/deepseek': {    // DeepSeek AI 接口
      target: 'http://localhost:3010',
      changeOrigin: true
    },
    '/api/zhipu': {       // 智谱 AI 接口
      target: 'http://localhost:3010',
      changeOrigin: true
    },
    '/api/v1': {          // v1 API（元数据、导入导出等）
      target: 'http://localhost:3010',
      changeOrigin: true,
      ws: true            // 支持 WebSocket
    },
    '/api/v2': {          // v2 API（BO 统一接口）⭐
      target: 'http://localhost:3010',
      changeOrigin: true,
      ws: true            // 支持 WebSocket
    }
  }
}
```

#### 端口分配表

| 服务 | 默认端口 | 环境变量 | 说明 |
|------|---------|---------|------|
| **Vite 前端** | 3004 | `VITE_DEV_PORT` | Vue.js 开发服务器，支持 HMR |
| **Flask 后端** | 5000 | `PORT` / `FLASK_PORT` | Python REST API + WebSocket |
| **Mock API** | 3001 | `MOCK_API_PORT` | 可选的 Node.js Mock 服务 |
| **E2E 测试** | 3004 | `E2E_PORT` | Playwright 测试使用 |

#### 敏感信息管理

**原则**: 敏感信息绝不提交到代码仓库

```
项目根目录/
├── .env.example          # ✅ 提交（模板文件，包含占位符）
├── .env                  # ❌ 不提交（包含真实密钥）
├── .gitignore            # ✅ 包含 .env 规则
└── meta/server.py        # ✅ 通过 os.environ.get() 读取
```

**安全检查清单**：

- [ ] `.env` 已添加到 `.gitignore`
- [ ] 生产环境 `JWT_SECRET_KEY` 已更换为强密码
- [ ] 生产环境 `FLASK_DEBUG=False`
- [ ] 生产环境 `CORS_ALLOWED_ORIGINS` 已限制为实际域名
- [ ] 第三方 API Key 已正确配置且权限最小化

---

### 10.5 数据库可靠性工程 (DRE) 子系统 [NEW v3.0]

> **背景**: v2.x 文档"部署运维"章节只字未提数据库可靠性。v3.0 已落地**完整的 DRE 体系**(8 个独立模块)。

#### 10.5.1 体系组件

| 组件 | 路径 | 职责 | 关键指标 |
|------|------|------|---------|
| **db_health_monitor** | [meta/core/db_health_monitor.py](file:///d:/filework/excel-to-diagram/meta/core/db_health_monitor.py) | 启动时 + 定时检查 DB 健康 | WAL 大小, pending frames, 并发访问数 |
| **sql_monitor** | [meta/core/sql_monitor.py](file:///d:/filework/excel-to-diagram/meta/core/sql_monitor.py) | 慢查询监控 (>100ms 触发) | P50/P95/P99 延迟, 慢查询率 |
| **sql_prometheus_exporter** | [meta/core/sql_prometheus_exporter.py](file:///d:/filework/excel-to-diagram/meta/core/sql_prometheus_exporter.py) | Prometheus 指标导出 (`:9090/metrics`) | 23+ 指标 |
| **sql_slow_query_logger** | [meta/core/sql_slow_query_logger.py](file:///d:/filework/excel-to-diagram/meta/core/sql_slow_query_logger.py) | 慢查询独立日志(带 EXPLAIN) | 慢查询 + SQL 计划 |
| **sql_connection_pool** | [meta/core/sql_connection_pool.py](file:///d:/filework/excel-to-diagram/meta/core/sql_connection_pool.py) | 连接池管理 (默认 10/worker) | 活跃连接/等待连接/超时 |
| **sql_write_queue** | [meta/core/sql_write_queue.py](file:///d:/filework/excel-to-diagram/meta/core/sql_write_queue.py) | 写队列背压(防止突发写打爆) | 队列深度/丢弃率/重试率 |
| **sql_checkpoint_manager** | [meta/core/sql_checkpoint_manager.py](file:///d:/filework/excel-to-diagram/meta/core/sql_checkpoint_manager.py) | WAL checkpoint 管理(快照前 flush) | checkpoint 次数/WAL 大小 |
| **sql_maintenance_scheduler** | [meta/core/sql_maintenance_scheduler.py](file:///d:/filework/excel-to-diagram/meta/core/sql_maintenance_scheduler.py) | 维护任务调度(vacuum/reindex) | 维护频率/耗时 |

#### 10.5.2 关键健康规则

```python
# meta/core/db_health_monitor.py:L45-L60
HEALTH_RULES = {
    'wal_size_mb':           {'warn': 1,   'critical': 5,   'action': 'checkpoint'},
    'pending_frames':        {'warn': 100, 'critical': 1000, 'action': 'flush'},
    'concurrent_writers':    {'warn': 50,  'critical': 100,  'action': 'throttle'},
    'long_running_txn_sec':  {'warn': 30,  'critical': 300,  'action': 'abort'},
    'wal_files_count':       {'warn': 50,  'critical': 200,  'action': 'cleanup'},
}
```

#### 10.5.3 监控集成

```
sql_monitor → Prometheus exporter → Grafana 看板
                                       ↓
                              告警规则 (P0/P1/P2):
                              - P0: connection_pool_exhausted → oncall
                              - P1: slow_query_rate > 5% → slack
                              - P2: wal_size > 1MB → 邮件
```

#### 10.5.4 DB 快照与 WAL 保护（关键修复 2026-06-02）

> **历史问题**: 测试 snapshot/restore 时未触发 WAL checkpoint → restore 后服务器仍持有旧 WAL → 数据不一致

**修复** (test.py):
```python
def _create_db_snapshot(self):
    self._checkpoint_db_wal()  # 先强制 flush WAL
    shutil.copy(self.db_path, snapshot_path)
    # 同时 copy -wal 和 -shm 文件(若存在)

def _checkpoint_db_wal(self):
    """强制 flush WAL 到主 DB 文件"""
    with self._get_db_connection() as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
```
