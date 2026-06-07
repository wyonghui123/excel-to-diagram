<template>
  <div v-if="sourceInfo" class="nav-source-info">
    <div class="nav-source-info__content">
      <el-icon :size="14" class="nav-source-info__icon">
        <Link />
      </el-icon>
      <span class="nav-source-info__text">
        从
        <strong>{{ sourceInfo.sourceNames.join(', ') }}</strong>
        的
        <strong>{{ sourceInfo.associationLabel }}</strong>
        导航
      </span>
      <el-tag
        v-if="sourceInfo.sourceCount > 1"
        size="small"
        type="info"
        class="nav-source-info__tag"
      >
        {{ sourceInfo.sourceCount }} 个对象
      </el-tag>
    </div>
    <el-button
      type="primary"
      size="small"
      link
      @click="onNavigateBack"
    >
      <el-icon><ArrowLeft /></el-icon>
      返回来源
    </el-button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Link, ArrowLeft } from '@element-plus/icons-vue'

const props = defineProps({
  sourceType: {
    type: String,
    default: ''
  },
  sourceIds: {
    type: Array,
    default: () => []
  },
  sourceNames: {
    type: Array,
    default: () => []
  },
  associationName: {
    type: String,
    default: ''
  },
  associationLabel: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['navigate-back'])

const sourceInfo = computed(() => {
  if (!props.sourceType || props.sourceIds.length === 0) return null

  return {
    sourceType: props.sourceType,
    sourceIds: props.sourceIds,
    sourceNames: props.sourceNames.length > 0
      ? props.sourceNames
      : props.sourceIds.map(id => `#${id}`),
    associationName: props.associationName,
    associationLabel: props.associationLabel || props.associationName,
    sourceCount: props.sourceIds.length
  }
})

function onNavigateBack() {
  emit('navigate-back')
}
</script>

<style scoped>
.nav-source-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  background: var(--el-color-primary-light-9, #ecf5ff);
  border: 1px solid var(--el-color-primary-light-7, #c6e2ff);
  border-radius: var(--el-border-radius-base, 4px);
  margin-bottom: var(--spacing-sm, 8px);
}

.nav-source-info__content {
  display: flex;
  align-items: center;
  gap: 6px;
}

.nav-source-info__icon {
  color: var(--el-color-primary, #ea580c);
  flex-shrink: 0;
}

.nav-source-info__text {
  font-size: 13px;
  color: var(--el-text-color-regular, #606266);
}

.nav-source-info__text strong {
  color: var(--el-text-color-primary, #303133);
}

.nav-source-info__tag {
  margin-left: 4px;
}
</style>
