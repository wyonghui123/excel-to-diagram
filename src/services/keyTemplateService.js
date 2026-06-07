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
 * - applyKeyTemplateSuggestion(newRow, codeValue, draftValues)
 * - suggestKeyTemplateCode(newRow, filterValues, draftValues, boService, config, isVueInternalProp)
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
 * @param {Object} newRow - 新建行（直接修改）
 * @param {string} codeValue - 建议的 code
 * @param {Map} draftValues - 草稿 Map（用于同步 rowDrafts.code）
 * @returns {{shouldUpdateDraft: boolean}} 是否需要触发响应式更新
 */
export function applyKeyTemplateSuggestion(newRow, codeValue, draftValues) {
  // Step 1: 设置 newRow.code
  newRow.code = codeValue

  // Step 2: 记录到 _initialValues（用于判断后续编辑是否变化）
  newRow._initialValues = { ...(newRow._initialValues || {}), code: codeValue }

  // Step 3: 同步到 draftValues
  const rowDrafts = draftValues.get(newRow.id)
  if (rowDrafts) {
    rowDrafts.code = codeValue
    return { shouldUpdateDraft: true }
  }
  return { shouldUpdateDraft: false }
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
 * @returns {Promise<{
 *   success: boolean,
 *   code?: string,
 *   shouldUpdateDraft?: boolean,
 *   skipped?: 'no_parent' | 'invalid_parent' | 'no_code',
 *   error?: Error
 * }>}
 */
export async function suggestKeyTemplateCode(
  newRow,
  filterValues,
  draftValues,
  boService,
  config = {},
  isVueInternalProp = () => false
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

    // Step 4: 应用建议
    if (result?.success && result.data?.code) {
      const applyResult = applyKeyTemplateSuggestion(newRow, result.data.code, draftValues)
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
