<!--
  [V1.2.0 2026-06-15] BoCodeSelector.vue - 跨域关系 Pick by Code 模式
  ===================================================================
  用途: 跨域关系创建时, 当 D1 manager 在 List mode 看不到 D2 BO,
        可在此模式输入目标 BO code 直接查询 (逃生口)
  行为:
    - 输入 BO code, 点击"查询" 调 /bo/business_object/pick_by_code
    - 成功后 emit('update:selected', bo) 给父组件
    - 失败 (404/401/500) 显示友好错误, 不阻塞用户
  Props:
    - productId (Number, required): 当前 product id (OQ2 必填, 防止跨产品误选)
    - disabled (Boolean): 父组件禁用状态
    - placeholder (String): 输入框 placeholder
  Emits:
    - update:selected (Object): { id, code, name, description, ... }
    - error (String): 错误码 (MISSING_CODE | BO_NOT_FOUND | NETWORK_ERROR | UNAUTHORIZED)
  Spec: .trae/specs/cross-domain-relationship-permission/spec.md (T3.1.2)
-->
<template>
  <div class="bo-code-selector">
    <div class="bo-code-selector__input-row">
      <el-input
        v-model="code"
        :placeholder="placeholder"
        :disabled="disabled || loading"
        clearable
        @keyup.enter="handleSearch"
        @clear="handleClear"
      >
        <template #append>
          <el-button
            :loading="loading"
            :disabled="disabled || !code || !code.trim()"
            @click="handleSearch"
          >
            查询
          </el-button>
        </template>
      </el-input>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="bo-code-selector__status">
      <el-icon class="is-loading"><Loading /></el-icon>
      <span>正在查询...</span>
    </div>

    <!-- 成功结果 -->
    <div v-else-if="result" class="bo-code-selector__result">
      <el-card shadow="never" class="bo-code-selector__card">
        <div class="bo-code-selector__card-header">
          <el-tag type="success" size="small">已找到</el-tag>
          <el-button
            type="primary"
            size="small"
            :disabled="disabled"
            @click="handleSelect"
          >
            选择
          </el-button>
        </div>
        <div class="bo-code-selector__card-body">
          <div class="bo-code-selector__row">
            <span class="bo-code-selector__label">编码:</span>
            <span class="bo-code-selector__value">{{ result.code }}</span>
          </div>
          <div class="bo-code-selector__row">
            <span class="bo-code-selector__label">名称:</span>
            <span class="bo-code-selector__value">{{ result.name }}</span>
          </div>
          <div v-if="result.description" class="bo-code-selector__row">
            <span class="bo-code-selector__label">描述:</span>
            <span class="bo-code-selector__value">{{ result.description }}</span>
          </div>
        </div>
      </el-card>
    </div>

    <!-- 错误提示 -->
    <el-alert
      v-else-if="errorMessage"
      :title="errorTitle"
      :type="errorType"
      :closable="false"
      show-icon
      class="bo-code-selector__alert"
    >
      <template v-if="errorHint">
        <div class="bo-code-selector__hint">{{ errorHint }}</div>
      </template>
    </el-alert>

    <!-- 空状态 (初始) -->
    <div v-else class="bo-code-selector__empty">
      <el-icon><Document /></el-icon>
      <span>输入 BO 完整编码 (如 <code>BO_B_001</code>), 按回车或点击"查询"</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { Loading, Document } from '@element-plus/icons-vue'
import boService from '@/services/boService'

const props = defineProps({
  productId: {
    type: [Number, String],
    required: true,
    validator: (v) => v !== null && v !== undefined && v !== ''
  },
  disabled: {
    type: Boolean,
    default: false
  },
  placeholder: {
    type: String,
    default: '请输入 BO 完整编码, 如 BO_B_001'
  }
})

const emit = defineEmits(['update:selected', 'error'])

// ===== State =====
const code = ref('')
const loading = ref(false)
const result = ref(null)
const errorMessage = ref('')
const errorCode = ref('')

// ===== Computed =====
const errorType = computed(() => {
  // 不同错误码对应不同 alert 颜色
  if (errorCode.value === 'BO_NOT_FOUND') return 'warning'
  if (errorCode.value === 'UNAUTHORIZED') return 'error'
  return 'error'
})

const errorTitle = computed(() => {
  switch (errorCode.value) {
    case 'BO_NOT_FOUND':
      return '未找到该 BO'
    case 'UNAUTHORIZED':
      return '未授权'
    case 'MISSING_CODE':
      return '请输入 BO 编码'
    case 'MISSING_PRODUCT_ID':
      return '缺少 product_id'
    case 'NETWORK_ERROR':
      return '网络错误'
    default:
      return '查询失败'
  }
})

const errorHint = computed(() => {
  switch (errorCode.value) {
    case 'BO_NOT_FOUND':
      return '请检查编码是否正确, 或确认该 BO 属于当前 product'
    case 'UNAUTHORIZED':
      return '请重新登录后再试'
    case 'NETWORK_ERROR':
      return '请检查网络连接, 或稍后重试'
    default:
      return ''
  }
})

// ===== Watch =====
watch(() => props.productId, (newVal, oldVal) => {
  // productId 变化时清空结果 (避免显示陈旧数据)
  if (newVal !== oldVal) {
    handleClear()
  }
})

// ===== Methods =====
async function handleSearch() {
  const trimmedCode = (code.value || '').trim()
  if (!trimmedCode) {
    errorCode.value = 'MISSING_CODE'
    errorMessage.value = '请输入 BO 编码'
    result.value = null
    emit('error', 'MISSING_CODE')
    return
  }
  if (!props.productId) {
    errorCode.value = 'MISSING_PRODUCT_ID'
    errorMessage.value = '缺少 product_id'
    result.value = null
    emit('error', 'MISSING_PRODUCT_ID')
    return
  }

  loading.value = true
  errorMessage.value = ''
  errorCode.value = ''
  result.value = null

  try {
    const res = await boService.pickBoByCode(trimmedCode, props.productId, {
      reason: 'cross_domain_relationship_create'
    })

    if (res.success && res.data) {
      result.value = res.data
      errorMessage.value = ''
    } else {
      // 后端返回 success=false, 提取 error_code
      const errCode = res.code || res.message || 'UNKNOWN'
      errorCode.value = mapErrorCode(errCode, res.httpStatus)
      errorMessage.value = errCode
      result.value = null
      emit('error', errorCode.value)
    }
  } catch (e) {
    // 网络异常
    errorCode.value = 'NETWORK_ERROR'
    errorMessage.value = e?.message || 'NETWORK_ERROR'
    result.value = null
    emit('error', 'NETWORK_ERROR')
  } finally {
    loading.value = false
  }
}

function handleSelect() {
  if (result.value) {
    emit('update:selected', { ...result.value })
  }
}

function handleClear() {
  code.value = ''
  result.value = null
  errorMessage.value = ''
  errorCode.value = ''
}

function mapErrorCode(backendCode, httpStatus) {
  // 后端错误码 → 前端友好错误码
  if (httpStatus === 404 || backendCode === 'BO_NOT_FOUND') return 'BO_NOT_FOUND'
  if (httpStatus === 401 || backendCode === 'UNAUTHORIZED') return 'UNAUTHORIZED'
  if (backendCode === 'MISSING_CODE') return 'MISSING_CODE'
  if (backendCode === 'MISSING_PRODUCT_ID') return 'MISSING_PRODUCT_ID'
  return 'UNKNOWN'
}

defineExpose({
  handleSearch,
  handleClear,
  // 暴露状态供父组件读取
  getResult: () => result.value,
  getError: () => ({ code: errorCode.value, message: errorMessage.value })
})
</script>

<style scoped>
.bo-code-selector {
  width: 100%;
}

.bo-code-selector__input-row {
  margin-bottom: 12px;
}

.bo-code-selector__status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

.bo-code-selector__result {
  margin-top: 4px;
}

.bo-code-selector__card {
  border: 1px solid var(--el-color-success-light-5);
  background-color: var(--el-color-success-light-9);
}

.bo-code-selector__card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.bo-code-selector__card-body {
  font-size: 14px;
}

.bo-code-selector__row {
  display: flex;
  gap: 8px;
  margin-bottom: 4px;
}

.bo-code-selector__label {
  color: var(--el-text-color-secondary);
  min-width: 48px;
}

.bo-code-selector__value {
  color: var(--el-text-color-primary);
  font-weight: 500;
}

.bo-code-selector__alert {
  margin-top: 4px;
}

.bo-code-selector__hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.bo-code-selector__empty {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 12px;
  color: var(--el-text-color-placeholder);
  font-size: 13px;
  border: 1px dashed var(--el-border-color);
  border-radius: var(--el-border-radius-base);
  background-color: var(--el-fill-color-blank);
}

.bo-code-selector__empty code {
  padding: 2px 6px;
  background-color: var(--el-fill-color);
  border-radius: 3px;
  font-family: var(--el-font-family-monospace, monospace);
  font-size: 12px;
  color: var(--el-text-color-regular);
}
</style>
