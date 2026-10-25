<template>
  <el-dialog
    :model-value="visible"
    title="展开订单行"
    width="560px"
    :close-on-click-modal="false"
    class="sales-order-expand-dialog"
    @update:model-value="val => $emit('update:visible', val)"
  >
    <el-alert
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 12px"
    >
      按物料销售用途结构把父行展开为子行。结构、数量与特征由后端求解，失败时返回具体规则。
    </el-alert>

    <el-form label-width="120px">
      <el-form-item label="父行">
        <span>{{ lineLabel }}</span>
      </el-form-item>
      <el-form-item label="定价模式">
        <el-select v-model="form.pricingMode" style="width: 100%">
          <el-option label="整包价（父行含价，子行为 0）" value="bundle_price" />
          <el-option label="子件价（子行含价，父行为 0）" value="component_price" />
          <el-option label="基准价 + 选项价" value="base_plus_option" />
        </el-select>
      </el-form-item>
      <el-form-item label="selections">
        <el-input
          v-model="form.selections"
          type="textarea"
          :rows="2"
          placeholder='可选，JSON 对象：{"结构行 id": true}'
        />
      </el-form-item>
      <el-form-item label="quantities">
        <el-input
          v-model="form.quantities"
          type="textarea"
          :rows="2"
          placeholder='可选，JSON 对象：{"结构行 id": 数量}'
        />
      </el-form-item>
      <el-form-item label="attribute_values">
        <el-input
          v-model="form.attributeValues"
          type="textarea"
          :rows="2"
          placeholder='可选，JSON 对象：{"特征编码": 取值}'
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="$emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">展开</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { apiV1 } from '@/utils/httpClient'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  orderId: {
    type: [String, Number],
    default: null
  },
  line: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['update:visible', 'success'])

const submitting = ref(false)
const form = ref({
  pricingMode: 'bundle_price',
  selections: '',
  quantities: '',
  attributeValues: ''
})

const lineLabel = computed(() => {
  const line = props.line || {}
  const parts = [line.line_no, line.item_name || line.item_code || line.item_id]
    .filter(v => v !== null && v !== undefined && v !== '')
  return parts.length > 0 ? parts.join(' / ') : '-'
})

const EXPAND_PRICING_MODES = ['bundle_price', 'component_price', 'base_plus_option']

watch(() => props.visible, (val) => {
  if (!val) return
  // 行上未展开时为 standalone，不在展开三档内 ⇒ 回落到默认整包价
  const current = props.line?.pricing_mode
  form.value = {
    pricingMode: EXPAND_PRICING_MODES.includes(current) ? current : 'bundle_price',
    selections: '',
    quantities: '',
    attributeValues: ''
  }
})

function _parseJsonObject(text, label) {
  const raw = (text || '').trim()
  if (!raw) return {}
  let value
  try {
    value = JSON.parse(raw)
  } catch (e) {
    throw new Error(`${label} 不是合法 JSON：${e.message}`)
  }
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${label} 必须是 JSON 对象`)
  }
  return value
}

async function handleSubmit() {
  if (submitting.value) return
  if (!props.orderId || !props.line?.id) {
    ElMessage.error('缺少订单或订单行标识')
    return
  }

  let selections
  let quantities
  let attributeValues
  try {
    selections = _parseJsonObject(form.value.selections, 'selections')
    quantities = _parseJsonObject(form.value.quantities, 'quantities')
    attributeValues = _parseJsonObject(form.value.attributeValues, 'attribute_values')
  } catch (e) {
    ElMessage.error(e.message)
    return
  }

  submitting.value = true
  try {
    const res = await apiV1.post(
      `/sales-orders/${props.orderId}/lines/${props.line.id}/expand`,
      {
        pricing_mode: form.value.pricingMode,
        selections,
        quantities,
        attribute_values: attributeValues
      }
    )
    if (res?.success) {
      const count = res.data?.component_count
      ElMessage.success(count !== null && count !== undefined
        ? `已展开 ${count} 个组件行`
        : '展开成功')
      emit('success', res.data)
      emit('update:visible', false)
      return
    }
    ElMessage.error(res?.message || res?.details?.rule || '展开失败')
  } catch (e) {
    ElMessage.error(e?.message || '展开失败')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.sales-order-expand-dialog :deep(.el-form-item) {
  margin-bottom: 14px;
}
</style>
