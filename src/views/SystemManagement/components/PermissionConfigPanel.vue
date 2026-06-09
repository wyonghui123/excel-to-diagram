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
    message.success('权限保存成功')
  } catch (error) {
    message.error('权限保存失败')
  } finally {
    saving.value = false
  }
}

async function handleDeleteConditionRule(rule: any) {
  try {
    await deleteRule(rule.id)
    message.success('条件规则删除成功')
  } catch (error) {
    message.error('条件规则删除失败')
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

async function initPermissions() {
  if (!props.roleId) return
  try {
    await loadMenus()
    await loadRules()
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
}
</style>
