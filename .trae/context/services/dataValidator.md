# dataValidator Context

> **目标文件**: `src/services/dataValidator.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P3
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

数据校验服务。基于规则的通用数据校验(必填、长度、范围、正则等)。

**架构位置**: P3 校验 service

## 2. 关键函数

| 函数 | 签名 | 用途 |
|------|------|------|
| `validate` | `(data, rules) => ValidationResult` | 校验 |
| `validateField` | `(value, rule) => ValidationResult` | 单字段 |
| `getRules` | `(objectType) => Rule[]` | 获取对象的规则 |
| `addCustomRule` | `(name, fn) => void` | 注册自定义规则 |

## 3. 调用方

预期:
- `src/components/common/MetaForm.vue`
- `src/components/ValidationPanel.vue`
- `src/services/metaService.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 通过 MetaForm 验证 |

## 5. 边界场景

- 嵌套对象校验
- 跨字段校验(确认密码)
- 异步校验(唯一性)
- 自定义规则

## 6. 易错点

- ⚠️ **错误信息可定位**: 错误必须含字段路径
- ⚠️ **异步规则**: 必须支持 Promise
- ⚠️ **短路**: 一个字段多个规则,遇错即停

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |