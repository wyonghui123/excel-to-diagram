<template>
  <div class="op-audit-log-section">
    <AuditLog
      v-if="objectType && hasRealObjectId"
      :logs="auditLogs"
      :loading="auditLogsLoading"
      :total="auditLogsTotal"
      :show-pagination="true"
      :current-page="currentPage"
      :page-size="20"
      :show-filter="true"
      :click-mode="'expand'"
      :object-type="objectType"
      :object-id="objectId"
      @page-change="handlePageChange"
      @filter-change="handleFilterChange"
      @log-click="handleLogClick"
    />
    <div v-else class="op-empty-state">
      <AppIcon name="warning" size="lg" />
      <p>缺少 objectType 或 objectId 属性，无法加载变更历史。</p>
    </div>
    <AuditLogDetail
      v-model:visible="detailVisible"
      :log="selectedLog"
    />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import AuditLog from '../AuditLog/AuditLog.vue'
import { AuditLogDetail } from '../AuditLogDetail'
import AppIcon from '../AppIcon/AppIcon.vue'
import { useAuditLogs } from '@/composables/useAuditLogs'

const props = defineProps({
  objectType: {
    type: String,
    default: null
  },
  objectId: {
    type: [String, Number],
    default: null
  }
})

const hasRealObjectId = computed(() => {
  const id = props.objectId
  if (id == null || id === '' || id === 'new') return false
  const numId = Number(id)
  return !isNaN(numId) && numId > 0
})

const {
  logs: auditLogs,
  total: auditLogsTotal,
  loading: auditLogsLoading,
  loadLogs,
  setPage,
  setFilters
} = useAuditLogs(
  computed(() => props.objectType),
  computed(() => props.objectId),
  { autoLoad: false, pageSize: 20 }
)

const detailVisible = ref(false)
const selectedLog = ref(null)
const currentPage = ref(1)

function handleLogClick(log) {
  selectedLog.value = log
  detailVisible.value = true
}

function handlePageChange(page) {
  currentPage.value = page
  setPage(page)
}

function handleFilterChange(filters) {
  currentPage.value = 1
  setFilters(filters)
}

function loadAuditLogs() {
  return loadLogs({ page: currentPage.value })
}

defineExpose({ loadAuditLogs })
</script>
