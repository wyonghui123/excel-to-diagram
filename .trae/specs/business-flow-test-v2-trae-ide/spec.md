# Spec: 业务流 E2E 测试智能生成系统 v2.0 (TRAE IDE 原生集成版)

> **作者**: AI Agent
> **创建日期**: 2026-06-13
> **最后更新**: 2026-06-13
> **状态**: Spec v2.0 已确认,等待开发启动
> **关联 Spec**: 无(新方向,首版)
> **关联 RFC**: 包含在本文档第 9 节

---

## 1. 背景与目标

### 1.1 背景

**项目环境**:
- **TRAE IDE**: 字节跳动 AI 原生 IDE(VS Code 内核),AI 优先的智能开发伴侣
- **AI Coding 范式**: 用户在 chat 中用自然语言与 Agent 对话,Agent 调用 Skill 完成任务
- **已有 22 个 Skill**: 全部已注册,可通过自然语言触发
- **45 个 YAML schema**: 业务规则结构化表达
- **12 个 E2E spec**: 多为单页业务,无跨页业务流
- **561 个 YonDesign 单测**: 已生成,但在 `__tests__` 目录,与业务流测试分层

**业界趋势(2026-05/06)**:
| 来源 | 关键洞见 | 启示 |
|------|---------|------|
| Trae CN 2026 完全指南 | TRAE 是"AI 优先的智能开发伴侣",代码/终端/调试器/版本控制与 AI 引擎深度打通 | 测试操作必须深度融入 IDE,不能脱离 |
| Trae-GStack (npm) | 21 个工作流命令,自然语言 + slash command 双触发 | 测试触发应是 slash command + 自然语言双模式 |
| Trae SWE-bench 论文(2025-05) | 70.6% 解决率,Tester Agent 跑回归测试,集成于 AI Coding Loop | 测试 Agent 必须是 Loop 一环,不是外挂 |
| Skywork Trae Workflow | Code → Format → Test → Commit 一体化,测试失败 AI 建议 fix,等用户决定 | 失败修复人在回路 |
| CSDN 2026 奇点大会 | AI 原生测试生成 417% 效率提升,Git 提交触发实时回归 | 触发点应覆盖开发全流程 |
| AI-Void 2026-05 文档 | 9 维度 AI Coding 中"AI-Driven Testing"是核心 | 测试能力是 AI IDE 的一等公民 |

**原 Spec v1.0 错位**:
- ❌ 强调 Pipeline CLI + AGENT_PORT 隔离
- ❌ 假设三 Agent Skill 是后端服务
- ❌ 缺少与 TRAE IDE 的对话触发集成

**Spec v2.0 关键调整**:
- ✅ 测试 Skill 是 TRAE IDE 的"一等公民",通过 chat + slash command 触发
- ✅ 三个新 Skill 仍是核心,但编排方式改为 TRAE Agent 在 chat 中调用
- ✅ 测试结果、Healer 修复建议、覆盖率报告直接在 IDE 中可视化
- ✅ 用户在对话中驱动整个流程(写业务代码 → chat 触发"测一下" → 看结果 → 触发"修复" → review YAML)

### 1.2 业务目标

| BO# | 目标 | 衡量指标 |
|-----|------|---------|
| BO-1 | 测试能力作为 TRAE IDE 原生功能,零上下文切换 | 用户在 IDE chat 中 1 句话触发完整测试流程 |
| BO-2 | AI Agent 理解业务流程,生成业务断言式 E2E | 业务流 E2E 场景 ≥ 40 个 |
| BO-3 | 业务规则覆盖率从 ~10% 提升到 80%+ | 业务规则派生测试 ≥ 288 条 |
| BO-4 | PM/BA 可在 IDE 中 review YAML 草稿 | business-flow.yaml 可在 IDE 中打开、编辑、review status |
| BO-5 | 测试维护成本降低,Healer 自愈率 ≥ 60% | 借鉴 Slack 数据 |

### 1.3 用户/涉众目标

| 涉众 | 在 TRAE IDE 中的目标 | 关键交互点 |
|------|---------------------|-----------|
| PM/BA | IDE 中直接 review YAML 草稿、点击 approve | `.trae/specs/<feat>/business-flow.yaml` 在 IDE 编辑器中 |
| QA 工程师 | IDE 中跑测试、看结果、看覆盖率 | chat 触发 + 终端面板结果 + coverage.html preview |
| 开发 | 写业务代码后,IDE 弹出"是否生成测试" | 代码保存时 TRAE 自动提示(基于 hooks) |
| AI Agent | 接收 chat 中的指令,自动编排三 Skill | chat input → Skill 调度 → 输出 |
| Tech Lead | IDE 中看业务覆盖率仪表盘 | `.trae/state/coverage.html` 在 IDE preview |
| 架构师 | schema 改后,IDE 中触发"重新派生业务规则" | chat: "schema 改了,重新派生出测试" |

---

## 2. 需求类型概览

| 类型 | 适用 | 证据(来源) |
|------|------|--------------|
| 业务 | 是 | 5 BO 目标,直接来自 2026 业界趋势 + 项目痛点 + TRAE IDE 约束 |
| 用户/涉众 | 是 | 6 类涉众在 IDE 中的目标 |
| 解决方案 | 是 | TRAE IDE chat 触发 + 三 Skill 协作 + IDE 可视化 |
| 功能 | 是 | FR-001 ~ FR-024,24 个核心功能 |
| 非功能 | 是 | NFR-001 ~ NFR-009 |
| 外部接口 | 是 | IF-001 ~ IF-005 |
| 过渡 | 是 | TR-001 ~ TR-003 |

---

## 3. 功能需求

### FR-001: TRAE IDE Chat 触发

- **描述**: 系统 MUST 在 TRAE IDE chat 中,接受用户自然语言指令,自动调用相应 Skill。
- **验收标准**:
  - chat: "为 AppButton 写测试" → 自动调用 test-gen Skill
  - chat: "测一下业务对象完整流程" → 自动调用 business-flow-planner Skill
  - chat: "跑测试" + 调用 playwright-cli-testing
  - chat: "修复这个失败" + 调用 business-flow-healer
  - chat: "派生出业务规则" + 调用 discover_business_rules
  - **支持 slash command 简写**(借鉴 trae-gstack):
    - `/test-gen` (为 X 写测试)
    - `/biz-test` (测一下业务流)
    - `/heal` (修复失败)
    - `/biz-rules` (派生业务规则)
- **优先级**: Must
- **类型映射**: 解决方案 / 功能
- **来源**: trae-gstack 21 个 slash command 范式;TRAE CN 2026 指南"自然语言交互";用户最新决策

### FR-002: Planner Skill - 业务流 YAML 起草(在 IDE 中)

- **描述**: Planner Skill MUST 在 TRAE IDE chat 中被触发后,基于 spec.md + business_rules.yaml,生成 business-flow.yaml 草稿,并在 IDE 编辑器中自动打开供 PM/BA review。
- **验收标准**:
  - 草稿生成后,自动在 IDE 编辑器中打开文件 `.trae/specs/<feat>/business-flow.yaml`
  - 文件头部显示 banner: `# 🤖 AI Generated Draft - needs_pm_review: true`
  - 顶部显示 review status: `review_status: draft`
  - **IDE 内集成 review actions**:
    - 状态栏显示 "📋 Business Flow Draft Ready"
    - 可点击按钮: `[Approve] [Request Changes] [Edit in IDE]`
    - 点击 Approve → 自动设置 `review_status: approved` 并触发 Generator
    - 点击 Request Changes → 进入 chat 反馈循环
- **优先级**: Must
- **类型映射**: 解决方案 / 功能

### FR-003: Generator Skill - 业务流 Playwright 代码生成(在 IDE 中)

- **描述**: Generator Skill MUST 在 PM/BA approve YAML 后,在 IDE 中生成 spec.js + Screenplay Task,直接在 IDE 终端面板跑测试。
- **验收标准**:
  - 生成的 `e2e/business-flow/<feat>.spec.js` 在 IDE 中自动打开
  - 生成任务写入 IDE 任务列表
  - 测试在 IDE 终端面板运行,实时显示结果
  - 失败的 trace 在 IDE 中可点击查看
- **优先级**: Must

### FR-004: Healer Skill - 失败自动修复(在 IDE 中,人在回路)

- **描述**: Healer Skill MUST 在测试失败后,在 IDE 中弹出修复建议,等用户确认后应用。
- **验收标准**:
  - 测试失败时,IDE 弹出对话框: "🔧 失败原因: locator 漂移. 建议修复: [显示 diff]"
  - 用户选项: `[Apply Fix] [Edit Manually] [Mark as Bug] [Skip]`
  - Apply Fix → 自动应用并重跑
  - Edit Manually → 打开 spec.js 让用户改
  - **业务断言失败 → 不弹出修复建议,直接显示业务语义错误,要求人工 review**
- **优先级**: Must

### FR-005: 业务规则抽取器(在 IDE 中触发)

- **描述**: chat 触发"派生出业务规则"或"schema 改了"时,自动运行 `discover_business_rules.py`,在 IDE 中显示派生结果。
- **验收标准**:
  - chat: "派生出业务规则" → 自动运行脚本
  - 产出 `.trae/specs/_business_rules/<object>.yaml` 在 IDE 中显示 diff
  - IDE 通知: "✅ 已派生 9 条业务规则,5 个新场景"
- **优先级**: Must

### FR-006: Screenplay Task 框架(IDE 项目结构)

- **描述**: Screenplay 框架在 `e2e/screenplay/` 目录,IDE 中提供代码片段。
- **验收标准**:
  - 在 IDE 中输入 `screenplay-task` 代码片段 → 自动生成 Task 模板
  - 在 IDE 中输入 `screenplay-actor` → 自动生成 Actor 模板
  - Snippet 在 `.vscode/xxx.code-snippets` 或 TRAE snippets 中
- **优先级**: Must

### FR-007: 业务断言库(IDE 中可视化)

- **描述**: BusinessRuleAssertor 在 IDE 中提供"业务断言"snippet。
- **验收标准**:
  - 在 IDE 中输入 `biz-assert` → 弹出"业务断言类型"选择
  - 选中后自动生成 `BusinessRuleAssertor.assertRule('xxx', context)`
  - **错误信息直接在 IDE 问题面板显示**,不是堆栈
- **优先级**: Must

### FR-008: Business-flow YAML Schema(IDE Schema 校验)

- **描述**: business-flow.yaml 在 IDE 中实时校验。
- **验收标准**:
  - IDE 安装 schema 关联(`.trae/specs/templates/business-flow.schema.json`)
  - 字段错时,IDE 显示红线提示
  - 自动补全(基于 schema)
- **优先级**: Must

### FR-009: 1 个示范场景端到端跑通(在 IDE 中)

- **描述**: 示范"业务对象生命周期"完整流程,在 IDE 中可见。
- **验收标准**:
  - chat: "测一下业务对象完整流程"
  - Planner 生成 YAML → IDE 自动打开 → 状态栏显示 draft ready
  - PM 点击 Approve → Generator 生成 spec.js + 跑测试
  - 跑测试时 IDE 终端面板实时显示进度
  - 业务断言覆盖率 ≥ 70%
- **优先级**: Must

### FR-010: AI 起草 + 人 review 协作流(IDE 中)

- **描述**: review 流程在 IDE 中通过按钮 + 状态栏完成。
- **验收标准**:
  - YAML 草稿生成后,IDE 通知 + 状态栏 + Review Actions 按钮
  - PM 可直接在 IDE 编辑器中修改 YAML
  - 修改后点击 "[Save & Approve]" → 触发 Generator
  - 可在 chat 中对话修改: "把 tasks 改成更细的步骤"
- **优先级**: Must

### FR-011: 5 业务域落地(基于 chat 触发)

- **描述**: chat 触发对 5 个业务域的测试生成。
- **验收标准**:
  - "测一下枚举管理" / "测一下审计日志" / "测一下导入导出" / "测一下产品版本"
  - 每个域 ≥ 3 场景
- **优先级**: Should

### FR-012: 业务规则覆盖率追溯(IDE 中可视化)

- **描述**: 覆盖率报告 `.trae/state/coverage.html` 在 IDE 中 preview。
- **验收标准**:
  - chat: "看业务覆盖率" → 在 IDE 中打开 coverage.html
  - 报告含覆盖率图 + 未覆盖规则列表 + 修复建议
- **优先级**: Should

### FR-013: Healer 边界(IDE 中可视化警告)

- **描述**: 安全模块不修复,IDE 中显示警告。
- **验收标准**:
  - Healer 检测到安全模块 → IDE 弹出红色警告: "⚠️ authService 模块不允许自动修复"
  - 显示 "请人工 review"
- **优先级**: Must

### FR-014: 多 Agent 端口隔离(IDE 后台)

- **描述**: 多 Agent 并行仍在 IDE 后台,使用 AGENT_PORT 3010-3019。
- **验收标准**:
  - Planner/Generator/Healer 可在不同 port 并行
  - IDE 显示当前活跃 Agent
  - 不影响用户前台操作
- **优先级**: Should

### FR-015: IDE 工作流模板(取代 v1 的 Pipeline CLI)

- **描述**: 不再是独立 CLI,而是 IDE 中的"工作流模板"。
- **验收标准**:
  - chat: "/biz-test-full <feat>" 触发完整流程
  - 各步骤在 IDE 中可视:
    - Step 1: 业务规则抽取 → 进度
    - Step 2: Planner 生成 → 状态
    - Step 3: PM Review → 等待
    - Step 4: Generator 生成 → 状态
    - Step 5: 跑测试 → 实时进度
    - Step 6: Healer → 等待用户决定
- **优先级**: Should

### FR-016: 业务流 spec 模板生成(在 IDE 中)

- **描述**: 模板在 IDE snippets。
- **验收标准**:
  - 在 IDE 中输入 `business-flow-template` → 自动展开 YAML 模板
  - 含 placeholder 提示
- **优先级**: Must

### FR-017: Healer 审计与可观测性(IDE 中可查)

- **描述**: `.trae/state/healings.jsonl` 在 IDE 中可查。
- **验收标准**:
  - chat: "看 healer 历史" → IDE 中显示最近修复记录
  - 含 trace_id / root_cause / fix_type
- **优先级**: Must

### FR-018: 业务流 spec.md 模板(在 IDE snippets)

- **描述**: spec.md 模板在 IDE snippets。
- **验收标准**:
  - `spec-business-flow` snippet 生成模板
- **优先级**: Should

### FR-019: 数据隔离(沿用现有,IDE 提示)

- **描述**: 测试数据使用 isolation,IDE 中显示 cleanup 状态。
- **验收标准**:
  - 测试前 IDE 提示"将创建测试数据(自动清理)"
  - 测试后 IDE 通知"已清理 X 条数据"
- **优先级**: Must

### FR-020: 业务流 Spec ↔ YAML 双向追溯(IDE 中)

- **描述**: 双向追溯在 IDE 中可视化。
- **验收标准**:
  - 打开 spec.md 时,IDE 显示关联的 business-flow.yaml 和 spec.js
  - 可点击跳转
- **优先级**: Should

### FR-021: 业务流测试目录规范(沿用)

- **描述**: 业务流 E2E 在独立目录 `e2e/business-flow/`。
- **验收标准**:
  - 与现有 `e2e/features/` 并存
  - IDE 中显示目录树
- **优先级**: Must

### FR-022: 业务流文档生成(IDE 中预览)

- **描述**: `.trae/state/coverage.html` 在 IDE preview 打开。
- **验收标准**:
  - chat: "生成覆盖率报告" → IDE preview 打开
  - 含场景覆盖、Healer 修复率、业务规则覆盖率
- **优先级**: Should

### FR-023: 业务流测试数据推演(IDE 提示)

- **描述**: 数据推演在 chat 中显示,IDE 提示用户确认。
- **验收标准**:
  - chat: "测一下边界值" → AI 推演边界数据
  - IDE 通知"将使用以下边界数据:[显示],确认? [Y/N]"
- **优先级**: Should

### FR-024: 业务流性能基线(IDE 状态栏)

- **描述**: 性能指标在 IDE 状态栏显示。
- **验收标准**:
  - 测试运行时,IDE 状态栏显示 "⏱ 5.2s | $0.12 | 8 scenarios"
  - 跑完显示 "✅ 5.2s | $0.12 | 8/8 passed"
- **优先级**: Should

---

## 4. 非功能需求

### NFR-001: 性能(IDE 响应)

- **描述**: IDE chat 响应 < 3s(简单 Skill 触发);复杂流程 < 5min
- **度量**: IDE 状态栏 timing
- **优先级**: Should

### NFR-002: 成本(LLM 成本,用户按需选模型)

- **描述**: 单 spec LLM 成本 < ¥5(假设用户按任务选合适模型);系统 MUST 记录每次调用的 model_name + tokens + cost,让用户可审计
- **度量**: `.trae/state/agent-runs.jsonl` 中 `model_name` + `cost_cny` 字段
- **模型选择策略** (用户决策,系统不强制):
  - **业务流规划** (需要强推理): 用户可选 Claude Sonnet 4 / GPT-5
  - **测试代码生成** (质量优先): 用户可选 Claude Sonnet 4 / DeepSeek V3
  - **快速 Healer 修复** (速度优先): 用户可选 Claude Haiku / DeepSeek V3
  - **中文业务理解**: 用户可选 Qwen 3.5 / DeepSeek V3 / Doubao
  - **多语言支持**: 用户可选 DeepSeek V3 (338 语言)
  - **多模态 UI 测试**: 用户可选 Gemini 2.5 Pro
  - **默认推荐**: 平衡场景用 Claude Sonnet 4 (质量+速度)
- **重要约束**: 模型由用户在 TRAE IDE chat 输入框切换,系统不锁定,只是记录
- **优先级**: Should

### NFR-003: 可靠性(Healer 自愈率)

- **描述**: Healer 对 DOM 漂移修复成功率 ≥ 60%
- **度量**: `healings.jsonl` success 比率
- **优先级**: Must

### NFR-004: 业务规则覆盖率

- **描述**: 业务规则派生测试覆盖 ≥ 80%
- **度量**: `coverage.json`
- **优先级**: Must

### NFR-005: 可观测性(IDE 内)

- **描述**: 所有 Agent 调用 MUST 在 IDE 中可见状态
- **度量**: IDE 状态栏 + 终端面板
- **优先级**: Must

### NFR-006: 安全性(Healer 默认 deny)

- **描述**: Healer 修复前 MUST 检查 `healer/PERMISSIONS.md`
- **度量**: IDE 警告 + healings.jsonl
- **优先级**: Must

### NFR-007: 数据隔离

- **描述**: 业务流测试 MUST 不污染生产 DB
- **度量**: auto-fixtures cleanup
- **优先级**: Must

### NFR-008: 多 Agent 隔离(IDE 后台)

- **描述**: Planner/Generator/Healer 并行运行
- **度量**: AGENT_PORT 3010-3019
- **优先级**: Should

### NFR-009: PM/QA 可参与性(IDE 内)

- **描述**: 100% 业务流场景 MUST 有 YAML 草稿,PM 可在 IDE 中 review
- **度量**: YAML 中 `agent_draft=true` 的比例 + IDE review 完成率
- **优先级**: Should

---

## 5. 外部接口需求

### IF-001: TRAE IDE Chat 接口

- **类型**: IDE API
- **端点**: TRAE IDE MCP chat interface
- **交互**: 自然语言输入 → 触发 Skill → 输出到 chat
- **错误处理**: IDE 通知 + 重试 1 次
- **来源**: TRAE CN 2026 指南

### IF-002: TRAE IDE Editor 接口

- **类型**: IDE API
- **端点**: TRAE file open / edit / save
- **交互**: 自动打开文件、显示 review 状态
- **来源**: TRAE IDE 特性

### IF-003: TRAE IDE Terminal 接口

- **类型**: IDE API
- **端点**: TRAE terminal panel
- **交互**: 跑测试、显示结果
- **来源**: TRAE IDE 特性

### IF-004: TRAE IDE Preview 接口

- **类型**: IDE API
- **端点**: TRAE preview panel
- **交互**: 打开 coverage.html
- **来源**: TRAE IDE 特性

### IF-005: GitHub / GitLab PR 接口

- **类型**: API
- **端点**: `POST /repos/:owner/:repo/pulls/:pr/comments`
- **交互**: 业务流 spec 自动附加到 PR
- **来源**: 现有 `.trae/skills/pr-creator`

---

## 6. 过渡需求

### TR-001: 从 0 到 1(IDE 内)

- **描述**: 业务流测试能力从无到有,在 IDE 中可触发
- **策略**:
  1. 实施基础设施(Week 1)
  2. 1 个示范场景在 IDE 中跑通(Week 2)
  3. PM/BA 试用,基于反馈优化(Week 3)
- **回滚方案**: 业务流目录独立,问题可独立停用

### TR-002: 1 到 5 业务域扩展

- **描述**: 5 个业务域测试
- **策略**: 业务对象 → 枚举 → 审计 → 导入导出 → 产品版本
- **回滚方案**: 每个域独立

### TR-003: IDE 工作流深度集成

- **描述**: 测试能力作为 IDE 核心功能
- **策略**:
  1. Phase 1: chat 触发可用
  2. Phase 2: IDE 通知 + 状态栏 + Review Actions
  3. Phase 3: 自动触发(代码保存时建议生成测试)
- **回滚方案**: 软提示 → 硬提示,渐进式

---

## 7. 约束与假设

### 7.1 技术约束

- **C-1**: MUST 沿用现有 22 个 Skill 体系,新 Skill 注册为 SK-022/023/024
- **C-2**: MUST 沿用现有 POM(`e2e/helpers/`)
- **C-3**: MUST 沿用现有 isolation 机制
- **C-4**: MUST 在 TRAE IDE 中完成所有用户交互(无独立 Web UI)
- **C-5**: MUST 沿用现有规则体系
- **C-6**: MUST 使用国内 LLM 模型(Qwen 3.5+)以符合数据合规要求

### 7.2 业务约束

- **B-1**: 测试触发 MUST 在 IDE chat 中(用户决策)
- **B-2**: Healer MUST 是 P0,人在回路(用户决策 + Skywork 实践)
- **B-3**: 业务断言 + DOM 断言混合(用户决策)
- **B-4**: AI 起草,人 review(用户决策)
- **B-5**: YAML 业务可读(用户决策)

### 7.3 假设

- **A-1**: TRAE IDE chat 可调用 Skill ✓(已确认)
- **A-2**: TRAE IDE 支持文件自动打开 + 编辑 ✓(已确认)
- **A-3**: TRAE IDE 支持 terminal panel 跑命令 ✓(TRAE 标准功能)
- **A-4**: TRAE IDE 支持 preview 打开 HTML ✓(TRAE 标准功能)
- **A-5**: 现有 561 YonDesign 单测保持稳定 ✓(已验证)
- **A-6**: TRAE IDE 支持多种 LLM 模型(Claude / GPT-5 / Gemini / Qwen / DeepSeek / Doubao 等),用户在每次对话前主动选择 ✓(TRAE 原生特性)
- **A-7**: TRAE IDE 支持自定义 slash command ✓(已确认)

---

## 8. 优先级与里程碑建议

### 8.1 优先级矩阵

| ID | 需求 | 优先级 | 原因 |
|----|------|--------|------|
| FR-001 | TRAE IDE Chat 触发 | Must (NEW) | 用户决策"融合在 AI Coding 中" |
| FR-002 | Planner Skill (IDE 中) | Must | 业务可读 |
| FR-003 | Generator Skill (IDE 中) | Must | IDE 中自动生成 |
| FR-004 | Healer Skill (IDE 中,人在回路) | Must | 用户决策 + 业界实践 |
| FR-005 | 业务规则抽取器 | Must | 基础数据 |
| FR-006 | Screenplay Task 框架 | Must | 业务流测试基础 |
| FR-007 | 业务断言库 | Must | 业务断言为主 |
| FR-008 | Business-flow YAML Schema | Must | IDE 校验 |
| FR-009 | 1 个示范场景 | Must | IDE 内可见效果 |
| FR-010 | AI 起草 + 人 review(IDE 按钮) | Must | 用户决策"AI 起草,人 review" |
| FR-011 | 5 业务域落地 | Should | 规模化 |
| FR-012 | 业务规则覆盖率追溯 | Should | IDE 中可视化 |
| FR-013 | Healer 边界(IDE 警告) | Must | 安全 |
| FR-014 | 多 Agent 端口隔离 | Should | IDE 后台 |
| FR-015 | IDE 工作流模板 | Should | 渐进取代 CLI |
| FR-016 | 业务流 spec 模板 | Must | IDE snippets |
| FR-017 | Healer 审计(IDE 可查) | Must | IDE 中可查 |
| FR-018 | 业务流 spec.md 模板 | Should | IDE snippets |
| FR-019 | 数据隔离(IDE 提示) | Must | 防污染 |
| FR-020 | Spec ↔ YAML 双向追溯(IDE) | Should | IDE 跳转 |
| FR-021 | 业务流测试目录 | Must | 隔离 |
| FR-022 | 业务流文档(IDE preview) | Should | IDE preview |
| FR-023 | 业务流测试数据推演(IDE 提示) | Should | 边界值 |
| FR-024 | 业务流性能基线(IDE 状态栏) | Should | IDE 状态栏 |
| NFR-001~009 | 综合质量 | Must/Should | 性能/成本/可靠性/可观测/安全/隔离/可参与性 |

### 8.2 建议里程碑(3 周路径)

| 里程碑 | 时间 | 范围 | 关键产出 |
|--------|------|------|---------|
| **M1 (Week 1)** | Day 1-3 | FR-005, FR-008, FR-016, FR-018 | 业务规则抽取器 + 45 个 `_business_rules/*.yaml` + business-flow.yaml Schema + IDE snippets |
| **M2 (Week 1-2)** | Day 4-7 | FR-006, FR-007, FR-019 | Screenplay Task 框架 + 业务断言库 + 数据隔离 |
| **M3 (Week 2)** | Day 8-10 | FR-001, FR-002, FR-003, FR-004, FR-009, FR-010, FR-013, FR-017 | **IDE 集成 P0**: chat 触发 + Planner/Generator/Healer 在 IDE 中可视化 + 1 个示范场景端到端 |
| **M4 (Week 3)** | Day 11-15 | FR-011, FR-012, FR-014, FR-015, FR-020, FR-021, FR-022, FR-023, FR-024, NFR | 5 业务域扩展 + 覆盖率报告(IDE preview)+ 双向追溯 + 性能基线(IDE 状态栏) |

### 8.3 关键依赖关系

```
FR-005 (规则抽取) → FR-008 (YAML Schema) → FR-016 (snippet) → FR-009 (示范)
                                                                ↓
FR-006 (Screenplay) + FR-007 (业务断言) ←───── FR-009 验证 ─────→ FR-002/003/004 (三 Skill)
                                                                ↓
                                              FR-001 (IDE chat 触发) ← 用户决策新增
                                                                ↓
                                              FR-011 (5 业务域扩展)
                                                                ↓
                                              FR-012/022 (IDE preview 报告)
```

---

## 9. 变更/设计提案 (RFC)

### 9.1 现状分析 (As-Is)

**现有架构**:
- **TRAE IDE** + 22 个 Skill(test-gen, playwright-cli-testing, problem-fixing 等)
- 用户在 IDE chat 中用自然语言触发
- 已有业务流测试能力: **仅支持单测和 E2E 生成,无业务流专门能力**

**现有痛点**:
1. **业务规则到测试 0% 派生**: 45 schema × 8 规则 = 360 业务规则,0 测试覆盖
2. **业务流测试 = 0**: 无跨页 E2E 业务场景
3. **Healer 缺失**: UI 变化导致的 73% 假阳性无修复
4. **PM/QA 参与度 0**: 业务流测试在 JS,PM 无法 review
5. **TRAE IDE 中缺业务流测试能力**: 用户需切到独立 CLI
6. **CLI 流程与 IDE 分离**: v1.0 Spec 假设有独立 Pipeline CLI,但 IDE 中无此入口

### 9.2 目标状态 (Target State)

**目标架构**(TRAE IDE 集成版):

