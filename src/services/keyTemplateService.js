/**
 * keyTemplateService.js - 键模板推导 service
 *
 * 业务规则下沉：将 useMetaList 中关于"新建行时根据 parent_id 推导 code"的
 * 纯函数业务逻辑抽取到独立 service。
 *
 * 抽出前的位置：useMetaList.js L1931-1977（_suggestKeyTemplateCode，47 行）
 * 抽出原因：纯函数业务逻辑下沉到 service 层
 * 重构 spec：[spec-fr-ui-003-004-005-useMetaList-refactor.md v1.5.0] §5
 *
 * 关键设计决策：
 * 1. **纯函数优先**（service 不依赖 Vue 响应式系统）
 * 2. **boService 注入式依赖**（便于单测 mock）
 * 3. **错误返回 {success, error, skipped, code}**（非抛异常）
 * 4. **响应式更新由调用方负责**（service 不直接 set ref）
 *
 * 公开 API：
 * - extractParentParams(filterValues, newRow, isVueInternalProp)
 * - hasInvalidParentId(parentParams)
 * - applyKeyTemplateSuggestion(newRow, codeValue, draftValues, formDirtyFields = null)
 * - suggestKeyTemplateCode(newRow, filterValues, draftValues, boService, config, isVueInternalProp)
 * - shouldSkipSuggestionForForm(codeFieldName, formDirtyFields)   [NEW 2026-06-10]
 * - resetKeyTemplateCode(formData, codeValue, formDirtyFields)     [NEW 2026-06-10]
 */

/**
 * 提取新建行的 parent_id 字段（用于键模板推导）
 * 业务规则：
 *   1. 从 filterValues 中提取 *_id 字段
 *   2. 从 newRow 中提取 *_id 字段（不覆盖 filterValues 中已存在的）
 *   3. 跳过 Vue 内部 prop（isVueInternalProp 判断）
 *   4. 跳过 _ 开头的字段
 *   5. 跳过 id 字段
 *
 * @param {Object} filterValues - 列表过滤值（响应式对象）
 * @param {Object} newRow - 新建行数据
 * @param {Function} isVueInternalProp - Vue 内部 prop 判断函数
 * @returns {Object} parentParams
 */
