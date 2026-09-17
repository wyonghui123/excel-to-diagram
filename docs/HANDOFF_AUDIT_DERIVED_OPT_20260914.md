# HANDOFF: audit_derived_fields 批量化后续优化 + 视图差异事实

> **日期**: 2026-09-14 | **基准**: HEAD 625c1b (delta r012 已部署 staging + prod)
> **交接方**: delta r012 部署会话 | **接手方**: 开发智能体（优化实施）
> **关联**: docs/staging-runbook.md §2.10 (502 修复) / §2.11 / §2.12 (r012 记录)

---

## 0. 当前状态基线（勿重测，直接采信）

| 项 | staging | prod |
|---|---|---|
| `audit_derived_fields.py` md5 | fe10a012 (批量版已部署) | fe10a012 (一致) |
| `migration_runner.py` md5 | a3ea5c22 | a3ea5c22 |
| service_module (5000行) | 200 / 0.18s | 200 / 0.53s |
| relationship (500行) | 200 / 0.27s | 200 / 0.45s |
| audit_logs 行数 | 119,161 | 119,071 |

批量路径 (`_batch_enrich_updated_at`) 语义已验证与 `materialization_registry.get_updated_at` 一致（ISO-only，不用 epoch）。

---

## 1. 实测事实：为什么只有 prod 是 UNION ALL 复合视图

**远端 python sqlite3 实测（2026-09-14，勿再重测）：**

| | staging (`/opt/app/staging/meta/architecture.db`) | prod (`/opt/app/deployments/meta/architecture.db`) |
|---|---|---|
| `audit_logs` | 有 (119,161 行) | 有 (119,071 行) |
| `audit_logs_archive` | **无** | 有 (**0 行**) |
| `v_audit_all` 定义 | **单表 SELECT**（不含 UNION ALL、不引用归档表） | **UNION ALL** (audit_logs + audit_logs_archive) |

**机制解释（写代码前必读）：**

1. `meta/migrations/v007_50_add_audit_union_view.py` 是一个**打包迁移**：`_ensure_archive_table`（若缺则建归档表）→ 建归档索引 → DROP+CREATE `v_audit_all` 为 `audit_logs UNION ALL audit_logs_archive`。**完整执行后必然同时留下归档表 + 复合视图**。
2. prod 是长生命周期库，`audit_logs`（由 `meta/scripts/init_database.py` 建，**不在迁移链里**）在 v007_50 执行前就已存在 → 完整执行 → 归档表(空) + UNION ALL 视图。
3. staging 库中 v007_50 的完整产物（归档表）不存在，视图是单表形态 → **v007_50 的复合分支从未在 staging 落地**；staging 的单表视图来自历史修复工具（repo 内即有单表重建器 `test_helpers/_tmp_recreate_v_audit.py` 这类脚本）。
4. 性能后果（§2.10 已实测）：UNION ALL 复合视图上做聚合，SQLite 无法扁平化 → CO-ROUTINE 物化 + SCAN×2，`idx_audit_object` 等 17 个索引全部失效 → ~99ms/次聚合；单表视图可扁平化命中索引 → 0.05ms/次。
5. **讽刺点**：prod 归档表 0 行 = 承担了 UNION ALL 的全部性能代价，却还没有任何归档收益。

**注意**：v007_50 还有静默跳过分支（`audit_logs` 不存在 → `return True` 记成功）——与 v082 窄表事故（runbook §2.9）同款"前提缺失→静默成功"模式。

---

## 2. 任务清单（按优先级）

### 任务 1：enum_api 残留逐行热点接入 SSOT 批量

**位置**: `meta/api/enum_api.py` `_enrich_updated_at`（约 L94-133，`for r in records:` 循环体 L111 附近逐行调 `get_updated_at`）

**问题**: 与 prod 502 完全相同的 O(n)×视图扫描模式。enum 列表通常小 → 潜在热点，但 audit_derived 策略的枚举表在数据量大时会复现。

**契约差异（关键，勿丢语义）**:
- enum_api 现版本 **跳过已有 `updated_at` 的记录**（`if r.get('updated_at') is not None: continue`）
- SSOT `_batch_enrich_updated_at`（audit_derived_fields.py L319）**无条件覆盖**

**实现建议**（二选一，倾向 a）:
- a) 给 `enrich_audit_virtual_fields` / `_batch_enrich_updated_at` 加 `preserve_existing: bool = False` 参数，enum_api 传 True
- b) enum_api 侧预分区：把已有 updated_at 的 record 摘出，仅对缺失者调批量

**回归点**: enum 列表/详情接口（enum_api 中还有 3 处直接查 `v_audit_all` 的列表查询 L328/L568/L581——不在本任务范围，只需确认不因本任务回归）。

### 任务 2：删除 audit_derived_fields.py 死代码（~150 行，零外部引用）

**范围**（全仓库 grep 已确认仅模块内部互相引用，无任何外部调用方，含 tests）:

| 行号 | 内容 | 删除理由 |
|---|---|---|
| L33-39 | `_AUDIT_DERIVE_SELECT_SQL` | epoch 优先语义，与批量路径矛盾 |
| L41-48 | `_AUDIT_DERIVE_SELECT_SQL_FALLBACK` | 同上 |
| L50-58 | `_AUDIT_DERIVE_SELECT_SQL_NO_VIEW` | 同上 |
| L59-65 | `_AUDIT_DERIVE_SELECT_SQL_NO_VIEW_FALLBACK` | 同上 |
| L96-145 | `_execute_audit_query` | 仅被 `_get_audit_field_value` 调用 |
| L147-179 | `_normalize_rows` | 仅被上述调用；`datetime.fromtimestamp(epoch/1000)` 本地时区解释 = v007_45 已弃用的 8h 漂移源 |
| L181-195(约) | `_get_audit_field_value` | 仅被 `get_audit_derived_updated_at` 调用 |
| L411-429 | `get_audit_derived_updated_at` | 公开入口，零调用方 |

**删除理由**: 这条 epoch-优先链路是语义地雷——谁哪天调了它，单查与列表（ISO-only）值可差 8 小时。L67-73 注释块和 L74-88 批量 SQL、L93 `_SQL_PARAM_CHUNK` **保留**。

**注意**: `meta/core/association/fallback.py` 里有个同名 `_execute_audit_query`（L111 附近），是无关函数，**不要动**。

### 任务 3：小修（可与任务 2 同 commit）

1. `_batch_read_materialized`（L290）：分片异常时当前返回 `{}` 丢弃已取分片 → 改为该分片 `continue` 保留部分结果
2. `enrich_audit_virtual_fields` docstring（约 L367）"如果 record 已有 updated_at（来自物化列），直接使用" 与实际无条件覆盖不符 → 改为"物化值由批量重读提供（与列值一致）"，避免误导后来者

> **[2026-09-14 二次分析补充] 本节以下 4 项是接手方在动手前必读的踩坑预警, 来源于对代码 / 引用图 / 历史的静态核验。**

### 任务 R0 (实施前必做): staging v_audit_all 实测确认, 别只信 prod 形态

HOFF §1 第 3 点说"staging 单表 SELECT 不含 UNION ALL" — 这是 HOFF 撰写方**推断**的, 不是 staging 端实测结论 (HOFF §0 仅列了 prod 端实测)。接手方在动代码前必须用 staging 远端 python 实际跑:

```python
import sqlite3
con = sqlite3.connect('/opt/app/staging/meta/architecture.db')
cur = con.cursor()
cur.execute("SELECT sql FROM sqlite_master WHERE name='v_audit_all'")
print(cur.fetchone())
# 若输出含 UNION ALL → HOFF §1 推断错误, 走 §1 第 2 点的 prod 分支;
# 若单表 → HOFF 推断成立, §1 解释正确
```

**若 staging 也是 UNION ALL**: HOFF §1 第 3 点的"v007_50 复合分支从未在 staging 落地" + "单表视图来自历史修复工具" 推断**全部失效**, 502 根因解释要重写, 服务端 0.18s/0.27s 基线与 prod 0.53s/0.45s 差异是别的因素 (索引/数据倾斜) 而非视图形态。

### 任务 1 实施补充: enum_api 接入点不在 `_enrich_updated_at` 单文件

HOFF 任务 1 写 "位置: `meta/api/enum_api.py` `_enrich_updated_at` (约 L94-133)" — 准确, 但 HOFF **未提** enum_api 还有 3 处**直接查 v_audit_all 的列表查询** (L328/L568/L581)。这些不走 `_enrich_updated_at`, 所以任务 1 修不到。接手方实施时:

- 不要扩大任务 1 范围去碰那 3 处 (HOFF §1 第 1 行明确"不在本任务范围")
- 但**回归时必须**抽测那 3 处的端点 (HOFF §5 第 5 行只说"enum 列表接口抽测 200"太粗, 建议明确"list_enum_types / list_enum_values / 详情页"的端点路径)
- 那 3 处 v_audit_all 直查是**与本任务同款 N+1 风险**, 但当前没在 prod 502 复现 (说明枚举表行数小), 留作下次 backlog

### 任务 2 实施补充: 删除前先确认 `get_audit_derived_updated_at` 真的零调用

HOFF 任务 2 写"全仓库 grep 已确认仅模块内部互相引用, 无任何外部调用方, 含 tests" — 我做了一次交叉核验, **结论一致**:

- `query_service.py:620` + `persistence_interceptor.py:1517` + `test_v007_51_materialized_updated_at.py:225` + `test_enrich.py:20` **只引用 `enrich_audit_virtual_fields` (SSOT 主入口, 不删)**, 不引用被删的 5 个函数
- `meta/core/association/fallback.py:108` 的 `_execute_audit_query` 签名 `(data_source, where_clause, bind_params, order_by)` 与 `audit_derived_fields._execute_audit_query` 签名 `(ds, object_type, object_ids, use_fallback)` **完全不同**, 仅同名无关, 删 audit_derived 版本零影响 ✓
- `docs/V007_45_FIX_PLAN.md` L207 引用 `_execute_audit_query(..., use_fallback=True)` 作为"备选方案" — 是历史设计文档, 源码删了不影响, 但**建议同步在 V007_45_FIX_PLAN.md 加注"该函数已删除, 备选方案已废弃"** 避免后续误导

**额外发现一处盲点**: 任务 2 删除范围未列 `_AUDIT_DERIVE_SELECT_SQL_FALLBACK` (L44-50) — 该 SQL 仅在 `use_fallback=True` 时被引用, 而 `use_fallback` 默认 False, 实际**整条 fallback 链路 (L44-50 + L61-67) 同样是死代码**。建议任务 2 删除清单扩为:

| 行号 | 内容 | 删除理由 |
|---|---|---|
| L33-39 | `_AUDIT_DERIVE_SELECT_SQL` | HOFF 已列 |
| L41-48 | `_AUDIT_DERIVE_SELECT_SQL_FALLBACK` | **HOFF 漏列, use_fallback 链路全死** |
| L52-58 | `_AUDIT_DERIVE_SELECT_SQL_NO_VIEW` | HOFF 已列 |
| L60-66 | `_AUDIT_DERIVE_SELECT_SQL_NO_VIEW_FALLBACK` | **HOFF 漏列, 同上** |
| L96-145 | `_execute_audit_query` | HOFF 已列 |
| L147-179 | `_normalize_rows` | HOFF 已列 |
| L181-197 | `_get_audit_field_value` | HOFF 已列 |
| L411-429 | `get_audit_derived_updated_at` | HOFF 已列 |

删 4 个 SQL 常量 + 4 个函数 = 删除行数从 ~150 → ~165 行, 顺手清掉 use_fallback 参数。

### 任务 3 实施补充: `_batch_read_materialized` `return {}` 影响面

HOFF 任务 3 第 1 点准确 (L307 `return {}` 改为 `continue` 保留已成功分片)。但**未提**这是**唯一**一处 `return {}` 提早返回, 整个 `_batch_enrich_updated_at` 流程对 materialized 策略的 fallback 行为是:

1. chunk 1 成功, result_map 加了 N 个 id
2. chunk 2 抛异常 (例: 表被 DDL 变更), 当前直接 `return {}` → **chunk 1 的结果也丢了**, 整个函数返回空 dict
3. `_batch_enrich_updated_at` L355 走 `result_map.get(str(rid)) or record.get('created_at')` — 全 fallback 到 created_at

后果: 物化表的 1000 条记录, 中间表结构变更后,**前 500 条原本可以读到真实 updated_at 全部退化成 created_at** — 列表页面上 500 条 updated_at 等于 created_at, 用户看不出数据被改过。

改 `continue` 后: chunk 1 保留, chunk 2 跳过, chunk 3 继续尝试, 部分记录仍能拿到真值 — 这正是"分片异常容错"该有的语义。建议同步把 L307 的 `return {}` 改为 `continue`, 并在 L304 加日志 `%s chunk %d failed: %s` 便于诊断。

---

## 3. 明确不做 / 禁止事项

- **禁止改动两环境 `v_audit_all` / `audit_logs_archive` 的 schema**（视图重建属架构决策，见 §4-C，未拍板）
- 禁止跑 migration_runner 全量（§3.2 v071 教训）；本次改动无新迁移
- 禁止向 `current/meta/**` 部署（死镜像，复盘铁律）；staging 后端文件目标恒为 `current/<X>/<file>.py`
- 不加 prod 复合索引 `audit_logs(object_type, object_id, action)`——EXPLAIN 实测 UNION ALL 视图 CO-ROUTINE 物化下索引不生效，加了也白加

---

## 4. 背景知识：prod 视图性能问题的长期方向（未拍板，仅记录）

- **A. 维持现状**: 批量后 5000 行 ≈ 10 chunk × 99ms ≈ 1s，可接受（当前实测 0.53s）
- **B. prod 视图重建为单表**（归档从未启用，0 行）：与 staging 对齐立即提速，但未来启用归档时需改回
- **C. 批量 SQL 脱离视图直查基表**: `_AUDIT_DERIVE_BATCH_SQL` 改为 `SELECT ... FROM audit_logs WHERE ...` 与 `SELECT ... FROM audit_logs_archive WHERE ...` 两次查询 Python 侧合并——把谓词下推从"查询计划器能不能"变成"代码一定"，两种视图结构下性能一致。**若未来归档真正启用，这是必选项**

---

## 5. 验证与交付要求

1. **单测**: `pytest meta/tests/test_v007_51_materialized_updated_at.py meta/tests/test_v007_52_materialization_ssot.py` 全绿
2. **引用复核**: 删除后全仓库 grep `get_audit_derived_updated_at|_execute_audit_query|_normalize_rows|_AUDIT_DERIVE_SELECT_SQL` 确认无残留引用（fallback.py 的同名函数除外）
3. **import-origin 门禁**: meta/** 文件部署 staging 前 `python -I tools/check_meta_import_origin.py <targets>`（远端跑）
4. **staging delta 链路**: `python tools/staging_round.py preflight → pack → deploy → verify`（round 递增）；后端文件单独走 upload+gate+复刻 env 重启（runbook §2.11 有 env 真相表，**staging-backend.service 模板是雷，未修勿装**）
5. **端点验收**: service_module(5000)/relationship(500) 200 且不劣于 §0 基线；enum 列表接口抽测 200
6. **prod 通道**: `staging_round.use_prod_gateway()`（9200 HTTPS 自签）；`yonaa_exec.py` 纯 HTTP 已失效勿用；prod 验证用真实登录 `POST /api/v1/auth/login {admin/admin123}`（无 dev-login 路由）；服务绑定内网 IP，远端 curl 勿用 127.0.0.1
7. **交付物**: 代码 commit + runbook 补记（§2.10 后追加小节）+ 汇报声明送达环境清单（本地 dev ≠ staging ≠ prod）

---

## 6. 执行结果 (2026-09-14 r013, 本文档任务全部闭环)

| 任务 | 状态 | 结果 |
|---|---|---|
| 任务 1 enum_api SSOT 批量 | 完成 | 方案 a: `preserve_existing` 参数 (33ecd525/dbb757ab), enum 端点实测 200/19-28ms |
| 任务 2 死代码删除 | 完成 | 294 行 (原 ~460), 含二次分析补列的 *_FALLBACK 全链; grep 无残留 (fallback.py 同名无关) |
| 任务 3 小修 | 完成 | 分片 `continue` + docstring 修正 |
| R0 staging 视图实测 | 完成 | 单表形态确认 (HOFF §1 推断成立) |
| 单测 | 全绿 | v007_50/51/52 = 7+7+15 passed; real_archive_e2e 4 error 环境性 (硬编码 worktree 路径) |
| staging 部署 | 完成 | 单发活树 (introspect 裁决, 禁双发死镜像) + 门禁 PASS + env 复刻重启; 验收 147ms/385ms/28ms/26ms |
| prod 部署 | 完成 | 备份→上传 md5 OK→systemctl restart→真实登录; 验收 508ms/644ms/19ms/24ms, updated_at 0 缺失 |
| 附带 | 完成 | v007_52 两个用例 legacy 表名修复 (HEAD 既有问题); runbook §2.13 (含复刻重启停机 4min 事故复盘) |

**新发现待办** (移交后续): deploy_topology.yaml staging `python_module.double_path_prefixes` 会写死镜像 `current/meta/**`, 与门禁/HOFF §3 冲突, 修前勿用 `deploy_upload.py upload` 发 staging 后端文件 (详见 runbook §2.13)

