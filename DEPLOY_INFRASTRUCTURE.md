# DEPLOY_INFRASTRUCTURE.md

> **目标读者**: AI Agent / 新接手工程师 / 运维 / 任何需要部署或维护本项目的人
> **最后更新**: 2026-07-03
> **本文件用途**: 让 AI Agent 在看到本项目时, 立刻能识别这是什么项目、怎么部署、怎么回滚、怎么监控

---

## 📋 项目元数据 (AI Agent 必读)

| 字段 | 值 |
|------|---|
| **项目名** | BIP-Backend (Excel-to-Diagram Architecture Management Backend) |
| **仓库** | `release/pre-2026-06-29` 分支 |
| **远端服务器** | `172.20.59.7` (MobaXterm SSH `root@172.20.59.7`) |
| **远端用户** | `root` (容器环境) |
| **Python** | `/opt/miniconda3-py39/bin/python` (conda py39 env) |
| **包管理** | pip (requirements.txt 在 `meta/`) |
| **数据库** | SQLite (`meta/architecture.db`) |
| **默认版本** | `v20260703_002` |
| **默认 backend 端口** | `5001` |
| **默认 frontend 端口** | `8081` |

---

## 🏗️ 远端服务器环境

### 路径约定

```
/opt/app/                          # 部署根 (DEPLOY_ROOT)
├── deployments/                   # 所有版本 (DEPLOYMENTS_DIR)
│   ├── v20260630_003/             # v3 (单进程 5000)
│   ├── v20260702_001/             # 中间版本
│   ├── v20260703_002/             # 当前 default (v4, 5001)
│   └── frontend_dist_files/       # 前端 dist (zip 顶层, 不在版本目录!)
├── current → deployments/v20260703_002  # 软链 (CURRENT_LINK)
├── shared/                        # 共享
│   └── logs/                      # 日志 (LOG_DIR)
│       ├── backend-v*.log
│       ├── frontend-v*.log
│       └── watch-YYYYMMDD.log
├── backups/                       # db 备份
└── tmp/deploy_bundle/             # 部署 bundle (远端解压目录, REPO_BUNDLE)
```

### 端口约定

| 端口 | 用途 | 何时使用 |
|------|------|----------|
| `5000` | v3 backend (单进程) | 2026-06-30 之前的版本 |
| `5001` | v4 backend (API only) | 2026-07-02 起的版本 (default) |
| `5002` | 测试端口 (临时) | 部署测试时用, **生产不要用** |
| `8081` | v4 unified (frontend + API 代理) | 2026-07-02 起的版本 (default) |
| `8082` | 测试端口 (临时) | 部署测试时用, **生产不要用** |

### 部署架构 (v3 vs v4)

**v003 之前** (2026-06-30 之前):
- 单进程: `nohup server.py > log 2>&1 &` 同时服务 API + frontend
- 端口: 5000
- 不需要 unified_server
- frontend 静态文件由 server.py 自己 serve

**v004 起** (2026-07-02 之后):
- 双进程:
  - `server.py` (backend only on 5001)
  - `unified_server.py` (frontend + API 代理 on 8081)
- unified_server.py 关键功能:
  - 静态文件 fallback (SPA)
  - API 代理 (透明转发)
  - **Token 持久化** (按 client IP, 解决前端 boService 401)
- 关键 BUG (已修): v4 给所有 BO endpoint 加 `@login_required`, 前端 boService 调时**不传 Authorization header** 导致 401, **unified 拦截 login 响应自动注入 token 解决**

### API 兼容 (v3 vs v4)

| 端点 | v3 | v4 |
|------|----|----|
| 登录 | `POST /api/v1/auth/login` | `POST /api/v2/action/user.authenticate` |
| 用户信息 | `GET /api/v1/users/me` | `GET /api/v2/bo/product?page_size=10` 等 BO endpoints |
| 枚举 | `GET /api/v1/enum-types` | `GET /api/v1/enum-types` (保持兼容) |
| 健康 | `GET /api/v1/health` (410) | `GET /api/v2/bo/health` (需 auth, 401) |

**关键**: **token 永远在 `data.token` 字段** (v3 和 v4 都一样, 不是顶层 `token`!)

---

## 🛠️ 部署工具 (10 个, 在 `deploy_bundle/`)

