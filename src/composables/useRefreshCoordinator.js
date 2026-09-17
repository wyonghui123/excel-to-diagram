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
    // [perf-2026-06-30] 并行刷新: 原串行 await N 个回调, 总时 ≈ Σ(每个).
    //   并行后总时 ≈ max(每个). OSS 勾选场景 5 list + scopeTree 串行 ~3s → 并行 ~1s.
    //   行为等价: 所有回调仍被执行, 失败项 catch 不影响其他 (与原 try-catch 等价).
    //   回调间无依赖 (list:${objectType} 和 scopeTree 独立刷新), 并行安全.
    //   Spec (docs/specs/spec-unified-refresh-protocol.md FR-002) 设计意图为
    //   "所有回调被执行 + 失败项静默 catch", 并行不违反此意图.
    const promises = entries.map(([key, fn]) =>
      fn().catch(e => console.error(`[coordinator] refresh failed for "${key}":`, e))
    )
    await Promise.all(promises)
    isRefreshing.value = false
  }

  return { register, unregister, refreshAll, isRefreshing }
}
