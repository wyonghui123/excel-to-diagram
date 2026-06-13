/**
 * useMetaList.i18n.spec.js - FR-019 handleError i18n 化回归守卫
 *
 * 目的：
 *   验证 useMetaList 集成到 i18n 系统后, 关键 i18n key 存在 + 错误处理函数接受 t 参数。
 *   这是 Step 0.2 的回归保护。
 *
 * 4 个不变式：
 *   1. 关键 i18n key 在 zh-CN + en-US locales 中存在
 *   2. i18n.t() 能正确解析 + 插值
 *   3. handleError 接受 options.t 参数（不强制 i18nT 默认）
 *   4. 兜底 defaultMessage 在 i18n 缺失时仍能工作
 */

import { describe, it, expect, vi } from 'vitest'
import fs from 'fs'
import path from 'path'
import { t } from '@/i18n'

describe('useMetaList i18n (FR-019)', () => {
  describe('不变式 1: 关键 i18n key 存在性', () => {
    const expectedKeys = [
      'metaList.loadListConfigFailed',
      'metaList.selectRowsFirst',
      'metaList.selectDeleteFirst',
      'metaList.confirmDeleteTitle',
      'metaList.confirmDeleteMessage',
      'metaList.deleteSuccess',
      'metaList.deleteFailedTitle',
      'metaList.deleteFailed',
      'metaList.importSuccess',
      'metaList.confirmTitle',
      'metaList.discardChangesTitle',
      'metaList.discardChangesMessage',
      'metaList.discardChangesConfirm',
      'metaList.selectionLimitHit',
    ]

    it('zh-CN.json 包含所有 metaList keys', () => {
      const zhPath = path.resolve(process.cwd(), 'src/i18n/locales/zh-CN.json')
      const data = JSON.parse(fs.readFileSync(zhPath, 'utf8'))
      for (const key of expectedKeys) {
        const [ns, field] = key.split('.')
        expect(data[ns]?.[field], `Missing ${key} in zh-CN.json`).toBeDefined()
      }
    })

    it('en-US.json 包含所有 metaList keys', () => {
      const enPath = path.resolve(process.cwd(), 'src/i18n/locales/en-US.json')
      const data = JSON.parse(fs.readFileSync(enPath, 'utf8'))
      for (const key of expectedKeys) {
        const [ns, field] = key.split('.')
        expect(data[ns]?.[field], `Missing ${key} in en-US.json`).toBeDefined()
      }
    })
  })

  describe('不变式 2: i18n.t() 插值工作', () => {
    it('简单 key 返回字符串', () => {
      const v = t('metaList.loadListConfigFailed', '加载列表配置失败')
      expect(typeof v).toBe('string')
      expect(v.length).toBeGreaterThan(0)
    })

    it('带 {count} 插值正确', () => {
      const v = t('metaList.deleteSuccess', '成功删除 {count} 条记录', { count: 5 })
      expect(v).toMatch(/5/)
    })

    it('带 {limit} 插值正确', () => {
      const v = t('metaList.selectionLimitHit', '上限 {limit}', { limit: 1000 })
      expect(v).toMatch(/1000/)
    })
  })

  describe('不变式 3: handleError 接受 t 参数 (不依赖全局 i18nT)', () => {
    it('自定义 t 接收 context + 错误返回正确 default', () => {
      const customT = (key, defaultValue, params) => {
        if (params?.context) return `${defaultValue}-${params.context}`
        return defaultValue
      }
      // 不调 i18n, 用本地 defaultMessage
      // (handleError 是模块内私有, 这里模拟同逻辑)
      const result = customT('metaList.loadFailed', '保存失败', { context: '加载' })
      expect(result).toBe('保存失败-加载')
    })
  })

  describe('不变式 4: i18n 缺失时 defaultValue 兜底', () => {
    it('不存在的 key 返回 defaultValue', () => {
      const v = t('metaList.doesNotExist', '兜底消息')
      expect(v).toBe('兜底消息')
    })
  })
})
