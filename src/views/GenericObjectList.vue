<template>
  <div class="generic-object-list">
    <MetaListPage
      ref="metaListRef"
      :object-type="objectType"
      :options="listOptions"
      :enable-detail="enableDetail"
      :enable-auto-crud="enableAutoCrud"
      @detail="(payload) => $emit('detail', payload)"
    >
      <template v-for="(_, slotName) in $slots" :key="slotName" #[slotName]="slotProps">
        <slot :name="slotName" v-bind="slotProps" />
      </template>
    </MetaListPage>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { MetaListPage } from '@/components/common/MetaListPage'

defineOptions({ name: 'GenericObjectList' })

const props = defineProps({
  objectType: {
    type: String,
    required: true
  },
  pageSize: {
    type: Number,
    default: 20
  },
  debug: {
    type: Boolean,
    default: false
  },
  enableDetail: {
    type: Boolean,
    default: true
  },
  enableAutoCrud: {
    type: Boolean,
    default: true
  }
})

defineEmits(['detail'])

const metaListRef = ref(null)

const listOptions = computed(() => ({
  autoLoad: true,
  pageSize: props.pageSize,
  debug: props.debug
}))

defineExpose({
  metaListRef
})
</script>

<style scoped>
.generic-object-list {
  height: 100%;
}
</style>
