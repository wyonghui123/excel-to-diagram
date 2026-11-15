<template>
  <div class="approval-policy-panel">
    <div class="toolbar">
      <el-select
        v-model="filters.scope_bo"
        class="filter-item"
        clearable
        filterable
        :placeholder="colLabel('scope_bo')"
        @change="reload()"
      >
        <el-option
          v-for="obj in objectChoices"
          :key="obj.object_type"
          :label="obj.name"
          :value="obj.object_type"
        />
      </el-select>
      <el-select
        v-model="filters.status"
        class="filter-item narrow"
        clearable
        :placeholder="colLabel('status')"
        @change="reload()"
      >
        <el-option
          v-for="(label, code) in dict('status')"
          :key="code"
          :label="label"
          :value="code"
        />
      </el-select>
      <el-input
        v-model="filters.keyword"
        class="filter-item keyword"
        clearable
        :placeholder="colLabel('code')"
        @keyup.enter="reload()"
      />
      <el-button type="primary" @click="reload()">{{ msg('query') }}</el-button>
      <el-button v-if="canWrite" plain type="primary" @click="openCreate">
        {{ msg('create') }}
      </el-button>
    </div>

    <el-table v-loading="loading" :data="rows" border size="small" :empty-text="msg('empty')">
      <el-table-column prop="code" :label="colLabel('code')" min-width="170" show-overflow-tooltip />
      <el-table-column prop="name" :label="colLabel('name')" min-width="160" show-overflow-tooltip />
      <el-table-column prop="scope_bo" :label="colLabel('scope_bo')" width="150" />
      <el-table-column prop="priority" :label="colLabel('priority')" width="80" align="right" />
      <el-table-column prop="condition_summary" :label="colLabel('condition_summary')" min-width="200" show-overflow-tooltip />
      <el-table-column prop="step_count" :label="colLabel('step_count')" width="90" align="right" />
      <el-table-column prop="version" :label="colLabel('version')" width="70" align="right" />
      <el-table-column :label="colLabel('status')" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="statusTone(row.status)">
            {{ dictLabel('status', row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column :label="msg('action')" width="150" fixed="right">
        <template #default="{ row }">
          <el-button v-if="canWrite" link type="primary" @click="openEdit(row)">
            {{ msg('edit') }}
          </el-button>
          <el-button link type="primary" @click="openPreview(row)">
            {{ msg('simulate') }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-if="total > pageSize"
      class="pager"
      layout="total, prev, pager, next"
      :current-page="page"
      :page-size="pageSize"
      :total="total"
      @current-change="onPageChange"
    />

    <!-- 编辑抽屉：表单 + JSON 条件 + 步骤行编辑（D-AP-08，不做流程画布） -->
    <el-drawer
      v-model="drawerVisible"
      :title="drawerMode === 'create' ? msg('create') : msg('edit')"
      size="760px"
      destroy-on-close
    >
      <el-form label-width="130px" label-position="left" size="small">
        <el-form-item :label="fieldLabel('code')" required>
          <el-input v-model="form.code" :placeholder="msg('policy_code_hint')" />
        </el-form-item>
        <el-form-item :label="fieldLabel('name')" required>
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item :label="fieldLabel('scope_bo')" required>
          <el-select v-model="form.scope_bo" filterable class="full-width">
            <el-option
              v-for="obj in objectChoices"
              :key="obj.object_type"
              :label="obj.name"
              :value="obj.object_type"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="fieldLabel('trigger_action')">
          <el-input v-model="form.trigger_action" />
        </el-form-item>
        <el-form-item :label="fieldLabel('priority')">
          <el-input-number v-model="form.priority" :min="0" :step="10" />
        </el-form-item>
        <el-form-item :label="fieldLabel('status')">
          <el-select v-model="form.status" class="full-width">
            <el-option
              v-for="(label, code) in dict('status')"
              :key="code"
              :label="label"
              :value="code"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="fieldLabel('effective_from')">
          <el-date-picker
            v-model="form.effective_from"
            type="datetime"
            value-format="YYYY-MM-DD HH:mm:ss"
            class="full-width"
          />
        </el-form-item>
        <el-form-item :label="fieldLabel('effective_to')">
          <el-date-picker
            v-model="form.effective_to"
            type="datetime"
            value-format="YYYY-MM-DD HH:mm:ss"
            class="full-width"
          />
        </el-form-item>
        <el-form-item :label="fieldLabel('description')">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item :label="fieldLabel('conditions_json')">
          <el-input v-model="form.conditionsText" type="textarea" :rows="7" spellcheck="false" />
          <div class="form-hint">{{ conditionFieldsHint }}</div>
        </el-form-item>
      </el-form>

      <div class="steps-header">
        <span class="steps-title">{{ fieldLabel('steps') }}</span>
        <el-button size="small" @click="addStep">{{ msg('step_add') }}</el-button>
      </div>
      <el-table :data="form.steps" size="small" border :empty-text="msg('steps_empty')">
        <el-table-column :label="fieldLabel('step_no')" width="72">
          <template #default="{ row }">
            <el-input-number v-model="row.step_no" :min="1" :controls="false" size="small" />
          </template>
        </el-table-column>
        <el-table-column :label="fieldLabel('approver_type')" width="120">
          <template #default="{ row }">
            <el-select v-model="row.approver_type" size="small">
              <el-option
                v-for="(label, code) in dict('approver_type')"
                :key="code"
                :label="label"
                :value="code"
              />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column :label="fieldLabel('approver_ref')" min-width="140">
          <template #default="{ row }">
            <el-input v-model="row.approver_ref" size="small" />
          </template>
        </el-table-column>
        <el-table-column :label="fieldLabel('approve_mode')" width="130">
          <template #default="{ row }">
            <el-select v-model="row.approve_mode" size="small">
              <el-option
                v-for="(label, code) in dict('approve_mode')"
                :key="code"
                :label="label"
                :value="code"
              />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column :label="fieldLabel('min_amount')" width="110">
          <template #default="{ row }">
            <el-input-number v-model="row.min_amount" :controls="false" size="small" />
          </template>
        </el-table-column>
        <el-table-column :label="fieldLabel('max_amount')" width="110">
          <template #default="{ row }">
            <el-input-number v-model="row.max_amount" :controls="false" size="small" />
          </template>
        </el-table-column>
        <el-table-column :label="fieldLabel('sla_hours')" width="90">
          <template #default="{ row }">
            <el-input-number v-model="row.sla_hours" :min="0" :controls="false" size="small" />
          </template>
        </el-table-column>
        <el-table-column width="60" align="center">
          <template #default="{ $index }">
            <el-button link type="danger" @click="form.steps.splice($index, 1)">
              {{ msg('step_remove') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="drawer-footer">
        <el-button @click="drawerVisible = false">{{ msg('cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="submit">
          {{ msg('save') }}
        </el-button>
      </div>
    </el-drawer>

    <!-- 命中试算：薄适配 resolver，展示快照、条件解释与审批链 -->
    <el-dialog v-model="previewVisible" :title="msg('preview_title')" width="760px">
      <div class="preview-inputs">
        <el-select v-model="previewForm.object_type" filterable :placeholder="fieldLabel('object_type')" class="filter-item">
          <el-option
            v-for="obj in objectChoices"
            :key="obj.object_type"
            :label="obj.name"
            :value="obj.object_type"
          />
        </el-select>
        <el-input v-model="previewForm.record_id" :placeholder="fieldLabel('record_id')" class="filter-item" />
        <el-input v-model="previewForm.trigger_action" :placeholder="fieldLabel('trigger_action')" class="filter-item narrow" />
        <el-button type="primary" :loading="previewing" @click="runPreview">
          {{ msg('preview_run') }}
        </el-button>
      </div>

      <el-empty v-if="!previewResult" :description="msg('preview_empty')" :image-size="60" />

      <div v-else class="preview-result">
        <div class="preview-summary">
          <el-tag :type="previewResult.required ? 'success' : 'info'" size="small">
            {{ previewResult.required ? msg('preview_hit') : msg('preview_miss') }}
          </el-tag>
          <span class="summary-item">{{ dictLabel('reason', previewResult.reason) }}</span>
          <span v-if="previewResult.policy_code" class="summary-item">
            {{ colLabel('code') }}: {{ previewResult.policy_code }}
          </span>
          <span v-if="previewResult.amount !== undefined" class="summary-item">
            amount: {{ previewResult.amount }}
          </span>
        </div>

        <template v-if="previewSnapshot">
          <el-descriptions :column="2" border size="small" class="preview-block">
            <el-descriptions-item :label="fieldLabel('name')">
              {{ previewSnapshot.policy_name }}
            </el-descriptions-item>
            <el-descriptions-item :label="fieldLabel('priority')">
              {{ previewSnapshot.priority }}
            </el-descriptions-item>
            <el-descriptions-item :label="msg('version_label')">
              {{ previewSnapshot.policy_version }}
            </el-descriptions-item>
            <el-descriptions-item :label="fieldLabel('trigger_action')">
              {{ previewSnapshot.trigger_action }}
            </el-descriptions-item>
          </el-descriptions>

          <div class="preview-section-title">{{ msg('explain_title') }}</div>
          <el-table :data="previewSnapshot.conditions_explain || []" size="small" border>
            <el-table-column prop="field" :label="colLabel('condition_summary')" min-width="120" />
            <el-table-column :label="fieldLabel('operator')" width="110">
              <template #default="{ row }">{{ dictLabel('operator', row.op) || row.op }}</template>
            </el-table-column>
            <el-table-column prop="expected" :label="fieldLabel('expected')" min-width="110" />
            <el-table-column prop="actual" :label="fieldLabel('actual')" min-width="110" />
            <el-table-column :label="fieldLabel('explain_result')" width="110">
              <template #default="{ row }">
                <el-tag :type="row.passed ? 'success' : 'danger'" size="small">
                  {{ row.passed ? msg('explain_passed') : msg('explain_failed') }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>

          <div class="preview-section-title">{{ fieldLabel('steps') }}</div>
          <el-table :data="previewSnapshot.steps || []" size="small" border>
            <el-table-column prop="step_no" :label="fieldLabel('step_no')" width="72" />
            <el-table-column prop="approver_type" :label="fieldLabel('approver_type')" width="100" />
            <el-table-column prop="approver_ref" :label="fieldLabel('approver_ref')" min-width="130" />
            <el-table-column prop="approve_mode" :label="fieldLabel('approve_mode')" width="90" />
            <el-table-column prop="min_amount" :label="fieldLabel('min_amount')" width="100" />
            <el-table-column prop="max_amount" :label="fieldLabel('max_amount')" width="100" />
            <el-table-column prop="sla_hours" :label="fieldLabel('sla_hours')" width="80" />
          </el-table>

          <el-collapse class="preview-block">
            <el-collapse-item :title="msg('snapshot_title')" name="snapshot">
              <pre class="snapshot-json">{{ snapshotJson }}</pre>
            </el-collapse-item>
          </el-collapse>
        </template>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useMessage } from '@/composables/useMessage'
import {
  createApprovalPolicy,
  getApprovalPolicy,
  getApprovalPolicyOptions,
  listApprovalPolicies,
  previewApprovalPolicy,
  saveApprovalPolicy,
} from '@/services/approvalPolicyService'

const props = defineProps({
  meta: { type: Object, default: () => ({}) },
  objectTypeOptions: { type: Array, default: () => [] },
  canWrite: { type: Boolean, default: false },
})

const message = useMessage()

const meta = computed(() => props.meta || {})
const msg = key => meta.value.messages?.[key] || key
const colLabel = key => meta.value.columns?.[key] || key
const fieldLabel = key => meta.value.fields?.[key] || colLabel(key)
const dict = kind => meta.value.dictionaries?.[kind] || {}
const dictLabel = (kind, code) => dict(kind)[code] || code || ''

const loading = ref(false)
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const filters = reactive({ scope_bo: '', status: '', keyword: '' })

const options = ref({ objects: [], operators: [], approver_types: [], statuses: [], approve_modes: [] })
const objectChoices = computed(() => {
  const objects = options.value.objects?.length
    ? options.value.objects
    : (props.objectTypeOptions || []).map(item => ({
        object_type: item.value || item.object_type || item.id,
        name: item.label || item.name || item.value || item.id,
      }))
  return objects
})

const drawerVisible = ref(false)
const drawerMode = ref('create')
const editingId = ref(null)
const saving = ref(false)
const form = reactive({
  code: '',
  name: '',
  scope_bo: '',
  trigger_action: 'submit',
  priority: 100,
  status: 'active',
  description: '',
  effective_from: '',
  effective_to: '',
  conditionsText: '[]',
  steps: [],
})

const previewVisible = ref(false)
const previewing = ref(false)
const previewResult = ref(null)
const previewForm = reactive({ object_type: '', record_id: '', trigger_action: 'submit' })

const previewSnapshot = computed(() => previewResult.value?.snapshot || null)
const snapshotJson = computed(() =>
  previewSnapshot.value ? JSON.stringify(previewSnapshot.value, null, 2) : ''
)

const conditionFieldsHint = computed(() => {
  const obj = objectChoices.value.find(item => item.object_type === form.scope_bo)
  const fields = obj?.fields || []
  if (!fields.length) return ''
  return fields.map(field => (field.name ? `${field.id}(${field.name})` : field.id)).join(' · ')
})

function statusTone(status) {
  if (status === 'active') return 'success'
  if (status === 'draft') return 'warning'
  return 'info'
}

async function loadOptions() {
  const response = await getApprovalPolicyOptions()
  if (response.success) {
    options.value = response.data || options.value
  } else {
    message.error(response.message || msg('options_failed'))
  }
}

async function reload(targetPage = 1) {
  page.value = targetPage
  loading.value = true
  try {
    const response = await listApprovalPolicies({
      page: page.value,
      page_size: pageSize.value,
      scope_bo: filters.scope_bo || undefined,
      status: filters.status || undefined,
      keyword: filters.keyword || undefined,
    })
    if (response.success) {
      const data = response.data || {}
      rows.value = data.items || []
      total.value = data.total || 0
    } else {
      message.error(response.message || msg('load_failed'))
    }
  } finally {
    loading.value = false
  }
}

function onPageChange(targetPage) {
  reload(targetPage)
}

function emptyForm() {
  return {
    code: '',
    name: '',
    scope_bo: '',
    trigger_action: 'submit',
    priority: 100,
    status: 'active',
    description: '',
    effective_from: '',
    effective_to: '',
    conditionsText: '[]',
    steps: [],
  }
}

function applyForm(policy) {
  form.code = policy.code || ''
  form.name = policy.name || ''
  form.scope_bo = policy.scope_bo || ''
  form.trigger_action = policy.trigger_action || 'submit'
  form.priority = policy.priority ?? 100
  form.status = policy.status || 'active'
  form.description = policy.description || ''
  form.effective_from = policy.effective_from || ''
  form.effective_to = policy.effective_to || ''
  form.conditionsText = JSON.stringify(policy.conditions || [], null, 2)
  form.steps = (policy.steps || []).map(step => ({ ...step }))
}

function openCreate() {
  Object.assign(form, emptyForm())
  editingId.value = null
  drawerMode.value = 'create'
  drawerVisible.value = true
}

async function openEdit(row) {
  const response = await getApprovalPolicy(row.id)
  if (!response.success) {
    message.error(response.message || msg('detail_failed'))
    return
  }
  applyForm(response.data || {})
  editingId.value = row.id
  drawerMode.value = 'edit'
  drawerVisible.value = true
}

function addStep() {
  form.steps.push({
    step_no: form.steps.length + 1,
    approver_type: 'role',
    approver_ref: '',
    approve_mode: 'any',
    min_amount: null,
    max_amount: null,
    sla_hours: null,
  })
}

function buildPayload() {
  let conditions
  try {
    conditions = JSON.parse(form.conditionsText || '[]')
  } catch (_) {
    throw new Error(msg('conditions_invalid'))
  }
  if (!Array.isArray(conditions)) throw new Error(msg('conditions_invalid'))
  return {
    code: form.code.trim(),
    name: form.name.trim(),
    scope_bo: form.scope_bo,
    trigger_action: form.trigger_action || 'submit',
    priority: form.priority,
    status: form.status,
    description: form.description,
    effective_from: form.effective_from || null,
    effective_to: form.effective_to || null,
    conditions,
    steps: form.steps.map((step, index) => ({
      ...step,
      step_no: step.step_no ?? index + 1,
    })),
  }
}

async function submit() {
  let payload
  try {
    payload = buildPayload()
  } catch (error) {
    message.error(error.message || msg('save_failed'))
    return
  }
  saving.value = true
  try {
    const response = drawerMode.value === 'create'
      ? await createApprovalPolicy(payload)
      : await saveApprovalPolicy(editingId.value, payload)
    if (!response.success) {
      message.error(response.message || msg('save_failed'))
      return
    }
    const version = response.data?.version ?? ''
    message.success(msg('save_success').replace('{version}', version))
    drawerVisible.value = false
    reload(page.value)
  } finally {
    saving.value = false
  }
}

function openPreview(row) {
  previewResult.value = null
  previewForm.object_type = row?.scope_bo || filters.scope_bo || ''
  previewForm.record_id = ''
  previewForm.trigger_action = row?.trigger_action || 'submit'
  previewVisible.value = true
}

async function runPreview() {
  if (!previewForm.object_type || !previewForm.record_id) {
    message.warning(msg('preview_inputs_required'))
    return
  }
  previewing.value = true
  try {
    const response = await previewApprovalPolicy({
      object_type: previewForm.object_type,
      record_id: previewForm.record_id,
      trigger_action: previewForm.trigger_action || 'submit',
    })
    if (!response.success) {
      message.error(response.message || msg('preview_failed'))
      return
    }
    previewResult.value = response.data
  } finally {
    previewing.value = false
  }
}

onMounted(async () => {
  await loadOptions()
  await reload()
})
</script>

<style scoped>
.approval-policy-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.filter-item {
  width: 180px;
}

.filter-item.narrow {
  width: 130px;
}

.filter-item.keyword {
  width: 220px;
}

.pager {
  justify-content: flex-end;
}

.full-width {
  width: 100%;
}

.form-hint {
  margin-top: 4px;
  color: #909399;
  font-size: 12px;
  line-height: 1.5;
  word-break: break-all;
}

.steps-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 8px 0;
}

.steps-title {
  font-weight: 600;
}

.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}

.preview-inputs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.preview-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
}

.preview-block {
  margin-top: 12px;
}

.preview-section-title {
  margin: 14px 0 6px;
  font-weight: 600;
}

.snapshot-json {
  max-height: 260px;
  overflow: auto;
  margin: 0;
  padding: 8px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.5;
}
</style>