/**
 * 响应式断点检测（JS 侧）
 *
 * 用途：CSS 媒体查询能改样式，但改不了结构 —— 例如「手机上隐藏部分表格列」
 * 这类需求必须由 JS 判断视口后决定渲染内容。本composable 是 CSS 断点的镜像，
 * 阈值必须与 styles/mixins.scss 的 $breakpoints 保持一致。
 *
 * 选型说明：用 matchMedia 而非 resize + clientWidth。
 * - matchMedia 由浏览器原生实现，不会在滚动时触发，性能更好
 * - 每个断点一个 MediaQueryList，彼此独立，只监听真正跨越的断点
 * - SSR / 测试环境无 matchMedia 时退化为"按 PC 处理"，不影响既有逻辑
 */
import { ref, readonly, onMounted, onUnmounted } from 'vue'

/** 与 styles/mixins.scss 的 $breakpoints 严格对应 */
export const BREAKPOINTS = {
  xs: 480,
  sm: 768,
  md: 1024,
  lg: 1200,
  xl: 1400
}

/**
 * @returns {{
 *   isXs: import('vue').Ref<boolean>,
 *   isSm: import('vue').Ref<boolean>,
 *   isMd: import('vue').Ref<boolean>,
 *   isLg: import('vue').Ref<boolean>,
 *   isXl: import('vue').Ref<boolean>,
 *   isMobile: import('vue').Ref<boolean>,
 *   isDesktop: import('vue').Ref<boolean>
 * }}
 */
export function useBreakpoints() {
  // 全部先置 false，挂载后再由 matchMedia 同步真实值。
  // 挂载前若假定为 PC，表格会先渲染全部列再收缩，造成可见的闪动。
  const isXs = ref(false)
  const isSm = ref(false)
  const isMd = ref(false)
  const isLg = ref(false)
  const isXl = ref(false)

  const state = { xs: isXs, sm: isSm, md: isMd, lg: isLg, xl: isXl }
  const lists = []
  let mounted = false

  function sync() {
    if (typeof window === 'undefined' || !window.matchMedia) return
    for (const key of Object.keys(state)) {
      state[key].value = window.matchMedia(`(max-width: ${BREAKPOINTS[key]}px)`).matches
    }
  }

  onMounted(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return
    for (const key of Object.keys(state)) {
      const mql = window.matchMedia(`(max-width: ${BREAKPOINTS[key]}px)`)
      const handler = e => { state[key].value = e.matches }
      // addEventListener 是现代 API；旧版 Safari 只支持 addListener
      if (mql.addEventListener) {
        mql.addEventListener('change', handler)
        lists.push([mql, handler])
      } else if (mql.addListener) {
        mql.addListener(handler)
        lists.push([mql, handler])
      }
    }
    sync()
    mounted = true
  })

  onUnmounted(() => {
    if (!mounted) return
    for (const [mql, handler] of lists) {
      if (mql.removeEventListener) mql.removeEventListener('change', handler)
      else if (mql.removeListener) mql.removeListener(handler)
    }
    lists.length = 0
    mounted = false
  })

  return {
    isXs: readonly(isXs),
    isSm: readonly(isSm),
    isMd: readonly(isMd),
    isLg: readonly(isLg),
    isXl: readonly(isXl),
    // isSm 已覆盖 xs(480) 的全部区间，手机场景不必区分
    isMobile: readonly(isSm),
    isDesktop: readonly(isLg)
  }
}