<template>
  <div class="data-permission-config">
    <FilterBar
      v-model="filters"
      :fields="filterFields"
      :default-visible-count="2"
      @search="onFilterSearch"
      @reset="onFilterReset"
    />

    <MetaTable
      :columns="columns"
      :data="filteredRules"
      :actions="actions"
      :loading="loading"
      :search-placeholder="null"
      empty-title="暂无数据权限规则"
      empty-description="点击「添加规则」创建条件型数据权限"
      empty-type="search"
      @action="handleAction"
    >
      <template #cell-user="{ row }">
        <div class="user-cell">
          <span class="user-name">{{ getUserName(row.role_id) }}</span>
        </div>
      </template>

      <template #cell-resource_type="{ row }">
        <div class="resource-cell">
          <span v-if="row.is_denied" class="badge-denied">禁止</span>
          <span class="resource-type">{{ getResourceLabel(row.resource_type) }}</span>
        </div>
      </template>

      <template #cell-permission_level="{ row }">
        <span class="perm-level-tag" :class="'level-' + (row.permission_level || 'read')">
          {{ getPermLevelLabel(row.permission_level) }}
        </span>
      </template>

      <template #cell-is_readonly="{ row }">
        <span v-if="row.is_readonly" class="readonly-badge">只读</span>
        <span v-else class="no-readonly">-</span>
      </template>

      <template #cell-condition="{ row }">
        <code class="condition-code">{{ row.condition }}</code>
      </template>

      <template #cell-friendly_condition="{ row }">
        <span v-if="row.friendly_condition" class="friendly-condition">
          {{ row.friendly_condition }}
        </span>
        <span v-else class="no-friendly">-</span>
      </template>

      <template #cell-inherit="{ row }">
        <div class="inherit-badges">
          <span v-if="row.inherit_to_children" class="inherit-badge down">向下继承</span>
          <span v-if="row.propagate_to_parents" class="inherit-badge up">向上传播</span>
          <span v-if="!row.inherit_to_children && !row.propagate_to_parents" class="no-inherit">-</span>
        </div>
      </template>
    </MetaTable>

    <ConditionRuleDialog
      v-if="showRuleDialog"
      :visible="showRuleDialog"
      :rule="editingRule"
      :role-id="selectedRoleId"
      @close="showRuleDialog = false"
      @saved="onRuleSaved"
    />

    <ConfirmDialog
      :visible="confirmState.visible"
      :title="confirmState.title"
      :message="confirmState.message"
      type="danger"
      @confirm="confirmState.onConfirm?.()"
      @cancel="confirmState.visible = false"
      @update:visible="confirmState.visible = $event"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import * as permService from '@/services/permissionService'
import { useMessage } from '@/composables/useMessage'
import { FilterBar, MetaTable } from '@/components/common'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import ConditionRuleDialog from './ConditionRuleDialog.vue'

const { success, error } = useMessage()

const loading = ref(false)
const rules = ref([])
const roles = ref([])
const users = ref([])
const filters = ref({})
const showRuleDialog = ref(false)
const editingRule = ref(null)
const selectedRoleId = ref(null)
const confirmState = ref({ visible: false, title: '', message: '', onConfirm: null })

const filterFields = computed(() => [
  {
    key: 'keyword',
    label: '筛选条件',
    type: 'text',
    placeholder: '条件表达式'
  },
  {
    key: 'resource_type',
    label: '资源类型',
    type: 'select',
    placeholder: '全部类型',
    options: [
      { value: '', label: '全部类型' },
      ...Object.entries(permService.RESOURCE_LABELS).map(([value, label]) => ({ value, label }))
    ]
  },
  {
    key: 'permission_level',
    label: '权限级别',
    type: 'select',
    placeholder: '全部级别',
    options: [
      { value: '', label: '全部级别' },
      ...Object.entries(permService.PERMISSION_LEVELS).map(([value, { label }]) => ({ value, label }))
    ]
  }
])

const filteredRules = computed(() => {
  let result = rules.value
  const keyword = filters.value.keyword?.trim().toLowerCase()
  const resourceType = filters.value.resource_type
  const permissionLevel = filters.value.permission_level

  if (keyword) {
    result = result.filter(rule =>
      rule.condition?.toLowerCase().includes(keyword) ||
      rule.friendly_condition?.toLowerCase().includes(keyword)
    )
  }

  if (resourceType) {
    result = result.filter(rule => rule.resource_type === resourceType)
  }

  if (permissionLevel) {
    result = result.filter(rule => rule.permission_level === permissionLevel)
  }

  return result
})

const columns = [
  { key: 'user', label: '用户/角色', width: '140px', slot: true },
  { key: 'resource_type', label: '资源类型', width: '120px', slot: true },
  { key: 'permission_level', label: '资源级别', width: '90px', slot: true },
  { key: 'is_readonly', label: '只读标识', width: '80px', slot: true },
  { key: 'condition', label: '条件表达式', slot: true },
  { key: 'friendly_condition', label: '友好显示', slot: true },
  { key: 'inherit', label: '继承设置', width: '160px', slot: true }
]

const actions = [
  {
    key: 'create',
    label: '添加规则',
    position: 'header',
    variant: 'primary'
  },
  {
    key: 'edit',
    label: '编辑',
    position: 'row',
    variant: 'default'
  },
  {
    key: 'delete',
    label: '删除',
    position: 'row',
    variant: 'danger'
  }
]

function getResourceLabel(resourceType) {
  return permService.getResourceLabel(resourceType)
}

function getPermLevelLabel(level) {
  return permService.getPermissionLevelLabel(level)
}

function getUserName(roleId) {
  const role = roles.value.find(r => r.id === roleId)
  return role?.name || `角色ID: ${roleId}`
}

async function loadRoles() {
  try {
    const r = await permService.loadRoles()
    if (r.success) {
      roles.value = r.data || []
    }
  } catch (e) {
    console.error('Failed to load roles:', e)
  }
}

async function loadRules() {
  loading.value = true
  try {
    const r = await permService.loadConditionRules()
    if (r.success) {
      rules.value = r.data || []
    }
  } catch (e) {
    error('加载数据权限规则失败')
  } finally {
    loading.value = false
  }
}

function handleAction({ key, row }) {
  switch (key) {
    case 'create':
      openCreateDialog()
      break
    case 'edit':
      openEditDialog(row)
      break
    case 'delete':
      deleteRule(row)
      break
  }
}

function openCreateDialog() {
  editingRule.value = null
  selectedRoleId.value = null
  showRuleDialog.value = true
}

function openEditDialog(rule) {
  editingRule.value = { ...rule }
  selectedRoleId.value = rule.role_id
  showRuleDialog.value = true
}

async function deleteRule(rule) {
  confirmState.value = {
    visible: true,
    title: '删除数据权限规则',
    message: `确定要删除此数据权限规则吗？\n条件：${rule.friendly_condition || rule.condition}`,
    onConfirm: async () => {
      try {
        const r = await permService.deleteConditionRule(rule.id)
        if (r.success) {
          await loadRules()
          success('数据权限规则删除成功')
        } else {
          error(r.message || '删除失败')
        }
      } catch (e) {
        error('网络错误')
      }
    }
  }
}

async function onRuleSaved() {
  showRuleDialog.value = false
  await loadRules()
  success('数据权限规则保存成功')
}

function onFilterSearch() {
}

function onFilterReset() {
  filters.value = {}
}

onMounted(() => {
  loadRoles()
  loadRules()
})
</script>

<style scoped>
.data-permission-config {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: var(--spacing-md);
}

.user-cell {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.user-name {
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

.resource-cell {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  flex-wrap: wrap;
}

.badge-denied {
  padding: 2px 6px;
  background: var(--color-error-bg);
  color: var(--color-error);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
}

.resource-type {
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

.permission-level {
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
}

.permission-level.level-read {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.permission-level.level-write {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.permission-level.level-admin {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.perm-level-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  text-align: center;
}

.perm-level-tag.level-read {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.perm-level-tag.level-write {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.perm-level-tag.level-admin {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.readonly-badge {
  display: inline-block;
  padding: 2px 8px;
  background: #f0f5ff;
  color: #165dff;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  text-align: center;
  border: 1px solid #adc6ff;
}

.no-readonly {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
}

.condition-code {
  padding: 4px 8px;
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-family: monospace;
  color: var(--color-text-secondary);
}

.friendly-condition {
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
}

.no-friendly {
  color: var(--color-text-tertiary);
}

.inherit-badges {
  display: flex;
  gap: var(--spacing-xs);
  flex-wrap: wrap;
}

.inherit-badge {
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
}

.inherit-badge.down {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.inherit-badge.up {
  background: var(--color-info-bg, #e6f4ff);
  color: var(--color-info, #1677ff);
}

.no-inherit {
  color: var(--color-text-tertiary);
}
</style>
