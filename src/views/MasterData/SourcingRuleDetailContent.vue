<template>
  <PageShell
    title="供应来源规则试算"
    :subtitle="ruleId ? `规则 ID：${ruleId}` : '未指定规则 ID'"
    :show-back-button="false"
  >
    <div class="sourcing-calc">
      <!-- 规则 ID：路由参数优先，缺失时由用户手填；校验规则以该 ID 为准 -->
      <el-card shadow="never">
        <div class="id-bar">
          <span class="id-label">规则 ID</span>
          <el-tag v-if="routeRuleId" type="info" size="large">{{ routeRuleId }}</el-tag>
          <template v-else>
            <el-input
              v-model="manualRuleId"
              class="id-input"
              placeholder="请输入规则 ID（正整数）"
              clearable
            />
            <span class="id-hint">当前地址未携带规则 ID，请手动填写；「校验规则」使用该 ID</span>
          </template>
        </div>
      </el-card>

      <!-- 试算表单 -->
      <el-card shadow="never">
        <template #header>
          <span class="card-title">试算</span>
        </template>

        <el-form :model="calcForm" label-width="120px" class="calc-form" @submit.prevent>
          <el-row :gutter="16">
            <el-col :xs="24" :sm="12" :md="8">
              <el-form-item label="物料 ID" required>
                <el-input v-model="calcForm.item_id" placeholder="item_id（正整数）" clearable />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12" :md="8">
              <el-form-item label="目的组织 ID" required>
                <el-input v-model="calcForm.dest_org_id" placeholder="dest_org_id（正整数）" clearable />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12" :md="8">
              <el-form-item label="用途" required>
                <el-select v-model="calcForm.usage" placeholder="请选择用途">
                  <el-option
                    v-for="option in USAGE_OPTIONS"
                    :key="option.value"
                    :label="option.label"
                    :value="option.value"
                  />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12" :md="8">
              <el-form-item label="生效日期">
                <el-date-picker
                  v-model="calcForm.date"
                  type="date"
                  value-format="YYYY-MM-DD"
                  placeholder="选填，缺省为今天"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12" :md="8">
              <el-form-item label="目的位置 ID">
                <el-input v-model="calcForm.dest_location_id" placeholder="dest_location_id（选填）" clearable />
              </el-form-item>
            </el-col>
          </el-row>

          <div v-if="formError" class="inline-error">{{ formError }}</div>

          <div class="form-actions">
            <el-button type="primary" :loading="calcLoading" @click="handleResolve">试算</el-button>
            <el-button :loading="validateLoading" @click="handleValidate">校验规则</el-button>
          </div>
        </el-form>
      </el-card>

      <!-- 试算成功 -->
      <el-card v-if="calcResult" shadow="never">
        <template #header>
          <div class="card-header">
            <span class="card-title">试算结果</span>
            <el-tag type="success" size="small">已命中来源</el-tag>
          </div>
        </template>

        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="rule_code">{{ fmt(calcResult.rule_code) }}</el-descriptions-item>
          <el-descriptions-item label="assignment_id">{{ fmt(calcResult.assignment_id) }}</el-descriptions-item>
          <el-descriptions-item label="source_type">{{ fmt(calcResult.source_type) }}</el-descriptions-item>
          <el-descriptions-item label="source_org_id">{{ fmt(calcResult.source_org_id) }}</el-descriptions-item>
          <el-descriptions-item label="source_location_id">{{ fmt(calcResult.source_location_id) }}</el-descriptions-item>
          <el-descriptions-item label="supplier_party_id">{{ fmt(calcResult.supplier_party_id) }}</el-descriptions-item>
          <el-descriptions-item label="supply_mode">{{ fmt(calcResult.supply_mode) }}</el-descriptions-item>
          <el-descriptions-item label="specificity_rank">{{ fmt(calcResult.specificity_rank) }}</el-descriptions-item>
          <el-descriptions-item label="line_id">{{ fmt(calcResult.line_id) }}</el-descriptions-item>
          <el-descriptions-item label="evaluated_at" :span="3">{{ fmt(calcResult.evaluated_at) }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 试算失败：展示契约错误码、message 与 hint，不弹窗 -->
      <el-card v-if="calcError" shadow="never" class="error-card">
        <template #header>
          <span class="card-title">试算失败</span>
        </template>
        <div class="error-line">
          <el-tag type="danger">{{ calcError.code }}</el-tag>
          <span class="error-message">{{ calcError.message }}</span>
        </div>
        <div v-if="calcError.hint" class="error-hint">提示：{{ calcError.hint }}</div>
        <div v-if="calcError.supplyMode" class="error-hint">供应方式：{{ calcError.supplyMode }}</div>
      </el-card>

      <!-- explain 快照：成功与失败共用，默认展开每一步，保证三步可见 -->
      <el-card v-if="explainSteps.length" shadow="never">
        <template #header>
          <div class="card-header">
            <span class="card-title">explain 快照</span>
            <div class="explain-steps">
              <el-tag v-for="(step, index) in explainSteps" :key="index" size="small" effect="plain">
                {{ step?.step || 'step' }}
              </el-tag>
            </div>
          </div>
        </template>

        <el-collapse v-model="openExplainPanels">
          <el-collapse-item
            v-for="(step, index) in explainSteps"
            :key="index"
            :name="String(index)"
            :title="`${index + 1}. ${step?.step || 'step'}`"
          >
            <pre class="json-block">{{ toJson(step) }}</pre>
          </el-collapse-item>
        </el-collapse>
      </el-card>

      <!-- 规则校验结果 -->
      <el-card v-if="validateResult" shadow="never">
        <template #header>
          <div class="card-header">
            <span class="card-title">规则校验</span>
            <el-tag :type="validateResult.ok ? 'success' : 'danger'" size="small">
              {{ validateResult.ok ? '校验通过' : '校验未通过' }}
            </el-tag>
          </div>
        </template>

        <div
          class="validate-banner"
          :class="validateResult.ok ? 'validate-banner--ok' : 'validate-banner--bad'"
        >
          <strong>{{ validateResult.ok ? '规则配置完整，可用于求值' : '规则配置存在矛盾，求值可能失败' }}</strong>
          <span>
            规则 ID：{{ fmt(validateResult.rule_id) }} ·
            来源行：{{ fmt(validateResult.line_count) }} ·
            作用域分配：{{ fmt(validateResult.assignment_count) }}
          </span>
        </div>

        <div class="section-title">分摊合计（ranks）</div>
        <el-table :data="validateResult.ranks || []" size="small" border empty-text="暂无 rank 数据">
          <el-table-column prop="rank" label="rank" width="120" />
          <el-table-column prop="total" label="合计(%)" width="140" />
          <el-table-column label="ok" width="120">
            <template #default="{ row }">
              <el-tag :type="row.ok ? 'success' : 'danger'" size="small">
                {{ row.ok ? '是' : '否' }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>

        <div class="section-title">
          作用域冲突（conflicts：{{ (validateResult.conflicts || []).length }}）
        </div>
        <el-table :data="validateResult.conflicts || []" size="small" border empty-text="无冲突">
          <el-table-column prop="scope_type" label="scope_type" min-width="140" />
          <el-table-column prop="scope_ref_id" label="scope_ref_id" min-width="120" />
          <el-table-column prop="dest_org_id" label="dest_org_id" min-width="120" />
          <el-table-column prop="dest_location_id" label="dest_location_id" min-width="150" />
        </el-table>

        <div class="section-title">
          错误（errors：{{ (validateResult.errors || []).length }}）
        </div>
        <el-table :data="validateResult.errors || []" size="small" border empty-text="无错误">
          <el-table-column prop="code" label="code" min-width="220" />
          <el-table-column prop="message" label="message" min-width="280" />
          <el-table-column prop="hint" label="hint" min-width="280" />
        </el-table>
      </el-card>

      <!-- 规则校验失败（如规则不存在） -->
      <el-card v-if="validateError" shadow="never" class="error-card">
        <template #header>
          <span class="card-title">规则校验失败</span>
        </template>
        <div class="error-line">
          <el-tag type="danger">{{ validateError.code }}</el-tag>
          <span class="error-message">{{ validateError.message }}</span>
        </div>
        <div v-if="validateError.hint" class="error-hint">提示：{{ validateError.hint }}</div>
      </el-card>
    </div>
  </PageShell>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { PageShell } from '@/components/common/PageShell'
import { resolveSourcing, validateSourcingRule } from '@/services/sourcingService'
import { logger } from '@/utils/logger'

defineOptions({ name: 'SourcingRuleDetailContent' })

const USAGE_OPTIONS = [
  { value: 'fulfillment', label: '履约（fulfillment）' },
  { value: 'purchasing', label: '采购（purchasing）' }
]

const route = useRoute()

const routeRuleId = computed(() => String(route.params.id ?? '').trim())
const manualRuleId = ref('')
const ruleId = computed(() => routeRuleId.value || manualRuleId.value.trim())

const calcForm = ref({
  item_id: '',
  dest_org_id: '',
  usage: 'fulfillment',
  date: '',
  dest_location_id: ''
})
const calcLoading = ref(false)
const formError = ref('')
const calcResult = ref(null)
const calcError = ref(null)
const openExplainPanels = ref([])

const validateLoading = ref(false)
const validateResult = ref(null)
const validateError = ref(null)

const explainSteps = computed(() => {
  const list = calcResult.value?.explain || calcError.value?.explain || []
  return Array.isArray(list) ? list : []
})

function fmt(value) {
  return value === null || value === undefined || value === '' ? '—' : value
}

function toJson(value) {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function positiveInt(raw) {
  const text = String(raw ?? '').trim()
  if (!/^\d+$/.test(text)) return null
  const num = Number(text)
  return Number.isSafeInteger(num) && num > 0 ? num : null
}

function expandExplain(steps) {
  openExplainPanels.value = (Array.isArray(steps) ? steps : []).map((_, index) => String(index))
}

async function handleResolve() {
  formError.value = ''
  calcResult.value = null
  calcError.value = null
  openExplainPanels.value = []

  const itemId = positiveInt(calcForm.value.item_id)
  const destOrgId = positiveInt(calcForm.value.dest_org_id)
  if (itemId === null) {
    formError.value = '物料 ID 必须是正整数'
    return
  }
  if (destOrgId === null) {
    formError.value = '目的组织 ID 必须是正整数'
    return
  }
  if (!calcForm.value.usage) {
    formError.value = '请选择用途'
    return
  }

  const params = { item_id: itemId, dest_org_id: destOrgId, usage: calcForm.value.usage }
  if (calcForm.value.date) params.date = calcForm.value.date
  const destLocationId = positiveInt(calcForm.value.dest_location_id)
  if (destLocationId !== null) params.dest_location_id = destLocationId

  calcLoading.value = true
  try {
    const res = await resolveSourcing(params)
    if (res?.success && res.data) {
      calcResult.value = res.data
      expandExplain(res.data.explain)
    } else {
      calcError.value = {
        code: res?.businessCode || res?.code || 'UNKNOWN_ERROR',
        message: res?.message || '试算失败',
        hint: res?.details?.hint || '',
        supplyMode: res?.details?.supply_mode || '',
        explain: Array.isArray(res?.details?.explain) ? res.details.explain : []
      }
      expandExplain(calcError.value.explain)
    }
  } catch (e) {
    logger.error('[SourcingCalc] resolve failed:', e)
    calcError.value = {
      code: 'CLIENT_ERROR',
      message: e?.message || String(e),
      hint: '',
      supplyMode: '',
      explain: []
    }
  } finally {
    calcLoading.value = false
  }
}

async function handleValidate() {
  validateResult.value = null
  validateError.value = null

  const id = positiveInt(ruleId.value)
  if (id === null) {
    validateError.value = {
      code: 'CLIENT_INVALID_RULE_ID',
      message: '请先填写正整数规则 ID',
      hint: ''
    }
    return
  }

  validateLoading.value = true
  try {
    const res = await validateSourcingRule(id)
    if (res?.success && res.data) {
      validateResult.value = res.data
    } else {
      validateError.value = {
        code: res?.businessCode || res?.code || 'UNKNOWN_ERROR',
        message: res?.message || '校验失败',
        hint: res?.details?.hint || ''
      }
    }
  } catch (e) {
    logger.error('[SourcingCalc] validate failed:', e)
    validateError.value = {
      code: 'CLIENT_ERROR',
      message: e?.message || String(e),
      hint: ''
    }
  } finally {
    validateLoading.value = false
  }
}

// 路由参数变化（SPA 内切换规则）时清空上一次结果，避免误读
watch(routeRuleId, () => {
  calcResult.value = null
  calcError.value = null
  validateResult.value = null
  validateError.value = null
  openExplainPanels.value = []
})
</script>

<style scoped>
.sourcing-calc {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.id-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--spacing-sm);
}

.id-label {
  font-weight: 600;
  color: var(--color-text-primary);
}

.id-input {
  width: 240px;
}

.id-hint {
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.card-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
}

.card-title {
  font-weight: 600;
  color: var(--color-text-primary);
}

.calc-form {
  padding-top: 4px;
}

.form-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.inline-error {
  margin-bottom: 12px;
  padding: 8px 12px;
  border: 1px solid #f56c6c;
  border-radius: var(--radius-sm);
  background: #fef0f0;
  color: #f56c6c;
  font-size: 13px;
}

.error-card {
  border-color: #fde2e2;
}

.error-line {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
}

.error-message {
  color: #f56c6c;
  font-weight: 500;
}

.error-hint {
  margin-top: 8px;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.explain-steps {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.json-block {
  margin: 0;
  padding: 12px;
  max-height: 360px;
  overflow: auto;
  border-radius: var(--radius-sm);
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
  font-family: monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}

.validate-banner {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: var(--spacing-md);
  padding: 10px 14px;
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  font-size: 13px;
}

.validate-banner--ok {
  border-color: #b3e19d;
  background: #f0f9eb;
  color: #529b2e;
}

.validate-banner--bad {
  border-color: #f56c6c;
  background: #fef0f0;
  color: #c45656;
  font-weight: 600;
}

.section-title {
  margin: var(--spacing-md) 0 var(--spacing-sm);
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-secondary);
}
</style>
