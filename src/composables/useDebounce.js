/**
 * 统一防抖/节流工具
 * 
 * 替代项目中分散的 setTimeout 防抖实现
 */

import { ref, onUnmounted } from 'vue'

/**
 * 创建一个防抖函数
 * @param {Function} fn - 要防抖的函数
 * @param {number} delay - 防抖延迟（毫秒），默认 300ms
 * @returns {{ debouncedFn: Function, cancel: Function, isPending: Ref<boolean> }}
 */
export function useDebounce(fn, delay = 300) {
  let timer = null
  const isPending = ref(false)

  function debouncedFn(...args) {
    if (timer) {
      clearTimeout(timer)
    }
    isPending.value = true
    timer = setTimeout(() => {
      isPending.value = false
      fn(...args)
    }, delay)
  }

  function cancel() {
    if (timer) {
      clearTimeout(timer)
      timer = null
      isPending.value = false
    }
  }

  onUnmounted(() => {
    cancel()
  })

  return { debouncedFn, cancel, isPending }
}

/**
 * 创建一个节流函数
 * @param {Function} fn - 要节流的函数
 * @param {number} interval - 节流间隔（毫秒），默认 300ms
 * @returns {{ throttledFn: Function, cancel: Function }}
 */
export function useThrottle(fn, interval = 300) {
  let lastTime = 0
  let timer = null

  function throttledFn(...args) {
    const now = Date.now()
    if (now - lastTime >= interval) {
      lastTime = now
      fn(...args)
    } else {
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => {
        lastTime = Date.now()
        fn(...args)
      }, interval - (now - lastTime))
    }
  }

  function cancel() {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
  }

  onUnmounted(() => {
    cancel()
  })

  return { throttledFn, cancel }
}
