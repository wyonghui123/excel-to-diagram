import { computed, ref, watch, unref } from 'vue'
import { boService } from '@/services/boService'

export function useCascadeSelect(metaObject) {
  const options = ref({})
  const loading = ref({})
  const error = ref({})

  const cascadeConfig = computed(() => {
    if (!metaObject.value) return []
    return metaObject.value.cascade_select || []
  })

  const cascadeChain = computed(() => {
    const chain = {}
    cascadeConfig.value.forEach(function(config) {
      chain[config.field] = {
        field: config.field,
        parentField: config.filter_by,
        parentObject: config.parent_object,
        displayField: config.parent_display_field || 'name'
      }
    })
    return chain
  })

  const cascadeFields = computed(() => Object.keys(cascadeChain.value))

  const parentFields = computed(() => {
    const result = []
    cascadeFields.value.forEach(function(fieldId) {
      const config = cascadeChain.value[fieldId]
      if (config && config.parentField) {
        result.push(config.parentField)
      }
    })
    return result
  })

  function clearDownstream(fieldId) {
    const config = cascadeChain.value[fieldId]
    if (!config) return
    
    const fieldIds = cascadeFields.value
    const startIndex = fieldIds.indexOf(fieldId)
    if (startIndex === -1) return
    
    fieldIds.slice(startIndex + 1).forEach(function(downstreamFieldId) {
      const downstreamConfig = cascadeChain.value[downstreamFieldId]
      if (downstreamConfig && downstreamConfig.parentField === config.field) {
        options.value[downstreamFieldId] = []
      }
    })
  }

  function clearAllDownstream(fieldId, formData) {
    const fieldIds = cascadeFields.value
    const startIndex = fieldIds.indexOf(fieldId)
    if (startIndex === -1) return
    fieldIds.slice(startIndex).forEach(function(fid) {
      options.value[fid] = []
      if (formData && formData[fid] !== undefined) {
        formData[fid] = null
      }
      // [FIX 2026-06-10] 同时清掉 _display 和 <fid>_name 缓存，避免父级 FK 改变后
      // 下游 FK 的显示文本（ValueHelpField 缓存的 display 字符串）残留，
      // 让用户看到「68」这种 ID 而不是空。
      const displayKey = `${fid}_display`
      if (formData && formData[displayKey] !== undefined) {
        formData[displayKey] = null
      }
      const nameKey = fid.replace(/_id$/, '') + '_name'
      if (formData && formData[nameKey] !== undefined) {
        formData[nameKey] = null
      }
    })
  }

  function getOptions(fieldId) {
    return options.value[fieldId] || []
  }

  function isLoading(fieldId) {
    return loading.value[fieldId] || false
  }

  function getError(fieldId) {
    return error.value[fieldId] || null
  }

  function isCascadeField(fieldId) {
    return cascadeFields.value.includes(fieldId)
  }

  function getParentField(fieldId) {
    const config = cascadeChain.value[fieldId]
    if (!config) return null
    return config.parentField || null
  }

  /**
   * [METHOD] getDownstreamFields
   * [DESCRIPTION] 获取指定字段的所有下游字段列表
   * 
   * @param {string} fieldId - 字段名
   * @returns {string[]} 下游字段列表
   */
  function getDownstreamFields(fieldId) {
    const downstream = []
    const chain = cascadeChain.value
    
    function collect(field) {
      Object.entries(chain).forEach(function(entry) {
        const [key, config] = entry
        if (config.parentField === field && !downstream.includes(key)) {
          downstream.push(key)
          collect(key)
        }
      })
    }
    
    collect(fieldId)
    return downstream
  }

  /**
   * [METHOD] inferParentFields
   * [DESCRIPTION] 反向推断父字段值，用于编辑模式加载完整层级路径
   * 
   * @param {string} fieldId - 当前字段名
   * @param {any} currentValue - 当前字段值
   * @returns {Promise<Object>} 推断结果 { success, data, message }
   */
  async function inferParentFields(fieldId, currentValue) {
    const config = cascadeChain.value[fieldId]
    if (!config) {
      return { success: false, message: '字段未配置级联' }
    }
    
    try {
      const result = await boService.read(config.parentObject, currentValue)
      
      if (!result.success || !result.data) {
        return { success: false, message: result.message || '未找到数据' }
      }
      
      const parentValue = result.data[config.parentField]
      
      if (parentValue && config.parentField) {
        const parentResult = await inferParentFields(config.parentField, parentValue)
        
        return {
          success: true,
          data: {
            ...parentResult.data,
            [config.parentField]: parentValue,
            [fieldId]: currentValue
          }
        }
      } else {
        return {
          success: true,
          data: { [fieldId]: currentValue }
        }
      }
    } catch (e) {
      return { success: false, message: e.message || '反向推断失败' }
    }
  }

  function getCascadeChainData() {
    const result = []
    cascadeFields.value.forEach(function(fieldId) {
      result.push({
        field: cascadeChain.value[fieldId].field,
        parentField: cascadeChain.value[fieldId].parentField,
        parentObject: cascadeChain.value[fieldId].parentObject,
        displayField: cascadeChain.value[fieldId].displayField,
        options: options.value[fieldId] || []
      })
    })
    return result
  }

  const cascadeDepth = computed(() => cascadeFields.value.length)
  const isEmptyChain = computed(() => cascadeFields.value.length === 0)

  function watchParentChanges(formData, callback) {
    return watch(
      function() {
        const data = unref(formData)
        return parentFields.value.map(function(f) { return data ? data[f] : undefined })
      },
      function(newValues, oldValues) {
        parentFields.value.forEach(function(parentField, index) {
          const newValue = newValues[index]
          const oldValue = oldValues ? oldValues[index] : undefined
          
          if (newValue !== oldValue) {
            cascadeFields.value.forEach(function(fieldId) {
              const config = cascadeChain.value[fieldId]
              if (config && config.parentField === parentField) {
                callback(fieldId, newValue)
              }
            })
          }
        })
      },
      { deep: true }
    )
  }

  return {
    cascadeConfig,
    cascadeChain,
    cascadeFields,
    parentFields,
    cascadeDepth,
    isEmptyChain,
    clearDownstream,
    clearAllDownstream,
    getOptions,
    isLoading,
    getError,
    isCascadeField,
    getParentField,
    getDownstreamFields,
    inferParentFields,
    getCascadeChainData,
    watchParentChanges,
    options,
    loading,
    error
  }
}

export function useFormCascade(metaObject, formData) {
  const cascade = useCascadeSelect(metaObject)
  let unwatch = null
  
  async function initialize() {
    const cascadeConfig = metaObject.value?.cascade_select
    if (!cascadeConfig || cascadeConfig.length === 0) return
    
    const allFieldIds = Object.keys(formData.value || {})
    const cascadeFieldIds = cascade.cascadeFields.value
    
    for (const fieldId of cascadeFieldIds) {
      if (allFieldIds.includes(fieldId) && formData.value[fieldId] != null) {
        try {
          const result = await cascade.inferParentFields(fieldId, formData.value[fieldId])
          if (result.success && result.data) {
            Object.assign(formData.value, result.data)
          }
        } catch (e) {
          console.warn('[useFormCascade] inferParentFields failed for', fieldId, e)
        }
      }
    }
    
    if (!unwatch) {
      unwatch = cascade.watchParentChanges(formData, function(fieldId, _newValue) {
        cascade.clearAllDownstream(fieldId, formData.value)
      })
    }
  }
  
  return {
    cascadeFields: cascade.cascadeFields,
    isCascadeField: cascade.isCascadeField,
    getParentField: cascade.getParentField,
    initialize
  }
}
