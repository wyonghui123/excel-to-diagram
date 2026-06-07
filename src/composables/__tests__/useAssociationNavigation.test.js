import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref, computed, nextTick } from 'vue'

const mockRouter = {
  push: vi.fn(),
  back: vi.fn(),
}

const mockRoute = {
  query: {},
  fullPath: '/test',
  path: '/test',
}

function createUseAssociationNavigation() {
  const NAV_STATE_KEY = '_nav_source_state'
  const navigationSource = ref(null)

  function parseNavigationParams() {
    const sourceType = mockRoute.query._nav_source_type
    const sourceIds = mockRoute.query._nav_source_ids
    const assocName = mockRoute.query._nav_assoc_name
    const sourceNames = mockRoute.query._nav_source_names

    if (!sourceType || !sourceIds) {
      navigationSource.value = null
      return null
    }

    navigationSource.value = {
      sourceType,
      sourceIds: sourceIds.split(',').map(Number),
      associationName: assocName,
      sourceNames: sourceNames ? sourceNames.split(',') : []
    }

    return navigationSource.value
  }

  function _saveSourceState(objectType, selectedIds, filterValues, sortInfo, pagination, scrollPosition) {
    const state = {
      path: mockRoute.fullPath,
      query: { ...mockRoute.query },
      scrollPosition: scrollPosition || 0,
      selectedIds: Array.from(selectedIds),
      filters: { ...filterValues },
      sort: sortInfo ? { ...sortInfo } : null,
      pagination: {
        current: pagination?.current || 1,
        pageSize: pagination?.pageSize || 20
      },
      timestamp: Date.now()
    }
    sessionStorage.setItem(`${NAV_STATE_KEY}_${objectType}`, JSON.stringify(state))
  }

  function _restoreSourceState(objectType) {
    const key = `${NAV_STATE_KEY}_${objectType}`
    const stored = sessionStorage.getItem(key)
    if (!stored) return null
    try {
      return JSON.parse(stored)
    } catch {
      return null
    }
  }

  function _clearSourceState(objectType) {
    sessionStorage.removeItem(`${NAV_STATE_KEY}_${objectType}`)
  }

  async function navigateToAssociation(association, selectedIds, objectType, options = {}) {
    const ids = Array.from(selectedIds)
    const targetEntity = association.target_entity || association.target_type

    let sourceNames = []
    sourceNames = ids.map(id => `#${id}`)

    if (options.saveState !== false) {
      _saveSourceState(
        objectType,
        selectedIds,
        options.filterValues || {},
        options.sortInfo || null,
        options.pagination || null,
        options.scrollPosition || 0
      )
    }

    const basePath = `/${targetEntity.replace(/_/g, '-')}`
    const query = {
      _nav_source_type: objectType,
      _nav_source_ids: ids.join(','),
      _nav_source_names: sourceNames.join(','),
      _nav_assoc_name: association.name,
    }
    if (options.context === 'dialog') {
      query._nav_context = 'dialog'
    }

    mockRouter.push({ path: basePath, query })
  }

  function navigateBack() {
    if (!navigationSource.value) return
    const state = _restoreSourceState(navigationSource.value.sourceType)
    if (state) {
      mockRouter.push({ path: state.path, query: state.query })
      return true
    }
    mockRouter.back()
    return true
  }

  function isNavigationTarget() {
    return !!(mockRoute.query._nav_source_type && mockRoute.query._nav_source_ids)
  }

  function getNavigationFilterParam() {
    if (!navigationSource.value) return {}
    const { sourceType, sourceIds } = navigationSource.value
    return {
      [`${sourceType}_id__in`]: sourceIds.join(',')
    }
  }

  return {
    navigationSource,
    parseNavigationParams,
    navigateToAssociation,
    navigateBack,
    isNavigationTarget,
    getNavigationFilterParam,
    saveSourceState: _saveSourceState,
    restoreSourceState: _restoreSourceState,
    clearSourceState: _clearSourceState,
  }
}


