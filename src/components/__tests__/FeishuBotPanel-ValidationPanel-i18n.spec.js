/**
 * 测试 FeishuBotPanel + ValidationPanel i18n 集成 (W5 i18n 第 2 批)
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { nextTick } from 'vue'

describe('FeishuBotPanel + ValidationPanel i18n 集成 (W5 第 2 批)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  describe('FeishuBotPanel', () => {
    it('包含 4 行 t() 调用（title/三元连接状态/connecting/connect）', async () => {
      const fs = await import('fs')
      const content = fs.readFileSync('d:/filework/excel-to-diagram/src/components/FeishuBotPanel.vue', 'utf-8')
      const matches = content.match(/t\(['"]feishuBot\./g) || []
      expect(matches.length).toBeGreaterThanOrEqual(4)
    })

    it('覆盖 5 个 keys（title/connected/disconnected/connecting/connect）', async () => {
      const { t, setLocale } = await import('@/i18n')
      setLocale('zh-CN')
      expect(t('feishuBot.title')).toBe('飞书机器人交互')
      expect(t('feishuBot.connected')).toBe('已连接')
      expect(t('feishuBot.disconnected')).toBe('未连接')
      expect(t('feishuBot.connecting')).toBe('连接中...')
      expect(t('feishuBot.connect')).toBe('连接机器人')
    })

    it('导入 t 函数', async () => {
      const fs = await import('fs')
      const content = fs.readFileSync('d:/filework/excel-to-diagram/src/components/FeishuBotPanel.vue', 'utf-8')
      expect(content).toMatch(/import\s+\{\s*t\s*\}\s+from\s+['"]@\/i18n['"]/)
    })
  })

  describe('ValidationPanel', () => {
    it('包含 5 个 t() 调用（title/errorCount/warningCount/infoCount/filterHint/filteredSummary 插值）', async () => {
      const fs = await import('fs')
      const content = fs.readFileSync('d:/filework/excel-to-diagram/src/components/ValidationPanel.vue', 'utf-8')
      const matches = content.match(/t\(['"]validationPanel\./g) || []
      expect(matches.length).toBeGreaterThanOrEqual(5)
    })

    it('filteredSummary 插值正确工作', async () => {
      const { t, setLocale } = await import('@/i18n')
      setLocale('zh-CN')
      const result = t('validationPanel.filteredSummary', '过滤: {objects}对象/{relations}关系', { objects: 3, relations: 5 })
      expect(result).toBe('过滤: 3对象/5关系')
    })

    it('导入 t 函数', async () => {
      const fs = await import('fs')
      const content = fs.readFileSync('d:/filework/excel-to-diagram/src/components/ValidationPanel.vue', 'utf-8')
      expect(content).toMatch(/import\s+\{\s*t\s*\}\s+from\s+['"]@\/i18n['"]/)
    })
  })

  describe('i18n 字典完整性', () => {
    it('zh-CN 包含 feishuBot 和 validationPanel 完整 keys', async () => {
      const { default: zh } = await import('@/i18n/locales/zh-CN.json')
      expect(zh.feishuBot).toBeDefined()
      expect(zh.feishuBot.title).toBe('飞书机器人交互')
      expect(zh.validationPanel).toBeDefined()
      expect(zh.validationPanel.title).toBe('数据校验结果')
    })

    it('en-US 包含 feishuBot 和 validationPanel 完整 keys', async () => {
      const { default: en } = await import('@/i18n/locales/en-US.json')
      expect(en.feishuBot).toBeDefined()
      expect(en.feishuBot.title).toBe('Feishu Bot Interaction')
      expect(en.validationPanel).toBeDefined()
      expect(en.validationPanel.title).toBe('Data Validation Results')
    })

    it('setLocale 切换后 t() 返回正确值', async () => {
      const { t, setLocale } = await import('@/i18n')
      setLocale('zh-CN')
      expect(t('feishuBot.title')).toBe('飞书机器人交互')
      setLocale('en-US')
      expect(t('feishuBot.title')).toBe('Feishu Bot Interaction')
    })
  })
})
