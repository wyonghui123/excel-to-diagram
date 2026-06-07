import { ref } from 'vue'

export function useRefreshCoordinator() {
  const callbacks = new Map()
  const isRefreshing = ref(false)

  function register(key, fn) {
    callbacks.set(key, fn)
  }

  function unregister(key) {
    callbacks.delete(key)
  }

  async function refreshAll() {
    if (callbacks.size === 0) return
    isRefreshing.value = true
    const entries = Array.from(callbacks.entries())
    for (const [key, fn] of entries) {
      try {
        await fn()
      } catch (e) {
        console.error(`[coordinator] refresh failed for "${key}":`, e)
      }
    }
    isRefreshing.value = false
  }

  return { register, unregister, refreshAll, isRefreshing }
}
