<template>
  <MetaTable
    :columns="versionColumns"
    :data="versions"
    :actions="tableActions"
    :loading="loading"
    :search-placeholder="'搜索版本...'"
    :empty-type="'folder'"
    :empty-title="'暂无版本数据'"
    :empty-description="'点击上方按钮新增版本'"
    @action="handleAction"
  />
</template>

<script setup>
import { computed } from 'vue'
import { MetaTable } from '../../../components/common'
import { versionMeta } from '../meta/entityMeta'

const props = defineProps({
  versions: {
    type: Array,
    default: () => []
  },
  product: {
    type: Object,
    default: () => ({})
  },
  loading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['create', 'edit', 'delete', 'open-arch-data', 'view-history'])

const versionColumns = computed(() => versionMeta.tableColumns)

const tableActions = computed(() => [
  ...versionMeta.actions
])

function handleAction({ key, type, row }) {
  if (type === 'header') {
    emit(key)
  } else {
    emit(key, row)
  }
}
</script>
