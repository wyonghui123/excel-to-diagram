# Tasks: 业务流 E2E 测试智能生成系统 v2.0

> **关联 Spec**: [spec.md](./spec.md)
> **总任务数**: 24 个
> **预计工期**: 3 周
> **里程碑**: M1 (Week 1) / M2 (Week 1-2) / M3 (Week 2) / M4 (Week 3)

---

## M1 (Week 1) - 基础设施

### T-001: 业务规则抽取器 (FR-005)

- [ ] 创建 `.trae/scripts/discover_business_rules.py`
  - [ ] 实现 schema YAML 解析
  - [ ] 实现 deletability 规则抽取
  - [ ] 实现 key_template 规则抽取
  - [ ] 实现 cascade_select 规则抽取
  - [ ] 实现 authorization 规则抽取
  - [ ] 实现 audit 规则抽取
  - [ ] 实现 aspect 规则抽取
  - [ ] 实现 cascade_delete 规则抽取
  - [ ] 实现 owner 规则抽取
  - [ ] 实现 filter_variant 规则抽取
- [ ] 输出 `.trae/specs/_business_rules/<object>.yaml` × 45
- [ ] 创建 `_index.json`(业务规则索引)
- [ ] 添加 CLI 入口:`python discover_business_rules.py --object business_object`
- [ ] 单元测试: `test_discover_business_rules.py`(10+ 测试)
- [ ] 集成测试: 跑一遍 45 个 schema,验证输出

**验收**: 45 个 `_business_rules/*.yaml` 生成成功,每文件含 5-15 条规则

---

### T-002: business-flow YAML Schema (FR-008)

- [ ] 创建 `.trae/specs/templates/business-flow.template.yaml`
  - [ ] 7 节结构: actor / goal / preconditions / tasks / questions / data_tables / cleanup
  - [ ] 含占位符 + 示例
- [ ] 创建 `.trae/specs/templates/business-flow.schema.json`
  - [ ] JSON Schema 校验
  - [ ] 字段类型定义
  - [ ] required/optional 标注
- [ ] 配置 IDE schema 关联 (`.vscode/settings.json`)
  - [ ] `yaml.schemas` 关联
  - [ ] IDE 自动补全
  - [ ] IDE 红线提示
- [ ] 单元测试: 校验示例 yaml 通过/失败

**验收**: IDE 中编辑 business-flow.yaml 实时校验 + 补全

---

### T-003: 业务流 spec 模板 (FR-016, FR-018)

- [ ] 创建 `.vscode/business-flow.code-snippets`
  - [ ] `business-flow-template` (YAML 模板)
  - [ ] `spec-business-flow` (spec.md 模板)
  - [ ] `screenplay-actor` (Actor 模板)
  - [ ] `screenplay-task` (Task 模板)
  - [ ] `biz-assert` (业务断言模板)
- [ ] 创建 `.trae/specs/templates/spec-business-flow.template.md`
  - [ ] 业务背景 / 涉众 / 业务规则 / 关键场景 / 边界条件 / 验收标准

**验收**: IDE snippets 可用,输入 prefix 触发

---

## M2 (Week 1-2) - Screenplay + 业务断言

### T-004: Screenplay 框架 (FR-006)

- [ ] 创建 `e2e/screenplay/actor.js`
  - [ ] `Actor` 类 (named / can / abilityTo / attemptsTo / ask)
  - [ ] `AdminActor` / `ReadonlyActor` / `BusinessAnalystActor` 工厂
- [ ] 创建 `e2e/screenplay/ability.js`
  - [ ] `BrowseTheWeb` (page 能力)
  - [ ] `CallAPI` (apiClient 能力)
  - [ ] `IsolateData` (isolation 能力)
- [ ] 创建 `e2e/screenplay/interactions/`
  - [ ] `Click.js`
  - [ ] `Fill.js`
  - [ ] `Hover.js`
  - [ ] `Wait.js`
  - [ ] `Select.js`
- [ ] 创建 `e2e/screenplay/tasks/` (业务原子动作)
  - [ ] `BusinessObjectTasks.js`
  - [ ] `RelationshipTasks.js`
  - [ ] `EnumTypeTasks.js`
  - [ ] `AuditLogTasks.js`
- [ ] 单元测试: `e2e/screenplay/__tests__/actor.spec.js`
- [ ] 单元测试: `e2e/screenplay/__tests__/tasks/*.spec.js`

**验收**: Screenplay 5 要素完整 + 单测通过

---

### T-005: 业务断言库 (FR-007)

