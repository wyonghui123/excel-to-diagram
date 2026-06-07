# 组件迁移指南

> **版本**: v1.0
> **日期**: 2026-04-09

---

## 迁移概述

将现有组件从自定义样式迁移到新的UI组件库和设计令牌系统。

---

## 迁移步骤

### 1. 按钮迁移

**原代码**:
```vue
<button
  class="direction-btn"
  :class="{ active: layoutControlConfig?.overallDirection === 'LR' }"
  @click="updateOverallDirection('LR')"
>
  <span class="direction-icon">⬇️</span>
  <span class="direction-label">垂直</span>
</button>
```

**迁移后**:
```vue
<template>
  <AppButton
    variant="secondary"
    size="sm"
    :class="{ 'btn-active': layoutControlConfig?.overallDirection === 'LR' }"
    @click="updateOverallDirection('LR')"
  >
    <template #icon>⬇️</template>
    垂直
  </AppButton>
</template>

<script setup>
import { AppButton } from '@/components/common'
</script>

<style scoped>
.btn-active {
  background: var(--color-primary);
  color: var(--color-text-inverse);
}
</style>
```

### 2. 输入框迁移

**原代码**:
```vue
<input
  v-model="searchText"
  type="text"
  class="search-input"
  placeholder="搜索..."
/>
```

**迁移后**:
```vue
<template>
  <AppInput
    v-model="searchText"
    placeholder="搜索..."
    size="md"
  />
</template>

<script setup>
import { AppInput } from '@/components/common'
</script>
```

### 3. 卡片迁移

**原代码**:
```vue
<div class="card">
  <div class="card-header">标题</div>
  <div class="card-body">内容</div>
</div>
```

**迁移后**:
```vue
<template>
  <AppCard title="标题">
    内容
  </AppCard>
</template>

<script setup>
import { AppCard } from '@/components/common'
</script>
```

---

## 样式变量替换

| 原变量 | 新变量 |
|--------|--------|
| `$primary-color` | `var(--color-primary)` |
| `$text-color` | `var(--color-text-primary)` |
| `$border-color` | `var(--color-border)` |
| `$spacing-sm` | `var(--spacing-sm)` |
| `$radius-md` | `var(--radius-md)` |

---

## 工具类替换

| 原类名 | 新类名 |
|--------|--------|
| `.flex-center` | `.d-flex.items-center.justify-center` |
| `.text-ellipsis` | `.text-ellipsis` |
| `.mt-sm` | `.mt-sm` |
| `.p-md` | `.p-md` |

---

## 批量替换脚本

可以使用以下正则表达式进行批量替换：

```bash
# 替换颜色变量
find src -name "*.vue" -o -name "*.scss" | xargs sed -i 's/\$primary-color/var(--color-primary)/g'
find src -name "*.vue" -o -name "*.scss" | xargs sed -i 's/\$text-color/var(--color-text-primary)/g'

# 替换间距变量
find src -name "*.vue" -o -name "*.scss" | xargs sed -i 's/\$spacing-sm/var(--spacing-sm)/g'
find src -name "*.vue" -o -name "*.scss" | xargs sed -i 's/\$spacing-md/var(--spacing-md)/g'
```

---

## 验证清单

- [ ] 所有颜色使用设计令牌
- [ ] 所有间距使用设计令牌
- [ ] 组件正确导入
- [ ] 样式无硬编码值
- [ ] 深色模式正常显示
- [ ] 响应式布局正常

---

## 常见问题

### Q: 自定义样式如何保留？
A: 可以在组件上添加自定义class，使用scoped样式覆盖。

### Q: 如何处理复杂的自定义按钮？
A: 使用AppButton的插槽功能，或继续使用原生button但使用设计令牌变量。

### Q: 迁移过程中如何保持向后兼容？
A: 可以逐步迁移，新旧样式并存，完成后再移除旧样式。
