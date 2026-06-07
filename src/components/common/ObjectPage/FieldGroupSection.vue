<template>
  <template v-for="(group, gIdx) in (section.fieldGroups || [])" :key="`${gIdx}-${formRenderKey}`">
    <AppCard :size="cardSize">
      <template #header>
        <span
          v-if="group.collapsed !== undefined"
          class="op-collapse-trigger"
          @click="toggleGroup(group)"
        >
          <AppIcon :name="isGroupExpanded(group) ? 'chevron-down' : 'chevron-right'" :size="14" />
        </span>
        <span>{{ group.title }}</span>
        <el-tag v-if="group.collapsed !== undefined" size="small" type="info" style="margin-left:auto">
          {{ group.fields?.length || 0 }}个字段
        </el-tag>
        <span
          v-if="group.collapsed !== undefined"
          class="op-collapse-hint"
          @click="toggleGroup(group)"
        >{{ isGroupExpanded(group) ? '收起' : '展开' }}</span>
      </template>

      <div v-show="!group.collapsed || isGroupExpanded(group)" :class="['op-fg-body', gridClass(group.layout)]">
        <ObjectPageField
          v-for="fieldKey in (group.fields || [])"
          :key="`${fieldKey}-${formRenderKey}`"
          :field-key="fieldKey"
          :form-data="formData"
          :field-defs="fieldDefs"
          :editing="editing"
          :value-help-field-keys="valueHelpFieldKeys"
          :enum-field-keys="enumFieldKeys"
          :object-type="objectType"
          :object-id="objectId"
          :is-cascade-field="isCascadeField"
          :get-cascade-parent="getCascadeParent"
          :form-render-key="formRenderKey"
          @field-update="$emit('field-update', $event)"
          @field-display-update="$emit('field-display-update', $event)"
          @out-mapping="$emit('out-mapping', $event)"
        />
      </div>
    </AppCard>
  </template>
</template>

<script setup>
import { ref } from 'vue'
import AppCard from '../AppCard/AppCard.vue'
import AppIcon from '../AppIcon/AppIcon.vue'
import ObjectPageField from './ObjectPageField.vue'

const props = defineProps({
  section: {
    type: Object,
    required: true
  },
  formData: {
    type: Object,
    required: true
  },
  fieldDefs: {
    type: Object,
    required: true
  },
  editing: {
    type: Boolean,
    default: false
  },
  valueHelpFieldKeys: {
    type: Set,
    default: () => new Set()
  },
  enumFieldKeys: {
    type: Set,
    default: () => new Set()
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
  formRenderKey: {
    type: Number,
    default: 0
  },
  isCascadeField: {
    type: Function,
    default: () => false
  },
  getCascadeParent: {
    type: Function,
    default: () => null
  }
})

defineEmits(['field-update', 'field-display-update', 'out-mapping'])

const expandedGroups = ref(new Set())

;(props.section.fieldGroups || []).forEach(group => {
  if (group.collapsed) {
    group._expanded = false
  }
})

function getGroupKey(group) {
  return `${props.section?.key}-${group.title}`
}

function toggleGroup(group) {
  const key = getGroupKey(group)
  if (expandedGroups.value.has(key)) {
    expandedGroups.value.delete(key)
  } else {
    expandedGroups.value.add(key)
  }
  expandedGroups.value = new Set(expandedGroups.value)
}

function isGroupExpanded(group) {
  return expandedGroups.value.has(getGroupKey(group))
}

function gridClass(layout) {
  const map = {
    'vertical': 'op-vertical',
    'grid-1': 'op-grid-1',
    'grid-2': 'op-grid-2',
    'grid-3': 'op-grid-3',
    'grid-4': 'op-grid-4'
  }
  return map[layout] || 'op-grid-4'
}
</script>
