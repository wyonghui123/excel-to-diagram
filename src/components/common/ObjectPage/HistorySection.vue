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

// 判断是否有有效的 objectId：
// 1. 排除 null / 空字符串 / 'new'（新建模式无历史）
// 2. 不再限制必须为数字 — 元数据驱动对象（enum_type / enum_value /
//    business_object / sub_domain / service_module 等）使用字符串主键（如
//    'annotation_category'），后端 auditLogService.getLogsByObject 会校验
//    objectId 是否存在并返回 404，因此前端只需保证非空即可
const hasRealObjectId = computed(() => {
  const id = props.objectId
  if (id == null) return false
  const strId = String(id).trim()
  if (strId === '' || strId === 'new') return false
  return true
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
