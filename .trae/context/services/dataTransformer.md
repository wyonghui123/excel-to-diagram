# dataTransformer Context

> **目标文件**: `src/services/dataTransformer.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P2
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

数据转换器。通用数据格式转换(对象 ↔ DTO、表单数据 ↔ API 数据等)。

**架构位置**: P2 工具型 service

## 2. 关键函数

| 函数 | 签名 | 用途 |
|------|------|------|
| `toDTO` | `(model) => DTO` | 模型 → DTO |
| `fromDTO` | `(dto) => Model` | DTO → 模型 |
| `toFormData` | `(model) => FormData` | 模型 → 表单 |
| `fromFormData` | `(form) => Model` | 表单 → 模型 |
| `clone` | `(data, deep) => Any` | 克隆 |

## 3. 调用方

预期:
- 几乎所有 service / component 都可能用
- `src/components/common/MetaForm.vue`
- `src/components/common/MetaTable.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 嵌套对象
- 循环引用
- Date 类型
- 数组处理

## 6. 易错点

- ⚠️ **深拷贝**: 默认浅拷贝,深拷贝需明确
- ⚠️ **类型转换**: Date / Number / Boolean
- ⚠️ **空值处理**: null vs undefined

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |