# 枚举依赖关系通用化 — 实现方案

> Edition: v4 — 新增 UI 适配细节、ValueHelp 影响分析、上层应用适配方案
>
> 完整 Spec 见 [spec.md](file:///d:/filework/excel-to-diagram/.trae/specs/relation-type-enum-refactor/spec.md)

---

## 行业参考对比

| 产品 | 方案 | 与我们的关系 |
|------|------|------------|
| **Salesforce** | Dependent Picklist（字段级依赖矩阵） | 我们是枚举类型级，比字段级更通用 |
| **ServiceNow** | Dependent Choice（内嵌依赖） | 我们独立关联表，多层级联更自然 |
| **Google Dataplex** | Taxonomy 层级树 | 纯树形，我们是图结构，可跨类型 |
| 我们的方案 | `enum_dependency_links` 关联表 | ✅ 维度/级联/分类三种模式，可复用，可多级 |

---

## 通用化设计：一张表承载三种模式

```
维度展开（本期）          级联联动（未来）          简单分类（未来）

relation_type            country                  product_category
├─ GENERATES             ├─ CN → province          ├─ 电子产品 → product_type
│   └─ direction         │   └─ Guangdong → city   ├─ 服装 → product_type
├─ UPDATES               │       └─...              ...
│   └─ direction         └─ US → province  
├─ TRIGGERS                  └─ California → city
│   └─ direction
└─ REFERENCES → 无
```

---

## 数据流

```
┌─────────────────────────┐
│   enum_types            │
│  ────────────────       │
│  id: relation_type      │
│  id: direction      ◄── 新枚举（3个值: PUSH/PULL/BIDIRECTIONAL）
└───────┬─────────────────┘
        │
┌───────▼─────────────────────────┐      ┌──────────────────────────────┐
│   enum_values                   │      │  enum_dependency_links       │
│  ───────────────────────        │◄─────│  ─────────────────────────── │
│  GENERATES   (type=rel_type)    │      │  parent: relation_type       │
│  UPDATES     (type=rel_type)    │      │  parent_value: GENERATES     │
│  TRIGGERS    (type=rel_type)    │      │  child_type: direction       │
│  REFERENCES  (type=rel_type)    │      │  child_value: NULL (全可用)   │
│  PUSH        (type=direction)   │      ├──────────────────────────────┤
│  PULL        (type=direction)   │      │  parent_value: UPDATES       │
│  BIDIREC..   (type=direction)   │      │  child_type: direction       │
└─────────────────────────────────┘      ├──────────────────────────────┤
                                         │  parent_value: TRIGGERS      │
                                         │  child_type: direction       │
                                         └──────────────────────────────┘
                                              恰 3 行 ✔
```

---

## UI 适配架构

```
┌────────────────────────────────────────────────────────────┐
│ 管理端 UI（Phase 3-4a）                                     │
│                                                             │
│ enum_type 详情页                                             │
│   ├─ 基本信息 (不变)                                         │
│   ├─ 维度配置 (dimension_schema → 标记只读)                  │
│   ├─ 枚举依赖 ✨新增 (enum_dependency_link.yaml → MetaListPage)│
│   │   └─ 可增删: 父值 / 子类型 / 子值                       │
│   └─ 枚举值 (不变)                                          │
│                                                             │
│ direction 枚举类型                                            │
│   └─ 普通枚举管理页面 (list + detail + values)               │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│ 业务端 UI（Phase 4b）                                        │
│                                                             │
│ 关系创建/编辑表单 (DetailPage)                                │
│   ├─ relation_type 下拉 (widget:select/enum_type:rel_type)   │
│   └─ EnumDependencySelector ✨新增                           │
│       └─ 选GENERATES → direction下拉；选REFERENCES → 空     │
│                                                             │
│ ObjectPage 业务对象详情                                      │
│   └─ 合并关系表                                             │
│       └─ relation_code → relation_type + EnumFieldDisplay ✓ │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│ ValueHelp 系统（不变，未来适配）                                │
│                                                             │
│ EnumValueHelpProvider.filter_by_dimension                   │
│   ├─ 现有: dimensions JSON 过滤 → 保留                      │
│   └─ 未来: enum_dependency_links JOIN → Phase 5            │
└────────────────────────────────────────────────────────────┘
```

---

## ValueHelp 影响分析

| ValueHelp 能力 | 当前基于 | 本次需改 | Phase |
|---------------|---------|:---:|:---:|
| 枚举选项加载 (select 下拉) | `enum_values` 表 | ❌ 不变 | — |
| 维度过滤 (filter_by_dimension) | `dimensions__` JSON | ❌ 保留兼容 | 5 (future) |
| 绑定强度校验 | behavior.binding_strength | ❌ 不变 | — |
| 依赖查询（新增） | **新** `/api/v1/enum-dependencies/` | ✅ 新增 | 3 |

**结论**：ValueHelp 系统本期零改动。`EnumDependencySelector` 独立于 ValueHelp，走自己的 API。

---

## 迁移脚本核心逻辑

```python
def migrate_dimension_json_to_dependency_links(ds):
    """将 enum_values.dimensions JSON → enum_dependency_links"""
    create_enum_dependency_links_table(ds)
    migrate_enum_class(ds, Direction)

    now = datetime.now().isoformat()
    rows = ds.query(
        "SELECT code, dimensions FROM enum_values WHERE enum_type_id = 'relation_type'"
    )
    for code, dims_json in rows:
        if not dims_json:
            continue  # REFERENCES → 跳过
        dims = json.loads(dims_json)
        for child_type_id in dims:
            ds.execute("""
                INSERT OR IGNORE INTO enum_dependency_links
                (parent_enum_type_id, parent_enum_value,
                 child_enum_type_id, child_enum_value,
                 created_at, updated_at)
                VALUES (?, ?, ?, NULL, ?, ?)
            """, ['relation_type', code, child_type_id, now, now])
    ds.commit()
```

## API

```
GET /api/v1/enum-dependencies/parent/relation_type/GENERATES
→ { dependencies: [{
      enum_type_id: "direction",
      enum_type_name: "操作方式",
      values: [
        {code: "PUSH", name: "推", name_en: "Push", sort_order: 1},
        {code: "PULL", name: "拉", name_en: "Pull", sort_order: 2},
        {code: "BIDIRECTIONAL", name: "双向", name_en: "Bidirectional", sort_order: 3}
      ]
    }]
  }

GET /api/v1/enum-dependencies/parent/relation_type/REFERENCES
→ { dependencies: [] }
```

## 文件变更总览

| 文件 | 类型 | Phase | 说明 |
|------|------|:---:|------|
| `meta/core/models.py` | 新增 | 1 | `Direction` 枚举类 |
| `meta/scripts/migrate_enums.py` | 修改 | 1-2 | 注册 Direction + 迁移脚本 |
| `meta/scripts/init_database.py` | 新增 | 1 | `create_enum_dependency_links_table()` |
| `meta/api/enum_api.py` | 新增 | 3 | 依赖查询 API endpoint |
| `meta/schemas/enum_dependency_link.yaml` | **新增** | 3 | 元模型定义 |
| `meta/schemas/enum_type.yaml` | 修改 | 3 | 新增 child_section |
| `meta/schemas/business_object.yaml` | 修改 | 4 | associations.columns 更新 |
| `src/services/enumService.js` | 新增 | 4 | `loadDependencyOptions()` |
| `src/components/common/EnumDependencySelector.vue` | **新增** | 4 | 依赖选择器组件 |
| `src/components/common/ObjectPage/ObjectPage.vue` | 修改 | 4 | relation_code → EnumFieldDisplay |
| `src/services/archDataConverter.js` | 修改 | 4 | 透传 relation_type |

## 预计工时

| Phase | 内容 | 预估 |
|-------|------|------|
| Phase 1 | Direction 枚举 + 建表 + 注册 | 1.5h |
| Phase 2 | 迁移脚本 | 1h |
| Phase 3 | API + YAML (enum_dependency_link + enum_type) | 2h |
| Phase 4a | 管理端 UI (子区域 + 只读标记) | 1h |
| Phase 4b | 业务端 UI (Selector + ObjectPage + archDataConverter) | 2h |
| Phase 5 | 验证 | 0.5h |
| **总计** | | **~8h** |
