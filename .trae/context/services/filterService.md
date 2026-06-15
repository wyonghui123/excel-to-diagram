# filterService Context

> **目标文件**: `src/services/filterService.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

筛选器服务。提供通用筛选条件的构建、序列化、查询应用能力。

**架构位置**: P1 业务 service

## 2. 关键函数

| 函数 | 签名 | 用途 |
|------|------|------|
| `applyFilter` | `(data, conditions) => Data[]` | 本地筛选(过滤数组)
| `buildConditions` | `(uiState) => Condition[]` | 从 UI 构建查询条件 |
| `parseConditions` | `(encoded) => Condition[]` | 反序列化 |
| `validateCondition` | `(cond) => ValidationResult` | 校验单个条件 |

## 3. 调用方

预期:
- `src/components/common/FilterBar/`
- `src/components/common/TableHeaderFilter/`
- `src/components/common/MetaListPage/`
- `src/components/common/RelationScopeTree/`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 通过 FilterBar 验证 |

## 5. 边界场景

- 空条件
- 多条件组合(AND / OR)
- 嵌套条件
- 条件类型不匹配
- 大数据量筛选性能

## 6. 易错点

- ⚠️ **空值处理**: `null` vs `undefined` vs `""`
- ⚠️ **大小写敏感**: 字符串筛选需明确
- ⚠️ **日期范围**: 时区处理

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |