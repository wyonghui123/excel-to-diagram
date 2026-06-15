# Skill 变更日志 (CHANGELOG)

> **格式**: [日期] [作者] [Skill ID] - [变更类型] - [变更描述]
> **变更类型**: `+` 新增 / `~` 修改 / `-` 删除 / `!` 关键

---

## 2026-06-13(Spec v2.0 TRAE IDE 集成版)

### ! 业务流 E2E 测试智能生成系统 v2.0 全部交付

- **+ SK-022 business-flow-planner** - 业务流 Planner,生成 business-flow.yaml 草稿(AI 起草 + PM review)
- **+ SK-023 business-flow-generator** - 业务流 Generator,从 reviewed YAML 生成 Playwright spec + Screenplay Task
- **+ SK-024 business-flow-healer** - 业务流 Healer,失败 trace 分析 + 人在回路修复(业务断言永不自动修复)
- **+ mcp_ide_server.py** - TRAE IDE MCP Server,8 个工具(file_open/file_edit/terminal_run/preview_html/status_bar_set/show_notification/show_dialog)
- **+ discover_business_rules.py** - 业务规则抽取器,扫描 37 个 schema 输出 77 条业务规则
- **+ coverage_report.py** - 业务规则覆盖率报告(HTML/MD/JSON)
- **+ trace_business_flow.py** - 双向追溯工具(spec.md ↔ yaml ↔ spec.js ↔ rules)
- **+ infer_test_data.py** - 测试数据推演(有效/无效/边界)
- **+ verify_nfrs.py** - 9 个 NFR 验证工具
- **+ e2e/screenplay/** - Screenplay Pattern 5 要素框架(actor/ability/interactions/tasks/questions)
- **+ BusinessRuleAssertor.js** - 业务规则断言器,9 种 rule type + 业务语义错误
- **+ 37 个 _business_rules/*.yaml** - 业务规则清单 + _index.json
- **+ business-flow.schema.json** - JSON Schema 校验
- **+ business-flow.template.yaml** - AI 起草模板
- **+ 5 业务域业务流 spec** (业务对象/枚举/审计/导入导出/产品版本)
- **+ IDE snippets** - 5 个 screenplay-template snippets
- **+ .ai/mcp.json** - trae-ide MCP server 配置
- **+ .vscode/settings.json** - YAML schema 关联
- **+ .trae/skills/_ROUTER/intent_router.md** - chat 路由规则

### ! 关键设计决策

1. **TRAE IDE chat + slash command 双模式触发**(借鉴 trae-gstack 21 命令)
2. **人在回路**: Healer 修复必须用户在 IDE 弹窗中点击 [Apply Fix] 才应用
3. **业务断言永不自动修复**: 业务规则违反 → 直接显示业务语义错误,要求人工
4. **多模型按需路由**: 模型由用户在 TRAE chat 中自选,系统不锁定(只记录 model_name + cost_cny)
5. **AI 起草 + PM review**: business-flow.yaml 标注 review_status: draft,Generator 只接受 reviewed/approved

### NFR 验证结果

- 4/9 NFR pass (NFR-005/006/007/008)
- 2/9 in_progress (NFR-004 9.1% 起步, NFR-009 1 个 yaml)
- 3/9 pending (NFR-001/002/003 需真实环境 LLM 调用)

### 测试统计

- 17 个 pytest 通过 (业务规则抽取器)
- 19 个 vitest 通过 (Screenplay 框架)
- 8/8 MCP Server 内置测试通过
- 11 个业务流 test cases 写完(尚未实际跑通,需真实环境)

---

## 2026-06-13(Spec v1.1 全量交付)

### ! AI Spec v1.1 全量文档交付完成

- 18 个 FR + 9 个 NFR + 5 个 IF + 3 个 TR 全部完成
- 22 个 Skill 全部注册(20 active + 2 deprecated)
- 120+ Context 文档
- 561 个 YonDesign 组件单测 + 12 个 Playwright E2E
