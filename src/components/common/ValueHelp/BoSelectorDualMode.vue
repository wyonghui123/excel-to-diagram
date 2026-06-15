<!--
  [V1.2.0 2026-06-15] BoSelectorDualMode.vue - 跨域关系双模式 ValueHelp
  ===================================================================
  用途: 关系表单 (source_bo, target_bo) 字段的双模式选择器
  模式:
    - List 模式 (默认): 4 级级联 + 跨域 toggle, 受 read scope 过滤
    - By Code 模式: 输入 BO code 直接查询, 跳过 read scope (逃生口)
  Props:
    - productId (Number, required)
    - modelValue (Object): 当前选中的 BO { id, code, name, ... }
    - label (String): 表单字段标签
    - required (Boolean)
    - allowCrossDomain (Boolean): List 模式是否显示"跨域浏览" toggle
  Emits:
    - update:modelValue (Object)
    - change (Object)
  Spec: .trae/specs/cross-domain-relationship-permission/spec.md (T3.1.3)
-->
<template>
  <div class="bo-selector-dual-mode">
    <!-- 当前已选 BO -->
    <div v-if="selectedBo" class="bo-selector-dual-mode__selected">
      <el-card shadow="never" class="bo-selector-dual-mode__card">
        <div class="bo-selector-dual-mode__card-header">
          <el-tag type="success" size="small">已选</el-tag>
          <el-button
            type="primary"
            size="small"
            text
            @click="openDialog"
          >
            更换
          </el-button>
        </div>
        <div class="bo-selector-dual-mode__card-body">
          <strong>{{ selectedBo.code }}</strong> — {{ selectedBo.name }}
          <span v-if="selectedBo.description" class="bo-selector-dual-mode__desc">
            ({{ selectedBo.description }})
          </span>
        </div>
      </el-card>
    </div>

    <!-- 触发按钮 (未选时显示) -->
    <el-button
      v-else
      :disabled="disabled"
      type="primary"
      plain
      @click="openDialog"
    >
      <el-icon><Search /></el-icon>
      <span>选择 BO</span>
    </el-button>

    <!-- 弹窗: 双模式 Tabs -->
    <el-dialog
      v-model="dialogVisible"
      :title="label || '选择业务对象'"
      width="640px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <el-tabs v-model="activeTab" class="bo-selector-dual-mode__tabs">
        <!-- Tab 1: List 模式 -->
        <el-tab-pane label="列表选择" name="list">
          <BoListSelector
            ref="listSelectorRef"
            :product-id="productId"
            :model-value="selectedBo"
            :allow-cross-domain="allowCrossDomain"
            :disabled="disabled"
            @update:selected="handleSelected"
            @cross-domain-toggled="handleCrossDomainToggled"
          />
        </el-tab-pane>

        <!-- Tab 2: By Code 模式 -->
        <el-tab-pane label="按编码选择" name="code">
          <BoCodeSelector
            ref="codeSelectorRef"
            :product-id="productId"
            :disabled="disabled"
            @update:selected="handleSelected"
            @error="handleCodeError"
          />
          <div class="bo-selector-dual-mode__tip">
            <el-icon><InfoFilled /></el-icon>
            <span>
              按编码可直接选择其他域的 BO (不受 read scope 限制),
              写时仍受 functional perm 校验。
            </span>
          </div>
        </el-tab-pane>
      </el-tabs>

      <template #footer>
        <el-button @click="dialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { Search, InfoFilled } from '@element-plus/icons-vue'
import BoListSelector from './BoListSelector.vue'
import BoCodeSelector from './BoCodeSelector.vue'

const props = defineProps({
  productId: {
    type: [Number, String],
    required: true
  },
  modelValue: {
    type: Object,
    default: null
  },
  label: {
    type: String,
    default: ''
  },
  required: {
    type: Boolean,
    default: false
  },
  disabled: {
    type: Boolean,
    default: false
  },
  allowCrossDomain: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['update:modelValue', 'change', 'cross-domain-toggled', 'code-error'])

// ===== State =====
const dialogVisible = ref(false)
const activeTab = ref('list')
const selectedBo = ref(props.modelValue)
const listSelectorRef = ref(null)
const codeSelectorRef = ref(null)

// ===== Watch =====
watch(() => props.modelValue, (val) => {
  selectedBo.value = val
}, { immediate: true, deep: true })

// ===== Methods =====
function openDialog() {
  if (props.disabled) return
  dialogVisible.value = true
}

function handleSelected(bo) {
  selectedBo.value = bo
  emit('update:modelValue', bo)
  emit('change', bo)
  // 选完自动关闭弹窗
  dialogVisible.value = false
}

function handleCrossDomainToggled(val) {
  emit('cross-domain-toggled', val)
}

function handleCodeError(errCode) {
  emit('code-error', errCode)
}

function clearSelection() {
  selectedBo.value = null
  emit('update:modelValue', null)
  emit('change', null)
}

defineExpose({
  openDialog,
  clearSelection,
  switchToList: () => { activeTab.value = 'list' },
  switchToCode: () => { activeTab.value = 'code' },
  getSelected: () => selectedBo.value
})
</script>

<style scoped>
.bo-selector-dual-mode {
  width: 100%;
}

.bo-selector-dual-mode__selected {
  margin-bottom: 8px;
}

.bo-selector-dual-mode__card {
  border: 1px solid var(--el-color-success-light-5);
  background-color: var(--el-color-success-light-9);
}

.bo-selector-dual-mode__card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.bo-selector-dual-mode__card-body {
  font-size: 14px;
  color: var(--el-text-color-primary);
}

.bo-selector-dual-mode__desc {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-left: 4px;
}

.bo-selector-dual-mode__tip {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-top: 12px;
  padding: 8px 12px;
  background-color: var(--el-color-info-light-9);
  border-radius: var(--el-border-radius-base);
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.bo-selector-dual-mode__tip .el-icon {
  color: var(--el-color-info);
  margin-top: 2px;
}

.bo-selector-dual-mode__tabs {
  min-height: 200px;
}
</style>
