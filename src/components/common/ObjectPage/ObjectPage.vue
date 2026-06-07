<template>
  <ObjectPageShell ref="shellRef" v-bind="$props" @back="$emit('back')" @navigate="$emit('navigate', $event)" @tab-change="$emit('tab-change', $event)" @field-update="$emit('field-update', $event)" @field-display-update="$emit('field-display-update', $event)" @update:editing="$emit('update:editing', $event)" @save="$emit('save')" @cancel="$emit('cancel')" @delete="$emit('delete')" @action="$emit('action', $event)" @refresh="$emit('refresh')" />
</template>

<script setup>
import { ref } from 'vue'
import ObjectPageShell from './ObjectPageShell.vue'

const shellRef = ref(null)

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

defineEmits(['back', 'navigate', 'tab-change', 'field-update', 'field-display-update',
  'update:editing', 'save', 'cancel', 'delete', 'action', 'refresh'])

/**
 * 判断字段是否为 FK（外键/关联）字段。
 * 判定规则：字段定义中包含 valueHelp，且 valueHelp.source.type === 'bo'。
 */
function isFkField(fieldKey) {
  const fieldDef = props.fieldDefinitions?.[fieldKey]
  if (!fieldDef?.valueHelp?.source) return false
  return fieldDef.valueHelp.source.type === 'bo'
}

/**
 * 获取 FK 字段关联的目标 BO 类型。
 * 非 FK 字段或缺少 target_bo 时返回 null。
 */
function getFkTargetObjectType(fieldKey) {
  const fieldDef = props.fieldDefinitions?.[fieldKey]
  if (!fieldDef?.valueHelp?.source) return null
  return fieldDef.valueHelp.source.target_bo || null
}

/**
 * 获取字段的显示值。
 * 优先取 `${key}_display` 或 `${keyName}_name`，否则取原值；null/undefined 返回 ''。
 */
function getFieldDisplayValue(fieldKey) {
  const formData = props.formData || {}
  const displayKey = formData[`${fieldKey}_display`] != null
    ? `${fieldKey}_display`
    : `${fieldKey.replace(/_id$/, '')}_name`
  const displayValue = formData[displayKey]
  if (displayValue) return displayValue
  const value = formData[fieldKey]
  return value == null ? '' : value
}

defineExpose({
  get saveAllChildMetaLists() { return shellRef.value?.saveAllChildMetaLists },
  get cancelAllChildMetaLists() { return shellRef.value?.cancelAllChildMetaLists },
  get hasChildUnsavedChanges() { return shellRef.value?.hasChildUnsavedChanges },
  get collectAllChildDraftCreates() { return shellRef.value?.collectAllChildDraftCreates },
  get visibleActions() { return shellRef.value?.visibleActions },
  get handleObjectPageAction() { return shellRef.value?.handleObjectPageAction },
  isFkField,
  getFkTargetObjectType,
  getFieldDisplayValue
})
</script>
