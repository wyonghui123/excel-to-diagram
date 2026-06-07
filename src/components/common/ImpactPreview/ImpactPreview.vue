<template>
  <div class="impact-preview">
    <div class="impact-preview__header">
      <h3 class="impact-preview__title">影响范围预览</h3>
    </div>

    <div v-if="loading" class="impact-preview__loading">
      <el-icon class="is-loading"><Loading /></el-icon>
      <span>加载中...</span>
    </div>

    <template v-else>
      <div class="impact-preview__summary">
        <div class="summary-title">统计摘要</div>
        <div class="summary-cards">
          <div
            v-for="stat in summaryStats"
            :key="stat.type"
            class="summary-card"
            :class="`summary-card--${stat.type}`"
          >
            <div class="summary-card__icon">
              <component :is="stat.icon" />
            </div>
            <div class="summary-card__content">
              <span class="summary-card__value">{{ stat.count }}</span>
              <span class="summary-card__label">{{ stat.label }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="impact-preview__detail">
        <div class="detail-header" @click="toggleDetail">
          <div class="detail-header__left">
            <el-icon class="detail-header__icon" :class="{ expanded: detailExpanded }">
              <ArrowRight />
            </el-icon>
            <span class="detail-header__title">详细对象清单</span>
            <span class="detail-header__count">({{ filteredTableData.length }} 项)</span>
          </div>
          <div class="detail-header__actions">
            <el-dropdown trigger="click" @command="handleFilterCommand">
              <el-button type="default" size="small">
                <el-icon><Filter /></el-icon>
                过滤
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="all">全部</el-dropdown-item>
                  <el-dropdown-item command="direct">直接匹配</el-dropdown-item>
                  <el-dropdown-item command="inherit">向下继承</el-dropdown-item>
                  <el-dropdown-item command="propagate">向上传播</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button type="primary" size="small" @click="handleExport">
              <el-icon><Download /></el-icon>
              导出 Excel
            </el-button>
          </div>
        </div>

        <el-collapse-transition>
          <div v-show="detailExpanded" class="detail-content">
            <el-table
              :data="paginatedData"
              style="width: 100%"
              border
              stripe
              @sort-change="handleSortChange"
            >
              <el-table-column
                prop="type"
                label="类型"
                width="100"
                sortable="custom"
              >
                <template #default="{ row }">
                  <span class="type-tag" :class="`type-tag--${row.type}`">
                    {{ typeLabels[row.type] || row.type }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column
                prop="code"
                label="编码"
                min-width="150"
                sortable="custom"
                show-overflow-tooltip
              />
              <el-table-column
                prop="name"
                label="名称"
                min-width="150"
                sortable="custom"
                show-overflow-tooltip
              />
              <el-table-column
                prop="impactType"
                label="影响方式"
                width="120"
                sortable="custom"
              >
                <template #default="{ row }">
                  <span class="impact-tag" :class="`impact-tag--${row.impactType}`">
                    {{ impactTypeLabels[row.impactType] || row.impactType }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column
                prop="permissionLevel"
                label="权限级别"
                width="100"
                sortable="custom"
              >
                <template #default="{ row }">
                  <span class="permission-tag" :class="`permission-tag--${row.permissionLevel}`">
                    {{ permissionLabels[row.permissionLevel] || row.permissionLevel }}
                  </span>
                </template>
              </el-table-column>
            </el-table>

            <div class="detail-pagination">
              <el-pagination
                v-model:current-page="currentPage"
                v-model:page-size="pageSize"
                :page-sizes="[10, 20, 50, 100]"
                :total="filteredTableData.length"
                layout="total, sizes, prev, pager, next, jumper"
                @size-change="handleSizeChange"
                @current-change="handleCurrentChange"
              />
            </div>
          </div>
        </el-collapse-transition>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { Loading, ArrowRight, Filter, Download } from '@element-plus/icons-vue'
import * as XLSX from 'xlsx'

const props = defineProps({
  impactData: {
    type: Object,
    default: () => ({})
  },
  loading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['export', 'filter-change'])

const typeLabels = {
  domain: '领域',
  subDomain: '子领域',
  serviceModule: '服务模块',
  businessObject: '业务对象'
}

const impactTypeLabels = {
  direct: '直接匹配',
  inherit: '向下继承',
  propagate: '向上传播'
}

const permissionLabels = {
  read: '读',
  write: '写',
  admin: '管理'
}

const detailExpanded = ref(true)
const currentPage = ref(1)
const pageSize = ref(20)
const filterType = ref('all')
const sortProp = ref('')
const sortOrder = ref('')

const summaryStats = computed(() => {
  const data = props.impactData || {}
  return [
    {
      type: 'domain',
      label: '领域',
      count: data.domainCount || 0,
      icon: 'div'
    },
    {
      type: 'subDomain',
      label: '子领域',
      count: data.subDomainCount || 0,
      icon: 'div'
    },
    {
      type: 'serviceModule',
      label: '服务模块',
      count: data.serviceModuleCount || 0,
      icon: 'div'
    },
    {
      type: 'businessObject',
      label: '业务对象',
      count: data.businessObjectCount || 0,
      icon: 'div'
    }
  ]
})

const tableData = computed(() => {
  const data = props.impactData || {}
  const items = data.items || []
  return items.map(item => ({
    ...item,
    type: item.type || 'unknown',
    code: item.code || '',
    name: item.name || '',
    impactType: item.impactType || 'direct',
    permissionLevel: item.permissionLevel || 'read'
  }))
})

const filteredTableData = computed(() => {
  let data = tableData.value

  if (filterType.value !== 'all') {
    data = data.filter(item => item.impactType === filterType.value)
  }

  if (sortProp.value && sortOrder.value) {
    data = [...data].sort((a, b) => {
      const aVal = a[sortProp.value] || ''
      const bVal = b[sortProp.value] || ''
      const compareResult = String(aVal).localeCompare(String(bVal), 'zh-CN')
      return sortOrder.value === 'ascending' ? compareResult : -compareResult
    })
  }

  return data
})

const paginatedData = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredTableData.value.slice(start, end)
})

function toggleDetail() {
  detailExpanded.value = !detailExpanded.value
}

function handleFilterCommand(command) {
  filterType.value = command
  currentPage.value = 1
  emit('filter-change', { type: command })
}

function handleSortChange({ prop, order }) {
  sortProp.value = prop || ''
  sortOrder.value = order || ''
}

function handleSizeChange(val) {
  pageSize.value = val
  currentPage.value = 1
}

function handleCurrentChange(val) {
  currentPage.value = val
}

function handleExport() {
  const data = filteredTableData.value.map(item => ({
    '类型': typeLabels[item.type] || item.type,
    '编码': item.code,
    '名称': item.name,
    '影响方式': impactTypeLabels[item.impactType] || item.impactType,
    '权限级别': permissionLabels[item.permissionLevel] || item.permissionLevel
  }))

  const ws = XLSX.utils.json_to_sheet(data)
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, '影响范围')

  const colWidths = [
    { wch: 12 },
    { wch: 25 },
    { wch: 25 },
    { wch: 12 },
    { wch: 10 }
  ]
  ws['!cols'] = colWidths

  const fileName = `影响范围_${new Date().toISOString().slice(0, 10)}.xlsx`
  XLSX.writeFile(wb, fileName)

  emit('export', { fileName, count: data.length })
}

watch(() => props.impactData, () => {
  currentPage.value = 1
}, { deep: true })
</script>

<style scoped>
.impact-preview {
  background: var(--color-bg-container);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-secondary);
  overflow: hidden;
}

.impact-preview__header {
  padding: var(--spacing-md) var(--spacing-lg);
  border-bottom: 1px solid var(--color-border-secondary);
  background: var(--color-bg-secondary);
}

.impact-preview__title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.impact-preview__loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xxl);
  color: var(--color-text-tertiary);
  gap: var(--spacing-sm);
}

.impact-preview__loading .el-icon {
  font-size: 32px;
  color: var(--color-primary);
}

.impact-preview__summary {
  padding: var(--spacing-lg);
  border-bottom: 1px solid var(--color-border-secondary);
}

.summary-title {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  margin-bottom: var(--spacing-md);
}

.summary-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--spacing-md);
}

.summary-card {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-md);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
  transition: all var(--transition-normal);
}

.summary-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-sm);
}

.summary-card__icon {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
}

.summary-card--domain .summary-card__icon {
  background: #fff7ed;
  color: #ea580c;
}

.summary-card--subDomain .summary-card__icon {
  background: #eff6ff;
  color: #2563eb;
}

.summary-card--serviceModule .summary-card__icon {
  background: #f0fdf4;
  color: #16a34a;
}

.summary-card--businessObject .summary-card__icon {
  background: #f5f3ff;
  color: #7c3aed;
}

.summary-card__content {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.summary-card__value {
  font-size: var(--font-size-xxl);
  font-weight: var(--font-weight-bold);
  color: var(--color-primary);
  line-height: 1;
}

.summary-card__label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.impact-preview__detail {
  padding: var(--spacing-lg);
}

.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  padding: var(--spacing-sm) 0;
  user-select: none;
}

.detail-header__left {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.detail-header__icon {
  transition: transform var(--transition-normal);
  color: var(--color-text-tertiary);
}

.detail-header__icon.expanded {
  transform: rotate(90deg);
}

.detail-header__title {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

.detail-header__count {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
}

.detail-header__actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.detail-content {
  margin-top: var(--spacing-md);
}

.type-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
}

.type-tag--domain {
  background: #fff7ed;
  color: #ea580c;
}

.type-tag--subDomain {
  background: #eff6ff;
  color: #2563eb;
}

.type-tag--serviceModule {
  background: #f0fdf4;
  color: #16a34a;
}

.type-tag--businessObject {
  background: #f5f3ff;
  color: #7c3aed;
}

.impact-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
}

.impact-tag--direct {
  background: #f6ffed;
  color: #52c41a;
  border: 1px solid #b7eb8f;
}

.impact-tag--inherit {
  background: #e6f7ff;
  color: #1890ff;
  border: 1px solid #91d5ff;
}

.impact-tag--propagate {
  background: #fff7e6;
  color: #fa8c16;
  border: 1px solid #ffd591;
}

.permission-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
}

.permission-tag--read {
  background: var(--color-bg-secondary);
  color: var(--color-text-secondary);
}

.permission-tag--write {
  background: var(--color-primary-bg);
  color: var(--color-primary);
}

.permission-tag--admin {
  background: #f6ffed;
  color: #52c41a;
}

.detail-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--spacing-md);
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--color-border-secondary);
}

@media (max-width: 768px) {
  .summary-cards {
    grid-template-columns: repeat(2, 1fr);
  }

  .detail-header {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-sm);
  }

  .detail-header__actions {
    width: 100%;
    justify-content: flex-end;
  }
}
</style>
