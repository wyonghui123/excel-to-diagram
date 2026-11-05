<template>
  <PageShell title="封箱作业">
    <div class="hu-seal-page">
      <AppCard title="扫码">
        <div class="scan-row">
          <el-input
            ref="scanInput"
            v-model="huNo"
            class="scan-input"
            placeholder="扫描或输入容器号，回车预检"
            clearable
            @keyup.enter="scan"
          />
          <AppButton variant="primary" size="sm" :loading="scanning" @click="scan">
            预检
          </AppButton>
        </div>
        <div v-if="scanError" class="scan-error">{{ scanError }}</div>
      </AppCard>

      <div class="workbench">
        <AppCard title="待封队列" class="queue-card">
          <EmptyState
            v-if="!queue.length"
            type="box"
            title="队列为空"
            description="扫码后自动加入待封队列"
          />
          <ul v-else class="queue-list">
            <li
              v-for="item in queue"
              :key="item.hu_id"
              class="queue-item"
              :class="{ 'queue-item--active': current?.hu?.id === item.hu_id }"
              @click="selectQueue(item)"
            >
              <div class="queue-main">
                <span class="queue-no">{{ item.hu_no }}</span>
                <el-tag size="small" :type="item.can_seal ? 'success' : 'danger'">
                  {{ item.can_seal ? '可封箱' : '有阻断' }}
                </el-tag>
              </div>
              <button class="queue-remove" type="button" @click.stop="removeQueue(item.hu_id)">×</button>
            </li>
          </ul>
          <div v-if="queue.length" class="queue-actions">
            <AppButton variant="secondary" size="sm" @click="clearQueue">清空</AppButton>
            <AppButton
              variant="primary"
              size="sm"
              :loading="batchSealing"
              :disabled="!sealableIds.length"
              @click="batchSeal"
            >批量封箱（{{ sealableIds.length }}）</AppButton>
          </div>
        </AppCard>

        <AppCard title="容器详情" class="detail-card">
          <EmptyState
            v-if="!current"
            type="box"
            title="尚未扫码"
            description="扫码后显示容器抬头、内容与预检结果"
          />
          <template v-else>
            <div class="hu-head">
              <span class="hu-no">{{ current.hu.hu_no }}</span>
              <el-tag size="small">{{ current.hu.status }}</el-tag>
              <span class="hu-meta">组织 {{ current.hu.org_id }}</span>
              <span class="hu-meta">库位 {{ current.hu.location_id ?? '未定' }}</span>
              <span class="hu-meta">{{ current.hu.hu_type }}</span>
            </div>

            <div v-if="current.checks?.blockers?.length" class="blockers">
              <div class="blockers-title">不能封箱</div>
              <ul>
                <li v-for="(blocker, index) in current.checks.blockers" :key="index">
                  <code>{{ blocker.rule }}</code> {{ blocker.message }}
                </li>
              </ul>
            </div>
            <div v-else class="ready">预检通过，可以封箱</div>

            <div class="section-title">内容（{{ current.contents.length }}）</div>
            <EmptyState v-if="!current.contents.length" type="box" title="容器为空" />
            <table v-else class="hu-table">
              <thead>
                <tr><th>类型</th><th>物料/子容器</th><th>数量</th><th>批次</th><th>序列号</th></tr>
              </thead>
              <tbody>
                <tr v-for="line in current.contents" :key="line.id">
                  <td>{{ line.content_type }}</td>
                  <td>{{ line.child_hu_id ? `#${line.child_hu_id}` : (line.item_id ?? '—') }}</td>
                  <td>{{ formatQty(line.qty) }}</td>
                  <td>{{ line.batch_id ?? '—' }}</td>
                  <td>{{ line.serial_id ?? '—' }}</td>
                </tr>
              </tbody>
            </table>

            <div v-if="current.children?.length" class="children">
              <div class="section-title">子容器</div>
              <div class="children-list">
                <span v-for="child in current.children" :key="child.id" class="child-chip">
                  {{ child.hu_no }} · {{ child.status }}
                </span>
              </div>
            </div>

            <div class="detail-actions">
              <AppButton
                variant="primary"
                size="sm"
                :loading="sealing"
                :disabled="!current.checks?.can_seal"
                @click="sealCurrent"
              >封箱</AppButton>
              <AppButton
                variant="secondary"
                size="sm"
                :loading="unsealing"
                :disabled="current.hu.status !== 'sealed'"
                @click="unsealCurrent"
              >解封</AppButton>
            </div>
          </template>
        </AppCard>
      </div>
    </div>
  </PageShell>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  batchSealHandlingUnits,
  scanHandlingUnit,
  sealHandlingUnit,
  unsealHandlingUnit
} from '@/services/handlingUnitService'

const scanInput = ref(null)
const huNo = ref('')
const current = ref(null)
const queue = ref([])
const scanning = ref(false)
const sealing = ref(false)
const unsealing = ref(false)
const batchSealing = ref(false)
const scanError = ref('')

const sealableIds = computed(() =>
  queue.value.filter(item => item.can_seal).map(item => item.hu_id)
)

onMounted(() => nextTick(() => scanInput.value?.focus?.()))

function focusScan() {
  nextTick(() => scanInput.value?.focus?.())
}

function formatQty(value) {
  if (value === null || value === undefined || value === '') return '0'
  return Number(value)
}

async function scan() {
  const code = huNo.value.trim()
  if (!code) return
  scanning.value = true
  scanError.value = ''
  try {
    const res = await scanHandlingUnit(code)
    if (!res.success) {
      scanError.value = res.message || '预检失败'
      ElMessage.error(scanError.value)
      return
    }
    current.value = res.data
    upsertQueue(res.data)
    huNo.value = ''
  } catch (e) {
    scanError.value = e?.message || '预检失败'
    ElMessage.error(scanError.value)
  } finally {
    scanning.value = false
    focusScan()
  }
}

function upsertQueue(data) {
  const hu = data.hu || {}
  const entry = {
    hu_id: hu.id,
    hu_no: hu.hu_no,
    status: hu.status,
    can_seal: !!data.checks?.can_seal
  }
  const index = queue.value.findIndex(item => item.hu_id === entry.hu_id)
  if (index >= 0) {
    queue.value.splice(index, 1, entry)
  } else if (queue.value.length < 50) {
    queue.value.push(entry)
  }
}

function removeQueue(huId) {
  queue.value = queue.value.filter(item => item.hu_id !== huId)
  if (current.value?.hu?.id === huId) current.value = null
}

function clearQueue() {
  queue.value = []
  current.value = null
}

async function selectQueue(item) {
  const res = await scanHandlingUnit(item.hu_no)
  if (!res.success) {
    ElMessage.error(res.message || '加载失败')
    return
  }
  current.value = res.data
}

async function refreshCurrent(huNoValue) {
  const res = await scanHandlingUnit(huNoValue)
  if (res.success) {
    current.value = res.data
    upsertQueue(res.data)
  } else {
    current.value = null
    queue.value = queue.value.filter(item => item.hu_no !== huNoValue)
  }
}

async function sealCurrent() {
  if (!current.value) return
  sealing.value = true
  try {
    const res = await sealHandlingUnit(current.value.hu.id)
    if (!res.success) {
      ElMessage.error(res.message || '封箱失败')
      return
    }
    ElMessage.success(`已封箱 ${current.value.hu.hu_no}`)
    await refreshCurrent(current.value.hu.hu_no)
  } finally {
    sealing.value = false
    focusScan()
  }
}

async function unsealCurrent() {
  if (!current.value) return
  try {
    await ElMessageBox.confirm(
      `确认解封 ${current.value.hu.hu_no}？`, '解封确认',
      { type: 'warning', confirmButtonText: '解封', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  unsealing.value = true
  try {
    const res = await unsealHandlingUnit(current.value.hu.id)
    if (!res.success) {
      ElMessage.error(res.message || '解封失败')
      return
    }
    ElMessage.success(`已解封 ${current.value.hu.hu_no}`)
    await refreshCurrent(current.value.hu.hu_no)
  } finally {
    unsealing.value = false
  }
}

async function batchSeal() {
  const ids = sealableIds.value
  if (!ids.length) return
  batchSealing.value = true
  try {
    const res = await batchSealHandlingUnits(ids)
    if (!res.success) {
      ElMessage.error(res.message || '批量封箱失败')
      return
    }
    const data = res.data || {}
    if (data.failed) {
      ElMessage.warning(`封箱 ${data.sealed} 箱，失败 ${data.failed} 箱`)
    } else {
      ElMessage.success(`封箱 ${data.sealed} 箱`)
    }
    const failedIds = new Set((data.items || []).filter(i => !i.ok).map(i => i.hu_id))
    queue.value = queue.value.filter(item => failedIds.has(item.hu_id))
    if (current.value?.hu?.id && !failedIds.has(current.value.hu.id)) {
      await refreshCurrent(current.value.hu.hu_no)
    }
  } finally {
    batchSealing.value = false
    focusScan()
  }
}
</script>

<style scoped>
.hu-seal-page { display: flex; flex-direction: column; gap: 16px; }
.scan-row { display: flex; gap: 8px; align-items: center; }
.scan-input { width: 360px; }
.scan-error { margin-top: 8px; color: #dc2626; font-size: 13px; }
.workbench { display: grid; grid-template-columns: 320px 1fr; gap: 16px; align-items: start; }
.queue-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.queue-item { display: flex; align-items: center; justify-content: space-between; padding: 8px 10px; border: 1px solid var(--border-color, #e5e7eb); border-radius: 6px; cursor: pointer; }
.queue-item--active { border-color: #0ea5e9; background: #f0f9ff; }
.queue-main { display: flex; gap: 8px; align-items: center; }
.queue-no { font-weight: 500; }
.queue-remove { border: none; background: transparent; font-size: 16px; color: #94a3b8; cursor: pointer; }
.queue-actions { display: flex; gap: 8px; margin-top: 12px; }
.hu-head { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 12px; }
.hu-no { font-weight: 600; font-size: 15px; }
.hu-meta { color: var(--text-secondary, #6b7280); font-size: 13px; }
.blockers { border: 1px solid #fecaca; background: #fef2f2; border-radius: 6px; padding: 10px 12px; margin-bottom: 12px; }
.blockers-title { color: #b91c1c; font-weight: 600; margin-bottom: 6px; }
.blockers ul { margin: 0; padding-left: 18px; font-size: 13px; }
.ready { color: #15803d; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 6px; padding: 8px 12px; margin-bottom: 12px; font-size: 13px; }
.section-title { font-weight: 500; margin: 12px 0 8px; }
.hu-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.hu-table th, .hu-table td { padding: 8px 10px; border-bottom: 1px solid var(--border-color, #e5e7eb); text-align: left; }
.hu-table th { color: var(--text-secondary, #6b7280); font-weight: 500; }
.children-list { display: flex; flex-wrap: wrap; gap: 8px; }
.child-chip { font-size: 12px; padding: 4px 8px; border-radius: 4px; background: #f1f5f9; }
.detail-actions { display: flex; gap: 8px; margin-top: 16px; }
</style>
