<template>
  <PageShell
    title="工程变更差异预览"
    :breadcrumbs="breadcrumbs"
  >
    <div class="ec-diff">
      <AppCard title="差异条件">
        <div class="ec-diff__form">
          <div class="ec-diff__field">
            <span class="ec-diff__label">工程结构</span>
            <el-select
              v-model="form.source_structure_id"
              filterable
              clearable
              placeholder="选择 usage=engineering 的结构"
              class="ec-diff__control"
              data-test="ec-diff-source"
            >
              <el-option
                v-for="item in engineeringStructures"
                :key="item.id"
                :label="structureLabel(item)"
                :value="item.id"
              />
            </el-select>
          </div>
          <div class="ec-diff__field">
            <span class="ec-diff__label">生产结构</span>
            <el-select
              v-model="form.target_structure_id"
              filterable
              clearable
              placeholder="选择 usage=production 的结构"
              class="ec-diff__control"
              data-test="ec-diff-target"
            >
              <el-option
                v-for="item in productionStructures"
                :key="item.id"
                :label="structureLabel(item)"
                :value="item.id"
              />
            </el-select>
          </div>
          <div class="ec-diff__field">
            <span class="ec-diff__label">基准日</span>
            <el-date-picker
              v-model="form.as_of"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="选择基准日"
              class="ec-diff__control"
              data-test="ec-diff-as-of"
            />
          </div>
          <AppButton
            variant="primary"
            data-test="ec-diff-run"
            :loading="diffLoading"
            @click="handleDiff"
          >
            生成差异预览
          </AppButton>
        </div>

        <el-alert
          v-if="structureError"
          type="warning"
          :closable="false"
          show-icon
          class="ec-diff__alert"
          data-test="ec-diff-structure-error"
          :title="structureError"
        />
        <el-alert
          v-if="diffError"
          type="error"
          :closable="false"
          show-icon
          class="ec-diff__alert"
          data-test="ec-diff-error"
          :title="diffError"
        />
      </AppCard>

      <AppCard v-if="diff" title="差异结果">
        <template #extra>
          <el-checkbox
            :model-value="allSelected"
            :indeterminate="someSelected && !allSelected"
            data-test="ec-diff-select-all"
            @change="toggleAll"
          >
            全选差异行
          </el-checkbox>
        </template>

        <div class="ec-diff__summary" data-test="ec-diff-summary">
          <el-tag type="success" size="small">新增 {{ diff.summary?.add ?? 0 }}</el-tag>
          <el-tag type="primary" size="small">修改 {{ diff.summary?.modify ?? 0 }}</el-tag>
          <el-tag type="danger" size="small">移除 {{ diff.summary?.remove ?? 0 }}</el-tag>
          <span class="ec-diff__meta">
            基准日 {{ diff.as_of || '—' }} · 工程版本 {{ diff.source_revision ?? '—' }} ·
            生产版本 {{ diff.target_revision ?? '—' }}
          </span>
        </div>

        <el-alert
          v-if="ambiguousRows.length"
          type="warning"
          :closable="false"
          show-icon
          class="ec-diff__alert"
          data-test="ec-diff-ambiguous"
          :title="`存在 ${ambiguousRows.length} 组同键多行差异，需人工确认（不会自动生成明细）`"
        >
          <div v-for="item in ambiguousRows" :key="item.match_key" class="ec-diff__ambiguous-line">
            {{ item.match_key }}：{{ item.message }}
          </div>
        </el-alert>

        <el-table
          :data="diff.rows"
          row-key="match_key"
          border
          data-test="ec-diff-table"
        >
          <el-table-column label="选择" width="70">
            <template #default="{ row }">
              <el-checkbox
                :model-value="isSelected(row)"
                data-test="ec-diff-row-check"
                @change="value => toggleRow(row, value)"
              />
            </template>
          </el-table-column>
          <el-table-column label="动作" width="90">
            <template #default="{ row }">
              <el-tag :type="lineTypeTagType(row.line_type)" size="small" effect="dark">
                {{ lineTypeLabel(row.line_type) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="组件物料" width="100">
            <template #default="{ row }">{{ row.component_item_id ?? '—' }}</template>
          </el-table-column>
          <el-table-column prop="match_key" label="匹配键" min-width="180" show-overflow-tooltip />
          <el-table-column label="旧用量" width="100">
            <template #default="{ row }">{{ fmt(row.old_qty_per) }}</template>
          </el-table-column>
          <el-table-column label="新用量" width="100">
            <template #default="{ row }">{{ fmt(row.new_qty_per) }}</template>
          </el-table-column>
          <el-table-column label="旧失效日" width="120">
            <template #default="{ row }">{{ fmt(row.old_valid_to) }}</template>
          </el-table-column>
          <el-table-column label="新失效日" width="120">
            <template #default="{ row }">{{ fmt(row.new_valid_to) }}</template>
          </el-table-column>
          <template #empty>
            <span data-test="ec-diff-empty">工程结构与生产结构无差异</span>
          </template>
        </el-table>
      </AppCard>

      <AppCard v-if="diff" title="创建变更单">
        <div class="ec-diff__form ec-diff__form--create">
          <div class="ec-diff__field">
            <span class="ec-diff__label">变更标题</span>
            <el-input
              v-model="createForm.title"
              maxlength="120"
              placeholder="请输入变更标题"
              class="ec-diff__control"
              data-test="ec-diff-title"
            />
          </div>
          <div class="ec-diff__field">
            <span class="ec-diff__label">变更类型</span>
            <el-select
              v-model="createForm.change_type"
              class="ec-diff__control"
              data-test="ec-diff-change-type"
            >
              <el-option
                v-for="option in CHANGE_TYPE_OPTIONS"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
          </div>
          <div class="ec-diff__field">
            <span class="ec-diff__label">生效日</span>
            <el-date-picker
              v-model="createForm.effective_date"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="选择生效日"
              class="ec-diff__control"
              data-test="ec-diff-effective-date"
            />
          </div>
          <div class="ec-diff__field ec-diff__field--wide">
            <span class="ec-diff__label">变更原因</span>
            <el-input
              v-model="createForm.reason"
              type="textarea"
              :rows="2"
              maxlength="2000"
              placeholder="说明本次变更原因"
              data-test="ec-diff-reason"
            />
          </div>
          <div class="ec-diff__actions">
            <span class="ec-diff__selected" data-test="ec-diff-selected-count">
              已勾选 {{ selectedRows.length }} 行
            </span>
            <AppButton
              variant="primary"
              data-test="ec-diff-create"
              :loading="createLoading"
              @click="handleCreate"
            >
              创建变更单
            </AppButton>
          </div>
        </div>

        <el-alert
          v-if="createError"
          type="error"
          :closable="false"
          show-icon
          class="ec-diff__alert"
          data-test="ec-diff-create-error"
          :title="createError"
        />
      </AppCard>
    </div>
  </PageShell>
</template>

<script setup>
import { computed, reactive, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { PageShell, AppCard, AppButton } from '@/components/common'
import boService from '@/services/boService'
import { diffStructures, createChange } from '@/services/engineeringChangeService'

defineOptions({ name: 'EngineeringChangeDiffPage' })

const CHANGE_TYPE_OPTIONS = [
  { value: 'new', label: '首次工程 BOM' },
  { value: 'revise', label: '改版' },
  { value: 'obsolete', label: '停用' }
]

const LINE_TYPE_LABELS = { add: '新增', modify: '修改', remove: '移除' }
const LINE_TYPE_TAG_TYPES = { add: 'success', modify: 'primary', remove: 'danger' }

const router = useRouter()

function todayText() {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

const breadcrumbs = [
  { label: '工程变更', to: '/master-data/engineering-change' },
  { label: '差异预览' }
]

const form = reactive({
  source_structure_id: null,
  target_structure_id: null,
  as_of: todayText()
})

const createForm = reactive({
  title: '',
  change_type: 'revise',
  effective_date: todayText(),
  reason: ''
})

const engineeringStructures = ref([])
const productionStructures = ref([])
const structureError = ref('')
const diff = ref(null)
const diffLoading = ref(false)
const diffError = ref('')
const selectedKeys = ref([])
const createLoading = ref(false)
const createError = ref('')

const ambiguousRows = computed(() => diff.value?.ambiguous || [])
const selectedRows = computed(() => {
  const rows = diff.value?.rows || []
  return rows.filter(row => selectedKeys.value.includes(rowKey(row)))
})
const allSelected = computed(
  () => (diff.value?.rows || []).length > 0 && selectedRows.value.length === diff.value.rows.length
)
const someSelected = computed(() => selectedRows.value.length > 0)

function rowKey(row) {
  return row?.match_key || `${row?.line_type}-${row?.component_item_id}-${row?.structure_line_id}`
}

function structureLabel(item) {
  const parts = [`#${item.id}`, `物料 ${item.item_id ?? '—'}`, `版本 ${item.revision ?? '—'}`]
  if (item.alternative_no) parts.push(`替代 ${item.alternative_no}`)
  return parts.join(' · ')
}

function lineTypeLabel(value) {
  return LINE_TYPE_LABELS[value] || value || '—'
}

function lineTypeTagType(value) {
  return LINE_TYPE_TAG_TYPES[value] || 'info'
}

function fmt(value) {
  return value === null || value === undefined || value === '' ? '—' : value
}

function normalizeList(result) {
  if (!result?.success) return []
  const payload = result.data
  if (Array.isArray(payload)) return payload
  if (Array.isArray(payload?.items)) return payload.items
  return []
}

async function loadStructures() {
  structureError.value = ''
  try {
    const [engineering, production] = await Promise.all([
      boService.query('item_structure', {
        usage: 'engineering',
        status: 'active',
        page: 1,
        page_size: 200
      }),
      boService.query('item_structure', {
        usage: 'production',
        status: 'active',
        page: 1,
        page_size: 200
      })
    ])
    engineeringStructures.value = normalizeList(engineering)
    productionStructures.value = normalizeList(production)
    if (!engineeringStructures.value.length || !productionStructures.value.length) {
      structureError.value = '未查询到可用的 active 工程结构或生产结构，请先在物料结构中维护。'
    }
  } catch (e) {
    structureError.value = e?.message || '工程结构 / 生产结构查询失败'
  }
}

function isSelected(row) {
  return selectedKeys.value.includes(rowKey(row))
}

function toggleRow(row, value) {
  const key = rowKey(row)
  const rest = selectedKeys.value.filter(item => item !== key)
  selectedKeys.value = value ? [...rest, key] : rest
}

function toggleAll(value) {
  selectedKeys.value = value ? (diff.value?.rows || []).map(rowKey) : []
}

async function handleDiff() {
  diffError.value = ''
  diff.value = null
  selectedKeys.value = []
  createError.value = ''

  if (!form.source_structure_id || !form.target_structure_id) {
    diffError.value = '请选择工程结构与生产结构'
    return
  }

  diffLoading.value = true
  try {
    const result = await diffStructures({
      source_structure_id: form.source_structure_id,
      target_structure_id: form.target_structure_id,
      as_of: form.as_of
    })
    if (!result.success) {
      diffError.value = result.message || '工程 BOM 差异预览失败'
      return
    }
    diff.value = result.data || null
    if (diff.value?.source_revision !== undefined && createForm.title === '') {
      createForm.title = `工程变更（结构 ${form.source_structure_id} → ${form.target_structure_id}）`
    }
  } catch (e) {
    diffError.value = e?.message || '工程 BOM 差异预览失败'
  } finally {
    diffLoading.value = false
  }
}

function buildLines() {
  return selectedRows.value.map(row => ({
    line_type: row.line_type,
    component_item_id: row.component_item_id,
    target_structure_id: row.target_structure_id,
    source_structure_id: row.source_structure_id,
    source_structure_line_id: row.source_structure_line_id,
    structure_line_id: row.structure_line_id,
    match_key: row.match_key,
    old_qty_per: row.old_qty_per,
    new_qty_per: row.new_qty_per,
    old_valid_to: row.old_valid_to,
    new_valid_to: row.new_valid_to
  }))
}

async function handleCreate() {
  createError.value = ''
  if (!createForm.title.trim()) {
    createError.value = '请填写变更标题'
    return
  }
  if (!createForm.effective_date) {
    createError.value = '请选择生效日'
    return
  }
  if (selectedRows.value.length === 0) {
    createError.value = '请至少勾选 1 条差异行'
    return
  }

  createLoading.value = true
  try {
    const result = await createChange({
      change_type: createForm.change_type,
      title: createForm.title.trim(),
      reason: createForm.reason.trim() || null,
      effective_date: createForm.effective_date,
      lines: buildLines()
    })
    if (!result.success) {
      createError.value = result.message || '工程变更单创建失败'
      return
    }
    const changeId = result.data?.id
    if (changeId) {
      router.push({ name: 'engineering-change-detail', params: { id: String(changeId) } })
      return
    }
    createError.value = '创建成功但未返回变更单 ID，请返回列表刷新查看'
  } catch (e) {
    createError.value = e?.message || '工程变更单创建失败'
  } finally {
    createLoading.value = false
  }
}

onMounted(loadStructures)
</script>

<style scoped lang="scss">
.ec-diff {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.ec-diff__form {
  display: flex;
  align-items: flex-end;
  gap: var(--spacing-md);
  flex-wrap: wrap;
}

.ec-diff__form--create {
  align-items: flex-start;
}

.ec-diff__field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ec-diff__field--wide {
  flex: 1 1 320px;
  min-width: 240px;
}

.ec-diff__label {
  font-size: 13px;
  color: var(--color-text-secondary);
}

.ec-diff__control {
  width: 240px;
}

.ec-diff__actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding-bottom: 2px;
}

.ec-diff__selected {
  font-size: 13px;
  color: var(--color-text-secondary);
}

.ec-diff__alert {
  margin-top: var(--spacing-sm);
}

.ec-diff__summary {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-sm);
  flex-wrap: wrap;
}

.ec-diff__meta {
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.ec-diff__ambiguous-line {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-top: 4px;
}
</style>
