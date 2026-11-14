---
description: "2026-09-02 staging 事故复盘 — 部署与 migration 基础设施不足点"
globs: ""
alwaysApply: false
---

# 2026-09-02 Staging 事故复盘

> **触发事件**: 172.20.59.7 staging 环境多服务崩溃 + 数据库半残 + 菜单/视图丢失
> **作者**: AI Assistant + 用户协同
> **状态**: 已修复完成（保留 3 个 DB 备份 + 4 个远程 patch）
> **目的**: 提炼流程/工具/规范层面的根因，避免重复

---

## 一、事故时间线（精简）

| 时间 | 现象 | 根因 |
|---|---|---|
| 09-01 晚 | staging 18081/19200 进程死亡，无人拉起 | 4 服务无统一守护 |
| 09-02 上午 | staging `org_members` 表缺失，login 500 | rollback 时漏掉 `v077` 表名列名回退 |
| 09-02 中午 | staging 视图全部消失（permission_set 等视图指向旧表） | rollback 时 DROP 了所有 view，没重建 |
| 09-02 下午 | staging `permission_sets` 表完全为空（FK 悬空） | rollback + rebuild 不完整 |
| 09-02 下午 | 用户点击 `/user-management` 无反应 | 前端 SPA 拿不到 accessible_menus（FK 悬空→JOIN 失败） |
| 09-02 晚 | staging `v_audit_all` view 缺失，列表 400 | rollback DROP view，未重建 |

**总修复时间**: ~6 小时；**总交互轮次**: ~80 轮；**创建临时脚本**: 22 个 `_tmp_*.py`

---

## 二、根因分类（5 类）

### 2.1 基础设施缺失（P0 - 必须修）

| # | 根因 | 现状 | 缺失 |
|---|---|---|---|
| A | **统一 rollback 流程缺失** | rollback = DROP view + 倒表列名 | 没重建 views/seed/admin/editor/viewer 权限集；没 post-check |
| B | **migration 幂等性不足** | v070-v079 都假设可重入 | SQLite 3.7.17 不支持 RENAME COLUMN / DROP COLUMN，跨 staging/prod 架构时必爆 |
| C | **数据库 schema 漂移检测缺失** | 无 SSOT 校验：YAML 期望 vs DB 实际 | 启动只 CREATE IF NOT EXISTS，不检查外键完整性、view 存在性 |
| D | **staging 与 local 同步通道缺失** | local → staging 全靠手动 zip deploy | 数据/视图/权限集不在 zip 内，deploy 后 staging 必然不齐 |
| E | **菜单双向同步机制缺失** | `init_menu_permissions.py` 启动时硬编码 `parent_menu: ''` 覆盖 v075 | v075 迁移永远会被 init 反向覆盖 |

### 2.2 工具链不足（P1 - 应该修）

| # | 根因 | 现状 | 缺失 |
|---|---|---|---|
| F | **无 staging 健康度一屏总览** | 每次重启/修复都手动 curl 4 个端口 + 翻 log | 缺一个 `staging_postcheck` 一次性验证：4 服务 UP + DB OK + views OK + permission_sets OK + v_audit_all OK + 6 个菜单可访问 |
| G | **无 migration 顺序推进工具** | v073 单独跑、v074-v079 一次跑、v079 又单跑 | 缺 `migrate_staging.py --from v070 --to v079` 一键推进 + 校验 |
| H | **remote ops 工具各自为战** | `core_service.py /api/exec`、`upload.py /api/upload`、`yexec`、`yupload`、`yuploaderun` 4 套命名 | 一会叫 yexec 一会叫 yonaa_exec，调用散乱 |
| I | **DB 备份链断裂** | 3 次修复 3 次手动 `shutil.copy2` | 缺统一的 `backup_db(db, label) → /opt/app/staging/backups/<ts>_<label>.db` + 索引 |
| J | **临时脚本无清理机制** | `test_helpers/_tmp_*.py` 22 个 | 无 TTL 清理 + 无 lint（已废弃的不删） |

### 2.3 流程规范缺失（P1 - 应该修）

| # | 根因 | 现状 | 缺失 |
|---|---|---|---|
| K | **rollback 没有"恢复后必跑清单"** | rollback 后只看 18081 HTTP 200 | 应强制跑：(1) init_menu_permissions (2) v_audit_all view 检查 (3) permission_sets admin/editor/viewer seed (4) 6 个核心菜单 accessible (5) dev-login smoke |
| L | **migration 后没有"双向一致性"验证** | 跑完 migration 直接进 13011 | 应该 staging vs local diff：(a) tables count (b) views count (c) permission_sets count (d) menu count (e) user-management 在 accessible_menus |
| M | **staging 数据完整性 vs local 对比缺失** | 菜单对齐靠手动跑 | 缺 `staging_diff.py --with local` 一次性报告差异 |
| N | **无 post-deploy smoke** | deploy 完只看 server.py 不挂 | 缺关键路径 smoke：dev-login → GET /menu-permission/visible → 验证 6 个 leaf_menus |

### 2.4 文档/SSOT 缺失（P2 - 可改进）

| # | 根因 | 现状 | 缺失 |
|---|---|---|---|
| O | **v070-v079 migration 没有 SPEC 文档** | 看 chat 历史才知道为啥要这些 | 缺 `migrations/CHANGELOG.md`（why / what / 顺序依赖 / 已知风险） |
| P | **init_menu_permissions 副作用没文档化** | 多次被它反覆盖 | 应在文件顶部大写 WARNING + system_menus 维护指南 |
| Q | **"为什么 staging 缺这些表"无复盘** | 事故已修但根因未沉淀 | 应有 INCIDENT_2026-09-02.md（已有，但内容偏少，缺流程反思） |

### 2.5 AI 协作效率（P2 - 可改进）

| # | 根因 | 现状 | 缺失 |
|---|---|---|---|
| R | **执行命令与规则理解混淆** | 用户"对比菜单"被理解成"修复 staging" | 多次跑完整迁移但用户其实只要 diff |
| S | **远程命令无 dry-run** | 直接对 staging 跑，错了再回滚 | 应该每个 staging ops 都有 `--dry-run` / `--local-only` 模式 |
| T | **状态信息每次都靠 SQL 查** | staging admin 是不是 6 个菜单都要 `SELECT COUNT(*) FROM permission_set_menu_permissions` | 应该 `staging_status.py` 一屏输出关键指标 |

---

## 三、最关键的 3 个改进（建议优先做）

### 3.1 P0: 统一 `staging_postcheck.py` — 事故一屏检测 ⭐⭐⭐

**Why**: 这次事故的所有根因（缺 view / 缺 permission_sets / 缺 menu / FK 悬空）都可以由它**1 次命令**检测出来，避免逐个排查浪费 80 轮交互。

**What**:
```bash
# 一次性验证（覆盖本次事故所有失败模式）
python tools/staging_postcheck.py --host 172.20.59.7
```

**应输出**:
```
✅ core_service 19200 UP
✅ log_service 19101 UP
✅ meta_backend 13011 UP (DB open OK)
✅ unified_18081 18081 UP
✅ views: v_audit_all exists
✅ permission_sets count: 3 (admin, editor, viewer)
✅ admin ps_menu_permissions: 6 rows
✅ admin ps_permissions: has '*'
✅ staging vs local menu diff: 0 critical
✅ /api/v1/menu-permission/visible returns 6 leaf_menus (user-management included)
✅ /api/v2/bo/permission_set?ordering=-updated_at returns 200
⚠️  org_permission_sets only 1 row (suggest binding more orgs)
⚠️  permission_set_dim_scopes empty (v079 seed not applied)
```

**实现位置**: `tools/staging_postcheck.py`（参考已有的 `staging_ops.py` + `staging_watchdog.sh`）

**检测内容（按本次事故根因）**:
1. 4 服务 HTTP 200
2. `SELECT name FROM sqlite_master WHERE type='view'` — 至少 `v_audit_all` 在
3. `SELECT COUNT(*) FROM permission_sets` — ≥ 3 (admin/editor/viewer)
4. `SELECT COUNT(*) FROM permission_set_menu_permissions WHERE permission_set_id=(admin id)` — ≥ 6
5. `SELECT COUNT(*) FROM permission_set_permissions WHERE permission_set_id=(admin id) AND permission_id=(SELECT id FROM permissions WHERE code='*')` — = 1
6. `GET /api/v1/menu-permission/visible` — 包含 user-management / permission-set-management
7. `GET /api/v2/bo/permission_set?ordering=-updated_at` — 200
8. （可选）`staging vs local` 菜单 SQL diff

**收益**:
- 事故检测从 80 轮交互 → 1 屏输出
- 未来类似问题（FK 悬空 / 缺 seed / 缺表）自动暴露
- rollback 后强制跑一次，避免人工遗漏

---

### 3.2 P0: 统一 `staging_migrate.py` — migration 推进工具 ⭐⭐⭐

**Why**: 本次 v070-v079 跨 7 次单独执行 + 手动 dump + 手动 rebuild，没有推进工具，每次都需要 AI 重新推导顺序。

**What**:
```bash
# 列出可执行的 migration（基于 schema_migrations 表）
python tools/staging_migrate.py list

# dry-run 推进（不执行，只 show plan）
python tools/staging_migrate.py apply --from v070 --to v079 --dry-run

# 真实推进
python tools/staging_migrate.py apply --from v070 --to v079

# 只看应用过的 migrations
python tools/staging_migrate.py status

# 回滚（DB 备份 + 倒序执行 downgrade）
python tools/staging_migrate.py rollback --to v069 --backup
```

**核心能力**:
- 自动解析 `meta/migrations/*.py` 的 `migrate(db_path)` 函数
- 自动检查依赖（v070 → v072 → v073 → ...）
- 自动备份：`shutil.copy2(db, backups/<ts>_pre_v070.db)`
- 自动 dry-run（先在临时 DB 执行，验证通过再实跑）
- 自动 post-check（跑完跑 `staging_postcheck.py`）

**收益**:
- 一次性推进 v070-v079，不用手动 7 次
- 每个 migration 必有 backup
- 强制 post-check 验证

---

### 3.3 P1: rollback SOP 文档化（不修代码，修流程） ⭐⭐

**Why**: 本次事故根本原因之一是"rollback 没有恢复清单"——只 DROP 了表/视图，没重建 admin seed，没 post-check，结果 staging 进入"半残态"运行了 1 天。

**What**: 在 `docs/STAGING_GUIDE.md` 增补 **§rollback 强制恢复清单**：

```markdown
## Rollback 强制恢复清单（v1.0 - 2026-09-02 复盘）

**触发条件**: 任何 staging 数据库 DROP TABLE / DROP VIEW / schema 重建 / 列名回退

**执行人**: AI Agent（自动）或 DevOps（手动）

### 必须恢复（按顺序）

1. **Views 重建**
   - 跑 `tools/staging_postcheck.py` 看哪些 view 缺
   - 跑对应 migration 重创建（v_audit_all → v007_50_add_audit_union_view.py）

2. **权限集 seed**
   - admin/editor/viewer 必须存在（migration v070 之后）
   - admin ps_menu_permissions 必须 ≥ 6 (arch-data, audit-log, org-management, permission-set-management, product-management, user-management)
   - admin ps_permissions 必须包含 '*'

3. **菜单 seed**
   - run `python meta/scripts/init_menu_permissions.py /opt/app/staging/meta/architecture.db`
   - 它会幂等 INSERT 缺失的菜单 + UPDATE 父菜单关系

4. **Post-check**
   - 跑 `python tools/staging_postcheck.py --strict`
   - 必须所有 ✅ 通过
   - 任意 ⚠️ 或 ❌ 必须先修复再走人

### 反模式（禁止）

- ❌ DROP 视图/表后只重启 server，看 200 就走
- ❌ rollback 不写 INCIDENT 文档
- ❌ 不备份就改 DB
```

