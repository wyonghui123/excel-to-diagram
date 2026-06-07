<template>
  <AppModal :model-value="visible" :title="title" width="560px" @update:model-value="$emit('update:visible', $event)">
    <div class="change-history" v-if="!loading">
      <div class="history-header">
        <span class="history-target">{{ targetName }}</span>
        <span class="history-count" v-if="history.length">共 {{ history.length }} 条变更记录</span>
        <span class="history-count history-empty" v-else>暂无变更记录</span>
      </div>
      <div class="history-list" v-if="history.length">
        <div class="history-item" v-for="item in displayedHistory" :key="item.id">
          <div class="history-main">
            <span class="history-time">{{ formatTime(item.created_at) }}</span>
            <span class="history-user">{{ item.user_name || 'system' }}</span>
            <span class="history-action" :class="'action-' + (item.action || '').toLowerCase()">
              {{ actionLabel(item.action) }}
            </span>
          </div>
          <div class="history-detail" v-if="item.field_name">
            <span class="history-field">{{ fieldLabel(item.field_name) }}:</span>
            <span class="history-old">{{ item.old_value || '(空)' }}</span>
            <span class="history-arrow">→</span>
            <span class="history-new">{{ item.new_value || '(空)' }}</span>
          </div>
          <div class="history-detail history-create" v-else-if="item.action === 'CREATE'">
            <span>创建了{{ objectTypeName }}记录</span>
          </div>
          <div class="history-detail history-delete" v-else-if="item.action === 'DELETE'">
            <span>删除了{{ objectTypeName }}记录</span>
          </div>
        </div>
      </div>
      <div class="history-list history-empty-state" v-else-if="!loading">
        <p>暂无变更记录</p>
        <p class="history-hint">对该{{ objectTypeName }}的增删改操作将在此处显示</p>
      </div>
      <button
        class="history-more-btn"
        v-if="history.length > displayLimit && !showAll"
        @click="showAll = true"
      >展开全部 {{ history.length }} 条记录</button>
      <button
        class="history-more-btn"
        v-else-if="showAll"
        @click="showAll = false"
      >收起</button>
      <div class="history-loading" v-if="loading">
        <span>加载中...</span>
      </div>
    </div>
  </AppModal>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { AppModal } from '../../../components/common'
import { boService } from '@/services/boService'
import { dateFormatService } from '@/services/DateFormatService'

const props = defineProps({
  visible: { type: Boolean, default: false },
  objectType: { type: String, default: '' },
  objectId: { type: [Number, String], default: null },
  targetName: { type: String, default: '' },
  title: { type: String, default: '变更日志' }
})

const emit = defineEmits(['update:visible'])

const history = ref([])
const loading = ref(false)
const showAll = ref(false)
const displayLimit = 15

const FALLBACK_TYPE_MAP = { product: '产品', version: '版本', domain: '领域', business_object: '业务对象' }

const objectTypeName = computed(() => {
  return FALLBACK_TYPE_MAP[props.objectType] || props.objectType
})

const displayedHistory = computed(() => {
  if (showAll.value || history.value.length <= displayLimit) return history.value
  return history.value.slice(0, displayLimit)
})

const FIELD_LABELS = {
  name: '名称',
  code: '编码/版本号',
  description: '描述',
  status: '状态',
  is_current: '当前版本',
  is_active: '是否活跃',
  product_id: '所属产品',
  product_name: '所属产品'
}

function fieldLabel(field) {
  return FIELD_LABELS[field] || field
}

function actionLabel(action) {
  const map = { CREATE: '创建', UPDATE: '更新', DELETE: '删除' }
  return map[action] || action || '未知'
}

function formatTime(timeStr) {
  if (!timeStr) return '-'
  try {
    const d = new Date(timeStr)
    if (isNaN(d.getTime())) return timeStr
    return dateFormatService.format(d, { dateStyle: 'medium', timeStyle: 'short' })
  } catch {
    return timeStr
  }
}

async function loadHistory() {
  if (!props.objectType || !props.objectId) {
    history.value = []
    return
  }
  loading.value = true
  try {
    const result = await boService.read(props.objectType, props.objectId)
    if (result.success) {
      history.value = result.data?.change_history || []
    } else {
      history.value = []
    }
  } catch (e) {
    console.error('Failed to load change history:', e)
    history.value = []
  } finally {
    loading.value = false
  }
}

watch(() => props.visible, (val) => {
  if (val) {
    showAll.value = false
    loadHistory()
  }
})
</script>

<style scoped>
.change-history {
  padding: 4px 0;
}
.history-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid #f0f0f0;
}
.history-target {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.history-count {
  font-size: 12px;
  color: var(--el-color-primary, #ea580c);
  background: #e6f4ff;
  padding: 2px 8px;
  border-radius: 10px;
}
.history-count.history-empty {
  color: var(--color-text-tertiary);
  background: #f5f5f5;
}
.history-list {
  display: flex;
  flex-direction: column;
  gap: 0;
  max-height: 420px;
  overflow-y: auto;
}
.history-empty-state {
  text-align: center;
  padding: 32px 16px;
  color: var(--color-text-tertiary);
  font-size: 13px;
}
.history-empty-state .history-hint {
  font-size: 12px;
  color: var(--color-text-disabled);
  margin-top: 4px;
}
.history-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  font-size: 13px;
  border-left: 3px solid #e8e8e8;
  position: relative;
  transition: border-color 0.2s;
}
.history-item:hover {
  border-left-color: var(--el-color-primary, #ea580c);
  background: #fafafa;
}
.history-item::before {
  content: '';
  position: absolute;
  left: -7px;
  top: 14px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--el-color-primary, #ea580c);
  border: 2px solid var(--color-bg-primary);
}
.history-main {
  display: flex;
  align-items: center;
  gap: 12px;
}
.history-time {
  color: var(--color-text-tertiary);
  font-size: 12px;
  white-space: nowrap;
}
.history-user {
  color: var(--el-color-primary, #ea580c);
  font-size: 12px;
  white-space: nowrap;
  font-weight: 500;
}
.history-action {
  color: var(--color-bg-primary);
  background: var(--color-text-tertiary);
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 3px;
  white-space: nowrap;
  text-transform: uppercase;
  font-weight: 500;
}
.history-action.action-create { background: var(--color-success, #16a34a); }
.history-action.action-update { background: var(--el-color-primary, #ea580c); }
.history-action.action-delete { background: #ff4d4f; }

.history-detail {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-text-secondary);
  padding-left: 8px;
}
.history-field {
  color: var(--color-text-tertiary);
  padding-left: 8px;
}
.history-old {
  text-decoration: line-through;
  color: var(--color-text-disabled);
}
.history-arrow {
  color: var(--el-color-primary, #ea580c);
.history-new {
  color: var(--color-success, #16a34a);
  font-weight: 500;
}
.history-detail.history-create {
  color: var(--color-success, #16a34a);
  font-weight: 500;
}
.history-detail.history-delete {
  color: #ff4d4f;
  font-weight: 500;
}
.history-more-btn {
  margin-top: 8px;
  padding: 6px 16px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  background: var(--color-bg-primary);
  cursor: pointer;
  font-size: 12px;
  color: var(--color-text-secondary);
  transition: all 0.2s;
}
.history-more-btn:hover {
  border-color: var(--el-color-primary, #ea580c);
  color: var(--el-color-primary, #ea580c);
}
.history-loading {
  text-align: center;
  padding: 24px;
  color: var(--color-text-tertiary);
  font-size: 13px;
}
</style>
