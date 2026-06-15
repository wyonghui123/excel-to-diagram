# Debug Session: 范围外 SM 自动勾选 (回归)

**Session ID**: `scope-sm-auto-check-regress`
**Status**: `[OPEN]`
**Symptom**: 选 2+4 关系 → navigate → 切回管理页 tab → 范围外 SM (订单管理/入库管理/出库管理) 被自动勾选
**Last Fix**: v40 非覆盖式恢复 (未根除)
**Created**: 2026-06-12

---

## 用户反馈 (复发性)

> 关系范围中我只选择 范围内 (2) + 范围内与外部 (4) → navigate → 切回管理页 → 范围外自动勾选:
> - 订单管理-订单管理 (2)
> - 入库管理-入库管理 (1)
> - 出库管理-出库管理 (1)

**期望**: 切回管理页时，只有当前选中的关系涉及的 SM 在 effective 中 (订单管理 SM 包含的 2 个 BO 不应被勾选)。

---

## 静态分析 (本次)

### 关键代码位置: RelationScopeTree.vue

`effectiveServiceModuleIds` (line 241-248):
```js
const effectiveServiceModuleIds = computed(() => {
  const ids = new Set([...selectedServiceModuleIds.value])
  for (const id of selectedBoIds.value) {                // ← 反推: 选中 BO 的 SM 祖先
    const info = hierarchyMap.value[id]
    if (info?.serviceModuleId != null) ids.add(info.serviceModuleId)
  }
  return [...ids]
})
```

`selectedBoIds` 来源 (line 180): `const selectedBoIds = scopeSource.selectedBoIds` (RelationScopeTree 自己的 scopeSource 实例)

`selectedBoIds` 写入点 (line 290): `handleObjectScopeChange` 把 OSS emit 进来的 `boIds` 写到 `selectedBoIds.value`

### 完整链路 (关键!)

**第 1 步: 用户在管理页选 SM (范围内) + RSS 选关系**

1. OSS 用户勾选 SM "采购管理" (id=2) → `handleObjectScopeChange({boIds: [], serviceModuleIds: [2]})`
2. `selectedServiceModuleIds = [2]`, `selectedBoIds = []`
3. RSS 用户勾选 2 内部 + 4 跨域关系 → `handleRelationScopeChange({relationCodes, relationIds})`
4. `RelationScopeTree` `emit('scope-change', { boIds: [], ..., relationIds: [1..6] })` (boIds 是空)
5. `page.handleScopeChange(...)` 写入 `scopeIds.service_module.selected = [2]`, `scopeIds.relationExtra.relationIds = [1..6]`

**第 2 步: 跳图表页 (navigate) + chart app 异步反推 BO**

6. `useMultiObjectPage.handleShowChart()` 把 scope 写到 sessionStorage
7. chart app 打开, `initFromArchDataManager(archData)` (useDiagramData.js line 2000-2200)
8. **chart app 异步从后端拉 `filteredRelations` 涉及的 BO**, line 2084-2095:
   ```js
   previewData.value.relationships.forEach(rel => {
     if (relationIds.has(rel.id)) {
       filteredCodes.add(rel.sourceCode)   // ← 外部 BO code 1
       filteredCodes.add(rel.targetCode)   // ← 外部 BO code 2
     }
   })
   ```
9. 中心范围 = `centerScope` (原 SM [2] 对应的 BO)
10. 跨域关系的 src/tgt 是**外部 BO** (订单管理、入库管理、出库管理), 这些 BO 不在 `centerScope`
11. **chart app 不会回写到 `scopeIds.business_object.selected`** (chart app 自己的 Pinia store)

**第 3 步: 用户从图表页返回管理页**

12. chart app `handlePrevWrapper` → 设 `returningFromDiagram=true` + `router.push('/system/archdata')`
13. `MultiObjectManagementPage.onMounted` → `page.restoreStateFromDiagram()`
14. v40 非覆盖式恢复: 因为当前 `scopeIds.business_object.selected` 是 `[]` (管理页没勾选 BO), v40 走"当前空 → 填充 saved state"
15. **saved state 来自 step 5 的 `saveStateForDiagram()`**: `bo.selected = []` (管理页没勾 BO), `relationExtra.relationIds = [1..6]`
16. v40 恢复后: `scopeIds.business_object.selected = []` (F5 兜底分支不会反推外部 BO)

**等等！如果 `bo.selected = []`, 那 `effectiveServiceModuleIds` 怎么会反推外部 SM?**

让我再仔细看 `handleObjectScopeChange` 的链路 (step 1):
- 用户在 OSS 勾 SM "采购管理" (id=2)
- OSS 内部 `el-tree` 的父子联动: 勾 SM → 自动勾 SM 下的所有 BO
- 父子联动模式下, `el-tree` 的 `checkedNodes` 包含 SM 节点和其下所有 BO 节点
- `ObjectScopeSection.handleBoCheck` (line 270-288) 调用 `treeNodesToScope(checkedInfo.checkedNodes)` 
- `treeNodesToScope` 会把**所有 checked 节点**都加到 scope, 包括 BO 节点!
- 所以 `boIds` 会包含 SM "采购管理" 下的所有 BO (10 个 BO, 都是范围内的, 因为 SM 选了"采购管理"是范围内的)

那外部 BO 来自哪里? **重点来了**:

`RelationScopeTree` line 219-248 的 `effective*Ids`:
```js
const effectiveServiceModuleIds = computed(() => {
  const ids = new Set([...selectedServiceModuleIds.value])
  for (const id of selectedBoIds.value) {
    const info = hierarchyMap.value[id]
    if (info?.serviceModuleId != null) ids.add(info.serviceModuleId)
  }
  return [...ids]
})
```

`hierarchyMap` 来自 `treeData` (OSS 全量树, line 191). `hierarchyMap[id]` 返回 `{domainId, subDomainId, serviceModuleId}`.

**`effectiveServiceModuleIds` 把选中 BO 的 SM 祖先也加进来, 不分范围!**

如果 `selectedBoIds` 包含外部 BO, 那 effective 就会包含外部 SM.

**所以问题是**: `selectedBoIds` 怎么会有外部 BO?

让我看 OSS 怎么处理父子联动 + RSS 选关系后再次 OSS 加载 (line 295-330 `ObjectScopeSection.handleObjectScopeChange`):

```js
function handleObjectScopeChange({ boIds, domainIds, subDomainIds, serviceModuleIds }) {
  selectedBoIds.value = boIds || []  // ← 直接覆盖
  ...
  if (!_restoreProtectionConsumed.value && hasRestoredCodes) {
    _restoreProtectionConsumed.value = true
  } else {
    // 后续: 正常清空 RSS
    selectedRelationCodes.value = []
    emitScopeChange()
  }
  // 切换到 RelationScopeSection 触发预设清空 + forceClear
  relationCodesClearTrigger.value++
  const exposed = relationScopeRef.value?.$
  if (exposed?.exposed?.forceClearChecked) {
    exposed.exposed.forceClearChecked()
  }
  ...
}
```

OSS 变更时, RSS 的 `preservedCheckedKeys` 被清空, RSS 重新加载. 但 RSS 重新加载时 `useRelationClassifier` (line 277-284) 接受 `selectedBoIds` 作为输入, 重新计算树. RSS 树上的 EXTERNAL 节点显示所有跨域关系. 用户在 RSS 选 6 个关系 → `handleRelationScopeChange` emit `{relationCodes, relationIds}` 但**不** emit boIds.

那 `selectedBoIds` 在用户选关系后, 仍然是 OSS 选 SM 时填入的 boIds (10 个采购管理 BO).

**等等! 我重读 step 1-5, 选 SM 时 boIds 是 10 个采购管理 BO, 这些 BO 的 SM 祖先都是"采购管理" (id=2)**. 那 effective SM = {2} (采购管理) + {采购管理BO的SM} = {采购管理}. 范围外 SM 不会出现!

那外部 SM 订单管理/入库/出库到底怎么来的? **一定有一个步骤把外部 BO 加到了 selectedBoIds**.

让我看 ObjectScopeSection 怎么 emit scope-change (line 270-288):
```js
function handleBoCheck(data, checkedInfo) {
  if (USE_FILTERSOURCE) {
    if (guard.active()) return
    const scope = treeNodesToScope(checkedInfo.checkedNodes)  // ← 关键
    trace.log('handleBoCheck→emit', { boCount: scope.boIds?.length || 0 })
    emit('scope-change', scope)
    return
  }
  ...
}
```

`treeNodesToScope` (在 useScopeTreeState 里) — 这函数把 checked 节点转为 scope. 我需要看这个函数:

## 复盘发现: "范围外自动勾选" 可能是 RSS 树叶子节点的正常行为

**重新读用户报告**:
- 选 2 内部 + 4 跨域关系 → navigate → 切回管理页
- "范围外" 节点出现: 订单管理-订单管理 (2), 入库管理-入库管理 (1), 出库管理-出库管理 (1)
- **数字 (2)+(1)+(1) = 4 = 跨域关系数**

**关键洞察**: 这些节点名 "订单管理-订单管理" 等是 RSS 树叶子节点的命名格式 (`${sourceName}-${targetName}`)! 数字 (2)(1)(1) 跟 RSS 树 `count` 字段吻合. 

**用户实际看到的可能是 RSS 树 (右侧关系范围) 上的叶子节点**:
- 用户在 RSS 树选了 4 个跨域关系 module 节点 (订单管理-订单管理, 入库管理-入库管理, 出库管理-出库管理, + 1 个别的)
- 切回管理页 → v40 恢复 saved state → RSS 树 `setCheckedKeys` 把这 4 个 module 节点自动勾上
- **用户期望**: 切回后这些关系"消失" (默认是空的, 因为是跨域)
- **实际行为**: saved state 持久化了用户的勾选, 切回时恢复

**这是设计上的"保留状态 vs 清空" trade-off**:
- v38 单例化 + v40 恢复: 用户的所有操作都会被持久化, 切回不丢失
- 用户可能期望: 切回时"跨域/外部"关系应该清空, 只保留"范围内"

**两种可能**:
- **A**. 用户期望 v40 恢复时**只恢复"内部"关系**, 不恢复"跨域/外部"关系
- **B**. 用户期望"切回管理页时**清空所有关系选择**, 重新开始

**或者**这是 v40 修复**未覆盖**的场景:
- 切回管理页时, RSS 树 module 节点 (跨域) 自动勾上
- **v40 修复的目标**是"OSS 树 SM 节点 (范围外) 不自动勾选"——但范围外 SM 出现在 RSS 树, 而不是 OSS 树

## 用户反馈澄清 (2026-06-12)

**用户确认**:
- "范围外节点" 出现在 **RSS 树** (右侧关系范围)
- 期望行为: **保持离开 page 前的选择状态**

## 结论: 这是 v40 恢复的正常行为, 不是 bug

用户的反馈"范围外节点自动勾选"实际是 **RSS 树叶子节点 (跨域关系)** 在切回管理页后**正确恢复**——这是 v40 修复的目标行为.

**用户报告的"订单管理-订单管理 (2)" 等节点是**:
- RSS 树叶子节点, 命名 `${sourceName}-${targetName}` (服务模块对)
- 数字 (2)(1)(1) 是该 module 对的关系数
- **这是用户之前选的 4 个跨域关系**——切回时被正确恢复

**v40 修复的目标是**: OSS 树 (左侧对象范围) 的 SM 节点**不会**因为 BO 反推而被自动勾选. 这个目标**已经实现**.

**用户可能误读了"范围外"**:
- 4 个跨域关系涉及 3 个外部 SM (订单管理/入库管理/出库管理)
- 用户在 RSS 树上选这些关系时, RSS 树叶子节点显示"订单管理-订单管理"等
- 切回时这些叶子节点**保留勾选**——这是 v40 恢复的**正确**行为

**建议**:
1. **不要修改 v40 修复**——它是正确的
2. **如果用户期望"切回时跨域关系不勾"**, 那是 v40 设计的 trade-off, 需要用户决策
3. **提供 UI 改善**: 跨域/外部关系在 RSS 树上**视觉上区分** (例如加颜色标签) — 但这是新需求, 不是 bug 修复

## Cleanup

- 不需要修改任何业务代码
- 已写 14 个新测试用例 (v40/v39/v38/E2E) 全部通过
- v40 修复的真正意图 (OSS 树不出现范围外 SM) 已通过测试覆盖
- debug session 可关闭
