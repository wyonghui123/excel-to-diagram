/**
 * useRenderCache - Phase 5+ 单元测试
 *
 * 契约覆盖：
 *   - LRU 策略：get 时移到末尾，超过 maxSize 时删除头部
 *   - djb2 哈希函数：相同输入相同输出，不同输入不同输出
 *   - 缓存键：chartType + hash
 *   - 边界条件：maxSize=0/负数 → 不缓存；空 mermaidText → miss；超大 SVG → 不缓存
 *   - 统计信息：hits/misses/hitRate 正确计算
 */
import { describe, it, expect, beforeEach } from 'vitest'
import {
  useRenderCache,
  djb2Hash,
  buildCacheKey,
  DEFAULT_MAX_SIZE,
  MAX_SVG_SIZE
} from '../useRenderCache.js'

describe('useRenderCache', () => {
  // ============================================================
  // djb2 哈希函数
  // ============================================================
  describe('djb2Hash', () => {
    it('空字符串应返回 "0"', () => {
      expect(djb2Hash('')).toBe('0')
    })

    it('相同输入应返回相同输出', () => {
      const h1 = djb2Hash('graph TD\n  A --> B')
      const h2 = djb2Hash('graph TD\n  A --> B')
      expect(h1).toBe(h2)
    })

    it('不同输入应返回不同输出', () => {
      const h1 = djb2Hash('graph TD\n  A --> B')
      const h2 = djb2Hash('graph TD\n  A --> C')
      expect(h1).not.toBe(h2)
    })

    it('应返回 16 进制字符串', () => {
      const h = djb2Hash('test')
      // 16 进制字符：0-9, a-f
      expect(/^[0-9a-f]+$/.test(h)).toBe(true)
    })

    it('长字符串应正常哈希不抛错', () => {
      const longStr = 'A'.repeat(10000)
      expect(() => djb2Hash(longStr)).not.toThrow()
    })
  })

  // ============================================================
  // buildCacheKey
  // ============================================================
  describe('buildCacheKey', () => {
    it('应组合 chartType 和 hash', () => {
      const key = buildCacheKey('graph TD', 'businessObject')
      expect(key).toMatch(/^businessObject:[0-9a-f]+$/)
    })

    it('不同 chartType 应产生不同 key', () => {
      const k1 = buildCacheKey('graph TD', 'businessObject')
      const k2 = buildCacheKey('graph TD', 'serviceModule')
      expect(k1).not.toBe(k2)
    })

    it('chartType 为空时应使用 default', () => {
      const key = buildCacheKey('graph TD', '')
      expect(key).toMatch(/^default:[0-9a-f]+$/)
    })

    it('相同 mermaidText + chartType 应产生相同 key', () => {
      const k1 = buildCacheKey('graph TD', 'businessObject')
      const k2 = buildCacheKey('graph TD', 'businessObject')
      expect(k1).toBe(k2)
    })
  })

  // ============================================================
  // 常量
  // ============================================================
  describe('常量', () => {
    it('DEFAULT_MAX_SIZE 应为 10', () => {
      expect(DEFAULT_MAX_SIZE).toBe(10)
    })

    it('MAX_SVG_SIZE 应为 10MB', () => {
      expect(MAX_SVG_SIZE).toBe(10 * 1024 * 1024)
    })
  })

  // ============================================================
  // 基础行为：get / set
  // ============================================================
  describe('基础 get / set', () => {
    let cache

    beforeEach(() => {
      cache = useRenderCache(10)
    })

    it('未命中时应返回 { hit: false }', () => {
      const result = cache.get('graph TD', 'businessObject')
      expect(result.hit).toBe(false)
      expect(result.svg).toBeUndefined()
    })

    it('命中时应返回 { hit: true, svg }', () => {
      const mermaidText = 'graph TD\n  A --> B'
      const svg = '<svg></svg>'
      cache.set(mermaidText, 'businessObject', svg)

      const result = cache.get(mermaidText, 'businessObject')
      expect(result.hit).toBe(true)
      expect(result.svg).toBe(svg)
    })

    it('不同 chartType 应独立缓存', () => {
      const mermaidText = 'graph TD\n  A --> B'
      cache.set(mermaidText, 'businessObject', '<svg id="bo">')
      cache.set(mermaidText, 'serviceModule', '<svg id="sm">')

      expect(cache.get(mermaidText, 'businessObject').svg).toBe('<svg id="bo">')
      expect(cache.get(mermaidText, 'serviceModule').svg).toBe('<svg id="sm">')
    })

    it('覆盖已存在的 key 应更新 svg', () => {
      const mermaidText = 'graph TD\n  A --> B'
      cache.set(mermaidText, 'businessObject', '<svg id="v1">')
      cache.set(mermaidText, 'businessObject', '<svg id="v2">')

      expect(cache.get(mermaidText, 'businessObject').svg).toBe('<svg id="v2">')
    })
  })

  // ============================================================
  // LRU 策略：get 时移到末尾，超容量时删除头部
  // ============================================================
  describe('LRU 策略', () => {
    it('get 时应将条目移到末尾（标记最近使用）', () => {
      const cache = useRenderCache(3)
      cache.set('A', 'businessObject', '<svg>A</svg>')
      cache.set('B', 'businessObject', '<svg>B</svg>')
      cache.set('C', 'businessObject', '<svg>C</svg>')

      // 访问 A → A 移到末尾
      cache.get('A', 'businessObject')

      // 插入 D → 应淘汰 B（最久未使用）
      cache.set('D', 'businessObject', '<svg>D</svg>')

      // B 应该被淘汰
      expect(cache.get('B', 'businessObject').hit).toBe(false)
      // A 应该还在（刚被访问）
      expect(cache.get('A', 'businessObject').hit).toBe(true)
      // C 应该还在
      expect(cache.get('C', 'businessObject').hit).toBe(true)
      // D 应该在
      expect(cache.get('D', 'businessObject').hit).toBe(true)
    })

    it('超容量时应删除最久未使用的条目', () => {
      const cache = useRenderCache(2)
      cache.set('A', 'businessObject', '<svg>A</svg>')
      cache.set('B', 'businessObject', '<svg>B</svg>')

      // 插入 C → 应淘汰 A
      cache.set('C', 'businessObject', '<svg>C</svg>')

      expect(cache.get('A', 'businessObject').hit).toBe(false)
      expect(cache.get('B', 'businessObject').hit).toBe(true)
      expect(cache.get('C', 'businessObject').hit).toBe(true)
    })

    it('maxSize=1 时只保留最近一个', () => {
      const cache = useRenderCache(1)
      cache.set('A', 'businessObject', '<svg>A</svg>')
      cache.set('B', 'businessObject', '<svg>B</svg>')

      expect(cache.get('A', 'businessObject').hit).toBe(false)
      expect(cache.get('B', 'businessObject').hit).toBe(true)
    })

    it('重复 set 同一 key 不应增加容量', () => {
      const cache = useRenderCache(2)
      cache.set('A', 'businessObject', '<svg>A</svg>')
      cache.set('A', 'businessObject', '<svg>A-v2</svg>')
      cache.set('A', 'businessObject', '<svg>A-v3</svg>')

      expect(cache.stats.value.size).toBe(1)
      expect(cache.get('A', 'businessObject').svg).toBe('<svg>A-v3</svg>')
    })
  })

  // ============================================================
  // 边界条件
  // ============================================================
  describe('边界条件', () => {
    it('maxSize=0 时不应缓存', () => {
      const cache = useRenderCache(0)
      cache.set('A', 'businessObject', '<svg>A</svg>')

      expect(cache.get('A', 'businessObject').hit).toBe(false)
      expect(cache.stats.value.size).toBe(0)
    })

    it('maxSize=负数 时不应缓存', () => {
      const cache = useRenderCache(-5)
      cache.set('A', 'businessObject', '<svg>A</svg>')

      expect(cache.get('A', 'businessObject').hit).toBe(false)
    })

    it('空 mermaidText → 不缓存且 miss', () => {
      const cache = useRenderCache(10)
      cache.set('', 'businessObject', '<svg></svg>')

      expect(cache.get('', 'businessObject').hit).toBe(false)
    })

    it('非字符串 mermaidText → 不缓存且 miss', () => {
      const cache = useRenderCache(10)
      cache.set(null, 'businessObject', '<svg></svg>')
      cache.set(undefined, 'businessObject', '<svg></svg>')
      cache.set(123, 'businessObject', '<svg></svg>')

      expect(cache.get(null, 'businessObject').hit).toBe(false)
      expect(cache.get(undefined, 'businessObject').hit).toBe(false)
      expect(cache.get(123, 'businessObject').hit).toBe(false)
    })

    it('超大 SVG（>10MB）应不缓存', () => {
      const cache = useRenderCache(10)
      // 构造 > 10MB 的字符串
      const hugeSvg = 'x'.repeat(MAX_SVG_SIZE + 1)

      cache.set('A', 'businessObject', hugeSvg)

      expect(cache.get('A', 'businessObject').hit).toBe(false)
      expect(cache.stats.value.size).toBe(0)
    })

    it('SVG 恰好等于 10MB 应可缓存', () => {
      const cache = useRenderCache(10)
      const exactSizeSvg = 'x'.repeat(MAX_SVG_SIZE)

      cache.set('A', 'businessObject', exactSizeSvg)

      expect(cache.get('A', 'businessObject').hit).toBe(true)
    })

    it('非字符串 SVG 应不缓存', () => {
      const cache = useRenderCache(10)
      cache.set('A', 'businessObject', null)
      cache.set('A', 'businessObject', undefined)
      cache.set('A', 'businessObject', 123)

      expect(cache.get('A', 'businessObject').hit).toBe(false)
    })
  })

  // ============================================================
  // 统计信息
  // ============================================================
  describe('stats 统计信息', () => {
    it('初始状态应为全 0', () => {
      const cache = useRenderCache(10)
      expect(cache.stats.value).toEqual({
        size: 0,
        hits: 0,
        misses: 0,
        hitRate: 0
      })
    })

    it('hit 应正确计数', () => {
      const cache = useRenderCache(10)
      cache.set('A', 'businessObject', '<svg>A</svg>')

      cache.get('A', 'businessObject')  // hit
      cache.get('A', 'businessObject')  // hit

      expect(cache.stats.value.hits).toBe(2)
      expect(cache.stats.value.misses).toBe(0)
      expect(cache.stats.value.hitRate).toBe(1)
    })

    it('miss 应正确计数', () => {
      const cache = useRenderCache(10)

      cache.get('A', 'businessObject')  // miss
      cache.get('B', 'businessObject')  // miss

      expect(cache.stats.value.hits).toBe(0)
      expect(cache.stats.value.misses).toBe(2)
      expect(cache.stats.value.hitRate).toBe(0)
    })

    it('混合命中应正确计算 hitRate', () => {
      const cache = useRenderCache(10)
      cache.set('A', 'businessObject', '<svg>A</svg>')

      cache.get('A', 'businessObject')  // hit
      cache.get('A', 'businessObject')  // hit
      cache.get('B', 'businessObject')  // miss

      expect(cache.stats.value.hits).toBe(2)
      expect(cache.stats.value.misses).toBe(1)
      expect(cache.stats.value.hitRate).toBeCloseTo(2 / 3, 5)
    })

    it('size 应反映当前缓存条目数', () => {
      const cache = useRenderCache(10)
      expect(cache.stats.value.size).toBe(0)

      cache.set('A', 'businessObject', '<svg>A</svg>')
      expect(cache.stats.value.size).toBe(1)

      cache.set('B', 'businessObject', '<svg>B</svg>')
      expect(cache.stats.value.size).toBe(2)

      // 覆盖 A，size 不变
      cache.set('A', 'businessObject', '<svg>A-v2</svg>')
      expect(cache.stats.value.size).toBe(2)
    })

    it('LRU 淘汰应更新 size', () => {
      const cache = useRenderCache(2)
      cache.set('A', 'businessObject', '<svg>A</svg>')
      cache.set('B', 'businessObject', '<svg>B</svg>')
      expect(cache.stats.value.size).toBe(2)

      // 插入 C → 淘汰 A
      cache.set('C', 'businessObject', '<svg>C</svg>')
      expect(cache.stats.value.size).toBe(2)
    })
  })

  // ============================================================
  // clear 方法
  // ============================================================
  describe('clear', () => {
    it('应清空所有缓存', () => {
      const cache = useRenderCache(10)
      cache.set('A', 'businessObject', '<svg>A</svg>')
      cache.set('B', 'businessObject', '<svg>B</svg>')

      cache.clear()

      expect(cache.stats.value.size).toBe(0)
      expect(cache.get('A', 'businessObject').hit).toBe(false)
      expect(cache.get('B', 'businessObject').hit).toBe(false)
    })

    it('应重置统计信息', () => {
      const cache = useRenderCache(10)
      cache.set('A', 'businessObject', '<svg>A</svg>')
      cache.get('A', 'businessObject')  // hit
      cache.get('B', 'businessObject')  // miss

      cache.clear()

      expect(cache.stats.value).toEqual({
        size: 0,
        hits: 0,
        misses: 0,
        hitRate: 0
      })
    })

    it('clear 后应能继续使用', () => {
      const cache = useRenderCache(10)
      cache.set('A', 'businessObject', '<svg>A</svg>')
      cache.clear()

      cache.set('B', 'businessObject', '<svg>B</svg>')
      expect(cache.get('B', 'businessObject').hit).toBe(true)
    })
  })

  // ============================================================
  // 实际场景模拟
  // ============================================================
  describe('实际场景', () => {
    it('颜色配置变更：同 mermaidText 反复 set+get 应命中', () => {
      // 模拟：颜色变化 → useReactiveRenderer 输出相同 mermaidText（结构不变）
      //       → 缓存命中，跳过 mermaid.run()
      const cache = useRenderCache(10)
      const mermaidText = 'graph TD\n  A --> B\n  style A fill:#f9f'

      cache.set(mermaidText, 'businessObject', '<svg>rendered</svg>')

      // 第二次相同 mermaidText → 命中
      const result = cache.get(mermaidText, 'businessObject')
      expect(result.hit).toBe(true)
      expect(result.svg).toBe('<svg>rendered</svg>')
    })

    it('scopeIds 切换：mermaidText 变化 → miss', () => {
      // 模拟：scopeIds 变化 → mermaidText 变化 → 缓存未命中
      const cache = useRenderCache(10)
      cache.set('graph TD\n  A --> B', 'businessObject', '<svg>1</svg>')

      // 不同 mermaidText → miss
      const result = cache.get('graph TD\n  A --> C', 'businessObject')
      expect(result.hit).toBe(false)
    })

    it('5000+ 节点大数据量应正常缓存（不超 10MB 限制）', () => {
      // 模拟：5000 节点 SVG 大约 5MB（估算）
      const cache = useRenderCache(5)
      const bigSvg = '<svg>' + '<g class="node"></g>'.repeat(5000) + '</svg>'

      cache.set('big-graph', 'businessObject', bigSvg)

      const result = cache.get('big-graph', 'businessObject')
      expect(result.hit).toBe(true)
      expect(result.svg).toBe(bigSvg)
    })
  })
})
