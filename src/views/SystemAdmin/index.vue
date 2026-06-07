<template>
  <div class="system-admin">
    <div class="page-content">
      <GenericObjectList
        object-type="audit_log"
        :page-size="50"
        :enable-auto-crud="false"
        @detail="handleViewDetail"
      >
        <template #cell-field_name="{ row }">
          <span v-if="row.field_name && row.field_name !== '_record'" class="field-name-badge">
            {{ getFieldName(row.field_name) }}
          </span>
          <span v-else class="no-field">-</span>
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
              {{ getActionLabel(selectedLog.action) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="对象类型">
            {{ getObjectTypeLabel(selectedLog.object_type) }}
          </el-descriptions-item>
          <el-descriptions-item label="对象ID">
            {{ selectedLog.object_id }}
          </el-descriptions-item>
          <el-descriptions-item label="业务标识">
            {{ selectedLog.formatted_identity || selectedLog.business_key || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="操作人">
            {{ selectedLog.user_name || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="IP地址">
            {{ selectedLog.ip_address || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="字段名">
            {{ getFieldName(selectedLog.field_name) }}
          </el-descriptions-item>
          <el-descriptions-item label="旧值">
            <div class="value-text">{{ selectedLog.old_value || '-' }}</div>
          </el-descriptions-item>
          <el-descriptions-item label="新值">
            <div class="value-text">{{ selectedLog.new_value || '-' }}</div>
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

const showDetail = ref(false)
const selectedLog = ref(null)

function handleViewDetail(payload) {
  selectedLog.value = payload.row
  showDetail.value = true
}

const OBJECT_TYPE_MAP = {
  'user': '用户',
  'role': '角色',
  'user_group': '用户组',
  'product': '产品',
  'version': '版本',
  'domain': '领域',
  'sub_domain': '子域',
  'service_module': '服务模块',
  'business_object': '业务对象',
  'relationship': '关系',
  'annotation': '标注',
  'enum_type': '枚举类型',
  'enum_value': '枚举值',
  '__audit_failure__': '审计失败'
}

const COMMON_FIELD_NAMES = {
  'id': 'ID',
  'name': '名称',
  'code': '编码',
  'description': '描述',
  'created_at': '创建时间',
  'updated_at': '更新时间',
  'created_by': '创建人',
  'updated_by': '更新人',
  'status': '状态',
  'is_active': '是否激活',
  'username': '用户名',
  'display_name': '显示名称',
  'email': '邮箱'
}

function getObjectTypeLabel(type) {
  return OBJECT_TYPE_MAP[type] || type
}

function getFieldName(fieldKey) {
  if (!fieldKey || fieldKey === '_record') return '-'
  return COMMON_FIELD_NAMES[fieldKey] || fieldKey
}

function getCategoryTagType(category) {
  const map = { business: 'primary', security: 'danger', operation: 'info', performance: 'warning', system: '' }
  return map[category] || ''
}

function getCategoryLabel(category) {
  const map = { business: '业务审计', security: '安全日志', operation: '运营日志', performance: '性能日志', system: '系统日志' }
  return map[category] || category
}

function getLevelTagType(level) {
  const map = { DEBUG: 'info', INFO: 'primary', WARNING: 'warning', ERROR: 'danger', CRITICAL: 'danger' }
  return map[level] || 'info'
}

function getLevelLabel(level) {
  const map = { DEBUG: '调试', INFO: '信息', WARNING: '警告', ERROR: '错误', CRITICAL: '严重' }
  return map[level] || level
}

function getActionTagType(action) {
  const map = { CREATE: 'success', UPDATE: 'warning', DELETE: 'danger', ASSOCIATE: 'primary', DISSOCIATE: 'info' }
  return map[action] || 'info'
}

function getActionLabel(action) {
  const map = { CREATE: '创建', UPDATE: '更新', DELETE: '删除', ASSOCIATE: '关联', DISSOCIATE: '取消关联' }
  return map[action] || action
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
