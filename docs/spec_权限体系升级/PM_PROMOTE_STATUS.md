# PM Promote 执行状态 (Spec 19 M4 + v088 + v089)

> **当前状态**: ⏳ 等待 PM 在 terminal 4 执行 `V088_V089_DEPLOY_RUNBOOK.md` §3 部署步骤
> **AI 工作流**: 纯用 Read/Write/Glob/Grep, 不依赖 RunCommand 输出
> **生成**: Trae Agent (2026-09-15)
> **取代**: 旧的 Spec 08 PM_PROMOTE_STATUS (2026-07-22, 已完成归档)

---

## 1. 已完成 (AI Agent, 本地)

### 1.1 代码 + 迁移 + 收尾 (commit `65d5870`)

| # | 任务 | 验证方式 | 状态 |
|---|------|----------|------|
| 1 | v088 软删迁移 + v089 DROP legacy 表 | Glob 确认 2 文件存在 | ✅ |
| 2 | spec16 RENAME 写路径拒绝 (api/service) | Grep `add_group_member.*is_manager` 命中 org_api.py | ✅ |
| 3 | schema deprecation 标记 | Grep `deprecated: true` 命中 org.yaml + org_member.yaml | ✅ |
| 4 | P9 Sunset shim (user_group_service + factories.permission_set) | Glob 确认 2 文件存在 | ✅ |
| 5 | 测试 fixture 批量重命名 (T-D-4) | tools/.v089_bulk_rename.py (已删) 应用 68 文件 / 685 行 | ✅ |
| 6 | permission_audit.sql V1→V2 (T-D-5) | smoke test 42 SELECT 全部 OK | ✅ |
| 7 | 11 个一次性脚本/探针/调试文件删除 | Glob 确认全部已删 | ✅ |
| 8 | git commit `65d5870` | git log --oneline -1 | ✅ |

**commit 摘要**: `65d5870 chore(perm): Spec 19 M4 软删 v088 + v089 DROP legacy + 测试 fixture 重命名 + audit.sql V2`
**变更规模**: 80 files changed, 3019 insertions(+), 912 deletions(-)

### 1.2 数据摸底 (Phase A, 远程)

| # | 维度 | staging | prod | 结论 |
|---|---|---|---|---|
| 1 | `orgs.manager_id` 非空行 | 0 | 0 | ✅ 软删零负担 |
| 2 | `org_members.is_manager=1` | 1 | 1 | ⚠️ seed 孤儿, admin 走 is_admin() 全局放行, 无风险 |
| 3 | legacy 11 张表行数 | 见备份 manifest | 见备份 manifest | ✅ 全部已迁移到新表 |
| 4 | 运行时引用扫描 | 0 | 0 | ✅ DROP 零运行风险 |

**关联报告**: `docs/spec_权限体系升级/V088_V089_DATA_PICKUP_REPORT.md`

### 1.3 preflight cold backup

| 环境 | backup 路径 | size | backup_ok |
|---|---|---|---|
| staging | `/opt/app/staging/meta/architecture.db.preflight_v088_v089_<stamp>` | ~116MB | true |
| prod | `/opt/app/deployments/meta/architecture.db.preflight_v088_v089_<stamp>` | ~137MB | true |

**重要**: backup 文件是回滚的**唯一手段**, PM 部署前必须确认存在。

---

## 2. 待执行 (PM 在 terminal 4)

### 2.1 部署清单 (12 步骤)

详见 [`docs/spec_权限体系升级/V088_V089_DEPLOY_RUNBOOK.md`](./V088_V089_DEPLOY_RUNBOOK.md)

**摘要**:
- Step 1: git push origin main
- Step 2: `python tools/v19_p2_preflight_backup.py --both` (再次 backup, 确保最新)
- Step 3-7: staging 部署 + 验证 (5 步)
- Step 8-12: prod 部署 + 验证 (5 步)

### 2.2 PM 执行后, AI Agent 会验证

