import { describe, it, expect, vi, beforeEach, afterEach, afterAll } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { setActivePinia, createPinia } from 'pinia'
import SystemSettings from '@/views/SystemManagement/SystemSettings.vue'

const _origFetch = globalThis.fetch
const _origResizeObserver = globalThis.ResizeObserver
const _origMatchMedia = globalThis.matchMedia

describe('SystemSettings', () => {
  const originalLocalStorage = global.localStorage

  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    // 修复 PR-TestFix-16: 在 ESM 严格模式下 global.* 是 readonly，
    // 必须用 Object.defineProperty 重新定义
    Object.defineProperty(global, 'localStorage', {
      writable: true,
      configurable: true,
      value: {
        getItem: vi.fn(),
        setItem: vi.fn(),
        removeItem: vi.fn(),
        clear: vi.fn()
      }
    })
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({ success: true, data: [], message: '' })
    })
    globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
    if (!globalThis.matchMedia) {
      globalThis.matchMedia = vi.fn().mockImplementation((q) => ({
        matches: false, media: q, onchange: null,
        addListener: vi.fn(), removeListener: vi.fn(),
        addEventListener: vi.fn(), removeEventListener: vi.fn(),
        dispatchEvent: vi.fn()
      }))
    }
  })

  afterEach(() => {
    global.localStorage = originalLocalStorage
  })

  afterAll(() => {
    globalThis.fetch = _origFetch
    globalThis.ResizeObserver = _origResizeObserver
    globalThis.matchMedia = _origMatchMedia
  })

  describe('基本渲染', () => {
    it('应该渲染系统设置容器', () => {
      const wrapper = mount(SystemSettings)
      expect(wrapper.find('.system-settings').exists()).toBe(true)
      expect(wrapper.find('.ss-container').exists()).toBe(true)
    })

    it('应该渲染侧边栏菜单', () => {
      const wrapper = mount(SystemSettings)
      expect(wrapper.find('.ss-sidebar').exists()).toBe(true)
      expect(wrapper.find('.ss-nav').exists()).toBe(true)
    })

    it('应该渲染所有菜单项', () => {
      const wrapper = mount(SystemSettings)
      const menuItems = wrapper.findAll('.ss-nav-item')
      expect(menuItems.length).toBe(6)
    })

    it('默认应该显示 AI 配置', () => {
      const wrapper = mount(SystemSettings)
      expect(wrapper.find('.section-title').text()).toBe('AI 服务配置')
    })
  })

  describe('菜单切换', () => {
    it('点击飞书集成应该显示飞书配置', async () => {
      const wrapper = mount(SystemSettings)

      const menuItems = wrapper.findAll('.ss-nav-item')
      await menuItems[1].trigger('click')

      expect(wrapper.find('.section-title').text()).toBe('飞书集成配置')
    })

    it('点击图表配置应该显示图表设置', async () => {
      const wrapper = mount(SystemSettings)

      const menuItems = wrapper.findAll('.ss-nav-item')
      await menuItems[2].trigger('click')

      expect(wrapper.find('.section-title').text()).toBe('图表默认配置')
    })

    it('点击数据验证应该显示验证设置', async () => {
      const wrapper = mount(SystemSettings)

      const menuItems = wrapper.findAll('.ss-nav-item')
      await menuItems[3].trigger('click')

      expect(wrapper.find('.section-title').text()).toBe('数据验证配置')
    })

    it('点击导出配置应该显示导出设置', async () => {
      const wrapper = mount(SystemSettings)

      const menuItems = wrapper.findAll('.ss-nav-item')
      await menuItems[4].trigger('click')

      expect(wrapper.find('.section-title').text()).toBe('导出配置')
    })

    it('点击关于应该显示关于信息', async () => {
      const wrapper = mount(SystemSettings)

      const menuItems = wrapper.findAll('.ss-nav-item')
      await menuItems[5].trigger('click')

      expect(wrapper.find('.about-content h3').text()).toBe('ArchWorkspace')
    })
  })

  describe('AI 配置', () => {
    it('应该显示 AI 服务提供商选项', () => {
      const wrapper = mount(SystemSettings)
      const radioOptions = wrapper.findAll('.radio-option')
      expect(radioOptions.length).toBe(2)
    })

    it('应该默认选择智谱 AI', () => {
      const wrapper = mount(SystemSettings)
      const zhipuRadio = wrapper.find('input[value="zhipu"]')
      expect(zhipuRadio.element.checked).toBe(true)
    })

    it('切换到 DeepSeek 应该更新选择', async () => {
      const wrapper = mount(SystemSettings)

      const deepseekRadio = wrapper.find('input[value="deepseek"]')
      await deepseekRadio.setChecked()

      const zhipuRadio = wrapper.find('input[value="zhipu"]')
      expect(zhipuRadio.element.checked).toBe(false)
    })

    it('应该显示智谱 API Key 输入框', () => {
      const wrapper = mount(SystemSettings)
      expect(wrapper.find('input[placeholder="请输入智谱 API Key"]').exists()).toBe(true)
    })

    it('应该显示 DeepSeek API Key 输入框', () => {
      const wrapper = mount(SystemSettings)
      expect(wrapper.find('input[placeholder="请输入 DeepSeek API Key"]').exists()).toBe(true)
    })

    it('应该显示 AI 模型选择', () => {
      const wrapper = mount(SystemSettings)
      expect(wrapper.find('.form-select').exists()).toBe(true)
    })
  })

  describe('飞书集成配置', () => {
    it('应该显示飞书配置表单', async () => {
      const wrapper = mount(SystemSettings)

      const menuItems = wrapper.findAll('.ss-nav-item')
      await menuItems[1].trigger('click')

      expect(wrapper.find('input[placeholder="请输入飞书 App ID"]').exists()).toBe(true)
      expect(wrapper.find('input[placeholder="请输入飞书 App Secret"]').exists()).toBe(true)
      expect(wrapper.find('input[placeholder="请输入群ID或用户ID"]').exists()).toBe(true)
    })

    it('应该显示启用飞书集成复选框', async () => {
      const wrapper = mount(SystemSettings)

      const menuItems = wrapper.findAll('.ss-nav-item')
      await menuItems[1].trigger('click')

      expect(wrapper.find('.form-checkbox').exists()).toBe(true)
    })

    it('应该显示测试连接按钮', async () => {
      const wrapper = mount(SystemSettings)

      const menuItems = wrapper.findAll('.ss-nav-item')
      await menuItems[1].trigger('click')

      const testBtn = wrapper.findAll('button').find(b => b.text().includes('测试连接'))
      expect(testBtn).toBeDefined()
      expect(testBtn.text()).toContain('测试连接')
    })
  })

  describe('图表配置', () => {
    it('应该显示配色方案选择', async () => {
      const wrapper = mount(SystemSettings)

      const menuItems = wrapper.findAll('.ss-nav-item')
      await menuItems[2].trigger('click')

      expect(wrapper.findAll('.form-select').length).toBeGreaterThan(0)
    })

    it('应该显示颜色选项', async () => {
      const wrapper = mount(SystemSettings)

      const menuItems = wrapper.findAll('.ss-nav-item')
      await menuItems[2].trigger('click')

      expect(wrapper.findAll('.color-option').length).toBe(3)
    })

    it('应该显示颜色选择器', async () => {
      const wrapper = mount(SystemSettings)

      const menuItems = wrapper.findAll('.ss-nav-item')
      await menuItems[2].trigger('click')

      expect(wrapper.find('.form-color-picker').exists()).toBe(true)
    })
  })

  describe('数据验证配置', () => {
    it('应该显示验证选项复选框', async () => {
      const wrapper = mount(SystemSettings)

      const menuItems = wrapper.findAll('.ss-nav-item')
      await menuItems[3].trigger('click')

      const checkboxes = wrapper.findAll('.form-checkbox')
      expect(checkboxes.length).toBe(4)
    })

    it('应该默认启用外键检查', async () => {
      const wrapper = mount(SystemSettings)

      const menuItems = wrapper.findAll('.ss-nav-item')
      await menuItems[3].trigger('click')

      const foreignKeyCheckbox = wrapper.find('input[type="checkbox"]')
      expect(foreignKeyCheckbox.element.checked).toBe(true)
    })
  })

  describe('导出配置', () => {
    it('应该显示导出格式选择', async () => {
      const wrapper = mount(SystemSettings)

      const menuItems = wrapper.findAll('.ss-nav-item')
      await menuItems[4].trigger('click')

      expect(wrapper.findAll('.form-select').length).toBeGreaterThan(0)
    })

    it('应该显示包含背景复选框', async () => {
      const wrapper = mount(SystemSettings)

      const menuItems = wrapper.findAll('.ss-nav-item')
      await menuItems[4].trigger('click')

      expect(wrapper.find('.form-checkbox').exists()).toBe(true)
    })
  })

  describe('保存配置', () => {
    it('应该显示保存按钮', () => {
      const wrapper = mount(SystemSettings)
      const saveBtn = wrapper.findAll('button').find(b => b.text().includes('保存配置'))
      expect(saveBtn).toBeDefined()
      expect(saveBtn.text()).toContain('保存配置')
    })

    it('应该显示恢复默认按钮', () => {
      const wrapper = mount(SystemSettings)
      const resetBtn = wrapper.findAll('button').find(b => b.text().includes('恢复默认'))
      expect(resetBtn).toBeDefined()
      expect(resetBtn.text()).toContain('恢复默认')
    })

    it('保存时应该存储到 localStorage', async () => {
      global.localStorage.getItem.mockReturnValue(null)

      const wrapper = mount(SystemSettings)
      const saveBtn = wrapper.findAll('button').find(b => b.text().includes('保存配置'))
      await saveBtn.trigger('click')

      await new Promise(resolve => setTimeout(resolve, 600))

      expect(global.localStorage.setItem).toHaveBeenCalledWith(
        'archWorkspaceConfig',
        expect.any(String)
      )
    })

    it('保存成功时应该显示成功提示', async () => {
      global.localStorage.getItem.mockReturnValue(null)

      const wrapper = mount(SystemSettings)
      const saveBtn = wrapper.findAll('button').find(b => b.text().includes('保存配置'))
      await saveBtn.trigger('click')

      await new Promise(resolve => setTimeout(resolve, 600))

      // 成功提示使用 Teleport 渲染到 body，需要在 document.body 中查找
      expect(document.body.querySelector('.success-toast')).not.toBeNull()
    })
  })

  describe('关于页面', () => {
    it('应该显示应用名称', async () => {
      const wrapper = mount(SystemSettings)

      const menuItems = wrapper.findAll('.ss-nav-item')
      await menuItems[5].trigger('click')

      expect(wrapper.find('.about-content h3').text()).toBe('ArchWorkspace')
    })

    it('应该显示版本号', async () => {
      const wrapper = mount(SystemSettings)

      const menuItems = wrapper.findAll('.ss-nav-item')
      await menuItems[5].trigger('click')

      expect(wrapper.find('.version').text()).toBe('版本 1.0.0')
    })
  })
})