**收益**:
- 未来 rollback 不会再次"半残"
- 文档即 SOP，新人/AI 都能照做

---

## 四、改进清单（按 ROI 排序）

| # | 改进 | 优先级 | 工作量 | 收益 |
|---|---|---|---|---|
| 1 | `staging_postcheck.py` 一屏检测 | P0 | 4h | 80 轮交互 → 1 次命令 |
| 2 | `staging_migrate.py` 一键推进 | P0 | 6h | 7 次手动 → 1 次 |
| 3 | Rollback 强制恢复清单文档 | P1 | 2h | 防再次半残 |
| 4 | `init_menu_permissions.py` 顶部大写 WARNING + 维护指南 | P1 | 1h | 防再被反覆盖 |
| 5 | `migration_lock` 表 + 推进幂等性 | P1 | 3h | 防重复执行 |
| 6 | v070-v079 SPEC 文档 / CHANGELOG | P2 | 4h | 知识沉淀 |
| 7 | 远程 ops 工具统一命名（yexec / yupload / yrunner 拆/合并） | P2 | 2h | 调用清晰 |
| 8 | `test_helpers/_tmp_*.py` TTL 清理脚本 | P2 | 1h | 仓库整洁 |
| 9 | INCIDENT_2026-09-02.md 完整复盘（链接到本文件） | P2 | 1h | 历史完整 |
| 10 | `staging_status.py` 一屏关键指标（staging_postcheck 的简化版） | P2 | 2h | 日常运维 |

---

## 五、立即可做（无需新工具）

以下操作可以直接套用现有工具完成，**不需要任何新代码**：

### 5.1 立即跑一次 staging_postcheck（手工版）—— 验证当前状态

```bash
# 一次性 SQL 检测 staging 当前状态
python -c "
import sys; sys.path.insert(0, 'd:/filework/excel-to-diagram/tools')
from staging_ops import exec_cmd

# views
r = exec_cmd('python3 -c \"import sqlite3; c=sqlite3.connect(\\\"/opt/app/staging/meta/architecture.db\\\"); print(\\\"\\\\n\\\".join(v[0] for v in c.execute(\\\"SELECT name FROM sqlite_master WHERE type=view\\\").fetchall()))\"', timeout=15)
print('=== views ==='); print(r.get('stdout',''))

# permission_sets
r = exec_cmd('python3 -c \"import sqlite3; c=sqlite3.connect(\\\"/opt/app/staging/meta/architecture.db\\\"); [print(dict(row)) for row in c.execute(\\\"SELECT id, code, name FROM permission_sets ORDER BY id\\\").fetchall()]\"', timeout=15)
print('=== permission_sets ==='); print(r.get('stdout',''))
"
```

### 5.2 写一份本次 patch 的 commit（待用户授权后）

```bash
# 本次修复的所有 staging-only patches 都应该 commit 到 deploy/ 但因为 staging 端是 deployed copy 而非 git worktree
# 建议：
# 1. 把 staging 上的 init_menu_permissions.py patch diff 同步到本地仓库
# 2. 把 v_audit_all view 重建脚本迁回 meta/migrations/（新增 v007.55 紧急 migration）
# 3. commit "fix: v_audit_all view + admin ps seed (incident 2026-09-02)"
```

### 5.3 把 `_tmp_*.py` 临时脚本迁移到正式位置

- `_tmp_recreate_v_audit.py` → `meta/migrations/v007_55_recreate_v_audit_all_for_staging.py`（让 staging 重新 init 时自动跑）
- `_tmp_fix_ps_seed.py` + `_tmp_grant_admin_perm.py` → 合并成 `meta/scripts/init_admin_seed.py`（server 启动时调用）

