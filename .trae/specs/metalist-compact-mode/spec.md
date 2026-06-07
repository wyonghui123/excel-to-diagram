# MetaListPage Compact Mode — 统一列表展示

> 版本: v1.1
> 创建日期: 2026-05-24
> 状态: 设计完成，待审阅

---

## 一、背景与目标

### 1.1 现状问题

当前项目中，列表展示由多个互不统一的组件各自实现：

| 场景 | 当前组件 | 内部实现 |
|------|----------|----------|
| 详情页已关联成员列表 | `AssociationPanel.vue` | 手写 `el-table` + `useAssociation` |
| N-M 添加关联弹窗 | `AssignmentDialog.vue` | 手写 `el-table` + `boService.query` |
| ValueHelp/SearchHelp 弹窗 | `SearchHelpDialog.vue` | 手写 `el-table` + `useValueHelp` |
| FK 字段表单选择 | `ValueHelpField.vue` → `SearchHelpDialog` | 同上（dialog result_type） |
| 独立列表页 | `MetaListPage.vue` | 全功能元数据驱动列表 |

所有组件各自维护表格逻辑（列检测、搜索、分页、选择），功能重叠、代码重复，体验不一致。

### 1.2 目标

1. **列表统一**：所有"表格选择列表"场景复用 `MetaListPage`，删除 `AssociationPanel`，精简 `SearchHelpDialog`
2. **按模式自适应**：同一个 `MetaListPage` 在不同容器中自动调整功能和样式
3. **列智能分级**：不同模式自动展示不同优先级的列（required/default/optional）
4. **功能复用**：分页、搜索、过滤、选择等能力全场景统一

---

## 二、Column Priority（列优先级系统）

### 2.1 三级分类

| 优先级 | 含义 | page 模式 | dialog 模式 | embedded 模式 |
|--------|------|:---:|:---:|:---:|
| `required` | 必须展示，识别对象用 | 显示 | 显示 | 显示 |
| `default` | 默认展示，辅助信息 | 显示 | 显示 | 隐藏 |
| `optional` | 可选展示，仅完整页 | 显示 | 隐藏 | 隐藏 |

### 2.2 自动推断规则

当 YAML 中未显式配置 `column_priority` 时，按以下规则自动推断：

```javascript
function inferColumnPriority(column, fieldMeta) {
  // L1: 业务键 → required
  if (column.prop === 'id') return 'required'
  if (fieldMeta?.business_key === true) return 'required'
  if (fieldMeta?.semantics?.display_name === true) return 'required'

  // L2: 系统时间戳 → optional
  const sysFields = ['created_at', 'updated_at', 'created_by', 'updated_by']
  if (sysFields.includes(column.prop)) return 'optional'
  if (fieldMeta?.type === 'datetime' || fieldMeta?.type === 'timestamp' || fieldMeta?.type === 'date') return 'optional'

  // L3: 其余 → default
  return 'default'
}
```

### 2.3 YAML 显式覆盖

```yaml
list:
  columns:
    - field: username
      width: 120
      column_priority: required    # 可选的，不写时自动推断
    - field: email
      width: 180
      # column_priority 未写 → 自动推断为 default
    - field: last_login_at
      width: 160
      format: datetime
      column_priority: default     # 手动提升：从 optional 改为 default（dialog 也展示）
```

### 2.4 visibleColumns 过滤逻辑

```javascript
const visibleColumns = computed(() => {
  return columns.value.filter(col => {
    // 保留原有的 visible / default_visible 过滤
    if (col.visible === false || col.default_visible === false) return false

    // compact mode 列优先级过滤
    // 仅在从 metaService 加载列时生效；columns prop 覆盖时跳过滤
    if (mode === 'page' || columnsFromProp) return true

    const priority = col.column_priority || 'default'
    if (mode === 'dialog') return priority === 'required' || priority === 'default'
    if (mode === 'embedded') return priority === 'required'

    return true
  })
})
```

**注意**：当通过 `columns` prop 直接传入列定义时（embedded/dialog 典型用法），列已经由父组件精选，**不经过 priority 过滤**。priority 过滤仅在 MetaListPage 自行从 metaService 加载列且 mode 非 page 时生效。

---

## 三、MetaListPage Compact Mode 设计

### 3.1 新增 Props

