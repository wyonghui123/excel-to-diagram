<template>
  <router-link
    v-if="value && targetRoute && !linkDisabled"
    :to="targetRoute"
    class="fk-link"
    :title="linkTitle"
    @click.stop
  >
    <span class="fk-link__text">{{ displayValue || value }}</span>
    <el-icon class="fk-link__icon" aria-hidden="true"><Promotion /></el-icon>
  </router-link>
  <span
    v-else-if="value"
    class="fk-link fk-link--disabled"
    :title="linkTitle"
  >
    <span class="fk-link__text">{{ displayValue || value }}</span>
    <el-icon class="fk-link__icon" aria-hidden="true"><Promotion /></el-icon>
  </span>
  <span v-else class="fk-empty">-</span>
</template>

<script setup>
import { computed } from 'vue'
import { Promotion } from '@element-plus/icons-vue'

const props = defineProps({
  value: {
    type: [String, Number],
    default: null
  },
  displayValue: {
    type: String,
    default: ''
  },
  targetObjectType: {
    type: String,
    required: true
  },
  /**
   * 禁用链接导航（dialog/embedded 模式下使用）
   * 降级为纯文本显示，保留视觉样式但不可点击跳转
   */
  linkDisabled: {
    type: Boolean,
    default: false
  },
  /**
   * 目标对象显示名称（用于 tooltip），未传时回退到 targetObjectType
   */
  targetObjectLabel: {
    type: String,
    default: ''
  }
})

const targetRoute = computed(() => {
  if (!props.value || !props.targetObjectType) return null
  // FK 链接总是跳转到详情页：/detail/:objectType/:id
  return { path: `/detail/${props.targetObjectType}/${props.value}` }
})

const linkTitle = computed(() => {
  const label = props.targetObjectLabel || props.targetObjectType || '关联对象'
  return `打开 ${label} 详情`
})
</script>

<style scoped>
.fk-link {
  color: var(--color-primary);
  text-decoration: none;
  cursor: pointer;
  transition: color 0.15s ease, text-decoration 0.15s ease;
  font-size: 13px;
  line-height: 1.6;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  vertical-align: middle;
}

.fk-link:hover {
  color: var(--color-primary-hover);
  text-decoration: underline;
}

.fk-link__text {
  /* 文本不换行，避免与图标分离 */
  white-space: nowrap;
}

/* FK 跳转标识图标：默认半透明，hover 时与文字一同高亮 */
.fk-link__icon {
  font-size: 12px;
  line-height: 1;
  opacity: 0.7;
  transition: opacity 0.15s ease;
  flex-shrink: 0;
}

.fk-link:hover .fk-link__icon {
  opacity: 1;
}

/* 禁用状态：保留颜色样式但无悬停效果和光标 */
.fk-link--disabled {
  cursor: default;
}

.fk-link--disabled:hover {
  text-decoration: none;
}

.fk-link--disabled .fk-link__icon {
  /* 禁用态下图标保持稍弱透明度，提示"不可点击跳转" */
  opacity: 0.5;
}

.fk-empty {
  color: var(--color-text-tertiary);
}
</style>
