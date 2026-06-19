<template>
  <div class="audit-log">
    <div v-if="loading" class="al-loading">
      <div class="al-spinner"></div>
      <span>加载日志...</span>
    </div>
    <div v-else-if="!logs || logs.length === 0" class="al-empty">
      <svg class="al-empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/>
      </svg>
      <span class="al-empty-text">暂无变更记录</span>
      <span class="al-empty-hint">当此对象被修改时，变更记录将显示在这里</span>
    </div>
    <template v-else>
      <div v-if="showFilter" class="al-filter">
        <div class="al-filter-row">
          <span class="al-filter-label">操作:</span>
          <AppButton
            v-for="opt in filterOptions"
            :key="opt.value"
            :variant="activeFilter === opt.value ? 'primary' : 'secondary'"
            size="xs"
            :class="{ 'al-filter-btn--active': activeFilter === opt.value }"
            @click="handleFilterChange(opt.value)"
          >
            {{ opt.label }}
          </AppButton>
        </div>
        <div class="al-filter-row" v-if="availableFields.length > 0">
          <span class="al-filter-label">字段:</span>
          <el-dropdown trigger="click" @command="handleFieldFilterChange">
            <AppButton variant="secondary" size="xs" class="al-field-dropdown">
              {{ activeFieldFilter ? getFieldLabel(activeFieldFilter) : '全部字段' }}
              <svg class="al-dropdown-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M6 9l6 6 6-6"/>
              </svg>
            </AppButton>
            <template #dropdown>
              <el-dropdown-menu class="al-field-menu">
                <div class="al-field-search">
                  <input
                    v-model="fieldSearchText"
                    type="text"
                    placeholder="搜索字段..."
                    class="al-field-search-input"
                  />
                </div>
                <el-dropdown-item :command="''" :class="{ 'is-active': !activeFieldFilter }">
                  全部字段
                </el-dropdown-item>
                <el-dropdown-item
                  v-for="field in filteredFieldOptions"
                  :key="field"
                  :command="field"
                  :class="{ 'is-active': activeFieldFilter === field }"
                >
                  {{ getFieldLabel(field) }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
        <div class="al-filter-actions">
          <AppButton
            variant="secondary"
            size="xs"
            @click="toggleAllGroups"
          >
            {{ allExpanded ? '折叠全部' : '展开全部' }}
          </AppButton>
        </div>
      </div>

      <div class="al-list">
        <div
          v-for="group in displayedGroups"
          :key="group.key"
          class="al-group"
        >
          <div class="al-group-header" @click="toggleGroup(group.key)">
            <div class="al-group-main">
              <span class="al-group-time">{{ formatTime(group.timestamp) }}</span>
              <span class="al-group-user">{{ formatUserName(group.user_name) }}</span>
              <span
                class="al-group-action"
                :class="'al-action--' + (group.primaryAction || 'unknown').toLowerCase()"
              >
                {{ formatAction(group.primaryAction) }}
              </span>
              <span class="al-group-count" v-if="group.items.length > 1 || group._children.length > 0">
                {{ group.items.length }} 项变更<span v-if="group._children.length > 0"> · {{ group._children.length }} 个新建子对象</span>
              </span>
            </div>
            <div class="al-group-toggle">
              <svg
                :class="['al-toggle-icon', { 'al-toggle-icon--expanded': expandedGroups.has(group.key) }]"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path d="M9 18l6-6-6-6"/>
              </svg>
            </div>
          </div>

          <div v-if="expandedGroups.has(group.key)" class="al-group-items">
            <AppCollapse v-if="group.items.length > 0" :default-expanded="true" class="al-items-collapse">
              <template #title>
                <span class="al-items-summary">
                  <span class="al-items-icon">●</span>
                  主对象字段变更
                  <el-tag size="small" type="info" effect="plain">{{ group.items.length }} 项</el-tag>
                </span>
              </template>
              <div class="al-items-list">
                <div
                  v-for="item in group.items"
                  :key="item.id"
                  :class="['al-item', { 'al-item--clickable': clickMode }]"
                  @click="handleLogClick(item)"
                >
                  <div class="al-detail al-detail--associate" v-if="item.action === 'ASSOCIATE' || item.action === 'ASSIGN'">
                    <span class="al-field">{{ getFieldLabel(item.field_name) || '关联' }}:</span>
                    <span class="al-associate-add">+ {{ parseTargetDisplay(item.new_value) }}</span>
                  </div>
                  <div class="al-detail al-detail--dissociate" v-else-if="item.action === 'DISSOCIATE' || item.action === 'REVOKE'">
                    <span class="al-field">{{ getFieldLabel(item.field_name) || '关联' }}:</span>
                    <span class="al-associate-remove">- {{ parseTargetDisplay(item.old_value) }}</span>
                  </div>
                  <div class="al-detail al-detail--batch-associate" v-else-if="item._batch_associate">
                    <span class="al-field">{{ getFieldLabel(item.field_name) || '关联' }}:</span>
                    <span class="al-associate-add">+ {{ formatBatchTargets(item._batch_targets) }}</span>
                  </div>
                  <div class="al-detail" v-else-if="item.field_name">
                    <span class="al-field">{{ getFieldLabel(item.field_name) }}:</span>
                    <span class="al-old">{{ getFieldValueDisplay(item.old_value, item.field_name) }}</span>
                    <span class="al-arrow">→</span>
                    <span class="al-new">{{ getFieldValueDisplay(item.new_value, item.field_name) }}</span>
                  </div>
                  <div class="al-detail al-detail--create" v-else-if="item.action === 'CREATE'">
                    <span>创建记录</span>
                  </div>
                  <div class="al-detail al-detail--delete" v-else-if="item.action === 'DELETE'">
                    <span>删除记录</span>
                  </div>
                  <div class="al-detail" v-else>
                    <span>{{ item.action }}</span>
                  </div>
                  <div v-if="item._source && item._source !== 'own'" class="al-source-badge">
                    {{ formatSource(item._source, item._child_type) }}
                  </div>
                  <div v-else-if="item._cascade_from && !item._source" class="al-cascade-from">
                    由 {{ item._cascade_from.type }} 级联操作
                  </div>
                </div>
              </div>
            </AppCollapse>

            <div v-if="group._children.length > 0" class="al-children-section">
              <AppCollapse :default-expanded="true">
                <template #title>
                  <span class="al-children-summary">
                    <span class="al-children-icon">▣</span>
                    级联影响 {{ group._children.length }} 个子对象
                    <el-tag v-if="getChildObjectTypes(group._children)" size="small" type="warning" effect="plain">
                      {{ getChildObjectTypes(group._children) }}
                    </el-tag>
                  </span>
                </template>
                <div class="al-children-list">
                  <div
                    v-for="child in group._children"
                    :key="child.id"
                    class="al-child-item"
                  >
                    <span class="al-child-type">{{ getObjectTypeLabel(child.object_type) }}</span>
                    <span class="al-child-action">{{ formatAction(child.action) }}</span>
                    <span v-if="child.field_name" class="al-child-detail">
                      {{ getFieldLabel(child.field_name) }}: {{ getFieldValueDisplay(child.old_value, child.field_name) }} → {{ getFieldValueDisplay(child.new_value, child.field_name) }}
                    </span>
                  </div>
                </div>
              </AppCollapse>
            </div>
          </div>
        </div>

        <AppButton
          v-if="!showPagination && logs.length > displayLimit && !showAll"
          variant="text"
          size="sm"
          block
          @click="showAll = true"
        >
          展开全部 {{ logs.length }} 条记录
        </AppButton>
        <AppButton
          v-else-if="!showPagination && showAll && logs.length > displayLimit"
          variant="text"
          size="sm"
          block
          @click="showAll = false"
        >
          收起
        </AppButton>
      </div>

      <div v-if="showPagination && total > pageSize" class="al-pagination">
        <el-pagination
          :current-page="currentPage"
          :page-size="pageSize"
          :total="total"
          layout="prev, pager, next"
          small
          @current-change="handlePageChange"
        />
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import AppButton from '@/components/common/AppButton/AppButton.vue'
import AppCollapse from '@/components/common/AppCollapse/AppCollapse.vue'
import { dateFormatService } from '@/services/DateFormatService'
import { getActionLabel, getUserNameDisplay, isInternalField, isInternalAction, getFieldLabel, getFieldValueDisplay, getObjectTypeLabel } from '@/utils/auditLogFormat'

const props = defineProps({
  logs: {
    type: Array,
    default: () => []
  },
  loading: {
    type: Boolean,
    default: false
  },
  displayLimit: {
    type: Number,
    default: 10
  },
  total: {
    type: Number,
    default: 0
  },
  showFilter: {
    type: Boolean,
    default: true
  },
  showPagination: {
    type: Boolean,
    default: false
  },
  currentPage: {
    type: Number,
    default: 1
  },
  pageSize: {
    type: Number,
    default: 20
  },
  clickMode: {
    type: String,
    default: ''
  },
  objectType: {
    type: String,
    default: ''
  },
  objectId: {
    type: [String, Number],
    default: null
  }
})

const emit = defineEmits([
  'page-change',
  'filter-change',
  'log-click'
])

const showAll = ref(false)
const activeFilter = ref('')
const activeFieldFilter = ref('')
const fieldSearchText = ref('')
const expandedGroups = ref(new Set())
const allExpanded = ref(true)

const filterOptions = [
  { label: '全部', value: '' },
  { label: '创建', value: 'CREATE' },
  { label: '更新', value: 'UPDATE' },
  { label: '删除', value: 'DELETE' },
  { label: '添加关联', value: 'ASSOCIATE' },
  { label: '移除关联', value: 'DISSOCIATE' },
  { label: '关联操作', value: '_association_target' },
  { label: '级联操作', value: '_cascade_child' },
  { label: '子对象变更', value: '_child_object' }
]

const availableFields = computed(() => {
  if (!Array.isArray(props.logs)) return []
  const fields = new Set()
  for (const item of props.logs) {
    if (item.field_name && !isInternalField(item.field_name)) {
      fields.add(item.field_name)
    }
  }
  return Array.from(fields).sort()
})

const filteredFieldOptions = computed(() => {
  if (!fieldSearchText.value) return availableFields.value
  const search = fieldSearchText.value.toLowerCase()
  return availableFields.value.filter(f => f.toLowerCase().includes(search))
})

const filteredLogs = computed(() => {
  if (!Array.isArray(props.logs)) return []
  let result = props.logs

  // [FIX 2026-06-15 业务化审查] 业务视图: 默认隐藏 _record 内部聚合字段
  // _record 是 cud 操作的聚合 summary, 业务上 group header 已经表明 (创建/更新/删除)
  // 显示出来会让业务人员困惑 "(空) -> DELETE" 是啥意思
  // 同时也隐藏其他内部技术字段 (extra_data, cascade_root_id 等)
  // 同时也隐藏内部技术 action (性能监控/审计系统/未知)
  result = result.filter(item => !isInternalField(item.field_name) && !isInternalAction(item.action))

  if (activeFilter.value) {
    if (activeFilter.value === 'ASSOCIATE') {
      result = result.filter(item => item.action === 'ASSOCIATE' || item.action === 'ASSIGN')
    } else if (activeFilter.value === 'DISSOCIATE') {
      result = result.filter(item => item.action === 'DISSOCIATE' || item.action === 'REVOKE')
    } else if (activeFilter.value.startsWith('_')) {
      result = result.filter(item => item._source === activeFilter.value.slice(1))
    } else {
      result = result.filter(item => item.action === activeFilter.value)
    }
  }

  if (activeFieldFilter.value) {
    result = result.filter(item => item.field_name === activeFieldFilter.value)
  }

  result = aggregateBatchAssociations(result)

  return result
})

const groupedLogs = computed(() => {
  const groups = new Map()

  for (const item of filteredLogs.value) {
    const groupKey = item.trace_id || item.transaction_id || `single-${item.id}`

    if (!groups.has(groupKey)) {
      groups.set(groupKey, {
        key: groupKey,
        timestamp: item.created_at,
        user_name: item.user_name,
        primaryAction: item.action,
        object_type: item.object_type,
        object_id: item.object_id,
        items: [],
        _children: []
      })
    }

    const group = groups.get(groupKey)
    if (item._parent_type) {
      group._children.push(item)
    } else if (item._source === 'cascade_child' || item._source === 'child_object') {
      group._children.push(item)
    } else if (
      // [FIX 2026-06-10] DISSOCIATE 级联删除（parent_object_type 存在）与主操作同 trace，
      // 应归为"子对象"而非主操作条目，避免"X 项变更"计数含 DISSOCIATE
      (item.action === 'DISSOCIATE' || item.action === 'REVOKE') &&
      item.parent_object_type
    ) {
      group._children.push(item)
    } else if (
      group.items.length > 0 &&
      group.object_type && item.object_type &&
      group.object_type !== item.object_type
    ) {
      // 方案 A: 同 trace 内跨 object_type 归为子对象
      group._children.push(item)
    } else {
      group.items.push(item)
    }

    if (item.created_at < group.timestamp) {
      group.timestamp = item.created_at
    }
  }

  for (const group of groups.values()) {
    // CREATE 组存在字段条目时, 移除冗余的 summary 条目 (field_name='')
    if (group.primaryAction === 'CREATE' && group.items.length > 1) {
      const hasFieldItem = group.items.some(it => it.field_name)
      if (hasFieldItem) {
        group.items = group.items.filter(it => it.field_name)
      }
    }
  }

  const result = Array.from(groups.values())
  result.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))

  return mergeAdjacentGroups(result)
})

function mergeAdjacentGroups(groups) {
  if (groups.length < 2) return groups
  const result = [groups[0]]
  for (let i = 1; i < groups.length; i++) {
    const prev = result[result.length - 1]
    const curr = groups[i]
    if (shouldMergeGroups(prev, curr)) {
      mergeGroupInto(prev, curr)
    } else {
      result.push(curr)
    }
  }
  return result
}

function shouldMergeGroups(prev, curr) {
  if (prev.primaryAction !== curr.primaryAction) return false
  // 双方都必须有 object_type + object_id 才考虑合并, 避免缺字段时误合并
  if (!prev.object_type || !curr.object_type) return false
  if (prev.object_id == null || curr.object_id == null) return false
  // 同 object 视为同一逻辑动作, 即便 user_name 显示有差异
  // (e.g. 一些条目记录的是 display_name '系统管理员', 另一些是 username 'admin')
  const sameObject = prev.object_type === curr.object_type &&
                     String(prev.object_id) === String(curr.object_id)
  if (!sameObject) return false
  const timeDelta = Math.abs(new Date(prev.timestamp) - new Date(curr.timestamp))
  return timeDelta < 5000
}

function mergeGroupInto(target, source) {
  const seenIds = new Set(target.items.map(it => it.id))
  for (const it of source.items) {
    if (!seenIds.has(it.id)) {
      target.items.push(it)
      seenIds.add(it.id)
    }
  }
  for (const child of source._children) {
    if (!seenIds.has(child.id)) {
      target._children.push(child)
      seenIds.add(child.id)
    }
  }
  if (new Date(source.timestamp) < new Date(target.timestamp)) {
    target.timestamp = source.timestamp
  }
}

watch(groupedLogs, (groups) => {
  if (allExpanded.value) {
    expandedGroups.value = new Set(groups.map(g => g.key))
  }
}, { immediate: true })

function toggleAllGroups() {
  allExpanded.value = !allExpanded.value
  if (allExpanded.value) {
    expandedGroups.value = new Set(groupedLogs.value.map(g => g.key))
  } else {
    expandedGroups.value = new Set()
  }
}

const displayedGroups = computed(() => {
  if (props.showPagination) return groupedLogs.value

  if (showAll.value) return groupedLogs.value

  let count = 0
  const result = []
  for (const group of groupedLogs.value) {
    if (count >= props.displayLimit) break
    result.push(group)
    count++
  }
  return result
})

function toggleGroup(groupKey) {
  const newExpanded = new Set(expandedGroups.value)
  if (newExpanded.has(groupKey)) {
    newExpanded.delete(groupKey)
  } else {
    newExpanded.add(groupKey)
  }
  expandedGroups.value = newExpanded
  allExpanded.value = newExpanded.size === groupedLogs.value.length
}

function handleFilterChange(filterValue) {
  activeFilter.value = filterValue
  showAll.value = false
  allExpanded.value = true
  if (typeof filterValue === 'string' && filterValue.startsWith('_')) {
    return
  }
  emit('filter-change', { action: filterValue || undefined, field: activeFieldFilter.value || undefined })
}

