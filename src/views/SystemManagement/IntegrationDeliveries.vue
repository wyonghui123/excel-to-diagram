<template>
  <PageShell
    title="消息运行面"
    subtitle="in / out messages：投递事实、失败原因与单条重试"
  >
    <AppCard title="投递实例">
      <div class="toolbar">
        <AppSelect
          v-model="filters.status"
          :options="statusOptions"
          size="sm"
          placeholder="全部状态"
          clearable
          class="w-140"
        />
        <AppSelect
          v-model="filters.direction"
          :options="directionOptions"
          size="sm"
          placeholder="全部方向"
          clearable
          class="w-140"
        />
        <AppSelect
          v-model="filters.target_type"
          :options="targetTypeOptions"
          size="sm"
          placeholder="全部目标类型"
          clearable
          class="w-170"
        />
        <AppButton variant="secondary" size="sm" :loading="loading" @click="reload">刷新</AppButton>
        <span class="spacer" />
        <span class="hint">共 {{ total }} 条</span>
      </div>

      <div v-if="error" class="alert">{{ error }}</div>
      <EmptyState
        v-else-if="!loading && !rows.length"
        type="empty"
        title="暂无投递记录"
        description="事件触发或导入提交后，投递事实会出现在这里"
      />
      <div v-else class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>#</th>
              <th>方向</th>
              <th>事件</th>
              <th>业务对象</th>
              <th>连接</th>
              <th>渠道 / 目标</th>
              <th>状态</th>
              <th>尝试</th>
              <th>最近错误</th>
              <th>下次重试</th>
              <th>创建时间</th>
              <th class="col-action">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.id">
              <td class="mono">{{ row.id }}</td>
              <td>{{ row.direction || '-' }}</td>
              <td class="mono">
                {{ row.event_type || '-' }}
                <span v-if="row.event_id" class="muted">#{{ row.event_id }}</span>
              </td>
              <td class="mono">
                {{ row.object_type || '-' }}
                <span v-if="row.object_id" class="muted">#{{ row.object_id }}</span>
              </td>
              <td class="mono">{{ row.connection_code || '-' }}</td>
              <td>
                <div>{{ row.channel || '-' }}</div>
                <div class="mono ellipsis muted" :title="row.target">{{ row.target || '-' }}</div>
              </td>
              <td>
                <span :class="['tag', statusClass(row.status)]">{{ row.status }}</span>
              </td>
              <td class="mono">{{ row.attempts ?? 0 }}</td>
              <td class="ellipsis err" :title="row.last_error">{{ row.last_error || '-' }}</td>
              <td class="mono">{{ row.next_retry_at || '-' }}</td>
              <td class="mono">{{ row.created_at }}</td>
              <td class="col-action">
                <AppButton
                  variant="ghost"
                  size="sm"
                  :disabled="!retryable(row.status)"
                  :loading="retrying === row.id"
                  @click="handleRetry(row)"
                >
                  重试
                </AppButton>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <Pagination
        v-if="total > 0"
        v-model:current="page"
        v-model:page-size="pageSize"
        :total="total"
        class="pager"
        @change="load"
        @pageSizeChange="onSizeChange"
      />
    </AppCard>
  </PageShell>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import {
  PageShell, AppCard, AppButton, AppSelect, EmptyState, Pagination,
} from '@/components/common'
import { useMessage } from '@/composables/useMessage'
import { fetchDeliveries, retryDelivery } from '@/services/integrationService'

defineOptions({ name: 'IntegrationDeliveries' })

const toast = useMessage()

const RETRYABLE = ['failed', 'skipped']

const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const retrying = ref(0)
const error = ref('')

const filters = reactive({ status: '', direction: '', target_type: '' })
const statusOptions = ['pending', 'sending', 'delivered', 'failed', 'skipped']
  .map((v) => ({ value: v, label: v }))
const directionOptions = ['inbound', 'outbound'].map((v) => ({ value: v, label: v }))
const targetTypeOptions = ['connection', 'webhook', 'user', 'role', 'external']
  .map((v) => ({ value: v, label: v }))

const retryable = (status) => RETRYABLE.includes(status)

function statusClass(status) {
  if (status === 'delivered') return 'tag-on'
  if (status === 'failed') return 'tag-bad'
  if (status === 'pending' || status === 'sending') return 'tag-warn'
  return 'tag-off'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchDeliveries({
      status: filters.status || undefined,
      direction: filters.direction || undefined,
      target_type: filters.target_type || undefined,
      page: page.value,
      page_size: pageSize.value,
    })
    if (res.success) {
      rows.value = res.data?.items || []
      total.value = res.data?.total ?? rows.value.length
    } else {
      error.value = res.message || '加载投递记录失败'
      rows.value = []
      total.value = 0
    }
  } finally {
    loading.value = false
  }
}

function reload() {
  page.value = 1
  load()
}

function onSizeChange() {
  page.value = 1
  load()
}

async function handleRetry(row) {
  retrying.value = row.id
  try {
    const res = await retryDelivery(row.id)
    if (!res.success) {
      toast.error(res.message || '重试失败')
      return
    }
    const info = res.data || {}
    if (info.debounced) {
      toast.warning('5 秒内重复点击已忽略')
    } else if (info.reset) {
      toast.success(`已重置 ${info.reset} 条投递`)
      await load()
    } else {
      toast.info(info.message || '当前状态不可重试')
    }
  } finally {
    retrying.value = 0
  }
}

onMounted(load)
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.spacer { flex: 1; }
.w-140 { width: 140px; }
.w-170 { width: 170px; }
.hint { font-size: 12px; color: var(--text-secondary, #6b7280); }
.alert {
  padding: 10px 12px;
  border-radius: 6px;
  background: #fef2f2;
  color: #b91c1c;
  font-size: 13px;
}
.table-wrap { overflow-x: auto; }
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.data-table th,
.data-table td {
  padding: 9px 10px;
  text-align: left;
  border-bottom: 1px solid var(--border-color, #eef0f3);
  white-space: nowrap;
}
.data-table th {
  font-weight: 600;
  color: var(--text-secondary, #6b7280);
  background: var(--bg-subtle, #f9fafb);
}
.data-table .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.data-table .ellipsis { max-width: 220px; overflow: hidden; text-overflow: ellipsis; }
.data-table .muted { color: var(--text-secondary, #9ca3af); margin-left: 4px; }
.data-table .err { color: #b91c1c; }
.col-action { text-align: right; }
.tag {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 12px;
}
.tag-on { background: #ecfdf5; color: #047857; }
.tag-warn { background: #fffbeb; color: #b45309; }
.tag-bad { background: #fef2f2; color: #b91c1c; }
.tag-off { background: #f3f4f6; color: #6b7280; }
.pager { margin-top: 14px; }
</style>