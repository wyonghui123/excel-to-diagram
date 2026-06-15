# MermaidComponent Component Context

> **目标文件**: `src/components/MermaidComponent.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

Mermaid 图渲染组件。封装 Mermaid.js,支持流程图、时序图、ER 图等。

**架构位置**: 图可视化核心组件

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `code` | String | `''` | Mermaid 代码 |
| `type` | String | `'flowchart'` | flowchart / sequence / class / er / state |
| `theme` | String | `'default'` | default / dark / forest |
| `interactive` | Boolean | `false` | 是否可交互 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `node-click` | `{nodeId}` | 节点点击 |
| `render-error` | `{error}` | 渲染错误 |

### Slot
无

## 3. 调用方(依赖)

- `mermaid`(npm 包)
- `src/services/diagramDataBuilder.js`
- `src/services/serviceModuleDiagramBuilder.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 通过 AADiagramApp 验证 |

## 5. 边界场景

- 语法错误
- 大图渲染性能
- 主题切换
- 导出图片

## 6. 易错点

- ⚠️ **错误降级**: 渲染失败显示错误占位
- ⚠️ **防抖**: 代码变更不应立即重渲染
- ⚠️ **内存**: 大图需清理

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |