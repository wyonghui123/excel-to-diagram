# zhipuValidator Context

> **目标文件**: `src/services/zhipuValidator.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P3
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

智谱 AI 校验器。调用智谱 GLM 模型进行智能校验(数据合理性、命名规范、业务规则)。

**架构位置**: P3 AI 集成 service

## 2. 关键函数

| 函数 | 签名 | 用途 |
|------|------|------|
| `validate` | `(data, type) => Promise<ValidationResult>` | AI 校验 |
| `suggest` | `(field) => Promise<Suggestion>` | 智能建议 |
| `explain` | `(error) => Promise<string>` | 错误解释 |

## 3. 调用方

预期:
- `src/components/ValidationPanel.vue`
- `src/components/common/MetaForm.vue`
- `src/services/dataValidator.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [X] (AI 模型难 E2E) |

## 5. 边界场景

- API 限流
- 模型超时
- 返回格式不稳定
- Token 计数与成本

## 6. 易错点

- ⚠️ **失败降级**: AI 失败必须回退到规则校验
- ⚠️ **成本控制**: 必须设调用上限
- ⚠️ **结果不稳定**: AI 结果可能不一致

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |