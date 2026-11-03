<template>
  <PageShell title="工程变更" :show-back-button="false">
    <template #title-bar-actions>
      <AppButton
        variant="primary"
        data-test="ec-create"
        @click="goCreate"
      >
        新建变更
      </AppButton>
    </template>

    <div class="ec-list">
      <div class="ec-toolbar">
        <span class="ec-toolbar__label">状态</span>
        <el-select
          v-model="filters.status"
          clearable
          placeholder="全部状态"
          class="ec-toolbar__status"
          data-test="ec-status-filter"
          @change="handleSearch"
        >
          <el-option
            v-for="option in STATUS_OPTIONS"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
        <el-button type="primary" data-test="ec-search" @click="handleSearch">查询</el-button>
        <el-button data-test="ec-reset" @click="handleReset">重置</el-button>
      </div>

      <el-alert
        v-if="error"
        type="error"
        :closable="false"
        show-icon
        class="ec-alert"
        data-test="ec-list-error"
        :title="error"
      />

      <el-table
        v-loading="loading"
        :data="rows"
        row-key="id"
        class="ec-table"
        data-test="ec-table"
        @row-click="handleRowClick"
      >
        <el-table-column prop="change_no" label="变更单号" min-width="150">
          <template #default="{ row }">
            <el-link type="primary" data-test="ec-row-no" @click.stop="goDetail(row)">
              {{ row.change_no || '—' }}
            </el-link>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small" data-test="ec-row-status">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="物料" width="100">
          <template #default="{ row }">
            {{ row.item_id ?? '—' }}
          </template>
        </el-table-column>
        <el-table-column label="项目" width="100">
          <template #default="{ row }">
            {{ row.project_id ?? '—' }}
          </template>
        </el-table-column>
        <el-table-column label="生效日" width="120">
          <template #default="{ row }">
            {{ row.effective_date || '—' }}
          </template>
        </el-table-column>
        <el-table-column label="明细数" width="90">
          <template #default="{ row }">
            {{ row.line_count ?? 0 }}
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">
            {{ row.created_at || '—' }}
          </template>
        </el-table-column>
        <template #empty>
          <span data-test="ec-empty">暂无工程变更单</span>
        </template>
      </el-table>

      <div class="ec-pagination">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          data-test="ec-pagination"
          @current-change="load"
          @size-change="handleSizeChange"
        />
      </div>
    </div>
  </PageShell>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { PageShell, AppButton } from '@/components/common'
import { listChanges } from '@/services/engineeringChangeService'

defineOptions({ name: 'EngineeringChangeListPage' })

const STATUS_OPTIONS = [
  { value: 'draft', label: '草稿' },
  { value: 'in_review', label: '评审中' },
  { value: 'approved', label: '已批准' },
  { value: 'applied', label: '已应用' },
  { value: 'rejected', label: '已驳回' },
  { value: 'cancelled', label: '已取消' }
]

const STATUS_TAG_TYPES = {
  draft: 'info',
  in_review: 'primary',
  approved: 'success',
  applied: 'success',
  rejected: 'danger',
  cancelled: 'warning'
}

const router = useRouter()

const filters = reactive({ status: '' })
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const error = ref('')

function statusLabel(status) {
  return STATUS_OPTIONS.find(option => option.value === status)?.label || status || '—'
}

function statusTagType(status) {
  return STATUS_TAG_TYPES[status] || 'info'
}

function handleSearch() {
  page.value = 1
  load()
}

function handleReset() {
  filters.status = ''
  page.value = 1
  load()
}

function handleSizeChange() {
  page.value = 1
  load()
}

function goCreate() {
  router.push({ name: 'engineering-change-diff' })
}

function goDetail(row) {
  if (!row?.id) return
  router.push({ name: 'engineering-change-detail', params: { id: String(row.id) } })
}

function handleRowClick(row) {
  goDetail(row)
}

async function load() {
  loading.value = true
  error.value = ''
  const params = { page: page.value, page_size: pageSize.value }
  if (filters.status) params.status = filters.status

  try {
    const result = await listChanges(params)
    if (!result.success) {
      error.value = result.message || '工程变更单列表查询失败'
      rows.value = []
      total.value = 0
      return
    }
    const payload = result.data || {}
    rows.value = Array.isArray(payload) ? payload : (payload.items || [])
    total.value = Array.isArray(payload) ? payload.length : (payload.total || 0)
  } catch (e) {
    error.value = e?.message || '工程变更单列表查询失败'
    rows.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped lang="scss">
.ec-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.ec-toolbar {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
}

.ec-toolbar__label {
  font-size: 13px;
  color: var(--color-text-secondary);
}

.ec-toolbar__status {
  width: 160px;
}

.ec-alert {
  margin: 0;
}

.ec-table {
  width: 100%;
}

.ec-pagination {
  display: flex;
  justify-content: flex-end;
  padding-top: var(--spacing-sm);
}
</style>
