<template>
  <main class="object-page__content">
    <section v-if="!hideHeader && ($slots.headerContent || $slots.info)" class="object-page__header-content">
      <slot name="headerContent">
        <div class="info-layout"><slot name="info" /></div>
      </slot>
    </section>

    <template v-if="hasSectionsConfig">
      <nav v-if="effectiveTabSections.length > 0" class="object-page__anchor-bar">
        <button
          v-for="tab in effectiveTabSections"
          :key="tab.key"
          :class="['anchor-tab', { 'anchor-tab--active': internalActiveTab === tab.key }]"
          @click="internalActiveTab = tab.key; onTabChange(tab.key)"
          type="button"
        >
          {{ tab.label }}
        </button>
      </nav>

      <div class="object-page__sections">
        <section
          v-for="section in effectiveTabSections"
          :key="section.key"
          v-show="internalActiveTab === section.key"
          class="op-section"
        >
          <template v-if="section.type === 'main_content'">
            <template v-for="mainSection in mainContentSections" :key="mainSection.key">
              <div class="op-section-header" v-if="mainSection.label">
                <AppIcon v-if="mainSection.icon" :name="mainSection.icon" size="sm" />
                <h3>{{ mainSection.label }}</h3>
              </div>
              <div class="op-section-content">
                <slot :name="`section-${mainSection.key}`">
                  <FieldGroupSection
                    v-if="mainSection.type === 'standard'"
                    :section="mainSection"
                    :form-data="formData"
                    :field-defs="fieldDefs"
                    :editing="editing"
                    :value-help-field-keys="valueHelpFieldKeys"
                    :enum-field-keys="enumFieldKeys"
                    :object-type="objectType"
                    :object-id="objectId"
                    :card-size="cardSize"
                    :form-render-key="formRenderKey"
                    :is-cascade-field="isCascadeField"
                    :get-cascade-parent="getCascadeParent"
                    @field-update="$emit('field-update', $event)"
                    @field-display-update="$emit('field-display-update', $event)"
                    @out-mapping="$emit('out-mapping', $event)"
                  />

                  <AssociationSection
                    v-else-if="mainSection.type === 'association' || mainSection.type === 'annotation'"
                    :ref="el => setAssociationRef(mainSection.key, el)"
                    :section="mainSection"
                    :object-type="objectType"
                    :object-id="objectId"
                    :editing="editing"
                    :ui-config="uiConfig"
                    @request-edit="$emit('update:editing', true)"
                    @open-assign="$emit('open-assign', $event)"
                    @refresh="(payload) => $emit('refresh', payload)"
                  />

                  <HistorySection
                    v-else-if="mainSection.type === 'history'"
                    :ref="el => setHistoryRef(mainSection.key, el)"
                    :object-type="objectType"
                    :object-id="objectId"
                    :parent-object-type="mainSection.parentObjectType || effectiveParentObjectType"
                    :parent-object-id="mainSection.parentObjectId || objectId"
                  />
                </slot>
              </div>
            </template>
          </template>

          <template v-else-if="section.type === 'custom' && section.component">
            <div class="op-custom-banner">
              <AppIcon name="bulb" :size="14" />
              <span>Custom Slot：<strong>{{ section.component }}</strong>（不受标准渲染引擎控制）</span>
            </div>
            <component
              :is="getComponent(section.component)"
              v-bind="section.props || {}"
              :form-data="formData"
              @update="$emit('field-update', $event)"
            />
          </template>
          <template v-else-if="section.type === 'custom' && section.key === 'permissions'">
            <!-- Special handling for role permission config -->
            <PermissionConfigPanel
              v-if="objectType === 'role'"
              :role-id="objectId"
            />
            <slot v-else :name="`section-${section.key}`" />
          </template>

          <template v-else-if="section.type === 'custom'">
            <!-- Custom section without component: render slot passed from parent -->
            <slot :name="`section-${section.key}`" />
          </template>

          <HistorySection
            v-else-if="section.type === 'history'"
            :ref="el => setHistoryRef(section.key, el)"
            :object-type="objectType"
            :object-id="objectId"
            :parent-object-type="section.parentObjectType || effectiveParentObjectType"
            :parent-object-id="section.parentObjectId || objectId"
          />

          <AssociationSection
            v-else-if="section.type === 'association' || section.type === 'annotation'"
            :ref="el => setAssociationRef(section.key, el)"
            :section="section"
            :object-type="objectType"
            :object-id="objectId"
            :editing="editing"
            :ui-config="uiConfig"
            @request-edit="$emit('update:editing', true)"
            @open-assign="$emit('open-assign', $event)"
            @refresh="(payload) => $emit('refresh', payload)"
          />

          <FieldGroupSection
            v-else
            :section="section"
            :form-data="formData"
            :field-defs="fieldDefs"
            :editing="editing"
            :value-help-field-keys="valueHelpFieldKeys"
            :enum-field-keys="enumFieldKeys"
            :object-type="objectType"
            :object-id="objectId"
            :card-size="cardSize"
            :form-render-key="formRenderKey"
            :is-cascade-field="isCascadeField"
            :get-cascade-parent="getCascadeParent"
            @field-update="$emit('field-update', $event)"
            @field-display-update="$emit('field-display-update', $event)"
            @out-mapping="$emit('out-mapping', $event)"
          />

          <slot :name="`section-${section.key}`" />
        </section>
      </div>
    </template>

    <template v-else>
      <slot />
    </template>
  </main>
</template>

<script setup>
import { ref, computed, watch, getCurrentInstance } from 'vue'
import { nextTick } from 'vue'
import AppIcon from '../AppIcon/AppIcon.vue'
import FieldGroupSection from './FieldGroupSection.vue'
import AssociationSection from './AssociationSection.vue'
import HistorySection from './HistorySection.vue'
import PermissionConfigPanel from '@/views/SystemManagement/components/PermissionConfigPanel.vue'

const MAIN_CONTENT_TAB_KEY = '__main_content__'

const props = defineProps({
  sections: {
    type: Array,
    default: () => []
  },
  formData: {
    type: Object,
    default: () => ({})
  },
  fieldDefs: {
    type: Object,
    default: () => ({})
  },
  editing: {
    type: Boolean,
    default: false
  },
  objectType: {
    type: String,
    default: null
  },
  objectId: {
    type: [String, Number],
    default: null
  },
  cardSize: {
    type: String,
    default: 'sm'
  },
  valueHelpFieldKeys: {
    type: Set,
    default: () => new Set()
  },
  enumFieldKeys: {
    type: Set,
    default: () => new Set()
  },
  uiConfig: {
    type: Object,
    default: () => ({})
  },
  cascadeFields: {
    type: Array,
    default: () => []
  },
  isCascadeField: {
    type: Function,
    default: () => false
  },
  getCascadeParent: {
    type: Function,
    default: () => null
  },
  formRenderKey: {
    type: Number,
    default: 0
  },
  hideHeader: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits([
  'tab-change',
  'field-update',
  'field-display-update',
  'out-mapping',
  'update:editing',
  'refresh',
  'open-assign',
  'request-edit'
])

const instance = getCurrentInstance()
const internalActiveTab = ref(null)

const historyRefs = ref({})
// [L2 2026-06-18 FIX] 跟踪 association/annotation section refs
//   用于在 onTabChange 和 coordinator refresh 时调用 section.refresh()
//   解决"详情页 v-show 切 tab 后子列表 stale"问题
const associationRefs = ref({})

function setHistoryRef(key, el) {
  if (el) {
    historyRefs.value[key] = el
  } else {
    delete historyRefs.value[key]
  }
}

function setAssociationRef(key, el) {
  if (el) {
    associationRefs.value[key] = el
  } else {
    delete associationRefs.value[key]
  }
}

const hasSectionsConfig = computed(() => props.sections && props.sections.length > 0)

const hasRealObjectId = computed(() => {
  const id = props.objectId
  if (id == null || id === '' || id === 'new') return false
  const numId = Number(id)
  return !isNaN(numId) && numId > 0
})

// [FIX 2026-06-12] 父对象查询: 哪些 objectType 自身日志很少, 但 "权限配置/成员管理/关联操作" 等
// 会写日志到 child object_type (parent_object_type=自身, parent_object_id=自身ID).
// 这些对象在详情页"操作日志" tab 需要同时拉 self + child 日志.
const SELF_REFERRING_PARENT_OBJECT_TYPES = new Set([
  'role',        // role_menu / role_permissions / role_data_permission / role_dimension_scope / role_v2_menu_permissions / permission_rule
  'user',        // user_role / user_group_member / user_data_scope
  'user_group',  // user_group_member
  'product',     // product-level 子对象 (如未来增加 product_member)
  'version',     // version-level 子对象
])

const effectiveParentObjectType = computed(() => {
  if (!props.objectType) return null
  return SELF_REFERRING_PARENT_OBJECT_TYPES.has(props.objectType) ? props.objectType : null
})

function isSectionVisible(section) {
  if (!section.visibleWhen) return true
  const { field, operator, value } = section.visibleWhen
  const fieldValue = props.formData[field]
  switch (operator) {
    case 'equals': return fieldValue === value
    case 'notEquals': return fieldValue !== value
    case 'exists': return fieldValue != null && fieldValue !== ''
    case 'in': return Array.isArray(value) ? value.includes(fieldValue) : false
    default: return true
  }
}

const visibleSections = computed(() => {
  if (!hasSectionsConfig.value) return []
  return props.sections.filter(section => isSectionVisible(section))
})

const mainContentSections = computed(() => {
  if (!hasSectionsConfig.value) return []
  return props.sections.filter(section => {
    if (!isSectionVisible(section)) return false
    if (!['always', 'inline', 'expandable'].includes(section.display)) return false
    return true
  })
})

const tabSections = computed(() => {
  if (!hasSectionsConfig.value) return []
  return props.sections.filter(section =>
    isSectionVisible(section) && !['always', 'inline', 'expandable'].includes(section.display)
  )
})

const hasAlwaysVisibleSections = computed(() => {
  if (!hasSectionsConfig.value) return false
  return props.sections.some(section => {
    if (!isSectionVisible(section)) return false
    return ['always', 'inline', 'expandable'].includes(section.display)
  })
})

const effectiveTabSections = computed(() => {
  const tabs = tabSections.value

  if (hasAlwaysVisibleSections.value) {
    const mainTab = { key: MAIN_CONTENT_TAB_KEY, label: '基本信息', type: 'main_content', icon: 'info' }
    if (tabs.length === 0) {
      return [mainTab]
    }
    return [mainTab, ...tabs]
  }

  return tabs
})

function onTabChange(tabKey) {
  _ignoreNextWatcher.value = true
  _prevEffectiveTabKeys.value = _buildEffectiveTabKeys(effectiveTabSections.value)
  const section = props.sections.find(s => s.key === tabKey)
  if (section?.type === 'history') {
    const historyRef = historyRefs.value[tabKey]
    if (historyRef?.loadAuditLogs) {
      nextTick(() => historyRef.loadAuditLogs())
    }
  }
  // [L2 2026-06-18 FIX] 切到 association/annotation tab 时刷新该 section 的子列表
  //   原因：v-show 模式下 section 一直挂载，首次拿数据后不再重拉。
  //   用户从该 tab 切走再切回看不到最新数据（除非手动点刷新）。
  //   切 tab 触发 refresh() 与 history tab 的 loadAuditLogs() 行为一致。
  if (section && (section.type === 'association' || section.type === 'annotation')) {
    const assocRef = associationRefs.value[tabKey]
    if (assocRef && typeof assocRef.refresh === 'function') {
      // nextTick 等 v-show 切完 DOM，避免 section 内部读取 width=0 等导致计算错误
      nextTick(() => {
        try { assocRef.refresh() }
        catch (e) { console.warn(`[ObjectPageContent] section refresh failed for "${tabKey}":`, e) }
      })
    }
  }
  emit('tab-change', tabKey)
}

// [L2 2026-06-18 FIX] 给 DetailPage coordinator 调用的统一入口：
//   刷新当前 ObjectPage 下所有 association/annotation section
//   （避免 v-show 缓存导致 stale）。history section 由 HistorySection 自身
//   监听 props 变化刷新，不需要在这里触发。
async function refreshAllSections() {
  const refs = Object.values(associationRefs.value).filter(Boolean)
  if (refs.length === 0) return
  // 并行刷新，不相互阻塞；任一失败不阻断其他
  await Promise.allSettled(refs.map(r => {
    if (typeof r.refresh === 'function') {
      try { return Promise.resolve(r.refresh()) }
      catch (e) { console.warn('[ObjectPageContent] refresh section error:', e); return Promise.resolve() }
    }
    return Promise.resolve()
  }))
}

function getComponent(componentName) {
  try {
    const components = instance?.appContext?.components || {}
    if (components[componentName]) return componentName
    return 'div'
  } catch (e) {
    return 'div'
  }
}

const _prevEffectiveTabKeys = ref('')
const _ignoreNextWatcher = ref(false)

function _buildEffectiveTabKeys(tabs) {
  return tabs.map(function(s) { return s.key }).join('|')
}

watch(effectiveTabSections, function(tabs) {
  if (tabs.length === 0) return
  var keys = _buildEffectiveTabKeys(tabs)

  if (_ignoreNextWatcher.value) {
    _ignoreNextWatcher.value = false
    _prevEffectiveTabKeys.value = keys
    return
  }

  if (!_prevEffectiveTabKeys.value) {
    _prevEffectiveTabKeys.value = keys
    if (!internalActiveTab.value) {
      internalActiveTab.value = tabs[0].key
    }
    return
  }

  if (keys === _prevEffectiveTabKeys.value) {
    return
  }
  _prevEffectiveTabKeys.value = keys

  var currentTabExists = tabs.some(function(s) { return s.key === internalActiveTab.value })
  if (!currentTabExists) {
    internalActiveTab.value = tabs[0].key
  }
}, { immediate: true })

watch(() => [props.objectId, visibleSections.value], () => {
  const hasMerged = visibleSections.value.some(s => s.customFetcher === 'merged_bo_relationships')
  if (hasMerged) {
    const assocSections = visibleSections.value.filter(s => s.customFetcher === 'merged_bo_relationships')
    for (const section of assocSections) {
      const sectionKey = section.key
      const assocRef = historyRefs.value[sectionKey]
      if (assocRef?.loadMergedRelationships) {
        assocRef.loadMergedRelationships()
      }
    }
  }
})

defineExpose({
  internalActiveTab,
  historyRefs,
  // [L2 2026-06-18] L1 commit 注册的 coordinator 回调依赖此方法
  //   调用场景：coordinator 触发 → DetailPage.coordinatorRefresh → objectPageRef.value.refreshAllSections()
  refreshAllSections,
  associationRefs
})
</script>

<style scoped>
.object-page__content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
}

.object-page__header-content {
  background: var(--color-bg-container);
  padding: var(--spacing-md);
  border-bottom: 1px solid var(--color-border-tertiary);
  margin-bottom: var(--spacing-sm);
}

.info-layout {
  max-width: var(--page-max-width);
}

.object-page__anchor-bar {
  display: flex;
  gap: 0;
  padding: 0 var(--spacing-md);
  background: var(--color-bg-container);
  border-bottom: 1px solid var(--color-border-secondary);
  flex-shrink: 0;
}

.anchor-tab {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-xs) var(--spacing-md);
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-tertiary);
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s ease;
}

.anchor-tab:hover {
  color: var(--color-primary);
  background: var(--color-primary-bg);
}

.anchor-tab--active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
}

.anchor-tab--active:hover {
  color: var(--color-primary);
  background: var(--color-primary-bg);
}

.object-page__sections {
  padding: var(--spacing-md);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
  flex-shrink: 0;
}

.op-section {
  width: 100%;
  flex-shrink: 0;
}

.op-section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: var(--color-bg-tertiary);
  border-bottom: 1px solid var(--color-border-secondary);
}

.op-section-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.op-section-content {
  padding: var(--spacing-md);
  min-height: auto;
  background: var(--color-bg-container);
}

.op-custom-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-success-bg, #ecfdf5);
  border: 1px solid var(--color-success-border, #6ee7b7);
  border-radius: var(--radius-md);
  margin-bottom: var(--spacing-sm);
  font-size: 13px;
  color: var(--color-success-dark, #047857);
}

@media (max-width: 768px) {
  .object-page__sections { padding: var(--spacing-xs) var(--spacing-sm); }
  .object-page__anchor-bar { padding: 0 var(--spacing-sm); }
}
</style>
