# 交互式用户指引设计方案

## 1. 方案概述

本方案为BIP应用架构管理系统设计交互式用户指引，帮助新用户快速了解系统功能，提升用户体验。

### 1.1 设计目标

- **降低学习成本**：新用户能在3分钟内了解系统核心功能
- **提升使用效率**：通过引导帮助用户快速完成首次操作
- **减少支持成本**：通过自助式引导减少用户咨询

### 1.2 方案组合

| 方案 | 触发时机 | 目标用户 | 实现方式 |
|------|---------|---------|---------|
| 新手引导 | 首次登录 | 新用户 | 分步骤高亮引导 |
| 功能提示 | 首次使用某功能 | 所有用户 | 气泡提示 |
| 帮助中心 | 用户主动查看 | 所有用户 | 可搜索文档 |

---

## 2. 新手引导设计

### 2.1 引导流程

```
步骤1: 欢迎页面
    ↓
步骤2: 介绍工作台（高亮应用模块区域）
    ↓
步骤3: 介绍产品版本管理
    ↓
步骤4: 介绍架构数据管理
    ↓
步骤5: 介绍AA图生成
    ↓
步骤6: 引导开始使用
```

### 2.2 引导步骤配置

```javascript
// src/config/tourSteps.js

export const WORKSPACE_TOUR_STEPS = [
  {
    id: 'welcome',
    title: '欢迎使用 BIP 应用架构管理系统',
    content: '这是一个帮助您管理产品架构、业务对象和生成关系图的工具。让我们花1分钟了解主要功能。',
    placement: 'center',
    beforeShow: () => {
      // 显示欢迎遮罩
    }
  },
  {
    id: 'apps-section',
    target: '.apps-tiles',
    title: '快捷应用区',
    content: '这里列出了系统的四个核心功能模块，点击即可进入对应功能。',
    placement: 'bottom',
    highlight: true
  },
  {
    id: 'product-version',
    target: '.app-tile:nth-child(1)',
    title: '产品版本管理',
    content: '管理您的产品线和版本信息。在这里可以创建产品、添加版本、查看版本历史。',
    placement: 'right',
    highlight: true
  },
  {
    id: 'arch-data',
    target: '.app-tile:nth-child(2)',
    title: '架构数据管理',
    content: '管理领域、子领域、服务模块和业务对象。这是系统的核心数据管理模块。',
    placement: 'right',
    highlight: true
  },
  {
    id: 'aa-diagram',
    target: '.app-tile:nth-child(3)',
    title: 'AA图生成',
    content: '通过向导式步骤，从Excel文件生成业务对象关系图。支持多种图表类型和布局方式。',
    placement: 'right',
    highlight: true
  },
  {
    id: 'frequent-products',
    target: '.frequent-products-section',
    title: '常用产品',
    content: '这里显示您最近访问的产品版本，方便快速进入工作。',
    placement: 'top',
    highlight: true
  },
  {
    id: 'get-started',
    title: '准备就绪！',
    content: '您已经了解了系统的基本功能。建议从"产品版本管理"开始，创建您的第一个产品。',
    placement: 'center',
    buttons: [
      { text: '稍后探索', action: 'close' },
      { text: '开始使用', action: 'start', primary: true }
    ]
  }
]
```

### 2.3 AA图生成引导步骤

```javascript
// src/config/tourSteps.js

export const DIAGRAM_TOUR_STEPS = [
  {
    id: 'step-upload',
    target: '.step-navigator',
    title: '步骤导航',
    content: 'AA图生成分为6个步骤：导入、中心、关系、类型、配置、展示。当前在第一步。',
    placement: 'bottom'
  },
  {
    id: 'upload-file',
    target: '.file-upload-area',
    title: '上传Excel文件',
    content: '点击或拖拽Excel文件到此处。支持.xlsx、.xls和.csv格式。',
    placement: 'right',
    highlight: true
  },
  {
    id: 'step-center',
    target: '.step-item:nth-child(2)',
    title: '选择中心范围',
    content: '上传后，选择要在图表中心显示的业务对象。',
    placement: 'bottom'
  },
  {
    id: 'step-relation',
    target: '.step-item:nth-child(3)',
    title: '选择关系范围',
    content: '选择要显示的对象关系类型和范围。',
    placement: 'bottom'
  },
  {
    id: 'step-type',
    target: '.step-item:nth-child(4)',
    title: '选择图表类型',
    content: '选择业务对象图或服务模块图。',
    placement: 'bottom'
  },
  {
    id: 'step-config',
    target: '.step-item:nth-child(5)',
    title: '配置图表参数',
    content: '设置布局方式、颜色分组、标签显示等参数。',
    placement: 'bottom'
  },
  {
    id: 'step-display',
    target: '.step-item:nth-child(6)',
    title: '查看关系图',
    content: '生成并查看最终的关系图，支持导出为PNG图片。',
    placement: 'bottom'
  }
]
```

---

## 3. 功能提示设计

### 3.1 提示配置

```javascript
// src/config/hints.js

export const FEATURE_HINTS = {
  // 产品版本管理提示
  'product-create': {
    target: '.create-product-btn',
    content: '点击这里创建您的第一个产品',
    placement: 'right',
    showOnce: true
  },
  
  // 架构数据管理提示
  'arch-tree-nav': {
    target: '.tree-navigator',
    content: '使用左侧树形导航快速定位到不同层级的架构数据',
    placement: 'right',
    showOnce: true
  },
  
  'arch-filter': {
    target: '.dynamic-filter',
    content: '使用筛选器快速过滤数据',
    placement: 'bottom',
    showOnce: true
  },
  
  'arch-import': {
    target: '.import-btn',
    content: '支持从Excel批量导入数据',
    placement: 'bottom',
    showOnce: true
  },
  
  // AA图生成提示
  'diagram-preset': {
    target: '.preset-selector',
    content: '保存常用的范围配置，下次快速加载',
    placement: 'bottom',
    showOnce: true
  },
  
  'diagram-layout': {
    target: '.layout-selector',
    content: '选择不同的布局算法：ELK适合复杂图，Dagre适合简单图',
    placement: 'left',
    showOnce: true
  }
}
```

### 3.2 提示显示逻辑

```javascript
// src/composables/useFeatureHint.js

import { ref, onMounted } from 'vue'

const HINT_STORAGE_KEY = 'bip_shown_hints'

export function useFeatureHint() {
  const shownHints = ref(new Set())
  
  const loadShownHints = () => {
    try {
      const stored = localStorage.getItem(HINT_STORAGE_KEY)
      if (stored) {
        shownHints.value = new Set(JSON.parse(stored))
      }
    } catch (e) {
      console.error('Failed to load shown hints:', e)
    }
  }
  
  const saveShownHints = () => {
    try {
      localStorage.setItem(HINT_STORAGE_KEY, JSON.stringify([...shownHints.value]))
    } catch (e) {
      console.error('Failed to save shown hints:', e)
    }
  }
  
  const shouldShowHint = (hintId) => {
    return !shownHints.value.has(hintId)
  }
  
  const markHintAsShown = (hintId) => {
    shownHints.value.add(hintId)
    saveShownHints()
  }
  
  const resetAllHints = () => {
    shownHints.value.clear()
    localStorage.removeItem(HINT_STORAGE_KEY)
  }
  
  onMounted(() => {
    loadShownHints()
  })
  
  return {
    shouldShowHint,
    markHintAsShown,
    resetAllHints
  }
}
```

---

## 4. 帮助中心设计

### 4.1 帮助文档结构

```
docs/
├── help/
│   ├── index.md              # 帮助中心首页
│   ├── getting-started/      # 快速开始
│   │   ├── overview.md       # 系统概述
│   │   ├── first-product.md  # 创建第一个产品
│   │   └── first-diagram.md  # 生成第一个图表
│   ├── features/             # 功能说明
│   │   ├── product-version.md
│   │   ├── arch-data.md
│   │   └── aa-diagram.md
│   ├── tutorials/            # 教程
│   │   ├── import-excel.md
│   │   ├── manage-objects.md
│   │   └── export-diagram.md
│   └── faq/                  # 常见问题
│       └── index.md
```

### 4.2 帮助中心组件

```vue
<!-- src/components/HelpCenter.vue -->

<template>
  <div class="help-center">
    <div class="help-header">
      <AppInput
        v-model="searchQuery"
        placeholder="搜索帮助文档..."
        @input="handleSearch"
      />
    </div>
    
    <div class="help-content">
      <nav class="help-nav">
        <div
          v-for="category in categories"
          :key="category.id"
          class="nav-category"
        >
          <h4>{{ category.title }}</h4>
          <ul>
            <li
              v-for="item in category.items"
              :key="item.id"
              :class="{ active: currentItem === item.id }"
              @click="selectItem(item)"
            >
              {{ item.title }}
            </li>
          </ul>
        </div>
      </nav>
      
      <main class="help-article">
        <article v-html="currentContent" />
      </main>
    </div>
  </div>
</template>
```

---

## 5. 用户状态管理

### 5.1 用户引导状态

```javascript
// src/stores/onboardingStore.js

import { defineStore } from 'pinia'

export const useOnboardingStore = defineStore('onboarding', {
  state: () => ({
    // 是否已完成新手引导
    hasCompletedTour: false,
    
    // 当前引导步骤
    currentTourStep: 0,
    
    // 已显示的功能提示
    shownHints: new Set(),
    
    // 是否跳过引导
    skippedTour: false,
    
    // 引导完成时间
    tourCompletedAt: null
  }),
  
  getters: {
    shouldShowTour: (state) => {
      return !state.hasCompletedTour && !state.skippedTour
    }
  },
  
  actions: {
    completeTour() {
      this.hasCompletedTour = true
      this.tourCompletedAt = new Date().toISOString()
      this.saveToStorage()
    },
    
    skipTour() {
      this.skippedTour = true
      this.saveToStorage()
    },
    
    resetTour() {
      this.hasCompletedTour = false
      this.skippedTour = false
      this.currentTourStep = 0
      this.tourCompletedAt = null
      this.saveToStorage()
    },
    
    markHintShown(hintId) {
      this.shownHints.add(hintId)
      this.saveToStorage()
    },
    
    saveToStorage() {
      const data = {
        hasCompletedTour: this.hasCompletedTour,
        skippedTour: this.skippedTour,
        shownHints: [...this.shownHints],
        tourCompletedAt: this.tourCompletedAt
      }
      localStorage.setItem('bip_onboarding', JSON.stringify(data))
    },
    
    loadFromStorage() {
      try {
        const stored = localStorage.getItem('bip_onboarding')
        if (stored) {
          const data = JSON.parse(stored)
          this.hasCompletedTour = data.hasCompletedTour || false
          this.skippedTour = data.skippedTour || false
          this.shownHints = new Set(data.shownHints || [])
          this.tourCompletedAt = data.tourCompletedAt
        }
      } catch (e) {
        console.error('Failed to load onboarding state:', e)
      }
    }
  }
})
```

---

## 6. 实现步骤

### 6.1 第一阶段：基础框架

1. 创建引导组件 `TourGuide.vue`
2. 实现步骤配置系统
3. 集成到工作台页面

### 6.2 第二阶段：功能提示

1. 创建提示组件 `FeatureHint.vue`
2. 实现提示显示逻辑
3. 在各功能模块添加提示

### 6.3 第三阶段：帮助中心

1. 创建帮助中心页面
2. 编写帮助文档
3. 实现搜索功能

---

## 7. 效果预览

### 7.1 新手引导效果

```
┌─────────────────────────────────────────────────────────────┐
│  ┌─────────────────────────────────────────────────────┐    │
│  │           欢迎使用 BIP 应用架构管理系统               │    │
│  │                                                     │    │
│  │  这是一个帮助您管理产品架构、业务对象和生成关系图    │    │
│  │  的工具。让我们花1分钟了解主要功能。                 │    │
│  │                                                     │    │
│  │         [跳过]              [开始引导 →]            │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ████████████████████████████████████████████████████████   │
│  █                                                        █  │
│  █  [产品版本管理]  [架构数据管理]  [AA图生成]  [系统配置] █  │
│  █                                                        █  │
│  ████████████████████████████████████████████████████████   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 功能提示效果

```
┌─────────────────────────────────────────┐
│  架构数据管理                           │
│  ┌─────────────────────────────────┐    │
│  │ 树形导航                        │    │
│  │                                 │ ◀──┌─────────────────┐
│  │ ▼ 产品A                         │    │ 使用左侧树形导航 │
│  │   ▼ 领域1                       │    │ 快速定位到不同   │
│  │     子领域1                     │    │ 层级的架构数据   │
│  │     子领域2                     │    │                 │
│  │   ▶ 领域2                       │    │ [知道了] [不再提示]│
│  │                                 │    └─────────────────┘
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

---

## 8. 技术选型建议

### 8.1 推荐方案

| 需求 | 推荐方案 | 理由 |
|------|---------|------|
| 新手引导 | 自定义实现 | 更灵活，可完全控制样式和交互 |
| 功能提示 | 自定义实现 | 轻量级，易于集成 |
| 帮助中心 | VuePress / VitePress | 文档化管理，支持搜索 |

### 8.2 可选方案

| 方案 | 优点 | 缺点 |
|------|------|------|
| vue-tour | 成熟稳定，开箱即用 | 样式定制受限 |
| driver.js | 轻量级，功能强大 | 需要额外适配Vue |
| shepherd.js | 功能丰富，可访问性好 | 体积较大 |

---

## 9. 后续优化

1. **数据驱动引导**：根据用户行为数据优化引导流程
2. **视频教程**：为复杂功能添加视频教程
3. **AI助手**：集成AI助手，提供智能问答
4. **反馈收集**：收集用户对引导的反馈，持续改进

---

*文档版本: 1.0*
*最后更新: 2026-04-30*
