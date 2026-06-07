import { describe, it, expect } from 'vitest'
import { tabGroupConfigs, getGroupTabs, getGroupTitle } from '../menuConfig'

describe('tabGroupConfigs', () => {
  describe('user-permission 配置', () => {
    it('应该存在 user-permission 配置', () => {
      expect(tabGroupConfigs).toHaveProperty('user-permission')
    })

    it('应该有正确的标题', () => {
      expect(getGroupTitle('user-permission')).toBe('用户与权限管理')
    })

    it('应该有 tabs 数组 (3 tab)', () => {
      const tabs = getGroupTabs('user-permission')
      expect(Array.isArray(tabs)).toBe(true)
      expect(tabs.length).toBe(3)
    })

    it(' profile  settings  ( AccountSettings )', () => {
      const tabs = getGroupTabs('user-permission')
      const profileTab = tabs.find(t => t.key === 'profile')
      const settingsTab = tabs.find(t => t.key === 'settings')
      expect(profileTab).toBeUndefined()
      expect(settingsTab).toBeUndefined()
    })

    it('用户管理 tab 应该有 objectType: user', () => {
      const tabs = getGroupTabs('user-permission')
      const userTab = tabs.find(t => t.key === 'users')
      expect(userTab).toBeDefined()
      expect(userTab.objectType).toBe('user')
    })

    it('角色权限 tab 应该有 objectType: role', () => {
      const tabs = getGroupTabs('user-permission')
      const roleTab = tabs.find(t => t.key === 'roles')
      expect(roleTab).toBeDefined()
      expect(roleTab.objectType).toBe('role')
    })
  })

  describe('business-config 配置', () => {
    it('应该存在 business-config 配置', () => {
      expect(tabGroupConfigs).toHaveProperty('business-config')
    })

    it('应该有正确的标题', () => {
      expect(getGroupTitle('business-config')).toBe('业务配置')
    })

    it('枚举类型管理 tab 应该有 objectType: enum_type', () => {
      const tabs = getGroupTabs('business-config')
      // 源码中 key 为 'enum-types'（复数 + 连字符）
      const enumTab = tabs.find(t => t.key === 'enum-types')
      expect(enumTab).toBeDefined()
      expect(enumTab.objectType).toBe('enum_type')
    })
  })

  describe('边界情况', () => {
    it('不存在的 group 应该返回空数组', () => {
      expect(getGroupTabs('nonexistent')).toEqual([])
    })

    it('不存在的 group 应该返回 groupKey 本身', () => {
      expect(getGroupTitle('nonexistent')).toBe('nonexistent')
    })

    it('所有 tab key 应该唯一', () => {
      for (const [groupKey, config] of Object.entries(tabGroupConfigs)) {
        const keys = config.tabs.map(t => t.key)
        expect(new Set(keys).size).toBe(keys.length)
      }
    })
  })
})
