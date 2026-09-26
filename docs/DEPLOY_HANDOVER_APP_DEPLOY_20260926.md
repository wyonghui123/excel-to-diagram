# DEPLOY HANDOVER — app 维度部署 + 部署可见性

> **HANDOFF_FROM**: 平台架构改造（A 可见性 + B 清单驱动部署）
> **HANDOFF_TO**: 部署打包智能体（deploy agent）
> **RISK**: LOW —— 本轮**零部署**，纯工具/配置层改动，远端无写入
> **TIMESTAMP**: 2026-09-26
> **状态**: 代码完成 + 单测通过；**待 PM 确认后进行首次 staging 验证**

---

## 0. TL;DR

| 字段 | 值 |
|------|-----|
| 需求 | ① 部署时合理管理"指定 app → 指定服务器"；② 排查时快速知道某服务器部署了哪些 app |
| 交付形态 | 清单 SSOT（`deploy_topology.yaml`）+ app 路径解析 + `--apps` 部署 + `app-status` 三方对账 |
| 改动文件 | 6 个代码/配置 + 2 份 SKILL.md + 1 份 README + 2 个测试文件 |
| 是否已部署 | **否**。prod 与 staging 都还是旧代码 |
| 测试状态 | 新增 11 passed（B）+ 6 passed（A）；既有部署测试回归全绿 |
| 最大风险 | `AGENT_INFRA_DETAILED.md` §7 描述的是**已冻结的一代部署链**，与现行链不同（见 §5） |
| 首次验证建议 | 用现行 `--target staging` 文件级入口，把 A 三件套部署到 staging（见 §7.2） |

---

## 1. 背景：这块要解决什么问题

### 1.1 两个原始诉求

1. **部署时**：如何合理管理"指定 app 部署到对应服务器"——不能靠人记，要有单一真源。
2. **排查时**：站在一台服务器前面，如何快速知道"它到底部署了哪些 app"。

### 1.2 为什么不能直接看进程/目录

- 应用是**动态加载**的：`ENABLED_APPS` 环境变量决定进程启动时注册哪些 app（`meta/core/app_registry.py`）。
  目录里有 app 包 ≠ 该 app 被加载；`ENABLED_APPS` 设了但包没传上去 = 启动直接失败。
- 因此需要**三层信息**才能刻画"这台服务器有哪些 app"：
  | 层 | 来源 | 回答 |
  |----|------|------|
  | 应然 | `deploy_topology.yaml` 的 `apps` | 这服务器"应该"有哪些 app |
  | 实时 | `GET /health` 的 `apps_mode` / `enabled_apps` | 进程"此刻"加载了哪些 |
  | 事实 | 平台库同目录 `runtime_apps.json` | 最近一次启动"实际"加载了哪些 |

---

## 2. 交付物清单（改了什么）

### 2.1 A 阶段：可见性三件套（2026-09-25 完成）

| 文件 | 改动 | 说明 |
|------|------|------|
| `meta/core/app_registry.py` | 修改 | 新增 `_loaded_manifests` 状态、`get_loaded_apps()`、`write_runtime_apps_snapshot(db_path)`、常量 `RUNTIME_APPS_FILENAME = "runtime_apps.json"`；`reset_app_routing_index()` 清空状态；`register_apps()` 末尾登记已加载清单 |
| `meta/server.py` | 修改 | ① 启动期在 `register_apps` 之后落盘 `runtime_apps.json`（独立 try，失败只 warning、**绝不阻断启动**）；② `/health` 增加 `apps_mode` / `enabled_apps` / `apps[]` |
| `meta/tests/test_health_apps_visibility_20260925.py` | 新增 | 6 passed；覆盖 enabled / legacy 两模式 + 落盘内容 + 落盘失败不抛 |
| `.gitignore` | 修改 | 忽略运行期产物 `/meta/runtime_apps.json` |
| `.trae/skills/devops-deploy-sop/SKILL.md`（两份副本） | 修改 | 见 §2.3 |

关键设计：**legacy 模式零行为变化**。没启用 app 时 `/health` 追加 `apps_mode: legacy` + `apps: []`，不改变原有 `status` / `service` 字段语义。

### 2.2 B 阶段：清单驱动部署 + 对账（2026-09-26 完成）

| 文件 | 改动 | 说明 |
|------|------|------|
| `tools/config/deploy_topology.yaml` | 修改 | 每个 target 新增 `apps_root` + `apps: []`；production 另加 `db_path` |
| `tools/lib/deploy_topology.py` | 修改 | 新增 `repo_root()` / `rel_to_repo()` / `app_id_of()` / `list_app_package_files()` 与排除常量；`DeployTarget` 新增 `apps_root` / `apps` / `db_path` / `health_base_url` 字段；`resolve_remote_paths()` 增加 **apps 分支** + 清单门禁 |
| `tools/staging_round.py` | 修改 | 新增 `_load_deploy_target` / `_expand_app_files` / `_check_prod_app_prereqs` / `cmd_app_status`；`prod-deploy` 增加 `--apps`；新增 `app-status` 子命令 |
| `tools/deploy_upload.py` | 修改 | `cmd_resolve` 捕获 `ValueError`，把门禁报错打成 `[ABORT]` 而非 traceback |
| `tools/tests/test_app_deploy_topology_20260926.py` | 新增 | 11 passed，见 §6 |
| `tools/README_DEPLOY_INFRA.md` | 修改 | 新增 §6「app 维度部署 + 三方对账」 |
| `.trae/skills/devops-deploy-sop/SKILL.md`（两份副本） | 修改 | 「应用清单排查」段加 `app-status` 首选路径；新增「app 维度部署」段 |

### 2.3 两份 SKILL.md 是独立副本

```
d:\filework\excel-to-diagram\.trae\skills\devops-deploy-sop\SKILL.md
d:\filework\.trae\skills\devops-deploy-sop\SKILL.md
```

两份内容**不同步**（hash 不同），改一处必须手动改另一处。本次已同步修改。

---

## 3. 怎么用

### 3.1 预检（纯本地，不联网）

```bash
# 看某个文件会被放到远端哪里（会校验 app 清单门禁）
python tools/deploy_upload.py --target production resolve meta/core/app_registry.py
python tools/deploy_upload.py --target production resolve apps/hello_world/app.yaml
```

注意：`--target` **必须写在子命令之前**（既有 CLI 约定）。

### 3.2 排查：这台服务器有哪些 app（三方对账，全只读）

```bash
python tools/staging_round.py app-status --target production
python tools/staging_round.py app-status --target staging
```

输出三层 + 差异集合。`[PASS] 三方一致` 为正常；`[WARN]` 逐条列出不一致项。
`/health` 未上报 `apps_mode` ⇒ 该实例仍在跑旧代码（A 未部署）。

### 3.3 部署：平台文件（现行方式，未改变）

```bash
APPROVED_DEPLOY=1 python tools/staging_round.py prod-deploy --files meta/core/app_registry.py meta/server.py
```

### 3.4 部署：整个 app 包（B 新增）

```bash
APPROVED_DEPLOY=1 python tools/staging_round.py prod-deploy --apps warehouse
```

执行顺序：`[0/7]` app 清单展开 + 前置门禁（只读） → 原有 7 步。

- 文件集 = `apps/<id>/**`，**硬排除** `data/`、`__pycache__`、`*.pyc`、`*.db`
- 远端落点 = `{apps_root}/<id>/X`
- 清单门禁：未登记在 `apps` 里的 app → `[ABORT]`
- 前置门禁：prod 平台库缺 `installed_apps`（v090）→ `[ABORT]`，**不自动执行迁移**

---

## 4. 关键实测事实（省去重新侦察）

以下均为**实测**结论（2026-09-25/26 只读侦察 + 代码核实），不是文档推测。

### 4.1 现行部署主链

```
tools/staging_round.py prod-deploy --files <files>
  → 校验 APPROVED_DEPLOY=1
  → prod-preflight（4 项 sanity）
  → local HEAD vs prod 落后 commits 比对（warn 不阻断）
  → DB .backup + manifest
  → tools/deploy_upload.py upload --target production
      （file-level 增量上传 + per-file md5 + stale check + audit JSONL）
  → systemctl restart meta-backend.service
  → grace 8s + 3 次探活
  → introspect（远端 import 验证模块实际加载路径）
  → 端点验收
  → 写 tools/.prod_deploy_history.json（PENDING_VERIFY → OK / FAIL_RESTART / FAIL_VERIFY）
```

### 4.2 目标环境事实

| 项 | production | staging |
|----|-----------|---------|
| host | 172.20.59.7 | 172.20.59.7 |
| gateway 端口 | 9200（**HTTPS**，secret `v007.52-core`） | 19200 |
| `deploy_root` | `/opt/app/deployments/meta` | `/opt/app/staging/deploy/current` |
| resolver | `flat_meta_package` | `symlink_namespace_package` |
| 后端服务 / 端口 | `meta-backend.service` / `5001` | — / `13011` |
| 前端 | `meta-unified.service`（`unified_8081.py`）/ `8081` | — |
| 平台库 | `/opt/app/deployments/meta/architecture.db` | 待实测 |

### 4.3 prod 当前是"纯 legacy 平台实例，零应用"

- 远端**无 `apps/` 目录**
- DB **无 `installed_apps` 表**（迁移停在 v089）
- `menus` 表 40 条**无 app 行**
- `.env.prod` 只有 `PORT=5001`，**无** `ENABLED_APPS` / `APP_DB_ROUTING`
- 远端 `git: command not found`

### 4.4 探活端点：只有 `/health` 可用

| 端点 | 结果 |
|------|------|
| `/health` | **200** `{"status":"ok","service":"arch-data-manage-api"}` —— 唯一存活的无鉴权探活点 |
| `/api/v1/health` | **410**（被 v1 sunset 中间件接管） |
| `/api/v1/apps/<id>/health` | **410** |

> 仓库里多处仍引用 `/api/v1/health` 作为健康检查地址，**都是死端点**，见 §7.6。

### 4.5 迁移三事实（最容易被误判）

1. **`server.py` 启动不跑通用迁移。** 全仓 `run_all_migrations()`（`meta/core/migration_runner.py`）**只有定义、无调用者**；`meta/migrations/README.md` 里"启动兜底"的描述是**失效描述**。
2. **`prod-deploy` 不执行迁移。** 它只把"`schema_migrations` 末尾 5 条 SUCCESS"当作不变量校验，不推进迁移。
3. **per-app 迁移已 PoC 验证但未接线。** `meta/tests/test_per_app_migration_runner_probe.py` 证明 `MigrationRunner(应用库, migrations_dir=apps/<id>/migrations)` 的迁移/版本表/锁/备份**全部落在应用库**、不串平台库——但生产链上没有任何调用点。

### 4.6 app 包根路径的推导依据（不是猜的）

```python
# meta/core/app_loader.py
get_apps_root() = Path(__file__).resolve().parents[2] / "apps"
# prod: __file__ = /opt/app/deployments/meta/core/app_loader.py
#       parents[2] = /opt/app/deployments
#       ⇒ apps_root = /opt/app/deployments/apps   ← 与 meta/ 平级，不是 meta/apps
```

这直接决定了 `resolve_remote_paths()` 里 app 路径**不能套** `{deploy_root}/{relative}` 模板，必须走独立分支。

### 4.7 gateway 限制

- gateway 有**命令词法白名单**：`sqlite3 ... architecture.db` 被**拒绝**。
- ⇒ 任何需要读远端 DB 的操作，都要**写远端 python 脚本**执行（`write_remote_script` + `remote_exec`），不能用 `sqlite3` CLI。
- `tools/yonaa_exec.py` 的 `_http_get` **只支持明文 HTTPConnection**，直连 9200（HTTPS）会 `Remote end closed connection without response`。用 `staging_round.use_prod_gateway()` + `write_remote_script`。

### 4.8 delta deploy 现状

现行 `prod-deploy` **已是文件级增量**（显式 `--files` + per-file md5 + stale check + audit JSONL），但**没有 app 维度**。B 补齐了 app 维度展开；应用级"移除清理"与"记录级 app 快照"仍待做（见 §7）。

---

## 5. ⚠️ 最大的坑：三代部署链并存 + 指南已过期

**这是接手方最容易踩的坑，请优先读本节。**

仓库里同时存在三代部署链，**只有第三代是活的**：

| 代 | 入口 | 状态 | 证据 |
|----|------|------|------|
| 一代 | `scripts/build-deploy-package.sh` 打 zip → `deployments/v{version}` → `/opt/app/current` symlink → `pkill/nohup python server.py` | ❌ **已冻结** | 远端 `/opt/app/current -> v20260713_002`，MANIFEST 停在 2026-07-13 |
| 二代 | `tools/deploy_prod.sh`（core_service 9200 + staging smoke guardrail + `pkill -9`） | 🟡 部分被吸收 | — |
| 三代 | `tools/staging_round.py <target>-deploy` → `tools/deploy_upload.py`（file-level 增量） | ✅ **现行** | §4.1 |

### 5.1 过期文档清单（会误导）

- **`docs/AGENT_INFRA_DETAILED.md` §7「部署打包智能体专属指南」** —— 描述的是**一代链**：
  `verify_deploy_bundle.py 6/6 PASS 才许上传`、`deploy.sh` 按需解压、`rebuild_zip.py` 全量发版、zip + MANIFEST。
  **这套流程对现行的 file-level 部署不适用。**
- `.trae/skills/devops-deploy-sop/SKILL.md` 中若出现 `deploy.sh` / `/opt/app/current` / `build-deploy-package.sh`，同属一代链残留。
- 相关但已明确废弃的文件在 `.trae/rules/.deprecated/`（MCP 浏览器方案，与部署无关，仅说明本仓库有"废弃文档未删"的历史习惯——**读到相关文档务必先核对是否与代码一致**）。

### 5.2 接手方应该做的第一件事

**不要相信文档，先信代码。** 判定某条链是否现行，用这个顺序：

1. 看 `tools/config/deploy_topology.yaml` 里的 target 定义（这是 SSOT）
2. 看 `tools/staging_round.py` / `tools/deploy_upload.py` 的 argparse 子命令
3. 远端核对：`ls -l /opt/app/deployments/` 与 `systemctl status meta-backend.service`

---

## 6. 测试与验证证据

### 6.1 测试入口（**唯一合法入口**）

```powershell
python d:\filework\test.py --file <相对 repo 的路径>
```

**禁止**直接跑 `pytest`（会绕过 `TEST_ENTRY=1` 守护）。`test.py` 内部是 `PROJECT_ROOT / args.file`。

### 6.2 本轮验证结果

| 测试 | 结果 |
|------|------|
| `tools/tests/test_app_deploy_topology_20260926.py`（新增） | **11 passed** |
| `meta/tests/test_health_apps_visibility_20260925.py`（A） | **6 passed** |
| `tools/tests/test_prod_history_two_step_20260918.py` | 6 passed |
| `tools/tests/test_prod_restart_grace_20260918.py` | 4 passed |
| `tools/lib/test_path_resolvers.py` | 6 passed |
| `tools/tests/test_deploy_service.py` | ⚠️ 1 项失败：`test_deploy_worker_progression` |

**关于那 1 项失败**：`test_deploy_worker_progression` 在 Windows 上真实调 `deploy.sh`、依赖 `/tmp/test.zip` 存在，属**既有环境性失败**。`tools/deploy_service.py` 未被本次改动、且只 import 标准库。**不是本次引入的回归。**

### 6.3 新增测试覆盖了什么

1. `apps/<id>/...` 路径识别（`app_id_of`）
2. app 包文件集展开，**排除** `__pycache__` / `*.pyc` / `data/`
3. production / staging target 读取 `apps_root` / `apps` / `db_path` / `health_base_url`
4. app 远端落点 = `{apps_root}/<id>/...`（与 `meta/` 平级）
5. `apps_root` 缺失 → 报错
6. 清单门禁：未登记的 app 在 resolve 阶段即报错
7. `_expand_app_files` 门禁 + 展开（`SystemExit`）
8. **回归**：平台文件（`meta/**`）远端落点**不变**

### 6.4 CLI 层实测记录（纯本地 + 只读）

```
$ python tools/deploy_upload.py --target production resolve meta/core/app_registry.py
  → /opt/app/deployments/meta/core/app_registry.py        # 平台路径不变 ✅

$ python tools/deploy_upload.py --target production resolve apps/hello_world/app.yaml
  → [ABORT] app 'hello_world' 不在 target 'production' 的部署清单内 ...   # 门禁生效 ✅

$ python tools/staging_round.py app-status --target production
  [1/3] 应然: apps_root=/opt/app/deployments/apps  apps=[]
  [2/3] 实时: /health → apps_mode=None  enabled_apps=(未上报)
  [3/3] 事实: runtime_apps.json → 不存在
  [对账] [WARN] 无法取得实时应用清单 (/health 未上报 enabled_apps)
```

最后一条是**预期结果**：prod 还在跑旧代码，所以三层都不完整。A 部署上去之后，同样的命令应变成 `[PASS] 三方一致`。

---

## 7. 待办：后续持续优化

### 7.1 【必做·阻塞首次真实验证】staging 的 `apps_root` 只读实测

`deploy_topology.yaml` 的 staging 段目前填的是**推测值**并已标 `[待只读实测确认]`：

```yaml
apps_root: /opt/app/staging/deploy/current/apps   # ← 待确认
```

原因：staging 走 `symlink_namespace_package` 活树，`app_loader.__file__` 可能是
`current/meta/core/app_loader.py`（⇒ `current/apps`）或 `current/core/app_loader.py`（⇒ `deploy/apps`）。

**动作**：只读 `ls` 一次确认。在部署真实 app 到 staging 之前必须完成。

### 7.2 【建议下一步】首次 staging 验证：平台代码

建议用**现行文件级入口**，把 A 三件套部署到 staging：

```bash
# staging 后端文件走的不是 staging_round.py（它只管前端 dist 轮次），
# 而是 deploy_upload.py 直连：
python tools/deploy_upload.py --target staging upload meta/core/app_registry.py meta/server.py
```

> ⚠️ **`staging_round.py` 里没有 `staging-deploy` 子命令。** 它的子命令是
> `init` / `preflight` / `pack` / `deploy` / `verify` / `status` / `rollback`，
> 属于**前端 dist 轮次**的打包链（`pack` 出 zip → `deploy` 上传换 dist），
> 与后端 `.py` 文件级部署是两条不同的路。
>
> ⚠️ **`--target` 必须写在子命令之前。** `deploy_upload.py` 的 argparse 把
> `--target` 定义为全局参数，写在文件后面会 `unrecognized arguments`。
> 而它自己文件头 docstring（L10-28）的示例**恰好写反了**（`upload xxx.py --target staging`），
> 照抄会失败 —— 这是文档 bug，见 §7.8。
>
> ⚠️ staging 后端**可能需要手动重启服务**才能生效（prod 侧由 `prod-deploy` 负责 restart，
> `deploy_upload.py` 本身只上传不重启）。执行前请确认 staging 的重启方式。

