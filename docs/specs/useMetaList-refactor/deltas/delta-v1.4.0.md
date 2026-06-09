## 目录

1. [1. 章节变更清单](#1-章节变更清单)
2. [2. 详细变更（增量内容）](#2-详细变更（增量内容）)
3. [20. ValueHelp 弹窗组件深度分析（v1.4.0 补充）](#20-valuehelp-弹窗组件深度分析（v140-补充）)
4. [变更记录](#变更记录)

---
# Delta v1.4.0: §20 ValueHelp 5 层链路 + self-loop

> **基线版本**: v4.0.0
> **目标版本**: v1.4.0
> **变更日期**: 2026-06-06
> **变更类型**: 增量
> **源 spec**: [spec-fr-ui-003-004-005-useMetaList-refactor.md v1.5.0](file:///d:/filework/excel-to-diagram/docs/specs/spec-fr-ui-003-004-005-useMetaList-refactor.md) L2791-L3082
> **章节数**: § 增量 §20 ValueHelp 5 层链路 + self-loop

## 1. 章节变更清单

| # | 章节 | 类型 | 摘要 |
|:-:|------|:---:|------|
| §X | §20 ValueHelp 5 层链路 + self-loop | 增量 | 详见 §2 详细变更 |

## 2. 详细变更（增量内容）

## 20. ValueHelp 弹窗组件深度分析（v1.4.0 补充）

> **目标**：深入审计 ValueHelp 弹窗组件（ValueHelpField / SearchHelpDialog / FkLinkField）对 MetaList 的依赖，揭示 5 层嵌套链路 + 6 种 fetcher 模式 + useMetaList ↔ MetaListPage self-loop
> **数据来源**：10 个核心文件 107KB / 32 个相关文件 / 4 层 displayMode 完整代码审计
> **结论先行**：**真实破坏面 25 → 28**；**5 层链路**（DetailPage → ObjectPage → ObjectPageField → ValueHelpField → SearchHelpDialog → MetaListPage）；**6 种 fetcher 自定义模式**（v1.3.0 是 3 种）；**useMetaList ↔ MetaListPage 存在 self-loop**（getFieldEditConfig → InlineEditCell → ValueHelpField → SearchHelpDialog → MetaListPage）

### 20.1 ValueHelp 弹窗生态全景

#### 20.1.1 10 个核心组件规模

```
ValueHelp 弹窗组件家族（107KB / 3,883 行）:
├── ValueHelpField.vue                    10.1KB /  338 行  (3 resultType: dropdown/dialog/inline)
├── FkLinkField/FkLinkField.vue            2.8KB /  123 行  (router-link 跳详情)
├── FkLinkField/index.js                   0.1KB /    1 行
├── SearchHelpDialog.vue                  22.3KB /  769 行  (3 displayMode: flat/tree_flat/tree)
├── useValueHelp.js                        9.3KB /  283 行  (composable)
├── ConditionRuleEditor/ValueHelpSelector  9.1KB /  378 行  (自实现 dropdown)
├── TableHeaderFilter/TableHeaderFilter   26.0KB /  887 行  (filterType='value_help')
├── FilterBar/FilterBar                   18.7KB /  685 行  (filterType='value_help')
├── bo/boSearchHelpService.js              2.2KB /   50 行  (v2 backend API)
└── bo/AssociationSelector                 6.6KB /  271 行  (SearchHelpDialog consumer)
```

#### 20.1.2 32 个 ValueHelp 相关文件全景（v1.4.0 实际数据）

| 类别 | 数量 | 文件 |
|------|:---:|------|
| **核心组件** | 4 | ValueHelpField / SearchHelpDialog / FkLinkField / useValueHelp |
| **业务组件** | 4 | ValueHelpSelector / AssociationSelector / TableHeaderFilter / FilterBar |
| **服务/数据** | 2 | boSearchHelpService / boService.searchValueHelp |
| **使用方（v1.4.0 新增 3）** | 9 | DimensionScopePanel / **ObjectPageField** / TableHeaderFilter / FilterBar / **MetaForm** / **InlineEditCell** / MetaListPage (L2183) / AssociationSelector / index.js |
| **详情页/表单** | 4 | MetaListPage / DetailPage / ObjectPage* (4 个) / MetaForm |
| **测试** | 4 | FkLinkField.spec / useValueHelp.spec / ObjectPage.fk-link.spec / FilterBar.spec |
| **文档/其他** | 5 | ComponentComparison / COMPONENT_LAYER_GUIDE / filterService / boService / service files |

### 20.2 ValueHelp 3 层架构 + 3 resultType + 3 displayMode

#### 20.2.1 ValueHelpField 3 大 resultType（v1.4.0 关键发现）

| resultType | UI 组件 | 是否用 MetaListPage | 用途 | 风险 |
|-----------|---------|:-----------------:|------|:----:|
| `'dropdown'` | el-select | ❌ | 单选/多选下拉 | 🟢 |
| `'dialog'` | el-input + SearchHelpDialog | ✅ **是** | 点击弹窗搜索 | 🔴 |
| `'inline'` | el-autocomplete | ❌ | 实时搜索补全 | 🟢 |

**关键**：只有 `dialog` 模式触发 **`SearchHelpDialog` → `MetaListPage`** 链路！

#### 20.2.2 SearchHelpDialog 3 大 displayMode

| displayMode | UI 组件 | 关键 props | fetcher 来源 |
|-------------|---------|-----------|-------------|
| `'flat'` | `<MetaListPage>` flat 列表 | `:object-type` `:columns-override` `:options.fetcher` | boService.searchValueHelp (L218-246) |
| `'tree_flat'` | `<MetaListPage>` + tree 混合 | 同上 | 同上 |
| `'tree'` | `<el-tree>` 树形 | 完全自实现 | 树形 fetcher |

**关键**：`'flat'` + `'tree_flat'` 用 **`MetaListPage`**，`'tree'` 不用。

#### 20.2.3 useValueHelp 3 大 sourceType

| sourceType | 数据来源 | sourceId 来源 |
|-----------|---------|--------------|
| `'enum'` | enum_value 表 | `source.enum_type_id` |
| `'bo'` | bo query | `source.target_bo` |
| `'custom'` | 自定义 endpoint | `source.endpoint` |

### 20.3 完整依赖链路图（v1.4.0 关键架构图）

```
┌─────────────────────────────────────────────────────────────┐
│                      业务场景                                │
│  详情页字段  │  表单字段  │  Inline Edit  │  过滤  │  关联  │
└──────────────────────┬──────────────────────────────────────┘
                       │
       ┌───────────────┼────────────────┐
       │               │                │
       ▼               ▼                ▼
┌──────────────┐ ┌─────────────┐ ┌────────────────┐
│ ObjectPage-  │ │  MetaForm   │ │ InlineEditCell │  ← 详情页/表单
│   Field.vue  │ │   .vue      │ │  .vue (L32/L82)│
└──────┬───────┘ └──────┬──────┘ └────────┬───────┘
       │                │                  │
       └────────────────┼──────────────────┘
                        ▼
              ┌──────────────────┐
              │  ValueHelpField  │  ← 字段渲染核心
              │  (3 resultType)  │  + useValueHelp (composable)
              └────────┬─────────┘
                       │
            ┌──────────┼──────────┐
            │          │          │
            ▼          ▼          ▼
       dropdown    dialog      inline
        (el-       (Search-     (el-auto-
         select)    HelpDialog)  complete)
                       │
                       ▼
              ┌──────────────────┐
              │ SearchHelpDialog │  ← 弹窗核心
              │ (3 displayMode)  │
              └────────┬─────────┘
                       │
                  flat/tree_flat
                       │
                       ▼
              ┌──────────────────┐
              │   MetaListPage    │  ← 列表渲染
              │ displayMode=dialog│
              └──────────────────┘


其他 SearchHelpDialog 直接消费者:
  - AssociationSelector.vue (bo/ 下) — customFetcher 注入
  - DimensionScopePanel.vue (SystemManagement/components/) — 维度选择
  - components/common/index.js — 组件注册


FkLinkField (router-link) ──→ 跳详情页
                                  ↓
                  /detail/:objectType/:id (route)
                                  ↓
              ┌──────────────────────────────┐
              │  ObjectDetailPage.vue (路由) │
              │  ↓                            │
              │  DetailPage (el-drawer)       │
              │  ↓                            │
              │  ObjectPage → 字段 →         │
              │  ValueHelpField →           │
              │  SearchHelpDialog →         │
              │  MetaListPage (再循环!)     │
              └──────────────────────────────┘
```

### 20.4 useMetaList 内部消费 ValueHelp 的 4 个点（v1.4.0 关键发现）

**重大发现**：useMetaList **不只被 ValueHelp 消费，自身也消费 ValueHelp 元数据**：

| 行号 | 用途 | 影响 |
|:---:|------|------|
| L1144 | 列元数据赋值 `valueHelpConfig: col.value_help_config` | 元数据解析 |
| L1357-1369 | filter_type 推断 `'value_help'` | 列表过滤 |
| L1360-1365 | FK 链接识别 | 链接渲染 |
| **L2183-2190** | **getFieldEditConfig 返回 `value_help` 类型** | **Inline Edit 触发 ValueHelpField** |

**关键链路**：`useMetaList.getFieldEditConfig` → 返回 `type: 'value_help'` → InlineEditCell L32/L82 渲染 `<ValueHelpField>` → 触发 `SearchHelpDialog` → 内嵌 **`MetaListPage`**

**这是** `useMetaList ↔ MetaListPage` **的内部循环**（self-loop）！

### 20.5 7 类 ValueHelp 消费场景

| 场景 | 触发位置 | 链路深度 | useMetaList 依赖 | 风险 |
|------|---------|:-------:|:---------------:|:----:|
| **A. 详情页字段** | ObjectPageField | 5 层 | 🟠 中（不直接调用，通过 valueHelpConfig 元数据） | 🔴 |
| **B. 表单字段** | MetaForm | 4 层 | 🟢 低（不直接） | 🟠 |
| **C. Inline Edit** | InlineEditCell | 3 层 | 🔴 **高**（useMetaList.getFieldEditConfig 直接触发） | 🔴 |
| **D. 列表过滤** | TableHeaderFilter / FilterBar | 3 层 | 🟢 低（不直接） | 🟠 |
| **E. 关联选择** | AssociationSelector | 2 层 | 🟢 低（直接用 SearchHelpDialog） | 🟠 |
| **F. 维度选择** | DimensionScopePanel | 2 层 | 🟢 低（直接用 SearchHelpDialog） | 🟡 |
| **G. 规则编辑** | ValueHelpSelector | 1 层 | 🟢 低（自实现） | 🟢 |

### 20.6 6 种 fetcher 自定义模式（v1.4.0 重大发现）

之前 v1.3.0 §19 提到 3 种 fetcher 模式，v1.4.0 §20 扩展到 **6 种**：

| # | 消费方 | fetcher 来源 | 用途 | 风险 |
|:-:|--------|-------------|------|:----:|
| 1 | [ObjectPage/AssociationSection.vue L195-202](file:///d:/filework/excel-to-diagram/src/components/common/ObjectPage/AssociationSection.vue) | `boService.queryAssociations` | m2m 关联 | 🟠 |
| 2 | [ObjectPage/AssociationSection.vue L311-329](file:///d:/filework/excel-to-diagram/src/components/common/ObjectPage/AssociationSection.vue) | 自定义 `annotationFetcher` | annotation 备注 | 🟠 |
| 3 | [ObjectPage/AssociationSection.vue L288-309](file:///d:/filework/excel-to-diagram/src/components/common/ObjectPage/AssociationSection.vue) | `boService.queryAssociations` | 普通关联 | 🟠 |
| **4** | **[SearchHelpDialog.vue L218-246](file:///d:/filework/excel-to-diagram/src/components/common/SearchHelpDialog.vue)** | `boService.searchValueHelp` | **ValueHelp 值搜索** | 🔴 |
| **5** | **[AssociationSelector.vue L107+](file:///d:/filework/excel-to-diagram/src/components/bo/AssociationSelector.vue)** | 自定义 `associationFetcher` | **关联选择** | 🔴 |
| 6 | ObjectChildSection | useParentChild 自实现 | 父子子表 | 🟠 |

**新发现**：refactor useMetaList 时**必须保证 6 种 fetcher 模式契约不变**！

### 20.7 真实破坏面（v1.4.0 修订 25 → 28）

| 类别 | 文件 | 数量 |
|------|------|:---:|
| **v1.3.0 已有**（25 个） | — | 25 |
| **新发现 ValueHelpField 直接消费方** | ObjectPageField + MetaForm + InlineEditCell | 3 |
| **总计真实破坏面** | | **28 个文件** |

### 20.8 重构风险矩阵（v1.4.0 完整版 21 项）

| # | 风险点 | 风险等级 | 来源 |
|:-:|--------|:-------:|------|
| 1-12 | v1.3.0 §19 风险（前 12 项） | - | - |
| 13 | **SearchHelpDialog 的 3 displayMode 中 flat/tree_flat 用 MetaListPage** | 🔴 | SearchHelpDialog.vue L55-70 |
| 14 | **ValueHelpField 的 dialog 模式触发 SearchHelpDialog** | 🔴 | ValueHelpField.vue L65-71 |
| 15 | **useMetaList.getFieldEditConfig 返回 value_help 类型** | 🔴 | useMetaList.js L2183-2190 |
| 16 | **InlineEditCell 双 ValueHelp 入口**（L32 + L82） | 🟠 | InlineEditCell.vue L32-85 |
| 17 | **useValueHelp composable 状态共享** | 🟠 | useValueHelp.js |
| 18 | **boSearchHelpService v2 API 协议** | 🟠 | boSearchHelpService.js |
| 19 | **FkLinkField 跳详情触发完整链路** | 🟠 | FkLinkField.vue L60 |
| 20 | **4 种 fetcher 自定义模式** | 🔴 | SearchHelpDialog + AssociationSection + AssociationSelector |
| 21 | **6 个 ValueHelp 测试** | 🟡 | FkLinkField.spec / useValueHelp.spec / ObjectPage.fk-link.spec / FilterBar.spec / MetaListPage.fk-link.spec / ObjectPage.association.spec |

### 20.9 决策点（v1.4.0 新增 TBD）

| ID | 项 | 推荐答案 | 决策点 |
|----|---|---------|--------|
| TBD-20-1 | SearchHelpDialog 的 MetaListPage 嵌入（displayMode flat/tree_flat）是否单测？ | **是** | ✅ 加 |
| TBD-20-2 | ValueHelpField 的 dialog 模式触发链路是否 E2E？ | **是** | ✅ 加 |
| TBD-20-3 | useMetaList.getFieldEditConfig 的 value_help 返回是否单测？ | **是** | ✅ 加 |
| TBD-20-4 | 6 种 fetcher 自定义模式是否单测？ | **是** | ✅ 加 |
| TBD-20-5 | 6 个 ValueHelp 测试是否需补 useMetaList 集成测试？ | **是** | ✅ 加 |
| TBD-20-6 | FkLinkField → /detail/:objectType/:id 跳转是否 E2E？ | **是** | ✅ 加 |
| TBD-20-7 | ValueHelp 弹窗 5 层链路性能是否需要基准？ | **是** | ✅ 加 |

### 20.10 PR 4-7 范围修订（v1.4.0）

| PR | v1.3.0 范围 | v1.4.0 修订 |
|:-:|------------|------------|
| **PR 4** | 6 service | ✅ 不变 |
| **PR 5** | 接口契约（25 文件） | 🟠 **扩到 28 文件**（+3 ValueHelpField consumer） |
| **PR 6** | 7 天完成 | ✅ 不变 |
| **PR 7** | 集成测试 | 🟠 **范围扩：6 种 fetcher 模式 × 4 种 displayMode** |
| **PR 8** | 清理 6 死代码 stub | ✅ 不变 |
| **PR 9 (v1.3.0 新增)** | 5 consumer 契约测试（2d） | 🟠 **扩：+3 ValueHelpField consumer（1d）** |
| **PR 10 (v1.4.0 新增)** | — | 🆕 **ValueHelp 弹窗 5 层链路 E2E（1d）** |

**PR 4-7 期间**：增加约 **2d**（PR 9 + 1d PR 10）

### 20.11 累计 ValueHelp 弹窗组件消费方

| 组件 | 真实消费方 | 数量 |
|------|-----------|:---:|
| **MetaListPage** | 12 + 1 (SearchHelpDialog) | **13** |
| **SearchHelpDialog** | 4 (ValueHelpField/AssociationSelector/DimensionScopePanel/index.js) | 4 |
| **ValueHelpField** | 6 (ObjectPageField/MetaForm/InlineEditCell/TableHeaderFilter/FilterBar/Index) | 6 |
| **useValueHelp** | 1 (ValueHelpField) | 1 |
| **FkLinkField** | 跳详情（间接） | 1 |

### 20.12 关键架构洞察

> **v1.4.0 §20 揭示**：
> 1. **ValueHelp 弹窗有 5 层嵌套链路**（DetailPage → ObjectPage → ObjectPageField → ValueHelpField → SearchHelpDialog → MetaListPage）
> 2. **useMetaList ↔ MetaListPage 存在 self-loop**（getFieldEditConfig → InlineEditCell → ValueHelpField → SearchHelpDialog → MetaListPage）
> 3. **6 种 fetcher 模式**（v1.3.0 是 3 种，v1.4.0 新增 searchValueHelp / associationFetcher / useParentChild）
> 4. **FkLinkField 跳详情**触发 5 层链路再次循环
> 5. **4 种 displayMode × 3 种 resultType × 5 种 fetcher = 60 种行为组合**——refactor 必须保证 100% 不变
> 6. **useMetaList 是"双向 + 自循环"中间件**（v1.3.0 §19 双向 + v1.4.0 §20 self-loop）

### 20.13 总结：v1.4.0 关键发现

#### 20.13.1 关键纠正
| 维度 | v1.3.0 假设 | v1.4.0 实际 |
|------|------------|------------|
| 真实破坏面 | 25 | **28**（+3） |
| fetcher 模式 | 3 | **6**（+3） |
| 弹窗链路深度 | 4 层 | **5 层**（多 1 层 ObjectPageField） |
| self-loop 风险 | 未识别 | **已识别**（useMetaList → ValueHelp → MetaListPage） |
| ValueHelpField 真实消费方 | 3 | **6**（+3：ObjectPageField/MetaForm/InlineEditCell） |

#### 20.13.2 重构影响
- 28 个文件需要保护
- 6 种 fetcher 模式必须契约保护
- 5 层弹窗链路必须 E2E 测试
- useMetaList ↔ MetaListPage self-loop 必须测试
- 60 种行为组合（4 displayMode × 3 resultType × 5 fetcher）必须保证不变

#### 20.13.3 一句话总结
> **v1.4.0 §20 揭示：ValueHelp 弹窗组件是 v1 frontend 的"5 层嵌套隐式核心"——不仅涉及 MetaListPage 嵌入，还存在 useMetaList ↔ MetaListPage self-loop。重构必须按"中间件 + self-loop"双重标准对待，不能仅当 list composable 或简单组件看待。**

#### 20.13.4 spec 演进全景
| 版本 | 字节 | 章节 | 主题 |
|:---:|:---:|:---:|------|
| v1.0.0 | ~50K | 18 | FR-UI-003/004/005 重构（PR 4-7） |
| v1.1.0 | ~72K | 21 | §15 头部产品对标 + 8 类 P0-P2 backlog |
| v1.2.0 | ~100K | 21 | §16-18 真实消费侧 + 组件依赖图 + v3 衔接 |
| v1.3.0 | ~125K | 22 | §19 DetailPage 双向链路 + 25 文件 |
| **v1.4.0** | **~150K** | **23** | **§20 ValueHelp 弹窗 5 层链路 + 28 文件 + self-loop** |
| **v1.5.0** | **~180K** | **28** | **§21-28 8 大遗漏审计 + 整体架构重构 + 35 文件** |

---

## 变更记录

| 版本 | 日期 | 变更内容 | 作者 |
|:---:|------|---------|------|
| 1.0.0 | 2026-06-06 | 初稿；从父 spec 拆出 PR 4-7 FR-UI-003/004/005 独立子 spec | AI Agent (Trae) |
| 1.1.0 | 2026-06-06 | **§15 补充：table/list UI 核心能力 backlog**（与头部产品对标 12 维分析 + 8 类 P0-P2 战略补充） | AI Agent (Trae) |
| 1.2.0 | 2026-06-06 | **§16-18 真实消费侧深度审计**（8 业务页 → 1 统一入口 + 6 死代码 + 4 子组件 + 6 service 依赖 + v3 引擎衔接） | AI Agent (Trae) |
| 1.3.0 | 2026-06-06 | **§19 DetailPage ↔ MetaListPage 双向链路分析**（修正 17 → 25 真实破坏面；新发现 5 consumer；4 种 displayMode；双向刷新链 E2E） | AI Agent (Trae) |
| 1.4.0 | 2026-06-06 | **§20 ValueHelp 弹窗组件深度分析**（修正 25 → 28 真实破坏面；6 种 fetcher 模式；5 层链路 E2E；useMetaList ↔ MetaListPage self-loop） | AI Agent (Trae) |
---


---
