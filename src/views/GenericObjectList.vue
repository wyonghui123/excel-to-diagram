<template>
  <div class="generic-object-list">
    <MetaListPage
      ref="metaListRef"
      :object-type="objectType"
      :options="listOptions"
      :enable-detail="enableDetail"
      :enable-auto-crud="enableAutoCrud"
      :extra-batch-actions="extraBatchActions"
      @detail="(payload) => $emit('detail', payload)"
      @row-dblclick="handleRowDblClick"
      @batch-action="handleBatchAction"
    >
      <template v-for="(_, slotName) in $slots" :key="slotName" #[slotName]="slotProps">
        <slot :name="slotName" v-bind="slotProps" />
      </template>
    </MetaListPage>

    <DocFlowDerivePanel
      v-if="docFlowRule"
      v-model="deriveVisible"
      :rule-id="deriveRuleId"
      :rule-label="deriveRuleLabel"
      :preselected-ids="derivePreselected"
      @done="refreshList"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { MetaListPage } from '@/components/common/MetaListPage'
import DocFlowDerivePanel from '@/components/business/DocFlow/DocFlowDerivePanel.vue'
import { listRules } from '@/services/docFlowService'

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

// [单据流 2026-11-08] 通用派生入口：规则来自服务端（source_bo 命中当前列表才显示按钮），
//   前端不硬编码规则名 / BO 名。
const docFlowRules = ref([])
const deriveVisible = ref(false)
const deriveRuleId = ref('')
const deriveRuleLabel = ref('')
const derivePreselected = ref([])

const docFlowRule = computed(
  () => docFlowRules.value.find((rule) => rule.source_bo === props.objectType) || null,
)

const extraBatchActions = computed(() => (
  docFlowRule.value
    ? [{ key: 'doc_flow_derive', label: '生成下游单据', variant: 'primary' }]
    : []
))

async function loadDocFlowRules() {
  try {
    const data = await listRules({})
    docFlowRules.value = data.rules || []
  } catch (error) {
    docFlowRules.value = []
  }
}

function openDerivePanel(ids) {
  if (!docFlowRule.value) return
  deriveRuleId.value = docFlowRule.value.rule_id
  deriveRuleLabel.value = '生成下游单据'
  derivePreselected.value = ids || []
  deriveVisible.value = true
}

function handleBatchAction(payload) {
  if (payload?.action?.key === 'doc_flow_derive') {
    openDerivePanel(payload.selectedIds || [])
  }
}

function refreshList() {
  metaListRef.value?.refresh?.()
}

onMounted(loadDocFlowRules)

defineExpose({
  metaListRef
})
</script>

<style scoped>
/* [FIX 2026-10-14 分页器被顶出视口] 本容器只写了 height:100%，没声明
   display:flex —— 子元素 MetaListPage 的 `flex:1` 因此完全失效（flex 属性
   只在父为 flex 容器时生效），它退回按内容高度撑开。
   实测 360x800 业务配置页: meta-list-page 撑到 4115px、卡片列表 3958px，
   分页器被顶到 4212px 处，用户需下滚 3412px 才碰得到分页器，
   看起来像「没有分页」；PC 端同样被顶出视口 263px。
   改为 flex column + min-height:0 后约束链恢复:
   meta-list-page 614px（=容器高）→ 卡片列表自己内部滚动 → 分页器常驻底部。 */
.generic-object-list {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
}
</style>
