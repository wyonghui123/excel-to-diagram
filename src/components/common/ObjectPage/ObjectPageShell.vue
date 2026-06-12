<template>
  <div class="object-page" :class="`object-page--${size}`">
    <ObjectPageHeader
      v-if="!hideHeader"
      :title="title"
      :subtitle="subtitle"
      :status="status"
      :status-type="statusType"
      :breadcrumbs="breadcrumbs"
      :show-back-button="showBackButton"
      :actions="processedActions"
      :visible-actions="visibleActions"
      :editing="internalEditing"
      :saving="saving"
      :object-type="objectType"
      :object-id="objectId"
      :show-state-transitions="showStateTransitions"
      :size="size"
      @back="$emit('back')"
      @navigate="$emit('navigate', $event)"
      @action="handleObjectPageAction"
      @refresh="handleRefresh"
    >
      <template #breadcrumb><slot name="breadcrumb" /></template>
      <template #actions><slot name="actions" /></template>
    </ObjectPageHeader>

    <ObjectPageContent
      :sections="sections"
      :form-data="formData"
      :field-defs="effectiveFieldDefs"
      :editing="internalEditing"
      :object-type="objectType"
      :object-id="objectId"
      :card-size="cardSize"
      :value-help-field-keys="valueHelpFieldKeys"
      :enum-field-keys="enumFieldKeys"
      :ui-config="uiConfig"
      :cascade-fields="cascadeFields"
      :is-cascade-field="isCascadeField"
      :get-cascade-parent="getCascadeParent"
      :form-render-key="formRenderKey"
      :hide-header="hideHeader"
      @tab-change="onTabChange"
      @field-update="handleFieldUpdate"
      @field-display-update="emit('field-display-update', $event)"
      @out-mapping="handleOutMapping"
      @update:editing="val => { internalEditing = val; $emit('update:editing', val) }"
      @refresh="$emit('refresh')"
      @open-assign="openAssignDialog"
    >
      <template #headerContent><slot name="headerContent" /></template>
      <template #info><slot name="info" /></template>
      <template v-for="(_, name) in $slots" :key="name" #[name]="slotData">
        <slot :name="name" v-bind="slotData || {}" />
      </template>
    </ObjectPageContent>

    <AssignmentDialog
      v-if="assignDialogState"
      :model-value="assignDialogState.visible"
      :object-type="objectType"
      :object-id="objectId"
      :association-name="assignDialogState.assocName"
      :config="assignDialogState.config"
      :exclude-ids="assignDialogState.excludeIds"
      @success="handleAssignSuccess"
      @update:model-value="(val) => { if (!val) assignDialogState = null }"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, provide } from 'vue'
import ObjectPageHeader from './ObjectPageHeader.vue'
import ObjectPageContent from './ObjectPageContent.vue'
import AssignmentDialog from '../AssignmentDialog/AssignmentDialog.vue'
import metaService from '@/services/metaService'
import boService from '@/services/boService'
// [NEW 2026-06-10] KeyTemplate 集成
import { useKeyTemplateFormSync } from '@/composables/useKeyTemplateFormSync'
import {
  suggestKeyTemplateCode as _suggestKeyTemplateCodeSvc,
  fetchKeyTemplateConfig as _fetchKeyTemplateConfigSvc,
  getCodeFieldPlaceholder as _getCodeFieldPlaceholderSvc,
  getCodeFieldTag as _getCodeFieldTagSvc
} from '@/services/keyTemplateService'

// [NEW 2026-06-10] KeyTemplate 表单脏字段跟踪
const {
  formDirtyFields,
  markFieldDirty,
  resetFieldDirty,
  isFieldDirty,
  clearAll: clearFormDirty
} = useKeyTemplateFormSync()

const props = defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  status: { type: String, default: '' },
  statusType: {
    type: String,
    default: 'default',
    validator: (value) => ['default', 'primary', 'success', 'warning', 'error'].includes(value)
  },
  breadcrumbs: { type: Array, default: () => [] },
  tabs: { type: Array, default: () => [] },
  activeTab: { type: [String, Number], default: null },
  showBackButton: { type: Boolean, default: false },
  size: {
    type: String,
    default: 'md',
    validator: (value) => ['sm', 'md', 'lg'].includes(value)
  },
  sections: { type: Array, default: () => [] },
  formData: { type: Object, default: () => ({}) },
  fieldDefinitions: { type: Object, default: () => ({}) },
  autoLoadMeta: { type: Boolean, default: false },
  cardSize: {
    type: String,
    default: 'sm',
    validator: (value) => ['sm', 'md', 'lg'].includes(value)
  },
  objectType: { type: String, default: null },
  objectId: { type: [String, Number], default: null },
  actions: { type: Array, default: () => [] },
  editing: { type: Boolean, default: false },
  saving: { type: Boolean, default: false },
  cascadeFields: { type: Array, default: () => [] },
  isCascadeField: { type: Function, default: () => false },
  getCascadeParent: { type: Function, default: () => null },
  showStateTransitions: { type: Boolean, default: true },
  hideHeader: { type: Boolean, default: false }
})

const emit = defineEmits(['back', 'navigate', 'tab-change', 'field-update', 'field-display-update',
  'update:editing', 'save', 'cancel', 'delete', 'action', 'refresh', 'apply-defaults'])

const internalEditing = ref(props.editing)

watch(() => props.editing, (val) => {
  internalEditing.value = val
})

// [NEW 2026-06-10] 编辑状态变为 false 时清理脏字段
// 关闭/取消编辑后 formDirtyFields 应清空，避免下次打开残留状态
watch(internalEditing, (val, oldVal) => {
  if (oldVal && !val) {
    clearFormDirty()
    // [FIXED 2026-06-11] 退出编辑模式时清空 parent params 累积缓存
    // 否则下次新建时会复用上次累积的 *_id 值，导致错误的 preview
    _ktParentParamsCache.value = {}
  }
})

const autoFieldDefs = ref({})
const uiConfig = ref(null)
const formRenderKey = ref(0)
const valueHelpFieldKeys = ref(new Set())
const enumFieldKeys = ref(new Set())

// [FIXED 2026-06-11] 累积缓存 key template parent field 值
// 解决 relationship 等多 parent 场景下级联选择时，emit('field-update') 异步
// 导致 props.formData 尚未更新、另一 parent 字段丢失 → API 返回 422
// 原 BUG：仅用 changedKey/changedValue 覆盖，调用 resuggest 时另一 parent 字段缺失
// 修复：每次 handleFieldUpdate 都把当前所有已知 parent 字段值存到缓存，
//   resuggest 用 formData ∪ 缓存 ∪ 触发参数作为最终的 parentParams
const _ktParentParamsCache = ref({})

const effectiveFieldDefs = computed(() => {
  const merged = { ...autoFieldDefs.value }
  for (const key of Object.keys(props.fieldDefinitions)) {
    const propDef = props.fieldDefinitions[key]
    const cleanDef = {}
    if (propDef) {
      for (const k of Object.keys(propDef)) {
        if (propDef[k] !== undefined) {
          cleanDef[k] = propDef[k]
        }
      }
    }
    merged[key] = { ...merged[key], ...cleanDef }
  }
  return merged
})

function _mapFieldTypeToWidget(fieldType) {
  const map = {
    'string': 'el-input',
    'text': 'el-input',
    'integer': 'el-input-number',
    'float': 'el-input-number',
    'boolean': 'el-switch',
    'date': 'el-date-picker',
    'datetime': 'el-date-picker',
    'json': 'el-input'
  }
  return (fieldType || '').toLowerCase() in map ? map[fieldType.toLowerCase()] : 'el-input'
}

