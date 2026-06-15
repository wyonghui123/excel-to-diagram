# Business Flow 路由规则 (T-008)

> **目标**: 用户在 TRAE IDE chat 中说自然语言,自动调用对应 Skill
> **位置**: `.trae/skills/_ROUTER/intent_router.md`

## 意图识别 → Skill 映射

| 用户输入模式 | 触发 Skill | 备注 |
|-------------|-----------|------|
| "为 X 写测试" / "/test-gen" / "/tg" | test-gen (SK-001) | 已有 |
| "测一下 X 业务流" / "/biz-test" / "/bt" | **business-flow-planner (SK-022)** | NEW |
| "/bt-continue" / "生成代码" | **business-flow-generator (SK-023)** | NEW |
| "测试失败" / "修复这个失败" / "/heal" / "/h" | **business-flow-healer (SK-024)** | NEW |
| "派生出业务规则" / "/biz-rules" / "/br" | discover_business_rules.py (T-001) | NEW |
| "看业务覆盖率" / "/biz-coverage" / "/bc" | coverage_report.py (T-014) | 计划 |
| "看 healer 历史" | healings.jsonl 显示 | 计划 |
| "schema 改了,重新派生" | discover_business_rules.py + planner | NEW |
| "/biz-test-full <feat>" / "/btf" | 全流程(Planner → review → Generator → run → Healer) | NEW |
| "跑测试" / "pytest" / "npx playwright test" / "启动服务" / "service_manager" / "restart service" | **test-bootstrap (SK-022)** | **NEW 2026-06-14** 前置 autoload，必读 multi-agent + SESSION_REMINDER |

## 完整流程(/biz-test-full)

```
1. /biz-test-full business-object-lifecycle

2. discover_business_rules.py --object business_object
   ↓ 输出 9+ 条业务规则

3. business-flow-planner
   ↓ LLM (用户选定的模型,如 Claude Sonnet 4) 生成 business-flow.yaml
   ↓ IDE 自动打开
   ↓ 状态栏: "📋 Business Flow Draft Ready"

4. PM/BA review (人在回路)
   ↓ 状态: draft → reviewed → approved

5. business-flow-generator
   ↓ 生成 spec.js + Screenplay Task
   ↓ IDE 自动打开
   ↓ 终端跑测试

6. 测试结果
   ├─ 全部通过 → 完成
   └─ 失败 → business-flow-healer
              ↓ 分析 root_cause
              ↓ 人在回路修复
              ↓ 重跑
```

## 在 TRAE IDE 中触发

TRAE IDE chat 识别 slash command (`/biz-test`, `/heal` 等) 和自然语言 (`.trae/skills/_ROUTER/intent_router.md` 提供规则)。

## 多模型路由

用户在 chat 输入框切换模型,系统记录 `model_name`。建议:

| 任务 | 推荐模型 | 原因 |
|------|---------|------|
| 业务流规划 (Planner) | Claude Sonnet 4 / GPT-5 | 强推理 |
| 测试代码生成 (Generator) | Claude Sonnet 4 / DeepSeek V3 | 平衡 |
| 快速 Healer 修复 | Claude Haiku / DeepSeek V3 | 速度 |
| 中文业务理解 | Qwen 3.5 / DeepSeek V3 | 中文 |
| 多模态 UI 测试 | Gemini 2.5 Pro | 视觉 |

注: 模型是用户决策,系统不锁定。
