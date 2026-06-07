<template>
  <div class="change-history">
    <AuditLog
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
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useAuditLogs } from '@/composables/useAuditLogs'
import AuditLog from '@/components/common/AuditLog/AuditLog.vue'

const props = defineProps({
  objectType: {
    type: String,
    required: true
  },
  objectId: {
    type: [String, Number],
    required: true
  }
})

const currentPage = ref(1)
const currentFilters = ref({})

const {
  logs: auditLogs,
  total: auditLogsTotal,
  loading: auditLogsLoading,
  loadLogs,
  setFilters,
  setPage
} = useAuditLogs(props.objectType, props.objectId, {
  autoLoad: false
})

function handlePageChange(page) {
  currentPage.value = page
  setPage(page)
}

function handleFilterChange(filters) {
  currentFilters.value = filters
  currentPage.value = 1
  setFilters(filters)
}

function handleLogClick(log) {
}

onMounted(() => {
  if (props.objectType && props.objectId) {
    loadLogs()
  }
})

watch(() => [props.objectType, props.objectId], () => {
  if (props.objectType && props.objectId) {
    currentPage.value = 1
    currentFilters.value = {}
    loadLogs()
  }
})
</script>

<style scoped>
.change-history {
  padding: var(--spacing-md);
  min-height: 200px;
}
</style>
