<!--
ActionExplorer.vue - E-3

Action 浏览器: 列出所有 19 Action, 含描述  schema  试调按钮。
- 调 apiv2action_schemas 拿所有 Action
- 用 useBoActionForm 自动生成表单
- "试调" 按钮 = 弹窗 + 填表 + 提交 + 显示结果
-->
<template>
  <div class="action-explorer">
    <div class="ae-header">
      <h2>[SEARCH] BO Action 浏览器</h2>
      <p class="ae-subtitle">浏览所有 {{ actions.length }} 个 BO Action + 试调 (v3.6)</p>
      <div class="ae-search">
        <input
          v-model="search"
          placeholder="按 action_id / description / tags 过滤..."
          class="ae-search-input"
        />
        <select v-model="filterType" class="ae-filter">
          <option value="">全部</option>
          <option value="action">action (写)</option>
          <option value="function">function (读)</option>
        </select>
        <button @click="loadActions" class="ae-btn">[REFRESH] 刷新</button>
        <a href="/api/v2/action/_docs" target="_blank" class="ae-btn-link">[DOC] Swagger UI</a>
      </div>
    </div>

    <div class="ae-list">
      <div
        v-for="action in filteredActions"
        :key="action.action_id"
        class="ae-card"
        :class="{ 'ae-function': action.operation_type === 'function' }"
      >
        <div class="ae-card-header">
          <div class="ae-title">
            <span class="ae-badge" :class="`ae-badge-${action.operation_type}`">
              {{ action.operation_type }}
            </span>
            <code class="ae-id">{{ action.action_id }}</code>
            <span v-if="action.requires_admin" class="ae-admin">[SYMBOL] admin</span>
          </div>
          <button @click="openTryDialog(action)" class="ae-btn-try">▶ Try</button>
        </div>
        <p class="ae-desc">{{ action.description }}</p>
        <div class="ae-meta">
          <span>[SYMBOL] {{ action.category || 'business' }}</span>
          <span v-if="action.object_type">[DECORATIVE] {{ action.object_type }}</span>
          <span v-if="action.idempotent">[DECORATIVE] idempotent</span>
        </div>
      </div>
    </div>

    <!-- 试调对话框 -->
    <div v-if="selectedAction" class="ae-modal" @click.self="closeTryDialog">
      <div class="ae-modal-content">
        <div class="ae-modal-header">
          <h3>试调: {{ selectedAction.action_id }}</h3>
          <button @click="closeTryDialog" class="ae-btn-close">×</button>
        </div>
        <div class="ae-modal-body">
          <p class="ae-modal-desc">{{ selectedAction.description }}</p>
          <div v-if="formFields.length > 0" class="ae-form">
            <div v-for="field in formFields" :key="field.name" class="ae-form-field">
              <label>
                {{ field.label }}
                <span v-if="field.required" class="ae-required">*</span>
                <span class="ae-field-type">({{ field.type }})</span>
              </label>
              <!-- 字符串输入 -->
              <input
                v-if="field.type === 'string' && !field.enum && field.format !== 'date'"
                v-model="formData[field.name]"
                :type="field.format === 'email' ? 'email' : 'text'"
                class="ae-input"
              />
              <!-- 日期 -->
              <input
                v-else-if="field.type === 'string' && field.format === 'date'"
                v-model="formData[field.name]"
                type="date"
                class="ae-input"
              />
              <!-- 枚举 -->
              <select
                v-else-if="field.enum"
                v-model="formData[field.name]"
                class="ae-input"
              >
                <option value="">-- 请选择 --</option>
                <option v-for="opt in field.enum" :key="opt" :value="opt">{{ opt }}</option>
              </select>
              <!-- 数字 -->
              <input
                v-else-if="field.type === 'integer' || field.type === 'number'"
                v-model.number="formData[field.name]"
                type="number"
                class="ae-input"
              />
              <!-- 布尔 -->
              <label v-else-if="field.type === 'boolean'" class="ae-checkbox-label">
                <input v-model="formData[field.name]" type="checkbox" />
                <span>{{ formData[field.name] ? 'true' : 'false' }}</span>
              </label>
              <!-- JSON 对象 -->
              <textarea
                v-else-if="field.type === 'object' || field.type === 'array'"
                v-model="formData[field.name]"
                class="ae-textarea"
                rows="4"
                :placeholder="field.type === 'object' ? '{...}' : '[...]'"
              />
              <span v-if="errors[field.name]" class="ae-error">{{ errors[field.name] }}</span>
            </div>
          </div>
          <div v-else class="ae-no-input">此 Action 无需参数</div>

          <div class="ae-actions">
            <button
              @click="submitTry"
              :disabled="submitting"
              class="ae-btn-submit"
            >
              {{ submitting ? '执行中...' : '[DECORATIVE] 执行' }}
            </button>
            <button @click="closeTryDialog" class="ae-btn-cancel">取消</button>
          </div>

          <div v-if="result" class="ae-result">
            <h4>结果:</h4>
            <pre>{{ JSON.stringify(result, null, 2) }}</pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { useBoAction } from '@/composables/useBoAction'
import { apiV2 } from '@/utils/httpClient'

const { callPost, callGet } = useBoAction()

const actions = ref([])
const search = ref('')
const filterType = ref('')
const selectedAction = ref(null)
const formData = reactive({})
const errors = ref({})
const submitting = ref(false)
const result = ref(null)

const formFields = ref([])

const filteredActions = computed(() => {
  return actions.value.filter(a => {
    if (filterType.value && a.operation_type !== filterType.value) return false
    if (search.value) {
      const q = search.value.toLowerCase()
      return (
        a.action_id.toLowerCase().includes(q) ||
        (a.description || '').toLowerCase().includes(q) ||
        (a.category || '').toLowerCase().includes(q)
      )
    }
    return true
  })
})

async function loadActions() {
  try {
    const res = await apiV2.get('/action/_schemas')
    actions.value = res.data?.actions || []
  } catch (e) {
    console.error('[ActionExplorer] loadActions failed:', e)
  }
}

function openTryDialog(action) {
  selectedAction.value = action
  result.value = null
  // 解析 input_schema 为表单字段
  formFields.value = []
  Object.keys(formData).forEach(k => delete formData[k])

  if (action.input_schema && action.input_schema.properties) {
    for (const [name, prop] of Object.entries(action.input_schema.properties)) {
      formFields.value.push({
        name,
        type: prop.type || 'string',
        required: action.input_schema.required?.includes(name) || false,
        enum: prop.enum || null,
        format: prop.format || null,
      })
      if (prop.default !== undefined) {
        formData[name] = prop.default
      } else if (prop.type === 'boolean') {
        formData[name] = false
      }
    }
  }
}

function closeTryDialog() {
  selectedAction.value = null
  result.value = null
}

function validate() {
  errors.value = {}
  for (const f of formFields.value) {
    const v = formData[f.name]
    if (f.required && (v === undefined || v === null || v === '')) {
      errors.value[f.name] = `${f.name} 必填`
    }
  }
  return Object.keys(errors.value).length === 0
}

async function submitTry() {
  if (!validate()) return
  submitting.value = true
  result.value = null
  try {
    const isFunction = selectedAction.value.operation_type === 'function'
    const payload = {}
    for (const f of formFields.value) {
      if (formData[f.name] !== undefined) {
        payload[f.name] = formData[f.name]
      }
    }
    const r = isFunction
      ? await callGet(selectedAction.value.action_id, payload)
      : await callPost(selectedAction.value.action_id, payload)
    result.value = r
  } catch (e) {
    result.value = { success: false, message: e.message }
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  loadActions()
})
</script>

