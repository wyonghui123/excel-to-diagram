# DEPLOY_HANDOVER_BUG_V007_21_PROD - 生产环境 disk I/O error 导致登录失败

> **SOP_VERSION**: PARALLEL_DEV_SOP v3.2 (TRIAL_RUNNING_PARALLEL)
> **RISK**: URGENT (生产服务中断)
> **depends_on**: V007.21 (cache_manager 修复, 已部署 3018)
> **HANDOFF_FROM**: dev-agent
> **TIMESTAMP**: 2026-07-07 09:30

---

## 0. TL;DR (7 字段)

| 字段 | 值 |
|------|-----|
| BUG-ID | V007.21-PROD-IOERROR |
| 根因类型 | INFRA / PROCESS-LIFECYCLE |
| 严重度 | P1-Critical (生产登录完全不可用) |
| 修复 Commit | 无 (无需代码 fix, 进程重启即可) |
| 集成 Commit | NONE (生产已恢复) |
| 验证状态 | ✅ PASS (admin/admin123 登录 200) |
| 主服务验证 | ✅ 已通过 (5001 + 8081 都返回 200) |

---

## 1. 根因 (5W1H)

| 项 | 内容 |
|------|------|
| **What** | 远程生产 meta backend (server.py 5001 端口) 登录失败, 返回 `sqlite3.OperationalError: disk I/O error` |
| **Where** | `meta/core/sql_adapters.py:804` (cursor.execute 时抛错) → `meta/services/auth_provider.py:157` (provider.authenticate) → `meta/services/user_authenticate.py:89` (user_authenticate_handler) → `meta/api/auth_api.py:65` (POST /api/v1/auth/login) |
| **When** | 2026-07-07 08:21:45 (用户首次尝试 admin 登录时触发); 之前 deploy_test 用户 08:20:36 登录成功 |
| **Why** | server.py 进程持有"已删除 inode"的 wal 文件句柄 (fd 11, 13, 15, 17, 19... 都显示 `(deleted)`)。sqlite 用这些 fd 写 wal 时, 操作系统返回 disk I/O error。这是 sqlite3 在启动时 `_safe_cleanup_wal_shm` + `wal_checkpoint(TRUNCATE)` 流程的竞态残留 |
| **Who** | 生产用户报告 login IO error; 开发智能体远程诊断 + 重启恢复 |
| **How to fix** | 重启 server.py 进程, 让 sqlite 重新创建干净的 wal/shm。新进程的 fd 全部指向新 inode, 不会再有 (deleted) 句柄 |

### 复现步骤

```bash
# 触发场景 (历史)
# 1. server.py 启动时执行 wal_checkpoint(TRUNCATE), truncate wal 文件
# 2. 但 server.py 同时创建多个 read/write connection, 每个都 open 同一个 wal inode
# 3. 启动 checkpoint 完成后, 某些 fd 仍持有旧 wal inode 引用
# 4. 后续 sqlite 操作使用这些 fd → OS 返回 disk I/O error (inode 已 unlink)

# 复现命令 (历史, 已修复)
curl -v -X POST http://172.20.59.7:8081/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
# 预期: 200 OK, success: true
# 实际 (修复前): 500 + disk I/O error
```

### 关键诊断证据

```bash
# 1. fd 显示 wal 句柄全部 (deleted)
ls -la /proc/<server_pid>/fd/ | grep wal
# lrwx------ ... 11 -> /opt/app/deployments/meta/architecture.db-wal (deleted)
# lrwx------ ... 13 -> /opt/app/deployments/meta/architecture.db-wal (deleted)
# ... 8+ 个都 (deleted)

# 2. db 文件本身完好
sqlite3 /opt/app/deployments/meta/architecture.db "PRAGMA integrity_check;"
# ok

# 3. 直接 python3 读 db 正常
python3 -c "import sqlite3; con=sqlite3.connect('/opt/app/deployments/meta/architecture.db', timeout=5); print(con.execute('SELECT count(*) FROM users').fetchone())"
# (1,)

# 4. jbd2 正常 (非磁盘故障)
ps aux | grep jbd2
# 状态 S (sleeping), wchan=kjournald2 (正常空闲)

# 5. dmesg 历史 jbd2 blocked 120s (云盘 IO 慢, 但非致命)
dmesg | grep jbd2 | tail -5
```

---

## 2. Fix 详情 (本次为运维操作, 无代码 fix)

### 2.1 改动文件清单 (spec.md 白名单)

