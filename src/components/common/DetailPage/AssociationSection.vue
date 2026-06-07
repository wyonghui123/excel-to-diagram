<template>
  <div class="association-section">
    <div class="as-header" @click="toggle">
      <div class="as-header__left">
        <el-icon class="as-header__arrow" :class="{ 'is-expanded': !collapsed }">
          <ArrowRight />
        </el-icon>
        <span class="as-header__title">{{ title }}</span>
        <el-tag v-if="count > 0" size="small" type="info" class="as-header__count">
          {{ count }}
        </el-tag>
      </div>
    </div>

    <div v-if="!collapsed" class="as-content">
      <slot />
    </div>
  </div>
</template>

<script setup>
import { ArrowRight } from '@element-plus/icons-vue'

const props = defineProps({
  title: {
    type: String,
    required: true
  },
  collapsed: {
    type: Boolean,
    default: true
  },
  count: {
    type: Number,
    default: 0
  }
})

const emit = defineEmits(['update:collapsed'])

function toggle() {
  emit('update:collapsed', !props.collapsed)
}
</script>

<style scoped>
.association-section {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  margin-bottom: 12px;
  overflow: hidden;
}

.as-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--el-fill-color-light);
  cursor: pointer;
  user-select: none;
  transition: background-color 0.2s;
}

.as-header:hover {
  background: var(--el-fill-color);
}

.as-header__left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.as-header__arrow {
  transition: transform 0.3s;
  color: var(--el-text-color-secondary);
}

.as-header__arrow.is-expanded {
  transform: rotate(90deg);
}

.as-header__title {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.as-header__count {
  margin-left: 4px;
}

.as-content {
  padding: 16px;
  background: var(--el-bg-color);
}
</style>
