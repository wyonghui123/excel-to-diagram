# 部署完整指南 (DEPLOYMENT.md)

> 完整的 Excel-to-Diagram 部署流程：准备 → 上传 → 部署 → 验证 → 回滚
> 更新: 2026-07-14 — 修正部署包路径、端口、版本号

---

## 1. 准备部署包（本地 Windows）

### 1.1 重建 `deploy_bundle/`

```bash
cd D:\filework\worktrees/release-prep
python tools/rebuild_bundle.py
```

**输出**：
```
deploy_bundle/
├── deploy-v20260713_223807_staging.zip   (部署 zip)
├── deploy.sh                             (部署脚本, 含 PHASE 0.5/0.6)
├── precheck.sh                           (部署前检查)
├── smoke_test.sh                         (smoke test)
├── rollback.sh                           (回滚脚本)
├── unified_server.py                     (前端代理服务)
├── lib/
│   ├── common.sh                         (通用函数库)
│   ├── check_deploy_health.sh            (健康检查)
│   └── fix_permissions.sh                (权限修复)
└── MANIFEST                              (文件清单)
```

> **注意**: 部署包目录名是 `deploy_bundle/`（不是 `_deploy_bundle/`）。
> 源工具脚本在 `tools/` 目录手工维护，`deploy_bundle/` 是由 `rebuild_bundle.ps1` 生成的（含 `[GENERATED]` 标记，禁止直接编辑）。

### 1.2 自检（推荐）

```bash
# 跑所有测试
python tools/test_deploy_generalized.py   # 通用化 (40 PASS)
python tools/test_precheck_smoke.py       # precheck+smoke (12 PASS)
python tools/e2e_sop_drill.py            # SOP 端到端 (18 PASS)
python tools/self_test.py                # 工具自检 (26 PASS)
```

**期望**：全 PASS

---

## 2. 上传到远端（堡垒机/MobaXterm）

### 2.1 打开堡垒机

浏览器 → `jumper.yyuap.com` → 登录 → 双因子 → 进 172.20.59.7

### 2.2 MobaXterm SFTP 拖文件

- MobaXterm → SFTP 标签
- 左侧本地：`D:\filework\worktrees/release-prep\deploy_bundle\`
- 右侧远端：`/tmp/`
- **拖整个 `deploy_bundle/` 目录**（不是单个文件！）

### 2.3 验证上传

```bash
# 远端终端
ls -la /tmp/deploy_bundle/
# 应该看到 7 个文件 + lib/ 目录
```

---

## 3. 部署到生产（堡垒机终端）

> **端口约定 (V007.50)**: prod 后端 `server.py` = 3011, 前端代理 `unified_8081` = 8081。
> staging 对应 13011/18081，详见 [STAGING_GUIDE.md](docs/STAGING_GUIDE.md)。

### 3.1 一键命令

```bash
bash /tmp/deploy_bundle/deploy.sh --version v20260714_001 --port 3011
```

**脚本自动**（10 阶段）：
1. **PHASE 0: precheck**（7 项健康检查）
2. **PHASE 0.5: 解压 zip + 生成 VERSION_PATH/MANIFEST**
3. **PHASE 0.6: 共享根 db 检查**（V46 共享根架构防护）
4. **PHASE 1: 停旧服务**
5. **PHASE 2: 备份 + 复制 db**
6. **PHASE 3: 写 systemd service**（如启用）
7. **PHASE 4: 启 backend（3011）**
8. **PHASE 5: 启 unified server（8081）**
9. **PHASE 6: curl 验证 + PHASE 6.5: smoke test（5 项真实功能）**
10. **PHASE 7: 切 current 链接**

**总耗时**：~30 秒

### 3.2 完整参数

```bash
bash /tmp/deploy_bundle/deploy.sh \
    --version v20260714_001 \            # 必填
    --port 3011 \                        # 必填 (prod backend 端口)
    --zip /opt/app/deploy-...zip \       # 可选, 默认自动找
    --frontend-port 8081 \               # 可选 (prod unified 端口)
    --db-source /path/to/old.db \        # 可选, 默认 current 版本
    --deploy-root /opt/app \             # 可选
    --unified /tmp/unified_server.py \   # 可选
    --skip-precheck \                    # 可选
    --skip-smoke \                       # 可选
    --no-systemd                         # 可选 (默认 no-systemd)
```

### 3.3 验证部署成功

DEPLOY SUMMARY 应该输出：
```
✓ 全部 PASS
浏览器访问: http://172.20.59.7:8081/
登录: admin / admin123
```

如果 FAIL：
- 看后端 log: `tail -f /opt/app/shared/logs/backend-v20260714_001.log`
- 看前端 log: `tail -f /opt/app/shared/logs/frontend-v20260714_001.log`

---

## 4. 浏览器验证

### 4.1 访问前端

浏览器：`http://172.20.59.7:8081/`

应该看到登录页面。

### 4.2 登录

- 用户名：`admin`
- 密码：`admin123`

### 4.3 验证核心功能

菜单 → 架构数据管理 → 检查：
- ✅ 业务对象列表能正常加载（500 条/页，~126ms）
- ✅ 详情抽屉能正常打开
- ✅ enum 管理显示 `fullEditable` / `extensible` / `locked`（不应出现 `fully_editable`）

