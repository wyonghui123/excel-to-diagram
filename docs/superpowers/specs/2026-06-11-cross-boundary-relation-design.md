# Cross-Boundary Relation 跨域关系补全 + 外部对象引入 设计 Spec

- **日期**: 2026-06-11
- **作者**: AI Agent
- **状态**: DRAFT (待用户审核)

---

## 1. 背景与问题

### 1.1 现状
架构数据图表 (AADiagramApp) 中：
- 用户在"中心范围"步骤选 26 BO（如采购管理领域）
- 在"关系范围"步骤通过 `selectedRelationNodeIds` 选 category 节点（默认全选）
- 期望看到的关系应包含：
  - 范围内↔范围内 (INTERNAL)
  - 范围内↔范围外 (CROSS_BOUNDARY) — **如 id=29 TEST600→BO_WAREHOUSE**
  - 范围外↔范围外 (EXTERNAL) — **保持原状，不处理（按用户决策）**

### 1.2 根因
[`relationClassifier.js:456-460`](file:///d:/filework/excel-to-diagram/src/services/relationClassifier.js#L456-L460)：
```js
const tree = [
  buildScopeNode(ScopeType.INTERNAL, '范围内', categoryStats[ScopeType.INTERNAL]),
  buildScopeNode(ScopeType.CROSS_BOUNDARY, '范围内与外部', categoryStats[ScopeType.CROSS_BOUNDARY]),
  buildScopeNode(ScopeType.EXTERNAL, '范围外', categoryStats[ScopeType.EXTERNAL])
].filter(node => node.count > 0)
```

**`ScopeType.EXTERNAL` 节点被 `count>0` 过滤掉**（实际上 CROSS_BOUNDARY 节点也存在数据但被合并了）—— id=29 这类 `src∈cs, tgt∉cs` 的关系没有可被勾选的 category 节点。

进一步看 [`relationClassifier.js:498-500`](file:///d:/filework/excel-to-diagram/src/services/relationClassifier.js#L498-L500)：
```js
const scopeType = (sourceInScope && targetInScope)
  ? ScopeType.INTERNAL
  : ScopeType.EXTERNAL  // 跨域 + 范围外 都被映射到 EXTERNAL
```

**`CROSS_BOUNDARY` 在分类时被合并到 `EXTERNAL`** —— 3 类关系只有 1 个 category 节点（INTERNAL）。

### 1.3 影响
1. **统计漏 1 条关系**：id=29 不被 `filteredRelations` 包含
2. **TEST600 不被引入**：id=29 src=TES600 不在 `relationFilteredBoCodes` 中
3. **图表展示缺节点**：groupModel 不渲染 TEST600
4. **导航统计少 1 关系 + 少 1 对象**

---

## 2. 设计目标

| 目标 | 度量 |
|------|------|
| 跨域关系 (id=29) 正确入 `filteredRelations` | 导航关系数: 28 → **29** |
| 跨域关系 src/tgt 范围外端 BO 入 `relationFilteredBoCodes` | 导航对象数: 25 → **26** |
| 统计显式包含"外部对象数" | 新增 `incremental.externalBusinessObjects` 字段 |
| 图表展示 TEST600 节点和连线 | SVG 包含 TEST600 文本 |
| **不破坏**用户"只选 INTERNAL 不引入外部"语义 | 全选时正确，不全选时不动 |

---

## 3. 解决方案

### 3.1 核心改动 1：收紧条件的 `filteredRelations` 补全

文件：[`useDiagramData.js:364-366`](file:///d:/filework/excel-to-diagram/src/views/AADiagramApp/composables/useDiagramData.js#L364-L366)

```js
const filteredRelations = computed(() => {
  // 旧逻辑: 从 category tree 选中的关系
  const fromTree = getSelectedRelationIds(
    relationCategoryTree.value,
    selectedRelationNodeIds.value
  )

  // 关键修复 v29: 补全跨域关系 (src ⊕ tgt ∈ centerScope)
  // 收紧条件: 仅当用户**主动选了 INTERNAL 或 CROSS_BOUNDARY** 节点时才补全
  //   - 保护 "用户只选 INTERNAL 不想引入外部" 语义
  //   - 默认全选场景 (selectedRelationNodeIds 含 INTERNAL+EXTERNAL): 走 fromTree 已选
  //   - 用户主动选了 CROSS_BOUNDARY 但 id=29 没进 fromTree: 补全
  const treeSet = new Set(fromTree)
  const fromCrossBoundary = []
  const centerSet = new Set(centerScope.value || [])

  if (previewData.value?.relationships && centerSet.size > 0) {
    // 判断用户是否选了 INTERNAL 或 CROSS_BOUNDARY category 节点
    const userSelectedInternalOrCross = (selectedRelationNodeIds.value || []).some(nodeId => {
      return nodeId.startsWith('internal-') || nodeId.startsWith('cross-boundary-')
    })

    if (userSelectedInternalOrCross) {
      previewData.value.relationships.forEach(rel => {
        if (rel.id == null) return
        if (treeSet.has(rel.id)) return  // 已被 fromTree 覆盖, 跳过
        // 排除自环
        if (rel.sourceCode === rel.targetCode) return
        const sourceIn = centerSet.has(rel.sourceCode)
        const targetIn = centerSet.has(rel.targetCode)
        // 仅跨域 (XOR 条件)
        if (sourceIn !== targetIn) {
          fromCrossBoundary.push(rel.id)
        }
      })
    }
  }

  // 去重合并
  return Array.from(new Set([...fromTree, ...fromCrossBoundary]))
})
```

**收紧条件解释**：
- `selectedRelationNodeIds` 含 `internal-*` 或 `cross-boundary-*` 节点 = **用户表达了"看范围外"的意图**
- 用户**只选 EXTERNAL 节点**（如 `external-cross-domain`）→ **不补全**（避免"想看纯外部"被污染）
- 用户**全选** → `fromTree` 已含 id=29（如果 EXTERNAL 节点未丢）→ **不重复补全**

**自我验证场景**：
| 用户选 | fromTree | fromCrossBoundary | 最终 |
|--------|---------|-------------------|------|
| 空 | [] | [] (条件不满足) | [] |
| 只 INTERNAL 22 | 22 | [] (src/tgt 都在cs) | 22 |
| INTERNAL + CROSS_BOUNDARY | 22+5 | +1 (id=29) | 28+1=29 |
| 全选 | 28+1=29 | 0 (已覆盖) | 29 |
| 只 EXTERNAL | 0 | [] (条件不满足) | 0 |

### 3.2 核心改动 2：导航统计显式"外部对象数"字段

文件：[`useDiagramData.js:403-409`](file:///d:/filework/excel-to-diagram/src/views/AADiagramApp/composables/useDiagramData.js#L403-L409)

```js
const incrementalStats = {
  domains: totalStats.domains - centerStats.domains,
  subDomains: totalStats.subDomains - centerStats.subDomains,
  serviceModules: totalStats.serviceModules - centerStats.serviceModules,
  businessObjects: totalStats.businessObjects - centerStats.businessObjects,
  // 新增 (v29): 跨域关系引入的范围外端 BO 数 (去重)
  externalBusinessObjects: externalBoCodes.value.size,
  objectRelations: filteredRelations.value.length
}
```

**字段含义**：`externalBusinessObjects` = `externalBoCodes.size` = rfb 中不在 centerScope 的 BO 数。

### 3.3 核心改动 3：导航栏展示"+外部对象"

文件：[AADiagramApp/index.vue 导航栏部分](file:///d:/filework/excel-to-diagram/src/views/AADiagramApp/index.vue)

导航栏当前显示 `2领域 · 2子域 · 26对象 · 29关系`。在末尾追加 **`+N外部对象`** 当 `incremental.externalBusinessObjects > 0`。

```vue
<!-- 现状 -->
<span>2领域 · 2子域 · 26对象 · 29关系</span>

<!-- 修复后 -->
<span>
  2领域 · 2子域 · 26对象 · 29关系
  <span v-if="incremental.externalBusinessObjects > 0" class="external-badge">
    +{{ incremental.externalBusinessObjects }}外部对象
  </span>
</span>
```

### 3.4 核心改动 4：分类树修复（次要）

文件：[`relationClassifier.js:456-460`](file:///d:/filework/excel-to-diagram/src/services/relationClassifier.js#L456-L460)

**修复 CROSS_BOUNDARY 实际分类**（将 line 498-500 的 EXTERNAL 二分法改为三分）：

```js
// 改为三分: 范围内 / 跨域 / 范围外
const scopeType = (sourceInScope && targetInScope)
  ? ScopeType.INTERNAL
  : (sourceInScope || targetInScope)
    ? ScopeType.CROSS_BOUNDARY
    : ScopeType.EXTERNAL
```

**注意**：**这部分修复作为次要**，**不阻塞主要修复**。即使不改分类树，**核心改动 1 的补全逻辑**已能保证 id=29 入 `filteredRelations` 和 TEST600 入 `rfb`。

---

## 4. 数据流

```
用户选择 selectedRelationNodeIds
  ↓
[3.1 修复] filteredRelations = fromTree ∪ fromCrossBoundary
  ↓
relationFilteredBoCodes (line 372)  ←  from filteredRelations
  ↓
externalBoCodes (line 252)          ←  rfb - centerScope
  ↓
incrementalStats (line 403) + externalBusinessObjects 字段
  ↓
displayStats.incremental → 导航栏 (line 283) → 末尾 +外部对象
```

---

## 5. 验证

### 5.1 测试脚本

[test_28_vs_29_fix.py](file:///d:/filework/excel-to-diagram/test_helpers/scripts/test_28_vs_29_fix.py) 验证：
- 关系数: 28 → **29** ✓
- 对象数: 25 → **26** ✓
- TEST600 节点在 SVG ✓
- 导航栏含 `+1外部对象` ✓

### 5.2 手工验证

**场景 A — 全选（默认）**：
1. 选 26 中心 BO
2. 关系全选
3. 期望：29 关系 / 26 对象 / `+1外部对象` / TEST600 节点可见

**场景 B — 只选 INTERNAL**：
1. 选 26 中心 BO
2. 关系只勾 INTERNAL 节点
3. 期望：22 关系 / 26 对象 / 无 `+外部对象` / TEST600 不可见（不引入）

**场景 C — 取消所有关系**：
1. 选 26 中心 BO
2. 关系全不选
3. 期望：0 关系 / 26 对象 / 无 `+外部对象`

### 5.3 边界

- **完全范围外关系** (src∉cs, tgt∉cs)：**不补全**（按用户决策 1）
- **自环关系** (`sourceCode === targetCode`)：**排除**
- **空 previewData**：`fromCrossBoundary = []`，不报错

---

## 6. 影响范围

| 文件 | 改动 |
|------|------|
| `useDiagramData.js:364-366` | `filteredRelations` 加跨域补全 |
| `useDiagramData.js:403-409` | `incrementalStats` 加 `externalBusinessObjects` |
| `AADiagramApp/index.vue` (导航栏) | 末尾追加 `+N外部对象` |
| `relationClassifier.js:498-500` (次要) | 三分法分类 |

**不改动**：
- `StatsDisplay.vue` 表格（已显示 `external` 行）
- `StepConfig.vue` 颜色配置（`centerScopeColor` 已支持）
- `groupModel/UnifiedRenderer.js` 渲染（自动跟随 rfb）
- `StepScope.vue` "新增业务对象" 列表（已基于 rfb）

---

## 7. 风险评估

| 风险 | 概率 | 缓解 |
|------|------|------|
| `relationCategoryTree` 返回不稳定 → 补全分支 N/A | 低 | 不动 tree 内部 |
| `selectedRelationNodeIds` 格式变化 | 中 | 用 `startsWith` 前缀匹配，宽松 |
| `previewData.relationships` 缺少 `id` 字段 | 低 | `rel.id == null` 跳过 |
| 自环被补全 | 低 | 显式排除 `sourceCode === targetCode` |
| 用户清空 selectedRelationNodeIds 后再点全选 | 低 | computed 依赖触发自动重算 |

---

## 8. 不在范围

- ❌ **不**重构 `relationCategoryTree` 树结构（用户决策 2）
- ❌ **不**处理完全范围外关系 (用户决策 1)
- ❌ **不**修改 groupModel 渲染层
- ❌ **不**改 StatsDisplay 表格（已有 external 行）
- ❌ **不**改 serviceModule 图逻辑
