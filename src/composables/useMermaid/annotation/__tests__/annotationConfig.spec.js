import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import {
  CATEGORY_CONFIG,
  TYPE_CONFIG,
  PANEL_POSITION,
  DEFAULT_CATEGORY,
  getCategoryConfig,
  registerCategoryConfig,
  registerCategoryConfigs
} from '@/composables/useMermaid/annotation/annotationConfig'

describe('annotationConfig', () => {
  describe('默认配置', () => {
    it('应该导出 CATEGORY_CONFIG', () => {
      expect(CATEGORY_CONFIG).toBeDefined()
      expect(typeof CATEGORY_CONFIG).toBe('object')
    })

    it('应该包含默认的 4 种分类', () => {
      expect(CATEGORY_CONFIG.important).toBeDefined()
      expect(CATEGORY_CONFIG.warning).toBeDefined()
      expect(CATEGORY_CONFIG.info).toBeDefined()
      expect(CATEGORY_CONFIG.tip).toBeDefined()
    })

    it('每种分类应该包含必要的属性', () => {
      const category = CATEGORY_CONFIG.important
      expect(category).toHaveProperty('label')
      expect(category).toHaveProperty('bg')
      expect(category).toHaveProperty('border')
    })

    it('默认分类不应该包含 icon 属性', () => {
      expect(CATEGORY_CONFIG.important).not.toHaveProperty('icon')
      expect(CATEGORY_CONFIG.warning).not.toHaveProperty('icon')
      expect(CATEGORY_CONFIG.info).not.toHaveProperty('icon')
      expect(CATEGORY_CONFIG.tip).not.toHaveProperty('icon')
    })

    it('应该导出 TYPE_CONFIG', () => {
      expect(TYPE_CONFIG).toBeDefined()
      expect(TYPE_CONFIG.container).toBeDefined()
      expect(TYPE_CONFIG.node).toBeDefined()
      expect(TYPE_CONFIG.relation).toBeDefined()
    })

    it('应该导出 PANEL_POSITION', () => {
      expect(PANEL_POSITION).toBeDefined()
      expect(PANEL_POSITION.BOTTOM).toBe('bottom')
      expect(PANEL_POSITION.RIGHT).toBe('right')
      expect(PANEL_POSITION.LEFT).toBe('left')
    })

    it('应该导出 DEFAULT_CATEGORY', () => {
      expect(DEFAULT_CATEGORY).toBe('info')
    })
  })

  describe('getCategoryConfig', () => {
    it('应该返回指定分类的配置', () => {
      const config = getCategoryConfig('important')
      expect(config).toBeDefined()
      expect(config.label).toBe('重要')
    })

    it('不存在的分类应该返回 null', () => {
      const config = getCategoryConfig('nonexistent')
      expect(config).toBeNull()
    })

    it('不存在的分类不应该回退到默认', () => {
      const config = getCategoryConfig('nonexistent')
      expect(config).not.toEqual(getCategoryConfig(DEFAULT_CATEGORY))
    })

    it('应该返回 info 分类的配置作为默认值行为', () => {
      const infoConfig = getCategoryConfig('info')
      expect(infoConfig.label).toBe('信息')
    })
  })

  describe('动态配置注册', () => {
    afterEach(() => {
      // 清理可能添加的动态配置
    })

    it('registerCategoryConfig 应该注册新的分类配置', () => {
      const newConfig = {
        label: '审查',
        bg: '#f0f0f0',
        border: '#666666'
      }

      registerCategoryConfig('review', newConfig)

      const config = getCategoryConfig('review')
      expect(config).toBeDefined()
      expect(config.label).toBe('审查')
      expect(config.bg).toBe('#f0f0f0')
      expect(config.border).toBe('#666666')
    })

    it('registerCategoryConfigs 应该批量注册分类配置', () => {
      const configs = {
        design: {
          label: '设计',
          bg: '#e3f2fd',
          border: '#1976d2'
        },
        implement: {
          label: '实现',
          bg: '#e8f5e9',
          border: '#388e3c'
        }
      }

      registerCategoryConfigs(configs)

      const designConfig = getCategoryConfig('design')
      expect(designConfig).toBeDefined()
      expect(designConfig.label).toBe('设计')

      const implementConfig = getCategoryConfig('implement')
      expect(implementConfig).toBeDefined()
      expect(implementConfig.label).toBe('实现')
    })

    it('动态配置应该覆盖默认配置', () => {
      const overrideConfig = {
        label: '星标',
        bg: '#fff9c4',
        border: '#f57f17'
      }

      registerCategoryConfig('important', overrideConfig)

      const config = getCategoryConfig('important')
      expect(config.label).toBe('星标')
    })

    it('CATEGORY_CONFIG 代理应该支持动态添加的属性', () => {
      const newConfig = {
        label: '备注',
        bg: '#fff3e0',
        border: '#e65100'
      }

      registerCategoryConfig('note', newConfig)

      expect(CATEGORY_CONFIG.note).toBeDefined()
      expect(CATEGORY_CONFIG.note.label).toBe('备注')
    })

    it('应该保留原有默认分类', () => {
      const config = getCategoryConfig('warning')
      expect(config).toBeDefined()
      expect(config.label).toBe('警告')
    })
  })

  describe('配置完整性', () => {
    const defaultCategories = ['important', 'warning', 'info', 'tip']

    defaultCategories.forEach(category => {
      it(`${category} 分类应该有完整的配置`, () => {
        const config = CATEGORY_CONFIG[category]
        expect(config).toBeDefined()
        expect(config.label).toBeTruthy()
        expect(config.bg).toMatch(/^#[0-9a-f]{6}$/i)
        expect(config.border).toMatch(/^#[0-9a-f]{6}$/i)
      })
    })
  })
})
