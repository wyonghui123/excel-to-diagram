import { describe, it, expect, vi } from 'vitest'
import { resolveHubOptions } from '../hubOptions'

vi.mock('@/components/common/HierarchyScopeTree', () => ({
  HierarchyScopeTree: { name: 'HierarchyScopeTree' }
}))

const ITEM_HUB = {
  object_types: ['item_group', 'item'],
  default_tab: 'item',
  tabs: { item: '物料/服务', item_group: '物料组' },
  state_key: 'materialManagerState',
  disable_version_context: true,
  scope: {
    type: 'hierarchy',
    object: 'item_group',
    scope_key: 'item',
    parent_field: 'parent_id',
    order_by: '',
    empty_text: '暂无物料组数据'
  },
  filters: {
    item: { field: 'item_group_id' },
    item_group: { mode: 'none' }
  }
}

const CALENDAR_HUB = {
  object_types: ['calendar', 'calendar_day'],
  default_tab: 'calendar',
  tabs: { calendar: '作业日历', calendar_day: '日历例外日' },
  disable_version_context: true,
  scope: {
    type: 'hierarchy',
    object: 'calendar',
    scope_key: 'calendar',
    parent_field: 'parent_calendar_id',
    badge_field: 'parentId',
    badge_map: {
      __root__: { label: '基准', type: 'primary' },
      __fallback__: { label: '派生', type: 'info' }
    },
    node_icon: 'none'
  },
  filters: {
    calendar: { field: 'id' },
    calendar_day: { field: 'calendar_id' }
  }
}

describe('resolveHubOptions', () => {
  it('把 items hub 解析为 MOMP options', () => {
    const { objectTypes, options } = resolveHubOptions(ITEM_HUB, { menuCode: 'material-management' })

    expect(objectTypes).toEqual(['item_group', 'item'])
    expect(options.defaultTab).toBe('item')
    expect(options.tabs).toEqual({ item_group: { label: '物料组' }, item: { label: '物料/服务' } })
    expect(options.stateKey).toBe('materialManagerState')
    expect(options.disableVersionContext).toBe(true)
    expect(options.menuCodeProvider()).toBe('material-management')

    // 树：object 与过滤键不同名（item_group 树 → item tab）
    const scopeProps = options.scopeTree.props
    expect(scopeProps.objectType).toBe('item_group')
    expect(scopeProps.scopeKey).toBe('item')
    expect(scopeProps.idsKey).toBe('itemGroupIds')
    expect(scopeProps.effectiveIdsKey).toBe('effectiveItemGroupIds')
    expect(scopeProps.orderBy).toBe('')
  })

  it('未声明 order_by 时不覆盖组件默认排序', () => {
    const { options } = resolveHubOptions({ ...ITEM_HUB, scope: { object: 'item_group', scope_key: 'item' } })
    expect('orderBy' in options.scopeTree.props).toBe(false)
  })

  it('按 effective 生成 __in 过滤；未勾选则不过滤', () => {
    const { options } = resolveHubOptions(ITEM_HUB)
    const scopeIds = { item: { selected: [1], effective: [1, 2, 3] } }

    expect(options.filterStrategies.item({ status: 'active' }, scopeIds))
      .toEqual({ status: 'active', item_group_id__in: '1,2,3' })
    expect(options.filterStrategies.item({ status: 'active' }, { item: { selected: [], effective: [] } }))
      .toEqual({ status: 'active' })
  })

  it('mode: none 的 tab 原样返回 filters（避免落入关系过滤默认分支）', () => {
    const { options } = resolveHubOptions(ITEM_HUB)
    const filters = { status: 'active' }
    expect(options.filterStrategies.item_group(filters, { item: { effective: [9] } })).toBe(filters)
  })

  it('未声明策略的 tab 也返回原 filters', () => {
    const { options } = resolveHubOptions({ ...ITEM_HUB, filters: { item: { field: 'item_group_id' } } })
    const filters = {}
    expect(options.filterStrategies.item_group(filters, {})).toBe(filters)
  })

  it('scope-change 同步 selected / effective 到 scopeIds[scope_key]', () => {
    const { options } = resolveHubOptions(ITEM_HUB)
    const scopeIds = { item: { selected: [], effective: [] } }
    options.scopeAdapter.handleScopeChange(
      { itemGroupIds: [5], effectiveItemGroupIds: [5, 6] },
      { scopeIds }
    )
    expect(scopeIds.item).toEqual({ selected: [5], effective: [5, 6] })
  })

  it('effective 为空时回退 selected', () => {
    const { options } = resolveHubOptions(ITEM_HUB)
    const scopeIds = { item: { selected: [], effective: [] } }
    options.scopeAdapter.handleScopeChange({ itemGroupIds: [7] }, { scopeIds })
    expect(scopeIds.item).toEqual({ selected: [7], effective: [7] })
  })

  it('calendar hub：父字段覆盖 + 基准/派生徽标 + 两个 tab 的过滤字段', () => {
    const { options } = resolveHubOptions(CALENDAR_HUB, { menuCode: 'calendar-list' })
    const scopeProps = options.scopeTree.props

    expect(scopeProps.parentField).toBe('parent_calendar_id')
    expect(scopeProps.idsKey).toBe('calendarIds')
    expect(scopeProps.effectiveIdsKey).toBe('effectiveCalendarIds')
    expect(scopeProps.badgeField).toBe('parentId')
    expect(scopeProps.nodeIcon).toBe(null)

    const scopeIds = { calendar: { effective: [1, 2] } }
    expect(options.filterStrategies.calendar({}, scopeIds)).toEqual({ id__in: '1,2' })
    expect(options.filterStrategies.calendar_day({}, scopeIds)).toEqual({ calendar_id__in: '1,2' })
  })

  it('org hub：单对象自指范围 + 全量分页 + 组织图标', () => {
    const { objectTypes, options } = resolveHubOptions({
      object_types: ['org'],
      default_tab: 'org',
      state_key: 'orgManagerStateBeforeDiagram',
      scope: {
        type: 'hierarchy',
        object: 'org',
        scope_key: 'org',
        parent_field: 'parent_id',
        order_by: '',
        paginate_all: true,
        node_icon: 'office'
      },
      filters: { org: { field: 'id' } }
    }, { menuCode: 'org-management' })

    expect(objectTypes).toEqual(['org'])
    expect(options.scopeTree.props.paginateAll).toBe(true)
    expect(options.scopeTree.props.nodeIcon).toBeTruthy()
    expect(options.scopeTree.props.idsKey).toBe('orgIds')
    expect(options.scopeTree.props.effectiveIdsKey).toBe('effectiveOrgIds')

    expect(options.filterStrategies.org({}, { org: { effective: [3, 4] } }))
      .toEqual({ id__in: '3,4' })
    // 未勾选 = 全量（组织页业务预期，不是空集守卫）
    expect(options.filterStrategies.org({}, { org: { effective: [] } })).toEqual({})
  })

  it('object_types 为空 → null', () => {
    expect(resolveHubOptions({})).toBe(null)
    expect(resolveHubOptions({ object_types: [] })).toBe(null)
  })

  it('scope_key 不在 object_types 内 → null（配置错误不静默通过）', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const result = resolveHubOptions({ ...ITEM_HUB, scope: { object: 'item_group', scope_key: 'nope' } })
    expect(result).toBe(null)
    spy.mockRestore()
  })

  it('scope.type 非 hierarchy → null', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const result = resolveHubOptions({ ...ITEM_HUB, scope: { type: 'relation' } })
    expect(result).toBe(null)
    spy.mockRestore()
  })

  describe('bridge（两段桥接）', () => {
    const PARTY_HUB = {
      object_types: ['party_group', 'party_archive', 'party_relation'],
      default_tab: 'party_archive',
      scope: { type: 'hierarchy', object: 'party_group', scope_key: 'party_group', order_by: '' },
      filters: {
        party_archive: {
          bridge: {
            through: 'party_relation',
            match_field: 'group_id',
            collect_field: 'party2_id',
            target_field: 'id',
            page_size: 500,
            empty_sentinel: '-1'
          }
        },
        party_group: { mode: 'none' },
        party_relation: { mode: 'none' }
      }
    }

    it('暴露 bridge 描述符供页面异步执行', () => {
      const { bridges } = resolveHubOptions(PARTY_HUB, { bridgeIds: {} })
      expect(bridges).toHaveLength(1)
      expect(bridges[0]).toMatchObject({
        objectType: 'party_archive',
        scopeKey: 'party_group',
        through: 'party_relation',
        matchField: 'group_id',
        collectField: 'party2_id',
        targetField: 'id'
      })
    })

    it('桥接结果为空集时发哨兵，未选范围时不过滤', () => {
      const bridgeIds = { party_archive: null }
      const { options } = resolveHubOptions(PARTY_HUB, { bridgeIds })
      const strategy = options.filterStrategies.party_archive

      expect(strategy({})).toEqual({})  // 未选组 → 全量

      bridgeIds.party_archive = ['9', '10']
      expect(strategy({})).toEqual({ id__in: '9,10' })

      bridgeIds.party_archive = []
      expect(strategy({})).toEqual({ id__in: '-1' })  // 选中但无关联 → 空集哨兵
    })

    it('组 / 关系 tab 不随左树收窄', () => {
      const { options } = resolveHubOptions(PARTY_HUB, { bridgeIds: {} })
      expect(options.filterStrategies.party_group({ page: 1 })).toEqual({ page: 1 })
      expect(options.filterStrategies.party_relation({ page: 1 })).toEqual({ page: 1 })
    })

    it('bridge 缺 through/collect_field 时降级为不过滤', () => {
      const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
      const { bridges, options } = resolveHubOptions({
        ...PARTY_HUB,
        filters: { party_archive: { bridge: { through: 'party_relation' } } }
      }, { bridgeIds: {} })
      expect(bridges).toHaveLength(0)
      expect(options.filterStrategies.party_archive({})).toEqual({})
      spy.mockRestore()
    })
  })
})
