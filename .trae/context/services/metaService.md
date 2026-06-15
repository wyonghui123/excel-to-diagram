# metaService Context

> **目标文件**: `src/services/metaService.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

元数据查询与变更。项目的核心数据服务,管理所有元模型相关的 CRUD 操作。

**架构位置**: 核心 service,被几乎所有业务组件调用

## 2. 关键函数

| 函数 | 签名 | 用途 |
|------|------|------|
| `queryMetaList` | `(params) => Promise<Meta[]>` | 元数据列表查询 |
| `getMetaById` | `(id) => Promise<Meta>` | 详情查询 |
| `createMeta` | `(data) => Promise<Meta>` | 创建 |
| `updateMeta` | `(id, data) => Promise<Meta>` | 更新 |
| `deleteMeta` | `(id) => Promise<void>` | 删除 |
| `batchSave` | `(items) => Promise<BatchResult>` | 批量保存 |

## 3. 调用方

预期调用方:
- `src/stores/meta.js`(Pinia store)
- `src/components/MetaTable.vue` / `MetaForm.vue` / `MetaListPage`
- `src/components/common/ObjectPage/*`
- `src/components/AADiagramApp.vue`
- `src/components/bo/ActionExecutor.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 通过 MetaListPage 验证 |
| 覆盖率 | 0% |

**目标**: ≥ 80%

## 5. 边界场景

- 大数据量查询(>1000 条,需分页)
- 批量保存部分失败
- 关联数据级联删除
- 并发编辑冲突(乐观锁)
- 软删除 vs 硬删除

## 6. 易错点

- [OK] **统一使用 httpClient**,不直接 fetch
- ⚠️ **批量保存**: 必须使用 batchSave 而非循环 updateMeta
- ⚠️ **缓存失效**: 写操作后必须 invalidate 缓存
- ⚠️ **大对象**: 详情查询可能含完整 tree,需考虑性能

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 Context | AI |