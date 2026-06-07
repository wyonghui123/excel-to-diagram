<template>
  <MetaDialog
    :visible="visible"
    :meta="versionMeta"
    :entity-data="effectiveVersion"
    @close="$emit('close')"
    @save="$emit('save', $event)"
    @update:visible="$emit('update:visible', $event)"
  />
</template>

<script setup>
import { computed } from 'vue'
import { MetaDialog } from '../../../components/common'
import { versionMeta } from '../meta/entityMeta'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  version: {
    type: Object,
    default: null
  },
  product: {
    type: Object,
    default: () => ({})
  }
})

const effectiveVersion = computed(() => {
  if (props.version) return props.version
  if (props.product?.id) {
    return { product_id: props.product.id }
  }
  return null
})

defineEmits(['close', 'save', 'update:visible'])
</script>
