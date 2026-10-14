<template>
  <div class="task-center">
    <SubNavTabs :tabs="tabs" :model-value="activeTab" aria-label="任务管理" @update:model-value="activeTab = $event" />

    <div v-show="activeTab === 'monitor'" class="task-center-content">
      <div v-if="loading" data-test="loading" class="tc-state">加载中…</div>
      <div v-else-if="error" data-test="error" class="tc-state tc-error">{{ error }}</div>
      <table v-else class="tc-table">
        <thead>
          <tr>
            <th>任务</th><th>状态</th><th>类型</th><th>Executor</th>
            <th>认领人</th><th>到期</th><th>更新时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="t in rows" :key="t.id" data-test="monitor-row" @click="openDetail(t.id)">
            <td>{{ t.title || t.id }}</td>
            <td>{{ t.status }}</td>
            <td>{{ t.type }}</td>
            <td>{{ t.executor_type }}</td>
            <td>{{ t.assignee || '—' }}</td>
            <td>{{ t.due_at || '—' }}</td>
            <td>{{ t.updated_at || '—' }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="!loading && !error && !rows.length" data-test="empty" class="tc-state">暂无任务</div>
    </div>

    <div v-show="activeTab === 'schedule'" class="task-center-content">
      <div v-if="scheduleLoading" data-test="schedule-loading" class="tc-state">加载中…</div>
      <div v-else-if="scheduleError" data-test="schedule-error" class="tc-state tc-error">{{ scheduleError }}</div>
      <table v-else class="tc-table">
        <thead>
          <tr>
            <th>流程</th><th>cron</th><th>下次运行</th><th>节点数</th><th>最近运行</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in scheduleRows" :key="s.workflow_key" data-test="schedule-row">
            <td>{{ s.name || s.workflow_key }}</td>
            <td>{{ s.cron_label || s.cron || '—' }}</td>
            <td>{{ s.next_run_at ? formatTime(s.next_run_at) : '—' }}</td>
            <td>{{ s.node_count }}</td>
            <td>{{ latestRunText(s) }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="!scheduleLoading && !scheduleError && !scheduleRows.length" data-test="schedule-empty" class="tc-state">暂无定时编排</div>
    </div>

    <TaskDetailDrawer
      :visible="drawerVisible"
      :task-id="drawerTaskId"
      :current-actor="currentActor"
      @close="drawerVisible = false"
      @claimed="reload"
    />
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { SubNavTabs } from '@/components/common'
import TaskDetailDrawer from './TaskDetailDrawer.vue'
import { fetchTasks, fetchWorkflowSchedules } from '@/services/taskService'
import { useAuthStore } from '@/stores/authStore'

defineOptions({ name: 'TaskCenter' })

// 「监控」= 任务实例视角；「调度」= 编排定义 + 触发规则 + 运行实例（只读）
const tabs = [{ key: 'monitor', label: '监控' }, { key: 'schedule', label: '调度' }]
const activeTab = ref('monitor')

const rows = ref([])
const loading = ref(false)
const error = ref('')
const drawerVisible = ref(false)
const drawerTaskId = ref('')

const scheduleRows = ref([])
const scheduleLoading = ref(false)
const scheduleError = ref('')

const authStore = useAuthStore()
const currentActor = ref(authStore.user?.user_id || authStore.user?.username || '')

async function reload() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchTasks({ page: 1, pageSize: 100 })
    if (res && res.success) {
      rows.value = res.data?.items || []
    } else {
      error.value = res?.message || '加载失败'
      rows.value = []
    }
  } catch (e) {
    error.value = e?.message || String(e)
    rows.value = []
  } finally {
    loading.value = false
  }
}

async function loadSchedules() {
  scheduleLoading.value = true
  scheduleError.value = ''
  try {
    const res = await fetchWorkflowSchedules()
    if (res && res.success) {
      scheduleRows.value = res.data?.items || []
    } else {
      scheduleError.value = res?.message || '加载失败'
      scheduleRows.value = []
    }
  } catch (e) {
    scheduleError.value = e?.message || String(e)
    scheduleRows.value = []
  } finally {
    scheduleLoading.value = false
  }
}

/** 最近一次运行的可读文本（无运行显示 —） */
function latestRunText(item) {
  const run = (item.runs || [])[0]
  if (!run) return '—'
  return `${run.status} ${run.done}/${run.total}`
}

/** 只取到分钟（后端返回 ISO 时间戳） */
function formatTime(value) {
  return String(value).replace('T', ' ').slice(0, 16)
}

function openDetail(taskId) {
  drawerTaskId.value = taskId
  drawerVisible.value = true
}

watch(activeTab, (tab) => {
  if (tab === 'schedule' && !scheduleRows.value.length && !scheduleLoading.value) {
    loadSchedules()
  }
})

onMounted(reload)
</script>

<style scoped>
.task-center { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.task-center-content { flex: 1; overflow: auto; padding: var(--spacing-md); }
.tc-table { width: 100%; border-collapse: collapse; }
.tc-table th, .tc-table td { text-align: left; padding: 8px; border-bottom: 1px solid var(--color-border); }
/* [FIX 2026-10-13 移动端] 表头恒为单行。此前缺 nowrap，窄屏下 7 列平分宽度
   后中文被压成竖排：实测表头高度 414px 屏 65px、360px 屏 113px
   （单行应约 33px），列宽被压到 36px 装不下 2 个汉字。 */
.tc-table th { white-space: nowrap; }
.tc-table tbody tr { cursor: pointer; }
.tc-table tbody tr:hover { background: var(--color-bg-layout); }
.tc-state { padding: 24px; text-align: center; color: var(--color-text-secondary); }
.tc-error { color: #f56c6c; }

/* [FIX 2026-10-13 移动端] 7 列在窄屏无法平分宽度，改由表格横向滚动。
   min-width 保证列不被压到装不下内容；父容器已有 overflow: auto。
   与 SubNavTabs 的「横向滚动」处理思路一致，不用隐藏列也不靠缩小字号。 */
@media screen and (max-width: 768px) {
  .tc-table { min-width: 640px; }
}
</style>