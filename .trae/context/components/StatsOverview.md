# StatsOverview Component Context

> **目标文件**: `src/components/StatsOverview.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P2
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

统计概览。展示数据模型的统计指标(对象数、字段数、关联数等)。

**架构位置**: 仪表板组件

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `metrics` | Metric[] | `[]` | 指标定义 |

### Slot
| Name | Description |
|------|-------------|
| `metric-<key>` | 自定义指标卡 |

## 3. 调用方(依赖)

- `src/services/metaService.js`
- `src/services/auditLogService.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 大量指标(>20)
- 实时刷新
- 加载状态

## 6. 易错点

- ⚠️ **缓存**: 指标必须缓存
- ⚠️ **实时性**: 避免过度刷新

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |