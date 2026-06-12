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
import { ref, computed, watch } from 'vue'
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
  },
  // [FIX 2026-06-12] 父对象查询: 当对象本身只有"自身日志" 而"权限配置/关联操作"
  // 等写到了 child object_type (parent_object_type=自身, parent_object_id=自身ID) 时,
  // 必须传 parentObjectType/parentObjectId 一起查 (后端 audit_api 用 OR 联合查询).
  // 典型用法: 角色详情页 (parent=role) / 用户组详情页 (parent=user_group) /
  //           用户详情页 (parent=user).
  parentObjectType: {
    type: String,
    default: null
  },
  parentObjectId: {
    type: [String, Number],
    default: null
  },
  // 是否在挂载时立即拉日志. 默认 true: 详情页打开/操作日志 tab 切换时自动加载,
  // 避免用户看到 "暂无变更记录" 然后再触发加载的闪烁/认知偏差.
  autoLoad: {
    type: Boolean,
    default: true
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
  {
    autoLoad: false, // HistorySection 自己控制首次加载时机 (见下方 watch)
    pageSize: 20,
    parentObjectType: computed(() => props.parentObjectType),
    parentObjectId: computed(() => props.parentObjectId),
  }
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

// [FIX 2026-06-12] 详情页打开或操作日志 tab 切换到该 section 时, 主动触发加载.
// 原因: ObjectPageContent 渲染 HistorySection 时用了 v-show, 默认 tab 在
// "基本信息", 操作日志 section 隐藏但 DOM 存在. v-show 不会触发 onMounted
// (如果切换 tab 不会重新挂载), 所以需要 watch objectId/objectType/parentObjectId
// 变化 + 挂载后主动 loadAuditLogs 一次.
watch(
  () => [props.objectType, props.objectId, props.parentObjectType, props.parentObjectId],
  () => {
    if (props.autoLoad && hasRealObjectId.value && props.objectType) {
      currentPage.value = 1
      loadLogs({ page: 1 })
    }
  },
  { immediate: true }
)
</script>
