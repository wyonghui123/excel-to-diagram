<template>
  <span class="enum-field-display">
    {{ displayValue }}
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  field: {
    type: Object,
    required: true
  },
  record: {
    type: Object,
    required: true
  },
  displayField: {
    type: String,
    default: null
  }
})

const displayValue = computed(() => {
  const displayField = props.displayField || props.field.ui?.display_field || 'name'
  const fieldId = props.field.id
  
  const enumFieldValue = props.record[`${fieldId}_${displayField}`]
  if (enumFieldValue) {
    return enumFieldValue
  }
  
  return props.record[fieldId] || ''
})
</script>

<style scoped>
.enum-field-display {
  display: inline-block;
}
</style>