describe('useAssociationNavigation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
    mockRoute.query = {}
    mockRouter.push.mockReset()
    mockRouter.back.mockReset()
  })

  afterEach(() => {
    sessionStorage.clear()
  })

  describe('parseNavigationParams', () => {
    it('TC-FE-NAV-001: 解析完整的导航参数', () => {
      mockRoute.query = {
        _nav_source_type: 'role',
        _nav_source_ids: '1,2,3',
        _nav_assoc_name: 'users',
        _nav_source_names: 'Admin,Editor,Viewer',
      }

      const { parseNavigationParams, navigationSource } = createUseAssociationNavigation()
      const result = parseNavigationParams()

      expect(result).not.toBeNull()
      expect(result.sourceType).toBe('role')
      expect(result.sourceIds).toEqual([1, 2, 3])
      expect(result.associationName).toBe('users')
      expect(result.sourceNames).toEqual(['Admin', 'Editor', 'Viewer'])
      expect(navigationSource.value).toBe(result)
    })

    it('TC-FE-NAV-002: 缺少参数时返回null', () => {
      mockRoute.query = {}

      const { parseNavigationParams, navigationSource } = createUseAssociationNavigation()
      const result = parseNavigationParams()

      expect(result).toBeNull()
      expect(navigationSource.value).toBeNull()
    })

    it('TC-FE-NAV-003: 缺少source_ids时返回null', () => {
      mockRoute.query = {
        _nav_source_type: 'role',
        _nav_assoc_name: 'users',
      }

      const { parseNavigationParams } = createUseAssociationNavigation()
      const result = parseNavigationParams()

      expect(result).toBeNull()
    })

    it('TC-FE-NAV-004: sourceNames为空时返回空数组', () => {
      mockRoute.query = {
        _nav_source_type: 'role',
        _nav_source_ids: '1',
        _nav_assoc_name: 'users',
      }

      const { parseNavigationParams } = createUseAssociationNavigation()
      const result = parseNavigationParams()

      expect(result).not.toBeNull()
      expect(result.sourceNames).toEqual([])
    })
  })

  describe('isNavigationTarget', () => {
    it('TC-FE-NAV-005: 有导航参数时返回true', () => {
      mockRoute.query = {
        _nav_source_type: 'role',
        _nav_source_ids: '1',
      }

      const { isNavigationTarget } = createUseAssociationNavigation()
      expect(isNavigationTarget()).toBe(true)
    })

    it('TC-FE-NAV-006: 无导航参数时返回false', () => {
      mockRoute.query = {}

      const { isNavigationTarget } = createUseAssociationNavigation()
      expect(isNavigationTarget()).toBe(false)
    })
  })

  describe('getNavigationFilterParam', () => {
    it('TC-FE-NAV-007: 生成正确的过滤参数', () => {
      mockRoute.query = {
        _nav_source_type: 'role',
        _nav_source_ids: '1,2,3',
        _nav_assoc_name: 'users',
      }

      const { parseNavigationParams, getNavigationFilterParam } = createUseAssociationNavigation()
      parseNavigationParams()
      const filterParam = getNavigationFilterParam()

      expect(filterParam).toEqual({ 'role_id__in': '1,2,3' })
    })

    it('TC-FE-NAV-008: 未解析时返回空对象', () => {
      const { getNavigationFilterParam } = createUseAssociationNavigation()
      const filterParam = getNavigationFilterParam()

      expect(filterParam).toEqual({})
    })
  })

  describe('navigateToAssociation', () => {
    it('TC-FE-NAV-009: 调用router.push跳转到目标页面', async () => {
      const { navigateToAssociation } = createUseAssociationNavigation()
      const association = {
        name: 'users',
        target_entity: 'user',
      }

      await navigateToAssociation(association, new Set([1, 2]), 'role')

      expect(mockRouter.push).toHaveBeenCalledWith(
        expect.objectContaining({
          path: '/user',
          query: expect.objectContaining({
            _nav_source_type: 'role',
            _nav_source_ids: '1,2',
            _nav_assoc_name: 'users',
          }),
        }),
      )
    })

    it('TC-FE-NAV-010: 保存源页面状态到sessionStorage', async () => {
      const { navigateToAssociation } = createUseAssociationNavigation()
      const association = { name: 'users', target_entity: 'user' }

      await navigateToAssociation(association, new Set([1]), 'role', {
        filterValues: { status: 'active' },
        sortInfo: { prop: 'name', order: 'ascending' },
        pagination: { current: 2, pageSize: 50 },
      })

      const stored = sessionStorage.getItem('_nav_source_state_role')
      expect(stored).not.toBeNull()
      const state = JSON.parse(stored)
      expect(state.selectedIds).toEqual([1])
      expect(state.filters).toEqual({ status: 'active' })
      expect(state.sort).toEqual({ prop: 'name', order: 'ascending' })
      expect(state.pagination.current).toBe(2)
      expect(state.pagination.pageSize).toBe(50)
    })

    it('TC-FE-NAV-011: dialog上下文添加_nav_context参数', async () => {
      const { navigateToAssociation } = createUseAssociationNavigation()
      const association = { name: 'users', target_entity: 'user' }

      await navigateToAssociation(association, new Set([1]), 'role', {
        context: 'dialog',
      })

      expect(mockRouter.push).toHaveBeenCalledWith(
        expect.objectContaining({
          query: expect.objectContaining({ _nav_context: 'dialog' }),
        }),
      )
    })

    it('TC-FE-NAV-012: saveState=false时不保存状态', async () => {
      const { navigateToAssociation } = createUseAssociationNavigation()
      const association = { name: 'users', target_entity: 'user' }

      await navigateToAssociation(association, new Set([1]), 'role', {
        saveState: false,
      })

      expect(sessionStorage.getItem('_nav_source_state_role')).toBeNull()
    })
  })

  describe('navigateBack', () => {
    it('TC-FE-NAV-013: 有保存状态时恢复到源页面', () => {
      const savedState = {
        path: '/roles',
        query: { page: '2' },
        scrollPosition: 300,
        selectedIds: [1, 2],
      }
      sessionStorage.setItem('_nav_source_state_role', JSON.stringify(savedState))

      mockRoute.query = {
        _nav_source_type: 'role',
        _nav_source_ids: '1,2',
      }

      const { parseNavigationParams, navigateBack } = createUseAssociationNavigation()
      parseNavigationParams()
      navigateBack()

      expect(mockRouter.push).toHaveBeenCalledWith({
        path: '/roles',
        query: { page: '2' },
      })
    })

    it('TC-FE-NAV-014: 无保存状态时调用router.back', () => {
      mockRoute.query = {
        _nav_source_type: 'role',
        _nav_source_ids: '1',
      }

      const { parseNavigationParams, navigateBack } = createUseAssociationNavigation()
      parseNavigationParams()
      navigateBack()

      expect(mockRouter.back).toHaveBeenCalled()
    })

    it('TC-FE-NAV-015: 未解析时直接返回不执行操作', () => {
      const { navigateBack } = createUseAssociationNavigation()
      const result = navigateBack()

      expect(mockRouter.push).not.toHaveBeenCalled()
      expect(mockRouter.back).not.toHaveBeenCalled()
    })
  })

  describe('状态管理 (SessionStorage)', () => {
    it('TC-FE-NAV-016: saveSourceState正确序列化数据', () => {
      const { saveSourceState } = createUseAssociationNavigation()
      saveSourceState('role', new Set([1, 2, 3]), { status: 'active' }, null, { current: 1, pageSize: 20 }, 100)

      const stored = JSON.parse(sessionStorage.getItem('_nav_source_state_role'))
      expect(stored.selectedIds).toEqual([1, 2, 3])
      expect(stored.filters).toEqual({ status: 'active' })
      expect(stored.scrollPosition).toBe(100)
      expect(stored.timestamp).toBeDefined()
    })

    it('TC-FE-NAV-017: restoreSourceState正确反序列化数据', () => {
      const original = {
        path: '/roles',
        query: {},
        selectedIds: [5, 6],
        filters: { name: 'test' },
        sort: { prop: 'id', order: 'desc' },
        pagination: { current: 3, pageSize: 10 },
        timestamp: Date.now(),
      }
      sessionStorage.setItem('_nav_source_state_user', JSON.stringify(original))

      const { restoreSourceState } = createUseAssociationNavigation()
      const restored = restoreSourceState('user')

      expect(restored.path).toBe('/roles')
      expect(restored.selectedIds).toEqual([5, 6])
      expect(restored.filters.name).toBe('test')
    })

    it('TC-FE-NAV-018: clearSourceState清除存储', () => {
      sessionStorage.setItem('_nav_source_state_role', '{}')
      const { clearSourceState } = createUseAssociationNavigation()
      clearSourceState('role')
      expect(sessionStorage.getItem('_nav_source_state_role')).toBeNull()
    })
  })
})
