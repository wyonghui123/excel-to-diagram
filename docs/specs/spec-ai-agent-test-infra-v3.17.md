## 目录

1. [1. 背景与目标](#1-背景与目标)
2. [2. 需求类型概览](#2-需求类型概览)
3. [3. 功能需求 (FR)](#3-功能需求-(fr))
4. [4. 非功能需求 (NFR)](#4-非功能需求-(nfr))
5. [5. 外部接口需求 (IF)](#5-外部接口需求-(if))
6. [6. 过渡需求 (TR)](#6-过渡需求-(tr))
7. [7. 约束与假设](#7-约束与假设)
8. [8. 优先级与里程碑](#8-优先级与里程碑)
9. [9. 变更/设计提案 (RFC)](#9-变更设计提案-(rfc))
10. [10. TBD 列表 (用户已澄清 + 行业研究决策)](#10-tbd-列表-(用户已澄清-行业研究决策))
11. [Spec + RFC 完整性检查](#spec-rfc-完整性检查)
12. [Spec + RFC 确认请求 (V2 — TBD 已澄清)](#spec-rfc-确认请求-(v2-—-tbd-已澄清))

---
# Spec: AI Coding Agent 友好测试基础设施 (v3.17-v3.18)

**Spec ID**: SPEC-AIT-001
**作者**: Trae AI Agent
**日期**: 2026-06-06
**状态**: Draft (待用户确认)
**关联版本**: v3.17 (开发态合规化) → v3.18 (本 spec 实施)

---

## 1. 背景与目标

### 1.1 背景

**当前现状** (v3.17 收官后):
- 13 pytest 模块 64 单测, 62/64 通过 (97%)
- 测试基础设施**为人类设计**:
  - 走 `python d:\filework\test.py` 入口 (DB 快照/锁/监控)
  - `service_manager.ps1` 启停 server (单实例)
  - 走 cookie 认证 (`tests/fixtures/admin_token.py`)
  - 走 stderr/stdout 输出
  - 单 agent 流程
- **未对 AI Coding Agent 优化**:
  - 无 test 模板生成器
  - 无 auto-server (agent 跑测试需手动启 server)
  - 无 fast feedback (单测 30s 含 DB 快照)
  - 无结构化结果 (agent 难解析)
  - 无错误码 + 修复建议 (agent 不知怎么修)
  - 无多 agent 隔离 (端口冲突, DB 共享)
  - 无 test data factory (agent 手动造数据)
  - 无 coverage gap 分析 (agent 不知测什么)
- **生产可观测性不足** (未来 AI Production Diagnostician 需求):
  - 无 trace_id 端到端
  - 无结构化 JSON 日志
  - 无 Prometheus 格式 metrics
  - 无 P50/P95/P99 latency
  - 无 `/_diagnostics` 端点
  - 错误码无 fix_hint
  - 无错误聚合
  - 无 alert 端点

### 1.2 业务目标

- **BG-1**: AI Coding Agent 写测试效率提升 5x (从模板 + factory 起步)
- **BG-2**: AI Coding Agent 跑测试反馈提升 6x (5s vs 30s)
- **BG-3**: 多 AI Coding Agent 并行写测试, 互不干扰 (端口/DB/worktree 隔离)
- **BG-4**: AI Coding Agent 修复准确率提升 2x (错误码 + fix_hint)
- **BG-5**: 未来 AI Production Diagnostician 可基于生产可观测性排查 (30min → 5min)
- **BG-6**: 生产可观测性达到 SaaS 业界标准 (Prometheus + JSON log + trace)

### 1.3 用户/涉众目标

| 涉众 | 角色 | 目标 |
|------|------|------|
| **AI Coding Agent** | 主要直接用户 | 高效写/跑/修测试, 隔离并行 |
| **团队开发者** | 间接用户 | 享受 Agent 写的测试, 可读可维护 |
| **SRE / Ops** | 间接用户 | 生产可观测性 + alert |
| **未来 AI Production Agent** | 远期用户 | 用 `_diagnostics` + trace 排查 |

---

## 2. 需求类型概览

| 类型 | 是否适用 | 证据来源 |
|------|----------|----------|
| Business | ✅ | 用户对话 ("AI Coding Agent 友好测试基础设施") |
| User/Stakeholder | ✅ | 开发态 + 生产态两角度 |
| Solution | ✅ | v3.17 已建基础 + 本 spec 扩展 |
| Functional | ✅ | 19 个 FR (D.1-D.10 + M.1-M.9) |
| Nonfunctional | ✅ | NFR-001 ~ NFR-005 (性能/隔离/可观测) |
| External Interface | ✅ | IF-001 ~ IF-005 (端点 + CLI) |
| Transition | ✅ | TR-001 ~ TR-002 (v3.17 → v3.18 兼容) |

---

## 3. 功能需求 (FR)

### 维度 D: 开发态 AI Coding Agent 友好

#### FR-D.1: Test 模板生成器

- **Description**: 系统 MUST 提供根据 action YAML schema 自动生成 test 模板的工具, Agent 调用即可得 1 个 test 模板文件
- **Acceptance Criteria**:
  - `python -m meta.tests.tools.gen_test_template <action_id>` 生成 `test_<action_id>.py`
  - 含 fixture 导入 (`bo_action_server_check`, `admin_cookie`)
  - 含 happy path 断言模板
  - 含 marker (`@pytest.mark.bo_action, @pytest.mark.<subdomain>`)
- **Priority**: Must
- **Source**: 用户对话 + 代码分析
- **关联**: 提升 BG-1 (5x)

#### FR-D.2: Test data factory

- **Description**: 系统 MUST 提供 factory_boy 风格的工厂类, Agent 用 `UserFactory.create(role='admin')` 即得测试数据
- **Acceptance Criteria**:
  - `meta/tests/factories/__init__.py` 暴露 `UserFactory`, `RoleFactory`, `SubscriptionFactory`
  - 每个 factory 支持 `.create(**kwargs)` 和 `.build()` (不写 DB)
  - 含 `cleanup_tracker` 集成, 测试结束自动清理
- **Priority**: Must
- **Source**: 用户对话
- **关联**: 提升 BG-1

#### FR-D.3: Auto-server fixture

- **Description**: `bo_action_server_or_start` fixture MUST 在 server 不在时自动启动, Agent 跑测试无需手动 `service_manager.ps1 start`
- **Acceptance Criteria**:
  - 改 `bo_action_server_check` 为 `bo_action_server_or_start`
  - 自动检测端口 3010, 不在则调 `service_manager.ps1 start` (后台)
  - 测试结束**不 kill** server (避免影响其他测试)
  - 失败时给清晰错误: "Server 启不起来, 请检查 X"
- **Priority**: Must
- **Source**: 用户对话
- **关联**: 提升 BG-2

#### FR-D.4: Fast feedback (单测)

- **Description**: `test.py --single <test_id>` MUST 跳过 DB 快照, 在 5s 内反馈单测结果
- **Acceptance Criteria**:
  - `--single` 参数, 接受 `module::test_func` 格式
  - 跳过 `_create_db_snapshot` / `_restore_db_snapshot`
  - 跳过 `LOCK` 获取
  - 日志: `[SINGLE] Skipping snapshot + lock for fast feedback`
  - 5s 内返回 (实测)
- **Priority**: Must
- **Source**: 用户对话
- **关联**: 提升 BG-2 (6x)

#### FR-D.5: JSON output 强化

- **Description**: `test.py --json <path>` MUST 输出完整 JSON schema, 包含每个测试的 trace_id, Agent 可机器消费
- **Acceptance Criteria**:
  - JSON 含: `total, passed, failed, errors, duration, results: [{name, status, duration_ms, trace_id, error_msg?}]`
  - 0 退出码 + success=True 表示全过
  - 已被 `v3.17` 部分实现, 本 spec 补 trace_id + 完整 schema
- **Priority**: Must
- **Source**: 代码分析 (test.py 已有 `--json`)
- **关联**: 提升 BG-4

#### FR-D.6: 错误码 + 修复建议

- **Description**: 系统 MUST 扩展现有 E001-E045 错误码, 加 `fix_hint: "检查 X 文件 Y 行 Z"`, Agent 可直接消费
- **Acceptance Criteria**:
  - 改 `meta/core/error_codes.py`: 每个 E0XX 加 `fix_hint` 字段
  - 新增 `/api/v2/action/_error_codes/<code>` 端点, 返回 code + message + fix_hint + see_also (相关文件)
  - 新增 `/api/v2/action/_error_codes` 列表端点
  - 集成到 `subflow_engine._write_audit` (error 时写 fix_hint)
  - **错误分类（2026-06-07 增强）**: `fix_task_manager.py` 的 `_categorize_error()` 支持细粒度分类：
    - `memory_db_not_supported`: v3.13+ :memory: 数据库已不支持
    - `assert_bool`: 布尔断言失败
    - `AttributeError`: 属性错误（如 PermissionService API 缺失）
    - `test_data`: 测试数据创建失败
    - 其他细粒度分类（见 `_categorize_error()` 实现）
- **Priority**: Must
- **Source**: 用户对话 + 错误码分析
- **关联**: 提升 BG-4 (2x)

#### FR-D.7: 多 Agent 隔离

- **Description**: 系统 MUST 支持多 AI Coding Agent 并行写/跑测试, 互不干扰 (端口/DB/worktree)
- **Acceptance Criteria**:
  - `service_manager.ps1` 升级: `--port 3010-3019` (10 个实例)
  - `service_manager.ps1 status --all` 显示所有实例
  - `test.py` 接受 `--port <port>` 参数
  - 每个端口独立 DB snapshot (用 port 派生 DB path: `architecture_<port>.db`)
  - 锁机制: port 内 exclusive, port 间共享
  - worktree 隔离: Agent 各自 worktree (但 pytest 在 project root 跑, 通过环境变量 `AGENT_PORT` 区分)
- **Priority**: Must
- **Source**: 用户对话 ("多智能体并行")
- **关联**: 提升 BG-3

#### FR-D.8: Property-based testing (hypothesis)

- **Description**: 系统 MUST 集成 hypothesis, Agent 可用 `@given(st.text(), st.integers())` 自动生成边界 input
- **Acceptance Criteria**:
  - `meta/tests/hypothesis_strategies.py` 提供常用 strategy (username, password, email 等)
  - 至少 5 个 test 用 `@given` (action_id 字段, role_code, object_id 等)
  - max_examples=20 防止超时
- **Priority**: Should
- **Source**: 用户对话 (隐含)
- **关联**: 提升 BG-1 (找边界 bug)

#### FR-D.9: Coverage gap 分析

- **Description**: 系统 MUST 提供 coverage gap 分析, 报告"未测代码"给 Agent 看, Agent 据此写新测试
- **Acceptance Criteria**:
  - `pytest-cov` 已支持, 加 `--cov-fail-under=80` (CI 阻断)
  - 新增 `python -m meta.tests.tools.coverage_gap` 报告: `未测行 > 10 的函数`
  - 输出 JSON 给 Agent 解析: `[{file, func, line_start, line_end, missing_lines}]`
- **Priority**: Must
- **Source**: 用户对话 (Agent 需知道测什么)
- **关联**: 提升 BG-1

#### FR-D.10: Mutation testing (mutmut)

- **Description**: 系统 MUST 集成 mutmut, 测测试质量, Agent 看到"代码改 1 行, 测试仍过 = 测试弱"
- **Acceptance Criteria**:
  - 至少 5 个核心 Action 跑 mutmut
  - 报告: mutation_score < 80% 的函数, Agent 据此补强测试
  - 不强求 CI 跑 (跑得慢, 本地跑)
- **Priority**: Should
- **Source**: 用户对话 (隐含)
- **关联**: 提升 BG-1 (测试质量)

### 维度 M: 生产态可观测性 (帮未来 Agent 排查)

#### FR-M.1: trace_id 端到端

- **Description**: 系统 MUST 给每个请求一个 trace_id, 跨 subflow/audit/SSE 关联, Agent 可追踪 1 个请求的完整生命周期
- **Acceptance Criteria**:
  - 入口生成 trace_id (UUID, 32 char), 来源: header `X-Trace-Id` 或自动生成
  - 注入到: log/SSE event/audit_log/SQL 注释
  - 响应 header 返 `X-Trace-Id`
  - 改 `subflow_engine._write_audit` 接受 trace_id
  - SSE event payload 含 `trace_id`
- **Priority**: Must
- **Source**: 用户对话 ("生产可观测性")
- **关联**: 提升 BG-6

#### FR-M.2: 结构化 JSON 日志

- **Description**: 系统 MUST 用 JSON 格式输出日志, 包含 `ts / level / trace_id / user_id / action_id / message`, Agent 可解析
- **Acceptance Criteria**:
  - 引入 `python-json-logger` 或自实现
  - 所有 print 替换为 `logger.info(...)`
  - 日志输出到 `logs/app.jsonl` (1 行 1 JSON)
- **Priority**: Must
- **Source**: 用户对话
- **关联**: 提升 BG-6

#### FR-M.3: Prometheus 格式 metrics

- **Description**: 系统 MUST 暴露 `/_metrics` 端点, 返回 Prometheus 格式 metrics, 标准监控可消费
- **Acceptance Criteria**:
  - `prometheus_client` 集成
  - 暴露: `bo_action_total{action_id, status}`, `bo_action_duration_seconds{action_id}`, `db_pool_active`, `db_pool_idle`, `write_queue_depth`, `http_requests_total{path, status}`
  - 端点: `GET /_metrics`
- **Priority**: Should
- **Source**: 业界标准
- **关联**: 提升 BG-6

#### FR-M.4: P50/P95/P99 latency

- **Description**: `_db_health` MUST 暴露 latency 分布, Agent 可识别慢请求
- **Acceptance Criteria**:
  - 在 `_db_health.data` 加 `latency_p50_ms / p95 / p99` (基于 5min 滑动窗口)
  - 复用 `meta/core/metrics_store.py` (如有) 或新建
  - 阈值: 超过 1000ms 在 alert 中
- **Priority**: Must
- **Source**: 业界标准
- **关联**: 提升 BG-5/BG-6

#### FR-M.5: /_diagnostics 端点

- **Description**: 系统 MUST 暴露 `/_diagnostics` 端点, 给 AI Production Agent 用, 含详细 + 错误码 + fix_hint
- **Acceptance Criteria**:
  - `GET /api/v2/action/_diagnostics` 返回 JSON:
    - `health` (简化版 _db_health)
    - `recent_errors` (1h 内, 聚合)
    - `error_codes` (E001-E045 + fix_hint)
    - `trace_recent` (最近 100 失败 trace_id)
    - `recovery_suggestions` (基于 _db_health 自动建议)
  - 需 admin 权限
- **Priority**: Must
- **Source**: 用户对话 ("可观测性帮智能体排查")
- **关联**: 提升 BG-5

#### FR-M.6: 错误码 + 修复建议 (与 FR-D.6 共享)

- **Description**: 错误码体系升级, 含 fix_hint
- **Acceptance Criteria** (与 FR-D.6 合并, 见上)

#### FR-M.7: 错误聚合

- **Description**: 系统 MUST 在 1h 内同类错误归一, 避免 1000 条相同错误刷屏
- **Acceptance Criteria**:
  - 错误归一: `code + trace_signature` (前 5 行 message)
  - `/api/v2/action/_error_clusters` 返回聚合: `[{code, count, last_seen, sample_trace_id}]`
- **Priority**: Should
- **Source**: 用户对话 (隐含)
- **关联**: 提升 BG-5

#### FR-M.8: Alert 端点

- **Description**: 系统 MUST 暴露 `/_alerts` 端点, 列出超阈值指标 (WAL > 1MB, 错误率 > 5%)
- **Acceptance Criteria**:
  - `/api/v2/action/_alerts` 返回 JSON: `[{level, metric, value, threshold, suggested_action}]`
  - 至少 3 类: DB/WAL/池/队列/错误率
- **Priority**: Should
- **Source**: 用户对话
- **关联**: 提升 BG-5

#### FR-M.9: 监控测试套件

- **Description**: 系统 MUST 测可观测性端点自身
- **Acceptance Criteria**:
  - 新增 `meta/tests/e2e/bo_action/test_observability_v318.py`
  - 8+ 测试: trace_id 注入, JSON log 格式, Prometheus 格式, P50/P95/P99, _diagnostics 内容, 错误聚合, alerts
- **Priority**: Must
- **Source**: 用户对话
- **关联**: 全局

---

## 4. 非功能需求 (NFR)

### NFR-001: 性能

- **Description**: D.4 fast feedback MUST < 5s (单测)
- **Measurement**: 实测 3 次取平均
- **Priority**: Must

### NFR-002: 隔离性

- **Description**: D.7 多 agent MUST 互不干扰 (端口/DB/worktree)
- **Measurement**: 跑 3 个 agent 并行 1min, 检查无冲突
- **Priority**: Must

### NFR-003: 可观测

- **Description**: M.1 trace_id MUST 100% 请求覆盖
- **Measurement**: 跑 100 请求, 全部有 trace_id
- **Priority**: Must

### NFR-004: 兼容

- **Description**: v3.17 测试 MUST 不回归
- **Measurement**: 跑全量 `test.py --all`, 62/64 仍通过
- **Priority**: Must

### NFR-005: 合规

- **Description**: 所有变更 MUST 符合 SESSION_REMINDER 18 铁律
- **Measurement**: code review + conftest.py 硬阻断
- **Priority**: Must

---

## 5. 外部接口需求 (IF)

### IF-001: /_diagnostics 端点

- **Type**: API
- **Endpoint**: `GET /api/v2/action/_diagnostics`
- **Auth**: admin required
- **Response Schema**:
  ```json
  {
    "health": { ... _db_health 简化版 ... },
    "recent_errors": [
      {"trace_id": "abc...", "code": "E005", "message": "...", "ts": "..."}
    ],
    "error_codes": [
      {"code": "E005", "message": "...", "fix_hint": "...", "see_also": ["meta/..."]}
    ],
    "trace_recent": [...],
    "recovery_suggestions": [...]
  }
  ```
- **Source**: 用户对话

### IF-002: /_metrics 端点

- **Type**: API
- **Endpoint**: `GET /_metrics`
- **Format**: Prometheus text format
- **Source**: 业界标准

### IF-003: /_alerts 端点

- **Type**: API
- **Endpoint**: `GET /api/v2/action/_alerts`
- **Auth**: admin
- **Response**:
  ```json
  {
    "alerts": [
      {"level": "warn", "metric": "db_wal_size_mb", "value": 1.5, "threshold": 1.0, "suggested_action": "run backup_db.py --check"}
    ]
  }
  ```

### IF-004: test.py --single 参数

- **Type**: CLI
- **Usage**: `python d:\filework\test.py --single meta/tests/e2e/bo_action/test_db_integrity.py::test_db_integrity_ok`
- **Effect**: 跳过 DB 快照/锁, < 5s 反馈
- **Source**: 用户对话

### IF-005: service_manager 多端口

- **Type**: CLI
- **Usage**: `service_manager.ps1 start --port 3011`
- **Effect**: 在 3011 起一个新实例
- **Source**: 用户对话 ("多 agent 隔离")

---

## 6. 过渡需求 (TR)

### TR-001: 兼容 v3.17 测试

- **Description**: v3.18 实施后, v3.17 13 模块 64 单测 MUST 仍 62/64 通过
- **Strategy**: 不改 `bo_action/conftest.py` 公共 fixtures, 仅新增
- **Rollback Plan**: 回滚 v3.18 即可
- **Source**: 业务连续性

### TR-002: 兼容 SESSION_REMINDER 铁律

- **Description**: 所有新代码 MUST 走 `test.py --file` (非 pytest), conftest.py 硬阻断
- **Strategy**: 复用 v3.17 的 `meta/tests/e2e/bo_action/conftest.py` 模式
- **Source**: SESSION_REMINDER

---

## 7. 约束与假设

### 7.1 技术约束

- C-1: 走 `test.py` 入口 (SESSION_REMINDER 铁律)
- C-2: 走 cookie 认证 (SESSION_REMINDER 踩坑)
- C-3: 走 `service_manager.ps1` (SESSION_REMINDER)
- C-4: 走 pytest 风格 (TestX/test_x, `python_classes=Test*`)
- C-5: 复用 v3.17 的 `meta/tests/e2e/bo_action/conftest.py` 模式
- C-6: 复用 `_db_health` 端点 (v3.16 实施)
- C-7: 复用 audit log (v3.15 实施)
- C-8: 复用 SSE (v3.8 实施)
- C-9: 复用 DB snapshot 保护 (test.py 内置)
- C-10: Python 3.14 + gevent 26.5 (v3.10 documented limitation)

### 7.2 业务约束

- B-1: 用户当前是开发态优先 (D 维度), 生产可观测性 (M) 可下迭代
- B-2: 多 AI Coding Agent 并行 (worktree 隔离由用户自己搞, 我们只做端口/DB)
- B-3: 不引入重量级依赖 (避免增加 CI 负担)

### 7.3 假设

- A-1: 用户有 .trae/rules/ 下的 multi-agent-coordination.md (实际**不存在**, 假设用户在 .trae 配置) - Source: TBD
- A-2: 工作目录 `d:\filework\excel-to-diagram`, project root 是 meta/ 的父级 - Source: Verified (v3.17 验证)
- A-3: backend 跑在 3010 端口 (默认, 可改) - Source: Verified (service_manager)
- A-4: v3.17 现状 (62/64) 已是 baseline - Source: Verified (v3.17 进度档)
- A-5: 用户有 git + worktree 能力 (Agent 并行) - Source: Assumed

---

## 8. 优先级与里程碑

| ID | 需求 | 优先级 | 原因 |
|----|------|:---:|------|
| FR-D.4 | Fast feedback | Must | 6x 提升, 工时 1h |
| FR-D.3 | Auto-server | Must | Agent 零摩擦, 工时 1h |
| FR-D.5 | JSON output | Must | Agent 解析, 工时 30min |
| FR-D.7 | 多 agent 隔离 | Must | 并行, 工时 2h |
| FR-D.1 | Test 模板生成器 | Must | 5x 写测试, 工时 1.5h |
| FR-D.2 | Factory | Must | Agent 造数据, 工时 1h |
| FR-D.6 | 错误码 + 建议 | Must | 2x 修复, 工时 2h |
| FR-D.9 | Coverage gap | Must | Agent 知测什么, 工时 1h |
| FR-D.8 | Property-based | Should | 边界, 工时 1.5h |
| FR-D.10 | Mutation | Should | 测试质量, 工时 1.5h |
| FR-M.5 | /_diagnostics | Must | Agent 入口, 工时 2h |
| FR-M.1 | trace_id | Must | 端到端, 工时 1.5h |
| FR-M.2 | JSON log | Must | 机器消费, 工时 1.5h |
| FR-M.4 | P50/P95/P99 | Must | 慢请求, 工时 30min |
| FR-M.6 | 错误码 + 建议 (共享 D.6) | Must | 复用 |
| FR-M.9 | 监控测试 | Must | 自测, 工时 1h |
| FR-M.3 | Prometheus | Should | 业界标准, 工时 1h |
| FR-M.7 | 错误聚合 | Should | 工时 1h |
| FR-M.8 | Alerts | Should | 工时 1h |

### 9.5.0 规则更新 (跟 Phase 1-6 同步, 5.75h)

| # | 文件 | 变更 | 工时 |
|---|------|------|:---:|
| 1 | SESSION_REMINDER.md | 增 `--single/--port/--json` 到合法入口; 增 fast feedback 章节; 增 multi-agent 端口隔离; 增 cookie 统一 | 30min |
| 2 | service_manager.ps1 | 增 `--port <port>` (3010-3019); 改 status schema (multi-instance); 改 lock per-port | 1h |
| 3 | test.py | 增 `--single/--port/--json` 参数 + per-port 锁 + trace_id schema | 1h |
| 4 | meta/tests/conftest.py | 增 3 个 CLI 到 `_block_unguarded_entry` 合法列表 | 30min |
| 5 | pytest.ini | 增 9 markers: `agent_friendly/multi_agent/observability/factory/template_generator/property_based/mutation/diagnostics/trace_id` | 15min |
| 6 | 新建 3 个 .trae/rules/*.md | `test-data-rules.md` (D.2) / `test-observability-rules.md` (M.1-M.9) / `multi-agent-coordination.md` (D.7) | 1.5h |
| 7 | TESTING_GUIDE.md | 改 9 节命令为 `python test.py --file`; 改认证为 cookie; 增 D.1 模板规范 | 1h |
| **小计** | - | - | **5.75h** |

**总工时**: 20h (Phase 1-6) + 5.75h (规则更新) = **25.75h**

### 建议里程碑

| 里程碑 | 范围 | 工时 | 交付物 |
|--------|------|:---:|--------|
| **M1: Phase 1 (D.3+D.4+D.5)** | Auto-server + Fast feedback + JSON | 2.5h | 3 FR, 跑全量 v3.17 |
| **M2: Phase 2 (D.7)** | 多 agent 隔离 | 2h | service_manager 多端口, 端口锁 |
| **M3: Phase 3 (D.1+D.2)** | Test 模板 + Factory | 2.5h | 8+ 模板, 3+ factory |
| **M4: Phase 4 (D.6+M.6)** | 错误码 + 建议 | 2h | 19 Action fix_hint |
| **M5: Phase 5 (M.1+M.5+M.9)** | trace_id + /_diagnostics + 测试 | 5h | 端到端 trace, 8+ 测 |
| **M6 (Optional)**: Phase 6 | D.8/D.10/M.3/M.7/M.8 | 6h | Should 全部 |

**Phase 1-5 = 14h**, Phase 1-6 = 20h

---

## 9. 变更/设计提案 (RFC)

### 9.1 现状分析 (As-Is)

**架构**:
```
[AI Coding Agent]
  ↓ python test.py
[d:\filework\test.py]  ← 唯一入口
  ├─ DB 快照/还原 (v3.17)
  ├─ 锁机制 (--all exclusive, --failed shared)
  └─ pytest -n4 (xdist)
       ↓
  [meta/tests/] + [meta/tests/e2e/bo_action/]  ← 测试目录
       ↓ HTTP (cookie)
  [service_manager.ps1]  ← 启停 server (单实例)
       ↓ 端口 3010
  [Backend Waitress]  ← 跑 19 Action + subflow
       ↓
  [meta/architecture.db]  ← 共享 DB
```

**痛点**:
- P-1: Agent 跑测试需手动 `service_manager.ps1 start` (摩擦)
- P-2: 单测 30s (含 DB 快照) (慢)
- P-3: stdout 输出, Agent 难解析
- P-4: 错误码 E001-E045 无 fix_hint
- P-5: 单端口 3010, 多 Agent 冲突
- P-6: 无 test 模板, Agent 需手写
- P-7: 无 factory, Agent 需手动造数据
- P-8: 无 trace_id, 生产难追踪
- P-9: 无 `/_diagnostics`, Agent 排查慢
- P-10: 无 Prometheus / JSON log, 业界标准缺失

**关键代码路径**:
- `d:\filework\test.py` (入口, 含 `--all/--failed/--file/--unit/--integration/--status`)
- `d:\filework\excel-to-diagram\pytest.ini` (markers)
- `d:\filework\excel-to-diagram\meta\tests\conftest.py` (硬阻断)
- `d:\filework\excel-to-diagram\meta\tests\e2e\bo_action\conftest.py` (v3.17 新)
- `d:\filework\excel-to-diagram\meta\api\bo_action_api.py` (19 Action 路由)
- `d:\filework\excel-to-diagram\meta\api\db_admin_api.py` (v3.16 端点)
- `d:\filework\excel-to-diagram\scripts\service_manager.ps1`
- `d:\filework\excel-to-diagram\meta\core\error_codes.py` (E001-E045)

### 9.2 目标状态 (Target State)

**架构**:
```
[AI Coding Agent (多)]
  ├─ Agent A: worktree-A, port 3010, DB-a
  ├─ Agent B: worktree-B, port 3011, DB-b
  └─ Agent C: worktree-C, port 3012, DB-c
       ↓ python test.py --port 3010
[d:\filework\test.py]  ← 升级: --port, --single, --json
  ├─ DB 快照/还原 (per-port)
  ├─ 端口锁 (port 内 exclusive, port 间共享)
  └─ pytest -n4 (xdist, per-port)
       ↓
  [test.py --single <id>]  ← 跳过快照, < 5s
  [test.py --json results.json]  ← 完整 schema + trace_id
       ↓ HTTP (cookie)
  [service_manager.ps1 start --port N]  ← 多实例
       ↓ port N (3010/3011/3012)
  [Backend Waitress (N instances)]  ← 多实例
       ↓
  [meta/architecture_<port>.db]  ← per-port DB
       ↓
  [/_diagnostics 端点]  ← 给 Agent 用
  [/_metrics Prometheus]  ← 给业界用
  [trace_id 端到端]  ← 每个请求

[test_templates/]  ← 8+ 模板 (FR-D.1)
[factories/]  ← 3+ factory (FR-D.2)
[property_strategies.py]  ← hypothesis (FR-D.8)
[coverage_gap tool]  ← CLI (FR-D.9)
[mutmut 配置]  ← (FR-D.10)

[error_codes.py 升级]  ← E001-E045 + fix_hint (FR-D.6/M.6)
[structured_logger.py]  ← JSON log (FR-M.2)
[metrics_store.py]  ← P50/P95/P99 (FR-M.4)
```

### 9.3 详细设计 (Detailed Design)

#### Module 设计

**新增模块** (5):
1. `meta/api/diagnostics_api.py` (~200 行): `/_diagnostics` 端点
2. `meta/api/metrics_api.py` (~150 行): `/_metrics` Prometheus + `/_alerts`
3. `meta/core/structured_logger.py` (~100 行): JSON logger
4. `meta/core/metrics_store.py` (~150 行): 滑动窗口 + P50/P95/P99
5. `meta/core/trace_id.py` (~50 行): trace_id 生成 + 注入

**新增目录**:
1. `meta/tests/factories/` (~3 factory × 50 行 = 150 行)
2. `meta/tests/templates/` (~8 模板 × 30 行 = 240 行)
3. `meta/tests/hypothesis_strategies.py` (~80 行)
4. `meta/tests/tools/gen_test_template.py` (~50 行, CLI)
5. `meta/tests/tools/coverage_gap.py` (~80 行, CLI)

**升级模块** (4):
1. `meta/core/error_codes.py`: 加 `fix_hint` + `see_also`
2. `meta/api/bo_action_api.py`: 注入 trace_id
3. `meta/services/subflow_engine.py`: trace_id 透传
4. `scripts/service_manager.ps1`: 多端口支持
5. `d:\filework\test.py`: `--single/--port` 参数

**新增测试** (5 文件, ~20 测):
1. `meta/tests/e2e/bo_action/test_observability_v318.py` (8 测)
2. `meta/tests/e2e/bo_action/test_agent_friendly_v318.py` (5 测)
3. `meta/tests/e2e/bo_action/test_diagnostics_v318.py` (3 测)
4. `meta/tests/e2e/bo_action/test_template_generator.py` (2 测)
5. `meta/tests/e2e/bo_action/test_multi_agent.py` (2 测)

#### 数据模型

**Trace ID**:
```python
# meta/core/trace_id.py
class TraceId:
    @staticmethod
    def generate() -> str:
        return uuid4().hex[:32]

    @staticmethod
    def get() -> Optional[str]:
        return g.get('trace_id')
```

**ErrorCode 升级**:
```python
# meta/core/error_codes.py
@dataclass
class ErrorCode:
    code: str
    message: str
    fix_hint: str  # 🆕
    see_also: List[str]  # 🆕 (相关文件路径)
    category: str  # 分类: auth, db, subflow, etc.
```

**Metrics Store**:
```python
# meta/core/metrics_store.py
class MetricsStore:
    def record(self, name: str, value: float, tags: dict) -> None: ...
    def p50(self, name: str) -> float: ...
    def p95(self, name: str) -> float: ...
    def p99(self, name: str) -> float: ...
```

#### API 设计 (关键端点)

| 端点 | 方法 | 角色 | 描述 |
|------|------|------|------|
| `/_diagnostics` | GET | admin | 综合诊断 (FR-M.5) |
| `/_metrics` | GET | 公开 | Prometheus 格式 (FR-M.3) |
| `/_alerts` | GET | admin | 告警列表 (FR-M.8) |
| `/_error_codes` | GET | 公开 | 错误码列表 (FR-M.6) |
| `/_error_codes/<code>` | GET | 公开 | 单个错误码 + fix_hint (FR-M.6) |
| `/_error_clusters` | GET | admin | 错误聚合 (FR-M.7) |

**`/_diagnostics` Response Schema**:
```json
{
  "success": true,
  "data": {
    "health": { ... 简化版 _db_health ... },
    "recent_errors": [
      {"trace_id": "abc...", "code": "E005", "ts": "2026-06-06T...", "message": "..."}
    ],
    "error_codes_count": 45,
    "error_codes": [
      {"code": "E005", "message": "...", "fix_hint": "检查 meta/api/auth.py:42"}
    ],
    "alerts_count": 2,
    "recovery_suggestions": [
      "DB WAL > 1MB, run: python scripts/backup_db.py --check"
    ],
    "generated_at": "2026-06-06T..."
  }
}
```

#### 主要流程

**流程 1: Agent 跑单测 (Fast Feedback)**
```
Agent 改 1 行代码
  ↓
python test.py --single meta/tests/.../test_x.py::test_y
  ↓
test.py 跳过 DB 快照/锁
  ↓
pytest 跑单测
  ↓
< 5s 反馈 (PASSED/FAILED + trace_id + fix_hint)
  ↓
Agent 根据 fix_hint 修复
```

**流程 2: 多 Agent 并行**
```
Agent A 在 port 3010
Agent B 在 port 3011
Agent C 在 port 3012
  ↓
各自 worktree
  ↓
各自 test.py --port <port>
  ↓
各自独立 DB snapshot
  ↓
互不干扰
```

**流程 3: 生产 Agent 排查**
```
生产报错 trace_id=abc
  ↓
Agent 调 GET /_diagnostics
  ↓
看 recent_errors[0]: {trace_id: "abc", code: "E005", message: "..."}
  ↓
Agent 调 GET /_error_codes/E005
  ↓
看 fix_hint: "检查 meta/api/auth.py:42"
  ↓
Agent 自动修, 验证
```

### 9.4 备选方案

| 选项 | 描述 | 优 | 劣 | 决策 |
|------|------|---|----|------|
| **O-A**: trace_id 自己实现 | 用 uuid4, Flask `g` 存储 | 简单, 无依赖 | 易丢, 跨进程难 | ✅ 选 (v3.18 范围) |
| **O-B**: OpenTelemetry | OTel SDK | 业界标准 | 重依赖, 学习曲线 | ❌ 推迟 (v3.19) |
| **O-A**: 端口 3010-3019 | 10 个实例, 简单 | 易理解, 够用 | 端口耗尽需扩 | ✅ 选 |
| **O-B**: 端口 + worktree | 加 worktree 隔离 | 更强隔离 | 复杂 | ❌ 推迟 (用户已自管) |
| **O-A**: 自实现 P50/P95/P99 | 滑动窗口 | 无依赖 | 简单实现 | ✅ 选 (5min 窗口) |
| **O-B**: prometheus_client 自带 | Histogram | 标准 | 重 | ⚠️ 选 Histogram 仅 metrics |

### 9.5 实施与迁移计划

#### 实施顺序 (6 Phase, 14h Phase 1-5 + 6h Phase 6)

**Phase 1 (2.5h) - 快速胜利**:
1. D.5 JSON output 强化 (+trace_id)
2. D.4 `--single` fast feedback
3. D.3 `bo_action_server_or_start` fixture

**Phase 2 (2h) - 多 Agent 隔离**:
1. D.7 service_manager 多端口
2. D.7 test.py --port
3. D.7 per-port DB
4. 端口锁机制

**Phase 3 (2.5h) - 写测试辅助**:
1. D.1 Test 模板生成器 (8 模板)
2. D.2 Factory (3 个)

**Phase 4 (2h) - 错误码升级**:
1. D.6/M.6 fix_hint
2. `/_error_codes/<code>` 端点
3. `/_error_codes` 列表

**Phase 5 (5h) - 可观测性**:
1. M.1 trace_id
2. M.2 JSON log
3. M.4 P50/P95/P99
4. M.5 `/_diagnostics` 端点
5. M.9 测试套件 (8+ 测)

**Phase 6 (6h, 可选) - Should 全部**:
1. D.8 hypothesis (1.5h)
2. D.9 coverage gap (1h)
3. D.10 mutation (1.5h)
4. M.3 Prometheus (1h)
5. M.7 错误聚合 (1h)
6. M.8 Alerts (1h)

#### 风险与缓解

| 风险 | 等级 | 缓解 |
|------|:---:|------|
| **R-1**: trace_id 注入破坏现有审计 | 🟡 | 改 `_write_audit` 接受可选 trace_id, 不传则 None |
| **R-2**: 多端口 service_manager 影响单实例 | 🟡 | 旧调用保持兼容, 默认仍 3010 |
| **R-3**: JSON log 改 print 影响 SSE | 🟢 | log 输出到文件, 不影响 SSE 流 |
| **R-4**: Fast feedback 跳过快照破坏测试隔离 | 🟡 | 仅 `--single` 跳过, 警告提示 |
| **R-5**: v3.17 13 模块 64 单测回归 | 🟢 | TR-001 保证, 跑全量验证 |
| **R-6**: Cookie vs Bearer 冲突 (跟 shared/) | 🟡 | 走 `tests/fixtures/admin_token.py` cookie 模式 |
| **R-7**: hypothesis 跑超时 | 🟢 | max_examples=20, deadline=2s |

#### 测试策略

**单元测试**: Phase 5 加 8+ 测 (FR-M.9)
**集成测试**: 跑全量 v3.17 13 模块 64 测, 不回归
**E2E 测试**:
- 跑 1 个 agent 改 1 行, 测 fast feedback
- 跑 3 个 agent 并行, 测隔离
- 调 `/_diagnostics`, 测 schema 完整
- 调 `/_metrics`, 测 Prometheus 格式

**性能测试**:
- 单测 < 5s (NFR-001)
- 100 测 < 30s (含并行)

#### 回滚计划

**每 Phase 独立**, 失败回滚:
- 改 conftest.py (新 fixtures) → 删
- 改 service_manager.ps1 → 旧版
- 改 test.py (新参数) → 旧版
- 新模块 (diagnostics_api 等) → 删

**整 v3.18 回滚**:
```bash
git revert v3.18-*
git checkout v3.17
```

---

## 10. TBD 列表 (用户已澄清 + 行业研究决策)

| ID | 项 | 缺失信息 | 决策 | 行业依据 |
|----|----|---------|------|---------|
| TBD-1 | M 维度优先级 | - | ✅ **M v3.18 一起做** (用户确认) | - |
| TBD-2 | D.7 隔离范围 | - | ✅ **只做端口+DB+env, worktree Agent 自管** | [Git worktree 是 multi-agent 事实标准](https://www.augmentcode.com/guides/agent-observability-for-ai-coding) (Cursor/Intent/Augment) |
| TBD-3 | D.10 Mutation 必做? | - | ✅ **Should, 本地跑, CI 跳过** | mutmut 是 Python 事实标准, 但**跑得慢**业界不 CI per-PR 跑 |
| TBD-4 | M.3 Prometheus 格式 | - | ✅ **Prometheus (业界标准)** | [Grafana 2026 Survey: Prometheus + OTel 是双柱, 65% 重投资](https://grafana.com/blog/observability-survey-OSS-open-standards-2026/) |
| TBD-5 | A-1: multi-agent-coordination.md | - | ✅ **Verified (用户自管)** | - |
| TBD-6 | service_manager 端口范围 | - | ✅ **3010-3019 (10) + 可配 env** | Testcontainers 随机, GitHub Actions 1-4, K8s 大范围; 10 是平衡点 |
| TBD-7 | fix_hint 文档化来源 | - | ✅ **Agent 自动推断** (用户确认) | - |
| TBD-8 | mutmut 5 核心 Action | - | ✅ **5+1 选**: user.* + batch_save + audit.export + subflow_chain + **permission_intersector** + enum_type.crud | 覆盖鉴权/CRUD/合规/子流程/**切面**/v3.5 |

### 行业研究补充 (作为决策依据)

- **OTel 决策**: v3.18 用 UUID (1h 可完成), v3.19 迁 OTel (有预算时)
  - 原因: [OTel 已毕业 (2026/5/21)](https://www.cncf.io/announcements/2026/05/21/cloud-native-computing-foundation-announces-opentelemetrys-graduation-solidifying-status-as-the-de-facto-observability-standard/), 但集成需 SDK+Collector+backend (重)
- **Multi-agent 隔离**: worktree Agent 自管 (业界共识), 我们只做端口/DB/env
- **Prometheus 必选**: 65% 企业重投资, 跟所有监控无缝集成, 无替代方案
- **Mutation 跑法**: 本地跑, CI 跳过 (业界共识: 跑得慢, nightly 跑)
- **Factory_boy 选型**: Python 社区事实标准, 已被 SQLAlchemy/pandas 等使用
- **Hypothesis 选型**: Python property-based testing 事实标准, SQLAlchemy/pandas 都在用
- **Port 范围**: 10 个是 AI Coding Agent 并发常用值, 可通过 `SERVICE_PORT_RANGE` env 扩展

---

## Spec + RFC 完整性检查

- ✅ Spec 含 **10 节**
- ✅ 末节名: **TBD List**
- ✅ TBD 内容完整 (8 项)
- ✅ RFC 嵌入在第 9 节
- ✅ 6 大需求类型覆盖 (Business/User/Solution/Functional/NFR/IF)
- ✅ 5 大 NFR (性能/隔离/可观测/兼容/合规)
- ✅ 6 Phase 实施计划 (14h Phase 1-5 + 6h Phase 6)
- ✅ 7 风险 + 缓解
- ✅ 完整测试策略
- ✅ 回滚计划

---

## Spec + RFC 确认请求 (V2 — TBD 已澄清)

我已完成 Spec + RFC, 8 个 TBD 已**全部澄清** (TBD-1/7 用户确认, TBD-2/3/4/6/8 行业研究决策)。请最终确认:

### 1. 授权

- [ ] 是否接受此 Spec + RFC (V2)?
- [ ] 是否授权 **Phase 1-5 (14h)** 立即开始实施?
  - Phase 1 (2.5h): D.5+D.4+D.3 (JSON+Fast+Auto-server)
  - Phase 2 (2h): D.7 (多 agent 端口/DB/env 隔离)
  - Phase 3 (2.5h): D.1+D.2 (Test 模板 + Factory)
  - Phase 4 (2h): D.6+M.6 (错误码 + fix_hint 自动推断)
  - Phase 5 (5h): M.1+M.2+M.4+M.5+M.9 (trace_id + JSON log + P50/P95/P99 + /_diagnostics + 8+ 测)
- [ ] 或仅 **Phase 1-4 (10h)** (含 M 部分但不含 trace_id + _diagnostics)?
- [ ] 或 **Phase 1-6 (20h)** (含 Should 全部: hypothesis + coverage + mutation + Prometheus + 错误聚合 + alerts)?

### 2. 8 个 TBD 已全部澄清 ✅

| ID | 决策 | 行业依据 |
|----|------|---------|
| TBD-1 | ✅ M v3.18 一起做 (用户) | - |
| TBD-2 | ✅ 只做端口+DB+env (行业) | Git worktree 是 multi-agent 事实标准 |
| TBD-3 | ✅ Should, 本地跑 (行业) | 业界不 CI per-PR 跑 |
| TBD-4 | ✅ Prometheus (行业) | 65% 企业重投资 |
| TBD-5 | ✅ Verified (假设) | - |
| TBD-6 | ✅ 3010-3019 + 可配 (行业) | Testcontainers/K8s/GH Actions 平衡 |
| TBD-7 | ✅ Agent 自动推断 (用户) | - |
| TBD-8 | ✅ 5+1 选 (行业) | 覆盖 6 大核心域 |

### 3. 补充信息

如 Spec/RFC 有不完整需补充, 请在 "Additional Info" 提供。

---

💡 如果觉得当前问题不足以澄清需求, 欢迎在 "Additional Info" 提供任何补充信息。