function handleFieldFilterChange(fieldValue) {
  activeFieldFilter.value = fieldValue
  showAll.value = false
  allExpanded.value = true
  emit('filter-change', { action: activeFilter.value || undefined, field: fieldValue || undefined })
}

function handlePageChange(page) {
  emit('page-change', page)
}

function handleLogClick(item) {
  if (!props.clickMode) return
  emit('log-click', item)
}

function formatTime(time) {
  if (!time) return '-'
  const date = new Date(time)
  if (isNaN(date.getTime())) return '-'
  return dateFormatService.format(date, { dateStyle: 'medium', timeStyle: 'short' })
}

function formatAction(action) {
  // [FIX 2026-06-15 业务化审查] 用统一工具函数覆盖全部 action, 避免 "未知"
  return getActionLabel(action)
}

function formatUserName(userName) {
  // [FIX 2026-06-15 业务化审查] "system" -> "系统", "[REDACTED]" -> "已脱敏"
  return getUserNameDisplay(userName)
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

function formatBatchTargets(targets) {
  if (!Array.isArray(targets) || targets.length === 0) return '-'
  if (targets.length <= 3) {
    return targets.join('、')
  }
  const shown = targets.slice(0, 2).join('、')
  return `${shown} 等 ${targets.length} 人`
}

function formatSource(source, childType) {
  const sourceMap = {
    'association_target': '来自关联',
    'cascade_child': '级联操作',
    'child_object': childType || '子对象',
    'relationship': '关系变更'
  }
  return sourceMap[source] || ''
}

// [FIX 2026-06-19 业务化] 聚合子对象类型为中文标签
// 例如 5 个 version 字段 → "版本", 1 个 product 字段 + 1 个 version 字段 → "产品 · 版本"
function getChildObjectTypes(children) {
  if (!children || children.length === 0) return ''
  const types = [...new Set(children.map(c => getObjectTypeLabel(c.object_type || c._child_type)))]
  return types.filter(Boolean).join(' · ')
}

function aggregateBatchAssociations(items) {
  if (!Array.isArray(items) || items.length < 2) return items
  
  const batchGroups = {}
  const nonBatchItems = []

  for (const item of items) {
    const isAssocAction = item.action === 'ASSOCIATE' || item.action === 'DISSOCIATE' || item.action === 'ASSIGN' || item.action === 'REVOKE'
    if (!isAssocAction || !item.transaction_id) {
      nonBatchItems.push(item)
      continue
    }

    const batchKey = `${item.transaction_id}|${item.action}|${item.field_name}`
    if (!batchGroups[batchKey]) {
      batchGroups[batchKey] = { action: item.action, field_name: item.field_name, items: [] }
    }
    batchGroups[batchKey].items.push(item)
  }

  const result = [...nonBatchItems]

  for (const [, group] of Object.entries(batchGroups)) {
    if (group.items.length >= 2) {
      const first = group.items[0]
      const targets = group.items.map(it => {
        const raw = group.action === 'DISSOCIATE' || group.action === 'REVOKE' ? it.old_value : it.new_value
        return parseTargetDisplay(raw)
      })
      result.push({
        ...first,
        _batch_associate: true,
        _batch_targets: targets,
        _batch_count: group.items.length
      })
    } else {
      result.push(group.items[0])
    }
  }

  return result
}
</script>

<style scoped>
.audit-log {
  width: 100%;
}

.al-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-xl);
  color: var(--color-text-secondary);
}

.al-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: al-spin 0.8s linear infinite;
}

@keyframes al-spin {
  to { transform: rotate(360deg); }
}

.al-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-2xl);
  color: var(--color-text-tertiary);
}

.al-empty-icon {
  width: 48px;
  height: 48px;
  opacity: 0.5;
}

.al-empty-text {
  font-size: var(--font-size-sm);
}

.al-empty-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.al-filter {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-md);
}

.al-filter-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  flex-wrap: wrap;
}

.al-filter-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  min-width: 36px;
}

.al-filter-actions {
  display: flex;
  justify-content: flex-end;
}

.al-field-dropdown {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  min-width: 100px;
}

.al-dropdown-icon {
  width: 12px;
  height: 12px;
}

.al-field-menu {
  max-height: 300px;
  overflow-y: auto;
}

.al-field-search {
  padding: var(--spacing-xs);
  border-bottom: 1px solid var(--color-border-light, var(--color-border));
}

.al-field-search-input {
  width: 100%;
  padding: 4px 8px;
  font-size: var(--font-size-xs);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  outline: none;
}

.al-field-search-input:focus {
  border-color: var(--color-primary);
}

.al-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.al-group {
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
  overflow: hidden;
}

.al-group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-sm) var(--spacing-md);
  cursor: pointer;
  transition: all var(--transition-normal);
}

.al-group-header:hover {
  background: var(--color-bg-tertiary);
}

.al-group-main {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  font-size: var(--font-size-sm);
  flex-wrap: wrap;
}

.al-group-time {
  color: var(--color-text-secondary);
  font-family: monospace;
  font-size: var(--font-size-xs);
}

.al-group-user {
  color: var(--color-text-primary);
  font-weight: var(--font-weight-medium);
}

.al-group-action {
  padding: 1px 8px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
  border: 1px solid var(--color-border-light, var(--color-border));
}

.al-group-count {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
  padding: 2px 6px;
  background: var(--color-bg-spotlight);
  border-radius: var(--radius-sm);
}

.al-group-toggle {
  flex-shrink: 0;
}

.al-toggle-icon {
  width: 16px;
  height: 16px;
  color: var(--color-text-tertiary);
  transition: transform 0.2s ease;
}

.al-toggle-icon--expanded {
  transform: rotate(90deg);
}

.al-group-items {
  border-top: 1px solid var(--color-border-light, var(--color-border));
  background: var(--color-bg-primary);
}

.al-item {
  padding: var(--spacing-xs) var(--spacing-md);
  border-bottom: 1px solid var(--color-border-light, var(--color-border));
}

.al-item:last-child {
  border-bottom: none;
}

.al-item--clickable {
  cursor: pointer;
}

.al-item--clickable:hover {
  background: var(--color-primary-bg);
}

.al-action--create,
.al-action--update,
.al-action--delete,
.al-action--assign,
.al-action--revoke,
.al-action--associate,
.al-action--dissociate,
.al-action--unknown {
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
  border-color: var(--color-border-light, var(--color-border));
}

.al-detail {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
}

.al-field {
  color: var(--color-text-primary);
  font-weight: var(--font-weight-medium);
}

.al-old {
  color: var(--color-text-tertiary);
  text-decoration: line-through;
  background: var(--color-bg-tertiary);
  padding: 0 4px;
  border-radius: var(--radius-sm);
}

.al-arrow {
  color: var(--color-text-tertiary);
}

.al-new {
  color: var(--color-text-primary);
  font-weight: var(--font-weight-medium);
  background: var(--color-primary-bg, var(--color-bg-tertiary));
  padding: 0 4px;
  border-radius: var(--radius-sm);
}

.al-detail--create {
  color: var(--color-text-secondary);
}

.al-detail--delete {
  color: var(--color-text-secondary);
}

.al-detail--associate,
.al-detail--batch-associate,
.al-detail--dissociate {
  color: var(--color-text-secondary);
}

.al-associate-add {
  color: var(--color-text-primary);
  font-weight: var(--font-weight-medium);
}

.al-associate-remove {
  color: var(--color-text-secondary);
  font-weight: var(--font-weight-medium);
  text-decoration: line-through;
}

.al-pagination {
  display: flex;
  justify-content: center;
  margin-top: var(--spacing-md);
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--color-border-light, var(--color-border));
}

.al-cascade-from {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  padding-left: var(--spacing-md);
  margin-top: 2px;
}

.al-source-badge {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  padding-left: var(--spacing-md);
  margin-top: 2px;
}

.al-children-section {
  margin-top: var(--spacing-sm);
  border-top: 1px solid var(--color-border-light, var(--color-border));
  padding-top: var(--spacing-sm);
}

.al-children-summary {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  font-size: var(--font-size-sm);
  color: var(--color-warning, #d97706);
  font-weight: 500;
}

.al-children-icon {
  color: var(--color-warning, #d97706);
  font-size: 14px;
  line-height: 1;
}

.al-children-list {
  padding-left: var(--spacing-md);
}

.al-items-collapse {
  margin-bottom: var(--spacing-sm);
}

.al-items-summary {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  font-weight: 500;
}

.al-items-icon {
  color: var(--color-primary, #3b82f6);
  font-size: 10px;
  line-height: 1;
}

.al-items-list {
  padding-left: var(--spacing-md);
  border-left: 2px solid var(--color-border-light, var(--color-border));
  margin-left: 4px;
}

.al-child-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-xs) 0;
  font-size: var(--font-size-sm);
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
  padding-left: var(--spacing-sm);
  padding-right: var(--spacing-sm);
  margin-bottom: var(--spacing-xs);
  transition: background var(--transition-normal);
}

.al-child-item:hover {
  background: var(--color-bg-secondary);
}

.al-child-type {
  color: var(--color-text-secondary);
  font-weight: var(--font-weight-medium);
}

.al-child-action {
  color: var(--color-text-primary);
}

.al-child-detail {
  color: var(--color-text-tertiary);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
