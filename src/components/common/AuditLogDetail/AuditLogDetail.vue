<template>
  <el-drawer
    :model-value="visible"
    title="变更详情"
    size="480px"
    :destroy-on-close="true"
    @close="handleClose"
  >
    <div v-if="!log" class="ald-empty">无日志数据</div>
    <div v-else class="ald-content">
      <div class="ald-header">
        <span class="ald-action-badge" :class="'ald-action--' + actionClass">
          {{ actionLabel }}
        </span>
        <span class="ald-time">{{ formattedTime }}</span>
      </div>

      <div class="ald-info">
        <div class="ald-info-row" v-if="log.user_name">
          <span class="ald-label">操作人</span>
          <span class="ald-value">{{ userNameDisplay }}</span>
        </div>
        <!-- [FIX 2026-06-15 业务化审查] 删除/翻译以下技术性字段:
             - 对象类型: 翻译为业务术语 (如 annotation -> 备注)
             - 对象ID:   删除 (业务人员已经在详情页, 信息冗余)
             - IP:       删除 (业务人员无需关心)
             - Trace:    删除 (UUID 是技术可观测性概念, 业务价值为 0)
        -->
        <div class="ald-info-row" v-if="objectTypeLabel">
          <span class="ald-label">对象类型</span>
          <span class="ald-value">{{ objectTypeLabel }}</span>
        </div>
        <div class="ald-info-row" v-if="log._cascade_from">
          <span class="ald-label">级联来源</span>
          <span class="ald-value ald-cascade-source">{{ log._cascade_from.type }} #{{ log._cascade_from.id }}</span>
        </div>
      </div>

      <!-- [DECORATIVE] FR-LOG-009: Action Kind Panel -->
      <div v-if="log.action_kind" class="ald-action-kind-panel">
        <h4 class="ald-section-title">Action 类型</h4>
        <el-tag :type="log.action_kind === 'instance' ? 'primary' : 'info'" size="default">
          {{ log.action_kind === 'instance' ? '[DECORATIVE] InstanceAction' : '[SYMBOL] StaticAction' }}
        </el-tag>
        <span class="ald-action-kind-hint">
          {{ log.action_kind === 'instance' ? '此 action 绑定到具体对象实例' : '此 action 不绑定实例' }}
        </span>
      </div>

      <!-- [DECORATIVE] FR-LOG-010: Outcome Panel -->
      <div v-if="log.outcome" class="ald-outcome-panel">
        <h4 class="ald-section-title">执行结果</h4>
        <el-tag :type="outcomeTagType" size="default">
          {{ outcomeIcon }} {{ outcomeLabel }}
        </el-tag>
        <div v-if="log.error_message" class="ald-error-row">
          <span class="ald-label">错误</span>
          <span class="ald-value ald-error-message">{{ log.error_message }}</span>
        </div>
      </div>

      <!-- [DECORATIVE] FR-LOG-011: RelatedEvents Panel AppCollapse 折叠 -->
      <div v-if="hasRelatedEvents" class="ald-related-panel">
        <AppCollapse title="相关操作" :default-expanded="false">
          <div v-if="log.parent_action_id" class="ald-related-section">
            <strong>父操作</strong> (id={{ log.parent_action_id }})
          </div>
          <div v-if="relatedHeader" class="ald-related-header">
            <span class="ald-related-action">{{ relatedHeader.action }}</span>
            <span class="ald-related-object">{{ relatedHeader.object_type }}#{{ relatedHeader.object_id }}</span>
          </div>
          <div v-if="relatedChildren.length > 0" class="ald-related-children">
            <strong>子操作</strong> ({{ relatedChildren.length }}):
            <ul class="ald-related-list">
              <li v-for="child in relatedChildren" :key="child.id"
                  @click="emit('update:visible', false); emit('selectLog', child)"
                  class="ald-related-item">
                <span class="ald-related-action">{{ child.action }}</span>
                <span class="ald-related-object">{{ child.object_type }}#{{ child.object_id }}</span>
                <el-tag size="small" :type="getChildOutcomeType(child.outcome)">{{ child.outcome }}</el-tag>
              </li>
            </ul>
          </div>
        </AppCollapse>
      </div>

      <div v-if="isCreateAction" class="ald-summary">
        <svg class="ald-summary-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M12 9v6m3-3H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z"/>
        </svg>
        <span>创建记录</span>
      </div>
      <div v-else-if="isDeleteAction" class="ald-summary ald-summary--delete">
        <svg class="ald-summary-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M15 12H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z"/>
        </svg>
        <span>删除记录</span>
      </div>
      <div v-else-if="isAssociateAction || isDissociateAction" class="ald-association">
        <h4 class="ald-section-title">{{ isAssociateAction ? '添加关联' : '移除关联' }}</h4>
        <div class="ald-single-change">
          <div class="ald-single-row">
            <span class="ald-label">关系</span>
            <span class="ald-value">{{ log.field_name || '-' }}</span>
          </div>
          <div class="ald-single-row">
            <span class="ald-label">目标对象</span>
            <span class="ald-value" :class="isAssociateAction ? 'ald-associate-add' : 'ald-associate-remove'">
              {{ parseTargetDisplay(isAssociateAction ? log.new_value : log.old_value) }}
            </span>
          </div>
        </div>
      </div>
      <div v-else class="ald-changes">
        <h4 class="ald-section-title">变更字段</h4>
        <table v-if="changes.length > 0" class="ald-change-table">
          <thead>
            <tr>
              <th>字段</th>
              <th>变更前</th>
              <th>变更后</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="change in changes" :key="change.field">
              <td class="ald-field-name">{{ change.field_label || change.field }}</td>
              <td class="ald-old-value">{{ change.old_value ?? '(空)' }}</td>
              <td class="ald-new-value">{{ change.new_value ?? '(空)' }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else-if="log.field_name" class="ald-single-change">
          <div class="ald-single-row">
            <span class="ald-label">变更字段</span>
            <span class="ald-value">{{ log.field_name }}</span>
          </div>
          <div class="ald-single-row">
            <span class="ald-label">变更前</span>
            <span class="ald-old-value">{{ log.old_value ?? '(空)' }}</span>
          </div>
          <div class="ald-single-row">
            <span class="ald-label">变更后</span>
            <span class="ald-new-value">{{ log.new_value ?? '(空)' }}</span>
          </div>
        </div>
      </div>
    </div>
  </el-drawer>
</template>

<script setup>
import { computed } from 'vue'
import { dateFormatService } from '@/services/DateFormatService'
import { getObjectTypeLabel, getUserNameDisplay, isInternalField, isInternalAction } from '@/utils/auditLogFormat'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  log: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['update:visible', 'selectLog'])

