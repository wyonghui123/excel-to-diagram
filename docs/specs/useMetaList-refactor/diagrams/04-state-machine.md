# Mermaid: 状态机图

> **类型**: D. useMetaList 8 个核心状态 + 12 个转移
> **创建日期**: 2026-06-06
> **替代**: spec v1.5.0 §15-20 中的 ASCII 图
> **优势**: IDE 原生渲染 + 可点击 + 可搜索 + 跨平台一致

---

```mermaid
stateDiagram-v2
    [*] --> Idle: useMetaList init

    Idle --> Loading: loadList()
    Loading --> Loaded: 数据返回
    Loading --> Error: fetch 失败

    Loaded --> Filtering: handleFilter()
    Loaded --> Searching: handleSearch()
    Loaded --> Sorting: handleSortChange()
    Loaded --> Paging: handlePageChange()
    Loaded --> Selecting: handleSelectionChange()
    Loaded --> Editing: startEditCell()

    Filtering --> Loaded
    Searching --> Loaded
    Sorting --> Loaded
    Paging --> Loaded
    Selecting --> Loaded

    Editing --> Editing: updateDraftValue()
    Editing --> Editing: addNewRow()
    Editing --> Drafted: finishEditCell()
    Drafted --> Editing: cancelInlineEdit()
    Drafted --> Saving: saveDraftValues()
    Saving --> Loaded: 成功
    Saving --> Drafted: 部分失败
    Drafted --> Editing: 重新编辑

    Loaded --> DetailOpen: openDetailDrawer()
    DetailOpen --> Loaded: closeDetailDrawer()

    Error --> Loading: retry (refresh)
    Loaded --> [*]: destroy
    DetailOpen --> [*]: destroy
    Drafted --> [*]: destroy

    note right of Loaded: 列表渲染 + 分页/排序
    note right of Editing: Inline Edit 模式
    note right of Drafted: 有未保存的草稿
    note right of DetailOpen: 侧边抽屉打开
    note right of Error: 错误恢复

    classDef critical fill:#ff6b6b,color:#fff
    classDef transient fill:#ffd93d,color:#333
    class Loaded critical
    class Loading,Filtering,Searching,Sorting,Paging,Selecting transient
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
