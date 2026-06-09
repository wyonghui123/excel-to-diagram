## 目录

1. [关键发现（调研阶段）](#关键发现（调研阶段）)
2. [Step 1: 新建 useRefreshCoordinator.js](#step-1-新建-userefreshcoordinatorjs)
3. [Step 2: boService 增强](#step-2-boservice-增强)
4. [Step 3: DetailPage CRUD 收敛到 boService](#step-3-detailpage-crud-收敛到-boservice)
5. [Step 4: MOMP 绑定协调器](#step-4-momp-绑定协调器)
6. [Step 5: MetaListPage 注册回调](#step-5-metalistpage-注册回调)
7. [Step 6: RelationScopeTree 注册回调](#step-6-relationscopetree-注册回调)
8. [Step 7: useMultiObjectPage 接入协调器](#step-7-usemultiobjectpage-接入协调器)
9. [Step 8: 清理旧 emit/watch 路径](#step-8-清理旧-emitwatch-路径)
10. [验证清单](#验证清单)

---
# 实施方案: 元数据驱动 MultiObjectPage 统一刷新协议

> 关联 Spec: [spec-unified-refresh-protocol.md](./spec-unified-refresh-protocol.md)  
> 创建日期: 2026-05-25

---

## 关键发现（调研阶段）

| 项目 | DetailPage.vue | boService.js |
|------|---------------|-------------|
| API 路径 | 硬编码 `/api/v2/bo/...` | 使用 `this.API_BASE_V2` |
| Authorization | `localStorage.getItem('auth_token')` 直接读取 | `useAuthStore().getAuthHeaders()` 通过 Pinia Store |
| Content-Type | 仅 handleSave 手动设置 | `_getHeaders()` 自动包含 |
| 401 处理 | 无 401 特殊处理 | 自动调用 `authStore.logout()` |
| 缓存处理 | 无缓存 | 有 LRU 缓存，操作后自动清除 |

**结论**: DetailPage 收敛到 boService 后，认证和 401 处理会自动升级，无需手动管理。

---

## Step 1: 新建 useRefreshCoordinator.js

**文件**: `src/composables/useRefreshCoordinator.js` (新建)

**操作**: 创建统一刷新协调器 Composable

```javascript
import { ref } from 'vue'

export function useRefreshCoordinator() {
  const callbacks = new Map()
  const isRefreshing = ref(false)

  function register(key, fn) {
    callbacks.set(key, fn)
  }

  function unregister(key) {
    callbacks.delete(key)
  }

  async function refreshAll() {
    if (callbacks.size === 0) return
    isRefreshing.value = true
    const entries = Array.from(callbacks.entries())
    for (const [key, fn] of entries) {
      try {
        await fn()
      } catch (e) {
        console.error(`[coordinator] refresh failed for "${key}":`, e)
      }
    }
    isRefreshing.value = false
  }

  return { register, unregister, refreshAll, isRefreshing }
}
```

**验证**: 无编译错误

---

## Step 2: boService 增强

**文件**: `src/services/boService.js`

### 2a: 新增模块级 coordinator 引用和 setter（在 class 定义之前）

在 `class BOService extends BaseService {` 之前添加:

```javascript
let _coordinator = null

export function setRefreshCoordinator(coordinator) {
  _coordinator = coordinator
}
```

### 2b: create() 增强 (L24-L36)

在 `this._clearCache(objectType)` 之后添加:

```javascript
_coordinator?.refreshAll()
```

### 2c: update() 增强 (L89-L101)

在 `this._clearCache(objectType)` 之后添加:

```javascript
_coordinator?.refreshAll()
```

### 2d: delete() 增强 (L103-L114)

在 `this._clearCache(objectType)` 之后添加:

```javascript
_coordinator?.refreshAll()
```

### 2e: read() 增加 forceRefresh 参数 (L38-L53)

将:
```javascript
async read(objectType, id) {
  const cacheKey = this._getCacheKey(objectType, 'read', id)
  const cached = this._getCached(cacheKey)
  if (cached) return cached
```

改为:
```javascript
async read(objectType, id, options = {}) {
  const cacheKey = this._getCacheKey(objectType, 'read', id)
  if (!options.forceRefresh) {
    const cached = this._getCached(cacheKey)
    if (cached) return cached
  }
```

**验证**: 项目编译通过；现有调用 `boService.read(objectType, id)` 不受影响（options 默认 {}）

---

## Step 3: DetailPage CRUD 收敛到 boService

**文件**: `src/components/common/DetailPage/DetailPage.vue`

### 3a: 添加 boService import (L146 附近)

```javascript
import boService from '@/services/boService'
```

### 3b: fetchData() 改用 boService.read() (L789-L819)

替换整个 try 块中的 fetch 调用:

```javascript
// 替换前:
const response = await fetch(`/api/v2/bo/${props.objectType}/${props.id}`, {
  headers: { Authorization: ... }
})
if (!response.ok) { ... }
const result = await response.json()
if (result.success) { data.value = result.data; emit('loaded', result.data) }
else { error.value = result.message || '加载数据失败' }

// 替换后:
const result = await boService.read(props.objectType, props.id)
if (result.success) {
  data.value = result.data
  emit('loaded', result.data)
} else {
  error.value = result.message || '加载数据失败'
}
```

注意: boService._handleResponse 已处理 401（自动 logout）和 !response.ok，返回统一 `{ success, message }` 格式。

### 3c: handleSave() 改用 boService.create/update (L938-L992)

替换 fetch 调用:

```javascript
// 替换前:
const response = await fetch(url, { method, headers, body: JSON.stringify(payload) })
const result = await response.json()

// 替换后:
const result = isCreate
  ? await boService.create(props.objectType, payload)
  : await boService.update(props.objectType, props.id, payload)
```

保存后重新获取数据部分 (L959-L975):

```javascript
// 替换前:
const refreshResp = await fetch(`/api/v2/bo/${props.objectType}/${props.id}`, { headers })
const refreshResult = await refreshResp.json()

// 替换后:
const refreshResult = await boService.read(props.objectType, props.id, { forceRefresh: true })
```

### 3d: handleDelete() 改用 boService.delete() (L1006-L1012)

```javascript
// 替换前:
const response = await fetch(`/api/v2/bo/${props.objectType}/${props.id}`, { method: 'DELETE', headers })
const result = await response.json()

// 替换后:
const result = await boService.delete(props.objectType, props.id)
```

**验证**: 
- 创建/编辑/删除操作功能正常
- 保存后 DetailPage 数据刷新正常
- 401 自动跳转登录页

---

## Step 4: MOMP 绑定协调器

**文件**: `src/components/common/MultiObjectManagementPage/MultiObjectManagementPage.vue`

### 4a: 添加 import (L198 附近)

```javascript
import { provide } from 'vue'  // 已有 ref, watch 等，添加 provide
import { useRefreshCoordinator } from '@/composables/useRefreshCoordinator'
import { setRefreshCoordinator } from '@/services/boService'
```

### 4b: setup() 中创建协调器并 provide

在 `const scopeTreeRef = ref(null)` 之后添加:

```javascript
const coordinator = useRefreshCoordinator()
provide('refreshCoordinator', coordinator)
setRefreshCoordinator(coordinator)
```

**验证**: 项目编译通过

---

## Step 5: MetaListPage 注册回调

**文件**: `src/components/common/MetaListPage/MetaListPage.vue`

### 5a: 添加 inject (import 行)

在 import 中添加 `inject`:

```javascript
import { ref, computed, watch, onMounted, onUnmounted, inject } from 'vue'
```

### 5b: setup() 中注入协调器

在 `const emit = defineEmits(...)` 之后添加:

```javascript
const coordinator = inject('refreshCoordinator', null)
```

### 5c: onMounted 中注册回调

在现有 `onMounted(() => {` 块末尾添加:

```javascript
if (coordinator) {
  coordinator.register(`list:${props.objectType}`, forceRefresh)
}
```

### 5d: onUnmounted 中注销回调

在现有 `onUnmounted(() => {` 块中添加:

```javascript
if (coordinator) {
  coordinator.unregister(`list:${props.objectType}`)
}
```

**验证**: 切换 tab 时 register/unregister 正常

---

## Step 6: RelationScopeTree 注册回调

**文件**: `src/components/common/RelationScopeTree/RelationScopeTree.vue`

### 6a: 添加 inject (import 行)

在 import 中添加 `inject`:

```javascript
import { ref, computed, watch, onMounted, onUnmounted, inject } from 'vue'
```

### 6b: setup() 中注入协调器

添加:

```javascript
const coordinator = inject('refreshCoordinator', null)
```

### 6c: 添加 onMounted 注册

```javascript
onMounted(() => {
  if (coordinator) {
    coordinator.register('scopeTree', refresh)
  }
})
```

### 6d: 添加 onUnmounted 注销

```javascript
onUnmounted(() => {
  if (coordinator) {
    coordinator.unregister('scopeTree')
  }
})
```

**验证**: 刷新时 scopeTree 回调被调用

---

## Step 7: useMultiObjectPage 接入协调器

**文件**: `src/composables/useMultiObjectPage.js`

### 7a: 添加 coordinator 参数

修改函数签名:

```javascript
export function useMultiObjectPage(objectTypes, config = {}, coordinator = null) {
```

### 7b: handleGlobalAction 'refresh' case (L635-L637)

替换:

```javascript
case 'refresh':
  refreshTrigger.value++
  break
```

为:

```javascript
case 'refresh':
  if (coordinator) {
    coordinator.refreshAll()
  } else {
    refreshTrigger.value++
  }
  break
```

### 7c: handleImportSuccess (L660-L663)

替换:

```javascript
function handleImportSuccess() {
  importDialogVisible.value = false
  refreshTrigger.value++
}
```

为:

```javascript
function handleImportSuccess() {
  importDialogVisible.value = false
  if (coordinator) {
    coordinator.refreshAll()
  } else {
    refreshTrigger.value++
  }
}
```

### 7d: MOMP 传入 coordinator

在 MultiObjectManagementPage.vue 中修改 useMultiObjectPage 调用:

```javascript
// 替换前:
const page = useMultiObjectPage(...)

// 替换后:
const page = useMultiObjectPage(..., coordinator)
```

注意: coordinator 需在 useMultiObjectPage 调用之前创建。

**验证**: 刷新按钮和导入成功后，三处 UI 全部刷新

---

## Step 8: 清理旧 emit/watch 路径

**文件**: 多个文件

### 8a: MetaListPage.vue — 移除 emit('refresh')

- handleDetailCreated (L1215-L1227): 移除 `emit('refresh')`
- handleDetailSaved (L1229-L1234): 移除 `emit('refresh')`
- handleDetailDelete (L1236-L1240): 移除 `emit('refresh')`
- handleBatchActionWrapper (L711-L716): 移除整个函数，模板改回 `handleBatchAction`
- executeDelete: 移除 `emit('refresh')`
- defineEmits: 移除 `'refresh'`

### 8b: MultiObjectManagementPage.vue — 移除旧路径

- 模板: 移除 `@refresh="handleDataChange"`
- 移除 `handleDataChange()` 函数 (L311-L322)
- 移除 `watch(() => page.refreshTrigger, ...)` (L344-L353)
- watch combinedFilters: 移除 `metaListPageRef.value.refresh()` 调用（保留 setContextFilters）

### 8c: useMultiObjectPage.js — refreshTrigger 保留但降级

保留 `refreshTrigger` 定义和导出（向后兼容），但主路径已走 coordinator。

**验证**: 全量 CRUD + 批量删除 + 刷新按钮 E2E 测试通过

---

## 验证清单

| 操作 | 预期结果 |
|------|---------|
| 新建对象并保存 | 列表出现新记录 + 对象范围树刷新 + 关系范围刷新 |
| 编辑对象并保存 | 列表数据更新 + 对象范围树刷新 + 关系范围刷新 |
| 删除对象 | 列表移除记录 + 对象范围树刷新 + 关系范围刷新 |
| 批量删除 | 列表移除记录 + 对象范围树刷新 + 关系范围刷新 |
| 点击刷新按钮 | 列表刷新 + 对象范围树刷新 + 关系范围刷新 |
| 导入数据 | 列表刷新 + 对象范围树刷新 + 关系范围刷新 |
| 切换 tab | 新 tab 的 MetaListPage 注册回调，旧 tab 注销 |
| 独立页面（非MOMP） | boService mutation 后不 crash（coordinator 为 null） |
| 401 响应 | 自动跳转登录页（boService._handleResponse 处理） |
