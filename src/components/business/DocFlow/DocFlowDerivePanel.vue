<template>
  <AppModal v-model="visible" :title="title" width="1000px">
    <div v-if="result" class="doc-flow-panel__result">
      <p>已生成边 {{ result.total_edges }} 条；新单据 {{ result.created.length }} 条。</p>
      <el-table :data="result.created" size="small" max-height="240">
        <el-table-column label="源行" prop="source_item" width="120" />
        <el-table-column label="下游单据" prop="target_id" width="180" />
        <el-table-column label="下游行" prop="target_item" width="180" />
        <el-table-column label="数量" prop="quantity" width="110" />
      </el-table>
    </div>

    <DocFlowSourcePicker
      v-else
      :rule-id="ruleId"
      :preselected-ids="preselectedIds"
      @change="onPick"
    />

    <template #footer>
      <AppButton variant="secondary" @click="close">{{ result ? '关闭' : '取消' }}</AppButton>
      <AppButton
        v-if="!result"
        variant="primary"
        :loading="submitting"
        :disabled="picked.length === 0"
        @click="submit"
      >
        生成下游
      </AppButton>
    </template>
  </AppModal>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import AppButton from '@/components/common/AppButton/AppButton.vue'
import AppModal from '@/components/common/AppModal/AppModal.vue'
import { deriveDocuments } from '@/services/docFlowService'
import DocFlowSourcePicker from './DocFlowSourcePicker.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  ruleId: { type: String, required: true },
  ruleLabel: { type: String, default: '' },
  preselectedIds: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue', 'done'])

const submitting = ref(false)
const picked = ref([])
const result = ref(null)

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})
const title = computed(() => props.ruleLabel || '生成本次下游数量')

watch(() => props.modelValue, (open) => {
  if (open) {
    result.value = null
    picked.value = []
  }
})

function onPick(rows) {
  picked.value = rows
}

async function submit() {
  if (picked.value.length === 0) return
  submitting.value = true
  try {
    const data = await deriveDocuments({
      rule_id: props.ruleId,
      target: { mode: 'create' },
      sources: picked.value.map((row) => ({
        source_id: row.source_id,
        source_item: row.source_item || '',
        quantity: Number(row.derive_qty || 0),
      })),
    })
    result.value = data
    emit('done', data)
  } finally {
    submitting.value = false
  }
}

function close() {
  visible.value = false
}
</script>

<style scoped>
.doc-flow-panel__result {
  padding: 4px 0 12px;
}
</style>