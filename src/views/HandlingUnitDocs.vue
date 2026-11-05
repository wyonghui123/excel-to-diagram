<template>
  <PageShell title="包装容器查询">
    <div class="hu-docs-page">
      <AppCard title="单据查容器">
        <div class="filter-row">
          <el-select v-model="docType" class="filter-select" @change="searchByDoc">
            <el-option label="收货单" value="receipt" />
            <el-option label="发货单" value="shipment" />
            <el-option label="调拨单" value="transfer_order" />
          </el-select>
          <el-input
            v-model="docNo"
            class="filter-input"
            placeholder="输入单据号后回车"
            clearable
            @keyup.enter="searchByDoc"
          />
          <AppButton variant="primary" size="sm" :loading="loadingDoc" @click="searchByDoc">
            查询
          </AppButton>
        </div>

        <EmptyState
          v-if="!groupedRows.length && !loadingDoc"
          type="box"
          title="暂无容器"
          description="输入单据号查询该单据关联的包装容器"
        />
        <table v-else class="hu-table">
          <thead>
            <tr>
              <th>容器号</th>
              <th>容器状态</th>
              <th>关系</th>
              <th>方向</th>
              <th>数量</th>
              <th>单据号</th>
              <th>单据日期</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in groupedRows"
              :key="row.hu_id"
              class="hu-row"
              @click="openContents(row)"
            >
              <td>{{ row.hu_no || `#${row.hu_id}` }}</td>
              <td><el-tag size="small">{{ row.hu_status || '—' }}</el-tag></td>
              <td>{{ linkTypeLabel(row.link_type) }}</td>
              <td>{{ row.direction === 'in' ? '入库' : '出库' }}</td>
              <td>{{ formatQty(row.qty) }}</td>
              <td>{{ row.doc_no }}</td>
              <td>{{ row.doc_date || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </AppCard>

      <AppCard title="容器查单据" class="card-gap">
        <div class="filter-row">
          <el-input
            v-model="huNo"
            class="filter-input"
            placeholder="输入容器号后回车"
            clearable
            @keyup.enter="searchByHu"
          />
          <AppButton variant="secondary" size="sm" :loading="loadingHu" @click="searchByHu">
            查询
          </AppButton>
        </div>

        <EmptyState
          v-if="!huRows.length && !loadingHu"
          type="box"
          title="暂无单据"
          description="输入容器号查询该容器（含子容器）关联的单据"
        />
        <table v-else class="hu-table">
          <thead>
            <tr>
              <th>单据类型</th>
              <th>单据号</th>
              <th>单据日期</th>
              <th>行号</th>
              <th>方向</th>
              <th>关系</th>
              <th>数量</th>
              <th>单据状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in huRows" :key="row.id">
              <td>{{ docTypeLabel(row.doc_type) }}</td>
              <td>{{ row.doc_no || '—' }}</td>
              <td>{{ row.doc_date || '—' }}</td>
              <td>{{ row.line_no || '—' }}</td>
              <td>{{ row.direction === 'in' ? '入库' : '出库' }}</td>
              <td>{{ linkTypeLabel(row.link_type) }}</td>
              <td>{{ formatQty(row.qty) }}</td>
              <td>{{ row.doc_status || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </AppCard>

      <el-drawer v-model="drawerVisible" title="容器内容" size="560px">
        <div v-if="contentLoading" class="drawer-state">加载中…</div>
        <div v-else-if="contentError" class="drawer-state drawer-state--error">{{ contentError }}</div>
        <template v-else-if="contentData">
          <div class="drawer-head">
            <span class="drawer-hu">{{ contentData.hu?.hu_no }}</span>
            <el-tag size="small">{{ contentData.hu?.status }}</el-tag>
          </div>
          <EmptyState
            v-if="!contentData.contents?.length"
            type="box"
            title="容器为空"
          />
          <table v-else class="hu-table">
            <thead>
              <tr><th>类型</th><th>物料/子容器</th><th>数量</th><th>批次</th><th>序列号</th></tr>
            </thead>
            <tbody>
              <tr v-for="line in contentData.contents" :key="line.id">
                <td>{{ line.content_type }}</td>
                <td>{{ line.child_hu_id ? `#${line.child_hu_id}` : (line.item_id ?? '—') }}</td>
                <td>{{ formatQty(line.qty) }}</td>
                <td>{{ line.batch_id ?? '—' }}</td>
                <td>{{ line.serial_id ?? '—' }}</td>
              </tr>
            </tbody>
          </table>
        </template>
      </el-drawer>
    </div>
  </PageShell>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getHandlingUnitContents,
  queryDocumentHuLinks
} from '@/services/handlingUnitService'

const docType = ref('receipt')
const docNo = ref('')
const huNo = ref('')
const rowsByDoc = ref([])
const huRows = ref([])
const loadingDoc = ref(false)
const loadingHu = ref(false)

const drawerVisible = ref(false)
const contentLoading = ref(false)
const contentError = ref('')
const contentData = ref(null)

const groupedRows = computed(() => {
  const map = new Map()
  for (const row of rowsByDoc.value) {
    const key = row.hu_id
    if (!map.has(key)) {
      map.set(key, {
        hu_id: row.hu_id,
        hu_no: row.hu_no,
        hu_status: row.hu_status,
        doc_no: row.doc_no,
        doc_date: row.doc_date,
        direction: row.direction,
        link_type: row.link_type,
        qty: 0
      })
    }
    const item = map.get(key)
    item.qty += Number(row.qty || 0)
    if (row.direction === 'out') item.direction = 'out'
    if (row.link_type === 'shipped' || row.link_type === 'packed') {
      item.link_type = row.link_type
    }
  }
  return Array.from(map.values())
})

function docTypeLabel(value) {
  return { receipt: '收货单', shipment: '发货单', transfer_order: '调拨单' }[value] || value
}

function linkTypeLabel(value) {
  return { planned: '计划', packed: '已装箱', shipped: '已发运' }[value] || value || '—'
}

function formatQty(value) {
  if (value === null || value === undefined || value === '') return '整行'
  return Number(value)
}

async function searchByDoc() {
  if (!docNo.value.trim()) {
    ElMessage.warning('请输入单据号')
    return
  }
  loadingDoc.value = true
  try {
    const res = await queryDocumentHuLinks({
      doc_type: docType.value,
      doc_no: docNo.value.trim(),
      page_size: 200
    })
    if (!res.success) {
      ElMessage.error(res.message || '查询失败')
      rowsByDoc.value = []
      return
    }
    rowsByDoc.value = res.data?.items || []
  } finally {
    loadingDoc.value = false
  }
}

async function searchByHu() {
  if (!huNo.value.trim()) {
    ElMessage.warning('请输入容器号')
    return
  }
  loadingHu.value = true
  try {
    const res = await queryDocumentHuLinks({
      hu_no: huNo.value.trim(),
      page_size: 200
    })
    if (!res.success) {
      ElMessage.error(res.message || '查询失败')
      huRows.value = []
      return
    }
    huRows.value = res.data?.items || []
  } finally {
    loadingHu.value = false
  }
}

async function openContents(row) {
  drawerVisible.value = true
  contentLoading.value = true
  contentError.value = ''
  contentData.value = null
  try {
    const res = await getHandlingUnitContents(row.hu_id, 'direct')
    if (!res.success) {
      contentError.value = res.message || '加载容器内容失败'
      return
    }
    contentData.value = res.data
  } catch (e) {
    contentError.value = e?.message || '加载容器内容失败'
  } finally {
    contentLoading.value = false
  }
}
</script>

<style scoped>
.hu-docs-page { display: flex; flex-direction: column; gap: 16px; }
.card-gap { margin-top: 4px; }
.filter-row { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
.filter-select { width: 140px; }
.filter-input { width: 280px; }
.hu-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.hu-table th, .hu-table td { padding: 8px 10px; border-bottom: 1px solid var(--border-color, #e5e7eb); text-align: left; }
.hu-table th { color: var(--text-secondary, #6b7280); font-weight: 500; }
.hu-row { cursor: pointer; }
.hu-row:hover { background: var(--bg-hover, #f8fafc); }
.drawer-state { padding: 24px; text-align: center; color: var(--text-secondary, #6b7280); }
.drawer-state--error { color: #dc2626; }
.drawer-head { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
.drawer-hu { font-weight: 600; }
</style>