// [FIX 2026-06-15 业务化审查] 业务名翻译
const objectTypeLabel = computed(() => getObjectTypeLabel(props.log?.object_type))
const userNameDisplay = computed(() => getUserNameDisplay(props.log?.user_name))

// [DECORATIVE] FR-LOG-011: RelatedEvents 状态
const hasRelatedEvents = computed(() => {
  return Boolean(props.log?.parent_action_id) || Boolean(props.log?._related_children?.length)
})

// 当前条是子操作 → 父操作 header 通过 parent_action_id 查
// 当前条是父操作 → related_children 数组携带子操作
const relatedHeader = computed(() => props.log?._related_header || null)
const relatedChildren = computed(() => props.log?._related_children || [])

function getChildOutcomeType(outcome) {
  if (outcome === 'success') return 'success'
  if (outcome === 'failure') return 'danger'
  if (outcome === 'denied') return 'warning'
  return 'info'
}

const actionClass = computed(() => {
  const action = (props.log?.action || 'unknown').toLowerCase()
  return action
})

const actionLabel = computed(() => {
  const actionMap = {
    'CREATE': '创建',
    'UPDATE': '更新',
    'DELETE': '删除',
    'ASSOCIATE': '添加关联',
    'DISSOCIATE': '移除关联',
    'ASSIGN': '分配',
    'REVOKE': '撤销'
  }
  return actionMap[props.log?.action] || props.log?.action || '未知'
})

const isCreateAction = computed(() => props.log?.action === 'CREATE')
const isDeleteAction = computed(() => props.log?.action === 'DELETE')
const isAssociateAction = computed(() => props.log?.action === 'ASSOCIATE' || props.log?.action === 'ASSIGN')
const isDissociateAction = computed(() => props.log?.action === 'DISSOCIATE' || props.log?.action === 'REVOKE')

// [DECORATIVE] FR-LOG-010: Outcome 状态计算
const outcomeTagType = computed(() => {
  const o = props.log?.outcome
  if (o === 'success') return 'success'
  if (o === 'failure') return 'danger'
  if (o === 'denied') return 'warning'
  if (o === 'retry') return 'info'
  return 'default'
})

const outcomeIcon = computed(() => {
  const o = props.log?.outcome
  if (o === 'success') return '[OK]'
  if (o === 'failure') return '[X]'
  if (o === 'denied') return '[SYMBOL]'
  if (o === 'retry') return '[REFRESH]'
  return '[SYMBOL]'
})

const outcomeLabel = computed(() => {
  const o = props.log?.outcome
  const map = {
    'success': 'SUCCESS',
    'failure': 'FAILURE',
    'denied': 'DENIED',
    'retry': 'RETRY',
  }
  return map[o] || o?.toUpperCase() || 'UNKNOWN'
})

const formattedTime = computed(() => {
  if (!props.log?.created_at) return '-'
  const date = new Date(props.log.created_at)
  if (isNaN(date.getTime())) return '-'
  return dateFormatService.format(date, { dateStyle: 'medium', timeStyle: 'short' })
})

const changes = computed(() => {
  if (!props.log?.changes && !props.log?.field_changes) return []
  return props.log.changes || props.log.field_changes || []
})

function handleClose() {
  emit('update:visible', false)
}

function parseTargetDisplay(raw) {
  if (!raw) return '-'
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (parsed && parsed.target_display && parsed.target_type) {
      return `${parsed.target_display}（${parsed.target_type}）`
    }
    return raw
  } catch {
    return raw
  }
}
</script>

<style scoped>
.ald-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-2xl);
  color: var(--color-text-tertiary);
}

.ald-content {
  padding: var(--spacing-md);
}

.ald-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-lg);
}

.ald-action-badge {
  padding: 4px 12px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
}

.ald-action--create {
  background: var(--color-success-bg, #dcfce7);
  color: var(--color-success, #16a34a);
}

.ald-action--update {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.ald-action--delete {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.ald-action--assign {
  background: var(--color-warning-bg, #fef3c7);
  color: var(--color-warning, #d97706);
}

.ald-action--revoke {
  background: var(--color-bg-spotlight);
  color: var(--color-text-secondary);
}

.ald-action--unknown {
  background: var(--color-bg-spotlight);
  color: var(--color-text-secondary);
}

.ald-time {
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  font-family: monospace;
}

.ald-info {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  padding: var(--spacing-md);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-lg);
}

.ald-info-row {
  display: flex;
  align-items: baseline;
  gap: var(--spacing-md);
  font-size: var(--font-size-sm);
}

.ald-label {
  color: var(--color-text-tertiary);
  min-width: 60px;
  flex-shrink: 0;
}

.ald-value {
  color: var(--color-text-primary);
  word-break: break-all;
}

.ald-summary {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-md);
  background: var(--color-success-bg, #dcfce7);
  border-radius: var(--radius-md);
  color: var(--color-success, #16a34a);
  font-size: var(--font-size-sm);
}

.ald-summary--delete {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.ald-summary-icon {
  width: 20px;
  height: 20px;
}

.ald-section-title {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  margin: 0 0 var(--spacing-sm) 0;
}

.ald-change-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}

.ald-change-table th {
  padding: var(--spacing-sm) var(--spacing-md);
  text-align: left;
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  background: var(--color-bg-secondary);
  border-bottom: 1px solid var(--color-border);
}

.ald-change-table td {
  padding: var(--spacing-sm) var(--spacing-md);
  color: var(--color-text-primary);
  border-bottom: 1px solid var(--color-border-light, var(--color-border));
}

.ald-field-name {
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

.ald-old-value {
  color: var(--color-error);
  text-decoration: line-through;
}

.ald-new-value {
  color: var(--color-success, #16a34a);
  font-weight: var(--font-weight-medium);
}

.ald-associate-add {
  color: var(--color-success, #16a34a);
  font-weight: var(--font-weight-medium);
}

.ald-associate-remove {
  color: var(--color-error);
  font-weight: var(--font-weight-medium);
}

.ald-cascade-source {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
}

.ald-single-change {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  padding: var(--spacing-md);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
}

.ald-single-row {
  display: flex;
  align-items: baseline;
  gap: var(--spacing-md);
  font-size: var(--font-size-sm);
}

/* [DECORATIVE] FR-LOG-009/010/011: v2 增强样式 */
.ald-action-kind-panel,
.ald-outcome-panel,
.ald-related-panel {
  margin-bottom: var(--spacing-lg);
  padding: var(--spacing-md);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
}

.ald-action-kind-hint {
  display: inline-block;
  margin-left: var(--spacing-sm);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
}

.ald-error-row {
  margin-top: var(--spacing-sm);
  padding: var(--spacing-sm);
  background: var(--color-error-bg, #fee2e2);
  border-radius: var(--radius-sm);
  display: flex;
  gap: var(--spacing-md);
  font-size: var(--font-size-sm);
}

.ald-error-message {
  color: var(--color-error, #dc2626);
  word-break: break-all;
}

.ald-related-section {
  font-size: var(--font-size-sm);
  margin-bottom: var(--spacing-sm);
}

.ald-related-header {
  padding: var(--spacing-sm);
  background: var(--color-primary-bg, #dbeafe);
  border-radius: var(--radius-sm);
  margin-bottom: var(--spacing-sm);
  font-size: var(--font-size-sm);
  display: flex;
  gap: var(--spacing-sm);
  align-items: center;
}

.ald-related-children {
  margin-top: var(--spacing-sm);
  font-size: var(--font-size-sm);
}

.ald-related-list {
  list-style: none;
  padding: 0;
  margin: var(--spacing-sm) 0 0 0;
}

.ald-related-item {
  padding: var(--spacing-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  margin-bottom: var(--spacing-xs);
  cursor: pointer;
  display: flex;
  gap: var(--spacing-sm);
  align-items: center;
  transition: background 0.15s;
}

.ald-related-item:hover {
  background: var(--color-bg-spotlight);
}

.ald-related-action {
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

.ald-related-object {
  color: var(--color-text-tertiary);
  font-family: monospace;
  font-size: var(--font-size-xs);
}
</style>
