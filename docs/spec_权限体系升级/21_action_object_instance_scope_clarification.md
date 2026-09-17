# 21 · 动作对象级 / 实例级语义显式化

> 文档编号: 21 | 状态: 草案 v1 | 更新: 2026-09-12
> 主题: 把「动作 = 对象级授权」与「数据范围 = 实例级授权」的两轴关系在 UI 上显式化;
>       并让用户清晰理解「未配置数据范围 = 全实例生效」的安全语义
> 前置: [15_权限配置融合单一化](./15_permission_config_unification.md)（两主轴定义）
>       / [19_org_admin_delegation](./19_org_admin_delegation.md)（实例级呈现）
>       / [20_dimension_scope_business_key](./20_dimension_scope_business_key.md)（业务键锚定）
> 关联: [16_role_to_permission_set_and_user_group_to_org](./16_role_to_permission_set_and_user_group_to_org.md)
>       / [17_org_tree_matrix_architecture](./17_org_tree_matrix_architecture.md)

***

## 1. 背景与动机

### 1.1 当前已就绪的两轴（实层）

| 轴 | 表 | 拦截器 | UI 入口 |
|---|---|---|---|
| 功能权限·对象级 | `permissions` + `permission_set_permissions` | `PermissionInterceptor` ([permission_interceptor.py:113](../../meta/core/interceptors/permission_interceptor.py)) | 矩阵「动作列」cell 勾选 |
| 数据权限·实例级 | `permission_set_data_permissions` + `dimension_scopes` + `permission_rules` | `DataPermissionInterceptor`（query）+ `WriteScopeInterceptor._check_write_read_linkage`（写前调 read PDP） | 矩阵「数据范围」列 → 条件按钮 → Rule Builder |

两轴模型在数据层 + 拦截器层已正交共存（[Spec15 §2.2](./15_permission_config_unification.md#22-数据权限单一范围--例外二分)）。

### 1.2 现状痛点（UI 缺语义标识）

1. **列头无层级提示**：`数据范围` 列与 `查看/创建/编辑/删除` 列平铺呈现，新用户无法直觉理解"勾动作列=对该类对象生效，配数据范围=只对部分实例生效"。
2. **「未配置数据范围 = 全实例」缺警示**：当前 16 个 BO 中**所有默认状态下**矩阵 cell 勾选 + 数据范围未配置 → 用户实际拥有该类对象的所有实例的操作权。**敏感动作（delete / export / import）尤其危险**。
3. **`action_type` 字段闲置**：[`_standard_actions.yaml`](../../meta/schemas/_standard_actions.yaml) 已声明 16 个 action 的 `action_type: crud / batch / business` 分类（[ActionType enum](../../meta/core/models_enums.py#L38-L42)），但前端 `DEFAULT_ACTION_LABELS` 完全忽略，没有按业务类型分块渲染。
4. **OWD 配置入口缺失**：`object_owd` 表已建（[migration add_object_owd_2026](../../meta/migrations/add_object_owd_2026.py)），Salesforce OWD 等价物，**对象级基线 UI 入口尚未实现**（[Spec 15 §5.1.7](./15_permission_config_unification.md#51-组件级动作细化合规-yondesign--封装组件规范) 已规划）。

### 1.3 横向对比（七家头部产品沉淀结论）

| 产品 | 表达方式 |
|---|---|
| SAP PFCG | ACTVT + Authorization Field（含 `*` 通配） |
| AWS IAM | Action + Resource ARN（含 `*`） + Condition |
| Salesforce | OWD（对象级基线） + Role Hierarchy + Sharing Rule |
| Azure RBAC | Actions/NotActions + AssignableScopes |
| Snowflake / Databricks | Object Privileges + Row Access Policy |
| Notion/Airtable/Linear | 角色预设（5-10档） + page 级 override |

→ **设计结论**：**没有任何头部产品在 action 上挂 `level / scope` 字段**。对象级 vs 实例级由 Resource/Scope 的取值（`*` vs 具体值）决定 — 业界共识。

## 2. 目标

### 2.1 必须达到（MUST）

| FR | 标题 | 说明 |
|---|---|---|
| FR-001 | **列头语义标识** | 矩阵列头需显式标注「对象级」/「实例级」，hover 显示完整含义 |
| FR-002 | **敏感动作未配范围警示** | delete / export / import / revoke / dissociate 五类动作，cell 勾选 + 数据范围未配置 → 行级警示 |
| FR-003 | **action_type 驱动分块渲染** | 利用 `_standard_actions.yaml.action_type` 在矩阵列上方分块（crud / batch / business 三组），低门槛语义 |
| FR-004 | **「未配置数据范围 = 全实例」显式声明** | 工具栏加可勾选项「仅显示未配置数据范围的资源」，点击展开全实例提示 |
| FR-005 | **OWD 现状栏** | 矩阵外加「对象级基线（OWD）」只读展示区，显示当前角色的 OWD 派生结果，**不开放编辑**（OWD 配置是 P3 单独 spec 负责） |

### 2.2 应当达到（SHOULD）

| FR | 标题 | 说明 |
|---|---|---|
| FR-006 | **action 工具栏 tooltip 显式说明该动作的"实例级影响"** | 例 delete hover：「删除操作可对数据范围内的实例生效；未配置范围时 = 全实例」 |
| FR-007 | **矩阵分组记忆** | 用户在「展开/折叠」动作组上的选择写入 localStorage，下次进权限配置页保持 |

### 2.3 不做（WON'T）

| 标题 | 理由 |
|---|---|
| 在 `permissions` 表加 `permission_level` 字段 | 与 `data_permissions.permission_level` 重名易混淆，破坏双轴模型 |
| 在 action 上加 `scope: object / instance` 字段 | 业界头部产品都不挂，AWS/SAP/PFCG 均不挂 |
| 拆分「对象级 CRUD」/「实例级 CRUD」两个 action | 动作应是同一个，范围是变量 |

## 3. 详细设计

### 3.1 FR-001 列头语义标识

#### 3.1.1 现状（[ResourceActionMatrix.vue:167](../../src/views/SystemManagement/components/ResourceActionMatrix.vue#L167)）

```vue
<el-table-column label="数据范围" min-width="240" v-if="dimensions.length > 0">
  ...
</el-table-column>
<el-table-column v-for="action in visibleColumns" :label="actionLabel(action)" />
```

#### 3.1.2 目标视觉

```
┌──────────┬──────────────────────┬─────────────────────────────────────┐
│ 资源      │ 📍 实例级             │ 🔑 对象级                            │
│ resource │ 数据范围              │ [CRUD 组] [批量组] [业务组]            │
│          │ (hover: 实例级范围)    │ (hover: 对象级权限，对该资源类型所有实例) │
└──────────┴──────────────────────┴─────────────────────────────────────┘
```

#### 3.1.3 关键修改点

**文件**：`src/views/SystemManagement/components/ResourceActionMatrix.vue`

1. **列头 slot 替换** — 「数据范围」列与「动作」列都用 `#header` slot 注入分组标签
2. **`visibleColumns` 改造** — 从 action 字符串数组 → 按 `action_type` 分组的对象数组

```javascript
// 新增 computed
const visibleActionGroups = computed(() => {
  const matrix = props.matrix?.columns || []
  const byType = { crud: [], batch: [], business: [] }
  for (const a of matrix) {
    const meta = actionMetaMap.value[a]
    const type = (meta && meta.action_type) || 'crud'  // 未声明走 crud 兜底
    if (byType[type]) byType[type].push(a)
  }
  return [
    { type: 'crud', label: 'CRUD', actions: byType.crud,
      hint: '对象级 CRUD 动作：对该资源类型的所有实例生效。配数据范围后 = 仅范围内实例可操作。' },
    { type: 'batch', label: '批量', actions: byType.batch,
      hint: '批量动作（导出/导入）：通常面向实例集合，建议同时配数据范围。' },
    { type: 'business', label: '业务', actions: byType.business,
      hint: '业务动作（分配/授权/审批）：与业务流程相关，与数据范围正交。' },
  ].filter(g => g.actions.length > 0)
})

const actionMetaMap = ref({})
watch(() => props.actionMeta, (meta) => {
  actionMetaMap.value = meta || {}
}, { immediate: true })
```

3. **新增 prop**：`actionMeta: { type: Object, default: () => ({}) }`
   - 由父组件 `PermissionConfigPanel.vue` 透传后端 /meta 下发的 `action_meta` 字段

4. **模板改动**（替换原 v-for `visibleColumns` 块）：

```vue
<!-- 动作列：按 action_type 分组 + 对象级标识 -->
<template v-for="group in visibleActionGroups" :key="group.type">
  <el-table-column
    v-if="group.actions.length > 0"
    :label="group.label"
    align="center"
  >
    <template #header>
      <div class="ram-col-header-group">
        <span class="ram-scope-icon">🔑</span>
        <span>{{ group.label }}</span>
        <el-tooltip :content="group.hint" placement="top" :teleported="true">
          <AppIcon name="info" :size="11" class="ram-col-header-info" />
        </el-tooltip>
      </div>
      <div class="ram-col-header-sub">对象级权限（对该资源类型所有实例）</div>
    </template>
    <template #default="{ row }">
      <!-- 单一动作列渲染（原 cell 渲染逻辑移到此处） -->
      <div v-for="action in group.actions" :key="action" class="ram-cell-group-cell">
        ...
      </div>
    </template>
  </el-table-column>
</template>
```

#### 3.1.4 兼容性 / 兼容性回归点

| 影响点 | 处理 |
|---|---|
| `actionFilter`（动作筛选下拉，原 line 67-80） | 同步改造：下拉分组（CRUD / 批量 / 业务），多选 + 类型分组 el-option-group |
| `extraActionsOf`（行内更多动作 popover，原 line 995） | **不变** — popover 仍展示"主矩阵列之外"的差异化动作 |
| `toggleColumn / isColumnAllGranted / isColumnIndeterminate`（原 line 1112-1133） | **保留为全集函数**，遍历 `props.matrix.columns`（不变），仅 UI 渲染分块 |
| `rowActions`（原 line 1001） | **不变** — 仍返回 `[...cols, ...extraActions]`，保存链路零影响 |

#### 3.1.5 CSS 新增

```css
.ram-col-header-group {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.ram-col-header-sub {
  font-size: 10px;
  font-weight: 400;
  color: var(--color-text-tertiary);
  margin-top: 2px;
}
.ram-scope-icon { font-size: 11px; }
.ram-col-header-info { color: var(--color-text-tertiary); cursor: help; }
.ram-col-header-info:hover { color: var(--color-brand); }
.ram-cell-group-cell {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0 4px;
}
```

### 3.2 FR-002 敏感动作未配范围警示

#### 3.2.1 规则定义

```javascript
// 新增常量（ResourceActionMatrix.vue 顶部）
const SENSITIVE_ACTIONS = new Set([
  'delete', 'export', 'import', 'revoke', 'dissociate'
])

// 新增 computed
function isSensitiveScopeGap(row) {
  if (props.readonly) return false  // 浏览态不警示
  if (rowScopeMode(row) === 'configured') return false
  return SENSITIVE_ACTIONS.has(...) // 至少一个敏感动作已勾选
}

function sensitiveScopeGapReason(row) {
  const granted = ['delete', 'export', 'import', 'revoke', 'dissociate']
    .filter(a => isSupported(row.resource_type, a) && cellOf(row, a).granted)
  return `已对该资源类型开放 ${granted.map(actionLabel).join('、')}权，\n` +
         `但「数据范围」未配置 → 当前默认 = 全实例。\n` +
         `建议：点击「配置条件」限定实例集合。`
}
```

#### 3.2.2 模板改动 — 资源列 cell 注入警示条

```vue
<!-- 在原 resource-cell 顶部 -->
<div v-if="isSensitiveScopeGap(row)" class="ram-sensitive-warn" data-test="ram-sensitive-warn">
  <el-tooltip :content="sensitiveScopeGapReason(row)" placement="top" :teleported="true">
    <span class="ram-sensitive-warn-icon">
      <AppIcon name="warning" :size="11" />
    </span>
  </el-tooltip>
</div>
```

#### 3.2.3 CSS

```css
.ram-sensitive-warn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 2px;
}
.ram-sensitive-warn-icon {
  display: inline-flex;
  padding: 1px 4px;
  background: var(--color-warning-bg, #fdf6ec);
  color: var(--color-warning, #e6a23c);
  border-radius: 3px;
  font-size: 10px;
}
```

#### 3.2.4 测试断言

| 场景 | 断言 |
|---|---|
| 勾 delete + 无数据范围 | `[data-test=ram-sensitive-warn]` 存在 |
| 配数据范围 | `[data-test=ram-sensitive-warn]` 不存在 |
| 取消勾 delete | `[data-test=ram-sensitive-warn]` 不存在 |
| hover 警示 | tooltip 含「delete」字样 |
| 浏览态 | `[data-test=ram-sensitive-warn]` 不存在 |

### 3.3 FR-003 action_type 驱动分块渲染

#### 3.3.1 后端契约扩展 — /meta 增 `action_meta` 字段

**文件**：`meta/api/permission_dimension_api.py`（1553 行附近）

**插入位置**：在 `action_labels = dict(_ACTION_LABELS)` 之后，下发前。

```python
# [Spec 21 FR-003] action_meta = {action_id: {action_type, name, label}}
# 来源: StandardActionLoader 加载的 _standard_actions.yaml
# 作用: 前端按 action_type 把矩阵列分块渲染（CRUD / 批量 / 业务）
action_meta: Dict[str, Dict[str, Any]] = {}
try:
    from meta.core.standard_action_loader import StandardActionLoader
    for ma in StandardActionLoader.get_actions():
        # yaml id 是 'crud_create', 'export', 'import'... 前端用的是后缀
        # 矩阵 action = StandardActionLoader id 去掉 'crud_' 前缀
        suffix = ma.id.replace('crud_', '')
        action_meta[suffix] = {
            'action_type': ma.action_type.value if hasattr(ma.action_type, 'value') else str(ma.action_type),
            'name': ma.name,
            'yaml_id': ma.id,
        }
except Exception as e:
    logger.warning(f"[Spec 21 FR-003] action_meta 加载失败: {e}")
```

**接口契约变更**：

```jsonc
// GET /api/v2/bo/permission_dimension/meta 返回 data 增字段：
{
  "data": {
    ...,
    "action_labels": { "create": "创建", "read": "查看", ... },
    "action_meta": {                                       // ← 新增
      "create":   { "action_type": "crud",     "name": "创建", "yaml_id": "crud_create" },
      "read":     { "action_type": "crud",     "name": "查看", "yaml_id": "crud_read" },
      "export":   { "action_type": "batch",    "name": "导出", "yaml_id": "export" },
      "import":   { "action_type": "batch",    "name": "导入", "yaml_id": "import" },
      "approve":  { "action_type": "business", "name": "审批", "yaml_id": "approve" },
      "associate":{ "action_type": "business", "name": "关联", "yaml_id": "associate" },
      ...
    },
    ...
  }
}
```

**兼容性**：
- 前端 `actionMeta` prop 缺省 `{}` → 全走 crud 兜底 → 旧 UI 无变化
- StandardActionLoader 失败 → action_meta 空 → 同上兜底

#### 3.3.2 前端消费 — 已在 FR-001 实现

`visibleActionGroups` 按 `action_meta.action_type` 分组。

### 3.4 FR-004 「未配置数据范围 = 全实例」显式声明

#### 3.4.1 实现位置 — 矩阵筛选栏新增 chip

```vue
<el-checkbox v-model="showUnscopedRisk" class="ram-show-unscoped-risk">
  仅显示未配置数据范围
</el-checkbox>
```

#### 3.4.2 行为

```javascript
const showUnscopedRisk = ref(false)

const filteredRows = computed(() => {
  let list = rows.value
  // ... 既有 resourceFilters / onlyAssigned 过滤 ...
  if (showUnscopedRisk.value) {
    list = list.filter(r => rowScopeMode(r) !== 'configured')
  }
  return list
})
```

#### 3.4.3 视觉强化

未配置范围的行 `资源列` 前加 🟡 标识 + tooltip：

```vue
<div v-if="!props.readonly && rowScopeMode(row) !== 'configured' && !hasAnyActionGranted(row)"
     class="ram-unscoped-warn" data-test="ram-unscoped-warn">
  <el-tooltip
    content="该资源类型未配置数据范围，勾选动作后默认对所有实例生效。"
    placement="top" :teleported="true">
    <AppIcon name="alert-circle" :size="11" />
  </el-tooltip>
</div>
```

**注**：`hasAnyActionGranted(row)` 判定"已勾选动作但未配范围" — 比 FR-002 更宽泛，不限定敏感动作。两种警示并存但不冲突：
- 🟡 `ram-unscoped-warn`：未配置范围（条件性 + 全动作适用）
- ⚠️ `ram-sensitive-warn`：未配置范围 + 已勾敏感动作（条件更窄 + 警示更深）

### 3.5 FR-005 OWD 现状栏（只读）

#### 3.5.1 后端契约扩展 — /meta 增 `object_owd` 字段

**插入位置**：`meta/api/permission_dimension_api.py` 在 `dimensions` 相关字段下发之后、菜单矩阵之前。

```python
# [Spec 21 FR-005] object_owd = [{bo_id, default_visibility, default_permission_level, description}]
# 来源: object_owd 表（已有数据，迁移脚本创建）
# 作用: 前端 OWD 只读展示卡（当前不做编辑入口，仅显示当前组织级基线）
object_owd: List[Dict[str, Any]] = []
try:
    if _data_source is not None:
        cursor = _data_source.execute(
            "SELECT bo_id, default_visibility, default_permission_level, description "
            "FROM object_owd ORDER BY bo_id"
        )
        for row in cursor.fetchall() or []:
            object_owd.append({
                'bo_id': row[0] if isinstance(row, tuple) else row['bo_id'],
                'default_visibility': row[1] if isinstance(row, tuple) else row['default_visibility'],
                'default_permission_level': row[2] if isinstance(row, tuple) else row['default_permission_level'],
                'description': row[3] if isinstance(row, tuple) else row['description'],
            })
except Exception as e:
    logger.warning(f"[Spec 21 FR-005] object_owd 加载失败: {e}")
```

**接口契约变更**：

```jsonc
{
  "data": {
    ...,
    "object_owd": [                                        // ← 新增
      { "bo_id": "product", "default_visibility": "private", "default_permission_level": "none",
        "description": "Default OWD for product" },
      ...
    ],
    ...
  }
}
```

#### 3.5.2 前端组件 — 新建 `ObjectOwdPanel.vue`

**新文件**：`src/views/SystemManagement/components/ObjectOwdPanel.vue`

```vue
<template>
  <AppCard
    title="对象级基线（OWD）"
    subtitle="每个对象类型的默认可见性（仅全局管理员可改）"
  >
    <el-table :data="props.owdList" size="small" :empty-text="emptyText" stripe>
      <el-table-column prop="bo_id" label="对象类型" width="140" />
      <el-table-column prop="default_visibility" label="默认可见性" width="160">
        <template #default="{ row }">
          <el-tag :type="visibilityTagType(row.default_visibility)" size="small">
            {{ visibilityLabel(row.default_visibility) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="default_permission_level" label="默认权限级别" width="140">
        <template #default="{ row }">
          {{ permissionLevelLabel(row.default_permission_level) }}
        </template>
      </el-table-column>
      <el-table-column prop="description" label="说明" />
    </el-table>
    <div v-if="props.owdList && props.owdList.length === 0" class="owd-empty">
      未配置 OWD（系统将按 Private + none 兜底）
    </div>
  </AppCard>
</template>

<script setup>
import AppCard from '@/components/common/AppCard/AppCard.vue'

const props = defineProps({
  owdList: { type: Array, default: () => [] }
})

const VISIBILITY_MAP = {
  'private':               { label: '仅 owner 可见',  type: 'info' },
  'public_read':           { label: '公开读',          type: 'success' },
  'public_read_write':     { label: '公开读写',        type: 'warning' },
  'controlled_by_parent':  { label: 'Controlled by Parent', type: '' },
}
const LEVEL_MAP = {
  'none':  'none（无默认授权）',
  'read':  'read（默认可读）',
  'write': 'write（默认可写）',
  'admin': 'admin（默认可管理）',
}
function visibilityLabel(v) { return VISIBILITY_MAP[v]?.label || v }
function visibilityTagType(v) { return VISIBILITY_MAP[v]?.type || '' }
function permissionLevelLabel(l) { return LEVEL_MAP[l] || l }

const emptyText = computed(() => '未配置 OWD')
</script>
```

#### 3.5.3 父组件 `PermissionConfigPanel.vue` 接入

```vue
<!-- 在 <ResourceActionMatrix> 上方插入 -->
<ObjectOwdPanel
  v-if="objectOwdList && objectOwdList.length > 0"
  :owd-list="objectOwdList"
  class="owd-panel"
/>
```

**数据流**：`usePermissionMeta()` composable 加载 /meta 时，从 `data.object_owd` 取值，存到 `objectOwdList` ref，透传给 OWD 卡。

**注意**：OWD 卡**不放在 ResourceActionMatrix 内**，避免与编辑态权限配置混淆。位置：`PermissionConfigPanel` 顶层，紧贴矩阵上方。

### 3.6 FR-006 action hover tooltip

在原 cell tooltip 上加一句话补充：

```vue
<el-tooltip
  :content="(cellOf(row, action).granted ? '已勾选 = 对该资源类型所有实例生效' : '未勾选 = 无此权限') +
            (SENSITIVE_ACTIONS.has(action) ? '\n[敏感动作] 建议同时配置数据范围' : '')"
  placement="top" :teleported="true">
  ...
</el-tooltip>
```

### 3.7 FR-007 矩阵分组记忆（localStorage）

```javascript
const STORAGE_KEY = 'ram-group-collapsed-v1'
const collapsedGroups = ref({ crud: false, batch: false, business: false })

// mount 时读取
onMounted(() => {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
    Object.assign(collapsedGroups.value, saved)
  } catch { /* ignore */ }
})

// watch 写入
watch(collapsedGroups, (v) => {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(v)) } catch { /* ignore */ }
}, { deep: true })
```

**注意**：localStorage 损坏（解析失败）→ 兜底默认全展开；不要抛错。

## 4. 验收清单

### 4.1 FR-001 列头语义标识

- [ ] 「数据范围」列头出现「📍 实例级」+ 「数据范围」副标签
- [ ] 动作列头出现「🔑 对象级」+ 「对象级权限（对该资源类型所有实例）」副标签
- [ ] 动作列按 crud/batch/business 三组分块（当 action_meta 含对应动作时）
- [ ] yaml 未声明 action 走 crud 组兜底，不报错

### 4.2 FR-002 敏感动作未配范围警示

- [ ] 勾 delete + 无数据范围 → 行左侧出现 ⚠️ 警示
- [ ] 配数据范围 → 警示消失
- [ ] 取消勾选 delete → 警示消失
- [ ] hover 警示 → tooltip 显示已开放的敏感动作清单
- [ ] 浏览态（readonly）不警示

### 4.3 FR-003 action_type 驱动分块渲染

- [ ] /meta 返回 `action_meta` 字段，16 个 action 全覆盖
- [ ] 前端按 `action_type` 分组渲染列
- [ ] 三组列对应三个表头分组标签（CRUD / 批量 / 业务）
- [ ] 后端 yaml id 与前端 action suffix 映射正确（`crud_create` → `create`）

### 4.4 FR-004 「未配置数据范围 = 全实例」显式声明

- [ ] 筛选栏新增「仅显示未配置数据范围」checkbox
- [ ] 勾选 → 仅显示无数据范围的行
- [ ] 未配置范围 + 已勾动作 → 行资源列加 🟡 `ram-unscoped-warn`

### 4.5 FR-005 OWD 现状栏

- [ ] /meta 返回 `object_owd` 字段
- [ ] 权限配置页顶部出现 OWD 只读卡片
- [ ] 内容 = `bo_id / default_visibility / default_permission_level / description`
- [ ] **不可编辑**（无编辑按钮、无 row-click）
- [ ] visibility 用 el-tag 着色：private=info / public_read=success / public_read_write=warning

### 4.6 FR-006 action hover tooltip

- [ ] 勾选状态在 tooltip 中明确：「已勾选 = 对所有实例生效」
- [ ] 敏感动作追加「[敏感动作] 建议同时配置数据范围」

### 4.7 FR-007 分组记忆

- [ ] 折叠/展开状态写入 localStorage（key=`ram-group-collapsed-v1`）
- [ ] 刷新页面后保持
- [ ] localStorage 损坏（解析失败）→ 兜底默认全展开，不报错

## 5. 实施计划

### 5.1 任务拆分

| 票号 | 标题 | 类型 | 工作量 | 文件 |
|---|---|---|---|---|
| T-21-01 | 后端 /meta 增 `action_meta` 字段 | 后端 | 0.5d | `meta/api/permission_dimension_api.py` |
| T-21-02 | 后端 /meta 增 `object_owd` 字段 | 后端 | 0.5d | `meta/api/permission_dimension_api.py` |
| T-21-03 | 新建 `ObjectOwdPanel.vue` | 前端 | 0.5d | `src/views/SystemManagement/components/ObjectOwdPanel.vue` |
| T-21-04 | `PermissionConfigPanel.vue` 接入 OWD 卡 + 透传 action_meta | 前端 | 0.5d | `src/views/SystemManagement/components/PermissionConfigPanel.vue` |
| T-21-05 | `ResourceActionMatrix.vue` 列头分组 + action_type 分块 | 前端 | 1d | `src/views/SystemManagement/components/ResourceActionMatrix.vue` |
| T-21-06 | `ResourceActionMatrix.vue` 敏感动作警示 + 「未配置范围」筛选 | 前端 | 0.5d | 同上 |
| T-21-07 | 矩阵分组折叠 + localStorage 记忆 | 前端 | 0.5d | 同上 |
| T-21-08 | E2E：列头 / 警示 / 筛选 / OWD 卡 | 测试 | 1d | `tests/e2e/` |

### 5.2 依赖与风险

- **T-21-01**：依赖 `StandardActionLoader.get_actions()` — 已有，零风险（[standard_action_loader.py:58](../../meta/core/standard_action_loader.py#L58)）
- **T-21-02**：依赖 `object_owd` 表已迁移 — 已有，零风险（[migration script](../../meta/migrations/add_object_owd_2026.py)）
- **T-21-05**：列头重构改动面较大，需回归现有 e2e（25+ 用例覆盖 cell 勾选、批量操作、来源标签、差异化动作）
- **T-21-08**：需新增 4-5 个 e2e 用例

### 5.3 上线策略（三 PR 渐进）

| Phase | 范围 | 风险 | 可单独回滚 |
|---|---|---|---|
| **Phase 1** | T-21-01 + T-21-02 + T-21-03 + T-21-04 — OWD 卡片先行 | 低：新组件 + 透传字段 | 是 |
| **Phase 2** | T-21-05 + T-21-07 — 矩阵列头分组 + 折叠记忆 | 中：视觉改造 | 是 |
| **Phase 3** | T-21-06 + T-21-08 — 敏感警示 + 筛选 + 测试 | 低：纯前端 | 是 |

### 5.4 回滚

- Phase 1：OWD 卡为新组件，回滚成本 0
- Phase 2：保留旧 `visibleColumns` computed 作为 fallback，UI 切回无分组模式
- Phase 3：警示渲染加 `v-if="false"` 兜底即可关闭

## 6. TBD（未来 spec 议题）

| 编号 | 议题 | 备注 |
|---|---|---|
| TBD-1 | **OWD 配置页** | 当前 spec 仅展示 OWD，配置入口是 [Spec15 §5.1.7](./15_permission_config_unification.md#51-组件级动作细化合规-yondesign--封装组件规范) 规划项，待单独立 spec |
| TBD-2 | **横切面 Condition** | 时间 / IP / MFA 等条件表达式扩展（业界 AWS / Snowflake 都有） |
| TBD-3 | **`permission_level` 三档下放** | 把 `admin/write/read` 暴露到矩阵 cell 下拉（与 data_permissions 字段重名问题需先解决） |

## 7. 关联阅读

- [Spec15 §2.2 数据权限单一"范围 + 例外"二分](./15_permission_config_unification.md#22-数据权限单一范围--例外二分)
- [Spec 19 FR-002 受托范围](./19_org_admin_delegation.md#fr-002-org--user-行的数据范围语义)
- [Spec 20 业务键锚定](./20_dimension_scope_business_key.md)
- [Spec 09 §3 三元组 Statement = Action + Resource + Condition](./09_unified_permission_architecture.md)
- [`_standard_actions.yaml`](../../meta/schemas/_standard_actions.yaml)
- [`object_owd` 迁移](../../meta/migrations/add_object_owd_2026.py)
- [`PermissionInterceptor`](../../meta/core/interceptors/permission_interceptor.py)
- [`DataPermissionInterceptor`](../../meta/core/interceptors/data_permission_interceptor.py)
- [`StandardActionLoader`](../../meta/core/standard_action_loader.py)
- [`MetaAction` / `ActionType`](../../meta/core/models.py#L557-L573)

***

**修订记录**

| 日期 | 修订人 | 内容 |
|---|---|---|
| 2026-09-12 | PM | v1 创建，对应会话「action 是否需要区分对象级 / 实例级」研究结论 |

***

## 附录 A：本次「动作对象级 / 实例级」研究 v0.1 沉淀（横向对比）

### A.1 七家头部产品对比

| 产品 | 动作粒度 | 实例范围表达 | 对象基线（OWD 等价物） | 异常/放宽机制 | 与本项目最像的概念 |
|---|---|---|---|---|---|
| **SAP PFCG** | ACTVT（01-06） | Authorization Field 值（含 `*`） | 无（顶层由主数据派生） | Field 值列表增删 | "角色 × 动作 × 字段值集合" 与我们的矩阵+条件最像 |
| **AWS IAM** | API verb（千级） | Resource ARN（含 `*`） | 无 | Condition 表达式（与资源正交） | "Statement = Action + Resource + Condition" 三元组 |
| **Salesforce** | 7 个 CRUD + View All/Modify All | Role Hierarchy（继承）+ Record Owner | **OWD（每个对象一个默认基线）** | Sharing Rule（owner/条件扩展） | **OWD = 我们已建表缺 UI；Sharing Rule = data_permissions** |
| **Azure RBAC** | Actions / DataActions（千级） | AssignableScopes（订阅/资源组） | 无（subscription 是天然范围） | NotActions / NotDataActions（对象级例外） | 三元组 Actions/NotActions/Scopes |
| **Snowflake** | 6 个 SQL verb | Database/Schema/Table 路径 | 无 | Row Access Policy / Masking Policy | 我们"条件规则"的最像物 |
| **Databricks** | 同 Snowflake | 同 Snowflake | 无 | Dynamic View + Column Mask | 同 Snowflake |
| **Notion/Airtable/Linear** | 能力集（5 档） | page/workspace 树 | 角色预设（5-10 档） | page-level 共享覆盖 | 我们的「角色预设」未来可参考 |

### A.2 五条深度洞察

1. **"对象级 vs 实例级"是个伪命题** — SAP / AWS 不区分这两层，因为它们的"对象级授权"实际上是 `Resource = *`（包含所有实例），与实例范围是同一个语义的两种取值。
2. **OWD 是"对象级第三层"** — 我们已建表 `object_owd`，但 UI 入口缺失（spec 15 已规划，本次 spec 21 补上"展示"+"待 P3 配置"）。
3. **"action 是否要区分 object/instance"是个错位提问** — 正确提问是："我们是否要在 UI 上让用户理解 action 是对象级、范围是实例级？"
4. **`action_type` 字段是更精准的分类轴** — 已有但闲置，可以分块渲染（crud / batch / business 三组）。
5. **条件表达式是业界共识** — AWS Condition / Snowflake Row Access Policy / Databricks Dynamic View — 都是条件表达式驱动的实例级范围。**这是我们的 dimension_object_mapping + permission_rules + data_permissions 三件套的本质**。
