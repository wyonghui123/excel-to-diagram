# Mermaid: 类图

> **类型**: C. useMetaList 75+ API + 6 核心类关系
> **创建日期**: 2026-06-06
> **替代**: spec v1.5.0 §15-20 中的 ASCII 图
> **优势**: IDE 原生渲染 + 可点击 + 可搜索 + 跨平台一致

---

```mermaid
classDiagram
    class useMetaList {
        +metaConfig: ref
        +objectType: string
        +config: object
        +columns: ref~array~
        +visibleColumns: computed
        +data: ref~array~
        +loading: ref~bool~
        +selectedRows: ref~array~
        +selectedIds: ref~Set~
        +filterValues: ref~object~
        +searchFields: computed
        +keyword: ref
        +toolbarActions: computed
        +rowActions: computed
        +batchActions: computed
        +pagination: object
        +sortInfo: ref
        +draftValues: ref~Map~
        +editingCell: ref
        +hasUnsavedChanges: computed
        +navigableAssociations: computed
        +init() void
        +loadList() Promise
        +refresh() Promise
        +handleAction(action) void
        +handleFilter(filters) void
        +handleSearch(keyword) void
        +handleSortChange(prop, order) void
        +handlePageChange(page) void
        +handleSelectionChange(rows) void
        +saveDraftValues() Promise
        +getDraftCreates() array
        +isCellEditable(row, field) bool
        +getFieldEditConfig(field) object
        +getNavigableAssociations() array
    }

    class MetaListPage {
        +objectType: String (prop)
        +displayMode: String (prop, default 'page')
        +columnsOverride: Array (prop)
        +options: Object (prop)
        +useMetaListMode: Boolean (computed)
        +metaListRef: ref
        +openDetailDrawer(row) void
        +closeDetailDrawer() void
        +registerMetaListRef(ref) void
    }

    class DetailPage {
        +visible: Boolean (prop)
        +standalone: Boolean (prop, default false)
        +sections: Array (prop)
        +useMetaList: Boolean (passthrough)
        +loadObjectMeta() Promise
    }

    class ObjectChildSection {
        +useMetaList: Boolean (prop, default false)
        +objectType: String
        +childObjectType: String
        +useMetaListMode: computed
    }

    class ObjectPageField {
        +field: Object
        +editConfig: Object
    }

    class ValueHelpField {
        +resultType: String (prop, 'dropdown'|'dialog'|'inline')
        +valueHelpConfig: Object
    }

    class SearchHelpDialog {
        +displayMode: String (prop, 'flat'|'tree_flat'|'tree')
        +entityType: String
        +columnsOverride: Array
    }

    useMetaList <.. MetaListPage : 内部使用
    MetaListPage <.. DetailPage : openDetailDrawer
    DetailPage ..> ObjectPageField : 字段渲染
    ObjectPageField ..> ValueHelpField : 触发
    ValueHelpField ..> SearchHelpDialog : dialog 模式
    SearchHelpDialog ..> MetaListPage : flat/tree_flat 模式
    DetailPage ..> ObjectChildSection : 父子子表
    ObjectChildSection ..> MetaListPage : useMetaList=true
    MetaListPage ..> useMetaList : self-loop (getFieldEditConfig)

    classDef critical fill:#ff6b6b,color:#fff
    classDef core fill:#4ecdc4,color:#fff
    class useMetaList critical
    class MetaListPage,DetailPage,ObjectChildSection,ValueHelpField,SearchHelpDialog core
```

---

**使用说明**：
- 在 IDE（如 VSCode）中直接渲染
- 在 GitHub / GitLab 中自动渲染
- 在文档站点（如 MkDocs / Docusaurus）中嵌入
- 可导出为 PNG / SVG / PDF

**维护规则**：
- Mermaid 块必须正确缩进（4 空格）
- 子图（subgraph）层级不超过 3 层
- 节点数 ≤ 50（保证可读性）
- 任何修改需同步更新对应的 ASCII 图（如果保留）