async function loadFieldMeta() {
  if (!props.autoLoadMeta || !props.objectType) return
  try {
    const result = await metaService.getUIConfig(props.objectType)
    if (result.success && result.data) {
      uiConfig.value = result.data

      if (result.data.fields) {
        const defs = {}
        const isAddMode = !props.objectId || props.objectId === 'new'
        for (const f of result.data.fields) {
          if (f.visible === false) continue
          if (f.ui?.visible === false) continue
          if (f.hidden_in_detail && !isAddMode) continue
          if (f.hidden_in_form && isAddMode) continue
          // [FIX v1.0.9 2026-06-10] owner 类不可编辑字段在 edit 模式也隐藏
          // 当字段同时设了 hidden_in_form: true + ui.editable: false 时,
          // 表示该字段（如 owner_id）用户永远不应该在 form 中看到,
          // 否则会误以为能修改。应改为使用 transfer action 修改 owner。
          if (!isAddMode && f.hidden_in_form && f.ui?.editable === false) continue

          const semantics = f.semantics || {}
          const isBusinessKey = semantics.business_key === true
          const isComputed = f.computed === true
          const isReadonlyAlways = semantics.readonly_always === true
          // parent_key（自引用外键，如 user_group.parent_id）允许用户修改：
          // 用户可重新指定父组，所以这里不应把 parent_key 当作 immutable。
          const isImmutable = semantics.immutable === true || f.immutable === true
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

          // 优先取顶层 value_help；若缺失但 ui.relation 存在，则按 ui.relation 构造 BO 类型 value_help
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

          // 根据是否有 valueHelp 决定 widget：有 valueHelp 时强制为 value_help（即使 ui.widget 是 select）
          const widget = valueHelp
            ? 'value_help'
            : (f.ui?.widget || _mapFieldTypeToWidget(f.type))

          defs[f.id] = {
            label: f.name || f.id,
            type: f.type || 'text',
            widget,
            required: f.required === true,
            editable: fieldEditable,
            readonly: fieldReadonly,
            immutable: isImmutable,
            placeholder: f.placeholder || f.ui?.placeholder || '',
            options: f.enum_values || f.options || undefined,
            valueHelp
          }
        }
        autoFieldDefs.value = defs
        const vhKeys = new Set()
        const enumKeys = new Set()
        for (const [key, d] of Object.entries(defs)) {
          if (d.widget === 'value_help' || d.valueHelp?.source?.type === 'bo' || d.valueHelp?.source?.type === 'enum') {
            vhKeys.add(key)
          } else if (d.options?.length) {
            enumKeys.add(key)
          }
        }
        valueHelpFieldKeys.value = vhKeys
        enumFieldKeys.value = enumKeys
        formRenderKey.value++

        if (isAddMode && result.data.fields) {
          const defaults = {}
          for (const f of result.data.fields) {
            if (f.default !== undefined && f.default !== null && props.formData[f.id] === undefined) {
              defaults[f.id] = f.default
            }
          }
          if (Object.keys(defaults).length > 0) {
            emit('apply-defaults', defaults)
          }
        }
      }
    }
  } catch (e) {
    console.warn('[ObjectPage] Failed to load field metadata:', e)
  }
}

onMounted(() => {
  if (props.autoLoadMeta) {
    loadFieldMeta()
  }
})

const ACTION_SEMANTIC_MAP = {
  'edit': 'start_edit', 'create': 'start_edit', 'update': 'start_edit', 'modify': 'start_edit',
  'save': 'save', 'submit': 'save', 'confirm': 'save',
  'cancel': 'cancel_edit', 'close': 'cancel_edit',
  'delete': 'delete', 'remove': 'delete', 'destroy': 'delete'
}

function inferSemantic(actionKey) {
  if (!actionKey) return 'default'
  const key = String(actionKey).toLowerCase()
  return ACTION_SEMANTIC_MAP[key] || key
}

const processedActions = computed(() => {
  if (!props.actions || props.actions.length === 0) return []
  return (props.actions || []).map(action => ({
    key: action.id || action.key,
    label: action.label,
    icon: action.icon,
    semantic: action.semantic || inferSemantic(action.id || action.key),
    variant: mapActionVariant(action.variant || action.type, action.id || action.key),
    confirmMessage: action.confirm || action.confirmMessage,
    confirmTitle: action.confirmTitle || '确认操作',
    container: action.container
  }))
})

const visibleActions = computed(() => {
  if (internalEditing.value) {
    return processedActions.value.filter(a =>
      a.semantic === 'save' || a.semantic === 'cancel_edit'
    )
  }
  return processedActions.value.filter(a =>
    a.semantic !== 'save' && a.semantic !== 'cancel_edit'
  )
})

function mapActionVariant(variant, actionKey) {
  const map = {
    'primary': 'primary',
    'success': 'success',
    'warning': 'warning',
    'danger': 'danger',
    'info': 'info',
    'default': 'secondary',
    'text': 'text'
  }
  if (!variant) {
    const semantic = inferSemantic(actionKey)
    if (semantic === 'save' || semantic === 'start_edit') return 'primary'
    if (semantic === 'delete') return 'danger'
    return 'secondary'
  }
  return map[variant] || 'secondary'
}

function handleObjectPageAction(action) {
  const semantic = action.semantic || inferSemantic(action.key)

  if (semantic === 'refresh') {
    formRenderKey.value++
    emit('refresh', action)
    return
  }

  if (semantic === 'start_edit') {
    emit('update:editing', true)
    emit('action', { action, editing: true })
    return
  }
  if (semantic === 'cancel_edit') {
    emit('cancel')
    emit('action', { action, editing: false })
    return
  }
  if (semantic === 'save') {
    emit('save')
    emit('action', { action })
    return
  }
  if (semantic === 'delete') {
    emit('delete')
    emit('action', { action })
    return
  }
  emit('action', { action })
}

function handleRefresh(payload = {}) {
  console.debug('[ObjectPageShell] handleRefresh, payload:', payload)
  formRenderKey.value++
  emit('refresh', payload)
}

function handleFieldUpdate({ key, value }) {
  emit('field-update', { key, value })

  // [NEW 2026-06-10][FIXED 2026-06-11] 仅 key template 实际依赖的 parent_id 字段才触发 resuggest
  // 原逻辑：所有 *_id 字段变化都触发 → BUG: 选 domain_id 也触发，但 service_module_code 未填，
  //   scope 退化到 "default"，生成的 code 是裸序列号（如 "44"）而不是 "PUM01"。
  // 修复：根据 key_template.segments 中 parent_field.source 推导出实际的 _id 字段名。
  //   例：source=service_module_code → 对应的 _id 字段 = service_module_id
  // 附加条件（不变）：
  //   1. 仅在新建模式（isAddMode）
  //   2. 仅当 code 字段未被用户编辑（formDirtyFields 中无 'code'）
  if (key && value && isAddMode.value && !isFieldDirty('code')) {
    const parentFields = _ktParentIdFields()
    if (Array.isArray(parentFields) ? parentFields.includes(key) : key === parentFields) {
      // [FIXED 2026-06-11] 写入 parent params 累积缓存。
      // 多 parent 场景（如 relationship: source_bo_id + target_bo_id）下，
      // emit 后 props.formData 异步更新，单次只能保证一个字段，
      // 必须从所有先前触发中累积，才能在任一字段触发时提供完整 parent_params。
      _ktParentParamsCache.value = {
        ..._ktParentParamsCache.value,
        [key]: value
      }
      // [FIXED 2026-06-11] 传入 key/value：emit('field-update') 后 props.formData 可能尚未更新
      // （Vue 事件是异步的），直接用 value 参数覆盖，避免读到旧值
      triggerKeyTemplateResuggest(key, value)
    }
  }
}

/**
 * [FIXED 2026-06-11] 从 key_template schema 推导出前端实际监听的 parent_id 字段名。
 *
 * 原理：segments 中的 parent_field.source 是后端字段名（如 service_module_code），
 *   前端表单中对应的字段是 service_module_id（用户在下拉列表中选中的是 ID）。
 *   对于 relationship，parent_field 有 source_code 和 target_code 两个，
 *   对应 source_bo_id 和 target_bo_id。
 *
 * @returns {string|string[]|null} parent_id 字段名（或数组）；无 key_template 时返回 null
 */
function _ktParentIdFields() {
  if (props.objectType === 'business_object') return 'service_module_id'
  if (props.objectType === 'relationship') return ['source_bo_id', 'target_bo_id']
  return null
}

/**
 * 触发 key template 重新建议（详情表单场景）
 * [NEW 2026-06-10] 父对象变化时自动调用
 *
 * @param {string} [changedKey] - [FIXED 2026-06-11] 触发变化的字段名，用于强制覆盖 formData 中的值
 * @param {any} [changedValue] - 字段的新值
 */
async function triggerKeyTemplateResuggest(changedKey, changedValue) {
  if (!props.objectType) return
  // 构造一个临时 newRow 用于 service 调用（包含当前 formData 的 *_id 字段）
  // [FIXED 2026-06-11] 三层覆盖保证多 parent 场景下所有字段都已就位：
  //   1) 基础：props.formData
  //   2) 累积缓存：_ktParentParamsCache（保留先前 trigger 时存的所有 parent 值）
  //   3) 当次参数：changedKey/changedValue（最新一次的值）
  // 这样在 relationship 场景下，先选 source 再选 target 时，
  //   第2次 resuggest 仍能拿到 source_bo_id（从缓存）+ target_bo_id（本次参数）。
  const tempNewRow = {
    id: props.objectId || 'new',
    _objectType: props.objectType,
    ...props.formData,
    ..._ktParentParamsCache.value
  }
  if (changedKey && changedValue !== undefined) {
    tempNewRow[changedKey] = changedValue
  }
  // 详情表单场景：filterValues 空、draftValues 空 Map
  // 关键：传入 formDirtyFields 作为保护（即使上一步判定已过，service 内还会再判一次）
  const result = await _suggestKeyTemplateCodeSvc(
    tempNewRow,
    {},
    new Map(),
    boService,
    { debug: false },
    () => false,
    formDirtyFields.value  // [NEW] 详情表单脏字段集合
  )
  if (result.success && result.code) {
    // 写回 formData.code
    props.formData.code = result.code
  } else if (result.error) {
    console.warn('[ObjectPageShell] key template resuggest failed:', result.error)
  }
}

/**
 * 用户点击"重置为自动生成"按钮
 * [NEW 2026-06-10] 选项 A 交互
 */
async function onCodeReset() {
  resetFieldDirty('code')
  // 重新建议（此时 formDirtyFields 已清空，会走应用分支）
  await triggerKeyTemplateResuggest()
}

function handleOutMapping(updates) {
  if (!updates || typeof updates !== 'object') return
  for (const [key, value] of Object.entries(updates)) {
    props.formData[key] = value
    emit('field-update', { key, value })
  }
}

function onTabChange(tabKey) {
  emit('tab-change', tabKey)
}

const assignDialogState = ref(null)

const childMetaListRefs = ref({})

// [NEW 2026-06-10] 提供 KeyTemplate 表单上下文给子组件（ObjectPageField）
// 通过 provide/inject 避免在 Content / FieldGroupSection 中转 props
const isAddMode = computed(() => !props.objectId || props.objectId === 'new')

// [FIX v1.1 2026-06-11] isCodeAutoManaged 判定需要等待后端确认 key_template.enabled
// 原"启发式判断"导致 role/user_group/permission 等无 key_template 的对象
// 误显示"自动"标签（因为它们的 code 字段可编辑）。现在只有后端明确 enabled=true
// 时才显示。
const keyTemplateLoaded = ref(false)
const keyTemplateEnabled = ref(false)
const codeFieldUserEditable = ref('auto_or_manual')
const codeFieldPlaceholderRef = ref('')
const codeFieldTagTextRef = ref('')
const codeFieldTagTypeRef = ref('info')

const isCodeAutoManaged = computed(() => {
  if (!isAddMode.value) return false
  // 必须等后端确认才显示（避免 role 等无 key_template 对象误显示）
  if (!keyTemplateLoaded.value) return false
  if (!keyTemplateEnabled.value) return false
  const codeDef = effectiveFieldDefs.value?.code
  if (!codeDef) return false
  // code 字段在 add 模式下可编辑（且非只读）→ 启用 key template 交互
  return codeDef.readonly !== true && codeDef.editable !== false
})

async function loadKeyTemplateConfig() {
  const objectType = props.objectType || (props.routeContext && props.routeContext.objectType)
  if (!isAddMode.value || !objectType) {
    keyTemplateLoaded.value = true
    keyTemplateEnabled.value = false
    codeFieldPlaceholderRef.value = ''
    codeFieldTagTextRef.value = ''
    return
  }
  try {
    const result = await _fetchKeyTemplateConfigSvc(objectType, boService)
    const enabled = !!result?.success && result.enabled === true
    keyTemplateEnabled.value = enabled
    if (enabled) {
      const userEditable = result.user_editable || 'auto_or_manual'
      codeFieldUserEditable.value = userEditable
      codeFieldPlaceholderRef.value = _getCodeFieldPlaceholderSvc(userEditable)
      const tag = _getCodeFieldTagSvc(userEditable)
      codeFieldTagTextRef.value = tag.text
      codeFieldTagTypeRef.value = tag.type
    } else {
      codeFieldPlaceholderRef.value = ''
      codeFieldTagTextRef.value = ''
    }
  } catch (e) {
    keyTemplateEnabled.value = false
    codeFieldPlaceholderRef.value = ''
    codeFieldTagTextRef.value = ''
    console.debug('[ObjectPageShell] loadKeyTemplateConfig failed:', e)
  } finally {
    keyTemplateLoaded.value = true
  }
}

watch(
  () => [isAddMode.value, props.objectType],
  () => { loadKeyTemplateConfig() },
  { immediate: true }
)

provide('keyTemplateContext', {
  isCodeAutoManaged,
  isFieldDirty,
  markFieldDirty,
  onCodeReset,
  // [NEW v1.1] user_editable 相关 UI 提示
  codeFieldPlaceholder: codeFieldPlaceholderRef,
  codeFieldTagText: codeFieldTagTextRef,
  codeFieldTagType: codeFieldTagTypeRef
})

provide('registerMetaListRef', (sectionKey, ref) => {
  if (ref && childMetaListRefs.value[sectionKey] !== ref) {
    childMetaListRefs.value[sectionKey] = ref
  }
})

function openAssignDialog(section) {
  console.debug('[ObjectPageShell] openAssignDialog called with section:', section)
  const assocConfig = uiConfig.value?.associations?.find(a => a.name === section.assocName)
  console.debug('[ObjectPageShell] assocConfig:', assocConfig)
  const metaListRef = childMetaListRefs.value[section.key]
  const currentItems = metaListRef?.data || []
  const targetKey = assocConfig?.target_key
  const excludeIds = targetKey
    ? (currentItems || []).map(item => item[targetKey] ?? item.id).filter(id => id != null && !String(id).includes(':'))
    : (currentItems || []).map(item => item.id).filter(id => id != null && !String(id).includes(':'))
  assignDialogState.value = {
    visible: true,
    assocName: section.assocName,
    sectionKey: section.key,
    config: assocConfig || {},
    excludeIds
  }
  console.debug('[ObjectPageShell] assignDialogState set:', assignDialogState.value)
}

async function handleAssignSuccess(items) {
  const sectionKey = assignDialogState.value?.sectionKey
  assignDialogState.value = null
  if (sectionKey) {
    boService._clearCache(props.objectType)
    const metaListRef = childMetaListRefs.value[sectionKey]
    if (metaListRef?.refresh) {
      await metaListRef.refresh()
    }
  }
  emit('refresh')
}

function saveAllChildMetaLists() {
  const refs = Object.values(childMetaListRefs.value).filter(Boolean)
  const results = []
  for (const mlRef of refs) {
    const hasChanges = typeof mlRef?.hasUnsavedChanges === 'object'
      ? mlRef.hasUnsavedChanges?.value
      : mlRef?.hasUnsavedChanges
    if (hasChanges) {
      results.push(Promise.resolve().then(() => mlRef.saveDraftValues()).then(r => ({ success: true })).catch(e => ({ success: false, error: e })))
    }
  }
  return Promise.all(results)
}

function cancelAllChildMetaLists() {
  const refs = Object.values(childMetaListRefs.value).filter(Boolean)
  for (const mlRef of refs) {
    if (mlRef?.cancelInlineEdit) {
      mlRef.cancelInlineEdit()
    }
    const editMode = typeof mlRef?.inlineEditMode === 'object'
      ? mlRef.inlineEditMode
      : mlRef?.inlineEditMode
    if (editMode) {
      if (typeof editMode === 'object' && 'value' in editMode) {
        editMode.value = false
      }
    }
  }
}

function hasChildUnsavedChanges() {
  const refs = Object.values(childMetaListRefs.value).filter(Boolean)
  return refs.some(mlRef => {
    const hasChanges = typeof mlRef?.hasUnsavedChanges === 'object'
      ? mlRef.hasUnsavedChanges?.value
      : mlRef?.hasUnsavedChanges
    return hasChanges
  })
}

function collectAllChildDraftCreates() {
  const result = {}
  const sections = props.sections || []
  for (const section of sections) {
    if (!section.assocName && !section.association) continue

    const childObjectType = section.association
    if (!childObjectType) continue

    const mlRef = childMetaListRefs.value[section.key]
    if (!mlRef) continue

    if (typeof mlRef.getDraftCreates !== 'function') continue

    const creates = mlRef.getDraftCreates()
    if (creates && creates.length > 0) {
      result[childObjectType] = creates
    }
  }
  return result
}

defineExpose({
  saveAllChildMetaLists,
  cancelAllChildMetaLists,
  hasChildUnsavedChanges,
  collectAllChildDraftCreates,
  internalEditing,
  visibleActions,
  handleObjectPageAction
})
</script>

<style scoped>
.object-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--color-bg-layout);
  overflow: hidden;
}

.object-page__breadcrumb-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  flex: 1;
}

.object-page__title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.object-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary);
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.object-subtitle {
  margin: 0;
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding-left: 8px;
  border-left: 1px solid var(--color-border-secondary);
}

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

.op-section--always {
  margin-bottom: var(--spacing-sm);
  background: var(--color-bg-container);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  overflow: hidden;
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

.op-list-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 120px;
  color: var(--color-text-tertiary);
  gap: var(--spacing-sm);
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

.op-card--collapsed {
  border-left: 3px dashed var(--color-border-secondary) !important;
  background: var(--color-bg-tertiary) !important;
}

.op-collapse-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  color: var(--color-text-secondary);
  transition: color 0.2s;
}

.op-collapse-trigger:hover {
  color: var(--color-primary);
}

.op-collapse-hint {
  font-size: 12px;
  color: var(--color-primary);
  font-weight: 500;
  cursor: pointer;
  margin-left: auto;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  transition: background-color 0.2s;
}

.op-collapse-hint:hover {
  background: var(--color-primary-bg);
}

.object-page__sections :deep(.app-card__body) {
  padding: var(--spacing-sm) !important;
}

.object-page__sections :deep(.app-card__header) {
  padding: 8px 12px !important;
  font-size: 13px !important;
  font-weight: 600 !important;
  color: var(--color-text-primary) !important;
  background: var(--color-bg-tertiary);
  border-bottom: 1px solid var(--color-border-secondary);
}

.op-fg-body {
  display: grid;
  gap: 12px 24px;
  padding: var(--spacing-md);
  min-height: auto;
  max-width: 960px;
}

.op-grid-1 {
  grid-template-columns: 1fr;
}

.op-grid-2 {
  grid-template-columns: repeat(2, minmax(200px, 1fr));
}

.op-grid-3 {
  grid-template-columns: repeat(3, minmax(160px, 1fr));
}

.op-grid-4 {
  grid-template-columns: repeat(4, minmax(140px, 1fr));
}

.op-vertical {
  grid-template-columns: 1fr;
  gap: 4px;
  padding: 12px 8px;
}

.op-field {
  display: flex;
  flex-direction: row;
  align-items: baseline;
  gap: 12px;
  min-width: 0;
  width: 100%;
  padding: 4px 0;
}

.op-field > .el-input,
.op-field > .el-select,
.op-field > .el-input-number,
.op-field > .el-date-editor {
  flex: 1 !important;
  min-width: 0 !important;
  max-width: none !important;
  width: auto !important;
}

.op-field > .el-input .el-input__wrapper,
.op-field > .el-select .el-input__wrapper {
  width: auto !important;
  max-width: none !important;
}

.op-field label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  font-weight: 500;
  flex-shrink: 0;
  white-space: nowrap;
  min-width: 70px;
}

.op-field .el-textarea {
  display: flex !important;
  flex-direction: column !important;
  width: 100% !important;
  max-width: 100%;
  min-height: 60px !important;
}

.op-field .el-textarea .el-textarea__inner {
  min-height: 60px !important;
  width: 100% !important;
}

.op-field .el-textarea label {
  width: 100% !important;
}

.op-field.op-span-2 {
  grid-column: span 2;
}

.op-field.op-span-full {
  grid-column: 1 / -1;
}

.op-required {
  color: var(--color-error);
  font-weight: 700;
}

.op-field-value {
  flex: 1;
  font-size: 14px;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.6;
}

@media (max-width: 1200px) {
  .op-grid-4 { grid-template-columns: repeat(3, 1fr); }
  .op-grid-3 { grid-template-columns: repeat(3, 1fr); }
}

@media (max-width: 900px) {
  .op-grid-4 { grid-template-columns: repeat(2, 1fr); }
  .op-grid-3 { grid-template-columns: repeat(2, 1fr); }
  .op-grid-2 { grid-template-columns: repeat(2, 1fr); }
}

@media (max-width: 768px) {
  .object-page__header { padding: var(--spacing-xs) var(--spacing-sm); }
  .object-page__sections { padding: var(--spacing-xs) var(--spacing-sm); }
  .object-page__anchor-bar { padding: 0 var(--spacing-sm); }

  .op-grid-4 { grid-template-columns: 1fr; }
  .op-grid-3 { grid-template-columns: 1fr; }
  .op-grid-2 { grid-template-columns: 1fr; }
}

.op-audit-log-section {
  padding: var(--spacing-sm) 0;
}

.op-association-section {
  padding: var(--spacing-sm) 0;
  min-height: 200px;
}

.op-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-xl);
  color: var(--color-text-secondary);
  text-align: center;
}
</style>