```
┌────────────────────────────────────────────────────────────────────┐
│                         TRAE IDE                                    │
│                                                                     │
│  ┌─────────────┐   chat: "测一下业务对象"   ┌──────────────────┐  │
│  │   User      │ ◄─────────────────────────►│  TRAE Agent      │  │
│  │             │                            │  (in chat)        │  │
│  └─────────────┘                            └────────┬─────────┘  │
│                                                      │             │
│                                                      │ 触发 Skill  │
│                                                      ▼             │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │   .trae/skills/                                              │  │
│  │   - test-gen (SK-001)                                       │  │
│  │   - business-flow-planner (SK-022) [NEW]                   │  │
│  │   - business-flow-generator (SK-023) [NEW]                 │  │
│  │   - business-flow-healer (SK-024) [NEW]                    │  │
│  │   - playwright-cli-testing (SK-002)                       │  │
│  │   - problem-fixing (SK-005)                                │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │   IDE 内可视化                                              │  │
│  │   ┌──────────────┐ ┌──────────────┐ ┌──────────────┐      │  │
│  │   │ Editor       │ │ Terminal     │ │ Preview      │      │  │
│  │   │ (YAML/spec)  │ │ (跑测试)     │ │ (覆盖率)     │      │  │
│  │   └──────────────┘ └──────────────┘ └──────────────┘      │  │
│  │   ┌──────────────────────────────────────────────────┐      │  │
│  │   │ 状态栏: "🤖 业务流 3/8 通过"                     │      │  │
│  │   └──────────────────────────────────────────────────┘      │  │
│  └────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
                                ↓ (本地文件)
┌────────────────────────────────────────────────────────────────────┐
│   .trae/specs/<feat>/                                              │
│     ├── spec.md                                                    │
│     ├── business-flow.yaml  ← AI 起草,人在 IDE 中 review           │
│     └── _traceability/coverage.json                                │
│                                                                     │
│   e2e/business-flow/<feat>.spec.js                                 │
│   e2e/screenplay/tasks/*.js                                        │
└────────────────────────────────────────────────────────────────────┘
```

**关键变化**:
1. **TRAE IDE chat 作为唯一入口**(无独立 CLI)
2. **三个新 Skill 注册为 SK-022/023/024**
3. **IDE 内可视化**: Editor / Terminal / Preview / Status Bar
4. **人在回路**: Healer 修复需用户在 IDE 中点击确认
5. **业务断言为主,DOM 断言为辅**

### 9.3 详细设计

#### 9.3.1 FR-001 TRAE IDE Chat 触发(核心新增)

**触发场景**:

| 用户输入 | 触发 Skill | 备注 |
|---------|----------|------|
| "为 AppButton 写测试" | test-gen (SK-001) | 已有 |
| "测一下业务对象完整流程" | business-flow-planner (SK-022) | NEW |
| "业务流测试跑一下" | playwright-cli-testing (SK-002) | 已有 |
| "修复这个测试失败" | business-flow-healer (SK-024) | NEW |
| "派生出业务规则" | discover_business_rules (FR-005) | NEW |
| "/biz-test-full <feat>" | 完整流程(SK-022→023→002→024) | NEW |
| "schema 改了,重新派生" | discover_business_rules + planner | NEW |

**slash command 简写**(借鉴 trae-gstack):

```markdown
# .trae/skills/_TEMPLATE/SLASH_COMMANDS.md

| Command | Alias | 触发 |
|---------|-------|------|
| /test-gen | /tg | test-gen |
| /biz-test | /bt | business-flow-planner |
| /biz-test-full | /btf | 全流程 |
| /heal | /h | business-flow-healer |
| /biz-rules | /br | 业务规则抽取 |
| /biz-coverage | /bc | 覆盖率报告 |
| /biz-review | /brv | PM review YAML |
```

#### 9.3.2 FR-002 Planner Skill (IDE 集成)

**SKILL.md 关键新增**:
```yaml
---
name: business-flow-planner
description: Generate business-flow.yaml draft from spec.md and business rules. In TRAE IDE, the draft is opened in editor with review status banner. Invoke when user says "测一下 XXX 业务流" or "/biz-test XXX".
triggers:
  - "测一下 XXX 业务流"
  - "/biz-test XXX"
  - "/bt XXX"
---

# business-flow-planner

## 1. 必读上下文
- `.trae/rules/SESSION_REMINDER.md`
- `.trae/context/business-view.md`
- `meta/schemas/<object>.yaml`
- `.trae/specs/<feat>/spec.md`
- `.trae/specs/_business_rules/<object>.yaml`

## 2. Pipeline

### Stage 1: 输入验证
- 确认 spec.md 存在
- 确认目标 schema 存在
- 确认 _business_rules/<object>.yaml 存在

### Stage 2: 业务流生成
- 用 LLM(Qwen 3.5)读取 spec.md + business_rules.yaml
- 生成 7 节 YAML(actor/goal/preconditions/tasks/questions/data_tables/cleanup)
- tasks 字段: 业务原子动作(非 UI 操作)
- questions 字段: 业务断言(非 DOM 断言)

### Stage 3: IDE 集成(关键)
- 写入 `.trae/specs/<feat>/business-flow.yaml`
- 头部 banner:
  ```yaml
  # 🤖 AI Generated Draft - needs_pm_review: true
  # Review Actions: [Approve] [Request Changes] [Edit in IDE]
  # Generated by: business-flow-planner
  # Generated at: 2026-06-13T10:00:00Z
  review_status: draft
  agent_draft: true
  ```
- 触发 IDE 文件打开命令
- 在状态栏显示: "📋 Business Flow Draft Ready - business-object-lifecycle"
- 显示 review action 按钮

## 3. 输出
- `.trae/specs/<feat>/business-flow.yaml`
- IDE 中自动打开
```

#### 9.3.3 FR-003 Generator Skill (IDE 集成)

**SKILL.md 关键新增**:
```yaml
---
name: business-flow-generator
description: Generate Playwright E2E spec + Screenplay Task from reviewed business-flow.yaml. In TRAE IDE, generated files are auto-opened and tests are run in terminal panel.
triggers:
  - PM/BA approved YAML
  - "生成代码"
  - "/bt-continue"
---

# business-flow-generator

## 1. 必读上下文
- `.trae/specs/<feat>/business-flow.yaml` (must be review_status: approved or reviewed)
- `.trae/skills/business-flow-planner/SKILL.md` (依赖)

## 2. Pipeline

### Stage 1: 校验
- 检查 review_status != "draft"
- 检查 tasks/questions 字段

### Stage 2: 生成 Screenplay Task
- 遍历 tasks 字段,生成 e2e/screenplay/tasks/<TaskName>.js
- 业务原子动作,不是 UI 操作

### Stage 3: 生成 Playwright Spec
- 遍历 questions 字段,生成 e2e/business-flow/<feat>.spec.js
- 业务断言(70%) + DOM 断言(30%)

### Stage 4: IDE 集成(关键)
- 打开生成的 spec.js
- 写入 IDE 任务列表
- 触发 terminal panel 跑测试
- 显示进度

## 3. 输出
- `e2e/screenplay/tasks/<TaskName>.js`
- `e2e/business-flow/<feat>.spec.js`
- IDE 中自动打开 + 跑测试
```

#### 9.3.4 FR-004 Healer Skill (人在回路)

**SKILL.md 关键新增**:
```yaml
---
name: business-flow-healer
description: Analyze failed Playwright tests, suggest fixes via IDE dialog, apply only after user confirmation. CRITICAL: Never fix business assertion failures automatically.
triggers:
  - "测试失败"
  - "修复这个失败"
  - "/heal"
---

# business-flow-healer

## 1. 必读上下文
- `.trae/skills/healer/PERMISSIONS.md` (deny list)
- `.trae/state/healings.jsonl` (历史)

## 2. Pipeline

### Stage 1: 失败分析
- 解析 trace.zip
- 判断 root_cause: locator_drift / wait_timeout / data_mismatch / business_assertion

### Stage 2: 业务断言失败 → 不修复
- 如果 root_cause = business_assertion:
  - IDE 弹出: "❌ 业务断言失败 - 需要人工 review"
  - 显示业务语义错误
  - 选项: [查看业务规则] [跳转到相关业务流 YAML] [忽略]

### Stage 3: UI/数据问题 → 提议修复
- 如果 root_cause ∈ {locator_drift, wait_timeout, data_mismatch}:
  - 生成修复建议
  - IDE 弹出对话框:
    ```
    🔧 失败原因: locator 漂移
    建议修复: 将 '.el-button--primary' 替换为 role=button[name='保存']
    
    [Apply Fix]  [Edit Manually]  [Mark as Bug]  [Skip]
    ```
  - Apply Fix → 应用并重跑
  - Edit Manually → 打开 spec.js
  - Mark as Bug → 写入 fix_tasks.json
  - Skip → 标记为预期失败

### Stage 4: 修复日志
- 写入 `.trae/state/healings.jsonl`
- 含 trace_id / root_cause / fix_type / success

## 3. 输出
- IDE 修复对话框
- 修复后的 spec.js (经用户确认)
- healings.jsonl
```

#### 9.3.5 IDE 集成机制(核心)

**MCP 配置**(`.ai/mcp.json`):
```json
{
  "mcpServers": {
    "trae-ide": {
      "command": "trae-ide-mcp",
      "args": ["--port", "3020"],
      "capabilities": [
        "file_open",
        "file_edit",
        "terminal_run",
        "terminal_watch",
        "preview_html",
        "status_bar_set",
        "show_notification",
        "show_dialog"
      ]
    }
  }
}
```

**Agent 调用示例**(在 chat 中):
```javascript
// 当用户说"测一下业务对象"
// 1. 检测意图 → 触发 business-flow-planner
// 2. Planner 调用 MCP:
mcp.trae_ide.show_notification({
  type: 'info',
  title: '🤖 业务流 Planner',
  message: '正在生成 business-flow.yaml...'
});
mcp.trae_ide.status_bar_set({
  text: '🤖 Planning business flow...',
  progress: 0.3
});

// 3. 完成后:
mcp.trae_ide.file_open({
  path: '.trae/specs/business-object-lifecycle/business-flow.yaml'
});
mcp.trae_ide.status_bar_set({
  text: '📋 Business Flow Draft Ready',
  color: 'yellow'
});
mcp.trae_ide.show_notification({
  type: 'action',
  title: '📋 Business Flow Draft Ready',
  message: '请 review business-flow.yaml',
  actions: [
    { id: 'approve', label: 'Approve', primary: true },
    { id: 'edit', label: 'Edit in IDE' },
    { id: 'reject', label: 'Request Changes' }
  ]
});
```

#### 9.3.6 Screenplay 框架

**目录结构**:
```
e2e/screenplay/
├── actor.js              # Actor 封装
├── ability.js            # Ability 抽象
├── interactions/
│   ├── Click.js
│   ├── Fill.js
│   └── ...
├── tasks/
│   ├── BusinessObjectTasks.js
│   ├── RelationshipTasks.js
│   └── ...
├── questions/
│   ├── BusinessQuestions.js
│   ├── BusinessRuleAssertor.js
│   └── ...
└── index.js
```

**Actor 示例** (`e2e/screenplay/actor.js`):
```javascript
import { BrowseTheWeb, CallAPI, IsolateData } from './ability';

export class Actor {
  constructor(name, abilities = {}) {
    this.name = name;
    this.abilities = abilities;
  }

  static named(name) {
    return new Actor(name);
  }

  can(ability) {
    this.abilities[ability.constructor.name] = ability;
    return this;
  }

  abilityTo(abilityName) {
    return this.abilities[abilityName];
  }

  async attemptsTo(...tasks) {
    for (const task of tasks) {
      await task.performAs(this);
    }
  }

  async ask(question) {
    return await question.answeredBy(this);
  }
}

export const AdminActor = (page, helpers) => Actor.named('Admin')
  .can(BrowseTheWeb.with(page))
  .can(CallAPI.using(helpers.apiClient))
  .can(IsolateData.using(helpers.isolation));

export const ReadonlyActor = (page, helpers) => Actor.named('Readonly')
  .can(BrowseTheWeb.with(page))
  .can(CallAPI.using(helpers.apiClient));
```

**Task 示例** (`e2e/screenplay/tasks/BusinessObjectTasks.js`):
```javascript
import { Click, Fill } from '../interactions';
import { BusinessRuleAssertor } from '../questions/BusinessRuleAssertor';

export class CreateBusinessObjectWithKeyTemplate {
  static with({ name, serviceModule }) {
    return new CreateBusinessObjectWithKeyTemplate({ name, serviceModule });
  }

  constructor(params) {
    this.params = params;
  }

  async performAs(actor) {
    const page = actor.abilityTo('BrowseTheWeb').page();

    // 业务流: 列表 → 新建 → 填写 → 验证自动编码 → 保存
    await page.goto('/business-object/list');
    await Click.on('[data-testid="new-business-object"]').performAs(actor);
    await Fill.the('name').with(this.params.name).performAs(actor);

    // 验证 key_template 自动填充(业务断言而非 UI 断言)
    const code = await page.inputValue('[data-testid="code"]');
    const expectedCode = `${this.params.serviceModule.code}01`;  // SEQ:2
    if (!code.startsWith(expectedCode.slice(0, -2))) {
      throw new Error(`key_template 自动编码失败: 期望 ${expectedCode}, 实际 ${code}`);
    }

    await Click.on('[data-testid="save"]').performAs(actor);

    return { code, name: this.params.name };
  }
}
```

**Question/BusinessRuleAssertor 示例** (`e2e/screenplay/questions/BusinessRuleAssertor.js`):
```javascript
export class BusinessRuleAssertor {
  static async assertRule(ruleId, context = {}) {
    const rule = await this.loadRule(ruleId);

    switch (rule.type) {
      case 'deletability':
        return await this.assertDeletability(rule, context);
      case 'key_template':
        return await this.assertKeyTemplate(rule, context);
      case 'cascade_select':
        return await this.assertCascadeSelect(rule, context);
      case 'authorization':
        return await this.assertAuthorization(rule, context);
      case 'audit':
        return await this.assertAudit(rule, context);
      default:
        throw new Error(`Unknown rule type: ${rule.type}`);
    }
  }

  static async assertDeletability(rule, { businessObject, apiClient }) {
    // 业务断言: 检查"存在关联关系的业务对象不能删除"
    const relations = await apiClient.get(`/business-object/${businessObject.id}/relations`);

    if (relations.length === 0) {
      return {
        valid: true,
        message: '无关联关系,可删除'
      };
    } else {
      return {
        valid: false,
        message: `存在 ${relations.length} 条关联,不允许删除`,
        ruleMessage: rule.message  // "存在关联关系的业务对象不能删除"
      };
    }
  }

  static async loadRule(ruleId) {
    const index = await this.loadIndex();
    return index.find(r => r.id === ruleId);
  }

  static async loadIndex() {
    const fs = require('fs').promises;
    const path = require('path');
    const content = await fs.readFile(
      path.join(process.cwd(), '.trae/specs/_business_rules/_index.json'),
      'utf-8'
    );
    return JSON.parse(content);
  }
}
```

