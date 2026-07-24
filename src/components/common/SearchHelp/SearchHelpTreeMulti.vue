<!--
  SearchHelpTreeMulti - Tree 多选语义化封装
  ===========================================
  元数据驱动的 SearchHelp 组件库: Tree 多选
  适用于 management_dimension 类型 (product/version/domain/sub_domain)

  Props:
    - visible (Boolean): 弹窗可见性
    - dimensionId (String): 维度 ID (如 'sub_domain', 'domain')
    - selectedValue (Array): 当前已选值 (ID 数组)
    - externalSelectedItems (Array): 已选完整对象 (用于 Delta 显示)
  Emits:
    - update:visible
    - confirm (Array): [{ value, display, code, node: { id, name, type } }, ...]
  Usage:
    <SearchHelpTreeMulti
      v-model:visible="showPicker"
      dimension-id="sub_domain"
      :selected-value="selectedSubDomainIds"
      @confirm="onSubDomainsSelected"
    />
-->
<template>
  <SearchHelpDialog
    :visible="visible"
    :value-help-config="config"
    :multiple="true"
    :selected-value="selectedValue"
    :external-selected-items="externalSelectedItems"
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
  selectedValue: { type: Array, default: () => [] },
  externalSelectedItems: { type: Array, default: () => [] },
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
    multiple: true,
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
