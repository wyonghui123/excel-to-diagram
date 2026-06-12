<template>
  <div class="audit-log-management">
    <div class="audit-overview" v-if="overview">
      <div class="stat-cards">
        <div class="stat-card stat-card--today">
          <div class="stat-card__icon">
            <el-icon :size="28"><Document /></el-icon>
          </div>
          <div class="stat-card__content">
            <div class="stat-card__value">{{ overview.today_count }}</div>
            <div class="stat-card__label">今日操作</div>
          </div>
        </div>
        <div class="stat-card stat-card--security">
          <div class="stat-card__icon">
            <el-icon :size="28"><Lock /></el-icon>
          </div>
          <div class="stat-card__content">
            <div class="stat-card__value">{{ overview.security_count }}</div>
            <div class="stat-card__label">安全事件</div>
          </div>
        </div>
        <div class="stat-card stat-card--error">
          <div class="stat-card__icon">
            <el-icon :size="28"><WarningFilled /></el-icon>
          </div>
          <div class="stat-card__content">
            <div class="stat-card__value">{{ overview.failed }}</div>
            <div class="stat-card__label">失败记录</div>
          </div>
        </div>
        <div class="stat-card stat-card--total">
          <div class="stat-card__icon">
            <el-icon :size="28"><DataLine /></el-icon>
          </div>
          <div class="stat-card__content">
            <div class="stat-card__value">{{ overview.total }}</div>
            <div class="stat-card__label">日志总数</div>
          </div>
        </div>
      </div>
      <div class="chart-row">
        <div class="chart-card">
          <div class="chart-card__title">日志类型分布</div>
          <div ref="pieChartRef" class="chart-container"></div>
        </div>
        <div class="chart-card chart-card--wide">
          <div class="chart-card__title">
            操作趋势
            <el-radio-group v-model="trendDays" size="small" @change="loadOverview" style="margin-left: 12px;">
              <el-radio-button :value="7">近7天</el-radio-button>
              <el-radio-button :value="30">近30天</el-radio-button>
            </el-radio-group>
          </div>
          <div ref="trendChartRef" class="chart-container"></div>
        </div>
      </div>
    </div>

    <MetaListPage
      ref="metaListRef"
      object-type="audit_log"
      :options="{
        autoLoad: true,
        pageSize: 50,
        debug: false
      }"
      @detail="handleViewDetail"
      @row-click="handleRowClick"
    >
      <template #cell-id="{ row }">
        <a class="id-link" @click.stop="handleViewDetail({ row })">{{ row.id }}</a>
      </template>

      <template #cell-object_type="{ row }">
        {{ getObjectTypeLabel(row.object_type) }}
      </template>

      <template #cell-field_name="{ row }">
        <span v-if="row.field_name && row.field_name !== '_record'" class="field-name-badge">
          {{ getFieldName(row.field_name, row.object_type) }}
        </span>
        <span v-else class="no-field">-</span>
      </template>
    </MetaListPage>

    <el-drawer
      v-model="showDetail"
      title="审计日志详情"
      size="720px"
      direction="rtl"
    >
      <div v-if="selectedLog" class="detail-content">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="日志ID">
            {{ selectedLog.id }}
          </el-descriptions-item>
          <el-descriptions-item label="操作时间">
            {{ formatDateTime(selectedLog.created_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="日志类型">
            <el-tag :type="getCategoryTagType(selectedLog.log_category)" size="small">
              {{ getCategoryLabel(selectedLog.log_category) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="日志级别">
            <el-tag :type="getLevelTagType(selectedLog.log_level)" size="small">
              {{ getLevelLabel(selectedLog.log_level) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="操作类型">
            <el-tag :type="getActionTagType(selectedLog.action)" size="small">
              {{ getActionLabel(selectedLog.action) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="对象类型">
            {{ getObjectTypeLabel(selectedLog.object_type) }}
          </el-descriptions-item>
          <el-descriptions-item label="对象">
            <span class="object-id">{{ selectedLog.object_id }}</span>
            <span v-if="selectedLog.object_display" class="object-display">
              {{ selectedLog.object_display }}
            </span>
            <span v-else-if="selectedLog.business_key" class="object-display">
              {{ selectedLog.business_key }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item v-if="selectedLog.parent_object_type" label="父对象">
            <span class="parent-type">{{ getObjectTypeLabel(selectedLog.parent_object_type) }}</span>
            <span class="object-id">{{ selectedLog.parent_object_id }}</span>
            <span v-if="selectedLog.parent_object_display" class="object-display">
              {{ selectedLog.parent_object_display }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="业务标识">
            {{ selectedLog.formatted_identity || selectedLog.business_key || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="操作人">
            {{ selectedLog.user_name || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="IP地址">
            {{ selectedLog.ip_address || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="字段名">
            {{ getFieldName(selectedLog.field_name, selectedLog.object_type) }}
          </el-descriptions-item>
          <el-descriptions-item label="旧值">
            <div class="value-text">{{ selectedLog.old_value || '-' }}</div>
          </el-descriptions-item>
          <el-descriptions-item label="新值">
            <div class="value-text">{{ selectedLog.new_value || '-' }}</div>
          </el-descriptions-item>
          <el-descriptions-item label="链路追踪ID">
            {{ selectedLog.trace_id || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="事务ID">
            {{ selectedLog.transaction_id || '-' }}
          </el-descriptions-item>
        </el-descriptions>

        <!-- [FIX 2026-06-11] DELETE 操作的完整字段明细 JSON 块 -->
        <div v-if="selectedLog.action === 'DELETE' && hasDeletedData" class="deleted-data-section">
          <div class="section-title">
            <el-icon><Delete /></el-icon>
            <span>删除对象完整明细</span>
            <el-tag size="small" type="info">{{ deletedDataKeys.length }} 个字段</el-tag>
          </div>
          <pre class="deleted-data-json">{{ deletedDataFormatted }}</pre>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { MetaListPage } from '@/components/common/MetaListPage'
import { formatDate } from '@/composables/useMetaList'
import * as auditLogService from '@/services/auditLogService'
// [FR-004] ECharts 按需导入: 只注册使用的图表类型, 减少 ~600KB
import * as echarts from 'echarts/core'
import { PieChart, LineChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  PieChart, LineChart,
  TitleComponent, TooltipComponent, LegendComponent, GridComponent,
  CanvasRenderer
])
import { Document, Lock, WarningFilled, DataLine, Delete } from '@element-plus/icons-vue'

const metaListRef = ref(null)
const showDetail = ref(false)
const selectedLog = ref(null)
const overview = ref(null)
const trendDays = ref(7)
const pieChartRef = ref(null)
const trendChartRef = ref(null)

let pieChart = null
let trendChart = null

// [FIX 2026-06-11] 点击列表行 → 打开 detail drawer (统一入口, 复用 handleViewDetail)
function handleRowClick(row) {
  if (!row || !row.id) return
  handleViewDetail({ row })
}

async function handleViewDetail(payload) {
  selectedLog.value = payload.row
  showDetail.value = true
  // [FIX 2026-06-11] 列表接口不带 extra_data 完整字段 (后端 list 不解析),
  // 详情接口解析为 extra_data_parsed. 这里调详情 API 补全 deleted_data 等 JSON 明细.
  if (payload.row && payload.row.id) {
    try {
      const res = await auditLogService.getLogById(payload.row.id)
      if (res && res.success && res.data) {
        selectedLog.value = { ...payload.row, ...res.data }
      }
    } catch (e) {
      console.warn('Failed to load audit log detail:', e)
    }
  }
}

// [FIX 2026-06-11] DELETE 明细 JSON 渲染: 兼容后端 extra_data_parsed.deleted_data
// 与可能的 selectedLog.deleted_data (旧版字段) 两种结构.
const deletedDataParsed = computed(() => {
  if (!selectedLog.value) return {}
  const parsed = selectedLog.value.extra_data_parsed || {}
  return parsed.deleted_data || selectedLog.value.deleted_data || {}
})

const hasDeletedData = computed(() => {
  return Object.keys(deletedDataParsed.value).length > 0
})

const deletedDataKeys = computed(() => Object.keys(deletedDataParsed.value))

const deletedDataFormatted = computed(() => {
  try {
    return JSON.stringify(deletedDataParsed.value, null, 2)
  } catch (e) {
    return String(deletedDataParsed.value)
  }
})

async function loadOverview() {
  try {
    const res = await auditLogService.getOverview({ days: trendDays.value })
    if (res.success) {
      overview.value = res.data
      await nextTick()
      renderPieChart(res.data.by_category || [])
      renderTrendChart(res.data.trend || [])
    }
  } catch (e) {
    console.warn('Failed to load audit overview:', e)
  }
}

const CATEGORY_COLORS = {
  business: '#ea580c',
  security: '#dc2626',
  operation: '#f59e0b',
  performance: '#16a34a',
  system: '#6b7280'
}

const CATEGORY_LABELS = {
  business: '业务审计',
  security: '安全日志',
  operation: '运营日志',
  performance: '性能日志',
  system: '系统日志'
}

function renderPieChart(categoryData) {
  if (!pieChartRef.value) return
  if (!pieChart) {
    pieChart = echarts.init(pieChartRef.value)
  }
  const data = categoryData.map(item => ({
    name: CATEGORY_LABELS[item.category] || item.category,
    value: item.count,
    itemStyle: { color: CATEGORY_COLORS[item.category] || '#909399' }
  }))
  pieChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, type: 'scroll' },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['50%', '45%'],
      avoidLabelOverlap: true,
      itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
      label: { show: false },
      emphasis: { label: { show: true, fontSize: 14, fontWeight: 'bold' } },
      data
    }]
  })
}

function renderTrendChart(trendData) {
  if (!trendChartRef.value) return
  if (!trendChart) {
    trendChart = echarts.init(trendChartRef.value)
  }
  const dates = trendData.map(d => d.date.slice(5))
  const counts = trendData.map(d => d.count)
  trendChart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 20, top: 20, bottom: 30 },
    xAxis: { type: 'category', data: dates, boundaryGap: false },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{
      type: 'line',
      data: counts,
      smooth: true,
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: 'rgba(234,88,12,0.3)' },
        { offset: 1, color: 'rgba(234,88,12,0.02)' }
      ])},
      lineStyle: { color: '#ea580c', width: 2 },
      itemStyle: { color: '#ea580c' }
    }]
  })
}

function handleResize() {
  pieChart?.resize()
  trendChart?.resize()
}

onMounted(() => {
  loadOverview()
  window.addEventListener('resize', handleResize)
  // [FIX 2026-06-12] 强制覆盖 el-table inline style height (MetaListPage :height='100%').
  // inline style 优先级 > CSS !important, 必须 JS 改. window resize 也要重新应用.
  setTimeout(forceElTableHeight, 0)
  setTimeout(forceElTableHeight, 200)
  window.addEventListener('resize', forceElTableHeight)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  window.removeEventListener('resize', forceElTableHeight)
  pieChart?.dispose()
  trendChart?.dispose()
  pieChart = null
  trendChart = null
})

// [FIX 2026-06-12] 强制 el-table 高度 = calc(100vh - 440px), 覆盖 MetaListPage
// 模板里 :height="tableHeight" 写到根元素的 inline style="height: 100%".
// inline style 优先级 > !important CSS, 必须 JS 改. 否则 50 行数据无法滚动.
function forceElTableHeight() {
  const tables = document.querySelectorAll('.audit-log-management .el-table')
  const target = `calc(100vh - 440px)`
  tables.forEach(t => { t.style.height = target })
}

const OBJECT_TYPE_MAP = {
  'user': '用户',
  'role': '角色',
  'user_group': '用户组',
  'product': '产品',
  'version': '版本',
  'domain': '领域',
  'sub_domain': '子域',
  'service_module': '服务模块',
  'business_object': '业务对象',
  'relationship': '关系',
  'annotation': '标注',
  'enum_type': '枚举类型',
  'enum_value': '枚举值',
  '__audit_failure__': '审计失败'
}

const COMMON_FIELD_NAMES = {
  'id': 'ID',
  'name': '名称',
  'code': '编码',
  'description': '描述',
  'created_at': '创建时间',
  'updated_at': '更新时间',
  'created_by': '创建人',
  'updated_by': '更新人',
  'status': '状态',
  'is_active': '是否激活',
  'username': '用户名',
  'display_name': '显示名称',
  'email': '邮箱'
}

function getObjectTypeLabel(type) {
  return OBJECT_TYPE_MAP[type] || type
}

function getFieldName(fieldKey, objectType) {
  if (!fieldKey || fieldKey === '_record') return '-'
  return COMMON_FIELD_NAMES[fieldKey] || fieldKey
}

function getCategoryTagType(category) {
  const map = {
    'business': 'primary',
    'security': '',
    'operation': '',
    'performance': '',
    'system': ''
  }
  return map[category] || ''
}

function getCategoryLabel(category) {
  const map = {
    'business': '业务审计',
    'security': '安全日志',
    'operation': '运营日志',
    'performance': '性能日志',
    'system': '系统日志'
  }
  return map[category] || category
}

function getLevelTagType(level) {
  const map = {
    'DEBUG': 'info',
    'INFO': 'primary',
    'WARNING': 'warning',
    'ERROR': 'danger',
    'CRITICAL': 'danger'
  }
  return map[level] || 'info'
}

function getLevelLabel(level) {
  const map = {
    'DEBUG': '调试',
    'INFO': '信息',
    'WARNING': '警告',
    'ERROR': '错误',
    'CRITICAL': '严重'
  }
  return map[level] || level
}

function getActionTagType(action) {
  const map = {
    'CREATE': 'success',
    'UPDATE': 'warning',
    'DELETE': 'danger',
    'ASSOCIATE': 'primary',
    'DISSOCIATE': 'info'
  }
  return map[action] || 'info'
}

function getActionLabel(action) {
  const map = {
    'CREATE': '创建',
    'UPDATE': '更新',
    'DELETE': '删除',
    'ASSOCIATE': '关联',
    'DISSOCIATE': '取消关联'
  }
  return map[action] || action
}

function formatDateTime(datetime) {
  return formatDate(datetime, 'YYYY-MM-DD HH:mm:ss')
}
</script>

<style scoped>
/* [FIX 2026-06-12] 整页 flex column: overview 占自然高度, MetaListPage 填满剩余空间.
   之前 height:100% + overflow:hidden 父子同时锁死高度, 内容超出后整页无法 scroll down. */
.audit-log-management {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.audit-overview {
  flex-shrink: 0;
  margin-bottom: 16px;
}

/* [FIX 2026-06-12] MetaListPage 是嵌入模式, 必须 flex:1 填满剩余高度,
   且 min-height:0 否则 flex item 默认 min-height:auto 不会缩小. */
.audit-log-management :deep(.meta-list-page) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

/* [FIX 2026-06-12] 强制 el-table__body-wrapper 内部滚动条.
   Element Plus 的 el-table 内部用 .el-scrollbar 包装, 真滚动容器是
   .el-scrollbar__wrap (不是 body-wrapper). el-scrollbar 默认隐藏滚动条,
   用户看不到就以为不能滚, 这里强制常驻显示. */
.audit-log-management :deep(.custom-table) {
  /* 视口高度 - 顶部导航 ~50 - overview ~250 - 分页 ~60 - 工具栏 ~50 - 余量 30
     800px 视口下约 360px, 1024px 视口约 580px.  */
  height: calc(100vh - 440px) !important;
  min-height: 360px;
  display: flex !important;
  flex-direction: column !important;
}
.audit-log-management :deep(.el-table__inner-wrapper) {
  display: flex !important;
  flex-direction: column !important;
  flex: 1 1 auto !important;
  min-height: 0 !important;
}
.audit-log-management :deep(.el-table__body-wrapper) {
  flex: 1 1 auto !important;
  min-height: 0 !important;
  overflow: visible !important;
}
/* [FIX 2026-06-12] 真滚动容器: el-scrollbar__wrap.
   强制常驻滚动条 + 略宽让用户清楚看到. */
.audit-log-management :deep(.el-table__body-wrapper .el-scrollbar__wrap) {
  overflow-y: auto !important;
  max-height: 100% !important;
}
.audit-log-management :deep(.el-table__body-wrapper .el-scrollbar__bar.is-vertical) {
  opacity: 1 !important;
  display: block !important;
  width: 8px !important;
}
/* 滚动条样式: 让用户清楚看到位置 */
.audit-log-management :deep(.el-table__body-wrapper .el-scrollbar__bar .el-scrollbar__thumb) {
  background: rgba(144, 147, 153, 0.5) !important;
  border-radius: 4px !important;
}

.stat-cards {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
}

.stat-card {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;  /* 16→12 缩卡片高度 */
  border-radius: 8px;
  background: #fff;
  border: 1px solid #ebeef5;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}

.stat-card__icon {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-card--today .stat-card__icon {
  background: rgba(234, 88, 12, 0.1);
  color: #ea580c;
}

.stat-card--security .stat-card__icon {
  background: rgba(245, 108, 108, 0.1);
  color: #F56C6C;
}

.stat-card--error .stat-card__icon {
  background: rgba(230, 162, 60, 0.1);
  color: #E6A23C;
}

.stat-card--total .stat-card__icon {
  background: rgba(103, 194, 58, 0.1);
  color: #67C23A;
}

.stat-card__value {
  font-size: 24px;
  font-weight: 600;
  line-height: 1.2;
  color: var(--color-text-primary, #303133);
}

.stat-card__label {
  font-size: 13px;
  color: var(--color-text-secondary, #909399);
  margin-top: 2px;
}

.chart-row {
  display: flex;
  gap: 16px;
}

.chart-card {
  flex: 1;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 12px 14px;  /* 16→12 缩图表卡片 */
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}

.chart-card--wide {
  flex: 2;
}

.chart-card__title {
  font-size: 13px;  /* 14→13 缩标题 */
  font-weight: 500;
  color: var(--color-text-primary, #303133);
  margin-bottom: 6px;  /* 8→6 */
  display: flex;
  align-items: center;
}

/* [FIX 2026-06-12] 图表高度 240→140, 让 audit-overview 总高 < 250px,
   释放空间给 meta-list-page 让 el-table 至少 400px 高度能内部滚动. */
.chart-container {
  height: 140px;
}

.field-name-badge {
  font-family: 'Consolas', 'Monaco', monospace;
  color: var(--color-text-secondary, #666);
  background: #f5f5f5;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 12px;
  border: 1px solid #e8e8e8;
}

.no-field {
  color: var(--color-text-tertiary, #999);
  font-style: italic;
}

.detail-content {
  padding: var(--spacing-md);
}

.value-text {
  max-height: 200px;
  overflow-y: auto;
  word-break: break-all;
}

.object-id {
  font-family: 'Consolas', 'Monaco', monospace;
  color: var(--color-text-tertiary, #999);
  font-size: 12px;
  margin-right: 8px;
}

.object-display {
  color: var(--el-color-primary, #ea580c);
  font-weight: 500;
}

.parent-type {
  display: inline-block;
  padding: 1px 6px;
  background: #e6f4ff;
  color: #0ea5e9;
  font-size: 12px;
  border-radius: 3px;
  margin-right: 6px;
}

/* [FIX 2026-06-11] ID 列链接样式 */
.id-link {
  color: var(--el-color-primary, #ea580c);
  cursor: pointer;
  text-decoration: none;
  font-weight: 500;
}
.id-link:hover {
  text-decoration: underline;
}

/* [FIX 2026-06-11] DELETE 明细 JSON 块样式 */
.deleted-data-section {
  margin-top: 24px;
  padding: 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
}

.deleted-data-section .section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-primary, #303133);
  margin-bottom: 12px;
}

.deleted-data-section .section-title .el-icon {
  color: #f56c6c;
}

.deleted-data-json {
  margin: 0;
  padding: 12px;
  background: #1f2937;
  color: #f3f4f6;
  border-radius: 4px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.6;
  max-height: 360px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
