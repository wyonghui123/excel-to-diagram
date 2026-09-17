<template>
  <div v-if="availableTransitions.length > 0" class="state-transition-buttons">
    <template v-for="transition in availableTransitions" :key="transition.id">
      <AppButton
        :variant="transition.highlight ? 'primary' : 'secondary'"
        size="sm"
        :disabled="disabled || loading"
        :loading="loading && executingId === transition.id"
        @click="handleTransition(transition)"
      >
        {{ transition.label }}
      </AppButton>
    </template>

    <el-dialog
      v-model="confirmDialogVisible"
      :title="confirmTitle"
      width="400px"
      :close-on-click-modal="false"
      append-to-body
    >
      <p>{{ confirmMessage }}</p>
      <template #footer>
        <el-button @click="confirmDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="loading" @click="confirmTransition">
          确定
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useCrudMessage } from '@/composables/useCrudMessage'
import { apiV2 } from '@/utils/httpClient'
import AppButton from '@/components/common/AppButton/AppButton.vue'

const props = defineProps({
  objectType: {
    type: String,
    required: true
  },
  objectId: {
    type: [Number, String],
    required: true
  },
  stateField: {
    type: String,
    default: 'status'
  },
  size: {
    type: String,
    default: 'small'
  },
  disabled: {
    type: Boolean,
    default: false
  },
  autoLoad: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['success', 'error', 'refresh'])

const message = useCrudMessage()
const loading = ref(false)
const executingId = ref(null)
const confirmDialogVisible = ref(false)
const pendingTransition = ref(null)
const transitions = ref([])

const availableTransitions = computed(() => {
  return transitions.value.filter(t => t.available && !t.hidden)
})

const confirmTitle = computed(() => {
  return pendingTransition.value?.label || '确认操作'
})

const confirmMessage = computed(() => {
  return pendingTransition.value?.confirmMessage || '确定要执行此操作吗？'
})

const loadTransitions = async () => {
  if (!props.objectType || !props.objectId || props.objectId === 'new') return
  
  loading.value = true
  try {
    const data = await apiV2.get(`/bo/${props.objectType}/${props.objectId}/state_transitions`)
    if (data.success) {
      transitions.value = data.data || []
    }
  } catch (error) {
    console.error('Failed to load state transitions:', error)
  } finally {
    loading.value = false
  }
}

const handleTransition = (transition) => {
  if (transition.confirmMessage) {
    pendingTransition.value = transition
    confirmDialogVisible.value = true
  } else {
    executeTransition(transition)
  }
}

const confirmTransition = () => {
  if (pendingTransition.value) {
    executeTransition(pendingTransition.value)
  }
}

const executeTransition = async (transition) => {
  loading.value = true
  executingId.value = transition.id
  confirmDialogVisible.value = false
  
  console.debug('[StateTransitionButtons] executeTransition:', transition)
  
  try {
    const data = await apiV2.put(
      `/bo/${props.objectType}/${props.objectId}`,
      { [transition.stateField]: transition.toState }
    )

    if (data.success) {
      // [FIX 2026-06-09] 用 useCrudMessage 替代 ElMessage
      message.stateChanged(transition.label, '数据')
      console.debug('[StateTransitionButtons] emit success and refresh, newStatus:', transition.toState, 'stateField:', transition.stateField)
      const refreshPayload = { newStatus: transition.toState, stateField: transition.stateField }
      console.debug('[StateTransitionButtons] emitting refresh with payload:', refreshPayload)
      emit('success', { transition, result: data, ...refreshPayload })
      emit('refresh', refreshPayload)
      await loadTransitions()
    } else {
      // [Spec 22 2026-09-13] 失败走 stateChangeFailed，自动识别 403 权限拒绝场景
      // ActionPermissionInterceptor 拒绝时，后端 message 含「缺少权限 activate（state_transition: xxx）」
      message.stateChangeFailed(transition.label, data, transition.actionRef || '')
      emit('error', { transition, error: data.message, httpStatus: data.httpStatus })
    }
  } catch (error) {
    // 真正的网络异常（apiV2 不会到这里，network error 走 apiV2 包装）
    console.error('State transition unexpected error:', error)
    message.stateChangeFailed(transition.label, error, transition.actionRef || '')
    emit('error', { transition, error: error.message })
  } finally {
    loading.value = false
    executingId.value = null
    pendingTransition.value = null
  }
}

onMounted(() => {
  if (props.autoLoad) {
    loadTransitions()
  }
})

watch(() => props.objectId, () => {
  if (props.autoLoad) {
    loadTransitions()
  }
})

defineExpose({
  loadTransitions,
  availableTransitions,
  executeTransition
})
</script>

<style scoped>
.state-transition-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin: 0;
  padding: 0;
}
</style>
