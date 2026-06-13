# shallowRef 改造报告 (W1 PR-1.3)

## 目标

替换 `ref(大数组/Map)` 为 `shallowRef(大数组/Map)`，避免 Vue 3 为每个元素创建 Proxy，提升大数据场景下的性能。

## 改造内容

### 1. 新增工具 `useShallowArrayRef` (src/composables/useShallowArrayRef.js)
```js
const { ref, set, trigger } = useShallowArrayRef([])
// ref: shallowRef
// set(arr): 整体替换（触发 watch）
// trigger(): 强制触发（用于 push/splice 后）
```

### 2. 应用：useFilterFlow.js
- **位置**：`registeredSources` ref(Map) → shallowRef(Map)
- **变更**：
  - 导入 `shallowRef, triggerRef`
  - `ref(new Map())` → `shallowRef(new Map())`
  - `registerSource` / `unregisterSource` 中显式 `trigger()` 调用
- **测试**：7 个烟雾测试覆盖（API 一致性 + sources computed 自动更新）

## 18 处 deep watch 审计结果

| 文件 | deep watches | 适用 shallowRef | 状态 |
|------|:---:|:---:|:---:|
| `components/common/MetaForm.vue` | 3 | ❌（form 对象需要 deep） | 不动 |
| `components/DataPreview.vue` | 2 | ⚠️ 需逐个评估 | 文档化 |
| `components/common/RelationScopeTree/RelationScopeSection.vue` | 2 | ⚠️ | 文档化 |
| `components/common/RelationScopeTree/RelationScopeTree.vue` | 2 | ⚠️ | 文档化 |
| `composables/useFilterFlow.js` | 2 | ✅（已改造） | **完成** |
| `components/CenterScopeSelector.vue` | 1 | ⚠️ | 文档化 |
| `components/MermaidComponent.vue` | 1 | ❌（props getter） | 不动 |
| `components/RelationCategoryTree.vue` | 1 | ⚠️ | 文档化 |
| `components/ScopeSelector.vue` | 1 | ⚠️ | 文档化 |
| `components/bo/AssociationSelector.vue` | 1 | ⚠️ | 文档化 |
| `components/common/EnumSelect.vue` | 1 | ⚠️ | 文档化 |
| `components/common/SearchHelpDialog.vue` | 1 | ⚠️ | 文档化 |
| `components/common/ValueHelpField.vue` | 1 | ⚠️ | 文档化 |
| `components/common/ConditionRuleEditor/*.vue` | 2 | ⚠️ | 文档化 |
| `components/common/ImpactPreview/ImpactPreview.vue` | 1 | ⚠️ | 文档化 |
| `components/common/RelationScopeTree/ObjectScopeSection.vue` | 1 | ⚠️ | 文档化 |

## shallowRef 适用规则

### ✅ 适用
- 大数组（> 100 元素）
- 大 Map/Set
- 整体替换语义（每次更新整组数据）
- 嵌套对象不需要响应式（仅顶层需要）

### ❌ 不适用
- 简单对象（< 10 字段）
- 表单数据（form 字段需要独立响应式）
- props 监听（getter 形式，无法控制源头）
- 需要细粒度响应的 UI 状态

## ⚠️ 注意事项

1. **push/splice 不触发响应式**：shallowRef 包装后，数组的修改方法不会触发更新
2. **Map/Set 同样不触发**：必须用 `triggerRef()` 显式触发
3. **整体替换仍然触发**：`ref.value = newArray` 仍然触发
4. **computed 仍工作**：`computed(() => ref.value)` 仍会重新计算（在 trigger 后）

## 后续 W5+ 建议

### 立即可做（低风险）
1. `useDiagramSteps.js` 的 STEPS 数组（已废弃但保留）
2. `DataPreview.vue` 中的 relations 数组（重写 watch 为比较 hash）
3. `useMetaList.js` 中的 selectedIds Set

### 需要重构（中等风险）
1. `MetaForm.vue` - 拆分为 per-field watcher，避免 deep
2. `RelationScopeTree/*` - 大规模重构为 shallowRef + 显式 trigger

### 不建议改（高风险）
1. `MermaidComponent.vue` props watcher - props 来自父组件无法控制
2. 任何需要细粒度 form 字段响应的场景

## 测试

- ✅ `useShallowArrayRef.spec.js`：9/9 通过
- ✅ `useFilterFlow-shallowRef.spec.js`：7/7 通过
- ✅ 已有 useFilterFlow 业务代码不受影响（API 兼容）

## 累计 PR-1.3 测试

| 测试文件 | 通过 |
|---------|:---:|
| useShallowArrayRef | 9/9 |
| useFilterFlow 烟雾 | 7/7 |
| useSelectionConfig（前 W2） | 15/15 |
| **本 PR 小计** | **31/31** |
