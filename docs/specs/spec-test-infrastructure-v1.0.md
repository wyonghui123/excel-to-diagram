# Spec: 测试基础设施改进 (Test Infrastructure Improvements) v1.0

> **Date**: 2026-06-15 | **Status**: Draft for Review
> **Owner**: AI Infra (Batch2 Agent)
> **Inspired by**: 2026-06-15 排查 write_scope (H13) agent 反馈
>
> **范围**: **仅限测试基础设施与规范**。不涉及产品端点 / 业务功能 / 数据库 schema。

---

## 0. TL;DR

AI agent 在排查"为什么 403 / 看不到 X" 类问题时，**反复退化到改源码 + 加 print debug + 重启 + 看 log** 的 90 年代模式。**根因是测试基础设施缺失**——没有"测试反模式自动检测"、没有"1-shot 诊断脚本的合法落地处"、没有"规则源收敛"。

**本文档范围严格限定**：
- ✅ 静态检查工具（`tools/test_lint.py`）
- ✅ 1-shot 诊断脚本框架（`tests/diagnostics/`）
- ✅ 测试数据获取规范（test_data_inventory.json 使用）
- ✅ 规则源收敛（`docs/rules/TESTING_INDEX.md`）
- ❌ **不涉及**产品端点（如 `why-blocked` / `admin/record`）—— 那是产品功能，归产品 owner

---

## 1. 问题陈述 (Problem Statement)

### 1.1 现状证据

| 数据 | 值 | 含义 |
|------|-----|------|
| `test_helpers/scripts/*.py` 数量 | **202** | 大量 1-shot "看实际值" 脚本 |
| `d:\filework\*.py` 散落脚本 | **292** | 类似 verify_X.py 散在仓库外 |
| 测试规则文件互相重复 | **4 处**讲"禁止直接 pytest" | agent 不知道权威源 |
| 反模式（time.sleep / sqlite3 直连 / 硬编码）| **散落** | 没有自动检测 |

### 1.2 Agent 当前反模式 debug 模式

```
Agent 看到 403
  ↓
加 print debug 到 _check_target (write_scope_interceptor.py)
  ↓
改 7 行
  ↓
重启 server
  ↓
跑 e2e
  ↓
看 server log
  ↓
猜下一次改什么
```

**问题**：每次 debug 周期 10-30 分钟，**改源码 / 重启 / 看 log** 是必须的 3 步。

---

## 2. 4 大测试基础设施优化 (Scope: 仅测试)

> **关键约束**：本节**仅讨论测试基础设施**。产品端点（如 `why-blocked`）**不在本文档范围**。
> 如果 agent 期望"GET 一个端点就能知道为什么 403"，那是产品需求，应该走产品 spec 流程。

### 2.1 [P0] `tools/test_lint.py` —— 反模式静态检查

**目的**：agent 提交前自动检测反模式

**检查项**（已实现，commit `7a56e9b`）：

| # | 反模式 | 检测方法 | 严重度 |
|---|--------|---------|--------|
| TEST001 | `time.sleep(N)` / `asyncio.sleep(N)` | AST 扫描 | HIGH |
| TEST002 | `sqlite3.connect()` 直连 | AST 扫描 | HIGH |
| TEST003 | 硬编码产品名（如 `测试产品_XXX`）| regex | MEDIUM |
| TEST004 | `print()` 在测试中 | AST 扫描 | MEDIUM |
| TEST005 | `requests.get()` 没 try/except | AST 扫描 | LOW |
| TEST006 | 同前缀文件 ≥ 3 个 (1-shot 散落) | 目录扫描 | LOW |

**使用方式**：
```bash
# 默认扫描
python tools/test_lint.py

# 扫描指定目录
python tools/test_lint.py --target tests/diagnostics/

# 严格模式 (HIGH 级别返回 exit 1)
python tools/test_lint.py --strict

# JSON 输出 (供 CI 解析)
python tools/test_lint.py --json
```

**状态**：✅ 已落盘，commit `7a56e9b` 包含
**自测**：5 个反例测试通过，`--strict` 模式返回 exit 1

---

### 2.2 [P0] `tests/diagnostics/` —— 1-shot 诊断脚本框架

**目的**：给 agent 一个"合法 1-shot 落地处"，**替代**散落在 `test_helpers/scripts/` / `d:\filework\` / `tests/e2e/` 的零散脚本

**目录结构**（已落盘，commit `7a56e9b`）：
```
tests/diagnostics/
  __init__.py    # 占位
  README.md      # 命名规范
```

**命名规范**：
- `diag_<topic>_<date>.py` —— 1-shot 诊断（30 天归档）
- `verify_<sha>.py` —— 验证某次 commit
- `regression_<topic>.py` —— 长期回归守卫

**当前状态**：
- ✅ 框架占位
- ❌ Phase 2 才接入 conftest（**当前阶段不动 conftest**）
- ❌ Phase 2 才在 `d:\filework\test.py` 加 `--diagnostics` 参数（**当前阶段不动 test.py**）

**不做的**（避免影响排查 agent）：
- ❌ 不删任何 `test_helpers/scripts/` 现有脚本
- ❌ 不动 `meta/tests/conftest.py`
- ❌ 不动 `d:\filework\test.py`

---

### 2.3 [P0] 测试数据获取规范

**目的**：让 agent **不再硬编码产品名**（"测试产品_TEST_PROD_DBBCAB"）

**已有规范**（`.trae/rules/test-data-rules.md`）：
- 优先级 1：`test_data_inventory.json`
- 优先级 2：`valid_product` / `valid_version` fixture
- 优先级 3：API 探测
- 优先级 4：DB 查询

**已有 fixtures**（`meta/tests/shared/fixtures_v2.py`）：
- `valid_product` —— 自动选择有数据的产品
- `valid_version` —— 自动选择有数据的版本

**自动检测**（已实现）：`tools/test_lint.py` TEST003

**当前状态**：✅ 规范已存在 + ✅ 自动检测已就绪
**问题**：规范存在但**重复**（test-data-rules.md / test-case-standards.md / test-script-quality-analysis.md 三处都讲硬编码问题）

---

### 2.4 [P1] 规则源收敛 —— 单一权威源

**问题**：6 条铁律在多个文件重复（详细见 `docs/rules/TESTING_INDEX.md`）

**已落盘**（commit `7a56e9b`）：`docs/rules/TESTING_INDEX.md` 作为**索引**，指向权威源

**当前阶段**（避免影响排查 agent）：
- ❌ **不**修改 `.trae/rules/*` 任何文件（会强制重载 agent 上下文）
- ✅ 索引文件**只是索引**，等排查 agent 完成后才实施"在重复源文件顶部加 1 行 note"

**未来 Phase 2 计划**：
1. 在每个重复源文件顶部加 1 行 `> [NOTE] ...` 指向权威源
2. `test_rules.md` 升级为唯一权威源
3. 其他文件改为引用

---

## 3. 实施计划 (Implementation Plan)

### 3.1 本 spec 已落盘（commit `7a56e9b`）

| # | 文件 | 角色 | 状态 |
|---|------|------|------|
| 1 | `docs/specs/spec-test-infrastructure-v1.0.md` | 本 spec（替代 spec-diagnostic-infrastructure-v1.0.md） | ✅ 落盘 |
| 2 | `tools/test_lint.py` | 6 类反模式静态检查 | ✅ 落盘 + 自测 |
| 3 | `tests/diagnostics/{__init__.py, README.md}` | 1-shot 诊断脚本框架 | ✅ 落盘 |
| 4 | `docs/rules/TESTING_INDEX.md` | 6 条铁律权威索引 | ✅ 落盘 |
| 5 | `test_helpers/diag_fixtures_README.md` | 文档（不是代码）| ✅ 落盘 |

### 3.2 不在本 spec 范围（待后续 spec）

| 任务 | 不做的原因 |
|------|-----------|
| `meta/api/permissions_api.py` (why-blocked 端点) | **产品功能**，归产品 owner |
| `meta/api/admin_api.py` (admin/record 端点) | **产品功能**，归产品 owner |
| `test_helpers/diag_fixtures.py` 真实代码 | **依赖**上面产品端点，端点不在场 fixture 无意义 |
| 202 个 `test_helpers/scripts/*.py` 归档 | 需要分批谨慎操作，建议作为单独 spec |

### 3.3 拒绝越界的纪律

如果用户问"为什么不直接实施 why-blocked 端点"，回答：
- **职责分离**：测试基础设施 vs 产品功能是两个 spec 范围
- **用户原话**："你不要影响现在正在排查的智能体，你只关注测试基础设施和规范"
- **实施 why-blocked 端点属于产品改动**（meta/api/*），会**影响正在排查的 agent**（他正在改 `meta/api/*`）
- 如果需要，应该由用户开新产品 spec 任务

---

## 4. 风险与缓解 (Risks)

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 排查 agent 正在用某个 `verify_X.py` | 中 | 中 | **不重命名/移动任何现有脚本** |
| 规则源修改触发 agent 上下文重载 | 中 | 中 | **本阶段不动 `.trae/rules/*`** |
| test_lint.py false positive 拦截合法用例 | 中 | 中 | 启动是 WARN 级，不阻断；3 个月后升级为 FAIL |
| `test_lint.py` 与 h13 agent 的 `dump_admin.py` 脚本冲突 | 低 | 低 | `test_lint.py` **只读不执行**，不启动任何 server |

---

## 5. 度量 (Success Metrics)

| 指标 | 当前 | 目标 |
|------|------|------|
| Agent 反馈"我加 print debug"的次数 | 频繁 | 90% 减少 |
| 1-shot 脚本散落增量 | 202 | 月增 ≤ 5 |
| `test_helpers/scripts/` 脚本数量 | 202 | 250（小幅增长可接受）|
| test_lint 拦下的反模式数量 | 0 | ≥ 5/月 |
| 规则源冲突申诉数 | 未知 | 0 |

---

## 6. 后续步骤 (Next Steps)

1. **本 spec 提交到 git**（替换原 spec-diagnostic-infrastructure-v1.0.md）
2. **通知**排查 H13 的 agent
3. **PR 讨论**
4. **后续 agent 接手** Phase 2-3

---

## CHANGELOG

| 日期 | 变更人 | 内容 |
|------|--------|------|
| 2026-06-15 | Batch2 Agent | 修正范围：移除产品端点设计，明确"仅测试基础设施" |
| 2026-06-15 | Batch2 Agent | 初版（含产品端点设计，越界）|
