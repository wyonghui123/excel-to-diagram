<template>
  <!-- drawer 模式：点击触发事件，由父组件在 drawer 中打开详情 -->
  <a
    v-if="value && targetObjectType && !linkDisabled && detailMode === 'drawer'"
    class="fk-link"
    :title="linkTitle"
    @click.stop="handleClick"
  >
    <span class="fk-link__text">{{ displayValue || value }}</span>
    <el-icon class="fk-link__icon" aria-hidden="true"><Promotion /></el-icon>
  </a>
  <!-- page 模式：router-link 跳转到独立详情页 -->
  <router-link
    v-else-if="value && targetRoute && !linkDisabled"
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
  <!--
    [FIX 2026-06-10] 当 value 为空但 displayValue 仍有值（如 cascade 清空下游 ID
    但残留显示文本、或后端 display_values 已就位但 formData[id] 缺失），
    显示 displayValue 作为提示，避免漏显。
  -->
  <span v-else-if="displayValue" class="fk-link fk-link--disabled fk-link--readonly">
    <span class="fk-link__text">{{ displayValue }}</span>
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
  },
  /**
   * 详情页打开模式：
   * - 'page': 跳转到独立详情页 /detail/:objectType/:id（默认）
   * - 'drawer': 触发 navigate 事件，由父组件在 drawer 中打开
   */
  detailMode: {
    type: String,
    default: 'page',
    validator: (v) => ['page', 'drawer'].includes(v)
  }
})

const emit = defineEmits(['navigate'])

const targetRoute = computed(() => {
  if (!props.value || !props.targetObjectType) return null
  return { path: `/detail/${props.targetObjectType}/${props.value}` }
})

const linkTitle = computed(() => {
  const label = props.targetObjectLabel || props.targetObjectType || '关联对象'
  return `打开 ${label} 详情`
})

function handleClick() {
  emit('navigate', {
    objectType: props.targetObjectType,
    id: props.value,
    displayValue: props.displayValue
  })
}
</script>

<style scoped>
.fk-link {
  /* FK 链接使用文本色 (近黑)，与主对象链接 (--color-primary 主橙色) 区分 */
  color: var(--color-text-primary);
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
  /* hover 时切换到主橙色，提示可点击 */
  color: var(--color-primary);
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