一次同时验证三件事：
1. **现行链没被 B 改坏**（回归）
2. `/health` 出现 `apps_mode` / `enabled_apps`
3. `app-status` 从 `[WARN]` 变 `[PASS]`（第 3 层需先补 staging 的 `db_path`）

> 注意：这一步会**真实部署**。必须 PM 确认后执行。

### 7.3 B2：迁移顺序门禁升级为"显式执行"

现在 `_check_prod_app_prereqs()` 只做**只读检查 + abort**，意图是"绝不隐式改库"。
若要支持"一条命令完成 app 部署"，需要设计显式迁移步骤：

```
① 传迁移文件（v090__create_installed_apps.py 等）
② 显式执行迁移（需 PM 批准 + 备份）
③ 传 app 包（排除 data/）
④ 幂等写 .env.prod 的 ENABLED_APPS
⑤ restart
⑥ 对账（清单 vs /health vs installed_apps）
```

**设计约束**：迁移执行必须可审计、可回滚，且与 `deploy_upload` 的 audit JSONL 打通。

### 7.4 B3：app 移除清理

现在删掉清单里的 app 只是"不再上传"，**远端残留目录仍在**，`ENABLED_APPS` 若引用它会导致启动失败。
需要设计"清单移除 ⇒ 远端目录归档/清理"的显式步骤（不可静默删，要留归档）。

### 7.5 app 库备份

`prod-deploy` 的 DB backup 目前**只备份平台库**。app 有独立应用库（`data/<id>.db`）。
因为 app 库不在上传集内（已排除 `data/`），日常部署不会覆盖它；但**一旦执行应用级迁移**（§7.3）就可能改表。
⇒ 迁移功能接线时必须同时补 app 库备份。

### 7.6 死端点清理（低风险，建议同批修）

以下位置仍把 `/api/v1/health` 当健康检查地址，实际返回 **410**：

- `config/monitoring/prometheus.yml`
- `config/monitoring/prometheus-alerts.yml`
- `config/monitoring/grafana-dashboard.json`
- `config/environment/server-prod.toml` 的 `health_endpoint`
- `.trae/commands/health.md`
- `.trae/templates/DEPLOY_HANDOVER.template.md`
- `.trae/rules/core/e2e-testing.md`
- 若干 `docs/`

另有代码层遗漏点：`meta/core/app_builder.py` **L613-616** 内**也有一个 `/health` handler**，
目前只返回 `status` / `service`，**未加 apps 字段**。若该 handler 在某条链路上生效，
可见性会不一致（同一个服务两个 `/health` 实现，需确认 `ApplicationBuilder` 构建的 app
与 `meta/server.py` 的 app 是同一个还是两套）。

### 7.7 其他遗留（非本次范围）

- 未跟踪文件 `tools/_invariant_i1.py`、`tools/_invariant_introspect.py`（前序窗口遗留，待 PM 定夺去留）
- roadmap backlog：`permission_set_service.py` 同款破损写入点；"取消勾选菜单不回收已同步功能权限行"；"矩阵保存后元数据不自动重拉（需 F5）"；ROOT_ONLY `/app/*` 死路由

### 7.8 文档 bug 清理（低风险）

- `tools/deploy_upload.py` **文件头 docstring L10-28** 的示例把 `--target` 写在文件参数之后，
  实际会 `unrecognized arguments`。应改为 `--target <t> upload <files>` 的顺序。
  （该 docstring 是接手方的第一入口，写反的代价很高，建议优先修。）
- `tools/README_DEPLOY_INFRA.md` 中若出现同类示例，一并核对。

---

## 8. 约束与铁律（必须遵守）

| 约束 | 内容 |
|------|------|
| **测试入口** | 只能 `python d:\filework\test.py --file <路径>`；**禁**直接 `pytest` |
| **prod 写门禁** | `APPROVED_DEPLOY=1` 必须由 PM 显式批准后设置，不要在脚本里默认加 |
| **严禁覆盖应用库** | `apps/<id>/data/*.db` 是**运行数据**，任何部署路径都必须排除 |
| **不隐式改库** | 迁移一律显式执行 + 需批准；工具不得自动跑迁移 |
| **清单即真源** | "这台服务器该有哪些 app"只认 `deploy_topology.yaml` 的 `apps`，不认目录扫描 |
| **先实测再改方案** | 本仓库文档与代码存在不一致历史（§5），改前先核实代码/远端 |
| **浏览器测试** | 唯一合法入口 `test_helpers/browser_auth_cli.py`（PlaywrightCLI）；**禁** MCP 浏览器工具 |
| **PowerShell** | 不支持 `&&` / heredoc；**禁**内联 `python -c`（写探针 `.py` 文件执行） |
| **git** | 不更新 git config；不擅自 `--no-verify` 跳过钩子 |

---

## 9. 端口问题（常见误解，先澄清）

**端口按 instance 分配，不按 app 分配。**

- **现行（单实例多 app / 合并部署）**：多个 app 跑在**同一后端进程**内，是多个 blueprint。
  共用后端端口（prod `5001` / staging `13011`）与前端端口（prod `8081`）。
  真正独立的是：路由前缀 `/api/v1/apps/<id>`、前端路径 `/app/<id>`、应用库 `data/<id>.db`、菜单/权限命名空间。
- **独立部署（多实例）才多端口**：属 roadmap Phase 2，需 4 条触发条件之一（独立演进 / 不同团队维护 / 独立扩容与故障域隔离 / 交付隔离），**未触发不投入**。
  且 `deploy_topology.yaml` **尚无 `instances:` 段**，部署工具当前只支持"一个 target 一个 `deploy_root`"。
- 默认端口单一真源 = `scripts/ports.json`（`{frontend: 3006, backend: 3011}`）。
  多实例靠 **per-instance 环境变量覆盖**，默认值只认这一个文件。

**对部署清单的含义**：`apps` 清单**不需要端口维度**。可选的是记 `instance_name` 以区分"prod 实例"与将来可能的独立实例。

---

## 10. 关联文档

| 文档 | 用途 |
|------|------|
| `tools/config/deploy_topology.yaml` | **SSOT**：target / deploy_root / apps_root / apps |
| `tools/README_DEPLOY_INFRA.md` §6 | app 维度部署 + 三方对账（面向使用者） |
| `.trae/skills/devops-deploy-sop/SKILL.md`（2 份） | SOP：部署命令 + 应用清单排查 |
| `docs/platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md` | 拓扑 Type 1-4、应用机制、Type 2 实测（§10.14） |
| `docs/AGENT_INFRA_DETAILED.md` §7 | ⚠️ **过期**，描述一代链，见 §5 |
| `docs/AGENT_INFRA.md` §0.8 | 各智能体协同边界（部署智能体职责） |
| `meta/core/app_loader.py` | `AppManifest` / `get_apps_root()` |
| `meta/core/app_registry.py` | `ENABLED_APPS` / `APP_DB_ROUTING` / 已加载清单登记 |
| `tools/lib/path_resolvers.py` | 各 target 的路径解析策略 |

---

## 11. 交接状态

| 阶段 | 状态 | 时间 | 操作人 |
|------|------|------|--------|
| 代码完成（A + B） | ✅ | 2026-09-26 | 平台架构改造 |
| 单测 + 回归 | ✅ | 2026-09-26 | 平台架构改造 |
| **远端部署** | ⏳ **未执行** | - | 待 PM 确认 |
| staging `apps_root` 实测 | ⏳ 待办 | - | deploy agent |
| 首次 staging 验证 | ⏳ 待 PM 批准 | - | deploy agent |
| 持续优化（B2/B3/备份/死端点） | ⏳ 待排期 | - | deploy agent |