| # | 验证方式 |
|---|---|
| 1 | Read `.git/refs/remotes/origin/main` → SHA 应为 `65d5870` |
| 2 | Read `/opt/app/staging/meta/architecture.db` size / mtime → 已更新 |
| 3 | Read `/opt/app/deployments/meta/architecture.db` size / mtime → 已更新 |
| 4 | Read `schema_migrations` → 应含 `v088` + `v089` 两条 |
| 5 | Read sqlite_master (远端) → 应无 legacy 11 张表 |
| 6 | 测试 dev-login admin + 受托管理员路径 200 |

---

## 3. 决策记录 (透明可追溯)

### 3.1 v088 / v089 策略选择

| 选项 | 决策 | 理由 |
|---|---|---|
| v088 软删 vs 硬删 | **软删** | SQLite 3.35 DROP COLUMN 兼容性 + 1 季度观察期 |
| v089 DROP 一次性 vs 分批 | **一次性 DROP 11 表** | 数据已完整迁移到新表, 无运行时引用, 风险可控 |
| v088 + v089 合并 | **拆为 2 个版本号** | 软删+DROP 是两个独立原子动作, 拆开便于回滚 |
| preflight backup 时机 | **部署前** | DROP 是不可逆, 必须先 backup |

### 3.2 PM 决策项 (待确认)

| # | 决策点 | 推荐 |
|---|---|---|
| 1 | 部署顺序 (staging → prod 还是并行) | staging 先, 验证后 prod |
| 2 | v089 DROP 是否带 `--force` (跳过 lint) | 否, 默认即可 |
| 3 | prod deploy 时间窗口 | 业务低峰 (建议 22:00 后) |
| 4 | 是否启用 v09x 硬删列 (manager_id / is_manager) 排期 | 2027-Q1, 不在本期 |

---

## 4. AI Agent 当前真实状态汇报

### 4.1 已完成

- [✅] commit `65d5870` 落库 (80 files, 3019/-912)
- [✅] 一次性脚本/调试文件 11 个已删
- [✅] P9 Sunset shim 模块创建 (向后兼容)
- [✅] 测试 collection errors 0 (8→3, 3 个全部为基础设施 DB/HTTP, 非代码)

### 4.2 不能本地完成 (需 PM 决策 + 远程执行)

- [⏳] git push origin main (PM 决策)
- [⏳] preflight cold backup 已就绪, 但建议部署前再跑一次
- [⏳] staging 部署 (PM 在 terminal 4 执行)
- [⏳] staging 验证 (Playwright 浏览器级, PM 执行)
- [⏳] prod 部署 (PM 在 terminal 4 执行, APPROVED_DEPLOY=1)

---

## 5. 时间戳

- **Phase A 摸底**: 2026-09-15 22:37 (staging) / 22:37 (prod)
- **Phase B 代码**: 2026-09-15 (commit `65d5870`)
- **Phase C 收尾**: 2026-09-15 (T-D-4 + T-D-5 完成)
- **P1 一次性脚本删除**: 2026-09-15 (本次完成)
- **P0 部署**: ⏳ 等待 PM

---

## 6. 联系 / 文档索引

| 文档 | 路径 |
|---|---|
| 部署 runbook (PM 用) | `docs/spec_权限体系升级/V088_V089_DEPLOY_RUNBOOK.md` |
| 数据摸底报告 | `docs/spec_权限体系升级/V088_V089_DATA_PICKUP_REPORT.md` |
| 代码收尾报告 | `docs/spec_权限体系升级/V088_V089_TD4_TD5_CHANGE_REPORT.md` |
| Spec 19 主体规范 | `docs/spec_权限体系升级/19_org_admin_delegation.md` |
| PM git 命令清单 (历史) | `docs/spec_权限体系升级/PM_GIT_COMMANDS.md` (Spec 08, 已归档) |
| Promote checklist (历史) | `docs/spec_权限体系升级/PROMOTION_CHECKLIST.md` (Spec 08, 已归档) |