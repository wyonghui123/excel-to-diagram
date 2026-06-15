# diagramDataBuilder Context

> **目标文件**: `src/services/diagramDataBuilder.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P2
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

图数据构建器。通用图数据结构构建,支持多种图类型(架构图、ER 图、流程图)。

**架构位置**: P2 图服务

## 2. 关键函数

| 函数 | 签名 | 用途 |
|------|------|------|
| `buildNodes` | `(items, type) => Node[]` | 构建节点 |
| `buildEdges` | `(relations) => Edge[]` | 构建边 |
| `buildLayout` | `(graph, algorithm) => GraphData` | 布局算法 |
| `applyStyle` | `(graph, theme) => GraphData` | 应用主题 |

## 3. 调用方

预期:
- `src/components/MermaidComponent.vue`
- `src/components/AADiagramApp.vue`
- `src/services/serviceModuleDiagramBuilder.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 大图性能
- 自循环
- 多重边
- 节点分组

## 6. 易错点

- ⚠️ **节点 ID 稳定**: 必须唯一且不变
- ⚠️ **性能**: 大图需懒渲染
- ⚠️ **主题一致性**: 必须遵循 YonDesign

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |