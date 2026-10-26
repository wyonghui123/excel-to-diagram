---
alwaysApply: false
description: "元数据对象配置 ui_view_config / detail.facets 关联分区 / 动作权限码时查阅此规则。给出三态必填判据、兜底推导导致裸 ID 列与编辑态空白的根因、平台关联端点过滤列写死何时必须改走 customFetcher、权限码双段式口径。"
globs: "meta/schemas/*.yaml,meta/core/ui_config/*.py,src/components/common/DetailPage/*.vue,src/components/common/ObjectPage/*.vue"
---

# 元模型 UI 视图配置规范（v2026.10.23）

> **来源**：2026-10-23 客户档案 / 供应商档案落点改造实战
> **触发场景**：给元数据对象补 `ui_view_config`、在详情页挂关联分区、给列表动作配权限码
> **核心教训**：**「YAML 里写了」不等于「界面生效」** —— 生效判据是后端真实下发的 JSON 形状

---

## 一、`ui_view_config` 三态必填（否则必出两类缺陷）

对象只要出现在任何 UI 面上（列表 / 详情 / 抽屉），下面三态**必须成组声明**：

| 状态 | 键 | 缺失后果 |
|------|----|---------|
| 列表 | `ui_view_config.list.columns` | 走兜底推导 → **裸 ID 列** |
| 表单 | `ui_view_config.form.sections` | 抽屉**零字段**（只剩保存/取消） |
| 详情 | `ui_view_config.detail.facets` | 详情页无字段分组 / 关联分区无处声明 |

### 1.1 裸 ID 列的根因（兜底推导）

`meta/core/ui_config/config_builder.py` L70-75：

```python
if not _ui_view_config_has_renderable_form(config.get('ui_view_config')):
    from meta.services.view_config_service import view_config_service
    _built = view_config_service.get_or_build_view_config(object_type, view_name)
    if _built:
        config['ui_view_config'] = _make_json_safe(_built)
```

兜底推导按 `ui.visible` 收**全部字段** ⇒ 技术主键 `id`、`created_at`、审计字段全被渲染成列，
列表里每行都显示裸 ID、看不出这条记录是谁。

### 1.2 编辑态空白的根因（两处渲染来源不同）

`src/components/common/DetailPage/DetailPage.vue` 的 `computedSections`：

| 来源 | 行号 | 生效条件 |
|------|------|---------|
| `ui_view_config.form.sections` | L686-736 | **读、写两态都渲染**（无 isEditing 门槛） |
| `detail.facets[].fieldGroup` | L880 | 仅 `!isEditing && formSections.length === 0` |
| `detail.tabs[].fieldGroup` | L839 | 编辑态显式 `continue`（跳过） |

⇒ 抽屉（编辑态）只能靠 `form.sections` 供给字段；`detail.facets` 里的 `fieldGroup` 顶多补只读态。

### 1.3 修复判据（不是「yaml 写了」）

**唯一可靠的判据是后端真实下发的 JSON**：

```python
from meta.core.ui_config.config_builder import _ui_view_config_has_renderable_form
# True ⇒ 走 YAML 声明；False ⇒ 已被兜底推导覆盖（裸 ID 列 / 空表单）
```

验证要**用真实 loader 加载 + `_make_json_safe` 序列化后**再看形状，不要只读 YAML 文本。

---

## 二、详情页关联分区：何时必须走 `customFetcher`

平台关联端点的过滤列**写死**在 `AssociationSection.vue` L1113-1119：

```js
const associationFilters = computed(() => {
  const parentKey = `${props.objectType}_id`      // ← 写死
  return { [parentKey]: props.objectId }
})
```

### 2.1 判据

| 场景 | 能否走平台关联端点 |
|------|------------------|
| 子表外键列名 == `{父对象类型}_id` | ✅ 可以 |
| 子表外键列名**不是**这个（如 `relation_id` / `party1_id` / `party2_id`） | ❌ **必须走 `customFetcher`** |

### 2.2 为什么必须 —— 这是数据泄漏，不是显示问题

后端收到一个**不存在的列名**过滤条件时，会**忽略该条件**返回全量。
结果：一个关系详情页会列出**所有人**的档案。

> **[!!!] 跨行数据泄漏级风险 [!!!]**
> 只要子表外键列名与 `{父对象类型}_id` 不一致，又没改走 `customFetcher`，
> 详情页就会把别的关系的数据一起列出来。改走 `customFetcher` 不是"显示问题"，是"权限问题"。

### 2.3 `customFetcher` 分区的声明写法

```yaml
detail:
  facets:
    - title: 客户档案
      id: customer_account_section
      type: association
      association: customer_account
      customFetcher: relation_accounts     # ← 关键
      readonly: true
      pageSize: 5
      actions:
        - key: create
          label: 新建客户档案
          variant: primary
          permission: customer_account:customer_account_create
```

放行闸门在 `DetailPage.vue` L901-905：带 `customFetcher` 的 facet **不要求**在 `associations` 里
声明集合类型（自定义取数器接管取数，与平台关联端点无关）。

> 注意 `detail.tabs` 分支（L776-870）与 `detail.facets` 分支（L871-932）**不是同一套闸门**：
> tabs 分支有 `safeActions` 过滤（readonly 时只保留 `list` / `create`），
> facets 分支（L917）直接把 `f.actions` 原样透传。声明分区前先确认父对象走的是哪个分支。

---

## 三、动作权限码：双段式 `{bo}:{bo}_{action}`

`permissions` 表里实际存在的形态是**双段式**：

```
customer_account:customer_account_create      ✅ 命中
customer_account:create                       ❌ 命中数 0 ⇒ 非 admin 看不到按钮
```

口径与 `menu_auto_generator._derive_permissions_from_bindings` 一致。
写单段式不会报错，只会**静默不显示按钮** —— 排查时先查 `permissions` 表实际值。

---

## 四、关联分区：按父行 role 互斥 还是 并列显示

判据不是「父行字段是否可编辑」，而是**父对象是否「一实例一角色」**：

- 父对象的一个实例只能对应**一个**角色（`role` 在唯一键里，如 `party_relation`
  ＝ `(party1_id, party2_id, role, le_org_id)` 且文件头写明「一实例一角色」）
  ⇒ 分区**必须按 role 互斥渲染**，用 `visibleWhen: {field: role, equals: X}`。
  两侧恒显示会让 UI 允许 DB 模型禁止的状态（一条关系同时挂客户档案和供应商档案）。
- 父对象的一个实例可**同时具备多个**角色（如 `party` 本身可既为客户又为供应商）
  ⇒ 分区可并列显示。

**role 可编辑不构成「恒显示」的理由**：role 改动后原档案脱离可见分区，属数据
一致性问题，应由「档案与关系 role 一致性」校验兜住，不能靠 UI 常驻来表达。

条件分区不依赖后端新模型字段时优先用 `visibleWhen`（`parse_ui_detail_facet` 已支持
`field/equals/in`）；确实无记录时应显示「暂无」空态占位，不要静默空白。

---

## 四之二、1:1 明细面必须是表单，不是表格

子表外键为 `UNIQUE`（DB 层强制 0..1）时：

- 声明 `cardinality: one`，前端渲染**内联字段组表单**（新建/编辑/保存），
  与 SAP S/4 角色页签字段组、D365 `CustTable` 表单页签同形。
- 不得配 `pageSize`、不得用 `el-table` —— 表格永远最多 1 行，形态即错误表达基数。

---

## 四之三、单页 hub 的页面形态：`ui_view_config.hub`（唯一真源）

「左树 + 多 tab」的单页 hub（菜单 `page_type=multi_object_hub` 且无 children）**不再一对象一个 Vue 壳**。
页面形态只在对象 YAML 里声明一次，前端由 `MultiObjectHubPage` 取配置渲染；
未声明 `hub` 的单页 hub 自动回退普通列表（架构数据 / 定价 / 业务配置等）。

```yaml
ui_view_config:
  hub:                                   # 被查对象 = 菜单 primary_object_type
    object_types: [item_group, item]     # 右表 tab 顺序（必填）
    default_tab: item
    tabs: { item: 物料/服务 }             # objectType → 标签；缺省用 objectType
    state_key: materialManagerState      # 图表往返快照键（sessionStorage）
    disable_version_context: true        # 主数据页恒 true
    scope:                               # 左树
      type: hierarchy                    # 当前仅 hierarchy（HierarchyScopeTree）
      object: item_group                 # 树查询的 BO
      scope_key: item                    # 写入 scopeIds 的键 = 受过滤的 tab
      parent_field: parent_id            # 缺省 parent_id（日历是 parent_calendar_id）
      flat: true                         # 扁平分类：不组树、无展开/收起
      order_by: ''                       # 省略=按 code；''=保持后端顺序
      badge_field / badge_map            # 节点徽标（枚举值 → {label,type}）
      node_icon: none|folder|location|office
      paginate_all: true                 # 树数据超后端单页上限(500)时循环拉全量
      empty_text / search_placeholder
    filters:                             # 每个 tab 的范围过滤；缺省=不受左树影响
      item: { field: item_group_id }     # → item_group_id__in = effective ids
      item_group: { mode: none }         # 显式声明「不过滤」
      party_archive:                     # 两段桥接（无直挂 FK 时）
        bridge:
          through: party_relation        # 中间 BO
          match_field: group_id          # 中间 BO 承接 effective ids 的字段
          collect_field: party2_id       # 从中间 BO 取出的字段
          target_field: id               # 右表过滤字段（→ id__in）
          page_size: 500
          empty_sentinel: '-1'           # 选中但无结果：防 __in 空串回退全量
```

口径要点：

- **`effective = 勾选 ∪ 全部子孙`**（树侧算好）；未勾选 = 不加过滤（看全量，业务预期）。
- **未声明的 tab 也要显式给策略**（`mode: none`）：`combinedFilters` 是 tab 间共享的 computed，
  落到默认分支会被注入 `relationExtra` 噪声过滤。
- **桥接失败回退全量**（`bridgeIds[objectType]=null`），宁可多显示不可误显空集。
- 菜单 `object_types` 只作路由登记（FK 落点），**不参与渲染决策**；渲染只认 `hub.object_types`。
- 新增/改页形态后必须核对两处序列化链：v1 `schema_loader._serialize_ui_view_config`、
  v2 `UIConfigBuilder.build`（整体替换时必须保留 yaml 声明的 `hub`）。
- **状态保留靠 `state_key`，不靠 keep-alive**：离开路由时 `onBeforeRouteLeave` →
  `saveStateForDiagram()` 写 sessionStorage（`scopeIds` / `activeTab` / `tabFilters`），
  返回时 `onMounted` → `restoreStateFromDiagram()` 恢复，树由
  `watch(checkedKeysFromScope)` 回写勾选。因此：不要给 hub 页另叠一套持久化；
  也不要把 `MultiObjectHubPage` 加进 keep-alive 白名单（按组件名缓存会让多个 hub
  页共用一个实例，必串状态）。快照只在**路由离开**时写，F5 / 新标签不保留，属预期边界。
  7 个 hub 页必须各有独立 `state_key`，否则快照互相覆盖。

**树组件只有一个**：`HierarchyScopeTree`（`flat` 控制平铺/树形、`paginate_all` 控制全量拉取）。
不存在第二个 *ScopeTree 专用壳 —— 页面差异一律进 YAML，不进组件。

---

## 五、自检清单

```
□ list.columns 声明齐全，且不含 id / 审计字段
□ form.sections 声明齐全（抽屉要靠它）
□ detail.facets 声明（含关联分区）
□ 关联分区：子表外键列名 == {父对象类型}_id ? 否 ⇒ 必须 customFetcher
□ 关联分区：customFetcher 分支在 AssociationSection 里已实现并有竞态守卫
□ 动作权限码用双段式，且已查 permissions 表确认存在
□ 子表外键 UNIQUE？（1:1）⇒ cardinality: one + 表单渲染，禁 pageSize/表格
□ 父对象「一实例一角色」？⇒ 分区必须 visibleWhen 按 role 互斥，禁两侧恒显示
□ 用真实 loader + _make_json_safe 验证下发形状，不只读 YAML
□ has_renderable_form == True（否则会走兜底推导）
□ 单页 hub：形态写在 ui_view_config.hub，不新增 Vue 壳；每 tab 都有 filters 策略
□ 单页 hub：改 page_type 必须配套 migration（种子只覆盖跑 seed 的环境）
□ 单页 hub：每页独立 state_key，状态靠快照恢复，不要加 keep-alive
□ 菜单 required_permissions 逐个查 permissions 表存在（双段式 `{bo}:{bo}_{action}`）
```

---

## 六、相关代码

- 兜底推导入口：[config_builder.py](file:///d:/filework/excel-to-diagram/meta/core/ui_config/config_builder.py) L7-24 / L70-75
- 详情页分区计算：[DetailPage.vue](file:///d:/filework/excel-to-diagram/src/components/common/DetailPage/DetailPage.vue) L636-932
- 关联分区组件：[AssociationSection.vue](file:///d:/filework/excel-to-diagram/src/components/common/ObjectPage/AssociationSection.vue)
- 单页 hub 解析：[hubOptions.js](file:///d:/filework/excel-to-diagram/src/components/common/MultiObjectHubPage/hubOptions.js)
- 单页 hub 渲染：[MultiObjectHubPage.vue](file:///d:/filework/excel-to-diagram/src/components/common/MultiObjectHubPage/MultiObjectHubPage.vue)
- 通用左树：[HierarchyScopeTree.vue](file:///d:/filework/excel-to-diagram/src/components/common/HierarchyScopeTree/HierarchyScopeTree.vue)
- 参照实现（客户档案）：[customer_account.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/customer_account.yaml)

---

## CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|---------|
| 2026-10-23 | AI Assistant | 初版：ui_view_config 三态必填与兜底推导根因、customFetcher 判据（跨行数据泄漏风险）、权限码双段式、自检清单 |
| 2026-10-23 | AI Assistant | **修正「分区恒显示」判据**（改为按父对象是否「一实例一角色」定）；新增「1:1 明细面必须是表单」与 `cardinality`/`visibleWhen` 用法 |
| 2026-10-24 | AI Assistant | 新增「单页 hub 的页面形态：`ui_view_config.hub`」契约（左树/多 tab 全部 YAML 声明，不新增 Vue 壳）；自检清单补 hub 与权限码存在性两条 |
| 2026-10-24 | AI Assistant | 补充 hub 页状态保留机制（`state_key` 快照 + 路由守卫写、挂载恢复、树回写；禁 keep-alive 与另叠持久化），自检清单补一条 |
