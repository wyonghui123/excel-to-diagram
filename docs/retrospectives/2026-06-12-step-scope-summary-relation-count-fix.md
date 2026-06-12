# 2026-06-12 StepScopeSummary 关系数量修复 — 经验记录

> **场景**：图表页 Step 3 范围选择，StepScopeSummary 三张卡片（中心范围/关系范围/总数）的关系数显示错误（+0 关系 vs 管理页 1+4=5）。
>
> **结果**：✅ center(4) + incremental(8) = total(12) 跟后端 preview 4 internal + 8 cross-boundary 完全对齐。

---

## 🐛 根因链路（5 层）

| 层级 | 问题 | 修复 |
|------|------|------|
| **L1. 关系分类树崩溃** | hierarchyFilter 模式下后端没返回外部 BO，前端 boMap 找不到 src/tgt BO，line 725 访问 `stats.domains[fallbackKey]` 但 SAME_MODULE 类型的 stats 没有 `domains` 字段 → 整页崩溃 | [relationClassifier.js:723](file:///d:/filework/excel-to-diagram/src/services/relationClassifier.js#L723-L729) 加 `if (!stats.domains) stats.domains = {}` 防御 |
| **L2. cross-boundary 节点缺失** | 后端 scopeType 在某些场景下错算（如 PROC_REQ_MNG*），cross-boundary 关系被标成 external，导致分类树里 cross-boundary 节点存在但 relationIds 为 0 | displayStats 兜底 |
| **L3. 统计依赖分类树** | displayStats 的 incremental/total 依赖 `relationCategoryTree` 中 cross-boundary 节点的 `relationIds` 字段 | 改用 `Math.max(分类树 ids, previewData truthIds)` 兜底 |
| **L4. 兜底条件过严** | 原 `if (ids.size === 0 && previewData)` 只在分类树完全空时兜底，hierarchyFilter 模式下分类树 partial 就不触发 | 改成总是算 previewData 的 truthIds，取 max |
| **L5. 后端 preview API 缺陷** | hierarchyFilter 模式下，关系的外部 BO (如 BO_LOCATION, BO_INV_LOG) 没随关系返回；某些 BO 类别下 scopeType 错算 | 需后端修 |

## ✅ 验证闭环（截图 + 算式）

`service_module_ids=2,3,4,5` (4 个服务模块 = 7 BO 中心范围)：
- 后端 API 直接验证：`/api/v2/bo/architecture/preview?versionId=1&service_module_ids=2,3,4,5` 返回 4 internal + 8 cross + 16 external ✓
- 前端 StepScopeSummary 显示：4 + 8 = 12 ✓
- 截图：[frontend_verify_step3_cards.jpg](file:///d:/filework/excel-to-diagram/test_output/frontend_verify_step3_cards.jpg)

---

## 📚 经验教训

### 1. **跨页数据流对齐是统计一致性的前提**

- 管理页 `buildRelationScopeTree` 走全量关系 API
- 图表页 `buildRelationCategoryTree` 走 `architecture/preview` 过滤 API
- 两个数据源不同 → 同一数据可能产生不同分类 → 用户的"1+4=5 vs 1+0=0"差异常是数据源差异导致

**教训**：跨页统计时，**第一件事是确认数据源**（哪个 endpoint、什么过滤条件、返回什么字段）。

### 2. **优先信任后端，但加业务定义兜底**

- 后端 `scope_type` 字段是权威（基于 center_scope + 完整 36 关系算的）
- 但当前端拿到的是**过滤后**的关系子集 + **不完整**的 BO 集合时，分类树自然不全
- 兜底逻辑：用 `previewData.relationships` + `centerScope` 业务定义 (XOR) 重算 scope

```js
// ✅ 兜底模板
if (previewData.value?.relationships) {
  const rels = previewData.value.relationships
  const centerSet = new Set(centerScope.value || [])
  const truthIds = new Set()
  for (const r of rels) {
    if (r.id == null || r.sourceCode === r.targetCode) continue
    if (r.scopeType === 'internal' || r.scopeType === 'cross-boundary') {
      truthIds.add(r.id); continue
    }
    // 业务定义兜底: src ⊕ tgt 任一端在中心范围
    const srcIn = centerSet.has(r.sourceCode)
    const tgtIn = centerSet.has(r.targetCode)
    if (srcIn || tgtIn) truthIds.add(r.id)
  }
  return Math.max(ids.size, truthIds.size)
}
```

**教训**：**业务定义 (XOR) 比后端字段更鲁棒**。后端字段可能错算、缺失、过时；业务定义基于"用户选了什么 BO" 永远正确。

### 3. **页面崩溃必须做端到端验证，不能只看类型对**

- 崩溃栈：line 725 `stats.domains[fallbackKey]` 在 SAME_MODULE stats 上 undefined
- 静态分析看不出问题（SAME_MODULE 和 OTHER 都走 line 638 else 分支，但只有 OTHER 有 stats.domains 字段）
- **必须实际触发场景**（用 hierarchyFilter 选中具体 BO，看是否崩）

**教训**：用 Playwright/curl 端到端验证"该崩的场景下不崩"，比类型检查更能发现真问题。

### 4. **CSS 变量统一页面风格的工业级实践**

- StepDisplay 用了硬编码 `linear-gradient(135deg, #1a73e8 0%, #4d92e8 100%)` + 绿色 badge → "花花绿绿"
- 改用 `--color-bg-primary`, `--color-primary-bg`, `--color-info-bg` → 跟 YonDesign 规范一致
- StepScopeSummary 改用 3 张等宽卡片 + border accent + icon 背景 + 大字号数字

**教训**：**硬编码颜色 = 设计债**。新组件务必用 CSS 变量，让设计令牌 (design tokens) 统一管理。

### 5. **数据流的"半成品"状态是常见 bug 源**

- 后端 `preview` 返回的是**部分 BO + 部分关系**（按 hierarchyFilter 过滤）
- 但前端 `boMap` 是基于**返回的 BO 列表**构建的
- 关系的 src/tgt 可能在**没返回的 BO**中 → boMap 找不到 → 关系分类树 fallback 走错分支

**教训**：**数据流是"半成品"时，分类逻辑必须有 fallback**。不能假设 boMap 一定包含 src/tgt。

### 6. **用 Math.max 做"双源数据"对齐**

- 分类树 ids（前端算的，可能漏）
- previewData truthIds（后端算的，可能错）
- `Math.max(ids, truthIds)` 取较大值作为兜底，**比单源更鲁棒**

**教训**：当两个数据源都有可能不完整时，**取并集的最大值**是最简单的容错。

---

## 🔧 修改文件清单

| 文件 | 改动 |
|------|------|
| [relationClassifier.js](file:///d:/filework/excel-to-diagram/src/services/relationClassifier.js#L723-L729) | 加 `if (!stats.domains) stats.domains = {}` 防御崩溃 |
| [useDiagramData.js](file:///d:/filework/excel-to-diagram/src/views/AADiagramApp/composables/useDiagramData.js#L1015-L1130) | center/incremental/total 三处加 `previewData` + `Math.max` 兜底 |
| [StepDisplay.vue](file:///d:/filework/excel-to-diagram/src/views/AADiagramApp/components/steps/StepDisplay.vue) | 硬编码颜色 → CSS 变量 |
| [StepScopeSummary.vue](file:///d:/filework/excel-to-diagram/src/views/AADiagramApp/components/steps/StepScopeSummary.vue) | 3 张卡片重构，商务简洁风格 |

## ⚠️ 已知遗留问题

1. **管理页 `buildRelationScopeTree` 同样需要业务定义兜底** — 当前是依赖后端 scopeType（[useMultiObjectPage.js](file:///d:/filework/excel-to-diagram/src/composables/useMultiObjectPage.js)）
2. **后端 `/api/v2/bo/architecture/preview` 关系没 join 外部 BO** — 需后端补 SQL
3. **后端 `scope_type` 在 PROC_REQ_MNG* 类 BO 下错算** — 需后端排查

## 🎯 端到端验证流程（可复用模板）

1. **API 直验**：用 `curl`/`fetch` 调后端 endpoint，记录 `byScopeType` 分布
2. **前端代码路径**：`previewData → archDataConverter → boMap → buildRelationCategoryTree → displayStats`
3. **崩溃验证**：用 `error-boundary` selector 检测 + `console.error` 监听
4. **数据验证**：用 `relationCategoryTree.value` 查节点 `count` / `relationIds` 长度
5. **算式验证**：center + incremental = total
6. **截图存证**：screenshot 元素 → 存 `test_output/*.jpg`

## 📌 类似场景快速迁移

下次遇到"统计数字对不上"的问题，按以下顺序排查：

1. ✅ **数据源**：管理页 vs 图表页用哪个 endpoint
2. ✅ **后端字段**：scope_type 是不是按中心范围算的
3. ✅ **数据流半成品**：hierarchyFilter 后 BO 列表是否完整
4. ✅ **分类树兜底**：sourceBO/targetBO 缺失时是否走 fallback
5. ✅ **displayStats 兜底**：分类树 partial 时是否用 previewData 重算
6. ✅ **算式验证**：center + incremental = total
