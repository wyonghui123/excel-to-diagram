# objectTypeService Context

> **目标文件**: `src/services/objectTypeService.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

对象类型(Object Type)管理。维护数据模型的对象类型定义,包括字段、约束、关系。

**架构位置**: P0 核心 service,与 metaService 紧密协作

## 2. 关键函数

| 函数 | 签名 | 用途 |
|------|------|------|
| `getObjectTypes` | `() => Promise<ObjectType[]>` | 获取所有对象类型 |
| `getObjectTypeByCode` | `(code) => Promise<ObjectType>` | 按 code 查询 |
| `createObjectType` | `(data) => Promise<ObjectType>` | 创建 |
| `updateObjectType` | `(id, data) => Promise<ObjectType>` | 更新 |
| `getObjectTypeFields` | `(code) => Promise<Field[]>` | 获取字段定义 |
| `deleteObjectType` | `(id) => Promise<void>` | 删除 |

## 3. 调用方

预期:
- `src/components/common/ObjectPage/*`
- `src/components/common/RelationScopeTree/*`
- `src/components/bo/AssociationSelector.vue`
- `src/services/metaService.js`(嵌套)

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 循环引用(A 引用 B,B 引用 A)
- 字段删除(级联)
- 对象类型软删除
- code 重命名
- 多语言字段名

## 6. 易错点

- ⚠️ **删除前检查依赖**: 强引用阻止删除
- ⚠️ **缓存**: 对象类型变更影响所有组件,需强制刷新
- ⚠️ **字段顺序**: 排序可能影响业务

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 Context | AI |