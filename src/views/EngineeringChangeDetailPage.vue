<template>
  <PageShell
    :title="pageTitle"
    :breadcrumbs="breadcrumbs"
    :show-back-button="true"
  >
    <template #title-bar-actions>
      <AppButton
        v-if="canSubmit"
        variant="primary"
        data-test="ec-action-submit"
        :loading="acting === 'submit'"
        @click="handleSubmit"
      >
        提交评审
      </AppButton>
      <AppButton
        v-if="canApprove"
        variant="success"
        data-test="ec-action-approve"
        :loading="acting === 'approve'"
        @click="handleApprove"
      >
        批准
      </AppButton>
      <AppButton
        v-if="canReject"
        variant="danger"
        data-test="ec-action-reject"
        :loading="acting === 'reject'"
        @click="handleReject"
      >
        驳回
      </AppButton>
      <AppButton
        v-if="canApply"
        variant="warning"
        data-test="ec-action-apply"
        :loading="acting === 'apply'"
        @click="handleApply"
      >
        应用到生产 BOM
      </AppButton>
      <AppButton
        v-if="canCancel"
        variant="secondary"
        data-test="ec-action-cancel"
        :loading="acting === 'cancel'"
        @click="handleCancel"
      >
        取消
      </AppButton>
    </template>

    <div class="ec-detail">
      <el-alert
        v-if="loadError"
        type="error"
        :closable="false"
        show-icon
        data-test="ec-detail-error"
        :title="loadError"
      />
      <el-alert
        v-if="actionMessage"
        type="success"
        :closable="false"
        show-icon
        data-test="ec-action-message"
        :title="actionMessage"
      />

      <AppCard title="变更单信息">
        <el-descriptions v-if="change" :column="2" border data-test="ec-header">
          <el-descriptions-item label="变更单号">{{ change.change_no || '—' }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusTagType(change.status)" size="small">
              {{ statusLabel(change.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="变更标题">{{ change.title || '—' }}</el-descriptions-item>
          <el-descriptions-item label="变更类型">{{ changeTypeLabel(change.change_type) }}</el-descriptions-item>
          <el-descriptions-item label="生效日">{{ change.effective_date || '—' }}</el-descriptions-item>
          <el-descriptions-item label="关联项目">{{ change.project_id ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="物料 ID">{{ change.item_id ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="目标生产结构">{{ change.target_structure_id ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ change.created_at || '—' }}</el-descriptions-item>
          <el-descriptions-item label="创建人">{{ change.created_by || '—' }}</el-descriptions-item>
          <el-descriptions-item label="应用时间">{{ change.applied_at || '—' }}</el-descriptions-item>
          <el-descriptions-item label="应用人">{{ change.applied_by || '—' }}</el-descriptions-item>
          <el-descriptions-item label="变更原因" :span="2">
            {{ change.reason || '—' }}
          </el-descriptions-item>
        </el-descriptions>
        <span v-else data-test="ec-detail-empty">加载中…</span>
      </AppCard>

      <AppCard title="变更明细">
        <el-table
          v-loading="loading"
          :data="lines"
          row-key="id"
          border
          data-test="ec-lines-table"
        >
          <el-table-column prop="line_no" label="行号" width="70" />
          <el-table-column label="变更动作" width="100">
            <template #default="{ row }">
              <el-tag
                :type="lineTypeTagType(row.line_type)"
                size="small"
                effect="dark"
                data-test="ec-line-type"
              >
                {{ lineTypeLabel(row.line_type) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="组件物料" width="100">
            <template #default="{ row }">{{ row.component_item_id ?? '—' }}</template>
          </el-table-column>
          <el-table-column prop="match_key" label="匹配键" min-width="180" show-overflow-tooltip />
          <el-table-column label="旧用量" width="100">
            <template #default="{ row }">{{ fmt(row.old_qty_per) }}</template>
          </el-table-column>
          <el-table-column label="新用量" width="100">
            <template #default="{ row }">{{ fmt(row.new_qty_per) }}</template>
          </el-table-column>
          <el-table-column label="旧失效日" width="120">
            <template #default="{ row }">{{ fmt(row.old_valid_to) }}</template>
          </el-table-column>
          <el-table-column label="新失效日" width="120">
            <template #default="{ row }">{{ fmt(row.new_valid_to) }}</template>
          </el-table-column>
          <el-table-column label="目标结构" width="100">
            <template #default="{ row }">{{ row.target_structure_id ?? '—' }}</template>
          </el-table-column>
          <el-table-column label="来源结构" width="100">
            <template #default="{ row }">{{ row.source_structure_id ?? '—' }}</template>
          </el-table-column>
          <el-table-column prop="note" label="备注" min-width="120" show-overflow-tooltip />
          <template #empty>
            <span data-test="ec-lines-empty">暂无明细</span>
          </template>
        </el-table>
      </AppCard>

      <AppCard title="影响预览（只读）">
        <div class="ec-impact">
          <el-alert
            type="info"
            :closable="false"
            show-icon
            data-test="ec-impact-readonly"
            title="影响预览为只读信息，仅供评审参考；本页不会修改生产 BOM 或工单。"
          />
          <el-alert
            v-if="impactError"
            type="error"
            :closable="false"
            show-icon
            data-test="ec-impact-error"
            :title="impactError"
          />

          <div class="ec-impact__section">
            <h4 class="ec-impact__title">
              受影响父项结构
              <span class="ec-impact__count">({{ parentStructures.length }})</span>
            </h4>
            <el-table
              v-loading="impactLoading"
              :data="parentStructures"
              row-key="structure_line_id"
              border
              size="small"
              data-test="ec-impact-parent-table"
            >
              <el-table-column label="结构 ID" width="100">
                <template #default="{ row }">{{ row.structure_id ?? '—' }}</template>
              </el-table-column>
              <el-table-column label="父项物料" width="100">
                <template #default="{ row }">{{ row.item_id ?? '—' }}</template>
              </el-table-column>
              <el-table-column label="用途" width="100">
                <template #default="{ row }">{{ row.usage ?? '—' }}</template>
              </el-table-column>
              <el-table-column label="版本" width="100">
                <template #default="{ row }">{{ row.revision ?? '—' }}</template>
              </el-table-column>
              <el-table-column label="状态" width="100">
                <template #default="{ row }">{{ row.status ?? '—' }}</template>
              </el-table-column>
              <el-table-column label="结构行" width="90">
                <template #default="{ row }">{{ row.structure_line_id ?? '—' }}</template>
              </el-table-column>
              <el-table-column label="组件物料" width="100">
                <template #default="{ row }">{{ row.component_item_id ?? '—' }}</template>
              </el-table-column>
              <el-table-column label="单位用量" width="100">
                <template #default="{ row }">{{ fmt(row.qty_per) }}</template>
              </el-table-column>
              <template #empty>
                <span data-test="ec-impact-parent-empty">无受影响父项结构</span>
              </template>
            </el-table>
          </div>

          <div class="ec-impact__section">
            <h4 class="ec-impact__title">
              在途工单
              <span class="ec-impact__count">({{ workOrders.length }})</span>
            </h4>
            <el-table
              v-loading="impactLoading"
              :data="workOrders"
              row-key="work_order_id"
              border
              size="small"
              data-test="ec-impact-work-order-table"
            >
              <el-table-column label="工单 ID" width="100">
                <template #default="{ row }">{{ row.work_order_id ?? '—' }}</template>
              </el-table-column>
              <el-table-column label="工单号" min-width="150">
                <template #default="{ row }">{{ row.work_order_no ?? '—' }}</template>
              </el-table-column>
              <el-table-column label="状态" width="100">
                <template #default="{ row }">{{ row.status ?? '—' }}</template>
              </el-table-column>
              <el-table-column label="涉及组件" min-width="200">
                <template #default="{ row }">{{ componentsLabel(row) }}</template>
              </el-table-column>
              <el-table-column label="创建时间" width="170">
                <template #default="{ row }">{{ row.created_at || '—' }}</template>
              </el-table-column>
              <template #empty>
                <span data-test="ec-impact-work-order-empty">无在途工单</span>
              </template>
            </el-table>
          </div>
        </div>
      </AppCard>
    </div>
  </PageShell>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { PageShell, AppCard, AppButton } from '@/components/common'
import { useAuthStore } from '@/stores/authStore'
import { can } from '@/services/permissionService'
import {
  getChange,
  getImpact,
  submitChange,
  approveChange,
  rejectChange,
  cancelChange,
  applyChange
} from '@/services/engineeringChangeService'

defineOptions({ name: 'EngineeringChangeDetailPage' })

const STATUS_LABELS = {
  draft: '草稿',
  in_review: '评审中',
  approved: '已批准',
  applied: '已应用',
  rejected: '已驳回',
  cancelled: '已取消'
}

const STATUS_TAG_TYPES = {
  draft: 'info',
  in_review: 'primary',
  approved: 'success',
  applied: 'success',
  rejected: 'danger',
  cancelled: 'warning'
}

const CHANGE_TYPE_LABELS = {
  new: '首次工程 BOM',
  revise: '改版',
  obsolete: '停用'
}

const LINE_TYPE_LABELS = { add: '新增', modify: '修改', remove: '移除' }
const LINE_TYPE_TAG_TYPES = { add: 'success', modify: 'primary', remove: 'danger' }

const route = useRoute()
const authStore = useAuthStore()

const change = ref(null)
const loading = ref(false)
const loadError = ref('')
const impact = ref(null)
const impactLoading = ref(false)
const impactError = ref('')
const acting = ref('')
const actionMessage = ref('')

const changeId = computed(() => String(route.params.id ?? '').trim())
const pageTitle = computed(() => change.value?.change_no || '工程变更详情')
const lines = computed(() => change.value?.lines || [])
const parentStructures = computed(() => impact.value?.parent_structures || [])
const workOrders = computed(() => impact.value?.work_orders || [])

const breadcrumbs = computed(() => {
  const crumbs = [{ label: '工程变更', to: '/master-data/engineering-change' }]
  if (change.value?.change_no) crumbs.push({ label: change.value.change_no })
  return crumbs
})

const hasCreate = computed(() => can('create', { objectType: 'engineering_change', authStore }))
const hasApprove = computed(() => can('approve', { objectType: 'engineering_change', authStore }))
const hasApply = computed(() => can('apply', { objectType: 'engineering_change', authStore }))
const status = computed(() => change.value?.status)

const canSubmit = computed(() => status.value === 'draft' && hasCreate.value)
const canApprove = computed(() => status.value === 'in_review' && hasApprove.value)
const canReject = computed(() => status.value === 'in_review' && hasApprove.value)
const canCancel = computed(
  () => ['draft', 'in_review', 'approved'].includes(status.value) && hasCreate.value
)
const canApply = computed(() => status.value === 'approved' && hasApply.value)

function statusLabel(value) {
  return STATUS_LABELS[value] || value || '—'
}

function statusTagType(value) {
  return STATUS_TAG_TYPES[value] || 'info'
}

function changeTypeLabel(value) {
  return CHANGE_TYPE_LABELS[value] || value || '—'
}

function lineTypeLabel(value) {
  return LINE_TYPE_LABELS[value] || value || '—'
}

function lineTypeTagType(value) {
  return LINE_TYPE_TAG_TYPES[value] || 'info'
}

function fmt(value) {
  return value === null || value === undefined || value === '' ? '—' : value
}

function componentsLabel(row) {
  const components = Array.isArray(row?.components) ? row.components : []
  if (components.length === 0) return '—'
  return components
    .map(item => `物料 ${item.component_item_id ?? '—'} × ${fmt(item.qty_required)}`)
    .join('；')
}

function errorMessage(result, fallback) {
  return result?.message || fallback
}

async function loadChange() {
  if (!changeId.value) {
    loadError.value = '缺少变更单 ID'
    return
  }
  loading.value = true
  loadError.value = ''
  try {
    const result = await getChange(changeId.value)
    if (!result.success) {
      loadError.value = errorMessage(result, '工程变更单详情查询失败')
      return
    }
    change.value = result.data || null
  } catch (e) {
    loadError.value = e?.message || '工程变更单详情查询失败'
  } finally {
    loading.value = false
  }
}

async function loadImpact() {
  if (!changeId.value) return
  impactLoading.value = true
  impactError.value = ''
  try {
    const result = await getImpact(changeId.value)
    if (!result.success) {
      impactError.value = errorMessage(result, '影响预览查询失败')
      return
    }
    impact.value = result.data || null
  } catch (e) {
    impactError.value = e?.message || '影响预览查询失败'
  } finally {
    impactLoading.value = false
  }
}

async function reload() {
  await Promise.all([loadChange(), loadImpact()])
}

async function runAction(action, fn, successText) {
  acting.value = action
  actionMessage.value = ''
  try {
    const result = await fn()
    if (!result.success) {
      loadError.value = errorMessage(result, '操作失败')
      return
    }
    actionMessage.value = successText
    await reload()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') {
      loadError.value = e?.message || '操作失败'
    }
  } finally {
    acting.value = ''
  }
}

async function handleSubmit() {
  try {
    await ElMessageBox.confirm('提交后明细不可再修改，确定提交评审吗？', '提交评审', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
  } catch (e) {
    return
  }
  runAction('submit', () => submitChange(changeId.value), '已提交评审')
}

async function handleApprove() {
  try {
    await ElMessageBox.confirm('确认批准该工程变更单吗？', '批准', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
  } catch (e) {
    return
  }
  runAction('approve', () => approveChange(changeId.value), '已批准')
}

async function handleReject() {
  let reason = ''
  try {
    const prompt = await ElMessageBox.prompt('请填写驳回原因（必填）', '驳回', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputValidator: value => (value && value.trim() ? true : '驳回原因不能为空')
    })
    reason = (prompt.value || '').trim()
  } catch (e) {
    return
  }
  runAction('reject', () => rejectChange(changeId.value, reason), '已驳回')
}

async function handleCancel() {
  try {
    await ElMessageBox.confirm('确认取消该工程变更单吗？', '取消', {
      confirmButtonText: '确定',
      cancelButtonText: '返回',
      type: 'warning'
    })
  } catch (e) {
    return
  }
  runAction('cancel', () => cancelChange(changeId.value), '已取消')
}

async function handleApply() {
  try {
    await ElMessageBox.confirm(
      '应用后将按生效日切换生产 BOM 结构行，且不可自动回滚，确定继续吗？',
      '应用到生产 BOM',
      { confirmButtonText: '确定应用', cancelButtonText: '取消', type: 'warning' }
    )
  } catch (e) {
    return
  }
  runAction('apply', () => applyChange(changeId.value), '已应用到生产 BOM')
}

onMounted(() => {
  loadChange()
  loadImpact()
})
</script>

<style scoped lang="scss">
.ec-detail {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.ec-impact {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.ec-impact__section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.ec-impact__title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.ec-impact__count {
  font-weight: 400;
  color: var(--color-text-tertiary);
}
</style>