| # | 工具 | 用途 | 何时用 |
|---|------|------|--------|
| 1 | `deploy.sh` | 完整部署 (PHASE 0-7) | 部署新版本 |
| 2 | `precheck.sh` | 8 项早期检查 (含 frontend_dist_files) | 部署前 |
| 3 | `smoke_test.sh` | 5 项真实 API | 部署后 |
| 4 | `rollback.sh` | 回滚 (v3/v4 架构自适应) | 出问题时 |
| 5 | `diagnose.sh` | 7 步深度诊断 | 出问题时 |
| 6 | `status.sh` | 一键状态 | 任何时候 |
| 7 | `restart.sh` | 重启当前 (不切版本) | 代码/配置更新 |
| 8 | `watch.sh` | 健康监控+自动恢复 | 长跑守护 |
| 9 | `deploy_history.sh` | 部署历史+一键切版本 | 回溯 |
| 10 | `unified_server.py` | frontend + API 代理 + token 持久化 | v4 必需 |

**所有 10 工具都通过本地 e2e 测试 (test_deploy_e2e.py 11/11 PASS)**。

---

## 📦 部署 bundle 结构 (deploy_bundle/)

```
deploy_bundle/
├── deploy-v20260703_002.zip (19.3MB)  # 部署包 (含 frontend_dist_files/)
├── deploy.sh, precheck.sh, smoke_test.sh, rollback.sh
├── diagnose.sh, status.sh, restart.sh, watch.sh, deploy_history.sh
├── unified_server.py
├── lib/common.sh                       # 共用函数 + 项目元数据
├── README.txt                          # 快速上手
└── tests/                              # 26 个可部署 e2e 测试
    ├── test_sop_local.py               # 本地 (Windows) 验证
    ├── test_deploy_e2e.py              # 部署全流程 (11/11 PASS)
    ├── test_frontend_dir.py            # unified 8081 服务
    ├── test_rollback_parallel.py       # 并行 v3 验证
    └── ... (22 个其他历史测试)
```

**重要**: `frontend_dist_files/` 在 zip 顶层, **不在**版本目录 (`v20260703_002/frontend_dist_files/`)!

---

## 🚀 部署流程 (3 步, 用户最简)

### Step 1: 本地 rebuild bundle

```bash
cd D:\filework\release-prep-worktree
powershell -NoProfile -ExecutionPolicy Bypass -File tools\rebuild_bundle.ps1
```

**重要**: rebuild 后**必须**验证:
```bash
Get-ChildItem deploy_bundle\ -Filter "*.sh" | Select Name
# 应该看到 9 个 sh: deploy, precheck, smoke_test, rollback, diagnose, status, restart, watch, deploy_history
```

### Step 2: SFTP 拖到远端

**MobaXterm SFTP 面板**:
- 远端导航: `/tmp/`
- 本地导航: `D:\filework\release-prep-worktree\deploy_bundle\`
- **拖** `deploy_bundle/` 覆盖到 `/tmp/`

### Step 3: 远端跑 deploy

```bash
ssh root@172.20.59.7
bash /tmp/deploy_bundle/deploy.sh --version v20260703_002 --port 5001
```

**deploy.sh PHASE 0-7**:
- PHASE 0: 事实采集 + 参数校验
- PHASE 0.5: 解压 zip (如 backend 缺 OR frontend_dist_files 缺)
- PHASE 1: 停旧
- PHASE 2: 备份 + 复制 db
- PHASE 3: systemd service (或 fallback nohup)
- PHASE 4: 启 backend
- PHASE 5: 启 unified_server
- PHASE 6: 端到端验证
- PHASE 6.5: smoke test (5 项真实 API)
- PHASE 7: 切 current 链接

---

## 🔄 回滚流程 (1 步)

```bash
ssh root@172.20.59.7
bash /tmp/deploy_bundle/rollback.sh --to v20260630_003 --port 5000
```

**rollback.sh 架构自动检测**:
- v3 (无 unified_server.py): 单 server.py 进程
- v4 (有 unified_server.py): 双进程 (backend + unified)
- 端口自动: `--port 5000` (v3) 或 `--port 5001` (v4)

---

## 📊 监控流程 (1 步)

```bash
# 单次检查
bash /tmp/deploy_bundle/watch.sh

# 循环监控 (每 30s)
bash /tmp/deploy_bundle/watch.sh --loop 30

# 失败时自动 restart
bash /tmp/deploy_bundle/watch.sh --loop 30 --auto-recover

