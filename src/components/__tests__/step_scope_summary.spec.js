/**
 * v40 修复: StepScopeSummary 的 hasIncremental 判断补全
 *
 * 问题: 关系范围可能仅新增关系（src/tgt 都在中心范围），
 *      此时 businessObjects/domains/subDomains/serviceModules 都为 0，
 *      但 objectRelations > 0。旧逻辑只检查 businessObjects/domains，
 *      导致关系范围统计误判为空（显示 "—"）。
 *
 * 修复: 改为检查 incremental 的所有维度（businessObjects / domains /
 *      subDomains / serviceModules / objectRelations）任一大于 0 即为 true。
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import StepScopeSummary from '../../views/AADiagramApp/components/steps/StepScopeSummary.vue'

function makeWrapper(props) {
  return mount(StepScopeSummary, { props })
}

describe('StepScopeSummary.hasIncremental (v40 修复)', () => {
  it('用户场景: 中心 18 对象/19 关系, 总数 18 对象/23 关系 → hasIncremental=true (4 条新增关系)', () => {
    // 关键场景: 关系范围只新增了关系（涉及 BO 都在中心范围内），BO/域/子/服 都为 0
    const wrapper = makeWrapper({
      center: { domains: 3, subDomains: 6, serviceModules: 12, businessObjects: 18, objectRelations: 19 },
      incremental: { domains: 0, subDomains: 0, serviceModules: 0, businessObjects: 0, objectRelations: 4 },
      total: { domains: 3, subDomains: 6, serviceModules: 12, businessObjects: 18, objectRelations: 23 }
    })

    // 关键断言: 旧逻辑会因 incremental.businessObjects=0 && incremental.domains=0 → false
    // 新逻辑: objectRelations=4 > 0 → true
    const vm = wrapper.vm
    expect(vm.hasIncremental).toBe(true)

    // 验证 "—" 符号不显示, "+4 关系" 显示
    const html = wrapper.html()
    expect(html).toContain('+4')
    expect(html).toContain('关系')
    expect(html).not.toContain('summary-card__empty')
  })

  it('增量 businessObjects=5 → hasIncremental=true', () => {
    const wrapper = makeWrapper({
      center: { domains: 3, subDomains: 6, serviceModules: 12, businessObjects: 18, objectRelations: 19 },
      incremental: { domains: 0, subDomains: 0, serviceModules: 1, businessObjects: 5, objectRelations: 8 },
      total: { domains: 3, subDomains: 6, serviceModules: 13, businessObjects: 23, objectRelations: 27 }
    })
    expect(wrapper.vm.hasIncremental).toBe(true)
  })

  it('增量全 0 (无关系范围选择) → hasIncremental=false', () => {
    const wrapper = makeWrapper({
      center: { domains: 3, subDomains: 6, serviceModules: 12, businessObjects: 18, objectRelations: 19 },
      incremental: { domains: 0, subDomains: 0, serviceModules: 0, businessObjects: 0, objectRelations: 0 },
      total: { domains: 3, subDomains: 6, serviceModules: 12, businessObjects: 18, objectRelations: 19 }
    })
    expect(wrapper.vm.hasIncremental).toBe(false)

    const html = wrapper.html()
    expect(html).toContain('summary-card__empty')
    expect(html).toContain('—')
  })

  it('incremental=null → hasIncremental=false (兜底)', () => {
    const wrapper = makeWrapper({
      center: { domains: 3, subDomains: 6, serviceModules: 12, businessObjects: 18, objectRelations: 19 },
      incremental: null,
      total: { domains: 3, subDomains: 6, serviceModules: 12, businessObjects: 18, objectRelations: 19 }
    })
    expect(wrapper.vm.hasIncremental).toBe(false)
  })

  it('增量只有 subDomains=2 → hasIncremental=true', () => {
    // 防御性测试: 修复后应覆盖子域维度
    const wrapper = makeWrapper({
      center: { domains: 1, subDomains: 3, serviceModules: 5, businessObjects: 8, objectRelations: 4 },
      incremental: { domains: 0, subDomains: 2, serviceModules: 0, businessObjects: 0, objectRelations: 0 },
      total: { domains: 1, subDomains: 5, serviceModules: 5, businessObjects: 8, objectRelations: 4 }
    })
    expect(wrapper.vm.hasIncremental).toBe(true)
  })

  it('增量只有 serviceModules=1 → hasIncremental=true', () => {
    const wrapper = makeWrapper({
      center: { domains: 1, subDomains: 1, serviceModules: 5, businessObjects: 8, objectRelations: 4 },
      incremental: { domains: 0, subDomains: 0, serviceModules: 1, businessObjects: 0, objectRelations: 0 },
      total: { domains: 1, subDomains: 1, serviceModules: 6, businessObjects: 8, objectRelations: 4 }
    })
    expect(wrapper.vm.hasIncremental).toBe(true)
  })

  it('增量只有 domains=1 → hasIncremental=true (与原逻辑兼容)', () => {
    const wrapper = makeWrapper({
      center: { domains: 1, subDomains: 1, serviceModules: 5, businessObjects: 8, objectRelations: 4 },
      incremental: { domains: 1, subDomains: 0, serviceModules: 0, businessObjects: 0, objectRelations: 0 },
      total: { domains: 2, subDomains: 1, serviceModules: 5, businessObjects: 8, objectRelations: 4 }
    })
    expect(wrapper.vm.hasIncremental).toBe(true)
  })
})

describe('StepScopeSummary.hasCenter / hasTotal (回归保护)', () => {
  it('center.businessObjects=18 → hasCenter=true', () => {
    const wrapper = makeWrapper({
      center: { domains: 3, subDomains: 6, serviceModules: 12, businessObjects: 18, objectRelations: 19 },
      incremental: null,
      total: { domains: 3, subDomains: 6, serviceModules: 12, businessObjects: 18, objectRelations: 19 }
    })
    expect(wrapper.vm.hasCenter).toBe(true)
  })

  it('center=null → hasCenter=null/false (兜底)', () => {
    const wrapper = makeWrapper({
      center: null,
      incremental: null,
      total: { domains: 3, subDomains: 6, serviceModules: 12, businessObjects: 18, objectRelations: 19 }
    })
    // computed 表达式 this.center && ... 在 center=null 时短路求值为 null
    // 模板 v-if 会判 falsy 跳过渲染, 跟 false 等效
    expect(!!wrapper.vm.hasCenter).toBe(false)
  })

  it('total.businessObjects=18 → hasTotal=true', () => {
    const wrapper = makeWrapper({
      center: { domains: 3, subDomains: 6, serviceModules: 12, businessObjects: 18, objectRelations: 19 },
      incremental: { domains: 0, subDomains: 0, serviceModules: 0, businessObjects: 0, objectRelations: 4 },
      total: { domains: 3, subDomains: 6, serviceModules: 12, businessObjects: 18, objectRelations: 23 }
    })
    expect(wrapper.vm.hasTotal).toBe(true)
  })
})
