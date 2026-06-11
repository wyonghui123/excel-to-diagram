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

export const useChartArchDataStore = defineStore('chartArchData', () => {
  // 上一次 "图表视图" 注入的 archData (handleGlobalAction('chart') 的返回值)
  const archData = ref<any | null>(null)

  // 最后更新时间 (毫秒时间戳) - 调试用
  const lastUpdatedAt = ref<number>(0)

  // 写入计数器 - 每次 setArchData 自增, 监听者可用此触发 watch
  const sequence = ref<number>(0)

  function setArchData(data: any) {
    archData.value = data
    lastUpdatedAt.value = Date.now()
    sequence.value++
  }

  function clear() {
    archData.value = null
    lastUpdatedAt.value = 0
    sequence.value = 0
  }

  return {
    archData,
    lastUpdatedAt,
    sequence,
    setArchData,
    clear
  }
})

export default useChartArchDataStore
