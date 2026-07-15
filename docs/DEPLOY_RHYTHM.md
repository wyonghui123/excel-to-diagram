# DEPLOY_RHYTHM.md

> **目标读者**: AI Agent / 工程师
> **最后更新**: 2026-07-15 (新增部署节奏约定)
> **本文件用途**: 明确"日常 vs hotfix" 部署节奏, 避免每次都走完整流程
> **总入口**: [DEPLOY_INFRASTRUCTURE.md §0](../DEPLOY_INFRASTRUCTURE.md)

---

## §0. 一图全貌

```
  日常开发流 (默认)                    Hotfix 流 (P0 故障)
  ────────────────                    ──────────────
  ┌────────────────┐                  ┌────────────────┐
  │ 1. 写代码/test │                  │ 1. 紧急修复    │
  └───────┬────────┘                  └───────┬────────┘
          ▼                                   ▼
  ┌────────────────┐                  ┌────────────────┐
  │ 2. 提交+本地测 │                  │ 2. 提交+本地测 │
  └───────┬────────┘                  └───────┬────────┘
          ▼                                   ▼
  ┌────────────────────────────────────────────────────────────┐
  │ 3. STAGING 部署 (每天 1-3 次)                              │
  │    - upload + migrate + monitor                            │
  │    - 观察 5-30 分钟                                         │
  └────────────────────────┬───────────────────────────────────┘
                           │
       ┌───────────────────┴───────────────────┐
       ▼                                       ▼
  ┌────────────────┐                  ┌────────────────┐
  │ 4a. 等 PROD    │                  │ 4b. 立即 PROD   │
  │     窗口       │                  │   (skip 观察)   │
  │   每天 21:00    │                  │   Hotfix 模式   │
  └───────┬────────┘                  └───────┬────────┘
          ▼                                   ▼
  ┌────────────────┐                  ┌────────────────┐
  │ 5. PROD 部署   │                  │ 5. PROD 部署   │
  │ 6. 灰度观察 24h│                  │ 6. 重点监控 1-2h│
  └────────────────┘                  └────────────────┘
```

---

## §1. 节奏表

| 维度 | 日常 (Daily) | Hotfix |
|------|-------------|--------|
| **频率** | 每天 1-3 次 staging 部署 | 立刻 |
| **STAGING 观察期** | **5-30 分钟** | **1-5 分钟** (sanity) |
| **PROD 部署时机** | **每天 21:00 (固定窗口)** | **立刻** |
| **PROD 灰度观察** | 24h | 1-2h 重点监控 |
| **风险等级** | 一般 | P0 |
| **回滚 SLA** | 1h 内 | 15 分钟内 |

---

## §2. PROD 部署时间窗口 (推荐)

```
  ┌────────────────────────────────────────────────────────┐
  │ 固定窗口：每天 21:00 - 22:00                            │
  │                                                        │
  │ 原因:                                                  │
  │  - 21:00 后用户活跃度下降 (核心工作时间外)              │
  │  - 出问题有 8h 修复窗口 (到次日 6:00 早高峰)            │
  │  - 团队下班前, 有人盯盘                                 │
  │  - 周末/节假日: 推到下一个工作日 21:00 (除非 hotfix)   │
  └────────────────────────────────────────────────────────┘
```

**变更窗口** (改动部署时间):
- 任何变更: 走 PR review, 至少 1 人确认
- 紧急: PM / 技术负责人同意

---

## §3. Hotfix 触发条件 (任一即触发)

- [ ] **P0 故障**: 500 错误 / 服务挂 / 数据损坏
- [ ] **安全漏洞**: 已知 CVE / 越权 / 注入
- [ ] **数据不一致**: DB 状态污染 / migration 错误
- [ ] **用户阻塞**: 核心功能完全不可用 (>50% 用户受影响)

**其他情况 (P1/P2)** → 走日常节奏。

---

## §4. 流程差异

### §4.1 日常 (Daily) — 完整流程 8 步

