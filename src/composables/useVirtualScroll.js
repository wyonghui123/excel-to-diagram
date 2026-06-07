/**
 * 虚拟滚动 composable
 * 
 * 基于 IntersectionObserver + CSS transform 的轻量虚拟滚动
 * 当数据量超过虚拟滚动阈值（默认 100 行）时自动启用
 * 
 * 用法:
 *   const { containerRef, virtualItems, totalHeight, scrollToTop } = useVirtualScroll(data, {
 *     itemHeight: 48,
 *     overscan: 10,
 *     threshold: 100,
 *   })
 */

import { ref, computed, onMounted, onUnmounted, shallowRef, watch } from 'vue'

export function useVirtualScroll(dataSource, options = {}) {
  const {
    itemHeight = 48,
    overscan = 10,
    threshold = 100,
    enabled = null,
  } = options

  const containerRef = ref(null)
  const scrollTop = shallowRef(0)
  const containerHeight = shallowRef(0)

  let observer = null

  const isEnabled = computed(() => {
    if (enabled !== null) return enabled
    return dataSource.value.length > threshold
  })

  const visibleCount = computed(() => {
    if (!isEnabled.value || containerHeight.value <= 0) return 0
    return Math.ceil(containerHeight.value / itemHeight) + overscan * 2
  })

  const startIndex = computed(() => {
    if (!isEnabled.value) return 0
    const raw = Math.floor(scrollTop.value / itemHeight) - overscan
    return Math.max(0, raw)
  })

  const endIndex = computed(() => {
    if (!isEnabled.value) return dataSource.value.length
    return Math.min(startIndex.value + visibleCount.value, dataSource.value.length)
  })

  const virtualItems = computed(() => {
    if (!isEnabled.value) {
      return dataSource.value.map((item, index) => ({ item, index }))
    }
    return dataSource.value.slice(startIndex.value, endIndex.value).map((item, i) => ({
      item,
      index: startIndex.value + i,
    }))
  })

  const totalHeight = computed(() => {
    if (!isEnabled.value) return 0
    return dataSource.value.length * itemHeight
  })

  const offsetY = computed(() => {
    if (!isEnabled.value) return 0
    return startIndex.value * itemHeight
  })

  function handleScroll(event) {
    scrollTop.value = event.target.scrollTop
  }

  function scrollToTop() {
    if (containerRef.value) {
      containerRef.value.scrollTop = 0
    }
  }

  function scrollToIndex(index) {
    if (containerRef.value && isEnabled.value) {
      containerRef.value.scrollTop = index * itemHeight
    }
  }

  onMounted(() => {
    if (containerRef.value) {
      containerRef.value.addEventListener('scroll', handleScroll, { passive: true })
      updateContainerHeight()
    }
    if (window.ResizeObserver) {
      observer = new ResizeObserver(() => {
        updateContainerHeight()
      })
      if (containerRef.value) {
        observer.observe(containerRef.value)
      }
    }
  })

  onUnmounted(() => {
    if (containerRef.value) {
      containerRef.value.removeEventListener('scroll', handleScroll)
    }
    if (observer) {
      observer.disconnect()
      observer = null
    }
  })

  function updateContainerHeight() {
    if (containerRef.value) {
      containerHeight.value = containerRef.value.clientHeight
    }
  }

  watch(() => dataSource.value, () => {
    updateContainerHeight()
  })

  return {
    containerRef,
    virtualItems,
    totalHeight,
    offsetY,
    isEnabled,
    scrollToTop,
    scrollToIndex,
  }
}