无代码改动 (本次为生产环境紧急恢复, 通过重启进程解决)。

### 2.2 Worktree Commit

NONE (无需代码 commit)。

### 2.3 集成 Commit (协调智能体操作后填)

NONE。

### 2.4 运维恢复步骤 (关键!)

#### A. 确认服务架构 (避免端口混淆)

```bash
# 远程服务器有 2 个 python 进程:
# - PID 1931: unified_server.py 监听 8081 (反向代理)
# - PID <动态>: server.py (meta backend) 监听 5001 (端口由 PORT 环境变量决定)

# 关键: 服务端口是 5001 不是 3011!
# 之前测试 3011 总是 connection refused, 因为 server.py 没启或启在 5001

ps aux | grep -E "python.*server" | grep -v grep
ss -tlnp | grep -E ":(5001|8081|3011)"
```

#### B. 复制环境变量 (从 unified_server.py 1931 复制)

```bash
# 1931 是 unified_server, env 已配好, 复制给 server.py
cat /proc/1931/environ | tr '\0' '\n' | grep -iE "JWT|FLASK|CORS|SECRET|MODE|PORT"

# 输出:
# BACKEND_PORT=5001
# FLASK_SECRET_KEY=deploy-v20260707_001-1783383610-do-not-use-in-prod-without-rotation-flask-key
# FLASK_ENV=production
# CORS_ALLOWED_ORIGINS=http://172.20.59.7:8081,http://127.0.0.1:8081,http://127.0.0.1:5001
# ARG_PORT=5001
# FLASK_DEBUG=false
# PORT=5001
# JWT_SECRET_KEY=deploy-v20260707_001-1783383610-do-not-use-in-prod-without-rotation-jwt-key
```

#### C. 重启 server.py (带完整环境变量)

```bash
cd /opt/app/deployments/meta

setsid env \
  BACKEND_PORT=5001 \
  FLASK_SECRET_KEY='deploy-v20260707_001-1783383610-do-not-use-in-prod-without-rotation-flask-key' \
  FLASK_ENV=production \
  CORS_ALLOWED_ORIGINS='http://172.20.59.7:8081,http://127.0.0.1:8081,http://127.0.0.1:5001' \
  ARG_PORT=5001 \
  FLASK_DEBUG=false \
  PORT=5001 \
  JWT_SECRET_KEY='deploy-v20260707_001-1783383610-do-not-use-in-prod-without-rotation-jwt-key' \
  /opt/miniconda3-py39/bin/python server.py \
  > /opt/app/shared/logs/backend-v$(date +%Y%m%d_%H%M%S).log 2>&1 < /dev/null &

NEW_PID=$!
disown
sleep 60  # 等 yaml 加载 + db 初始化
ps -p $NEW_PID
```

#### D. 验证 login

```bash
# 直接 5001
curl -v -X POST http://localhost:5001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# 通过 8081 代理
curl -v -X POST http://localhost:8081/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# 预期: 200 OK + success: true
```

---

## 3. v3.2 流程执行情况 (8 阶段)

| 阶段 | 负责方 | 状态 | 备注 |
|------|--------|------|------|
| 0. 创建 spec | dev-agent | ✅ | 本 doc 即 spec |
| 1. 白名单 + 预检 | dev-agent | ✅ | 无代码改动, 跳过 |
| 2. 修复 | dev-agent | ✅ | 无代码 fix, 仅运维重启 |
| 3. Worktree 验证 | dev-agent | ✅ | 远程 curl login 200 |
| 4. Stash 检查 | dev-agent | ✅ | 无 stash |
| 5. commit | dev-agent | N/A | 无 commit |
| 6. 推送 | dev-agent | N/A | 无 commit |
| 7. 主服务验证 | dev-agent + 用户 | ✅ | 用户确认 login 成功 |

---

## 4. 关键洞察 (避免下次重复踩坑)

### 4.1 端口混淆陷阱

**远程生产 meta backend 实际监听 5001, 不是 3011**。这是部署时通过 PORT 环境变量决定的。

之前调试一直在 curl 3011, 一直 connection refused, 浪费了很多时间。

**未来**: dev/ops 必须在所有诊断命令前列出 `ss -tlnp` 确认实际监听端口。

### 4.2 安全检查 + 环境变量依赖

server.py 启动时 `run_startup_checks()` 严格检查:
- JWT_SECRET_KEY
- FLASK_SECRET_KEY
- CORS_ALLOWED_ORIGINS