```javascript
const props = defineProps({
  // ========== 现有 Props（保持不变） ==========
  objectType:       { type: String, required: true },
  options:          { type: Object, default: () => ({}) },
  initialFilters:   { type: Object, default: () => ({}) },
  exportOptions:    { type: Object, default: () => ({ includeFilters: true }) },
  importOptions:    { type: Object, default: () => ({ validateBeforeImport: true }) },
  rowActionsWidth:  { type: [Number, String], default: 200 },
  enableDetail:     { type: Boolean, default: true },
  enableAutoCrud:   { type: Boolean, default: true },
  rowMutability:    { type: String, default: null },
  externalEditing:  { type: Boolean, default: null },

  // ========== 新增 Props ==========

  /**
   * 列表模式
   * 'page'     - 完整页面模式（默认，保持现有行为）
   * 'embedded' - 内嵌面板模式（详情页关联Tab）
   * 'dialog'   - 弹窗选择模式（AssignmentDialog内）
   */
  mode: {
    type: String,
    default: 'page',
    validator: (v) => ['page', 'embedded', 'dialog'].includes(v)
  },

  /**
   * 列定义覆盖（embedded/dialog 模式生效）
   * 传入后跳过 metaService.getViewConfig()，直接使用此列定义
   * 格式兼容 YAML list.columns（{ field, label, width, ... }）
   */
  columns: {
    type: Array,
    default: null
  },

  /**
   * 排除的 ID 列表（dialog 模式生效）
   * 通过 fetcher 参数传给后端做 SQL NOT IN 过滤
   */
  excludeIds: {
    type: Array,
    default: () => []
  },

  /**
   * 行唯一键（用于 excludeIds 匹配和 selection）
   * 默认 'id'
   */
  rowKey: {
    type: String,
    default: 'id'
  },

  /**
   * 行操作按钮（embedded/dialog 模式生效）
   * page 模式下从 YAML row_actions 读取，此 prop 忽略
   * 格式: [{ key: string, label: string, type?: string, icon?: string }]
   */
  rowActions: {
    type: Array,
    default: null
  }
})
```

### 3.2 功能开关矩阵

```
功能                           page(默认)    embedded     dialog
───────────────────────────────────────────────────────────────
搜索框                         显示         显示         显示
过滤器（可见+高级+表头）         显示         隐藏         显示
工具栏操作按钮                   显示         隐藏         隐藏
行选择 checkbox                 可选         隐藏         强制开启
详情 Drawer                     可用         禁用         禁用
自动 CRUD（新建/编辑/删除）       可用         禁用         禁用
导出 / 导入                     可用         禁用         禁用
内联编辑                        可用         禁用         禁用
行操作（rowActions）             来自 YAML    来自 prop    隐藏
分页                            完整组件      精简版       精简版
样式                            页面级       紧凑内嵌     紧凑弹窗
```

### 3.3 新增 emits

```javascript
const emit = defineEmits([
  // ========== 现有 emits ==========
  'action', 'create', 'edit', 'delete', 'detail',
  'export', 'import', 'batch-delete', 'data-loaded',
  'request-edit',

  // ========== 新增 emits ==========

  /**
   * embedded 模式下工具栏按钮点击
   * payload: { action: string }
   */
  'toolbar-action'
])
```

### 3.4 `useMetaList` 适配

在 `useMetaList.js` 中新增以下逻辑分支：

**A. 列来源分支**

```
if (columns prop 已传入 && (mode === 'embedded' || mode === 'dialog')):
    → 直接用 columns prop，调用 _transformColumns() 转换格式
    → 跳过 metaService.getViewConfig()
else:
    → 现有流程：metaService.getViewConfig() → _transformColumns()
```

**B. 数据加载分支**

```
loadList():
    params = { page, pageSize, keyword, filters, ordering }

    if (excludeIds.length > 0):
        params.exclude_ids = excludeIds.join(',')   // 传给后端

    if (options.fetcher):
        result = await options.fetcher(params)       // 自定义数据源
    else:
        result = await boService.query(objectType, params)
```

**C. 行选择分支**

```
selectionConfig.enabled:
    if (mode === 'dialog'):
        → true （强制开启）
    elif (mode === 'embedded'):
        → false （强制关闭）
    else:
        → 现有逻辑（有批量操作或 metaConfig 配置时开启）
```

### 3.5 CSS Compact 样式

当 `mode !== 'page'` 时，注入 `meta-list-page--compact` class：

```scss
.meta-list-page--compact {
  height: auto;              // 取消 100% 高度（由父容器决定）

  .toolbar-area {
    padding: 8px 0;          // 缩小工具栏内边距
  }

  .filter-area,
  .toolbar-actions,
  .toolbar-right-actions {
    display: none;           // 隐藏过滤器行和操作按钮行
  }

  .meta-table-wrapper {
    margin-top: 0;
  }

  .pagination-container {
    padding: 8px 0 0;
    justify-content: flex-end;
  }

  :deep(.el-table) {
    font-size: 13px;          // 缩小表格字体

    .el-table__header th {
      padding: 8px 0;        // 缩小表头内边距
    }

    .el-table__body td {
      padding: 6px 0;        // 缩小单元格内边距
    }
  }
}
```

---

## 四、数据流设计

### 4.1 Embedded 模式（详情页关联面板）

```
ObjectPage (详情页)
  │
  │  section = { type:'association', assocName:'members', assocType:'many_to_many' }
  │  assocConfig = uiConfig.associations.find(a => a.name === 'members')
  │
  ▼
<MetaListPage
  mode="embedded"
  :object-type="assocConfig.target_type"               // 'user'
  :columns="assocConfig.display.columns"               // 列定义覆盖
  :options="{
    fetcher: (params) => boService.queryAssociations(   // 自定义数据源
      objectType, objectId, assocName, params
    ),
    pageSize: 10
  }"
  :initial-filters="{}"                                 // 无需额外过滤
  :row-actions="assocRowActions"                        // [{key:'remove', label:'移除', type:'danger'}]
  @action="handleAssocRowAction"
/>

<!-- [添加成员] 按钮由 ObjectPage 在外层渲染 -->
```

数据流：
```
boService.queryAssociations('user_group', 1, 'members', {page, pageSize, keyword})
  → GET /api/v2/bo/user_group/1/associations/members
  → 后端查 user_group_members 中间表 JOIN users
  → 返回 { items: [...], total: N }
```

### 4.2 Dialog 模式（AssignmentDialog 弹窗）

```
AssignmentDialog (弹窗外壳)
  │
  │  targetType = props.config.target_type              // 'user'
  │  excludeIds = props.excludeIds                     // 已关联的用户ID
  │
  ▼
<MetaListPage
  mode="dialog"
  :object-type="targetType"                             // 'user'
  :columns="config.display?.columns"                   // 列定义覆盖
  :exclude-ids="excludeIds"                            // 后端过滤
  :options="{ pageSize: 10 }"
  @selection-change="handleSelectionChange"
/>

<!-- 弹窗 footer 保留：[取消] [确定(N)] -->
```

数据流：
```
boService.query('user', {page, pageSize, keyword, exclude_ids: '1,2,3'})
  → GET /api/v2/bo/user?page=1&page_size=10&keyword=zhang&exclude_ids=1,2,3
  → 后端 _do_list() 解析 exclude_ids → WHERE id NOT IN (1,2,3)
  → 返回 { items: [...], total: N }
```

### 4.3 后端 exclude_ids 支持

在 `persistence_interceptor.py` 的 `_do_list()` 方法中（约第370行附近），`else` 分支需新增处理：

```python
# 在 _do_list() 的 params 遍历中新增：
elif key == 'exclude_ids':
    # dialog 模式传入的排除 ID 列表
    values = [int(v.strip()) for v in value.split(',') if v.strip()]
    if values:
        placeholders = ','.join(['?' for _ in values])
        filters[f"id NOT IN ({placeholders})"] = values
```

位置：`else` 分支中，在忽略未知字段之前，添加对 `exclude_ids` 特殊参数的处理。

### 4.4 Dialog 模式（SearchHelpDialog 弹窗 — ValueHelp/SearchHelp）

**现状**：`SearchHelpDialog.vue` 内部手写了完整的 el-table 渲染逻辑（约 100 行模板 + 200 行 script），包括搜索、分页、单选/多选。`ValueHelpField.vue` 在 `result_type === 'dialog'` 时打开此弹窗。

**改造策略**：
- `SearchHelpDialog` 保留弹窗外壳、搜索框、确认/取消 footer、树形模式的 el-tree
- `flat` 和 `tree_flat` 模式下的 el-table → `MetaListPage(mode='dialog')`
- `tree` 模式保留 el-tree（与表格渲染差异太大，不在本次统一范围）

**数据适配**：

value_help API 返回的是标准化格式 `{data: [{value, display, code, extra}, ...]}`，而 MetaListPage 的 fetcher 需要返回 `{success, data: {items, total}}`。需要在 fetcher 中做一层映射：

```javascript
// SearchHelpDialog 内的 fetcher 适配器
function valueHelpFetcher(params) {
  return boService.searchValueHelp(sourceType, sourceId, {
    search: params.keyword,
    search_fields: presentation.search_fields,
    page: params.page,
    pageSize: params.pageSize,
    sort: params.sort,
    filters: filterParams,
  }).then(res => ({
    success: res.success,
    data: {
      items: (res.data?.data || []).map(item => ({
        ...item,
        id: item.value,              // MetaListPage 用 id 做 rowKey
      })),
      total: res.data?.total || 0
    }
  }))
}
```

**列映射**：value_help 的 `presentation.columns` 使用 `{field, label, width}` 格式，与 MetaListPage 的 `columns` prop 格式兼容。

**行键**：value_help 数据的唯一键是 `value`，MetaListPage 需要 `row-key="value"`（而不是默认的 `id`）。fetcher 适配器中已通过 `id: item.value` 统一。

**SearchHelpDialog 改造后结构**：

```
el-dialog (720px)
  ├── 搜索栏 (el-input) — 保留在 SearchHelpDialog 中
  │
  ├── [flat / tree_flat 模式]
  │   └── MetaListPage (mode='dialog')
  │       :object-type="source.target_bo"
  │       :columns="presentation.columns"
  │       :row-key="'value'"
  │       :options="{fetcher: valueHelpFetcher, pageSize: pageSize}"
  │       @selection-change="handleSelectionChange"
  │
  ├── [tree 模式] el-tree (lazy) — 保持不变
  │
  ├── [多选标签] 已选项标签列表 — 保留
  │
  └── footer: 取消 / 确定 — 保留
```

**限制**：
- `tree` 模式和 `lazy` 加载的 el-tree 不在本次统一范围
- 级联绑定（parameter_bindings）的过滤参数仍由 `useValueHelp.getFilterParams()` 计算，通过 fetcher 闭包传入

---

## 五、组件变更清单

### 5.1 修改的文件

| 文件 | 变更类型 | 变更内容 |
|------|----------|----------|
| `MetaListPage.vue` | 修改 | 新增 `mode`/`columns`/`excludeIds`/`rowKey`/`rowActions` props；compact CSS class；条件渲染工具栏/详情/CRUD |
| `useMetaList.js` | 修改 | columns prop 覆盖逻辑；column_priority 推断与过滤；excludeIds 传递；selection 模式开关 |
| `AssignmentDialog.vue` | 修改 | 内部 el-table 替换为 MetaListPage (mode='dialog')；保留弹窗外壳和 footer |
| `SearchHelpDialog.vue` | 修改 | flat/tree_flat 模式下的 el-table 替换为 MetaListPage (mode='dialog')；保留弹窗外壳、搜索框、footer、tree 模式 |
| `ObjectPage.vue` | 修改 | association section 中 AssociationPanel → MetaListPage (mode='embedded') |
| `bo_framework.py` | 修改 | 关联序列化中增加 `target_type` 别名和 `target_display_name_field`（上一轮已完成） |
| `persistence_interceptor.py` | 修改 | `_do_list()` 支持 `exclude_ids` 参数 |

### 5.2 删除的文件

| 文件 | 原因 |
|------|------|
| `AssociationPanel.vue` | 功能被 MetaListPage (mode='embedded') 完全替代 |
| `AssociationPanel/index.js` | 配套导出文件 |

### 5.3 关联调整

| 文件 | 调整 |
|------|------|
| `src/components/common/index.js` | 移除 AssociationPanel 导出 |
| `DetailSection.vue` | 检查是否有 AssociationPanel 引用 |
| `DetailPage.vue` | 检查关联 Tab 相关逻辑是否需要调整 |

---

## 六、向后兼容

### 6.1 对现有 page 模式的影响

| 行为 | 影响 |
|------|------|
| `mode` 默认值为 `'page'` | 使用 MetaListPage 的现有页面无需任何改动 |
| `columns` prop 默认 `null` | page 模式下不生效，仍走 metaService 加载 |
| `column_priority` 默认推断 | page 模式不过滤列，所有现有列照常显示 |
| `excludeIds` 默认 `[]` | page 模式不传入，不影响现有查询 |

### 6.2 风险控制

- `column_priority` 不配置时走自动推断，不会改变现有列展示行为
- `_transformColumns` 新增字段采用浅合并，不影响现有转换逻辑
- `visibleColumns` 过滤仅在 `mode !== 'page'` 时生效

---

## 七、测试计划

### 7.1 单元测试

| 测试项 | 验证内容 |
|--------|----------|
| `inferColumnPriority()` | id → required; username(business_key) → required; created_at(datetime) → optional; email → default |
| `visibleColumns` page 模式 | 所有列通过，包括 required + default + optional |
| `visibleColumns` dialog 模式 | optional 列被过滤 |
| `visibleColumns` embedded 模式 | default + optional 列被过滤，仅 required |
| `columns` prop 覆盖 | 传入后跳过 metaService 加载 |
| `selectionConfig` dialog 模式 | `enabled` 为 true |
| `selectionConfig` embedded 模式 | `enabled` 为 false |

### 7.2 集成测试（MCP 浏览器验证）

| 场景 | 验证步骤 |
|------|----------|
| **用户组 → 成员 Tab** | 打开用户组详情 → 切换到"成员"Tab → 确认表格展示 (username, display_name, email) 列 |
| **用户组 → 添加成员弹窗** | 点击"添加成员" → 确认弹窗内有搜索框 + 过滤器（如 status） + checkbox + 分页 |
| **用户组 → 移除成员** | 点击逐行"移除"按钮 → 确认关联被删除 |
| **弹窗搜索过滤** | 在添加成员弹窗搜索 "admin" → 确认结果过滤正确 |
| **弹窗排除已关联** | 确认已关联的成员不在弹窗列表中 |
| **其他对象关联** | 角色 → 权限、角色 → 用户组、用户 → 用户组 等场景均正常 |
| **ValueHelp flat 模式** | 编辑用户 → 点击某个 FK 字段（如 parent user_group）→ 打开 SearchHelpDialog → 确认表格有搜索 + 分页 + 行选择 |
| **ValueHelp tree_flat 模式** | 编辑 domain → 选择 parent domain → 确认表格展示且层级信息正常 |
| **ValueHelp tree 模式** | 有层级关系的 value_help → 确认 el-tree 渲染正常（未受影响） |
| **ValueHelp 多选** | multiple=true 的 value_help → 确认 checkbox 列 + 底部已选标签 → 确认提交后值正确 |

---

## 八、实施步骤

```
Phase 1: useMetaList.js 核心逻辑
  1.1 inferColumnPriority() 函数
  1.2 columns prop 覆盖分支
  1.3 excludeIds 参数透传
  1.4 selectionConfig 模式开关
  1.5 visibleColumns priority 过滤

Phase 2: MetaListPage.vue 模板
  2.1 mode/columns/excludeIds/rowKey props
  2.2 条件渲染（toolbar 隐藏、详情禁用、CRUD 禁用）
  2.3 compact CSS class
  2.4 toolbar-action emit

Phase 3: 后端适配
  3.1 persistence_interceptor.py exclude_ids 支持

Phase 4: ObjectPage 替换 AssociationPanel
  4.1 association section 改用 MetaListPage (mode='embedded')
  4.2 行操作事件处理
  4.3 删除 AssociationPanel.vue 及相关导出

Phase 5: AssignmentDialog 替换内部表格
  5.1 内部 el-table → MetaListPage (mode='dialog')
  5.2 selection-change 对接

Phase 6: SearchHelpDialog 替换内部表格
  6.1 flat/tree_flat 模式 el-table → MetaListPage (mode='dialog')
  6.2 valueHelpFetcher 适配器（数据格式映射）
  6.3 tree 模式保持不变
  6.4 多选标签 + 确认/取消 footer 保留

Phase 7: 验证
  7.1 MCP 浏览器回归测试
  7.2 所有场景逐个验证（N-M 关联 + ValueHelp/SearchHelp）
```
