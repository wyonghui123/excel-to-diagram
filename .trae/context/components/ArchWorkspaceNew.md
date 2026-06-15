# ArchWorkspaceNew Component Context

> **目标文件**: `src/components/ArchWorkspaceNew.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

新架构工作区。新一代架构图编辑工作区,支持节点拖拽、连线、自动布局。

**架构位置**: AADiagramApp 的下一代

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `workspaceId` | String | `''` | 工作区 ID |
| `readOnly` | Boolean | `false` | 只读 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `save` | `{data}` | 保存 |
| `change` | `{data}` | 变更 |

## 3. 调用方(依赖)

- `src/services/diagramDataBuilder.js`
- `src/services/relationClassifier.js`
- `src/components/MermaidComponent.vue`(预览)
- `src/components/common/MetaTable.vue`(节点列表)

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 大图(>200 节点)
- 拖拽性能
- 撤销/重做
- 自动保存

## 6. 易错点

- ⚠️ **撤销栈**: 必须支持 undo/redo
- ⚠️ **自动保存**: 必须节流

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |