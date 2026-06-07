# 用户指引集成指南

## 1. 快速开始

### 1.1 在工作台集成新手引导

修改 `src/components/ArchWorkspaceNew.vue`：

```vue
<template>
  <div class="arch-workspace">
    <!-- 原有内容 -->
    
    <!-- 添加新手引导组件 -->
    <TourGuide
      ref="tourGuide"
      :steps="WORKSPACE_TOUR_STEPS"
      :auto-start="false"
      @complete="handleTourComplete"
      @close="handleTourClose"
    />
    
    <!-- 添加帮助按钮 -->
    <button class="help-btn" @click="startTour">
      <AppIcon name="help" size="sm" />
    </button>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import TourGuide from './TourGuide.vue'
import { useOnboardingStore } from '@/stores/onboardingStore'
import { WORKSPACE_TOUR_STEPS } from '@/config/tourSteps'

const tourGuide = ref(null)
const onboardingStore = useOnboardingStore()

const startTour = () => {
  tourGuide.value?.start()
}

const handleTourComplete = () => {
  console.log('Tour completed!')
}

const handleTourClose = () => {
  console.log('Tour closed')
}

onMounted(() => {
  onboardingStore.loadFromStorage()
  
  // 首次登录自动显示引导
  if (onboardingStore.shouldShowTour) {
    setTimeout(() => {
      startTour()
    }, 1000)
  }
})
</script>

<style lang="scss" scoped>
.help-btn {
  position: fixed;
  bottom: 24px;
  right: 24px;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: var(--color-primary);
  color: white;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-lg);
  transition: all var(--transition-normal);
  z-index: 100;

  &:hover {
    transform: scale(1.1);
    box-shadow: var(--shadow-xl);
  }
}
</style>
```

### 1.2 在AA图生成页面集成引导

修改 `src/views/AADiagramApp/index.vue`：

```vue
<template>
  <div class="aa-diagram-app">
    <!-- 原有内容 -->
    
    <!-- 添加步骤引导 -->
    <TourGuide
      ref="tourGuide"
      :steps="DIAGRAM_TOUR_STEPS"
      :auto-start="false"
      @complete="handleTourComplete"
    />
    
    <!-- 添加帮助按钮 -->
    <button class="tour-help-btn" @click="startTour">
      <AppIcon name="help" size="sm" />
      <span>操作指引</span>
    </button>
  </div>
</template>

<script>
import TourGuide from '@/components/TourGuide.vue'
import { DIAGRAM_TOUR_STEPS } from '@/config/tourSteps'

export default {
  components: {
    TourGuide
  },
  setup() {
    const tourGuide = ref(null)
    
    const startTour = () => {
      tourGuide.value?.start()
    }
    
    const handleTourComplete = () => {
      // 可以记录用户完成了AA图引导
    }
    
    return {
      tourGuide,
      startTour,
      handleTourComplete,
      DIAGRAM_TOUR_STEPS
    }
  }
}
</script>
```

---

## 2. 功能提示使用

### 2.1 基本用法

```vue
<template>
  <div class="my-component">
    <button class="import-btn">导入数据</button>
    
    <!-- 添加功能提示 -->
    <FeatureHint
      hint-id="arch-import"
      target=".import-btn"
      content="支持从Excel批量导入数据"
      placement="bottom"
      :show-once="true"
    />
  </div>
</template>

<script setup>
import FeatureHint from '@/components/FeatureHint.vue'
</script>
```

### 2.2 条件显示

```vue
<template>
  <div class="data-table">
    <!-- 只在首次访问时显示提示 -->
    <FeatureHint
      v-if="!hasImportedData"
      hint-id="first-import"
      target=".import-btn"
      content="点击这里导入您的第一批数据"
      placement="right"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import FeatureHint from '@/components/FeatureHint.vue'

const hasImportedData = ref(false)
</script>
```

---

## 3. 高级用法

### 3.1 自定义引导步骤

```javascript
// 在组件中动态生成步骤
const customSteps = computed(() => {
  const steps = [...WORKSPACE_TOUR_STEPS]
  
  // 根据用户权限添加额外步骤
  if (userStore.isAdmin) {
    steps.push({
      id: 'admin-settings',
      target: '.admin-panel',
      title: '管理员设置',
      content: '作为管理员，您可以在这里配置系统参数。',
      placement: 'left',
      highlight: true
    })
  }
  
  return steps
})
```

### 3.2 引导完成回调

```vue
<script setup>
import { useOnboardingStore } from '@/stores/onboardingStore'

const onboardingStore = useOnboardingStore()

const handleTourComplete = () => {
  // 记录到分析系统
  analytics.track('tour_completed', {
    tour_type: 'workspace',
    completed_at: new Date().toISOString()
  })
  
  // 显示欢迎消息
  message.success('引导完成！开始探索吧！')
  
  // 可以引导用户到下一步操作
  router.push('/product-version')
}
</script>
```

### 3.3 重置引导状态

```vue
<template>
  <div class="settings-page">
    <h3>用户引导设置</h3>
    
    <button @click="resetAllGuides">
      重置所有引导
    </button>
    
    <button @click="resetHints">
      重置功能提示
    </button>
  </div>
</template>

<script setup>
import { useOnboardingStore } from '@/stores/onboardingStore'
import { useMessage } from '@/composables/useMessage'

const onboardingStore = useOnboardingStore()
const message = useMessage()

const resetAllGuides = () => {
  onboardingStore.resetTour()
  message.success('已重置所有引导，刷新页面后将重新显示')
}

const resetHints = () => {
  onboardingStore.resetAllHints()
  message.success('已重置所有功能提示')
}
</script>
```

---

## 4. 样式自定义

### 4.1 自定义引导主题

```scss
// 在 src/styles/_tour-theme.scss 中定义

.tour-tooltip {
  // 自定义背景色
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  
  // 自定义标题样式
  .tour-title {
    color: white;
    font-size: 18px;
  }
  
  // 自定义内容样式
  .tour-content {
    color: rgba(255, 255, 255, 0.9);
  }
  
  // 自定义按钮样式
  .tour-actions {
    background: rgba(0, 0, 0, 0.2);
  }
}

// 自定义高亮框样式
.tour-highlight {
  border-color: #667eea;
  box-shadow: 0 0 0 9999px rgba(102, 126, 234, 0.3),
              0 0 20px rgba(102, 126, 234, 0.5);
}
```

### 4.2 响应式适配

```scss
// 移动端适配
@include respond-to('sm') {
  .tour-tooltip {
    width: 280px;
    font-size: 14px;
  }
  
  .tour-highlight {
    // 移动端使用更明显的边框
    border-width: 3px;
  }
}
```

---

## 5. 测试

### 5.1 单元测试

```javascript
// src/components/__tests__/TourGuide.spec.js

import { mount } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import TourGuide from '../TourGuide.vue'
import { WORKSPACE_TOUR_STEPS } from '@/config/tourSteps'

describe('TourGuide', () => {
  it('should render with steps', () => {
    const wrapper = mount(TourGuide, {
      props: {
        steps: WORKSPACE_TOUR_STEPS
      }
    })
    
    expect(wrapper.find('.tour-overlay').exists()).toBe(false)
  })
  
  it('should show tour when start() is called', async () => {
    const wrapper = mount(TourGuide, {
      props: {
        steps: WORKSPACE_TOUR_STEPS
      }
    })
    
    await wrapper.vm.start()
    
    expect(wrapper.find('.tour-overlay').exists()).toBe(true)
  })
  
  it('should emit complete event when tour finishes', async () => {
    const wrapper = mount(TourGuide, {
      props: {
        steps: [{ id: 'test', title: 'Test', content: 'Test' }]
      }
    })
    
    await wrapper.vm.start()
    await wrapper.vm.handleComplete()
    
    expect(wrapper.emitted('complete')).toBeTruthy()
  })
})
```

---

## 6. 最佳实践

### 6.1 引导设计原则

1. **简洁明了**：每个步骤只介绍一个功能点
2. **循序渐进**：按照用户操作流程设计步骤顺序
3. **可跳过**：允许用户随时跳过引导
4. **可重播**：提供入口让用户重新查看引导

### 6.2 功能提示原则

1. **及时性**：在用户需要时显示，不要过早打扰
2. **相关性**：提示内容与当前操作相关
3. **可关闭**：用户可以轻松关闭提示
4. **可禁用**：提供"不再提示"选项

### 6.3 数据埋点

```javascript
// 记录引导相关事件
const trackTourEvent = (eventName, data = {}) => {
  analytics.track(eventName, {
    ...data,
    timestamp: new Date().toISOString(),
    userId: userStore.userId
  })
}

// 使用示例
trackTourEvent('tour_started', { tour_type: 'workspace' })
trackTourEvent('tour_step_viewed', { step_id: 'apps-section', step_index: 1 })
trackTourEvent('tour_completed', { tour_type: 'workspace' })
trackTourEvent('tour_skipped', { tour_type: 'workspace', last_step: 2 })
```

---

## 7. 常见问题

### Q1: 如何在特定条件下显示引导？

```javascript
// 只在首次访问某个页面时显示
onMounted(() => {
  const hasVisitedPage = localStorage.getItem('visited_diagram_page')
  
  if (!hasVisitedPage) {
    tourGuide.value?.start()
    localStorage.setItem('visited_diagram_page', 'true')
  }
})
```

### Q2: 如何处理动态内容？

```vue
<template>
  <TourGuide
    :steps="dynamicSteps"
    @step-change="handleStepChange"
  />
</template>

<script setup>
const dynamicSteps = ref([])

// 等待内容加载完成后设置步骤
watch(dataLoaded, (loaded) => {
  if (loaded) {
    dynamicSteps.value = generateStepsFromData(data.value)
  }
})
</script>
```

### Q3: 如何实现多语言支持？

```javascript
// src/config/tourSteps.js
import { useI18n } from 'vue-i18n'

export const getWorkspaceTourSteps = () => {
  const { t } = useI18n()
  
  return [
    {
      id: 'welcome',
      title: t('tour.welcome.title'),
      content: t('tour.welcome.content'),
      placement: 'center'
    },
    // ...
  ]
}
```

---

*文档版本: 1.0*
*最后更新: 2026-04-30*
