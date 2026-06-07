# draftPersistService

> **服务路径**: `src/services/draftPersistService.js`
> **创建日期**: 2026-06-06
> **创建者**: AI Agent (Trae)
> **关联 PR**: PR 4 (FR-UI-005)
> **关联 spec**: [spec-fr-ui-003-004-005-useMetaList-refactor.md v1.5.0](file:///d:/filework/excel-to-diagram/docs/specs/spec-fr-ui-003-004-005-useMetaList-refactor.md) §6
> **测试覆盖**: 17 个单测 ([draftPersistService.spec.js](file:///d:/filework/excel-to-diagram/src/services/__tests__/draftPersistService.spec.js))

---

## 1. 服务目的

将 `useMetaList.js` 中关于"收集 drafts / 构造 payload / 保存草稿"的纯函数业务逻辑抽取到独立 service。

**业务场景**：用户编辑列表行（修改字段、添加新行）后，点击"保存"按钮，系统收集所有 draft 编辑，调用后端 `batch_save` Action 批量保存。

## 2. 公开 API

### 2.1 `hasDraftChanges(fields, initialValues)`

**作用**：检查是否包含已变更字段

**业务规则**：
1. 跳过 `_` 开头的字段（系统字段）
2. 比较 `fields[key]` vs `initialValues[key]`

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `fields` | `Object` | ✅ | 用户编辑后的字段 |
| `initialValues` | `Object` | ✅ | 行初始值 |

**返回**：`boolean`（true 表示有变更）

### 2.2 `buildDraftPayload(fields, row, isNewRow)`

**作用**：构造单行 draft payload

**业务规则**：
1. **新建行**：从 `row` 中保留 `*_id` 字段（parent_id 等）
2. **更新行**：仅使用 `fields`
3. 跳过 `_` 开头的字段
4. 跳过 `row.id` 字段
5. `fields` 中的字段覆盖 `row` 中的字段

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `fields` | `Object` | ✅ | 用户编辑字段 |
| `row` | `Object` | ❌ | 原始行（仅新建行使用）|
| `isNewRow` | `boolean` | ✅ | 是否新建行 |

**返回**：`Object` payload

### 2.3 `collectDrafts(draftValues, data)`

**作用**：收集 drafts（业务逻辑下沉）

**流程**：
1. 遍历 `draftValues`
2. 对每行判断是否包含变更（`hasDraftChanges`）
3. 无变更：标记 `toRemove`
4. 有变更：构造 payload，加入 `drafts`

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `draftValues` | `Map` | ✅ | 草稿 Map |
| `data` | `Array` | ✅ | 表格数据（数组）|

**返回**：

```typescript
{
  drafts: Array<{row_id, is_new, fields}>,  // 待保存
  toRemove: Array<{rowId, removeFromData: boolean}>,  // 待清理
}
```

**注意**：非 `__new_` 行的 `initialValues` 为 `{}`（**业务规则保留**），所以任何非空 fields 都视为有变更。这是 useMetaList 原代码行为（spec v1.5.0 §6.1.3 字节级一致要求）。

### 2.4 `saveAllDrafts({objectType, draftValues, data, callPost, showMessage})`

**作用**：主入口 - 保存所有草稿（业务逻辑下沉）

**完整流程**：
1. 收集 `drafts` + `toRemove`（`collectDrafts`）
2. 清理 `toRemove`（从 `data` + `draftValues` 移除）
3. 如果 `drafts` 为空，提前返回 `{success: true, created: 0, updated: 0}`
4. 调用后端 `batch_save`（`callPost`）
5. 成功：显示成功消息，返回 `{success, created, updated}`
6. 失败：返回 `{success, error, failures}`

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `objectType` | `string` | ✅ | 实体类型 |
| `draftValues` | `Map` | ✅ | 草稿 Map |
| `data` | `ref \| array` | ✅ | 表格数据（支持 ref.value 自动解构）|
| `callPost` | `Function` | ✅ | `useBoAction.callPost`（注入式依赖）|
| `showMessage` | `Object` | ❌ | 注入式消息服务（默认 null 不显示）|

**返回**：

```typescript
Promise<{
  success: boolean,
  created: number,
  updated: number,
  error?: string,
  failures?: Array,
}>
```

**示例**：

```javascript
import { saveAllDrafts } from '@/services/draftPersistService'

const { callPost } = await import('@/composables/useBoAction')
const result = await saveAllDrafts({
  objectType: 'order',
  draftValues: draftValues.value,
  data: data,  // ref 或 array 均可
  callPost,
  showMessage: ElMessage,
})

if (result.success) {
  // 清空草稿 + refresh
}
```

### 2.5 `getDraftCreates(draftValues, data)`

**作用**：获取所有待创建的新增行 payload

**用途**：供父组件收集子数据后调用 `deepInsert` 使用

**业务规则**：
1. 仅处理 `rowId` 以 `__new_` 开头的新建行
2. 跳过未变更的草稿
3. 跳过 `_` 开头的字段
4. 跳过 `id` 字段

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `draftValues` | `Map` | ✅ | 草稿 Map |
| `data` | `Array` | ✅ | 表格数据（数组）|

**返回**：`Array` 待创建行的 payload 数组

## 3. 业务规则

### 3.1 draft 状态机

```
[未编辑] ──编辑──→ [draftValues 中] ──保存──→ [后端]
                     ↓
                [无变化] → [移除]
                [有变化] → [drafts] → [后端 batch_save]
```

### 3.2 新建行 vs 更新行

| 维度 | 新建行（`__new_*`）| 更新行 |
|------|-----------------|--------|
| `initialValues` 查找 | ✅ 查找 | ❌ 不查找（默认为 `{}`）|
| `*_id` 保留 | ✅ 从 row 保留 | ❌ 仅 fields |
| 数据清理 | ✅ 成功保存后从 data 移除 | ❌ 保留原数据 |

### 3.3 batch_save 协议

```javascript
// 请求
{
  object_type: 'order',
  drafts: [
    { row_id: 1, is_new: false, fields: {name: 'changed'} },
    { row_id: '__new_1', is_new: true, fields: {name: 'new order', parent_id: 5} }
  ]
}

// 响应
{
  success: true,
  data: {
    created: [{id: 100, ...}, ...],
    updated: [{id: 1, ...}, ...],
    failures: []
  }
}
```

## 4. 注入式依赖

### 4.1 `callPost(actionName, params)`

- 来源：`useBoAction.callPost`（动态 import 避免循环依赖）
- 作用：发送 POST 请求到 `/api/v2/action/{actionName}`
- 接口契约：返回 `{success, data, message, code}` 格式

### 4.2 `showMessage`（可选）

- 来源：`ElMessage` 或自定义消息服务
- 作用：成功时显示 toast
- 不传：静默（不显示消息）

### 4.3 `data`（ref 或 array）

- 自动识别：ref 对象 `{value: [...]}` 或直接 array
- 通过 `data?.value !== undefined ? data.value : data` 兼容两种

## 5. 单测矩阵（17 个用例）

| # | 用例 | 覆盖点 |
|:-:|------|------|
| TC-1 | `hasDraftChanges` `_` 开头字段被跳过 | 边界条件 |
| TC-2 | `hasDraftChanges` 值相同无变更 | 业务规则 |
| TC-3 | `hasDraftChanges` 值不同有变更 | 业务规则 |
| TC-4 | `buildDraftPayload` 新建行保留 `*_id` | 业务规则 |
| TC-5 | `buildDraftPayload` 更新行仅 fields | 业务规则 |
| TC-6 | `buildDraftPayload` 跳过 `_` 开头 | 边界条件 |
| TC-7 | `buildDraftPayload` 跳过 row 中 id | 边界条件 |
| TC-8 | `collectDrafts` 空 drafts 返回空 | 边界条件 |
| TC-9 | `collectDrafts` `__new_` 行未变更 → toRemove | 业务规则 |
| TC-10 | `collectDrafts` 混合 new/非 new 行的部分变更 | 业务规则 |
| TC-11 | `saveAllDrafts` 空 draftValues 提前返回 | 边界条件 |
| TC-12 | `saveAllDrafts` 全部未变更时返回空 | 业务规则 |
| TC-13 | `saveAllDrafts` 成功返回 created/updated | 主入口 |
| TC-14 | `saveAllDrafts` 失败返回 error | 错误处理 |
| TC-15 | `getDraftCreates` 跳过非 `__new_` 行 | 业务规则 |
| TC-16 | `getDraftCreates` 跳过未变更 | 业务规则 |
| TC-17 | `getDraftCreates` 包含已变更的新行 | 主入口 |

## 6. 调用方

### 6.1 useMetaList.js

```javascript
// src/composables/useMetaList.js L2042
import { saveAllDrafts as _saveAllDraftsSvc, getDraftCreates as _getDraftCreatesSvc } from '@/services/draftPersistService'

function getDraftCreates() {
  return _getDraftCreatesSvc(draftValues.value, data.value)
}

async function saveDraftValues() {
  loading.value = true
  try {
    const { callPost } = await import('@/composables/useBoAction')
    const result = await _saveAllDraftsSvc({
      objectType: objectType.value,
      draftValues: draftValues.value,
      data: data,
      callPost,
      showMessage: ElMessage,
    })
    if (result.success) {
      draftValues.value.clear()
      draftValues.value = new Map()
      await refresh()
    } else {
      throw new Error(result.error || '保存失败')
    }
  } catch (e) {
    handleError('保存修改', e)
  } finally {
    loading.value = false
  }
}
```

## 7. 设计决策

### 7.1 为什么分 5 个函数（而不是 1 个大函数）？

- **可测试性**：每个函数独立测试
- **可复用性**：`hasDraftChanges` / `buildDraftPayload` 可被其他 service 复用
- **可读性**：每个函数单一职责

### 7.2 为什么 `data` 接受 ref 或 array？

- `saveAllDrafts` 内部使用 `data.value`（如果 data 是 ref）
- `collectDrafts` 需要纯 array（`.find` 调用）
- `saveAllDrafts` 兼容两种调用方式

### 7.3 为什么 `__new_` 行才查找 initialValues？

- 这是 useMetaList 原代码行为（spec v1.5.0 §6.1.3 字节级一致要求）
- 业务逻辑：非 `__new_` 行（已保存的行）认为一定有变更（用户编辑过）
- 不修改原行为，防止破坏现有功能

## 8. 错误处理

| 场景 | 行为 |
|------|------|
| `draftValues` 为空 | 提前返回 `{success: true, created: 0, updated: 0}` |
| `callPost` 抛异常 | 返回 `{success: false, error: e.message}` |
| `callPost` 返回 `success: false` | 返回 `{success: false, error, failures}` |
| `data` 为 null/undefined | 视为空数组 |
| `data.value` 为空 | 视为空数组 |

## 9. 未来扩展

- [ ] 支持乐观锁（version 字段）
- [ ] 支持 partial update（仅更新变更字段）
- [ ] 支持批量操作的原子性保证（事务）
- [ ] 支持失败重试（指数退避）

## 10. 变更记录

| 版本 | 日期 | 变更内容 | 作者 |
|:---:|------|---------|------|
| 1.0.0 | 2026-06-06 | 初稿；从 useMetaList.js L2071-2174 抽取 | AI Agent (Trae) |
