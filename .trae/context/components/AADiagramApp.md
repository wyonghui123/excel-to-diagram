# AADiagramApp Component Context

> **目标文件**: `src/components/AADiagramApp.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

架构图主应用。项目的核心视图,展示数据模型的关系图。

**架构位置**: 顶层应用,被路由直接挂载

## 2. Props/Emit/Slot

### 2.1 Props
无外部 props(顶级应用,内部管理所有状态)

### 2.2 主要状态
- `nodes`: 图节点
- `edges`: 图边
- `selectedNode`: 当前选中节点
- `layout`: 布局算法

### 2.3 Emit
无外部 emit

### 2.4 Slot
无

## 3. 调用方(依赖)

- `src/services/metaService.js`
- `src/services/relationClassifier.js`
- `src/services/diagramDataBuilder.js`
- `src/services/serviceModuleDiagramBuilder.js`
- `src/components/MermaidComponent.vue`
- `src/components/ValidationPanel.vue`
- `src/components/common/ObjectPage/*`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试(Vitest + @vue/test-utils) | ⚠️ 0% |
| E2E(Playwright) | [OK] 间接验证 |
| 覆盖率 | 0% |

**目标**: ≥ 60%(主应用通常难测试)

## 5. 边界场景

- 大图(>200 节点)性能
- 空数据
- 加载状态
- 选中/取消选中
- 节点拖拽

## 6. 易错点

- ⚠️ **性能**: 大图必须懒渲染
- ⚠️ **状态管理**: 用 Pinia 而非 local state
- ⚠️ **清理**: 卸载时清理事件监听

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |