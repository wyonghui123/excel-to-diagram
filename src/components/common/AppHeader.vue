<template>
  <header class="page-header">
    <div class="page-header__left">
      <slot name="left">
        <el-button v-if="showBack" link @click="$emit('back')">
          <el-icon><ArrowLeft /></el-icon>
          返回
        </el-button>
        <h1 v-if="title" class="page-header__title">{{ title }}</h1>
      </slot>
    </div>

    <div class="page-header__right">
      <slot name="right" />
    </div>
  </header>
</template>

<script setup>
import { ArrowLeft } from '@element-plus/icons-vue'

defineProps({
  title: {
    type: String,
    default: ''
  },
  showBack: {
    type: Boolean,
    default: false
  }
})

defineEmits(['back'])
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md) var(--spacing-lg);
  background: var(--el-bg-color, #fff);
  border-bottom: 1px solid var(--el-border-color, #e5e6eb);
}

.page-header__left {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.page-header__title {
  margin: 0;
  font-size: var(--el-font-size-large, 18px);
  font-weight: 600;
  color: var(--el-text-color-primary, #303133);
}

.page-header__right {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}
</style>