---

## 六、09-03 续篇：org_members 复发事故复盘（v1.1）

> **触发事件**: 09-03 早 staging 登录 500 `no such table: org_members`，修复后复发，再修后又出 `no such table: org_permission_sets`
> **修复**: 3 层（cron 禁用 + SQLITE_DB_PATH 修复 + deploy 树旧库 symlink 真库）
> **总耗时**: ~2.5h；**关键教训**: 修复被自己覆盖 + 假绿终验 + 打地鼠式修复

### 6.1 时间线

| 时间 | 事件 | 教训 |
|---|---|---|
| 03:00 | cron `sync_staging_db.sh` 用 **7 月 14 日旧备份**覆盖 staging DB（无任何日志告警） | 基础设施在静默对抗修复 |
| 08:0x | 定位到代码相对路径问题，本地修改 `user_authenticate.py`/`auth_api.py`（**未 commit**） | 埋下祸根 |
| 08:12-08:17 | R4 执行全量 git-tracked 恢复（6015 文件）→ **把未 commit 的修复覆盖回旧版** | 自己的恢复操作毁掉自己的修复 |
| 08:19 | R6 重启 + 终验用 `dev-login` → 全绿 | **假绿**：dev-login 不走完整 authenticate 链路 |
| 08:22 | 用户真实登录 `POST /api/v2/action/user.authenticate` → org_members 崩 | 用户成为真正的 smoke test |
| 08:39 | 部署 2 文件修复 + 真实路由复验 → 通过 | 终验必须用真实路由 |
| 08:45 | 用户报新错误 `no such table: org_permission_sets`（menu-permission API） | 同类问题第 2 处，说明是模式问题不是孤例 |
| 08:5x | 盘点发现 **60 处**运行时相对路径引用（40+ 文件）；所有引用落点汇于 `deploy/current/meta/architecture.db` 旧库 | 停止打地鼠，找共同失败面 |
| 08:5x | `mv` 旧库到 /tmp + `ln -s` 真库，一处修复覆盖全部 60 处 → 全绿 | 在正确的层修复：1 条命令 vs 40 文件 diff |

### 6.2 新增根因分类（在 2.1-2.5 基础上）

| # | 根因 | 层级 | 说明 |
|---|---|---|---|
| U | **DB SSOT 破坏：deploy 树内存在 architecture.db 旧副本** | P0 | 60 处相对路径（`__file__` 相对 / cwd 相对）全部落点于此；部署包不该含 DB，deploy 树不该有 DB 副本 |
| V | **DB 路径解析无统一 helper** | P0 | `os.environ.get('SQLITE_DB_PATH') or 相对路径` 模式散落 60 处；缺 `meta/core/db_path.py` 单点收敛 |
| W | **危险 cron 无清单无告警** | P0 | `sync_staging_db.sh` 每天 03:00 静默覆盖 DB；cron 应有清单 + 变更需审批 + 执行留日志 |
| X | **未 commit 的修复被全量恢复覆盖** | P0 | 流程铁律：**先 commit 再做任何 restore/deploy**；恢复操作前必须 `git status` 确认无未保存修复 |
| Y | **假绿终验：dev-login ≠ 真实登录** | P0 | smoke 必须打**前端真实调用的路由**（`POST /api/v2/action/user.authenticate`）+ 真实 payload，而非 dev/旁路路由 |
| Z | **同类错误复发时未及时上升到模式层** | P1 | 第 2 处 org_permission_sets 出现后才发现 60 处同款；应在第 1 处修复时就 grep 全量同类模式 |

### 6.3 已落地的修复（当前 staging 状态）

1. cron `sync_staging_db.sh` 已注释禁用
2. `user_authenticate.py` / `auth_api.py` 修复已 commit（`58ffb2c`）+ delta 部署
3. `/opt/app/staging/deploy/current/meta/architecture.db` → symlink → `/opt/app/staging/meta/architecture.db`（旧库备份在 `/tmp/old_deploy_meta_db_20260903.db`）
4. 终验改用真实路由：login 200 + menu-permission/visible 200 + matrix 非 null

### 6.4 改进清单执行状态（#11-15 已全部落地 2026-09-03）

| # | 改进 | 状态 | 落地方式 |
|---|---|---|---|
| 11 | `meta/core/db_path.py` 统一 helper + 批量替换 | ✅ commit `48ca72a` | 74 处替换（66 文件，api/services/core 全量），`get_meta_db_path()` env 优先；staging 已同步部署 + 真实路由复验全绿。symlink 补丁仍保留作双保险 |
| 12 | 部署包排除 `*.db` | ✅ commit `5c30416` | (a) git untrack 107 个 DB 文件（`meta/backups/` 85MB 历史备份是 deploy 树旧库的土壤）+ .gitignore 规则；(b) `smart_extract.sh` v2 重写（ASCII 注释根治乱码语法错）+ FULL/DELTA 双模式 db-guard，已部署远端 3 个位置并实测 guard 生效 |
| 13 | staging cron 清单化 | ✅ 记录于 §6.6 | 实际清单极简：仅 1 条已禁用 cron + 3 个系统级 |
| 14 | smoke 三连固化 | ✅ commit `9824438` | `tools/staging_postcheck.py`：16 项检测（4 端口 + DB 链路 + 真实登录路由 + menu + matrix），实测 16/16 ALL GREEN |
| 15 | 残留进程 6580 | ✅ 已清理 | 8 月 1 日孤儿进程 `/tmp/unified_8081.py`（占 8081 端口），pkill（正则技巧防自匹配）后 8081 释放、18081 无恙 |

### 6.6 staging cron 清单（2026-09-03 盘点）

| 来源 | 内容 | 状态 |
|---|---|---|
| root crontab | `0 3 * * * sync_staging_db.sh`（用 7 天前备份覆盖 staging DB——设计即灾难） | 已禁用（行首 `#DISABLED#`） |
| /etc/cron.d/log_service_monitor | log_service 监控 | 保留 |
| /etc/cron.d/0hourly, sysstat | 系统标准 | 保留 |

**规则**：新增/修改 staging cron 必须在本表登记 + 用户审批；DB 类同步任务一律禁止静默覆盖。

### 6.5 三条最深的教训（写给未来 AI/人）

1. **先 commit 再动 staging**：任何 restore/deploy 之前 `git status` 必须干净。未提交的修复等于不存在，且会被自己的工具链销毁。
2. **终验 = 复刻用户真实路径**：dev-login、curl 首页 200、端口监听都是假绿。只有打前端真实调用的路由 + 真实参数，绿才算绿。
3. **同类错误出现第 2 次时立即停止修实例**：grep 全量找共同失败面，在正确的层（环境/架构/模式）一次修完。

---

## 七、CHANGELOG

| 日期 | 变更 | 内容 |
|---|---|---|
| 2026-09-02 19:00 | AI Assistant | v1.0 创建复盘文档：5 类根因 + 3 大改进 + 立即可做清单 |
| 2026-09-03 09:00 | AI Assistant | v1.1 增补 §六 09-03 org_members 复发复盘：6 类新根因 (U-Z) + 已落地修复 + 3 条核心教训 |
| 2026-09-03 10:00 | AI Assistant | v1.2 改进 #11-15 全部落地：db_path 统一 (48ca72a)、DB untrack + smart_extract v2 db-guard (5c30416)、postcheck 16/16 (9824438)、cron 清单、残留进程清理 |

---

**下一步建议**：
1. **用户决策**：先做哪个改进？（建议：1+3 共 6h，能解决 80% 问题）
2. **立即可做**：跑 §五.1 的 staging_postcheck 手工版验证当前真实状态
3. **AI 待办**：把 `_tmp_recreate_v_audit.py` 迁成正式 migration（用户授权后）