<style scoped>
.action-explorer {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}
.ae-header h2 {
  margin: 0 0 4px 0;
  color: #1f2937;
}
.ae-subtitle {
  margin: 0 0 16px 0;
  color: #6b7280;
  font-size: 14px;
}
.ae-search {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.ae-search-input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 14px;
}
.ae-filter, .ae-btn, .ae-btn-link {
  padding: 8px 16px;
  border: 1px solid #d1d5db;
  background: #fff;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  text-decoration: none;
  color: #374151;
}
.ae-btn-link {
  color: #2563eb;
}
.ae-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 12px;
}
.ae-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-left: 4px solid #2563eb;
  border-radius: 6px;
  padding: 12px 16px;
  transition: box-shadow 0.2s;
}
.ae-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}
.ae-function {
  border-left-color: #10b981;
}
.ae-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.ae-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}
.ae-badge {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  text-transform: uppercase;
  font-weight: 600;
}
.ae-badge-action {
  background: #dbeafe;
  color: #1e40af;
}
.ae-badge-function {
  background: #d1fae5;
  color: #065f46;
}
.ae-id {
  font-family: monospace;
  font-size: 14px;
  color: #111827;
  font-weight: 600;
}
.ae-admin {
  font-size: 11px;
  color: #dc2626;
}
.ae-btn-try {
  background: #2563eb;
  color: #fff;
  border: none;
  padding: 4px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}
.ae-btn-try:hover {
  background: #1d4ed8;
}
.ae-desc {
  margin: 0 0 8px 0;
  font-size: 13px;
  color: #4b5563;
  line-height: 1.5;
}
.ae-meta {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: #6b7280;
}
.ae-modal {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}
.ae-modal-content {
  background: #fff;
  border-radius: 8px;
  width: 600px;
  max-width: 90vw;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
}
.ae-modal-header {
  padding: 16px 20px;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.ae-modal-header h3 {
  margin: 0;
  font-size: 16px;
  color: #1f2937;
}
.ae-btn-close {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #6b7280;
}
.ae-modal-body {
  padding: 16px 20px;
  overflow-y: auto;
}
.ae-modal-desc {
  margin: 0 0 16px 0;
  color: #6b7280;
  font-size: 13px;
}
.ae-form-field {
  margin-bottom: 12px;
}
.ae-form-field label {
  display: block;
  font-size: 13px;
  margin-bottom: 4px;
  font-weight: 500;
}
.ae-field-type {
  color: #9ca3af;
  font-size: 11px;
  font-weight: normal;
}
.ae-required {
  color: #dc2626;
}
.ae-input, .ae-textarea {
  width: 100%;
  padding: 6px 10px;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  font-size: 13px;
  box-sizing: border-box;
}
.ae-textarea {
  font-family: monospace;
}
.ae-checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
}
.ae-error {
  display: block;
  color: #dc2626;
  font-size: 11px;
  margin-top: 2px;
}
.ae-actions {
  display: flex;
  gap: 8px;
  margin-top: 16px;
}
.ae-btn-submit, .ae-btn-cancel {
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  border: none;
}
.ae-btn-submit {
  background: #2563eb;
  color: #fff;
}
.ae-btn-submit:disabled {
  background: #9ca3af;
  cursor: not-allowed;
}
.ae-btn-cancel {
  background: #e5e7eb;
  color: #374151;
}
.ae-result {
  margin-top: 16px;
  background: #f9fafb;
  padding: 12px;
  border-radius: 4px;
  border: 1px solid #e5e7eb;
}
.ae-result h4 {
  margin: 0 0 8px 0;
  font-size: 13px;
  color: #374151;
}
.ae-result pre {
  margin: 0;
  font-size: 12px;
  font-family: monospace;
  color: #1f2937;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 300px;
  overflow-y: auto;
}
.ae-no-input {
  color: #6b7280;
  text-align: center;
  padding: 16px;
  font-size: 13px;
}
</style>