# 失败时自动 rollback
bash /tmp/deploy_bundle/watch.sh --loop 30 --rollback-on-fail
```

---

## 🧪 测试流程 (本地 + 远端)

### 本地 (Windows) - 快速验证

```bash
cd D:\filework\release-prep-worktree
python tests/test_deploy_e2e.py    # 11/11 PASS (验证 10 工具 + 关键逻辑)
```

### 远端 - 真实环境 e2e

```bash
ssh root@172.20.59.7
/opt/miniconda3-py39/bin/python /tmp/deploy_bundle/tests/test_rollback_parallel.py
/opt/miniconda3-py39/bin/python /tmp/deploy_bundle/tests/test_frontend_dir.py
```

---

## ⚠️ 已修复的关键 BUG (AI Agent 应知晓)

| # | BUG | 修复 | 影响 |
|---|-----|------|------|
| 1 | env BUG 反复 (8+ 次) | 改用 `nohup python server.py` 不带 `env` | 后端启失败 |
| 2 | 8081 404 (frontend_dist_files 缺) | `deploy.sh` PHASE 0.5 强制解压 + `precheck.sh` Check 8/8 | 浏览器 404 |
| 3 | v4 boService 401 (无 Authorization) | `unified_server.py` 加 token 持久化 (按 client IP) | 菜单加载失败 |
| 4 | v3 server.py 强 check 8081 | 测试用 5002 + 临时改 .env | 并行测试失败 |
| 5 | smoke /api/v1/health 410 | 改用 `/api/v1/enum-types` (兼容 v3/v4) | smoke FAIL |
| 6 | login grep 漏 data.token | status.sh/restart.sh 改用 python json 解析 | login FAIL |
| 7 | rebuild 没复制 status.sh | `rebuild_bundle.ps1` $tools 数组加全 | 文件缺失 |
| 8 | rebuild 没复制 tests/ | `rebuild_bundle.ps1` 加 tests/ 复制 | 测试无法跑 |
| 9 | 部署后没 SFTP 拖就跑 | AI Agent 应养成"先 SFTP 再跑" | No such file |

---

## 🤖 AI Agent 部署规范

### ✅ DO (应该做的)

1. **写完任何 tools/X.sh 后**:
   - 改 `tools/rebuild_bundle.ps1` 的 `$tools` 数组 (加 X.sh)
   - 跑 `rebuild_bundle.ps1` 验证 deploy_bundle/ 有 X.sh
   - commit + 告诉用户 SFTP 拖
2. **改完文件**:
   - 本地先跑 `python tests/test_deploy_e2e.py` (11/11 PASS)
   - 验证通过后再让用户 SFTP 拖
3. **诊断问题时**:
   - **先看 log** (`tail -50 /opt/app/shared/logs/backend-*.log`)
   - **再跑 diagnose.sh** (`bash /tmp/deploy_bundle/diagnose.sh`)
   - **最后**才让用户回滚
4. **重启服务**:
   - 用 `bash /tmp/deploy_bundle/restart.sh` (1 步)
   - **不要**手动 `pkill + nohup` (容易忘 env vars)

### ❌ DON'T (不要做的)

1. **不要**让用户跑命令时**没** SFTP 拖过最新 deploy_bundle
2. **不要**在没看 log 时猜根因
3. **不要**写脚本时假设有 `bash` (容器可能没 git-bash, 用 Python)
4. **不要**改 `tools/X.sh` 但忘了改 `rebuild_bundle.ps1` 复制
5. **不要**让用户跑 `bash X.sh` 时**没**确认远端有该文件
6. **不要**假设 v3 和 v4 架构相同 (v3 单进程, v4 双进程)
7. **不要**假设 v3 和 v4 API 相同 (login 端点不同)

---

## 📞 快速诊断清单

| 症状 | 检查 | 命令 |
|------|------|------|
| 浏览器 404 | unified 启了? frontend_dist_files 在? | `ss -tlnp \| grep 8081` + `ls /opt/app/deployments/frontend_dist_files/` |
| 浏览器 401 | unified token 注入? backend JWT 密钥? | `tail -f /opt/app/shared/logs/frontend-*.log` + `grep TOKEN_CACHE` |
| backend 没启 | env vars? port 占用? .env? | `tail -50 /opt/app/shared/logs/backend-*.log` |
| login FAIL | token 在 data.token? user_id 匹配? | `curl -X POST .../api/v1/auth/login -d '{...}' \| python -m json.tool` |
| 想回滚 | current 指向哪? 有几个旧版本? | `bash /tmp/deploy_bundle/deploy_history.sh` |
| 想监控 | watch 是否循环? | `bash /tmp/deploy_bundle/watch.sh --loop 30` |

---

## 📝 版本历史

| 版本 | 日期 | 主要变化 |
|------|------|----------|
| v20260630_003 | 2026-06-30 | v3 架构 (单进程 5000) |
| v20260702_001 | 2026-07-02 | 中间版本 (可能坏) |
| v20260703_002 | 2026-07-03 | v4 架构 (5001+8081 双进程) + enum mutability 修复 |

---

**维护**: 任何部署相关变更 (新工具/新 BUG/新端口), **必须**更新本文档。
