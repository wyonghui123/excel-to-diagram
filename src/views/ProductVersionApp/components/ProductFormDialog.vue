<template>
  <MetaDialog
    :visible="visible"
    :meta="productMeta"
    :entity-data="product"
    @close="$emit('close')"
    @save="$emit('save', $event)"
    @update:visible="$emit('update:visible', $event)"
  />
</template>

<script setup>
import { MetaDialog } from '../../../components/common'
import { productMeta } from '../meta/entityMeta'

defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  product: {
    type: Object,
    default: null
  }
})

defineEmits(['close', 'save', 'update:visible'])
</script>