- [ ] 创建 `e2e/screenplay/questions/BusinessRuleAssertor.js`
  - [ ] `assertRule(ruleId, context)` 入口
  - [ ] `assertDeletability` 实现
  - [ ] `assertKeyTemplate` 实现
  - [ ] `assertCascadeSelect` 实现
  - [ ] `assertAuthorization` 实现
  - [ ] `assertAudit` 实现
  - [ ] `loadRule` 从 `_index.json` 加载
  - [ ] 错误信息含**业务语义**(非"DOM 文本不匹配")
- [ ] 创建 `e2e/screenplay/questions/BusinessQuestions.js`
  - [ ] 业务问题(待回答)
  - [ ] 高层 API
- [ ] 单元测试: 各类规则断言测试
- [ ] 集成测试: 真实业务对象测试

**验收**: 业务断言占 ≥ 70%,错误信息含业务语义

---

### T-006: 数据隔离 (FR-019)

- [ ] 沿用 `e2e/helpers/auto-fixtures.js`
- [ ] IDE 集成:
  - [ ] 测试前 IDE 通知"将创建测试数据(自动清理)"
  - [ ] 测试后 IDE 通知"已清理 X 条数据"
- [ ] 验证: 跑测试后 DB 无 `e2e_*` 残留

**验收**: 数据隔离 + IDE 提示

---

## M3 (Week 2) - 三 Skill + IDE 集成 (P0)

### T-007: TRAE IDE MCP Server (FR-001)

- [ ] 创建 `.trae/scripts/mcp_ide_server.py`
  - [ ] `file_open(path)` - 打开文件
  - [ ] `file_edit(path, content)` - 编辑
  - [ ] `terminal_run(cmd)` - 跑命令
  - [ ] `terminal_watch(pattern)` - 监听输出
  - [ ] `preview_html(path)` - 打开 HTML
  - [ ] `status_bar_set(text, color, progress)` - 状态栏
  - [ ] `show_notification(type, title, message, actions)` - 通知
  - [ ] `show_dialog(title, content, actions)` - 弹窗
- [ ] 配置 `.ai/mcp.json`
  - [ ] 注册 `trae-ide` MCP server
  - [ ] 端口 3020
- [ ] 单元测试: 8 个 MCP 工具测试
- [ ] 集成测试: 在 TRAE IDE 中验证

**验收**: 8 个 MCP 工具可调用,IDE 可视化生效

---

### T-008: TRAE IDE Chat 触发路由 (FR-001)

- [ ] 创建 `.trae/skills/_ROUTER/intent_router.md`
  - [ ] 意图识别规则
  - [ ] 关键词 → Skill 映射
  - [ ] 多轮对话支持
- [ ] 配置 slash commands
  - [ ] `/test-gen` / `/tg`
  - [ ] `/biz-test` / `/bt`
  - [ ] `/biz-test-full` / `/btf`
  - [ ] `/heal` / `/h`
  - [ ] `/biz-rules` / `/br`
  - [ ] `/biz-coverage` / `/bc`
  - [ ] `/biz-review` / `/brv`
- [ ] 单元测试: 意图识别测试

**验收**: chat 中自然语言 + slash command 双模式触发

---

### T-009: Planner Skill 注册 (FR-002)

- [ ] 创建 `.trae/skills/business-flow-planner/`
  - [ ] `SKILL.md` (含 triggers / 必读上下文 / Pipeline)
  - [ ] `PROMPT_TEMPLATE.md` (Qwen 3.5 prompt)
  - [ ] `OUTPUT_SPEC.md` (business-flow.yaml 输出规范)
  - [ ] `examples/business-object-lifecycle.yaml` (示例)
- [ ] 在 `.trae/skills/INDEX.md` 注册为 SK-022
- [ ] IDE 集成:
  - [ ] 生成后自动 file_open
  - [ ] 状态栏显示 "📋 Business Flow Draft Ready"
  - [ ] 通知 + Review Actions 按钮 (Approve / Edit / Reject)
  - [ ] Approve → 自动设 `review_status: approved` + 触发 Generator
  - [ ] Reject → 进入 chat 反馈循环

**验收**: chat 触发后,YAML 在 IDE 中自动打开,PM 可 review

---

### T-010: Generator Skill 注册 (FR-003)

- [ ] 创建 `.trae/skills/business-flow-generator/`
  - [ ] `SKILL.md` (含 triggers / 必读上下文 / Pipeline)
  - [ ] `PROMPT_TEMPLATE.md` (Qwen 3.5 prompt)
  - [ ] `OUTPUT_SPEC.md` (spec.js 输出规范)
  - [ ] `examples/business-object-lifecycle.spec.js` (示例)
- [ ] 在 `.trae/skills/INDEX.md` 注册为 SK-023
- [ ] 校验逻辑:
  - [ ] `review_status != "draft"`
  - [ ] tasks/questions 字段必填
- [ ] 生成逻辑:
  - [ ] Screenplay Task 类生成
  - [ ] Playwright spec.js 生成
  - [ ] 业务断言 70% + DOM 断言 30%
- [ ] IDE 集成:
  - [ ] 打开生成的 spec.js
  - [ ] terminal panel 跑测试
  - [ ] 实时进度

**验收**: approved YAML → 自动生成 spec.js + 跑测试

---

### T-011: Healer Skill 注册 (FR-004, FR-013, FR-017)

- [ ] 创建 `.trae/skills/business-flow-healer/`
  - [ ] `SKILL.md` (含 triggers / 必读上下文 / Pipeline)
  - [ ] `PROMPT_TEMPLATE.md` (Qwen 3.5 prompt)
  - [ ] `OUTPUT_SPEC.md` (修复策略规范)
  - [ ] `examples/heal-cases.json` (示例)
- [ ] 在 `.trae/skills/INDEX.md` 注册为 SK-024
- [ ] 失败分析:
  - [ ] 解析 trace.zip
  - [ ] 判断 root_cause: locator_drift / wait_timeout / data_mismatch / business_assertion
- [ ] 业务断言失败 → 不修复:
  - [ ] IDE 弹出 "❌ 业务断言失败 - 需要人工 review"
  - [ ] 显示业务语义错误
  - [ ] 选项: [查看业务规则] [跳转 YAML] [忽略]
- [ ] UI/数据问题 → 人在回路修复:
  - [ ] IDE 弹窗显示建议
  - [ ] 选项: [Apply Fix] [Edit Manually] [Mark as Bug] [Skip]
  - [ ] 业务断言失败时直接显示业务语义错误
- [ ] Healer 边界 (FR-013):
  - [ ] 检查 `healer/PERMISSIONS.md` deny list
  - [ ] 安全模块 → IDE 红色警告
- [ ] 修复日志:
  - [ ] `.trae/state/healings.jsonl`
  - [ ] 含 trace_id / root_cause / fix_type / success
- [ ] 单元测试: 各修复策略测试

**验收**: 测试失败时人在回路,业务断言不自动修复

---

### T-012: 1 个示范场景 (FR-009)

- [ ] 创建 `.trae/specs/business-object-lifecycle/`
  - [ ] `spec.md` (现有,可直接用)
  - [ ] `business-flow.yaml` (AI 起草,PM review)
  - [ ] `_traceability.json`
- [ ] 业务规则覆盖:
  - [ ] deletability (删除有关系的对象应失败)
  - [ ] key_template (新建时 code 自动填充)
  - [ ] cascade_select (域-子域-服务模块级联)
- [ ] 跨页面 ≥ 3:
  - [ ] 列表 → 详情 → 关系编辑 → 删除确认
- [ ] 业务断言 ≥ 5,DOM 断言 ≤ 2
- [ ] 端到端跑通:
  - [ ] chat: "测一下业务对象完整流程"
  - [ ] Planner → YAML 草稿 → IDE 打开
  - [ ] PM Approve → Generator → spec.js
  - [ ] 跑测试 → 100% pass
  - [ ] 模拟 1 次 Healer 修复(locator 漂移)

**验收**: 1 个示范场景在 IDE 中端到端跑通

---

## M4 (Week 3) - 规模化 + 可视化

### T-013: 5 业务域扩展 (FR-011)

- [ ] 业务对象 (已示范)
  - [ ] 业务对象生命周期 ✓
- [ ] 枚举管理
  - [ ] enum-type-list.spec.js
  - [ ] enum-value-crud.spec.js
- [ ] 审计日志
  - [ ] audit-log.spec.js
- [ ] 导入导出
  - [ ] batch-export-import.spec.js
- [ ] 产品版本
  - [ ] product-version.spec.js
- [ ] 每个域 ≥ 3 场景
- [ ] 业务规则覆盖每个域 ≥ 5 条核心规则

**验收**: 5 业务域共 ≥ 15 个跨页 E2E

---

### T-014: 业务规则覆盖率报告 (FR-012, FR-022)

