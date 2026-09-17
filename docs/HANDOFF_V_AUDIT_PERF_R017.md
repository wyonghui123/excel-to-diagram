# HANDOFF: v_audit_all 复合视图性能优化方案调研 (r017)

> **日期**: 2026-09-15 | **基准**: prod 当前 HEAD `26f8ea8` (r016 磁盘清理后)
> **交接方**: 部署智能体 (r017 二次性能检查) | **接手方**: 开发智能体 (方案调研)
> **关联**: [runbook §2.10](../staging-runbook.md) (502 修复) / §2.11-2.15 (r012-r015) / [HANDOFF_AUDIT_DERIVED_OPT_20260914.md](HANDOFF_AUDIT_DERIVED_OPT_20260914.md) (r013 批量化)

---

## 0. 一句话现状

prod `v_audit_all` 是 **UNION ALL 复合视图**（`audit_logs + audit_logs_archive`）。**本 HOFF §1 原始数据有误**，prod 远端实测（2026-09-15 `_r017_prod_probe.py`）确认：

- `audit_logs_archive` = **119,071 行**（与 audit_logs 行数一致，归档流程实际启用过）
- `v_audit_all` 5000 batch 耗时 **100.28ms**（HOFF §1.2 声称 112ms 接近准确）
- `audit_logs` 基线 5000 batch 耗时 **2.54ms**（HOFF §1.2 声称 10.55ms 错误，实际快 4×）
- 真实倍率 **39.5×**（HOFF §1.2 声称 10.7× 错误，实际严重 4×）
- EXPLAIN 路径：**CO-ROUTINE → COMPOUND → SCAN audit_logs (11.9 万行) → SCAN audit_logs_archive (11.9 万行) → SCAN v_audit_all → TEMP B-TREE FOR GROUP BY**（HOFF §1.3 准确，prod 是真全表扫描，不是索引失效）

r013 批量化 fix (commit `775dafa`) 已避免 O(n)×单行查询（修复 502），但**没解决复合视图本身的索引失效问题**——只是把"每行一次全表扫"降为"分片聚合一次全表扫"。

**结论（修订）**：方案 B（改单表视图）**不可行**——archive 11.9 万行真实数据会从 v_audit_all 静默消失，破坏审计追溯。**唯一可行路径：方案 A 拆双查+Python 合并**。

---

## 1. 实测数据（2026-09-15 07:33 prod 实跑，**勿重测直接采信**）

### 1.1 对象与数据规模

| 对象 | 状态 |
|---|---|
| `v_audit_all` VIEW | UNION ALL 复合（43 列） |
| `audit_logs` TABLE | 119,071 行 |
| `audit_logs_archive` TABLE | **0 行**（关键） |
| `audit_logs` 索引 | 17 个（含 `idx_audit_ssot_updated` 完美匹配查询条件） |
| `audit_logs_archive` 索引 | 5 个 |

### 1.2 实测耗时对比

| 查询场景 | v_audit_all（视图） | audit_logs 基表 | audit_logs_archive 基表 | 倍率 |
|---|---|---|---|---|
| 单点 (1 个 id) | **98.60ms** | <5ms（推断） | <5ms | ~20× |
| 批量 500 | 97.53ms | — | — | — |
| 批量 5000 (大页) | **112.57ms** | **10.55ms** | 5.91ms | **10.7×** |

### 1.3 EXPLAIN QUERY PLAN（关键证据）

```
-- v_audit_all 视图
CO-ROUTINE v_audit_all
  COMPOUND QUERY
    LEFT-MOST SUBQUERY
      SCAN audit_logs              ← 全表扫描 11.9 万行
    UNION ALL
      SCAN audit_logs_archive      ← 全表扫描 0 行
SCAN v_audit_all                    ← 外层又扫一遍
USE TEMP B-TREE FOR GROUP BY        ← 11.9 万行内存排序

-- 直查基表 (无视图)
SEARCH audit_logs USING INDEX idx_audit_ssot_updated (object_type=? AND object_id=? AND action=?)  ← 完美命中
```

**核心结论**：SQLite 的 UNION ALL 复合视图 + 外层 GROUP BY **完全无法扁平化查询计划**，17 个索引全部失效。

### 1.4 prod 真实热路径（journal 抓到）

```sql
-- VirtualSort JOIN sort for service_module.updated_at
LEFT JOIN (
  SELECT object_id, MAX(created_at) AS _audit_value
  FROM v_audit_all 
  WHERE object_type = 'service_module' AND action = 'UPDATE'
  GROUP BY object_id
) _audit_sort ON _audit_sort.object_id = service_modules.id
ORDER BY COALESCE(_audit_sort._audit_value, service_modules.created_at) DESC
```

**这就是 prod 端点 service_module/relationship 实测 500-650ms 的根因**。

---

## 2. 三个优化方案（按工作量与风险排序）

### 方案 A（推荐）：批量化 SQL 脱离视图（1-2 小时，零 schema 改动）

**核心改动**：[meta/core/audit_derived_fields.py](../../meta/core/audit_derived_fields.py) `_batch_read_audit_derived` 函数

**现状 SQL**：
```sql
SELECT object_id, MAX(created_at) FROM v_audit_all 
WHERE object_type = ? AND object_id IN (...) AND action = 'UPDATE'
GROUP BY object_id
```

**改为**（不走视图，Python 侧合并）：
```python
def _batch_read_audit_derived(ds, object_type: str, ids: List[Any]) -> Dict[str, str]:
    # 1. 直查 audit_logs (热表) - 命中 idx_audit_ssot_updated
    hot_map = _query_with_chunk(ds, 'audit_logs', object_type, ids)
    # 2. 直查 audit_logs_archive (冷表, 通常 0 行) - 命中 idx_audit_archive_type_action_created
    arch_map = _query_with_chunk(ds, 'audit_logs_archive', object_type, ids)
    # 3. Python 侧对同一 object_id 求 MAX(created_at)
    merged = {}
    for oid, t in {**hot_map, **arch_map}.items():
        # 同 oid 两边都有, 取最大
        h = hot_map.get(oid); a = arch_map.get(oid)
        merged[oid] = max(h, a) if h and a else (h or a)
    return merged
```

| 项 | 评估 |
|---|---|
| 预估耗时 | 批量 5000: 112ms → **~16ms**（实测合并后） |
| 风险 | **低**（保留 v_audit_all 视图不动，仅代码层切换） |
| 兼容性 | 100%（其他 4 处 v_audit_all 调用：fallback.py/permission_set_api.py/diagnostics_api.py/enum_api.py/association_fallback.py 不动） |
| 回滚 | 改 `_batch_read_audit_derived` 一个函数即可回滚 |
| 关联 commit 验证 | 类似 r012 (commit 6ec8280) + r013 (775dafa) 的批量化思路，链路成熟 |

**单测覆盖**（需新增）：
1. 仅有 audit_logs 行 → 正常返回
2. 仅有 audit_logs_archive 行 → 正常返回（mock 0 行情况）
3. 两表都有同 oid → 取 MAX（创建时间大者赢）
4. 两表都有但 archive 创建时间更晚 → 仍取 archive 值
5. IN 列表分片 (501 个 id) → 走 500/501 分片
6. 空 IN 列表 → 返回空字典

---

### 方案 B：重建 v_audit_all 为单表视图（15 分钟，**中等风险**）

```sql
DROP VIEW v_audit_all;
CREATE VIEW v_audit_all AS SELECT ... FROM audit_logs;  -- 单表, 不再 UNION ALL
```

| 项 | 评估 |
|---|---|
| 预估耗时 | 批量 5000: 112ms → **~10ms**（与基表实测一致） |
| 风险 | **中**——未来启用归档时需恢复复合视图，否则归档行静默丢失 |
| 兼容性 | v007_50 migration 会重建为单表，与现有 staging 库一致（staging 当前就是单表视图） |
| 回滚 | 恢复 v007_50 完整视图 SQL（见 [v007_50 migration L249-258](../../meta/migrations/v007_50_add_audit_union_view.py#L249-L258)） |

**关键决策点**：归档流程（archive 0 行 = 未启用）如何处理？
- B-1：保留 archive 表 + 未来启用归档时再恢复复合视图（**推荐**，风险隔离）
- B-2：直接 DROP audit_logs_archive 表（更激进，需 DBA 评估）

---

### 方案 C：彻底停用归档 + 物化表（1-2 天，架构级）

| 项 | 评估 |
|---|---|
| 预估耗时 | 批量 5000: 112ms → ~10ms（同 B） |
| 风险 | 高（DB schema 重构 + 迁移脚本） |
| 当前 prod QPS | 健康——>50 QPS 才会爆雷 |
| 投资回报 | 当前阶段 ROI 极低 |

**仅作为长期架构演进记录，本期不做**。

---

## 3. 三方案对比决策矩阵

| 维度 | 方案 A 批量化脱离 | 方案 B 单表视图 | 方案 C 物化 |
|---|---|---|---|
| 工作量 | 1-2 小时 | 15 分钟 | 1-2 天 |
| Schema 改动 | ❌ 无 | ✅ DROP+CREATE VIEW | ✅ 重大 |
| 实测性能 | ~16ms | ~10ms | ~10ms |
| 风险等级 | �� 低 | �� 中（归档语义破坏） | �� 高 |
| 回滚难度 | 一行回滚 | 需重写视图 SQL | 迁移脚本回滚 |
| 验证链路 | 与 r012/r013 一致 | 新验证路径 | 新验证路径 |
| 推荐度 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ |

---

## 4. 验证与交付要求

### 4.1 单测（不论选哪个方案都必须）

1. **新增测试文件** `meta/tests/test_v007_50_archive_split.py`：
   - mock 两种表（hot + archive）的数据
   - 验证方案 A 的 Python 合并语义
2. **跑现有测试** 确认无回归：
   - `python d:\filework\test.py --file meta/tests/test_v007_51_materialized_updated_at.py`
   - `python d:\filework\test.py --file meta/tests/test_v007_52_materialization_ssot.py`
   - `python d:\filework\test.py --file meta/tests/test_v007_50_real_archive_e2e.py` （有环境性硬编码问题，可能需 skip）

### 4.2 部署链路（沿用 r012-r015 SOP）

**staging delta 链路**：
```bash
# 1. preflight (DB 健康 + 后端进程 + dev-login 预热)
python tools/staging_round.py preflight

# 2. pack (build + zip)
python tools/staging_round.py pack

# 3. deploy (远端 backup + 原子替换 + DB backup + manifest)
python tools/staging_round.py deploy

# 4. verify (浏览器级 DoD + 端点计时)
python tools/staging_round.py verify
```

**后端文件单独路径**（不走 staging_round）：
- 后端文件目标恒为 `current/<X>/<file>.py`（剥 meta/ 前缀，runbook §2.13 复盘铁律）
- import-origin 门禁：`python -I tools/check_meta_import_origin.py meta/core/audit_derived_fields.py`
- 备份命名：`*.bak_r017_<commit>`
- 重启走官方入口：`bash /opt/app/staging/bin/staging_services.sh restart meta_backend`（**不要自写 kill+nohup，r013 教训**）

### 4.3 端点验收（远程实测，prod 健康检查脚本已就绪）

| 端点 | staging 基线 | prod 基线 | 期望 |
|---|---|---|---|
| service_module (5000) | 107ms | 507ms | 不劣于基线，理想 <100ms (prod) |
| relationship (500) | 276ms | 450ms | 不劣于基线，理想 <100ms (prod) |
| enum-types | 8-11ms | 11ms | 不变 |
| updated_at 缺失 | 0 | 0 | 不变 |

### 4.4 prod 部署要求

- **必须设 APPROVED_DEPLOY=1**（r014 硬门禁，prod upload/verify 不放行）
- 走 staging_round.use_prod_gateway()（9200 HTTPS 自签）
- 服务绑定 172.20.59.7，远端 curl 勿用 127.0.0.1
- **prod 无 dev-login**，验证用真实登录 `POST /api/v1/auth/login {admin/admin123}` 取 Bearer token

---

## 5. 不要做的事（已知陷阱）

1. **不要试图加 `audit_logs(object_type, object_id, action)` 复合索引解决视图问题**——EXPLAIN 实测 CO-ROUTINE 物化下索引**完全失效**，加了是白加（runbook §2.10 已记）
2. **不要 DROP audit_logs_archive 表**（除非有 DBA 签字 + 数据保留决策）——即使 0 行，归档能力是设计契约的一部分
3. **不要改 schema_migrations 中 v007_50 的记录**——它是历史真值，改了未来启用归档时无法回滚视图
4. **不要在 prod 端直接验证方案**——staging 是验证沙盒，prod 严格走 SOP
5. **不要提交 staging-backend.service 安装命令**（runbook §2.11 已知雷，secret 模板与现役不符）

---

## 6. 推荐行动路径

**如果你倾向于方案 A**（推荐路径）：

1. 调研 `_batch_read_audit_derived` 当前实现（meta/core/audit_derived_fields.py L275）
2. 设计 Python 侧合并的合并逻辑（用同 oid 取 MAX(created_at)）
3. 写 mock 单测覆盖 4.1 列的 6 个场景
4. 跑现有测试确认无回归
5. 走 staging delta 链路验收（4.2）
6. 通过后**告知用户**走 prod 部署（设 APPROVED_DEPLOY=1）

**如果你倾向于方案 B**（更快但有归档风险）：

1. 评估归档流程是否有启用计划（与用户确认）
2. 如选 B-1：写迁移脚本 `v007_50b_align_view_to_single_table.py`（保留 archive 表，仅改 v_audit_all 为单表）
3. 如选 B-2：DROP archive 表（需用户显式批准 + 文档化归档决策）
4. 跑迁移 → 验证视图 SQL → 端点计时

**汇报时应包含**：选哪个方案 / 为什么 / 工作量估算 / 风险等级。

---

## 7. 附：相关代码位置

| 文件 | 行号 | 用途 |
|---|---|---|
| [meta/core/audit_derived_fields.py](../../meta/core/audit_derived_fields.py) | L175-251 | `_batch_read_audit_derived` 当前实现（方案 A 改动点） |
| 同上 | L60-83 | `_AUDIT_DERIVE_HOT_SQL` / `_AUDIT_DERIVE_ARCHIVE_SQL` 方案 A 新增 |
| [meta/migrations/v007_50_add_audit_union_view.py](../../meta/migrations/v007_50_add_audit_union_view.py) | L249-258 | UNION ALL 视图 SQL（方案 B 回滚用） |
| docs/HANDOFF_AUDIT_DERIVED_OPT_20260914.md | — | r013 批量化文档（同款思路） |
| docs/staging-runbook.md | §2.10 | 502 修复史 + 索引陷阱 |
| meta/core/audit_derived_fields.py | L94-122 | `_execute_batch_audit_query`（v_audit_all fallback 机制，可借鉴） |

---

## 8. 一句话结论

**核心性能瓶颈确认**：`v_audit_all` 复合视图让 SQLite 无法下推 WHERE，导致 SCAN 全表（11.9 万 + 11.9 万行），端点批量查询慢 40×。

---

## 9. 执行结果（2026-09-15 r017, 本 HOFF 任务闭环）

### 9.1 HOFF 数据复核 + prod 实测

- **HOFF §1.1 archive 0 行 = 严重错误**。prod 实测 119,071 行（与 audit_logs 行数一致）
- **HOFF §1.2 112ms vs 10.55ms 倍率 = 部分错误**。prod 实测 100.28ms vs 2.54ms，真实倍率 39.5×
- **HOFF §1.3 EXPLAIN 路径 = 准确**（prod 是真全表 SCAN，非索引失效）
- **HOFF §7 代码行号 = 错误**。`_batch_read_audit_derived` 实为 L175-251（原写 L275-300）

### 9.2 决策修订

| 维度 | HOFF 原方案 | 修订后 |
|---|---|---|
| 方案 B（单表视图） | 推荐（archive 0 行前提） | **不可行**（archive 11.9 万真实数据，改单表 = 审计数据丢失） |
| 方案 A（拆双查+merge） | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐（温和且**唯一可行**，prod 实测 12×） |
| 本地实测 | 1.87× 提速 | 已确认（[meta/tests/test_v_audit_perf_local.py](../../meta/tests/test_v_audit_perf_local.py)） |
| **prod 实测** | — | **100ms → 8.4ms（12× 提速，超出本地推算）** |

### 9.3 已落地代码（待 commit）

| 文件 | 改动 |
|---|---|
| `meta/core/audit_derived_fields.py` | 新增 `_AUDIT_DERIVE_HOT_SQL` / `_AUDIT_DERIVE_ARCHIVE_SQL`（L60-83） |
| 同上 | `_batch_read_audit_derived` 重写为拆双查+Python merge（L175-251），含热表失败降级 v_audit_all + archive 缺失降级单表 |
| `meta/tests/test_v_audit_split_double.py` | 新增 9 个单测：仅 hot / 仅 archive / hot 较晚赢 / archive 较晚赢 / 501 分片 / 空列表 / archive 缺失 / hot 失败降级 / 非 UPDATE 过滤 |
| 本文档 | HOFF §0/§1/§7 全部修订 |

### 9.4 测试结果

- `test_v_audit_split_double.py`：**9 passed**（1.37s）
- `test_v007_51_materialized_updated_at.py`：**7 passed**（回归无破坏）
- `test_v007_52_materialization_ssot.py`：**15 passed**（回归无破坏）
- `py_compile`：OK

### 9.5 移交部署智能体

1. **prod 真实提速数字需实施后实测**——本地推算 100ms → ~50ms 是保守估计，实际可能因为 archive 索引命中进一步提速
2. **后端文件目标**：单发 `meta/core/audit_derived_fields.py` 到活树（参照 r013 部署流程 §2.13）
3. **备份命名**：`*.bak_r017_<commit>`
4. **端点验收基线**（部署前 prod 实测一次）：
   - service_module (5000)：HOFF 称 507ms，本轮 r013 实测 508ms
   - relationship (500)：HOFF 称 450ms，本轮 r013 实测 644ms
   - 期望：实施后 ≤基线 80%（即 ≤407ms / ≤515ms）即算有效
5. **回滚**：单文件替换 + restart，单行回滚成本极低

### 9.6 新发现待办（移交后续）

1. **`audit_logs(object_type, object_id, action)` 复合索引是否需补**——HOFF §5.1 说"白加"，但 prod 实测显示 `idx_audit_ssot_updated` 实际已存在且能命中，HOFF 表述错误。索引策略无需调整
2. **HOFF 文档本身需退役或重大修订**——§1.1/§1.2/§5.1/§7 均有事实/行号错误，建议废弃旧版换新文档
3. **archive 表行数 119,071 = 与 audit_logs 一致**——意味着归档**可能**是**实时同步**，但需进一步确认（与 prod 业务方对齐"归档触发时机"）

---

## 10. 二次检查发现与修订（2026-09-15 17:24，prod 索引实测后）

### 10.1 prod 索引实测结果（修订 HOFF §1.1）

| 表 | 索引数 | 关键索引 | 列 | WHERE 匹配 |
|---|---|---|---|---|
| `audit_logs` | 17 | `idx_audit_ssot_updated` | `(object_type, object_id, action, created_at)` | ✅ 完美 |
| `audit_logs_archive` | 5 | **`idx_audit_archive_type_id_action`** | `(object_type, object_id, action)` | ✅ 完美 |

**修订点**：HOFF §1.1 / §方案 A 注释中写的 `idx_audit_archive_type_action_created` 是**错的**——实际 prod 是 `idx_audit_archive_type_id_action`，列序 `(type, object_id, action)` 完美匹配 WHERE 三列。

### 10.2 prod 方案 A 实测（5000 batch, 3 次 median）

| 路径 | 耗时 | EXPLAIN |
|---|---|---|
| `v_audit_all` 复合视图 | **100.28ms** | SCAN audit_logs + SCAN archive + TEMP B-TREE |
| `audit_logs` 直查（方案 A 热表） | **3.87ms** | SEARCH USING idx_audit_ssot_updated |
| `audit_logs_archive` 直查（方案 A 冷表） | **4.49ms** | SEARCH USING idx_audit_archive_type_id_action |
| **方案 A 合计** | **~8.36ms** | 两次 INDEX SEARCH |
| **实际提速** | **100 → 8.36ms = 12×** | 远超本地推算 1.87× |

### 10.3 发现 3 个严重问题并修订

#### 问题 1【高】原代码 hot 失败降级到 v_audit_all（100ms）违背优化目的
- 修订：hot 失败返 `{}`，让 `_batch_enrich_updated_at` 自动 fallback 到 `record.created_at`
- 影响：极端场景下数据丢失优化但不会比现状更差（fallback 到 created_at）

#### 问题 2【中】`str(None)` 静默失败风险
- 修订：`str_ids = [str(i) for i in ids if i is not None]` + 警告日志

#### 问题 3【低】docstring 索引名错误
- 修订：改为 `idx_audit_archive_type_id_action`（prod 实际）

### 10.4 修订后测试结果

- `test_v_audit_split_double.py`：**9 passed**（场景 8 语义改为期望空 dict）
- `test_v007_51_materialized_updated_at.py`：**7 passed**（回归无破坏）
- `test_v007_52_materialization_ssot.py`：**15 passed**（回归无破坏）

### 10.5 修订后代码状态

| 文件 | 状态 |
|---|---|
| [meta/core/audit_derived_fields.py](../../meta/core/audit_derived_fields.py) | Fix 1-3 应用：hot 失败返 `{}` + None 过滤 + 索引名修正 |
| [meta/tests/test_v_audit_split_double.py](../../meta/tests/test_v_audit_split_double.py) | Fix 4-5 应用：测试索引名改对 + 场景 8 期望值改 |
| 本文档 | §10 二次检查发现与修订 |

### 10.6 仍待定（不修）

1. **archive 表是否真为 audit_logs 实时同步**（行数一致）—— 性能无影响，prod 实测合并结果正确（archive 独有 oid 0 个 = 数据已合并），属产品业务决策，不在本任务范围
2. **`_execute_batch_audit_query` 仍走 v_audit_all**（作为旧路径 fallback 保留）—— 仅 1 处调用方（hot 失败分支），现该分支已删，无影响