#### 9.3.7 IDE 代码片段

**`.vscode/business-flow.code-snippets`**:
```json
{
  "business-flow-actor": {
    "prefix": "screenplay-actor",
    "body": [
      "import { Actor } from './actor';",
      "import { BrowseTheWeb } from './ability';",
      "",
      "export const ${1:Admin}Actor = (page, helpers) =>",
      "  Actor.named('${1:Admin}')",
      "    .can(BrowseTheWeb.with(page))",
      "    .can(CallAPI.using(helpers.apiClient));"
    ],
    "description": "Screenplay Actor 模板"
  },
  "business-flow-task": {
    "prefix": "screenplay-task",
    "body": [
      "import { Click, Fill } from '../interactions';",
      "",
      "export class ${1:TaskName} {",
      "  static with(params) { return new ${1:TaskName}(params); }",
      "  constructor(params) { this.params = params; }",
      "  async performAs(actor) {",
      "    ${2:// 业务原子动作}",
      "  }",
      "}"
    ],
    "description": "Screenplay Task 模板"
  },
  "biz-assert": {
    "prefix": "biz-assert",
    "body": [
      "await BusinessRuleAssertor.assertRule('${1:rule-id}', {",
      "  ${2:// context}",
      "});"
    ],
    "description": "业务断言模板"
  },
  "business-flow-template": {
    "prefix": "business-flow-template",
    "body": [
      "# 🤖 AI Generated Draft - needs_pm_review: ${1|true,false|}",
      "# Generated by: ${2:business-flow-planner}",
      "# Generated at: ${3:2026-06-13T10:00:00Z}",
      "review_status: ${4|draft,reviewed,approved|}",
      "agent_draft: ${5|true,false|}",
      "",
      "actor: ${6:Admin}",
      "goal: ${7:业务目标}",
      "",
      "preconditions:",
      "  - ${8:前置条件}",
      "",
      "tasks:",
      "  - id: ${9:T_BIZ_001}",
      "    title: ${10:任务标题}",
      "    params:",
      "      ${11:// params}",
      "",
      "questions:",
      "  - ruleId: ${12:BR-xxx}",
      "    expected: ${13:// expected}",
      "    context:",
      "      ${14:// context}",
      "",
      "data_tables:",
      "  ${15:// 测试数据}",
      "",
      "cleanup:",
      "  ${16:// 清理策略}"
    ],
    "description": "business-flow.yaml 模板"
  }
}
```

### 9.4 备选方案

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| A: 独立 Pipeline CLI (v1.0) | 可在 CI 跑 | 与 IDE 分离,用户需切上下文 | Rejected (用户决策"融合在 AI Coding") |
| B: TRAE IDE Chat 触发 (v2.0) | 一等公民,零切换 | 需 IDE API 支持 | **Selected** |
| C: Web UI 中转 | 可视化好 | 又是独立界面 | Rejected |
| D: 只 IDE 触发,无 CI | 简单 | 失去 CI 集成 | Rejected (保留 CI 能力,只是触发在 IDE) |
| E: 国内 LLM (Qwen 3.5) | 成本低、中文友好、合规 | 国际化场景弱 | **Selected** (用户决策"国内模型") |
| F: Claude / GPT-4o | 质量高 | 成本高、合规风险 | Rejected |

### 9.5 实施与迁移计划

#### 9.5.1 实施顺序(3 周)

**Week 1 - 基础设施**:
- Day 1-2: FR-005 业务规则抽取器
- Day 3-4: FR-008 YAML Schema + IDE 关联
- Day 5-7: FR-006/007 Screenplay + 业务断言 + IDE snippets

**Week 2 - 三 Skill + IDE 集成**:
- Day 8-9: FR-001 TRAE IDE chat 触发 + slash commands
- Day 10-11: FR-002/003 Planner + Generator + IDE 可视化
- Day 12: FR-004 Healer (人在回路)
- Day 13-14: FR-009 1 个示范场景(业务对象)

**Week 3 - 规模化 + 可视化**:
- Day 15-17: FR-011 5 业务域扩展
- Day 18-19: FR-012/022 覆盖率报告(IDE preview)
- Day 20: FR-013/017 Healer 警告 + 审计(IDE 可查)
- Day 21-22: FR-019/023/024 数据隔离 + 数据推演 + 性能基线
- Day 23-25: NFR-001~009 验证

#### 9.5.2 风险缓解

| 风险 | 概率 | 影响 | 缓解策略 |
|------|------|------|---------|
| TRAE IDE API 限制 | 中 | 高 | 先在 MCP 层封装,IDE API 变化时只改 MCP server |
| Healer 修复引入 bug | 中 | 高 | 人在回路 + 业务断言不修复 + 修复日志全审计 |
| LLM 成本失控 | 中 | 中 | 监控 + 单 spec 预算 ¥3.5 + IDE 状态栏实时显示 |
| PM/QA 不愿 review | 中 | 高 | IDE 内 review 按钮 + review checklist + 状态栏常驻 |
| 业务流测试太慢 | 中 | 中 | IDE 状态栏显示进度 + 优先用 API + UI 混合 |
| 国内 LLM 能力不足 | 低 | 中 | Qwen 3.5 已达 GPT-4 水平,关键路径可双模型 |
| TRAE chat 与 Skill 协议 | 低 | 中 | 沿用 trae-gstack 模式 + 协议简单 |

#### 9.5.3 测试策略

- **单元测试**: discover_business_rules.py、BusinessRuleAssertor、Healer strategies
- **集成测试**: Planner → Generator → IDE 可视化端到端
- **E2E 测试**: 业务对象生命周期(在 IDE 中跑)

#### 9.5.4 回滚方案

- 业务流目录独立 `e2e/business-flow/`,失败不影响现有
- Skill 独立注册 SK-022/023/024,失败可单独禁用
- IDE MCP 配置独立,失败可关闭 MCP

---

## 10. TBD 清单

| ID    | Item | 缺失信息 | 下一步 |
|-------|------|----------|--------|
| TBD-1 | TRAE IDE MCP API 完整签名 | 已确认支持基础接口(2026-06-13) | Week 1 Day 1 完整对接 |
| TBD-2 | slash command 在 TRAE 中的注册方式 | 已确认支持(2026-06-13) | Week 1 验证完整语法 |
| TBD-3 | LLM 模型选型(Qwen 3.5 vs Qwen-Max) | 用户决策"国内模型" | Week 1 选型测试,优先 Qwen 3.5 |
| TBD-4 | IDE 通知的 UI 形式(Toast / 状态栏 / 弹窗) | UX 验证 | Week 2 试 |
| TBD-5 | Healer 修复的细粒度(a11y tree 回退) | 实际修复率 | Week 2 Healer 实施时 A/B |
| TBD-6 | 业务规则覆盖率目标(80% / 90%) | 实际可达成性 | Week 3 调整 |
| TBD-7 | 业务断言 vs DOM 断言比例(70/30 / 80/20) | 实际可观测性 | Week 3 调整 |
| TBD-8 | CI 集成方式(IDE 触发后是否同步 CI) | CI 现状 | Week 3 决定 |
| TBD-9 | 业务流 spec 触发时机(PR / push / nightly) | CI 时长 | Week 3 决定 |
| TBD-10 | TRAE chat 自然语言理解的准确率 | 实际误识别率 | Week 2-3 收集 |

---

## 附录 A: 文件清单

实施本 Spec 需要创建/修改的文件:

### 新建 Skill 目录

```
.trae/skills/
├── business-flow-planner/
│   ├── SKILL.md
│   ├── PROMPT_TEMPLATE.md
│   └── OUTPUT_SPEC.md
├── business-flow-generator/
│   ├── SKILL.md
│   ├── PROMPT_TEMPLATE.md
│   └── OUTPUT_SPEC.md
└── business-flow-healer/
    ├── SKILL.md
    ├── PROMPT_TEMPLATE.md
    └── OUTPUT_SPEC.md
```

### 新建脚本

```
.trae/scripts/
├── discover_business_rules.py        # FR-005
├── coverage_report.py                 # FR-012
└── mcp_ide_server.py                  # FR-001 IDE 集成
```

### 新建 Schema/模板

```
.trae/specs/templates/
├── business-flow.template.yaml        # FR-008
├── business-flow.schema.json          # FR-008
└── spec-business-flow.template.md     # FR-018
```

### 新建 E2E 框架

```
e2e/screenplay/
├── actor.js
├── ability.js
├── interactions/
├── tasks/
├── questions/
│   ├── BusinessQuestions.js
│   └── BusinessRuleAssertor.js
└── index.js

e2e/business-flow/                     # 业务流 E2E(独立于 features/)
```

### 新建 IDE 配置

```
.vscode/
├── business-flow.code-snippets        # FR-006/016 snippets
└── settings.json                       # YAML schema 关联
```

### 新建业务规则文件

```
.trae/specs/_business_rules/           # 45 个 schema 派生
├── _index.json
├── business_object.yaml
├── relationship.yaml
├── service_module.yaml
├── domain.yaml
├── sub_domain.yaml
├── product.yaml
├── version.yaml
├── enum_type.yaml
├── enum_value.yaml
├── user.yaml
├── user_group.yaml
├── permission.yaml
├── audit_log.yaml
├── change_event.yaml
└── ... (45 个)
```

### 新建追溯文件

```
.trae/specs/_traceability/
└── coverage.json
```

### 状态文件(已存在,扩展)

```
.trae/state/
├── agent-runs.jsonl                   # 现有,扩展
├── healings.jsonl                     # 新建(FR-017)
└── coverage.html                      # 新建(FR-022)
```

### 演示场景

```
.trae/specs/business-object-lifecycle/
├── spec.md                            # 现有,用作输入
├── business-flow.yaml                 # FR-009 AI 起草
└── _traceability.json
```

---

## 附录 B: 关键路径文件链接

实施时需优先读取的项目现有资产:

- [Skills INDEX](file:///d:/filework/excel-to-diagram/.trae/skills/INDEX.md) - 22 个 Skill 注册表
- [Context INDEX](file:///d:/filework/excel-to-diagram/.trae/context/INDEX.md) - 120+ Context 文档
- [Healer PERMISSIONS](file:///d:/filework/excel-to-diagram/.trae/skills/healer/PERMISSIONS.md) - Healer 边界
- [test-gen SKILL](file:///d:/filework/excel-to-diagram/.trae/skills/test-gen/SKILL.md) - 现有 test-gen 范式
- [playwright-cli-testing](file:///d:/workplace/.trae/skills/playwright-cli-testing/SKILL.md) - 现有 E2E 范式
- [test-gen OUTPUT_SPEC](file:///d:/filework/excel-to-diagram/.trae/skills/test-gen/OUTPUT_SPEC.md) - 测试输出规范
- [auto-fixtures](file:///d:/filework/excel-to-diagram/e2e/helpers/auto-fixtures.js) - E2E 数据隔离
- [business_object.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/business_object.yaml) - 业务对象 schema(最丰富)
- [SESSION_REMINDER](file:///d:/filework/excel-to-diagram/.trae/rules/SESSION_REMINDER.md) - 全局规则入口
- [multi-agent-coordination](file:///d:/filework/excel-to-diagram/.trae/rules/multi-agent-coordination.md) - 多 Agent 协作

---

## Spec + RFC 完整性自检

✅ **Spec 包含 10 个章节**: 背景与目标 / 需求类型概览 / 功能需求 / 非功能需求 / 外部接口需求 / 过渡需求 / 约束与假设 / 优先级与里程碑建议 / 变更设计提案 (RFC) / TBD 清单
✅ **最后一节**: TBD 清单(10 项)
✅ **FR 总数**: 24 个(FR-001~FR-024)
✅ **NFR 总数**: 9 个(NFR-001~NFR-009)
✅ **IF 总数**: 5 个(IF-001~IF-005)
✅ **TR 总数**: 3 个(TR-001~TR-003)
✅ **RFC 包含**: As-Is / Target State / Detailed Design / Alternatives / Implementation Plan / Risk / Testing / Rollback

**关键修订对比**:

| 维度 | v1.0 | v2.0 |
|------|------|------|
| 触发方式 | Pipeline CLI | **TRAE IDE chat + slash command** |
| 入口 | 独立 CLI | **chat 中自然语言** |
| 可视化 | HTML 报告 | **IDE Editor + Terminal + Preview + Status Bar** |
| Healer | 自动修复 | **人在回路,等用户确认** |
| PM review | Git 流程 | **IDE 内 review 按钮** |
| 进度跟踪 | 日志 | **IDE 状态栏实时显示** |
| 错误展示 | 堆栈 | **IDE 通知 + 业务语义** |
| LLM 模型 | Claude/GPT-4o | **用户每次对话前自选(TRAE 原生切换),系统不锁定** |
| 多 Agent | AGENT_PORT 隔离 | **IDE 后台 + 状态栏显示** |

---

## 关联研究来源

本 Spec 设计与以下 2026 年 5-6 月 AI Coding 最佳实践深度对齐:

- [Trae CN 2026 完全指南](https://blog.csdn.net/the_finals/article/details/161893557)
- [Trae Power Workflow (Skywork)](https://skywork.ai/blog/trae-power-workflow-how-i-automated-code-%E2%86%92-format-%E2%86%92-test-%E2%86%92-commit-without-writing-a-single-config/)
- [@xdmjun/trae-gstack](https://www.npmjs.com/package/@xdmjun/trae-gstack)
- [Advanced Usage of Cursor and Trae (QubitTool)](https://qubittool.com/en/blog/cursor-trae-advanced-prompting-guide)
- [AI-Powered Automated Issue Resolution (Trae SWE-bench 70.6%)](https://www.zenml.io/llmops-database/ai-powered-automated-issue-resolution-achieving-state-of-the-art-performance-on-swe-bench)
- [Mastering AI Coding Systems (AI-Void 2026-05)](https://media.aivoid.dev/pdfs/mastering-ai-coding-systems-from-copilots-to-agents_20260504180410.pdf)
- [Best practices for using AI in VS Code](https://code.visualstudio.com/docs/copilot/best-practices)
- [20 Battle-Tested Prompts for developers in 2026](https://chatgptaihub.com/20-battle-tested-prompts-for-developers-in-2026/)
- [AI驱动测试用例生成革命 (CSDN 2026 奇点大会)](https://blog.csdn.net/ProceChat/article/details/160956843)