---

## 5. 出问题回滚

### 5.1 一键回滚

```bash
bash /tmp/deploy_bundle/rollback.sh --to v20260713_001 --port 3011
```

**回滚**：
- 停当前版本（3011）
- 启旧版本（3011，同端口替换）
- 切 current 链接 → 旧版本

### 5.2 完整回滚参数

```bash
bash /tmp/deploy_bundle/rollback.sh \
    --to v20260713_001 \                 # 必填 (回滚到的版本)
    --port 3011 \                        # 必填 (prod backend 端口)
    --frontend-port 8081 \               # 可选
    --deploy-root /opt/app \             # 可选
    --no-systemd                         # 可选
```

### 5.3 验证回滚成功

```bash
# 远端
curl -s -o /dev/null -w "3011: HTTP %{http_code}\n" http://localhost:3011/api/v1/health
# 应该 200

curl -s -o /dev/null -w "8081: HTTP %{http_code}\n" http://localhost:8081/
# 应该 200
```

---

## 6. 部署新版本

### 6.1 准备新 zip

```bash
# 本地
python tools/rebuild_bundle.py --zip deploy-v20260715_001.zip
```

### 6.2 上传 + 部署

```bash
# MobaXterm SFTP 上传新 deploy_bundle/

# 远端
bash /tmp/deploy_bundle/deploy.sh --version v20260715_001 --port 3011
```

**关键**：**不改脚本**，只改 `--version --port` 参数。

> **注意**: prod backend 固定使用 3011 端口。如需并行测试新版本，请部署到 staging (端口 13011)，
> 详见 [STAGING_GUIDE.md](docs/STAGING_GUIDE.md)。

---

## 7. 并行部署多版本（仅限测试）

> **V007.50 架构**: prod 固定 3011，staging 固定 13011。并行部署仅用于 A/B 测试，生产环境不建议。

prod (3011) + staging (13011) 可同时跑：

```bash
# prod (当前版本)
bash /tmp/deploy_bundle/deploy.sh --version v20260714_001 --port 3011

# staging (测试版本)
bash /opt/app/staging/scripts/deploy_staging.sh
```

**注意**：
- prod 8081 和 staging 18081 是独立的前端代理，互不影响
- staging db 与 prod 隔离（`/opt/app/staging/meta/architecture.db`）
- 详见 [STAGING_GUIDE.md](docs/STAGING_GUIDE.md) 第 4 节完整部署流程

---

## 8. 文件位置速查

### 远端 (172.20.59.7)

| 路径 | 内容 |
|------|------|
| `/opt/app/deployments/current` | 符号链接，指向当前激活版本 |
| `/opt/app/deployments/meta/` | prod 当前版本目录（server.py 所在） |
| `/opt/app/deployments/v<version>/` | 历史版本目录 |
| `/opt/app/shared/logs/` | 所有日志 |
| `/opt/app/backups/` | db 备份 |
| `/tmp/deploy_bundle/` | 部署包（SFTP 上传的）|
| `/opt/app/staging/` | staging 环境根目录（V007.50） |

### 本地 (D:\filework\worktrees/release-prep)

| 路径 | 内容 |
|------|------|
| `tools/` | 所有脚本（手工维护，源） |
| `deploy_bundle/` | 一键部署包（`rebuild_bundle.ps1` 生成，含 `[GENERATED]` 标记） |
| `docs/STAGING_GUIDE.md` | staging 使用指南（V007.50） |
| `docs/OPS_MANUAL.md` | 运维手册（4 端口架构） |

---

## 9. 部署时间线示例（V007.50 staging 部署）

| 时间 | 事件 | 工具 |
|------|------|------|
| 2026-07-13 22:34 | 首次部署 staging v20260713_223437 | deploy_staging.sh |
| 2026-07-13 22:38 | 修复后重部署 staging v20260713_223807 | deploy_staging.sh |
| 2026-07-14 08:00 | 发现 DB 路径冲突（DataSource 双 instance） | `/proc/PID/fd` 排查 |
| 2026-07-14 08:30 | 修复: deploy/current/architecture.db → symlink | start_staging_v00750.sh |
| 2026-07-14 09:00 | 验证: 进程 fd 只有 1 个 .db 文件 | `ls -la /proc/PID/fd/` |
| 2026-07-14 15:00 | 综合环境健康检查通过 | perf_check4.py |

---

## 10. 相关文档

- [docs/STAGING_GUIDE.md](docs/STAGING_GUIDE.md) — staging 使用指南（V007.50 4 端口架构）
- [docs/OPS_MANUAL.md](docs/OPS_MANUAL.md) — 远程运维服务智能体使用手册
- [DEPLOY_SOP_V2.md](DEPLOY_SOP_V2.md) — 部署 SOP（代码已部署 ≠ 数据已生效）
- [docs/INCIDENT_RESPONSE_RUNBOOK.md](docs/INCIDENT_RESPONSE_RUNBOOK.md) — 事故响应手册
- [docs/PERFORMANCE_BASELINE.md](docs/PERFORMANCE_BASELINE.md) — 性能基线（2026-07-14）
- [.trae/rules/core-service-architecture.md](../.trae/rules/core-service-architecture.md) — 元能力服务架构铁律
