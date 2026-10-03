# 规则模型（属性确定）实施计划 — Phase / 任务列表 / 里程碑

> **版本**：v1.6 | **日期**：2026-10-03 | **状态**：已实施（M0~M7 已完成；T-26 YAML 声明化后置）
> **关联文档**：
> - [2026-10-02-rule-model-spec.md](./2026-10-02-rule-model-spec.md)（Spec + RFC v1.3，已确认）
> - [2026-10-02-rule-model-research.md](./2026-10-02-rule-model-research.md)（对标研究报告 v1.11）

---

## 1. 已落定决策

| 编号 | 决策 | 结论 |
|---|---|---|
| Q1 | 读取入口 | **零新表 + 新增 `RuleProvider` 读取入口**；9 处调用点收口 |
| TBD-1 | 载体选型 | **方案 A：新增 `RuleType.DEFAULT`**（爆炸半径已核查，见 §2.2） |
| Q4 | 拆分 / 分摊 | **放二期**；一期在 Spec 中显式划界（FR-012） |
| Q8 | 可解释性 | **一期只做日志**（结构按可回放设计）；dry-run 二期复用同结构 |

---

## 2. 技术方案细化

### 2.1 载体重定义（方案 A 落地）

```
MetaRule (基类, models.py L141-170)
  └── MetaDefaultRule(MetaRule)          # 新增
        rule_type      = RuleType.DEFAULT
        triggers       = [BEFORE_SAVE]   # 默认
        overwrite      = FILL_IF_EMPTY | OVERRIDE
        apply_on       = USER_INPUT | SYSTEM | BOTH
        on_recompute   = RECOMPUTE_KEEP | RECOMPUTE_CLEAR
        source_type    = constant | field | cross_object | expression
        source_ref     = 取值引用（常量字面量 / 字段 id / 对象.字段 / 表达式）
        priority       = int（越小越先）
```

### 2.2 `RuleType.DEFAULT` 落地清单（爆炸半径：5 个 Python 点，前端 0）

| # | 文件 | 位置 | 改动 |
|---|---|---|---|
| 1 | `meta/core/models_enums.py` | L94-101 `RuleType` | 新增 `DEFAULT = "default"` |
| 2 | `meta/core/yaml_loader.py` | L219 字符串映射 | 新增 `"default": RuleType.DEFAULT` |
| 3 | `meta/core/rule_executor.py` | L446 `resolve_*` 分发 | 识别 DEFAULT 类型 |
| 4 | `meta/core/rule_executor.py` | L1097 `_execute_rule` | 新增 DEFAULT 分支 → `DefaultExecutor` |
| 5 | `meta/core/rule_chain.py` | L287 `_create_node` | 新增 DEFAULT 节点（依赖图） |
| 6 | `meta/core/async_interceptor_engine.py` | L41 异步规则名单 | 评估是否纳入（建议：一期不纳入） |
| — | `src/**` | — | **零改动**（前端无 meta rule_type 枚举消费） |

> 附带：`MetaObject.get_derivations()` 等访问器（models.py L1023-1060）需新增 `get_defaults()`，由 `RuleProvider` 委托。

### 2.3 `RuleProvider` 收口清单（9 处生产代码）

| # | 文件 | 行 | 现状用途 |
|---|---|---|---|
| 1 | `meta/api/bo_api.py` | 472 | 遍历取校验类规则 |
| 2 | `meta/api/bo_api.py` | 2059 | 规则列表 |
| 3 | `meta/api/bo_api.py` | 2116 | 规则列表 |
| 4 | `meta/api/manage_api.py` | 1266 | 规则列表 |
| 5 | `meta/services/computation_service.py` | 106 | 扫 `MetaComputation` |
| 6 | `meta/core/cross_object_chain.py` | 81 | 跨对象链取规则 |
| 7 | `meta/core/metadata_validator.py` | 340 | 扫 `MetaDerivation` |
| 8 | `meta/core/rule_chain.py` | 230 | `RuleDependencyAnalyzer` |
| 9 | `meta/core/interceptors/action_permission_interceptor.py` | 74 | 扫 `state_transition` |
| — | `meta/core/models.py` | 1023-1060 | 对象内访问器：**保留为底层**，Provider 委托 |

> 测试代码（`meta/tests/**` 中 30+ 处直接访问 `meta_obj.rules`）**不改**：测试直接访问数据、不经 Provider，属合理用法。

### 2.4 执行次序与覆盖（关键实现点）

```
action_executor.create/update
  └── rule_engine.compute(...)                  # 现有：全局排序 + 全部执行（COMPUTATION）
  └── rule_engine.default_by_priority(...)      # 新增：按 target_field 分组 + 首个命中
        1. 分组：按 target_fields 拆成 N 个组（同组竞争同一字段）
        2. 组内排序：priority asc, rule.id asc
        3. 逐条判定 condition；命中即写值并停止该组
        4. 覆盖判定：FILL_IF_EMPTY 且目标非空 → 跳过（记日志）
        5. apply_on 过滤：USER_INPUT / SYSTEM / BOTH
        6. 写值后登记 ctx.auto_filled[field] = rule_id
  └── execute_rules(BEFORE_SAVE)                # 现有校验链
  └── MetaField.default                          # 静态兜底（最后）
```

### 2.5 日志结构（`DefaultLogEntry`，一期可回放）

| 字段 | 说明 |
|---|---|
| `rule_id` | 规则标识 |
| `seq` | 排序后序号（全局） |
| `target_field` | 目标字段 |
| `hit` | 是否命中（bool） |
| `miss_reason` | `CONDITION_FALSE` / `SHADOWED_BY`（被更小 seq 同组规则抢先）/ `TARGET_NOT_EMPTY` / `APPLY_ON_SKIP` |
| `value` | 带出的值（未命中为 null） |
| `source_type` / `source_ref` | 取值来源 |
| `factor_snapshot` | 仅 condition 引用的字段快照（控制体积） |
| `elapsed_ms` | 单条耗时 |

> 与二期 dry-run **共用同一份结构**：dry-run = 不落库地跑同一条链路并返回 `logs`。

---

## 3. Phase 规划

| Phase | 名称 | 目标 | 对应任务 | 里程碑 |
|---|---|---|---|---|
| **P1** | 入口收口 | 统一读取入口，行为零变化 | T-01 … T-04 | M1 |
| **P2** | 属性确定语义 | 让 DEFAULT 可用（五要素齐备） | T-05 … T-11 | M2 |
| **P3** | 可解释性 | 日志可回答「为何是这个值」 | T-12 … T-14 | M3 |
| **P4** | 文档收口 | 研究报告口径修正 + 回填结果 | T-15 … T-16 | M4 |
| **P5** | 二期·dry-run 预演 | 不落库返回「哪条规则带出什么值」判定链（对齐"先只做日志"） | T-17 … T-18 | M5 |
| **P6** | 二期·汇总补强 | 按父外键分组的取值聚合（SUM/AVG/MAX/MIN by FK） | T-19 … T-20 | M6 |
| **P7** | 二期·拆分/分摊 | 1→N 守恒（Σ子行 = 父行）：分摊写已有行 / 拆分建新行 | T-21 … T-25 | M7 |
| — | 二期其余（预留） | 集合确定、定价、在线配置、规则版本化 | — | — |

---

## 4. 任务列表

### P1 入口收口（零行为变更）

| ID | 任务 | 触及文件 | 产出 | 依赖 | 验收 |
|---|---|---|---|---|---|
| T-01 | 锁定读取点清单并加回归基线 | §2.3 全部 9 处 | 基线测试跑通记录 | — | 存量测试全绿（改前基线） |
| T-02 | 新增 `RuleProvider`（直读 + 委托 `MetaObject` 访问器） | `meta/core/rule_provider.py`（新） | Provider 实现 + 单测 | T-01 | 单测：`get_rules` 保序不过滤 / `get_enabled_rules` 过滤且保序 / `get_rules_by_type` 保序 |
| T-03 | 9 处调用点改走 Provider（透传，分 2 个 commit） | §2.3 清单 | 调用点替换 | T-02 | 替换前后返回集完全一致（对比断言） |
| T-04 | P1 回归 | — | 回归报告 | T-03 | 存量测试全绿（改后与基线一致） |

### P2 属性确定语义

| ID | 任务 | 触及文件 | 产出 | 依赖 | 验收 |
|---|---|---|---|---|---|
| T-05 | 新增 `RuleType.DEFAULT` + yaml 映射 | `models_enums.py`、`yaml_loader.py` | 枚举 + 映射 | T-04 | YAML 中 `rule_type: default` 可加载 |
| T-06 | 新增 `MetaDefaultRule` dataclass + `get_defaults()` | `models.py` | 模型类 + 访问器 | T-05 | 字段默认值正确；`triggers` 默认 `BEFORE_SAVE` |
| T-07 | `DefaultExecutor` + 分发接入 | `rule_executor.py`（L446/L1097） | 执行器 | T-06 | 按类型正确分发 |
| T-08 | `RuleEngine.default_by_priority`（分组 + 首个命中 + tie-break） | `rule_executor.py` | 核心算法 | T-07 | 单测：多规则竞争同字段仅首条生效 |
| T-09 | 覆盖语义 / apply_on / 再判定 | `rule_executor.py`、`RuleContext` | 覆盖与重判 | T-08 | 单测：4 类组合（FILL_IF_EMPTY/OVERRIDE × KEEP/CLEAR） |
| T-10 | 依赖图与异步名单兼容 | `rule_chain.py`、`async_interceptor_engine.py` | 兼容分支 | T-08 | 依赖分析不因新类型报错 |
| T-11 | `action_executor` 集成 | `action_executor.py`（`_do_create` 约 L1575、`_do_update` 约 L1922；helper 约 L509-538） | 保存链路接入 | T-09 | 集成测试：保存后落库值正确 |

### P3 可解释性

| ID | 任务 | 触及文件 | 产出 | 依赖 | 验收 |
|---|---|---|---|---|---|
| T-12 | `DefaultLogEntry` 定义 + 装配 | `rule_executor.py` | 日志结构 | T-11 | 字段齐全（§2.5 表） |
| T-13 | 日志出口（**口径调整**：不经 `RuleExecutionReport.logs`，改为 `apply_defaults` 返回 + `_log_default_rules` 输出） | `rule_executor.py`、`action_executor.py` | 日志出口 | T-12 | 一次保存可打印完整判定链 |
| T-14 | 日志单测（含未命中原因分类） | `meta/tests/` | 单测 | T-13 | `not_first_match` / `target_not_empty` / `condition_false` 均可复现 |

### P4 文档收口

| ID | 任务 | 触及文件 | 产出 | 依赖 | 验收 |
|---|---|---|---|---|---|
| T-15 | 研究报告 4 处口径修正（含 §10.2 / §10.6#10 / §10.7#3 / §11 结论 8 派生同步点） | `2026-10-02-rule-model-research.md` | v1.10 | T-11 | §1 / §8.2 落点 / §8.10 汇总 / §8.3 `priority` 四处改正 |
| T-16 | Spec / Plan 回填实施结果 + CHANGELOG | 本文件、Spec | 结项 | T-15 | 与实际代码一致 |

**研究报告待修正 4 处明细**：

1. §1 / §8.2：「第三类属性确定**缺失**」→ 「规则容器已有（`MetaRule` + `RuleEngine` + `meta_obj.rules`），缺 `default` 语义」
2. §8.2 落点：`persistence_interceptor` → **`RuleEngine` + `action_executor` 的 BEFORE_SAVE**
3. §8.10 ②：「反向汇总 = ❌ 缺口 / 最低成本补齐项」→ **部分具备**（计数类 `count_children` / `count_relations` + 表级 `SUM·AVG·MAX·MIN` **已有**；仍缺**按父分组的取值聚合 + 子行增删改重算**）
4. §8.3：补「`priority` 现为全局全执行，DEFAULT 需专用『分组 + 首个命中』分支」

### P5 二期·dry-run 预演（不落库）

| ID | 任务 | 触及文件 | 产出 | 依赖 | 验收 |
|---|---|---|---|---|---|
| T-17 | `ActionExecutor.dry_run_defaults`（浅拷贝求值 + 返回判定链，零写库） | `action_executor.py` | dry-run 入口 | T-13 | 集成测试：dry-run 带出值 == 真实保存落库值；业务表/审计表计数均为 0 |
| T-18 | 试算 API `POST /api/v1/meta/<object_type>/defaults-preview` | `meta_api.py` | 只读预演端点 | T-17 | 路由已注册；`change_source` 由登录用户判定 |

> **T-17 设计口径**：dry-run **复用同一条 `apply_defaults`**（同排序 / 同首个命中 / 同覆盖语义 / 同 `change_source`），差别仅在「在浅拷贝上跑、不落库、不写审计」。v1 边界 = **只覆盖 DEFAULT 规则段**（不含必填校验 / 计算 / 冗余守卫，后者在真实链路更外层），对齐用户「先只做日志」。
>
> **与在线配置的关系**：该端点是后续「在线配置规则」的**试算底座** —— 配置了规则要能马上看到「这单会被带出什么」，闭环才成立。前端 UI 仍是后置项。

### P6 二期·汇总补强（按父分组的取值聚合）

| ID | 任务 | 触及文件 | 产出 | 依赖 | 验收 |
|---|---|---|---|---|---|
| T-19 | `_aggregate_field_by_parent` + `_batch_aggregate_field_by_parent`（单条 + `GROUP BY` 批量） | `computation_service.py` | 按父分组取值聚合 | T-13 | 单测：SUM/AVG/MAX/MIN by FK；无子行返 `None`；批量 == 逐条 |
| T-20 | 声明口径与 `count_children` 对称 + 向下兼容 | `computation_service.py`、`meta/tests/` | 分支 + 回归 | T-19 | 未声明 `target_object` 时保持整表聚合（存量 30 passed） |

> **T-19 声明口径**：与 `count_children` 对称 —— `computation.type` 复用 `sum_field`/`avg_field`/`max_field`/`min_field`，另给 `target_object`（或 `child_object`）+ `foreign_key`（缺省从层级/关联配置推导）+ `source_field`。**不带 `target_object` 即回落整表/条件聚合**（存量语义不变）。SQL：单条 `WHERE fk = ?`；批量 `WHERE fk IN (...) GROUP BY fk`（1 SQL 替代 N+1，与 `_batch_count_children` 同构）。
>
> **sort/filter 下推**：启用此能力**不新增 `comp_type`**，故 `computed_subqueries.is_supported` 行为不变 —— 仍只下推 `count_relations`/`count_children`；取值聚合沿用既有「非下推 → 内存排序」回退，无新增静默失败风险。

### P7 二期·拆分/分摊（1→N 守恒）

| ID | 任务 | 触及文件 | 产出 | 依赖 | 验收 |
|---|---|---|---|---|---|
| T-21 | 纯守恒算法 `plan(total, weights, scale)`（最大余数法） | `meta/services/allocation_service.py`（新） | 分配算法 + 单测 | — | 单测：Σ 精确守恒（含负总额 / 小数权重 / 各种 scale） |
| T-22 | 子行定位 + 外键推导 `_resolve_children` | `allocation_service.py` | 子行定位 + `resolve_foreign_key` | T-21 | 单测：显式 fk / 缺省从层级推导 / 数量不匹配 422 |
| T-23 | `allocate()` 分摊到已有 N 行（事务 + 回读守恒断言） | `allocation_service.py` | 分摊主体 | T-22 | 集成：三等份守恒落库；按 id 对齐权重；写失败整体回滚 |
| T-24 | `split()` 拆分生成 N 新行（复用同一引擎） | `allocation_service.py` | 拆分主体 | T-23 | 集成：新建 N 行守恒；`template` 附加字段；回滚 |
| T-25 | 接线 BO Action（`allocation.apply` / `allocation.split`） | `meta/services/allocation_apply.py`（新）、`bo_action_registrations.py` | 2 个 Action + 契约同步 | T-24 | `test_bo_action_contract.py` 36 passed（数量断言 19→21） |
| T-26 | **（后置）** `RuleType.ALLOCATION` + YAML 声明化 | `models_enums.py`、`yaml_loader.py`、加载链路 | 声明式分摊规则 | T-25 | 见下方「为何后置」 |

> **T-21 算法口径**：**最大余数法**（largest remainder）—— 以最小整数单位（分）计算基数，余数按 `(余数降序, 序号升序)` 确定性补给前 `diff` 行，保证 `Σ 分配值 == 总额` **精确成立**（无浮点误差）。权重先按 `w_scale` 整数化（`Decimal` 的 `//` 是**向零截断**而非下取整，负总额下会破坏 `[0, n)` 性质），全程用 Python `int` 运算。
>
> **T-23/T-24 原子性口径**：写操作包在 `self.ds.transaction()` 内；`ActionExecutor._do_*` 的内层事务因 `datasource.transaction()` 的**嵌套守卫**（`if self.in_transaction: yield; return`）加入外层 —— 任一行写失败即 `raise AllocationError`，整体回滚（实测注入第 2 行失败后业务表零残留）。写入后**回读求和**并与父行总额比对，不一致则 422。
>
> **T-26 为何后置（用户明确后置）**：`RULE_TYPE_MAP` 对未知 `rule_type` **静默回退为 `VALIDATION`**（`yaml_loader.py` L213-231），新增 `RuleType.ALLOCATION` 若漏注册映射，分摊规则会被当成校验**静默执行**，爆炸半径大。故本轮以「独立服务 + BO Action」交付（与 `batch_delete` 同模式），YAML 声明化留待后续并须同步加载链路。

---

## 5. 里程碑

| 里程碑 | 名称 | 内容 | 验收标准（可验证） | 状态 |
|---|---|---|---|---|
| **M0** | 计划确认 | Spec + Plan 评审通过 | 用户确认本文件 | ✅ 已完成 |
| **M1** | 读取入口统一 | T-01 … T-04 | 9 处调用点经 `RuleProvider`；替换前后返回集一致；存量测试全绿 | ✅ 已完成（T-01 基线缺口见 §9） |
| **M2** | 属性确定可用 | T-05 … T-11 | 五要素单测通过；经 `action_executor` 保存对象后落库值符合预期 | ✅ 已完成（`test_default_rule_unit.py` 35 passed） |
| **M3** | 可解释可排查 | T-12 … T-14 | 单次保存日志可回答「哪条规则 / 为何命中 / 值从哪来 / 为何未命中」 | ✅ 已完成（T-13 出口口径调整见 §9） |
| **M4** | 文档收口 | T-15 … T-16 | 研究报告四处口径修正；Spec/Plan 与实际代码一致 | ✅ 已完成（研究 v1.10 / Spec v1.1） |
| **M5** | 二期·dry-run 预演 | T-17 … T-18 | 预演带出值 == 真实保存落库值；业务表与审计表零写入；试算端点可用 | ✅ 已完成（`test_default_rule_integration.py` 8 passed） |
| **M6** | 二期·汇总补强 | T-19 … T-20 | 按父分组 SUM/AVG/MAX/MIN 正确；批量 == 逐条；无子行返 `None`；存量整表聚合不变 | ✅ 已完成（`test_computation_aggregation.py` 30 passed） |
| **M7** | 二期·拆分/分摊 | T-21 … T-25 | 1→N 守恒精确（Σ子行 = 父行）；按 id 对齐权重；写失败整体回滚；2 个 BO Action 可用 | ✅ 已完成（`test_allocation_plan.py` 27 / `test_allocation_allocate.py` 11 / `test_bo_action_contract.py` 36 passed） |

> 二期其余（不在本轮）：集合确定、定价、在线配置 UI、规则版本化 + 生效期。拆分·分摊已于 M7 落地（见 §4 P7）；其中 YAML 声明化（T-26）后置。

---

## 6. 风险与应对

| ID | 风险 | 影响 | 应对 |
|---|---|---|---|
| R1 | `RuleType` 枚举扩散 | 中 | **已核查**：仅 5 个 Python 点，前端零改动（§2.2） |
| R2 | 复用 `_compute_by_priority` 会导致「全部执行」语义错误 | 高 | 强制新增 `default_by_priority`；在代码注释与测试中固化差异 |
| R3 | 9 处调用点替换引入行为漂移 | 高 | T-03 分 2 个 commit + 前后返回集对比断言；T-01 先建基线 |
| R4 | 存量测试大量直接访问 `meta_obj.rules` | 低 | 测试不改（不经 Provider 属合理用法） |
| R5 | 跨对象取数导致保存变慢 | 中 | 仅 condition 命中路径取数；批量/缓存；NFR-001 门限 |
| R6 | 日志体积 | 低 | `factor_snapshot` 仅含 condition 引用字段；一期仅 logging 不落库（TBD-2/6） |
| R7 | 因子变化时误清用户手工值 | 中 | `auto_filled` 来源标记；仅清自动值；`RECOMPUTE_KEEP` 为默认 |

---

## 7. 不做清单（一期边界）

- 拆分 / 分摊（1→N 守恒，**已于二期 M7 落地**，见 §4 P7；其中 YAML 声明化 T-26 后置）；反向汇总取值聚合（N→1，计数类 + **按父分组 SUM/AVG/MAX/MIN** 已于 M6 落地，见 §4 P6）
- dry-run 预演（**一期边界**；二期 v1 已于 M5 落地，见 §4 P5）
- 在线配置 UI / 规则热加载（dry-run 试算端点已就绪，UI 后置）
- 规则版本化 + 生效期（不承诺按当时规则复现历史单据）
- 前端联动（`ON_CHANGE`）——除非 TBD-5 确认纳入

---

## 8. 验证方式（按项目铁律）

- 单元/集成测试：`python d:\filework\test.py`（**禁止直接 pytest**）
- 涉及服务时：`scripts/service_manager.ps1`（**禁止直接 `npm run dev` / `python dev.py`**）
- 严格模式（可选）：reload 元数据 `POST /api/v1/meta/reload` 后复验
- 首次执行 T-01 时用 `--help` 确认 meta 单测选择器（记为 TBD-P1）

---

## 9. 实施进展记录

### M1（P1 入口收口）— 已完成

| 任务 | 状态 | 产出 / 证据 |
|---|---|---|
| T-01 锁定读取点 + 基线 | 部分 | 读取点已锁定并扩展为 **9 处**（原估 6 处）；**改动前基线未采集**（见下方诚实说明） |
| T-02 `RuleProvider` + 单测 | 完成 | `meta/core/rule_provider.py`；`meta/tests/test_rule_provider_unit.py` **9 passed** |
| T-03 9 处调用点替换 | 完成 | 9 处全部改为 `get_rule_provider().get_rules(...)`；7 个文件各加 1 行 import |
| T-04 P1 回归 | 完成 | 见下表；合计 **113 passed / 32 skipped / 0 failed** |

**T-03 替换清单（9 处）**：`bo_api.py`(×3：L472/L2059/L2116)、`manage_api.py`、`computation_service.py`、`cross_object_chain.py`、`metadata_validator.py`、`rule_chain.py`、`action_permission_interceptor.py`。`meta/core/models.py` 的 `MetaObject` 访问器保留为底层（Provider 委托）；`meta/tests/**` 中 30+ 处直接访问不改（测试直访数据属合理用法）。

**T-04 回归结果（实测）**

| 测试文件 | 结果 |
|---|---|
| `test_rule_provider_unit.py` | 9 passed |
| `test_rule_engine.py` | 9 passed |
| `test_derivation.py` | 6 passed |
| `test_state_adoption_verification.py` | 22 passed + 1 skipped |
| `test_phase3_final_verification.py` | 27 passed |
| `test_version_visibility_unit.py` | 15 passed |
| `test_spec22_state_transition_action_pool.py` | 15 passed |
| `metadata/test_metadata_validators.py` | 10 passed |
| `test_computation_service_unit.py` | 31 skipped（订阅工厂未配置，预先存在，非本次改动导致） |

**诚实说明（T-01 缺口）**：改动前未先跑基线，故上表为**改动后单次运行**结果，不具备「改前/改后对比」证据强度。补偿措施：9 处调用点均为「遍历全部规则 + duck-typing 过滤」，`get_rules()` 原样返回即语义等价；且 Provider 单测覆盖了保序/不过滤/过滤三类语义。后续 M2 起，任何行为变更任务均先采集基线。

**未阻断项**：
- `--unit` 全量运行因 3 个环境依赖文件采集报错而中断（`meta/tests/migrations/test_e2e_verify.py` 需本地 sqlite；`test_export_e2e.py` / `test_v10_verify.py` 需后端 3010 在线）——与本次改动无关，改以逐 `--file` 方式运行。
- `test_computation_service_unit.py` 全量 skipped，第 5 处改动点未被实际执行验证（改动为机械等价替换）。

### M2（P2 属性确定语义）— 已完成

| 任务 | 状态 | 产出 / 证据 |
|---|---|---|
| T-05 `RuleType.DEFAULT` + yaml 映射 | 完成 | `models_enums.py` 枚举新增；`yaml_loader.py` 加 `RULE_TYPE_MAP` 项、`parse_default_rule`、`parse_rule` 分发 |
| T-06 `MetaDefaultRule` + 访问器 | 完成 | `models.py` dataclass（`source_type` / `source_value` / `apply_mode` / `apply_on` / `recompute`；`target_field` 只读属性）；`MetaObject.get_defaults()`；`RuleProvider.get_default_rules()` |
| T-07 `DefaultExecutor` + 分发 | 完成 | `rule_executor.py`：`_do_execute` 写入链（`apply_on` → `condition` → `no_value` → `target_not_empty` → 写入 + `overwritten` 标记）；`_execute_rule` 新增 `RuleType.DEFAULT` 分支；`validate_rule_for_object_type` 矩阵新增行（VIEW 拒绝） |
| T-08 `default_by_priority` | 完成 | 按 **`target_field`** 分组；组内 `(priority, rule.id)` 排序；**首个「命中且写入成功」获胜**，其后同组记 `not_first_match` |
| T-09 覆盖 / apply_on / 再判定 | 完成 | `apply_mode=fill_if_empty｜override`；`apply_on=user_input｜system｜both` 由 `ActionExecutor._resolve_change_source()` 驱动；`recompute=keep｜clear` 经 `_apply_recompute` |
| T-10 依赖图与异步名单兼容 | 完成（**核实为无需改代码**） | 见下方 T-10 结论 |
| T-11 `action_executor` 集成 | 完成 | `_do_create`（L1575）/ `_do_update`（L1922）在 `BEFORE_SAVE` **校验之前**调用 `apply_defaults`；新增 `_resolve_change_source`（L509）+ `_log_default_rules`（L523） |

**T-10 结论（无需改代码）**：

- `rule_chain.py` `_create_node`：DEFAULT 落入 `return None` 分支，`analyze()` 有 `if node:` 守卫 → **DEFAULT 不参与隐式规则链依赖图**，符合设计（DEFAULT 有专用求值器，不走链）。
- `async_interceptor_engine.py` L29-55：名单是**拦截器名字**（`PURE_READONLY` / `READ_MODIFY_WRITE` / `WRITE` / `ASYNC_INTERCEPTOR_NAMES`），与 `RuleType` 无关。
- 前端 `.vue/.js/.ts` 对 `derivation` 等 rule type 字符串**零引用** → 前端零改动（与 §2.2 爆炸半径核查一致）。

**M2 实测证据**：`test_default_rule_unit.py` **35 passed**（覆盖 T-05~T-09 / T-12 / T-14）；回归 `test_rule_engine.py` 9、`test_rule_provider_unit.py` 9、`test_derivation.py` 6、`metadata/test_metadata_validators.py` 10、`test_spec22_state_transition_action_pool.py` 15、`test_state_adoption_verification.py` 10 —— 全部 passed。导入环检查：`action_executor` / `rule_provider` 均可导入，无循环依赖。

**预先存在、非本次引入**：`meta/tests/test_action_executor.py` 2 failed（本地 sqlite `audit_logs` 表缺 `log_category` / `parent_object_type` / `error_message` 列，报错发生在**审计写库**，未触及默认值逻辑）+ 4 passed；`test_action_executor_validation_integration.py` 8 skipped；`test_computation_service_unit.py` 31 skipped（订阅工厂未配置）。

**实现偏差（已回填 Spec）**：Spec 草案字段名 `overwrite` / `on_recompute` / `source_ref` 实际落为 `apply_mode` / `recompute` / `source_value`；来源标记落为 `RuleContext.auto_filled_fields`（`set`）。「首个命中」口径细化为「首个**条件命中且实际写入成功**的规则获胜」。

**M2 补强：端到端验证（2026-10-03 追加，commit `0d5ea6ba`）**

T-11 的验收项「集成测试：保存后落库值正确」原先只有单测证据（直调 `apply_defaults`、绕过保存链路），经复核为**证据强度不足**，已补齐 [test_default_rule_integration.py](file:///d:/filework/excel-to-diagram/meta/tests/test_default_rule_integration.py)（**5 passed**）——走真实 `ActionExecutor.execute(obj, "crud_create", {...})`，断言 sqlite 落库值。

**E2E 首跑即发现 1 个真实缺陷（已修复，同 commit）**：

- **现象**：`price_list` 落库为 `PL_SYS`，而判定日志显示获胜规则 `d_pl_user` 算出的是 `PL_ZOR` —— 日志与落库值**不一致**。
- **根因**：`_do_create` 在 `apply_defaults`（L1575）之后又调用 `execute_rules(BEFORE_SAVE)`（L1581），后者按 `get_rules_by_trigger` 取规则 —— DEFAULT 规则默认 `triggers=[BEFORE_SAVE]`，于是被**二次执行**。该路径语义是「全局排序 + 全部执行」且 `change_source` 缺省 `both`，故 `apply_on='system'` 的规则被误触发并覆盖前一步结果。
- **修复**：`execute_rules` 选择规则时排除 `RuleType.DEFAULT`（`rule_executor.py` L1283-1291），使其只能经专用入口 `default_by_priority` / `apply_defaults` 执行。
- **为何单测漏掉**：单测直调 `apply_defaults`，不经过 `execute_rules` —— 这正是补 E2E 的价值所在。

**E2E 用例（7 项断言覆盖）**：① 条件命中 → 落库 ② 条件不命中 → 不写入 ③ `FILL_IF_EMPTY` 不覆盖用户已填值 ④ `OVERRIDE` 覆盖用户已填值 ⑤ `apply_on='system'` 在 `user_input` 下跳过（用「该目标字段唯一规则」干净验证）⑥ 同组首个命中获胜（`d_pt_first` 胜、`d_pt_second` 记 `not_first_match`）⑦ 判定日志可观测（`[DefaultRule]` / `not_first_match` / `apply_on_mismatch`）。

**M2 回归（修复后复跑）**：`test_default_rule_unit.py` 35 passed、`test_rule_engine.py` 9 passed、`test_rule_provider_unit.py` 9 passed、`test_default_rule_integration.py` 5 passed；`test_action_executor.py` 仍为 2 failed + 4 passed（与 M1 基线完全一致，无新增失败）。

### M3（P3 可解释性）— 已完成

| 任务 | 状态 | 产出 / 证据 |
|---|---|---|
| T-12 `DefaultLogEntry` + 装配 | 完成（**提前至 M2**） | T-07/T-08 需要，故提前实现；12 字段 + `to_dict()` |
| T-13 日志出口 | 完成（**口径调整**） | **不并入 `RuleExecutionReport`**（避免改动既有校验报告语义）；改由 `apply_defaults` 返回 `(data, logs)` + `ActionExecutor._log_default_rules` 逐条 `logging.info` |
| T-14 日志单测 | 完成 | `TestDefaultByPriority::test_log_seq_and_factor_snapshot` / `test_log_to_dict_keys`；`skip_reason` 五枚举 `condition_false` / `target_not_empty` / `apply_on_mismatch` / `not_first_match` / `no_value` 可复现 |

**M3 一期边界**：`auto_filled_fields` **不跨请求持久化**（TBD-3），故 `RECOMPUTE_CLEAR` 仅对同一请求内多次重判生效；`apply_defaults(...)` 已预留 `previously_auto_filled` 形参供二期接入。

### M4（P4 文档收口）— 已完成

| 任务 | 状态 | 产出 |
|---|---|---|
| T-15 研究报告口径修正 | 完成 | `2026-10-02-rule-model-research.md` → **v1.10**：§1、§8.2、§8.10②（连带 §10.2 / §10.6 #10 / §10.7 #3 / §11 结论 8 同步）、§8.3 四处主修正 |
| T-16 Spec / Plan 回填 | 完成 | Spec → **v1.1**（FR-005 细化 / FR-007 一期边界 / FR-010 实现口径 / §9.3 字段名回填）；本文件 M2~M4 进展记录 |

> **T-15 口径修正的实证依据**：原判「反向汇总 = ❌ 缺口 / 最低成本补齐项」**过强** —— 代码级核实 `computation_service.py` 已有 `count_children`（含 `GROUP BY` 批量版）/ `count_relations` / 表级 `SUM·AVG·MAX·MIN`；仍缺的是**按父分组的取值聚合 + 子行增删改重算**。已按「部分具备」改写。

### M5（P5 二期·dry-run 预演）— 已完成

| 任务 | 状态 | 产出 / 证据 |
|---|---|---|
| T-17 `dry_run_defaults` | 完成 | `action_executor.py` L539-587；浅拷贝求值 + 返回 `{success, change_source, data, auto_filled_fields, logs}`；异常被吞（预演失败不影响调用方） |
| T-18 试算端点 | 完成 | `meta_api.py` L322-358 `POST /api/v1/meta/<object_type>/defaults-preview`；已核实注册为 `/api/v1/meta/<object_type>/defaults-preview` |
| 回归 | 完成 | `meta/tests/test_default_rule_integration.py` **8 passed**（5 既有 + 3 新增）；新增 3 项见下 |

**新增 3 项测试（`TestDryRunDefaults`）**：

1. `test_dry_run_writes_nothing_and_matches_real_save` —— ①带出值正确 ②业务表计数 = 0 ③入参未被就地改写 ④**逐字段核对「dry-run 结果 == 真实保存落库值」**（可回放）
2. `test_dry_run_logs_carry_skip_reasons` —— 日志含 `not_first_match` / `apply_on_mismatch` / `seq` / `factor_snapshot`
3. `test_dry_run_does_not_persist_audit_or_data` —— 预演不产生审计记录

> **二期开工前的现状核查结论（代码级）**：原计划「紧接着补校验」**不成立** —— 校验已具备（`MetaValidation` + `ValidationExecutor` + `action_executor` L792-859 可阻断保存，见研究报告 §10.6 #6 [v1.11]）。核实后的真实缺口为：**按父分组的取值聚合**（低）、**集合确定**（大）、**拆分·分摊**（硬，带守恒）、**定价**（宜独立引擎）、**dry-run**（本 M5 已补）、**在线配置 UI**。

### M6（P6 二期·汇总补强）— 已完成

| 任务 | 状态 | 产出 / 证据 |
|---|---|---|
| T-19 按父分组取值聚合 | 完成 | `computation_service.py`：`_is_parent_grouped` / `_resolve_parent_aggregation` / `_aggregate_field_by_parent`（单条）+ `_batch_aggregate_field_by_parent`（`GROUP BY` 批量，失败回退逐条）；`compute_field` / `compute_batch` 两处分发分支 |
| T-20 向下兼容 | 完成 | 未声明 `target_object` → 仍走原整表/条件聚合；`_aggregate_field` 签名未改 |
| 回归 | 完成 | `meta/tests/test_computation_aggregation.py` **30 passed**（既有 18 + 新增 12）；`test_computation_by_semantics.py` **7 passed** |

**新增 12 项测试（`TestParentGroupedAggregation`）**：SUM/AVG/MAX/MIN by FK、无子行返 `None`、未知 `target_object`、缺 `source_field`、`foreign_key` 从层级推导、`compute_field`/`compute_batch` 分发、批量结果 == 逐条、无 `target_object` 时整表语义不变、批量 SQL 失败回退逐条。

**实现要点（与 `_count_children` 对称）**：

1. 复用既有 `comp_type`（`sum_field`/`avg_field`/`max_field`/`min_field`），以 `target_object` + `foreign_key` + `source_field` 声明「按父分组」；**不新增 `comp_type`** → `computed_subqueries` 下推矩阵不变，无非下推静默失败风险。
2. 单条 `SELECT <FUNC>(src) FROM child WHERE fk = ?`；批量 `SELECT fk, <FUNC>(src) FROM child WHERE fk IN (...) AND fk IS NOT NULL GROUP BY fk`（1 SQL 替代 N+1）。
3. 无匹配子行取值 `None`（与 SQL 聚合无行语义一致，区别于 `count_children` 的 `0`）。

> **诚实说明**：该测试文件此前因含 `INSERT INTO`（in-memory sqlite 夹具）被项目 raw-SQL 守卫**整文件跳过**（存量 17 项从未实际执行）。本轮按项目惯例（同 `test_object_owd.py` / `test_decision_effect.py`）在文件头 `os.environ.setdefault('ALLOW_RAW_SQL', '1')` 解除跳过，存量 17 项 + 新增 13 项一次性实跑通过。文件内全部为 `:memory:` sqlite，不触碰真实 DB。

### M7（P7 二期·拆分/分摊）— 已完成

| 任务 | 状态 | 产出 / 证据 |
|---|---|---|
| T-21 纯守恒算法 `plan()` | 完成 | `meta/services/allocation_service.py`（新，477 行）：最大余数法；`test_allocation_plan.py` 覆盖基础/守恒/校验三类 |
| T-22 子行定位 + FK 推导 | 完成 | `AllocationService._resolve_children` + `resolve_foreign_key`（`_require_ident` 白名单防注入）；显式 fk / 缺省推导 / 数量不匹配 422 |
| T-23 `allocate()` 分摊已有行 | 完成 | 事务内逐行 `crud_update` + 回读求和守恒断言；权重按 id 对齐；写失败 → 422 整体回滚 |
| T-24 `split()` 拆分建新行 | 完成 | 事务内 `crud_create` N 行 + 回读守恒；`weights` 优先否则 `split_count` 均分；`template` 附加字段 |
| T-25 接线 BO Action | 完成 | `meta/services/allocation_apply.py`（新）+ `bo_action_registrations.py` 注册 `allocation.apply` / `allocation.split`（`requires_admin=True`） |
| T-26 YAML 声明化 | **后置** | 用户明确后置；`RuleType.ALLOCATION` + 加载链路未做（见 §4 P7「为何后置」） |

**交付物**：`allocation_service.py`、`allocation_apply.py`、`test_allocation_plan.py`（27 passed）、`test_allocation_allocate.py`（11 passed，`pytestmark = pytest.mark.integration` + `ALLOW_RAW_SQL` 解除守卫）。commit `0d1f86a5`（7 files, +1136/-5）。

**关键实现要点**：

1. **权重整数化**：`Decimal` 的 `//` 是**向零截断**而非下取整 —— 负总额（`plan(-100,[1,1,1])`）下会得 `[-33.33]×3`（Σ=-99.99）破坏守恒。修复为按 `w_scale` 整数化后全程 Python `int` 运算。
2. **返回值规范化**：`Decimal` 除法会消尾零（`7000/100` → `'70'` 非 `'70.00'`），故统一 `.quantize(10**-scale)`。
3. **原子性**：`datasource.transaction()` 的**嵌套守卫**（`if self.in_transaction: yield; return`）使 `ActionExecutor` 内层 commit 加入外层；实测注入第 2 行失败后业务表**零残留**。
4. **契约机器校验**：`bo_action_contract.validate_registry` 要求 `object_type` 非空 → 用 `'*'`；`input_schema` 须为 `{"type":"object"}`。
5. **admin 门禁**：`requires_admin` 由 `bo_action_api.py` 从 registry 元数据统一施加，新 action 自动获得，无需额外配置。

**测试结果**：`test_allocation_plan.py` **27 passed** + `test_allocation_allocate.py` **11 passed** + `test_bo_action_contract.py` **36 passed** = **74 passed**。

**二次检查（提交前）**：修复 2 处 —— ① `allocation_service.py` 的 `from typing import ...` 漏了 `Dict`（因 Python 3.14.3 PEP 649 延迟注解求值未暴露；≤3.13 会导入即 `NameError`）；② `allocate()` 中 `parent_meta` 未使用（重构残留）。另确认全仓仅 1 处 action 数量断言（contract test）已同步 19→21，e2e 文件为硬编码清单无数量断言。

**未同步（依赖运行中的后端）**：`src/composables/useBoAction.types.d.ts` 重生成、`docs/api/bo-action-postman-collection.json` / `-apifox.json` 重导出、e2e 覆盖 2 个新 action。

---

## CHANGELOG

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-02 | v1.0 | 初版：Phase / 任务列表 / 里程碑；含方案 A 爆炸半径核查与 9 处收口清单 |
| 2026-10-03 | v1.1 | 新增 §9 实施进展记录：M1 完成 + T-04 回归结果 + T-01 基线缺口诚实说明；修正 T-02 验收项（`get_default_rules` 推迟至 T-06） |
| 2026-10-03 | v1.2 | **M2/M3/M4 完成回填**：§9 追加 M2（T-05~T-11，含 **T-10「依赖图/异步名单无需改代码」结论**、实现偏差、35 passed 证据、预先存在的 2 failed 归因）、M3（**T-12 提前至 M2**、**T-13 出口口径调整**、一期边界）、M4（T-15/T-16 产出）；§4 T-13/T-14/T-15 行修正；§5 里程碑表加「状态」列（M0~M4 全部完成） |
| 2026-10-03 | v1.3 | **补 T-11 的 E2E 证据并修复其暴露的缺陷**（commit `0d5ea6ba`）：新增 `meta/tests/test_default_rule_integration.py`（5 passed，走真实 `ActionExecutor` 落库）；E2E 首跑发现 DEFAULT 规则被 `execute_rules(BEFORE_SAVE)` **二次执行**、`change_source` 缺省 `both` 导致 `apply_on='system'` 规则误覆盖（`price_list` 由 `PL_ZOR` 变 `PL_SYS`）；修复为 `execute_rules` 排除 `RuleType.DEFAULT`；§9 追加「M2 补强：端到端验证」小节 |
| 2026-10-03 | v1.4 | **二期开工**：新增 P5 / M5「dry-run 预演」并落地 —— T-17 `ActionExecutor.dry_run_defaults`（复用同一条 `apply_defaults`，浅拷贝+零写库）、T-18 `POST /api/v1/meta/<object_type>/defaults-preview`；`test_default_rule_integration.py` 增至 **8 passed**；§3 二期行拆分（dry-run 已启动 / 其余预留并补入「集合确定 / 汇总补强 / 定价」）；§9 追加 M5 与二期现状核查结论（校验已具备、无需立项） |
| 2026-10-03 | v1.5 | **二期·汇总补强落地**：新增 P6 / M6 —— T-19 `_aggregate_field_by_parent` + `_batch_aggregate_field_by_parent`（按父外键分组的 SUM/AVG/MAX/MIN，单条 + `GROUP BY` 批量）、T-20 声明口径与 `count_children` 对称 + 向下兼容；复用既有 `comp_type`（不新增）故下推矩阵不变；`test_computation_aggregation.py` 解除 raw-SQL 守卫跳过并增至 **30 passed**（既有 18 + 新增 12）；§7 不做清单同步（取值聚合 N→1 已补） |
| 2026-10-03 | v1.6 | **二期·拆分/分摊落地**：新增 P7 / M7 —— T-21 `plan()` 最大余数法、T-22 `_resolve_children`（含 FK 推导）、T-23 `allocate()`、T-24 `split()`、T-25 2 个 BO Action（`allocation.apply` / `allocation.split`，commit `0d1f86a5`）；T-26 YAML 声明化**后置**；测试 **74 passed**（27 + 11 + 36）；§3 二期行拆分（新增 P7，把「拆分/分摊」移出预留）、§5 加 M7 行并更新「二期其余」注、§7 不做清单标注 M7 已落地、§9 追加 M7 小节（含二次检查修复项与未同步生成物） |
