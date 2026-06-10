<template>
  <el-drawer
    v-if="!standalone"
    :model-value="visible"
    :title="drawerTitle"
    direction="rtl"
    size="50%"
    destroy-on-close
    @close="handleClose"
  >
    <div class="detail-page">
      <div v-if="loading" class="dp-loading">
        <AppIcon name="refresh" size="24" class="spin" />
        <span>加载中...</span>
      </div>

      <div v-else-if="error" class="dp-error">
        <AppIcon name="warning" size="24" />
        <p>{{ error }}</p>
        <AppButton variant="primary" size="sm" @click="handleRefresh">重试</AppButton>
      </div>

      <div v-else-if="!data" class="dp-empty">
        <AppIcon name="warning" size="24" />
        <p>未找到数据</p>
      </div>

      <div v-else class="dp-content">
        <slot name="default" :data="data" />
        <ObjectPage
          v-if="!$slots.default && metaLoaded"
          ref="objectPageRef"
          :title="drawerTitle"
          :subtitle="dataSubtitle"
          :status="dataStatus"
          :status-type="dataStatusType"
          :show-back-button="false"
          :sections="computedSections"
          :form-data="data"
          :field-definitions="computedFieldDefs"
          :cascade-fields="cascade.cascadeFields?.value"
          :is-cascade-field="cascade.isCascadeField"
          :get-cascade-parent="cascade.getParentField"
          :actions="computedActions"
          :editing="internalEditing"
          :saving="saving"
          :auto-load-meta="true"
          :object-type="objectType"
          :object-id="id"
          :card-size="'sm'"
          :loading="false"
          size="sm"
          :hide-header="hideHeader"
          @tab-change="handleTabChange"
          @field-update="handleFieldUpdate"
          @field-display-update="handleFieldDisplayUpdate"
          @update:editing="internalEditing = $event"
          @action="handleObjectPageAction"
        >
          <template v-for="section in computedSections" :key="section.key" #[`section-${section.key}`]>
            <slot :name="`section-${section.key}`" :data="data" />
          </template>
        </ObjectPage>
        <div v-if="!$slots.default && !metaLoaded" class="dp-loading-inline">
          <AppIcon name="refresh" size="16" class="spin" />
          <span>加载配置中...</span>
        </div>
      </div>
    </div>

    <template #footer>
      <!--
        底部操作区按 mode 动态渲染（useDetailActions）。
        关闭动作不再放 footer —— 由 el-drawer 顶部 X 承担，避免重复按钮。
        add/edit 模式下保存/取消由 ObjectPageHeader 提供，footer 留空。
      -->
      <slot name="footer" :actions="footerActions">
        <AppButton
          v-for="act in footerActions.filter((a) => a.visible)"
          :key="act.key"
          :variant="act.variant"
          :disabled="act.disabled"
          @click="act.onClick"
        >
          <AppIcon v-if="act.icon" :name="act.icon" size="sm" />
          {{ act.label }}
        </AppButton>
      </slot>
    </template>
  </el-drawer>

  <div v-else class="detail-page detail-page--standalone">
    <div v-if="loading" class="dp-loading">
      <AppIcon name="refresh" size="24" class="spin" />
      <span>加载中...</span>
    </div>

    <div v-else-if="error" class="dp-error">
      <AppIcon name="warning" size="24" />
      <p>{{ error }}</p>
      <AppButton variant="primary" size="sm" @click="handleRefresh">重试</AppButton>
    </div>

    <div v-else-if="!data" class="dp-empty">
      <AppIcon name="warning" size="24" />
      <p>未找到数据</p>
    </div>

    <div v-else class="dp-content">
      <slot name="default" :data="data" />
      <ObjectPage
        v-if="!$slots.default && metaLoaded"
        ref="objectPageRef"
        :title="drawerTitle"
        :subtitle="dataSubtitle"
        :status="standalone ? '' : dataStatus"
        :status-type="dataStatusType"
        :show-back-button="false"
        :sections="computedSections"
        :form-data="data"
        :field-definitions="computedFieldDefs"
        :cascade-fields="cascade.cascadeFields?.value"
        :is-cascade-field="cascade.isCascadeField"
        :get-cascade-parent="cascade.getParentField"
        :actions="computedActions"
        :editing="internalEditing"
        :saving="saving"
        :auto-load-meta="true"
        :object-type="objectType"
        :object-id="id"
        :card-size="'sm'"
        :loading="false"
        size="sm"
        :hide-header="hideHeader"
        @tab-change="handleTabChange"
        @field-update="handleFieldUpdate"
        @field-display-update="handleFieldDisplayUpdate"
        @update:editing="internalEditing = $event"
        @action="handleObjectPageAction"
      >
        <template v-for="section in computedSections" :key="section.key" #[`section-${section.key}`]="sectionData">
          <!-- Always render slot if provided by parent -->
          <slot :name="`section-${section.key}`" :data="data" />
        </template>
      </ObjectPage>
      <div v-if="!$slots.default && !metaLoaded" class="dp-loading-inline">
        <AppIcon name="refresh" size="16" class="spin" />
        <span>加载配置中...</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useMessage } from '@/composables/useMessage'
import { useVersionContext } from '@/composables/useVersionContext'
import { useFormCascade } from '@/composables/useCascadeSelect'
import { useDetailActions } from '@/composables/useDetailActions'
import metaService from '@/services/metaService'
import boService from '@/services/boService'
import { objectTypeService } from '@/services/objectTypeService'
import { AppButton } from '@/components/common/AppButton'
import { AppIcon } from '@/components/common/AppIcon'
import { ObjectPage } from '@/components/common/ObjectPage'

const { selectedVersionId } = useVersionContext()

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  objectType: { type: String, required: true },
  id: { type: [String, Number], required: true },
  mode: { type: String, default: 'view' },
  createMode: { type: Boolean, default: false },
  editMode: { type: Boolean, default: false },
  statusField: { type: String, default: null },
  statusMap: { type: Object, default: () => ({}) },
  readonly: { type: Boolean, default: false },
  showDelete: { type: Boolean, default: true },
  showHistory: { type: Boolean, default: true },
  standalone: { type: Boolean, default: false },
  hideHeader: { type: Boolean, default: false }
})

const emit = defineEmits(['update:modelValue', 'close', 'refresh', 'delete', 'loaded', 'saved', 'created'])

const message = useMessage()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})
const loading = ref(false)
const error = ref(null)
const data = ref(null)

const effectiveMode = computed(() => {
  if (props.createMode) return 'add'
  if (props.editMode) return 'edit'
  return props.mode
})

const internalEditing = ref(effectiveMode.value === 'add' || effectiveMode.value === 'edit')
const saving = ref(false)

/**
 * footer 操作按钮配置：按 mode 动态渲染
 * view 模式 → 仅"刷新"（X 按钮承担关闭）
 * add/edit 模式 → footer 让空（保存/取消已在 ObjectPageHeader）
 * 调用方可通过 <template #footer="slotProps"> 完全自定义
 */
const { actions: footerActions } = useDetailActions({
  mode: effectiveMode,
  saving,
  loading,
  hasData: computed(() => !!data.value),
  onSave: handleSave,
  onCancel: handleObjectPageAction.bind(null, { action: { key: 'cancel' } }),
  onRefresh: handleRefresh,
})

const entityMeta = ref(null)
const cascade = useFormCascade(
  computed(() => entityMeta.value),
  computed(() => data.value || {})
)
const metaLoaded = ref(false)

async function loadEntityMeta() {
  if (!props.objectType) {
    console.warn('[DetailPage] [WARNING] loadEntityMeta: objectType 为空，跳过')
    metaLoaded.value = true
    return
  }
  if (metaLoaded.value) {
    return
  }
  try {
    const result = await metaService.getUIConfig(props.objectType)
    if (result.success) {
      entityMeta.value = result.data
      _applyFieldDefaults()
    } else {
      console.warn(`[DetailPage] [WARNING] getUIConfig 失败:`, result.message || '无消息')
    }
  } catch (e) {
    console.warn('[DetailPage] Failed to load entity meta:', e)
  } finally {
    metaLoaded.value = true
    // [FIX] 启动 FK 级联监听：父字段变化时清空下游 formData。
    // 工具函数 (useFormCascade.initialize -> clearAllDownstream) 已实现，
    // 但需要 entityMeta 加载完才有 cascade_select 配置可用。
    // 这里 fire-and-forget：watch 注册是同步的，inferParentFields 只在编辑模式有意义。
    if (entityMeta.value?.cascade_select?.length) {
      cascade.initialize()
    }
  }
}

function _applyFieldDefaults() {
  const isAddMode = effectiveMode.value === 'add' || props.id === 'new'
  if (!isAddMode || !entityMeta.value?.fields) return
  if (!data.value) data.value = {}
  let changed = false
  for (const f of entityMeta.value.fields) {
    if (f.default !== undefined && f.default !== null && data.value[f.id] === undefined) {
      data.value[f.id] = f.default
      changed = true
    }
  }
  if (changed) {
    data.value = { ...data.value }
  }
}

const hasAuditAspect = computed(() => {
  if (!entityMeta.value) return false
  const aspects = entityMeta.value.aspects || []
  return aspects.includes('audit_aspect')
})

const drawerTitle = computed(() => {
  const metaLabel = entityMeta.value?.name || entityMeta.value?.label
  const objectLabel = metaLabel || objectTypeService.getLabel(props.objectType)
  if (effectiveMode.value === 'add') {
    return `新建${objectLabel}`
  }
  return `${objectLabel}详情`
})

const dataSubtitle = computed(() => {
  // 🆕 v1.1 owner refactor (FR-006): 显示 effective_owner_id_display
  const owner = data.value?.effective_owner_id_display
  if (owner) {
    return `负责人: ${owner}`
  }
  return ''
})

const STATUS_FIELD_CANDIDATES = ['status', 'is_active', 'state', 'enabled', 'active']

function getStatusFieldName() {
  if (!entityMeta.value?.fields) return 'status'
  for (const candidate of STATUS_FIELD_CANDIDATES) {
    const found = entityMeta.value.fields.find(f =>
      (f.id || f.name) === candidate || f.semantics?.status === true
    )
    if (found) return found.id || found.name
  }
  return 'status'
}

const dataStatus = computed(() => {
  if (!data.value) return ''
  const statusField = getStatusFieldName()
  const val = data.value[statusField]
  console.debug('[DetailPage] dataStatus computed:', { statusField, val, data: data.value })
  if (val === undefined || val === null) return ''
  if (typeof val === 'boolean') return val ? '启用中' : '已停用'
  return String(val)
})

const dataStatusType = computed(() => {
  if (!data.value) return 'default'
  const statusField = getStatusFieldName()
  const val = data.value[statusField]
  if (typeof val === 'boolean') return val ? 'success' : 'danger'
  return 'default'
})

const computedFieldDefs = computed(() => {
  if (!entityMeta.value?.fields) return {}
  const defs = {}
  const isAddMode = effectiveMode.value === 'add' || props.id === 'new'
  
  for (const f of entityMeta.value.fields) {
    if (f.visible === false) continue
    if (f.ui?.visible === false) continue
    if (f.hidden_in_detail && !isAddMode) continue
    if (f.hidden_in_form && isAddMode) continue
    // [FIX v1.0.9 2026-06-10] owner 类不可编辑字段在 edit 模式也隐藏
    if (!isAddMode && f.hidden_in_form && f.ui?.editable === false) continue
    
    const semantics = f.semantics || {}
    // parent_key（自引用外键）允许用户修改（可重新指定父组），不应被视作 immutable。
    const isImmutable = semantics.immutable === true || f.immutable === true
    const isReadonlyAlways = semantics.readonly_always === true
    const isBusinessKey = semantics.business_key === true
    const isComputed = f.computed === true
    const backendNotEditable = f.editable === false
    const backendReadonly = f.readonly === true
    const uiEditable = f.ui?.editable
    
    const fieldEditable = uiEditable !== false 
      && f.id !== 'id' 
      && !backendNotEditable
      && !(isBusinessKey && !isAddMode)
      && !isComputed
    
    const fieldReadonly = isReadonlyAlways 
      || backendReadonly 
      || uiEditable === false 
      || (isBusinessKey && !isAddMode)
      || isComputed
      || f.id.toLowerCase() === 'type'
    
    let valueHelp = f.value_help
    if (!valueHelp && f.ui?.relation) {
      valueHelp = {
        source: {
          type: 'bo',
          target_bo: f.ui.relation,
          value_field: 'id',
          display_field: f.ui.display_field || 'name'
        }
      }
    }

    defs[f.id] = {
      label: f.name || f.id,
      type: f.type || 'text',
      widget: f.ui?.widget || undefined,
      required: f.required === true,
      editable: fieldEditable,
      readonly: fieldReadonly,
      immutable: isImmutable && !isAddMode,
      placeholder: f.ui?.placeholder || '',
      options: f.enum_values || f.options || undefined,
      valueHelp
    }
  }
  return defs
})

const computedActions = computed(() => {
  if (props.readonly) return []

  const isAddMode = effectiveMode.value === 'add' || props.id === 'new'
  
  if (isAddMode) {
    return [buildAction('save'), buildAction('cancel')]
  }

  const isSystemEnumType = props.objectType === 'enum_type' && data.value?.category === 'system'
  if (isSystemEnumType) {
    return []
  }

  const detailConfig = entityMeta.value?.ui_view_config?.detail
  const yamlActions = detailConfig?.actions || []

  if (yamlActions.length > 0) {
    return yamlActions.map(a => {
      if (typeof a === 'string') {
        return buildAction(a)
      }
      return {
        id: a.id || a.key,
        key: a.key || a.id,
        label: a.label,
        icon: a.icon,
        variant: a.variant || a.type,
        container: a.container
      }
    })
  }

  const actions = [buildAction('edit')]
  if (internalEditing.value) {
    actions.push(buildAction('save'))
    actions.push(buildAction('cancel'))
  }
  if (props.showDelete && !internalEditing.value) {
    actions.push(buildAction('delete'))
  }
  return actions
})

function buildAction(key) {
  const map = {
    edit: { id: 'edit', key: 'edit', label: '编辑', icon: 'edit', variant: 'primary' },
    save: { id: 'save', key: 'save', label: '保存', icon: 'save', variant: 'primary' },
    cancel: { id: 'cancel', key: 'cancel', label: '取消', icon: 'close', variant: 'secondary' },
    delete: { id: 'delete', key: 'delete', label: '删除', icon: 'delete', variant: 'danger' }
  }
  return map[key] || { id: key, key, label: key, icon: key, variant: '' }
}

const computedSections = computed(() => {
  const sections = []

  const isAddMode = effectiveMode.value === 'add' || props.id === 'new'
  const isEditing = internalEditing.value || isAddMode
  const allFields = entityMeta.value?.fields || []
  const fieldMetaMap = {}
  allFields.forEach(f => { fieldMetaMap[f.id] = f })

  const virtualFieldDisplayNameMap = {}
  for (const f of allFields) {
    if (f.storage === 'virtual' && f.id.endsWith('_id')) {
      const nameField = f.id.replace(/_id$/, '_name')
      if (fieldMetaMap[nameField]) {
        virtualFieldDisplayNameMap[f.id] = nameField
      }
    }
  }

  function adaptFieldForMode(fieldId) {
    if (!isEditing && virtualFieldDisplayNameMap[fieldId]) {
      return virtualFieldDisplayNameMap[fieldId]
    }
    return fieldId
  }

  function adaptFieldsForMode(fields) {
    return (fields || []).map(adaptFieldForMode)
  }

  function shouldShowField(fieldId) {
    const f = fieldMetaMap[fieldId]
    if (!f) return true
    if (f.visible === false || f.ui?.visible === false) return false
    if (f.hidden_in_detail && !isAddMode) return false
    if (f.hidden_in_form && isAddMode) return false
    // [FIX v1.0.9 2026-06-10] owner 类不可编辑字段在 edit 模式也隐藏
    if (!isAddMode && f.hidden_in_form && f.ui?.editable === false) return false
    if (isAddMode) {
      const semantics = f.semantics || {}
      const isSystem = semantics.system_field === true || f.system_field === true
      if (isSystem || isSystemField(f.id)) return false
      const semanticsType = (semantics.type || '').toLowerCase()
      if (semanticsType === 'audit' || semanticsType === 'system') return false
    }
    return true
  }

  function filterFields(fields) {
    return (fields || []).filter(shouldShowField)
  }

  const formConfig = entityMeta.value?.ui_view_config?.form
  const formSections = formConfig?.sections || []

  if (formSections.length > 0) {
    for (const section of formSections) {
      if (section.columns && section.columns.length > 0) {
        const fieldGroups = []
        for (const col of section.columns) {
          const filteredFields = adaptFieldsForMode(filterFields(col.fields || []))
          if (filteredFields.length === 0) continue
          fieldGroups.push({
            title: col.title || '',
            layout: 'grid-2',
            fields: filteredFields
          })
        }
        if (fieldGroups.length === 0) continue
        sections.push({
          key: section.title || 'form',
          label: section.title || '表单',
          icon: 'info',
          type: 'standard',
          display: 'always',
          fieldGroups
        })
      } else {
        const filteredFields = adaptFieldsForMode(filterFields(section.fields || []))
        if (filteredFields.length === 0) continue
        sections.push({
          key: section.title || 'form',
          label: section.title || '表单',
          icon: 'info',
          type: 'standard',
          display: 'always',
          fieldGroups: [{
            title: '',
            layout: section.layout || 'grid-2',
            fields: filteredFields
          }]
        })
      }
    }
  }

  const detailConfig = entityMeta.value?.ui_view_config?.detail
  const facets = detailConfig?.facets || []
  const tabs = detailConfig?.tabs || []
  const entityAssociations = entityMeta.value?.associations || []

  console.debug('[DetailPage] computedSections:', {
    entityAssociations,
    tabs: tabs.length,
    associationsKeys: Object.keys(entityAssociations)
  })

  function isCollectionAssociation(assocName) {
    if (assocName === 'annotation') {
      return true
    }
    const assoc = entityAssociations.find(a => a.name === assocName || a.target === assocName || a.target_type === assocName)
    console.debug('[DetailPage] isCollectionAssociation:', assocName, 'found:', !!assoc, 'assoc:', assoc)
    if (!assoc) return false
    return assoc.type === 'one_to_many' || assoc.type === 'many_to_many' || assoc.type === 'merged_one_to_many' || assoc.type === 'parent_child' || assoc.type === 'reverse_many_to_many'
  }

  function shouldShowAssociation(tab) {
    if (!isEditing) {
      return true
    }
    const assocName = tab.association || tab.id || ''
    const assocDef = entityAssociations.find(a => a.name === assocName)
    if (tab.readonly || assocDef?.readonly) {
      return true
    }
    return false
  }

  function getAssociationType(assocName) {
    const assoc = entityAssociations.find(a => a.name === assocName)
    return assoc?.type || null
  }

  if (tabs.length > 0) {
    for (const tab of tabs) {
      if (tab.type === 'fields' || (!tab.type && tab.fields)) {
        if (isEditing || formSections.length > 0) continue
        sections.push({
          key: tab.id || 'basic',
          label: tab.label || '基本信息',
          icon: tab.icon || 'info',
          type: 'standard',
          fieldGroups: [{
            title: tab.label || '基本信息',
            layout: 'grid-2',
            fields: filterFields(tab.fields)
          }]
        })
      } else if (tab.type === 'association') {
        if (!shouldShowAssociation(tab)) {
          console.debug('[DetailPage] Skipping association tab:', tab.association, '(editing mode)')
          continue
        }
        if (isCollectionAssociation(tab.association)) {
          const assocDef = entityAssociations.find(a => a.name === tab.association)
          console.debug('[DetailPage] Creating association section:', tab.association, 'assocDef:', assocDef)
          // [FIX 2026-06-09] readonly 时强制把 unassign/assign 移除，
          // 只保留 list（防止下游 manyToManyRowActions 即使 section.readonly
          // 解析失败仍兜底出"移除"按钮）。
          const isAssocReadonly = !!(tab.readonly || assocDef?.readonly)
          const safeActions = isAssocReadonly
            ? (tab.actions || ['list']).filter(a => {
                const key = typeof a === 'string' ? a : (a.key || a.id)
                return key === 'list'
              })
            : (tab.actions || ['assign', 'unassign', 'list'])
          sections.push({
            key: tab.id || tab.association,
            label: tab.label || tab.association,
            icon: tab.icon || 'link',
            type: 'association',
            association: assocDef?.target_type || assocDef?.target_entity || tab.association || '',
            assocName: tab.association,
            assocType: assocDef?.type,
            pageSize: tab.pageSize || 20,
            display: tab.display || 'inline',
            actions: safeActions,
            readonly: isAssocReadonly
          })
        } else {
        }
      } else if (tab.type === 'history') {
        sections.push({
          key: tab.id || 'audit-log',
          label: tab.label || '操作日志',
          icon: tab.icon || 'history',
          type: 'history'
        })
      } else if (tab.type === 'fieldGroup') {
        if (isEditing || formSections.length > 0) continue
        sections.push({
          key: tab.id || tab.title,
          label: tab.label || tab.title,
          icon: tab.icon || 'info',
          type: 'standard',
          fieldGroups: [{
            title: tab.title || tab.label,
            layout: 'grid-2',
            fields: filterFields(tab.fields)
          }]
        })
      } else if (tab.type === 'custom') {
        sections.push({
          key: tab.id || 'custom',
          label: tab.label || '自定义',
          icon: tab.icon || 'settings',
          type: 'custom'
        })
      }
    }
  } else if (facets.length > 0) {
    const basicFieldGroups = facets
      .filter(f => f.type === 'fieldGroup')
      .map(f => ({
        title: f.title,
        layout: 'grid-2',
        fields: filterFields(f.fields)
      }))

    if (basicFieldGroups.length > 0 && !isEditing && formSections.length === 0) {
      sections.push({
        key: 'basic',
        label: '基本信息',
        icon: 'info',
        type: 'standard',
        display: 'always',
        fieldGroups: basicFieldGroups
      })
    }

    facets
      .filter(f => f.type === 'association')
      .forEach(f => {
        if (!shouldShowAssociation(f)) {
          return
        }
        const assocName = f.association || f.id || f.title
        if (isCollectionAssociation(assocName)) {
          const assocDef = entityAssociations.find(a => a.name === assocName)
          sections.push({
            key: f.id || f.title || f.association,
            label: f.label || f.title || f.association,
            icon: 'link',
            type: 'association',
            association: assocDef?.target_type || assocDef?.target_entity || assocName || '',
            assocName: assocName,
            assocType: assocDef?.type,
            pageSize: f.pageSize || 20,
            display: f.display || 'inline',
            actions: f.actions || ['assign', 'unassign', 'list'],
            readonly: f.readonly || assocDef?.readonly || false,
            customFetcher: f.customFetcher || assocDef?.customFetcher || null
          })
        }
      })

    facets
      .filter(f => f.type === 'history')
      .forEach(f => {
        sections.push({
          key: f.id || 'audit-log',
          label: f.label || '操作日志',
          icon: 'history',
          type: 'history'
        })
      })
  } else {
    const visibleFields = (entityMeta.value?.fields || [])
      .filter(f => f.ui?.visible !== false && f.id !== 'id')
      .map(f => f.id)

    if (visibleFields.length > 0 && !isEditing) {
      const groups = []
      const chunkSize = 4
      for (let i = 0; i < visibleFields.length; i += chunkSize) {
        groups.push({
          title: i === 0 ? '基本信息' : `信息 (${i + 1})`,
          layout: 'grid-2',
          fields: visibleFields.slice(i, i + chunkSize)
        })
      }
      sections.push({
        key: 'basic',
        label: '基本信息',
        icon: 'info',
        type: 'standard',
        fieldGroups: groups
      })
    }
  }

  const childSections = entityMeta.value?.ui_view_config?.child_sections || []
  for (const cs of childSections) {
    if (cs.child_object === 'annotation') {
      if (isAddMode) continue
      sections.push({
        key: 'annotation',
        label: cs.title || '备注信息',
        icon: 'note',
        type: 'annotation',
        association: 'annotation',
        assocName: 'annotation',
        assocType: 'annotation',
        pageSize: cs.pageSize || 10,
        display: cs.display || 'expandable',
        columns: cs.columns || [],
        actions: cs.actions || ['create', 'edit', 'delete'],
        defaultSort: cs.defaultSort || null,
        readonly: false
      })
    } else if (isCollectionAssociation(cs.child_object)) {
      const assocDef = entityAssociations.find(a =>
        a.name === cs.child_object || a.target === cs.child_object || a.target_type === cs.child_object
      )
      sections.push({
        key: cs.child_object,
        label: cs.title || cs.child_object,
        icon: 'list',
        type: 'association',
        association: assocDef?.target_type || assocDef?.target_entity || cs.child_object || '',
        assocName: cs.child_object,
        assocType: assocDef?.type || 'parent_child',
        pageSize: cs.pageSize || 20,
        display: cs.display || 'always',
        actions: cs.actions || ['assign', 'unassign', 'list'],
        readonly: cs.readonly || assocDef?.readonly || false,
        useMetaList: cs.useMetaList !== undefined ? cs.useMetaList : false,
        enableDetail: cs.enableDetail !== undefined ? cs.enableDetail : true,
        enableAutoCrud: cs.enableAutoCrud !== undefined ? cs.enableAutoCrud : false,
        rowMutability: cs.rowMutability || 'fully_editable'
      })
    } else if (cs.child_object) {
      sections.push({
        key: cs.child_object,
        label: cs.title || cs.child_object,
        icon: 'list',
        type: 'association',
        association: cs.child_object,
        assocName: cs.child_object,
        assocType: 'parent_child',
        pageSize: cs.pageSize || 20,
        display: cs.display || 'always',
        actions: cs.actions || ['create', 'edit', 'delete'],
        readonly: cs.readonly || false,
        useMetaList: cs.useMetaList !== undefined ? cs.useMetaList : false,
        enableDetail: cs.enableDetail !== undefined ? cs.enableDetail : true,
        enableAutoCrud: cs.enableAutoCrud !== undefined ? cs.enableAutoCrud : false,
        rowMutability: cs.rowMutability || 'fully_editable',
        inlineEdit: cs.inlineEdit || null,
        columns: cs.columns || null
      })
    }
  }

  if (hasAuditAspect.value && !sections.some(s => s.type === 'history') && !isAddMode) {
    sections.push({
      key: 'audit-log',
      label: '操作日志',
      icon: 'history',
      type: 'history'
    })
  }

  console.log(`[DetailPage] [SYMBOL] computedSections 结果: ${sections.length} 个 section, 模式=${effectiveMode.value}, isEditing=${isEditing}`, sections.map(s => ({ key: s.key, type: s.type, fieldGroups: s.fieldGroups?.length, assocName: s.assocName })))

  return sections
})

watch(() => props.modelValue, (val) => {
  if (val) {
    loadEntityMeta()
  } else {
    internalEditing.value = false
  }
})

onMounted(() => {
  if (effectiveMode.value === 'add') {
    data.value = {}
    if (selectedVersionId.value) {
      data.value.version_id = selectedVersionId.value
    }
    loading.value = false
  } else {
    fetchData()
  }
  loadEntityMeta()
})

watch(() => [props.objectType, props.id, props.mode, props.createMode, props.editMode], () => {
  metaLoaded.value = false
  entityMeta.value = null
  internalEditing.value = effectiveMode.value === 'add' || effectiveMode.value === 'edit'
  if (effectiveMode.value === 'add') {
    data.value = {}
    if (selectedVersionId.value) {
      data.value.version_id = selectedVersionId.value
    }
    loading.value = false
  } else {
    fetchData()
  }
  loadEntityMeta()
}, { immediate: true })

watch(selectedVersionId, () => {
  if ((effectiveMode.value === 'add' || props.id === 'new') && selectedVersionId.value && !data.value.version_id) {
    data.value.version_id = selectedVersionId.value
  }
})

async function fetchData(options = {}) {
  if (props.mode === 'add' || props.id === 'new' || !props.id) {
    data.value = {}
    loading.value = false
    return
  }
  
  loading.value = true
  error.value = null

  try {
    console.debug('[DetailPage] fetchData, objectType:', props.objectType, 'id:', props.id)
    const result = await boService.read(props.objectType, props.id, options)
    if (result.success) {
      console.debug('[DetailPage] fetchData success, data:', result.data)
      data.value = result.data
      emit('loaded', result.data)
    } else {
      error.value = result.message || '加载数据失败'
    }
  } catch (e) {
    console.error('DetailPage fetchData error:', e)
    error.value = '网络错误，请稍后重试'
  } finally {
    loading.value = false
  }
}

async function handleRefresh(payload = {}) {
  console.debug('[DetailPage] handleRefresh called, payload:', payload)
  
  const hasDirectUpdate = payload && payload.newStatus != null && payload.newStatus !== undefined && payload.stateField && data.value
  console.debug('[DetailPage] hasDirectUpdate:', hasDirectUpdate)
  
  if (hasDirectUpdate) {
    console.debug('[DetailPage] Updating status directly:', payload.stateField, '=', payload.newStatus)
    data.value = { ...data.value, [payload.stateField]: payload.newStatus }
    console.debug('[DetailPage] dataStatus after direct update:', dataStatus.value)
  } else {
    console.debug('[DetailPage] Fetching fresh data (forceRefresh)')
    await fetchData({ forceRefresh: true })
    console.debug('[DetailPage] after fetchData, dataStatus:', dataStatus.value)
  }
}

function handleClose() {
  internalEditing.value = false
  emit('update:modelValue', false)
  emit('close')
}

function handleTabChange(tabKey) {
}

function handleFieldUpdate({ key, value }) {
  if (data.value) {
    data.value = { ...data.value, [key]: value }
  }
}

function handleFieldDisplayUpdate({ key, displayValue }) {
  // 同步更新 _display 字段，让 ValueHelpField 在重新挂载时能拿到正确的 initial_options
  if (data.value) {
    data.value = { ...data.value, [`${key}_display`]: displayValue }
  }
}

const objectPageRef = ref(null)

async function handleObjectPageAction({ action }) {
  const key = action.key || action.id

  switch (key) {
    case 'edit':
      internalEditing.value = true
      break

    case 'cancel':
      if (objectPageRef.value?.hasChildUnsavedChanges?.()) {
        try {
          const { ElMessageBox } = await import('element-plus')
          await ElMessageBox.confirm(
            '子列表有未保存的修改，确定要放弃吗？',
            '提示',
            { type: 'warning', confirmButtonText: '放弃', cancelButtonText: '取消' }
          )
        } catch {
          return
        }
        objectPageRef.value?.cancelAllChildMetaLists?.()
      }
      internalEditing.value = false
      if (effectiveMode.value === 'add') {
        emit('close')
      }
      break

    case 'save':
      await handleSave()
      break

    case 'delete':
      await handleDelete()
      break

    default:
  }
}

const SYSTEM_FIELDS = new Set([
  'id', 'type', 'created_at', 'updated_at', 'created_by', 'updated_by',
  'created_date', 'updated_date', 'created_user', 'updated_user',
  'tenant_id'
])

function isSystemField(fieldId) {
  return SYSTEM_FIELDS.has(fieldId.toLowerCase())
}

async function handleSave() {
  saving.value = true
  try {
    const isCreate = effectiveMode.value === 'add' || props.id === 'new'
    const url = isCreate 
      ? `/api/v2/bo/${props.objectType}` 
      : `/api/v2/bo/${props.objectType}/${props.id}`
    const method = isCreate ? 'POST' : 'PUT'

    let payload
    if (isCreate) {
      payload = {}
      const fieldDefs = computedFieldDefs.value
      for (const [key, value] of Object.entries(data.value)) {
        if (isSystemField(key)) continue
        // [FIX] 新建模式下：不过滤 readonly 字段，因为 parent_key/context_field 等
        // readonly_always 字段（如 version_id）在新建时必须提交。后端在 update 时
        // 才会做 readonly 校验。
        const def = fieldDefs[key]
        if (def?.immutable && !isCreate) continue
        if (key === 'can_delete' || key === 'relation_count') continue
        if (['version_name', 'domain_name', 'sub_domain_name', 'service_module_name'].includes(key)) continue
        payload[key] = value
      }
    } else {
      payload = {}
      const fieldDefs = computedFieldDefs.value
      for (const [key, value] of Object.entries(data.value)) {
        if (isSystemField(key)) continue
        const def = fieldDefs[key]
        if (def?.readonly || def?.immutable) continue
        if (!def?.editable) continue
        if (key === 'can_delete' || key === 'relation_count') continue
        payload[key] = value
      }
    }

    const hasChildChanges = objectPageRef.value?.hasChildUnsavedChanges?.()

    if (isCreate && hasChildChanges) {
      const children = objectPageRef.value.collectAllChildDraftCreates()
      const result = await boService.deepInsert(props.objectType, payload, children)

      if (result.success) {
        message.success('创建成功')
        internalEditing.value = false
        const savedData = result.data?.parent || result.data || {}
        data.value = savedData
        emit('saved', savedData)
        emit('created', savedData)
      } else {
        message.error(result.message || '创建失败')
      }
      return
    }

    const result = isCreate
      ? await boService.create(props.objectType, payload)
      : await boService.update(props.objectType, props.id, payload)
    if (result.success) {
      if (objectPageRef.value?.hasChildUnsavedChanges?.()) {
        try {
          await objectPageRef.value.saveAllChildMetaLists()
        } catch (childError) {
          console.error('[DetailPage] Child MetaList save error:', childError)
          message.warning('主对象已保存，但子列表部分保存失败')
        }
      }

      message.success(isCreate ? '创建成功' : '保存成功')
      internalEditing.value = false
      if (!isCreate && props.id) {
        try {
          const refreshResult = await boService.read(props.objectType, props.id, { forceRefresh: true })
          if (refreshResult.success && refreshResult.data) {
            data.value = refreshResult.data
            emit('saved', refreshResult.data)
          } else {
            data.value = result.data || data.value
            emit('saved', result.data)
          }
        } catch {
          data.value = result.data || data.value
          emit('saved', result.data)
        }
      } else {
        data.value = result.data || data.value
        emit('saved', result.data)
        if (isCreate) {
          emit('created', result.data)
        }
      }
    } else {
      message.error(result.message || (isCreate ? '创建失败' : '保存失败'))
    }
  } catch (e) {
    console.error('[DetailPage] Save error:', e)
    message.error('保存请求失败')
  } finally {
    saving.value = false
  }
}

async function handleDelete() {
  try {
    const { ElMessageBox } = await import('element-plus')
    await ElMessageBox.confirm(
      '确定要删除此记录吗？此操作不可恢复。',
      '确认删除',
      { confirmButtonText: '确定删除', cancelButtonText: '取消', type: 'warning' }
    )

    const result = await boService.delete(props.objectType, props.id)
    if (result.success) {
      message.success('删除成功')
      emit('delete')
      handleClose()
    } else {
      message.error(result.message || '删除失败')
    }
  } catch (e) {
    if (e !== 'cancel') {
      message.error('删除请求失败')
    }
  }
}

defineExpose({
  get visibleActions() { return objectPageRef.value?.visibleActions },
  internalEditing,
  handleObjectPageAction,
  handleRefresh
})
</script>

<style scoped lang="scss">
.detail-page {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.dp-loading,
.dp-error,
.dp-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-sm);
  padding: 60px var(--spacing-lg);
  color: var(--color-text-secondary);
  font-size: 14px;

  p {
    margin: 0;
    color: var(--color-text-tertiary);
  }
}

.dp-content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.dp-loading-inline {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-md);
  color: var(--color-text-secondary);
  font-size: 13px;
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
