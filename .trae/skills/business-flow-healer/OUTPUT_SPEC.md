# business-flow-healer - OUTPUT_SPEC

## 输出

1. **人在回路修复建议** (主要)
2. `.trae/state/healings.jsonl` 记录 (审计)

## 修复建议格式

```javascript
// Before
await page.click('.el-button--primary');

// After
await page.getByRole('button', { name: '保存' }).click();
```

## 修复日志格式 (healings.jsonl)

每行一个 JSON:

```json
{
  "trace_id": "uuid-32-chars",
  "spec_path": "e2e/business-flow/<feat>.spec.js",
  "root_cause_slug": "locator_drift",
  "fix_strategy": "role_based_replacement",
  "iterations": 1,
  "status": "healed|denied|not_healed|failed",
  "fix_diff": "...",
  "duration_ms": 1234,
  "user_decision": "apply|edit|skip|mark_bug",
  "ts": "2026-06-13T10:00:00Z"
}
```

## 状态机

```
        失败 trace
            ↓
        分析 root_cause
            ↓
   ┌────────┴────────┐
   ↓                 ↓
business_assertion  UI/data
   ↓                 ↓
显示业务错误    检查 deny list
   ↓                 ↓
不修复        ┌─────┴─────┐
              ↓           ↓
          允许修复     denied
              ↓           ↓
         提议修复    弹出警告
              ↓
       人在回路
       ┌───┴───┬────┐
       ↓       ↓    ↓
    apply   edit  skip
       ↓       ↓    ↓
    应用+重跑 打开  标记
              spec  bug
```

## 质量门禁

| 指标 | 目标 |
|------|------|
| 业务断言不修复 | 100% |
| 人在回路 | 100% |
| 安全模块 deny | 100% |
| 自愈率 | ≥ 60% (借鉴 IJESR 2026-01) |
| 最大重试 | ≤ 3 |
