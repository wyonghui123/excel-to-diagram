<template>
  <Drawer
    :model-value="modelValue"
    title="打印记录"
    :width="920"
    @update:model-value="handleVisible"
  >
    <div class="print-runs">
      <div class="print-runs__toolbar">
        <span class="print-runs__hint">
          打印次数与最近打印时间派生自打印记录，不写业务表（D-PR-09）。
        </span>
        <AppButton variant="secondary" size="sm" :loading="loading" @click="load">刷新</AppButton>
      </div>

      <el-table
        v-loading="loading"
        :data="runs"
        size="small"
        border
        empty-text="暂无打印记录"
      >
        <el-table-column label="时间" width="148">
          <template #default="{ row }">{{ row.created_at }}</template>
        </el-table-column>
        <el-table-column label="触发" width="84">
          <template #default="{ row }">{{ triggerLabel(row.trigger) }}</template>
        </el-table-column>
        <el-table-column label="模板" min-width="130">
          <template #default="{ row }">
            <span v-if="row.template_id">
              #{{ row.template_id }} / v{{ row.template_version }}
            </span>
            <span v-else class="print-runs__muted">默认版式</span>
          </template>
        </el-table-column>
        <el-table-column label="正式序号" width="88" align="center">
          <template #default="{ row }">{{ row.print_seq || '—' }}</template>
        </el-table-column>
        <el-table-column label="水印" width="82">
          <template #default="{ row }">{{ watermarkLabel(row.watermark) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="88">
          <template #default="{ row }">
            <el-tag :type="row.status === 'succeeded' ? 'success' : (row.status === 'failed' ? 'danger' : 'info')" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作人" width="110">
          <template #default="{ row }">{{ row.operator_name || row.operator_id }}</template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <template v-if="row.status === 'succeeded' && row.attachment_id">
              <el-button link type="primary" size="small" :loading="busyId === row.id" @click="handleReprint(row)">
                重打
              </el-button>
              <el-button link type="primary" size="small" :disabled="busyId === row.id" @click="handleDownload(row)">
                下载
              </el-button>
            </template>
            <el-tooltip v-else-if="row.error_message" :content="row.error_message" placement="top">
              <span class="print-runs__muted">失败</span>
            </el-tooltip>
            <span v-else class="print-runs__muted">—</span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </Drawer>
</template>

<script setup>
import { ref, watch } from 'vue'
import { AppButton, Drawer } from '@/components/common'
import { useMessage } from '@/composables/useMessage'
import {
  fetchArchivedPdf,
  fetchRuns,
  openPdfBlob,
  reprintRun,
  savePdfBlob
} from '@/services/printService'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  boCode: { type: String, required: true },
  docId: { type: String, default: '' }
})
const emit = defineEmits(['update:modelValue'])
const message = useMessage()

const runs = ref([])
const loading = ref(false)
const busyId = ref(null)

const TRIGGER_LABELS = {
  preview: '预览',
  print: '打印',
  download: '下载',
  batch: '批量',
  reprint: '重打'
}
const WATERMARK_LABELS = {
  NONE: '无',
  PREVIEW: '预览',
  DRAFT: '草稿',
  REPRINT: '重打'
}
const STATUS_LABELS = { running: '进行中', succeeded: '成功', failed: '失败' }

function triggerLabel(value) {
  return TRIGGER_LABELS[value] || value || '—'
}
function watermarkLabel(value) {
  return WATERMARK_LABELS[value] || value || '—'
}
function statusLabel(value) {
  return STATUS_LABELS[value] || value || '—'
}

function handleVisible(value) {
  emit('update:modelValue', value)
}

async function load() {
  if (!props.boCode || !props.docId) return
  loading.value = true
  try {
    const response = await fetchRuns({ bo_code: props.boCode, doc_id: props.docId, limit: 100 })
    runs.value = response.success ? (response.data || []) : []
    if (!response.success) message.error(response.message || '打印记录加载失败')
  } catch (error) {
    message.error('打印记录加载失败', error)
  } finally {
    loading.value = false
  }
}

async function handleReprint(row) {
  busyId.value = row.id
  try {
    const response = await reprintRun(row.id)
    if (!response.success) {
      message.error(response.message || '重打失败')
      return
    }
    openPdfBlob(response.data)
    message.success('已重打（复用归档字节，内容零漂移）')
    await load()
  } catch (error) {
    message.error('重打失败', error)
  } finally {
    busyId.value = null
  }
}

async function handleDownload(row) {
  busyId.value = row.id
  try {
    const response = await fetchArchivedPdf(row.attachment_id, row.id, { inline: false })
    if (!response.success) {
      message.error(response.message || '归档文件下载失败')
      return
    }
    const base = row.doc_no || props.docId || 'print'
    savePdfBlob(response.data, `${base}_run${row.id}.pdf`)
  } catch (error) {
    message.error('归档文件下载失败', error)
  } finally {
    busyId.value = null
  }
}

watch(
  () => [props.modelValue, props.boCode, props.docId],
  ([visible]) => {
    if (visible) load()
  }
)
</script>

<style scoped>
.print-runs__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}
.print-runs__hint {
  color: var(--color-text-secondary);
  font-size: 12px;
}
.print-runs__muted {
  color: var(--color-text-secondary);
  font-size: 12px;
}
</style>