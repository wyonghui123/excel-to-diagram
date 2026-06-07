# Mermaid: 时序图

> **类型**: B. DetailPage 打开 → 内嵌编辑 → 保存 → 刷新 完整时序
> **创建日期**: 2026-06-06
> **替代**: spec v1.5.0 §15-20 中的 ASCII 图
> **优势**: IDE 原生渲染 + 可点击 + 可搜索 + 跨平台一致

---

```mermaid
sequenceDiagram
    autonumber
    participant User
    participant MetaListPage
    participant useMetaList
    participant DetailPage
    participant ObjectPage
    participant ObjectChildSection
    participant InnerMetaListPage as MetaListPage (embedded)
    participant boService
    participant metaService

    User->>MetaListPage: 点击"查看详情"按钮
    activate MetaListPage
    MetaListPage->>DetailPage: openDetailDrawer(row)
    activate DetailPage
    DetailPage->>ObjectPage: 渲染（metaLoaded）
    activate ObjectPage
    ObjectPage->>metaService: getListConfig(objectType)
    metaService-->>ObjectPage: 元数据
    ObjectPage->>ObjectChildSection: 渲染子表
    activate ObjectChildSection
    ObjectChildSection->>InnerMetaListPage: useMetaList=true 时嵌入
    activate InnerMetaListPage
    InnerMetaListPage->>useMetaList: 初始化
    useMetaList->>boService: query(objectType, params)
    boService-->>useMetaList: 列表数据
    useMetaList-->>InnerMetaListPage: columns + data
    InnerMetaListPage-->>ObjectChildSection: 渲染
    ObjectChildSection-->>ObjectPage: 渲染完成
    ObjectPage-->>DetailPage: 渲染完成
    DetailPage-->>MetaListPage: 显示 drawer
    deactivate ObjectPage
    deactivate ObjectChildSection
    deactivate InnerMetaListPage
    deactivate DetailPage

    User->>DetailPage: 在内嵌列表编辑字段
    DetailPage->>InnerMetaListPage: 触发 Inline Edit
    InnerMetaListPage->>boService: 暂存到 draftValues
    User->>DetailPage: 点击"保存"
    DetailPage->>boService: update(values)
    boService-->>DetailPage: 成功
    DetailPage->>boService: _clearCache(objectType)
    DetailPage->>MetaListPage: 关闭 drawer + refresh()
    deactivate MetaListPage
    MetaListPage->>boService: query(objectType, params)
    boService-->>MetaListPage: 新数据
    MetaListPage-->>User: 列表更新
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
