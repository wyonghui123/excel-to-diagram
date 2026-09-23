# Schema Evolution Capability — 整体方案

> **版本**:v3.2 (v3.0 + 第四次研究 MDL + 第五次研究 EP 库 + PoC A/B/C 实证)
> **日期**:2026-09-22(v3.2 升级)
> **作者**:AI Agent + 团队 review
> **文档类型**:战略 + 战术一体化方案
> **性质**:单一真相源,所有"schema 演化能力建设"的入口文档

---

## §0 执行摘要(TL;DR)

### 0.1 一句话命题

> **"产品柔性 = 业务架构柔性 × 部署能力 × schema 规范性,权重 60:20:10。schema 规范不是演化能力的核心,业务架构才是。"**

### 0.2 三个核心决策(团队必须立即接受)

| # | 决策 | 理由 |
|---|---|---|
| **D1** | **范式转移**:从"规范驱动"→"识别驱动" | 规范是治标,识别才是治本 |
| **D2** | **3 支柱权重**:业务架构 60% > 部署 20% > schema 10% | 反推我们历史事故分布 |
| **D3** | **可测试先行**:4 个 PoC(修正后 1.7-3.2 人天) → 验证后再投入 | 避免"规范过载"陷阱(详见 §9.5 第三次 + 第四次研究) |

### 0.3 关键论断(反对过度规范化)

> **"在敏捷 / DevOps / AI Agent 三个时代,组织失败的最常见模式是"规范过载",不是"规范不足"。我们的方案必须"能砍就砍",而不是"加规范"。"**

---

## §1 命题与范式(为什么)

### 1.1 命题的精确表述

**用户原始命题**:
> AI 时代 + 企业敏捷 + 频繁 schema 变更 → migration 架构应该长什么样

**展开后的命题**:
> "在 AI 时代 + 企业敏捷下,产品演化能力 = 业务架构柔性 × 部署能力 × schema 规范性。三者权重悬殊(60:20:10)。**不均衡建设会导致"局部最优、整体次优"**。"

### 1.2 关键术语澄清

| 术语 | 定义 |
|---|---|
| **演化能力** | 产品面对变化时的适应速度与稳定性 |
| **产品柔性** | 演化能力的可观察表现,业务可塑性 |
| **业务架构柔性** | 业务概念清晰边界 + 跨边界时 schema 自然解耦 |
| **部署能力** | schema 与应用版本协同的部署与回滚能力 |
| **Schema 规范性** | migration 文件的工程化质量 |

### 1.3 范式转移点

| 维度 | v1.0(已废) | v3.0(本方案) |
|---|---|---|
| **核心命题** | migration 怎么写 | 演化能力怎么建 |
| **核心驱动** | 规范驱动(加 N 条) | 识别驱动(找问题根源) |
| **核心指标** | migration 写法合规率 | 产品迭代周期 + schema 演化事故率 |
| **核心团队** | DBA | 业务架构师 + SRE + DBA + PM + AI Agent |
| **演化能力来源** | 5 个 schema 原语 | 60% 业务架构 + 20% 部署 + 10% schema |

---

## §2 三大支柱(做什么)

### 2.1 总架构图

```
演化能力 = 60% × 业务架构柔性 + 20% × 部署能力 + 10% × schema 规范
                          ↓                       ↓                       ↓
              子原语 A1-A4            子原语 B1-B6              子原语 C1-C3
              (领域边界/上下文/           (history/grace/           (Expand-Contract/
              聚合/演化前瞻)              compat/canary/             Spec-Link/短小)
                                        shadow)
```

### 2.2 支柱 A:业务架构柔性(60%)—最高优先级

#### 子原语 A1:Domain Boundary First(领域边界优先)

**原则**:任何 schema 变更前,必须先回答业务领域边界问题。

**强制 review checklist**(PR 提交前):
- [ ] 这个字段/表属于哪个业务领域?
- [ ] 这个变更跨 2+ 领域吗?(跨 = 必须先做领域拆分)
- [ ] 已有同名字段在不同领域?(是 = 必须做 Bounded Context 拆分)

**review 形式**:架构 review 会议(每月 1 次),**不是 CI 检查**。

#### 子原语 A2:Bounded Context Mapping(限界上下文映射)

**原则**:不同业务上下文,可对同一业务概念有不同 schema 模型。

**实施方式**: `docs/domain/contexts/*.yml` + 跨上下文事件表。

**实证**: v089 DROP user_group_members → prod 报错的**根因**就是 `user_group` 在 3 个上下文含义不同,一刀切 DROP → 用户系统报错。

#### 子原语 A3:Aggregate Root Design(聚合根设计)

**原则**:**业务不变量的边界 = 聚合边界 = 一次事务边界 = schema 同步演化边界**。

**对 migration 的影响**:
- 同一聚合字段变更 = 可单 migration
- 跨聚合字段同步 = 应跨多次 migration
- 跨聚合 + 强同步 = **业务架构应重新设计**

#### 子原语 A4:Evolution Direction Foresight(演化方向前瞻)

**原则**:提前识别"纵向重组候选"(合表/拆表/改语义),提前标红线。

**实施方式**: `docs/domain/evolution_forecast/` 季度 review。

### 2.3 支柱 B:部署能力(20%)—已部分落地

| # | 子原语 | 状态 | 工作量 |
|---|---|---|---|
| **B1** | Deploy History 两步写 | ✅ 已落地(2026-09-18 commit cd33bd2a) | 0 |
| **B2** | Restart Grace Period | ✅ 已落地 | 0 |
| **B3** | Compat Matrix 维护 | ⚠️ 规范已写,未落地 | 1 人天 |
| **B4** | Rollback 走应用版本 | ✅ 规范已写(订正 v1.0 错误) | 0.5 人天(规范强化) |
| **B5** | Canary Deploy | ⚠️ 推荐,未落地 | 1 人天 |
| **B6** | Shadow Migration | ⚠️ 可选 | 1 人天 |

**实证**: 2026-09-18 prod 部署 P0 三件套教训 — restart false-negative → abort → 误回滚风险。B1+B2 已治标。

### 2.4 支柱 C:Schema 规范(10%)—7 子原语(v3.2 升级)

> **v3.2 升级**:第五次研究新增 C6(执行模式必选)+ C7(回退路径必填)。原 C1-C5 不变。

#### 子原语 C1:Expand-Contract 强制

| 变更类型 | 破坏性 | 处理 |
|---|---|---|
| ADD COLUMN 可空/有 DEFAULT | 否 | 单次 migration |
| ADD COLUMN NOT NULL 无 DEFAULT | ⚠️ 中度 | Expand(可空) + Backfill |
| RENAME / DROP TABLE / DROP COLUMN / CHANGE TYPE | ✅ 高 | **5 阶段 Expand-Contract**(Expand → Backfill → Migrate → Deprecate → Contract) |
| DROP INDEX / CONSTRAINT | ⚠️ 中度 | 单次 + 监控 |

**禁止**:同一 PR 含 DROP TABLE / DROP COLUMN(无 deprecated 90 天记录 + grep 无引用)。

#### 子原语 C2:Spec-Link 必填

任何 schema 变更 PR 必须挂业务 spec 链接(spec 由 PM + 架构师共同写)。

**PR 模板**:见 §4.4。

#### 子原语 C3:单 Migration 短小

单个 migration < 30 行 SQL/Python(不含 docstring)。**长 = 必然耦合 = 必然可拆 = 必须拆**。

#### 子原语 C6:Execution Pattern 必选(第五次研究新增)

**必填字段**:`execution_pattern: EP1-EP8` (详见 §11)。

**决策依据**: §11.3 决策树(变更类型 × 表大小 × DB 引擎 × 应用层改造)

**验证工具**: D4 审查阶段 `meta/tools/migration_lint.py` 机读校验(PoC E)

**不通过的后果**:**阻断 PR merge**

#### 子原语 C7:Rollback Path 必填(第五次研究新增)

**必填字段**:`rollback_strategy: A/B/C`

- **A 自动 undo**(Flyway undo): 仅适合纯 schema 变更,**数据变更不可逆**
- **B 新 migration 修补**(Forward-fix): 业内**主流推荐**(Flyway 官方文档)
- **C DB 快照 + 还原**: 大改动需停机,**当前项目默认不启用**

**当前项目默认 B**(v089 即 B)。

#### 不在规范里的(避免过载)

| 条款 | 决定 |
|---|---|
| schema-as-code | ❌ 缓行(过度抽象) |
| time window policy | ❌ 缓行(成本高于收益) |
| drift 检测 | ❌ 缓行(等 v200) |
| baseline 命令 | ❌ 暂不需要 |
| repeatable migrations | ❌ 暂不需要 |
| full schema contract | ❌ 只校验关键表 |
| audit_log trigger | ⚠️ 可选 |
| evolution timeline 文档 | ⚠️ 改为 forecast review |

**理由**:每加一条规范 = 团队多一份认知负担 = 演化减速。

---

## §3 识别系统架构(怎么做)

### 3.1 4 层架构图

```
┌──────────────────────────────────────────────────────────────┐
│   Layer 4: 应用引用图 (Application Schema References)         │
│   ─ yaml 引用 + 代码 AST 扫描 + PRAGMA 外键                   │
│   ─ output: {table:orgs} → [yaml/role.yaml, code/...py]      │
└──────────────────────────────────────────────────────────────┘
                              ↓ 影响分析
┌──────────────────────────────────────────────────────────────┐
│   Layer 3: 差异引擎 (Schema Diff Engine)                      │
│   ─ DB Schema ←→ 期望 Schema                                  │
│   ─ output: diff report + impact report                       │
└──────────────────────────────────────────────────────────────┘
                              ↑ 提取 ↓ 比较
┌──────────────────────────────────────────────────────────────┐
│   Layer 2: 声明式 schema 真相源 (Source of Truth)              │
│   ─ meta/schemas/snapshot.yml (master, 唯一可信)              │
│   ─ generated_schema.sql (派生, SQL 输出)                    │
│   ─ 47 个 yaml (派生, 给 BODefinition)                       │
│   ─ .schema_version.json (派生, 哈希指纹)                     │
└──────────────────────────────────────────────────────────────┘
                              ↑ 生成 ↓ 实例化
┌──────────────────────────────────────────────────────────────┐
│   Layer 1: DB 实例化状态 (Actual Database State)               │
│   ─ SchemaIntrospector.list_tables() / introspect()           │
│   ─ PRAGMA table_info / foreign_key_list / index_list        │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 我们当前的能力清单(实地调研结果)

| # | 能力 | 文件 | 状态 |
|---|---|---|---|
| 1 | `SchemaIntrospector.list_tables()` | `meta/core/schema_introspector.py:49` | ✅ 实现 |
| 2 | `SchemaIntrospector.introspect(table)` | `meta/core/schema_introspector.py:76` | ✅ 实现 |
| 3 | `SchemaIntrospector.diff_with_yaml()` | `meta/core/schema_introspector.py:106` | ✅ 实现 |
| 4 | `SchemaComparator.compare()` | `meta/core/schema_generator.py:329` | ✅ 实现 |
| 5 | `SchemaMigrator.migrate()` | `meta/core/schema_generator.py:374` | ✅ 实现 |
| 6 | `sync_schema.py --diff` | `meta/tools/sync_schema.py:71` | ✅ 实现 |
| 7 | `generated_schema.sql` | `meta/schemas/generated_schema.sql` | ✅ 已有(2026-05-26)|
| 8 | `.schema_version.json` 哈希 | `meta/tools/sync_schema.py:53` | ✅ 实现 |
| 9 | `app_builder.with_auto_schema()` | `meta/core/app_builder.py:66` | ✅ 调用 |
| 10 | **应用引用图** | ❌ | ❌ **完全缺失** |
| 11 | **snapshot.yml 单一真相源** | ❌(多源分散) | ❌ **缺失** |
| 12 | **统一 diff 引擎** | ❌(功能分散) | ❌ **缺失** |
| 13 | **DDL 实时审计** | ❌ | ❌ 缺失(SQLite 限制) |

**结论**: **60% 能力已有,但串联度 = 0,自动化 = 0,可发现性 = 低**。

### 3.3 关键改进:L2 单源化 + L4 引用图

**L2 改进**:**snapshot.yml 作为 master**,其他都是它的派生。
**L4 新增**:`SchemaReferenceGraph` — 这是治 v089 类事故的根治手段。

---

## §4 PoC 验证路径(立刻做什么)

### 4.1 总原则

- **可单独测试**(每个 PoC 独立验证)
- **可低成本试错**(每个 0.5-1.5 人天)
- **有明确产出**(验证假设 + 给团队反馈)
- **失败也是学习**(每个 PoC 必须有失败标准)

### 4.2 PoC 候选

> **§9.5 第三次研究修正(2026-09-22)**:经 git 历史 + 代码实地调研,**工作量从原 2.5 人天下调到 1.2-1.7 人天**(详见 §9.5)。其中 PoC A 不是"建",是"修 + 实证"。

| 方向 | 假设(Hypothesis)| 原估 | 修正 | 风险 | 推荐度 |
|---|---|---|---|---|---|
| **A: snapshot.yml 单一真相源** | H1: 建立后生成成本低于分散维护 | 0.5 | **0.2 人天** | 低 | ⭐⭐⭐⭐⭐ |
| **B: 应用引用图** | H2: 引用图可在 v089 类事故前自动发现"代码引用不存在的表" | 1.5 | **0.5-1 人天** | 中 | ⭐⭐⭐⭐⭐ |
| **C: 部署期 schema drift 检测** | H3: 每次 deploy 前自动对比 prod DB 与 snapshot | 0.5 | **0.5 人天** | 低 | ⭐⭐⭐⭐ |
| **D: DDL 实时审计触发器** | H4: DDL 触发器可实时捕获 schema 变更 | 1 | **缓行** | 高(SQLite) | ⭐⭐ |

### 4.3 PoC A:snapshot.yml 真相源(0.2 人天 — 第三次研究修正)

**实施步骤**:
1. 从现有 47 yaml + generated_schema.sql 抽取 `meta/schemas/snapshot.yml`
2. 写 `tools/regen_snapshot.py`:从 yaml + sql 重新生成 snapshot.yml(必须可复现)
3. 写 `tools/schema_diff.py --snapshot`:对比 DB vs snapshot,输出 diff

**成功标准**:
- 一致率 ≥ 95%(snapshot 与 47 yaml + sql)
- 误报率 < 5%(prod 真实跑一遍)
- 生成耗时 < 30s

**失败标准**:
- 一致率 < 90% → 暂停,先统一 yaml 格式
- 生成耗时 > 60s → 改用增量生成

### 4.4 PoC B:应用引用图(0.5-1 人天 — 第三次研究修正)

**实施步骤**:
1. 写 `meta/core/schema_reference_graph.py`(最小可用版)
2. 实现 3 个扫描器:
   - `scan_yaml_references()` — 解析 47 yaml 的 `table_name` / `through` / `source_key` / `target_key`
   - `scan_code_references()` — AST 扫描 Python f-string 中的 SQL(`FROM {table}`、`DELETE FROM {x}`)
   - `scan_fk_references()` — PRAGMA foreign_key_list
3. 写 `tools/schema_ref_graph.py --impact <table>` 查询影响面

**关键测试**:
- 把 v089 DROP 的 11 张表名放进 snapshot.yml
- 用 `schema_ref_graph --impact user_group_members` 查询
- **期望**:能看到 role.yaml 中 `through: user_group_members` 引用(实际 prod 报错源头)

**成功标准**:
- v089 类引用被正确发现
- 查询响应 < 2s
- 漏报率 < 10%

**失败标准**:
- v089 类引用未被识别 → 暂停,先研究 AST 扫描覆盖率
- 查询响应 > 5s → 改用增量索引

### 4.5 PoC C:部署期 drift 检测(0.5 人天 — 维持)

**实施步骤**:
1. 写 `tools/check_schema_drift.py`
2. 流程:取 prod DB schema → 取 snapshot.yml → diff → 不一致则警告
3. 集成到 `tools/staging_round.py deploy`(deploy 前调用)

**成功标准**:
- 报告含已知 drift 项 ≥ 70%
- 误报率 < 10%
- 部署流程集成无副作用

**失败标准**:
- 误报率 > 20% → 改 strict → lenient 模式
- 报告空(< 30% 已知 drift) → 暂停

### 4.6 PoC D:DDL 实时审计(缓行)

**SQLite 限制**:**SQLite 没有 DDL 触发器** — 这与 PG/MySQL 不同。

**替代方案**:应用层包装器 `meta/core/ddl_capture.py` 拦截 schema 改操作。

**建议**:PoC D 暂缓,等迁移到 PostgreSQL 时再考虑。

### 4.7 PoC E:Migration Lint(第五次研究新增,v3.2)

**目的**:在 PR 阶段机读校验 `execution_pattern` + `rollback_strategy` 两个必填字段。

**假设**:**H5**: 通过静态 lint 强制填写 EP/回退字段,可显著降低"未指定执行模式"导致的 prod 锁表事故。

| 项 | 内容 |
|---|---|
| 投入 | 0.5 人天(基于 AST 解析 + YAML schema 校验) |
| 产出 | `meta/tools/migration_lint.py` |
| 集成点 | PR CI hook(类似 PoC B 的 ref_graph CI 阻断) |

**实现核心**:
```python
def lint_migration(migration_path: str) -> List[Issue]:
    issues = []
    spec = load_migration_spec(migration_path)  # 解析 .migration_spec/vXXX.yaml
    if 'execution_pattern' not in spec:
        issues.append(Issue.MISSING_EXECUTION_PATTERN(migration_path))
    if 'rollback_strategy' not in spec:
        issues.append(Issue.MISSING_ROLLBACK_STRATEGY(migration_path))
    if spec.get('execution_pattern') not in {f'EP{i}' for i in range(1, 9)}:
        issues.append(Issue.INVALID_EXECUTION_PATTERN(spec.get('execution_pattern')))
    # EP4-EP8 在 SQLite 上不可用
    if spec.get('execution_pattern') in {'EP2', 'EP3', 'EP4', 'EP8'}:
        issues.append(Issue.EP_NOT_SUPPORTED_ON_SQLITE(spec['execution_pattern']))
    return issues
```

**成功标准**:
- [ ] 检测"缺 execution_pattern" 100% 命中
- [ ] 检测"缺 rollback_strategy" 100% 命中
- [ ] 检测"SQLite 上用 EP2-EP8" 100% 命中
- [ ] 退出码语义:有 issue → exit 1(CI 阻断)

**失败标准**:
- 误报率 > 10% → 改 strict 模式
- 漏报(实际不合规但未告警) > 0 → 立即修复

---

## §5 行业最佳实践(对标)

### 5.1 业内主要产品矩阵

| 产品 | 范式 | 声明式 | 自动 diff | 引用追踪 | 适用 |
|---|---|---|---|---|---|
| **Skeema**(GitHub 在用) | SQL CREATE 声明式 | ✅ | ✅ | ⚠️ 部分 | MySQL/MariaDB |
| **Atlas**(Ariga) | HCL 声明式 | ✅ | ✅ | ✅(Premium) | 多 DB |
| **Prisma** | Schema 声明式 | ✅ | ✅ | ✅(Client) | TS 项目 |
| **Flyway** | SQL 版本化 | ⚠️ 弱 | ⚠️ 弱 | ❌ | 多 DB |
| **Pgroll**(Supabase, 2024+) | Migration job | ⚠️ 弱 | ✅(job 内置) | ❌ | Postgres |
| **Bytebase** | SQL 声明式 + UI | ✅ | ✅ | ⚠️ 部分 | 多 DB |

### 5.2 业内最佳实践 5 个 takeaway

| # | takeaway | 来源 |
|---|---|---|
| 1 | **声明式 schema 是 AI 时代的"上下文",不要建多源** | Skeema 文档原话 |
| 2 | **DB 与期望 diff 必自动化,且保证 DDL 100% 正确** | Skeema "internal safety mechanisms" |
| 3 | **应用引用图 = 高级话题,但能根治"运行时发现 schema 不一致"** | Prisma Client + Skeema Premium |
| 4 | **per-table per-file 优于单文件 snapshot** | Skeema 文档 |
| 5 | **schema drift detection 要 deploy 前/后双重** | Bytebase / Pgroll |

### 5.3 我们与业内的差距

| 差距 | 业内范式 | 我们当前 | 优先级 |
|---|---|---|---|
| 真相源分散 | 单一 snapshot 目录 | 47 yaml + 1 sql + 1 json | 🔴 高 |
| 缺引用图 | Prisma Client / Skeema Premium | 完全没 | 🔴 高 |
| 缺 per-table file | Skeema 模式 | 单文件 generated_schema.sql | 🟡 中 |
| DDL 无实时审计 | Bytebase 模式 | 无 | 🟢 低(SQLite 限制) |
| 缺 impact 报告 | Prisma 模式 | 无 | 🟡 中 |

---

## §6 整体实施路径(2.5 周)

### 6.1 阶段规划

```
Week 1 (PoC 验证阶段):
  Day 1: PoC A (snapshot.yml 单一真相源)
  Day 2-3: PoC B (应用引用图)
  Day 4: PoC C (部署期 drift 检测)
  Day 5: 复盘 + 决策

Week 2 (生产落地,若 PoC 成功):
  Day 1-2: 把 PoC A 落地为生产工具
  Day 3-4: 把 PoC B 落地为生产工具
  Day 5: 把 PoC C 集成进 staging_round.py

Week 2.5 (业务架构 review 启动,若全部 PoC 成功):
  Day 1: 创建 docs/domain/contexts/ (3 个上下文)
  Day 2: 创建 docs/domain/aggregates/ (2 个聚合)
  Day 3: 创建 docs/domain/evolution_forecast/
  Day 4: 召集首次架构 review 会议
  Day 5: B3 (compat matrix) + B5 (canary deploy) 规划
```

### 6.2 总工作量

| 阶段 | 工作量 | 关键产出 |
|---|---|---|
| PoC A | 0.5 人天 | snapshot.yml + diff 工具 |
| PoC B | 1.5 人天 | 引用图 + impact 工具 |
| PoC C | 0.5 人天 | drift 检测 + staging 集成 |
| 业务架构 review 启动 | 3 人天 | contexts + aggregates + forecast |
| 生产落地(PoC A/B/C) | 5-7 人天 | 生产工具 |
| **合计** | **10.5-12.5 人天 / 2.5 周** | |

### 6.3 决策树(失败路径)

```
PoC A 失败 → 暂停,先统一 yaml 格式
PoC B 失败 → 暂停,先研究 AST 覆盖率
PoC C 失败 → 改 strict → lenient 模式,再试

全部失败 → 回到"靠 PR review 的人工时代",承认技术天花板
部分失败 → 重新评估权重,可能回归 v2.0 规范精简
全部成功 → 进入生产落地
```

---

## §7 风险与局限

### 7.1 v3.0 的局限

| 局限 | 说明 |
|---|---|
| 60:20:10 权重基于我们历史反推 | 不普适,业界可能不同 |
| 业务架构 review 可能流于形式 | 架构师可能过度发挥,导致规范变"人治" |
| 多 DB 协调未涵盖 | SQLite 限制,未来 PG 时需扩展 |
| 跨多个 Bounded Context 事务一致性未涉及 | Saga/CQRS 复杂,本方案不涉 |
| 大规模团队(> 50 人)协调未涉及 | 我们目前 < 10 人 |

### 7.2 错误的可能性

- 60:20:10 实际可能是 50:30:20 或 70:15:15
- 业务架构 review 没真实产出,只是 DBA 改名
- "精简到 3 条"是修辞诱惑,团队仍想要更多条款

### 7.3 未来 review 触发条件

- 6 个月后(2027-03):第一次 v3.0 review
- v200 migration 后:重新评估
- 团队规模翻倍后:重新评估

---

## §8 反思与自我质问(本方案的认知价值)

### 8.1 我们走了什么弯路

| 轮次 | 错在哪 | 自我反思 |
|---|---|---|
| **v1.0 5 个原语** | 过度抽象,过度规范化 | 把"工具栈"思维当"演化能力" |
| **v1.1 订正 + 8 补** | 在战术层修补 | 没意识到根因在战略层 |
| **v2.0 60:20:10 + 11 子原语** | 仍偏向"加规范" | 应转向"减规范 + 加识别" |
| **识别系统研究** | 没串联已有 60% 能力 | 应该先盘清存量,再说增量 |
| **行业对标 + PoC** | 终于收敛到可执行 | PoC 失败也是学习 |

### 8.2 真正的不变认知

> **"产品柔性不在 migration 规范,在业务架构。"**

> **"在敏捷 / DevOps / AI Agent 三个时代,组织失败的最常见模式是'规范过载',不是'规范不足'。"**

> **"识别 ≠ 自动修复。短期识别就是 80% 价值。"**

### 8.3 下次 review 应严格质问

- 6 个月后,**业务架构 review 真的有产出吗?**
- **compat_matrix 真的被 CI 用了吗?**
- **3 条规范 vs 5 条规范,事故率真的有差异吗?**

如果回答"没有",**v4.0 应继续精简,而不是继续加条款**。

---

## §9 决策选项(给团队)

### 选项 A:立即落地 v3.0

**做什么**: 2.5 周 / 10.5-12.5 人天落地整个方案
**适用**: 团队资源充裕,演化能力是当务之急

### 选项 B:先 PoC,验证后再决定(推荐)

**做什么**: 原 2.5 人天 / **第三次+第四次研究修正后 1.7-3.2 人天**跑 4 个 PoC,验证后决策
**适用**: 资源有限,需要证据再投入
**核心修正**:PoC A 第一动作不是"建",而是"修 sync_schema.py import + 跑一次 diff"(0.2 人天实证)。详见 §9.5。

### 选项 C:只落地高 ROI 部分(PoC A + B + 业务架构 review)

**做什么**: 5 人天,治本
**适用**: 团队认知强,愿意先建最高优先级

### 选项 D:维持现状

**做什么**: 不动,等下次事故再说
**适用**: 暂无资源

---

## §9.5 选项 B 的第三次穿透研究(2026-09-22)

> **研究动机**:v3.0 §9 选项 B 的 PoC 设计是"理论设计",未做 git 历史 + 代码实地调研。**直接信,会落入"研究过拟合"陷阱**。

### 9.5.1 关键问题:为什么之前不做?

#### git 历史实证(2026-09-22)

| 工具/能力 | 首次入库 commit | 入库后演进 | 状态判断 |
|---|---|---|---|
| `meta/tools/sync_schema.py` | `46aa28cd baseline` (2026-09) | **零 commit** | 一次性快照,从未实际使用 |
| `meta/core/schema_generator.py` | `46aa28cd` | `9c877fe3 fix: missing MetaIndex import` | **历史已腐烂,曾被修过又闲置** |
| `tools/staging_round.py` prod-preflight | baseline 后增量 | 多次增量 | **活跃使用** |
| `schema-evolution-capability.md` | 本次新建 | 无 | v3.0 |

**结论**:`sync_schema.py` 在 baseline 里就是**死的代码** —— 写完后没跑过几次,import 错误没修,导致能力闲置整整几个月。这次 v089 prod 报错前,**根本没人真正依赖它做事**。

#### 2026-07-14 smart-delta-deploy 设计的盲点

查 `docs/superpowers/specs/2026-07-14-smart-delta-deploy-design.md` 的"完整 7 步工作流" —— **第 4 步"远端解包"只做了文件 MD5 对账**,**完全没有"DB schema 期望对账"这个维度**。

> 这是**设计层面的盲点**:只关心代码 drift,不关心 schema drift。但 schema drift **才是 v089 报错的根因**(代码里 `role.yaml` 引用 `user_group_members` 表,而该表从未被 `generated_schema.sql` 生成) —— **比代码 drift 更隐蔽、更致命**。

#### 元反思:"规范驱动"思路为什么失灵?

V3.0 §1.3 提到"范式转移:规范驱动 → 识别驱动",但**核心没回答一个问题**:

> **即使规范写得再完美,谁来"持续执行"它?**

sync_schema.py 本来就是这个"持续执行者",但它:
1. **从来没真正跑通过**(import 错误)
2. **没有"产出→消费"的回路**(没人订阅它的输出)
3. **没有"对账→阻断"的强制点**(没有接入 prod-preflight)

**所以这次研究的核心反思是**:

> "规范驱动"的本质是**寄希望于"人/AI自觉遵守"** —— 在 AI Coding Agent 时代这是个**危险假设**(AI 是 LLM,不是规则引擎,会"幻觉"出 `through: user_group_members` 引用)。
>
> **必须把"识别 + 阻断"做成工具,而不是规范。**

### 9.5.2 v3.0 §9 选项 B 的修正

#### 工作量估算修正

| PoC | 原估算 | 修正估算 | 修正依据 |
|---|---|---|---|
| **A: snapshot.yml 真相源** | 0.5 人天 | **0.2 人天** | `sync_schema.py` 核心代码已存在(355 行),实际只需修 import + 跑一次 |
| **B: 应用引用图** | 1.5 人天 | **0.5-1 人天** | yaml 数据已存在(11 yaml + 5 through),`association_engine._through_non_id_columns()` 已实现,仅需新写一层扫描器 |
| **C: 部署期 drift 检测** | 0.5 人天 | **0.5 人天** | 全新实现,但 `prod-preflight` 钩子已就绪,接入成本低 |
| **D: DDL 实时审计** | 缓行 | **缓行** | SQLite 限制,真正跳过 |
| **总计** | **2.5 人天** | **1.2-1.7 人天** | 比原方案少 ~50% |

**核心发现**:这个能力的**大部分零件已经在仓库里**(只是闲置/腐烂),实际工作量**显著低于从零开始**。

#### 关键修正:PoC A 不是"建",是"修"

原方案 PoC A 是"建 snapshot.yml 真相源"。但 sync_schema.py 已经在 baseline 里写过,只是 import 错误。

**真实可执行第一步不是"建 PoC A",而是"修 sync_schema.py + 跑一次 diff"**:

```bash
# Step 1: 修 import (10 分钟)
# meta/tools/sync_schema.py:20
#   from meta import registry, list_meta_objects, get_meta_object
# → from meta import get_meta_object
# (list_meta_objects 在 meta/__init__.py 没导出,需用 get_meta_object 替代)

# Step 2: 跑一次 diff (5 分钟)
cd d:\filework\excel-to-diagram
python -m meta.tools.sync_schema --diff

# Step 3: 把生成的 .schema_version.json commit 进去 (5 分钟)
git add meta/schemas/.schema_version.json
git commit -m "chore(schema): baseline snapshot from existing yaml"
```

**这一步就是 PoC A 的"实证" —— 跑通 = 成功,跑不通 = 暴露更深问题**。

### 9.5.3 真正的选项 B 可执行路径(4 阶段 1.2-1.7 人天)

> **核心原则**:用最低成本让"schema drift 检测"**真实地、可重复地**在 prod-preflight 跑起来一次。**不要"建规范",要"造机器"**。

#### 阶段 1:实证 PoC A(0.2 人天,半天)

| 动作 | 时间 | 产出 |
|---|---|---|
| 修 `sync_schema.py` import | 10 分钟 | 文件可执行 |
| 跑 `--diff` | 5 分钟 | 真实差异报告 |
| commit `.schema_version.json` | 5 分钟 | 真相源基线入库 |
| 写 `docs/research/poc-a-evidence.md` | 1 小时 | 实证结果记录 |

**成功标准**:
- [ ] `--diff` 命令**无异常退出**
- [ ] 输出的 `new_fields` 是真实存在的(不是空表里"假装新增"的字段)
- [ ] `.schema_version.json` 文件 < 50KB(可纳入 git 跟踪)

**失败标准**(任一命中即说明更深问题):
- [ ] `--diff` 报 ImportError / NameError → 说明 schema_generator 比想象更腐烂,需要先修它
- [ ] 输出"new_objects = []"但实际有 yaml → 说明 yaml 没被 `meta.registry` 加载,加载机制有问题
- [ ] 输出"new_fields"包含**真实 DB 中已存在的字段** → 说明 hash 算法把"无关变化"也算进了

#### 阶段 2:最小引用图 PoC B(0.5 人天)

| 动作 | 时间 | 产出 |
|---|---|---|
| 新增 `meta/tools/ref_graph.py` | 2 小时 | 仅扫描 `*.yaml` 中的 `through` 字段,生成 `meta/schemas/.ref_graph.json` |
| 跑一次生成 | 5 分钟 | 真实引用图数据 |
| commit `.ref_graph.json` | 5 分钟 | 引用图入库 |

**注意**:这一阶段**不查代码**(grep SQL),只查 yaml 内的 `through: xxx` 字段。**够轻、够快**。

**输出格式设计**:
```json
{
  "edges": [
    {
      "from_table": "user_group_members",
      "to_table": "user_groups",
      "via": "yaml:role.yaml:assigned_groups.through",
      "type": "association",
      "cascade_delete": true
    },
    {
      "from_table": "role_permissions",
      "to_table": "permissions",
      "via": "yaml:role.yaml:role_permissions.through",
      "type": "m2m_join_table"
    }
  ]
}
```

**成功标准**:
- [ ] 输出的 edges 与 yaml 内 `through` 字段 100% 对应(用 grep yaml 反向验证)
- [ ] 能精确指出 `role.yaml:assigned_groups.through` 引用了不存在的 `user_group_members` 表(如果当前 yaml 状态如此)

**这是 v089 报错的"复现能力"**:有 ref_graph.json,任何"yaml 通过 through 引用不存在的表"都会被立刻识别。

#### 阶段 3:部署期 drift 检测 PoC C(0.5 人天)

| 动作 | 时间 | 产出 |
|---|---|---|
| 新增 `meta/tools/drift_check.py` | 3 小时 | 对比 .schema_version.json vs 实际 DB schema |
| 接入 `tools/staging_round.py` `prod-preflight` | 1 小时 | prod-preflight 第 5 项检查 |
| 跑一次真实 prod-preflight | 30 分钟 | 真实 drift 报告(可能为空,可能暴露真实漂移) |

**实现核心**(基于已有 `SchemaComparator`):
```python
# meta/tools/drift_check.py 核心逻辑
def check_drift(conn) -> List[Drift]:
    drifts = []
    for table_name in get_all_meta_tables():
        meta_obj = get_meta_object(table_name)
        if not meta_obj:
            drifts.append(Drift.EXTRA_TABLE_IN_DB(table_name))
            continue
        actual_columns = introspect_db_columns(conn, table_name)
        expected_columns = meta_obj.fields
        diff = compare_columns(actual_columns, expected_columns)
        if diff.missing_in_db:
            drifts.append(Drift.MISSING_COLUMNS(table_name, diff.missing_in_db))
        if diff.extra_in_db:
            drifts.append(Drift.EXTRA_COLUMNS(table_name, diff.extra_in_db))
    return drifts
```

**接入 prod-preflight**:
```python
# tools/staging_round.py 中追加
def run_prod_preflight(args):
    checks = [
        check_port_listen,           # 已有
        check_service_active,         # 已有
        check_db_quick_check,         # 已有
        check_lag_commits,            # 已有
        check_schema_drift,           # 新增,引用 drift_check.check_drift
    ]
```

**成功标准**:
- [ ] 在 prod 实际跑一次,产出"无 drift"或"列出真实 drift"
- [ ] 如果列出 drift,需要人工判断哪些需要修、哪些是历史遗留(可能是 false positive)

**注意**:这个 PoC 第一次跑很可能**会暴露一堆历史 drift**(因为之前没人对账过)。需要人工"triaging"过程,不要把它当一次性任务。

#### 阶段 4:沉淀成可重复流程(0.2 人天)

| 动作 | 时间 | 产出 |
|---|---|---|
| 把 PoC A 跑通脚本 commit 进 `meta/tools/` | 5 分钟 | 工具版本化 |
| 把 PoC B 跑通脚本 commit | 5 分钟 | 工具版本化 |
| 在 `deploy.sh` 加一行 `python -m meta.tools.drift_check --prod` | 30 分钟 | **强制点**(每次部署必跑) |
| 更新 v3.0 文档 §10 附录:记录实证结果 | 1 小时 | 文档闭环 |

**关键点**:`deploy.sh` 加一行是**整个研究的成败点** —— 没有这个,drift_check 只是个一次性玩具。

#### 阶段 5:执行层基建(0.5-1.5 人天,第五次研究新增)

> **承接**:前三阶段完成"识别层闭环"后,第五次研究引入"执行层"概念。
> **新增 PoC E**(见 §4.7):`migration_lint.py` 静态校验 EP/rollback 字段。

| 动作 | 时间 | 产出 |
|---|---|---|
| 写 `meta/tools/migration_lint.py` | 0.3 人天 | 静态校验 `execution_pattern` + `rollback_strategy` 必填 |
| 跑一次真实 lint(对 v001-v089 历史 migration) | 0.1 人天 | 历史 migration 合规报告 |
| 接入 PR CI hook | 0.1 人天 | **强制点**(PR 缺 EP/rollback 即阻断) |

**成功标准**:
- [ ] 检测"缺 execution_pattern" 100% 命中
- [ ] 检测"缺 rollback_strategy" 100% 命中
- [ ] 历史 migration 合规率报告输出(预期 < 5%,作为 baseline)

**失败标准**:
- 误报率 > 10% → 改 strict 模式
- 历史 migration 100% 不合规 → 说明 PoC C 的 lint 规则不切实际,需放宽

**与原 §9.5.3 阶段 1-4 的关系**:
- 阶段 1-4 = 识别层闭环(L1-L4 yaml 部分)
- **阶段 5 = 执行层基建**(C6/C7 + PoC E)

**合计工作量**:**1.2-1.7(识别) + 0.5-1.5(执行) = 1.7-3.2 人天**(从 §9.5 修正后 1.2-1.7 人天,扩展为完整闭环)。

### 9.5.4 修正后的"成功/失败标准"

#### 整体成功标准(整个选项 B 走完)

**必要条件**(全部命中才算成功):
1. `python -m meta.tools.sync_schema --diff` 在 prod DB 上**无错跑通**
2. `python -m meta.tools.ref_graph` 产出 yaml 引用图,**能复现 v089 报错**(role.yaml 引用 user_group_members)
3. `python -m meta.tools.drift_check --prod` 在 prod-preflight 阶段输出报告
4. `deploy.sh` 在 prod 部署前**自动调用 drift_check**,有 drift 时阻断

#### 整体失败标准(任一命中即"选项 B 路线失败")

1. **PoC A 实证失败**:`sync_schema.py` 修完后 import 还有更深问题(比如 `MetaIndex` 等模型也缺失) → 表明 `schema_generator` 模块需整体重写,工作量翻 3 倍 → **回归到选项 C(只做 L1+L2 文件对账,放弃 schema drift)**
2. **PoC B 暴露太多 false positive**:yaml `through` 字段虽然语法有效,但实际项目中通过 `staging/init_and_seed` 动态建表,引用图识别不到 → **ref_graph 必须依赖 init_and_seed 后的真实 DB schema,而非 yaml**
3. **PoC C 跑出 100+ 个 drift**:所有都是历史遗留 → 说明"对账"概念本身有问题,需要重新定义 baseline(选择某个 commit 作为 schema 真相起点)

#### 修正 v3.0 原"95% 一致率"标准

V3.0 文档 §4.2 原"PoC 失败标准:95% 一致率"**过于严苛且定义不清**。修正为:

> **"实证标准"**:第一次跑出的 drift 报告中,**真实业务 drift 必须 < 5 个**;剩余 drift 都可解释为"init_and_seed 动态建表"或"历史 baseline 偏差"。
>
> **不追求 100% 一致,追求"可解释"** —— 这是更现实的工程标准。

### 9.5.5 为何这次必须"立即动手"而非"再设计"

#### 元论证:别再画饼了

回顾 v1.0 → v1.1 → v2.0 → v3.0:
- 4 个版本,1 周
- 文档总长从 80 行扩到 ~430 行
- 但**实际代码改动:0 行**

这是"研究过拟合"的典型症状:**写得越多,跑得越少**。

#### 原则修正

**之前的隐含假设**:"规范要先写清楚,再动手"。**这是错的**。
- sync_schema.py 就是这个假设的反例:规范从来没人写,但代码 baseline 进了仓库就闲置
- 真正可执行的路径是:**"先让一个 PoC 跑起来,跑的过程会发现所有规范里没写清的问题"**

#### 选项 B 的本质修正

**原方案**:"PoC 先行" = 先写 PoC 计划,再实施
**修正后**:"PoC 实证" = **第一个动作就是修 sync_schema.py import + 跑一次 diff**(30 分钟),跑出来的输出本身就是 PoC 的产出

**这是研究-工程一体化的核心修正 —— 把研究产物直接当成 PoC 输入,跑通即闭环**。

### 9.5.6 立即可执行的下一步(0.5 小时内)

如果团队认可上述分析,**下一动作序列**应该是:

```bash
# Step 1 (10 min): 修 import
# 编辑 D:\filework\excel-to-diagram\meta\tools\sync_schema.py 第 20 行
# 从: from meta import registry, list_meta_objects, get_meta_object
# 到:   from meta import get_meta_object
# (然后在文件里找 list_meta_objects 的来源,可能是 meta.core.registry 或类似)

# Step 2 (5 min): 试跑
cd d:\filework\excel-to-diagram
python -m meta.tools.sync_schema --diff

# Step 3 (20 min): 把输出结果录入
# 写入 docs/research/poc-a-evidence.md,记录:
#   - 命令实际输出
#   - .schema_version.json 大小
#   - 是否能真实反映 yaml 状态
#   - 暴露的任何问题

