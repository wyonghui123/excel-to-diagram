<template>
  <div class="doc-flow-trace">
    <h4 class="doc-flow-trace__title">上游来源</h4>
    <el-table v-loading="loading" :data="upstream" size="small" max-height="220">
      <el-table-column label="源单据" prop="source_bo" width="200" />
      <el-table-column label="源行" prop="source_item" width="160" />
      <el-table-column label="数量" prop="quantity" width="110" />
      <el-table-column label="规则" prop="rule_id" width="200" />
      <el-table-column label="状态" prop="status" width="100" />
    </el-table>

    <h4 class="doc-flow-trace__title">下游去向</h4>
    <el-table v-loading="loading" :data="downstream" size="small" max-height="220">
      <el-table-column label="目标单据" prop="target_bo" width="200" />
      <el-table-column label="目标行" prop="target_item" width="160" />
      <el-table-column label="数量" prop="quantity" width="110" />
      <el-table-column label="规则" prop="rule_id" width="200" />
      <el-table-column label="状态" prop="status" width="100" />
    </el-table>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { listEdges } from '@/services/docFlowService'

const props = defineProps({
  objectType: { type: String, required: true },
  recordId: { type: [String, Number], required: true },
})

const loading = ref(false)
const upstream = ref([])
const downstream = ref([])

async function reload() {
  if (!props.recordId) {
    upstream.value = []
    downstream.value = []
    return
  }
  loading.value = true
  try {
    // [2026-11-12] 后端 /doc-flow/edges 返回 {items, total}（分页规范），不是 {edges}
    const incoming = await listEdges({ target_bo: props.objectType, target_id: props.recordId })
    upstream.value = incoming?.items || []
    const outgoing = await listEdges({ source_bo: props.objectType, source_id: props.recordId })
    downstream.value = outgoing?.items || []
  } finally {
    loading.value = false
  }
}

onMounted(reload)
watch(() => [props.objectType, props.recordId], reload)
</script>

<style scoped>
.doc-flow-trace__title {
  margin: 12px 0 8px;
  font-size: 14px;
  color: var(--el-text-color-primary);
}
</style>