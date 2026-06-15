/**
 * chartArchDataStore (v32)
 *
 * 架构数据图表 (chart tab) 的"数据注入入口" Pinia store
 *
 * 解决问题:
 *   v30/v31 之前用 sessionStorage + module-level cache 在 management → chart
 *   切换间传递 archData, 出现两个问题:
 *     1) sessionStorage 在 onNavPrev 时被清, 同会话内"返回管理页→再点 chart tab"
 *        chart 组件 re-mount, 拿不到数据
 *     2) 用 module cache 兜底后, 用户在管理页改选择并点击 图表视图, cache 还是旧的
 *        旧数据, 必须手动清理才能更新
 *
 * 重新设计 (v32 - "图表视图" = 显式数据更新入口):
 *   - 架构管理页 (MultiObjectManagementPage) 的 "图表视图" 按钮:
 *       chartStore.setArchData(chartData)   // 写入最新数据
 *       tabStore.openTab / switchTab(...)   // 切到 chart tab (单例)
 *       router.push('/archdata-chart')      // 路由导航
 *   - 架构数据图表页 (AADiagramApp) onMounted:
 *       archData = chartStore.archData       // 从 store 读
 *       if (archData) initDataFromArch(archData)
 *   - 用户手动点 chart tab (不经过 图表视图):
 *       拿到的就是 chartStore.archData 里的旧数据 (这是可接受的 trade-off,
 *       用户已确认)
 *   - F5 刷新 / 关闭浏览器 / 直接 URL 访问 /archdata-chart:
 *       chartStore 是 Pinia (内存变量, 不持久化), 拿不到数据
 *       走 6 步骤默认流程
 *
 * 不持久化 (in-memory only):
 *   - 关闭浏览器 → 状态全清 (符合预期, 下次需要重新走 图表视图)
 *   - F5 刷新 → Pinia store 重置, chart tab 走 6 步骤 (符合预期)
 *
 * @since 2026-06-11
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

// [2026-06-15] 缓存版本号
//  schema 变化时递增, 旧版本缓存自动失效 (防止读取过期数据结构导致崩溃)
const CACHE_VERSION = 1

// [2026-06-15] 缓存过期时间 (毫秒)
//  30 分钟: 平衡"用户切走 30 分钟内回来"和"防止陈旧数据"
//  - 太短: 用户切走喝杯水回来要重新生成
//  - 太长: archData 改了/范围变了还看到旧图
const CACHE_TTL_MS = 30 * 60 * 1000

export const useChartArchDataStore = defineStore('chartArchData', () => {
  // 上一次 "图表视图" 注入的 archData (handleGlobalAction('chart') 的返回值)
  const archData = ref<any | null>(null)

  // 最后更新时间 (毫秒时间戳) - 调试用
  const lastUpdatedAt = ref<number>(0)

  // 写入计数器 - 每次 setArchData 自增, 监听者可用此触发 watch
  const sequence = ref<number>(0)

  // [2026-06-15] diagramData 缓存
  //   解决问题: 切 tab 回来时 diagramData 丢失, 显示"图表尚未生成"
  //   - diagramData: 缓存的图表数据
  //   - diagramConfigHash: 配置/范围 hash, 不匹配则缓存失效
  //   - diagramCachedAt: 写入时间, 用于 TTL 检查
  //   - diagramCacheVersion: 缓存版本, schema 升级时清空旧版本
  const diagramData = ref<any | null>(null)
  const diagramConfigHash = ref<string>('')
  const diagramCachedAt = ref<number>(0)
  const diagramCacheVersion = ref<number>(CACHE_VERSION)

  function setArchData(data: any) {
    archData.value = data
    lastUpdatedAt.value = Date.now()
    sequence.value++
    // [2026-06-15] archData 变化 → 范围/对象集合变了 → 缓存的 diagramData 不再有效
    //  触发场景:
    //   - 用户在架构管理页改了 BO/关系选择 → 点 图表视图
    //   - 旧缓存的 diagramData 用了旧范围, 必须清空
    clearDiagramCache()
  }

  function clear() {
    archData.value = null
    lastUpdatedAt.value = 0
    sequence.value = 0
    clearDiagramCache()
  }

  /**
   * [2026-06-15] 写入 diagramData 缓存
   * @param data 图表数据
   * @param configHash 当前配置/范围 hash (从 useDiagramData.computeConfigHash() 算)
   */
  function setDiagramCache(data: any, configHash: string) {
    diagramData.value = data
    diagramConfigHash.value = configHash
    diagramCachedAt.value = Date.now()
    diagramCacheVersion.value = CACHE_VERSION
  }

  /**
   * [2026-06-15] 读取 diagramData 缓存
   * @param configHash 当前配置/范围 hash
   * @returns 命中返回 data, 未命中返回 null
   *
   * 未命中场景:
   *   1) 无缓存 (从未 generate 过 / F5 后 Pinia 重置 / clearDiagramCache)
   *   2) 版本不匹配 (schema 升级)
   *   3) configHash 不匹配 (用户改了 colorScheme / centerScope / chartType 等)
   *   4) 超过 TTL (30 分钟)
   */
  function getDiagramCache(configHash: string): any | null {
    // 1) 版本不匹配 → 清空 + 返回 null
    if (diagramCacheVersion.value !== CACHE_VERSION) {
      clearDiagramCache()
      return null
    }
    // 2) 无缓存
    if (!diagramData.value) return null
    // 3) configHash 不匹配 → 范围/配置变了, 缓存失效
    if (diagramConfigHash.value !== configHash) {
      clearDiagramCache()
      return null
    }
    // 4) 过期 (TTL)
    if (Date.now() - diagramCachedAt.value > CACHE_TTL_MS) {
      clearDiagramCache()
      return null
    }
    return diagramData.value
  }

  function clearDiagramCache() {
    diagramData.value = null
    diagramConfigHash.value = ''
    diagramCachedAt.value = 0
  }

  return {
    archData,
    lastUpdatedAt,
    sequence,
    setArchData,
    clear,

    // [2026-06-15] diagramData 缓存
    diagramData,
    diagramConfigHash,
    diagramCachedAt,
    diagramCacheVersion,
    setDiagramCache,
    getDiagramCache,
    clearDiagramCache
  }
})

export default useChartArchDataStore
