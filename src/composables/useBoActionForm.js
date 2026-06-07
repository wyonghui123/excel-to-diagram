/**
 * useBoActionForm - E-2
 *
 * 基于 input_schema 自动生成 Vue 表单
 * 支持 string / integer / number / boolean / enum / date / object / array
 *
 * 用法:
 *   import { useBoActionForm } from '@/composables/useBoActionForm'
 *   const { schema, Form, validate, buildPayload } = useBoActionForm('enum_type.create', { initial: {} })
 *
 *   <template>
 *     <Form />
 *     <el-button @click="submit">提交</el-button>
 *   </template>
 */
import { computed, ref, reactive } from 'vue'
import { apiV2 } from '@/utils/httpClient'
import { useBoAction } from './useBoAction'

export function useBoActionForm(actionId, options = {}) {
  const { initial = {}, schema: providedSchema = null } = options
  const { callPost } = useBoAction()

  const schema = ref(providedSchema)
  const formData = reactive({ ...initial })
  const errors = reactive({})
  const submitting = ref(false)
  const lastResult = ref(null)

  // 加载 schema (若未提供)
  async function loadSchema() {
    if (providedSchema) return
    try {
      const result = await apiV2.get('/action/_schemas')
      if (result.success) {
        const action = result.data?.actions?.find(a => a.action_id === actionId)
        if (action) {
          schema.value = action.input_schema || { type: 'object' }
        } else {
          schema.value = { type: 'object', additionalProperties: true }
        }
      } else {
        schema.value = { type: 'object', additionalProperties: true }
      }
    } catch (e) {
      console.error('[useBoActionForm] loadSchema failed:', e)
      schema.value = { type: 'object', additionalProperties: true }
    }
  }

  // 校验
  function validate() {
    Object.keys(errors).forEach(k => delete errors[k])
    if (!schema.value || !schema.value.properties) return true
    let valid = true
    for (const [fieldName, fieldSchema] of Object.entries(schema.value.properties)) {
      const value = formData[fieldName]
      // required 校验
      if (schema.value.required?.includes(fieldName)) {
        if (value === undefined || value === null || value === '') {
          errors[fieldName] = `${fieldName} 必填`
          valid = false
        }
      }
      // type 校验
      if (value !== undefined && value !== null && fieldSchema.type) {
        if (fieldSchema.type === 'integer' || fieldSchema.type === 'number') {
          if (isNaN(Number(value))) {
            errors[fieldName] = `${fieldName} 必须是数字`
            valid = false
          }
        }
        if (fieldSchema.type === 'string' && fieldSchema.minLength && String(value).length < fieldSchema.minLength) {
          errors[fieldName] = `${fieldName} 长度不能少于 ${fieldSchema.minLength}`
          valid = false
        }
      }
      // enum 校验
      if (fieldSchema.enum && !fieldSchema.enum.includes(value)) {
        errors[fieldName] = `${fieldName} 必须是 ${fieldSchema.enum.join('/')}`
        valid = false
      }
    }
    return valid
  }

  // 构造 payload (只含 schema 中声明的字段)
  function buildPayload() {
    if (!schema.value || !schema.value.properties) return { ...formData }
    const payload = {}
    for (const fieldName of Object.keys(schema.value.properties)) {
      if (formData[fieldName] !== undefined) {
        payload[fieldName] = formData[fieldName]
      }
    }
    return payload
  }

  async function submit() {
    if (!validate()) {
      return { success: false, message: '表单校验失败' }
    }
    submitting.value = true
    try {
      const r = await callPost(actionId, buildPayload())
      lastResult.value = r
      return r
    } finally {
      submitting.value = false
    }
  }

  // 表单字段定义 (供 UI 组件渲染)
  const fields = computed(() => {
    if (!schema.value || !schema.value.properties) return []
    return Object.entries(schema.value.properties).map(([name, prop]) => ({
      name,
      label: name,
      type: prop.type || 'string',
      required: schema.value.required?.includes(name) || false,
      enum: prop.enum || null,
      format: prop.format || null,
      minLength: prop.minLength || null,
      maxLength: prop.maxLength || null,
      default: prop.default !== undefined ? prop.default :
               prop.type === 'boolean' ? false :
               prop.type === 'integer' || prop.type === 'number' ? 0 : '',
    }))
  })

  return {
    schema,
    fields,
    formData,
    errors,
    submitting,
    lastResult,
    loadSchema,
    validate,
    buildPayload,
    submit,
  }
}

export default useBoActionForm
