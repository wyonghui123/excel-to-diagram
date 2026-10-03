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
import { ref, onMounted } from 'vue'
import { SubNavTabs } from '@/components/common'
import TaskDetailDrawer from './TaskDetailDrawer.vue'
import { fetchTasks } from '@/services/taskService'
import { useAuthStore } from '@/stores/authStore'

defineOptions({ name: 'TaskCenter' })

// P1 只有「监控」；「定义 / 编排」归 P3（不塞占位 tab）
const tabs = [{ key: 'monitor', label: '监控' }]
const activeTab = ref('monitor')

const rows = ref([])
const loading = ref(false)
const error = ref('')
const drawerVisible = ref(false)
const drawerTaskId = ref('')

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

function openDetail(taskId) {
  drawerTaskId.value = taskId
  drawerVisible.value = true
}

onMounted(reload)
</script>

<style scoped>
.task-center { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.task-center-content { flex: 1; overflow: auto; padding: var(--spacing-md); }
.tc-table { width: 100%; border-collapse: collapse; }
.tc-table th, .tc-table td { text-align: left; padding: 8px; border-bottom: 1px solid var(--color-border); }
.tc-table tbody tr { cursor: pointer; }
.tc-table tbody tr:hover { background: var(--color-bg-layout); }
.tc-state { padding: 24px; text-align: center; color: var(--color-text-secondary); }
.tc-error { color: #f56c6c; }
</style>