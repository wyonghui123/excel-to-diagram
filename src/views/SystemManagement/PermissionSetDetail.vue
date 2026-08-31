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
        :sections="sections"
        :form-data="permissionSetData"
        :auto-load-meta="true"
        :loading="loading"
        :actions="detailActions"
        :editing="isEditing"
        :saving="isSaving"
        :object-type="'permission_set'"
        :object-id="permissionSetId"
        size="lg"
        @update:editing="isEditing = $event"
        @save="handleSave"
        @cancel="handleCancel"
        @apply-defaults="handleApplyDefaults"
      >
      </ObjectPage>
    </PageShell>

    <div v-if="!permissionSetId" class="psd-empty">
      <AppIcon name="warning" size="32" />
      <div class="psd-empty__title">缺少参数</div>
      <div class="psd-empty__desc">权限集ID无效</div>
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
// [P4-新4b 2026-08-29] Spec 16: 统一变量名为 permissionSetId，roleId 仅作 alias 保持路由 param 兼容
const permissionSetId = computed(() => roleId.value)

const permissionSet = ref(null)
const loading = ref(false)
const isEditing = ref(false)
const isSaving = ref(false)

const pageTitle = computed(() =>
  isNewMode.value ? '新建权限集' : (permissionSet.value?.name || '权限集详情')
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

const permissionSetData = computed(() => permissionSet.value || {})

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

async function loadPermissionSet() {
  if (!permissionSetId.value) return

  loading.value = true
  try {
    const result = await boService.read('permission_set', permissionSetId.value)

    if (result.success) {
      permissionSet.value = result.data
      updateTabLabel()
    } else {
      message.error(result.message || '加载失败')
    }
  } catch (error) {
    console.error('Failed to load permission set:', error)
    message.error('加载失败')
  } finally {
    loading.value = false
  }
}

function updateTabLabel() {
  const tab = tabStore.tabs.find(t => t.id === route.path)
  if (tab && permissionSet.value) {
    tabStore.updateTabLabel(tab.id, `权限集: ${permissionSet.value.name || permissionSet.value.code}`)
  }
}

function handlePermissionsSaved() {
  // 权限保存后不调用 loadRole()，避免 ObjectPage 重新渲染导致 tab 跳回
}

const isNewMode = computed(() => {
  return !permissionSetId.value || permissionSetId.value === 'new'
})

async function initNewPermissionSet() {
  try {
    const result = await metaService.getUIConfig('permission_set')
    if (result.success && result.data?.fields) {
      const defaults = {}
      for (const f of result.data.fields) {
        if (f.default !== undefined && f.default !== null) {
          defaults[f.id] = f.default
        }
      }
      permissionSet.value = { ...defaults }
    } else {
      permissionSet.value = { is_active: 1 }
    }
  } catch {
    permissionSet.value = { is_active: 1 }
  }
  isEditing.value = true
}

function handleApplyDefaults(defaults) {
  if (!permissionSet.value) {
    permissionSet.value = { ...defaults }
  } else {
    for (const [key, value] of Object.entries(defaults)) {
      if (permissionSet.value[key] === undefined) {
        permissionSet.value[key] = value
      }
    }
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
      message.success(isNewMode.value ? '创建成功' : '保存成功')
      isEditing.value = false
      if (isNewMode.value && result.data?.id) {
        // [P4-新4b 2026-08-29] Fix: 旧代码引用不存在的 RolePermissionDetail 路由。
        // 跳转到 PermissionSetDetailContent (有完整权限联动)。
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
    message.error('保存权限集失败：' + (error?.message || '请检查输入后重试'), error)
  } finally {
    isSaving.value = false
  }
}

function handleCancel() {
  isEditing.value = false
  loadPermissionSet()
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
      router.push({ path: '/user-permission', query: { tab: 'permission_sets' } })
    }
  }
}

onMounted(() => {
  if (isNewMode.value) {
    initNewPermissionSet()
  } else {
    loadPermissionSet()
  }
})

watch(() => route.params.id || route.params.roleId, (newId, oldId) => {
  if (newId !== oldId) {
    if (!newId || newId === 'new') {
      initNewPermissionSet()
    } else {
      loadPermissionSet()
    }
  }
})
</script>

<style scoped lang="scss">
.permission-set-detail {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: var(--color-bg-page);
}

.psd-empty {
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
    font-size: 14px;
    color: var(--color-text-tertiary);
  }
}
</style>