```bash
# === 1-2. 本地: 写代码 + 提交 + 本地 e2e ===
cd d:\filework\release-prep-worktree
git status -s                  # 确认改了哪些
$env:ALLOW_RAW_SQL="1"
python -m pytest meta/tests/xxx -v

# === 3. STAGING 部署 (delta + migration) ===
python tools/staging_deploy_orchestrator.py
# 或手动:
#   - yupload 新文件
#   - 跑 migration_runner
#   - 验证 monitor + archive dry-run

# === 4a. 等 PROD 窗口 (到 21:00) ===
# 在此期间: 监控 staging, 收集反馈, 修小问题

# === 5. PROD 部署 ===
# 走 staging_deploy_orchestrator 但改参数 (prod port)
# 关键步骤:
#   - 备份 DB: deploy.sh PHASE 2
#   - 跑 migration: deploy.sh PHASE 2.6
#   - lint: deploy.sh PHASE 2.55
#   - restart service: restart.sh

# === 6. 灰度观察 24h ===
# 监控:
#   - backend log
#   - user 反馈
#   - monitor_migrations (每 6h 跑一次)
#   - 出问题 → rollback (用旧版本 vXXX)
```

### §4.2 Hotfix — 压缩流程 4 步

```bash
# === 1. 紧急修复 (定位 + 修) ===
# 关键: 修复尽量小, 不要夹带其他改动

# === 2. 提交 + STAGING (压缩观察) ===
git add + commit
python tools/staging_deploy_orchestrator.py
# 观察 1-5 分钟, 只看核心冒烟

# === 3. 立即 PROD (skip 等待窗口) ===
# 走标准 prod 部署流程
# 关键: 通知团队 (群里说一下)

# === 4. 重点监控 1-2h ===
# 盯盘:
#   - backend log (tail -f)
#   - 1h 后跑一次 monitor_migrations
#   - 通知 PM / 技术负责人监控结果
#   - 出问题 → 立即 rollback
```

---

## §5. 决策树 (该走哪条流?)

```
  发现问题 / 需求
       │
       ▼
  ┌────────────────────┐
  │ 是否 P0 触发条件?  │
  │ (见 §3 列表)        │
  └────┬───────────────┘
       │
   ┌───┴───┐
   ▼       ▼
  是       否
   │       │
   ▼       ▼
  Hotfix  日常
   │       │
   ▼       ▼
  §4.2   §4.1
```

---

## §6. 实施清单

### §6.1 推荐自动化 (未来可做)

- [x] `staging_deploy_orchestrator.py --mode daily` (V007.55 已支持)
- [x] `staging_deploy_orchestrator.py --mode hotfix` (V007.55 已支持)
- [x] `prod_deploy_orchestrator.py` (V007.55 一键 prod 部署, 含备份)
- [x] `monitor_migrations.py --check-regression` (V007.55 回归测试告警)
- [x] `regression_test_suite.py` (V007.55 9 场景 sqlite io error 演练)
- [x] `sqlite_chaos.py` deprecated + `--redirect-to-regression` 软迁移
- [ ] `watch.sh` 加 cron 任务 (每 6h 跑 monitor_migrations)
- [ ] Slack/IM 通知 (部署开始/结束/失败 + regression FAIL)
- [ ] DB 自动备份到 OSS (7 天保留)
- [ ] cron 每天 9 点跑 `monitor_migrations --check-regression` + 告警

### §6.2 当前状态 (2026-07-15)

- ✅ 日常流程: 跑得通 (本会话已走 8 步)
- ✅ Hotfix 流程: 工具已支持 (`DEPLOY_MODE=hotfix`)
- ✅ 回归测试: 集成到 staging_deploy_orchestrator Step 10.5 + monitor --check-regression
- ✅ V007.55 完成: systemd unit 守护 log_service (install_log_service_systemd.py) + cron 告警 (setup_log_service_cron.py)
- ⚠️ 自动监控: watch.sh 需手工启动, 没 cron
- ⚠️ 通知: 手工 (无 IM 集成)

---

## §7. 历史决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-07-15 | 默认 daily 21:00, hotfix 立即 | 避免 staging 观察太久, 集中 prod 风险 |
| 2026-07-15 | Hotfix 4 步压缩 | 紧急修复, 1-5 分钟 sanity 已够 |
| 2026-07-15 | PROD 灰度 24h | 用户活跃度 + 修复窗口 |

---

**总入口**: [DEPLOY_INFRASTRUCTURE.md](../DEPLOY_INFRASTRUCTURE.md) §0
**5 分钟速查**: [AGENT_INFRA.md](AGENT_INFRA.md)
**Migration 实战**: [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md)
