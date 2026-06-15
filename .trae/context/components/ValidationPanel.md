# ValidationPanel Component Context

> **目标文件**: `src/components/ValidationPanel.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

校验面板。展示数据校验结果(规则校验 + AI 校验),支持修复建议。

**架构位置**: 数据校验可视化

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `target` | Object | `null` | 校验目标(对象或数组) |
| `objectType` | String | `''` | 对象类型 |
| `mode` | String | `'live'` | live / on-demand |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `fix` | `{issue}` | 修复某项 |
| `ignore` | `{issue}` | 忽略 |

### Slot
无

## 3. 调用方(依赖)

- `src/services/dataValidator.js`
- `src/services/zhipuValidator.js`
- `src/services/deepseekValidator.js`
- `src/services/annotationService.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 大量 issue(>100)
- AI 校验超时
- 修复失败

## 6. 易错点

- ⚠️ **AI 降级**: 超时回退到规则校验
- ⚠️ **分级展示**: 错误/警告/提示 分级

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |