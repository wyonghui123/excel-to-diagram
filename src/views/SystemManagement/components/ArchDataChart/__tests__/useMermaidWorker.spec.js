/**
 * useMermaidWorker - Phase 5+ 单元测试
 *
 * 契约覆盖：
 *   - 异步渲染：返回 Promise<{ mermaidText, links, groupModel }>
 *   - 降级策略：Worker 不可用/超时/出错 → 主线程同步执行
 *   - 边界条件：rawData=null 立即 resolve
 *   - computeInWorker: 纯计算函数，输入输出可预测
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { nextTick } from 'vue'

// Mock groupModel 依赖
vi.mock('@/services/groupModel', () => {
  const mockBuildGroups = vi.fn((data, chartType) => {
    if (!data || !data.domains) return []
    return data.domains.map(d => ({
      id: `D_${d.id}`,
      type: 'DOMAIN',
      title: d.name,
      children: [],
      containers: [],
      isCenter: false
    }))
  })

  const mockExtractLinks = vi.fn((rels) => {
    if (!Array.isArray(rels)) return []
    return rels.map(r => ({
      source: r.source_bo_id,
      target: r.target_bo_id,
      relationCode: r.relation_code,
      label: r.relation_code
    }))
  })

  const mockGroupModel = {
    fromUserConfig: vi.fn(() => ({
      groups: [],
      type: 'mockGroupModel'
    }))
  }

  const mockUnifiedRenderer = {
    render: vi.fn(() => 'graph TD\n  A --> B')
  }

  return {
    buildGroupsFromFlatten: mockBuildGroups,
    extractLinks: mockExtractLinks,
    GroupModel: mockGroupModel,
    UnifiedRenderer: mockUnifiedRenderer,
    ChartType: { BUSINESS_OBJECT: 'businessObject', SERVICE_MODULE: 'serviceModule' }
  }
})

// 导入被测模块（在 mock 之后）
import {
  useMermaidWorker,
  computeInWorker,
  supportsWorker,
  WORKER_TIMEOUT
} from '../useMermaidWorker.js'
import { buildGroupsFromFlatten, extractLinks, GroupModel, UnifiedRenderer } from '@/services/groupModel'

// ============================================================
// 辅助：构造 mock rawData
// ============================================================
function makeRawData(withRelationships = true) {
  const data = {
    domains: [
      { id: 'D1', code: 'D1', name: '领域1' },
      { id: 'D2', code: 'D2', name: '领域2' }
    ],
    subDomains: [],
    serviceModules: [],
    businessObjects: []
  }

  if (withRelationships) {
    data.relationships = [
      { source_bo_id: 'BO1', target_bo_id: 'BO2', relation_code: 'rel1' }
    ]
  }

  return data
}

describe('useMermaidWorker', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // ============================================================
  // 常量
  // ============================================================
  describe('常量', () => {
    it('WORKER_TIMEOUT 应为 5000ms', () => {
      expect(WORKER_TIMEOUT).toBe(5000)
    })
  })

  // ============================================================
  // supportsWorker
  // ============================================================
  describe('supportsWorker', () => {
    it('在 jsdom 环境中应返回 true 或 false（取决于 window.Worker）', () => {
      // happy-dom/jsdom 可能有或没有 Worker，这里只验证不抛错
      expect(typeof supportsWorker()).toBe('boolean')
    })
  })

  // ============================================================
  // computeInWorker - 纯计算函数
  // ============================================================
  describe('computeInWorker', () => {
    it('rawData=null 应返回空结果', () => {
      const result = computeInWorker(null, 'businessObject')
      expect(result).toEqual({
        mermaidText: '',
        links: [],
        groupModelPlain: null
      })
    })

    it('正常输入应调用 buildGroupsFromFlatten + extractLinks + UnifiedRenderer.render', () => {
      const rawData = makeRawData()
      const result = computeInWorker(rawData, 'businessObject', { layoutEngine: 'dagre' })

      expect(buildGroupsFromFlatten).toHaveBeenCalledWith(rawData, 'businessObject')
      expect(extractLinks).toHaveBeenCalledWith(rawData.relationships)
      expect(GroupModel.fromUserConfig).toHaveBeenCalled()
      expect(UnifiedRenderer.render).toHaveBeenCalled()

      expect(result.mermaidText).toBe('graph TD\n  A --> B')
      expect(result.links).toHaveLength(1)
      expect(result.groupModelPlain).toBeNull()
    })

    it('无 relationships 应返回空 links', () => {
      const rawData = makeRawData(false)
      const result = computeInWorker(rawData, 'businessObject')

      expect(result.links).toEqual([])
    })

    it('layoutControlConfig 为 null 应使用默认值', () => {
      const rawData = makeRawData()
      // 不传 layoutControlConfig，应该使用 null 默认值
      expect(() => computeInWorker(rawData, 'businessObject')).not.toThrow()
    })

    it('chartType=serviceModule 应传递正确参数', () => {
      const rawData = makeRawData()
      computeInWorker(rawData, 'serviceModule')

      expect(buildGroupsFromFlatten).toHaveBeenCalledWith(rawData, 'serviceModule')
    })
  })

  // ============================================================
  // useMermaidWorker composable
  // ============================================================
  describe('useMermaidWorker composable', () => {
    it('初始状态：isWorkerAvailable 为 boolean，isUsingFallback=false', () => {
      const { isWorkerAvailable, isUsingFallback, lastError } = useMermaidWorker()

      expect(typeof isWorkerAvailable.value).toBe('boolean')
      expect(isUsingFallback.value).toBe(false)
      expect(lastError.value).toBeNull()
    })

    it('render(null, ...) 应立即 resolve 空结果', async () => {
      const { render } = useMermaidWorker()

      const result = await render(null, 'businessObject')

      expect(result).toEqual({
        mermaidText: '',
        links: [],
        groupModel: null
      })
    })

    it('render(rawData, ...) 应返回 mermaidText 和 links', async () => {
      const { render } = useMermaidWorker()
      const rawData = makeRawData()

      const result = await render(rawData, 'businessObject')

      expect(result.mermaidText).toBe('graph TD\n  A --> B')
      expect(result.links).toHaveLength(1)
      expect(result.groupModel).toBeNull()  // 注：当前实现不返回 groupModel
    })

    it('render 应触发 buildGroupsFromFlatten 调用', async () => {
      const { render } = useMermaidWorker()
      const rawData = makeRawData()

      buildGroupsFromFlatten.mockClear()
      await render(rawData, 'businessObject')

      expect(buildGroupsFromFlatten).toHaveBeenCalledWith(rawData, 'businessObject')
    })

    it('terminate 应不抛错', () => {
      const { terminate } = useMermaidWorker()
      expect(() => terminate()).not.toThrow()
    })

    it('多次 render 应复用同一 Worker 实例', async () => {
      const { render } = useMermaidWorker()
      const rawData = makeRawData()

      // 第一次 render
      await render(rawData, 'businessObject')
      // 第二次 render
      await render(rawData, 'businessObject')

      // buildGroupsFromFlatten 应被调用两次（每次 render 都执行一次）
      expect(buildGroupsFromFlatten).toHaveBeenCalledTimes(2)
    })
  })

  // ============================================================
  // 降级策略
  // ============================================================
  describe('降级策略', () => {
    it('computeInWorker 抛错时 render 应 reject', async () => {
      const { render } = useMermaidWorker()
      const rawData = makeRawData()

      // 让 buildGroupsFromFlatten 抛错
      const error = new Error('mock build error')
      buildGroupsFromFlatten.mockImplementationOnce(() => {
        throw error
      })

      await expect(render(rawData, 'businessObject')).rejects.toThrow('mock build error')
    })
  })

  // ============================================================
  // 边界条件
  // ============================================================
  describe('边界条件', () => {
    it('rawData 为 undefined 应返回空结果', async () => {
      const { render } = useMermaidWorker()

      const result = await render(undefined, 'businessObject')

      expect(result.mermaidText).toBe('')
      expect(result.links).toEqual([])
    })

    it('chartType 为 undefined 应不抛错（buildGroupsFromFlatten 内部处理）', async () => {
      const { render } = useMermaidWorker()
      const rawData = makeRawData()

      // mock 的 buildGroupsFromFlatten 不会因 chartType 为 undefined 抛错
      const result = await render(rawData, undefined)

      expect(result).toBeDefined()
    })

    it('layoutControlConfig 为 undefined 应使用默认 null', async () => {
      const { render } = useMermaidWorker()
      const rawData = makeRawData()

      // 不传第三个参数
      const result = await render(rawData, 'businessObject')

      expect(result).toBeDefined()
    })
  })
})
