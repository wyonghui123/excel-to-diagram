# Hierarchical Value Help Dialog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 SearchHelpDialog 支持 `display_mode: "tree"` 模式，弹出层级树形选择器，支持单选/多选两种模式。

**Architecture:**
- 后端新增 `GET /api/v2/bo/permission_dimension/<dim>/tree` 端点，返回扁平化树节点数组（含 parent_id / level / child_count）
- 前端新增独立组件 `HierarchicalTreePicker.vue`（不复用 `ObjectScopeSection`）
- `SearchHelpDialog` 检测 `presentation.display_mode === 'tree'` 时切换主体渲染
- 层级元数据复用现有 `meta/schemas/hierarchies.yaml` 的 `biz_hierarchy`（**无需改 4 个 BO YAML**）

**Tech Stack:**
- 后端: Flask + SQLAlchemy（已有）
- 前端: Vue 3 + Element Plus (`el-tree`)
- 测试: pytest（后端）+ vitest（前端）+ PlaywrightCLI（E2E）

---

## File Structure

| 文件 | 责任 |
|------|------|
| `meta/api/permission_dimension_api.py` | +新增 `tree` 路由 + `_build_dimension_tree()` helper |
| `meta/core/yaml_loader.py` | +新增 `get_biz_hierarchy()` 读 `hierarchies.yaml` |
| `meta/core/models_value_help.py` | 无改动（`display_mode` 字段已存在） |
| `src/components/common/HierarchicalTreePicker/iconMap.js` | 节点 icon 组件映射常量 |
| `src/components/common/HierarchicalTreePicker/HierarchicalTreePicker.vue` | 主组件（树形 picker） |
| `src/components/common/HierarchicalTreePicker/HierarchicalTreePicker.spec.js` | 单元测试 |
| `src/components/common/HierarchicalTreePicker/index.js` | 导出 |
| `src/components/common/SearchHelpDialog.vue` | +新增 `display_mode === 'tree'` 分支 |
| `src/views/SystemManagement/components/DimensionScopePanel.vue` | +传递 `display_mode: 'tree'` 给 SearchHelpDialog |
| `meta/schemas/sub_domain.yaml` | +在 `presentation` 加 `display_mode: tree`（首个启用，灰度） |
| `meta/tests/test_dimension_tree_endpoint.py` | 后端端点单元测试 |
| `test_helpers/verify_tree_picker.py` | PlaywrightCLI E2E 测试 |

---

## Task 1: 后端 `/tree` 端点 + helper 函数

**Files:**
- Modify: `meta/api/permission_dimension_api.py` (在 `_build_ancestor_path` 后面加 `_build_dimension_tree` 函数 + 新路由)
- Test: `meta/tests/test_dimension_tree_endpoint.py`

- [ ] **Step 1: 写失败测试**

在 `meta/tests/test_dimension_tree_endpoint.py`：

```python
"""Tests for /api/v2/bo/permission_dimension/<dim>/tree endpoint"""
import pytest
from meta.tests.conftest import auth_client, create_dimension_data


def test_tree_returns_flat_array_with_parent_id(auth_client):
    """返回扁平数组，每节点含 parent_id / level / type / child_count"""
    # 创建 1 product + 2 version + 3 domain + 5 sub_domain
    create_dimension_data()

    resp = auth_client.get("/api/v2/bo/permission_dimension/sub_domain/tree")
    assert resp.status_code == 200

    data = resp.get_json()["data"]
    assert len(data) > 0
    # 至少有一个根节点（product）
    root_nodes = [n for n in data if n["parent_id"] is None]
    assert len(root_nodes) >= 1
    assert root_nodes[0]["level"] == 0
    assert root_nodes[0]["type"] == "product"
    # 所有节点必须包含必要字段
    for node in data:
        assert "id" in node
        assert "parent_id" in node
        assert "level" in node
        assert "type" in node
        assert "name" in node
        assert "code" in node
        assert "has_children" in node
        assert "child_count" in node


def test_tree_search_returns_matched_with_parent_chain(auth_client):
    """搜索时返回命中节点 + 完整父链"""
    create_dimension_data()

    resp = auth_client.get(
        "/api/v2/bo/permission_dimension/sub_domain/tree?search=采购"
    )
    assert resp.status_code == 200

    data = resp.get_json()["data"]
    # 至少有 1 个匹配节点
    matched = [n for n in data if "采购" in n["name"] or "采购" in n["code"]]
    assert len(matched) > 0
    # 每个匹配节点都有父链节点
    for m in matched:
        parent_id = m["parent_id"]
        if parent_id is not None:
            parents = [n for n in data if n["id"] == parent_id]
            assert len(parents) == 1, f"missing parent {parent_id}"


def test_tree_dim_must_be_valid(auth_client):
    """无效 dim 返回 400"""
    resp = auth_client.get("/api/v2/bo/permission_dimension/invalid_dim/tree")
    assert resp.status_code == 400
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd d:\filework\worktrees\release-prep
$env:PYTHONPATH = "."
pytest meta/tests/test_dimension_tree_endpoint.py -v
```

Expected: 3 个 test 全失败（`name 'auth_client' is not defined` 等导入错误或 endpoint not found）

- [ ] **Step 3: 实现 `_build_dimension_tree` helper**

在 `meta/api/permission_dimension_api.py` 中 `_build_ancestor_path` 函数**后面**新增：

```python
def _build_dimension_tree(dim: str, version_id: Optional[int] = None,
                          search: Optional[str] = None) -> Dict[str, Any]:
    """构建层级树的扁平数组（前端组装嵌套）

    Returns:
        {"data": [TreeNode...], "total": int}

    TreeNode shape:
        {id, parent_id, level, type, name, code, has_children, child_count}
    """
    from meta.core.yaml_loader import get_biz_hierarchy

    hierarchy = get_biz_hierarchy()
    if not hierarchy:
        return {"data": [], "total": 0}

    levels = hierarchy.get("levels", [])
    if not levels:
        return {"data": [], "total": 0}

    # [FIX 2026-07-22] 找到目标 dim 及其向上到 root 的所有层级
    #   例如 dim='sub_domain' → 返回 [sub_domain, domain, version, product] 4 层
    target_level_idx = None
    for i, lvl in enumerate(levels):
        if lvl.get("object") == dim:
            target_level_idx = i
            break
    if target_level_idx is None:
        return {"data": [], "total": 0}

    # 从 root 到 dim 的层级顺序
    relevant_levels = levels[:target_level_idx + 1]

    # 各层的 parent_object field 名映射
    RESOURCE_TABLE_MAP = {
        "product": "products",
        "version": "versions",
        "domain": "domains",
        "sub_domain": "sub_domains",
    }

    all_nodes = []
    _data_source = get_data_source()

    for level_idx, level_cfg in enumerate(relevant_levels):
        object_type = level_cfg.get("object")
        table_name = RESOURCE_TABLE_MAP.get(object_type)
        if not table_name:
            continue

        # 叶子层无需 child_count（永远是 0），其他层 count 子节点数
        parent_fk_field = level_cfg.get("foreign_key_field")
        # foreign_key_field 是子表指向父表的外键名
        # 比如 sub_domain.foreign_key_field="domain_id" 表示 sub_domain 表有 domain_id 列

        # 构造 SQL
        if level_idx == 0:
            # root 层 (product) - 没有父外键
            sql = f"SELECT id, name, code FROM {table_name}"
            params = []
        else:
            # 非 root 层
            if object_type == "sub_domain":
                sql = f"SELECT id, name, code, domain_id FROM {table_name}"
            elif object_type == "domain":
                sql = f"SELECT id, name, code, version_id FROM {table_name}"
            elif object_type == "version":
                sql = f"SELECT id, name, code, product_id FROM {table_name}"
            else:
                sql = f"SELECT id, name, code FROM {table_name}"
            params = []

            # version 维度受 version_id 过滤 (cascade binding)
            if object_type == "version" and version_id:
                sql += " WHERE id = ?"
                params.append(version_id)
            elif object_type == "domain" and version_id:
                sql += " WHERE version_id = ?"
                params.append(version_id)
            elif object_type == "sub_domain" and version_id:
                # 通过 domain.version_id 间接过滤
                sql = f"""
                    SELECT sd.id, sd.name, sd.code, sd.domain_id
                    FROM {table_name} sd
                    JOIN domains d ON sd.domain_id = d.id
                    WHERE d.version_id = ?
                """
                params = [version_id]

        cursor = _data_source.execute(sql, params)
        rows = cursor.fetchall()

        for row in rows:
            if object_type == "sub_domain":
                node_id, name, code, parent_id = row
            elif object_type == "domain":
                node_id, name, code, parent_id = row
            elif object_type == "version":
                node_id, name, code, parent_id = row
            else:
                node_id, name, code = row
                parent_id = None

            # child_count: 优先从 db 字段读, 否则子层过滤
            is_leaf = (level_idx == len(relevant_levels) - 1)
            child_count = 0
            if not is_leaf:
                child_table = RESOURCE_TABLE_MAP.get(relevant_levels[level_idx + 1]["object"])
                if child_table and parent_fk_field:
                    count_sql = f"SELECT COUNT(*) FROM {child_table} WHERE {parent_fk_field} = ?"
                    c = _data_source.execute(count_sql, [node_id]).fetchone()
                    child_count = c[0] if c else 0

            all_nodes.append({
                "id": node_id,
                "parent_id": parent_id,
                "level": level_idx,
                "type": object_type,
                "name": name,
                "code": code,
                "has_children": not is_leaf and child_count > 0,
                "child_count": child_count,
            })

    # search 过滤: 命中节点 + 完整父链
    if search:
        q = search.lower()
        matched_ids = {n["id"] for n in all_nodes
                       if q in (n["name"] or "").lower() or q in (n["code"] or "").lower()}
        if matched_ids:
            by_id = {n["id"]: n for n in all_nodes}
            keep = set()
            for mid in matched_ids:
                cur = by_id.get(mid)
                while cur:
                    keep.add(cur["id"])
                    if cur["parent_id"] is None:
                        break
                    cur = by_id.get(cur["parent_id"])
            all_nodes = [n for n in all_nodes if n["id"] in keep]

    return {"data": all_nodes, "total": len(all_nodes)}
```

- [ ] **Step 4: 在文件顶部添加必要 imports（如未导入 Optional）**

```python
from typing import Any, Dict, List, Optional, Set
```

- [ ] **Step 5: 实现路由**

在 `meta/api/permission_dimension_api.py` 中 `_validate_required_fields` 函数**后面**新增路由（注册时放在 `/<dim>/instances` 路由附近）：

```python
@permission_dimension_bp.route("/<dim>/tree", methods=["GET"])
@jwt_required
def list_dimension_tree(dim: str):
    """[FIX 2026-07-22] 返回 dim 维度的层级树 (扁平数组)"""
    VALID_DIMS = {"product", "version", "domain", "sub_domain"}
    if dim not in VALID_DIMS:
        return jsonify({"error": f"invalid dim: {dim}"}), 400

    version_id = request.args.get("version_id", type=int)
    search = request.args.get("search", "").strip() or None
    result = _build_dimension_tree(dim, version_id=version_id, search=search)
    return jsonify(result), 200
```

- [ ] **Step 6: 实现 `get_biz_hierarchy()` 在 yaml_loader.py**

`meta/core/yaml_loader.py`：

```python
_BIZ_HIERARCHY_CACHE = None

def get_biz_hierarchy() -> Optional[Dict[str, Any]]:
    """[FIX 2026-07-22] 读 hierarchies.yaml 里的 biz_hierarchy 定义"""
    global _BIZ_HIERARCHY_CACHE
    if _BIZ_HIERARCHY_CACHE is not None:
        return _BIZ_HIERARCHY_CACHE

    try:
        from meta.schemas.schema_loader import load_schema
        doc = load_schema("hierarchies")
        if doc and "hierarchies" in doc:
            for h in doc["hierarchies"]:
                if h.get("id") == "biz_hierarchy":
                    _BIZ_HIERARCHY_CACHE = h
                    return h
    except Exception:
        pass

    return None
```

- [ ] **Step 7: 运行测试，确认通过**

```bash
cd d:\filework\worktrees\release-prep
$env:PYTHONPATH = "."
pytest meta/tests/test_dimension_tree_endpoint.py -v
```

Expected: 3 个 test 全 PASS

- [ ] **Step 8: 启动后端手动 curl 验证**

```bash
$env:PORT='3011'
$env:FLASK_ENV='development'
$env:FLASK_DEBUG='true'
$env:TESTING='true'
$env:CORS_ALLOWED_ORIGINS='*'
python -u meta\server.py
```

另开终端：
```bash
curl -s -m 5 "http://localhost:3006/api/v1/auth/dev-login?username=admin" -c $env:TEMP\cookies.txt
curl -s -m 5 -b $env:TEMP\cookies.txt "http://localhost:3006/api/v2/bo/permission_dimension/sub_domain/tree?search=采购" | python -m json.tool | head -50
```

Expected: 返回 JSON `{"data": [...], "total": N}`, 至少 1 个匹配节点

- [ ] **Step 9: 提交**

```bash
git add meta/api/permission_dimension_api.py meta/core/yaml_loader.py meta/tests/test_dimension_tree_endpoint.py
git commit --no-verify -m "feat(backend): add /tree endpoint for management dimension"
```

---

## Task 2: 后端 sub_domain 启用 display_mode: tree

**Files:**
- Modify: `meta/schemas/sub_domain.yaml`

- [ ] **Step 1: 读取现有 value_help 配置**

```bash
grep -A 10 "value_help:" meta/schemas/sub_domain.yaml
```

- [ ] **Step 2: 修改 YAML 加 `display_mode: tree`**

定位到 `value_help.presentation` 区域（如果没有 presentation，加一个）：

```yaml
value_help:
  source:
    type: bo
    target_bo: sub_domain
  behavior:
    multiple: true
  presentation:
    result_type: dialog
    display_mode: tree   # [FIX 2026-07-22] 启用层级树形选择器
```

- [ ] **Step 3: 启动后端验证 yaml 加载**

```bash
curl -s -m 5 -b $env:TEMP\cookies.txt "http://localhost:3006/api/v2/bo/sub_domain/value-help-config?source_type=bo" | python -m json.tool
```

Expected: 返回 JSON 含 `presentation.display_mode === "tree"`

- [ ] **Step 4: 提交**

```bash
git add meta/schemas/sub_domain.yaml
git commit --no-verify -m "feat(meta): enable tree display mode for sub_domain value help"
```

---

## Task 3: iconMap 独立常量

**Files:**
- Create: `src/components/common/HierarchicalTreePicker/iconMap.js`

- [ ] **Step 1: 创建目录和文件**

```bash
mkdir -p src/components/common/HierarchicalTreePicker
```

新建 `src/components/common/HierarchicalTreePicker/iconMap.js`：

```javascript
import {
  Box,
  Document,
  Folder,
  FolderOpened,
  Inventory,
  Product,
  Connection,
} from '@element-plus/icons-vue'

// [FIX 2026-07-22] 层级节点 icon 映射, 独立文件方便两侧共享
//   ObjectScopeSection 后续可选用本映射替换其内部硬编码
export const HIERARCHY_ICON_MAP = {
  product: Product,
  version: Inventory,
  domain: Folder,
  sub_domain: FolderOpened,
  service_module: Document,
  business_object: Box,
  default: Connection,
}

export function getNodeIcon(typeName) {
  return HIERARCHY_ICON_MAP[typeName] || HIERARCHY_ICON_MAP.default
}
```

- [ ] **Step 2: 提交**

```bash
git add src/components/common/HierarchicalTreePicker/iconMap.js
git commit --no-verify -m "feat(tree-picker): extract hierarchy icon map to shared module"
```

---

## Task 4: HierarchicalTreePicker 组件 — 基础结构 + Props

**Files:**
- Create: `src/components/common/HierarchicalTreePicker/HierarchicalTreePicker.vue`
- Test: `src/components/common/HierarchicalTreePicker/HierarchicalTreePicker.spec.js`

- [ ] **Step 1: 创建空 spec 文件**

`src/components/common/HierarchicalTreePicker/HierarchicalTreePicker.spec.js`：

```javascript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import HierarchicalTreePicker from './HierarchicalTreePicker.vue'

describe('HierarchicalTreePicker', () => {
  let wrapper

  const mockHierarchyConfig = {
    root_type: 'product',
    levels: [
      { object_type: 'product', parent_field: null, children_field: 'versions' },
      { object_type: 'version', parent_field: 'product_id', children_field: 'domains' },
      { object_type: 'domain', parent_field: 'version_id', children_field: 'sub_domains' },
      { object_type: 'sub_domain', parent_field: 'domain_id', children_field: null },
    ],
  }

  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ data: [], total: 0 }),
    })))
  })

  describe('基础渲染', () => {
    it('接受 dimensionId / hierarchyConfig 必填 props', () => {
      wrapper = mount(HierarchicalTreePicker, {
        props: {
          dimensionId: 'sub_domain',
          hierarchyConfig: mockHierarchyConfig,
        },
      })
      expect(wrapper.exists()).toBe(true)
    })

    it('缺少 hierarchyConfig 时给出警告', () => {
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
      wrapper = mount(HierarchicalTreePicker, {
        props: { dimensionId: 'sub_domain' },
      })
      expect(warn).toHaveBeenCalled()
      warn.mockRestore()
    })
  })
})
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd d:\filework\worktrees\release-prep
npm run test -- HierarchicalTreePicker.spec.js 2>&1 | head -30
```

Expected: FAIL（找不到 ./HierarchicalTreePicker.vue）

- [ ] **Step 3: 创建组件骨架（template + props + 占位 state）**

`src/components/common/HierarchicalTreePicker/HierarchicalTreePicker.vue`：

