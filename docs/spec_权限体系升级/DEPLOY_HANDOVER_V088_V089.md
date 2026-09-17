# DEPLOY_HANDOVER_V088_V089

> **接手对象**: 部署智能体 (Trae / 任何 IDE Agent)
> **交出方**: Trae Agent (2026-09-15)
> **状态**: ⏳ 等待接手执行
> **范围**: Spec 19 M4 软删 (v088) + DROP legacy 表 (v089) 的 staging + prod 部署
> **风险**: 🟡 中 (prod DROP 11 张 legacy 表)

---

## 0. TL;DR (30 秒版)

**任务**: 把 commit `65d5870` + `7c7f5e2` 推到 origin，部署到 staging + prod，让 v088 + v089 迁移在两个环境跑起来。

**已经为你做完的事**:
1. ✅ 代码 commit (`65d5870`) — 80 files, 3019/-912
2. ✅ 部署文档 commit (`7c7f5e2`) — 2 files, 419/-81
3. ✅ preflight cold backup (staging 116MB + prod 137MB)
4. ✅ 数据摸底 (prod role_permissions 427 行已在 permission_set_permissions 961 行里覆盖)
5. ✅ 测试 collection 0 错误 (8 → 0)

**你需要做的**:
1. `git push origin main`
2. `python tools/v19_p2_preflight_backup.py --both` (再跑一次, 双保险)
3. 按 [`V088_V089_DEPLOY_RUNBOOK.md`](./V088_V089_DEPLOY_RUNBOOK.md) §3 走 staging 7 步
4. staging 通过后, 按 §4 走 prod 5 步
5. 出问题按 runbook §5 回滚 (30 秒内可还原)

---

## 1. 接手前必读 (5 分钟)

### 1.1 必须理解的核心事实

| # | 事实 | 证据 |
|---|---|---|
| 1 | v088 + v089 是 Spec 19 M4 软删 + DROP 收尾, 不是新功能 | [Spec 19 §10 TBD-4](19_org_admin_delegation.md) |
| 2 | 11 张 legacy 表 (roles/user_groups/...) 里的数据**全部已迁移**到 spec16 RENAME 后的新表 | [`V088_V089_DATA_PICKUP_REPORT.md` §1.2](./V088_V089_DATA_PICKUP_REPORT.md) |
| 3 | v088 软删对象 (`orgs.manager_id` / `org_members.is_manager`) **真实数据 0 行** (admin 走 is_admin() 全局放行) | [`V088_V089_DATA_PICKUP_REPORT.md` §1.1](./V088_V089_DATA_PICKUP_REPORT.md) |
| 4 | 代码层对 legacy 表的运行时引用 = **0** (services/api/core 全 grep 过) | [`V088_V089_DATA_PICKUP_REPORT.md` §1.3](./V088_V089_DATA_PICKUP_REPORT.md) |
| 5 | DROP 是不可逆, 但 backup 116MB+137MB 已就位, 回滚 SLA 30 秒 | [`V088_V089_DATA_PICKUP_REPORT.md` §2.3](./V088_V089_DATA_PICKUP_REPORT.md) |
| 6 | prod `role_permissions` 有 427 行, 但**已迁移**到 `permission_set_permissions` (961 行, 含 v087 backfill + 历史新增) | [`v19_v089_legacy_safety_audit.py`](../../tools/v19_v089_legacy_safety_audit.py) |

### 1.2 不要做的事

| # | 不要做 | 原因 |
|---|---|---|
| 1 | 不要跑 `git reset --hard` 退回 v088 之前的 commit | backup 路径固定, 回滚用 `cp + DELETE FROM schema_migrations` 而非 git reset |
| 2 | 不要修改 `org_service.py` / `org_api.py` 的 is_manager 软删逻辑 | 这是已 PM 决策过的最终态, 改回去会破坏受托管理员 |
| 3 | 不要跳过 `v19_p2_preflight_backup.py --both` 直接部署 | DROP 不可逆, 必须有最新 backup |
| 4 | 不要合并 v088 + v089 为一个版本号 | 拆开是为了回滚粒度 (软删可以独立撤销) |
| 5 | 不要并行推 staging + prod | staging 必须先验证, 浏览器 DoD 5 min, prod 必须在 staging 通过后再上 |
| 6 | 不要把 `tools/v19_p2_*.py` 删了 | audit/preflight 是长期运维工具, 不是一次性脚本 |

### 1.3 必须遵守的约束

| # | 约束 | 来源 |
|---|---|---|
| 1 | 用 `python tools/deploy_upload.py upload` 单文件部署, 不要用 `git pull` 拉全仓 | [staging-runbook §2.16 r017 split-double](../../docs/staging-runbook.md) |
| 2 | migration 必须用 `python3 -m meta.core.migration_runner` (远端 python3, 不在本机) | [meta/core/migration_runner.py §_cli_main](../../meta/core/migration_runner.py) |
| 3 | prod deploy 必须 `APPROVED_DEPLOY=1` 环境变量 + `--files` 显式列出文件 | [staging_round.py §prod-deploy](../../tools/staging_round.py) |
| 4 | 浏览器级 DoD 必须用 `test_helpers/browser_auth_cli.py` (PlaywrightCLI), **禁止用 MCP 浏览器** | [.trae/rules/SESSION_REMINDER.md §浏览器测试铁律](../../.trae/rules/SESSION_REMINDER.md) (如果存在) |
| 5 | commit 前不要 `git config --global` 改 user/email (用户配置, 不要动) | 系统默认铁律 |

---

## 2. 接手清单 (Checklist)

### 2.1 Phase 0: 准备 (5 分钟)

- [ ] **读 3 份核心文档**:
  1. [`V088_V089_DEPLOY_RUNBOOK.md`](./V088_V089_DEPLOY_RUNBOOK.md) (12 步部署清单)
  2. [`V088_V089_DATA_PICKUP_REPORT.md`](./V088_V089_DATA_PICKUP_REPORT.md) (数据摸底)
  3. [`V088_V089_TD4_TD5_CHANGE_REPORT.md`](./V088_V089_TD4_TD5_CHANGE_REPORT.md) (代码收尾)

- [ ] **确认当前 commit**:
  ```bash
  cd d:\filework\excel-to-diagram
  git log --oneline -3
  # 预期: 7c7f5e2 docs(perm) ... runbook ...
  #       65d5870 chore(perm) ... Spec 19 M4 ...
  ```

- [ ] **确认 backup 文件存在**:
  ```bash
  # 远端 staging
  ls -la /opt/app/staging/meta/architecture.db.preflight_v088_v089_*
  # 远端 prod
  ls -la /opt/app/deployments/meta/architecture.db.preflight_v088_v089_*
  # 预期: 2 个文件各 ~116MB / ~137MB
  ```

- [ ] **PM 决策三选**:
  - 数据已迁移? → YES
  - v089 DROP 11 张表? → YES
  - 现在就执行 staging? → YES (推荐)

### 2.2 Phase 1: 推送 + 备份 (3 分钟)

- [ ] **Step 1: git push**:
  ```bash
  git push origin main
  ```
  预期: 2 个 commit 推到 origin/main, SHA `7c7f5e2` 在远端

- [ ] **Step 2: 再次 backup (双保险)**:
  ```bash
  python tools/v19_p2_preflight_backup.py --both
  ```
  预期: 4 个 backup 文件 (staging 2 个 + prod 2 个, 含最新 stamp)
  如果 backup FAIL: **abort, 不要继续**

### 2.3 Phase 2: staging 部署 (10 分钟)

详细命令见 runbook §3, 这里给关键检查点:

- [ ] **Step 3: staging 上传 11 个文件** (runbook §3.3)
  ```bash
  python tools/deploy_upload.py upload \
    meta/migrations/v088__deprecate_manager_id_and_is_manager.py \
    meta/migrations/v089__drop_legacy_user_group_and_role_tables.py \
    meta/services/org_service.py \
    meta/services/user_group_service.py \
    meta/api/org_api.py \
    meta/schemas/org.yaml \
    meta/schemas/org_member.yaml \
    meta/schemas/generated_schema.sql \
    meta/scripts/init_auth_tables.py \
    meta/scripts/permission_audit.sql \
    meta/tests/factories/permission_set.py \
    meta/tests/conftest.py \
    --target staging
  ```
  预期: 12/12 文件上传成功, MD5 一致

- [ ] **Step 4: staging dry-run migration**:
  ```bash
  # 远端 staging
  cd /opt/app/staging
  python3 -m meta.core.migration_runner --dry-run
  ```
  预期输出含:
  ```
  Pending migrations:
    v088: deprecate manager_id and is_manager
    v089: drop legacy user group and role tables
  ```
  **如果 pending 为空**: v088/v089 已跑过 (异常, abort)
  **如果有 v0xx 错误**: 看 migration_runner 输出排查

- [ ] **Step 5: staging 执行 migration**:
  ```bash
  # 远端 staging
  cd /opt/app/staging
  python3 -m meta.core.migration_runner
  ```
  预期:
  - v088: `[v088] migrate: OK`, `[v088] verify: PASS`
  - v089: `[v089] migrate: OK (DROP 9 张表)`, `[v089] verify: PASS`

  **如果 v089 FAIL (legacy 表不存在)**: 这是正常的, DROP IF EXISTS 幂等
  **如果 v089 FAIL (DB locked)**: lsof 查谁在用, abort

- [ ] **Step 6: staging 重启 + 验证**:
  ```bash
  # 本地
  python tools/staging_round.py preflight
  python tools/staging_round.py status
  ```
  预期: 5 项 preflight PASS, status 显示 round N 已部署

- [ ] **Step 7: staging 浏览器 DoD**:
  ```python
  # d:/filework/excel-to-diagram/test_helpers/browser_auth_cli.py
  from test_helpers.browser_auth_cli import PlaywrightCLI

  with PlaywrightCLI() as cli:
      cli.authenticated_navigate('/system/permission_set')
      # 测试 1: add_group_member(is_manager=True) → 400 + DEPRECATED_IS_MANAGER
      # 测试 2: 受托管理员 (matrix org 行规则) 仍能管受托组织
  ```
  DoD 清单:
  - [ ] 受托管理员范围操作返回 200
  - [ ] `add_group_member(is_manager=True)` 返回 400 + `DEPRECATED_IS_MANAGER`
  - [ ] 前端组织详情页不显示 is_manager 字段
  - [ ] `sqlite3 < permission_audit.sql` 跑通 0 错误

### 2.4 Phase 3: prod 部署 (10 分钟)

仅在 Phase 2 全部 ✅ 后执行:

- [ ] **Step 8: prod preflight** (runbook §4.1):
  ```bash
  python tools/staging_round.py prod-preflight
  ```
  预期: 4 项 PASS

- [ ] **Step 9: prod 一站式 deploy** (runbook §4.2):
  ```bash
  APPROVED_DEPLOY=1 python tools/staging_round.py prod-deploy \
    --files \
      meta/migrations/v088__deprecate_manager_id_and_is_manager.py \
      meta/migrations/v089__drop_legacy_user_group_and_role_tables.py \
      meta/services/org_service.py \
      meta/services/user_group_service.py \
      meta/api/org_api.py \
      meta/schemas/org.yaml \
      meta/schemas/org_member.yaml \
      meta/schemas/generated_schema.sql \
      meta/scripts/init_auth_tables.py \
      meta/scripts/permission_audit.sql \
      meta/tests/factories/permission_set.py \
      meta/tests/conftest.py \
    --verify-endpoints /api/v2/bo/permission_set /api/v2/bo/org /api/v1/auth/dev-login
  ```
  预期:
  - DB backup 自动落到 `.bak_<stamp>`
  - 12 文件上传 + 重启 + introspect 全过
  - 3 个 verify-endpoint 全 200

- [ ] **Step 10: prod dry-run migration** (runbook §4.3):
  ```bash
  # 远端 prod (走 staging_round.py use_prod_gateway)
  python3 -m meta.core.migration_runner --dry-run
  ```
  预期: 同 staging

- [ ] **Step 11: prod 执行 migration** (runbook §4.4):
  ```bash
  # 远端 prod
  python3 -m meta.core.migration_runner
  ```
  预期: v088 + v089 全部 PASS (prod role_permissions 427 行会被 DROP)

- [ ] **Step 12: prod 验证** (runbook §4.5):
  ```bash
  python tools/staging_round.py prod-status
  ```
  预期: 服务 OK + 0 落后 commits

### 2.5 Phase 4: 收尾 (5 分钟)

- [ ] **commit 部署后状态**:
  ```bash
  # 本地: 更新 PM_PROMOTE_STATUS.md 标注部署完成
  # 替换 "⏳ 等待 PM" → "✅ 已部署 2026-XX-XX"
  git add docs/spec_权限体系升级/PM_PROMOTE_STATUS.md
  git commit -m "docs(perm): v088+v089 staging+prod 部署完成 (<date>)"
  ```

- [ ] **(可选) 删除一次性工具** (如果不再用):
  ```bash
  # tools/v19_p2_audit_remote.py (一次性摸底, 可保留作长期审计)
  # tools/v19_p2_preflight_backup.py (建议保留作长期运维工具)
  # tools/v19_v089_legacy_safety_audit.py (一次性校验, 可保留)
  ```

- [ ] **更新 Spec 19 文档**:
  - `19_org_admin_delegation.md` 头部状态加 "M4 已部署 2026-XX-XX"
  - 标记 TBD-4 (org/user_group 双表收敛) 为 ✅ 已解决

---

## 3. 失败处理 (Incident Response)

### 3.1 常见失败模式

| 症状 | 原因 | 处理 |
|---|---|---|
| `git push` 报 401/403 | token 过期 | 联系用户重置 token, 不要改 .git/config |
| deploy_upload 上传后 MD5 不一致 | 网络中断 | 重试 upload, 单文件幂等 |
| migration_runner 报 `no such column` | v088 验证失败, 数据异常 | abort, 看 schema_migrations 表当前 state |
| `add_group_member(is_manager=True)` 返回 500 | 代码层 deprecation 拦截没生效 | 重启 server.py, 看日志 |
| 受托管理员返回 403 | OrgAdminScopeService 受影响 | abort, 检查 v084/v088 顺序 |
| prod 部署后 500 | 备份/迁移/重启某一步失败 | **立即回滚**, 见 §3.2 |

### 3.2 回滚命令 (30 秒内可还原)

**staging**:
```bash
# 1. 还原 DB
cp /opt/app/staging/meta/architecture.db.preflight_v088_v089_<stamp> \
   /opt/app/staging/meta/architecture.db

# 2. 清掉 schema_migrations 里的 v088/v089
sqlite3 /opt/app/staging/meta/architecture.db \
  "DELETE FROM schema_migrations WHERE version IN ('v088', 'v089');"

# 3. 重启 server.py
systemctl restart staging-backend  # 或对应服务名

# 4. 验证 (runbook §5)
python tools/staging_round.py preflight
```

**prod**:
```bash
# 1. 用 staging_round 工具回滚 (推荐)
python tools/staging_round.py prod-rollback --to <stamp>
# 加 --confirm 才真正执行, 默认 dry-run

# 2. 或手动 (紧急)
cp /opt/app/deployments/meta/architecture.db.preflight_v088_v089_<stamp> \
   /opt/app/deployments/meta/architecture.db
# 清 schema_migrations
# 重启
```

### 3.3 上报模板

如果遇到本交接文档没覆盖的失败:

```markdown
## Incident Report

**时间**: YYYY-MM-DD HH:MM
**环境**: staging / prod
**步骤**: Phase X Step Y
**症状**: <一句话描述>
**影响范围**: <用户/服务/数据>
**已尝试**: <已做的修复>
**需要决策**: <具体问题, 选项 A/B/C>
**相关 SHA**: <当前 commit SHA>
**backup stamp**: <部署前 backup 时间戳>
```

上报到 PM, 不要自行决策继续/回滚。

---

## 4. 关键文件 / 工具 / 链接 索引

### 4.1 必须看的 4 份文档

| 文档 | 路径 | 用途 |
|---|---|---|
| 部署 runbook | [`V088_V089_DEPLOY_RUNBOOK.md`](./V088_V089_DEPLOY_RUNBOOK.md) | 12 步 + 回滚 |
| 数据摸底 | [`V088_V089_DATA_PICKUP_REPORT.md`](./V088_V089_DATA_PICKUP_REPORT.md) | 决策证据 |
| 代码收尾 | [`V088_V089_TD4_TD5_CHANGE_REPORT.md`](./V088_V089_TD4_TD5_CHANGE_REPORT.md) | 测试 fixture + audit.sql |
| PM 状态 | [`PM_PROMOTE_STATUS.md`](./PM_PROMOTE_STATUS.md) | 整体进度 |

### 4.2 必须用的 3 个工具脚本

| 工具 | 路径 | 作用 |
|---|---|---|
| 远程 backup | [`tools/v19_p2_preflight_backup.py`](../../tools/v19_p2_preflight_backup.py) | staging+prod 冷备份 |
| 数据摸底 | [`tools/v19_p2_audit_remote.py`](../../tools/v19_p2_audit_remote.py) | 远程 DB 摸底 |
| 安全性校验 | [`tools/v19_v089_legacy_safety_audit.py`](../../tools/v19_v089_legacy_safety_audit.py) | 验证新表覆盖 legacy |

### 4.3 必须懂的 4 个工具 (不需要修改)

| 工具 | 路径 | 作用 |
|---|---|---|
| migration runner | [`meta/core/migration_runner.py`](../../meta/core/migration_runner.py) | 跑 v088/v089 |
| staging 部署 | [`tools/staging_round.py`](../../tools/staging_round.py) | staging 6 步 |
| 文件上传 | [`tools/deploy_upload.py`](../../tools/deploy_upload.py) | 单文件上传 |
| 浏览器验证 | [`test_helpers/browser_auth_cli.py`](../../test_helpers/browser_auth_cli.py) | PlaywrightCLI |

### 4.4 spec 文档

| 文档 | 路径 | 用途 |
|---|---|---|
| Spec 19 主体 | [`19_org_admin_delegation.md`](./19_org_admin_delegation.md) | M4 背景 + FR/NFR |
| Spec 16 改名 | [`16_role_to_permission_set_and_user_group_to_org.md`](./16_role_to_permission_set_and_user_group_to_org.md) | legacy 表怎么来的 |
| staging runbook | [`../staging-runbook.md`](../../docs/staging-runbook.md) | 部署 SOP + 历史教训 |
| PROD 部署 | [`../PROD_DELTA_DEPLOY_RUNBOOK.md`](../../docs/PROD_DELTA_DEPLOY_RUNBOOK.md) | prod 部署细节 |

---

## 5. 上下文快照 (Snapshot)

### 5.1 当前代码状态

```bash
$ git log --oneline -3
7c7f5e2 docs(perm): Spec 19 M4 部署 runbook + PM 状态更新 (v088+v089 deploy ready)
65d5870 chore(perm): Spec 19 M4 软删 v088 + v089 DROP legacy + 测试 fixture 重命名 + audit.sql V2
1dba6c1 perf(audit): v3.61 FK 结构化 N+1 → batch query (relationship 9 FK 从 9-18 次 SQL 降到 4 次)
```

### 5.2 工作区状态 (清理后)

```
M (modified): 0
?? (untracked): 12 个调试残留 (.startup_state_slot*.json, MagicMock/, screenshots/, waitress.err, logs/meta_resp.json, meta/tests/test_v_audit_perf_local.py)
```

这些是 Trae / Vite / debug 残留, **不影响部署**, 部署后用 `git clean -fd` 清掉。

### 5.3 已知 已知

| # | 已知问题 | 影响 | 处理 |
|---|---|---|---|
| 1 | staging_round.py deploy 含 frontend dist 部署 | 跟 migration 独立 | 不要用 `staging_round.py deploy` (它会包 dist), 用 `deploy_upload.py upload` 单文件 |
| 2 | staging_round.py 的 `use_prod_gateway()` 切换 prod 路由 | prod 操作必须走这个 | 不要试图直接 `ssh prod`, 走工具链 |
| 3 | `python` vs `python3` 在远端 | 远端是 `python3`, 本机是 `python` | 见 runbook §3.4-3.5 (远端 python3, 本地 python) |
| 4 | migration_runner 必须 `--db-path` 显式 | 默认走 env `SQLITE_DB_PATH` | 远端 env 已配, 不需要传 `--db-path` |

### 5.4 不在本次范围的项 (避免 scope creep)

| # | 任务 | 排期 |
|---|---|---|
| 1 | DROP COLUMN `orgs.manager_id` (SQLite 3.35+) | 2027-Q1, v09x |
| 2 | DROP COLUMN `org_members.is_manager` | 2027-Q1, v09x |
| 3 | 删 P9 Sunset shim (`user_group_service.py` + `factories/permission_set.py`) | 2027-Q1, 跟 DROP COLUMN 一起 |
| 4 | Spec 19 M3 (FR-007 强化 + FR-008 UI + 委托审计报表) | 2026-Q4 |
| 5 | Spec 19 TBD-6 (实例级有效权限树) | 立项待定 |
| 6 | Spec 22 (state_transition 入 action 池) | 草案 v1.2, 立项待 PM |

---

## 6. 接手方自检 (Self-Check)

部署完成后, 部署智能体应该自检:

- [ ] **commit 65d5870 + 7c7f5e2 已在 origin/main**
- [ ] **staging DB 的 schema_migrations 含 v088 + v089 两条**
- [ ] **staging DB 的 sqlite_master 不含 legacy 11 张表**
- [ ] **prod DB 的 schema_migrations 含 v088 + v089 两条**
- [ ] **prod DB 的 sqlite_master 不含 legacy 11 张表**
- [ ] **staging 受托管理员路径 200**
- [ ] **staging add_group_member(is_manager=True) 返回 400 + DEPRECATED_IS_MANAGER**
- [ ] **prod 受托管理员路径 200 (admin token)**
- [ ] **prod add_group_member(is_manager=True) 返回 400 + DEPRECATED_IS_MANAGER**
- [ ] **PM_PROMOTE_STATUS.md 已更新到"已部署"**
- [ ] **backup 文件没删, 留作 7 天观察期回滚用**

如有任何自检项不通过, 走 §3.2 回滚命令 + 上报 PM。

---

## 7. 联系 / Escalation

- **交出方**: Trae Agent (本次上下文)
- **接手方**: 部署智能体 (下一个 session)
- **决策人**: PM (`dev@archworkspace.local`)
- **紧急回滚**: 见 §3.2, SLA 30 秒
- **复杂问题**: 上报 PM, 见 §3.3 模板

---

**生成时间**: 2026-09-15
**状态**: ⏳ 等待接手
**下次同步**: Phase 4 完成后, 部署智能体更新 PM_PROMOTE_STATUS.md 并 commit 部署后状态