# Step 4 (15 min): 决策会
# 根据 Step 3 实证结果,决定:
#   A. PoC A 实证成功 → 进入阶段 2(引用图)
#   B. PoC A 实证失败 → 暴露 schema_generator 更深问题,重新评估
```

**总投入 0.5 小时**,但获得的产出:
- **真实数据**:`.schema_version.json` 文件(可入库)
- **真实判断**:PoC A 是否可行
- **真实推进**:从"研究文档"变成"实证记录"

### 9.5.7 三次研究的收敛对比

| 维度 | v3.0 文档 | 第二次(深度质问) | 第三次(本次) |
|---|---|---|---|
| **核心产出** | 4 个 PoC 路径设计 | 工作量估算 + 成功/失败标准 | **真执行路径 + git 历史实证** |
| **关键发现** | PoC 缺乏识别层 | 缺"识别驱动" vs "规范驱动"区分 | **仓库里 70% 能力已存在但闲置** |
| **对自身批评** | 无 | 缺乏"工具 vs 规范"对比 | **"研究过拟合"自省** |
| **最终建议** | "PoC 先行" | "工作量 2.5 人天" | **"0.5 小时内动手实证 PoC A"** |

### 9.5.8 对 v3.0 全文的修正项汇总

| 位置 | 原内容 | 修正 |
|---|---|---|
| §0.2 D3 | "3 个 PoC(2.5 人天)" | "3 个 PoC(**修正后 1.2-1.7 人天**,详见 §9.5)" |
| §4.2 PoC 候选 | 工作量列 | 新增"原估/修正"两列,加 §9.5 修正注解 |
| §4.3 标题 | "(0.5 人天)" | "(0.2 人天 — 第三次研究修正)" |
| §4.4 标题 | "(1.5 人天)" | "(0.5-1 人天 — 第三次研究修正)" |
| §4.5 标题 | "(0.5 人天)" | "(0.5 人天 — 维持)" |
| §9 选项 B | "2.5 人天跑 3 个 PoC" | "原 2.5 / **修正后 1.2-1.7 人天**,第一动作是修 import + 跑 diff" |

---

## §10 附录

### 10.1 关键文件参考

| 文件 | 用途 |
|---|---|
| `meta/core/schema_introspector.py` | L1 DB 实例化状态识别 |
| `meta/core/schema_generator.py` | L3 差异引擎 + Migrator |
| `meta/tools/sync_schema.py` | CLI + 版本指纹 |
| `meta/schemas/generated_schema.sql` | 当前 schema 输出 |
| `meta/migrations/v089__drop_legacy_user_group_and_role_tables.py` | v089 反模式案例 |
| `meta/core/association_engine.py:1386` | v089 prod 报错精确行 |
| `meta/core/migration_runner.py` | migration runner + lock + checksum |

### 10.2 关键术语表

| 术语 | 定义 |
|---|---|
| **Schema-as-Code** | schema 期望状态用声明式表达 |
| **Expand-Contract** | 破坏性变更拆 3-5 阶段 |
| **Branch By Abstraction** | 应用层 Expand-Contract 模式 |
| **Schema Contract** | 应用声明 schema 依赖 |
| **Policy-as-Code** | 治理规则声明式 |
| **Bounded Context** | 限界上下文(业务边界) |
| **Aggregate Root** | 聚合根(业务不变量边界) |
| **Schema Drift** | DB 实际状态与期望状态不一致 |
| **Migration Replay** | 空 DB 跑全 migration 链 |
| **Repeatable Migration** | Flyway 派生对象管理模式 |

### 10.3 版本历史

| 版本 | 日期 | 主要变更 |
|---|---|---|
| v1.0 | 2026-09-18 | 5 个原语 + 5 步骤(过度抽象,已废)|
| v1.1 | 2026-09-18 | 订正 v1.0 错误哲学 + 8 补(战术修补) |
| v2.0 | 2026-09-18 | 60:20:10 + 11 子原语(范式转移)|
| **v3.0** | **2026-09-18** | **三大支柱 + 识别系统 + PoC 路径(整体方案)** |

### 10.4 来源

- Martin Fowler: Evolutionary Database Design (2016)
- Flyway 文档: undo migrations 反思
- [Skeema (GitHub 在用)](https://github.com/skeema/skeema)
- [Atlas (Ariga)](https://atlasgo.io/atlas-schema/sqlite)
- [Prisma introspection](https://www.prisma.io/docs/orm/prisma-schema/introspection)
- [Pgroll (Supabase)](https://github.com/supabase/pgroll)
- 我们项目 v001-v089 历史 migration

---

## §11 Migration 执行模式库(第五次研究,v3.2 新增)

> **承接**:第四次研究(MDL 8 阶段)解决"如何设计",本节解决"如何执行"。
> **关键命题**:给定设计好的 migration 文件,**执行策略**(EP1-EP8)的适用场景和代价。

### 11.1 为什么"执行模式"和"设计模式"是两件事

| 维度 | 第四次研究:设计模式 | 第五次研究:执行模式 |
|---|---|---|
| 关心什么 | migration 文件长什么样 | migration 文件怎么 apply 到 prod DB |
| 输出 | migration SQL/Python 代码 | **执行策略**(单条 vs 拆分 vs 异步) |
| 失败代价 | 代码写错 → review 时返工 | 锁表 30 分钟 → **整个 prod 不可用** |
| 业内代表 | Expand-Contract / Branch By Abstraction | Online DDL / Backfill 分批 / 灰度 |

### 11.2 EP 库总览(8 个执行模式)

#### EP1:瞬时 DDL(Synchronous DDL)

**定义**:同步执行 DDL,接受短暂锁表。

**适用**:
- 小表(< 10 万行)
- 业务低峰期
- 风险可控的变更(`ADD COLUMN NULL` / `ADD INDEX`)

**风险**:大表**分钟级锁表**,主从延迟雪崩。

**决策规则**:
```
if (table_rows < 100k) AND (变更类型 ∈ {ADD COLUMN NULL, ADD INDEX}) AND (低峰期):
    → EP1 (瞬时)
else:
    → 评估 EP2-EP8
```

#### EP2:Online DDL(原生)— MySQL 5.6+ / PostgreSQL 11+

**定义**:使用 DB 原生 Online DDL,内部实现"先复制 → 后切换"。

**MySQL**:`ALTER TABLE ... ALGORITHM=INPLACE, LOCK=NONE`
**PostgreSQL**:`ALTER TABLE ... CONCURRENTLY`(限于索引)

**适用**:大表 `ADD COLUMN` / `ADD INDEX`,业务高峰期可接受轻微性能影响。

**我们的现状**:**SQLite 不支持**。

#### EP3:Concurrent Index(并发索引)

**定义**:创建索引不锁表(仅阻塞写入,不阻塞读取)。

**MySQL**:部分版本原生支持。
**PostgreSQL**:`CREATE INDEX CONCURRENTLY` —— 业内金标准。
**SQLite**:**不支持**。

#### EP4:影子表 + 双写(Shadow Table + Dual Write)

**定义**:创**新表(影子表)** → 应用层**双写**新旧表 → 后台**数据迁移** → 切读 → 删旧表。

**业内代表**:
- Facebook OnlineSchemaChange(2010)
- GitHub gh-ost(2016)
- Shopify pt-online-schema-change

**适用**:大表 `ALTER COLUMN TYPE` / `DROP COLUMN` / 重命名

**代价**:双倍存储(临时) + 双写应用层代码改造 + 数据迁移耗时。

#### EP5:分批提交(Batched Backfill)

**定义**:Backfill 大批量数据时,**分批**(每次 1 万行) + **间歇**(每批间 sleep)**提交**。

**适用**:`UPDATE WHERE` 大批量回填,批量数据迁移。

**关键参数**:
- `batch_size = 10000`(业内经验值)
- `sleep_ms = 100`(让其他 DML 能进来)
- **必须有"已迁移到哪"的进度持久化**

#### EP6:Backfill Async(异步后台任务)

**定义**:把 Backfill 放到**应用层后台任务**,不阻塞 migration。

**优势**:migration 阶段只做"加列"(快),backfill 在生产环境**慢慢跑**。

**适用**:数据规模大,bashfill 可能**小时级**,业务可接受"新老数据暂时不一致"。

#### EP7:Feature Flag + 应用层分支

**定义**:**用 Feature Flag 控制**新代码路径的开启/关闭,migration 与应用层解耦。

**业内代表**:Stripe / GitHub 批量回填

**优势**:migration 失败 → 关 flag 即可,**无需回退 DB**。

**适用**:复杂迁移(类型变更 + 应用层同步),长期演进(90 天 deprecate 周期)。

#### EP8:gh-ost / pt-osc(影子表工具)

**定义**:用外部工具实现 EP4,**自动管理影子表 + 双写 + 切读**。

**优势**:**应用层零修改**(工具接管),可暂停 / 可恢复(binlog 位置记录)。

**限制**:**MySQL only**,需要 binlog row 模式。

### 11.3 决策框架:何时用哪个 EP?

#### 11.3.1 决策树

```
Step 1: 变更类型是什么?
│
├── ADD COLUMN NULL → EP1 (瞬时)
├── ADD COLUMN NOT NULL 无 DEFAULT → EP5 (分批 backfill) 或 EP6 (异步)
├── ADD INDEX                    → EP3 (Concurrent Index) [PG/MySQL] 或 EP1 [SQLite]
├── MODIFY COLUMN TYPE           → EP4 (影子表) 或 EP7 (Feature Flag)
├── DROP COLUMN                  → EP4 (影子表 - 谨慎) 或 90 天 deprecate 后 EP1
├── RENAME COLUMN                → EP7 (Feature Flag) 或 双写 EP4
└── DROP TABLE                   → EP1 (瞬时) + 30 天 deprecate 检查

Step 2: 表大小?
│
├── < 10万行    → EP1 (默认)
├── 10万 - 100万 → 评估 Step 3
└── > 100万     → EP4-EP8(必须)

Step 3: DB 引擎?
│
├── SQLite      → 几乎只能用 EP1/EP5 (无 Online DDL)
├── MySQL 5.6+  → EP2 / EP3 / EP4 / EP8 都支持
└── PostgreSQL 11+ → EP2 / EP3 都支持, EP4 / EP8 需外部工具

Step 4: 是否允许应用层改造?
│
├── 是           → EP4 / EP6 / EP7 都可以
└── 否           → EP8 (gh-ost) 优先
```

#### 11.3.2 决策矩阵(速查表)

| 变更类型 | 小表(< 10万) | 中表(10万-100万) | 大表(> 100万) |
|---|---|---|---|
| ADD COLUMN NULL | EP1 | EP1 | EP2/EP5 |
| ADD COLUMN NOT NULL | EP1+EP5 | EP5 | EP5+EP6 |
| ADD INDEX | EP1 | EP3 | EP3 |
| MODIFY TYPE | EP1+EP7 | EP7 | EP4/EP7/EP8 |
| DROP COLUMN | EP1(慎) | EP4 | EP4(90天) |
| RENAME COLUMN | EP7 | EP7 | EP7 |
| DROP TABLE | EP1+审计 | EP1+审计 | EP1+审计 |

### 11.4 对我们项目的具体含义

#### 11.4.1 现状盘点

- **DB 引擎**:SQLite(`meta/architecture.db`,109 MB)
- **SQLite 不支持**:EP2(Online DDL) / EP3(Concurrent Index) / EP4(影子表) / EP8(gh-ost)
- **SQLite 部分支持**:EP5(分批) / EP6(应用层异步) / EP7(Feature Flag)
- **当前主用**:EP1(瞬时)

#### 11.4.2 我们的"现实选择集"

| EP | 是否可用 | 备注 |
|---|---|---|
| EP1 瞬时 DDL | ✅ 主用 | SQLite 文件锁,小表秒级,大表分钟级 |
| EP5 分批提交 | ✅ 可用 | Python 层 for-loop + commit + sleep |
| EP6 Backfill Async | ✅ 可用 | 已有 `ai_async_task` 对象可复用 |
| EP7 Feature Flag | ✅ 可用 | 通过 yaml 的 `enabled` 字段 + 代码分支 |
| EP2/EP3/EP4/EP8 | ❌ 不可用 | SQLite 限制 |

#### 11.4.3 SQLite 特定的"Online DDL 替代方案"

| 场景 | 替代方案 |
|---|---|
| 大表 ALTER | **关闭服务 → 离线 ALTER → 重启** |
| 大表 ADD INDEX | **关闭服务 → 离线加索引 → 重启**(SQLite 索引维护慢) |
| 数据迁移 | EP5 分批 + EP6 异步 |
| 紧急回退 | **保留 DB 文件 backup,失败可回滚** |

#### 11.4.4 未来切引擎的迁移路径

> **当我们从 SQLite 切到 PostgreSQL/MySQL 时**(无论是 v200 还是更早),EP 库会"激活":

| 当前 SQLite 限制 | 切到 PG/MySQL 后可获得 |
|---|---|
| 无 Online DDL | EP2(原生) |
| 无 Concurrent Index | EP3(`CREATE INDEX CONCURRENTLY`) |
| 无影子表 | EP4(双写) / EP8(gh-ost) |

**关键**:**EP7(Feature Flag)和 EP6(异步)与引擎无关,先实施可平滑迁移**。

### 11.5 对 v3.2 子原语的补充

#### 11.5.1 C6(Execution Pattern 必选)

| 项 | 内容 |
|---|---|
| 必填字段 | `execution_pattern: EP1-EP8` |
| 决策依据 | §11.3 决策树(变更类型 × 表大小 × DB 引擎 × 应用层改造) |
| 验证工具 | D4 审查阶段 `meta/tools/migration_lint.py` 机读校验 |
| 不通过的后果 | **阻断 PR merge** |
| 成本 | ~0.3 人天 |

#### 11.5.2 C7(Rollback Path 必填)

| 策略 | 说明 | 当前项目使用 |
|---|---|---|
| A 自动 undo | 仅适合纯 schema 变更,**数据变更不可逆** | ❌ |
| B 新 migration 修补 | 业内**主流推荐**(Flyway 官方) | ✅ **默认**(v089 即 B) |
| C DB 快照 + 还原 | 大改动需停机 | ❌ |

### 11.6 可立即落地的工作(优先级)

| 优先级 | 工作 | 产出 | 工作量 |
|---|---|---|---|
| P0 | 把 EP1-EP8 + 决策树写入本文档 | 模式库单一真相源 | ✅ 本次完成 |
| P1 | `meta/tools/migration_lint.py` 静态校验 | PoC E | 0.3 人天 |
| P2 | 把 EP 决策集成到 `migration_runner.py` | 钩子函数 | 0.3 人天 |
| P3 | 真实 case demo(v089 重新设计) | 案例文档 | 1-2 人天 |
| 未来 | 切到 PG/MySQL 激活 EP2/EP3/EP8 | 与现有系统集成 | 3-5 人天 |

### 11.7 一句话总结

> **"识别"完成后,真正决定 prod 稳定的是"执行模式"。业内 8 个 EP(EP1-EP8)覆盖从瞬时到影子表的全光谱;我们当前在 SQLite 受限,但 EP7(Feature Flag) / EP6(异步) / EP5(分批) 仍然可用;v3.0 子原语 C1-C5 应升级到 C1-C7,新增 C6(执行模式必选)+ C7(回退路径必填)。"**

---

## §12 一句话(总)

> **"v3.2 把'演化能力'从'migration 规范'重新定义为'业务架构 + 部署 + schema 三支柱'(权重 60:20:10)。识别层 100% 闭环(L1-L4 yaml 部分 + PoC A/B/C 已实证);执行层新增 C6(执行模式必选)+ C7(回退路径必填),通过 PoC E(migration lint)落地。schema 规范从 3 条升级到 7 条,业务架构 review 仍为最高优先级。失败也是学习。"**

---

**版本**: v3.2 (v3.0 + 第四次研究 + 第五次研究)
**生效日期**: 2026-09-25(预留 1 周共识期)
**下次 review 触发**: PoC A/B/C/E 任一失败 / 切引擎到 PG/MySQL / v100+
**下次 review**: 2027-03-18
**核心反馈渠道**: team + AI Agent