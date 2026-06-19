<template>
  <div class="object-detail-page" tabindex="-1" ref="pageRef">
    <div class="object-detail-page__content">
      <div class="odp-title-bar">
        <div class="odp-title-bar__left">
          <button class="odp-back-link" @click="handleClose">
            <AppIcon name="arrow-left" size="sm" />
            <span>返回</span>
          </button>
          <span class="odp-title-bar__sep"></span>
          <span class="odp-title-bar__title">{{ displayTitle }}</span>
        </div>
        <div class="odp-title-bar__right">
          <AppButton
            v-for="act in (detailPageRef?.visibleActions || [])"
            :key="act.key"
            :variant="act.variant || 'secondary'"
            size="sm"
            @click="detailPageRef?.handleObjectPageAction({ action: act })"
          >
            {{ act.label }}
          </AppButton>
          <StateTransitionButtons
            v-if="objectType && id && id !== 'new'"
            :object-type="objectType"
            :object-id="id"
            size="small"
            @success="handleStateTransitionSuccess"
          />
        </div>
      </div>

      <!--
        [FIX 2026-06-18] v-if 用 detailPageEverMounted 标记，避免 app 顶部 tab 切走时 unmount
          原因：原本 v-if="objectType && (id || mode === 'add')" 会在 route 变化
          (objectType 变 undefined) 时 unmount DetailPage，再切回时 remount，
          丢失 internalEditing 等所有内部状态。
          修复：onMounted 设置 detailPageEverMounted=true，v-if 用这个标记；
          ObjectDetailPage 自身被 keep-alive 缓存，detailPageEverMounted 不会重置，
          因此切走再切回 DetailPage 不会被销毁。
      -->
      <DetailPage
        v-if="detailPageEverMounted"
        ref="detailPageRef"
        :key="detailPageMountKey"
        :object-type="objectType"
        :id="id || (mode === 'add' ? 'new' : null)"
        :mode="mode"
        :standalone="true"
        :hide-header="true"
        :status-field="statusField"
        :status-map="statusMap"
        :readonly="readonly"
        :show-delete="showDelete"
        :show-history="showHistory"
        @close="handleClose"
        @delete="handleDelete"
        @loaded="handleDataLoaded"
        @saved="handleSaved"
      >
        <!-- Role permission config panel -->
        <template #section-permissions="{ data }">
          <PermissionConfigPanel
            :role-id="data?.id || id"
            :role="data"
            @saved="handleRefresh"
          />
        </template>
      </DetailPage>

      <div v-else class="odp-empty">
        <AppIcon name="warning" size="32" />
        <div class="odp-empty__title">缺少参数</div>
        <div class="odp-empty__desc">对象类型或ID无效</div>
        <AppButton variant="primary" size="sm" @click="handleClose">返回</AppButton>
      </div>
    </div>

    <Teleport to="body">
      <div v-if="showConfirmDialog" class="odp-confirm-overlay" @click.self="cancelClose">
        <div class="odp-confirm-dialog">
          <div class="odp-confirm-dialog__header">
            <AppIcon name="warning" size="20" class="odp-confirm-dialog__icon" />
            <span>关闭页面</span>
          </div>
          <div class="odp-confirm-dialog__body">
            当前页面有未保存的修改，确定要离开吗？
          </div>
          <div class="odp-confirm-dialog__footer">
            <button class="odp-btn odp-btn--secondary" @click="cancelClose">继续编辑</button>
            <button class="odp-btn odp-btn--primary" @click="confirmClose">离开</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, watch, provide, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useTabStore } from '@/stores/tabStore'
import DetailPage from '@/components/common/DetailPage/DetailPage.vue'
import { AppButton, AppIcon } from '@/components/common'
import PermissionConfigPanel from '@/views/SystemManagement/components/PermissionConfigPanel.vue'
import StateTransitionButtons from '@/components/bo/StateTransitionButtons.vue'
import metaService from '@/services/metaService'
import { objectTypeService } from '@/services/objectTypeService'

defineOptions({ name: 'ObjectDetail' })
import { useFieldPolicy } from '@/composables/useFieldPolicy'  // [DECORATIVE] [NEW] v1.3 / FR-6.1

const emit = defineEmits(['refresh'])

const router = useRouter()
const route = useRoute()
const tabStore = useTabStore()
const pageRef = ref(null)
const detailPageRef = ref(null)

// [FIX 2026-06-18] 关键修复：objectType/id 缓存上次的有效值
//   原因：app 顶部 tab 切走时，route.params.objectType/id 变 undefined，
//   切回时变回原值。如果直接用 computed 传给 DetailPage，watch 会把
//   "undefined → 'product'" 判断为"切到不同对象"，导致 internalEditing 重置。
//
//   修复：route 切走时 objectType 变 undefined 不向下传；用 lastValidObjectType
//   缓存上次的有效值，DetailPage 的 props 保持稳定，状态完整保留。
//   真正"切到不同对象"靠 effectiveObjectType !== lastValidObjectType 判断。
const rawObjectType = computed(() => route.params.objectType)
const rawId = computed(() => route.params.id)
const lastValidObjectType = ref(null)
const lastValidId = ref(null)
watch([rawObjectType, rawId], ([newType, newId]) => {
  if (newType && newId) {
    lastValidObjectType.value = newType
    lastValidId.value = newId
  }
}, { immediate: true })
const objectType = computed(() => lastValidObjectType.value || rawObjectType.value)
const id = computed(() => lastValidId.value || rawId.value)
// [FIX 2026-06-18] mode 也需要缓存：add 模式下 route.query.mode='add'，
//   切走时 query 清空 → mode 退到 'view'，切回时又变 'add'，触发
//   DetailPage watch 的 "same object mode change" 分支走
//   `data.value = {}` 清空用户已填表单。
//   修复：用 lastValidMode 缓存，route 抖动时 mode 保持稳定。
const rawMode = computed(() => route.query.mode)
const lastValidMode = ref(null)
watch(rawMode, (newMode) => {
  if (newMode) {
    lastValidMode.value = newMode
  }
}, { immediate: true })
const mode = computed(() => lastValidMode.value || rawMode.value || 'view')
// [FIX 2026-06-18] 重命名为 detailPageMountKey：仅用于强制 remount DetailPage
//   (PermissionConfigPanel saved 后)，平时稳定不变。
//   之前叫 detailPageKey 时配合 v-if="objectType && (id || mode === 'add')"，
//   在 app 顶部 tab 切走时 (route 变化 → id 变 undefined) 会 unmount DetailPage，
//   切回时 remount 丢失 internalEditing 等内部状态。
const detailPageMountKey = ref(0)
// [FIX 2026-06-18] 首次 mount 后设为 true，v-if 用这个标记
//   目的：ObjectDetailPage 被 keep-alive 缓存，detailPageEverMounted 不会重置，
//   保证切走再切回时 DetailPage 不被销毁
const detailPageEverMounted = ref(false)

const entityMeta = ref(null)

// [DECORATIVE] [NEW] v1.3 / FR-6.1: 字段策略
const { autoLoad: autoLoadPolicies } = useFieldPolicy(
  computed(() => entityMeta.value),
  computed(() => [])
)

const STATUS_FIELD_CANDIDATES = ['status', 'is_active', 'state', 'enabled', 'active']

const statusField = computed(() => {
  if (!entityMeta.value?.fields) return null
  for (const candidate of STATUS_FIELD_CANDIDATES) {
    const found = entityMeta.value.fields.find(f =>
      (f.id || f.name) === candidate || f.semantics?.status === true
    )
    if (found) return found.id || found.name
  }
  return null
})

const statusMap = computed(() => {
  if (!entityMeta.value?.fields || !statusField.value) {
    const defaultMap = {
      'active': { label: '启用', type: 'success' },
      'inactive': { label: '禁用', type: 'danger' },
      'pending': { label: '待审核', type: 'warning' }
    }
    return defaultMap
  }
  const field = entityMeta.value.fields.find(f => (f.id || f.name) === statusField.value)
  if (field?.enum_values?.length) {
    const map = {}
    field.enum_values.forEach(ev => {
      map[ev.value] = { label: ev.label || ev.name, type: ev.type || ev.style || 'default' }
    })
    return map
  }
  return {
    'active': { label: '启用', type: 'success' },
    'inactive': { label: '禁用', type: 'danger' },
    'pending': { label: '待审核', type: 'warning' }
  }
})

const readonly = computed(() => route.query.readonly === 'true')
const showDelete = computed(() => route.query.showDelete !== 'false')
const showHistory = computed(() => route.query.showHistory !== 'false')

const pageTitle = computed(() => {
  if (!objectType.value) return '对象详情'
  const metaName = entityMeta.value?.name || entityMeta.value?.label
  const displayName = metaName || objectTypeService.getLabel(objectType.value)
  if (mode.value === 'add') return `新建${displayName}`
  return `${displayName}详情`
})

const objectName = ref('')
const displayTitle = computed(() => objectName.value ? `${pageTitle.value} ${objectName.value}` : pageTitle.value)

const dirty = ref(false)
const showConfirmDialog = ref(false)
let pendingCloseAction = null

provide('detailPageDirty', {
  isDirty: () => dirty.value,
  setDirty: (value) => { dirty.value = !!value }
})

function getPrimaryNameField() {
  if (entityMeta.value?.display_name_field) return entityMeta.value.display_name_field
  return null
}

function handleDataLoaded(data) {
  if (!data) return
  const primary = getPrimaryNameField()
  const nameFields = primary ? [primary] : ['name', 'username', 'title', 'code', 'label']
  for (const field of nameFields) {
    if (data[field]) {
      objectName.value = data[field]
      break
    }
  }
  updateTabLabel()
}

function handleSaved(savedData) {
  if (mode.value === 'add' && savedData?.id) {
    const listConfig = entityMeta.value?.ui_view_config?.list
    const basePath = listConfig?.detail_path || `/detail/${objectType.value}`
    const newPath = `${basePath}/${savedData.id}`
    const oldTabId = route.path
    tabStore.replaceTabId(oldTabId, newPath, newPath)
    router.replace({ path: newPath }).catch(() => {})
  }
}

function handleClose() {
  if (dirty.value) {
    pendingCloseAction = doClose
    showConfirmDialog.value = true
  } else {
    doClose()
  }
}

function confirmClose() {
  showConfirmDialog.value = false
  dirty.value = false
  if (pendingCloseAction) {
    pendingCloseAction()
    pendingCloseAction = null
  }
}

function cancelClose() {
  showConfirmDialog.value = false
  pendingCloseAction = null
}

function doClose() {
  const tabId = route.path
  const currentTab = tabStore.tabs.find(t => t.id === tabId)
  const sourceTabId = currentTab?.meta?.sourceTabId

  tabStore.closeTab(tabId)

  const remaining = tabStore.tabs
  if (remaining.length === 0) {
    router.push('/')
    return
  }

  if (sourceTabId) {
    const sourceTab = remaining.find(t => t.id === sourceTabId)
    if (sourceTab) {
      tabStore.switchTab(sourceTabId)
      router.push(sourceTab.path || sourceTab.id)
      return
    }
  }

  const activeTab = remaining.find(t => t.id === tabStore.activeTabId)
  if (activeTab) {
    router.push(activeTab.path || activeTab.id)
  } else if (remaining.length > 0) {
    const lastTab = remaining[remaining.length - 1]
    router.push(lastTab.path || lastTab.id)
  } else {
    router.push('/')
  }
}

function handleRefresh() {
  // [FIX 2026-06-18] PermissionConfigPanel saved 后强制 remount DetailPage
  //   用作 mount key，递增触发组件重建 (注意：必须用 :key 才生效)
  detailPageMountKey.value++
}

function handleDelete() {
  handleClose()
}

function handleStateTransitionSuccess({ newStatus, stateField }) {
  console.debug('[ObjectDetailPage] handleStateTransitionSuccess called', { newStatus, stateField }, 'detailPageRef:', !!detailPageRef.value)
  // 直接调用 DetailPage.handleRefresh，传入新状态
  // DetailPage 内部会直接更新 data.status = newStatus，无需 remount
  if (detailPageRef.value?.handleRefresh) {
    detailPageRef.value.handleRefresh({ newStatus, stateField })
  } else {
    console.warn('[ObjectDetailPage] detailPageRef.handleRefresh not available')
  }
}

function handleKeydown(e) {
  if (e.key === 'Escape') {
    handleClose()
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
  pageRef.value?.focus()
  loadEntityMeta()
  // [FIX 2026-06-18] 首次 mount 后设置 detailPageEverMounted=true
  //   之后 ObjectDetailPage 被 keep-alive 缓存，这个 ref 不会重置，
  //   保证切走再切回时 v-if=true，DetailPage 不被销毁
  detailPageEverMounted.value = true
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
})

watch(objectType, () => {
  loadEntityMeta()
})

async function loadEntityMeta() {
  if (!objectType.value) return
  try {
    const result = await metaService.getUIConfig(objectType.value)
    if (result.success && result.data) {
      entityMeta.value = result.data
      updateTabLabel()
    } else {
      entityMeta.value = result.data || result
    }
  } catch (e) {
    console.warn('Failed to load entity meta for', objectType.value, e)
  }
  // [DECORATIVE] [NEW] v1.3 / FR-6.1: 激活 field-policies API
  if (objectType.value && autoLoadPolicies) {
    autoLoadPolicies(objectType.value, 'read').catch(e => {
      console.warn('[ObjectDetailPage] autoLoad field-policies failed:', e)
    })
  }
}

function updateTabLabel() {
  const tab = tabStore.tabs.find(t => t.id === route.path)
  if (!tab) return
  const newLabel = objectName.value ? `${pageTitle.value} ${objectName.value}` : pageTitle.value
  if (tab.label !== newLabel) {
    tabStore.updateTabLabel(tab.id, newLabel)
  }
}
</script>

<style scoped lang="scss">
.object-detail-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: var(--color-bg-page);
  outline: none;
}

.object-detail-page__content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.odp-title-bar {
  display: flex;
  align-items: center;
  padding: 8px var(--spacing-md);
  flex-shrink: 0;

  &__left {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  &__sep {
    width: 1px;
    height: 14px;
    background: var(--color-border);
  }

  &__title {
    font-size: 14px;
    font-weight: 600;
    color: var(--color-text-primary);
  }

  &__right {
    display: flex;
    align-items: center;
    gap: 12px;
    flex: 0 0 auto;
    margin-left: auto;
  }
}

.odp-back-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  font-size: 13px;
  color: var(--color-text-secondary);
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;

  &:hover {
    color: var(--color-primary);
    background: var(--color-bg-tertiary);
  }

  &:active {
    color: var(--color-primary-hover);
  }
}

.odp-empty {
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

.odp-confirm-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-index-tour);
}

.odp-confirm-dialog {
  background: var(--color-bg-container);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  min-width: 360px;
  max-width: 480px;
  overflow: hidden;

  &__header {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);
    padding: var(--spacing-md) var(--spacing-lg);
    font-size: 15px;
    font-weight: 600;
    color: var(--color-text-primary);
    border-bottom: 1px solid var(--color-border);
  }

  &__icon {
    color: var(--color-warning);
  }

  &__body {
    padding: var(--spacing-lg);
    font-size: 14px;
    color: var(--color-text-secondary);
    line-height: 1.6;
  }

  &__footer {
    display: flex;
    justify-content: flex-end;
    gap: var(--spacing-sm);
    padding: var(--spacing-sm) var(--spacing-lg) var(--spacing-md);
    border-top: 1px solid var(--color-border);
  }
}

.odp-btn {
  padding: 6px 16px;
  font-size: 13px;
  font-weight: 500;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all 0.15s ease;
  border: 1px solid transparent;

  &--secondary {
    color: var(--color-text-primary);
    background: var(--color-bg-tertiary);
    border-color: var(--color-border);

    &:hover {
      background: var(--color-bg-secondary);
    }
  }

  &--primary {
    color: #fff;
    background: var(--color-primary);
    &:hover {
      opacity: 0.9;
    }
  }
}
</style>
