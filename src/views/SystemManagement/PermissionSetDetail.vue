<template>
  <div class="role-detail">
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
        :sections="sections"
        :form-data="roleData"
        :auto-load-meta="true"
        :loading="loading"
        :actions="detailActions"
        :editing="isEditing"
        :saving="isSaving"
        :object-type="'role'"
        :object-id="roleId"
        size="lg"
        @update:editing="isEditing = $event"
        @save="handleSave"
        @cancel="handleCancel"
        @apply-defaults="handleApplyDefaults"
      >
      </ObjectPage>
    </PageShell>

    <div v-if="!roleId" class="rd-empty">
      <AppIcon name="warning" size="32" />
      <div class="rd-empty__title">缺少参数</div>
      <div class="rd-empty__desc">角色ID无效</div>
      <AppButton variant="primary" size="sm" @click="handleBack">返回</AppButton>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTabStore } from '@/stores/tabStore'
import { boService } from '@/services/boService'
import { metaService } from '@/services/metaService'
import { useMessage } from '@/composables/useMessage'
import { PageShell } from '@/components/common/PageShell'
import { ObjectPage } from '@/components/common/ObjectPage'
import { AppButton, AppIcon } from '@/components/common'
const route = useRoute()
const router = useRouter()
const tabStore = useTabStore()
const message = useMessage()

const roleId = computed(() => {
  const id = route.params.id || route.params.roleId
  return id ? String(id) : null
})

const role = ref(null)
const loading = ref(false)
const isEditing = ref(false)
const isSaving = ref(false)

const pageTitle = computed(() =>
  isNewMode.value ? '新建角色' : (role.value?.name || '角色详情')
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

const roleData = computed(() => role.value || {})

const detailActions = [
  { id: 'edit', label: '编辑', icon: 'edit', type: 'primary' },
  { id: 'save', label: '保存', icon: 'check', type: 'primary' },
  { id: 'cancel', label: '取消', icon: 'close', type: 'default' }
]

const sections = [
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
        title: '状态与属性',
        icon: 'toggle',
        layout: 'grid-2',
        fields: ['is_active', 'is_system']
      },
      {
        title: '统计信息',
        icon: 'chart',
        layout: 'grid-2',
        collapsed: true,
        fields: ['user_count', 'permission_count']
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
    key: 'audit-log',
    label: '操作日志',
    icon: 'history',
    type: 'history'
    // [FIX 2026-06-12] 父对象查询: ObjectPageContent 会自动检测 role/user/user_group
    // 等 SELF_REFERRING_PARENT_OBJECT_TYPES, 自动给 HistorySection 传
    // parentObjectType='role' + parentObjectId=objectId (即 role.id).
    // 这里不需要手动指定.
  }
]

async function loadRole() {
  if (!roleId.value) return

  loading.value = true
  try {
    const result = await boService.read('role', roleId.value)

    if (result.success) {
      role.value = result.data
      updateTabLabel()
    } else {
      message.error(result.message || '加载失败')
    }
  } catch (error) {
    console.error('Failed to load role:', error)
    message.error('加载失败')
  } finally {
    loading.value = false
  }
}

function updateTabLabel() {
  const tab = tabStore.tabs.find(t => t.id === route.path)
  if (tab && role.value) {
    tabStore.updateTabLabel(tab.id, `角色: ${role.value.name || role.value.code}`)
  }
}

function handlePermissionsSaved() {
  // 权限保存后不调用 loadRole()，避免 ObjectPage 重新渲染导致 tab 跳回
}

const isNewMode = computed(() => {
  return !roleId.value || roleId.value === 'new'
})

async function initNewRole() {
  try {
    const result = await metaService.getUIConfig('role')
    if (result.success && result.data?.fields) {
      const defaults = {}
      for (const f of result.data.fields) {
        if (f.default !== undefined && f.default !== null) {
          defaults[f.id] = f.default
        }
      }
      role.value = { ...defaults }
    } else {
      role.value = { is_active: 1 }
    }
  } catch {
    role.value = { is_active: 1 }
  }
  isEditing.value = true
}

function handleApplyDefaults(defaults) {
  if (!role.value) {
    role.value = { ...defaults }
  } else {
    for (const [key, value] of Object.entries(defaults)) {
      if (role.value[key] === undefined) {
        role.value[key] = value
      }
    }
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
    message.error('保存角色失败：' + (error?.message || '请检查输入后重试'), error)
  } finally {
    isSaving.value = false
  }
}

function handleCancel() {
  isEditing.value = false
  loadRole()
}

function handleNavigate(crumb) {
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

onMounted(() => {
  if (isNewMode.value) {
    initNewRole()
  } else {
    loadRole()
  }
})

watch(() => route.params.id || route.params.roleId, (newId, oldId) => {
  if (newId !== oldId) {
    if (!newId || newId === 'new') {
      initNewRole()
    } else {
      loadRole()
    }
  }
})
</script>

<style scoped lang="scss">
.role-detail {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: var(--color-bg-page);
}

.rd-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-sm);
  padding: 60px var(--spacing-lg);
  color: var(--color-text-secondary);

  &__title {
    font-size: 15px;
    font-weight: 600;
    color: var(--color-text-primary);
  }

  &__desc {
    font-size: 13px;
    color: var(--color-text-tertiary);
  }
}
</style>
