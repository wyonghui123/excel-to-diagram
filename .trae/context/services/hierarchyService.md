# hierarchyService Context

> **目标文件**: `src/services/hierarchyService.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

层级关系管理。维护对象之间的父子层级结构(如组织树、目录树、分类树)。

**架构位置**: P1 业务 service

## 2. 关键函数

| 函数 | 签名 | 用途 |
|------|------|------|
| `getTree` | `(rootId) => Promise<Node[]>` | 获取树 |
| `getAncestors` | `(nodeId) => Promise<Node[]>` | 上级链路 |
| `getDescendants` | `(nodeId) => Promise<Node[]>` | 下级链路 |
| `moveNode` | `(nodeId, newParent) => Promise<void>` | 移动节点 |
| `reorderChildren` | `(parentId, orderedIds) => Promise<void>` | 重排序 |

## 3. 调用方

预期:
- `src/components/common/RelationScopeTree/`
- `src/components/RelationCategoryTree.vue`
- `src/components/TreeNode.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 循环引用(节点不能移动到自身后代下)
- 深层级(>10 层)
- 大树(>10000 节点)懒加载
- 移动节点级联
- 跨 scope 移动

## 6. 易错点

- ⚠️ **循环检测**: 必须服务端校验
- ⚠️ **懒加载**: 大树不应一次性返回
- ⚠️ **移动影响范围**: 移动后需 invalidate 缓存

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |