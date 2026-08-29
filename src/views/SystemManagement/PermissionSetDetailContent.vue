<template>
  <div class="permission-set-detail">
    <PageShell
      :title="pageTitle"
      :subtitle="permissionSet?.code || ''"
      :breadcrumbs="breadcrumbs"
      :show-back-button="true"
      @back="handleBack"
      @navigate="handleNavigate"
    >
      <ObjectPage
        :title="pageTitle"
        :subtitle="permissionSet?.code || ''"
        :status="permissionSetStatus"
        :status-type="permissionSetStatusType"
        :show-back-button="false"
        :sections="permissionSections"
        :form-data="permissionSetData"
        :field-definitions="fieldDefs"
        :loading="loading"
        :actions="detailActions"
        :editing="isEditing"
        :saving="isSaving"
        :object-type="'permission_set'"
        :object-id="permissionSetId"
        size="lg"
        @tab-change="handleTabChange"
        @action="handleDetailAction"
        @update:editing="isEditing = $event"
        @save="handleSave"
        @cancel="handleCancel"
      >
        <!-- Custom Slot: 权限配置面板 -->
        <template #section-permissions>
          <!-- [v40 2026-08-27] 一体化编辑：editing 由 ObjectPage 统一下发；
               保存通过 ref.save() 在顶层「保存」动作中一并提交 -->
          <PermissionConfigPanel
            ref="permPanelRef"
            :permission-set-id="permissionSetId"
            :permission-set="permissionSet"
            :editing="isEditing"
            @saved="handlePermissionSaved"
            @reset="handlePermissionReset"
          />
        </template>

        <!-- Custom Slot: 关联组织 -->
        <template #section-assigned_groups>
          <div style="padding: 16px;">
            <p v-if="loadingGroups">加载组织...</p>
            <p v-else-if="assignedGroups.length === 0">暂无关联组织</p>
            <div v-else>
              <div v-for="group in assignedGroups" :key="group.id" style="padding:8px 12px;margin-bottom:4px;border:1px solid var(--color-border-light);border-radius:var(--radius-md);display:flex;align-items:center;justify-content:space-between">
                <div>
                  <span style="font-size:14px;font-weight:500">{{ group.name }}</span>
                  <span style="font-size:12px;color:var(--color-text-tertiary);margin-left:8px;font-family:monospace">{{ group.code }}</span>
                </div>
                <span v-if="group.member_count !== undefined" style="font-size:12px;color:var(--color-text-quaternary)">{{ group.member_count }} 人</span>
              </div>
            </div>
          </div>
        </template>
      </ObjectPage>

      <!-- [v70 2026-08-28] 权限体检弹窗：体检是权限集 object 的 validation action，
           入口在 ObjectPage 头部标准 action 区（原 PermissionConfigPanel 底部按钮已移除） -->
      <PermissionAuditDialog
        v-if="showAuditDialog"
        :permission-set-id="permissionSetId"
        @close="showAuditDialog = false"
      />
    </PageShell>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTabStore } from '@/stores/tabStore'
import { boService } from '@/services/boService'
import { useMessage } from '@/composables/useMessage'
import { PageShell } from '@/components/common/PageShell'
import { ObjectPage } from '@/components/common/ObjectPage'
import PermissionConfigPanel from './components/PermissionConfigPanel.vue'
import PermissionAuditDialog from './components/PermissionAuditDialog.vue'

const route = useRoute()
const router = useRouter()
const tabStore = useTabStore()
const message = useMessage()

const roleId = computed(() => route.params.roleId as string)
// [v70 2026-08-29 P4-新4a] Spec 16: 统一变量名为 permissionSetId，roleId 仅作 alias 保持外部路由 param 名兼容
const permissionSetId = computed(() => roleId.value)

const permissionSet = ref<any>(null)
const loading = ref(false)
const isEditing = ref(false)
const isSaving = ref(false)
/** [v40 2026-08-27] 权限面板引用：顶层「保存」时联动提交权限 */
const permPanelRef = ref<any>(null)

const isNewMode = computed(() => {
  return !permissionSetId.value || permissionSetId.value === 'new'
})

const assignedGroups = ref<any[]>([])
const loadingGroups = ref(false)

const pageTitle = computed(() =>
  `权限集详情：${permissionSet.value?.name || '加载中...'}`
)

const permissionSetStatus = computed(() =>
  permissionSet.value?.is_active ? '启用中' : '已停用'
)

const permissionSetStatusType = computed(() =>
  permissionSet.value?.is_active ? 'success' : 'default'
)

const breadcrumbs = computed(() => [
  { label: '系统管理', to: '/system' },
  { label: '用户与权限', to: '/user-permission' },
  { label: '权限集管理', to: '/user-permission?tab=permission_sets' },
  { label: pageTitle.value }
])

const fieldDefs = computed(() => ({
  name: { label: '权限集名称', type: 'text' },
  code: { label: '权限集编码', type: 'text' },
  description: { label: '描述', type: 'textarea' },
  is_active: { label: '状态', type: 'switch' }
}))

const permissionSetData = computed(() => permissionSet.value || {})

