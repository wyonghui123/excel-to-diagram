<template>
  <div class="diff-view" data-test="diff-view">
    <div class="diff-view__summary" data-test="diff-summary">
      <el-tag type="success" size="small" disable-transitions data-test="diff-summary-add">
        新增 {{ summaryCount('add') }}
      </el-tag>
      <el-tag type="primary" size="small" disable-transitions data-test="diff-summary-modify">
        修改 {{ summaryCount('modify') }}
      </el-tag>
      <el-tag type="danger" size="small" disable-transitions data-test="diff-summary-remove">
        移除 {{ summaryCount('remove') }}
      </el-tag>
      <span v-if="revisionText" class="diff-view__meta" data-test="diff-revision">
        {{ revisionText }}
      </span>
      <span v-if="diff?.as_of" class="diff-view__meta" data-test="diff-as-of">
        对比基准日 {{ diff.as_of }}
      </span>
    </div>

    <el-alert
      v-if="errorMessage"
      type="error"
      :closable="false"
      show-icon
      :title="errorMessage"
      data-test="diff-error"
    />

    <el-alert
      v-else-if="ambiguous.length"
      type="warning"
      :closable="false"
      show-icon
      data-test="diff-ambiguous"
    >
      <template #title>存在 {{ ambiguous.length }} 处匹配键歧义，未产出差异行</template>
      <div v-for="item in ambiguous" :key="item.match_key" class="diff-view__ambiguous-item">
        {{ item.match_key }}：{{ item.message }}
      </div>
    </el-alert>

    <el-table
      v-loading="loading"
      :data="rows"
      size="small"
      border
      :row-class-name="rowClassName"
      data-test="diff-table"
    >
      <el-table-column label="类型" width="88">
        <template #default="{ row }">
          <el-tag :type="lineTypeTag(row.line_type)" size="small" disable-transitions>
            {{ lineTypeLabel(row.line_type) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="组件" min-width="160">
        <template #default="{ row }">{{ componentLabel(row) }}</template>
      </el-table-column>
      <el-table-column label="替代组" width="110">
        <template #default="{ row }">{{ displayValue(row.substitute_group_code) }}</template>
      </el-table-column>
      <el-table-column label="工序号" width="90">
        <template #default="{ row }">{{ displayValue(row.operation_seq) }}</template>
      </el-table-column>
      <el-table-column label="字段差异" min-width="240">
        <template #default="{ row }">
          <span v-if="!fieldDiffs(row).length" class="diff-view__empty">—</span>
          <div
            v-for="entry in fieldDiffs(row)"
            :key="entry.field"
            class="diff-view__field"
            data-test="diff-field"
          >
            <span class="diff-view__field-label">{{ entry.label }}</span>
            <span v-if="entry.mode !== 'add'" class="diff-view__old">{{ entry.old }}</span>
            <span v-if="entry.mode === 'change'" class="diff-view__arrow">→</span>
            <span v-if="entry.mode !== 'remove'" class="diff-view__new">{{ entry.new }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="140">
        <template #default="{ row }">{{ displayValue(row.note) }}</template>
      </el-table-column>
      <template #empty>
        <span data-test="diff-empty">工程结构与生产结构无差异</span>
      </template>
    </el-table>
  </div>
</template>

<script setup>
/**
 * DiffView.vue - 工程 BOM 差异只读渲染（T13-10）
 *
 * 数据来自 POST /api/v1/engineering-changes/diff（engineeringChangeService.diffStructures）。
 * 只读：不提供勾选/创建变更单能力，变更单流程仍由既有页面承担。
 * 行语义：add=新增 / modify=字段变化 / remove=移除；字段差异仅展示实际变化的项。
 */

import { computed, onMounted, ref, watch } from 'vue'
import { diffStructures } from '@/services/engineeringChangeService'
import { logger } from '@/utils/logger'

const props = defineProps({
  sourceStructureId: { type: [Number, String], default: null },
  targetStructureId: { type: [Number, String], default: null },
  asOf: { type: String, default: '' },
  // 可选：component_item_id → 显示名
  itemLabels: { type: Object, default: () => ({}) },
  autoLoad: { type: Boolean, default: true }
})

const emit = defineEmits(['loaded', 'error'])

const loading = ref(false)
const diff = ref(null)
const errorMessage = ref('')

const FIELD_LABELS = {
  qty_per: '单位用量',
  fixed_qty: '固定用量',
  valid_to: '有效期至',
  optional_flag: '可选件'
}
const LINE_TYPE_LABELS = { add: '新增', modify: '修改', remove: '移除' }
const LINE_TYPE_TAGS = { add: 'success', modify: 'primary', remove: 'danger' }

const rows = computed(() => (Array.isArray(diff.value?.rows) ? diff.value.rows : []))
const ambiguous = computed(() =>
  Array.isArray(diff.value?.ambiguous) ? diff.value.ambiguous : []
)
const revisionText = computed(() => {
  const from = diff.value?.source_revision
  const to = diff.value?.target_revision
  if (from === undefined && to === undefined) return ''
  return `版本 ${displayValue(from)} → ${displayValue(to)}`
})

function summaryCount(type) {
  return diff.value?.summary?.[type] ?? 0
}

function lineTypeLabel(type) {
  return LINE_TYPE_LABELS[type] || type || '-'
}

function lineTypeTag(type) {
  return LINE_TYPE_TAGS[type] || 'info'
}

function componentLabel(row) {
  const key = row?.component_item_id
  if (key === null || key === undefined) return '-'
  return props.itemLabels[key] || String(key)
}

function displayValue(value) {
  return value === null || value === undefined || value === '' ? '-' : String(value)
}

function isEmpty(value) {
  return value === null || value === undefined || value === ''
}

function pick(row, side, field) {
  const obj = row?.[side]
  if (obj && typeof obj === 'object' && field in obj) return obj[field]
  const flatKey = side === 'old' ? `old_${field}` : `new_${field}`
  return row?.[flatKey]
}

function normalize(value) {
  return isEmpty(value) ? '' : String(value)
}

/** 当前行要展示的字段差异（add 只取新值 / remove 只取旧值 / modify 只取变化项） */
function fieldDiffs(row) {
  const type = row?.line_type
  if (!LINE_TYPE_LABELS[type]) return []
  const entries = []
  for (const field of Object.keys(FIELD_LABELS)) {
    const oldVal = pick(row, 'old', field)
    const newVal = pick(row, 'new', field)
    if (type === 'modify') {
      if (normalize(oldVal) === normalize(newVal)) continue
      entries.push({
        field,
        label: FIELD_LABELS[field],
        old: displayValue(oldVal),
        new: displayValue(newVal),
        mode: 'change'
      })
    } else if (type === 'add') {
      if (isEmpty(newVal)) continue
      entries.push({ field, label: FIELD_LABELS[field], old: '', new: displayValue(newVal), mode: 'add' })
    } else {
      if (isEmpty(oldVal)) continue
      entries.push({ field, label: FIELD_LABELS[field], old: displayValue(oldVal), new: '', mode: 'remove' })
    }
  }
  return entries
}

function rowClassName({ row }) {
  return `diff-row diff-row--${row?.line_type || 'unknown'}`
}

async function loadDiff() {
  if (!props.sourceStructureId || !props.targetStructureId) {
    diff.value = null
    errorMessage.value = ''
    return
  }
  loading.value = true
  errorMessage.value = ''
  try {
    const result = await diffStructures({
      source_structure_id: props.sourceStructureId,
      target_structure_id: props.targetStructureId,
      as_of: props.asOf || undefined
    })
    if (!result?.success) {
      const message = result?.message || '工程 BOM 差异预览失败'
      errorMessage.value = message
      diff.value = null
      emit('error', message)
      return
    }
    diff.value = result.data || null
    emit('loaded', diff.value)
  } catch (err) {
    logger.warn('[DiffView] 差异预览失败', err)
    const message = err?.message || '工程 BOM 差异预览失败'
    errorMessage.value = message
    diff.value = null
    emit('error', message)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  if (props.autoLoad) loadDiff()
})

watch(
  () => [props.sourceStructureId, props.targetStructureId, props.asOf],
  () => {
    if (props.autoLoad) loadDiff()
  }
)

defineExpose({ reload: loadDiff })
</script>

<style scoped>
.diff-view__summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.diff-view__meta {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.diff-view__ambiguous-item {
  font-size: 12px;
  margin-top: 4px;
}

.diff-view__field {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  line-height: 20px;
}

.diff-view__field-label {
  color: var(--el-text-color-secondary);
}

.diff-view__old {
  color: var(--el-color-danger);
}

.diff-view__arrow {
  color: var(--el-text-color-secondary);
}

.diff-view__new {
  color: var(--el-color-success);
}

.diff-view__empty {
  color: var(--el-text-color-secondary);
}
</style>