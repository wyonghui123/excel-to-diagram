<template>
  <div v-if="visible" class="print-panel">
    <AppButton variant="secondary" size="sm" :loading="busy === 'preview'" @click="handlePreview">
      打印预览
    </AppButton>
    <AppButton variant="secondary" size="sm" :loading="busy === 'print'" @click="handlePrint">
      打印
    </AppButton>
    <AppButton variant="secondary" size="sm" :loading="busy === 'download'" @click="handleDownload">
      下载 PDF
    </AppButton>
    <AppButton variant="text" size="sm" @click="runsVisible = true">打印记录</AppButton>

    <PrintRunsDrawer
      v-model="runsVisible"
      :bo-code="objectType"
      :doc-id="docId"
    />
  </div>
</template>

<script setup>
/**
 * 单据打印动作（spec §11 M6）
 *
 * - 接入点 = (bo_code, header 类型)，从 `/api/print/printable` 派生清单匹配；
 * - 权限随目标 BO：仅当用户具备 `<bo>:read` 时展示（后端仍二次校验）；
 * - 预览走 /render（不归档），打印/下载走 /run 归档后取附件字节，
 *   重打复用归档字节（内容零漂移，D-PR-08）。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { AppButton } from '@/components/common'
import { useMessage } from '@/composables/useMessage'
import { useAuthStore } from '@/stores/authStore'
import {
  fetchArchivedPdf,
  fetchPrintable,
  openPdfBlob,
  renderPreview,
  runPrint,
  savePdfBlob
} from '@/services/printService'
import PrintRunsDrawer from './PrintRunsDrawer.vue'

const props = defineProps({
  objectType: { type: String, required: true },
  docId: { type: [String, Number], default: '' },
  typeId: { type: [String, Number], default: null }
})

const message = useMessage()
const authStore = useAuthStore()

const capabilities = ref([])
const capabilityLoaded = ref(false)
const busy = ref('')
const runsVisible = ref(false)

const docId = computed(() => (props.docId === null || props.docId === undefined ? '' : String(props.docId)))

const matched = computed(() => {
  const entries = capabilities.value.filter((item) => item.bo_code === props.objectType)
  if (!entries.length) return null
  if (props.typeId !== null && props.typeId !== undefined && props.typeId !== '') {
    const exact = entries.find((item) => String(item.type_id) === String(props.typeId))
    if (exact) return exact
  }
  if (entries.length === 1) return entries[0]
  return entries.find((item) => item.is_default_type) || null
})

const typeCode = computed(() => (matched.value ? matched.value.type_code : ''))
const visible = computed(() => (
  capabilityLoaded.value
  && Boolean(matched.value)
  && Boolean(docId.value)
  && docId.value !== 'new'
  && authStore.hasPermission(`${props.objectType}:read`)
))

async function loadCapability() {
  if (!props.objectType) return
  try {
    const response = await fetchPrintable()
    if (response.success) capabilities.value = response.data || []
  } catch {
    // 清单加载失败时静默隐藏入口，打印能力不可用时不影响单据页其他功能
    capabilities.value = []
  } finally {
    capabilityLoaded.value = true
  }
}

async function withBusy(action, runner) {
  if (busy.value) return
  busy.value = action
  try {
    await runner()
  } catch (error) {
    message.error('打印请求失败', error)
  } finally {
    busy.value = ''
  }
}

function payload() {
  return { bo_code: props.objectType, type_code: typeCode.value, doc_id: docId.value }
}

function handlePreview() {
  withBusy('preview', async () => {
    const response = await renderPreview({ ...payload(), mode: 'preview' })
    if (!response.success) {
      message.error(response.message || '预览渲染失败')
      return
    }
    openPdfBlob(response.data)
  })
}

function handlePrint() {
  withBusy('print', async () => {
    const response = await runPrint({ ...payload(), trigger: 'print' })
    if (!response.success) {
      message.error(response.message || '打印失败')
      return
    }
    const { run, attachment_id: attachmentId } = response.data || {}
    if (!run || !attachmentId) {
      message.warning('已归档，但未返回附件')
      return
    }
    const pdf = await fetchArchivedPdf(attachmentId, run.id, { inline: true })
    if (!pdf.success) {
      message.error(pdf.message || '读取归档打印件失败')
      return
    }
    openPdfBlob(pdf.data)
    message.success(`已归档第 ${run.print_seq || 1} 份并打开打印件`)
  })
}

function handleDownload() {
  withBusy('download', async () => {
    const response = await runPrint({ ...payload(), trigger: 'download' })
    if (!response.success) {
      message.error(response.message || '下载失败')
      return
    }
    const { run, attachment_id: attachmentId } = response.data || {}
    if (!run || !attachmentId) {
      message.warning('已归档，但未返回附件')
      return
    }
    const pdf = await fetchArchivedPdf(attachmentId, run.id, { inline: false })
    if (!pdf.success) {
      message.error(pdf.message || '读取归档打印件失败')
      return
    }
    const base = (run.doc_no || props.docId || 'print').replace(/\//g, '_')
    savePdfBlob(pdf.data, `${base}_print${run.print_seq || 1}.pdf`)
  })
}

onMounted(loadCapability)
watch(() => props.objectType, () => {
  capabilityLoaded.value = false
  capabilities.value = []
  loadCapability()
})
</script>

<style scoped>
.print-panel {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
</style>