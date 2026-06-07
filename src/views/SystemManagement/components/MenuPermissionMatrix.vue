<template>
  <div class="menu-permission-matrix">
    <div v-if="loading" class="loading-state">
      <div style="color:var(--color-warning, #f59e0b)">[加载中... menusLength={{ modelValue.length }} loading={{ loading }}]</div>
    </div>

    <div v-else-if="modelValue.length === 0" class="empty-state">
      <el-empty description="暂无菜单权限配置" />
    </div>

    <div v-else class="menu-list">
      <div
        v-for="menu in modelValue"
        :key="menu.menu_code"
        :class="['menu-card', { 'is-assigned': menu.assigned }]"
      >
        <div class="menu-card-header">
          <input
            type="checkbox"
            :checked="menu.assigned"
            @change="handleToggleMenu(menu)"
          />
          <div class="menu-title-area" @click="toggleMenuExpand(menu)">
            <span class="menu-name">{{ menu.display_name }}</span>
            <span class="menu-path">{{ menu.menu_path }}</span>
            <span
              class="expand-icon"
              :class="{ expanded: expandedMenus.has(menu.menu_code) }"
            >▶</span>
          </div>

          <div class="menu-badges">
            <span
              v-if="menu.required_permissions?.length"
              :class="['badge', 'badge-capability', { 'badge-all-granted': allCapsGranted(menu) }]"
            >
              {{ grantedCapCount(menu) }}/{{ menu.required_permissions.length }} 权限
            </span>
            <span v-if="menu.has_data_scope" class="badge badge-scope">有数据范围</span>
          </div>
        </div>

        <div v-if="expandedMenus.has(menu.menu_code)" class="menu-card-body">
          <!-- 动作分组区域（主展示） -->
          <div v-if="menu.bo_permission_groups?.length" class="action-groups-section">
            <div class="section-label">
              <AppIcon name="key" :size="12" />
              <span>功能权限</span>
            </div>
            <div
              v-for="boGroup in menu.bo_permission_groups"
              :key="boGroup.bo_id"
              class="bo-group-row"
            >
              <span class="bo-name">{{ boGroup.bo_name }}</span>
              <div class="group-toggles">
                <button
                  v-for="groupKey in ['view', 'edit', 'manage']"
                  :key="groupKey"
                  v-show="boGroup.groups[groupKey]"
                  :class="['group-btn', `group-${groupKey}`, {
                    'is-active': boGroup.groups[groupKey]?.granted,
                    [`source-${boGroup.groups[groupKey]?.source}`]: true
                  }]"
                  @click="handleToggleActionGroup(menu, boGroup.bo_id, groupKey)"
                >
                  <span class="group-btn-label">{{ GROUP_LABELS[groupKey] }}</span>
                  <span class="group-source-tag">{{ sourceLabel(boGroup.groups[groupKey]) }}</span>
                </button>
                <!-- 独立动作 -->
                <button
                  v-for="sp in boGroup.standalone"
                  :key="sp.action"
                  :class="['group-btn', 'group-standalone', {
                    'is-active': sp.granted,
                    [`source-${sp.source}`]: true
                  }]"
                  @click="handleToggleStandalone(menu, boGroup.bo_id, sp.action)"
                >
                  <span class="group-btn-label">{{ sp.label }}</span>
                  <span class="group-source-tag">{{ sourceLabel(sp) }}</span>
                </button>
              </div>
            </div>
          </div>

          <!-- 详细权限列表（可折叠） -->
          <details v-if="menu.required_permissions?.length" class="perm-details" open>
            <summary>详细权限 ({{ menu.required_permissions.length }})</summary>
            <div class="capability-matrix">
              <div
                v-for="rp in menu.required_permissions"
                :key="rp.code"
                :class="['cap-item', { 'cap-granted': rp.granted, 'cap-excluded': rp.source === 'exclude' }]"
                @click="handleTogglePermission(menu, rp)"
              >
                <span class="cap-check">
                  <input
                    type="checkbox"
                    :checked="rp.granted"
                    @click.stop
                    @change="handleTogglePermission(menu, rp)"
                  />
                </span>
                <span class="cap-label">{{ rp.label }}</span>
                <span class="cap-code">{{ rp.code }}</span>
                <span
                  :class="['cap-source-tag', `source-${rp.source || 'none'}`]"
                >
                  {{ permSourceLabel(rp) }}
                </span>
              </div>
            </div>
          </details>

          <div v-if="menu.has_data_scope && menu.data_scopes" class="data-scope-inline">
            <div class="scope-label">
              <AppIcon name="edit" :size="12" /> 数据约束（此菜单的数据访问范围）
            </div>
            <div v-for="scope in menu.data_scopes" :key="scope.resource_type" class="scope-item">
              <span class="scope-type">{{ scope.resource_type }}</span>
              <span class="scope-detail">
                {{ scope.permissions.length }} 条规则 ({{ scope.permissions.map(p => p.level).join(', ') }})
              </span>
              <button class="btn-link btn-xs" @click="$emit('configure-scope', menu, scope)">配置</button>
            </div>
          </div>

          <div
            v-if="menu.assigned && !menu.has_data_scope && menu.data_permission_hint?.resource_types?.length"
            class="data-scope-hint"
          >
            <span class="hint-icon"><AppIcon name="tip" :size="14" /></span>
            建议为此菜单配置
            <button class="btn-link btn-xs" @click="$emit('configure-data-scope', menu)">数据权限</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef } from 'vue'
import { AppIcon } from '@/components/common/AppIcon'
import {
  SOURCE_LABELS,
  getSourceLabel,
  GROUP_LABELS,
  SECTION_TITLES,
  type PermissionSource,
} from '../constants/permissionConstants'

interface Permission {
  code: string
  label: string
  granted: boolean
  source: PermissionSource
}

interface DataScope {
  resource_type: string
  permissions: Array<{ level: string }>
}

interface ActionGroupState {
  granted: boolean
  source: PermissionSource
}

interface StandalonePerm {
  action: string
  label: string
  granted: boolean
  source: PermissionSource
}

interface BoPermissionGroup {
  bo_id: string
  bo_name: string
  groups: Record<string, ActionGroupState>
  standalone: StandalonePerm[]
}

interface BoBinding {
  bo_id: string
  role: 'primary' | 'secondary' | 'reference'
  include_actions?: string[]
}

interface Menu {
  menu_code: string
  display_name: string
  menu_path: string
  assigned: boolean
  has_data_scope: boolean
  required_permissions: Permission[]
  bo_permission_groups?: BoPermissionGroup[]
  data_scopes?: DataScope[]
  data_permission_hint?: { resource_types: string[] }
  bo_bindings?: BoBinding[]
  primary_object_type?: string
  object_types?: string[]
  auto_generated?: boolean
}

const props = defineProps<{
  modelValue: Menu[]
  loading?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [menus: Menu[]]
  'change': [menus: Menu[]]
  'configure-scope': [menu: Menu, scope: DataScope]
  'configure-data-scope': [menu: Menu]
  'toggle-action-group': [menu: Menu, boId: string, groupKey: string]
  'toggle-standalone': [menu: Menu, boId: string, action: string]
}>()

const expandedMenus = ref(new Set<string>())

const menus = toRef(props, 'modelValue')

function handleToggleMenu(menu: Menu) {
  menu.assigned = !menu.assigned

  if (menu.assigned) {
    expandedMenus.value.add(menu.menu_code)
    menu.required_permissions?.forEach(p => {
      p.granted = true
      p.source = 'auto'
    })
    menu.bo_permission_groups?.forEach(bg => {
      Object.keys(bg.groups).forEach(gk => {
        bg.groups[gk].granted = true
        bg.groups[gk].source = 'auto'
      })
      bg.standalone?.forEach(sp => {
        sp.granted = true
        sp.source = 'auto'
      })
    })
  } else {
    menu.required_permissions?.forEach(p => {
      p.granted = false
      p.source = ''
    })
    menu.bo_permission_groups?.forEach(bg => {
      Object.keys(bg.groups).forEach(gk => {
        bg.groups[gk].granted = false
        bg.groups[gk].source = ''
      })
      bg.standalone?.forEach(sp => {
        sp.granted = false
        sp.source = ''
      })
    })
  }

  emit('update:modelValue', menus.value)
  emit('change', menus.value)
}

function handleTogglePermission(menu: Menu, perm: Permission) {
  perm.granted = !perm.granted
  perm.source = perm.granted ? 'include' : 'exclude'

  if (perm.granted && !menu.assigned) {
    menu.assigned = true
    expandedMenus.value.add(menu.menu_code)
  }

  // 重新推导该 BO 的分组状态
  const boId = perm.code.split(':')[0]
  recalcGroupStatus(menu, boId)

  emit('update:modelValue', menus.value)
  emit('change', menus.value)
}

function handleToggleActionGroup(menu: Menu, boId: string, groupKey: string) {
  emit('toggle-action-group', menu, boId, groupKey)
  emit('update:modelValue', menus.value)
  emit('change', menus.value)
}

function handleToggleStandalone(menu: Menu, boId: string, action: string) {
  emit('toggle-standalone', menu, boId, action)
  emit('update:modelValue', menus.value)
  emit('change', menus.value)
}

// 重新计算动作分组状态
function recalcGroupStatus(menu: Menu, boId: string) {
  const boGroup = menu.bo_permission_groups?.find(g => g.bo_id === boId)
  if (!boGroup) return

  const ACTION_GROUPS_MAP: Record<string, string[]> = {
    view: ['read', 'list'],
    edit: ['read', 'list', 'create', 'update'],
    manage: ['read', 'list', 'create', 'update', 'delete'],
  }

  const boPerms = menu.required_permissions?.filter(p => p.code.startsWith(`${boId}:`)) || []

  Object.keys(ACTION_GROUPS_MAP).forEach(gk => {
    const groupActions = ACTION_GROUPS_MAP[gk]
    const matchingPerms = boPerms.filter(p => {
      const action = p.code.split(':')[1]
      return groupActions.includes(action)
    })

    if (matchingPerms.length === 0) return

    const allGranted = matchingPerms.every(p => p.granted)
    const sources = new Set(matchingPerms.map(p => p.source))

    let groupSource: PermissionSource = ''
    if (sources.has('exclude')) groupSource = 'exclude'
    else if (sources.has('include')) groupSource = 'include'
    else if (sources.has('auto')) groupSource = 'auto'

    if (boGroup.groups[gk]) {
      boGroup.groups[gk].granted = allGranted
      boGroup.groups[gk].source = groupSource
    }
  })
}

function toggleMenuExpand(menu: Menu) {
  if (expandedMenus.value.has(menu.menu_code)) {
    expandedMenus.value.delete(menu.menu_code)
  } else {
    expandedMenus.value.add(menu.menu_code)
  }
  expandedMenus.value = new Set(expandedMenus.value)
}

function allCapsGranted(menu: Menu) {
  return menu.required_permissions?.every(p => p.granted)
}

function grantedCapCount(menu: Menu) {
  if (!menu.required_permissions) return 0
  return menu.required_permissions.filter(p => p.granted).length
}

function sourceLabel(item: { granted: boolean; source: PermissionSource } | undefined): string {
  if (!item) return ''
  return getSourceLabel(item.source)
}

function permSourceLabel(perm: Permission): string {
  return getSourceLabel(perm.source || 'none')
}
</script>

<style scoped lang="scss">
@import '../../../styles/mixins.scss';

.menu-permission-matrix {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.loading-state,
.empty-state {
  padding: var(--spacing-lg);
  text-align: center;
}

.menu-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.menu-card {
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  transition: all var(--transition-normal);
  overflow: hidden;

  &:hover {
    border-color: var(--color-border);
  }

  &.is-assigned {
    border-left: 3px solid var(--yonyou-orange-600, #ea580c);
    background: rgba(234, 88, 12, 0.02);
  }
}

.menu-card-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);

  input[type='checkbox'] {
    width: 16px;
    height: 16px;
    accent-color: var(--yonyou-orange-600, #ea580c);
    cursor: pointer;
    flex-shrink: 0;
  }
}

.menu-title-area {
  flex: 1;
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  min-width: 0;
  cursor: pointer;
}

.menu-name {
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--color-text-primary);
  white-space: nowrap;
}

.menu-path {
  font-size: var(--font-size-xs);
  color: var(--color-text-quaternary);
  font-family: monospace;
  opacity: 0.7;
}

.expand-icon {
  font-size: 10px;
  color: var(--color-text-quaternary);
  transition: transform var(--transition-fast);
  flex-shrink: 0;

  &.expanded {
    transform: rotate(90deg);
  }
}

.menu-badges {
  display: flex;
  gap: var(--spacing-xs);
  flex-shrink: 0;
}

.badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 10px;
  font-weight: 500;
  white-space: nowrap;

  &.badge-capability {
    background: var(--color-bg-secondary);
    color: var(--color-text-secondary);

    &.badge-all-granted {
      background: var(--color-success-bg);
      color: var(--color-success);
    }
  }

  &.badge-scope {
    background: var(--color-primary-bg);
    color: var(--color-primary);
  }
}

.menu-card-body {
  padding: var(--spacing-sm) var(--spacing-md) var(--spacing-md) calc(var(--spacing-md) + 20px);
  border-top: 1px solid var(--color-border-light);
  animation: slideDown 0.15s ease;
}

// 动作分组区域
.action-groups-section {
  margin-bottom: var(--spacing-md);
}

.section-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  margin-bottom: var(--spacing-sm);
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.bo-group-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  margin-bottom: 4px;
  transition: background var(--transition-fast);

  &:hover {
    background: var(--color-bg-spotlight);
  }
}

.bo-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-primary);
  min-width: 60px;
}

.group-toggles {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.group-btn {
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-secondary);
  font-size: var(--font-size-xs);
  cursor: pointer;
  transition: all var(--transition-fast);
  background: var(--color-bg-primary);
  color: var(--color-text-tertiary);
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);

  &:hover {
    border-color: var(--color-primary);
    color: var(--color-primary);
  }

  &.is-active {
    border-color: var(--color-primary);
    background: var(--color-primary-bg);
    color: var(--color-primary);
    font-weight: 500;
  }

  // source 标签
  .group-source-tag {
    font-size: var(--font-size-xxs);
    padding: 0 8px;
    border-radius: var(--radius-full);
    font-weight: 400;
    background: var(--color-bg-secondary);
    color: var(--color-text-secondary);
  }

  &.source-include .group-source-tag {
    background: var(--color-primary-bg);
    color: var(--color-primary);
  }

  &.source-exclude {
    border: 1px dashed var(--color-border);
    background: var(--color-bg-primary);
    color: var(--color-text-quaternary);

    .group-source-tag {
      background: var(--color-error-bg);
      color: var(--color-error);
    }

    .group-btn-label {
      text-decoration: line-through;
      text-decoration-color: var(--color-error);
    }
  }
}

// 详细权限列表
.perm-details {
  margin-bottom: var(--spacing-sm);

  summary {
    font-size: var(--font-size-xs);
    color: var(--color-text-secondary);
    cursor: pointer;
    padding: 4px 0;
    font-weight: 500;

    &:hover {
      color: var(--color-text-primary);
    }
  }
}

.capability-matrix {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: var(--spacing-xs);
}

.cap-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  transition: all var(--transition-fast);
  font-size: 12px;
  cursor: pointer;

  &:hover {
    background: var(--color-bg-spotlight);
  }

  &.cap-granted {
    border-left: 2px solid var(--color-text-quaternary);
  }

  &.cap-excluded {
    background: var(--color-error-bg);
    border-left: 2px solid var(--color-error);
    color: var(--color-text-tertiary);

    .cap-label {
      text-decoration: line-through;
      text-decoration-color: var(--color-error);
    }
  }
}

.cap-check {
  flex-shrink: 0;
  display: flex;
  align-items: center;

  input[type='checkbox'] {
    cursor: pointer;
    accent-color: var(--color-primary);
  }
}

.cap-label {
  font-weight: 500;
  color: var(--color-text-primary);
  min-width: 70px;
}

.cap-code {
  color: var(--color-text-quaternary);
  font-family: monospace;
  font-size: 11px;
  flex: 1;
}

// ==================== 源标签统一样式 ====================
// 用于 .group-source-tag（按钮内）和 .cap-source-tag（详细权限行）
%source-tag-base {
  font-size: var(--font-size-xxs);
  padding: 0 8px;
  border-radius: var(--radius-full);
  font-weight: 400;
  background: var(--color-bg-secondary);
  color: var(--color-text-secondary);

  &.source-include { background: var(--color-primary-bg); color: var(--color-primary); }
  &.source-exclude { background: var(--color-error-bg); color: var(--color-error); }
  &.source-none { background: var(--color-bg-secondary); color: var(--color-text-quaternary); }
}

.group-source-tag {
  @extend %source-tag-base;
}

.cap-source-tag {
  @extend %source-tag-base;
  flex-shrink: 0;
}

.data-scope-inline {
  margin-top: var(--spacing-sm);
}

.scope-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  margin-bottom: var(--spacing-xs);
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.scope-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-xs) var(--spacing-sm);
  background: var(--color-bg-spotlight);
  border-radius: var(--radius-sm);
  margin-bottom: 4px;
}

.scope-type {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-primary);
  background: var(--color-primary-bg);
  padding: 1px 6px;
  border-radius: var(--radius-sm);
}

.scope-detail {
  font-size: 11px;
  color: var(--color-text-tertiary);
  flex: 1;
}

.data-scope-hint {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  margin-top: var(--spacing-sm);
  padding: var(--spacing-xs) var(--spacing-sm);
  background: #fffbe6;
  border-radius: var(--radius-sm);
  font-size: 11px;
  color: var(--color-text-secondary);
}

.hint-icon {
  font-size: 12px;
}

.btn-link {
  @include button-link;
  font-size: 11px;
  padding: 0;

  &.btn-xs {
    font-size: 11px;
    padding: 0;
  }
}

@keyframes slideDown {
  from { opacity: 0; max-height: 0; }
  to { opacity: 1; max-height: 400px; }
}
</style>
