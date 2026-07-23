<template>
  <div class="permission-config-panel">
    <!-- 管理维度范围（维度驱动配置入口） -->
    <DimensionScopePanel
      :role-id="roleId"
      @dimension-scopes-saved="handleDimensionScopesSaved"
      @auto-derived="handleAutoDerived"
    />

    <!-- 菜单与功能权限 -->
    <section class="perm-section">
      <div class="perm-header">
        <h4>
          <AppIcon name="menu" :size="14" />
          菜单与功能权限
        </h4>
        <div class="header-summary">
          <span class="summary-item assigned">
            {{ assignedMenuCount }}/{{ totalMenuCount }} 菜单已分配
          </span>
          <span class="summary-item func-perm">
            {{ totalFuncPermissions }} 项功能权限
          </span>
        </div>
      </div>

      <p class="perm-guide">
        勾选菜单即授予入口和对应的功能权限（自动同步）。取消菜单不影响已授予权限。
      </p>

      <!-- 菜单权限矩阵组件 -->
      <MenuPermissionMatrix
        v-model="menus"
        :loading="menusLoading"
        @change="handleMenuPermissionChange"
        @configure-scope="handleConfigureScope"
        @configure-data-scope="handleConfigureDataScope"
        @toggle-action-group="handleToggleActionGroup"
        @toggle-standalone="handleToggleStandalone"
      />

      <div class="perm-actions-bar">
        <button class="btn btn-ghost" @click="selectAllMenus">全选菜单</button>
        <button class="btn btn-ghost" @click="clearAllMenus">清空</button>
        <div class="actions-spacer"></div>
        <button
          class="btn btn-primary"
          @click="savePermissions"
          :disabled="saving"
        >
          {{ saving ? '保存中...' : '保存全部权限' }}
        </button>
      </div>
    </section>

    <!-- 条件型权限 -->
    <section class="perm-section condition-section">
      <h4>
        <AppIcon name="filter" :size="14" />
        条件型权限
      </h4>
      <p class="section-desc">(基于条件表达式，新增资源自动继承)</p>

      <button class="btn btn-ghost" @click="showAddConditionDialog = true">
        + 添加条件规则
      </button>

      <!-- 条件规则列表组件 -->
      <ConditionRuleList
        v-model="conditionRules"
        :loading="rulesLoading"
        @delete="handleDeleteConditionRule"
        @edit="handleEditConditionRule"
      />
    </section>

    <!-- [P6-T3 2026-07-20] 禁止规则 (Panel 5, Spec §3.10 / §8.6) -->
    <!-- Deny 优先: rule_type='prohibition' + is_denied=1, Layer 0 短路 -->
    <section class="perm-section prohibition-section">
      <h4>
        <AppIcon name="ban" :size="14" />
        禁止规则
      </h4>
      <p class="section-desc">
        (Deny 优先：命中即拒绝，优先于所有 Allow 规则，包括 * 通配符)
      </p>

      <button class="btn btn-ghost" @click="showAddProhibitionDialog = true">
        + 添加禁止规则
      </button>

      <div v-if="prohibitionRulesLoading" class="prohibition-loading">
        加载中...
      </div>
      <div v-else-if="prohibitionRules.length === 0" class="prohibition-empty">
        暂无禁止规则
      </div>
      <ul v-else class="prohibition-list">
        <li
          v-for="rule in prohibitionRules"
          :key="rule.id"
          class="prohibition-item"
        >
          <div class="prohibition-info">
            <span class="prohibition-resource">{{ rule.resource_type || '*' }}</span>
            <span class="prohibition-level">{{ rule.permission_level || 'all' }}</span>
            <code v-if="rule.condition" class="prohibition-cond">{{ rule.condition }}</code>
          </div>
          <button
            class="btn btn-danger btn-sm"
            @click="handleDeleteProhibitionRule(rule)"
            :disabled="prohibitionSaving"
          >
            删除
          </button>
        </li>
      </ul>

      <!-- 添加禁止规则的内联表单 -->
      <div v-if="showAddProhibitionDialog" class="prohibition-form">
        <h5>新增禁止规则</h5>
        <div class="form-row">
          <label>资源类型</label>
          <input
            v-model="newProhibitionRule.resource_type"
            placeholder="如 product / version / * (全部)"
            class="form-input"
          />
        </div>
        <div class="form-row">
          <label>权限级别</label>
          <select v-model="newProhibitionRule.permission_level" class="form-input">
            <option value="read">read</option>
            <option value="write">write</option>
            <option value="delete">delete</option>
            <option value="*">all (*)</option>
          </select>
        </div>
        <div class="form-row">
          <label>条件 (可选)</label>
          <input
            v-model="newProhibitionRule.condition"
            placeholder="如 status = 'archived'"
            class="form-input"
          />
        </div>
        <div class="form-actions">
          <button
            class="btn btn-primary btn-sm"
            @click="handleSaveProhibitionRule"
            :disabled="prohibitionSaving"
          >
            {{ prohibitionSaving ? '保存中...' : '保存' }}
          </button>
          <button class="btn btn-ghost btn-sm" @click="cancelAddProhibition">
            取消
          </button>
        </div>
      </div>
    </section>

    <!-- [P11-T3 2026-07-20] Owner 规则 (Panel 4, Spec §4.11.2 / §8.11) -->
    <!-- rule_type='owner' - 资源所有者自动获得 admin 权限 -->
    <section class="perm-section owner-section">
      <h4>
        <AppIcon name="user" :size="14" />
        Owner 规则
      </h4>
      <p class="section-desc">
        (资源所有者自动获得权限; condition 如 owner_id = ${user.id})
      </p>

      <button class="btn btn-ghost" @click="showAddOwnerDialog = true">
        + 添加 Owner 规则
      </button>

      <div v-if="ownerRulesLoading" class="owner-loading">
        加载中...
      </div>
      <div v-else-if="ownerRules.length === 0" class="owner-empty">
        暂无 Owner 规则
      </div>
      <ul v-else class="owner-list">
        <li
          v-for="rule in ownerRules"
          :key="rule.id"
          class="owner-item"
        >
          <div class="owner-info">
            <span class="owner-resource">{{ rule.resource_type || '*' }}</span>
            <span class="owner-level">{{ rule.permission_level || 'admin' }}</span>
            <code v-if="rule.condition" class="owner-cond">{{ rule.condition }}</code>
          </div>
          <button
            class="btn btn-danger btn-sm"
            @click="handleDeleteOwnerRule(rule)"
            :disabled="ownerSaving"
          >
            删除
          </button>
        </li>
      </ul>

      <!-- 添加 Owner 规则的内联表单 -->
      <div v-if="showAddOwnerDialog" class="owner-form">
        <h5>新增 Owner 规则</h5>
        <div class="form-row">
          <label>资源类型</label>
          <input
            v-model="newOwnerRule.resource_type"
            placeholder="如 product / version / * (全部)"
            class="form-input"
          />
        </div>
        <div class="form-row">
          <label>权限级别</label>
          <select v-model="newOwnerRule.permission_level" class="form-input">
            <option value="read">read</option>
            <option value="write">write</option>
            <option value="admin">admin</option>
          </select>
        </div>
        <div class="form-row">
          <label>条件</label>
          <input
            v-model="newOwnerRule.condition"
            placeholder="如 owner_id = ${user.id}"
            class="form-input"
          />
        </div>
        <div class="form-actions">
          <button
            class="btn btn-primary btn-sm"
            @click="handleSaveOwnerRule"
            :disabled="ownerSaving"
          >
            {{ ownerSaving ? '保存中...' : '保存' }}
          </button>
          <button class="btn btn-ghost btn-sm" @click="cancelAddOwner">
            取消
          </button>
        </div>
      </div>
    </section>

    <!-- [P11-T5 2026-07-20] Visibility 规则 (Panel 6, Spec §8.11) -->
    <!-- rule_type='visibility' - 5 种级别: public/private/department_only/role_only/hidden -->
    <section class="perm-section visibility-section">
      <h4>
        <AppIcon name="eye" :size="14" />
        Visibility 规则
      </h4>
      <p class="section-desc">
        (5 种级别: public / private / department_only / role_only / hidden)
      </p>

      <button class="btn btn-ghost" @click="showAddVisibilityDialog = true">
        + 添加 Visibility 规则
      </button>

      <div v-if="visibilityRulesLoading" class="visibility-loading">
        加载中...
      </div>
      <div v-else-if="visibilityRules.length === 0" class="visibility-empty">
        暂无 Visibility 规则
      </div>
      <ul v-else class="visibility-list">
        <li
          v-for="rule in visibilityRules"
          :key="rule.id"
          class="visibility-item"
        >
          <div class="visibility-info">
            <span class="visibility-resource">{{ rule.resource_type || '*' }}</span>
            <span class="visibility-level">{{ rule.permission_level }}</span>
            <code v-if="rule.condition" class="visibility-cond">{{ rule.condition }}</code>
          </div>
          <button
            class="btn btn-danger btn-sm"
            @click="handleDeleteVisibilityRule(rule)"
            :disabled="visibilitySaving"
          >
            删除
          </button>
        </li>
      </ul>

      <!-- 添加 Visibility 规则的内联表单 -->
      <div v-if="showAddVisibilityDialog" class="visibility-form">
        <h5>新增 Visibility 规则</h5>
        <div class="form-row">
          <label>资源类型</label>
          <input
            v-model="newVisibilityRule.resource_type"
            placeholder="如 product / version / * (全部)"
            class="form-input"
          />
        </div>
        <div class="form-row">
          <label>可见性级别</label>
          <select v-model="newVisibilityRule.permission_level" class="form-input">
            <option value="public">public (所有人可见)</option>
            <option value="department_only">department_only (仅本部门)</option>
            <option value="role_only">role_only (仅本角色)</option>
            <option value="private">private (仅本人)</option>
            <option value="hidden">hidden (隐藏)</option>
          </select>
        </div>
        <div class="form-row">
          <label>条件 (可选)</label>
          <input
            v-model="newVisibilityRule.condition"
            placeholder="如 status = 'published'"
            class="form-input"
          />
        </div>
        <div class="form-actions">
          <button
            class="btn btn-primary btn-sm"
            @click="handleSaveVisibilityRule"
            :disabled="visibilitySaving"
          >
            {{ visibilitySaving ? '保存中...' : '保存' }}
          </button>
          <button class="btn btn-ghost btn-sm" @click="cancelAddVisibility">
            取消
          </button>
        </div>
      </div>
    </section>

    <!-- [P11-T6 2026-07-20] * 通配符二次确认对话框 (Spec §4.11.3 / §8.11) -->
    <div v-if="showWildcardConfirm" class="wildcard-confirm-overlay">
      <div class="wildcard-confirm-dialog">
        <h5>
          <AppIcon name="warning" :size="16" />
          安全确认: * 通配符配置
        </h5>
        <p class="wildcard-warning">
          您正在为资源类型 <code>{{ pendingWildcardResource }}</code> 配置权限。
          <br />
          <strong>*</strong> 表示所有资源, 这是一个高风险操作, 可能导致权限过度放开。
        </p>
        <label class="wildcard-checkbox">
          <input
            v-model="wildcardAcknowledged"
            type="checkbox"
          />
          我理解 * 通配符的安全风险, 确认继续
        </label>
        <div class="form-actions">
          <button
            class="btn btn-primary btn-sm"
            @click="confirmWildcardSave"
            :disabled="!wildcardAcknowledged"
          >
            确认保存
          </button>
          <button class="btn btn-ghost btn-sm" @click="cancelWildcardSave">
            取消
          </button>
        </div>
      </div>
    </div>

    <!-- 条件规则对话框 -->
    <ConditionRuleDialog
      v-if="showAddConditionDialog"
      :role-id="roleId"
      :rule="editingRule"
      @close="handleConditionDialogClose"
      @saved="handleConditionRuleSaved"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, toRef } from 'vue'
import { AppIcon } from '@/components/common/AppIcon'
import MenuPermissionMatrix from './MenuPermissionMatrix.vue'
import ConditionRuleList from './ConditionRuleList.vue'
import ConditionRuleDialog from '../ConditionRuleDialog.vue'
import DimensionScopePanel from './DimensionScopePanel.vue'
import { useMenuPermission } from '../composables/useMenuPermission'
import { useConditionRules } from '../composables/useConditionRules'
import { useMessage } from '@/composables/useMessage'
// [P6-T3 2026-07-20] 直接复用 permissionService 加载/保存 prohibition 规则
import * as permService from '@/services/permissionService'

// [FIX v1.0.4] 改用项目统一消息系统 (useMessage + NotificationContainer)
//   - 旧实现用 ElMessage, 与 RoleDetailDrawer 的 useMessage 不一致
//   - Element Plus ElMessage 在 role 详情页内部被 high-z modal 遮挡时
//     通知 fixed 定位失效, 看不见
//   - NotificationContainer 是 z-index: 1700, teleport to body, 永远在最上层
const message = useMessage()

const props = defineProps<{
  roleId: string
  role: any
}>()

const {
  menus,
  loading: menusLoading,
  loadMenus,
  selectAll,
  clearAll,
  applyDerived,
  toggleActionGroup,
  toggleStandaloneAction,
  save: saveMenuPermissions
} = useMenuPermission(toRef(props, 'roleId'))

const {
  rules: conditionRules,
  loading: rulesLoading,
  loadRules,
  deleteRule
} = useConditionRules(toRef(props, 'roleId'))

const saving = ref(false)
const showAddConditionDialog = ref(false)
const editingRule = ref(null)

// [P6-T3 2026-07-20] 禁止规则状态 (Spec §3.10 / §8.6)
// rule_type='prohibition' + is_denied=1, Layer 0 短路
const prohibitionRules = ref<any[]>([])
const prohibitionRulesLoading = ref(false)
const prohibitionSaving = ref(false)
const showAddProhibitionDialog = ref(false)
const newProhibitionRule = ref({
  resource_type: '',
  permission_level: 'read',
  condition: ''
})

// [P11-T3 2026-07-20] Owner 规则状态 (Panel 4, Spec §4.11.2 / §8.11)
// rule_type='owner' - 资源所有者自动获得权限
const ownerRules = ref<any[]>([])
const ownerRulesLoading = ref(false)
const ownerSaving = ref(false)
const showAddOwnerDialog = ref(false)
const newOwnerRule = ref({
  resource_type: '',
  permission_level: 'admin',
  condition: 'owner_id = ${user.id}'
})

// [P11-T5 2026-07-20] Visibility 规则状态 (Panel 6, Spec §8.11)
// rule_type='visibility' - 5 种级别: public/private/department_only/role_only/hidden
const visibilityRules = ref<any[]>([])
const visibilityRulesLoading = ref(false)
const visibilitySaving = ref(false)
const showAddVisibilityDialog = ref(false)
const newVisibilityRule = ref({
  resource_type: '',
  permission_level: 'public',
  condition: ''
})

// [P11-T6 2026-07-20] * 通配符二次确认状态 (Spec §4.11.3 / §8.11)
// 任何 rule_type 的 resource_type='*' 时弹出二次确认
const showWildcardConfirm = ref(false)
const wildcardAcknowledged = ref(false)
const pendingWildcardResource = ref('')
const pendingWildcardSaveFn = ref<(() => Promise<void>) | null>(null)

const totalMenuCount = computed(() => menus.value.length)
const assignedMenuCount = computed(() => 
  menus.value.filter(m => m.assigned).length
)
const totalFuncPermissions = computed(() => 
  menus.value.reduce((sum, m) => sum + (m.required_permissions?.length || 0), 0)
)

function handleMenuPermissionChange() {
  // 菜单权限变化时的处理
}

function handleToggleActionGroup(menu: any, boId: string, groupKey: string) {
  toggleActionGroup(menu, boId, groupKey as 'view' | 'edit' | 'manage')
}

function handleToggleStandalone(menu: any, boId: string, action: string) {
  toggleStandaloneAction(menu, boId, action)
}

function handleConfigureScope(menu: any, scope: any) {
  message.info(`配置 ${menu.display_name} 的 ${scope.resource_type} 数据范围`)
}

function handleConfigureDataScope(menu: any) {
  const hintTypes = menu.data_permission_hint?.resource_types || []
  message.info(`为 ${menu.display_name} 配置数据权限：${hintTypes.join(', ')}`)
}

function handleDimensionScopesSaved() {
  // DimensionScopePanel internally handles role reload after saving
}

async function handleAutoDerived(result: any) {
  const recommendedMenus = result?.recommended_menus || []
  const derivedPerms = result?.derived_permissions || []

  applyDerived(recommendedMenus, derivedPerms)
  await loadRules()
  // [FIX v1.0.2] 自动派生后, 直接落库, 不让用户再点保存
  // 避免 "推荐了 version:read 但 DB 没写入" 的认知错位
  try {
    await saveMenuPermissions()
  } catch (e) {
    console.error('auto-save after derive failed:', e)
  }
  // 不显示消息，由 RoleDetailDrawer 统一显示
}

function selectAllMenus() {
  selectAll()
}

function clearAllMenus() {
  clearAll()
}

async function savePermissions() {
  saving.value = true
  try {
    await saveMenuPermissions()
    message.saved('权限设置')
  } catch (error) {
    message.error('保存权限设置失败：' + (error?.message || '请稍后重试'), error)
  } finally {
    saving.value = false
  }
}

async function handleDeleteConditionRule(rule: any) {
  try {
    await deleteRule(rule.id)
    message.deleted('条件规则')
  } catch (error) {
    message.error('删除条件规则失败：' + (error?.message || '请稍后重试'), error)
  }
}

function handleEditConditionRule(rule: any) {
  editingRule.value = rule
  showAddConditionDialog.value = true
}

function handleConditionDialogClose() {
  showAddConditionDialog.value = false
  editingRule.value = null
}

async function handleConditionRuleSaved() {
  await loadRules()
  handleConditionDialogClose()
}

// ============================================================================
// [P6-T3 2026-07-20] 禁止规则 (Prohibition) — Spec §3.10 / §8.6
// ============================================================================

async function loadProhibitionRules() {
  if (!props.roleId) return
  if (!/^\d+$/.test(String(props.roleId))) {
    prohibitionRules.value = []
    return
  }
  prohibitionRulesLoading.value = true
  try {
    // 复用 condition rules API, 通过 rule_type='prohibition' 过滤
    const r = await permService.loadConditionRules({
      role_id: props.roleId,
      rule_type: 'prohibition'
    })
    if (r.success) {
      prohibitionRules.value = (r.data || []).filter(
        (rule: any) => rule.is_denied === true || rule.is_denied === 1
      )
    } else {
      throw new Error(r.message || '加载禁止规则失败')
    }
  } catch (error) {
    console.error('[PermissionConfigPanel] loadProhibitionRules error:', error)
    prohibitionRules.value = []
  } finally {
    prohibitionRulesLoading.value = false
  }
}

async function handleSaveProhibitionRule() {
  if (!props.roleId) return
  if (!/^\d+$/.test(String(props.roleId))) {
    message.error('保存失败: 角色尚未保存, 请先保存角色')
    return
  }
  // [P11-T6] resource_type='*' 需二次确认
  if (newProhibitionRule.value.resource_type === '*') {
    pendingWildcardResource.value = '*'
    pendingWildcardSaveFn.value = doSaveProhibitionRule
    showWildcardConfirm.value = true
    wildcardAcknowledged.value = false
    return
  }
  await doSaveProhibitionRule()
}

async function doSaveProhibitionRule() {
  prohibitionSaving.value = true
  try {
    const rule = {
      role_id: props.roleId,
      rule_type: 'prohibition',
      resource_type: newProhibitionRule.value.resource_type || null,
      permission_level: newProhibitionRule.value.permission_level,
      condition: newProhibitionRule.value.condition || null,
      is_denied: 1  // Prohibition 规则强制 is_denied=1
    }
    const r = await permService.saveConditionRule(rule)
    if (!r.success) {
      throw new Error(r.message || '保存禁止规则失败')
    }
    message.saved('禁止规则')
    cancelAddProhibition()
    await loadProhibitionRules()
  } catch (error: any) {
    message.error('保存禁止规则失败: ' + (error?.message || '请稍后重试'), error)
  } finally {
    prohibitionSaving.value = false
  }
}

async function handleDeleteProhibitionRule(rule: any) {
  if (!rule?.id) return
  prohibitionSaving.value = true
  try {
    const r = await permService.deleteConditionRule(rule.id)
    if (!r.success) {
      throw new Error(r.message || '删除禁止规则失败')
    }
    message.deleted('禁止规则')
    await loadProhibitionRules()
  } catch (error: any) {
    message.error('删除禁止规则失败: ' + (error?.message || '请稍后重试'), error)
  } finally {
    prohibitionSaving.value = false
  }
}

function cancelAddProhibition() {
  showAddProhibitionDialog.value = false
  newProhibitionRule.value = {
    resource_type: '',
    permission_level: 'read',
    condition: ''
  }
}

// ============================================================================
// [P11-T3 2026-07-20] Owner 规则 (Panel 4) — Spec §4.11.2 / §8.11
// ============================================================================

async function loadOwnerRules() {
  if (!props.roleId) return
  if (!/^\d+$/.test(String(props.roleId))) {
    ownerRules.value = []
    return
  }
  ownerRulesLoading.value = true
  try {
    const r = await permService.loadConditionRules({
      role_id: props.roleId,
      rule_type: 'owner'
    })
    if (r.success) {
      ownerRules.value = r.data || []
    } else {
      throw new Error(r.message || '加载 Owner 规则失败')
    }
  } catch (error) {
    console.error('[PermissionConfigPanel] loadOwnerRules error:', error)
    ownerRules.value = []
  } finally {
    ownerRulesLoading.value = false
  }
}

async function handleSaveOwnerRule() {
  if (!props.roleId) return
  if (!/^\d+$/.test(String(props.roleId))) {
    message.error('保存失败: 角色尚未保存, 请先保存角色')
    return
  }
  // [P11-T6] resource_type='*' 需二次确认
  if (newOwnerRule.value.resource_type === '*') {
    pendingWildcardResource.value = '*'
    pendingWildcardSaveFn.value = doSaveOwnerRule
    showWildcardConfirm.value = true
    wildcardAcknowledged.value = false
    return
  }
  await doSaveOwnerRule()
}

async function doSaveOwnerRule() {
  ownerSaving.value = true
  try {
    const rule = {
      role_id: props.roleId,
      rule_type: 'owner',
      resource_type: newOwnerRule.value.resource_type || null,
      permission_level: newOwnerRule.value.permission_level,
      condition: newOwnerRule.value.condition || null,
      is_denied: 0
    }
    const r = await permService.saveConditionRule(rule)
    if (!r.success) {
      throw new Error(r.message || '保存 Owner 规则失败')
    }
    message.saved('Owner 规则')
    cancelAddOwner()
    await loadOwnerRules()
  } catch (error: any) {
    message.error('保存 Owner 规则失败: ' + (error?.message || '请稍后重试'), error)
  } finally {
    ownerSaving.value = false
  }
}

async function handleDeleteOwnerRule(rule: any) {
  if (!rule?.id) return
  ownerSaving.value = true
  try {
    const r = await permService.deleteConditionRule(rule.id)
    if (!r.success) {
      throw new Error(r.message || '删除 Owner 规则失败')
    }
    message.deleted('Owner 规则')
    await loadOwnerRules()
  } catch (error: any) {
    message.error('删除 Owner 规则失败: ' + (error?.message || '请稍后重试'), error)
  } finally {
    ownerSaving.value = false
  }
}

function cancelAddOwner() {
  showAddOwnerDialog.value = false
  newOwnerRule.value = {
    resource_type: '',
    permission_level: 'admin',
    condition: 'owner_id = ${user.id}'
  }
}

// ============================================================================
// [P11-T5 2026-07-20] Visibility 规则 (Panel 6) — Spec §8.11
// ============================================================================

async function loadVisibilityRules() {
  if (!props.roleId) return
  if (!/^\d+$/.test(String(props.roleId))) {
    visibilityRules.value = []
    return
  }
  visibilityRulesLoading.value = true
  try {
    const r = await permService.loadConditionRules({
      role_id: props.roleId,
      rule_type: 'visibility'
    })
    if (r.success) {
      visibilityRules.value = r.data || []
    } else {
      throw new Error(r.message || '加载 Visibility 规则失败')
    }
  } catch (error) {
    console.error('[PermissionConfigPanel] loadVisibilityRules error:', error)
    visibilityRules.value = []
  } finally {
    visibilityRulesLoading.value = false
  }
}

async function handleSaveVisibilityRule() {
  if (!props.roleId) return
  if (!/^\d+$/.test(String(props.roleId))) {
    message.error('保存失败: 角色尚未保存, 请先保存角色')
    return
  }
  // [P11-T6] resource_type='*' 需二次确认
  if (newVisibilityRule.value.resource_type === '*') {
    pendingWildcardResource.value = '*'
    pendingWildcardSaveFn.value = doSaveVisibilityRule
    showWildcardConfirm.value = true
    wildcardAcknowledged.value = false
    return
  }
  await doSaveVisibilityRule()
}

async function doSaveVisibilityRule() {
  visibilitySaving.value = true
  try {
    const rule = {
      role_id: props.roleId,
      rule_type: 'visibility',
      resource_type: newVisibilityRule.value.resource_type || null,
      permission_level: newVisibilityRule.value.permission_level,
      condition: newVisibilityRule.value.condition || null,
      is_denied: 0
    }
    const r = await permService.saveConditionRule(rule)
    if (!r.success) {
      throw new Error(r.message || '保存 Visibility 规则失败')
    }
    message.saved('Visibility 规则')
    cancelAddVisibility()
    await loadVisibilityRules()
  } catch (error: any) {
    message.error('保存 Visibility 规则失败: ' + (error?.message || '请稍后重试'), error)
  } finally {
    visibilitySaving.value = false
  }
}

async function handleDeleteVisibilityRule(rule: any) {
  if (!rule?.id) return
  visibilitySaving.value = true
  try {
    const r = await permService.deleteConditionRule(rule.id)
    if (!r.success) {
      throw new Error(r.message || '删除 Visibility 规则失败')
    }
    message.deleted('Visibility 规则')
    await loadVisibilityRules()
  } catch (error: any) {
    message.error('删除 Visibility 规则失败: ' + (error?.message || '请稍后重试'), error)
  } finally {
    visibilitySaving.value = false
  }
}

function cancelAddVisibility() {
  showAddVisibilityDialog.value = false
  newVisibilityRule.value = {
    resource_type: '',
    permission_level: 'public',
    condition: ''
  }
}

// ============================================================================
// [P11-T6 2026-07-20] * 通配符二次确认 (Spec §4.11.3 / §8.11)
// ============================================================================

async function confirmWildcardSave() {
  if (!wildcardAcknowledged.value) return
  showWildcardConfirm.value = false
  const fn = pendingWildcardSaveFn.value
  pendingWildcardSaveFn.value = null
  pendingWildcardResource.value = ''
  if (fn) {
    await fn()
  }
}

function cancelWildcardSave() {
  showWildcardConfirm.value = false
  wildcardAcknowledged.value = false
  pendingWildcardSaveFn.value = null
  pendingWildcardResource.value = ''
}

async function initPermissions() {
  if (!props.roleId) return
  try {
    await loadMenus()
    await loadRules()
    await loadProhibitionRules()  // [P6-T3] 加载禁止规则
    await loadOwnerRules()         // [P11-T3] 加载 Owner 规则
    await loadVisibilityRules()    // [P11-T5] 加载 Visibility 规则
  } catch (e) {
    console.error('[PermissionConfigPanel] initPermissions error:', e)
  }
}

onMounted(() => {
  initPermissions()
})
</script>

<style scoped lang="scss">
@import '../../../styles/mixins.scss';

.permission-config-panel {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xl);
}

.perm-section {
  background: var(--color-bg-container);
  border-radius: var(--radius-md);
  padding: var(--spacing-lg);
  border: 1px solid var(--color-border-light);
}

.perm-section h4 {
  margin: 0 0 var(--spacing-md);
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.perm-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-sm);
  flex-wrap: wrap;
  gap: var(--spacing-sm);
}

.header-summary {
  display: flex;
  gap: var(--spacing-md);
  flex-wrap: wrap;
}

.summary-item {
  font-size: var(--font-size-xs);
  padding: 2px 8px;
  border-radius: var(--radius-sm);

  &.assigned {
    background: var(--color-success-bg);
    color: var(--color-success);
  }

  &.func-perm {
    background: rgba(250, 140, 22, 0.1);
    color: #fa8c16;
  }
}

.perm-guide {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-bottom: var(--spacing-md);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-spotlight);
  border-radius: var(--radius-sm);
  border-left: 3px solid var(--yonyou-orange-600, #ea580c);
  line-height: 1.5;
}

.perm-actions-bar {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-md);
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--color-border-light);
}

.actions-spacer {
  flex: 1;
}

.condition-section {
  h4 {
    margin-bottom: var(--spacing-sm);
  }

  .section-desc {
    font-size: var(--font-size-xs);
    color: var(--color-text-quaternary);
    font-weight: normal;
    margin-left: var(--spacing-sm);
    margin-bottom: var(--spacing-md);
  }
}

.btn {
  cursor: pointer;
  padding: var(--spacing-xs) var(--spacing-md);
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-light);
  background: transparent;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  transition: all var(--transition-fast);

  &:hover {
    border-color: var(--color-border);
    color: var(--color-text-primary);
  }

  &.btn-primary {
    background: var(--yonyou-orange-600, #ea580c);
    color: white;
    border-color: var(--yonyou-orange-600, #ea580c);

    &:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }
  }

  /* [P6-T3 2026-07-20] 禁止规则 Panel 用 danger 样式 */
  &.btn-danger {
    background: var(--color-error-bg, #fff1f0);
    color: var(--color-error, #ff4d4f);
    border-color: var(--color-error, #ff4d4f);

    &:hover {
      background: var(--color-error, #ff4d4f);
      color: white;
    }

    &:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }
  }

  &.btn-sm {
    padding: 2px var(--spacing-sm);
    font-size: var(--font-size-xs);
  }
}

/* [P6-T3 2026-07-20] 禁止规则 (Prohibition) 面板样式 */
.prohibition-section {
  h4 {
    margin-bottom: var(--spacing-sm);
  }

  .section-desc {
    font-size: var(--font-size-xs);
    color: var(--color-error, #ff4d4f);
    font-weight: normal;
    margin-left: var(--spacing-sm);
    margin-bottom: var(--spacing-md);
  }
}

.prohibition-loading,
.prohibition-empty {
  padding: var(--spacing-md);
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
}

.prohibition-list {
  list-style: none;
  padding: 0;
  margin: var(--spacing-md) 0;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.prohibition-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-error-bg, #fff1f0);
  border-left: 3px solid var(--color-error, #ff4d4f);
  border-radius: var(--radius-sm);
}

.prohibition-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--font-size-sm);
  flex: 1;
  flex-wrap: wrap;
}

.prohibition-resource {
  font-weight: 500;
  color: var(--color-text-primary);
}

.prohibition-level {
  padding: 2px 6px;
  background: var(--color-error, #ff4d4f);
  color: white;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
}

.prohibition-cond {
  font-family: monospace;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  background: var(--color-bg-spotlight);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
}

.prohibition-form {
  margin-top: var(--spacing-md);
  padding: var(--spacing-md);
  background: var(--color-bg-spotlight);
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-light);

  h5 {
    margin: 0 0 var(--spacing-md);
    font-size: var(--font-size-sm);
    color: var(--color-text-primary);
  }

  .form-row {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);
    margin-bottom: var(--spacing-sm);

    label {
      min-width: 80px;
      font-size: var(--font-size-sm);
      color: var(--color-text-secondary);
    }

    .form-input {
      flex: 1;
      padding: var(--spacing-xs) var(--spacing-sm);
      border: 1px solid var(--color-border-light);
      border-radius: var(--radius-sm);
      font-size: var(--font-size-sm);

      &:focus {
        outline: none;
        border-color: var(--yonyou-orange-600, #ea580c);
      }
    }
  }

  .form-actions {
    display: flex;
    gap: var(--spacing-sm);
    margin-top: var(--spacing-md);
  }
}

/* [P11-T3 2026-07-20] Owner 规则面板样式 (Panel 4) */
.owner-section {
  h4 {
    margin-bottom: var(--spacing-sm);
  }

  .section-desc {
    font-size: var(--font-size-xs);
    color: var(--color-text-quaternary);
    font-weight: normal;
    margin-left: var(--spacing-sm);
    margin-bottom: var(--spacing-md);
  }
}

.owner-loading,
.owner-empty {
  padding: var(--spacing-md);
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
}

.owner-list {
  list-style: none;
  padding: 0;
  margin: var(--spacing-md) 0;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.owner-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-success-bg, #f6ffed);
  border-left: 3px solid var(--color-success, #52c41a);
  border-radius: var(--radius-sm);
}

.owner-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--font-size-sm);
  flex: 1;
  flex-wrap: wrap;
}

.owner-resource {
  font-weight: 500;
  color: var(--color-text-primary);
}

.owner-level {
  padding: 2px 6px;
  background: var(--color-success, #52c41a);
  color: white;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
}

.owner-cond {
  font-family: monospace;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  background: var(--color-bg-spotlight);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
}

.owner-form {
  margin-top: var(--spacing-md);
  padding: var(--spacing-md);
  background: var(--color-bg-spotlight);
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-light);

  h5 {
    margin: 0 0 var(--spacing-md);
    font-size: var(--font-size-sm);
    color: var(--color-text-primary);
  }

  .form-row {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);
    margin-bottom: var(--spacing-sm);

    label {
      min-width: 80px;
      font-size: var(--font-size-sm);
      color: var(--color-text-secondary);
    }

    .form-input {
      flex: 1;
      padding: var(--spacing-xs) var(--spacing-sm);
      border: 1px solid var(--color-border-light);
      border-radius: var(--radius-sm);
      font-size: var(--font-size-sm);

      &:focus {
        outline: none;
        border-color: var(--yonyou-orange-600, #ea580c);
      }
    }
  }

  .form-actions {
    display: flex;
    gap: var(--spacing-sm);
    margin-top: var(--spacing-md);
  }
}

/* [P11-T5 2026-07-20] Visibility 规则面板样式 (Panel 6) */
.visibility-section {
  h4 {
    margin-bottom: var(--spacing-sm);
  }

  .section-desc {
    font-size: var(--font-size-xs);
    color: var(--color-text-quaternary);
    font-weight: normal;
    margin-left: var(--spacing-sm);
    margin-bottom: var(--spacing-md);
  }
}

.visibility-loading,
.visibility-empty {
  padding: var(--spacing-md);
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
}

.visibility-list {
  list-style: none;
  padding: 0;
  margin: var(--spacing-md) 0;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.visibility-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-spotlight, #fafafa);
  border-left: 3px solid var(--yonyou-orange-600, #ea580c);
  border-radius: var(--radius-sm);
}

.visibility-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--font-size-sm);
  flex: 1;
  flex-wrap: wrap;
}

.visibility-resource {
  font-weight: 500;
  color: var(--color-text-primary);
}

.visibility-level {
  padding: 2px 6px;
  background: var(--yonyou-orange-600, #ea580c);
  color: white;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
}

.visibility-cond {
  font-family: monospace;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  background: var(--color-bg-container);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
}

.visibility-form {
  margin-top: var(--spacing-md);
  padding: var(--spacing-md);
  background: var(--color-bg-spotlight);
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-light);

  h5 {
    margin: 0 0 var(--spacing-md);
    font-size: var(--font-size-sm);
    color: var(--color-text-primary);
  }

  .form-row {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);
    margin-bottom: var(--spacing-sm);

    label {
      min-width: 80px;
      font-size: var(--font-size-sm);
      color: var(--color-text-secondary);
    }

    .form-input {
      flex: 1;
      padding: var(--spacing-xs) var(--spacing-sm);
      border: 1px solid var(--color-border-light);
      border-radius: var(--radius-sm);
      font-size: var(--font-size-sm);

      &:focus {
        outline: none;
        border-color: var(--yonyou-orange-600, #ea580c);
      }
    }
  }

  .form-actions {
    display: flex;
    gap: var(--spacing-sm);
    margin-top: var(--spacing-md);
  }
}

/* [P11-T6 2026-07-20] * 通配符二次确认对话框样式 */
.wildcard-confirm-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.45);
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
}

.wildcard-confirm-dialog {
  background: var(--color-bg-container, #fff);
  border-radius: var(--radius-md, 6px);
  padding: var(--spacing-lg, 16px);
  width: 480px;
  max-width: 90vw;
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.15);

  h5 {
    margin: 0 0 var(--spacing-md, 12px);
    font-size: var(--font-size-base, 14px);
    color: var(--color-error, #ff4d4f);
    display: flex;
    align-items: center;
    gap: var(--spacing-xs, 4px);
  }

  .wildcard-warning {
    font-size: var(--font-size-sm, 13px);
    color: var(--color-text-primary, #333);
    line-height: 1.6;
    margin: 0 0 var(--spacing-md, 12px);

    code {
      background: var(--color-bg-spotlight, #fafafa);
      padding: 2px 6px;
      border-radius: var(--radius-sm, 3px);
      font-family: monospace;
    }

    strong {
      color: var(--color-error, #ff4d4f);
    }
  }

  .wildcard-checkbox {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm, 8px);
    font-size: var(--font-size-sm, 13px);
    color: var(--color-text-primary, #333);
    margin: 0 0 var(--spacing-md, 12px);
    cursor: pointer;

    input[type='checkbox'] {
      cursor: pointer;
    }
  }

  .form-actions {
    display: flex;
    gap: var(--spacing-sm, 8px);
    justify-content: flex-end;
  }
}

</style>
