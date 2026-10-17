/**
 * [移动端回归网 2026-10-14] MetaListPage 响应式行为单测
 *
 * 为什么需要这个文件：MetaListPage 是全项目移动端逻辑最复杂、历史回归最多的
 * 组件 —— 本周就出过三次线上事故，全部由人工截图发现、事后靠注释记录：
 *
 *   1. 2026-10-13 模板写 `v-if="isMobile"` 而非 `useCardView`，
 *      导致 embedded 复用方（审计日志页）被卡片化，cardColumns 返回 []
 *      渲染出「只有标题的 -」的空卡片，把真实表格顶掉。
 *   2. 2026-10-13 importance 与 column_priority 语义混用，
 *      审计日志 13 列 importance 全为 medium 被全部滤掉，表格全空白。
 *   3. 2026-10-14 分页器被内容顶出视口，360px 屏需下滚 3412px 才可见。
 *
 * 这四处逻辑都有注释，但没有自动化保护，下一次改动极易再次踩中。
 * 本文件把「曾经出过事故的决策点」固化为断言。
 *
 * matchMedia mock 复用 src/test/setup.js 的全局 mock（matches 恒 false = PC），
 * 通过 helper 覆写为窄屏，不改动全局 setup。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick, ref } from 'vue'
import { setupPinia } from '@/test/setup'

// 与 useBreakpoints.BREAKPOINTS.sm 一致；改动需同步 styles/mixins.scss
const MOBILE_MAX_WIDTH = 768

/**
 * visibleColumns 的取值由每个用例通过 __setColumns 注入。
 * 不能写死：tableColumns / cardColumns / cardPrimaryColumn 三者全部
 * 派生自 visibleColumns，写死等于把被测逻辑的输入也锁死。
 *
 * 组件解构后按 ref 用（.value），故这里返回 ref；Proxy 让 __setColumns
 * 的赋值对已创建的 ref 立即生效，无需重建组件实例。
 */
const __visibleColumnsRef = ref([])
function __setColumns(cols) {
  __visibleColumnsRef.value = (cols || []).map(c => ({ ...c }))
}

vi.mock('@/composables/useMetaList', () => {
  // 用 Proxy 按「用法」而非「名字」兜底 —— 依据是组件里实际出现的三种访问形态：
  //   1) 当函数调用（onXxx / getXxx / isXxx / hasXxx）→ vi.fn()
  //   2) .value.filter / .map / 遍历                      → ref([])
  //   3) .value.has()  —— selectedIds 是 Set（实测：ref([]) 会炸
  //      「selectedIds.value.has is not a function」）
  //   4) .value 读布尔/字符串                            → ref(undefined)
  const FUNCTION_PREFIX = /^(on|get|is|has|load|refresh|toggle|clear|start|finish|update|add|remove|save|cancel|enable|disable|set|batch|parse|navigate)/
  const ARRAY_FIELD = /(?<![a-z])[a-z]*(s|ies|List|Options|Actions|Columns|Rows|Filters|Rules)$/
  // Set 型字段：selectedIds 等，走 .has() 判定
  const SET_FIELD = /selectedIds$/

  const defaults = {
    data: ref([
      { id: 1, code: 'AUD-001', name: '创建枚举类型', operator: 'admin', status: 'success' },
      { id: 2, code: 'AUD-002', name: '修改权限集', operator: 'user1', status: 'success' }
    ]),
    loading: ref(false),
    error: ref(null),
    total: ref(2),
    pagination: ref({ current: 1, pageSize: 20, total: 2 }),
    // 组件按 ref 解构（.value），与 __setColumns 共享同一个 ref 实例
    visibleColumns: __visibleColumnsRef,
    columns: ref([]),
    selectionConfig: ref({ enabled: false, mode: 'multiple' }),
    paginationConfig: ref({
      layout: 'total, sizes, prev, pager, next, jumper',
      pageSizes: [10, 20, 50],
      background: true
    })
  }

  return {
    useMetaList: () =>
      new Proxy({ ...defaults }, {
        get(target, prop) {
          if (prop in target) return target[prop]
          if (typeof prop !== 'string') return undefined
          let value
          if (FUNCTION_PREFIX.test(prop)) value = vi.fn()
          else if (SET_FIELD.test(prop)) value = ref(new Set())
          else if (ARRAY_FIELD.test(prop)) value = ref([])
          else value = ref(undefined)
          target[prop] = value
          return value
        },
        has() {
          return true
        }
      })
  }
})

vi.mock('@/composables/useAssociationNavigation', () => ({
  useAssociationNavigation: () => ({
    navigationSource: ref(null),
    parseNavigationParams: vi.fn(() => null),
    navigateToAssociation: vi.fn(),
    navigateBack: vi.fn(),
    // 被 isNavTarget computed 直接调用，必须是函数
    isNavigationTarget: vi.fn(() => false),
    getNavigationFilterParam: vi.fn(() => null),
    getRoutePath: vi.fn(() => '/test')
  })
}))

/**
 * 把 matchMedia 设为指定视口宽度。useBreakpoints 用
 * `(max-width: ${px}px)` 匹配，故「窄屏」= 375 命中 sm、「宽屏」= 1280 不命中。
 */
function setViewport(width) {
  window.matchMedia = vi.fn().mockImplementation(query => {
    const m = /max-width:\s*(\d+)px/.exec(query)
    const max = m ? Number(m[1]) : Infinity
    return {
      matches: width <= max,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn()
    }
  })
}

/** 覆盖 import/setup.js 里的原始 mock，便于测试后复原 */
let originalMatchMedia
beforeEach(() => {
  originalMatchMedia = window.matchMedia
  // MetaListPage 的 setup 链路里 useMenuPermissions 会调 useMenuPermissions store，
  // 未激活 Pinia 时 setup 直接抛错（实测 13 个用例全挂在这一步）。
  // setup.js 已导出该 helper，复用它而非在本地重建。
  const pinia = setupPinia()
  return pinia
})
afterEach(() => {
  window.matchMedia = originalMatchMedia
})

const COLUMNS = [
  { prop: 'id', label: '日志ID', importance: 'medium' },
  { prop: 'code', label: '业务标识', businessKey: true, importance: 'high' },
  { prop: 'name', label: '操作对象', importance: 'high' },
  { prop: 'operator', label: '操作人', importance: 'medium' },
  { prop: 'status', label: '结果', importance: 'low' }
]

/**
 * columns 传 props.options.columns，同时注入 useMetaList 的 visibleColumns。
 * 两者需一致：组件在模板侧读 props.options.columns 做过滤判断，
 * 而 tableColumns/cardColumns 派生自 visibleColumns。
 */
async function mountList(props = {}) {
  const columns = props.options?.columns || COLUMNS
  __setColumns(columns)
  const wrapper = mount((await import('../MetaListPage.vue')).default, {
    props: {
      objectType: 'audit_log',
      options: { columns },
      ...props
    },
    global: {
      stubs: {
        // 卡片/表格分支都会用到的重组件，避免子组件副作用干扰断言
        ObjectDetailPage: true,
        AppModal: true,
        Drawer: true,
        ElForm: true,
        ElFormItem: true,
        ElInput: true,
        ElSelect: true,
        ElOption: true,
        ElTableColumn: true
      }
    }
  })
  // useBreakpoints 在 onMounted 里同步 matchMedia，需等一个 tick
  await nextTick()
  await nextTick()
  return wrapper
}

describe('MetaListPage 移动端回归网', () => {
  describe('useCardView: displayMode 三分支（回归 1）', () => {
    it('page + 窄屏 → 走卡片视图', async () => {
      setViewport(375)
      const wrapper = await mountList({ displayMode: 'page' })
      expect(wrapper.vm.useCardView).toBe(true)
    })

    it('embedded + 窄屏 → 必须保持表格，卡片化会渲染空卡片', async () => {
      // [FIX 2026-10-13] 审计日志页实测中招：卡片只有标题、没有任何标签行，
      // 而依赖的 el-table 被 v-else 顶掉，页面看起来是空的。
      setViewport(375)
      const wrapper = await mountList({ displayMode: 'embedded' })
      expect(wrapper.vm.useCardView).toBe(false)
    })

    it('dialog + 窄屏 → 保持表格（该弹窗强依赖 el-table 的 row-click/多选）', async () => {
      setViewport(375)
      const wrapper = await mountList({ displayMode: 'dialog' })
      expect(wrapper.vm.useCardView).toBe(false)
    })

    it('page + 宽屏 → 不卡片化', async () => {
      setViewport(1280)
      const wrapper = await mountList({ displayMode: 'page' })
      expect(wrapper.vm.useCardView).toBe(false)
    })
  })

  describe('cardColumns: 非卡片态必须为空数组', () => {
    it('embedded 窄屏下 cardColumns 为 []，不得产出空卡片', async () => {
      // [FIX 2026-10-13] 这是回归 1 的真正根因：模板若误用 isMobile 判定，
      // 会出现「useCardView=false 却走了卡片分支」的错配，于是渲染出空卡片。
      //
      // 注意 cardPrimaryColumn 本身**不**受 useCardView 约束（见
      // MetaListPage.vue:1034-1040，它无条件计算，仅 cardColumns 里守卫）。
      // 所以防线是两段而非一段：模板用 useCardView 选分支 +
      // cardColumns 在非卡片态返回 []。此处只断言后者，前者由
      // 「useCardView 为 false」+ 模板源码保证。
      setViewport(375)
      const wrapper = await mountList({ displayMode: 'embedded' })
      expect(wrapper.vm.useCardView).toBe(false)
      expect(wrapper.vm.cardColumns).toEqual([])
    })

    it('page 窄屏下 cardColumns 非空且不含主键列（避免标题重复）', async () => {
      setViewport(375)
      const wrapper = await mountList({ displayMode: 'page' })
      expect(wrapper.vm.useCardView).toBe(true)
      expect(wrapper.vm.cardPrimaryColumn).not.toBeNull()
      const primaryProp = wrapper.vm.cardPrimaryColumn.prop
      expect(wrapper.vm.cardColumns.some(c => c.prop === primaryProp)).toBe(false)
    })
  })

  describe('tableColumns: 窄屏按 importance 降级（回归 2）', () => {
    it('窄屏仅保留 importance=high 的列', async () => {
      setViewport(375)
      const wrapper = await mountList({ displayMode: 'page' })
      const props = wrapper.vm.tableColumns.map(c => c.prop)
      expect(props).toContain('code')
      expect(props).toContain('name')
      expect(props).not.toContain('status')
    })

    it('宽屏不做列降级', async () => {
      setViewport(1280)
      const wrapper = await mountList({ displayMode: 'page' })
      expect(wrapper.vm.tableColumns.length).toBe(COLUMNS.length)
    })

    it('全列均非 high 时放弃降级，全部保留（保护性兜底）', async () => {
      // 回归 2 的教训：importance 全部缺失/非 high 时若降级成空列集，
      // el-table 会收到空 colgroup，渲染出 50 个空 tr 且无任何 JS 报错。
      setViewport(375)
      const noHigh = COLUMNS.map(c => ({ ...c, importance: 'medium' }))
      const wrapper = await mountList({ displayMode: 'page', options: { columns: noHigh } })
      expect(wrapper.vm.tableColumns.length).toBe(noHigh.length)
    })
  })

  describe('分页器: 卡片态替换布局（回归 3）', () => {
    it('卡片态使用短布局，保留「共 N 条」', async () => {
      // [FIX 2026-10-13] 之前用 CSS display:none 隐藏子块，
      // 代价是把「共 N 条」也一起藏了，用户不知道总数。
      setViewport(375)
      const wrapper = await mountList({ displayMode: 'page' })
      expect(wrapper.vm.effectivePaginationLayout).toBe('total, prev, pager, next')
      expect(wrapper.vm.effectivePaginationLayout).toContain('total')
    })

    it('非卡片态沿用配置的原布局', async () => {
      setViewport(1280)
      const wrapper = await mountList({ displayMode: 'page' })
      expect(wrapper.vm.effectivePaginationLayout).not.toBe('total, prev, pager, next')
    })

    it('卡片态页码数收敛为 5（默认 7 在窄屏过宽）', async () => {
      setViewport(375)
      const wrapper = await mountList({ displayMode: 'page' })
      expect(wrapper.vm.effectivePagerCount).toBe(5)
    })
  })

  describe('断点一致性', () => {
    it('移动端判定阈值与 useBreakpoints.BREAKPOINTS.sm 一致', async () => {
      const { BREAKPOINTS } = await import('@/composables/useBreakpoints')
      expect(BREAKPOINTS.sm).toBe(MOBILE_MAX_WIDTH)
    })

    it('sm 边界（恰好 768px）应视为窄屏，769px 为宽屏', async () => {
      // max-width 是闭区间，若实现改成 < 会在 768px 出现行为分叉
      setViewport(768)
      const atEdge = await mountList({ displayMode: 'page' })
      expect(atEdge.vm.useCardView).toBe(true)

      setViewport(769)
      const above = await mountList({ displayMode: 'page' })
      expect(above.vm.useCardView).toBe(false)
    })
  })
})
