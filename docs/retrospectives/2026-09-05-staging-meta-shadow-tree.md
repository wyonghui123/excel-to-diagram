# 复盘：staging `meta` 包影子树 —— "部署成功但代码从未被加载"

> 日期: 2026-09-05 | 状态: 已确认根因 + 已修复 + 门禁已落地
> 关联: 83eb505 (org_service 修复), 48ca72a (db_path), 449aa1c (dimension-scopes),
>       2026-09-03-staging-frontend-stale-dist.md, docs/spec_权限体系升级/16_*.md

---

## 1. 一句话结论

staging 后端的 `import meta` 实际解析到 **`/opt/app/staging/deploy/current/` 根目录本身**
（`deploy/meta` 符号链接 → `current`，且 `current/__init__.py` 就是 `meta/__init__.py` 的平铺拷贝），
因此 repo 的 `meta/<X>/<file>.py` 必须部署到 `current/<X>/<file>.py`；
而 `current/meta/**` 这个"看起来最像仓库结构"的嵌套目录是一个**从未被任何进程加载过的死镜像**。
2026-09-05 之前的多轮"部署"（含 9-03 一次全量、9-04 多个文件）写进了死镜像——
文件 md5 全对、py_compile 全过、dev-login 全 200，但运行中的后端一行新代码都没收到。

---

## 2. 事件与症状

- 用户报告: staging 组织详情「资源 × 功能权限」矩阵不显示 3 个权限集及其维度范围条件
  （财资管理子领域编辑 / 大财务架构数据查看 / YonBIP产品查看；数据已确认配置无误）。
- 根因 A（代码）: `OrgService` 权限预览聚合不读 `permission_set_dimension_scopes`（commit 83eb505 修复）。
- 根因 B（送达，本文主角）: 修复先后两次部署到 `current/meta/services/org_service.py`（死路径），
  重启后行为零变化；插桩调试日志 `/tmp/org_scope_dbg.log` 始终 0 字节。

---

## 3. 运行时机制（真相）

```
/opt/app/staging/bin/staging_services.sh
  └─ meta_backend: python /opt/app/staging/deploy/current/server.py
       server.py L16: sys.path.insert(0, dirname(dirname(abspath(__file__))))
                    = sys.path.insert(0, '/opt/app/staging/deploy')      ← 关键
       sys.path = ['/opt/app/staging/deploy', '/opt/app/staging/deploy/current', ...]

/opt/app/staging/deploy/meta  ->  symlink  ->  /opt/app/staging/deploy/current
/opt/app/staging/deploy/current/__init__.py   ← 内容 = repo meta/__init__.py（平铺拷贝）

⇒ import meta          → deploy/meta/__init__.py → realpath = current/
⇒ meta.services.org_service → current/services/org_service.py    ← 唯一活树
⇒ current/meta/**      → 永不解析（同名嵌套死镜像）
```

布局的来历: `deploy_staging.sh` L29 `cp -r $PROD_DIR/meta/* $NEW_DIR/` ——
staging 的版本目录 = **meta 包内容平铺**（`meta/*` → 版本根/*），而非仓库原样结构。
死镜像则来自后续某次"按仓库原样打包"的全量推送（9-03 09:33 整树 mtime 一致可证）。

---

## 4. 本事件时间线（2026-09-05）

| 时刻 | 动作 | 结果 |
|---|---|---|
| 08:37:59 | deploy_org_service_fix.py → `current/meta/services/`（错） | 备份 bak_083759、md5 匹配、py_compile 过、重启、dev-login 200（**假成功**） |
| 08:43:41 | 插桩版再部署到同一路径 + py_compile | `current/meta/services/__pycache__/org_service.cpython-39.pyc` mtime=08:43:41（**py_compile 产生，非进程 import——证据陷阱**） |
| 08:44+ | 触发 preview/config 接口后读日志 | `/tmp/org_scope_dbg.log` = 0 字节（**代码未被加载的第一强信号**，初期被误判为"触发探针问题"） |
| 09:0x | probe_server_py: 读出 L16 sys.path.insert | 会话摘要中算错层级为 `/opt/app/staging`（少一层 → `deploy`），探 `/opt/app/staging/meta/services/` 空手 |
| 09:1x | probe_find_real_meta: 发现 `deploy/meta -> current` symlink、双份 org_service.py、current 根有 `__init__.py` | 机制破案 |
| 08:51:34 | 干净修复版部署到 `current/services/`（对）+ 重启 PID 7476 | |
| 08:55+ | API: scope_matrix 出现 3 条 `__expression_display`；UI: 矩阵三行"查看（1 条）" | 验收通过 |
| 09:2x | 提交 83eb505 | |

---

## 5. 证据陷阱清单（为什么"每一步都像成功"）

1. **md5 校验自证**: 校验的是"写入的那个文件"，不是"进程解析到的文件"。
2. **py_compile 门禁**: 只证语法；且 `python -m py_compile` 会写 `__pycache__/*.pyc`，
   pyc mtime 让人误以为"进程已加载新文件"。
3. **dev-login 200**: 只证服务活着，与代码版本零相关。
4. **9-04 的"双写"**: R005 时代部分文件同时写了两棵树 → 死镜像里也有新文件，
   `ls/md5` 两处都"看起来部署过"。
5. **探针 sys.path 顺序敏感**: 复刻实验时先 `insert(current)` 后 `insert(deploy)`，
   顺序反了会 find_spec 到嵌套死路径，得出**与运行相反的结论**（本会话真实踩过一次）。
6. **会话压缩丢真知**: 前会话已总结"疑似真正加载的 meta 包位置与 deploy/current/meta 不同"，
   但路径算术错一层（staging vs deploy），后续探针在错误目录上空转。
7. **`/tmp/inspect.py` 遮蔽标准库**（9-01 遗留调试脚本）: 任何脚本放 /tmp 直接跑，
   `sys.path[0]=/tmp` → `import inspect` 拿到假模块 → `import meta` 全链炸出
   "inspect has no attribute 'signature'" 假故障（已隔离为 `inspect.py.quarantined_20260905`）。

---

## 6. 双树审计结果（2026-09-05 md5 实测）

| 树 | 定位 | 最后全量 | 代码基线 |
|---|---|---|---|
| live 活树 `current/<api,services,core>` | **唯一被加载** | 08-31 16:19:48 | commit **15654ec**（org_api.py md5 169cfed5 匹配）+ 7 个文件级热修 |
| nested 死镜像 `current/meta/**` | 从未被加载 | 09-03 09:33:33 | **main HEAD 快照**（org_api==48ca72a、db_path、bo_api 均与 HEAD 一致） |

live 树 8-31 之后真正到达的热修（mtime 证据）: permission_config_loader.py、
permission_dimension_engine.py（9-01）、manage_api.py（9-02）、org_service.py（9-05 本次）。
9-03 全量与 9-04 的 app_builder.py / permission_dimension_api.py /
permission_set_dimension_scope_api.py **全部落进死镜像**。

**由此产生的真实风险缺口**:
- 449aa1c 的 `permission_set_dimension_scope_api.py` POST 归一（canonical ID-form）**不在 live 树**
  → staging 仍可能写回 OBJ-form（GET 旧代码 + v083 数据清洗暂时掩盖了症状）。
- 48ca72a 的 `meta/core/db_path.py` 在 live 树**不存在**（ONLY_NESTED）
  → "DB 路径统一解析"修复未送达，目前全靠 server env `SQLITE_DB_PATH` 兜底。
- 其余 8-30 之后所有后端 commit（fc7c364、a04d2ee 等）中未被单独热修的部分同样未送达。

---

## 7. 历史同类事件盘点（"修复已做出，但运行面没收到"家族）

| 日期 | 症状 | 未送达环节 | 当时教训去向 |
|---|---|---|---|
| 2026-07-04 | dev 修好 prod 没修 | prod 部署链（还误改了 dev 代码） | 进 memory 硬约束 |
| 2026-09-03 早 | `no such table: org_members` | 相对路径 DB（cwd=bin）+ 热修未提交被全量覆盖 | memory 记录 |
| 2026-09-03 | staging 前端跑旧 dist | dist 产物送达 | 复盘 + "三条铁律" |
| 2026-08-29 | 主仓库后端进程跑旧代码 | 进程未重启/旧代码 | memory 记录 |
| 2026-09-05 | 后端行为零变化 | **meta 包解析路径（本文）** | 本复盘 |

家族共同点: 修复在**制作域**完成并自验证通过（本地 dev / 单测 / 本地浏览器），
但**运行域**（staging/prod 进程、dist、模块解析）未收到；且每次都只沉淀了
**文字约束**——文字约束拦不住下一次，工具门禁才能。

---

## 8. 根因（5 Whys）

1. 行为为何无变化？→ 进程加载的是旧代码。
2. 为何旧代码？→ 新文件写到 `current/meta/services/`（死路径）。
3. 为何写死路径？→ 部署脚本按**仓库结构镜像映射** `meta/services/ → current/meta/services/`，
   未验证 import 解析；嵌套死目录 + symlink 让"错误路径"看起来最合理。
4. 为何无人拦截？→ 布局真相是隐性知识（只散落在 memory 与个别脚本里）；
   部署自检全部对"写入文件"自证；约束在会话压缩后不可见。
5. 为何系统允许该状态长期存在？→ 8-31 之后 staging 缺少**全量对齐机制**与
   **送达验证门禁**，死镜像无人清理，双轨持续发散。

系统性放大因素: gateway 命令白名单限制排障手段（禁 rm/变量）诱发变通；
pyc/py_compile 污染证据链；跨会话压缩丢失关键算术（deploy 而非 staging）。

---

## 9. 已执行处置

1. 修复送达: org_service.py → `current/services/`（+ 规范目录同步），重启后 API/UI 双层验收通过（83eb505）。
2. `/tmp/inspect.py` → `inspect.py.quarantined_20260905`（消除标准库遮蔽假故障源）。
3. 新增门禁工具 **`tools/check_meta_import_origin.py`**（远端实测 PASS）:
   复刻 server.py sys.path，对目标输出 LIVE/DEAD 双路状态与内容分歧，落点错误即 EXIT 1。
   必须以 `python -I` 运行（防 /tmp 遮蔽）。
4. 修正 `.runtime/deploy_org_service_fix.py`、`.runtime/instrument_deploy_org_service.py`
   的 REMOTE 常量（死路径 → 活路径）。
5. project_memory: 重写 staging 路径硬约束（禁止部署 current/meta/**、禁止双写、
   部署前 origin 门禁、/tmp 遮蔽禁令）+ 双树审计结论。

## 10. 防再发（SOP，写进每次 meta/** 后端热修）

1. **部署前**: 上传并以 `python -I /tmp/check_meta_import_origin.py meta/<X>/<file>.py` 断言 LIVE 落点。
2. **部署映射**: repo `meta/<X>/<file>.py` → `current/<X>/<file>.py`（去掉 meta/ 前缀）。
   禁止写 `current/meta/**`；禁止"两份都写"。
3. **部署后送达验证**: 必须有"运行中进程可见的行为差异"（版本探针/接口新字段/调试日志——
   日志在正确文件里为空 = 未加载的第一信号）。md5/py_compile/dev-login 不构成送达证明。
4. **排障纪律**: 远端 python 脚本一律 `python -I`；复刻 sys.path 时严格按
   `[deploy, current]` 顺序；怀疑加载错路径时，直接查 `realpath(deploy/meta)`。

## 11. 待决事项（2026-09-05 下午已全部执行，见第 12 章）

- [x] **A. staging live 全量对齐 main HEAD**: 已完成 — NEW_VER `v20260905_101523_staging_align_head`
  平铺部署（1137 文件 md5 全验）+ 热修移植（3b85127）+ 原子切 symlink + 门禁 PASS。
- [x] **B. 死镜像清理**: NEW_VER 从 HEAD 平铺打包，`current/meta/**` 未带入新版本目录（死镜像随旧
  current 弃用，未再可加载）。
- [x] **C. 449aa1c POST 归一修复**: 已随 main HEAD 送达，行为级验证通过（dimension-scope 写后读全 ID-form）。
- [ ] D.（低优先级）评估 server.py sys.path 语义改造以消除平铺/嵌套双态——改造会**静默切换**
  全部 meta.* 到嵌套树，必须在 A 完成且两树一致后才可考虑。

## 13. 同日追加事故：锚点库被整体换为 spec15 旧库（登录 500 真根因）

### 12.1 事件链

1. Phase 2 切换完成（10:18），mx195 行为验证 **V1 真实登录 500** — 排查发现 meta_backend 实际
   使用的锚点库 `/opt/app/staging/meta/architecture.db` **缺失全部 spec16 表**。
2. 关键对比：9-04 备份 `backups/architecture.db.v083_normalize_20260904_201110` = spec16 完整库
   （76 表，v072-v082 已执行）；而当前活库与 **7-13 的**
   `deploy/v20260713_223437_staging/architecture.db` **同源**（audit_logs 行数 119069 一致、
   users 样本逐行一致、size 逐字节相同），schema_migrations 仅剩 10 条旧记录。
3. 时间窗：09:41 早间会话还能正常浏览（keep-alive 验证通过）→ 10:18 切换后即 500。
   **换库发生在 09:41~10:18，换库者未定罪。**
4. 嫌疑逐一排除：我方 mx181-mx210 全链脚本审计均只读；`staging_services.sh` 无任何 DB 拷贝逻辑；
   `server.py _preflight_db_check`（L186-223）的 `.bak` 覆盖**未触发**（backend.log 无
   PREFLIGHT FAILED 记录）。

### 12.2 恢复过程（每步断言失败即停）

- **Step A**: stop（unified_18081 + meta_backend，core_service 19200 不动=保执行通道）→
  spec15 旧库救援留档 `meta/architecture.db.spec15_rescued_20260905_105959` → cp v083 备份 →
  md5 一致（a44b3322）/ integrity ok / 76 表 / orgs=35 / permission_sets=40。
- **Step B**: 手动执行 v083（归一 3 行 OBJ-form→`[13]/[7]/[49]`）+ 补 schema_migrations 记录
  （现 19 条）+ v074 修复版同步 NEW_VER。
- **Step C**: start → 验证全 PASS（登录 200 / org 266 权限矩阵 3 权限集 API+浏览器双级 /
  dimension-scope 写后读 ID-form）。

### 12.3 铁律（新增）

1. **绝不对 staging 锚点库跑 `run_pending_migrations` 全扫**：NEW_VER migrations 目录 52 文件中
   锚点库只记录 10 条旧迁移，且 v083 备份系的迁移记录**无 .py 后缀**（runner 按文件名匹配不上），
   全扫会把 51 个文件当 pending 重放——v081 会 DROP legacy 表，v070 系在 9-02 战役中从未完整验证。
   只允许手动逐个执行 + 手动补记录。
2. **server.py `_preflight_db_check` 是潜伏回滚器**：启动时 integrity_check 失败会用
   `architecture.db.bak` 整个覆盖活库（L206 `shutil.copy2`）。meta 目录必须保持无
   `architecture.db.bak`，否则 DB 异常时被旧 .bak 静默回滚。本次未触发纯属幸运。
3. **验证 org 对象要用业务键核对**：本次 mx195 写死 ORG_ID=265（税务服务应用架构），而早间验证的
   3 权限集绑定在 org **266**（财资管理应用架构）。API 验证前先查库定位业务 org，勿凭记忆写 ID。

### 12.4 遗留风险

- **换库者未定罪**：若再出现"登录 500 + spec16 表消失"，按 12.1 链条排查；建议给锚点库加
  指纹巡检（表数 / 关键行数 / md5 定期记录）。
- prod 未同步：405218c（v074 修复）只在 repo，prod 部署计划另行安排。

---

## 14. 后续补注 (2026-09-13)

> [2026-09-13] AI Agent 补注: 本节由后续工作追加，反映 deploy_topology 通用化方案与本文关系。

### 14.1 本文 vs 后续 (2026-09-13) 的 staging 拓扑差异

| 维度 | 9-05 当时 | 9-13 现在 |
|---|---|---|
| 部署目录 | 平铺活树 `current/<X>/<file>.py` | **同**（NEW_VER 平铺） |
| meta/ 角色 | **死镜像** (9-03 一次全量推入后无人清理) | **namespace package 子集** (spec22 主动写 meta/X/Y) |
| meta/core/bo_framework.py | 不存在 (因 meta 是死目录) | **不存在** (因 meta 是 spec22 改的子集, bo_framework 等未修改文件只在顶层) |
| Python 加载 `from meta.api.X` | 走 namespace package 解析 (meta 是目录) | **同** |
| Python 加载成功? | OK (meta.api.X 找到的是顶层 X.py 的 symlink) | **部分 OK** (meta.api.bo_api OK, 但 meta.core.bo_framework 失败) |
| backend lazy import? | 不依赖 | **是** (通过 lazy route 注册规避 cold-start 失败) |

### 14.2 9-05 结论的修正

9-05 复盘说 "禁止双写 `current/meta/**`"，**该结论在 9-05 当时是正确的** (meta 是死目录)。

**但 9-13 之后不再适用**: 9-05~9-13 之间某次 staging 全量对齐（创建了 `v1789297457_staging_spec22`）时，把 meta/ 目录带进了 NEW_VER；后续 spec22 又主动在 meta/X/Y 上传补丁文件 — 现在 meta/ 不再是死镜像，而是 namespace package 子集。

**这种拓扑变化不可在工具层静态防御**，只能：
1. **抽象化**：用 deploy_topology 框架 ([retrospective 2026-09-13](./2026-09-13-deploy-topology-generalization.md)) 让"路径解析策略"可声明式配置
2. **运行时 introspect**：deploy_upload.py 的 `--introspect` 功能，远端实际跑 `import` 看加载路径
3. **md5 自证永远不够**：见 §5 第 1 条

### 14.3 9-05 仍正确的结论

1. **md5/py_compile/dev-login 不构成送达证明** — 仍正确
2. **必须有"运行中进程可见的行为差异"** — 仍正确
3. **复刻 sys.path 必须按 [deploy, current] 顺序** — 仍正确（但 9-13 NEW_VER v1789297457_staging_spec22 没有 [deploy, current] 这一层，直接 cwd 进入）
4. **打包必须平铺 (meta/* 内容)** — 仍正确（9-05 NEW_VER v20260905_101523_staging_align_head 和 9-13 NEW_VER v1789297457_staging_spec22 都是平铺）
5. **禁止 /tmp 污染** — 仍正确（`check_meta_import_origin.py` 9-05 创建，仍在 `/tmp/`）

### 14.4 关联文档

- [retrospective 2026-09-13-deploy-topology-generalization.md](./2026-09-13-deploy-topology-generalization.md) — deploy_topology 框架 (DeployTarget + PathResolver)
- [tools/deploy_upload.py](../../tools/deploy_upload.py) — 通用部署拓扑 CLI (resolve/upload/verify/healthcheck)
- [tools/lib/deploy_topology.py](../../tools/lib/deploy_topology.py) — 核心抽象
- [docs/staging-runbook.md §3.4](../staging-runbook.md#34-通用部署拓扑-deploy_uploadpy--2026-09-13-推荐) — 使用 SOP
