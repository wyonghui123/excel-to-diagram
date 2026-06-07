# Phase B 详细实施手册 (phase-b-implementation.md)

> **目的**：将 useMetaList 重构 spec 转化为 8 个 PR 的可执行详细步骤
> **创建日期**：2026-06-06
> **依据 spec**：[spec-fr-ui-003-004-005-useMetaList-refactor.md v1.5.0](file:///d:/filework/excel-to-diagram/docs/specs/spec-fr-ui-003-004-005-useMetaList-refactor.md)
> **工作量**：12.5d（4 PR 必须 + 4 PR 可选）
> **执行模式**：每 PR 完成后立即跑 `python d:\filework\test.py --failed` 验证零回归

---

## 1. 实施路线图（8 PR / 12.5d）

| PR | 工作量 | 价值 | 状态 | 立即执行 |
|:-:|:-----:|:----:|:----:|:----:|
| **PR 8** | 0.5d | ⭐⭐⭐⭐⭐ | 🟠 待实施 | ✅ |
| **PR 4** | 2d | ⭐⭐⭐⭐⭐ | 🟠 待实施 | ✅ |
| **PR 5** | 2d | ⭐⭐⭐⭐ | 🟠 待实施 | ✅ |
| **PR 6** | 1d | ⭐⭐⭐ | 🟠 待实施 | 🟠 |
| **PR 7** | 1d | ⭐⭐⭐ | 🟠 待实施 | 🟠 |
| **PR 9** | 2d | ⭐⭐⭐⭐ | 🟠 待实施 | 🟠 |
| **PR 10** | 1d | ⭐⭐⭐⭐ | 🟠 待实施 | 🟠 |
| **PR 11+** | 3d | ⭐⭐⭐ | 🟠 待实施 | 🟢 |

**最小可执行单元（1 周内 4.5d）**：PR 8 + PR 4 + PR 5

---

## 2. PR 8 详细步骤（0.5d - 立即）

### 2.1 目标

清理 6 死代码 stub，节省 4.5KB / 226 行代码。

### 2.2 死代码 stub 确认清单

| # | 文件 | 大小 | 行数 | 引用情况 |
|:-:|------|:---:|:---:|---------|
| 1 | [src/views/SystemManagement/UserGroupManagement.vue](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/UserGroupManagement.vue) | 720B | 35 | **仅 ComponentComparison.vue 字符串引用**（非 import）|
| 2 | RoleManagement.vue | 825B | 40 | **0 引用** |
| 3 | UserManagement.vue | 500B | 28 | **0 引用** |
| 4 | VersionManagement.vue | 1,351B | 61 | **0 引用**（但有 VersionContextSelector 引用）|
| 5 | EnumValueList.vue | 681B | 34 | **仅 ComponentComparison.vue 字符串引用** |
| 6 | ProductManagement.vue | 509B | 28 | **0 引用** |
| **总计** | | **4,586B** | **226 行** | — |

### 2.3 验证步骤（删除前必做）

```bash
# 1. 确认 0 import 引用
rg "from ['\"].*(UserGroupManagement|RoleManagement|UserManagement|VersionManagement|EnumValueList|ProductManagement)['\"]" src/ --type vue --type js
# 结果：0 行（仅 ComponentComparison.vue 字符串引用，删除 ComponentComparison 字符串即可）

# 2. 确认 0 路由引用
rg "UserGroupManagement|RoleManagement|UserManagement|VersionManagement|EnumValueList|ProductManagement" src/router/
# 结果：0 行

# 3. 确认菜单 ComponentComparison 字符串位置
rg "'SystemManagement/(UserGroupManagement|RoleManagement|UserManagement|VersionManagement|EnumValueList|ProductManagement)'" src/
# 结果：仅 EnumValueList（v1.5.0 §15 列举错误，已确认实际有 2 处 EnumValueList 字符串）
```

### 2.4 实施步骤

```bash
# 步骤 1：删除 6 个死代码 stub
rm src/views/SystemManagement/UserGroupManagement.vue
rm src/views/SystemManagement/RoleManagement.vue
rm src/views/SystemManagement/UserManagement.vue
rm src/views/SystemManagement/VersionManagement.vue
rm src/views/SystemManagement/EnumValueList.vue
rm src/views/SystemManagement/ProductManagement.vue

# 步骤 2：清理 ComponentComparison.vue 字符串引用（仅 EnumValueList）
# 在 src/views/ComponentComparison.vue 中删除 L5154 字符串
#   "component: 'SystemManagement/EnumValueList'"
# 同时 L5218 字符串 "SystemManagement/EnumValueList"

# 步骤 3：跑测试
cd d:\filework\excel-to-diagram
python d:\filework\test.py --failed --retries=0 --reporter=line
# 预期：0 个测试失败（如果有 EnumValue 相关 E2E 失败，需单独看）
```

### 2.5 风险评估

| 风险 | 概率 | 缓解 |
|------|:---:|------|
| ComponentComparison.vue 隐藏引用 | 中 | 删除前 grep 确认 |
| 子菜单配置 | 低 | 检查 menu config |
| 路由配置 | 低 | grep 确认 |
| 单元测试 import | 低 | grep 确认 |

### 2.6 验收标准

- [ ] 6 文件删除
- [ ] ComponentComparison.vue 字符串引用清理
- [ ] 0 测试失败
- [ ] 0 E2E 失败
- [ ] git commit + push

---

## 3. PR 4 详细步骤（2d - 6 service 下沉）

### 3.1 目标

将 useMetaList.js 三个高 ROI 业务下沉点（99 行）抽取到 2 个新 service。

### 3.2 三个下沉点（基于实际代码审计）

| 下沉点 | 行号 | 行数 | 复杂度 | 抽到 service |
|:------:|:---:|:---:|:-----:|------------|
| `_suggestKeyTemplateCode` | L1931-1977 | 47 行 | 中 | `keyTemplateService.js` |
| `saveDraftValues` 业务逻辑 | L2099-2162 | 64 行（含 HTTP 41 行）| 高 | `draftPersistService.js` |
| `getDraftCreates` | L2071-2094 | 24 行 | 低 | `draftPersistService.js` |
| **总计** | | **135 行** | | **2 service** |

**修正 spec v1.5.0 §1.3**：实际下沉 3 个函数 = 135 行（spec 假设 99 行）

### 3.3 service 1: `keyTemplateService.js`

**位置**：`src/services/keyTemplateService.js`

**公开 API**：

```javascript
/**
 * 提取新建行的 parent_id 字段（用于键模板推导）
 * @param {Object} filterValues - 列表过滤值
 * @param {Object} newRow - 新建行数据
 * @param {Function} isVueInternalProp - Vue 内部 prop 判断
 * @returns {Object} parentParams
 */
export function extractParentParams(filterValues, newRow, isVueInternalProp) {
  const parentParams = {}
  Object.keys(filterValues)
    .filter(key => !isVueInternalProp(key) && key.endsWith('_id'))
    .forEach(key => { parentParams[key] = filterValues[key] })
  Object.keys(newRow)
    .filter(key => !key.startsWith('_') && key.endsWith('_id') && key !== 'id')
    .forEach(key => {
      if (!(key in parentParams) && newRow[key] != null) {
        parentParams[key] = newRow[key]
      }
    })
  return parentParams
}

/**
 * 检查 parentParams 是否包含无效 parent_id
 * @param {Object} parentParams
 * @returns {boolean}
 */
export function hasInvalidParentId(parentParams) {
  return Object.values(parentParams).some(
    v => v === 'new' || v === '' || v === null || v === undefined
  )
}

/**
 * 应用建议的 code 到新建行 + draftValues
 * @param {Object} newRow
 * @param {string} codeValue
 * @param {Map} draftValues - useMetaList 的 draftValues ref.value
 * @returns {void} 直接修改 newRow 和 draftValues
 */
export function applyKeyTemplateSuggestion(newRow, codeValue, draftValues) {
  newRow.code = codeValue
  newRow._initialValues = { ...(newRow._initialValues || {}), code: codeValue }
  
  const rowDrafts = draftValues.get(newRow.id)
  if (rowDrafts) {
    rowDrafts.code = codeValue
    // 注意：不能在 service 内触发响应式（service 是纯函数）
    // 由调用方负责 set
  }
  return { newRow, shouldUpdateDraft: !!rowDrafts }
}

/**
 * 主入口：建议 key template code（业务逻辑下沉）
 * @param {Object} newRow
 * @param {Object} filterValues
 * @param {Map} draftValues
 * @param {Object} boService
 * @param {Object} config
 * @param {Function} isVueInternalProp
 * @returns {Promise<{code?: string, skipped?: string, error?: Error}>}
 */
export async function suggestKeyTemplateCode(newRow, filterValues, draftValues, boService, config, isVueInternalProp) {
  try {
    const parentParams = extractParentParams(filterValues, newRow, isVueInternalProp)
    if (Object.keys(parentParams).length === 0) return { skipped: 'no_parent' }
    
    if (hasInvalidParentId(parentParams)) {
      if (config.debug) {
        console.log('[keyTemplateService] Skipped: parent record not yet saved')
      }
      return { skipped: 'invalid_parent' }
    }
    
    const result = await boService.suggestKeyTemplateCode(
      newRow._objectType || newRow.objectType,
      {},
      parentParams
    )
    
    if (result.success && result.data?.code) {
      const applyResult = applyKeyTemplateSuggestion(newRow, result.data.code, draftValues)
      return { code: result.data.code, shouldUpdateDraft: applyResult.shouldUpdateDraft }
    }
    return { skipped: 'no_code' }
  } catch (e) {
    if (config.debug) {
      console.warn('[keyTemplateService] Error:', e)
    }
    return { error: e }
  }
}
```

**单测矩阵**（`src/services/__tests__/keyTemplateService.spec.js`）：

| 用例 | 输入 | 期望输出 |
|------|------|---------|
| extractParentParams: 仅有 filterValues | filter={user_id:1}, newRow={} | {user_id:1} |
| extractParentParams: 仅有 newRow | filter={}, newRow={order_id:5} | {order_id:5} |
| extractParentParams: 合并 + 不覆盖 | filter={user_id:1}, newRow={order_id:5} | {user_id:1, order_id:5} |
| extractParentParams: 跳过 Vue 内部 | filter={$el:1}, newRow={} | {} |
| extractParentParams: 跳过 _ 开头 | newRow={_id:1} | {} |
| extractParentParams: 跳过 id | newRow={id:1} | {} |
| hasInvalidParentId: 'new' | {user_id:'new'} | true |
| hasInvalidParentId: '' | {user_id:''} | true |
| hasInvalidParentId: null | {user_id:null} | true |
| hasInvalidParentId: undefined | {user_id:undefined} | true |
| hasInvalidParentId: 正常 | {user_id:1} | false |
| applyKeyTemplateSuggestion: 有 drafts | newRow={id:1}, drafts Map | shouldUpdateDraft=true |
| applyKeyTemplateSuggestion: 无 drafts | newRow={id:1}, drafts 空 | shouldUpdateDraft=false |
| suggestKeyTemplateCode: 完整流程 | mock boService | 返回 code |
| suggestKeyTemplateCode: 失败 | mock throw | 返回 error |

**预期**：15 个单测全过

### 3.4 service 2: `draftPersistService.js`

**位置**：`src/services/draftPersistService.js`

**公开 API**：

```javascript
/**
 * 检查是否包含已变更字段
 * @param {Object} fields - 用户编辑后的字段
 * @param {Object} initialValues - 行初始值
 * @returns {boolean}
 */
export function hasDraftChanges(fields, initialValues) {
  return Object.keys(fields).some(key => {
    if (key.startsWith('_')) return false
    return fields[key] !== initialValues[key]
  })
}

/**
 * 构造单行 draft payload（业务逻辑下沉）
 * @param {Object} fields - 用户编辑字段
 * @param {Object} row - 原始行
 * @param {boolean} isNewRow
 * @returns {Object} payload
 */
export function buildDraftPayload(fields, row, isNewRow) {
  const payload = {}
  if (isNewRow && row) {
    // 新建行：保留 * _id 字段
    Object.keys(row).forEach(key => {
      if (key.startsWith('_') || key === 'id') return
      if (fields.hasOwnProperty(key)) return
      if (key.endsWith('_id') && row[key] != null && row[key] !== '') {
        payload[key] = row[key]
      }
    })
  }
  // 覆盖/更新
  for (const [fieldName, newValue] of Object.entries(fields)) {
    if (fieldName.startsWith('_')) continue
    payload[fieldName] = newValue
  }
  return payload
}

/**
 * 收集 drafts（业务逻辑下沉）
 * @param {Map} draftValues
 * @param {Array} data
 * @returns {Array<{row_id, is_new, fields, shouldRemove}>
 *   {row_id, is_new, fields, shouldRemove: true} 表示需删除空 draft
 * }
 */
export function collectDrafts(draftValues, data) {
  const drafts = []
  const toRemove = []  // 空 draft
  for (const [rowId, fields] of draftValues.entries()) {
    const rowIdStr = String(rowId)
    const isNewRow = rowIdStr.startsWith('__new_')
    const row = isNewRow ? data.find(r => String(r.id) === rowIdStr) : null
    const initialValues = row?._initialValues || {}
    
    if (!hasDraftChanges(fields, initialValues)) {
      if (isNewRow) {
        toRemove.push({ rowId: rowIdStr, removeFromData: true })
      }
      toRemove.push({ rowId, removeFromData: false })
      continue
    }
    
    const payload = buildDraftPayload(fields, row, isNewRow)
    drafts.push({ row_id: rowId, is_new: isNewRow, fields: payload })
  }
  return { drafts, toRemove }
}

/**
 * 主入口：保存所有草稿（业务逻辑下沉）
 * @param {Object} params
 * @param {string} params.objectType
 * @param {Map} params.draftValues
 * @param {Array} params.data
 * @param {Function} params.callPost - useBoAction.callPost（注入式依赖）
 * @param {Function} params.showMessage - ElMessage（注入式依赖）
 * @returns {Promise<{success: boolean, created: number, updated: number, error?: string}>}
 */
export async function saveAllDrafts({ objectType, draftValues, data, callPost, showMessage }) {
  if (draftValues.size === 0) return { success: true, created: 0, updated: 0 }
  
  const { drafts, toRemove } = collectDrafts(draftValues, data)
  
  // 清理空 drafts
  for (const r of toRemove) {
    if (r.removeFromData) {
      data.value = data.value.filter(row => String(row.id) !== r.rowId)
    }
    draftValues.delete(r.rowId)
  }
  
  if (drafts.length === 0) return { success: true, created: 0, updated: 0 }
  
  try {
    const r = await callPost('batch_save', {
      object_type: objectType,
      drafts,
    })
    
    if (r.success) {
      const createdCount = (r.data?.created || []).length
      const updatedCount = (r.data?.updated || []).length
      if (showMessage) showMessage.success(`成功创建 ${createdCount} 项, 更新 ${updatedCount} 项`)
      return { success: true, created: createdCount, updated: updatedCount }
    }
    
    const failures = r.data?.failures || []
    const errorMsg = failures.length > 0
      ? `${failures.length} 项失败: ${failures[0].message}`
      : (r.message || '保存失败')
    return { success: false, error: errorMsg, failures }
  } catch (e) {
    return { success: false, error: e.message }
  }
}

/**
 * 获取所有待创建的新增行 payload
 * @param {Map} draftValues
 * @param {Array} data
 * @returns {Array} 待创建行的 payload 数组
 */
export function getDraftCreates(draftValues, data) {
  const creates = []
  for (const [rowId, fields] of draftValues.entries()) {
    const rowIdStr = String(rowId)
    if (!rowIdStr.startsWith('__new_')) continue

    const row = data.find(r => String(r.id) === rowIdStr)
    const initialValues = row?._initialValues || {}

    if (!hasDraftChanges(fields, initialValues)) continue

    const payload = {}
    for (const [fieldName, newValue] of Object.entries(fields)) {
      if (fieldName.startsWith('_') || fieldName === 'id') continue
      payload[fieldName] = newValue
    }
    creates.push(payload)
  }
  return creates
}
```

**单测矩阵**（`src/services/__tests__/draftPersistService.spec.js`）：

| # | 用例 | 期望 |
|:-:|------|------|
| 1 | hasDraftChanges: _ 开头 | false |
| 2 | hasDraftChanges: 值相同 | false |
| 3 | hasDraftChanges: 值不同 | true |
| 4 | buildDraftPayload: 新建行+保留 _id | payload 包含 parent_id |
| 5 | buildDraftPayload: 更新行+不保留 _id | payload 仅 fields |
| 6 | buildDraftPayload: 跳过 _ | ✅ |
| 7 | buildDraftPayload: 跳过 id | ✅ |
| 8 | collectDrafts: 空 drafts | {drafts:[], toRemove:[]} |
| 9 | collectDrafts: 全部未变更 | {drafts:[], toRemove:[...]} |
| 10 | collectDrafts: 部分变更 | {drafts:[...], toRemove:[]} |
| 11 | saveAllDrafts: 空 draftValues | {success:true, created:0} |
| 12 | saveAllDrafts: 全部未变更 | {success:true, created:0} |
| 13 | saveAllDrafts: 成功 | {success:true, created:N} |
| 14 | saveAllDrafts: 失败 | {success:false, error:...} |
| 15 | getDraftCreates: 跳过非 new 行 | ✅ |
| 16 | getDraftCreates: 跳过未变更 | ✅ |
| 17 | getDraftCreates: 包含 payload | ✅ |

**预期**：17 个单测全过

### 3.5 useMetaList.js 修改

**修改 1：导入 service**

```javascript
// 原 L25-50
import { ElMessage, ElMessageBox } from 'element-plus'
import { boService } from '@/services/bo'
// ... 等

// 新增 L51-52
import { suggestKeyTemplateCode as _suggestKeyTemplateCodeSvc } from '@/services/keyTemplateService'
import { saveAllDrafts as _saveAllDraftsSvc, getDraftCreates as _getDraftCreatesSvc } from '@/services/draftPersistService'
```

**修改 2：替换 _suggestKeyTemplateCode**

```javascript
// 原 L1931-1977（47 行）→ 新（5 行）
async function _suggestKeyTemplateCode(newRow) {
  const result = await _suggestKeyTemplateCodeSvc(
    newRow,
    filterValues.value,
    draftValues.value,
    boService,
    config,
    isVueInternalProp
  )
  // 触发响应式（service 是纯函数）
  if (result.shouldUpdateDraft) {
    draftValues.value = new Map(draftValues.value)
  }
}
```

**修改 3：替换 saveDraftValues**

```javascript
// 原 L2099-2174（76 行）→ 新（10 行）
async function saveDraftValues() {
  loading.value = true
  try {
    const result = await _saveAllDraftsSvc({
      objectType: objectType.value,
      draftValues: draftValues.value,
      data: data,
      callPost: (await import('@/composables/useBoAction')).callPost,
      showMessage: ElMessage,
    })
    if (result.success) {
      draftValues.value.clear()
      draftValues.value = new Map()
      await refresh()
    } else {
      handleError('保存修改', new Error(result.error))
    }
  } catch (e) {
    handleError('保存修改', e)
  } finally {
    loading.value = false
  }
}
```

**修改 4：替换 getDraftCreates**

```javascript
// 原 L2071-2094（24 行）→ 新（1 行）
function getDraftCreates() {
  return _getDraftCreatesSvc(draftValues.value, data.value)
}
```

### 3.6 行数变化预期

| 文件 | 原行数 | 新行数 | 减少 |
|------|:-----:|:-----:|:---:|
| useMetaList.js | 2,499 | 2,384 | **-115** |
| keyTemplateService.js | 0 | 90 | +90 |
| draftPersistService.js | 0 | 100 | +100 |
| keyTemplateService.spec.js | 0 | 130 | +130 |
| draftPersistService.spec.js | 0 | 170 | +170 |
| **总代码行** | **2,499** | **2,874** | **+375（测试覆盖）** |

**核心**：useMetaList.js 减少 115 行 = **-4.6%**（spec 假设 5-6% 减少率）

### 3.7 风险评估

| 风险 | 概率 | 缓解 |
|------|:---:|------|
| 响应式更新丢失（draftValues set） | 中 | useMetaList 内手动 set |
| callPost 动态 import 时序 | 中 | 保留 dynamic import |
| ElMessage 注入式依赖破坏 | 低 | 显式传入 |
| 错误处理不一致 | 中 | service 返回 {success, error}，调用方 handleError |

### 3.8 验收标准

- [ ] 2 service 文件创建（keyTemplateService.js / draftPersistService.js）
- [ ] 32 个单测全过
- [ ] useMetaList.js 减少 ≥100 行
- [ ] 0 行为变化（所有 75+ API 契约保持）
- [ ] 集成测试通过
- [ ] E2E 关键路径通过（详情/编辑/保存）

---

## 4. PR 5 详细步骤（2d - 接口契约保护）

### 4.1 目标

建立 35 文件的 useMetaList 接口契约守卫，确保重构不破坏行为。

### 4.2 接口契约 3 层

| 层 | 工具 | 范围 |
|----|------|------|
| **L1 单测** | Vitest | 75+ API 行为快照（基于现有 useMetaList.batch.spec.js / useMetaList.integration.spec.js）|
| **L2 集成测试** | Vitest + jsdom | 35 文件 × 4 displayMode 行为 |
| **L3 E2E** | Playwright | 关键路径（详情/编辑/保存/ValueHelp） |

### 4.3 L1 单测：35 文件契约矩阵

| 文件 | useMetaList 解构 API | 测试矩阵 |
|------|---------------------|---------|
| MetaListPage.vue | 全部 75+ | 行为快照 |
| AuditLogManagement.vue | formatDate | 1 |
| GenericObjectList.vue | 透传 | 集成 |
| 6 死代码 stub | 0 | PR 8 删除后跳过 |
| ObjectPage/AssociationSection.vue | 3 处嵌入 | displayMode='embedded' 3 场景 |
| ObjectChildSection.vue | 双模式 | useMetaList=true/false |
| SearchHelpDialog.vue | flat/tree_flat | 2 displayMode |
| AssignmentDialog.vue | dialog | 1 |
| MultiObjectManagementPage.vue | 透传 | 集成 |

**新增测试文件**：

```
src/composables/__tests__/
├── useMetaList.api_contract.spec.js     ← 75+ API 数量+签名
├── useMetaList.behavior.spec.js         ← 行为不变式
├── useMetaList.batch.spec.js            ← 已存在（保留）
├── useMetaList.integration.spec.js      ← 已存在（保留）
└── useMetaList.displaymode.spec.js      ← 4 displayMode
```

### 4.4 L2 集成测试：4 displayMode

```javascript
// useMetaList.displaymode.spec.js
import { mount } from '@vue/test-utils'
import MetaListPage from '@/components/common/MetaListPage/MetaListPage.vue'

describe('useMetaList 4 displayMode', () => {
  test('page mode: 完整功能（工具栏 + 详情 + 导入导出）', async () => {
    // mount MetaListPage 不传 displayMode
    // 验证：toolbar 可见、详情按钮、导入导出
  })
  
  test('embedded mode: 嵌入模式（无外壳）', async () => {
    // mount 时传 displayMode='embedded'
    // 验证：无 toolbar、外壳 class 不存在
  })
  
  test('dialog mode: 弹窗模式', async () => {
    // mount 时传 displayMode='dialog'
    // 验证：无 draw header
  })
  
  test('default mode: 兜底为 page', async () => {
    // 不传 displayMode
    // 验证：行为等同 page
  })
})
```

### 4.5 L3 E2E：关键路径

```javascript
// e2e/specs/useMetaList-5-layer-link.spec.js
test('ValueHelp 5 层链路: Field → SearchHelp → MetaListPage → 选择 → 回填', async () => {
  // 1. 打开 user_group 详情页
  // 2. 点击 ValueHelp 字段
  // 3. 验证 SearchHelpDialog 打开
  // 4. 验证内嵌 MetaListPage 渲染
  // 5. 选择 row
  // 6. 验证回填到字段
})
```

### 4.6 验收标准

- [ ] useMetaList.api_contract.spec.js 全过（75+ API 数量+签名）
- [ ] useMetaList.behavior.spec.js 全过（10 行为不变式）
- [ ] useMetaList.displaymode.spec.js 全过（4 displayMode）
- [ ] e2e/useMetaList-5-layer-link.spec.js 全过
- [ ] CI 集成（任何 PR 必跑）
- [ ] 0 现有测试失败

---

## 5. PR 6 + PR 7 详细步骤（2d - 集成 + E2E）

### 5.1 PR 6 集成 + 文档（1d）

**任务**：
- 集成测试：模拟完整场景
- 文档更新：services/README.md + useMetaList.md
- 移除 useMetaList.js 中重复的纯函数（已下沉到 service）

**新增文档**：

```
docs/services/
├── keyTemplateService.md
├── draftPersistService.md
└── useMetaList.md  ← 重构后版本
```

### 5.2 PR 7 E2E 验证（1d）

**任务**：
- 21 个 E2E 关键路径（基于 spec v1.5.0 §8.2）
- 跑 `python d:\filework\test.py --all --force`
- 0 回归确认

### 5.3 验收标准

- [ ] 21 个 E2E 全过
- [ ] test.py 全量 0 回归
- [ ] 3 个新服务文档
- [ ] useMetaList.md 重构后版本

---

## 6. PR 9 + PR 10 详细步骤（3d - Consumer 契约）

### 6.1 PR 9 5 consumer 契约（2d）

**5 consumer 集成测试**：

| Consumer | 集成测试矩阵 |
|----------|-------------|
| ObjectPage/AssociationSection.vue | 3 处嵌入（m2m/annotation/default）|
| ObjectChildSection.vue | 双模式（useMetaList=true/false）|
| SearchHelpDialog.vue | 3 displayMode（flat/tree_flat/tree）|
| AssignmentDialog.vue | dialog 模式 |
| MultiObjectManagementPage.vue | useMultiObjectPage 集成 |

### 6.2 PR 10 ValueHelp 5 层链路 E2E（1d）

**任务**：
- E2E: Field → ValueHelpField → SearchHelpDialog → MetaListPage → 选择回填
- E2E: 4 displayMode 端到端
- E2E: 6 fetcher 自定义函数

### 6.3 验收标准

- [ ] 5 consumer × 4 displayMode = 20 集成测试
- [ ] 6 fetcher 模式 E2E
- [ ] ValueHelp 5 层链路 E2E

---

## 7. PR 11+ 详细步骤（3d - 8 大遗漏）

### 7.1 任务

**8 大遗漏补强**（spec v1.5.0 §21-25）：

| # | 任务 | 工作量 |
|:-:|------|:-----:|
| 1 | 路由层 3 文件（detailRouteGuard）| 0.5d |
| 2 | Store 7 文件（listActionStore 拆分）| 1d |
| 3 | 通知系统双轨迁移（useMessage + ElMessage）| 1d |
| 4 | 守卫 1 文件（page_type 路由级）| 0.5d |

### 7.2 验收标准

- [ ] 35 文件全部加固
- [ ] useMessage 统一
- [ ] 0 回归

---

## 8. 风险 + 决策

### 8.1 关键风险

| 风险 | 概率 | 影响 | 缓解 |
|------|:---:|:---:|------|
| useMetaList 行为变化 | 中 | 高 | PR 5 接口契约 + api_contract.spec.js |
| 响应式更新丢失 | 中 | 中 | 手动 set draftValues |
| callPost dynamic import 时序 | 中 | 中 | 保留动态导入 |
| 测试覆盖不足 | 中 | 高 | PR 5 强制跑 |
| 工期超期 | 中 | 中 | PR 8/4/5 优先（最高 ROI）|

### 8.2 决策点

| ID | 决策 | 推荐 |
|----|------|------|
| D-PR4-1 | service 内触发响应式 vs 纯函数？ | **纯函数**（service 不依赖 Vue）|
| D-PR4-2 | callPost 注入式 vs 直接 import？ | **注入式**（更易测试）|
| D-PR4-3 | useMetaList 减少 100 行 vs 200 行？ | **100 行**（足够，2 service 独立）|
| D-PR5-1 | 接口契约守卫 = 单测 vs e2e？ | **单测**（更细）|
| D-PR9-1 | 5 consumer 集成 vs 单元？ | **集成**（更贴近真实）|

---

## 9. 实施命令清单

```bash
# === PR 8 (0.5d) ===
cd d:\filework\excel-to-diagram
rm src/views/SystemManagement/UserGroupManagement.vue
rm src/views/SystemManagement/RoleManagement.vue
rm src/views/SystemManagement/UserManagement.vue
rm src/views/SystemManagement/VersionManagement.vue
rm src/views/SystemManagement/EnumValueList.vue
rm src/views/SystemManagement/ProductManagement.vue
# 手动编辑 src/views/ComponentComparison.vue 移除字符串引用
python d:\filework\test.py --failed --retries=0 --reporter=line

# === PR 4 (2d) ===
# 创建 src/services/keyTemplateService.js + draftPersistService.js
# 创建 src/services/__tests__/keyTemplateService.spec.js + draftPersistService.spec.js
# 修改 src/composables/useMetaList.js（import + 3 个下沉点替换）
npx vitest run src/services/__tests__/ --reporter=verbose
python d:\filework\test.py --failed --retries=0 --reporter=line

# === PR 5 (2d) ===
# 创建 src/composables/__tests__/useMetaList.api_contract.spec.js
# 创建 src/composables/__tests__/useMetaList.behavior.spec.js
# 创建 src/composables/__tests__/useMetaList.displaymode.spec.js
# 创建 e2e/specs/useMetaList-5-layer-link.spec.js
npx vitest run src/composables/__tests__/ --reporter=verbose

# === 集成验证 ===
python d:\filework\test.py --all --force
```

---

## 10. 一句话总结

> **Phase B 12.5d = 8 PR / 0.5+2+2+1+1+2+1+3d = 立即可执行 PR 8+4+5（4.5d / 1 周价值）= useMetaList.js 减少 115 行 + 32 个 service 单测 + 35 文件契约保护 + 6 死代码清理（4.5KB 节省）= 价值最高的 ROI 起点。**
