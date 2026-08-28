/**
 * GroupRoleDialog.spec.js - 用户组角色对话框测试
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import GroupRoleDialog from '@/views/SystemManagement/GroupRoleDialog.vue'

const mockBoService = {
  query: vi.fn(),
  associate: vi.fn(),
  dissociate: vi.fn()
}

vi.mock('@/services/boService', () => ({
  default: mockBoService
}))

const mockRoles = [
  { id: 1, code: 'admin', name: '管理员', is_system: true },
  { id: 2, code: 'user', name: '普通用户', is_system: false },
  { id: 3, code: 'viewer', name: '访客', is_system: false }
]

describe('GroupRoleDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    
    mockBoService.query.mockResolvedValue({
      success: true,
      data: { items: mockRoles, total: 3 }
    })
  })

  const mountComponent = (props = {}) => {
    return mount(GroupRoleDialog, {
      props: {
        groupId: 1,
        groupName: '开发团队',
        existingRoles: [],
        ...props
      },
      global: {
        plugins: [ElementPlus]
      }
    })
  }

  describe('数据加载', () => {
    it('应该在挂载时加载角色列表', async () => {
      await mountComponent()
      
      expect(mockBoService.query).toHaveBeenCalledWith('role', expect.objectContaining({
        page: 1,
        page_size: 100
      }))
    })

    it('应该显示加载状态', async () => {
      mockBoService.query.mockImplementation(() => new Promise(() => {}))
      
      const wrapper = mountComponent()
      
      expect(wrapper.vm.loading).toBe(true)
    })
  })

  describe('角色选择', () => {
    it('应该能够选择角色', async () => {
      const wrapper = await mountComponent()
      
      wrapper.vm.toggleRole(1)
      
      expect(wrapper.vm.selectedRoleIds).toContain(1)
    })

    it('应该能够取消选择', async () => {
      const wrapper = await mountComponent()
      
      wrapper.vm.selectedRoleIds = [1, 2]
      wrapper.vm.toggleRole(1)
      
      expect(wrapper.vm.selectedRoleIds).not.toContain(1)
      expect(wrapper.vm.selectedRoleIds).toContain(2)
    })

    it('应该能够清空所有选择', async () => {
      const wrapper = await mountComponent()
      
      wrapper.vm.selectedRoleIds = [1, 2, 3]
      wrapper.vm.clearAll()
      
      expect(wrapper.vm.selectedRoleIds).toEqual([])
    })
  })

  describe('角色显示', () => {
    it('应该显示系统角色标签', async () => {
      const wrapper = await mountComponent()
      
      await wrapper.vm.$nextTick()
      
      const systemRole = wrapper.vm.allRoles.find(r => r.is_system)
      expect(systemRole.is_system).toBe(true)
    })
  })

  describe('保存操作', () => {
    it('应该添加新角色', async () => {
      mockBoService.associate.mockResolvedValue({ success: true })
      
      const wrapper = await mountComponent()
      
      wrapper.vm.selectedRoleIds = [1, 2]
      
      await wrapper.vm.handleSave()
      
      expect(mockBoService.associate).toHaveBeenCalledTimes(2)
    })

    it('应该移除已删除的角色', async () => {
      mockBoService.associate.mockResolvedValue({ success: true })
      mockBoService.dissociate.mockResolvedValue({ success: true })
      
      const wrapper = await mountComponent({
        existingRoles: [{ role_id: 1 }, { role_id: 3 }]
      })
      
      wrapper.vm.selectedRoleIds = [1, 2]
      
      await wrapper.vm.handleSave()
      
      expect(mockBoService.dissociate).toHaveBeenCalledWith('user_group', 1, 'roles', 3, 'role')
    })

    it('保存成功后应该关闭对话框', async () => {
      mockBoService.associate.mockResolvedValue({ success: true })
      
      const wrapper = await mountComponent()
      
      wrapper.vm.selectedRoleIds = [1]
      
      await wrapper.vm.handleSave()
      
      expect(wrapper.emitted('saved')).toBeTruthy()
      expect(wrapper.emitted('close')).toBeTruthy()
    })
  })

  describe('初始化', () => {
    it('应该初始化已选角色', async () => {
      const wrapper = await mountComponent({
        existingRoles: [
          { role_id: 1, code: 'admin' },
          { role_id: 2, code: 'user' }
        ]
      })
      
      expect(wrapper.vm.selectedRoleIds).toEqual([1, 2])
    })
  })
})
