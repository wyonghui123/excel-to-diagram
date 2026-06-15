# ImportDialog Component Context

> **目标文件**: `src/components/common/ImportDialog/ImportDialog.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

导入对话框。完整的导入流程:文件选择 → 预览 → 字段映射 → 确认导入。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `modelValue` | Boolean | `false` | 显隐 |
| `targetObjectType` | String | `''` | 目标对象类型 |
| `template` | String | `''` | 模板 ID(可选) |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `update:modelValue` | `{value}` | 显隐 |
| `success` | `{count}` | 成功 |

### Slot
| Name | Description |
|------|-------------|
| `preview` | 自定义预览 |

## 3. 调用方(依赖)

- `src/components/FileUploader.vue`
- `src/components/DataPreview.vue`
- `src/services/excelParser.js`
- `src/services/archDataConverter.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 大文件
- 部分行失败
- 字段映射缺失

## 6. 易错点

- ⚠️ **步骤**: 必须清晰展示当前步骤
- ⚠️ **回退**: 每步可回退
- ⚠️ **错误行**: 失败行必须可下载

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |