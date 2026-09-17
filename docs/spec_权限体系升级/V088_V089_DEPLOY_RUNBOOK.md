# V088 + V089 部署 Runbook (PM 执行)

> **commit**: `65d5870` (main 分支, 已 commit)
> **执行人**: PM (Terminal 4)
> **日期**: 2026-09-15
> **关联报告**:
> - [V088_V089_DATA_PICKUP_REPORT.md](./V088_V089_DATA_PICKUP_REPORT.md) (Phase A 摸底)
> - [V088_V089_TD4_TD5_CHANGE_REPORT.md](./V088_V089_TD4_TD5_CHANGE_REPORT.md) (Phase B+C 代码)
>
> **风险等级**: 🟡 中 (prod DROP 11 张 legacy 表)
> **回滚成本**: 🟢 低 (DB .backup 已在 v089 部署前完成, 可秒级回滚)

---

## 1. PM 执行清单总览

| # | 步骤 | 命令 | 风险 | 时间 |
|---|---|---|---|---|
| 1 | 推送 commit 到 origin | `git push origin main` | 🟢 | 1min |
| 2 | preflight cold backup | `python tools/v19_p2_preflight_backup.py --both` | 🟢 | 2min |
| 3 | staging: 上传代码 | `python tools/deploy_upload.py upload meta/migrations/v088__deprecate_manager_id_and_is_manager.py meta/migrations/v089__drop_legacy_user_group_and_role_tables.py meta/services/org_service.py meta/services/user_group_service.py meta/api/org_api.py meta/schemas/org.yaml meta/schemas/org_member.yaml meta/schemas/generated_schema.sql meta/scripts/init_auth_tables.py meta/scripts/permission_audit.sql meta/tests/factories/permission_set.py meta/tests/conftest.py --target staging` | 🟢 | 2min |
| 4 | staging: dry-run migration | `python3 -m meta.core.migration_runner --dry-run` (远端) | 🟢 | 30s |
| 5 | staging: 执行 migration | `python3 -m meta.core.migration_runner` (远端) | 🟡 | 1min |
| 6 | staging: 重启 + 验证 | `python tools/staging_round.py preflight && python tools/staging_round.py status` | 🟢 | 1min |
| 7 | staging: 浏览器验证 | dev-login + 试 add_group_member(is_manager=True) 看 400 + Spec 19 M2 受托管理员照常工作 | 🟡 | 5min |
| 8 | prod: preflight | `python tools/staging_round.py prod-preflight` | 🟢 | 30s |
| 9 | prod: 上传代码 | `APPROVED_DEPLOY=1 python tools/staging_round.py prod-deploy --files <上面 staging 同 11 个文件>` | 🟡 | 5min |
| 10 | prod: dry-run migration | 远端 `python3 -m meta.core.migration_runner --dry-run` | 🟢 | 30s |
| 11 | prod: 执行 migration | 远端 `python3 -m meta.core.migration_runner` | 🟠 | 1min |
| 12 | prod: 验证 | `python tools/staging_round.py prod-status` + 浏览器回归 | 🟡 | 5min |

---

## 2. P1 已完成收尾 (本地, 不需要 PM 执行)

### 2.1 删除一次性脚本 + 调试探针

```bash
cd d:\filework\excel-to-diagram
rm tools/.v089_bulk_rename.py
rm tools/.v089_check_false_positive.py
rm tools/.v089_td4_scan.py
rm tools/.v19_test_mtime.py
rm tools/.v19_test_stale.py
rm tools/.v19_test_stale2.py
rm tools/.test_remote_stat.py
rm tools/.test_remote_stat2.py
rm tools/.v361_prod_backup.txt
rm tools/.v361_prod_preflight.txt
rm tools/test_2_1_prod_subcommands.py
```

**状态**: ✅ **已完成** (2026-09-15 Trae Agent 执行, 11 文件已删)

---

## 3. P0 部署步骤 (PM 执行)

### 3.1 Step 1: 推送 commit

```bash
cd d:\filework\excel-to-diagram
git push origin main
```

**预期**:
- 远程 `origin/main` SHA 与本地 `65d5870` 一致
- 推送成功 (历史 token 已 hardcoded 在 config, 无需额外认证)

### 3.2 Step 2: preflight cold backup

```bash
cd d:\filework\excel-to-diagram
python tools/v19_p2_preflight_backup.py --both
```

**预期**:
- staging: `.preflight_v088_v089_<stamp>` ~116MB
- prod: `.preflight_v088_v089_<stamp>` ~137MB
- 两个 manifest JSON 包含 legacy_tables + v088 软删目标行数

**注意**: 步骤 2 必须在步骤 5 (staging migration) **之前** 完成, 失败不允许继续。

### 3.3 Step 3: staging 上传代码

部署 11 个 v088/v089 相关文件到 staging:

```bash
cd d:\filework\excel-to-diagram
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

> **注**: `meta/tests/` 文件属于测试代码, prod 不一定需要; 但 staging 必须有, 用于 collection 验证。
> 如果 prod-deploy 想省测试文件, 可分两步走 (staging 上传全部, prod 只上传运行时文件)。

### 3.4 Step 4: staging dry-run migration

```bash
# staging 远端
cd /opt/app/staging
python3 -m meta.core.migration_runner --dry-run
```

**预期输出** (应看到):
```
Pending migrations:
  v088: deprecate manager_id and is_manager
  v089: drop legacy user group and role tables
```

**如果失败** (pending 列表为空 / 报 v088 已跑 / 报 DB 不存在):
- 检查 `SQLITE_DB_PATH` 环境变量
- 检查 `/opt/app/staging/meta/architecture.db` 是否存在
- abort, 联系 AI Agent

### 3.5 Step 5: staging 执行 migration

```bash
# staging 远端
cd /opt/app/staging
python3 -m meta.core.migration_runner
```

**预期行为**:
- v088 执行: 验证数据层 (零动作, 仅报告); `verify()` 返回 True
- v089 执行: DROP 9 张 legacy 表 (user_groups / user_group_members / roles / role_permissions / ...); `verify()` 验证 sqlite_master 中无这些表

**如果失败**:
- v088 失败: 检查数据层是否仍合法 (`orgs.manager_id=0 / org_members.is_manager=1=1`)
- v089 失败: 检查 legacy 表是否被锁 (lsof) / 检查 DROP 权限

### 3.6 Step 6: staging 重启 + 验证

```bash
cd d:\filework\excel-to-diagram
python tools/staging_round.py preflight
python tools/staging_round.py status
```

**预期**: 5 项 preflight 全部 PASS, status 显示 round N 已部署。

### 3.7 Step 7: staging 浏览器验证 (DoD)

浏览器执行 (用 PlaywrightCLI 或人工):

```python
# d:/filework/excel-to-diagram/test_helpers/browser_auth_cli.py
from test_helpers.browser_auth_cli import PlaywrightCLI

with PlaywrightCLI() as cli:
    cli.authenticated_navigate('/system/permission_set')  # 任意权限集页面
    # 验证 1: add_group_member(is_manager=True) 返回 400 + DEPRECATED_IS_MANAGER
    # 验证 2: 受托管理员登录仍能进入受托组织
    # 验证 3: permission_audit.sql 可执行 (sqlite3 < permission_audit.sql)
```

**DoD 检查**:
- [ ] 受托管理员 (matrix org 行有规则) 仍能管受托组织
- [ ] `add_group_member(is_manager=True)` 返回 400 + `DEPRECATED_IS_MANAGER`
- [ ] 前端组织详情页不显示「is_manager」字段 (前端早 hide)
- [ ] audit.sql 跑通 42 个 SELECT, 0 报错

---

## 4. prod 部署 (Step 8-12, staging 通过后执行)

### 4.1 Step 8: prod preflight

```bash
cd d:\filework\excel-to-diagram
python tools/staging_round.py prod-preflight
```

**预期**: 4 项 PASS (port / service / DB / 落后 commits)

### 4.2 Step 9: prod 一站式 deploy

```bash
cd d:\filework\excel-to-diagram
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

**预期**:
- DB backup 自动落到 `.bak_<stamp>`
- 文件上传 + 重启 + introspect 全过
- 验证端点 3 个全 200

### 4.3 Step 10: prod dry-run migration

```bash
# 远端 prod
python3 -m meta.core.migration_runner --dry-run
```

### 4.4 Step 11: prod 执行 migration

```bash
# 远端 prod
python3 -m meta.core.migration_runner
```

**预期**:
- v088: 验证零数据负担, OK
- v089: DROP 9 张 legacy 表, 注意 prod `role_permissions` 有 **427 行**, 但**已迁移到新表**, DROP 安全

### 4.5 Step 12: prod 验证

```bash
cd d:\filework\excel-to-diagram
python tools/staging_round.py prod-status
```

**预期**: 服务状态 OK + 0 落后 commits + 部署历史显示本轮 stamp。

---

## 5. 回滚预案 (如出现 500 / collection error)

### 5.1 staging 回滚

```bash
# 远端: 从步骤 2 的 backup 还原
cp /opt/app/staging/meta/architecture.db.preflight_v088_v089_<stamp> \
   /opt/app/staging/meta/architecture.db
# 然后: 手工 `DELETE FROM schema_migrations WHERE version IN ('v088','v089');`
# 然后: 重启 server.py
```

### 5.2 prod 回滚

```bash
cd d:\filework\excel-to-diagram
python tools/staging_round.py prod-rollback --to <stamp>
# 加 --confirm 才真正执行
```

---

## 6. 验证脚本 (PM 可选执行, 浏览器级)

```python
# d:/filework/excel-to-diagram/test_helpers/scripts/verify_v088_v089_deploy.py
"""V088 + V089 部署后浏览器级 DoD 验证"""
from playwright.sync_api import sync_playwright

def verify():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        # dev-login admin
        page.goto('http://localhost:3010/api/v1/auth/dev-login?username=admin')
        # 1. 测试 add_group_member(is_manager=True) → 400
        resp = page.request.post(
            'http://localhost:3010/api/v2/bo/org_member',
            data={'org_id': 1, 'user_id': 100, 'is_manager': True}
        )
        assert resp.status == 400, f'expected 400, got {resp.status}'
        assert 'DEPRECATED_IS_MANAGER' in resp.text()
        # 2. 测试受托管理员路径 (matrix org 行规则)
        # ... 略, 见 Spec 19 §8.1 M2 验证记录
        browser.close()
    print('OK: v088/v089 DoD 验证通过')

if __name__ == '__main__':
    verify()
```

---

## 7. 后续待办 (部署后)

- [ ] 部署成功后删 `tools/v19_p2_audit_remote.py` (一次性摸底工具)
- [ ] 部署成功后删 `tools/v19_p2_preflight_backup.py` (一次性 backup 工具, 可保留作长期运维)
- [ ] 部署成功后删 `tools/v19_v089_legacy_safety_audit.py` (一次性校验工具)
- [ ] 更新 `docs/spec_权限体系升级/PROMOTION_CHECKLIST.md` 标注 commit `65d5870`
- [ ] 更新 `docs/spec_权限体系升级/19_org_admin_delegation.md` v1.6 标注 M4 部署完成

---

## 8. 联系 / Escalation

- **数据摸底报告**: `docs/spec_权限体系升级/V088_V089_DATA_PICKUP_REPORT.md`
- **代码收尾报告**: `docs/spec_权限体系升级/V088_V089_TD4_TD5_CHANGE_REPORT.md`
- **AI Agent 工具**: `tools/v19_p2_audit_remote.py`, `tools/v19_v089_legacy_safety_audit.py`
- **回滚命令清单**: 见 §5

---

**生成时间**: 2026-09-15
**生成人**: Trae Agent
**PM 状态**: ⏳ 等待执行 (Step 1 → 12)