如果 env 没配, production mode 立即 RuntimeError 退出。

**未来**:
- 必须从同一服务器上其他同服务进程复制 env (而不是 .env 文件, 部署用 deploy-v20260707_001- 前缀)
- env 中的 secret key 含 deploy version 前缀, 不可硬编码

### 4.3 (deleted) wal inode 句柄

server.py 启动时 `_safe_cleanup_wal_shm` + `wal_checkpoint(TRUNCATE)` 创建了一个**有缺陷的状态**:
- 多线程 sqlite handles 引用旧 wal inode
- TRUNCATE 操作让旧 inode 被 unlink
- sqlite 句柄仍持有 inode 引用 (fd 显示 (deleted))
- 后续 IO 操作 OS 拒绝 (disk I/O error)

**这是真 bug, 需要后续代码 fix** (虽然本次重启绕过了)。

**建议代码 fix 方向** (后续 sprint):
1. `_safe_cleanup_wal_shm` 在 close 旧 connection 前必须先 checkpoint
2. `SQLiteConnectionPool._create_connection` 创建后必须 PRAGMA quick_check 验证
3. `reader()` 第一次 yield 前必须 self-test (SELECT 1)

### 4.4 生产服务缺自动重启

本次事件耗时 ~30 分钟手动恢复 (env 查找 + 启动失败 + 重试)。

**建议** (后续 sprint):
- 加 systemd unit 或 supervisor 配置
- 实现 server.py 启动失败自动重试 (3 次)
- 加入进程健康监控 (curl 5001/api/v1/health)

### 4.5 部署用 secret key 命名约定

env 中的 secret key 形如:
```
deploy-v20260707_001-1783383610-do-not-use-in-prod-without-rotation-...
```

格式: `deploy-<version>-<timestamp>-<warning>-<purpose>-key`

**未来**: 在 INFRA_HANDOVER.md 中记录 secret key 提取方式, 避免每次都 `cat /proc/<pid>/environ`。

---

## 5. 后续 TODO (协调智能体)

| # | TODO | 优先级 | 状态 |
|---|------|--------|------|
| 1 | 加 systemd / supervisor 配置自动重启 server.py | P1 | ⏳ 待办 |
| 2 | 修 `_safe_cleanup_wal_shm` + `wal_checkpoint(TRUNCATE)` 竞态 | P2 | ⏳ 待办 |
| 3 | `SQLiteConnectionPool._create_connection` 加 self-test | P2 | ⏳ 待办 |
| 4 | INFRA_HANDOVER.md 增加 secret key 提取 SOP | P3 | ⏳ 待办 |
| 5 | 部署时自动 dump env 到 `.env.deploy-<version>` 备份 | P3 | ⏳ 待办 |

---

## 6. 时间线 (完整事件)

| 时间 | 事件 |
|------|------|
| 2026-07-07 08:14 | 部署开始 (deploy-v20260706_021 → deploy-v20260707_001) |
| 2026-07-07 08:20 | server.py (PID 1905) + unified_server.py (PID 1931) 启动 |
| 2026-07-07 08:20:36 | deploy_test 用户登录成功 |
| 2026-07-07 08:20:37 | GET /api/v1/users/me 成功 |
| 2026-07-07 08:21:45 | admin 用户登录 → `disk I/O error` |
| 2026-07-07 08:42 | 用户报告生产登录失败 |
| 2026-07-07 08:43 - 09:25 | 远程诊断 + 多次重启尝试 (security check 失败等) |
| 2026-07-07 09:07 | 用户发现 db 文件 (deleted) wal 状态 |
| 2026-07-07 09:13 | 前台 timeout 30s 启动看到 yaml 加载 |
| 2026-07-07 09:19 | security check 失败 RuntimeError, 进程退出 |
| 2026-07-07 09:25 | setsid env <完整env> 启动 server.py 成功 (5001) |
| 2026-07-07 09:25:51 | meta backend 启动完成, db pool 初始化成功 |
| 2026-07-07 09:27:49 | admin/admin123 登录成功 (5001 + 8081 都 200) |

---

## 7. 参考资料

- Server: 172.20.59.7 (yonaa)
- Backend log: `/opt/app/shared/logs/backend-v20260707_*.log`
- DB: `/opt/app/deployments/meta/architecture.db` (98MB, integrity ok)
- 部署版本: deploy-v20260707_001
- Worktree: integration/2026-07-04
- 主服务: 5001 (server.py) + 8081 (unified_server.py 反向代理)