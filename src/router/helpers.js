/**
 * [FR-018] 路由辅助工具
 */
import publicRoutes from './modules/public'
import businessRoutes from './modules/business'
import systemRoutes from './modules/system'
import devRoutes from './modules/dev'

/**
 * 合并所有静态路由
 * 顺序敏感: public → business → system → dev
 *  - public 必须有 / 兜底路由
 *  - 业务/系统路由在动态路由加载前作为兜底
 *  - dev 路由在生产环境可被剔除
 */
export function buildStaticRoutes(options = {}) {
  const { includeDev = true } = options
  const routes = [
    ...publicRoutes,
    ...businessRoutes,
    ...systemRoutes
  ]
  if (includeDev) {
    routes.push(...devRoutes)
  }
  return routes
}

/**
 * 统计路由数量 (调试用,验证模块化后无遗漏)
 */
export function countRoutes(routes) {
  let count = 0
  for (const r of routes) {
    count += 1
    if (r.children) count += countRoutes(r.children)
  }
  return count
}
