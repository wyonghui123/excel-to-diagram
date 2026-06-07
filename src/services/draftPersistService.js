/**
 * draftPersistService.js - 草稿持久化 service
 *
 * 业务规则下沉：将 useMetaList 中关于"收集 drafts / 构造 payload / 保存草稿"
 * 的纯函数业务逻辑抽取到独立 service。
 *
 * 抽出前的位置：
 *   - useMetaList.js L2071-2094 (getDraftCreates, 24 行)
 *   - useMetaList.js L2099-2162 (saveDraftValues 业务逻辑, 64 行)
 * 抽出原因：纯函数业务逻辑下沉到 service 层
 * 重构 spec：[spec-fr-ui-003-004-005-useMetaList-refactor.md v1.5.0] §6
 *
 * 关键设计决策：
 * 1. **纯函数优先**（service 不依赖 Vue 响应式系统）
 * 2. **callPost 注入式依赖**（避免 service 直接 import composables）
 * 3. **showMessage 注入式依赖**（便于单测）
 * 4. **错误返回 {success, error, ...}**（非抛异常）
 * 5. **响应式更新由调用方负责**（service 不直接 set ref）
 *
 * 公开 API：
 * - hasDraftChanges(fields, initialValues)
 * - buildDraftPayload(fields, row, isNewRow)
 * - collectDrafts(draftValues, data)
 * - saveAllDrafts({objectType, draftValues, data, callPost, showMessage})
 * - getDraftCreates(draftValues, data)
 */

/**
 * 检查是否包含已变更字段
 * 业务规则：
 *   1. 跳过 _ 开头的字段（系统字段）
 *   2. 比较 fields[key] vs initialValues[key]
 *
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
 * 构造单行 draft payload
 * 业务规则：
 *   1. 新建行：从 row 中保留 *_id 字段（parent_id 等）
 *   2. 更新行：仅使用 fields
 *   3. 跳过 _ 开头的字段
 *   4. 跳过 id 字段
 *   5. fields 中的字段覆盖 row 中的字段
 *
 * @param {Object} fields - 用户编辑字段
 * @param {Object} row - 原始行（仅新建行使用）
 * @param {boolean} isNewRow
 * @returns {Object} payload
 */
export function buildDraftPayload(fields, row, isNewRow) {
  const payload = {}

  if (isNewRow && row) {
    // 新建行：保留 * _id 字段（parent_id 等）
    Object.keys(row).forEach(key => {
      if (key.startsWith('_') || key === 'id') return
      if (fields.hasOwnProperty(key)) return  // fields 优先
      if (key.endsWith('_id') && row[key] != null && row[key] !== '') {
        payload[key] = row[key]
      }
    })
  }

  // 覆盖/更新：fields 中的所有字段
  for (const [fieldName, newValue] of Object.entries(fields)) {
    if (fieldName.startsWith('_')) continue
    payload[fieldName] = newValue
  }

  return payload
}

/**
 * 收集 drafts（业务逻辑下沉）
 *
 * 流程：
 *   1. 遍历 draftValues
 *   2. 对每行判断是否包含变更（hasDraftChanges）
 *   3. 无变更：标记 toRemove
 *   4. 有变更：构造 payload，加入 drafts
 *
 * @param {Map} draftValues
 * @param {Array} data
 * @returns {{
 *   drafts: Array<{row_id, is_new, fields}>,
 *   toRemove: Array<{rowId, removeFromData: boolean}>
 * }}
 */
export function collectDrafts(draftValues, data) {
  const drafts = []
  const toRemove = []

  for (const [rowId, fields] of draftValues.entries()) {
    const rowIdStr = String(rowId)
    const isNewRow = rowIdStr.startsWith('__new_')
    const row = isNewRow ? data.find(r => String(r.id) === rowIdStr) : null
    const initialValues = row?._initialValues || {}

    if (!hasDraftChanges(fields, initialValues)) {
      // 无变更：标记删除
      if (isNewRow) {
        toRemove.push({ rowId: rowIdStr, removeFromData: true })
      }
      toRemove.push({ rowId, removeFromData: false })
      continue
    }

    // 有变更：构造 payload
    const payload = buildDraftPayload(fields, row, isNewRow)
    drafts.push({ row_id: rowId, is_new: isNewRow, fields: payload })
  }

  return { drafts, toRemove }
}

/**
 * 主入口：保存所有草稿（业务逻辑下沉）
 *
 * 完整流程：
 *   1. 收集 drafts + toRemove
 *   2. 清理 toRemove（从 data + draftValues 移除）
 *   3. 如果 drafts 为空，提前返回
 *   4. 调用后端 batch_save
 *   5. 成功：显示成功消息，返回 {success, created, updated}
 *   6. 失败：返回 {success, error, failures}
 *
 * C2 修复（v1.1）：service 不再直接操作 ref.value
 *   - data 参数为**纯 array**（调用方负责 ref → array 转换）
 *   - toRemove 元数据返回，由调用方负责应用
 *
 * @param {Object} params
 * @param {string} params.objectType
 * @param {Map} params.draftValues
 * @param {Array} params.data - **纯 array**（非 ref / 非 reactive）
 * @param {Function} params.callPost - useBoAction.callPost（注入式依赖）
 * @param {Object} params.showMessage - 注入式消息服务（默认 null 不显示）
 * @returns {Promise<{
 *   success: boolean,
 *   created: number,
 *   updated: number,
 *   error?: string,
 *   failures?: Array,
 *   toRemove?: Array<{rowId, removeFromData}>
 * }>}
 */
export async function saveAllDrafts({
  objectType,
  draftValues,
  data,
  callPost,
  showMessage = null,
} = {}) {
  if (!draftValues || draftValues.size === 0) {
    return { success: true, created: 0, updated: 0, toRemove: [] }
  }

  // Step 1: 收集 drafts（C2 修复：data 必须是纯 array，不检测 ref）
  const { drafts, toRemove } = collectDrafts(draftValues, data)

  // Step 2: 清理 draftValues 中的 toRemove（service 内部可操作 Map）
  for (const r of toRemove) {
    draftValues.delete(r.rowId)
  }

  // Step 3: drafts 为空
  if (drafts.length === 0) {
    return { success: true, created: 0, updated: 0, toRemove }
  }

  // Step 4: 调用后端
  try {
    const r = await callPost('batch_save', {
      object_type: objectType,
      drafts,
    })

    // Step 5: 成功
    if (r.success) {
      const createdCount = (r.data?.created || []).length
      const updatedCount = (r.data?.updated || []).length
      if (showMessage?.success) {
        showMessage.success(`成功创建 ${createdCount} 项, 更新 ${updatedCount} 项`)
      }
      return { success: true, created: createdCount, updated: updatedCount, toRemove }
    }

    // Step 6: 失败（toRemove 已应用，不再返回）
    const failures = r.data?.failures || []
    const errorMsg = failures.length > 0
      ? `${failures.length} 项失败: ${failures[0].message}`
      : (r.message || '保存失败')
    return { success: false, error: errorMsg, failures, toRemove }
  } catch (e) {
    return { success: false, error: e.message || String(e), toRemove }
  }
}

/**
 * 获取所有待创建的新增行 payload
 * 供父组件收集子数据后调用 deepInsert 使用
 *
 * 业务规则：
 *   1. 仅处理 rowId 以 __new_ 开头的新建行
 *   2. 跳过未变更的草稿
 *   3. 跳过 _ 开头的字段
 *   4. 跳过 id 字段
 *
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
