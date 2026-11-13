<template>
  <el-tag v-if="item" :type="tagType" size="small" disable-transitions>
    {{ item.label }}
  </el-tag>
  <span v-else class="enum-tag--unknown">{{ displayValue }}</span>
</template>

<script setup>
/**
 * EnumTag.vue - 枚举/状态标签（T13-4）
 *
 * 本组件是 EnumColor -> Element Plus el-tag type 的唯一映射点；
 * 未知枚举值渲染原值（0 / false 不会被当空显示成 '-'）+ info 色。
 */

import { computed, onMounted, ref, watch } from 'vue'
import { useEnumMeta } from '@/composables/useEnumMeta'

const props = defineProps({
  enumName: { type: String, default: '' },
  value: { type: [String, Number, Boolean], default: null },
  // 迁移期可选：由调用方传入 ui-meta 的 schema_version，缺省走默认缓存
  schemaVersion: { type: String, default: undefined }
})

const COLOR_TO_TAG_TYPE = {
  success: 'success',
  warning: 'warning',
  danger: 'danger',
  info: 'info',
  primary: 'primary'
}

const { load, getItem } = useEnumMeta()
// 模块级缓存非响应式，加载完成后 bump 触发重新取值
const cacheTick = ref(0)

const item = computed(() => {
  cacheTick.value // 建立响应式依赖
  return getItem(props.enumName, props.value)
})
const tagType = computed(() => COLOR_TO_TAG_TYPE[item.value?.color] || 'info')
const displayValue = computed(() =>
  props.value === null || props.value === undefined ? '-' : String(props.value)
)

async function ensureLoaded() {
  if (!props.enumName) return
  try {
    await load(props.enumName, props.schemaVersion)
    cacheTick.value++
  } catch {
    // 枚举下发失败保持未知态（fail-closed：显示原值 + info）
  }
}

onMounted(ensureLoaded)
watch(() => [props.enumName, props.schemaVersion], ensureLoaded)
</script>

<style scoped>
.enum-tag--unknown {
  color: var(--el-text-color-secondary);
}
</style>