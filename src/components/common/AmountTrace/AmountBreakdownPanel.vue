<template>
  <div class="amount-breakdown" v-loading="loading">
    <div class="ab-toolbar">
      <el-button size="small" :loading="loading" @click="load">
        刷新回溯
      </el-button>
      <el-button
        type="primary"
        size="small"
        :loading="recalculating"
        :disabled="!canRecalc"
        :title="recalcDisabledReason"
        @click="recalc"
      >
        重新计算金额
      </el-button>
      <el-tag v-if="trace?.meta?.kernel" size="small" type="info" effect="plain">
        内核：{{ trace.meta.kernel }}
      </el-tag>
      <el-tag v-if="trace?.meta?.readonly" size="small" type="info" effect="plain">
        只读回溯
      </el-tag>
      <span v-if="trace?.meta?.generated_at" class="ab-generated">
        {{ trace.meta.generated_at }}
      </span>
    </div>

    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="error"
      :closable="false"
      show-icon
    />
    <el-alert
      v-else-if="trace && !canRecalc && recalcDisabledReason"
      :title="recalcDisabledReason"
      type="info"
      :closable="false"
      show-icon
    />

    <template v-if="trace">
      <!-- 抬头 -->
      <div class="ab-card">
        <div class="ab-card__head">
          <strong>抬头金额</strong>
          <span class="ab-card__sub">{{ trace.header.document_no || ('#' + trace.record_id) }}</span>
          <el-tag size="small" type="info" effect="plain">{{ trace.header.status || '-' }}</el-tag>
          <span v-if="trace.header.currency?.code" class="ab-card__sub">
            {{ trace.header.currency.code }}（{{ trace.header.decimal_places }} 位）
          </span>
        </div>
        <el-table :data="headerRows" size="small" border class="ab-amount-table">
          <el-table-column prop="label" label="金额项" width="120" />
          <el-table-column prop="stored" label="存储值" align="right" min-width="110" />
          <el-table-column prop="recomputed" label="重算值" align="right" min-width="110" />
          <el-table-column label="漂移" align="right" min-width="110">
            <template #default="{ row }">
              <el-tag v-if="row.drift !== null && row.drift !== undefined"
                      size="small" :type="isDrift(row.drift) ? 'danger' : 'success'" effect="plain">
                {{ formatAmount(row.drift, trace.header.decimal_places) }}
              </el-tag>
              <span v-else class="ab-muted">-</span>
            </template>
          </el-table-column>
        </el-table>
        <div class="ab-formula">{{ trace.header.formula }}</div>
        <div v-if="trace.header.recompute_error" class="ab-error">
          重算失败：{{ trace.header.recompute_error }}
        </div>
      </div>

      <!-- 行明细 -->
      <div class="ab-card">
        <div class="ab-card__head">
          <strong>行金额回溯</strong>
          <span class="ab-card__sub">共 {{ trace.lines.length }} 行</span>
        </div>
        <el-table :data="trace.lines" size="small" border class="ab-line-table">
          <el-table-column type="expand">
            <template #default="{ row }">
              <div class="ab-line-expand">
                <div class="ab-formula">{{ row.formula }}</div>

                <el-descriptions :column="3" size="small" border class="ab-desc">
                  <el-descriptions-item label="取价来源">
                    {{ row.price_source || '未记录' }}
                  </el-descriptions-item>
                  <el-descriptions-item label="税码">
                    {{ row.tax_code || '-' }}
                    <span v-if="row.tax_rate_percent !== null && row.tax_rate_percent !== undefined">
                      （{{ row.tax_rate_percent }}%）
                    </span>
                  </el-descriptions-item>
                  <el-descriptions-item label="税额取整">
                    {{ row.rounding_label }}
                  </el-descriptions-item>
                  <el-descriptions-item label="行净调整额">
                    {{ formatAmount(row.net_adjustment, row.decimal_places) }}
                  </el-descriptions-item>
                  <el-descriptions-item label="含税单价">
                    {{ row.price_includes_tax ? '是（gross→net 倒算）' : '否（net→gross 正算）' }}
                  </el-descriptions-item>
                  <el-descriptions-item label="币种">
                    {{ row.currency || '-' }}
                  </el-descriptions-item>
                </el-descriptions>

                <div v-if="row.calc" class="ab-calc">
                  <div class="ab-calc__head">
                    <strong>定价过程</strong>
                    <el-tag size="small" type="info" effect="plain">
                      {{ row.calc.process_code || row.calc.code || '-' }}
                    </el-tag>
                    <span class="ab-muted">
                      {{ row.calc.document_type }} / {{ row.calc.result_semantic || '-' }}
                    </span>
                  </div>
                  <el-table v-if="row.calc.steps?.length" :data="row.calc.steps" size="small" border>
                    <el-table-column prop="seq" label="#" width="50" />
                    <el-table-column prop="label" label="定价元素" min-width="140" />
                    <el-table-column prop="price_element_code" label="元素码" width="120" />
                    <el-table-column prop="base_value" label="基数" align="right" width="100" />
                    <el-table-column prop="unit_price" label="单价" align="right" width="100" />
                    <el-table-column prop="extended_amount" label="本步金额" align="right" width="110" />
                    <el-table-column prop="running_net_amount" label="累计净额" align="right" width="110" />
                    <el-table-column label="跳过" width="80" align="center">
                      <template #default="{ row: step }">
                        <el-tag v-if="step.skipped" size="small" type="info" effect="plain">跳过</el-tag>
                        <span v-else class="ab-muted">-</span>
                      </template>
                    </el-table-column>
                  </el-table>
                  <div v-else class="ab-muted">无定价步骤快照（未走定价过程或历史数据未记录）。</div>
                </div>

                <div v-if="row.price_trace" class="ab-trace">
                  <div class="ab-calc__head"><strong>取价轨迹（price_trace）</strong></div>
                  <pre class="ab-pre">{{ pretty(row.price_trace) }}</pre>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="line_no" label="#" width="55" />
          <el-table-column prop="label" label="物料 / 服务" min-width="150" show-overflow-tooltip />
          <el-table-column prop="qty" label="数量" align="right" width="90" />
          <el-table-column prop="unit_price" label="单价" align="right" width="100" />
          <el-table-column label="净额" align="right" width="110">
            <template #default="{ row }">{{ formatAmount(row.stored.net_amount, row.decimal_places) }}</template>
          </el-table-column>
          <el-table-column label="税额" align="right" width="110">
            <template #default="{ row }">{{ formatAmount(row.stored.tax_amount, row.decimal_places) }}</template>
          </el-table-column>
          <el-table-column label="价税合计" align="right" width="120">
            <template #default="{ row }">{{ formatAmount(row.stored.gross_amount, row.decimal_places) }}</template>
          </el-table-column>
          <el-table-column label="净额漂移" align="right" width="110">
            <template #default="{ row }">
              <el-tag v-if="row.drift" size="small"
                      :type="isDrift(row.drift.net_amount) ? 'danger' : 'success'" effect="plain">
                {{ formatAmount(row.drift.net_amount, row.decimal_places) }}
              </el-tag>
              <span v-else class="ab-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column label="取价来源" min-width="120" show-overflow-tooltip>
            <template #default="{ row }">
              <span>{{ row.price_source || '-' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 调整 -->
      <div class="ab-card">
        <div class="ab-card__head">
          <strong>金额调整</strong>
          <el-tag size="small" :type="adjustmentModeType" effect="plain">
            {{ adjustmentModeLabel }}
          </el-tag>
        </div>
        <div class="ab-note">{{ trace.adjustments.note }}</div>

        <el-table v-if="trace.adjustments.mode === 'adjustment_document'"
                  :data="trace.adjustments.documents || []" size="small" border>
          <el-table-column prop="invoice_no" label="调整单号" min-width="140" />
          <el-table-column prop="status" label="状态" width="100" />
          <el-table-column prop="invoice_date" label="日期" width="110" />
          <el-table-column label="金额" align="right" width="120">
            <template #default="{ row }">
              {{ formatAmount(row.gross_amount, trace.header.decimal_places) }}
            </template>
          </el-table-column>
          <el-table-column label="关系" width="120">
            <template #default="{ row }">{{ row.relation || '调整单' }}</template>
          </el-table-column>
        </el-table>

        <template v-else-if="trace.adjustments.mode === 'header_allocation'">
          <el-descriptions :column="2" size="small" border>
            <el-descriptions-item label="抬头折扣额">
              {{ formatAmount(trace.adjustments.header_discount_amount, trace.header.decimal_places) }}
            </el-descriptions-item>
            <el-descriptions-item label="抬头附加费">
              {{ formatAmount(trace.adjustments.header_surcharge_amount, trace.header.decimal_places) }}
            </el-descriptions-item>
          </el-descriptions>
          <el-table :data="trace.adjustments.lines || []" size="small" border class="ab-adj-table">
            <el-table-column prop="line_no" label="#" width="60" />
            <el-table-column prop="label" label="行 / 抬头" min-width="160" />
            <el-table-column label="分摊额" align="right" width="140">
              <template #default="{ row }">
                {{ formatAmount(row.amount, trace.header.decimal_places) }}
              </template>
            </el-table-column>
          </el-table>
        </template>
      </div>
    </template>

    <el-empty v-else-if="!loading && !errorMessage" description="暂无金额回溯数据" :image-size="60" />
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useMessage } from '@/composables/useMessage'
import { getAmountTrace, recalcAmount } from '@/services/amountTraceService'

const props = defineProps({
  objectType: { type: String, required: true },
  recordId: { type: [String, Number], required: true },
  autoLoad: { type: Boolean, default: true }
})

const emit = defineEmits(['loaded', 'recalculated'])

const message = useMessage()
const loading = ref(false)
const recalculating = ref(false)
const errorMessage = ref('')
const trace = ref(null)

const AMOUNT_LABELS = {
  net_amount: '净额',
  tax_amount: '税额',
  gross_amount: '价税合计',
  rounding_diff: '尾差',
  header_discount_amount: '抬头折扣',
  header_surcharge_amount: '抬头附加费',
  supplier_gross_amount: '供应商含税额',
  non_recoverable_tax_amount: '不可抵扣税额',
  price_diff_amount: '价格差异额'
}

const headerRows = computed(() => {
  const header = trace.value?.header
  if (!header) return []
  const stored = header.stored || {}
  const recomputed = header.recomputed || {}
  const drift = header.drift || {}
  return Object.keys(AMOUNT_LABELS)
    .filter((key) => stored[key] !== undefined && stored[key] !== null
      || recomputed[key] !== undefined && recomputed[key] !== null)
    .map((key) => {
      const d = drift[key]
      return {
        key,
        label: AMOUNT_LABELS[key],
        stored: stored[key] === null || stored[key] === undefined
          ? '-' : formatAmount(stored[key], header.decimal_places),
        recomputed: recomputed[key] === null || recomputed[key] === undefined
          ? '-' : formatAmount(recomputed[key], header.decimal_places),
        drift: d === null || d === undefined ? null : d
      }
    })
})

const canRecalc = computed(() => Boolean(trace.value?.recalc?.allowed))
const recalcDisabledReason = computed(() => trace.value?.recalc?.reason || '')

const ADJUSTMENT_LABELS = {
  none: '无调整',
  header_allocation: '抬头折扣 / 附加费分摊',
  adjustment_document: '独立调整单'
}
const adjustmentModeLabel = computed(
  () => ADJUSTMENT_LABELS[trace.value?.adjustments?.mode] || trace.value?.adjustments?.mode || '-'
)
const adjustmentModeType = computed(() => {
  const mode = trace.value?.adjustments?.mode
  if (mode === 'adjustment_document') return 'warning'
  if (mode === 'header_allocation') return 'success'
  return 'info'
})

function formatAmount(value, decimals = 2) {
  if (value === null || value === undefined || value === '') return '-'
  const num = Number(value)
  if (Number.isNaN(num)) return '-'
  return num.toFixed(Number.isInteger(decimals) ? decimals : 2)
}

function isDrift(value) {
  return Math.abs(Number(value) || 0) > 0.0001
}

function pretty(value) {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

async function load() {
  if (!props.objectType || !props.recordId) return
  loading.value = true
  errorMessage.value = ''
  try {
    const resp = await getAmountTrace(props.objectType, props.recordId)
    if (resp?.success) {
      trace.value = resp.data
      emit('loaded', resp.data)
    } else {
      trace.value = null
      errorMessage.value = resp?.message || '加载金额回溯失败'
    }
  } catch (err) {
    trace.value = null
    errorMessage.value = err?.message || '加载金额回溯失败'
  } finally {
    loading.value = false
  }
}

async function recalc() {
  if (!canRecalc.value || recalculating.value) return
  recalculating.value = true
  try {
    const resp = await recalcAmount(props.objectType, props.recordId)
    if (resp?.success) {
      message.success(resp.message || '金额重算完成')
      emit('recalculated', resp.data)
      await load()
    } else {
      message.error(resp?.message || '金额重算失败')
    }
  } catch (err) {
    message.error(err?.message || '金额重算失败')
  } finally {
    recalculating.value = false
  }
}

watch(
  () => [props.objectType, props.recordId],
  () => {
    trace.value = null
    if (props.autoLoad) load()
  },
  { immediate: props.autoLoad }
)

defineExpose({ load, recalc })
</script>

<style scoped>
.amount-breakdown { display: flex; flex-direction: column; gap: 12px; }
.ab-toolbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ab-generated { margin-left: auto; color: var(--el-text-color-secondary); font-size: 12px; }
.ab-card { border: 1px solid var(--el-border-color-lighter); border-radius: 6px; padding: 10px 12px; }
.ab-card__head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.ab-card__sub { color: var(--el-text-color-secondary); font-size: 12px; }
.ab-formula { margin-top: 6px; font-size: 12px; color: var(--el-text-color-secondary); }
.ab-error { margin-top: 6px; font-size: 12px; color: var(--el-color-danger); }
.ab-note { margin-bottom: 8px; font-size: 12px; color: var(--el-text-color-secondary); }
.ab-muted { color: var(--el-text-color-placeholder); font-size: 12px; }
.ab-line-expand { padding: 8px 12px; display: flex; flex-direction: column; gap: 10px; }
.ab-calc__head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.ab-pre { margin: 0; max-height: 240px; overflow: auto; font-size: 12px; background: var(--el-fill-color-light); padding: 8px; border-radius: 4px; }
.ab-adj-table { margin-top: 8px; }
</style>