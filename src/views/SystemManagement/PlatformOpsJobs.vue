<template>
  <PageShell title="平台运维作业">
    <div class="ops-page">
      <!-- 加载中 -->
      <div v-if="loading" data-test="ops-loading" class="ops-state">加载中…</div>

      <!-- 加载失败（含未接线 503） -->
      <div v-else-if="error" data-test="ops-error" class="ops-state ops-state--error">{{ error }}</div>

      <!-- 暂停态（CRON_JOBS_ENABLED=0）：不显示表格 -->
      <div v-else-if="paused" data-test="ops-paused">
        <AppCard title="调度已暂停">
          <p class="ops-paused-text">调度器当前处于暂停状态（CRON_JOBS_ENABLED=0），暂无运行中的作业。</p>
        </AppCard>
      </div>

      <!-- 正常态：运维作业 + 平台作业 两张卡 -->
      <template v-else>
        <div v-if="actionError" data-test="ops-action-error" class="ops-state ops-state--error">{{ actionError }}</div>

        <AppCard title="运维作业">
          <EmptyState v-if="!maintenanceRows.length" data-test="ops-empty" type="box" title="暂无作业" />
          <div v-else class="ops-table-wrap">
            <table class="ops-table">
              <thead>
                <tr>
                  <th>作业码</th><th>调度</th><th>下次运行</th><th>handler 就绪</th><th>启用</th><th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in maintenanceRows" :key="row.code" data-test="ops-row">
                  <td>{{ row.code }}</td>
                  <td>{{ row.schedule || '—' }}</td>
                  <td>{{ row.next_run_at || '—' }}</td>
                  <td>{{ row.handler_registered ? '是' : '否' }}</td>
                  <td>{{ row.enabled ? '是' : '否' }}</td>
                  <td>
                    <AppButton
                      data-test="ops-run-now"
                      variant="secondary"
                      size="sm"
                      :loading="!!running[row.code]"
                      @click="runNow(row.code)"
                    >立即执行</AppButton>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </AppCard>

        <AppCard title="平台作业" class="ops-card--gap">
          <EmptyState v-if="!platformRows.length" data-test="ops-empty" type="box" title="暂无作业" />
          <div v-else class="ops-table-wrap">
            <table class="ops-table">
              <thead>
                <tr>
                  <th>作业码</th><th>调度</th><th>下次运行</th><th>handler 就绪</th><th>启用</th><th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in platformRows" :key="row.code" data-test="ops-row">
                  <td>{{ row.code }}</td>
                  <td>{{ row.schedule || '—' }}</td>
                  <td>{{ row.next_run_at || '—' }}</td>
                  <td>{{ row.handler_registered ? '是' : '否' }}</td>
                  <td>{{ row.enabled ? '是' : '否' }}</td>
                  <td>
                    <AppButton
                      data-test="ops-run-now"
                      variant="secondary"
                      size="sm"
                      :loading="!!running[row.code]"
                      @click="runNow(row.code)"
                    >立即执行</AppButton>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </AppCard>
      </template>
    </div>
  </PageShell>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { PageShell, AppCard, AppButton, EmptyState } from '@/components/common'
import { fetchSchedulerStatus, runSchedulerJob } from '@/services/schedulerService'

defineOptions({ name: 'PlatformOpsJobs' })

const loading = ref(false)
const error = ref('')
const actionError = ref('')
const paused = ref(false)
const maintenance = ref({})
const platform = ref({})
/** 已点击「立即执行」且尚未返回的作业码集合 */
const running = ref({})

/** 分组对象 → 表格行数组（缺省字段兜底空串/布尔） */
function toRows(group) {
  if (!group || typeof group !== 'object') return []
  return Object.entries(group).map(([code, v]) => ({
    code,
    schedule: v && v.schedule != null ? v.schedule : '',
    next_run_at: v && v.next_run_at != null ? v.next_run_at : '',
    handler_registered: !!(v && v.handler_registered),
    enabled: !!(v && v.enabled)
  }))
}

const maintenanceRows = computed(() => toRows(maintenance.value))
const platformRows = computed(() => toRows(platform.value))

/**
 * 拉取调度器状态。
 * @param {{silent?:boolean}} [opts] silent=true 时不切换整页 loading（用于执行后刷新）
 */
async function load({ silent = false } = {}) {
  if (!silent) loading.value = true
  error.value = ''
  try {
    const res = await fetchSchedulerStatus()
    if (res && res.success === true && res.data) {
      paused.value = !!res.data.paused
      maintenance.value = res.data.maintenance || {}
      platform.value = res.data.platform || {}
    } else {
      error.value = res?.message || '加载失败'
    }
  } catch (e) {
    error.value = e?.message || String(e)
  } finally {
    if (!silent) loading.value = false
  }
}

/** 立即执行某作业；成功后静默刷新状态 */
async function runNow(code) {
  actionError.value = ''
  running.value = { ...running.value, [code]: true }
  try {
    const res = await runSchedulerJob(code)
    if (res && res.success) {
      await load({ silent: true })
    } else {
      actionError.value = res?.message || '执行失败'
    }
  } catch (e) {
    actionError.value = e?.message || String(e)
  } finally {
    running.value = { ...running.value, [code]: false }
  }
}

onMounted(load)
</script>

<style scoped>
.ops-page { display: flex; flex-direction: column; gap: var(--spacing-md); }
.ops-card--gap { margin-top: var(--spacing-md); }
.ops-state { padding: 24px; text-align: center; color: var(--color-text-secondary); }
.ops-state--error { color: #f56c6c; }
.ops-paused-text { margin: 0; color: var(--color-text-secondary); }

.ops-table-wrap { width: 100%; overflow-x: auto; }
.ops-table { width: 100%; border-collapse: collapse; }
.ops-table th, .ops-table td { text-align: left; padding: 8px; border-bottom: 1px solid var(--color-border); }
/* 表头恒为单行，避免窄屏下中文被压成竖排 */
.ops-table th { white-space: nowrap; }

/* 6 列在窄屏无法平分宽度，改用横向滚动 + min-width，与 TaskCenter 处理一致 */
@media screen and (max-width: 768px) {
  .ops-table { min-width: 640px; }
}
</style>
