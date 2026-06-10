/**
 * useFieldPolicy - 统一字段策略 Hook
 * 
 * 提供字段级别的策略评估能力，与后端 FieldPolicyEngine 规则一致。
 * 
 * 功能：
 * 1. editable 映射 - 返回字段可编辑性
 * 2. visible 映射 - 返回字段可见性
 * 3. 动态策略 - 支持基于 row/action 的条件判断
 */

import { ref, computed, watch } from 'vue'
import { apiV2 } from '@/utils/httpClient'

/**
 * 系统字段集合 - 这些字段始终不可编辑和不可见
 */
const SYSTEM_FIELDS = new Set([
  'id', '_id', 'type', 'tenant_id',
  'created_at', 'updated_at', 'created_by', 'updated_by',
  'created_date', 'updated_date', 'created_user', 'updated_user',
  'is_system', 'system_flag', 'readonly'
])

/**
 * 检查是否是系统字段
 * @param {string} fieldId - 字段标识
 * @returns {boolean}
 */
function isSystemField(fieldId) {
  return SYSTEM_FIELDS.has(fieldId?.toLowerCase())
}

/**
 * useFieldPolicy Hook
 * 
 * @param {Ref} metaConfig - 元数据配置（包含 fields 和 listConfig）
 * @param {Ref} columns - 列配置（可选）
 * @returns {Object} - 策略工具函数和计算属性
 */
