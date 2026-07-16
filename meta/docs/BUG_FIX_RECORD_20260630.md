# BUG FIX RECORD - 2026-06-30

## 问题 1：对象范围树勾选级联问题

### 现象

在架构管理页面，对象范围树勾选"库存管理"服务模块（叶子节点）时，
整个"供应链云"领域及其下所有节点都被勾选。

### 根因（两层）

#### 根因 1：`:default-checked-keys` 绑定含父节点 key

`objectCheckedNodeKeys` computed（`ObjectScopeSection.vue` 行 159-161）
直接返回 `scopeToNodeKeys()` 的结果，该函数从 `scopeIds.effective` 提取的
父节点 id（如 domain d_1）对应的 node key。

computed 绑定到 el-tree 的 `:default-checked-keys`（模板行 49）。

当 `loadTreeData` silent 模式下 `sameStructure=false` 时，
`treeData.value = newTree` 触发 el-tree 重建，`:default-checked-keys`
重新应用 → 父节点 d_1 被设为 checked → 在 `check-strictly=false` 下
**向下级联勾选整个子树**。

#### 根因 2：guard.enter() 时序错误

原来 `guard.enter()` 在 `treeData.value = newTree` **之后**才执行。
el-tree 重建时触发的 @check 事件（因 `:default-checked-keys`）在 guard 之外，
`handleBoCheck` emit scope-change → scopeIds 被污染。

### 修复

#### 修复 1：`objectCheckedNodeKeys` computed 用 `collectLeafKeys` 过滤

```javascript
// Before
const objectCheckedNodeKeys = computed(() => {
  return scopeToNodeKeys(treeData.value, props.scopeIds)
})

// After
const objectCheckedNodeKeys = computed(() => {
  const allKeys = scopeToNodeKeys(treeData.value, props.scopeIds)
  return collectLeafKeys(allKeys, treeData.value)  // 只返回叶子节点 key
})
```

#### 修复 2：guard.enter() 提前 + setCheckedKeys 过滤

```javascript
// Before
treeData.value = newTree
// ... 若干 nextTick
guard.enter()
treeRef.value.setCheckedKeys(currentCheckedKeys)

// After
guard.enter()  // 提前到 treeData.value 之前
treeData.value = newTree
// ...
const leafCheckedKeys = collectLeafKeys(currentCheckedKeys, newTree)
treeRef.value.setCheckedKeys(leafCheckedKeys)
```

### 关键经验

1. **el-tree `:default-checked-keys` vs `setCheckedKeys`**：两者在 `check-strictly=false`
   下行为相同——设置父节点 checked 都会向下级联勾选子树。
   之前只保护了 `watch` 中的 `setCheckedKeys`，忽略了 `:default-checked-keys` 绑定。

2. **guard 保护范围**：guard 只保护 `guard.enter()` 之后的代码。
   `treeData.value = newTree` 触发 el-tree 重建，`:default-checked-keys` 在重建过程中
   重新应用，此时 guard 还未激活。

3. **collectLeafKeys v1 vs v2**：
   - v1 错误：在父节点 key 在 set 中时，推导其所有叶子子节点 → 导致 setCheckedKeys
     设置所有叶子 → 向上传播让整个子树 checked
   - v2 正确：只保留 newKeys 中本身就是叶子的 key，不推导父节点的子节点

4. **effective ids 的来源**：effective ids 来自 `hierarchyMap`（`RelationScopeTree.vue`），
   从子孙节点推导祖先 domain/sub_domain id。`scopeToNodeKeys` 从 effective ids
   匹配树节点返回 node keys，返回值含父节点 key。

---

## 问题 2：对象范围树勾选后自动收起

### 根因

`loadTreeData` silent 模式下 `sameStructure` 短路保护被 `!USE_FILTERSOURCE`
条件跳过，导致每次勾选都重建 treeData → el-tree 重建 → 用户展开状态丢失。

### 修复

去掉 `!USE_FILTERSOURCE` 条件，让 sameStructure 短路保护对所有模式生效。

---

## 问题 3：对象范围树勾选 → 领域/子领域表格不联动

### 根因

`RelationScopeTree.vue` 中 `hierarchyMap` key 类型不匹配：
`ObjectScopeSection.vue` 的 `selectedDomainIds` 等是 number[]，
但 `hierarchyMap[domainId]` 用字符串 key 查询。

### 修复

`hierarchyMap` 用 `originalId`（number）作 key/value，与 `selectedXxxIds` 类型对齐。

---

## 涉及文件

| 文件 | 修复内容 |
|------|---------|
| `src/components/common/RelationScopeTree/ObjectScopeSection.vue` | collectLeafKeys v2；objectCheckedNodeKeys 过滤；guard 时序 |
| `src/components/common/RelationScopeTree/RelationScopeTree.vue` | hierarchyMap key 类型 |
| `src/composables/useMermaid/annotation/useAnnotation.js` | 备注过滤 |
| `src/composables/useMermaid/tooltip/useTooltip.js` | tooltip 按 filter 过滤 |
| `src/composables/useMermaid/renderer/useSvgProcessor.js` | 透传 filter |
| `src/composables/useMermaid/syntax/useBusinessObjectSyntax.js` | 透传统数数组 + 编码修复 |
| `src/composables/useMermaid/syntax/useBlockDiagramSyntax.js` | 透传统数数组 |

---

## CHANGELOG

| 日期 | 修复人 | 修复内容 |
|------|--------|---------|
| 2026-06-30 | AI Assistant | 级联勾选修复（两层根因）；树收起修复；表格联动修复；备注过滤修复 |
