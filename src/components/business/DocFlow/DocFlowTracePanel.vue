<template>
  <div class="doc-flow-trace">
    <p v-if="expanded" class="doc-flow-trace__hint">已按单据头展开 {{ lineCount }} 行</p>
    <el-alert
      v-if="truncated"
      class="doc-flow-trace__alert"
      type="warning"
      :closable="false"
      show-icon
      title="行数过多，结果已截断"
    />

    <h4 class="doc-flow-trace__title">上游来源</h4>
    <el-table v-loading="loading" :data="upstream" size="small" max-height="220">
      <el-table-column label="源单据" prop="peer_bo" width="200" />
      <el-table-column label="源单号" prop="peer_id" width="160" />
      <el-table-column label="源行" prop="peer_item" width="120" />
      <el-table-column label="数量" prop="quantity" width="110" />
      <el-table-column label="规则" prop="rule_id" width="200" />
      <el-table-column label="边数" prop="edge_count" width="90" />
    </el-table>

    <h4 class="doc-flow-trace__title">下游去向</h4>
    <el-table v-loading="loading" :data="downstream" size="small" max-height="220">
      <el-table-column label="目标单据" prop="peer_bo" width="200" />
      <el-table-column label="目标单号" prop="peer_id" width="160" />
      <el-table-column label="目标行" prop="peer_item" width="120" />
      <el-table-column label="数量" prop="quantity" width="110" />
      <el-table-column label="规则" prop="rule_id" width="200" />
      <el-table-column label="边数" prop="edge_count" width="90" />
    </el-table>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { traceDocuments } from '@/services/docFlowService'

const props = defineProps({
  objectType: { type: String, required: true },
  recordId: { type: [String, Number], required: true },
})

const loading = ref(false)
const upstream = ref([])
const downstream = ref([])
const expanded = ref(false)
const lineCount = ref(0)
const truncated = ref(false)

function reset() {
  upstream.value = []
  downstream.value = []
  expanded.value = false
  lineCount.value = 0
  truncated.value = false
}

async function reload() {
  if (!props.recordId) {
    reset()
    return
  }
  loading.value = true
  try {
    // [2026-11-12] 单次调用：后端把头 id 解析为行 id 集合后再查边，
    // 返回 {upstream:{items}, downstream:{items}, expanded, line_scope, truncated}
    const data = await traceDocuments({
      bo: props.objectType,
      id: props.recordId,
    })
    upstream.value = data?.upstream?.items || []
    downstream.value = data?.downstream?.items || []
    expanded.value = data?.expanded === true
    lineCount.value = data?.line_scope?.count || 0
    truncated.value = data?.truncated === true
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
.doc-flow-trace__hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.doc-flow-trace__alert {
  margin-top: 8px;
}
</style>