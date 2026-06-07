# Mermaid: 依赖关系图

> **类型**: A. 5 层链路 + 12 节点 + 4 service + self-loop 标记
> **创建日期**: 2026-06-06
> **替代**: spec v1.5.0 §15-20 中的 ASCII 图
> **优势**: IDE 原生渲染 + 可点击 + 可搜索 + 跨平台一致

---

```mermaid
graph TD
    subgraph "前端 5 层链路"
        DetailPage["DetailPage<br/>(el-drawer)"]
        ObjectPage["ObjectPage<br/>(壳)"]
        ObjectPageContent["ObjectPageContent"]
        ObjectChildSection["ObjectChildSection<br/>(useMetaList prop)"]
        MetaListPage["MetaListPage<br/>(核心容器)"]
        useMetaList["useMetaList<br/>(composable)"]
    end

    subgraph "ValueHelp 弹窗"
        ObjectPageField["ObjectPageField"]
        MetaForm["MetaForm"]
        InlineEditCell["InlineEditCell"]
        ValueHelpField["ValueHelpField<br/>(3 resultType)"]
        SearchHelpDialog["SearchHelpDialog<br/>(3 displayMode)"]
    end

    subgraph "Service 依赖"
        boService["boService"]
        metaService["metaService"]
        filterService["filterService"]
        useListActionStore["useListActionStore"]
    end

    DetailPage --> ObjectPage
    ObjectPage --> ObjectPageContent
    ObjectPage --> ObjectChildSection
    ObjectPageContent --> MetaListPage
    ObjectChildSection --> MetaListPage
    MetaListPage --> useMetaList
    useMetaList --> boService
    useMetaList --> metaService
    useMetaList --> filterService
    useMetaList --> useListActionStore

    ObjectPageField --> ValueHelpField
    MetaForm --> ValueHelpField
    InlineEditCell --> ValueHelpField
    ValueHelpField --> SearchHelpDialog
    SearchHelpDialog --> MetaListPage

    useMetaList -. "self-loop:<br/>getFieldEditConfig<br/>→ value_help" .-> InlineEditCell
    useMetaList -. "self-loop" .-> ValueHelpField

    classDef critical fill:#ff6b6b,color:#fff
    classDef core fill:#4ecdc4,color:#fff
    classDef support fill:#95a5a6,color:#fff

    class DetailPage,MetaListPage,useMetaList critical
    class ObjectPage,ObjectChildSection,ValueHelpField,SearchHelpDialog core
    class boService,metaService,filterService,useListActionStore support
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
