# filterVariantService Context

> **目标文件**: `src/services/filterVariantService.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

筛选变体(Filter Variant)管理。允许用户保存/加载筛选条件预设,支持共享与私有变体。

**架构位置**: P1 业务 service

## 2. 关键函数

| 函数 | 签名 | 用途 |
|------|------|------|
| `listVariants` | `(scope) => Promise<Variant[]>` | 列出变体 |
| `getVariant` | `(id) => Promise<Variant>` | 详情 |
| `saveVariant` | `(data) => Promise<Variant>` | 保存 |
| `deleteVariant` | `(id) => Promise<void>` | 删除 |
| `shareVariant` | `(id, users) => Promise<void>` | 共享 |
| `setDefault` | `(id) => Promise<void>` | 设为默认 |

## 3. 调用方

预期:
- `src/components/common/FilterVariantSelector.vue`
- `src/components/common/MetaListPage/`
- `src/stores/filterVariant.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 通过 FilterVariantSelector 验证 |

## 5. 边界场景

- 共享变体权限
- 私有变体访问控制
- 变体冲突(同名)
- 变体删除级联
- 默认变体切换

## 6. 易错点

- ⚠️ **scope 隔离**: 变体按 scope 隔离(用户/角色/全局)
- ⚠️ **缓存**: 当前变体应在 store 缓存
- ⚠️ **并发保存**: 乐观锁

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |