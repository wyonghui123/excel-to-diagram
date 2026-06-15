# serviceModuleDiagramBuilder Context

> **目标文件**: `src/services/serviceModuleDiagramBuilder.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P2
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

服务模块图构建器。将服务依赖关系转换为图形数据(Mermaid/Cytoscape 格式)。

**架构位置**: P2 图构建器

## 2. 关键函数

| 函数 | 签名 | 用途 |
|------|------|------|
| `buildGraph` | `(services) => GraphData` | 构建图数据 |
| `toMermaid` | `(graph) => string` | 转为 Mermaid |
| `toCytoscape` | `(graph) => Elements` | 转为 Cytoscape |
| `layout` | `(graph, options) => GraphData` | 自动布局 |

## 3. 调用方

预期:
- `src/components/MermaidComponent.vue`
- `src/components/AADiagramApp.vue`
- `src/components/ServiceModuleConfig.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 循环依赖
- 大图(>200 节点)
- 自循环
- 节点分组(cluster)
- 边标签

## 6. 易错点

- ⚠️ **布局性能**: 大图布局慢,需异步
- ⚠️ **节点标识**: 必须稳定,否则 diff 失败
- ⚠️ **样式**: 节点/边样式应可配置

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |