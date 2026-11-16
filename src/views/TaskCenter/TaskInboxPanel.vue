<template>
  <AppCard class="task-inbox-panel">
    <template #header>
      <div class="tip-header">
        <span class="tip-title">我的待办</span>
        <AppButton @click="reload">刷新</AppButton>
      </div>
    </template>

    <div class="tip-buckets">
      <button
        v-for="b in buckets"
        :key="b.key"
        :data-test="`bucket-tab-${b.key}`"
        class="tip-bucket"
        :class="{ active: activeBucket === b.key }"
        @click="selectBucket(b.key)"
      >
        {{ b.label }}
        <span class="tip-badge">{{ b.count }}</span>
      </button>
    </div>

    <div v-if="approvalRows.length" data-test="batch-bar" class="tip-batch">
      <el-checkbox
        :model-value="allSelected"
        :indeterminate="selectedIds.length > 0 && !allSelected"
        data-test="batch-select-all"
        @change="toggleSelectAll"
      >
        待审批 {{ approvalRows.length }} 项
      </el-checkbox>
      <el-input
        v-model="batchComment"
        class="tip-batch-comment"
        size="small"
        clearable
        placeholder="审批意见（驳回必填）"
      />
      <AppButton
        data-test="batch-approve"
        size="sm"
        :disabled="!selectedIds.length || !!batchRunning"
        :loading="batchRunning === 'approve'"
        @click="runBatch('approve')"
      >
        批量通过
      </AppButton>
      <AppButton
        data-test="batch-reject"
        variant="danger"
        size="sm"
        :disabled="!selectedIds.length || !!batchRunning"
        :loading="batchRunning === 'reject'"
        @click="runBatch('reject')"
      >
        批量驳回
      </AppButton>
    </div>
    <div
      v-if="batchMessage"
      data-test="batch-result"
      class="tip-batch-result"
      :class="{ 'tip-error': batchFailed }"
    >
      <span>{{ batchMessage }}</span>
      <AppButton
        v-if="batchRetryableIds.length"
        data-test="batch-retry"
        size="xs"
        @click="retryBatch"
      >
        重试失败项
      </AppButton>
    </div>
    <ul
      v-if="batchFailedList.length"
      data-test="batch-fail-list"
      class="tip-batch-fail-list"
    >
      <li v-for="item in batchFailedList" :key="item.task_id" data-test="batch-fail-item">
        {{ item.task_id }}：{{ item.message || '未知原因' }}<span v-if="item.httpStatus">（{{ item.httpStatus }}）</span><span v-if="item.retryable"> · 可重试</span>
      </li>
    </ul>

    <div v-if="loading" data-test="loading" class="tip-state">加载中…</div>
    <div v-else-if="error" data-test="error" class="tip-state tip-error">{{ error }}</div>
    <ul v-else-if="rows.length" class="tip-list">
      <li
        v-for="row in rows"
        :key="row.task_id"
        data-test="inbox-row"
        class="tip-row"
        :class="{ 'tip-row--approval': row.type === 'approval' }"
        @click="$emit('open-detail', row.task_id)"
      >
        <div class="tip-row-main">
          <el-checkbox
            v-if="row.type === 'approval'"
            :data-test="`row-check-${row.task_id}`"
            :model-value="selectedIds.includes(row.task_id)"
            class="tip-row-check"
            @click.stop
            @change="toggleRow(row.task_id)"
          />
          <span class="tip-row-title">{{ row.title || row.task_id }}</span>
          <span v-if="row.pause" class="tip-chip" :class="`tip-chip--${row.pause.tone}`">
            {{ row.pause.label }}
          </span>
          <span v-if="row.isOverdue" class="tip-chip tip-chip--danger">{{ row.overdueLabel }}</span>
        </div>
        <div class="tip-row-meta">
          <span class="tip-chip tip-chip--muted">{{ row.bucketLabel }}</span>
          <span class="tip-status">{{ statusLabel(row) }}</span>
          <span v-if="row.due_at" class="tip-due">到期 {{ row.due_at }}</span>
        </div>
      </li>
    </ul>
    <div v-else data-test="empty" class="tip-state">暂无待办</div>
  </AppCard>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { AppCard, AppButton } from '@/components/common'
import { useTaskInbox } from '@/composables/useTaskInbox'
import { BATCH_MAX_SIZE } from '@/services/taskService'
import { statusLabel } from '@/constants/taskStatus'

defineEmits(['open-detail'])
defineOptions({ name: 'TaskInboxPanel' })

const props = defineProps({
  appId: { type: String, default: null },
  limit: { type: Number, default: 50 }
})

const {
  rows, activeBucket, loading, error, buckets, setBucket, load, submitBatch, precheckDecidable
} = useTaskInbox({ appId: props.appId, limit: props.limit })

// ---- 批量审批（D-AP-12：逐条 submitDecision，失败不中断；§9.13.4.3 护栏）----
const selectedIds = ref([])
const batchComment = ref('')
const batchRunning = ref('')
const batchMessage = ref('')
const batchFailed = ref(false)
const batchRetryableIds = ref([])
const batchFailedList = ref([])
const lastDecision = ref('approve')

const approvalRows = computed(() => rows.value.filter(row => row.type === 'approval'))
const allSelected = computed(() =>
  approvalRows.value.length > 0 && approvalRows.value.every(row => selectedIds.value.includes(row.task_id))
)

function selectBucket(key) {
  setBucket(activeBucket.value === key ? '' : key)
}

function reload() {
  load()
}

function toggleSelectAll(checked) {
  if (!checked) {
    selectedIds.value = []
    return
  }
  const ids = approvalRows.value.map(row => row.task_id)
  selectedIds.value = ids.slice(0, BATCH_MAX_SIZE)
  if (ids.length > BATCH_MAX_SIZE) {
    batchFailed.value = false
    batchMessage.value = `最多批量 ${BATCH_MAX_SIZE} 项，已选择前 ${BATCH_MAX_SIZE} 项，请分批处理`
  }
}

function toggleRow(taskId) {
  selectedIds.value = selectedIds.value.includes(taskId)
    ? selectedIds.value.filter(id => id !== taskId)
    : [...selectedIds.value, taskId]
}

async function decideBatch(taskIds, decision, blocked = []) {
  if (!taskIds.length) return
  if (decision === 'reject' && !batchComment.value.trim()) {
    batchFailed.value = true
    batchMessage.value = '驳回需填写审批意见'
    return
  }
  batchRunning.value = decision
  batchFailed.value = false
  batchMessage.value = ''
  batchRetryableIds.value = []
  batchFailedList.value = []
  lastDecision.value = decision
  try {
    const summary = await submitBatch(taskIds, { decision, comment: batchComment.value.trim() })
    batchRetryableIds.value = summary.retryableIds
    batchFailedList.value = summary.failed.map(item => ({
      ...item,
      retryable: item.httpStatus === 502
    }))
    batchFailed.value = summary.failed.length > 0
    let text = ''
    text += `成功 ${summary.succeeded.length} / 失败 ${summary.failed.length}`
    if (summary.failed.length) {
      text += `：${summary.failed.map(item => item.message || item.task_id).join('；')}`
    }
    if (blocked.length) text += `；已排除 ${blocked.length} 项不可决策`
    batchMessage.value = text
    selectedIds.value = selectedIds.value.filter(id => !summary.succeeded.includes(id))
    if (summary.succeeded.length && !summary.failed.length) batchComment.value = ''
  } catch (e) {
    batchFailed.value = true
    batchMessage.value = e?.message || String(e)
  } finally {
    batchRunning.value = ''
  }
}

const batchActionLabels = {
  approve: '通过',
  reject: '驳回'
}

async function runBatch(decision) {
  const ids = selectedIds.value.slice()
  if (!ids.length) return
  if (ids.length > BATCH_MAX_SIZE) {
    batchFailed.value = true
    batchMessage.value = `选中 ${ids.length} 项超过批量上限 ${BATCH_MAX_SIZE}，请分批处理`
    return
  }
  const action = batchActionLabels[decision]
  try {
    await ElMessageBox.confirm(`确认${action}选中的 ${ids.length} 项审批任务？`, '批量审批', { type: 'warning' })
  } catch (_) {
    return
  }
  // 点击前预判：无权限/状态已变化的项先排除，避免逐条 403
  const { decidable, blocked } = await precheckDecidable(ids, decision)
  if (!decidable.length) {
    batchFailed.value = true
    batchRunning.value = ''
    batchMessage.value = '选中项均不可决策（无权限或状态已变化）'
    return
  }
  await decideBatch(decidable, decision, blocked)
}

function retryBatch() {
  const ids = batchRetryableIds.value.slice()
  if (!ids.length) return
  decideBatch(ids, lastDecision.value)
}

onMounted(load)
</script>

<style scoped>
.tip-header { display: flex; align-items: center; justify-content: space-between; }
.tip-title { font-weight: 600; }
.tip-buckets { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.tip-bucket {
  border: 1px solid var(--color-border); background: transparent;
  border-radius: 999px; padding: 4px 12px; cursor: pointer; font-size: 13px;
}
.tip-bucket.active { border-color: var(--color-primary); color: var(--color-primary); }
.tip-badge {
  display: inline-block; margin-left: 6px; min-width: 18px; text-align: center;
  background: var(--color-bg-layout); border-radius: 9px; font-size: 12px; padding: 0 4px;
}
.tip-batch {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
  padding: 8px 10px; margin-bottom: 12px;
  background: var(--color-bg-layout); border-radius: 6px; font-size: 13px;
}
.tip-batch-comment { width: 220px; }
.tip-batch-result {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  margin-bottom: 12px; font-size: 13px; color: var(--color-text-secondary);
}
.tip-batch-fail-list {
  margin: 0 0 12px; padding-left: 24px;
  font-size: 12px; color: var(--color-text-secondary);
}
.tip-batch-fail-list li { margin: 2px 0; }
.tip-list { list-style: none; margin: 0; padding: 0; }
.tip-row { padding: 10px 8px; border-bottom: 1px solid var(--color-border); cursor: pointer; }
.tip-row--approval { border-left: 2px solid var(--color-primary); }
.tip-row-check { margin-right: 4px; }
.tip-row:hover { background: var(--color-bg-layout); }
.tip-row-main { display: flex; align-items: center; gap: 8px; }
.tip-row-title { font-weight: 500; }
.tip-row-meta { display: flex; gap: 8px; align-items: center; margin-top: 4px; font-size: 12px; color: var(--color-text-secondary); }
.tip-chip { font-size: 12px; padding: 1px 8px; border-radius: 4px; }
.tip-chip--info { background: rgba(64, 158, 255, 0.12); color: #409eff; }
.tip-chip--warning { background: rgba(230, 162, 60, 0.12); color: #e6a23c; }
.tip-chip--danger { background: rgba(245, 108, 108, 0.12); color: #f56c6c; }
.tip-chip--muted { background: var(--color-bg-layout); color: var(--color-text-secondary); }
.tip-state { padding: 24px; text-align: center; color: var(--color-text-secondary); }
.tip-error { color: #f56c6c; }
</style>