# MetaDialog Component Context

> **目标文件**: `src/components/common/MetaDialog.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

元数据对话框。基于 MetaForm 的弹窗式编辑,适用于"新建/编辑"的快速场景。

**架构位置**: 基于 AppModal + MetaForm

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `modelValue` | Boolean | `false` | 显示(v-model)
| `title` | String | `''` | 标题 |
| `objectType` | String | `''` | 对象类型 code |
| `data` | Object | `null` | 初始数据(null = 新建)
| `width` | String | `'600px'` | 宽度 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `update:modelValue` | `{value}` | 显隐变化 |
| `submit` | `{data}` | 提交成功 |
| `cancel` | - | 取消 |

### Slot
| Name | Description |
|------|-------------|
| `default` | 自定义内容(覆盖 MetaForm) |
| `footer` | 自定义底部按钮 |

## 3. 调用方(依赖)

- `src/components/common/AppModal.vue`
- `src/components/common/MetaForm.vue`
- `src/services/metaService.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 数据未变关闭提示
- 大表单滚动
- 嵌套对话框

## 6. 易错点

- ⚠️ **关闭前确认**: 表单 dirty 时弹确认
- ⚠️ **Esc 关闭**: 默认允许

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |