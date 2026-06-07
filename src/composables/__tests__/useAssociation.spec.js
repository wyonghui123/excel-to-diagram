/**
 * useAssociation.spec.js - 关联操作 Composable 测试
 *
 * 测试核心功能：
 * 1. queryAssociations - 查询关联列表
 * 2. countAssociations - 统计关联数量
 * 3. assign/unassign - 单个关联操作
 * 4. batchAssign/batchUnassign - 批量关联操作
 * 5. 选择管理 - clearSelection/toggleSelection/selectAll/unassignSelected
 * 6. 错误处理 - 缺少 associationName
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'

vi.mock('@/services/boService', () => ({
  default: {
    queryAssociationsV2: vi.fn(),
    countAssociationsV2: vi.fn(),
    assignAssociationV2: vi.fn(),
    unassignAssociationV2: vi.fn(),
    batchAssignAssociationsV2: vi.fn(),
    batchUnassignAssociationsV2: vi.fn(),
  }
}))

import boService from '@/services/boService'
import { useAssociation } from '@/composables/useAssociation'

describe('useAssociation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('initial state', () => {
    it('has correct default values', () => {
      const sourceId = ref(1)
      const { items, total, loading, error, count, selectedItems } = useAssociation(
        'user',
        { associationName: 'roles', sourceId }
      )

      expect(items.value).toEqual([])
      expect(total.value).toBe(0)
      expect(loading.value).toBe(false)
      expect(error.value).toBeNull()
      expect(count.value).toBe(0)
      expect(selectedItems.value).toEqual([])
    })

    it('has correct computed values', () => {
      const sourceId = ref(1)
      const { hasItems, hasSelectedItems } = useAssociation(
        'user',
        { associationName: 'roles', sourceId }
      )

      expect(hasItems.value).toBe(false)
      expect(hasSelectedItems.value).toBe(false)
    })
  })

  describe('queryAssociations', () => {
    it('queries associations successfully', async () => {
      const sourceId = ref(1)
      boService.queryAssociationsV2.mockResolvedValue({
        success: true,
        data: {
          items: [{ id: 1, name: 'admin' }, { id: 2, name: 'user' }],
          total: 2,
        },
      })

      const { queryAssociations, items, total } = useAssociation(
        'user',
        { associationName: 'roles', sourceId }
      )

      const result = await queryAssociations()

      expect(boService.queryAssociationsV2).toHaveBeenCalledWith(
        'user', 1, 'roles', {}
      )
      expect(items.value).toHaveLength(2)
      expect(total.value).toBe(2)
    })

    it('handles query error', async () => {
      const sourceId = ref(1)
      boService.queryAssociationsV2.mockResolvedValue({
        success: false,
        message: 'Query failed',
      })

      const { queryAssociations, error } = useAssociation(
        'user',
        { associationName: 'roles', sourceId }
      )

      const result = await queryAssociations()

      expect(result).toBeNull()
      expect(error.value).toBe('Query failed')
    })

    it('handles exception', async () => {
      const sourceId = ref(1)
      boService.queryAssociationsV2.mockRejectedValue(new Error('Network error'))

      const { queryAssociations, error } = useAssociation(
        'user',
        { associationName: 'roles', sourceId }
      )

      const result = await queryAssociations()

      expect(result).toBeNull()
      expect(error.value).toBe('Network error')
    })

    it('requires associationName', async () => {
      const sourceId = ref(1)
      const { queryAssociations, error } = useAssociation(
        'user',
        { sourceId }
      )

      const result = await queryAssociations()

      expect(result).toBeNull()
      expect(error.value).toBe('associationName is required')
    })
  })

  describe('countAssociations', () => {
    it('counts associations successfully', async () => {
      const sourceId = ref(1)
      boService.countAssociationsV2.mockResolvedValue({
        success: true,
        data: { count: 5 },
      })

      const { countAssociations, count } = useAssociation(
        'user',
        { associationName: 'roles', sourceId }
      )

      const result = await countAssociations()

      expect(result).toBe(5)
      expect(count.value).toBe(5)
    })

    it('handles count error', async () => {
      const sourceId = ref(1)
      boService.countAssociationsV2.mockResolvedValue({
        success: false,
        message: 'Count failed',
      })

      const { countAssociations, error } = useAssociation(
        'user',
        { associationName: 'roles', sourceId }
      )

      const result = await countAssociations()

      expect(result).toBe(0)
      expect(error.value).toBe('Count failed')
    })

    it('requires associationName', async () => {
      const sourceId = ref(1)
      const { countAssociations, error } = useAssociation(
        'user',
        { sourceId }
      )

      const result = await countAssociations()

      expect(result).toBe(0)
      expect(error.value).toBe('associationName is required')
    })
  })

  describe('assign', () => {
    it('assigns successfully and refreshes', async () => {
      const sourceId = ref(1)
      boService.assignAssociationV2.mockResolvedValue({ success: true })
      boService.queryAssociationsV2.mockResolvedValue({
        success: true,
        data: { items: [], total: 0 },
      })
      boService.countAssociationsV2.mockResolvedValue({
        success: true,
        data: { count: 1 },
      })

      const { assign } = useAssociation(
        'user',
        { associationName: 'roles', sourceId }
      )

      const result = await assign(5)

      expect(boService.assignAssociationV2).toHaveBeenCalledWith(
        'user', 1, 'roles',
        { target_id: 5, metadata: {} }
      )
      expect(result).toBe(true)
    })

    it('handles assign failure', async () => {
      const sourceId = ref(1)
      boService.assignAssociationV2.mockResolvedValue({
        success: false,
        message: 'Already assigned',
      })

      const { assign, error } = useAssociation(
        'user',
        { associationName: 'roles', sourceId }
      )

      const result = await assign(5)

      expect(result).toBe(false)
      expect(error.value).toBe('Already assigned')
    })

    it('requires associationName', async () => {
      const sourceId = ref(1)
      const { assign, error } = useAssociation(
        'user',
        { sourceId }
      )

      const result = await assign(5)

      expect(result).toBe(false)
      expect(error.value).toBe('associationName is required')
    })
  })

  describe('unassign', () => {
    it('unassigns successfully and refreshes', async () => {
      const sourceId = ref(1)
      boService.unassignAssociationV2.mockResolvedValue({ success: true })
      boService.queryAssociationsV2.mockResolvedValue({
        success: true,
        data: { items: [], total: 0 },
      })
      boService.countAssociationsV2.mockResolvedValue({
        success: true,
        data: { count: 0 },
      })

      const { unassign } = useAssociation(
        'user',
        { associationName: 'roles', sourceId }
      )

      const result = await unassign(5)

      expect(boService.unassignAssociationV2).toHaveBeenCalledWith(
        'user', 1, 'roles',
        { association_record_id: 5 }
      )
      expect(result).toBe(true)
    })

    it('handles unassign failure', async () => {
      const sourceId = ref(1)
      boService.unassignAssociationV2.mockResolvedValue({
        success: false,
        message: 'Not assigned',
      })

      const { unassign, error } = useAssociation(
        'user',
        { associationName: 'roles', sourceId }
      )

      const result = await unassign(5)

      expect(result).toBe(false)
      expect(error.value).toBe('Not assigned')
    })
  })

  describe('batchAssign', () => {
    it('batch assigns successfully', async () => {
      const sourceId = ref(1)
      boService.batchAssignAssociationsV2.mockResolvedValue({
        success: true,
        data: { assigned: 3 },
      })
      boService.queryAssociationsV2.mockResolvedValue({
        success: true,
        data: { items: [], total: 0 },
      })
      boService.countAssociationsV2.mockResolvedValue({
        success: true,
        data: { count: 3 },
      })

      const { batchAssign } = useAssociation(
        'user',
        { associationName: 'roles', sourceId }
      )

      const result = await batchAssign([1, 2, 3])

      expect(boService.batchAssignAssociationsV2).toHaveBeenCalledWith(
        'user', 1, 'roles',
        { target_ids: [1, 2, 3], metadata: {} }
      )
      expect(result).toEqual({ assigned: 3 })
    })

    it('requires targetIds', async () => {
      const sourceId = ref(1)
      const { batchAssign, error } = useAssociation(
        'user',
        { associationName: 'roles', sourceId }
      )

      const result = await batchAssign([])

      expect(result).toBeNull()
      expect(error.value).toBe('targetIds is required')
    })

    it('requires associationName', async () => {
      const sourceId = ref(1)
      const { batchAssign, error } = useAssociation(
        'user',
        { sourceId }
      )

      const result = await batchAssign([1, 2])

      expect(result).toBeNull()
      expect(error.value).toBe('associationName is required')
    })
  })

  describe('batchUnassign', () => {
    it('batch unassigns successfully', async () => {
      const sourceId = ref(1)
      boService.batchUnassignAssociationsV2.mockResolvedValue({
        success: true,
        data: { unassigned: 2 },
      })
      boService.queryAssociationsV2.mockResolvedValue({
        success: true,
        data: { items: [], total: 0 },
      })
      boService.countAssociationsV2.mockResolvedValue({
        success: true,
        data: { count: 0 },
      })

      const { batchUnassign } = useAssociation(
        'user',
        { associationName: 'roles', sourceId }
      )

      const result = await batchUnassign([1, 2])

      expect(boService.batchUnassignAssociationsV2).toHaveBeenCalledWith(
        'user', 1, 'roles',
        { target_ids: [1, 2] }
      )
      expect(result).toEqual({ unassigned: 2 })
    })

    it('requires targetIds', async () => {
      const sourceId = ref(1)
      const { batchUnassign, error } = useAssociation(
        'user',
        { associationName: 'roles', sourceId }
      )

      const result = await batchUnassign([])

      expect(result).toBeNull()
      expect(error.value).toBe('targetIds is required')
    })
  })

  describe('selection management', () => {
    it('clears selection', () => {
      const sourceId = ref(1)
      const { selectedItems, clearSelection, toggleSelection } = useAssociation(
        'user',
        { associationName: 'roles', sourceId }
      )

      toggleSelection({ id: 1, name: 'admin' })
      expect(selectedItems.value).toHaveLength(1)

      clearSelection()
      expect(selectedItems.value).toHaveLength(0)
    })

    it('toggles selection', () => {
      const sourceId = ref(1)
      const { selectedItems, toggleSelection } = useAssociation(
        'user',
        { associationName: 'roles', sourceId }
      )

      toggleSelection({ id: 1, name: 'admin' })
      expect(selectedItems.value).toHaveLength(1)
      expect(selectedItems.value[0].id).toBe(1)

      toggleSelection({ id: 1, name: 'admin' })
      expect(selectedItems.value).toHaveLength(0)
    })

    it('selects all items', async () => {
      const sourceId = ref(1)
      boService.queryAssociationsV2.mockResolvedValue({
        success: true,
        data: {
          items: [{ id: 1, name: 'admin' }, { id: 2, name: 'user' }],
          total: 2,
        },
      })

      const { queryAssociations, selectAll, selectedItems, hasSelectedItems } = useAssociation(
        'user',
        { associationName: 'roles', sourceId }
      )

      await queryAssociations()
      selectAll()

      expect(selectedItems.value).toHaveLength(2)
      expect(hasSelectedItems.value).toBe(true)
    })

    it('unassigns selected items', async () => {
      const sourceId = ref(1)
      boService.queryAssociationsV2.mockResolvedValue({
        success: true,
        data: {
          items: [{ id: 1, name: 'admin' }, { id: 2, name: 'user' }],
          total: 2,
        },
      })
      boService.batchUnassignAssociationsV2.mockResolvedValue({
        success: true,
        data: { unassigned: 2 },
      })
      boService.countAssociationsV2.mockResolvedValue({
        success: true,
        data: { count: 0 },
      })

      const { queryAssociations, selectAll, unassignSelected, selectedItems } = useAssociation(
        'user',
        { associationName: 'roles', sourceId }
      )

      await queryAssociations()
      selectAll()
      const result = await unassignSelected()

      expect(result).toBe(true)
      expect(selectedItems.value).toHaveLength(0)
    })

    it('skips unassignSelected when no items selected', async () => {
      const sourceId = ref(1)
      const { unassignSelected } = useAssociation(
        'user',
        { associationName: 'roles', sourceId }
      )

      const result = await unassignSelected()

      expect(result).toBe(false)
      expect(boService.batchUnassignAssociationsV2).not.toHaveBeenCalled()
    })
  })

  describe('setSourceId', () => {
    it('updates source id', () => {
      const sourceId = ref(1)
      const { setSourceId } = useAssociation(
        'user',
        { associationName: 'roles', sourceId }
      )

      setSourceId(42)
      expect(sourceId.value).toBe(42)
    })
  })

  describe('loadPage', () => {
    it('calls queryAssociations with pagination', async () => {
      const sourceId = ref(1)
      boService.queryAssociationsV2.mockResolvedValue({
        success: true,
        data: { items: [], total: 0 },
      })

      const { loadPage } = useAssociation(
        'user',
        { associationName: 'roles', sourceId }
      )

      await loadPage(2, 25)

      expect(boService.queryAssociationsV2).toHaveBeenCalledWith(
        'user', 1, 'roles',
        { page: 2, page_size: 25 }
      )
    })
  })
})
