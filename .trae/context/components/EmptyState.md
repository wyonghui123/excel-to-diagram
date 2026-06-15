# EmptyState Component Context

> **目标文件**: `src/components/common/EmptyState.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [OK]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

空状态。统一空数据占位(图标 + 文案 + 操作)。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `icon` | String | `''` | 图标名 |
| `title` | String | `'暂无数据'` | 标题 |
| `description` | String | `''` | 描述 |
| `size` | String | `'medium'` | small / medium / large |

### Slot
| Name | Description |
|------|-------------|
| `default` | 自定义内容 |
| `action` | 操作按钮 |

## 3. 调用方

- 各种列表/页面

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

**目标**: ≥ 90%

## 5. 边界场景

- 加载中 vs 空 vs 错误状态
- 自定义图标的颜色

## 6. 易错点

- ⚠️ **区分**: 加载中应使用 Loading,而非 Empty

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |