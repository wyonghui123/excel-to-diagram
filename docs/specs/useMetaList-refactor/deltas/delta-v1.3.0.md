## 目录

1. [1. 章节变更清单](#1-章节变更清单)
2. [2. 详细变更（增量内容）](#2-详细变更（增量内容）)
3. [19. DetailPage ↔ MetaListPage 双向链路分析（v1.3.0 补充）](#19-detailpage-metalistpage-双向链路分析（v130-补充）)

---
# Delta v1.3.0: §19 DetailPage 双向链路 + 25 文件

> **基线版本**: v3.0.0
> **目标版本**: v1.3.0
> **变更日期**: 2026-06-06
> **变更类型**: 增量
> **源 spec**: [spec-fr-ui-003-004-005-useMetaList-refactor.md v1.5.0](file:///d:/filework/excel-to-diagram/docs/specs/spec-fr-ui-003-004-005-useMetaList-refactor.md) L2032-L2387
> **章节数**: § 增量 §19 DetailPage 双向链路 + 25 文件

## 1. 章节变更清单

| # | 章节 | 类型 | 摘要 |
|:-:|------|:---:|------|
| §X | §19 DetailPage 双向链路 + 25 文件 | 增量 | 详见 §2 详细变更 |

## 2. 详细变更（增量内容）

## 19. DetailPage ↔ MetaListPage 双向链路分析（v1.3.0 补充）

> **目标**：深入审计 DetailPage 对 MetaList 的依赖，揭示之前 §16 未发现的 5 个真实 consumer 与双向刷新链
> **数据来源**：[DetailPage.vue L1-1107](file:///d:/filework/excel-to-diagram/src/components/common/DetailPage/DetailPage.vue) + [ObjectPage/* L1-137](file:///d:/filework/excel-to-diagram/src/components/common/ObjectPage/) + [ObjectChildSection.vue L1-633](file:///d:/filework/excel-to-diagram/src/components/common/ObjectChildSection/ObjectChildSection.vue) + 双向 grep
> **结论先行**：**真实破坏面 17 → 25**；**DetailPage 自身 0 个 useMetaList 调用**，但通过 ObjectPage 的 section 配置**间接控制 4 处 MetaListPage 嵌入**（displayMode='embedded' ×3 + 双模式 ×1）

### 19.1 关键纠正：v1.2.0 §16 真实破坏面计算有遗漏

| 维度 | v1.2.0 §16.5 假设 | v1.3.0 实际 |
|------|----------------|------------|
| 直接 `import useMetaList` 文件数 | 6 | 6 ✅ |
| 直接 `import MetaListPage` 文件数 | **未统计** | **12**（+6 个新发现） |
| 总计真实破坏面 | 17 个 | **25 个**（+8） |
| 双向循环 | 未识别 | **MetaListPage → DetailPage → ObjectPage → MetaListPage** |
| displayMode 维度 | 未提及 | 4 种（page/embedded/dialog/未指定） |

### 19.2 DetailPage 组件家族规模（v1.3.0 实际数据）

```
src/components/common/DetailPage/                 (54.9KB / 1824 行)
├── DetailPage.vue                                35.3KB / 1107 行  (核心)
├── DetailSection.vue                             17.7KB /  627 行
├── AssociationSection.vue                        1.8KB /   98 行  (简化包装)
└── index.js                                      0.1KB /    2 行

src/components/common/ObjectPage/                 (64.1KB / 2194 行)
├── ObjectPage.vue                                2.7KB /   61 行  (轻量壳)
├── ObjectPageShell.vue                          23.6KB /  865 行
├── ObjectPageContent.vue                        14.5KB /  507 行  (含 AssociationSection)
├── ObjectPageWithChildren.vue                    4.5KB /  137 行  (含 ObjectChildSection)
├── ObjectPageField.vue                          11.1KB /  405 行
└── ObjectPageHeader.vue                          7.7KB /  289 行

src/views/ObjectDetailPage.vue                    13.2KB /  499 行  (路由级 DetailPage 包装)
```

**合计 119.0KB / 4,517 行** —— 这是与 useMetaList 重构密切相关的"详情页生态"。

### 19.3 双向循环依赖图（v1.3.0 实际代码审计）

```
┌────────────────────────────────────────────────────────────────────┐
│                MetaList (table/list UI)                            │
│  MetaListPage.vue (50KB / 1772 行)                                │
│  ├─ 75+ 公开 API 给 MetaListPage 自身解构                          │
│  └─ openDetailDrawer() ────────────────────┐                      │
└───────────────────────────────────────────│──────────────────────┘
                                            │
                                            ▼
              ┌──────────────────────────────────────────────┐
              │      DetailPage (35KB / 1107 行)              │
              │  - 抽屉模式（el-drawer）                      │
              │  - 独立模式（standalone）                     │
              │  - service: boService (v1 backend)           │
              │                                                │
              │ 透传 2 个 useMetaList 字段（L721/L739）       │
              │  ↓                                            │
              │ <ObjectPage> (61 行)                         │
              │   ├─ <ObjectPageContent>                    │
              │   │   ├─ FieldGroupSection                  │
              │   │   ├─ HistorySection                     │
              │   │   └─ <AssociationSection>  ←────────┐   │
              │   │                                     │   │
              │   └─ <ObjectPageWithChildren>           │   │
              │       └─ <ObjectChildSection>  ←────┐   │   │
              └─────────────────────────────────────│───│───┘
                                                    │   │
   ┌────────────────────────────────────────────────┘   │
   │                                                    │
   ├─→ ObjectPage/AssociationSection.vue (1.8KB)       │
   │     (1.8KB 简化包装，但逻辑有 633 行)             │
   │     ├─ isManyToMany: <MetaListPage embedded :options.fetcher=queryAssociations />
   │     ├─ isAnnotation: <MetaListPage embedded :objectType='annotation' (硬编码) />
   │     └─ default: <MetaListPage embedded :initial-filters={parent_id: id} />
   │     (3 处 MetaListPage 嵌入)
   │
   └─→ ObjectChildSection/ObjectChildSection.vue (11.1KB)
         (双模式开关)
         ├─ useMetaList=false (默认): useParentChild 自实现 + el-table
         └─ useMetaList=true: <MetaListPage embedded :options=metaListOptions />
         (双模式切换)
```

### 19.4 4 种 displayMode 完整画像

| displayMode | 消费方 | 数量 | 关键差异 |
|-------------|--------|:---:|---------|
| `'page'` | GenericObjectList / AuditLogManagement / 6 死代码 stub | 8 | **全功能**（工具栏 + 详情 + 导入导出 + 完整 dialog 容器） |
| `'embedded'` | ObjectPage/AssociationSection (×3) + ObjectChildSection (useMetaList=true) | 4 | **嵌入模式**（无外壳、无 toolbar header、嵌入父容器） |
| `'dialog'` | SearchHelpDialog + AssignmentDialog | 2 | **弹窗模式**（el-dialog 容器，无 page header） |
| 未指定 | MultiObjectManagementPage | 1 | 默认行为（推测为 page 模式） |
| **小计** | **12 个 .vue** | **15 处 MetaListPage 嵌入** | - |

**新发现**：`displayMode` 是 useMetaList 重构的**关键行为维度**——refactor 后必须保证 **3 种 displayMode × 完整 API 行为不变**。

### 19.5 5 个新发现的 consumer 详细分析

#### 19.5.1 ObjectPage/AssociationSection.vue（**3 处 MetaListPage 嵌入**）

| 场景 | 触发条件 | displayMode | 关键 props | fetcher 来源 |
|------|---------|-------------|-----------|-------------|
| **Many-to-Many 关联** | assocType='many_to_many' + assocName + targetType | embedded | `:columns-override=manyToManyColumns` | `boService.queryAssociations` (L196) |
| **Annotation 备注** | section.type='annotation' + hasRealObjectId | embedded | `:object-type='annotation'` (硬编码) | 自定义 `annotationFetcher` (L311-329) |
| **普通关联** | targetType + objectType + objectId | embedded | `:initial-filters={parent_id: id}` (L285) | `boService.queryAssociations` (L289) |

**风险等级**：🔴 **高**——详情页核心场景，重构 useMetaList 必须保证 3 处嵌入行为不变

**refactor 影响**：
- 任何 useMetaList 公开 API 的行为/默认值变化 → 3 处嵌入同步出问题
- fetcher 注入机制（`options.fetcher`）必须保持兼容
- inject 协同（`registerMetaListRef` from MetaListPage via ObjectPage L180）必须保留

#### 19.5.2 ObjectChildSection.vue（**双模式开关**）

```vue
<!-- 模式 1: useMetaList=false (默认，自实现) -->
<div v-else-if="hasData" class="ocs-table-wrapper">
  <el-table :data="data"> ... </el-table>  <!-- 简单表格 -->
</div>

<!-- 模式 2: useMetaList=true (高级模式) -->
<div v-if="useMetaListMode" class="ocs-metalist-wrapper">
  <MetaListPage :object-type="childObjectType" :options="metaListOptions"
                :initial-filters :enable-detail :enable-auto-crud
                :row-mutability="effectiveRowMutability" />
</div>
```

**关键 props（双模式共享）**：
- `useMetaList: Boolean` (默认 false)
- `enableDetail: Boolean` (默认 true)
- `enableAutoCrud: Boolean` (默认 true)
- `rowMutability: String` (默认 null)

**风险等级**：🟠 **中**——双模式都需保证行为不变

**新发现**：ObjectChildSection **同时 import 了 DetailPage**（L167），存在**潜在三重循环**（MetaListPage → DetailPage → ObjectChildSection → MetaListPage）

#### 19.5.3 SearchHelpDialog.vue（**值选择对话框**）

```vue
<MetaListPage :object-type="entityType" :display-mode="'dialog'"
              :columns-override :options :toolbar-actions-override
              :row-actions-override :batch-actions-override />
```

**关键 props**：
- `displayMode='dialog'` (与 page / embedded 区分)
- 用于 FkLinkField / ValueHelpField 值选择

**风险等级**：🟠 **中**——FkLinkField 是核心组件，搜索 → 选择 → 回填

#### 19.5.4 AssignmentDialog.vue（**分配对话框**）

```vue
<MetaListPage :object-type="entityType" :display-mode="'dialog'"
              :options :enable-detail :enable-auto-crud />
```

**关键 props**：
- `displayMode='dialog'`
- 用于多对多关联分配（assign / unassign）

**风险等级**：🟠 **中**——核心工作流

#### 19.5.5 MultiObjectManagementPage.vue（**多对象管理**）

```vue
<MetaListPage :object-type :options ... />
```

**特殊**：
- 使用 `useMultiObjectPage` composable（**第 2 个被发现的 composable**，除 useMultiObjectList 外）
- L210 `import { setRefreshCoordinator } from '@/services/boService'` —— 接入 boService refresh 协调
- L209 `import { useRefreshCoordinator } from '@/composables/useRefreshCoordinator'` —— 刷新协调器

**风险等级**：🟡 **低-中**

### 19.6 双向刷新链（v1.3.0 新增关键发现）

#### 19.6.1 完整刷新链路

```
1. MetaListPage 列表行 → 用户点击"查看详情"按钮
   ↓
2. MetaListPage.openDetailDrawer(row) (L1241)
   ↓ showDetailDrawer=true
3. <DetailPage> 内部 <ObjectPage> 渲染
   ↓ metaLoaded 后
4. ObjectPage → ObjectPageContent → <AssociationSection> 渲染
   ↓ 关联 section 加载
5. AssociationSection → <MetaListPage embedded> 渲染
   ↓ 用户编辑内嵌列表
6. 用户保存 → boService.create/update
   ↓ 保存成功后
7. AssociationSection 调用 boService._clearCache(props.objectType) (L408/602)
   ↓
8. refresh() → metaListRef.value.refresh() (L626-630)
   ↓
9. emit('refresh') → 父 MetaListPage 收到
   ↓
10. 父 MetaListPage 重新加载列表（避免列表与详情不一致）
```

**关键同步点**：
- `boService._clearCache` 是关键——**必须在重构时保留**
- `metaListRef.refresh()` 通过 `ObjectPage` 内部的 `registerMetaListRef` 注入传递

#### 19.6.2 双向刷新链风险点

| # | 风险点 | 风险等级 | 修复建议 |
|:-:|--------|:-------:|---------|
| 1 | useMetaList 重构后 `refresh()` 函数引用变化 | 🔴 | **接口契约保护**：必须保持 `metaListRef.value.refresh()` 可用 |
| 2 | `boService._clearCache` 时机变化 | 🟠 | **接口契约保护**：调用时机/参数必须不变 |
| 3 | inject `registerMetaListRef` 链路变化 | 🟠 | **保持 inject/provide 协议** |
| 4 | fetcher 自定义函数调用顺序变化 | 🟠 | **保持 fetcher 签名一致** |
| 5 | useListActionStore 派发时机变化 | 🟡 | **保持派发协议** |

### 19.7 真实破坏面（v1.3.0 修订 17 → 25）

| 类别 | 文件 | 数量 |
|------|------|:---:|
| **核心消费** | MetaListPage.vue | 1 |
| **路由级消费** | GenericObjectList + ObjectDetailPage | 2 |
| **真定制页** | AuditLogManagement | 1 |
| **死代码 stub** | 6 个 (UserGroup/Role/User/Version/EnumValue/Product) | 6 |
| **新增发现的 consumer**（v1.3.0 补充） | ObjectPage/AssociationSection + ObjectChildSection + SearchHelpDialog + AssignmentDialog + MultiObjectManagementPage | 5 |
| **useMetaList 直接测试** | 2 spec (integration + batch) | 2 |
| **MetaListPage 子测试** | 4 spec (fk-link/AssociationNavigationMenu/NavigationSourceInfo) | 4 |
| **useDetail 平行测试** | 1 spec (useDetail.spec.js) | 1 |
| **formatDate 工具引用** | 3 文件 (InlineEditCell/AuditLogManagement/SystemAdmin) | 3 |
| **总计真实破坏面** | | **25 个文件** |

### 19.8 重构风险矩阵（v1.3.0 完整版）

| # | 风险点 | 风险等级 | 来源 |
|:-:|--------|:-------:|------|
| 1 | useMetaList 重构后 75+ API 行为变化 | 🔴 | MetaListPage.vue L649-739 |
| 2 | **displayMode='embedded' 嵌入模式下 useMetaList 行为差异** | 🔴 | ObjectPage/AssociationSection L4/L45/L71 |
| 3 | **displayMode='dialog' 弹窗模式下 useMetaList 行为差异** | 🔴 | SearchHelpDialog + AssignmentDialog |
| 4 | **useMetaList=true 双模式切换** | 🟠 | ObjectChildSection L46-62 |
| 5 | **boService 缓存清除时机**（双向刷新链） | 🟠 | AssociationSection L408/602/410/567/611 |
| 6 | fetcher 自定义函数（queryAssociations/annotations） | 🟠 | AssociationSection L195-202/288-309/311-329 |
| 7 | AssociationSection 自身 3 个 fetcher 模式 | 🟡 | manyToMany/association/annotation |
| 8 | 5+ 个 useMetaList 事件回调 | 🟡 | openDetailDrawer/refresh/data-loaded |
| 9 | **6 个死代码 stub** 误删 | 🟢 | 0 import（PR 8 清理） |
| 10 | **5 个新发现 consumer 的测试覆盖** | 🟠 | ObjectChildSection/SearchHelpDialog/AssignmentDialog/MultiObjectManagementPage/AssociationSection |
| 11 | **ObjectDetailPage 路由详情 + DetailPage 协调** | 🟠 | L271-273 handleStateTransitionSuccess |
| 12 | **三重潜在循环**（MetaListPage→DetailPage→ObjectChildSection→MetaListPage） | 🟡 | ObjectChildSection L167 import DetailPage |

### 19.9 决策点（v1.3.0 新增 TBD）

| ID | 项 | 推荐答案 | 决策点 |
|----|---|---------|--------|
| TBD-19-1 | 之前漏掉的 5 个 consumer 是否需补 useMetaList 集成测试？ | **是**（高 ROI：覆盖度从 50% → 95%） | ✅ 加 |
| TBD-19-2 | displayMode='embedded' 是否单测？ | **是**（3 个场景：manyToMany/annotation/default） | ✅ 加 |
| TBD-19-3 | displayMode='dialog' 是否单测？ | **是**（2 个场景：SearchHelp/Assignment） | ✅ 加 |
| TBD-19-4 | useMetaList=true 双模式是否单测？ | **是**（ObjectChildSection 模式切换） | ✅ 加 |
| TBD-19-5 | DetailPage ↔ MetaListPage 双向刷新链是否 E2E？ | **是**（openDetailDrawer → save → refresh） | ✅ 加 |
| TBD-19-6 | fetcher 自定义函数（queryAssociations/annotations）是否单测？ | **是**（3 个 fetcher × 参数透传 × 返回值格式） | ✅ 加 |
| TBD-19-7 | 真实破坏面 25 个是否每个都需要契约保护？ | **不是**：8 个 MetaListPage consumer + 17 个间接 = 25 个全部保护 | ✅ 全保护 |
| TBD-19-8 | ObjectChildSection 三重循环风险？ | **保持现有 import 协议**（DetailPage 备用），不增加新 import | ✅ 保持 |
| TBD-19-9 | PR 4-7 范围是否扩展到 25 个文件？ | **是**：扩展原 PR 5 范围 | ✅ 扩 |

### 19.10 PR 4-7 范围修订（v1.3.0）

| PR | v1.2.0 范围 | v1.3.0 修订 |
|:-:|------------|------------|
| **PR 4** | 6 service | ✅ 不变 |
| **PR 5** | 接口契约 + 测试（原 17 文件） | 🟠 **扩到 25 文件** |
| **PR 6** | 7 天完成 | ✅ 不变 |
| **PR 7** | 集成测试 | 🟠 **范围扩：12 consumer × 4 displayMode** |
| **PR 8** | 清理 6 死代码 stub | ✅ 不变（0.5d） |
| **PR 9 (新增)** | — | 🆕 **补 5 consumer 契约测试**（2d） |

**PR 4-7 期间**：增加约 **2d** 工作量到 PR 9

### 19.11 6 个 service 依赖关系在双向链路中的变化

#### 19.11.1 useMetaList 自身依赖（不变）

| 依赖 | 调用点 | 用途 | refactor 风险 |
|------|:----:|------|:-----------:|
| boService (L19) | L395, L450 | 数据加载 | 🔴 行为不变 |
| metaService (L20) | L325, L884 | 元数据 | 🔴 行为不变 |
| dateFormatService (L21) | L2463 | 日期 | 🟢 工具 |
| useFieldPolicy (L22) | L1800 | 字段策略 | 🟡 业务 |
| useListActionStore (L23) | L1763 | 派发 | 🟢 工具 |
| filterService (L24-35) | 多个 | 过滤转换 | 🟡 业务 |
| safeExpression.evaluateCondition (L17) | 1 处 | 表达式 | 🟢 工具 |
| ElMessage/ElMessageBox (L18) | 多个 | 错误处理 | 🟢 UI |

#### 19.11.2 双向链路中的新协同点

| 协同点 | 来源 | 风险 |
|--------|------|:----:|
| **boService.read 共享** | DetailPage L818 + MetaListPage 内嵌 | 🟠 缓存一致性 |
| **boService._clearCache 时机** | AssociationSection L408/602 | 🔴 双向刷新链 |
| **boService.queryAssociations fetcher** | AssociationSection L196/289 | 🟠 fetcher 签名 |
| **boService.unassignAssociationV2** | AssociationSection L384/594 | 🟠 关联操作 |
| **refreshCoordinator inject** | MetaListPage L647 + MultiObjectManagementPage L209/210 | 🟡 跨页协调 |
| **registerMetaListRef inject** | ObjectPage/AssociationSection L180 | 🟡 ref 传递 |

**关键**：useMetaList 重构时如果**改变了 boService 的清除时机/方式**，会破坏 detail ↔ list 的双向刷新链。

### 19.12 4 类消费场景的差异

| 场景 | displayMode | 容器 | 工具栏 | 详情抽屉 | 导入导出 | 行内编辑 | 风险 |
|------|-------------|------|:-----:|:-------:|:-------:|:-------:|:---:|
| 列表页（GenericObjectList） | page | 整页 | ✅ | ✅ | ✅ | ✅ | 🟠 |
| 详情页内嵌（AssociationSection ×3） | embedded | 内嵌 | ❌ | ❌ | ❌ | ❌ | 🔴 |
| 父子子表（ObjectChildSection） | embedded | 内嵌 | ❌ | ❌ | ❌ | ❌ | 🟠 |
| 值选择（SearchHelpDialog） | dialog | el-dialog | ✅ | ❌ | ❌ | ❌ | 🟠 |
| 关联分配（AssignmentDialog） | dialog | el-dialog | ✅ | ❌ | ❌ | ❌ | 🟠 |
| 多对象管理 | 默认 | 整页 | ✅ | ✅ | ✅ | ✅ | 🟡 |

**新发现**：useMetaList 4 种 displayMode 提供**渐进增强**——核心 API 一致，外围 UI 元素按需启用。重构必须保证**所有 displayMode 的核心 API 行为完全一致**。

### 19.13 与父 spec v2.0.1 的关系

父 spec §1.3 提到"周边模块"未消费 useMetaList —— **v1.3.0 §19 揭示这个假设是错误的**：
- ObjectPage/AssociationSection 是 useMetaList 的**核心消费者**（不是"周边"）
- ObjectChildSection / SearchHelpDialog / AssignmentDialog / MultiObjectManagementPage 都是 useMetaList 的**真实业务消费者**

**修正建议**：父 spec v2.0.1 §1.3 应更新为"**useMetaList 的真实消费方 = 12 个 .vue（25 个文件受 refactor 影响）**"。

### 19.14 总结：v1.3.0 关键发现

#### 19.14.1 真实破坏面
- **17 → 25**（+8 个文件）
- 之前 §16.1.1 漏掉 **5 个真实 consumer**（AssociationSection/ObjectChildSection/SearchHelpDialog/AssignmentDialog/MultiObjectManagementPage）
- 之前 §16.5 漏掉 **1 个测试**（useDetail.spec.js）
- 之前 §16 漏掉 **1 个路由级消费者**（ObjectDetailPage）

#### 19.14.2 关键架构特征
- **双向循环**：MetaListPage ↔ DetailPage（不是单向）
- **三重潜在循环**：MetaListPage → DetailPage → ObjectChildSection → MetaListPage
- **4 种 displayMode**：page / embedded / dialog / 默认
- **3 种 fetcher 模式**：queryAssociations / annotation / default
- **boService 共享**：双向刷新链的关键

#### 19.14.3 重构影响
- useMetaList 75+ API 必须保护（接口契约）
- 4 种 displayMode 行为必须保护（displayMode 单测）
- 双向刷新链必须 E2E 测试
- 5 个新 consumer 必须补契约测试（PR 9）
- 6 service 依赖必须保留（接口稳定）

#### 19.14.4 一句话总结
> **v1.3.0 §19 揭示：useMetaList 是 v1 frontend 的"中间层核心"——不仅是 GenericObjectList 的内部实现，更是 DetailPage 详情页体系（12 consumer / 25 文件）的隐式核心。重构必须按"中间件"标准对待，不能仅当 list composable 看待。**

---

---
