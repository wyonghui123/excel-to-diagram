<template>
  <transition name="toolbar-slide">
    <div v-if="show" class="inline-edit-toolbar" :class="[`position-${position}`]">
      <div class="toolbar-content">
        <el-icon class="warning-icon"><WarningFilled /></el-icon>
        <span class="draft-count">
          {{ draftCount }} 项已修改
        </span>
        <el-divider direction="vertical" />
        <el-button size="small" :disabled="saving" @click="$emit('cancel')">
          取消
        </el-button>
        <el-button 
          type="primary" 
          size="small" 
          :loading="saving"
          @click="$emit('save')"
        >
          保存
        </el-button>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { WarningFilled } from '@element-plus/icons-vue'

defineProps({
  show: {
    type: Boolean,
    default: false
  },
  draftCount: {
    type: Number,
    default: 0
  },
  position: {
    type: String,
    default: 'bottom',
    validator: (v) => ['top', 'bottom'].includes(v)
  },
  saving: {
    type: Boolean,
    default: false
  }
})

defineEmits(['save', 'cancel'])
</script>

<style scoped>
.inline-edit-toolbar {
  position: sticky;
  left: 0;
  right: 0;
  z-index: 100;
  background: #fff;
  border: 1px solid var(--el-color-primary-light-5);
  border-radius: 4px;
  padding: 8px 16px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.inline-edit-toolbar.position-bottom {
  bottom: 0;
  margin-top: 8px;
}

.inline-edit-toolbar.position-top {
  top: 0;
  margin-bottom: 8px;
}

.toolbar-content {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.warning-icon {
  color: var(--el-color-warning);
  font-size: 16px;
}

.draft-count {
  font-size: 14px;
  color: var(--el-text-color-regular);
  font-weight: 500;
}

.toolbar-slide-enter-active,
.toolbar-slide-leave-active {
  transition: all 0.3s ease;
}

.toolbar-slide-enter-from,
.toolbar-slide-leave-to {
  opacity: 0;
  transform: translateY(10px);
}
</style>
