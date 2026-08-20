<template>
  <div class="system-admin">
    <div class="page-content">
      <GenericObjectList
        object-type="audit_log"
        :page-size="50"
        :enable-auto-crud="false"
        @detail="handleViewDetail"
      >
        <template #cell-object_type="{ row }">
          {{ formatObjectTypeLabel(row.object_type, row) }}
        </template>
        <template #cell-field_name="{ row }">
          <span v-if="row.field_name && row.field_name !== '_record'" class="field-name-badge">
            {{ getFieldLabel(row.field_name, row) }}
          </span>
          <span v-else class="no-field">-</span>
        </template>
        <template #cell-old_value="{ row }">
          {{ getFieldValueDisplay(row.old_value, row.field_name, row) }}
        </template>
        <template #cell-new_value="{ row }">
          {{ getFieldValueDisplay(row.new_value, row.field_name, row) }}
        </template>
        <template #cell-user_name="{ row }">
          {{ getUserNameDisplay(row.user_name) }}
        </template>
        <template #cell-log_category="{ row }">
          <el-tag :type="getCategoryTagType(row.log_category)" size="small">
            {{ getCategoryLabel(row.log_category) }}
          </el-tag>
        </template>
        <template #cell-log_level="{ row }">
          <el-tag :type="getLevelTagType(row.log_level)" size="small">
            {{ getLevelLabel(row.log_level) }}
          </el-tag>
        </template>
        <template #cell-action="{ row }">
          <el-tag :type="getActionTagType(row.action)" size="small">
            {{ getActionLabel(row.action, row) }}
          </el-tag>
        </template>
      </GenericObjectList>
    </div>

    <el-drawer
      v-model="showDetail"
      title="审计日志详情"
      size="640px"
      direction="rtl"
    >
      <div v-if="selectedLog" class="detail-content">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="操作时间">
            {{ formatDateTime(selectedLog.created_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="日志类型">
            <el-tag :type="getCategoryTagType(selectedLog.log_category)" size="small">
              {{ getCategoryLabel(selectedLog.log_category) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="日志级别">
            <el-tag :type="getLevelTagType(selectedLog.log_level)" size="small">
              {{ getLevelLabel(selectedLog.log_level) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="操作类型">
            <el-tag :type="getActionTagType(selectedLog.action)" size="small">
              {{ getActionLabel(selectedLog.action, selectedLog) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="对象类型">
            {{ formatObjectTypeLabel(selectedLog.object_type, selectedLog) }}
          </el-descriptions-item>
          <el-descriptions-item label="对象ID">
            {{ selectedLog.object_id }}
          </el-descriptions-item>
          <el-descriptions-item label="业务标识">
            {{ selectedLog.formatted_identity || selectedLog.business_key || selectedLog.object_display || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="操作人">
            {{ getUserNameDisplay(selectedLog.user_name) }}
          </el-descriptions-item>
          <el-descriptions-item label="IP地址">
            {{ selectedLog.ip_address || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="字段名">
            {{ getFieldLabel(selectedLog.field_name, selectedLog) }}
          </el-descriptions-item>
          <el-descriptions-item label="旧值">
            <div class="value-text">{{ getFieldValueDisplay(selectedLog.old_value, selectedLog.field_name, selectedLog) }}</div>
          </el-descriptions-item>
          <el-descriptions-item label="新值">
            <div class="value-text">{{ getFieldValueDisplay(selectedLog.new_value, selectedLog.field_name, selectedLog) }}</div>
          </el-descriptions-item>
          <el-descriptions-item label="链路追踪ID">
            {{ selectedLog.trace_id || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="事务ID">
            {{ selectedLog.transaction_id || '-' }}
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import GenericObjectList from '@/views/GenericObjectList.vue'
import { formatDate } from '@/composables/useMetaList'
import {
  getObjectTypeLabel as formatObjectTypeLabel,
  getActionLabel,
  getFieldLabel,
  getFieldValueDisplay,
  getUserNameDisplay,
  getCategoryLabel,
  getCategoryTagType,
  getLevelLabel,
  getLevelTagType,
  getActionTagType,
} from '@/utils/auditLogFormat'

const showDetail = ref(false)
const selectedLog = ref(null)

function handleViewDetail(payload) {
  selectedLog.value = payload.row
  showDetail.value = true
}

function formatDateTime(datetime) {
  return formatDate(datetime, 'YYYY-MM-DD HH:mm:ss')
}
</script>

<style scoped>
.system-admin {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--color-bg-layout);
}

.page-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.field-name-badge {
  font-family: 'Consolas', 'Monaco', monospace;
  color: var(--color-text-secondary, #666);
  background: #f5f5f5;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 12px;
  border: 1px solid #e8e8e8;
}

.no-field {
  color: var(--color-text-tertiary, #999);
  font-style: italic;
}

.detail-content {
  padding: var(--spacing-md);
}

.value-text {
  max-height: 200px;
  overflow-y: auto;
  word-break: break-all;
  white-space: pre-wrap;
}
</style>