- [ ] 创建 `.trae/scripts/coverage_report.py`
  - [ ] 读取 `_business_rules/_index.json`
  - [ ] 读取 `e2e/business-flow/*.spec.js`
  - [ ] 解析 spec.js 中的 `BusinessRuleAssertor.assertRule` 调用
  - [ ] 计算业务规则覆盖率
  - [ ] 找出未覆盖规则
  - [ ] 生成 `.trae/state/coverage.html` (HTML 报告)
  - [ ] 生成 `.trae/state/coverage.md` (Markdown 摘要)
- [ ] IDE preview 集成:
  - [ ] chat: "看业务覆盖率" → IDE preview 打开
  - [ ] 报告含覆盖率图 + 未覆盖规则列表 + 修复建议
- [ ] 单元测试: 报告生成测试

**验收**: coverage.html 在 IDE preview 打开,可视化清晰

---

### T-015: 双向追溯 (FR-020)

- [ ] 在 spec.md 头部添加:
  - [ ] `## business_flow: .trae/specs/<feat>/business-flow.yaml`
  - [ ] `<!-- scenario-id: T_BIZ_BO_001 -->`
- [ ] 实现反向追溯:
  - [ ] 打开 spec.md → IDE 显示关联 yaml + spec.js
  - [ ] 可点击跳转
- [ ] 单元测试: 追溯解析测试

**验收**: 双向追溯在 IDE 中可视化

---

### T-016: 业务流测试目录 (FR-021)

- [ ] 创建 `e2e/business-flow/` 目录
- [ ] 业务流 E2E 全部在此目录
- [ ] 与现有 `e2e/features/` 并存
- [ ] IDE 中显示目录树
- [ ] 更新 `e2e/README.md`

**验收**: 业务流 E2E 在独立目录,不污染现有

---

### T-017: 业务流测试数据推演 (FR-023)

- [ ] 在 Planner 中增加数据推演逻辑:
  - [ ] 读取 schema 字段约束(pattern / min / max)
  - [ ] 生成有效/无效数据各 1 套
  - [ ] 边界值自动识别
  - [ ] 失败时给出违反的规则名
- [ ] IDE 提示:
  - [ ] chat: "测一下边界值" → AI 推演
  - [ ] IDE 通知"将使用以下边界数据:[显示],确认? [Y/N]"
  - [ ] 用户确认 → 应用

**验收**: 数据推演在 IDE 中显示,用户可确认

---

### T-018: 业务流性能基线 (FR-024)

- [ ] 在 IDE 状态栏显示:
  - [ ] 测试运行时: "⏱ 5.2s | ¥0.12 | 8 scenarios"
  - [ ] 跑完: "✅ 5.2s | ¥0.12 | 8/8 passed"
- [ ] 在 `.trae/state/agent-runs.jsonl` 扩展字段:
  - [ ] `duration_ms`
  - [ ] `cost_cny`
  - [ ] `scenarios_count`
- [ ] 单元测试: 状态栏更新测试

**验收**: IDE 状态栏实时显示性能指标

---

### T-019: 多 Agent 端口隔离 (FR-014)

- [ ] 沿用 `.trae/rules/multi-agent-coordination.md`
- [ ] AGENT_PORT 3010-3019
- [ ] Planner → 3010
- [ ] Generator → 3011
- [ ] Healer → 3012
- [ ] IDE 后台运行
- [ ] IDE 状态栏显示当前活跃 Agent

**验收**: 多 Agent 并行不冲突,IDE 显示活跃 Agent

---

### T-020: IDE 工作流模板 (FR-015)

- [ ] 实现 `/biz-test-full <feat>` 工作流
- [ ] 全流程可视化:
  - [ ] Step 1: 业务规则抽取 → 进度
  - [ ] Step 2: Planner 生成 → 状态
  - [ ] Step 3: PM Review → 等待
  - [ ] Step 4: Generator 生成 → 状态
  - [ ] Step 5: 跑测试 → 实时进度
  - [ ] Step 6: Healer → 等待用户决定
- [ ] 单元测试: 工作流状态机测试

**验收**: chat: "/biz-test-full <feat>" 完整流程可视化

---

## 收尾任务 (Week 3 末)

### T-021: Healer 审计可查 (FR-017)

- [ ] chat: "看 healer 历史" → IDE 中显示
- [ ] 表格列: time / spec / root_cause / fix_strategy / status
- [ ] 复用 `.trae/state/healings.jsonl`

**验收**: Healer 历史在 IDE 中可视化

---

### T-022: NFR 验证 (NFR-001 ~ NFR-009)

- [ ] NFR-001 性能: IDE chat 响应 < 3s
- [ ] NFR-002 成本: 单 spec LLM 成本 < ¥3.5
- [ ] NFR-003 可靠性: Healer 自愈率 ≥ 60%
- [ ] NFR-004 业务规则覆盖率 ≥ 80%
- [ ] NFR-005 可观测性: 所有 Agent 状态 IDE 可见
- [ ] NFR-006 安全性: Healer 默认 deny
- [ ] NFR-007 数据隔离: 无 DB 污染
- [ ] NFR-008 多 Agent 隔离: AGENT_PORT 工作
- [ ] NFR-009 PM 可参与性: review 完成率 ≥ 60%

**验收**: 9 个 NFR 全部达标

---

### T-023: 文档更新

- [ ] 更新 `.trae/skills/INDEX.md` (SK-022/023/024)
- [ ] 更新 `.trae/skills/CHANGELOG.md`
- [ ] 更新 `.trae/rules/SESSION_REMINDER.md` (新增 TBD)
- [ ] 更新 `.trae/context/INDEX.md` (新增业务流测试相关)
- [ ] 创建 `docs/business-flow-test-v2-guide.md` (用户手册)

**验收**: 文档与实现同步

---

### T-024: 最终验收

- [ ] 跑通所有 24 个 FR
- [ ] 9 个 NFR 达标
- [ ] 5 业务域共 ≥ 15 跨页 E2E
- [ ] 业务规则覆盖率 ≥ 80%
- [ ] 1 个示范场景 100% pass
- [ ] Healer 自愈率 ≥ 60%
- [ ] PM/BA 试用反馈

**验收**: 全部完成,进入生产

---

## 任务统计

| 里程碑 | 任务数 | 工期 | 关键路径 |
|--------|--------|------|---------|
| M1 | 3 | 3 天 | 业务规则 + Schema + 模板 |
| M2 | 3 | 4 天 | Screenplay + 业务断言 + 隔离 |
| M3 | 6 | 7 天 | **P0**: MCP + 路由 + 三 Skill + 示范 |
| M4 | 8 | 7 天 | 5 域扩展 + 报告 + 追溯 + 性能 + 文档 |
| 收尾 | 4 | 4 天 | NFR 验证 + 文档 + 最终验收 |
| **总计** | **24** | **25 天 (3.5 周)** | |

---

## 依赖关系图

```
T-001 (规则抽取) ─┐
                  ├─→ T-009 (Planner) ─┐
T-002 (Schema) ────┤                    ├─→ T-012 (示范) ─→ T-013 (5 域)
                  │                    │
T-003 (snippet) ──┤                    │
                  │                    │
T-004 (Screenplay)┤                    │
                  │                    │
T-005 (断言库) ───┤                    │
                  │                    │
T-006 (隔离) ─────┘                    │
                                       │
T-007 (MCP) ───────┐                   │
                   ├─→ T-008 (路由) ──┤
T-002 (Schema) ────┘                   │
                                       │
                                       ├─→ T-014 (覆盖率) ─→ T-022 (NFR)
T-010 (Generator) ─┐                   │
                   ├─→ T-011 (Healer)─┤
T-005 (断言库) ────┘                   │
                                       │
                                       ├─→ T-015 (追溯)
                                       ├─→ T-017 (数据推演)
                                       ├─→ T-018 (性能基线)
                                       ├─→ T-019 (多 Agent)
                                       └─→ T-020 (工作流)
```

---

## 关键里程碑 Checklist

### M1 完成 (Day 3)

- [ ] 45 个 `_business_rules/*.yaml` 生成
- [ ] business-flow.yaml Schema 校验可用
- [ ] IDE snippets 5 个可用

### M2 完成 (Day 7)

- [ ] Screenplay 5 要素 + 4 个 Task 类
- [ ] BusinessRuleAssertor 5 种规则断言
- [ ] 数据隔离 IDE 提示

### M3 完成 (Day 14) - **P0 关键**

- [ ] 8 个 MCP 工具可用
- [ ] chat 触发 7 个 slash command
- [ ] 3 个 Skill (Planner/Generator/Healer) 注册
- [ ] Healer 人在回路
- [ ] 1 个示范场景端到端跑通

### M4 完成 (Day 21)

- [ ] 5 业务域 ≥ 15 跨页 E2E
- [ ] coverage.html 在 IDE preview
- [ ] 双向追溯可视化
- [ ] IDE 状态栏性能基线
- [ ] 9 个 NFR 全部达标

### 最终验收 (Day 25)

- [ ] 24 个 FR 全部完成
- [ ] 文档同步更新
- [ ] PM/BA 试用反馈
- [ ] 进入生产
