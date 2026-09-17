<template>
  <div class="generic-object-list">
    <MetaListPage
      ref="metaListRef"
      :object-type="objectType"
      :options="listOptions"
      :enable-detail="enableDetail"
      :enable-auto-crud="enableAutoCrud"
      @detail="(payload) => $emit('detail', payload)"
      @row-dblclick="handleRowDblClick"
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

// [FIX 2026-06-29] 行双击触发 detail action (与点击 detail 按钮行为一致)
//   - Spec: docs/specs/useMetaList-refactor/spec-base-v1.0.0.md #15
//   - Batch2 Agent dd01708 在 MetaListPage 加了 emit, 但 4 个 consumer 都没监听
function handleRowDblClick({ row }) {
  if (!row) return
  metaListRef.value?.onRowAction?.({ action: { key: 'detail' }, row })
}

defineExpose({
  metaListRef
})
</script>

<style scoped>
.generic-object-list {
  height: 100%;
}
</style>
