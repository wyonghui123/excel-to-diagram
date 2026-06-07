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
          />

          <AssociationSection
            v-else-if="section.type === 'association' || section.type === 'annotation'"
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

function setHistoryRef(key, el) {
  if (el) {
    historyRefs.value[key] = el
  } else {
    delete historyRefs.value[key]
  }
}

const hasSectionsConfig = computed(() => props.sections && props.sections.length > 0)

const hasRealObjectId = computed(() => {
  const id = props.objectId
  if (id == null || id === '' || id === 'new') return false
  const numId = Number(id)
  return !isNaN(numId) && numId > 0
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
  emit('tab-change', tabKey)
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
  historyRefs
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
