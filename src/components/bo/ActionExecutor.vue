<template>
  <div class="action-executor">
    <template v-if="actions.length === 1">
      <el-button
        :type="getButtonType(actions[0])"
        :size="size"
        :disabled="disabled || loading"
        :loading="loading"
        @click="handleAction(actions[0])"
      >
        <el-icon v-if="actions[0].icon">
          <component :is="actions[0].icon" />
        </el-icon>
        {{ actions[0].label || actions[0].name }}
      </el-button>
    </template>
    
    <template v-else-if="actions.length > 1">
      <el-dropdown
        trigger="click"
        :disabled="disabled || loading"
        @command="handleAction"
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
            <template v-for="group in groupedActions" :key="group.category">
              <template v-if="group.category">
                <el-dropdown-item
                  v-for="action in group.actions"
                  :key="action.id || action.name"
                  :command="action"
                  :disabled="isActionDisabled(action)"
                  :divided="action.divided"
                >
                  <el-icon v-if="action.icon">
                    <component :is="action.icon" />
                  </el-icon>
                  {{ action.label || action.name }}
                </el-dropdown-item>
              </template>
              <template v-else>
                <el-dropdown-item
                  v-for="action in group.actions"
                  :key="action.id || action.name"
                  :command="action"
                  :disabled="isActionDisabled(action)"
                  :divided="action.divided"
                >
                  <el-icon v-if="action.icon">
                    <component :is="action.icon" />
                  </el-icon>
                  {{ action.label || action.name }}
                </el-dropdown-item>
              </template>
            </template>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </template>

    <el-dialog
      v-model="paramDialogVisible"
      :title="currentAction?.label || '执行操作'"
      width="500px"
      :close-on-click-modal="false"
      append-to-body
    >
      <el-form
        v-if="currentAction?.params"
        ref="paramFormRef"
        :model="paramForm"
        :rules="paramRules"
        label-width="100px"
      >
        <el-form-item
          v-for="param in currentAction.params"
          :key="param.name"
          :label="param.label || param.name"
          :prop="param.name"
          :required="param.required"
        >
          <el-input
            v-if="param.type === 'text' || param.type === 'string'"
            v-model="paramForm[param.name]"
            :placeholder="param.placeholder"
          />
          <el-input
            v-else-if="param.type === 'textarea'"
            v-model="paramForm[param.name]"
            type="textarea"
            :rows="param.rows || 3"
            :placeholder="param.placeholder"
          />
          <el-input-number
            v-else-if="param.type === 'number' || param.type === 'integer'"
            v-model="paramForm[param.name]"
            :min="param.min"
            :max="param.max"
            :step="param.step"
          />
          <el-select
            v-else-if="param.type === 'select' || param.type === 'enum'"
            v-model="paramForm[param.name]"
            :placeholder="param.placeholder || '请选择'"
          >
            <el-option
              v-for="option in param.options"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <el-switch
            v-else-if="param.type === 'boolean'"
            v-model="paramForm[param.name]"
          />
          <el-date-picker
            v-else-if="param.type === 'date'"
            v-model="paramForm[param.name]"
            type="date"
            :placeholder="param.placeholder"
          />
          <el-input
            v-else
            v-model="paramForm[param.name]"
            :placeholder="param.placeholder"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="paramDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="loading" @click="executeWithParams">
          执行
        </el-button>
      </template>
    </el-dialog>

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
        <el-button type="primary" :loading="loading" @click="confirmExecute">
          确定
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="resultDialogVisible"
      :title="resultTitle"
      width="500px"
      append-to-body
    >
      <div class="action-executor__result">
        <el-result
          v-if="lastResult?.success"
          icon="success"
          title="操作成功"
          :sub-title="lastResult.message"
        />
        <el-result
          v-else
          icon="error"
          title="操作失败"
          :sub-title="lastResult?.message || '未知错误'"
        />
      </div>
      <template #footer>
        <el-button type="primary" @click="resultDialogVisible = false">
          关闭
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, reactive } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import { useCrudMessage } from '@/composables/useCrudMessage'
import boService from '@/services/boService'
import { evaluateCondition } from '@/utils/safeExpression'

const props = defineProps({
  objectType: {
    type: String,
    required: true
  },
  objectId: {
    type: [Number, String],
    required: true
  },
  actions: {
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
    default: '操作'
  },
  record: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['execute', 'success', 'error'])

const message = useCrudMessage()

const loading = ref(false)
const paramDialogVisible = ref(false)
const confirmDialogVisible = ref(false)
const resultDialogVisible = ref(false)
const currentAction = ref(null)
const pendingAction = ref(null)
const paramFormRef = ref(null)
const paramForm = reactive({})
const paramRules = ref({})
const lastResult = ref(null)

const groupedActions = computed(() => {
  const groups = {}
  
  props.actions.forEach(action => {
    const category = action.category || ''
    if (!groups[category]) {
      groups[category] = {
        category,
        actions: []
      }
    }
    groups[category].actions.push(action)
  })
  
  return Object.values(groups)
})

const confirmTitle = computed(() => {
  return pendingAction.value?.confirmTitle || '确认操作'
})

const confirmMessage = computed(() => {
  return pendingAction.value?.confirmMessage || '确定要执行此操作吗？'
})

const resultTitle = computed(() => {
  return lastResult.value?.success ? '操作成功' : '操作失败'
})

const getButtonType = (action) => {
  return action.buttonType || action.type || 'primary'
}

const isActionDisabled = (action) => {
  if (action.disabled) return true
  
  if (action.condition && props.record) {
    const visible = evaluateCondition(action.condition, props.record, 'record')
    return !visible
  }
  
  return false
}

const handleAction = (action) => {
  if (isActionDisabled(action)) return
  
  currentAction.value = action
  
  if (action.params && action.params.length > 0) {
    Object.keys(paramForm).forEach(key => delete paramForm[key])
    
    action.params.forEach(param => {
      paramForm[param.name] = param.default !== undefined ? param.default : null
    })
    
    paramRules.value = {}
    action.params.forEach(param => {
      if (param.required) {
        paramRules.value[param.name] = [
          { required: true, message: `${param.label || param.name} 是必填项`, trigger: 'blur' }
        ]
      }
    })
    
    paramDialogVisible.value = true
  } else if (action.requireConfirm) {
    pendingAction.value = action
    confirmDialogVisible.value = true
  } else {
    executeAction(action, {})
  }
}

const executeWithParams = async () => {
  if (paramFormRef.value) {
    try {
      await paramFormRef.value.validate()
    } catch (e) {
      return
    }
  }
  
  paramDialogVisible.value = false
  
  if (currentAction.value.requireConfirm) {
    pendingAction.value = currentAction.value
    confirmDialogVisible.value = true
  } else {
    executeAction(currentAction.value, { ...paramForm })
  }
}

const confirmExecute = () => {
  confirmDialogVisible.value = false
  if (pendingAction.value) {
    executeAction(pendingAction.value, { ...paramForm })
  }
}

const executeAction = async (action, params) => {
  loading.value = true
  
  try {
    const result = await boService.executeAction(
      props.objectType,
      props.objectId,
      action.name || action.id,
      params
    )
    
    lastResult.value = result
    
    if (result.success) {
      if (action.showResult !== false) {
        resultDialogVisible.value = true
      } else {
        message.success(result.message || `${action.label || action.name} 成功`)
      }
      emit('success', { action, result, params })
    } else {
      if (action.showError !== false) {
        resultDialogVisible.value = true
      } else {
        message.error(`${action.label || action.name} 失败`, result)
      }
      emit('error', { action, error: result.message, params })
    }

    emit('execute', { action, result, params })
  } catch (error) {
    console.error('Action execution error:', error)
    lastResult.value = { success: false, message: error.message }

    if (action.showError !== false) {
      resultDialogVisible.value = true
    } else {
      message.error(`${action.label || action.name} 失败: ${error.message}`, error)
    }
    
    emit('error', { action, error: error.message, params })
  } finally {
    loading.value = false
    currentAction.value = null
    pendingAction.value = null
  }
}

defineExpose({
  executeAction,
  lastResult
})
</script>

<style scoped>
.action-executor {
  display: inline-block;
}

.action-executor__result {
  padding: 20px 0;
}

.el-dropdown-menu__item {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