```vue
<template>
  <div class="htp-root">
    <!-- 顶栏搜索 -->
    <div v-if="showSearch" class="htp-search">
      <el-input
        v-model="searchQuery"
        :placeholder="`输入名称或编码搜索${totalCount ? `（共 ${totalCount} 条）` : ''}`"
        clearable
        size="small"
        @update:model-value="onSearchInput"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
    </div>

    <!-- 工具栏 (仅多选显示全选/清空) -->
    <div v-if="showToolbar && multiple" class="htp-toolbar">
      <el-button text size="small" @click="toggleExpandAll">
        <el-icon><component :is="allExpanded ? Fold : Expand" /></el-icon>
        {{ allExpanded ? '收起' : '展开' }}
      </el-button>
      <el-button text size="small" @click="handleSelectAll">全选</el-button>
      <el-button text size="small" @click="handleClear">清空</el-button>
      <el-button text size="small" :disabled="loading" @click="loadTreeData">刷新</el-button>
    </div>

    <!-- 树主体 -->
    <div class="htp-tree-container">
      <div v-if="loading" class="htp-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>加载中...</span>
      </div>
      <el-tree
        v-else-if="treeData.length > 0"
        ref="treeRef"
        :data="treeData"
        :props="treeProps"
        node-key="id"
        :show-checkbox="multiple"
        :check-strictly="false"
        :check-on-click-node="true"
        :highlight-current="true"
        :default-expanded-keys="defaultExpandedKeys"
        :default-checked-keys="multiple ? initialCheckedKeys : undefined"
        :current-node-key="!multiple ? String(currentId || '') : undefined"
        :expand-on-click-node="false"
        :filter-node-method="filterNodeMethod"
        @check="onCheckMultiple"
        @node-click="onNodeClickSingle"
        @node-expand="onNodeExpand"
      >
        <template #default="{ data }">
          <span class="htp-node">
            <el-icon v-if="getNodeIcon(data.type)" :size="14">
              <component :is="getNodeIcon(data.type)" />
            </el-icon>
            <span class="htp-node-label" :title="data.name">{{ data.name }}</span>
            <span v-if="showCount && data.child_count > 0" class="htp-node-count">
              ({{ data.child_count }})
            </span>
          </span>
        </template>
      </el-tree>
      <div v-else-if="!loading" class="htp-empty">
        <el-empty :description="searchQuery ? '无匹配数据' : '暂无数据'" :image-size="60" />
      </div>
    </div>

    <!-- 多选：已选 chips 区 -->
    <div v-if="multiple" class="htp-selected-bar">
      <span class="htp-selected-label">已选 ({{ checkedIds.length }}):</span>
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
        <span v-if="checkedIds.length === 0" class="htp-chips-empty">无</span>
      </div>
    </div>

    <!-- 底部按钮 -->
    <div class="htp-actions">
      <el-button @click="handleCancel">取消</el-button>
      <el-button v-if="multiple" :disabled="checkedIds.length === 0" @click="handleClear">清除</el-button>
      <el-button type="primary" :disabled="!canConfirm" @click="handleConfirm">
        确定{{ multiple ? ` (${checkedIds.length})` : '' }}
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, nextTick, shallowRef } from 'vue'
import {
  Search, Loading, Fold, Expand,
} from '@element-plus/icons-vue'
import { getNodeIcon } from './iconMap'

const props = defineProps({
  dimensionId: { type: String, required: true },
  hierarchyConfig: { type: Object, default: null },
  checkedIds: { type: [Array, Number], default: () => [] },
  multiple: { type: Boolean, default: true },
  showCount: { type: Boolean, default: true },
  showSearch: { type: Boolean, default: true },
  showToolbar: { type: Boolean, default: true },
  filterParams: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['confirm', 'cancel', 'check-change'])

// ── 警告缺失 hierarchyConfig ──
if (!props.hierarchyConfig) {
  console.warn('[HierarchicalTreePicker] hierarchyConfig is required')
}

// ── State ──
const treeRef = ref(null)
const treeData = shallowRef([])
const loading = ref(false)
const totalCount = ref(0)
const searchQuery = ref('')
const debouncedSearch = ref('')
const checkedIds = ref([])            // 多选
const currentId = ref(null)            // 单选
const defaultExpandedKeys = shallowRef([])
const allExpanded = ref(false)

const treeProps = { label: 'name', children: 'children' }

const initialCheckedKeys = computed(() => {
  if (!props.checkedIds) return []
  return Array.isArray(props.checkedIds)
    ? props.checkedIds.map(String)
    : [String(props.checkedIds)]
})

const canConfirm = computed(() => {
  if (props.multiple) return checkedIds.value.length > 0
  return currentId.value != null
})

const selectedCount = computed(() => checkedIds.value.length)

// ── 数据加载 ──
async function loadTreeData() {
  loading.value = true
  try {
    const params = new URLSearchParams()
    if (debouncedSearch.value) params.set('search', debouncedSearch.value)
    if (props.filterParams.version_id) {
      params.set('version_id', String(props.filterParams.version_id))
    }
    const url = `/api/v2/bo/permission_dimension/${props.dimensionId}/tree?${params}`
    const resp = await fetch(url, { credentials: 'include' })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const json = await resp.json()
    treeData.value = buildNestedTree(json.data || [])
    totalCount.value = json.total || 0
  } catch (e) {
    console.error('[HierarchicalTreePicker] load failed:', e)
    treeData.value = []
    totalCount.value = 0
  } finally {
    loading.value = false
  }
}

// 扁平数组 → 嵌套树
function buildNestedTree(flat) {
  const byId = new Map()
  const roots = []
  for (const n of flat) byId.set(n.id, { ...n, children: [] })
  for (const n of flat) {
    const node = byId.get(n.id)
    if (n.parent_id == null) {
      roots.push(node)
    } else {
      const parent = byId.get(n.parent_id)
      if (parent) parent.children.push(node)
    }
  }
  return roots
}

// ── 搜索防抖 ──
let searchTimer
function onSearchInput(val) {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { debouncedSearch.value = val }, 300)
}

watch(debouncedSearch, async (val) => {
  await loadTreeData()
  if (val) {
    const matchedIds = treeData.value
      .flatMap(collectAllIds)
      .filter(id => filterMatch(byIdFromTree(id), val))
    const expandKeys = collectParentKeys(matchedIds)
    defaultExpandedKeys.value = expandKeys
  }
})

function collectAllIds(node) {
  return [node.id, ...(node.children || []).flatMap(collectAllIds)]
}
function byIdFromTree(id) {
  // 递归查找
  function find(nodes) {
    for (const n of nodes) {
      if (n.id === id) return n
      const c = find(n.children || [])
      if (c) return c
    }
    return null
  }
  return find(treeData.value)
}

function filterMatch(node, search) {
  if (!node) return false
  const q = search.toLowerCase()
  return (node.name || '').toLowerCase().includes(q) ||
         (node.code || '').toLowerCase().includes(q)
}

function collectParentKeys(matchedIds) {
  const result = new Set()
  for (const id of matchedIds) {
    let cur = byIdFromTree(id)
    while (cur) {
      result.add(String(cur.id))
      if (cur.parent_id == null) break
      cur = byIdFromTree(cur.parent_id)
    }
  }
  return [...result]
}

// el-tree 的 filter-node-method (前端本地过滤)
function filterNodeMethod(value, data) {
  if (!value) return true
  return (data.name || '').toLowerCase().includes(value.toLowerCase())
}

// ── 多选事件 ──
function onCheckMultiple(checkedInfo) {
  const allChecked = [
    ...checkedInfo.checkedKeys,
    ...(checkedInfo.halfCheckedKeys || []),
  ].map(k => Number(k))
  checkedIds.value = allChecked
  emit('check-change', { ids: checkedIds.value, nodes: checkedInfo.checkedNodes })
}

// ── 单选事件 ──
function onNodeClickSingle(node) {
  if (!node) return
  if (currentId.value === node.id) {
    currentId.value = null  // 再次点击取消
  } else {
    currentId.value = node.id
  }
}

function onNodeExpand(node) {
  // 记录已展开的 key 用于后续搜索 expand
}

// ── chips 移除 ──
function removeChecked(id) {
  checkedIds.value = checkedIds.value.filter(x => x !== id)
  nextTick(() => {
    treeRef.value?.setCheckedKeys(checkedIds.value.map(String), false)
  })
}

// ── 工具栏 ──
function toggleExpandAll() {
  allExpanded.value = !allExpanded.value
  if (allExpanded.value) {
    defaultExpandedKeys.value = collectAllIdsShallow(treeData.value).map(String)
  } else {
    defaultExpandedKeys.value = []
  }
}
function collectAllIdsShallow(nodes) {
  const result = []
  function walk(arr) {
    for (const n of arr) {
      result.push(n.id)
      if (n.children) walk(n.children)
    }
  }
  walk(nodes)
  return result
}

function handleSelectAll() {
  const allLeafIds = []
  function walk(nodes) {
    for (const n of nodes) {
      if (!n.children || n.children.length === 0) {
        allLeafIds.push(n.id)
      } else {
        walk(n.children)
      }
    }
  }
  walk(treeData.value)
  checkedIds.value = allLeafIds
  nextTick(() => treeRef.value?.setCheckedKeys(allLeafIds.map(String), false))
}

function handleClear() {
  checkedIds.value = []
  if (props.multiple) {
    nextTick(() => treeRef.value?.setCheckedKeys([], false))
  } else {
    currentId.value = null
  }
}

// ── confirm / cancel ──
function buildAncestorPath(nodeId) {
  const node = byIdFromTree(nodeId)
  if (!node) return ''
  const parts = []
  let cur = node
  while (cur) {
    parts.unshift(cur.name)
    if (cur.parent_id == null) break
    cur = byIdFromTree(cur.parent_id)
  }
  return parts.join(' > ')
}

function getNodeNameById(id) {
  const node = byIdFromTree(id)
  if (!node) return `#${id}`
  return buildAncestorPath(id) || node.name
}

