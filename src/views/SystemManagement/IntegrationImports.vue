<template>
  <PageShell
    title="导入交付面"
    subtitle="staging 三段式：落库 → 校验 → 提交；批次保留期后可下载错误报告"
  >
    <AppCard title="导入批次">
      <div class="toolbar">
        <AppInput
          v-model="filters.object_type"
          size="sm"
          placeholder="对象类型（如 item）"
          clearable
          class="w-170"
          @keyup.enter="reload"
        />
        <AppButton variant="secondary" size="sm" :loading="loading" @click="reload">刷新</AppButton>
        <span class="spacer" />
        <span class="hint">共 {{ total }} 个批次</span>
      </div>

      <div v-if="error" class="alert">{{ error }}</div>
      <EmptyState
        v-else-if="!loading && !rows.length"
        type="empty"
        title="暂无导入批次"
        description="导入文件落 staging 后，批次会出现在这里"
      />
      <div v-else class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>批次号</th>
              <th>总行数</th>
              <th>待提交</th>
              <th>已导入</th>
              <th>失败行</th>
              <th>创建时间</th>
              <th>过期时间</th>
              <th>状态</th>
              <th class="col-action">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.batch_no">
              <td class="mono">{{ row.batch_no }}</td>
              <td class="mono">{{ row.total }}</td>
              <td class="mono">{{ row.pending }}</td>
              <td class="mono">{{ row.imported }}</td>
              <td class="mono">
                <span v-if="row.invalid" class="bad">{{ row.invalid }}</span>
                <span v-else>0</span>
              </td>
              <td class="mono">{{ row.created_at }}</td>
              <td class="mono">{{ row.expires_at }}</td>
              <td>
                <span :class="['tag', row.expired ? 'tag-off' : 'tag-on']">
                  {{ row.expired ? '已过期' : '有效' }}
                </span>
              </td>
              <td class="col-action">
                <AppButton variant="ghost" size="sm" @click="openBatch(row)">明细</AppButton>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <Pagination
        v-if="total > 0"
        v-model:current="page"
        v-model:page-size="pageSize"
        :total="total"
        class="pager"
        @change="load"
        @pageSizeChange="onSizeChange"
      />
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
        type="empty"
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
                <span :class="['tag', rowStatusClass(row.status)]">{{ row.status }}</span>
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
import { ref, reactive, onMounted } from 'vue'
import {
  PageShell, AppCard, AppButton, AppInput, AppSelect, Drawer, EmptyState, Pagination,
} from '@/components/common'
import { useMessage } from '@/composables/useMessage'
import {
  fetchImportBatches, fetchImportBatch, fetchImportRows, fetchImportErrorReport,
} from '@/services/integrationService'

defineOptions({ name: 'IntegrationImports' })

const toast = useMessage()

const STAGING_STATUSES = ['pending', 'valid', 'invalid', 'imported', 'skipped']

const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const error = ref('')
const filters = reactive({ object_type: '' })

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
const rowStatusOptions = STAGING_STATUSES.map((v) => ({ value: v, label: v }))

function rowStatusClass(status) {
  if (status === 'imported') return 'tag-on'
  if (status === 'invalid') return 'tag-bad'
  if (status === 'valid') return 'tag-warn'
  return 'tag-off'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchImportBatches({
      object_type: filters.object_type || undefined,
      page: page.value,
      page_size: pageSize.value,
    })
    if (res.success) {
      rows.value = res.data?.items || []
      total.value = res.data?.total ?? rows.value.length
    } else {
      error.value = res.message || '加载批次失败'
      rows.value = []
      total.value = 0
    }
  } finally {
    loading.value = false
  }
}

function reload() {
  page.value = 1
  load()
}

function onSizeChange() {
  page.value = 1
  load()
}

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

onMounted(load)
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
.col-action { text-align: right; }
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