// [v70 2026-08-28] 权限体检是权限集 object 的 validation action，放入标准 action 区。
//   浏览态可见（编辑中数据未落库，体检结果会误导）；新建模式无 permissionSetId，不显示。
const detailActions = computed(() => {
  const actions = [
    { id: 'edit', label: '编辑', icon: 'edit', type: 'primary' },
    { id: 'save', label: '保存', icon: 'check', type: 'primary' },
    { id: 'cancel', label: '取消', icon: 'close', type: 'default' }
  ]
  if (!isNewMode.value) {
    // [v71 2026-08-28] primary 变体：与 编辑/删除 填充风格保持一致
    actions.push({ id: 'audit', label: '权限体检', icon: 'search', type: 'primary' })
  }
  return actions
})

const showAuditDialog = ref(false)

function handleDetailAction(payload: any) {
  const key = payload?.action?.key
  if (key === 'audit') {
    showAuditDialog.value = true
  }
}

const permissionSections = [
  {
    key: 'basic',
    label: '基本信息',
    icon: 'info',
    type: 'standard',
    fieldGroups: [
      {
        title: '权限集标识',
        icon: 'tag',
        layout: 'grid-2',
        fields: ['name', 'code']
      },
      {
        title: '描述信息',
        icon: 'file-text',
        layout: 'grid-1',
        fields: ['description']
      },
      {
        title: '状态',
        icon: 'toggle',
        layout: 'grid-1',
        fields: ['is_active']
      }
    ]
  },
  {
    key: 'permissions',
    label: '权限配置',
    icon: 'lock',
    type: 'custom'
  },
  {
    key: 'assigned_groups',
    label: '已分配组织',
    icon: 'users',
    type: 'custom'
  },
  {
    key: 'audit-log',
    label: '操作日志',
    icon: 'history',
    type: 'history'
  }
]

async function loadPermissionSet() {
  if (!permissionSetId.value) return

  loading.value = true
  try {
    const result = await boService.read('permission_set', permissionSetId.value)

    if (result.success) {
      permissionSet.value = result.data
    }
  } catch (error) {
    console.error('Failed to load permission set:', error)
  } finally {
    loading.value = false
  }

  loadAssignedGroups()
}

async function loadAssignedGroups() {
  if (!permissionSetId.value) return
  loadingGroups.value = true
  try {
    const result = await boService.queryAssociations('permission_set', permissionSetId.value, 'assigned_orgs', { page_size: 999 })
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

async function handleSave() {
  if (!permissionSet.value) return

  isSaving.value = true
  try {
    const saveData = {
      name: permissionSet.value.name,
      description: permissionSet.value.description,
      is_active: permissionSet.value.is_active
    }

    let result
    if (isNewMode.value) {
      result = await boService.create('permission_set', saveData)
    } else {
      result = await boService.update('permission_set', permissionSetId.value, saveData)
    }

    if (result.success) {
      // [v59 2026-08-27] 时序修复：必须「先保存权限 → 再退出编辑态」。
      //   此前 isEditing=false 先执行，PermissionConfigPanel 的 watch(isEditing)
      //   退出分支会立即 menus.value=editSnapshot 恢复快照 + 清空 matrixChanges/范围快照，
      //   随后的 panel.save() 存的全是编辑前的旧状态 → 菜单勾选/矩阵/范围全部"保存无效"。
      if (!isNewMode.value && permPanelRef.value?.save) {
        try {
          await permPanelRef.value.save()
        } catch (permError) {
          // 保存失败 → 保持编辑态让用户修正重试（权限集元数据已落库，不回滚）
          message.error('权限集已保存，但权限设置保存失败，请在权限配置区检查后重试', permError)
          return
        }
      }
      message.success(isNewMode.value ? '创建成功' : '保存成功')
      isEditing.value = false
      if (isNewMode.value && result.data?.id) {
        // [P4-新4a 2026-08-29] Fix: 旧代码引用不存在的 RolePermissionDetail 路由。
        // 路由表里只有 PermissionSetDetailContent，跳转自身带新 id。
        const newPath = `/system/permission-set-detail/${result.data.id}`
        tabStore.replaceTabId(route.path, newPath, newPath)
        router.replace({ path: newPath })
      } else {
        await loadPermissionSet()
      }
    } else {
      message.error(result.message || '保存失败')
    }
  } catch (error) {
    console.error('Failed to save permission set:', error)
    message.error('保存权限失败：' + (error?.message || '请稍后重试'), error)
  } finally {
    isSaving.value = false
  }
}

function handleCancel() {
  loadPermissionSet()
}

function handleNavigate(crumb: any) {
  if (crumb.to) {
    router.push(crumb.to)
  }
}

function handleBack() {
  const tabId = route.path
  tabStore.closeTab(tabId)

  const remaining = tabStore.tabs
  if (remaining.length === 0) {
    router.push('/')
  } else {
    const activeTab = tabStore.tabs.find(t => t.id === tabStore.activeTabId)
    if (activeTab?.path) {
      router.push(activeTab.path)
    } else {
      router.push({ path: '/user-permission', query: { tab: 'permission_sets' } })
    }
  }
}

function handleTabChange(tabKey: string) {
  // ObjectPage handles audit-log loading internally
}

function handlePermissionSaved() {
  loadPermissionSet()
}

onMounted(() => {
  loadPermissionSet()
})
</script>

<style scoped lang="scss">
.permission-set-detail {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: var(--color-bg-page);
}
</style>