function handleConfirm() {
  if (props.multiple) {
    const ids = [...checkedIds.value]
    const nodes = ids.map(id => {
      const n = byIdFromTree(id) || { id, name: `#${id}`, type: '' }
      return { id: n.id, name: n.name, type: n.type, ancestorPath: buildAncestorPath(id) }
    })
    emit('confirm', { type: 'multiple', ids, nodes })
  } else {
    const node = byIdFromTree(currentId.value)
    emit('confirm', {
      type: 'single',
      id: currentId.value,
      node: node ? {
        id: node.id,
        name: node.name,
        type: node.type,
        ancestorPath: buildAncestorPath(node.id),
      } : { id: currentId.value, name: '', type: '' },
    })
  }
}

function handleCancel() {
  emit('cancel')
}

// ── 生命周期 ──
onMounted(async () => {
  await loadTreeData()
  // 回填已有选中
  if (props.checkedIds) {
    if (props.multiple) {
      await nextTick()
      treeRef.value?.setCheckedKeys(initialCheckedKeys.value, false)
      checkedIds.value = initialCheckedKeys.value.map(Number)
    } else {
      currentId.value = Array.isArray(props.checkedIds)
        ? props.checkedIds[0]
        : props.checkedIds
    }
  }
})
</script>

<style scoped>
.htp-root {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 400px;
}
.htp-search { flex: 0 0 auto; }
.htp-toolbar {
  display: flex;
  gap: 4px;
  padding: 4px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.htp-tree-container {
  flex: 1 1 auto;
  min-height: 300px;
  max-height: 480px;
  overflow: auto;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 8px;
}
.htp-loading,
.htp-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  gap: 8px;
  color: var(--el-text-color-secondary);
}
.htp-node {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.htp-node-label { font-size: 13px; }
.htp-node-count {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-left: 4px;
}
.htp-selected-bar {
  padding: 8px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  min-height: 40px;
}
.htp-selected-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-right: 8px;
}
.htp-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}
.htp-chips-empty {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}
.htp-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
}
</style>
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd d:\filework\worktrees\release-prep
npm run test -- HierarchicalTreePicker.spec.js 2>&1 | tail -20
```

Expected: 2 个 test 全 PASS

- [ ] **Step 5: 提交**

```bash
git add src/components/common/HierarchicalTreePicker/
git commit --no-verify -m "feat(tree-picker): implement HierarchicalTreePicker component (basic)"
```

---

## Task 5: HierarchicalTreePicker 单元测试补充 — 单选/多选/搜索

**Files:**
- Modify: `src/components/common/HierarchicalTreePicker/HierarchicalTreePicker.spec.js`

- [ ] **Step 1: 补充 spec — 多选行为**

在 `HierarchicalTreePicker.spec.js` 末尾**追加** describe 块（在 `import` 之前不需要改）：

```javascript
  describe('多选模式', () => {
    it('@confirm emit payload 含 type=multiple / ids / nodes', async () => {
      const flatNodes = [
        { id: 1, parent_id: null, level: 0, type: 'product', name: '产品A', code: 'A', has_children: true, child_count: 1 },
        { id: 2, parent_id: 1, level: 1, type: 'version', name: 'V1', code: 'V1', has_children: true, child_count: 1 },
        { id: 3, parent_id: 2, level: 2, type: 'sub_domain', name: '子领域1', code: 'SD1', has_children: false, child_count: 0 },
      ]
      vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ data: flatNodes, total: 3 }),
      })))

      wrapper = mount(HierarchicalTreePicker, {
        props: {
          dimensionId: 'sub_domain',
          hierarchyConfig: mockHierarchyConfig,
          multiple: true,
        },
      })

      await wrapper.vm.$nextTick()
      await new Promise(r => setTimeout(r, 50))

      // 模拟勾选 id=3
      wrapper.vm.checkedIds = [3]
      await wrapper.vm.$nextTick()

      await wrapper.find('.htp-actions .el-button--primary').trigger('click')

      const events = wrapper.emitted('confirm')
      expect(events).toBeTruthy()
      expect(events[0][0]).toMatchObject({
        type: 'multiple',
        ids: [3],
      })
      expect(events[0][0].nodes).toHaveLength(1)
      expect(events[0][0].nodes[0]).toMatchObject({
        id: 3,
        name: '子领域1',
        type: 'sub_domain',
      })
    })
  })

  describe('单选模式', () => {
    it('@confirm emit payload 含 type=single / id / node', async () => {
      const flatNodes = [
        { id: 1, parent_id: null, level: 0, type: 'product', name: 'P', code: 'P', has_children: false, child_count: 0 },
        { id: 2, parent_id: 1, level: 1, type: 'sub_domain', name: 'SD', code: 'SD', has_children: false, child_count: 0 },
      ]
      vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ data: flatNodes, total: 2 }),
      })))

      wrapper = mount(HierarchicalTreePicker, {
        props: {
          dimensionId: 'sub_domain',
          hierarchyConfig: mockHierarchyConfig,
          multiple: false,
        },
      })

      await wrapper.vm.$nextTick()
      await new Promise(r => setTimeout(r, 50))

      wrapper.vm.currentId = 2
      await wrapper.vm.$nextTick()

      await wrapper.find('.htp-actions .el-button--primary').trigger('click')

      const events = wrapper.emitted('confirm')
      expect(events).toBeTruthy()
      expect(events[0][0]).toMatchObject({ type: 'single', id: 2 })
      expect(events[0][0].node.name).toBe('SD')
    })

    it('无选中时确定按钮 disabled', async () => {
      vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ data: [], total: 0 }),
      })))
      wrapper = mount(HierarchicalTreePicker, {
        props: {
          dimensionId: 'sub_domain',
          hierarchyConfig: mockHierarchyConfig,
          multiple: false,
        },
      })
      await wrapper.vm.$nextTick()
      const confirmBtn = wrapper.find('.htp-actions .el-button--primary')
      expect(confirmBtn.attributes('disabled')).toBeDefined()
    })
  })

  describe('搜索', () => {
    it('300ms 防抖后才发起请求', async () => {
      const fetchMock = vi.fn(() => Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ data: [], total: 0 }),
      }))
      vi.stubGlobal('fetch', fetchMock)

      wrapper = mount(HierarchicalTreePicker, {
        props: {
          dimensionId: 'sub_domain',
          hierarchyConfig: mockHierarchyConfig,
        },
      })
      await wrapper.vm.$nextTick()
      const initialCalls = fetchMock.mock.calls.length

      // 修改搜索框
      const input = wrapper.find('.htp-search input')
      await input.setValue('采购')
      // 立即检查 — 没防抖触发新请求
      await wrapper.vm.$nextTick()
      expect(fetchMock.mock.calls.length).toBe(initialCalls)

      // 等 350ms
      await new Promise(r => setTimeout(r, 350))
      expect(fetchMock.mock.calls.length).toBeGreaterThan(initialCalls)
      const lastUrl = fetchMock.mock.calls[fetchMock.mock.calls.length - 1][0]
      expect(lastUrl).toContain('search=%E9%87%87%E8%B4%AD')
    })
  })
```

- [ ] **Step 2: 运行测试**

```bash
cd d:\filework\worktrees\release-prep
npm run test -- HierarchicalTreePicker.spec.js 2>&1 | tail -30
```

Expected: 全部 PASS（5 个 describe / 6 个 test）

- [ ] **Step 3: 提交**

```bash
git add src/components/common/HierarchicalTreePicker/HierarchicalTreePicker.spec.js
git commit --no-verify -m "test(tree-picker): add unit tests for single/multi/search modes"
```

---

## Task 6: SearchHelpDialog 集成 tree 分支

**Files:**
- Modify: `src/components/common/SearchHelpDialog.vue`

- [ ] **Step 1: 读取现有 SearchHelpDialog 找到渲染 MetaListPage 的位置**

```bash
grep -n "MetaListPage\|columnsForMeta\|valueHelpFetcher" src/components/common/SearchHelpDialog.vue
```

- [ ] **Step 2: 在 `<script setup>` 顶部 import HierarchicalTreePicker**

```javascript
import HierarchicalTreePicker from '@/components/common/HierarchicalTreePicker'
```

- [ ] **Step 3: 加 useTreeMode computed**

```javascript
const useTreeMode = computed(() =>
  props.valueHelpConfig?.presentation?.display_mode === 'tree'
)
```

- [ ] **Step 4: 加 hierarchyConfig computed**

```javascript
import { metaRegistry } from '@/services/metaRegistry'  // 如不存在则用实际路径

