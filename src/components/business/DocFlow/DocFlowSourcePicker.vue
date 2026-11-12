<template>
  <div class="doc-flow-picker">
    <div class="doc-flow-picker__toolbar">
      <el-checkbox v-model="includeZero" @change="reload">显示未结量为 0 的行</el-checkbox>
      <AppButton variant="secondary" size="sm" :loading="loading" @click="reload">刷新</AppButton>
    </div>

    <el-table
      ref="tableRef"
      v-loading="loading"
      :data="rows"
      row-key="row_key"
      max-height="360"
      @selection-change="onSelectionChange"
    >
      <el-table-column type="selection" width="46" />
      <el-table-column
        v-for="col in columns"
        :key="col.field"
        :label="col.label"
        min-width="140"
      >
        <template #default="{ row }">{{ row.display_values[col.field] || '' }}</template>
      </el-table-column>
      <el-table-column label="数量" width="110">
        <template #default="{ row }">{{ formatQty(row.quantity) }}</template>
      </el-table-column>
      <el-table-column label="已生成" width="110">
        <template #default="{ row }">{{ formatQty(row.consumed_qty) }}</template>
      </el-table-column>
      <el-table-column label="未结" width="110">
        <template #default="{ row }">{{ formatQty(row.open_qty) }}</template>
      </el-table-column>
      <el-table-column label="本次生成" width="150">
        <template #default="{ row }">
          <el-input-number
            v-model="row.derive_qty"
            :min="0"
            :max="row.open_qty"
            :precision="4"
            :step="1"
            size="small"
            controls-position="right"
          />
        </template>
      </el-table-column>
    </el-table>

    <div class="doc-flow-picker__pager">
      <el-pagination
        layout="total, prev, pager, next"
        :total="total"
        :page-size="pageSize"
        :current-page="page"
        @current-change="onPageChange"
      />
    </div>
  </div>
</template>

<script setup>
import { nextTick, onMounted, ref } from 'vue'
import AppButton from '@/components/common/AppButton/AppButton.vue'
import { listRules, listSources } from '@/services/docFlowService'

const props = defineProps({
  ruleId: { type: String, required: true },
  preselectedIds: { type: Array, default: () => [] },
})
const emit = defineEmits(['change'])

const tableRef = ref(null)
const loading = ref(false)
const rows = ref([])
const columns = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const includeZero = ref(false)

function formatQty(value) {
  const num = Number(value || 0)
  return Number.isInteger(num) ? String(num) : num.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')
}

function rowKey(sourceId, sourceItem) {
  return `${sourceId}::${sourceItem || ''}`
}

function onSelectionChange(selection) {
  emit('change', selection.filter((row) => Number(row.derive_qty) > 0))
}

function onPageChange(next) {
  page.value = next
  reload()
}

async function loadColumns() {
  const data = await listRules({})
  const rule = (data.rules || []).find((item) => item.rule_id === props.ruleId)
  // `source_columns` 由服务端把 display_fields 解析成 {field, label}；前端不猜标签
  columns.value = rule?.source_columns || []
}

async function reload() {
  loading.value = true
  try {
    const data = await listSources(props.ruleId, {
      page: page.value,
      page_size: pageSize.value,
      include_zero_open: includeZero.value,
    })
    rows.value = (data.items || []).map((row) => ({
      ...row,
      row_key: rowKey(row.source_id, row.source_item),
      derive_qty: Number(row.open_qty || 0),
    }))
    total.value = Number(data.total || 0)
    await nextTick()
    const wanted = (props.preselectedIds || []).map(String)
    wanted.forEach((id) => {
      const target = rows.value.find((row) => String(row.source_id) === id)
      if (target && tableRef.value) tableRef.value.toggleRowSelection(target, true)
    })
    emit('change', rows.value.filter((row) => wanted.includes(String(row.source_id))))
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadColumns()
  await reload()
})
</script>

<style scoped>
.doc-flow-picker__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.doc-flow-picker__pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}
</style>