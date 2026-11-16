<template>
  <PageShell
    title="导入交付面"
    subtitle="staging 三段式：落库 → 校验 → 提交；批次保留期后可下载错误报告"
  >
    <AppCard title="导入批次">
      <!-- 批次列表的列 / 标签 / 徽标由 meta/schemas/import_staging_rows.yaml
           的 list 块（批次聚合视图）驱动；对象类型是查询条件，放在工具栏。
           批次下钻抽屉是本页唯一保留的复合视图（动作 detail 只声明入口） -->
      <MetaResourcePage
        ref="resourceRef"
        object-type="import_staging_rows"
        :extra-params="extraParams"
        @row-action="onRowAction"
      >
        <template #toolbar>
          <div class="toolbar">
            <AppInput
              v-model="objectTypeInput"
              size="sm"
              placeholder="对象类型（如 item）"
              clearable
              class="w-170"
              @keyup.enter="applyFilter"
            />
            <AppButton variant="secondary" size="sm" @click="applyFilter">刷新</AppButton>
          </div>
        </template>
      </MetaResourcePage>
    </AppCard>

    <Drawer v-model="drawer" :title="`批次 ${currentBatch}`" width="920px">
      <div v-if="summary" class="summary">
        <div class="summary-item"><span>总行数</span><b>{{ summary.total }}</b></div>
        <div class="summary-item"><span>失败行</span><b class="bad">{{ summary.invalid }}</b></div>
        <div class="summary-item"><span>创建</span><b>{{ summary.created_at || '-' }}</b></div>
        <div class="summary-item"><span>过期</span><b>{{ summary.expires_at || '-' }}</b></div>
        <div class="summary-item"><span>保留</span><b>{{ summary.expired ? '已过期' : '有效' }}</b></div>
        <div class="spacer" />
        <AppButton
          variant="secondary"
          size="sm"
          :disabled="!summary.error_report_ready"
          :loading="downloading"
          @click="downloadReport"
        >
          下载错误报告
        </AppButton>
      </div>

      <div class="toolbar">
        <AppSelect
          v-model="rowFilters.status"
          :options="rowStatusOptions"
          size="sm"
          placeholder="全部状态"
          clearable
          class="w-140"
        />
        <AppInput
          v-model="rowFilters.object_type"
          size="sm"
          placeholder="对象类型（如 item）"
          clearable
          class="w-170"
        />
        <AppButton variant="secondary" size="sm" :loading="rowLoading" @click="loadRows">查询</AppButton>
        <span class="spacer" />
        <span class="hint">共 {{ rowTotal }} 行</span>
      </div>

      <div v-if="rowError" class="alert">{{ rowError }}</div>
      <EmptyState
        v-else-if="!rowLoading && !rowsDetail.length"
        type="folder"
        title="该批次没有匹配的行"
      />
      <div v-else class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>对象</th>
              <th>行号</th>
              <th>状态</th>
              <th>错误字段</th>
              <th>错误码</th>
              <th>错误信息</th>
              <th>目标记录</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rowsDetail" :key="`${row.object_type}-${row.row_no}`">
              <td class="mono">{{ row.object_type }}</td>
              <td class="mono">{{ row.row_no }}</td>
              <td>
                <span :class="['tag', rowStatusClass(row.status)]">{{ rowStatusLabel(row.status) }}</span>
              </td>
              <td class="mono">{{ row.error_field || '-' }}</td>
              <td class="mono">{{ row.error_code || '-' }}</td>
              <td class="ellipsis" :title="row.error_message">{{ row.error_message || '-' }}</td>
              <td class="mono">{{ row.target_record_id || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <Pagination
        v-if="rowTotal > 0"
        v-model:current="rowPage"
        v-model:page-size="rowPageSize"
        :total="rowTotal"
        class="pager"
        @change="loadRows"
        @pageSizeChange="onRowSizeChange"
      />
    </Drawer>
  </PageShell>
</template>

<script setup>
import { computed, ref, reactive, onMounted, nextTick } from 'vue'
import {
  PageShell, AppCard, AppButton, AppInput, AppSelect, Drawer,
  EmptyState, Pagination, MetaResourcePage,
} from '@/components/common'
import { useMessage } from '@/composables/useMessage'
import {
  fetchImportBatch, fetchImportRows, fetchImportErrorReport,
  fetchIntegrationOptions,
} from '@/services/integrationService'

defineOptions({ name: 'IntegrationImports' })

// 语义色 → 现有样式类；标签与颜色本身仍来自 YAML 的 ui.options
const TAG_BY_COLOR = {
  success: 'tag-on',
  warning: 'tag-warn',
  danger: 'tag-bad',
  info: 'tag-off',
  gray: 'tag-off',
}

const toast = useMessage()
const resourceRef = ref(null)

// 对象类型是批次聚合视图的额外查询参数：输入后点「刷新」或回车才生效
const objectTypeInput = ref('')
const appliedObjectType = ref('')
const extraParams = computed(() => ({ object_type: appliedObjectType.value || undefined }))

async function applyFilter() {
  appliedObjectType.value = objectTypeInput.value.trim()
  // extraParams 作为 prop 传给列表页：先等父组件把新值传下去，否则 refresh 会读到上一轮参数
  await nextTick()
  resourceRef.value?.refresh?.()
}

const drawer = ref(false)
const currentBatch = ref('')
const summary = ref(null)
const downloading = ref(false)

const rowsDetail = ref([])
const rowTotal = ref(0)
const rowPage = ref(1)
const rowPageSize = ref(50)
const rowLoading = ref(false)
const rowError = ref('')
const rowFilters = reactive({ status: '', object_type: '' })

// 取值域来自后端 YAML 元数据（GET /integrations/options），前端不再维护常量数组
const stagingStatus = ref([])
const rowStatusOptions = computed(() => stagingStatus.value)
const stagingStatusMap = computed(() => Object.fromEntries(
  stagingStatus.value.map((item) => [item.value, item]),
))

function rowStatusLabel(status) {
  return stagingStatusMap.value[status]?.label || status
}

function rowStatusClass(status) {
  const color = stagingStatusMap.value[status]?.color
  return TAG_BY_COLOR[color] || 'tag-off'
}

function onRowAction({ action, row }) {
  if (action.id === 'detail' && row) openBatch(row)
}

// ---------------- 批次明细 ----------------
async function openBatch(row) {
  currentBatch.value = row.batch_no
  summary.value = null
  rowsDetail.value = []
  rowTotal.value = 0
  rowError.value = ''
  rowPage.value = 1
  rowFilters.status = ''
  rowFilters.object_type = ''
  drawer.value = true

  const res = await fetchImportBatch(row.batch_no)
  if (res.success) {
    summary.value = res.data || null
  } else {
    rowError.value = res.message || '加载批次汇总失败'
  }
  await loadRows()
}

async function loadRows() {
  if (!currentBatch.value) return
  rowLoading.value = true
  rowError.value = ''
  try {
    const res = await fetchImportRows(currentBatch.value, {
      status: rowFilters.status || undefined,
      object_type: rowFilters.object_type || undefined,
      page: rowPage.value,
      page_size: rowPageSize.value,
    })
    if (res.success) {
      rowsDetail.value = res.data?.items || []
      rowTotal.value = res.data?.total ?? rowsDetail.value.length
    } else {
      rowError.value = res.message || '加载行失败'
      rowsDetail.value = []
      rowTotal.value = 0
    }
  } finally {
    rowLoading.value = false
  }
}

function onRowSizeChange() {
  rowPage.value = 1
  loadRows()
}

async function downloadReport() {
  downloading.value = true
  try {
    const res = await fetchImportErrorReport(
      currentBatch.value,
      summary.value?.error_report_url,
    )
    if (!res.success) {
      toast.error(res.message || '下载失败')
      return
    }
    const blob = res.data instanceof Blob ? res.data : new Blob([res.data])
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `import-errors-${currentBatch.value}.csv`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
  } finally {
    downloading.value = false
  }
}

async function loadOptions() {
  const res = await fetchIntegrationOptions()
  if (res.success) {
    stagingStatus.value = (res.data || {}).staging_status || []
  }
}

onMounted(loadOptions)
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.spacer { flex: 1; }
.w-140 { width: 140px; }
.w-170 { width: 170px; }
.hint { font-size: 12px; color: var(--text-secondary, #6b7280); }
.alert {
  padding: 10px 12px;
  border-radius: 6px;
  background: #fef2f2;
  color: #b91c1c;
  font-size: 13px;
}
.summary {
  display: flex;
  align-items: center;
  gap: 22px;
  padding: 10px 12px;
  margin-bottom: 12px;
  border-radius: 6px;
  background: var(--bg-subtle, #f9fafb);
  font-size: 13px;
}
.summary-item { display: flex; flex-direction: column; gap: 2px; }
.summary-item span { font-size: 12px; color: var(--text-secondary, #6b7280); }
.summary-item b { font-weight: 600; }
.bad { color: #b91c1c; }
.table-wrap { overflow-x: auto; }
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.data-table th,
.data-table td {
  padding: 9px 10px;
  text-align: left;
  border-bottom: 1px solid var(--border-color, #eef0f3);
  white-space: nowrap;
}
.data-table th {
  font-weight: 600;
  color: var(--text-secondary, #6b7280);
  background: var(--bg-subtle, #f9fafb);
}
.data-table .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.data-table .ellipsis { max-width: 260px; overflow: hidden; text-overflow: ellipsis; }
.tag {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 12px;
}
.tag-on { background: #ecfdf5; color: #047857; }
.tag-warn { background: #fffbeb; color: #b45309; }
.tag-bad { background: #fef2f2; color: #b91c1c; }
.tag-off { background: #f3f4f6; color: #6b7280; }
.pager { margin-top: 14px; }
</style>
