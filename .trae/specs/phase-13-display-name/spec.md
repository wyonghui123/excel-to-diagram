# Spec: Phase 13 — DisplayName 统一显示名称服务

---

## 1. 背景与目标

### 1.1 背景

当前系统中，同一字段在不同 UI 上下文中的显示名称（display name）解析逻辑分散在 10+ 个前端组件和后端处理器中，各组件使用不同的回退链：

| 组件 | 位置 | 解析逻辑 |
|------|------|---------|
| MetaListPage（列标题） | useMetaList.js L878 | `col.label \|\| col.title` |
| MetaListPage（筛选标签） | useMetaList.js L1187 | `field.label \|\| field.name \|\| field.semantics?.display_name \|\| field.id` |
| MetaListPage（删除确认） | MetaListPage.vue L730-734 | `row[displayNameField] \|\| row[businessKeyField] \|\| row.name \|\| row.code \|\| ...` |
| MetaListPage（详情标题） | MetaListPage.vue L522 | `metaConfig?.detail?.title \|\| metaConfig?.name \|\| '详情'` |
| MetaTable（列标题） | MetaTable.vue L93 | `col.label`（无回退） |
| MetaForm（字段标签） | MetaForm.vue L16 | `field.label`（无回退，validator 要求 label 存在） |
| ObjectPage（字段标签） | ObjectPage.vue L400 | `def?.label \|\| key`（无 field.name 回退） |
| DetailPage（字段标签） | DetailPage.vue L316 | `f.name \|\| f.id` |
| FilterBar（字段标签） | FilterBar.vue L11 | `field.label`（无回退，validator 要求 label 存在） |
| ExportDialog（对象名称） | ExportDialog.vue L86-92 | 硬编码 `objectTypeNameMap` |
| Excel导出（列标题） | 后端 | 使用 `field.name` |

**核心痛点是三个"不存在"**：
1. **不存在统一的面向对象实例的显示名称定义** — 删除确认对话框中靠硬编码的 heuristics 猜测
2. **不存在统一的面向关联字段的显示格式定义** — 关联选择器的组合显示格式无法声明
3. **不存在统一的字段显示名称解析服务** — 各组件独立回退，链不一致

### 1.2 业务目标

- 消除系统中字段显示名称的多源解析不一致问题
- 为关联选择器、删除确认、面包屑导航等场景提供统一的对象显示名称机制
- 坚守 YAML 单一事实原则，YAML `fields[].name` 是所有场景的默认显示名称

### 1.3 用户/涉众目标

- YAML 配置者：只需在 `fields[].name` 声明一次字段名称，无需在各个 view config 中重复
- 终端用户：在任何上下文中看到一致的字段显示名称
- 后端开发者：通过 DisplayNameService 统一获取显示名称
- 前端开发者：通过 `displayNameService` 工具函数统一获取显示名称

---

## 2. 需求类型概览

| 类型 | 是否适用 | 证据来源 |
|------|---------|---------|
| 业务需求 | 是 | Phase 13 past_chat、系统一致性要求 |
| 用户/涉众需求 | 是 | 开发者消除硬编码，终端用户看到一致名称 |
| 解决方案需求 | 是 | DisplayNameService 统一解析 |
| 功能需求 | 是 | FR-001 ~ FR-008 |
| 非功能需求 | 是 | NFR-001 ~ NFR-003（性能、兼容性、单一事实） |
| 外部接口需求 | 是 | IF-001 ~ IF-003（API 字段扩展、前端组件集成） |
| 过渡需求 | 是 | TR-001（渐进迁移，零破坏） |

---

## 3. 功能需求

### FR-001: 对象级显示名称字段声明

- **描述**: 系统必须支持在 YAML 对象定义中通过 `display_name_field` 声明该对象用于展示的主字段
- **验收标准**:
  - YAML 对象顶层支持 `display_name_field: <字段ID>` 属性
  - 未显式声明时，系统自动推断（优先 `semantics.display_name: true` → `name` → `code` → 首个 `string` 字段）
  - 推断结果在 API 响应中通过 `display_name_field` 字段返回
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: Phase 13 past_chat、MetaListPage.vue L730-734 的硬编码启发式逻辑

### FR-002: 关联显示格式声明

- **描述**: 系统必须支持在 YAML `relations[]` 中通过 `display_format` 声明关联对象的组合显示格式
- **验收标准**:
  - `relations[]` 支持 `display_format: "{field1} - {field2}"` 格式字符串
  - 未声明时，默认使用目标对象的 `display_name_field`
  - 格式字符串中的字段ID如果不存在于关联对象中，不报错，原样显示
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: Phase 12 Value Help 关联选择器的显示需求

### FR-003: 后端 DisplayNameService 字段名解析

- **描述**: 后端必须提供 `DisplayNameService.get_field_name(object_type, field_id, context)` 方法，按优先级解析字段显示名称
- **验收标准**:
  - 解析优先级: view-level override → `field.name` → `field.id`
  - 支持 context: `list`（列表列标题）/ `detail`（详情标签）/ `form`（表单标签）/ `filter`（筛选标签）/ `association`（关联显示）/ `search`（搜索占位）/ `header`（页面标题）/ `confirm`（确认对话）/ `export`（导出标题）/ `default`（默认）
  - `get_all_field_names(object_type, context)` 批量返回所有字段显示名称
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: Phase 13 past_chat、各组件分散解析

### FR-004: 后端 DisplayNameService 对象实例名解析

- **描述**: 后端必须提供 `get_object_display_name(object_type, record)` 方法
- **验收标准**:
  - 使用对象的 `display_name_field` 从 record 取值
  - 回退链: display_name_field → name → code → id
  - 在 API 响应的 `record` 对象中附加 `_display_name` 字段
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: MetaListPage.vue L730-734 删除确认逻辑

### FR-005: 后端 DisplayNameService 关联显示解析

- **描述**: 后端必须提供 `get_association_display(object_type, relation_id, record)` 方法
- **验收标准**:
  - 使用 relation 的 `display_format` 格式化（如 `"{code} - {name}"` → `"PRD001 - 产品A"`）
  - 未配 `display_format` 时回退到目标对象的 `get_object_display_name`
  - 格式化占位符缺失时不报错
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: Phase 12 Value Help 集成

### FR-006: API 响应扩展

- **描述**: `GET /api/v2/meta/{type}/ui-config` 响应必须包含 Phase 13 新增字段
- **验收标准**:
  - 新增 `display_name_field`: 对象显示名称字段ID
  - 新增 `field_display_names`: `{ field_id: display_name, ... }` 字典
  - 新增 `relation_displays`: `{ relation_id: display_format, ... }` 字典
- **优先级**: Must
- **类型映射**: 外部接口需求
- **来源**: 后端到前端的数据传递

### FR-007: 前端 DisplayNameService 工具

- **描述**: 前端必须提供 `createDisplayNameService(metaConfig)` 工具函数
- **验收标准**:
  - `getFieldName(fieldId, context)`: 返回字段在指定上下文中的显示名称
  - `getObjectDisplayName(record)`: 返回对象实例的显示名称
  - `getAssociationDisplay(relationId, record)`: 返回关联对象的格式化显示
  - 零依赖，纯函数，基于 `metaConfig` 中的 `field_display_names` / `display_name_field` / `relation_displays`
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: 前端多组件统一需求

### FR-008: YAML 单一事实原则守护

- **描述**: 新增功能必须遵守 YAML 单一事实原则
- **验收标准**:
  - `fields[].name` 是字段默认显示名称的唯一来源
  - 视图级 `title` 仅在不同于 `field.name` 时才需配置
  - 不新增 field 级的 `display_config` 属性（避免冗余）
  - 新增属性仅放在它逻辑上归属的层级（对象级 `display_name_field`、关联级 `display_format`）
- **优先级**: Must
- **类型映射**: 非功能需求（架构约束）
- **来源**: 项目规范文档 `meta-model-schema-sync.md`

---

## 4. 非功能需求

### NFR-001: 性能

- **描述**: DisplayNameService 不应对 API 响应时间产生显著影响
- **测量**: 后端在 `get_ui_config()` 中预计算 `field_display_names`，前端无需逐字段查询。单次调用 < 5ms
- **优先级**: Must
- **来源**: 工程判断

### NFR-002: 向后兼容

- **描述**: 所有现有 YAML schema 无需修改即可工作
- **测量**: 不配 `display_name_field` 的对象自动推断，不配 `display_format` 的关联使用目标对象的 `display_name_field`。现有前端组件无需改代码即可继续工作
- **优先级**: Must
- **来源**: 用户确认的渐进迁移要求

### NFR-003: 可测试性

- **描述**: DisplayNameService 必须是纯逻辑服务，不依赖数据库或外部状态
- **测量**: 单元测试覆盖率 > 90%，可独立于 Flask 测试
- **优先级**: Should
- **来源**: 工程质量

---

## 5. 外部接口需求

### IF-001: API `/api/v2/meta/{type}/ui-config` 扩展

- **类型**: API
- **端点**: `GET /api/v2/meta/{type}/ui-config`
- **新增响应字段**:
```json
{
  "id": "business_object",
  "name": "业务对象",
  "display_name_field": "name",              // 新增
  "field_display_names": {                     // 新增
    "code": "编码",
    "name": "名称",
    "domain_name": "所属领域",
    "status": "状态"
  },
  "relation_displays": {                       // 新增
    "domain": "{code} - {name}",
    "module": null
  },
  "fields": [...]
}
```
- **来源**: Phase 13 设计

### IF-002: 前端 MetaListPage 组件集成

- **类型**: UI
- **入口**: [MetaListPage.vue](file:///d:/filework/excel-to-diagram/src/components/common/MetaListPage/MetaListPage.vue)
- **变更**:
  - L168: 列标题 `column.label` 回退链增加 field.name
  - L730-734: 删除确认用 `displayNameService.getObjectDisplayName(row)`
  - L522: 详情标题用 `displayNameService.getFieldName` 获取对象级名称
  - L9/L95/L100/L127: 搜索和筛选占位符统一风格
- **来源**: 代码分析

### IF-003: 前端其他组件集成

- **类型**: UI
- **变更清单**:

| 组件/文件 | 行号 | Before | After |
|-----------|------|--------|-------|
| useMetaList.js `_transformColumns` | L878 | `label: col.label \|\| col.title` | `label: col.label \|\| col.title \|\| displayNameService.getFieldName(col.key)` |
| useMetaList.js `_transformFilters` | L1187 | `field.label \|\| field.name \|\| field.semantics?.display_name \|\| field.id` | `displayNameService.getFieldName(key, 'filter')` |
| DetailPage.vue | L316 | `label: f.name \|\| f.id` | `label: displayNameService.getFieldName(f.id, 'detail')` |
| MetaTable.vue | L93 | `{{ col.label }}` | 不变（label 已在 useMetaList 中解析） |
| MetaForm.vue | L118 | validator: `f.key && f.label` | validator: `f.key`（放宽，label 由 MetaForm 内部计算） |
| FilterBar.vue | L186 | validator: `f.key && f.label` | validator: `f.key`（放宽） |
| ObjectPage.vue | L400 | `def?.label \|\| key` | `displayNameService.getFieldName(key, 'detail')` |
| ExportDialog.vue | L86-92 | 硬编码 objectTypeNameMap | `metaConfig?.name` 或 `displayNameService.getFieldName(objectType, 'header')` |
| MetaDialog.vue | L97-100 | `meta.label` | `meta.label \|\| displayNameService.getFieldName(objectType, 'header')` |
- **来源**: 代码分析

---

## 6. 过渡需求

### TR-001: 渐进迁移（零破坏）

- **描述**: 现有 YAML 和代码无需修改即可正常工作
- **策略**:
  1. 后端新增字段为 API 响应增量添加，不修改现有字段
  2. 前端组件通过 DisplayNameService 增强回退链，带原逻辑作为优先优先级
  3. 现有 YAML 中与 `field.name` 相同的 `columns.title` 不需要立即删除（可渐进清理）
  4. 未配 `display_name_field` 的对象自动推断，行为等价于现有 heuristics
- **回滚计划**: 移除新增字段，前端回退到原回退链逻辑
- **来源**: 用户确认

---

## 7. 约束与假设

### 7.1 技术约束

- Python 3.10+ (dataclass + typing)
- Vue 3 Composition API
- 不引入新的 Python 依赖
- 不引入新的前端 npm 包

### 7.2 业务约束

- 本次只聚焦 DisplayName（不包含 Consumption View / I18n / Shared Property）
- YAML 单一事实原则不可违反
- 不改变现有 MetaTable/MetaForm 的 prop 接口（向后兼容）

### 7.3 假设

- `fields[].name` 当前在所有 YAML schema 中都是中文名称 — 来源：已验证代码库中 26 个 YAML 文件
- 前端 metaService 10分钟缓存不会成为 DisplayName 更新的阻碍 — 来源：DisplayName 跟随 schema 更新，不需要比 schema 更频繁的更新
- 关联对象的 `display_name_field` 字段值总是存在于 record 中 — 来源：假设数据完整性由数据库保证

---

## 8. 优先级与里程碑建议

| ID | 需求 | 优先级 | 理由 |
|----|------|--------|------|
| FR-001 | 对象级 display_name_field | Must | 基础能力，所有后续功能依赖 |
| FR-003 | 后端 DisplayNameService | Must | 核心服务 |
| FR-006 | API 响应扩展 | Must | 前后端桥梁 |
| FR-007 | 前端 DisplayNameService | Must | 所有前端组件统一入口 |
| FR-005 | 关联显示格式 | Must | Phase 12 Value Help 集成依赖 |
| FR-002 | 关联显示格式 YAML 声明 | Must | Phase 12 Value Help 集成依赖 |
| FR-004 | 对象实例名解析 | Must | 删除确认/导出/面包屑需求 |
| FR-008 | 单一事实原则验证 | Must | 架构约束 |

**建议里程碑**:

| 里程碑 | 范围 | 预计 |
|--------|------|------|
| M1: 后端模型 + 服务 | FR-001, FR-003, FR-005, FR-006 | 后端 DisplayNameService + API 扩展 |
| M2: 前端 DisplayNameService | FR-007 | 前端工具函数 + metaService 适配 |
| M3: 通用组件集成 | IF-002, IF-003（MetaListPage/MetaTable/MetaForm/DetailPage/FilterBar） | 10个组件的渐进增强 |
| M4: 业务模块 + Excel | 业务模块验证 + ExportDialog 适配 + Excel 导出后端适配 | 适配点验证 |
| M5: YAML 渐进补全 + 单一事实验证 | FR-008, FR-002 | YAML schema 补充 + 原则验证 |

---

## 9. 变更/设计提案（RFC）

### 9.1 As-Is 分析

#### 当前架构

```
YAML Schema (fields[].name = 唯一权威源)
     │
     ▼
BOFramework.get_ui_config() → API Response
     │                          ├── fields[].name
     │                          ├── ui_view_config.list.columns[].title（冗余）
     │                          └── (无 display_name_field / display_format)
     │
     ▼
前端各组件独立解析：
     ├── MetaListPage: col.label || col.title
     ├── MetaTable:     col.label (no fallback)
     ├── MetaForm:      field.label (validator requires label)
     ├── DetailPage:    f.name || f.id
     ├── ObjectPage:    def?.label || key
     ├── FilterBar:     field.label (validator requires label)
     └── ExportDialog:  hardcoded objectTypeNameMap
```

#### 当前问题清单

| # | 问题 | 影响范围 | 严重程度 |
|---|------|---------|---------|
| 1 | 列标题 `title` 与 `field.name` 重复声明 | 所有 YAML schema | 中（维护负担） |
| 2 | 删除确认靠硬编码 heuristics | MetaListPage.vue L730-734 | 高（业务逻辑脆弱） |
| 3 | 关联显示格式无法声明 | 关联选择器 | 高（Phase 12 依赖） |
| 4 | MetaTable/MetaForm/FilterBar validator 要求 label 存在 | 所有动态渲染组件 | 中（数据冗余） |
| 5 | 回退链不一致（6种不同的 fallback pattern） | 所有 UI | 高（一致性） |
| 6 | ExportDialog 对象类型名称硬编码 | ExportDialog.vue L86-92 | 低（但需修正） |

#### 相关代码路径

| 文件 | 关键行 |
|------|--------|
| `meta/core/models.py` | MetaObject dataclass、RelationConfig dataclass |
| `meta/core/yaml_loader.py` | YAML 解析逻辑 |
| `meta/core/bo_framework.py` | `get_ui_config()` L395-500 |
| `src/composables/useMetaList.js` | `_transformColumns` L870-928, `_transformFilters` L1225-1259 |
| `src/components/common/MetaListPage/MetaListPage.vue` | L9, L95, L100, L127, L168, L522, L730-734 |
| `src/components/common/MetaTable/MetaTable.vue` | L93, L293 |
| `src/components/common/MetaForm.vue` | L16, L118 |
| `src/components/common/DetailPage/DetailPage.vue` | L316 |
| `src/components/common/ObjectPage/ObjectPage.vue` | L400-403 |
| `src/components/common/FilterBar/FilterBar.vue` | L11, L186 |
| `src/components/common/ExportDialog/ExportDialog.vue` | L86-92 |
| `src/services/metaService.js` | 全文件 |

### 9.2 目标状态

#### 目标架构

```
YAML Schema
  ├── fields[].name = 字段唯一默认显示名称（单一事实）
  ├── display_name_field: <字段ID> — 对象级显示字段（新事实）
  └── relations[].display_format: "{code} - {name}" — 关联显示格式（新事实）
     │
     ▼
DisplayNameService（后端）
  ├── get_field_name(obj_type, field_id, context)
  ├── get_object_display_name(obj_type, record)
  ├── get_association_display(obj_type, rid, record)
  └── get_all_field_names(obj_type, context)
     │
     ▼
BOFramework.get_ui_config()
  ├── 注入 display_name_field
  ├── 注入 field_display_names (预计算)
  └── 注入 relation_displays
     │
     ▼
API Response → metaService.js（透传缓存）
     │
     ▼
DisplayNameService（前端）
  ├── getFieldName(fieldId, context)
  ├── getObjectDisplayName(record)
  └── getAssociationDisplay(relationId, record)
     │
     ▼
所有前端组件通过统一入口获取（单一解析链）:
  ├── MetaListPage → useMetaList → displayNameService
  ├── MetaTable → displayNameService
  ├── MetaForm → displayNameService
  ├── DetailPage → displayNameService
  ├── ObjectPage → displayNameService
  ├── FilterBar → displayNameService
  └── ExportDialog → displayNameService
```

#### 关键变更

| 变更 | 类型 | 影响 |
|------|------|------|
| `MetaObject` + `display_name_field` | 数据模型 | 新增 Optional 字段 |
| `RelationConfig` + `display_format` | 数据模型 | 新增 Optional 字段 |
| `display_name_service.py` | 新建 | 后端统一服务 |
| `API /ui-config` 扩展 | API | 3 个新字段 |
| `displayNameService.js` | 新建 | 前端统一工具函数 |
| 10 个组件渐进增强 | 重构 | 统一回退链 |

### 9.3 详细设计

#### 9.3.1 模块/组件设计

```
Phase 13 新增/修改的文件：

后端:
├── meta/core/models.py              [修改] MetaObject + display_name_field
│                                        RelationConfig + display_format
├── meta/core/yaml_loader.py         [修改] 解析新增字段
├── meta/services/display_name_service.py  [新建] 核心服务
└── meta/core/bo_framework.py        [修改] get_ui_config() 注入新字段

前端:
├── src/utils/displayNameService.js  [新建] 前端 DisplayNameService
├── src/services/metaService.js      [修改] 确认透传新字段
├── src/composables/useMetaList.js   [修改] L878, L1187 统一回退链
├── src/components/common/MetaListPage/MetaListPage.vue  [修改] L730-734
├── src/components/common/MetaTable/MetaTable.vue        [修改] L293 validator
├── src/components/common/MetaForm.vue                   [修改] L118 validator
├── src/components/common/DetailPage/DetailPage.vue       [修改] L316
├── src/components/common/ObjectPage/ObjectPage.vue       [修改] L400-403
├── src/components/common/FilterBar/FilterBar.vue         [修改] L186 validator
└── src/components/common/ExportDialog/ExportDialog.vue   [修改] L86-92

不在此范围的:
- Consumption View（后续评估）
- I18n / 多语言（Phase 14）
- Shared Property（后续评估）
```

#### 9.3.2 数据模型

```python
# MetaObject 新增
@dataclass
class MetaObject:
    display_name_field: Optional[str] = None  # 如 "name"

# RelationConfig 新增
@dataclass
class RelationConfig:
    display_format: Optional[str] = None  # 如 "{code} - {name}"
```

#### 9.3.3 主流程

**流程1: 字段显示名称解析（get_field_name）**

```
Input: object_type="business_object", field_id="code", context="list"

1. meta = registry.get("business_object")
2. field = meta.fields.find(f.id == "code")  → {id: "code", name: "编码", ...}
3. view_override = meta.ui_view_config.list.columns.find(title exists)
   → 如果 YAML column 有 title="编码"，返回 "编码"
   → 如果没有 title，进入下一步
4. return field.name → "编码" ✓
```

**流程2: 对象实例显示名称（get_object_display_name）**

```
Input: object_type="business_object", record={id:1, code:"BO001", name:"我的对象"}

1. meta = registry.get("business_object")
2. display_field = meta.display_name_field  → "name"（来自 YAML）
3. return record["name"] → "我的对象" ✓

如果未配 display_name_field:
2. display_field = auto_infer(meta)
   → semantics.display_name: true? → 返回该字段
   → has field "name"? → 返回 "name"
   → has field "code"? → 返回 "code"
   → first string non-system field
```

**流程3: 关联显示（get_association_display）**

```
Input: object_type="product", relation_id="domain",
       record={id:3, code:"AI", name:"人工智能"}

1. meta = registry.get("product")
2. rel = meta.relations.find(r.id == "domain")
3. rel.display_format is "{code} - {name}"?
   → format → "AI - 人工智能" ✓
4. else → get_object_display_name("domain", record) → "人工智能"
```

#### 9.3.4 DisplayNameContext 定义

```python
class DisplayNameContext:
    DEFAULT = "default"       # 默认
    LIST = "list"             # 列表页列标题
    DETAIL = "detail"         # 详情页字段标签
    FORM = "form"             # 表单字段标签
    FILTER = "filter"         # 筛选器标签
    ASSOCIATION = "association"  # 关联选择器
    SEARCH = "search"         # 搜索框占位符
    HEADER = "header"         # 页面标题/面包屑
    CONFIRM = "confirm"       # 确认对话框
    EXPORT = "export"         # 导出列标题
```

#### 9.3.5 前端组件适配详细分析

##### （A）通用UI组件适配点

**MetaListPage + useMetaList**（最核心的适配点）

| 行号 | 当前 | 适配后 | 影响场景 |
|------|------|--------|---------|
| L878 | `label: col.label \|\| col.title` | `label: col.label \|\| col.title \|\| ds.getFieldName(col.key)` | 所有列表页列标题 |
| L825 | `label: col?.label \|\| col?.title \|\| field` | `label: ds.getFieldName(field, 'filter')` | 列头筛选下拉 |
| L1066 | `label = (col.label \|\| col.title \|\| '').toString()` | `label = ds.getFieldName(col.key)` | 列宽推断 |
| L1187 | `field.label \|\| field.name \|\| field.semantics?.display_name \|\| field.id` | `ds.getFieldName(key, 'filter')` | 筛选器自动生成 |
| MetaListPage.vue L95 | `:label="field.label"` | 不变（label 已在上层解析） | 筛选器标签 |
| MetaListPage.vue L168 | `:label="column.label"` | 不变（label 已在上层解析） | 表格列标题 |
| MetaListPage.vue L9 | `f.label` | 不变（label 已在上层解析） | 搜索占位符 |
| MetaListPage.vue L522 | `metaConfig?.detail?.title \|\| metaConfig?.name \|\| '详情'` | `metaConfig?.detail?.title \|\| ds.getFieldName(objectType, 'header') \|\| '详情'` | 详情标题 |
| MetaListPage.vue L730-734 | 硬编码 heuristics | `ds.getObjectDisplayName(row)` | 删除确认 |

**MetaTable**

| 行号 | 当前 | 适配后 |
|------|------|--------|
| L93 | `{{ col.label }}` | 不变（label 来自上层，已统一解析） |
| L293 | validator: `col.key && col.label` | validator: `col.key`（放宽，label 非必需） |

**MetaForm**

| 行号 | 当前 | 适配后 |
|------|------|--------|
| L16 | `{{ field.label }}` | 不变 |
| L30/L44/L58/L70 | `placeholder \|\| '请输入${field.label}'` | 不变（placeholder 来自上层） |
| L118 | validator: `f.key && f.label` | validator: `f.key`（放宽） |

**FilterBar**

| 行号 | 当前 | 适配后 |
|------|------|--------|
| L11 | `{{ field.label }}` | 不变 |
| L186 | validator: `f.key && f.label` | validator: `f.key`（放宽） |

**DetailPage**

| 行号 | 当前 | 适配后 |
|------|------|--------|
| L316 | `label: f.name \|\| f.id` | `label: ds.getFieldName(f.id, 'detail')` |

**ObjectPage**

| 行号 | 当前 | 适配后 |
|------|------|--------|
| L400 | `def?.label \|\| key` | `ds.getFieldName(key, 'detail')` |

**ExportDialog**

| 行号 | 当前 | 适配后 |
|------|------|--------|
| L86-92 | 硬编码 `objectTypeNameMap` | 优先使用 `metaConfig?.name` 或 `ds.getFieldName(objectType, 'header')` |

**InlineEditCell**

| 行号 | 当前 | 适配后 |
|------|------|--------|
| L174/L177 | `props.fieldConfig?.placeholder` | 不变（placeholder 来自上层） |

##### （B）已适配业务模块的适配点

| 模块 | 文件 | 当前状态 | DisplayName 影响 |
|------|------|---------|-----------------|
| 用户管理 | UserManagement.vue | 使用 MetaListPage + 自定义 cell | 列标题/筛选/删除确认通过 MetaListPage 自动适配 |
| 角色权限中心 | RolePermissionCenter.vue | 自定义页面，使用 `role.name` 标题 | L3 `role.name` 需改为使用 YAML 中的 display_name_field |
| 用户组管理 | UserGroupManagement.vue | 使用 MetaListPage | 通过 MetaListPage 自动适配 |
| 日志管理 | AuditLogManagement.vue | 使用 MetaListPage | 通过 MetaListPage 自动适配 |
| 枚举类型管理 | EnumTypeManagement.vue | 使用 MetaListPage | 通过 MetaListPage 自动适配 |
| 枚举值管理 | EnumValueManagement.vue | 使用 MetaListPage | 通过 MetaListPage 自动适配 |

**关键发现**：大部分已适配业务模块（5/6）通过 MetaListPage 自动获得 DisplayName 能力，**几乎无需额外改动**。唯一需要关注的是 RolePermissionCenter.vue，它是一个复杂的自定义页面，标题使用了 `role.name`。

**RolePermissionCenter.vue 适配**：
```javascript
// L2-4 Before:
<h2 class="rpc-title">角色权限配置：{{ role?.name || '加载中...' }}</h2>

// After: 使用 metaConfig?.display_name_field 自动解析
// 如果该页面加载了 role metaConfig，可用:
<h2 class="rpc-title">角色权限配置：{{ getObjectDisplayName(role) || '加载中...' }}</h2>
```

##### （C）Excel 导入导出的适配点

**ExportDialog**

| 行号 | 当前 | 适配后 |
|------|------|--------|
| L86-92 | 硬编码 `objectTypeNameMap: { user: '用户', role: '角色', ... }` | 使用 `metaConfig?.name`（来自 YAML 的 `name` 字段） |

**后端 Excel 导出** ✅ 已确认无需改动

代码位置：[import_export_service.py](file:///d:/filework/excel-to-diagram/meta/services/import_export_service.py#L214-L215)

```python
# L214-215: Excel 导出列标题使用 mf.name（即 fields[].name）
for mf in export_fields:
    header_row.append(mf.name or mf.id)
```

**结论**：后端导出已遵循单一事实原则，使用 `fields[].name` 而非 `columns.title`。**无需任何改动。**

**Excel 导入模板** ✅ 已确认无需改动

导入模板同样使用 `field.name` 作为列标题，映射时通过 `field_by_name` 做匹配（[import_export_service.py:L257-258](file:///d:/filework/excel-to-diagram/meta/services/import_export_service.py#L257-L258)）。**无需改动。**

**MetaDialog 标题解析** ✅ 已确认

代码位置：[MetaDialog.vue](file:///d:/filework/excel-to-diagram/src/components/common/MetaDialog.vue#L97-L100)

```javascript
// L97-100: 对话框标题使用 props.meta.label
const dialogTitle = computed(() => {
  if (props.title) return props.title
  return props.entityData ? `${props.editTitle}${props.meta.label || ''}` : `${props.addTitle}${props.meta.label || ''}`
})
```

当前使用 `meta.label`（由调用方传入），DisplayNameService 可增强此处回退为 `metaConfig?.name`。**影响面极小，实施时适配。**

**MetaFormDialog.vue 不存在** — 整个项目只有 MetaDialog.vue，不涉及额外适配。

#### 9.3.6 MetaTable/MetaForm/FilterBar validator 放宽分析

当前这三个组件的 props validator 要求 `col.key && col.label` 或 `f.key && f.label`：

```javascript
// MetaTable.vue L293
columns: { validator: (val) => val.every(col => col.key && col.label) }

// MetaForm.vue L118
fields: { validator: (val) => val.every(f => f.key && f.label) }

// FilterBar.vue L186
fields: { validator: (val) => val.every(f => f.key && f.label) }
```

**适配策略**：放宽 validator 但不移除 label 传递。DisplayNameService 不会改变 label 的赋值位置，它只是在 label 赋值时的回退链中增加 `field.name`。因此：

```javascript
// After: 放宽 validator
columns: { validator: (val) => val.every(col => col.key) }
// 实际使用时，label 仍然会被赋值（通过 useMetaList 的 _transformColumns）
// 只是 validator 不再强制要求
```

**为什么不能完全依赖 DisplayNameService 动态查询而不传 label**：
- MetaTable 是一个纯展示组件，它不应该关心如何获取元数据
- 保持 label 作为 prop 传递，DisplayNameService 在上层（useMetaList）计算 label
- 这样 MetaTable/MetaForm/FilterBar 保持纯粹的展示职责

### 9.4 备选方案

| 方案 | 优点 | 缺点 | 决策 |
|------|------|------|------|
| A: 在每个 field 下新增 `display_config` | 配置集中 | 违反单一事实原则，每个 field 都要写一堆 | ❌ 拒绝 |
| B: 完全由前端 DisplayNameService 解析（不经过后端） | 简单 | 前端需要每次请求时自己查 MetaRegistry，增加延迟 | ❌ 拒绝 |
| C: 后端预计算 + 前端 DisplayNameService（当前方案） | 单一事实、零前端查询延迟、服务端可控 | 需修改 API | ✅ 选择 |

### 9.5 实施与迁移计划

#### 实施顺序

```
Step 1: 后端模型改动
  ├── models.py: MetaObject + display_name_field, RelationConfig + display_format
  ├── yaml_loader.py: 解析新增字段
  └── 单元测试 → 验证模型

Step 2: 后端 DisplayNameService
  ├── meta/services/display_name_service.py → 新建
  ├── bo_framework.py get_ui_config() → 注入 3 个新字段
  └── 单元测试 → 验证解析逻辑

Step 3: YAML Schema 渐进补全
  ├── P0: business_object.yaml (+ display_name_field: name)
  ├── P0: product.yaml (+ display_name_field: name)
  ├── P0: domain.yaml (+ display_name_field: name)
  ├── P1: role.yaml (+ display_name_field: name)
  ├── P1: user.yaml (+ display_name_field: username)
  └── P1: 有 business_key 的对象 → 补 relations.display_format

Step 4: 前端 DisplayNameService
  ├── src/utils/displayNameService.js → 新建
  └── src/services/metaService.js → 确认透传

Step 5: 前端组件渐进增强
  ├── useMetaList.js → L878, L1187 统一回退链
  ├── MetaListPage.vue → L730-734 删除确认
  ├── DetailPage.vue → L316
  ├── ObjectPage.vue → L400
  ├── MetaTable/MetaForm/FilterBar validator 放宽
  └── ExportDialog.vue → objectTypeNameMap 移除

Step 6: 验证
  ├── 功能测试：所有页面的字段显示名称正确
  ├── 回归测试：现有 YAML schema 无修改仍正常工作
  ├── 单一事实验证：确认无冗余 title 声明导致的显示差异
  └── 边界测试：无 YAML 对象、缺失字段、format 占位符缺失
```

#### 风险缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| MetaForm/FilterBar validator 放宽后，label 缺失导致显示空白 | 用户体验 | useMetaList 总是会填充 label，只是放宽了 validator 的硬约束 |
| 自动推断的 display_name_field 不准确 | 显示错误 | 渐进补全 YAML display_name_field，自动推断只是过渡期的安全网 |
| API 响应体积增大 | 性能 | field_display_names 字典极小（~30 fields * ~10 chars = ~300 bytes） |

#### 测试策略

| 测试类型 | 范围 |
|---------|------|
| 单元测试 | `display_name_service.py` 所有方法（> 90% 覆盖率） |
| 集成测试 | API `/ui-config` 返回包含新字段 |
| 前端单元测试 | `displayNameService.js` 工具函数 |
| E2E 测试 | 用户管理列表页列标题 ← 来自 field.name 而非 columns.title |
| 回归测试 | 不配 display_name_field 的老 YAML → 自动推断 |
| 边界测试 | 空 record、缺失 format 字段、无 YAML 对象类型 |

#### 回滚计划

1. 从 `get_ui_config()` 移除新增字段注入
2. 前端回退 useMetaList 的回退链到原逻辑
3. 移除 `display_name_field` / `display_format` 从 YAML schema（可选）
4. 删除 `display_name_service.py` 和 `displayNameService.js`

---

## 10. TBD 清单

| ID | 条目 | 缺失信息 | 下一步 |
|----|------|---------|--------|
| TBD-1 | ~~后端 Excel 导出列标题来源~~ | ✅ **已确认**：使用 `field.name`（[import_export_service.py L215](file:///d:/filework/excel-to-diagram/meta/services/import_export_service.py#L215)），无需改动 | 已解决 |
| TBD-2 | ~~MetaFormDialog / MetaDialog 标题逻辑~~ | ✅ **已确认**：MetaDialog.vue L97-100 使用 `meta.label`，MetaFormDialog.vue 不存在。影响面极小，实施时适配 | 已解决 |
| TBD-3 | Consumption View / I18n / Shared Property 后续优先级 | 用户决策 | 本次不涉及，记录待办 |

---

**Spec + RFC 包含10个章节，最后一节为"TBD 清单"，内容完整。**