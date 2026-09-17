import { classify } from '@/services/scaleGuard/guard'

/** 进入图表时的判定包装: level = ok|soft|hard, counts 供文案/组件展示 */
export function decideEntryState(counts, cfg) {
  return { level: classify(counts, cfg), counts }
}
