<template>
  <div class="role-permission-detail">
    <PageShell
      :title="pageTitle"
      :subtitle="role?.code || ''"
      :breadcrumbs="breadcrumbs"
      :show-back-button="true"
      @back="handleBack"
      @navigate="handleNavigate"
    >
      <ObjectPage
        :title="pageTitle"
        :subtitle="role?.code || ''"
        :status="roleStatus"
        :status-type="roleStatusType"
        :show-back-button="false"
        :sections="permissionSections"
        :form-data="roleData"
        :field-definitions="fieldDefs"
        :loading="loading"
        :actions="detailActions"
        :editing="isEditing"
        :saving="isSaving"
        :object-type="'role'"
        :object-id="roleId"
        size="lg"
        @tab-change="handleTabChange"
        @update:editing="isEditing = $event"
        @save="handleSave"
        @cancel="handleCancel"
      >
        <!-- Custom Slot: 权限配置面板 -->
        <template #section-permissions>
          <PermissionConfigPanel
            :role-id="roleId"
            :role="role"
            @saved="handlePermissionSaved"
            @reset="handlePermissionReset"
          />
        </template>

        <!-- Custom Slot: 关联用户组 -->
        <template #section-assigned_groups>
          <div style="padding: 16px;">
            <p v-if="loadingGroups">加载用户组...</p>
            <p v-else-if="assignedGroups.length === 0">暂无关联用户组</p>
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

const route = useRoute()
const router = useRouter()
const tabStore = useTabStore()
const message = useMessage()

const roleId = computed(() => route.params.roleId as string)

const role = ref<any>(null)
const loading = ref(false)
const isEditing = ref(false)
const isSaving = ref(false)

const isNewMode = computed(() => {
  return !roleId.value || roleId.value === 'new'
})

const assignedGroups = ref<any[]>([])
const loadingGroups = ref(false)

const pageTitle = computed(() =>
  `角色权限配置：${role.value?.name || '加载中...'}`
)

const roleStatus = computed(() =>
  role.value?.is_active ? '启用中' : '已停用'
)

const roleStatusType = computed(() =>
  role.value?.is_active ? 'success' : 'default'
)

const breadcrumbs = computed(() => [
  { label: '系统管理', to: '/system' },
  { label: '用户与权限', to: '/user-permission' },
  { label: '角色管理', to: '/user-permission?tab=roles' },
  { label: pageTitle.value }
])

const fieldDefs = computed(() => ({
  name: { label: '角色名称', type: 'text' },
  code: { label: '角色编码', type: 'text' },
  description: { label: '描述', type: 'textarea' },
  is_active: { label: '状态', type: 'switch' }
}))

const roleData = computed(() => role.value || {})

const detailActions = [
  { id: 'edit', label: '编辑', icon: 'edit', type: 'primary' },
  { id: 'save', label: '保存', icon: 'check', type: 'primary' },
  { id: 'cancel', label: '取消', icon: 'close', type: 'default' }
]

const permissionSections = [
  {
    key: 'basic',
    label: '基本信息',
    icon: 'info',
    type: 'standard',
    fieldGroups: [
      {
        title: '角色标识',
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
    label: '用户组',
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

async function loadRole() {
  if (!roleId.value) return

  loading.value = true
  try {
    const result = await boService.read('role', roleId.value)

    if (result.success) {
      role.value = result.data
    }
  } catch (error) {
    console.error('Failed to load role:', error)
  } finally {
    loading.value = false
  }

  loadAssignedGroups()
}

async function loadAssignedGroups() {
  if (!roleId.value) return
  loadingGroups.value = true
  try {
    const result = await boService.queryAssociations('role', roleId.value, 'assigned_groups', { page_size: 999 })
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
  if (!role.value) return

  isSaving.value = true
  try {
    const saveData = {
      name: role.value.name,
      description: role.value.description,
      is_active: role.value.is_active
    }

    let result
    if (isNewMode.value) {
      result = await boService.create('role', saveData)
    } else {
      result = await boService.update('role', roleId.value, saveData)
    }

    if (result.success) {
      message.success(isNewMode.value ? '创建成功' : '保存成功')
      isEditing.value = false
      if (isNewMode.value && result.data?.id) {
        const newRoute = router.resolve({
          name: 'RolePermissionDetail',
          params: { roleId: result.data.id }
        })
        tabStore.replaceTabId(route.path, newRoute.path, newRoute.fullPath)
        router.replace({
          name: 'RolePermissionDetail',
          params: { roleId: result.data.id }
        })
      } else {
        await loadRole()
      }
    } else {
      message.error(result.message || '保存失败')
    }
  } catch (error) {
    console.error('Failed to save role:', error)
    message.error('保存权限失败：' + (error?.message || '请稍后重试'), error)
  } finally {
    isSaving.value = false
  }
}

function handleCancel() {
  loadRole()
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
    const activeTab = remaining.find(t => t.id === tabStore.activeTabId)
    if (activeTab?.path) {
      router.push(activeTab.path)
    } else {
      router.push({ path: '/user-permission', query: { tab: 'roles' } })
    }
  }
}

function handleTabChange(tabKey: string) {
  // ObjectPage handles audit-log loading internally
}

function handlePermissionSaved() {
  loadRole()
}

function handlePermissionReset() {
  loadRole()
}

onMounted(() => {
  loadRole()
})
</script>

<style scoped lang="scss">
.role-permission-detail {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: var(--color-bg-page);
}
</style>
