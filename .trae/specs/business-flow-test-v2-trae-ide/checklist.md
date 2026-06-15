# Checklist: 业务流 E2E 测试智能生成系统 v2.0

> **关联 Spec**: [spec.md](./spec.md)
> **关联 Tasks**: [tasks.md](./tasks.md)
> **总条目数**: 80+ 个验收点
> **最后更新**: 2026-06-13

---

## 1. 功能需求验收

### FR-001: TRAE IDE Chat 触发 ✓

- [ ] chat: "为 AppButton 写测试" → test-gen 触发
- [ ] chat: "测一下业务对象完整流程" → business-flow-planner 触发
- [ ] chat: "跑测试" → playwright-cli-testing 触发
- [ ] chat: "修复这个失败" → business-flow-healer 触发
- [ ] chat: "派生出业务规则" → discover_business_rules 触发
- [ ] chat: "schema 改了,重新派生" → discover + planner
- [ ] slash command `/test-gen` 工作
- [ ] slash command `/biz-test` 工作
- [ ] slash command `/biz-test-full` 工作
- [ ] slash command `/heal` 工作
- [ ] slash command `/biz-rules` 工作
- [ ] slash command `/biz-coverage` 工作
- [ ] slash command `/biz-review` 工作

**验收**: 13 个 chat/slash 触发点全部生效

---

### FR-002: Planner Skill (IDE 中) ✓

- [ ] chat 触发后 Planner 自动调用
- [ ] 读取 spec.md 成功
- [ ] 读取业务规则 YAML 成功
- [ ] 调用 Qwen 3.5 生成 business-flow.yaml
- [ ] YAML 头部 banner 正确
- [ ] `review_status: draft` 正确
- [ ] `agent_draft: true` 正确
- [ ] YAML 7 节结构完整
- [ ] tasks 字段是业务原子动作(非 UI 操作)
- [ ] questions 字段是业务断言(非 DOM 断言)
- [ ] IDE 自动打开文件
- [ ] IDE 状态栏显示 "📋 Business Flow Draft Ready"
- [ ] IDE 通知 + Review Actions 按钮
  - [ ] Approve 按钮
  - [ ] Edit in IDE 按钮
  - [ ] Request Changes 按钮
- [ ] Approve → 自动设 `review_status: approved`
- [ ] Approve → 触发 Generator
- [ ] Reject → 进入 chat 反馈循环

**验收**: 16 个验收点全部通过

---

### FR-003: Generator Skill (IDE 中) ✓

- [ ] 只接受 `review_status != "draft"` 的 YAML
- [ ] 校验 tasks/questions 字段必填
- [ ] 遍历 tasks 字段生成 Screenplay Task 类
- [ ] 遍历 questions 字段生成业务断言
- [ ] 生成 `e2e/screenplay/tasks/<TaskName>.js`
- [ ] 生成 `e2e/business-flow/<feat>.spec.js`
- [ ] 业务断言占 ≥ 70%
- [ ] DOM 断言占 ≤ 30%
- [ ] IDE 自动打开 spec.js
- [ ] IDE 任务列表显示
- [ ] IDE 终端面板跑测试
- [ ] 实时进度显示
- [ ] 失败 trace 可点击查看

**验收**: 13 个验收点全部通过

---

### FR-004: Healer Skill (人在回路) ✓ ✓ (P0)

- [ ] 测试失败时 IDE 弹出对话框
- [ ] 显示失败原因(locator 漂移/wait 超时/数据不匹配/业务断言)
- [ ] 显示建议修复(diff)
- [ ] Apply Fix 按钮
- [ ] Edit Manually 按钮
- [ ] Mark as Bug 按钮
- [ ] Skip 按钮
- [ ] Apply Fix → 自动应用并重跑
- [ ] Edit Manually → 打开 spec.js
- [ ] Mark as Bug → 写入 fix_tasks.json
- [ ] Skip → 标记为预期失败
- [ ] **业务断言失败 → 不弹出修复建议**
- [ ] 业务断言失败 → 显示业务语义错误
- [ ] 业务断言失败 → 要求人工 review

**验收**: 14 个验收点全部通过(其中 P0 项必须)

---

### FR-005: 业务规则抽取器 ✓

- [ ] chat: "派生出业务规则" → 自动运行脚本
- [ ] chat: "schema 改了,重新派生" → 自动重跑
- [ ] `.trae/scripts/discover_business_rules.py` 存在
- [ ] 解析 9 种规则类型:
  - [ ] deletability
  - [ ] key_template
  - [ ] cascade_select
  - [ ] authorization
  - [ ] audit
  - [ ] aspect
  - [ ] cascade_delete
  - [ ] owner
  - [ ] filter_variant
- [ ] 输出 45 个 `_business_rules/<object>.yaml`
- [ ] 每个 YAML 含 5-15 条规则
- [ ] 生成 `_index.json` 索引
- [ ] 单元测试 10+ 通过
- [ ] IDE 通知"已派生 N 条业务规则"
- [ ] IDE 显示 diff(对比上次)

**验收**: 13 个验收点全部通过

---

### FR-006: Screenplay Task 框架 ✓

- [ ] `e2e/screenplay/actor.js` 存在
- [ ] `Actor` 类实现 (named / can / abilityTo / attemptsTo / ask)
- [ ] `AdminActor` 工厂
- [ ] `ReadonlyActor` 工厂
- [ ] `BusinessAnalystActor` 工厂
- [ ] `e2e/screenplay/ability.js` 存在
- [ ] `BrowseTheWeb` ability
- [ ] `CallAPI` ability
- [ ] `IsolateData` ability
- [ ] `e2e/screenplay/interactions/` 目录
  - [ ] Click.js
  - [ ] Fill.js
  - [ ] Hover.js
  - [ ] Wait.js
  - [ ] Select.js
- [ ] `e2e/screenplay/tasks/` 目录
  - [ ] BusinessObjectTasks.js
  - [ ] RelationshipTasks.js
  - [ ] EnumTypeTasks.js
  - [ ] AuditLogTasks.js
- [ ] IDE snippet `screenplay-actor` 工作
- [ ] IDE snippet `screenplay-task` 工作
- [ ] 单元测试通过

**验收**: 16 个验收点全部通过

---

### FR-007: 业务断言库 ✓

- [ ] `BusinessRuleAssertor.js` 存在
- [ ] `assertRule(ruleId, context)` 入口
- [ ] `assertDeletability` 实现
- [ ] `assertKeyTemplate` 实现
- [ ] `assertCascadeSelect` 实现
- [ ] `assertAuthorization` 实现
- [ ] `assertAudit` 实现
- [ ] `loadRule` 从 `_index.json` 加载
- [ ] 错误信息含**业务语义**(非"DOM 文本不匹配")
- [ ] `BusinessQuestions.js` 存在
- [ ] IDE snippet `biz-assert` 工作
- [ ] IDE 问题面板显示业务错误(非堆栈)
- [ ] 单元测试通过

**验收**: 13 个验收点全部通过

---

### FR-008: Business-flow YAML Schema (IDE) ✓

- [ ] `.trae/specs/templates/business-flow.template.yaml` 存在
- [ ] 7 节结构: actor / goal / preconditions / tasks / questions / data_tables / cleanup
- [ ] 含占位符 + 示例
- [ ] `.trae/specs/templates/business-flow.schema.json` 存在
- [ ] JSON Schema 校验
- [ ] 字段类型定义
- [ ] required/optional 标注
- [ ] `.vscode/settings.json` 关联
- [ ] IDE 字段错时显示红线
- [ ] IDE 自动补全

**验收**: 10 个验收点全部通过

---

### FR-009: 1 个示范场景 (业务对象) ✓

- [ ] `.trae/specs/business-object-lifecycle/spec.md` 存在
- [ ] `.trae/specs/business-object-lifecycle/business-flow.yaml` 存在
- [ ] YAML 标注 `review_status: approved`
- [ ] 业务规则覆盖:
  - [ ] deletability (删除有关系的对象应失败)
  - [ ] key_template (新建时 code 自动填充)
  - [ ] cascade_select (域-子域-服务模块级联)
- [ ] 跨页面 ≥ 3:
  - [ ] 列表
  - [ ] 详情
  - [ ] 关系编辑
  - [ ] 删除确认
- [ ] 业务断言 ≥ 5
- [ ] DOM 断言 ≤ 2
- [ ] chat 触发 "测一下业务对象完整流程" 跑通
- [ ] Planner → YAML → IDE 打开
- [ ] PM Approve → Generator → spec.js
- [ ] 跑测试 100% pass
- [ ] Healer 模拟修复 1 次(locator 漂移)

**验收**: 14 个验收点全部通过

---

### FR-010: AI 起草 + 人 review (IDE 按钮) ✓

- [ ] YAML 草稿生成后 IDE 通知
- [ ] IDE 状态栏显示
- [ ] IDE Review Actions 按钮
- [ ] PM 可在 IDE 编辑器中修改 YAML
- [ ] 修改后点击 Save & Approve → 触发 Generator
- [ ] chat 中对话修改(多轮)
- [ ] review_status 三态: draft / reviewed / approved
- [ ] Generator 只接受 reviewed/approved

**验收**: 8 个验收点全部通过

---

### FR-011: 5 业务域落地 ✓

- [ ] 业务对象 (1 示范 + 扩展)
- [ ] 枚举管理:
  - [ ] enum-type-list.spec.js
  - [ ] enum-value-crud.spec.js
  - [ ] (3 个场景)
- [ ] 审计日志:
  - [ ] audit-log.spec.js
  - [ ] (3 个场景)
- [ ] 导入导出:
  - [ ] batch-export-import.spec.js
  - [ ] (3 个场景)
- [ ] 产品版本:
  - [ ] product-version.spec.js
  - [ ] (3 个场景)
- [ ] 每个域 ≥ 3 场景
- [ ] 共 ≥ 15 跨页 E2E
- [ ] 业务规则覆盖每个域 ≥ 5 条核心规则

**验收**: 9 个验收点全部通过

---

### FR-012: 业务规则覆盖率追溯 (IDE preview) ✓

- [ ] `.trae/scripts/coverage_report.py` 存在
- [ ] 读取 `_business_rules/_index.json`
- [ ] 解析 spec.js 中的 `BusinessRuleAssertor.assertRule` 调用
- [ ] 计算业务规则覆盖率
- [ ] 找出未覆盖规则
- [ ] 生成 `.trae/state/coverage.html`
- [ ] 生成 `.trae/state/coverage.md`
- [ ] chat: "看业务覆盖率" → IDE preview 打开
- [ ] 报告含覆盖率图
- [ ] 报告含未覆盖规则列表
- [ ] 报告含修复建议

**验收**: 11 个验收点全部通过

---

### FR-013: Healer 边界 (IDE 警告) ✓

- [ ] 检测到安全模块 → IDE 弹出红色警告
- [ ] 警告文案: "⚠️ authService 模块不允许自动修复"
- [ ] 显示 "请人工 review"
- [ ] 检查 `healer/PERMISSIONS.md` deny list
- [ ] 修复日志记录 "denied: module=xxx"

**验收**: 5 个验收点全部通过

---

### FR-014: 多 Agent 端口隔离 ✓

- [ ] AGENT_PORT 3010-3019 范围
- [ ] Planner → 3010
- [ ] Generator → 3011
- [ ] Healer → 3012
- [ ] IDE 后台运行
- [ ] IDE 状态栏显示当前活跃 Agent

**验收**: 6 个验收点全部通过

---

### FR-015: IDE 工作流模板 ✓

- [ ] chat: `/biz-test-full <feat>` 触发完整流程
- [ ] Step 1: 业务规则抽取 → 进度可见
- [ ] Step 2: Planner 生成 → 状态可见
- [ ] Step 3: PM Review → 等待交互
- [ ] Step 4: Generator 生成 → 状态可见
- [ ] Step 5: 跑测试 → 实时进度
- [ ] Step 6: Healer → 等待用户决定
- [ ] 全流程可视化(无 CLI 黑盒)

**验收**: 8 个验收点全部通过

---

### FR-016: 业务流 spec 模板 (IDE snippets) ✓

- [ ] `.vscode/business-flow.code-snippets` 存在
- [ ] `business-flow-template` snippet
- [ ] `spec-business-flow` snippet
- [ ] `screenplay-actor` snippet
- [ ] `screenplay-task` snippet
- [ ] `biz-assert` snippet
- [ ] 输入 prefix 触发补全

**验收**: 7 个验收点全部通过

---

### FR-017: Healer 审计 (IDE 可查) ✓

- [ ] `.trae/state/healings.jsonl` 写入
- [ ] 含 trace_id
- [ ] 含 root_cause
- [ ] 含 fix_type
- [ ] 含 success
- [ ] chat: "看 healer 历史" → IDE 显示
- [ ] 表格列: time / spec / root_cause / fix_strategy / status

**验收**: 7 个验收点全部通过

---

### FR-018: 业务流 spec.md 模板 (IDE snippets) ✓

- [ ] `.trae/specs/templates/spec-business-flow.template.md` 存在
- [ ] 含业务背景 / 涉众 / 业务规则 / 关键场景 / 边界条件 / 验收标准
- [ ] IDE snippet `spec-business-flow` 工作

**验收**: 3 个验收点全部通过

---

### FR-019: 数据隔离 (IDE 提示) ✓

- [ ] 沿用 `e2e/helpers/auto-fixtures.js`
- [ ] 测试前 IDE 提示"将创建测试数据(自动清理)"
- [ ] 测试后 IDE 通知"已清理 X 条数据"
- [ ] 跑测试后 DB 无 `e2e_*` 残留
- [ ] 30 天清理(复用 prune_agent_logs.py)

**验收**: 5 个验收点全部通过

---

### FR-020: 业务流 Spec ↔ YAML 双向追溯 (IDE) ✓

- [ ] spec.md 头部 `## business_flow: ...`
- [ ] scenario-id 注释
- [ ] 打开 spec.md → IDE 显示关联 yaml + spec.js
- [ ] 可点击跳转
- [ ] 反向追溯: spec.js → yaml → spec.md

**验收**: 5 个验收点全部通过

---

### FR-021: 业务流测试目录规范 ✓

- [ ] `e2e/business-flow/` 目录存在
- [ ] 业务流 E2E 全部在此目录
- [ ] 与 `e2e/features/` 并存
- [ ] IDE 中显示目录树
- [ ] `e2e/README.md` 更新

**验收**: 5 个验收点全部通过

---

### FR-022: 业务流文档生成 (IDE preview) ✓

- [ ] `.trae/state/coverage.html` 生成
- [ ] chat: "生成覆盖率报告" → IDE preview 打开
- [ ] 含场景覆盖
- [ ] 含 Healer 修复率
- [ ] 含业务规则覆盖率

**验收**: 5 个验收点全部通过

---

### FR-023: 业务流测试数据推演 (IDE 提示) ✓

- [ ] Planner 增加数据推演逻辑
- [ ] 读取 schema 字段约束(pattern / min / max)
- [ ] 生成有效/无效数据各 1 套
- [ ] 边界值自动识别
- [ ] 失败时给出违反的规则名
- [ ] chat: "测一下边界值" → AI 推演
- [ ] IDE 通知显示边界数据
- [ ] 用户确认 → 应用

**验收**: 8 个验收点全部通过

---

### FR-024: 业务流性能基线 (IDE 状态栏) ✓

- [ ] 测试运行时 IDE 状态栏显示
- [ ] 显示格式: "⏱ 5.2s | ¥0.12 | 8 scenarios"
- [ ] 跑完显示: "✅ 5.2s | ¥0.12 | 8/8 passed"
- [ ] `agent-runs.jsonl` 扩展字段
  - [ ] `duration_ms`
  - [ ] `cost_cny`
  - [ ] `scenarios_count`

**验收**: 7 个验收点全部通过

---

## 2. 非功能需求验收

### NFR-001: 性能 ✓

- [ ] IDE chat 响应 < 3s(简单 Skill 触发)
- [ ] 复杂流程 < 5min

**验收**: 性能指标达标

---

### NFR-002: 成本 ✓

- [ ] 单 spec LLM 成本 < ¥3.5
- [ ] `agent-runs.jsonl` 含 `cost_cny` 字段
- [ ] IDE 状态栏实时显示

**验收**: 成本指标达标

---

### NFR-003: 可靠性 ✓

- [ ] Healer 对 DOM 漂移修复成功率 ≥ 60%
- [ ] `healings.jsonl` success 比率 ≥ 0.6

**验收**: 可靠性指标达标

---

### NFR-004: 业务规则覆盖率 ✓

- [ ] 业务规则派生测试覆盖 ≥ 80%
- [ ] `coverage.json` 报告生成

**验收**: 覆盖率 ≥ 80%

---

### NFR-005: 可观测性 (IDE 内) ✓

- [ ] 所有 Agent 调用在 IDE 状态栏可见
- [ ] 所有 Agent 调用在 IDE 终端面板可见
- [ ] 状态变化实时反映

**验收**: 9 个 NFR 全部达标

---

### NFR-006: 安全性 ✓

- [ ] Healer 修复前检查 `healer/PERMISSIONS.md`
- [ ] 安全模块 deny 自动修复
- [ ] IDE 红色警告
- [ ] `healings.jsonl` 记录 denied

**验收**: 安全约束生效

---

### NFR-007: 数据隔离 ✓

- [ ] 业务流测试不污染生产 DB
- [ ] auto-fixtures cleanup 工作
- [ ] 30 天后清理

**验收**: 无 DB 污染

---

### NFR-008: 多 Agent 隔离 (IDE 后台) ✓

- [ ] Planner/Generator/Healer 并行
- [ ] AGENT_PORT 3010-3019 隔离
- [ ] 各自 `agent-runs.jsonl` 独立
- [ ] IDE 状态栏显示活跃 Agent

**验收**: 多 Agent 不冲突

---

### NFR-009: PM/QA 可参与性 (IDE 内) ✓

- [ ] 100% 业务流场景有 YAML 草稿
- [ ] YAML `agent_draft=true` 标注完整
- [ ] IDE review 完成率 ≥ 60%
- [ ] PM 可直接在 IDE 编辑器修改

**验收**: PM/QA 充分参与

---

## 3. 外部接口验收

### IF-001: TRAE IDE Chat 接口 ✓

- [ ] TRAE IDE MCP chat interface 可用
- [ ] 自然语言输入
- [ ] 触发 Skill
- [ ] 输出到 chat
- [ ] IDE 通知 + 重试 1 次

**验收**: chat 接口工作

---

### IF-002: TRAE IDE Editor 接口 ✓

- [ ] TRAE file open 可用
- [ ] TRAE file edit 可用
- [ ] TRAE file save 可用
- [ ] 自动打开文件
- [ ] 显示 review 状态

**验收**: Editor 接口工作

---

### IF-003: TRAE IDE Terminal 接口 ✓

- [ ] TRAE terminal panel 可用
- [ ] 跑测试
- [ ] 实时显示结果
- [ ] 进度条

**验收**: Terminal 接口工作

---

### IF-004: TRAE IDE Preview 接口 ✓

- [ ] TRAE preview panel 可用
- [ ] 打开 coverage.html
- [ ] 渲染正常

**验收**: Preview 接口工作

---

### IF-005: GitHub / GitLab PR 接口 ✓

- [ ] `.trae/skills/pr-creator` 可用
- [ ] 业务流 spec 自动附加到 PR

**验收**: PR 接口工作

---

## 4. 过渡验收

### TR-001: 从 0 到 1 (IDE 内) ✓

- [ ] 业务流测试能力从无到有
- [ ] 在 IDE 中可触发
- [ ] 1 个示范场景在 IDE 中跑通
- [ ] PM/BA 试用,基于反馈优化

**验收**: 业务流测试能力可用

---

### TR-002: 1 到 5 业务域扩展 ✓

- [ ] 业务对象 → 枚举 → 审计 → 导入导出 → 产品版本
- [ ] 每个域 ≥ 3 场景
- [ ] 共 ≥ 15 跨页 E2E

**验收**: 5 业务域全部覆盖

---

### TR-003: IDE 工作流深度集成 ✓

- [ ] Phase 1: chat 触发可用
- [ ] Phase 2: IDE 通知 + 状态栏 + Review Actions
- [ ] Phase 3: 自动触发(代码保存时建议生成测试)
- [ ] 软提示 → 硬提示,渐进式

**验收**: IDE 集成深度

---

## 5. 约束验收

### 5.1 技术约束

- [ ] C-1: 沿用 22 个 Skill 体系,新 Skill 注册为 SK-022/023/024
- [ ] C-2: 沿用现有 POM(`e2e/helpers/`)
- [ ] C-3: 沿用现有 isolation 机制
- [ ] C-4: 在 TRAE IDE 中完成所有用户交互
- [ ] C-5: 沿用现有规则体系
- [ ] C-6: 不锁定特定 LLM 模型,用户在 TRAE chat 自由切换,系统只记录 model_name + cost

**验收**: 6 个技术约束遵守

---

### 5.2 业务约束

- [ ] B-1: 测试触发在 IDE chat 中
- [ ] B-2: Healer P0,人在回路
- [ ] B-3: 业务断言 + DOM 断言混合
- [ ] B-4: AI 起草,人 review
- [ ] B-5: YAML 业务可读

**验收**: 5 个业务约束遵守

---

### 5.3 假设验证

- [ ] A-1: TRAE IDE chat 可调用 Skill ✓
- [ ] A-2: TRAE IDE 支持文件自动打开 + 编辑 ✓
- [ ] A-3: TRAE IDE 支持 terminal panel 跑命令 ✓
- [ ] A-4: TRAE IDE 支持 preview 打开 HTML ✓
- [ ] A-5: 现有 561 YonDesign 单测保持稳定 ✓
- [ ] A-6: TRAE IDE 支持多种 LLM 模型,用户每次对话前自选 ✓(TRAE 原生切换)
- [ ] A-7: TRAE IDE 支持自定义 slash command ✓

**验收**: 7 个假设全部成立

---

## 6. 文档验收

- [ ] `.trae/skills/INDEX.md` 更新(SK-022/023/024 注册)
- [ ] `.trae/skills/CHANGELOG.md` 更新
- [ ] `.trae/rules/SESSION_REMINDER.md` 更新
- [ ] `.trae/context/INDEX.md` 更新
- [ ] `docs/business-flow-test-v2-guide.md` 创建(用户手册)

**验收**: 文档与实现同步

---

## 7. 最终验收

- [ ] 24 个 FR 全部完成
- [ ] 9 个 NFR 全部达标
- [ ] 5 业务域共 ≥ 15 跨页 E2E
- [ ] 业务规则覆盖率 ≥ 80%
- [ ] 1 个示范场景 100% pass
- [ ] Healer 自愈率 ≥ 60%
- [ ] PM/BA 试用反馈
- [ ] IDE 内 8 个 MCP 工具工作
- [ ] 7 个 slash command 工作
- [ ] 业务流目录独立

**验收**: 全部完成,进入生产

---

## 验收记录

| 里程碑 | 验收人 | 日期 | 结果 |
|--------|--------|------|------|
| M1 (Week 1) | ___ | ___ | ☐ |
| M2 (Week 1-2) | ___ | ___ | ☐ |
| M3 (Week 2) | ___ | ___ | ☐ (P0 必须) |
| M4 (Week 3) | ___ | ___ | ☐ |
| 最终 | ___ | ___ | ☐ |

---

## 风险与未决项

参见 [spec.md TBD 清单](./spec.md#10-tbd-清单):

- TBD-1: TRAE IDE MCP API 完整对接
- TBD-2: slash command 完整语法
- TBD-3: LLM 模型选型(Qwen 3.5 vs Qwen-Max)
- TBD-4: IDE 通知 UI 形式
- TBD-5: Healer 修复细粒度
- TBD-6: 业务规则覆盖率目标
- TBD-7: 业务断言 vs DOM 断言比例
- TBD-8: CI 集成方式
- TBD-9: 业务流 spec 触发时机
- TBD-10: TRAE chat 自然语言理解准确率

---

**版本历史**:

| 版本 | 日期 | 变更 | 作者 |
|------|------|------|------|
| 1.0 | 2026-06-13 | 初版,与 Spec v2.0 同步 | AI Agent |
