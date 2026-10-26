---
alwaysApply: false
description: "AI 组件开发模板 - Vue 3 Composition API + Element Plus"
---

# AI 组件开发模板（v4.0 拆分）

> **拆分自** `AI_AGENT_COMPONENT_GUIDE.md` (593 行)
> **本文件覆盖**：§4 组件开发模板 + index.js 导出模板
> **相关**：[ai-component-reference.md](./ai-component-reference.md)（核心原则）/ [ai-component-checklist.md](./ai-component-checklist.md)（检查清单）

---

## 标准组件结构

```vue
<!-- src/components/common/ComponentName/ComponentName.vue -->
<template>
  <el-button
    :type="type"
    :size="size"
    :disabled="disabled"
    @click="handleClick"
  >
    <slot>{{ label }}</slot>
  </el-button>
</template>

<script setup>
import { ref, computed, defineEmits } from 'vue'

// Props 定义
const props = defineProps({
  type: {
    type: String,
    default: 'primary',
    validator: (v) => ['primary', 'success', 'warning', 'danger', 'info'].includes(v)
  },
  size: {
    type: String,
    default: 'default',
    validator: (v) => ['large', 'default', 'small'].includes(v)
  },
  disabled: { type: Boolean, default: false },
  label: { type: String, default: '' }
})

// Emits 定义
const emit = defineEmits(['click', 'change'])

// 内部状态
const internalState = ref(false)

// 计算属性
const computedValue = computed(() => {
  return props.disabled ? 'disabled' : 'enabled'
})

// 方法
function handleClick(event) {
  if (props.disabled) return
  emit('click', event)
}

// 生命周期
onMounted(() => {
  // 初始化逻辑
})

onBeforeUnmount(() => {
  // 清理逻辑
})
</script>

<style scoped>
/* 组件样式 - 使用 YonDesign 规范 */
.app-component-name {
  border-radius: var(--radius-md);  /* 6px */
}
</style>
```

---

## index.js 导出模板

```javascript
// src/components/common/ComponentName/index.js
import ComponentName from './ComponentName.vue'

ComponentName.install = function(Vue) {
  Vue.component(ComponentName.name, ComponentName)
}

export default ComponentName
export { ComponentName }
```

---

## 关键模式

### 1. v-model 双向绑定

```vue
<template>
  <el-input v-model="modelValue" @update:modelValue="emit('update:modelValue', $event)" />
</template>

<script setup>
const props = defineProps({ modelValue: { type: String, default: '' } })
const emit = defineEmits(['update:modelValue'])
</script>
```

### 2. 插槽透传

```vue
<template>
  <el-card>
    <slot name="header" />
    <slot />
    <template v-if="$slots.footer" #footer>
      <slot name="footer" />
    </template>
  </el-card>
</template>
```

### 3. Provide / Inject

```vue
<!-- Parent -->
<script setup>
import { provide } from 'vue'
provide('theme', 'dark')
</script>

<!-- Child -->
<script setup>
import { inject } from 'vue'
const theme = inject('theme', 'light')
</script>
```

### 4. 异步组件

```javascript
import { defineAsyncComponent } from 'vue'

const HeavyComponent = defineAsyncComponent(() =>
  import('./HeavyComponent.vue')
)
```

---

## CHANGELOG

| 日期 | 变更 | 内容 |
|---|---|---|
| 2026-09-02 | 拆分 | 从 AI_AGENT_COMPONENT_GUIDE 拆出模板 |