export function extractParentParams(filterValues, newRow, isVueInternalProp) {
  const parentParams = {}

  // Step 1: 从 filterValues 提取
  Object.keys(filterValues || {})
    .filter(key => !isVueInternalProp(key) && key.endsWith('_id'))
    .forEach(key => {
      parentParams[key] = filterValues[key]
    })

  // Step 2: 从 newRow 提取（不覆盖）
  Object.keys(newRow || {})
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
 * 业务规则：parent record 未保存（值为 'new'/''/null/undefined）时跳过
 *
 * @param {Object} parentParams
 * @returns {boolean} true 表示包含无效 parent_id
 */
export function hasInvalidParentId(parentParams) {
  return Object.values(parentParams).some(
    v => v === 'new' || v === '' || v === null || v === undefined
  )
}

/**
 * 应用建议的 code 到新建行 + draftValues
 * 注意：直接修改 newRow 的 code / _initialValues 字段
 *
 * [FIX 2026-06-10] 异步竞态保护（inline edit 模式）：
 *   _suggestKeyTemplateCode 是 fire-and-forget 异步调用，user 可能在
 *   自动建议返回之前已经在 code 字段输入了值。无条件覆盖会丢掉用户输入，
 *   而且更糟的是: 覆盖后 fields.code === initialValues.code，
 *   saveDraftValues 走到 hasDraftChanges=false 分支会把新建行从 data 中
 *   静默删除，造成"保存不生效"假象。
 *   修复: 仅在用户尚未触达 code 字段时才应用建议（code 键不在 rowDrafts 中）。
 *
 * [FIX 2026-06-10 v2] 详情表单模式保护（formDirtyFields 路径）：
 *   详情表单（ObjectPageShell）走 formData + field-update 事件链，
 *   不经过 rowDrafts。formDirtyFields 是 useKeyTemplateFormSync
 *   维护的响应式 Set，记录用户在表单中编辑过的字段。
 *   当 formDirtyFields.has('code') 为真时，跳过自动建议。
 *
 * @param {Object} newRow - 新建行（直接修改）
 * @param {string} codeValue - 建议的 code
 * @param {Map} draftValues - 草稿 Map（用于同步 rowDrafts.code）
 * @param {Set|null} [formDirtyFields=null] - 详情表单脏字段集合（可选）
 * @returns {{shouldUpdateDraft: boolean, skipped?: string}} 是否需要触发响应式更新
 */
export function applyKeyTemplateSuggestion(newRow, codeValue, draftValues, formDirtyFields = null) {
  // Step 0a: inline edit 路径保护（rowDrafts）
  const rowDrafts = draftValues.get(newRow.id)
  if (rowDrafts && Object.prototype.hasOwnProperty.call(rowDrafts, 'code')) {
    return { shouldUpdateDraft: false, skipped: 'user_edited' }
  }

  // Step 0b: 详情表单路径保护（formDirtyFields） [NEW 2026-06-10]
  if (formDirtyFields && formDirtyFields.has('code')) {
    return { shouldUpdateDraft: false, skipped: 'user_edited_form' }
  }

  // Step 1: 设置 newRow.code
  newRow.code = codeValue

  // Step 2: 记录到 _initialValues（用于判断后续编辑是否变化）
  newRow._initialValues = { ...(newRow._initialValues || {}), code: codeValue }

  // Step 3: 同步到 draftValues
  if (rowDrafts) {
    rowDrafts.code = codeValue
    return { shouldUpdateDraft: true }
  }
  return { shouldUpdateDraft: false }
}

/**
 * 检查详情表单场景下是否应跳过建议
 * [NEW 2026-06-10] 选项 A 交互 (Salesforce 派)
 * 与 inline edit 的 rowDrafts.has('code') 语义对齐。
 *
 * 用法：详情表单的父对象变化回调中，先调此函数判断是否跳过建议。
 *
 * @param {string} codeFieldName - code 字段名（通常是 'code'）
 * @param {Set|null} formDirtyFields - useKeyTemplateFormSync 返回的 formDirtyFields
 * @returns {boolean} true 表示应跳过自动建议
 */
export function shouldSkipSuggestionForForm(codeFieldName, formDirtyFields) {
  if (!formDirtyFields) return false
  return formDirtyFields.has(codeFieldName) === true
}

/**
 * 重置 code 字段的"已编辑"状态并应用新建议值
 * [NEW 2026-06-10] 选项 A 交互 (Salesforce 派)
 *
 * 用于 UI 中的"重置为自动生成"按钮：
 *   1. 从 formDirtyFields 中删除 code（清除 dirty 标记）
 *   2. 设置 formData.code = codeValue
 *
 * 实际触发重建议的逻辑由调用方负责（ObjectPageShell 调用 suggestKeyTemplateCode）。
 *
 * @param {Object} formData - 详情表单数据对象
 * @param {string} codeValue - 重新建议的 code
 * @param {Set|null} formDirtyFields - 详情表单脏字段集合
 * @returns {{success: boolean}} 是否成功
 */
export function resetKeyTemplateCode(formData, codeValue, formDirtyFields) {
  if (!formData) {
    return { success: false }
  }
  // Step 1: 清除 code 字段的 dirty 标记
  if (formDirtyFields && formDirtyFields.has('code')) {
    formDirtyFields.delete('code')
  }
  // Step 2: 应用新值
  formData.code = codeValue
  return { success: true }
}

/**
 * 主入口：建议 key template code
 *
 * 完整流程：
 *   1. 提取 parentParams
 *   2. 检查 parentParams 是否为空
 *   3. 检查是否包含无效 parent_id
 *   4. 调用 boService.suggestKeyTemplateCode
 *   5. 应用建议
 *
 * @param {Object} newRow - 新建行
 * @param {Object} filterValues - 列表过滤值
 * @param {Map} draftValues - 草稿 Map
 * @param {Object} boService - 注入式依赖（boService）
 * @param {Object} config - useMetaList 配置 {debug: boolean}
 * @param {Function} isVueInternalProp - Vue 内部 prop 判断函数
 * @param {Set|null} [formDirtyFields=null] - 详情表单脏字段集合 [NEW 2026-06-10]
 * @returns {Promise<{
 *   success: boolean,
 *   code?: string,
 *   shouldUpdateDraft?: boolean,
 *   skipped?: 'no_parent' | 'invalid_parent' | 'no_code' | 'user_edited_form',
 *   error?: Error
 * }>}
 */
export async function suggestKeyTemplateCode(
  newRow,
  filterValues,
  draftValues,
  boService,
  config = {},
  isVueInternalProp = () => false,
  formDirtyFields = null  // [NEW 2026-06-10] 详情表单脏字段保护
) {
  try {
    // Step 1: 提取 parentParams
    const parentParams = extractParentParams(filterValues, newRow, isVueInternalProp)
    if (Object.keys(parentParams).length === 0) {
      return { success: false, skipped: 'no_parent' }
    }

    // Step 2: 检查无效 parent_id
    if (hasInvalidParentId(parentParams)) {
      if (config.debug) {
        console.log('[keyTemplateService] Skipped: parent record not yet saved')
      }
      return { success: false, skipped: 'invalid_parent' }
    }

    // Step 3: 调用后端
    const objectType = newRow._objectType || newRow.objectType
    if (!objectType) {
      return { success: false, error: new Error('Missing objectType') }
    }

    const result = await boService.suggestKeyTemplateCode(objectType, {}, parentParams)

    // Step 4: 应用建议（传入 formDirtyFields 保护）
    if (result?.success && result.data?.code) {
      const applyResult = applyKeyTemplateSuggestion(newRow, result.data.code, draftValues, formDirtyFields)
      return {
        success: true,
        code: result.data.code,
        shouldUpdateDraft: applyResult.shouldUpdateDraft,
      }
    }
    return { success: false, skipped: 'no_code' }
  } catch (e) {
    if (config.debug) {
      console.warn('[keyTemplateService] Error:', e)
    }
    return { success: false, error: e }
  }
}