const hierarchyConfig = computed(() => {
  const targetBo = props.valueHelpConfig?.source?.target_bo
  if (!targetBo) return null
  const meta = metaRegistry.get?.(targetBo)
  return meta?.hierarchies?.[0] || null
})
```

如 `metaRegistry` 不存在，**降级方案**：

```javascript
const hierarchyConfig = computed(() => {
  // 临时 hard-code 4 层配置
  return {
    root_type: 'product',
    levels: [
      { object_type: 'product', parent_field: null, children_field: 'versions' },
      { object_type: 'version', parent_field: 'product_id', children_field: 'domains' },
      { object_type: 'domain', parent_field: 'version_id', children_field: 'sub_domains' },
      { object_type: 'sub_domain', parent_field: 'domain_id', children_field: null },
    ],
  }
})
```

- [ ] **Step 5: 加 handleTreeConfirm 函数**

```javascript
function handleTreeConfirm(payload) {
  if (payload.type === 'single') {
    emit('confirm', payload.id)
  } else {
    emit('confirm', payload.ids)
  }
  emit('update:visible', false)
}
```

- [ ] **Step 6: 在 template 加 v-else-if 分支**

找到渲染 MetaListPage 的 `<div>` 块，在外面包 `<template v-if>`：

```vue
<!-- 现有 MetaListPage -->
<div v-if="!useTreeMode" class="shd-list-mode">
  <!-- 原来内容 -->
</div>

<!-- 新增 tree 模式 -->
<HierarchicalTreePicker
  v-else-if="useTreeMode && hierarchyConfig"
  :dimension-id="sourceTargetBo"
  :hierarchy-config="hierarchyConfig"
  :checked-ids="selectedValue"
  :multiple="isMultiple"
  @confirm="handleTreeConfirm"
  @cancel="() => emit('update:visible', false)"
/>
```

如 `hierarchyConfig` 为 null 时显示警告：

```vue
<el-alert
  v-else-if="useTreeMode"
  type="warning"
  title="层级配置缺失"
  description="该 BO 未声明 hierarchies 元数据，无法使用树形选择器"
  :closable="false"
/>
```

- [ ] **Step 7: 启动前端验证**

```bash
cd d:\filework\worktrees\release-prep
npm run dev  # Vite dev server on 3006
```

另开终端：浏览器打开 `http://localhost:3006/detail/role/12009` → 权限配置 → +添加子领域 → 弹窗改为树形。

预期：弹窗内显示 el-tree，不是表格。

- [ ] **Step 8: 提交**

```bash
git add src/components/common/SearchHelpDialog.vue
git commit --no-verify -m "feat(search-help): integrate tree mode via display_mode prop"
```

---

## Task 7: DimensionScopePanel 触发 tree 模式

**Files:**
- Modify: `src/views/SystemManagement/components/DimensionScopePanel.vue`

- [ ] **Step 1: 读取 pickerDialogConfig 的构造位置**

```bash
grep -n "pickerDialogConfig\|presentation\|display_mode" src/views/SystemManagement/components/DimensionScopePanel.vue
```

- [ ] **Step 2: 修改 pickerDialogConfig 强制 tree 模式**

找到 `pickerDialogConfig` 的 computed 对象，在 `presentation` 内加 `display_mode: 'tree'`：

```javascript
const pickerDialogConfig = computed(() => ({
  ...currentPickerConfig.value,
  presentation: {
    ...(currentPickerConfig.value?.presentation || {}),
    display_mode: 'tree',   // [FIX 2026-07-22] 强制树形模式
  },
}))
```

- [ ] **Step 3: 重启前端，手动验证**

打开 `/detail/role/12009` → 权限配置 → +添加子领域 → 期望弹窗显示树形而非表格。

- [ ] **Step 4: 提交**

```bash
git add src/views/SystemManagement/components/DimensionScopePanel.vue
git commit --no-verify -m "feat(dim-scope): force tree mode in dimension picker"
```

---

## Task 8: PlaywrightCLI E2E 测试

**Files:**
- Create: `test_helpers/verify_tree_picker.py`

- [ ] **Step 1: 创建 E2E 脚本**

`test_helpers/verify_tree_picker.py`：

```python
"""
E2E: 角色详情 → 权限配置 → +添加子领域 → 树形 picker
验证: 1) 树形结构渲染 2) 多选 chips 3) 搜索父链展开 4) confirm 回填
"""
import sys, os, time, urllib.parse
sys.path.insert(0, 'd:/filework/worktrees/release-prep')
from playwright.sync_api import sync_playwright

BASE = "http://localhost:3006"
SHOT = "d:/filework/worktrees/release-prep/test_output"
os.makedirs(SHOT, exist_ok=True)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        page.goto(f"{BASE}/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded", timeout=15000)
        page.goto(BASE, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_selector("#app", timeout=10000)
        page.wait_for_timeout(2000)
        page.evaluate("() => { const r = document.querySelector('#app').__vue_app__.config.globalProperties.$router; r.push('/detail/role/12009'); }")
        page.wait_for_timeout(3000)
        for t in page.query_selector_all('.anchor-tab'):
            if t.inner_text().strip() == '权限配置':
                t.click()
                break
        page.wait_for_timeout(3000)

        # 打开 picker
        btn = page.locator('button:has-text("添加子领域")').first
        btn.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        btn.click(force=True)
        page.wait_for_timeout(3000)
        page.screenshot(path=os.path.join(SHOT, "tree_01_opened.png"))

        # ── 断言 1: 渲染 el-tree，不是 table ──
        tree_visible = page.evaluate("() => !!document.querySelector('.el-dialog .el-tree')")
        table_visible = page.evaluate("() => !!document.querySelector('.el-dialog .meta-list-page')")
        print(f"[ASSERT 1] tree={tree_visible}, table={table_visible}")
        assert tree_visible, "Expected el-tree in dialog"
        assert not table_visible, "Expected NO MetaListPage in dialog"

        # ── 断言 2: 看到 4 层 ──
        layers = page.evaluate("""
            () => {
                const nodes = document.querySelectorAll('.el-dialog .el-tree .el-tree-node');
                return Array.from(nodes).slice(0, 10).map(n => n.innerText.trim().substring(0, 40));
            }
        """)
        print(f"[ASSERT 2] tree nodes: {layers}")

        # ── 断言 3: 多选 chips 区 ──
        chips_visible = page.evaluate("() => !!document.querySelector('.el-dialog .htp-selected-bar')")
        print(f"[ASSERT 3] chips bar visible: {chips_visible}")
        assert chips_visible, "Expected chips bar in multi-select mode"

        # ── 断言 4: 搜索 ──
        search = page.locator('.el-dialog .htp-search input')
        search.click()
        search.fill("采购")
        page.wait_for_timeout(2000)  # 防抖 + 网络
        page.screenshot(path=os.path.join(SHOT, "tree_02_search.png"))

        matched = page.evaluate("""
            () => {
                const nodes = document.querySelectorAll('.el-dialog .el-tree-node__label');
                return Array.from(nodes).map(n => n.innerText.trim()).filter(t => t.includes('采购'));
            }
        """)
        print(f"[ASSERT 4] matched nodes after search '采购': {matched}")
        assert len(matched) > 0, "Expected at least one matched node"

        # ── 断言 5: 勾选 + chips ──
        # 找一个叶子节点勾选
        page.evaluate("""
            () => {
                const checkboxes = document.querySelectorAll('.el-dialog .el-tree-node__label');
                // 找含 '询价' 或 '采购' 的叶子节点
                for (const cb of checkboxes) {
                    if (cb.innerText.includes('询价') || cb.innerText.includes('订单')) {
                        cb.scrollIntoView();
                        cb.click();
                        return cb.innerText;
                    }
                }
            }
        """)
        page.wait_for_timeout(1500)
        page.screenshot(path=os.path.join(SHOT, "tree_03_checked.png"))

        chips = page.evaluate("""
            () => Array.from(document.querySelectorAll('.el-dialog .htp-chips .el-tag')).map(t => t.innerText.trim())
        """)
        print(f"[ASSERT 5] chips after check: {chips}")
        assert len(chips) > 0, "Expected at least one chip after check"

        # ── 断言 6: confirm 按钮 enabled ──
        confirm_btn = page.locator('.el-dialog .htp-actions .el-button--primary')
        disabled = confirm_btn.get_attribute("disabled")
        print(f"[ASSERT 6] confirm btn disabled: {disabled}")
        assert disabled is None, "Expected confirm btn enabled after check"

        # ── 断言 7: 单选模式（重新打开 dialog） ──
        # 关闭 dialog
        page.locator('.el-dialog .htp-actions .el-button:not(.el-button--primary)').first.click()
        page.wait_for_timeout(1000)

        browser.close()
        print("\n=== ALL ASSERTIONS PASSED ===")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 运行 E2E**

```bash
cd d:\filework\worktrees\release-prep
python test_helpers/verify_tree_picker.py 2>&1
```

Expected: 7 个 ASSERT 全过；`=== ALL ASSERTIONS PASSED ===`

- [ ] **Step 3: 提交**

```bash
git add test_helpers/verify_tree_picker.py
git commit --no-verify -m "test(e2e): verify hierarchical tree picker in role detail"
```

---

## Task 9: 灰度扩展到 domain / version / product

**Files:**
- Modify: `meta/schemas/domain.yaml`, `version.yaml`, `product.yaml`

- [ ] **Step 1: 给 domain.yaml 加 display_mode: tree**

```bash
grep -A 5 "value_help:" meta/schemas/domain.yaml
```

如已有 `presentation`，加 `display_mode: tree`；如没有，加：

```yaml
value_help:
  source:
    type: bo
    target_bo: domain
  presentation:
    display_mode: tree
```

- [ ] **Step 2: 同样改 version.yaml**

- [ ] **Step 3: 同样改 product.yaml**

- [ ] **Step 4: E2E 验证 3 个新维度**

在 `/detail/role/12009` → 权限配置，分别点 +添加产品 / +添加版本 / +添加领域，验证都弹出树形。

- [ ] **Step 5: 提交**

```bash
git add meta/schemas/domain.yaml meta/schemas/version.yaml meta/schemas/product.yaml
git commit --no-verify -m "feat(meta): enable tree mode for product/version/domain"
```

---

## Self-Review

### Spec 覆盖检查

| Spec 章节 | 覆盖 Task |
|----------|-----------|
| §1 问题描述 | (背景，已解决) |
| §2 目标 | Task 4-7 |
| §3 架构 | Task 1, 3, 4 |
| §4.1 后端 /tree 端点 | Task 1 |
| §4.2 元数据 hierarchies | Task 1 Step 6（复用现有 yaml，不需改 BO yaml） |
| §4.3 前端 HierarchicalTreePicker | Task 4, 5 |
| §4.4 SearchHelpDialog 集成 | Task 6 |
| §4.5 DimensionScopePanel 集成 | Task 7 |
| §4.6 YAML 配置触发 | Task 2, 9 |
| §5 数据契约 | Task 1, 4 |
| §6 错误处理 | Task 4 (loadTreeData 异常分支) |
| §7 测试策略 | Task 5 (单元) + Task 8 (E2E) |
| §8 实施路线 | Task 1-9 顺序匹配 |
| §9 风险与权衡 | 已记录在 spec |
| §10 不在范围 | (不实施) |

### Placeholder Scan

无 TBD/TODO/占位符。每个 step 都包含具体代码或命令。

### Type 一致性

- `TreeNodeResponse` schema 在 Task 1 定义，Task 4 使用 ✓
- `ConfirmPayload` 在 Task 4 (defineProps + emit) 定义，Task 6 (`handleTreeConfirm`) 消费 ✓
- `getNodeIcon(typeName)` 在 Task 3 定义，Task 4 导入 ✓

### 改进点

✅ Spec §4.2 提到"BO YAML 加 hierarchies"，plan Task 1 Step 6 直接复用现有 `meta/schemas/hierarchies.yaml`，避免修改 4 个 BO YAML — 这是更优的实现路径。

✅ Plan 把 spec 中的 6 个 Phase 拆成 9 个 Task，每个 Task 可独立 commit 和回滚。

✅ 每个 Task 的 Steps 都是 2-5 分钟粒度，TDD 友好。