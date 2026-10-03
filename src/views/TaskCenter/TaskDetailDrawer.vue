<template>
  <AppModal :model-value="visible" :title="task?.title || '任务详情'" width="720px" @close="$emit('close')">
    <div v-if="loading" data-test="loading" class="tdd-state">加载中…</div>
    <div v-else-if="error" data-test="error" class="tdd-state tdd-error">{{ error }}</div>
    <div v-else-if="task" class="tdd-body">
      <div class="tdd-head">
        <span class="tdd-chip tdd-chip--muted">{{ task.status }}</span>
        <span class="tdd-chip tdd-chip--muted">{{ task.type }}</span>
        <span class="tdd-chip tdd-chip--muted">{{ task.executor_type }}</span>
        <span v-if="pause" data-test="pause-badge" class="tdd-chip" :class="`tdd-chip--${pause.tone}`">
          {{ pause.label }}
        </span>
      </div>

      <dl class="tdd-fields">
        <div><dt>认领人</dt><dd>{{ task.executor_assignee || '—' }}</dd></div>
        <div><dt>到期</dt><dd>{{ task.due_at || '—' }}</dd></div>
        <div><dt>创建人</dt><dd>{{ task.created_by || '—' }}</dd></div>
        <div><dt>业务单据</dt><dd>{{ task.doc_ref || '—' }}</dd></div>
      </dl>

      <div v-if="canClaim" class="tdd-actions">
        <AppButton data-test="claim-btn" :disabled="claiming" @click="onClaim">
          {{ claiming ? '认领中…' : '认领' }}
        </AppButton>
        <span v-if="claimMsg" class="tdd-claim-msg">{{ claimMsg }}</span>
      </div>

      <h4 class="tdd-section">活动流</h4>
      <ul v-if="events.length" class="tdd-timeline">
        <li v-for="ev in events" :key="ev.id" data-test="event-item" class="tdd-event">
          <span class="tdd-event-time">{{ ev.occurred_at }}</span>
          <span class="tdd-event-body">
            <span class="tdd-event-type">{{ ev.event_type }}</span>
            <span v-if="ev.from_status || ev.to_status" class="tdd-event-move">
              {{ ev.from_status || '—' }} → {{ ev.to_status || '—' }}
            </span>
            <span class="tdd-event-actor">{{ ev.actor || 'system' }}（{{ ev.actor_kind || 'system' }}）</span>
            <span v-if="ev.reason" class="tdd-event-reason">{{ ev.reason }}</span>
          </span>
        </li>
      </ul>
      <div v-else data-test="no-events" class="tdd-state">暂无活动记录</div>
    </div>
  </AppModal>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { AppModal, AppButton } from '@/components/common'
import { fetchTaskDetail, fetchTaskEvents, claimTask, derivePause } from '@/services/taskService'

const emit = defineEmits(['close', 'claimed'])
defineOptions({ name: 'TaskDetailDrawer' })

const props = defineProps({
  visible: { type: Boolean, default: false },
  taskId: { type: String, default: '' },
  currentActor: { type: String, default: '' }
})

const task = ref(null)
const events = ref([])
const loading = ref(false)
const error = ref('')
const claiming = ref(false)
const claimMsg = ref('')

const pause = computed(() => derivePause(task.value))

const candidates = computed(() => {
  const c = task.value?.executor_candidates
  if (Array.isArray(c)) return c
  if (c && typeof c === 'object') return [...(c.users || []), ...(c.agents || []), ...(c.groups || [])]
  return []
})

const canClaim = computed(() => {
  const t = task.value
  if (!t || !props.currentActor) return false
  return t.status === 'ready' && t.assign_policy === 'claim' &&
    (candidates.value.includes(props.currentActor))
})

async function load() {
  if (!props.visible || !props.taskId) return
  loading.value = true
  error.value = ''
  claimMsg.value = ''
  try {
    const [detail, evts] = await Promise.all([
      fetchTaskDetail(props.taskId),
      fetchTaskEvents(props.taskId)
    ])
    if (!detail || detail.success !== true || !detail.data) {
      error.value = detail?.message || '任务不存在或无权查看'
      task.value = null
      events.value = []
    } else {
      task.value = detail.data
      events.value = (evts && evts.success && Array.isArray(evts.data)) ? evts.data : []
    }
  } catch (e) {
    error.value = e?.message || String(e)
    task.value = null
  } finally {
    loading.value = false
  }
}

async function onClaim() {
  claiming.value = true
  claimMsg.value = ''
  try {
    const res = await claimTask(props.taskId)
    if (res && res.success) {
      claimMsg.value = '认领成功'
      await load()
      emit('claimed')
    } else {
      claimMsg.value = res?.message || '认领失败'
    }
  } catch (e) {
    claimMsg.value = e?.message || String(e)
  } finally {
    claiming.value = false
  }
}

watch(() => [props.visible, props.taskId], load, { immediate: true })
</script>

<style scoped>
.tdd-head { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.tdd-chip { font-size: 12px; padding: 2px 8px; border-radius: 4px; }
.tdd-chip--info { background: rgba(64, 158, 255, 0.12); color: #409eff; }
.tdd-chip--warning { background: rgba(230, 162, 60, 0.12); color: #e6a23c; }
.tdd-chip--danger { background: rgba(245, 108, 108, 0.12); color: #f56c6c; }
.tdd-chip--muted { background: var(--color-bg-layout); color: var(--color-text-secondary); }
.tdd-fields { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px 16px; margin: 0 0 16px; }
.tdd-fields dt { font-size: 12px; color: var(--color-text-secondary); }
.tdd-fields dd { margin: 2px 0 0; }
.tdd-actions { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.tdd-claim-msg { font-size: 13px; color: var(--color-primary); }
.tdd-section { margin: 8px 0; }
.tdd-timeline { list-style: none; margin: 0; padding: 0; border-left: 2px solid var(--color-border); }
.tdd-event { display: flex; gap: 12px; padding: 6px 12px; }
.tdd-event-time { color: var(--color-text-secondary); font-size: 12px; white-space: nowrap; }
.tdd-event-body { display: flex; gap: 8px; flex-wrap: wrap; font-size: 13px; }
.tdd-event-type { font-weight: 500; }
.tdd-event-move { color: var(--color-primary); }
.tdd-state { padding: 24px; text-align: center; color: var(--color-text-secondary); }
.tdd-error { color: #f56c6c; }
</style>