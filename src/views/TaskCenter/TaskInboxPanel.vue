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

    <div v-if="loading" data-test="loading" class="tip-state">加载中…</div>
    <div v-else-if="error" data-test="error" class="tip-state tip-error">{{ error }}</div>
    <ul v-else-if="rows.length" class="tip-list">
      <li
        v-for="row in rows"
        :key="row.task_id"
        data-test="inbox-row"
        class="tip-row"
        @click="$emit('open-detail', row.task_id)"
      >
        <div class="tip-row-main">
          <span class="tip-row-title">{{ row.title || row.task_id }}</span>
          <span v-if="row.pause" class="tip-chip" :class="`tip-chip--${row.pause.tone}`">
            {{ row.pause.label }}
          </span>
          <span v-if="row.isOverdue" class="tip-chip tip-chip--danger">{{ row.overdueLabel }}</span>
        </div>
        <div class="tip-row-meta">
          <span class="tip-chip tip-chip--muted">{{ row.bucketLabel }}</span>
          <span class="tip-status">{{ row.status }}</span>
          <span v-if="row.due_at" class="tip-due">到期 {{ row.due_at }}</span>
        </div>
      </li>
    </ul>
    <div v-else data-test="empty" class="tip-state">暂无待办</div>
  </AppCard>
</template>

<script setup>
import { onMounted } from 'vue'
import { AppCard, AppButton } from '@/components/common'
import { useTaskInbox } from '@/composables/useTaskInbox'

defineEmits(['open-detail'])
defineOptions({ name: 'TaskInboxPanel' })

const props = defineProps({
  appId: { type: String, default: null },
  limit: { type: Number, default: 50 }
})

const {
  rows, activeBucket, loading, error, buckets, setBucket, load
} = useTaskInbox({ appId: props.appId, limit: props.limit })

function selectBucket(key) {
  setBucket(activeBucket.value === key ? '' : key)
}

function reload() {
  load()
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
.tip-list { list-style: none; margin: 0; padding: 0; }
.tip-row { padding: 10px 8px; border-bottom: 1px solid var(--color-border); cursor: pointer; }
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