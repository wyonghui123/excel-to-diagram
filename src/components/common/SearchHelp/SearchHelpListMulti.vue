<!--
  SearchHelpListMulti - List 多选语义化封装
  ===========================================
  元数据驱动的 SearchHelp 组件库: List 多选

  Props:
    - visible (Boolean): 弹窗可见性
    - targetBo (String): 目标业务对象 (如 'version', 'domain')
    - valueField / displayField / codeField: 字段映射
    - selectedValue (Array): 当前已选值 (ID 数组)
    - externalSelectedItems (Array): 已选完整对象 (用于 Delta 显示)
    - customFetcher (Function): 自定义数据获取器
  Emits:
    - update:visible
    - confirm (Array): [{ value, display, code }, ...]
  Usage:
    <SearchHelpListMulti
      v-model:visible="showPicker"
      target-bo="domain"
      :selected-value="selectedDomainIds"
      @confirm="onDomainsSelected"
    />
-->
<template>
  <SearchHelpDialog
    :visible="visible"
    :value-help-config="config"
    :multiple="true"
    :selected-value="selectedValue"
    :external-selected-items="externalSelectedItems"
    :custom-fetcher="customFetcher"
    @update:visible="$emit('update:visible', $event)"
    @confirm="$emit('confirm', $event)"
  />
</template>

<script setup>
import { computed } from 'vue'
import SearchHelpDialog from '../SearchHelpDialog.vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  targetBo: { type: String, required: true },
  valueField: { type: String, default: 'id' },
  displayField: { type: String, default: 'name' },
  codeField: { type: String, default: 'code' },
  selectedValue: { type: Array, default: () => [] },
  externalSelectedItems: { type: Array, default: () => [] },
  customFetcher: { type: Function, default: null },
})

defineEmits(['update:visible', 'confirm'])

const config = computed(() => ({
  source: {
    type: 'bo',
    target_bo: props.targetBo,
    value_field: props.valueField,
    display_field: props.displayField,
    code_field: props.codeField,
  },
  behavior: {
    validation: true,
    binding_strength: 'strict',
    multiple: true,
  },
  presentation: {
    display_mode: 'flat',
    display_format: `{${props.codeField}} - {${props.displayField}}`,
    columns: [
      { field: props.codeField, label: '编码', width: 120 },
      { field: props.displayField, label: '名称', width: 200 },
    ],
  },
}))
</script>
