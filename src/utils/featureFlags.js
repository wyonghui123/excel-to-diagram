/**
 * 轻量 feature flag 机制 (2026-08-11)
 *
 * 目的: 图表内新入口 (如右键菜单的颜色控制) 用独立 flag 控制, 可快速关闭回退,
 *   避免污染正式功能. 遵循项目"所有 UI 显示优化通过独立 feature flag 控制"的既有约束.
 *
 * 覆盖优先级 (高→低):
 *   1. URL query:  ?ff_<name>=0|1|false|true   (快速回退/验证, 无需改码)
 *   2. 环境变量:   import.meta.env.VITE_FF_<NAME>  ('0'/'false' 关闭, '1'/'true' 开启)
 *   3. 默认值:     DEFAULTS[name]
 *
 * 用法:
 *   import { isFeatureEnabled } from '@/utils/featureFlags'
 *   if (isFeatureEnabled('ctxMenuColor')) { ... }
 */
const DEFAULTS = {
  // 空白区域右键菜单中的"颜色设置"子菜单入口
  ctxMenuColor: true,
  // 图例项颜色块点击改色 (方案A: 图例项色块 → 弹出调色板改该分组颜色, 复用 customColors 增量变色)
  legendItemColor: true,
  // [PERF 2026-08-13] process_svg 后处理性能优化总开关:
  //   1) addTrailingDottedLines ELK(hideTails) 早退 — 跳过 3 万次 getPointAtLength 无用计算
  //   2) addNodeCodeAttributes 预建 Map — 消除 O(节点²) find
  //   3) matchPathsToRelations Set 去重 — 消除 O(path²) some
  //   4) tooltip 事件委托 — 替换 2400+ 独立监听器
  perfProcessSvg: true
}

function parseBool(v) {
  if (v === '1' || v === 'true' || v === true) return true
  if (v === '0' || v === 'false' || v === false) return false
  return undefined
}

export function isFeatureEnabled(name) {
  // 1. URL query 覆盖 (最高优先级, 支持运行时快速回退)
  if (typeof window !== 'undefined' && window.location?.search) {
    const params = new URLSearchParams(window.location.search)
    const qv = parseBool(params.get('ff_' + name))
    if (qv !== undefined) return qv
  }
  // 2. 环境变量覆盖
  if (typeof import.meta !== 'undefined') {
    const envVal = import.meta.env?.['VITE_FF_' + name.toUpperCase()]
    const ev = parseBool(envVal)
    if (ev !== undefined) return ev
  }
  // 3. 默认值
  return DEFAULTS[name] !== false
}
