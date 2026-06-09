<template>
  <div class="state-transition-button">
    <template v-if="availableTransitions.length === 1">
      <el-button
        :type="buttonType"
        :size="size"
        :disabled="disabled || loading"
        :loading="loading"
        @click="handleTransition(availableTransitions[0])"
      >
        {{ availableTransitions[0].label || availableTransitions[0].name }}
      </el-button>
    </template>
    
    <template v-else-if="availableTransitions.length > 1">
      <el-dropdown
        trigger="click"
        :disabled="disabled || loading"
        @command="handleTransition"
      >
        <el-button
          :type="buttonType"
          :size="size"
          :disabled="disabled || loading"
          :loading="loading"
        >
          {{ buttonText }}
          <el-icon class="el-icon--right">
            <ArrowDown />
          </el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item
              v-for="transition in availableTransitions"
              :key="transition.id || transition.name"
              :command="transition"
              :disabled="transition.disabled"
            >
              <el-icon v-if="transition.icon">
                <component :is="transition.icon" />
              </el-icon>
              {{ transition.label || transition.name }}
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
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
import { ref, computed } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import { useCrudMessage } from '@/composables/useCrudMessage'
import boService from '@/services/boService'

const props = defineProps({
  objectType: {
    type: String,
    required: true
  },
  objectId: {
    type: [Number, String],
    required: true
  },
  currentState: {
    type: String,
    default: ''
  },
  stateField: {
    type: String,
    default: 'status'
  },
  rules: {
    type: Array,
    default: () => []
  },
  buttonType: {
    type: String,
    default: 'primary'
  },
  size: {
    type: String,
    default: 'default'
  },
  disabled: {
    type: Boolean,
    default: false
  },
  buttonText: {
    type: String,
    default: '状态操作'
  }
})

const emit = defineEmits(['transition', 'success', 'error'])

const message = useCrudMessage()
const loading = ref(false)
const confirmDialogVisible = ref(false)
const pendingTransition = ref(null)

const availableTransitions = computed(() => {
  if (!props.rules || props.rules.length === 0) return []
  
  return props.rules
    .filter(rule => {
      if (rule.type !== 'state_transition') return false
      
      if (rule.from_states && rule.from_states.length > 0) {
        return rule.from_states.includes(props.currentState)
      }
      
      return true
    })
    .map(rule => ({
      id: rule.id,
      name: rule.name || rule.id,
      label: rule.label || rule.name || rule.id,
      toState: rule.to_state,
      icon: rule.icon,
      disabled: rule.disabled || false,
      requireConfirm: rule.require_confirm !== false,
      confirmMessage: rule.confirm_message || `确定要执行此操作吗？`,
      action: rule.action
    }))
})

const confirmTitle = computed(() => {
  return pendingTransition.value?.label || '确认操作'
})

const confirmMessage = computed(() => {
  return pendingTransition.value?.confirmMessage || '确定要执行此操作吗？'
})

const handleTransition = (transition) => {
  if (transition.disabled) return
  
  if (transition.requireConfirm) {
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
  confirmDialogVisible.value = false
  
  try {
    let result
    
    if (transition.action) {
      result = await boService.executeAction(
        props.objectType,
        props.objectId,
        transition.action,
        { [props.stateField]: transition.toState }
      )
    } else {
      result = await boService.update(props.objectType, props.objectId, {
        [props.stateField]: transition.toState
      })
    }
    
    if (result.success) {
      // [FIX 2026-06-09] 用 useCrudMessage 替代 ElMessage
      // 避免 high-z modal (z-index > 2200) 遮挡 Element Plus 的 fixed 定位 toast
      message.stateChanged(transition.label, '数据')
      emit('success', { transition, result })
      emit('transition', { transition, result })
    } else {
      message.error(`${transition.label} 失败`, result)
      emit('error', { transition, error: result.message })
    }
  } catch (error) {
    console.error('State transition error:', error)
    message.error(`${transition.label} 失败`, error)
    emit('error', { transition, error: error.message })
  } finally {
    loading.value = false
    pendingTransition.value = null
  }
}

defineExpose({
  availableTransitions,
  executeTransition
})
</script>

<style scoped>
.state-transition-button {
  display: inline-block;
}

.el-dropdown-menu__item {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
