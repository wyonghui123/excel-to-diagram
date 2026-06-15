# 业务流 E2E 测试智能生成系统 v2.0 - 用户指南

> **版本**: 2.0
> **日期**: 2026-06-13
> **适用**: TRAE IDE 用户(PM/QA/开发/架构师)

## 1. 一分钟上手

在 TRAE IDE chat 输入:

```
测一下业务对象完整流程
```

或用 slash command:

```
/biz-test business-object-lifecycle
```

AI 会自动:
1. 扫描 schema,生成业务规则
2. 起草 `business-flow.yaml`(在 IDE 中自动打开)
3. 状态栏显示 "📋 Business Flow Draft Ready"
4. 等您 review

## 2. 完整工作流

```
[PM/QA]                       [TRAE IDE + AI]                      [结果]
   │                                  │                               │
   │ "测一下业务对象"                   │                               │
   ├─────────────────────────────────►│ SK-022 Planner               │
   │                                  ├─ 业务规则抽取                 │
   │                                  ├─ YAML 起草                   │
   │                                  ├─ IDE 打开 + 通知             │
   │◄─────────────────────────────────┤                              │
   │                                  │                               │
   │ [Approve]                        │                               │
   ├─────────────────────────────────►│ SK-023 Generator             │
   │                                  ├─ 生成 spec.js                 │
   │                                  ├─ 跑测试                       │
   │◄─────────────────────────────────┤                              │
   │                                  │                               │
   │ "测试失败,修复"                   │ SK-024 Healer                │
   ├─────────────────────────────────►├─ 分析 root_cause              │
   │                                  ├─ 人在回路弹窗                │
   │◄─────────────────────────────────┤                              │
   │ [Apply Fix]                      │                               │
   ├─────────────────────────────────►│ 应用 + 重跑                   │
   │                                  │                              │
```

## 3. 业务断言 vs DOM 断言

**业务断言** (优先, ≥ 70%):
```javascript
// 业务规则违反
await BusinessRuleAssertor.assertRule('BR-business_object-DEL-condition', {
  businessObject, apiClient, relationCount: 1
});
// 错误: "存在关联关系的业务对象不能删除"
```

**DOM 断言** (辅助, ≤ 30%):
```javascript
// DOM 文本不匹配
await expect(page.locator('h1')).toHaveText('成功');
// 错误: "expected '...' to be '...'"
```

**业务断言的错误信息含业务语义**,Healer 不会自动修复(因为是业务变更)。

## 4. 7 个 slash command

| Command | 用途 |
|---------|------|
| `/biz-test` 或 `/bt` | 测一下业务流 |
| `/bt-continue` | PM Approve 后继续生成 |
| `/heal` 或 `/h` | 修复失败测试 |
| `/biz-rules` 或 `/br` | 派生业务规则 |
| `/biz-coverage` 或 `/bc` | 看覆盖率 |
| `/biz-test-full` 或 `/btf` | 完整流程 |
| `/test-gen` 或 `/tg` | 单元测试(已有) |

## 5. 业务规则覆盖

跑一遍:
```bash
python .trae/scripts/coverage_report.py
```

输出:
- `coverage.html` (IDE preview)
- `coverage.md` (Markdown 摘要)
- `_traceability/coverage.json` (机器可读)

目标: **业务规则覆盖率 ≥ 80%**(NFR-004)

## 6. 人在回路(Healer)

**Healer 永远不会自动应用修复**,必须用户决策:

- **业务断言失败** → 不提议修复,直接显示业务语义错误
- **UI 漂移** → 提议修复,等用户点 [Apply Fix]
- **安全模块** (authService) → 拒绝修复,弹出红色警告

修复记录在 `.trae/state/healings.jsonl`,可审计。

## 7. 多模型

模型由**您在 TRAE chat 输入框中切换**,系统不锁定,只记录:

| 任务 | 推荐 |
|------|------|
| 业务流规划 | Claude Sonnet 4 / GPT-5 |
| 测试代码生成 | Claude Sonnet 4 / DeepSeek V3 |
| 快速 Healer | Claude Haiku / DeepSeek V3 |
| 中文业务 | Qwen 3.5 / DeepSeek V3 |

## 8. 常见问题

### Q: 业务断言失败时怎么办?
**A**: Healer 不修复业务断言。请:
1. 查看 IDE 弹窗中的业务规则说明
2. 跳转到对应 business-flow.yaml
3. 如规则变更,在 spec.md 中更新规则定义

### Q: 我能在 IDE 编辑 business-flow.yaml 吗?
**A**: 可以。直接编辑保存即可,Generator 接受任何 `review_status: reviewed/approved` 的 YAML。

### Q: 5 业务域具体是哪些?
**A**: 业务对象 / 枚举 / 审计 / 导入导出 / 产品版本。每个 ≥ 3 场景。

### Q: 数据会污染生产 DB 吗?
**A**: 不会。所有测试数据用 `e2e_*` 前缀,自动清理。

## 9. 关键文件

| 文件 | 用途 |
|------|------|
| `.trae/specs/<feat>/business-flow.yaml` | 业务流 YAML(AI 起草 + PM review) |
| `e2e/business-flow/<feat>.spec.js` | Playwright 业务流 spec |
| `e2e/screenplay/` | Screenplay 5 要素 |
| `.trae/specs/_business_rules/` | 37 个 schema 派生的业务规则 |
| `.trae/state/coverage.html` | 覆盖率报告(IDE preview) |

## 10. 下一步

1. **提升覆盖率** (NFR-004): 9.1% → 80%
   - 在 chat: "/biz-test <业务域>" 派生出更多业务流
2. **积累业务流**: 5 业务域共 ≥ 15 跨页 E2E
3. **PM/BA 参与**: review business-flow.yaml,让 AI 起草更准确
4. **Healer 自愈**: 让 UI 变化自动修复,降低维护成本

---

参考:
- [Spec v2.0 完整文档](file:///d:/filework/excel-to-diagram/.trae/specs/business-flow-test-v2-trae-ide/spec.md)
- [Tasks 任务清单](file:///d:/filework/excel-to-diagram/.trae/specs/business-flow-test-v2-trae-ide/tasks.md)
- [Checklist 验收](file:///d:/filework/excel-to-diagram/.trae/specs/business-flow-test-v2-trae-ide/checklist.md)
