# MetaForm Component Context

> **目标文件**: `src/components/common/MetaForm.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

元数据表单。基于对象类型 schema 自动生成的表单,支持校验、提交、草稿。

**架构位置**: 核心表单组件,被 ObjectPage、MetaDialog 等使用

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `objectType` | String | `''` | 对象类型 code |
| `modelValue` | Object | `{}` | 表单数据(v-model)
| `mode` | String | `'edit'` | create / edit / view |
| `readonly` | Boolean | `false` | 只读模式 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `update:modelValue` | `{value}` | 数据变化 |
| `submit` | `{data}` | 提交 |
| `validate-fail` | `{errors}` | 校验失败 |

### Slot
| Name | Description |
|------|-------------|
| `field-<fieldName>` | 自定义字段 |
| `actions` | 自定义操作按钮 |

## 3. 调用方(依赖)

- `src/services/objectTypeService.js`
- `src/services/metaService.js`
- `src/services/dataValidator.js`
- `src/services/draftPersistService.js`
- `src/components/common/AppInput/AppInput.vue`
- `src/components/common/AppSelect/AppSelect.vue`
- `src/components/common/EnumSelect.vue`
- `src/components/common/ValueHelpField.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

**目标**: ≥ 80%

## 5. 边界场景

- 嵌套对象
- 数组字段
- 跨字段校验
- 异步校验(唯一性)
- 草稿恢复

## 6. 易错点

- ⚠️ **提交后清草稿**: 必须
- ⚠️ **必填校验**: 客户端 + 服务端双校验
- ⚠️ **错误信息**: 必须含字段路径

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |