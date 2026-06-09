## 目录

1. [概述](#概述)
2. [性能目标](#性能目标)
3. [优化策略](#优化策略)
4. [性能检查清单](#性能检查清单)
5. [性能测试工具](#性能测试工具)
6. [性能基准](#性能基准)
7. [持续优化建议](#持续优化建议)

---
# 前端性能优化指南

## 概述

本文档提供管理维度权限配置系统的前端性能优化策略，目标是实现界面响应时间 < 200ms。

## 性能目标

- **首次加载时间**: < 2s
- **交互响应时间**: < 200ms
- **列表渲染时间**: < 500ms (1000 条数据)
- **内存占用**: < 100MB

## 优化策略

### 1. 组件懒加载

#### 1.1 路由级懒加载

```javascript
// router/index.js
const routes = [
  {
    path: '/management-dimensions',
    component: () => import('@/views/ManagementDimensions/index.vue'),
    meta: { preload: false }
  },
  {
    path: '/permission-rules',
    component: () => import('@/views/PermissionRules/index.vue'),
    meta: { preload: false }
  }
]
```

#### 1.2 组件级懒加载

```vue
<template>
  <div>
    <button @click="showDialog = true">配置权限</button>
    <Suspense v-if="showDialog">
      <template #default>
        <PermissionDialog />
      </template>
      <template #fallback>
        <LoadingSpinner />
      </template>
    </Suspense>
  </div>
</template>

<script setup>
import { defineAsyncComponent, ref } from 'vue'

const PermissionDialog = defineAsyncComponent(() =>
  import('@/components/PermissionDialog.vue')
)

const showDialog = ref(false)
</script>
```

### 2. 虚拟滚动优化

#### 2.1 大数据列表虚拟滚动

```vue
<template>
  <div class="virtual-list-container">
    <VirtualList
      :items="dimensionInstances"
      :item-size="48"
      :buffer="10"
      @scroll-end="loadMore"
    >
      <template #default="{ item }">
        <DimensionInstanceItem :item="item" />
      </template>
    </VirtualList>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import VirtualList from '@/components/common/VirtualList'

const dimensionInstances = ref([])
const pageSize = 50
const currentPage = ref(1)

const loadMore = async () => {
  const data = await fetchInstances(currentPage.value++, pageSize.value)
  dimensionInstances.value.push(...data)
}
</script>
```

#### 2.2 树形结构虚拟滚动

```vue
<template>
  <div class="tree-container">
    <VirtualTree
      :data="treeData"
      :node-height="32"
      :expanded-keys="expandedKeys"
    >
      <template #node="{ node }">
        <TreeNode :node="node" @toggle="toggleNode" />
      </template>
    </VirtualTree>
  </div>
</template>
```

### 3. 数据缓存策略

#### 3.1 API 响应缓存

```javascript
// composables/useDimensionCache.js
import { ref, computed } from 'vue'

const cache = new Map()
const CACHE_TTL = 5 * 60 * 1000 // 5分钟

export function useDimensionCache() {
  const getCacheKey = (dimensionId, params) => {
    return `${dimensionId}:${JSON.stringify(params)}`
  }

  const getCachedData = (key) => {
    const cached = cache.get(key)
    if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
      return cached.data
    }
    cache.delete(key)
    return null
  }

  const setCacheData = (key, data) => {
    cache.set(key, {
      data,
      timestamp: Date.now()
    })
  }

  const fetchWithCache = async (fetcher, dimensionId, params) => {
    const key = getCacheKey(dimensionId, params)
    
    // 先查缓存
    const cached = getCachedData(key)
    if (cached) {
      return cached
    }
    
    // 缓存未命中，发起请求
    const data = await fetcher(dimensionId, params)
    setCacheData(key, data)
    return data
  }

  return {
    fetchWithCache,
    getCachedData,
    setCacheData
  }
}
```

#### 3.2 组件状态缓存

```vue
<script setup>
import { ref, onActivated, onDeactivated } from 'vue'

const scrollPosition = ref(0)
const filterState = ref({})

// 组件激活时恢复状态
onActivated(() => {
  window.scrollTo(0, scrollPosition.value)
})

// 组件停用时保存状态
onDeactivated(() => {
  scrollPosition.value = window.scrollY
})
</script>
```

### 4. 防抖和节流

#### 4.1 搜索输入防抖

```vue
<template>
  <input
    v-model="searchQuery"
    @input="handleSearchDebounced"
    placeholder="搜索维度实例..."
  />
</template>

<script setup>
import { ref } from 'vue'
import { useDebounceFn } from '@vueuse/core'

const searchQuery = ref('')

const handleSearch = async (query) => {
  // 执行搜索
  const results = await searchInstances(query)
  // 更新结果
}

const handleSearchDebounced = useDebounceFn(handleSearch, 300)
</script>
```

#### 4.2 滚动事件节流

```vue
<script setup>
import { useThrottleFn } from '@vueuse/core'

const handleScroll = useThrottleFn(() => {
  // 处理滚动
}, 100)
</script>
```

### 5. 请求优化

#### 5.1 批量请求合并

```javascript
// services/batchRequest.js
class BatchRequestManager {
  constructor() {
    this.queue = []
    this.timer = null
  }

  add(request) {
    return new Promise((resolve, reject) => {
      this.queue.push({ request, resolve, reject })
      
      if (!this.timer) {
        this.timer = setTimeout(() => this.flush(), 50)
      }
    })
  }

  async flush() {
    const batch = this.queue.splice(0, this.queue.length)
    this.timer = null
    
    if (batch.length === 0) return
    
    try {
      const results = await this.executeBatch(batch.map(b => b.request))
      batch.forEach((item, index) => {
        item.resolve(results[index])
      })
    } catch (error) {
      batch.forEach(item => item.reject(error))
    }
  }

  async executeBatch(requests) {
    // 执行批量请求
    const response = await fetch('/api/v1/batch', {
      method: 'POST',
      body: JSON.stringify({ requests })
    })
    return response.json()
  }
}

export const batchManager = new BatchRequestManager()
```

#### 5.2 请求取消

```javascript
// composables/useCancellableRequest.js
import { ref, onUnmounted } from 'vue'

export function useCancellableRequest() {
  const abortController = ref(null)

  const fetch = async (url, options = {}) => {
    // 取消之前的请求
    if (abortController.value) {
      abortController.value.abort()
    }

    // 创建新的 AbortController
    abortController.value = new AbortController()

    try {
      const response = await fetch(url, {
        ...options,
        signal: abortController.value.signal
      })
      return response.json()
    } catch (error) {
      if (error.name === 'AbortError') {
        console.log('请求已取消')
      } else {
        throw error
      }
    }
  }

  // 组件卸载时取消所有请求
  onUnmounted(() => {
    if (abortController.value) {
      abortController.value.abort()
    }
  })

  return { fetch }
}
```

### 6. 渲染优化

#### 6.1 使用 v-memo 优化列表渲染

```vue
<template>
  <div v-for="item in items" :key="item.id" v-memo="[item.id, item.status]">
    <ItemComponent :item="item" />
  </div>
</template>
```

#### 6.2 计算属性缓存

```vue
<script setup>
import { computed } from 'vue'

const props = defineProps(['items'])

// 使用计算属性缓存结果
const filteredItems = computed(() => {
  return props.items.filter(item => item.active)
})

const sortedItems = computed(() => {
  return [...filteredItems.value].sort((a, b) => a.name.localeCompare(b.name))
})
</script>
```

### 7. 资源优化

#### 7.1 图片懒加载

```vue
<template>
  <img
    v-lazy="imageUrl"
    :alt="alt"
    class="lazy-image"
  />
</template>

<script setup>
import { directive as vLazy } from 'vue3-lazy'

const imageUrl = ref('path/to/image.jpg')
</script>
```

#### 7.2 字体优化

```css
/* 使用 font-display: swap 避免字体加载阻塞 */
@font-face {
  font-family: 'CustomFont';
  src: url('/fonts/custom.woff2') format('woff2');
  font-display: swap;
}
```

### 8. 性能监控

#### 8.1 性能指标收集

```javascript
// utils/performance.js
export function measurePerformance(name, fn) {
  const start = performance.now()
  const result = fn()
  const end = performance.now()
  
  console.log(`${name} 耗时: ${(end - start).toFixed(2)}ms`)
  
  // 上报性能数据
  if (end - start > 200) {
    reportSlowOperation(name, end - start)
  }
  
  return result
}

export function measureAsyncPerformance(name, fn) {
  return async (...args) => {
    const start = performance.now()
    const result = await fn(...args)
    const end = performance.now()
    
    console.log(`${name} 耗时: ${(end - start).toFixed(2)}ms`)
    
    if (end - start > 200) {
      reportSlowOperation(name, end - start)
    }
    
    return result
  }
}
```

#### 8.2 组件性能追踪

```vue
<script setup>
import { onMounted, onUpdated } from 'vue'

const componentName = 'DimensionList'

onMounted(() => {
  performance.mark(`${componentName}-mount-start`)
})

onUpdated(() => {
  performance.mark(`${componentName}-update-start`)
})
</script>
```

## 性能检查清单

### 启动性能
- [ ] 路由懒加载已配置
- [ ] 第三方库按需引入
- [ ] 首屏资源已压缩
- [ ] 关键 CSS 内联

### 运行时性能
- [ ] 大列表使用虚拟滚动
- [ ] 防抖节流已应用
- [ ] 计算属性合理使用
- [ ] 避免不必要的响应式数据

### 网络性能
- [ ] API 响应已缓存
- [ ] 请求已合并
- [ ] 图片已懒加载
- [ ] 静态资源已 CDN 加速

### 内存性能
- [ ] 组件卸载时清理定时器
- [ ] 取消未完成的请求
- [ ] 避免内存泄漏
- [ ] 大对象及时释放

## 性能测试工具

### 1. Chrome DevTools
- Performance 面板：分析运行时性能
- Network 面板：分析网络请求
- Memory 面板：分析内存使用

### 2. Lighthouse
```bash
lighthouse http://localhost:5000 --view
```

### 3. Vue DevTools
- 组件树分析
- 性能追踪
- 状态检查

## 性能基准

| 指标 | 目标值 | 测量方法 |
|------|--------|----------|
| 首次内容绘制 (FCP) | < 1.5s | Lighthouse |
| 最大内容绘制 (LCP) | < 2.5s | Lighthouse |
| 首次输入延迟 (FID) | < 100ms | Lighthouse |
| 累积布局偏移 (CLS) | < 0.1 | Lighthouse |
| 交互响应时间 | < 200ms | Performance API |
| 列表渲染时间 | < 500ms | Performance API |

## 持续优化建议

1. **定期性能审计**: 每月使用 Lighthouse 进行性能审计
2. **监控慢操作**: 收集并分析用户端的慢操作日志
3. **优化热点路径**: 重点关注高频使用的功能
4. **技术债务清理**: 定期重构性能瓶颈代码
5. **性能预算**: 设定性能预算，超出时告警