export function useFieldPolicy(metaConfig, columns) {
  /**
   * 后端字段策略 API 返回结果
   * 结构: { field_name: { editable, visible, required, conditional_required }, ... } 或 null
   * null 表示未加载或 API 不可用，触发 fallback 到本地推断逻辑
   */
  const fieldPolicies = ref(null)

  /**
   * [DECORATIVE] [NEW] v1.2 / FR-4.5: 条件必填映射表
   * 结构: { field_id: [{condition, message, severity}, ...] }
   * 来源: fieldPolicies API 响应中的 conditional_required 数组
   */
  const requiredMap = ref({})

  /**
   * 从后端字段策略 API 加载策略评估结果
   * @param {string} objectType - 对象类型
   * @param {string} context - 上下文 (read|create|update)
   * @param {string} mutability - 可变性 (locked|extensible|fully_editable)
   * @returns {Promise<boolean>} 是否加载成功
   */
  async function loadFieldPolicies(objectType, context, mutability) {
    try {
      const params = new URLSearchParams()
      if (context) params.set('context', context)
      if (mutability) params.set('mutability', mutability)
      const query = params.toString()
      const path = `/meta/${objectType}/field-policies${query ? '?' + query : ''}`
      const result = await apiV2.get(path)
      if (result.success && result.data) {
        fieldPolicies.value = result.data
        // [DECORATIVE] [NEW] v1.2 / FR-4.5: 提取 conditional_required 到 requiredMap
        const newRequiredMap = {}
        for (const [fieldId, policy] of Object.entries(result.data)) {
          if (policy.conditional_required && policy.conditional_required.length > 0) {
            newRequiredMap[fieldId] = policy.conditional_required
          }
        }
        requiredMap.value = newRequiredMap
        return true
      }
      fieldPolicies.value = null
      return false
    } catch {
      fieldPolicies.value = null
      return false
    }
  }

  /**
   * editableMap - 字段可编辑性映射
   * 优先从后端 API 结果读取，fallback 到本地推断逻辑
   */
  const editableMap = computed(() => {
    const map = {}
    
    // 优先从后端 API 结果读取
    if (fieldPolicies.value) {
      for (const [fieldId, policy] of Object.entries(fieldPolicies.value)) {
        map[fieldId] = policy.editable === true
      }
      return map
    }
    
    // Fallback: 本地推断逻辑
    if (!metaConfig.value?.fields) {
      return map
    }
    
    for (const field of metaConfig.value.fields) {
      const fieldId = field.id || field.key
      
      if (isSystemField(fieldId)) {
        map[fieldId] = false
        continue
      }
      
      const semantics = field.semantics || {}
      if (semantics.readonly_always === true) {
        map[fieldId] = false
        continue
      }
      
      if (field.computed === true) {
        map[fieldId] = false
        continue
      }
      
      if (field.editable === false) {
        map[fieldId] = false
        continue
      }
      
      const ui = field.ui || {}
      if (ui.editable === false) {
        map[fieldId] = false
        continue
      }
      
      map[fieldId] = ui.editable !== false
    }
    
    return map
  })
  
  /**
   * visibleMap - 字段可见性映射
   * 优先从后端 API 结果读取，fallback 到本地推断逻辑
   */
  const visibleMap = computed(() => {
    const map = {}
    
    // 优先从后端 API 结果读取
    if (fieldPolicies.value) {
      for (const [fieldId, policy] of Object.entries(fieldPolicies.value)) {
        map[fieldId] = policy.visible === true
      }
      return map
    }
    
    // Fallback: 本地推断逻辑
    if (!metaConfig.value?.fields) {
      return map
    }
    
    for (const field of metaConfig.value.fields) {
      const fieldId = field.id || field.key
      
      if (isSystemField(fieldId)) {
        map[fieldId] = false
        continue
      }
      
      if (field.visible === false) {
        map[fieldId] = false
        continue
      }
      
      const ui = field.ui || {}
      if (ui.visible === false) {
        map[fieldId] = false
        continue
      }
      
      map[fieldId] = true
    }
    
    return map
  })
  
  /**
   * immutableMap - 不可变字段映射
   * 优先从后端 API 结果读取，fallback 到本地推断逻辑
   */
  const immutableMap = computed(() => {
    const map = {}
    
    // 优先从后端 API 结果读取
    if (fieldPolicies.value) {
      for (const [fieldId, policy] of Object.entries(fieldPolicies.value)) {
        // API 中 editable=false 且非 readonly_always → 视为 immutable
        map[fieldId] = policy.editable === false
      }
      return map
    }
    
    // Fallback: 本地推断逻辑
    if (!metaConfig.value?.fields) {
      return map
    }
    
    for (const field of metaConfig.value.fields) {
      const fieldId = field.id || field.key
      const semantics = field.semantics || {}
      map[fieldId] = semantics.immutable === true || field.immutable === true || isSystemField(fieldId)
    }
    
    return map
  })
  
  /**
   * readonlyAlwaysMap - 始终只读字段映射
   * 优先从后端 API 结果读取，fallback 到本地推断逻辑
   */
  const readonlyAlwaysMap = computed(() => {
    const map = {}
    
    // 优先从后端 API 结果读取
    if (fieldPolicies.value) {
      for (const [fieldId, policy] of Object.entries(fieldPolicies.value)) {
        // API 中 editable=false 且 visible=true → 视为 readonly_always
        map[fieldId] = policy.editable === false && policy.visible === true
      }
      return map
    }
    
    // Fallback: 本地推断逻辑
    if (!metaConfig.value?.fields) {
      return map
    }
    
    for (const field of metaConfig.value.fields) {
      const fieldId = field.id || field.key
      const semantics = field.semantics || {}
      map[fieldId] = semantics.readonly_always === true
    }
    
    return map
  })
  
  /**
   * businessKeyMap - 业务主键字段映射
   * 业务主键在创建时可编辑，创建后只读（与 immutable 行为一致）
   */
  const businessKeyMap = computed(() => {
    const map = {}
    
    if (!metaConfig.value?.fields) {
      return map
    }
    
    for (const field of metaConfig.value.fields) {
      const fieldId = field.id || field.key
      const semantics = field.semantics || {}
      map[fieldId] = semantics.business_key === true
    }
    
    return map
  })
  
  /**
   * 判断单个字段是否可编辑
   *
   * 判断优先级：
   * 1. 系统字段 → 不可编辑
   * 2. readonly_always 语义 → 始终不可编辑
   * 3. business_key 语义 → 创建时可编辑，更新时不可编辑
   * 4. immutable 语义 → 创建时可编辑，更新时不可编辑
   * 5. ui.editable 显式配置 → 使用配置值
   * 6. mutability 逻辑 → 根据对象类型评估
   * 7. 默认值 → 可编辑
   *
   * [FIX 2026-06-10] API 加载的策略默认是 read context，会将
   * immutable / business_key 字段判为 editable=false。新增行（__new_/__isNew）
   * 必须用本地语义重新评估，否则像 enum_value.code 这种业务主键将无法录入。
   *
   * @param {string} fieldId - 字段标识
   * @param {Object} row - 行数据（用于判断是否新行）
   * @param {string} mutability - 对象 mutability (locked/fully_editable/extensible)
   * @returns {boolean}
   */
  function isEditable(fieldId, row = null, mutability = null) {
    // 优先从后端 API 结果读取
    if (fieldPolicies.value) {
      const policy = fieldPolicies.value[fieldId]
      if (policy !== undefined) {
        // 新增行：API 加载通常是 read context，对 create 场景不准确，
        // 必须用本地 readonly_always / system 兜底，避免 business_key /
        // immutable 字段在新建时被锁死。
        // 注意：editableMap / readonlyAlwaysMap 都会被 API 结果污染（顶部 fast-path），
        // 这里只查本地 metaConfig.fields 的 ui.editable / readonly_always / system。
        if (isNewRowCheck(row)) {
          if (isSystemField(fieldId)) return false
          if (metaConfig.value?.fields) {
            const localField = metaConfig.value.fields.find(
              f => (f.id || f.key) === fieldId
            )
            if (localField?.semantics?.readonly_always === true) return false
            if (localField?.ui?.editable === false) return false
            if (localField?.editable === false) return false
          }
          return true
        }
        return policy.editable === true
      }
      // API 结果中无此字段，fallback 到当前判断链
    }

    if (isSystemField(fieldId)) {
      return false
    }
    
    if (readonlyAlwaysMap.value[fieldId] === true) {
      return false
    }
    
    if (businessKeyMap.value[fieldId] === true) {
      const isNewRow = isNewRowCheck(row)
      if (!isNewRow) {
        return false
      }
    }
    
    if (immutableMap.value[fieldId] === true) {
      const isNewRow = isNewRowCheck(row)
      if (!isNewRow) {
        return false
      }
    }
    
    // 显式 editable = false
    if (editableMap.value[fieldId] === false) {
      // 新行时 editable: false 的字段可能需要特殊处理
      // 通常 editable: false 意味着始终不可编辑
      return false
    }
    
    // mutability 逻辑
    if (mutability) {
      return evaluateMutability(fieldId, row, mutability)
    }
    
    // 从 columns 获取 immutable 信息
    if (columns?.value) {
      const column = columns.value.find(c => c.prop === fieldId || c.key === fieldId)
      if (column?.immutable) {
        const isNew = isNewRowCheck(row)
        if (!isNew) {
          return false
        }
      }
    }
    
    return true
  }
  
  /**
   * 判断字段是否可见
   * @param {string} fieldId - 字段标识
   * @returns {boolean}
   */
  function isVisible(fieldId) {
    // 优先从后端 API 结果读取
    if (fieldPolicies.value) {
      const policy = fieldPolicies.value[fieldId]
      if (policy !== undefined) {
        return policy.visible === true
      }
      // API 结果中无此字段，fallback 到当前判断链
    }
    
    if (isSystemField(fieldId)) {
      return false
    }
    
    if (visibleMap.value[fieldId] === false) {
      return false
    }
    
    return true
  }
  
  /**
   * 判断字段是否必填
   * 优先从后端 API 结果读取，fallback 到本地推断逻辑
   * @param {string} fieldId - 字段标识
   * @returns {boolean}
   */
  function isRequired(fieldId) {
    // 优先从后端 API 结果读取
    if (fieldPolicies.value) {
      const policy = fieldPolicies.value[fieldId]
      if (policy !== undefined) {
        return policy.required === true
      }
    }
    
    // Fallback: 从 metaConfig 推断
    if (!metaConfig.value?.fields) {
      return false
    }
    
    const field = metaConfig.value.fields.find(f => (f.id || f.key) === fieldId)
    if (!field) return false
    
    if (field.required === true) return true
    const ui = field.ui || {}
    if (ui.required === true) return true
    
    return false
  }

  /**
   * [DECORATIVE] [NEW] v1.3 / FR-6.3: 条件必填评估器
   * 用 new Function + with(row) 沙箱评估条件表达式
   * @param {string} condition - 条件表达式 (如 "domain_id is not None")
   * @param {Object} row - 行数据
   * @returns {boolean}
   */
  function evaluateCondition(condition, row) {
    if (!condition || !row) return false
    try {
      const fn = new Function('row', `with(row) { return !!((${condition}) || false); }`)
      return Boolean(fn({ ...row }))
    } catch {
      return false
    }
  }

  /**
   * [DECORATIVE] [NEW] v1.3 / FR-6.3: 基于 row 上下文的重载 isRequired
   * 先调基础 isRequired(fieldId)，再检查 conditional_required 条件是否满足。
   * @param {string} fieldId - 字段标识
   * @param {Object} row - 行数据（用于条件评估）
   * @returns {boolean}
   */
  function isRequiredByRow(fieldId, row = null) {
    if (isRequired(fieldId)) return true

    if (requiredMap.value && row) {
      const rules = requiredMap.value[fieldId]
      if (rules && Array.isArray(rules) && rules.length > 0) {
        for (const rule of rules) {
          if (rule.condition && evaluateCondition(rule.condition, row)) {
            return true
          }
        }
      }
    }

    if (metaConfig.value?.fields && row) {
      const field = metaConfig.value.fields.find(f => (f.id || f.key) === fieldId)
      if (field?.conditional_required) {
        const rules = Array.isArray(field.conditional_required)
          ? field.conditional_required
          : [field.conditional_required]
        for (const rule of rules) {
          if (rule.condition && evaluateCondition(rule.condition, row)) {
            return true
          }
        }
      }
    }

    return false
  }
  
  /**
   * 判断字段是否不可变
   * @param {string} fieldId - 字段标识
   * @returns {boolean}
   */
  function isImmutable(fieldId) {
    return immutableMap.value[fieldId] === true || isSystemField(fieldId)
  }
  
  /**
   * 评估 mutability 逻辑
   * 
   * @param {string} fieldId - 字段标识
   * @param {Object} row - 行数据
   * @param {string} mutability - mutability 值 (locked/fully_editable/extensible)
   * @returns {boolean}
   */
  function evaluateMutability(fieldId, row, mutability) {
    if (mutability === 'locked') {
      return false
    }
    
    if (mutability === 'fully_editable') {
      return true
    }
    
    if (mutability === 'extensible') {
      // extensible: 非系统字段可编辑
      if (isSystemField(fieldId)) {
        return false
      }
      
      // 检查 is_system 字段
      const isSystem = row?.is_system === true
      return !isSystem
    }
    
    return true
  }
  
  /**
   * 检查是否是新增行
   * @param {Object} row - 行数据
   * @returns {boolean}
   */
  function isNewRowCheck(row) {
    if (!row) return false
    const id = row.id
    return String(id).startsWith('__new_') || row._isNew === true
  }
  
  /**
   * 获取不可编辑字段列表
   * @param {string[]} fieldIds - 字段标识列表
   * @param {Object} row - 行数据
   * @param {string} mutability - mutability 值
   * @returns {string[]}
   */
  function getReadonlyFields(fieldIds, row = null, mutability = null) {
    return fieldIds.filter(id => !isEditable(id, row, mutability))
  }
  
  /**
   * 获取可编辑字段列表
   * @param {string[]} fieldIds - 字段标识列表
   * @param {Object} row - 行数据
   * @param {string} mutability - mutability 值
   * @returns {string[]}
   */
  function getEditableFields(fieldIds, row = null, mutability = null) {
    return fieldIds.filter(id => isEditable(id, row, mutability))
  }
  
  /**
   * 判断行是否可编辑
   * @param {Object} row - 行数据
   * @param {string} mutability - mutability 值
   * @param {string} action - 操作类型 (create/update/read)
   * @returns {boolean}
   */
  function isRowEditable(row, mutability = null, action = 'read') {
    if (!mutability) {
      return true
    }
    
    if (mutability === 'locked') {
      return false
    }
    
    if (mutability === 'fully_editable') {
      return true
    }
    
    if (mutability === 'extensible') {
      if (action === 'create') {
        return true
      }
      return !row?.is_system
    }
    
    return true
  }
  
  /**
   * [DECORATIVE] [NEW] v1.3 / FR-6.1: 字段策略是否已加载
   */
  const policiesLoaded = ref(false)

  /**
   * [DECORATIVE] [NEW] v1.3 / FR-6.1: 自动加载入口
   * 列表页 / 详情页 mount 时调用，激活后端 field-policies API
   * @param {string} objectType - 对象类型 (如 'user', 'role')
   * @param {string} context - 上下文 (read|create|update)
   * @param {string} mutability - 可变性 (locked|extensible|fully_editable)
   * @returns {Promise<boolean>}
   */
  async function autoLoad(objectType, context = 'read', mutability = null) {
    if (!objectType) return false
    policiesLoaded.value = false
    const ok = await loadFieldPolicies(objectType, context, mutability)
    policiesLoaded.value = ok
    return ok
  }

  return {
    // 后端策略
    fieldPolicies,
    loadFieldPolicies,
    requiredMap,  // [DECORATIVE] [NEW] v1.2 / FR-4.5: 条件必填映射

    autoLoad,           // [DECORATIVE] [NEW] v1.3 / FR-6.1
    policiesLoaded,     // [DECORATIVE] [NEW] v1.3 / FR-6.1

    editableMap,
    visibleMap,
    immutableMap,
    readonlyAlwaysMap,
    businessKeyMap,
    
    isEditable,
    isVisible,
    isRequired,
    isImmutable,
    isNewRowCheck,
    isRowEditable,
    isRequiredByRow,     // [DECORATIVE] [NEW] v1.3 / FR-6.3
    evaluateCondition,   // [DECORATIVE] [NEW] v1.3 / FR-6.3 (供 MetaForm 独立复用)
    
    // 批量操作
    getEditableFields,
    getReadonlyFields,
    
    // 工具
    isSystemField,
    evaluateMutability
  }
}

export default useFieldPolicy
