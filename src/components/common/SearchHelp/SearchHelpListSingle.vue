<!--
  SearchHelpListSingle - List 单选语义化封装
  ===========================================
  元数据驱动的 SearchHelp 组件库: List 单选
  自动构建 valueHelpConfig, 使用者只需传 targetBo

  Props:
    - visible (Boolean): 弹窗可见性
    - targetBo (String): 目标业务对象 (如 'version', 'domain')
    - valueField (String): 值字段 (默认 'id')
    - displayField (String): 显示字段 (默认 'name')
    - codeField (String): 编码字段 (默认 'code')
    - selectedValue (String|Number): 当前已选值
    - customFetcher (Function): 自定义数据获取器
  Emits:
    - update:visible
    - confirm (Object): { value, display, code, ...selectedItem }
  Usage:
    <SearchHelpListSingle
      v-model:visible="showPicker"
      target-bo="version"
      :selected-value="form.version_id"
      @confirm="onVersionSelected"
    />
-->
<template>
  <SearchHelpDialog
    :visible="visible"
    :value-help-config="config"
    :multiple="false"
    :selected-value="selectedValue"
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
  selectedValue: { type: [String, Number], default: '' },
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
    multiple: false,
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
