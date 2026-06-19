<template>
  <div v-if="visible" class="drawer-overlay" @click.self="$emit('close')">
    <div class="drawer-panel">
      <div class="drawer-header">
        <h3>{{ role?.name || '角色' }} - 角色详情</h3>
        <button class="close-btn" @click="$emit('close')">&times;</button>
      </div>

      <div class="drawer-content">
        <div class="section basic-info">
          <div class="info-row"><span class="label">角色编码：</span><span>{{ role?.code || '-' }}</span></div>
          <div class="info-row"><span class="label">角色名称：</span><span>{{ role?.name || '-' }}</span></div>
          <div class="info-row"><span class="label">描述：</span><span>{{ role?.description || '无' }}</span></div>
        </div>

        <!-- Tab 导航 -->
        <div class="drawer-tabs">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            class="drawer-tab"
            :class="{ active: activeTab === tab.key }"
            @click="activeTab = tab.key"
          >{{ tab.label }}</button>
        </div>

        <!-- 关联用户组 Tab -->
        <div v-if="activeTab === 'groups'" class="groups-tab">
          <div v-if="loadingGroups" class="loading-state"><span class="spinner"></span>加载用户组...</div>
          <div v-else-if="assignedGroups.length === 0" class="empty-tip">暂无关联用户组</div>
          <div v-else class="group-list">
            <div v-for="group in assignedGroups" :key="group.id" class="group-item">
              <div class="group-info">
                <span class="group-name">{{ group.name }}</span>
                <span class="group-code">{{ group.code }}</span>
              </div>
              <span class="group-member-count" v-if="group.member_count !== undefined">
                {{ group.member_count }} 人
              </span>
            </div>
          </div>
        </div>

        <!-- 权限配置 Tab -->
        <div v-if="activeTab === 'permissions'">
          <div v-if="loadingUnified" class="loading-state"><span class="spinner"></span>加载权限配置...</div>
          <template v-else>
          <!-- 管理维度范围 -->
          <DimensionScopePanel
            :role-id="String(role?.id || '')"
            @dimension-scopes-saved="handleDimensionScopesSaved"
            @auto-derived="handleAutoDerived"
          />

          <div class="unified-perm-section">
            <div class="perm-header">
              <h4>菜单与功能权限</h4>
              <div class="header-summary" v-if="unifiedData.summary">
                <span class="summary-item assigned">{{ unifiedData.summary.assigned_menus }}/{{ unifiedData.summary.total_menus }} 菜单已分配</span>
                <span class="summary-item func-perm" v-if="unifiedData.summary.total_function_permissions > 0">
                  {{ unifiedData.summary.total_function_permissions }} 项功能权限
                </span>
                <span class="summary-item data-scope" v-if="unifiedData.summary.total_data_scopes > 0">{{ unifiedData.summary.total_data_scopes }} 条数据范围</span>
              </div>
            </div>
            
            <p class="perm-guide">
              勾选菜单即授予入口和对应的功能权限（自动同步）。取消菜单不影响已授予权限。
            </p>

            <div class="menu-list">
              <div 
                v-for="menu in unifiedData.menus" 
                :key="menu.menu_code"
                :class="['menu-card', { 'is-assigned': menu.assigned }]"
              >
                <div class="menu-card-header" @click="toggleMenu(menu.menu_code, $event)">
                  <input 
                    type="checkbox" 
                    :checked="menu.assigned"
                    @change="toggleMenu(menu.menu_code, $event.target.checked)"
                    @click.stop
                  />
                  <div class="menu-title-area" @click.stop="toggleMenuExpand(menu.menu_code)">
                    <span class="menu-name">{{ menu.display_name }}</span>
                    <span class="menu-path">{{ menu.menu_path }}</span>
                    <span class="expand-icon" :class="{ expanded: expandedMenus.has(menu.menu_code) }">▸</span>
                  </div>
                  
                  <div class="menu-badges">
                    <span v-if="menu.required_permissions?.length" 
                          :class="['badge', 'badge-capability', { 'badge-all-granted': allCapsGranted(menu) }]">
                      {{ grantedCapCount(menu) }}/{{ menu.required_permissions.length }} 权限
                    </span>
                    <span v-if="menu.has_data_scope" class="badge badge-scope">有数据范围</span>
                  </div>
                </div>

                <div v-if="expandedMenus.has(menu.menu_code)" class="menu-card-body">
                  <div v-if="menu.required_permissions?.length" class="capability-list">
                    <div class="capability-label">
                      <span v-if="menu.assigned"><AppIcon name="key" :size="14" /> 已关联功能权限（随菜单自动授予）</span>
                      <span v-else><AppIcon name="key" :size="14" /> 关联功能权限（勾选菜单后自动授予）</span>
                    </div>
                    <div class="capability-matrix">
                      <div 
                        v-for="rp in menu.required_permissions" 
                        :key="rp.code"
                        :class="['cap-item', {
                          'cap-granted': rp.granted,
                          'cap-pending': !rp.granted && menu.assigned,
                          'cap-inactive': !rp.granted && !menu.assigned
                        }]"
                      >
                        <span class="cap-status">
                          <AppIcon v-if="rp.granted" name="check-circle" :size="12" />
                          <span v-else-if="menu.assigned" class="status-icon status-pending">◌</span>
                          <span v-else class="status-icon status-idle">○</span>
                        </span>
                        <span class="cap-label">{{ rp.label }}</span>
                        <span class="cap-code">{{ rp.code }}</span>
                        <span :class="['cap-source-tag', rp.source === 'auto' ? 'source-auto' : 'source-manual']">
                          {{ rp.granted ? (rp.source === 'auto' ? '自动' : '手动') : '待授予' }}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div v-if="menu.has_data_scope" class="data-scope-inline">
                    <div class="scope-label"><AppIcon name="edit" :size="14" /> 数据约束（此菜单的数据访问范围）：</div>
                    <div v-for="scope in menu.data_scope" :key="scope.resource_type" class="scope-item">
                      <span class="scope-type">{{ scope.resource_type }}</span>
                      <span class="scope-detail">
                        {{ scope.permissions.length }} 条规则
                        ({{ scope.permissions.map(p => p.level).join(', ') }})
                      </span>
                      <button class="btn-link btn-xs" @click="openDataScopeConfig(menu, scope)">配置</button>
                    </div>
                  </div>

                  <div v-else-if="menu.assigned && !menu.has_data_scope && menu.data_permission_hint?.resource_types?.length" class="data-scope-hint">
                    <span class="hint-icon"><AppIcon name="tip" :size="14" /></span>
                    建议为此菜单配置
                    <button class="btn-link btn-xs" @click="openDataScopeForMenu(menu)">数据权限</button>
                  </div>
                </div>
              </div>
            </div>

            <div class="menu-actions-bar">
              <button class="btn btn-ghost" @click="selectAllMenus">全选菜单</button>
              <button class="btn btn-ghost" @click="clearAllMenus">清空</button>
              <div class="actions-spacer"></div>
              <button class="btn btn-primary" @click="saveUnifiedPermissions" :disabled="saving">
                {{ saving ? '保存中...' : '保存全部权限' }}
              </button>
            </div>
          </div>

          <div class="standalone-data-section">
            <h4>条件型权限 <span class="section-desc">(基于条件表达式，新增资源自动继承)</span></h4>
            
            <div style="margin-bottom:var(--spacing-md)">
              <button class="btn btn-ghost" @click="showConditionDialog = true">+ 添加条件规则</button>
            </div>

            <div v-if="conditionRules.length === 0" class="empty-tip">暂无条件型权限规则</div>
            <div v-else class="perm-list">
              <div v-for="rule in conditionRules" :key="rule.id" class="perm-item" :class="{ 'is-denied': rule.is_denied }">
                <div class="perm-main">
                  <span v-if="rule.is_denied" class="denied-badge">禁止</span>
                  <span class="perm-name">{{ rule.resource_type }}</span>
                  <code class="perm-condition">{{ rule.condition }}</code>
                </div>
                <div v-if="rule.friendly_condition" class="perm-friendly">
                  {{ rule.friendly_condition }}
                </div>
                <div class="perm-meta">
                  <span class="perm-level" :class="'level-' + (rule.permission_level || 'read')">{{ getPermLevelLabel(rule.permission_level) }}</span>
                  <span v-if="rule.inherit_to_children" class="inherit-badge">继承</span>
                  <button class="btn-link danger" @click="removeConditionRule(rule)">删除</button>
                </div>
              </div>
            </div>
          </div>
        </template>
        </div>

        <!-- 操作日志 Tab -->
        <div v-if="activeTab === 'logs'" class="logs-tab">
          <AuditLog
            :logs="roleLogs"
            :loading="loadingLogs"
            :total="roleLogsTotal"
            :show-pagination="true"
            :current-page="1"
            :page-size="20"
            :show-filter="true"
            :click-mode="'expand'"
            object-type="role"
            :object-id="role?.id"
            @page-change="setRoleLogsPage"
            @filter-change="setRoleLogsFilters"
            @log-click="handleAuditLogClick"
          />
        </div>
      </div>
    </div>
    <ConfirmDialog
      :visible="confirmState.visible"
      :title="confirmState.title"
      :message="confirmState.message"
      type="danger"
      @confirm="confirmState.onConfirm?.()"
      @cancel="confirmState.visible = false"
      @update:visible="confirmState.visible = $event"
    />

    <ConditionRuleDialog
      v-if="showConditionDialog"
      :roleId="role?.id"
      @close="showConditionDialog = false"
      @saved="onConditionRuleSaved"
    />

    <!-- Audit Log Detail Drawer -->
    <AuditLogDetail
      v-model:visible="auditLogDetailVisible"
      :log="selectedAuditLog"
    />
  </div>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import * as permService from '@/services/permissionService'
import { useMessage } from '@/composables/useMessage'
import { boService } from '@/services/boService'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import ConditionRuleDialog from './ConditionRuleDialog.vue'
import DimensionScopePanel from './components/DimensionScopePanel.vue'
import AppIcon from '@/components/common/AppIcon/AppIcon.vue'
import { AuditLog } from '@/components/common/AuditLog'
import { AuditLogDetail } from '@/components/common/AuditLogDetail'
import { useAuditLogs } from '@/composables/useAuditLogs'

const props = defineProps({
  visible: { type: Boolean, default: false },
  role: { type: Object, default: null }
})
const emit = defineEmits(['close', 'updated'])

const message = useMessage()

const FALLBACK_RESOURCE_TYPES = Object.entries(permService.RESOURCE_LABELS)
  .map(([value, label]) => ({ value, label }))
  .sort((a, b) => a.label.localeCompare(b.label))

const resourceTypes = ref(FALLBACK_RESOURCE_TYPES)

const permissionLevels = [
  { value: 'none', label: '无权限' },
  { value: 'read', label: '只读' },
  { value: 'write', label: '可编辑' },
  { value: 'manage', label: '完全管理' },
]

const LEVEL_LABELS = Object.fromEntries(
  Object.entries(permService.PERMISSION_LEVELS).map(([k, v]) => [k, v.label])
)

const tabs = [
  { key: 'groups', label: '关联用户组' },
  { key: 'permissions', label: '权限配置' },
  { key: 'logs', label: '操作日志' }
]
const activeTab = ref('groups')

const assignedGroups = ref([])
const loadingGroups = ref(false)

const unifiedData = ref({ menus: [], summary: null, role_function_permissions: [] })
const loadingUnified = ref(false)
const saving = ref(false)

const {
  logs: roleLogs,
  total: roleLogsTotal,
  loading: loadingLogs,
  loadLogs: loadRoleLogs,
  setPage: setRoleLogsPage,
  setFilters: setRoleLogsFilters
} = useAuditLogs('role', computed(() => props.role?.id), {
  autoLoad: false,
  // [FIX 2026-06-12] 角色详情"操作日志" tab 同时拉:
  //  - object_type='role' & object_id=role.id (角色自身的 UPDATE 名称/描述等)
  //  - parent_object_type='role' & parent_object_id=role.id (权限配置 5 种 object_type)
  // 后端 audit_api.py get_audit_logs 会用 OR 联合查询两种条件
  parentObjectType: 'role',
  parentObjectId: computed(() => props.role?.id),
})

const auditLogDetailVisible = ref(false)
const selectedAuditLog = ref(null)

function handleAuditLogClick(log) {
  selectedAuditLog.value = log
  auditLogDetailVisible.value = true
}

const dataPermissions = ref([])
const confirmState = ref({ visible: false, title: '', message: '', onConfirm: null })

const conditionRules = ref([])
const showConditionDialog = ref(false)
let searchTimeout = null

const expandedMenus = ref(new Set())

async function loadObjectTypes() {
  try {
    const r = await permService.loadObjectTypes()
    if (r.success && r.data) {
      resourceTypes.value = r.data.map(o => ({ value: o.id, label: o.name }))
        .sort((a, b) => a.label.localeCompare(b.label))
    }
  } catch (e) {}
}

async function loadUnifiedPermissions() {
  if (!props.role) return
  loadingUnified.value = true
  try {
    const r = await permService.loadUnifiedPermissions(props.role.id)
    if (r.success) {
      unifiedData.value = r.data
    } else {
      console.error('[UnifiedPerms] API error:', r)
    }
  } catch (e) {
    console.error('[UnifiedPerms] Fetch error:', e)
  } finally {
    loadingUnified.value = false
  }
}

function grantedCapCount(menu) {
  if (!menu.required_permissions) return 0
  return menu.required_permissions.filter(p => p.granted).length
}

function allCapsGranted(menu) {
  if (!menu.required_permissions?.length) return false
  return menu.required_permissions.every(p => p.granted)
}

async function loadConditionRules() {
  if (!props.role) return
  try {
    const r = await permService.loadConditionRules({ role_id: props.role.id })
    if (r.success) conditionRules.value = r.data || []
  } catch (e) {
    console.error('Failed to load condition rules:', e)
  }
}

async function loadAssignedGroups() {
  if (!props.role) return
  loadingGroups.value = true
  try {
    const result = await boService.queryAssociations('role', props.role.id, 'assigned_groups', { page_size: 999 })
    if (result.success) {
      assignedGroups.value = Array.isArray(result.data) ? result.data : (result.data?.items || [])
    } else {
      assignedGroups.value = []
    }
  } catch (e) {
    console.error('Failed to load assigned groups:', e)
    assignedGroups.value = []
  } finally {
    loadingGroups.value = false
  }
}

async function removeConditionRule(rule) {
  confirmState.value = {
    visible: true, title: '删除条件规则',
    message: `确定删除条件规则 "${rule.condition}" 吗？`,
    onConfirm: async () => {
      try {
        const r = await permService.deleteConditionRule(rule.id)
        if (r.success) {
          await loadConditionRules()
          message.deleted('条件规则')
        } else {
          message.error(r.message || '删除条件规则失败，请稍后重试')
        }
      } catch (e) { message.error('删除条件规则失败，请检查网络后重试', e) }
      confirmState.value.visible = false
    }
  }
}

async function onConditionRuleSaved() {
  showConditionDialog.value = false
  await loadConditionRules()
  message.success('条件规则已添加')
}

function toggleMenu(menuCode, checked, event) {
  const menu = unifiedData.value.menus.find(m => m.menu_code === menuCode)
  if (menu) {
    menu.assigned = !!checked
    if (checked) {
      expandedMenus.value.add(menuCode)
      menu.required_permissions?.forEach(p => {
        p.source = 'auto'
      })
    }
    expandedMenus.value = new Set(expandedMenus.value)
  }
}

function toggleMenuExpand(menuCode) {
  if (expandedMenus.value.has(menuCode)) {
    expandedMenus.value.delete(menuCode)
  } else {
    expandedMenus.value.add(menuCode)
  }
  expandedMenus.value = new Set(expandedMenus.value)
}

function selectAllMenus() {
  unifiedData.value.menus.forEach(m => { 
    m.assigned = true
    m.required_permissions?.forEach(p => { p.source = 'auto' })
  })
}

function clearAllMenus() {
  unifiedData.value.menus.forEach(m => { m.assigned = false })
  expandedMenus.value.clear()
}

async function saveUnifiedPermissions() {
  if (!props.role) return
  saving.value = true
  try {
    const assignedCodes = unifiedData.value.menus.filter(m => m.assigned).map(m => m.menu_code)

    // [FIX v1.0.2] 收集所有显式操作过的功能权限 (source != '')
    //   - source='auto' 来自菜单勾选自动派生, granted=true → 后端 INSERT
    //   - source='auto' 来自菜单勾选自动派生, granted=false → 后端 DELETE
    //   - source='include' 手动包含 → 后端 INSERT
    //   - source='exclude' 手动排除 → 后端 DELETE
    //   - source='' 未分配 → 不传
    // 这是修复"取消勾选 version 权限后保存, DB 没删"的核心逻辑
    const permissions = unifiedData.value.menus
      .flatMap(m => m.required_permissions || [])
      .filter(p => p.source && p.source !== '')
      .map(p => ({ code: p.code, granted: !!p.granted }))

    const r = await permService.saveMenuPermissions(props.role.id, {
      menu_codes: assignedCodes,
      permissions,
    })
    if (r.success) {
      const syncedCount = r.data?.synced_permissions?.length || 0
      const permCount = permissions.length
      const subtitle = permCount > 0
        ? `${assignedCodes.length} 个菜单，已处理 ${permCount} 项功能权限`
        : `${assignedCodes.length} 个菜单，已同步 ${syncedCount} 项功能权限`
      message.detail('权限已保存', subtitle, 'success')
      emit('updated')
      await loadUnifiedPermissions()
    } else {
      message.error(r.message || '保存失败')
    }
  } catch (e) {
    console.error('[saveUnifiedPermissions] error:', e)
    message.error('保存权限失败，请检查网络后重试', e)
  } finally {
    saving.value = false
  }
}

function openDataScopeConfig(menu, scope) {
  message.info(`配置 ${menu.display_name} 的 ${scope.resource_type} 数据范围`)
}

function openDataScopeForMenu(menu) {
  const hintTypes = menu.data_permission_hint?.resource_types || []
  message.info(`为 ${menu.display_name} 配置数据权限：${hintTypes.join(', ')}`)
}

function onResourceTypeChange() {
}

async function loadResources() {
  return
}

function debounceSearchResources() {
}

function isSelected(id) { return false }

function toggleSelection(res) {
}

async function addPermissions() {
  return
}

async function removePermission(perm) {
  return
}

function getResourceName(perm) {
  return ''
}

function getResourceCode(perm) {
  return ''
}

function getPermLevelLabel(level) { return permService.getPermissionLevelLabel(level) }

async function handleDimensionScopesSaved() {
  await loadUnifiedPermissions()
  await loadConditionRules()
  emit('updated')
}

async function handleAutoDerived(result) {
  const menuCount = result.recommended_menus?.length || 0
  const permCount = result.derived_permissions?.length || 0
  message.detail('维度推荐完成', `${menuCount} 个推荐菜单，${permCount} 项功能权限`, 'success')
  await loadUnifiedPermissions()
  await loadConditionRules()
  emit('updated')
}

watch(() => props.visible, (val) => {
  if (val) {
    activeTab.value = 'groups'
    loadObjectTypes()
    loadAssignedGroups()
    loadUnifiedPermissions()
    loadConditionRules()
    loadRoleLogs()
  }
})
</script>

<style scoped lang="scss">
@import '../../styles/mixins.scss';

.drawer-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.4); z-index: 1000; display: flex; justify-content: flex-end; }
.drawer-panel { width: 680px; max-width: 95vw; background: var(--color-bg-container); height: 100vh; overflow-y: auto; box-shadow: var(--shadow-xl); display: flex; flex-direction: column; }
.drawer-header { display: flex; align-items: center; justify-content: space-between; padding: var(--spacing-lg); border-bottom: 1px solid var(--color-border); position: sticky; top: 0; background: var(--color-bg-container); z-index: 2; flex-shrink: 0; }
.drawer-header h3 { margin: 0; font-size: var(--font-size-lg); }
.close-btn { border: none; background: transparent; font-size: 24px; cursor: pointer; color: var(--color-text-quaternary); }
.drawer-content { padding: var(--spacing-lg); flex: 1; }

/* Tab 导航样式 */
.drawer-tabs { display: flex; gap: var(--spacing-md); border-bottom: 1px solid var(--color-border); margin-bottom: var(--spacing-lg); }
.drawer-tab { padding: var(--spacing-sm) var(--spacing-md); background: transparent; border: none; border-bottom: 2px solid transparent; cursor: pointer; font-size: var(--font-size-sm); color: var(--color-text-secondary); transition: all var(--transition-normal); }
.drawer-tab:hover { color: var(--color-text-primary); }
.drawer-tab.active { color: var(--color-primary); border-bottom-color: var(--color-primary); font-weight: var(--font-weight-medium); }

.section { margin-bottom: var(--spacing-xl); }
.section h4 { font-size: var(--font-size-base); color: var(--color-text-primary); margin: 0 0 var(--spacing-md); }
.section-desc { font-size: var(--font-size-xs); color: var(--color-text-quaternary); font-weight: normal; margin-left: var(--spacing-sm); }

.basic-info { background: var(--color-bg-spotlight); border-radius: var(--radius-md); padding: var(--spacing-md); margin-bottom: var(--spacing-lg); }
.info-row { display: flex; gap: var(--spacing-sm); margin-bottom: var(--spacing-xs); font-size: var(--font-size-sm); }
.info-row .label { color: var(--color-text-tertiary); min-width: 70px; }

.loading-state { display: flex; align-items: center; justify-content: center; gap: var(--spacing-sm); padding: calc(var(--spacing-xl) * 2); color: var(--color-text-tertiary); }
.spinner { display: inline-block; width: 20px; height: 20px; border: 2px solid var(--color-border); border-top-color: var(--color-primary); border-radius: 50%; animation: spin 0.8s linear infinite; }

.unified-perm-section { margin-bottom: var(--spacing-xl); margin-top: var(--spacing-xl); }

.perm-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--spacing-sm); flex-wrap: wrap; gap: var(--spacing-sm); }
.perm-header h4 { margin: 0; }
.header-summary { display: flex; gap: var(--spacing-md); flex-wrap: wrap; }
.summary-item { font-size: var(--font-size-xs); padding: 2px 8px; border-radius: var(--radius-sm); white-space: nowrap; }
.summary-item.assigned { background: var(--color-success-bg, #dcfce7); color: var(--color-success, #16a34a); }
.summary-item.func-perm { background: var(--color-warning-bg, #fef3c7); color: var(--color-warning, #f59e0b); font-weight: 500; }
.summary-item.data-scope { background: var(--color-info-bg, #dbeafe); color: var(--el-color-primary, #ea580c); }

.perm-guide { font-size: var(--font-size-xs); color: var(--color-text-tertiary); margin-bottom: var(--spacing-md); padding: var(--spacing-sm) var(--spacing-md); background: var(--color-bg-spotlight); border-radius: var(--radius-sm); border-left: 3px solid var(--color-primary); line-height: 1.5; }

.menu-list { display: flex; flex-direction: column; gap: var(--spacing-sm); }

.menu-card { border: 1px solid var(--color-border-light); border-radius: var(--radius-md); transition: all var(--transition-normal); overflow: hidden; }
.menu-card:hover { border-color: var(--color-border); }
.menu-card.is-assigned { border-left: 3px solid var(--color-primary); background: rgba(234,88,12,0.02); }

.menu-card-header { display: flex; align-items: center; gap: var(--spacing-sm); padding: var(--spacing-sm) var(--spacing-md); cursor: default; }
.menu-card-header input[type='checkbox'] { width: 16px; height: 16px; accent-color: var(--color-primary); cursor: pointer; flex-shrink: 0; }

.menu-title-area { flex: 1; display: flex; align-items: center; gap: var(--spacing-xs); min-width: 0; cursor: pointer; }
.menu-name { font-size: var(--font-size-sm); font-weight: 500; color: var(--color-text-primary); white-space: nowrap; }
.menu-path { font-size: var(--font-size-xs); color: var(--color-text-quaternary); font-family: monospace; opacity: 0.7; }
.expand-icon { font-size: 10px; color: var(--color-text-quaternary); transition: transform var(--transition-fast); flex-shrink: 0; }
.expand-icon.expanded { transform: rotate(90deg); }

.menu-badges { display: flex; gap: var(--spacing-xs); flex-shrink: 0; }
.badge { font-size: 10px; padding: 1px 6px; border-radius: 10px; font-weight: 500; white-space: nowrap; }
.badge-capability { background: var(--color-warning-bg, #fef3c7); color: var(--color-warning, #f59e0b); }
.badge-capability.badge-all-granted { background: var(--color-success-bg, #dcfce7); color: var(--color-success, #16a34a); }
.badge-scope { background: var(--color-info-bg, #dbeafe); color: var(--el-color-primary, #ea580c); }

.menu-card-body { padding: var(--spacing-sm) var(--spacing-md) var(--spacing-md) calc(var(--spacing-md) + 28px); border-top: 1px solid var(--color-border-light); animation: slideDown 0.15s ease; }

.capability-list { margin-bottom: var(--spacing-sm); }
.capability-label { font-size: var(--font-size-xs); color: var(--color-text-secondary); margin-bottom: var(--spacing-sm); font-weight: 500; }

.capability-matrix { display: flex; flex-direction: column; gap: 4px; }

.cap-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  transition: all var(--transition-fast);
  font-size: 12px;
}
.cap-granted {
  background: rgba(22, 163, 74, 0.08);
  border: 1px solid rgba(22, 163, 74, 0.2);
}
.cap-pending {
  background: rgba(245, 158, 11, 0.06);
  border: 1px dashed rgba(245, 158, 11, 0.3);
  animation: pulse-orange 1.5s ease infinite;
}
.cap-inactive {
  background: var(--color-bg-tertiary);
  opacity: 0.6;
}

.cap-status { flex-shrink: 0; width: 18px; text-align: center; }
.status-icon { font-size: 12px; font-weight: bold; }
.status-ok { color: var(--color-success, #16a34a); }
.status-pending { color: var(--color-warning, #f59e0b); }
.status-idle { color: var(--color-border); }

.cap-label { font-weight: 500; color: var(--color-text-primary); min-width: 70px; }
.cap-code { color: var(--color-text-quaternary); font-family: monospace; font-size: 11px; flex: 1; }
.cap-source-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  flex-shrink: 0;
  font-weight: 500;
}
.source-auto { background: var(--color-info-bg, #dbeafe); color: var(--el-color-primary, #ea580c); }
.source-manual { background: var(--color-purple-bg, #ede9fe); color: var(--color-primary-purple, #7c3aed); }
.cap-item .cap-source-tag:not(.source-auto):not(.source-manual) {
  background: var(--color-warning-bg, #fef3c7); color: var(--color-warning-hover, #d97706);
}

@keyframes pulse-orange {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

.data-scope-inline { margin-top: var(--spacing-sm); }
.scope-label { font-size: var(--font-size-xs); color: var(--color-text-secondary); margin-bottom: var(--spacing-xs); }
.scope-item { display: flex; align-items: center; gap: var(--spacing-sm); padding: var(--spacing-xs) var(--spacing-sm); background: var(--color-bg-spotlight); border-radius: var(--radius-sm); margin-bottom: 4px; }
.scope-type { font-size: 11px; font-weight: 600; color: var(--color-primary); background: var(--color-primary-bg); padding: 1px 6px; border-radius: var(--radius-sm); }
.scope-detail { font-size: 11px; color: var(--color-text-tertiary); flex: 1; }

.data-scope-hint { display: flex; align-items: center; gap: var(--spacing-xs); margin-top: var(--spacing-sm); padding: var(--spacing-xs) var(--spacing-sm); background: var(--color-warning-bg, #fef3c7); border-radius: var(--radius-sm); font-size: 11px; color: var(--color-text-secondary); }
.hint-icon { font-size: 12px; }

.menu-actions-bar { display: flex; align-items: center; gap: var(--spacing-sm); margin-top: var(--spacing-md); padding-top: var(--spacing-md); border-top: 1px solid var(--color-border-light); }
.actions-spacer { flex: 1; }

.standalone-data-section { margin-top: var(--spacing-xl); padding-top: var(--spacing-lg); border-top: 2px solid var(--color-border); }

.btn { @include button-secondary; cursor: pointer; &.btn-primary { @include button-primary; } }
.btn-ghost { background: transparent; border: 1px solid var(--color-border-light); color: var(--color-text-secondary); &:hover { border-color: var(--color-border); color: var(--color-text-primary); } }
.btn-link { @include button-link; &.danger { color: var(--color-error, #f5222d); &:hover { text-decoration: underline; } } &.btn-xs { font-size: 11px; padding: 0; } }

.add-perm-form { background: var(--color-bg-spotlight); padding: var(--spacing-md); border-radius: var(--radius-md); margin-bottom: var(--spacing-lg); }
.form-row { display: flex; gap: var(--spacing-md); }
.form-group { flex: 1; margin-bottom: var(--spacing-sm); }
.form-group label { display: block; font-size: var(--font-size-xs); color: var(--color-text-secondary); margin-bottom: var(--spacing-xs); }
.form-group select, .form-group input { width: 100%; padding: var(--spacing-xs) var(--spacing-sm); border: 1px solid var(--color-border); border-radius: var(--radius-sm); font-size: var(--font-size-sm); outline: none; &:focus { border-color: var(--color-primary); box-shadow: 0 0 0 2px rgba(234,88,12,0.1); } }
.selected-count { color: var(--color-primary); font-weight: normal; }
.checkbox-label { display: flex; align-items: center; gap: var(--spacing-xs); cursor: pointer; font-size: var(--font-size-sm); input { width: 14px; height: 14px; accent-color: var(--color-primary); } }

.resource-selector { border: 1px solid var(--color-border); border-radius: var(--radius-sm); overflow: hidden; }
.selector-toolbar { display: flex; gap: var(--spacing-xs); padding: var(--spacing-xs); background: var(--color-bg-container); border-bottom: 1px solid var(--color-border); }
.search-input { flex: 1; padding: 4px 8px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); font-size: var(--font-size-xs); outline: none; &:focus { border-color: var(--color-primary); } }
.btn-clear { padding: 2px 8px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-bg-container); font-size: var(--font-size-xs); cursor: pointer; }
.selector-list { max-height: 180px; overflow-y: auto; }
.empty-state { padding: var(--spacing-md); text-align: center; color: var(--color-text-quaternary); font-size: var(--font-size-xs); }
.resource-item { display: flex; align-items: center; gap: var(--spacing-xs); padding: 6px 10px; cursor: pointer; border-bottom: 1px solid var(--color-border-light); &:hover { background: var(--color-bg-spotlight); } &.selected { background: var(--color-primary-bg); } input { width: 14px; height: 14px; } }
.resource-info { display: flex; flex-direction: column; }
.resource-name { font-size: var(--font-size-xs); color: var(--color-text-primary); }
.resource-code { font-size: 10px; color: var(--color-text-tertiary); }

.perm-list-header { font-size: var(--font-size-xs); color: var(--color-text-tertiary); margin-bottom: var(--spacing-sm); }
.empty-tip { text-align: center; color: var(--color-text-quaternary); padding: var(--spacing-lg); font-size: var(--font-size-sm); }

.groups-tab { padding-top: var(--spacing-sm); }
.group-list { display: flex; flex-direction: column; gap: var(--spacing-sm); }
.group-item { display: flex; align-items: center; justify-content: space-between; padding: var(--spacing-sm) var(--spacing-md); background: var(--color-bg-spotlight); border-radius: var(--radius-md); border: 1px solid var(--color-border-light); }
.group-info { display: flex; flex-direction: column; gap: 2px; }
.group-name { font-size: var(--font-size-sm); color: var(--color-text-primary); font-weight: var(--font-weight-medium); }
.group-code { font-size: var(--font-size-xs); color: var(--color-text-tertiary); font-family: monospace; }
.group-member-count { font-size: var(--font-size-xs); color: var(--color-text-quaternary); background: var(--color-bg-layout); padding: 2px 8px; border-radius: var(--radius-sm); }

.perm-list { display: flex; flex-direction: column; gap: var(--spacing-sm); }
.perm-item { display: flex; flex-direction: column; gap: 4px; padding: var(--spacing-sm); background: var(--color-bg-spotlight); border-radius: var(--radius-md); }
.perm-main { display: flex; align-items: baseline; gap: var(--spacing-xs); }
.perm-name { font-size: var(--font-size-sm); color: var(--color-text-primary); font-weight: var(--font-weight-medium); }
.perm-code { font-size: var(--font-size-xs); color: var(--color-text-tertiary); font-family: monospace; }
.perm-meta { display: flex; align-items: center; justify-content: space-between; }
.perm-level { font-size: var(--font-size-xs); padding: 2px 6px; border-radius: var(--radius-sm); font-weight: var(--font-weight-medium); }
.level-none { background: var(--color-bg-tertiary); color: var(--color-text-tertiary); }
.level-read { background: var(--color-info-bg, #dbeafe); color: var(--el-color-primary, #ea580c); }
.level-write { background: var(--color-warning-bg, #fef3c7); color: var(--color-warning, #f59e0b); }
.level-manage, .level-admin { background: var(--color-danger-bg, #fee2e2); color: var(--color-danger, #dc2626); }

.perm-item.is-denied { border-left: 3px solid var(--color-error); }
.denied-badge { display: inline-block; padding: 1px 6px; border-radius: var(--radius-sm); background: var(--color-error-bg, #fff1f0); color: var(--color-error); font-size: 10px; font-weight: var(--font-weight-medium); margin-right: var(--spacing-xs); }
.perm-condition { font-size: var(--font-size-xs); color: var(--color-text-tertiary); font-family: monospace; background: var(--color-bg-layout); padding: 2px 6px; border-radius: var(--radius-sm); }
.perm-friendly { font-size: var(--font-size-xs); color: var(--color-text-secondary); margin-top: 4px; padding-left: 4px; }
.inherit-badge { font-size: 10px; padding: 1px 6px; border-radius: var(--radius-sm); background: var(--color-success-bg, #dcfce7); color: var(--color-success, #16a34a); margin-left: var(--spacing-xs); }

@keyframes spin { to { transform: rotate(360deg); } }
@keyframes slideDown { from { opacity: 0; max-height: 0; } to { opacity: 1; max-height: 400px; } }
</style>