# deepseekValidator Context

> **目标文件**: `src/services/deepseekValidator.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P3
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

DeepSeek AI 校验器。调用 DeepSeek 模型进行智能数据校验。

**架构位置**: P3 AI 集成 service

## 2. 关键函数

| 函数 | 签名 | 用途 |
|------|------|------|
| `validate` | `(data, type) => Promise<ValidationResult>` | AI 校验 |
| `chat` | `(messages) => Promise<string>` | 通用对话 |
| `streamChat` | `(messages, onChunk) => Promise<void>` | 流式 |

## 3. 调用方

预期:
- `src/components/ValidationPanel.vue`
- `src/services/dataValidator.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [X] (AI 模型难 E2E) |

## 5. 边界场景

- API 限流
- 流式中断
- 内容安全过滤
- Token 限制

## 6. 易错点

- ⚠️ **流式清理**: 中断时必须清理
- ⚠️ **安全**: 内容必须过滤
- ⚠️ **重试**: 失败可重试,但有限制

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |