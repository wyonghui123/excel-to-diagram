# SPEC: 层级值帮助对话框 (Hierarchical Value Help)

> 日期: 2026-07-22
> 状态: Draft → 待用户审阅
> 触发问题: 角色详情页 → 权限配置 tab → 管理维度 → 子领域多选弹窗中，"所属路径"列是扁平字符串，162 行压平，用户多选困难，看不到层级结构
> 解决方案: 借鉴 SAP Fiori Elements Hierarchical F4 Help + Element Plus `el-tree` + 复用现有 `ObjectScopeSection` 的交互模式

---

## TL;DR

| 项目 | 内容 |
|------|------|
| **核心** | SearchHelpDialog 新增 `display_mode: "tree"` 模式，复用弹窗骨架，主体改为 `el-tree` |
| **复用** | 新组件 `HierarchicalTreePicker.vue` 独立存在，**不改 `ObjectScopeSection.vue`** |
| **数据源** | 新增后端 `GET /api/v2/bo/management_dimension/<dim>/tree` 端点 |
| **元数据** | 6 个 dimension BO YAML 顶层加 `hierarchies: [...]` 声明层级结构 |
| **模式** | 支持**单选 / 多选**两种模式（prop `multiple` 控制） |
| **首批范围** | product / version / domain / sub_domain（4 个层级，sub_domain 是叶子） |
| **不影响** | 现有 flat 模式、`ObjectScopeSection`、其他 BO 的值帮助 |

---

## 一、问题描述

### 1.1 用户场景

```
1. 角色管理 → 角色"采购管理领域编辑" (PUMEDIT, id=12009) → 详情页
2. 权限配置 tab → 管理维度范围 → "子领域"组 → 点 "+ 添加子领域"
3. 弹出 SearchHelpDialog
4. 看到 162 行平铺表格，"所属路径"列全是 "产品A > 版本1.0 > 采购域 > ..."
5. 用户要选 5 个相关子领域 → 肉眼+搜索，找不到父子关系
6. 选 "采购域" 下所有子领域 → 逐个勾选，无法批量
```

### 1.2 现有 flat 模式痛点

| 痛点 | 影响 |
|------|------|
| **162 行压平** | 视觉噪音大，决策慢 |
| **路径列字符串** | "产品A > 版本1.0 > 采购域 > 子领域-询价单" 跨多列宽，可读性差 |
| **看不到层级关系** | "采购域-子领域X" 和 "销售域-子领域X" 视觉上无区分 |
| **不能批量选父节点** | 选某父节点下所有子领域要逐个勾 |
| **搜索只对当前页生效** | 不展开父链 |
| **无法回选** | 多选 chips 没有移除入口，只能在树中再次取消勾选 |

### 1.3 行业标杆

| 厂商/库 | 关键借鉴 |
|---------|---------|
| **SAP Fiori Elements** | Hierarchical F4 Help：树形 F4 + 命中节点父链展开 + 高亮 |
| **Element Plus** | `el-tree` + `el-tree-select` + 搜索过滤 |
| **Ant Design** | `TreeSelect` + `showCheckedStrategy` 多选回填策略 |

---

## 二、目标 & 非目标

### 2.1 目标

1. 在弹窗内显示层级树形结构，父节点可展开/折叠
2. 支持单选（点 node 即选中）和多选（checkbox 联动）两种模式
3. 搜索命中节点自动展开父链 + 高亮
4. 多选模式有 chips 区，每个 chip 可单独移除
5. 复用现有 `ObjectScopeSection` 的交互模式（工具栏、图标、count 标注）
6. 通过元数据声明驱动，**不破坏现有 flat 模式**

### 2.2 非目标 (YAGNI)

1. 不支持 drag-and-drop 节点排序（不在值帮助场景里需要）
2. 不支持节点编辑（只读选择）
3. 不支持虚拟滚动（首批 4 层数据量 < 1000，无需）
4. 不支持跨维度混合选择（每个 ValueHelp 只针对一个 BO）
5. 不重写 `ObjectScopeSection`（用户决策：独立新组件，不改旧）
6. 不支持权限维度的过滤（不在值帮助范围，由上游 scope 控制）

---

## 三、架构

### 3.1 新增文件清单

```
src/components/common/HierarchicalTreePicker/
├── HierarchicalTreePicker.vue          # 主组件
├── HierarchicalTreePicker.spec.js      # 单元测试
└── index.js                            # 导出

meta/api/
└── management_dimension_api.py         # +新增 tree 路由 (在 _query_child_ids 后面)

meta/core/
├── yaml_loader.py                      # +读 hierarchies 字段
└── models_meta.py                      # +MetaObject.hierarchies 字段 (如已存在则不重复)

meta/schemas/
├── product.yaml                        # +hierarchies
├── version.yaml                        # +hierarchies
├── domain.yaml                         # +hierarchies
└── sub_domain.yaml                     # +hierarchies
```

### 3.2 数据流

```
┌──────────────────────────────────────────────────────────────┐
│  ValueHelpField (dialog mode, display_mode=tree)             │
│  ↓ 点击输入框                                                │
│  SearchHelpDialog (display_mode=tree 分支)                   │
│  ↓ 渲染主体                                                  │
│  HierarchicalTreePicker                                      │
│  ├─ onMounted → GET /tree 端点 → 树数据                     │
│  ├─ search → GET /tree?search=... → 命中节点+父链            │
│  └─ @confirm → emit({type, id|ids, node|nodes})             │
│  ↓                                                          │
│  SearchHelpDialog @confirm → 转发到 ValueHelpField            │
│  ↓ emit('update:modelValue', id|ids)                       │
│  表单字段更新                                                │
└──────────────────────────────────────────────────────────────┘
```

### 3.3 复用层级

| 复用物 | 来源 | 用法 |
|--------|------|------|
| `el-dialog` 弹窗骨架 | `SearchHelpDialog.vue` | 复用，新增 `<HierarchicalTreePicker v-else-if="useTreeMode" />` 分支 |
| `el-tree` 树形控件 | Element Plus | 直接用，配置按单/多选模式不同 |
| 节点 icon 映射 | 新建独立常量 `iconMap.js` (`src/components/common/HierarchicalTreePicker/iconMap.js`) | 提到独立文件，避免从 `ObjectScopeSection` 内部复制；后续两边可共用 |
| 节点 count 字段 | 后端 `child_count` 计算字段 | 已存在于 `service_module`，其他 3 个 dimension 加 `computation` 声明 |
| 元数据 `hierarchies` | BO YAML | 单一事实源 |

**明确不复用**：`ObjectScopeSection.vue` 内部 logic（避免改旧组件风险）。icon 映射提到独立常量文件供两侧共享（ObjectScopeSection 后续可选择迁移到共享文件，本期不动）。

---

## 四、详细设计

### 4.1 后端：`/tree` 端点

#### URL & 路由

```python
@management_dimension_bp.route("/<dim>/tree", methods=["GET"])
@jwt_required
def list_dimension_tree(dim: str):
    """返回 dim 维度的层级树 (扁平数组, 每节点带 parent_id)"""
```

#### Query 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `search` | str | 否 | 模糊匹配 name/code，命中节点 + 完整父链 |
| `version_id` | int | 否 | 仅当 dim ∈ {version, domain, sub_domain} 时有意义，限制 root 范围 |
| `max_depth` | int | 否 | 默认从 hierarchyConfig[0].levels 读，单维可截断 |

#### 返回数据

```json
{
  "data": [
    {
      "id": 1,
      "parent_id": null,
      "level": 0,
      "type": "product",
      "name": "产品A",
      "code": "PRD_A",
      "has_children": true,
      "child_count": 12
    },
    {
      "id": 5,
      "parent_id": 1,
      "level": 1,
      "type": "version",
      "name": "版本1.0",
      "code": "V1.0",
      "has_children": true,
      "child_count": 8
    },
    {
      "id": 339,
      "parent_id": 5,
      "level": 2,
      "type": "sub_domain",
      "name": "询价单子领域",
      "code": "INQ",
      "has_children": false,
      "child_count": 0
    }
  ],
  "total": 162
}
```

#### 内部实现（伪代码）

```python
def list_dimension_tree(dim):
    hierarchy = get_hierarchy_for_dim(dim)  # 从 yaml_loader 读 hierarchies[0]
    levels = hierarchy.levels  # [{object_type, parent_field}, ...]
    
    # 收集所有层级的节点 (扁平查询)
    all_nodes = []
    for level_cfg in levels:
        rows = query_layer(level_cfg.object_type, version_id)  # 单 SQL
        for row in rows:
            all_nodes.append({
                "id": row.id,
                "parent_id": row[level_cfg.parent_field] if level_cfg.parent_field else None,
                "level": level_index,
                "type": level_cfg.object_type,
                "name": row.name,
                "code": row.code,
                "has_children": level_index < len(levels) - 1,
                "child_count": row.child_count or 0,
            })
    
    # search 过滤: 命中节点 + 父链
    if search:
        all_nodes = filter_with_parent_chain(all_nodes, search)
    
    return {"data": all_nodes, "total": len(all_nodes)}
```

**性能**：
- 不带 search：4 层各 1 次 SQL（4 次查询，已优化）
- 带 search：先按 name/code 过滤叶子，再向上回溯到 root
- 数据量预期：4 层共 < 1000 节点，内存构建树足够

#### 安全

- `@jwt_required` 鉴权（继承现有装饰器）
- `apply_target_permissions` 仍生效（已有权限过滤逻辑）
- 子查询参数化（避免 SQL 注入）

### 4.2 元数据：BO YAML `hierarchies` 字段

#### product.yaml

```yaml
hierarchies:
  - root_type: product
    levels:
      - object_type: product
        parent_field: null
        children_field: versions
        icon: Box
      - object_type: version
        parent_field: product_id
        children_field: domains
        icon: Folder
      - object_type: domain
        parent_field: version_id
        children_field: sub_domains
        icon: FolderOpened
      - object_type: sub_domain
        parent_field: domain_id
        children_field: null  # 叶子节点
        icon: Document
```

#### 字段语义

| 字段 | 必填 | 说明 |
|------|------|------|
| `root_type` | 是 | 树根节点类型（当 dim == root_type 时返回所有根） |
| `levels[].object_type` | 是 | 该层节点类型名 |
| `levels[].parent_field` | 是 | DB 列名，指向父级 `id`；root 层为 `null` |
| `levels[].children_field` | 是 | 仅供前端展示，子节点键名；叶子层为 `null` |
| `levels[].icon` | 否 | Element Plus icon 组件名，前端按名字查 `iconComponentMap` |

#### yaml_loader 扩展

`yaml_loader.py` 已能读取 `meta` 顶层字段。验证 `hierarchies` 是否已支持：

```bash
grep -n "hierarchies" meta/core/yaml_loader.py
```

如未支持，新增：
```python
if 'hierarchies' in doc:
    meta_obj.hierarchies = doc['hierarchies']
```

### 4.3 前端：`HierarchicalTreePicker.vue`

#### Props

```ts
interface Props {
  /** 维度 ID（必填），如 'sub_domain' */
  dimensionId: { type: String, required: true },

  /** hierarchyConfig 从 BO YAML hierarchies[0] 传入 */
  hierarchyConfig: {
    type: Object as PropType<HierarchyConfig>,
    required: true
  },

  /** 已有选中（编辑态回填）：
   *  - 多选模式：number[] (id 数组)
   *  - 单选模式：number | null
   */
  checkedIds: { type: [Array, Number] as PropType<number[] | number | null>, default: () => [] },

  /** 单选/多选，默认多选 */
  multiple: { type: Boolean, default: true },

  /** 节点右侧显示 child_count 标注 */
  showCount: { type: Boolean, default: true },

  /** 顶栏搜索框 */
  showSearch: { type: Boolean, default: true },

  /** 显示工具栏（展开/全选/清空/刷新） */
  showToolbar: { type: Boolean, default: true },

  /** 父级 dim 筛选（如 dim=domain 时 version_id=5） */
  filterParams: { type: Object, default: () => ({}) },
}
```

#### Emits

```ts
interface Emits {
  /** 用户点"确定"，带最终选中结果 */
  (e: 'confirm', payload: SinglePayload | MultiplePayload): void

  /** 用户点"取消"或 close dialog */
  (e: 'cancel'): void

  /** 实时变化（用于上层 form 同步预览） */
  (e: 'check-change', payload: { ids: number[]; nodes: any[] }): void
}

type SinglePayload = {
  type: 'single'
  id: number
  node: { id: number; name: string; type: string; ancestorPath?: string; [k: string]: any }
}

type MultiplePayload = {
  type: 'multiple'
  ids: number[]
  nodes: Array<{ id: number; name: string; type: string; ancestorPath?: string; [k: string]: any }>
}
```

#### 内部状态

```ts
const treeData = shallowRef<TreeNode[]>([])
const loading = ref(false)
const searchQuery = ref('')
const debouncedSearch = ref('')
const checkedIds = ref<number[]>([])      // 多选
const currentId = ref<number | null>(null) // 单选
const defaultExpandedKeys = shallowRef<string[]>([])
```

#### 模板结构（多选模式）

```vue
<template>
  <div class="htp-root">
    <div v-if="showSearch" class="htp-search">
      <AppInput
        v-model="searchQuery"
        :placeholder="`输入名称或编码搜索（共 ${totalCount} 条）`"
        clearable size="sm"
        @update:model-value="onSearchInput"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </AppInput>
    </div>

    <div v-if="showToolbar && multiple" class="htp-toolbar">
      <AppButton variant="text" size="sm" @click="toggleExpandAll">
        <component :is="allExpanded ? Fold : Expand" />
        {{ allExpanded ? '收起' : '展开' }}
      </AppButton>
      <AppButton variant="text" size="sm" @click="handleSelectAll">全选</AppButton>
      <AppButton variant="text" size="sm" @click="handleClear">清空</AppButton>
      <AppButton variant="text" size="sm" @click="loadTreeData" :disabled="loading">刷新</AppButton>
    </div>

    <div class="htp-tree-container">
      <div v-if="loading" class="htp-loading">加载中...</div>
      <el-tree
        v-else
        ref="treeRef"
        :data="treeData"
        :props="treeProps"
        node-key="id"
        :show-checkbox="multiple"
        :check-strictly="false"
        :check-on-click-node="true"
        :highlight-current="true"
        :default-expand-all="false"
        :default-expanded-keys="defaultExpandedKeys"
        :default-checked-keys="multiple ? initialCheckedKeys : undefined"
        :current-node-key="!multiple ? String(currentId) : undefined"
        :expand-on-click-node="false"
        :filter-node-method="filterNodeMethod"
        @check="onCheckMultiple"
        @node-click="onNodeClickSingle"
        @node-expand="onNodeExpand"
      >
        <template #default="{ data }">
          <span class="htp-node">
            <el-icon v-if="getNodeIcon(data)" :size="14">
              <component :is="getNodeIcon(data)" />
            </el-icon>
            <span class="htp-node-label">{{ data.name }}</span>
            <span v-if="showCount && data.child_count > 0" class="htp-node-count">
              ({{ data.child_count }})
            </span>
          </span>
        </template>
      </el-tree>
    </div>

    <!-- 多选：已选 chips 区 -->
    <div v-if="multiple" class="htp-selected-bar">
      <span class="htp-selected-label">已选 ({{ selectedCount }}):</span>
      <div class="htp-chips">
        <el-tag
          v-for="id in checkedIds"
          :key="id"
          closable
          size="small"
          @close="removeChecked(id)"
        >
          {{ getNodeNameById(id) }}
        </el-tag>
        <span v-if="selectedCount === 0" class="htp-chips-empty">无</span>
      </div>
    </div>

    <!-- 底部按钮 -->
    <div class="htp-actions">
      <el-button @click="handleCancel">取消</el-button>
      <el-button v-if="multiple" @click="handleClear" :disabled="selectedCount === 0">清除</el-button>
      <el-button type="primary" @click="handleConfirm" :disabled="!canConfirm">
        确定{{ multiple ? ` (${selectedCount})` : '' }}
      </el-button>
    </div>
  </div>
</template>
```

#### 关键逻辑

**单选/多选开关**：
```ts
const canConfirm = computed(() => {
  if (props.multiple) return checkedIds.value.length > 0
  return currentId.value != null
})

function onCheckMultiple(checkedInfo) {
  // el-tree 4.x: checkedInfo = { checkedKeys, checkedNodes, halfCheckedKeys, halfCheckedNodes }
  const allChecked = [
    ...checkedInfo.checkedKeys,
    ...checkedInfo.halfCheckedKeys
  ].map(k => Number(k))
  checkedIds.value = allChecked
  emit('check-change', { ids: checkedIds.value, nodes: checkedInfo.checkedNodes })
}

function onNodeClickSingle(node) {
  // 单选：再次点同一节点取消
  if (currentId.value === node.id) {
    currentId.value = null
  } else {
    currentId.value = node.id
  }
}
```

**搜索带防抖 + 父链展开**：
```ts
const debouncedSearch = ref('')
let searchTimer
function onSearchInput(val) {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { debouncedSearch.value = val }, 300)
}

watch(debouncedSearch, async (val) => {
  await loadTreeData({ search: val })
  // 自动展开命中节点的父链
  if (val) {
    const matchedIds = treeData.value.filter(n => filterMatch(n, val)).map(n => n.id)
    const expandKeys = collectParentKeys(matchedIds, treeData.value)
    defaultExpandedKeys.value = expandKeys
  }
})

// 前端过滤（同时本地匹配 + 后端命中）
function filterNodeMethod(value, data) {
  if (!value) return true
  return data.name?.toLowerCase().includes(value.toLowerCase())
}

// 命中判断：name/code 任一包含搜索字符串（不区分大小写）
function filterMatch(node, search) {
  const q = search.toLowerCase()
  return node.name?.toLowerCase().includes(q) ||
         node.code?.toLowerCase().includes(q)
}

// 收集所有命中节点 + 它们的祖先节点 keys（用于 el-tree 展开）
function collectParentKeys(matchedIds, allNodes) {
  const byId = new Map(allNodes.map(n => [n.id, n]))
  const result = new Set()
  for (const id of matchedIds) {
    let cur = byId.get(id)
    while (cur) {
      result.add(String(cur.id))
      if (cur.parent_id == null) break
      cur = byId.get(cur.parent_id)
    }
  }
  return [...result]
}
```

**回填编辑态已有选中**：
```ts
const initialCheckedKeys = computed(() => {
  if (!props.checkedIds) return []
  return Array.isArray(props.checkedIds)
    ? props.checkedIds.map(String)
    : [String(props.checkedIds)]
})

onMounted(async () => {
  await loadTreeData()
  if (props.checkedIds) {
    if (props.multiple) {
      await nextTick()
      treeRef.value?.setCheckedKeys(initialCheckedKeys.value, false)
    } else {
      currentId.value = Array.isArray(props.checkedIds) ? props.checkedIds[0] : props.checkedIds
    }
  }
})
```

**生成 ancestorPath（用于 confirm payload 和 chips 显示）**：
```ts
function buildAncestorPath(nodeId) {
  const byId = new Map(treeData.value.map(n => [n.id, n]))
  const parts = []
  let cur = byId.get(nodeId)
  while (cur) {
    parts.unshift(cur.name)
    if (cur.parent_id == null) break
    cur = byId.get(cur.parent_id)
  }
  return parts.join(' > ')
}

// chips 显示优先用 ancestorPath（更直观），回填字段用 name
function getNodeNameById(id) {
  const node = treeData.value.find(n => n.id === id)
  if (!node) return `#${id}`  // 节点不在当前树（跨 version 选了别的）
  return buildAncestorPath(id) || node.name
}
```

### 4.4 SearchHelpDialog 集成

**SearchHelpDialog.vue** 增加分支：

```vue
<template>
  <el-dialog ...>
    <!-- 现有 flat 模式 -->
    <MetaListPage v-if="!useTreeMode" ... />

    <!-- 新增 tree 模式 -->
    <HierarchicalTreePicker
      v-else-if="useTreeMode"
      :dimension-id="sourceTargetBo"
      :hierarchy-config="hierarchyConfig"
      :checked-ids="selectedValue"
      :multiple="isMultiple"
      @confirm="handleTreeConfirm"
      @cancel="handleClose"
    />
  </el-dialog>
</template>

<script setup>
import HierarchicalTreePicker from '@/components/common/HierarchicalTreePicker'

const useTreeMode = computed(() =>
  props.valueHelpConfig?.presentation?.display_mode === 'tree'
)

const sourceTargetBo = computed(() => {
  return props.valueHelpConfig?.source?.target_bo || ''
})

const hierarchyConfig = computed(() => {
  // 从 meta registry 读 hierarchies[0]
  const metaObj = metaRegistry.get(sourceTargetBo.value)
  return metaObj?.hierarchies?.[0] || null
})

function handleTreeConfirm(payload) {
  if (payload.type === 'single') {
    emit('confirm', payload.id)
  } else {
    emit('confirm', payload.ids)
  }
  emit('update:visible', false)
}
</script>
```

### 4.5 DimensionScopePanel 集成

`DimensionScopePanel.pickerFetcher` 当前**只在 `display_mode !== 'tree'` 时被调用**。当 `display_mode === 'tree'`：

- **不走 pickerFetcher**（tree 组件自带数据加载）
- 通过 `valueHelpConfig.presentation.display_mode === 'tree'` 触发 SearchHelpDialog 走新分支

无需修改 `pickerFetcher`，但 `pickerDialogConfig` 应透传 `display_mode`：

```js
const pickerDialogConfig = computed(() => ({
  ...currentPickerConfig.value,
  presentation: {
    ...currentPickerConfig.value.presentation,
    display_mode: 'tree'  // 强制 tree 模式
  }
}))
```

### 4.6 触发开关（YAML 配置）

在 `sub_domain.yaml` 等 4 个 BO 上声明：

```yaml
# sub_domain.yaml
value_help:
  source:
    type: bo
    target_bo: sub_domain
  behavior:
    multiple: true
  presentation:
    result_type: dialog
    display_mode: tree        # 新增：触发 tree 模式
```

`ValueHelpPresentation.display_mode` 字段已存在（默认 `"flat"`），扩展枚举加 `"tree"`。

---

## 五、数据契约

### 5.1 后端响应 schema

```typescript
interface TreeNodeResponse {
  id: number
  parent_id: number | null
  level: number        // 0-based, root=0
  type: string         // 'product' | 'version' | 'domain' | 'sub_domain'
  name: string
  code: string
  has_children: boolean
  child_count: number
}

interface TreeResponse {
  data: TreeNodeResponse[]
  total: number
}
```

### 5.2 组件 → 上层 payload

```typescript
type ConfirmPayload = SinglePayload | MultiplePayload

interface SinglePayload {
  type: 'single'
  id: number
  node: {
    id: number
    name: string
    type: string
    ancestorPath?: string
    [k: string]: any
  }
}

interface MultiplePayload {
  type: 'multiple'
  ids: number[]
  nodes: Array<{
    id: number
    name: string
    type: string
    ancestorPath?: string
    [k: string]: any
  }>
}
```

---

## 六、错误处理

| 错误场景 | 表现 | 处理 |
|---------|------|------|
| 后端 `/tree` 500 | loading 状态结束，弹"暂无数据" | 显示 `<el-empty>`，工具栏刷新按钮可用 |
| 后端 `/tree` 鉴权失败 | 401，跳转登录 | 已有 axios 拦截器处理 |
| `hierarchyConfig` 缺失 | 控制台警告，tree 不渲染 | SearchHelpDialog 弹 warning，禁用确定按钮 |
| 搜索无结果 | 树区显示"无匹配数据" | 同上 |
| 单选模式没选 | "确定"按钮 disabled | — |
| 多选模式全空 | "确定 (0)" disabled，"清除" disabled | — |
| 已选节点不在加载到的树里（如跨 version 选了别的） | 回填时勾不上 | 显示 warning，提示"部分选中项不在当前范围" |
| 数据 > 1000 节点 | 首次加载较慢 | 显示 loading + 提示"数据量较大" |

---

## 七、测试策略

### 7.1 单元测试

`HierarchicalTreePicker.spec.js`：

```js
describe('HierarchicalTreePicker', () => {
  describe('单选模式', () => {
    it('点 node 即选中', ...)
    it('再次点同一 node 取消选中', ...)
    it('confirm 只 emit 单个 id', ...)
    it('无选中时 confirm 按钮禁用', ...)
    it('回填 initialCheckedId 高亮对应节点', ...)
  })

  describe('多选模式', () => {
    it('checkbox 联动父子勾选', ...)
    it('移除 chip 同步取消勾选', ...)
    it('全选/清空 工具栏', ...)
    it('confirm emit ids 数组', ...)
    it('chips 区显示已选节点名', ...)
  })

  describe('搜索', () => {
    it('300ms 防抖', ...)
    it('命中节点父链自动展开', ...)
    it('匹配字符串高亮', ...)
    it('搜索无结果显示 empty', ...)
  })

  describe('数据加载', () => {
    it('onMounted 调 /tree 端点', ...)
    it('带 search 重载', ...)
    it('500 错误显示 empty', ...)
    it('刷新按钮重新加载', ...)
  })
})
```

### 7.2 E2E 测试（PlaywrightCLI）

`test_helpers/verify_tree_picker.py`：

1. 登录 → 角色详情 → 权限配置 → + 添加子领域
2. 断言 dialog 打开，看到树形结构（不是 table）
3. 断言 4 层可见：product > version > domain > sub_domain
4. 点击 sub_domain 叶子节点 → 选中
5. 点击 "确定" → 字段回填
6. 多选模式：勾选 3 个 sub_domain → chips 区显示 3 个
7. 移除一个 chip → tree 中对应勾选取消
8. 搜索 "采购" → 命中节点父链展开
9. 单选 vs 多选切换（同一组件不同 prop）

### 7.3 回归测试

- 现有 flat 模式的所有 E2E（其他使用 flat 的 BO 值帮助）
- `ObjectScopeSection` 现有功能（架构数据管理页）
- 角色详情页 /detail/role/12009 flat 表格

---

## 八、实施路线

| Phase | 内容 | 工作量 | 验证 |
|-------|------|--------|------|
| **Phase 1** | 后端 `/tree` 端点 + 单元测试 | 1 天 | curl 验证 4 个 dim 返回正确层级 |
| **Phase 2** | 4 个 BO YAML 加 `hierarchies` + yaml_loader 支持 | 半天 | 启动应用，metaObj.hierarchies 非空 |
| **Phase 3** | `HierarchicalTreePicker.vue` 组件 + 单测 | 1.5 天 | 单元测试 + Storybook |
| **Phase 4** | `SearchHelpDialog` 集成 + 单/多选分支 | 0.5 天 | 手动验证 dialog 切换 |
| **Phase 5** | `sub_domain.yaml` 启用 `display_mode: tree` + E2E | 0.5 天 | PlaywrightCLI 全套 E2E |
| **Phase 6** | 同样配置扩展到 domain/version/product | 0.5 天 | 3 个新维度 E2E |
| **总计** | | **4.5 天** | |

灰度策略：
1. Phase 5 先只启用 `sub_domain`（一个叶子节点）
2. 观察 1 周无回归 → Phase 6 扩展到 3 个父层

---

## 九、风险与权衡

| 风险 | 缓解 |
|------|------|
| `ObjectScopeSection` 不复用导致代码重复 | 用户决策：保持独立，重复 < 200 行可控 |
| 数据量超 1000 节点 | 首批限定 4 层 + sub_domain 叶子级；如果超再加 lazy 加载 |
| 单选模式 UX 细节差异 | 已列出明确行为表，spec 内固定 |
| 搜索结果与初始勾选冲突 | 搜索命中节点保留原勾选状态，不清除 |
| `el-tree` 性能瓶颈（>2000 节点） | 后续可换 `el-table-v2` 实现 tree-shape，接口不变 |
| 6 个 worktree 同步（主仓 + release-prep） | Phase 6 完成时一并同步到主仓 |

---

## 十、不在范围

- 不重写 `ObjectScopeSection.vue`
- 不支持节点拖拽排序
- 不支持节点编辑
- 不支持虚拟滚动（首批数据量够小）
- 不支持跨维度混合选择

---

## 十一、相关文件清单

新增：
- `src/components/common/HierarchicalTreePicker/HierarchicalTreePicker.vue`
- `src/components/common/HierarchicalTreePicker/HierarchicalTreePicker.spec.js`
- `src/components/common/HierarchicalTreePicker/index.js`

修改：
- `meta/api/management_dimension_api.py`（+新增 tree 路由）
- `meta/core/yaml_loader.py`（+读 hierarchies 字段，如未支持）
- `meta/schemas/product.yaml`、`version.yaml`、`domain.yaml`、`sub_domain.yaml`（+hierarchies）
- `src/components/common/SearchHelpDialog.vue`（+tree 分支）
- `src/views/SystemManagement/components/DimensionScopePanel.vue`（+tree 触发）
- `src/composables/useValueHelp.js`（+透传 display_mode）

---

## 十二、成功标准

- [ ] 角色详情 /detail/role/12009 → 权限配置 → +添加子领域 弹窗改为树形
- [ ] 单选模式：点 node 即选中，再次点取消，"确定"按钮可用即触发
- [ ] 多选模式：checkbox 联动父子 + 半选态，chips 区可单独移除
- [ ] 搜索命中节点父链自动展开 + 高亮
- [ ] 编辑态已有选中正确回填（多选/单选分别验证）
- [ ] flat 模式（其他 BO）零回归
- [ ] ObjectScopeSection 零回归
- [ ] 4 个 BO YAML `hierarchies` 配置生效
- [ ] `/tree` 端点 4 个 dim 各 1 次 SQL，< 100ms 响应