# AppModal Component Context

> **目标文件**: `src/components/common/AppModal/AppModal.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [OK]
> **测试覆盖**: ✅ 100% (60 tests)

## 1. 职责 (What)

通用模态框。基于 Element Plus `<el-dialog>` 封装。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `modelValue` | Boolean | `false` | v-model 显隐 |
| `title` | String | `''` | 标题 |
| `width` | String | `'500px'` | 宽度 |
| `closeOnClickModal` | Boolean | `true` | 点击遮罩关闭 |
| `closeOnPressEscape` | Boolean | `true` | Esc 关闭 |
| `showClose` | Boolean | `true` | 显示关闭按钮 |
| `draggable` | Boolean | `false` | 可拖拽 |
| `fullscreen` | Boolean | `false` | 全屏 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `update:modelValue` | `{value}` | 显隐变化 |
| `open` | - | 打开 |
| `close` | - | 关闭 |

### Slot
| Name | Description |
|------|-------------|
| `default` | 内容 |
| `header` | 自定义头部 |
| `footer` | 底部按钮 |

## 3. 调用方

- Element Plus `<el-dialog>`
- `src/components/common/MetaDialog.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ✅ 100% (60 tests) |
| E2E | [OK] 间接验证 |

**目标**: ≥ 90%(基础组件) ✅ 已达成

## 5. 边界场景

- 嵌套 modal
- 极宽内容
- 全屏切换

## 6. 易错点

- ⚠️ **嵌套**: z-index 管理
- ⚠️ **关闭确认**: 父组件负责

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |