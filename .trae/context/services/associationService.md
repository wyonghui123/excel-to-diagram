# associationService Context

> **目标文件**: `src/services/associationService.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

关联关系管理。维护对象之间的关联(Association),如引用、外键、虚拟关联。

**架构位置**: P1 业务 service

## 2. 关键函数

| 函数 | 签名 | 用途 |
|------|------|------|
| `getAssociations` | `(objectId) => Promise<Assoc[]>` | 出向关联 |
| `getReverseAssociations` | `(objectId) => Promise<Assoc[]>` | 入向关联 |
| `createAssociation` | `(data) => Promise<Assoc>` | 创建 |
| `deleteAssociation` | `(id) => Promise<void>` | 删除 |
| `validateCyclic` | `(sourceId, targetId) => boolean` | 防止循环 |

## 3. 调用方

预期:
- `src/components/common/ObjectPage/AssociationSection.vue`
- `src/components/common/DetailPage/AssociationSection.vue`
- `src/components/bo/AssociationCell.vue`
- `src/components/bo/AssociationSelector.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 自关联(对象关联自身)
- 循环引用(A→B→C→A)
- 多类型关联(多种关系类型)
- 关联删除级联

## 6. 易错点

- ⚠️ **方向性**: 出向 vs 入向必须明确
- ⚠️ **级联删除**: 删除对象时关联处理策略
- ⚠️ **批量操作**: 大量关联时性能

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |