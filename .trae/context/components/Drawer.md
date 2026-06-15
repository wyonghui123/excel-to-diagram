# Drawer Component Context

> **目标文件**: `src/components/common/Drawer/Drawer.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P2
> **YonDesign**: [OK]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

抽屉。从侧边滑出的弹层,常用于详情预览、辅助编辑。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `modelValue` | Boolean | `false` | 显隐 |
| `title` | String | `''` | 标题 |
| `direction` | String | `'rtl'` | rtl / ltr / ttb / btt |
| `size` | String | `'400px'` | 大小 |
| `withHeader` | Boolean | `true` | 显示头部 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `update:modelValue` | `{value}` | 显隐 |
| `open` | - | 打开 |
| `close` | - | 关闭 |

### Slot
| Name | Description |
|------|-------------|
| `default` | 内容 |
| `header` | 自定义头部 |
| `footer` | 底部 |

## 3. 调用方

- Element Plus `<el-drawer>`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 多方向
- 嵌套抽屉

## 6. 易错点

- ⚠️ **遮罩**: 移动端可能不需要遮罩

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |