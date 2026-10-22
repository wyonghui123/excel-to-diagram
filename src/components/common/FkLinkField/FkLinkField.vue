<template>
  <!-- drawer 模式：点击触发事件，由父组件在 drawer 中打开详情 -->
  <a
    v-if="isClickable && detailMode === 'drawer'"
    class="fk-link"
    :title="linkTitle"
    @click.stop="handleClick"
  >
    <span class="fk-link__text">{{ displayValue || value }}</span>
    <el-icon class="fk-link__icon" aria-hidden="true"><Promotion /></el-icon>
  </a>
  <!-- page 模式：router-link 跳转到独立详情页 -->
  <router-link
    v-else-if="isClickable"
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
  },
  /**
   * [FK 2026-10-22] 跳转落点覆盖（value_help.source.detail_target_bo）。
   * 非空时用它替代 targetObjectType 作为详情页 BO——让链接落到信息更完整的
   * 基表而非只读视图。空 = 与 targetObjectType 同口径（向后兼容）。
   */
  linkObjectType: {
    type: String,
    default: ''
  },
  /**
   * [FK 2026-10-22] 跳转落点 id（后端 enrichment 下发的 {field}_link_id）。
   * 与 linkObjectType 配套：id 空间不同源时（如 FK 存 parties.id、落点 orgs.id）
   * 由后端换算后下发。为 null 表示查不到对应落点行（历史脏数据）⇒ 渲染纯文本。
   * 未传（undefined）时回退用 value。
   */
  linkId: {
    type: [String, Number],
    default: undefined
  }
})

const emit = defineEmits(['navigate'])

// 落点 BO：优先 detail_target_bo，缺省与 targetObjectType 同口径
const resolvedObjectType = computed(() => props.linkObjectType || props.targetObjectType || '')

// 落点 id：linkId 为 null 时无落点（脏数据）；undefined 时回退用 value
const resolvedId = computed(() => {
  if (props.linkId === null) return null
  return props.linkId !== undefined ? props.linkId : props.value
})

const targetRoute = computed(() => {
  if (resolvedId.value == null || !resolvedObjectType.value) return null
  return { path: `/detail/${resolvedObjectType.value}/${resolvedId.value}` }
})

const isClickable = computed(() => {
  if (props.linkDisabled) return false
  if (!props.value || !targetRoute.value) return false
  return true
})

const linkTitle = computed(() => {
  if (resolvedId.value == null) return '暂无对应落点记录'
  const label = props.targetObjectLabel || resolvedObjectType.value || '关联对象'
  return `打开 ${label} 详情`
})

function handleClick() {
  emit('navigate', {
    objectType: resolvedObjectType.value,
    id: resolvedId.value,
    displayValue: props.displayValue
  })
}
</script>

<style scoped>
.fk-link {
  /* 使用文本主色（黑色）保持与原版一致；hover 时用 primary 强调交互 */
  color: var(--color-text-primary);
  text-decoration: none;
  cursor: pointer;
  transition: color 0.15s ease, text-decoration 0.15s ease;
  font-size: 13px;
  line-height: 1.6;
  /* 显式锁死普通字重，避免被父级 (cell/el-tooltip/表头 sortable) 的
     font-weight: 500/700 影响而看起来像 strong */
  font-weight: 400;
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
  /* 与 .fk-link 同步锁死普通字重，防止外部 strong 样式干扰 */
  font-weight: 400;
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
