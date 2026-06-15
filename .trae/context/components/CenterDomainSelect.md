# CenterDomainSelect Component Context

> **目标文件**: `src/components/CenterDomainSelect.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P2
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

中心域选择器。选择业务中心域(类似 SaaS 多租户的"工作区")。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `modelValue` | String | `''` | 中心域 ID |
| `multiple` | Boolean | `false` | 多选 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `update:modelValue` | `{value}` | 值变化 |

## 3. 调用方(依赖)

- `src/stores/centerDomain.js`(可能)
- `src/services/metaService.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 单中心域 vs 多中心域
- 切换中心域触发刷新

## 6. 易错点

- ⚠️ **持久化**: 当前中心域应持久化
- ⚠️ **影响范围**: 切换会影响所有数据

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |