<!--
  SearchHelpTreeSingle - Tree 单选语义化封装
  ===========================================
  元数据驱动的 SearchHelp 组件库: Tree 单选
  适用于 permission_dimension 类型 (product/version/domain/sub_domain)

  Props:
    - visible (Boolean): 弹窗可见性
    - dimensionId (String): 维度 ID (如 'sub_domain', 'domain')
    - selectedValue (String|Number): 当前已选值
  Emits:
    - update:visible
    - confirm (Object): { value, display, code, node: { id, name, type, ancestorPath } }
  Usage:
    <SearchHelpTreeSingle
      v-model:visible="showPicker"
      dimension-id="domain"
      :selected-value="form.domain_id"
      @confirm="onDomainSelected"
    />
-->
<template>
  <SearchHelpDialog
    :visible="visible"
    :value-help-config="config"
    :multiple="false"
    :selected-value="selectedValue"
    @update:visible="$emit('update:visible', $event)"
    @confirm="$emit('confirm', $event)"
  />
</template>

<script setup>
import { computed } from 'vue'
import SearchHelpDialog from '../SearchHelpDialog.vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  dimensionId: { type: String, required: true },
  selectedValue: { type: [String, Number], default: '' },
})

defineEmits(['update:visible', 'confirm'])

const config = computed(() => ({
  source: {
    type: 'bo',
    target_bo: props.dimensionId,
    value_field: 'id',
    display_field: 'name',
    code_field: 'code',
  },
  behavior: {
    validation: true,
    binding_strength: 'strict',
    multiple: false,
  },
  presentation: {
    display_mode: 'tree',
    columns: [
      { field: 'code', label: '编码', width: 120 },
      { field: 'name', label: '名称', width: 200 },
    ],
  },
}))
</script>
