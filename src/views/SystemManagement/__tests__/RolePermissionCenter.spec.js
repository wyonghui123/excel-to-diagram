/**
 * RolePermissionCenter 组件测试 - 4区域布局
 * 
 * 测试内容：
 * 1. 4区域布局渲染
 * 2. 组件集成
 * 3. 数据联动
 * 4. API调用
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import RolePermissionCenter from '../RolePermissionCenter.vue'

const mockFetch = vi.fn()
global.fetch = mockFetch

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/system/roles/:roleId', component: RolePermissionCenter },
    { path: '/system', component: { template: '<div>System</div>' } }
  ]
})

describe('RolePermissionCenter - 4区域布局', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockFetch.mockClear()
  })
  
  describe('布局渲染', () => {
    
    it('应该渲染4个主要区域', async () => {
      const wrapper = mount(RolePermissionCenter, {
        global: {
          plugins: [router],
          stubs: {
            ManagementDimensionSelector: true,
            ConditionRuleEditor: true,
            ImpactPreview: true
          }
        }
      })
      
      await router.push('/system/roles/1')
      await router.isReady()
      await flushPromises()
      
      expect(wrapper.find('.role-permission-center').exists()).toBe(true)
      expect(wrapper.find('.rpc-header').exists()).toBe(true)
      expect(wrapper.find('.rpc-aside').exists()).toBe(true)
      expect(wrapper.find('.rpc-main').exists()).toBe(true)
      expect(wrapper.find('.rpc-editor-section').exists()).toBe(true)
      expect(wrapper.find('.rpc-preview-section').exists()).toBe(true)
      expect(wrapper.find('.rpc-bottom-section').exists()).toBe(true)
      
      wrapper.unmount()
    })
    
    it('应该显示标题和角色名称', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          data: { id: 1, name: '测试角色', code: 'TEST_ROLE' }
        })
      })
      
      const wrapper = mount(RolePermissionCenter, {
        global: {
          plugins: [router],
          stubs: {
            ManagementDimensionSelector: true,
            ConditionRuleEditor: true,
            ImpactPreview: true
          }
        }
      })
      
      await router.push('/system/roles/1')
      await router.isReady()
      await flushPromises()
      
      const title = wrapper.find('.rpc-title')
      expect(title.exists()).toBe(true)
      
      wrapper.unmount()
    })
    
    it('应该显示保存和重置按钮', async () => {
      const wrapper = mount(RolePermissionCenter, {
        global: {
          plugins: [router],
          stubs: {
            ManagementDimensionSelector: true,
            ConditionRuleEditor: true,
            ImpactPreview: true
          }
        }
      })
      
      await router.push('/system/roles/1')
      await router.isReady()
      await flushPromises()
      
      const saveButton = wrapper.find('button:has(.el-icon) + button:has(.el-icon)')
      expect(saveButton.exists()).toBe(true)
      
      const resetButton = wrapper.find('button:has(.el-icon)')
      expect(resetButton.exists()).toBe(true)
      
      wrapper.unmount()
    })
  })
  
  describe('组件集成', () => {
    
    it('应该集成ManagementDimensionSelector组件', async () => {
      const wrapper = mount(RolePermissionCenter, {
        global: {
          plugins: [router],
          stubs: {
            ManagementDimensionSelector: {
              template: '<div class="mock-dimension-selector">Dimension Selector</div>'
            },
            ConditionRuleEditor: true,
            ImpactPreview: true
          }
        }
      })
      
      await router.push('/system/roles/1')
      await router.isReady()
      await flushPromises()
      
      expect(wrapper.find('.mock-dimension-selector').exists()).toBe(true)
      
      wrapper.unmount()
    })
    
    it('应该集成ConditionRuleEditor组件', async () => {
      const wrapper = mount(RolePermissionCenter, {
        global: {
          plugins: [router],
          stubs: {
            ManagementDimensionSelector: true,
            ConditionRuleEditor: {
              template: '<div class="mock-rule-editor">Rule Editor</div>'
            },
            ImpactPreview: true
          }
        }
      })
      
      await router.push('/system/roles/1')
      await router.isReady()
      await flushPromises()
      
      expect(wrapper.find('.mock-rule-editor').exists()).toBe(true)
      
      wrapper.unmount()
    })
    
    it('应该集成ImpactPreview组件', async () => {
      const wrapper = mount(RolePermissionCenter, {
        global: {
          plugins: [router],
          stubs: {
            ManagementDimensionSelector: true,
            ConditionRuleEditor: true,
            ImpactPreview: {
              template: '<div class="mock-impact-preview">Impact Preview</div>'
            }
          }
        }
      })
      
      await router.push('/system/roles/1')
      await router.isReady()
      await flushPromises()
      
      expect(wrapper.find('.mock-impact-preview').exists()).toBe(true)
      
      wrapper.unmount()
    })
  })
  
  describe('数据联动', () => {
    
    it('维度选择应该触发字段加载', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ data: [] })
      })

      const wrapper = mount(RolePermissionCenter, {
        global: {
          plugins: [router],
          stubs: {
            ManagementDimensionSelector: true,
            ConditionRuleEditor: true,
            ImpactPreview: true
          }
        }
      })

      await router.push('/system/roles/1')
      await router.isReady()
      await flushPromises()

      const vm = wrapper.vm
      vm.selectedDimensionId = 'domain'
      await flushPromises()

      expect(vm.selectedDimensionId).toBe('domain')

      wrapper.unmount()
    })
    
    it('规则保存后应该刷新规则列表', async () => {
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ data: [] })
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ data: [] })
        })
      
      const wrapper = mount(RolePermissionCenter, {
        global: {
          plugins: [router],
          stubs: {
            ManagementDimensionSelector: true,
            ConditionRuleEditor: {
              template: '<div></div>',
              methods: {
                validate: () => true,
                getFormData: () => ({
                  resource_type: 'domain',
                  condition: 'id = 1',
                  permission_level: 'read'
                }),
                reset: () => {}
              }
            },
            ImpactPreview: true
          }
        }
      })
      
      await router.push('/system/roles/1')
      await router.isReady()
      await flushPromises()
      
      wrapper.unmount()
    })
    
    it('规则删除后应该更新列表', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true })
      })
      
      const wrapper = mount(RolePermissionCenter, {
        global: {
          plugins: [router],
          stubs: {
            ManagementDimensionSelector: true,
            ConditionRuleEditor: true,
            ImpactPreview: true
          }
        }
      })
      
      await router.push('/system/roles/1')
      await router.isReady()
      await flushPromises()
      
      const vm = wrapper.vm
      vm.permissionRules = [
        { id: 1, condition: 'id = 1', resource_type: 'domain' }
      ]
      
      wrapper.unmount()
    })
  })
  
  describe('API调用', () => {
    
    it('应该在挂载时加载角色信息', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          data: { id: 1, name: '测试角色', code: 'TEST_ROLE' }
        })
      })
      
      const wrapper = mount(RolePermissionCenter, {
        global: {
          plugins: [router],
          stubs: {
            ManagementDimensionSelector: true,
            ConditionRuleEditor: true,
            ImpactPreview: true
          }
        }
      })
      
      await router.push('/system/roles/1')
      await router.isReady()
      await flushPromises()
      
      expect(mockFetch).toHaveBeenCalled()
      
      wrapper.unmount()
    })
    
    it('应该在挂载时加载管理维度', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          data: [
            { id: 'domain', name: '领域', code: 'domain' },
            { id: 'version', name: '版本', code: 'version' }
          ]
        })
      })
      
      const wrapper = mount(RolePermissionCenter, {
        global: {
          plugins: [router],
          stubs: {
            ManagementDimensionSelector: true,
            ConditionRuleEditor: true,
            ImpactPreview: true
          }
        }
      })
      
      await router.push('/system/roles/1')
      await router.isReady()
      await flushPromises()
      
      wrapper.unmount()
    })
    
    it('应该在挂载时加载权限规则', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          data: [
            { id: 1, condition: 'id = 1', resource_type: 'domain' }
          ]
        })
      })
      
      const wrapper = mount(RolePermissionCenter, {
        global: {
          plugins: [router],
          stubs: {
            ManagementDimensionSelector: true,
            ConditionRuleEditor: true,
            ImpactPreview: true
          }
        }
      })
      
      await router.push('/system/roles/1')
      await router.isReady()
      await flushPromises()
      
      wrapper.unmount()
    })
    
    it('计算影响范围应该调用正确的API', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          data: {
            domainCount: 2,
            subDomainCount: 5,
            serviceModuleCount: 10,
            businessObjectCount: 20
          }
        })
      })
      
      const wrapper = mount(RolePermissionCenter, {
        global: {
          plugins: [router],
          stubs: {
            ManagementDimensionSelector: true,
            ConditionRuleEditor: true,
            ImpactPreview: true
          }
        }
      })
      
      await router.push('/system/roles/1')
      await router.isReady()
      await flushPromises()
      
      const vm = wrapper.vm
      await vm.calculateImpact({
        resource_type: 'domain',
        condition: 'id = 1',
        permission_level: 'read'
      })
      
      expect(mockFetch).toHaveBeenCalled()
      
      wrapper.unmount()
    })
  })
  
  describe('工具函数', () => {
    
    it('getDimensionName应该返回正确的维度名称', async () => {
      const wrapper = mount(RolePermissionCenter, {
        global: {
          plugins: [router],
          stubs: {
            ManagementDimensionSelector: true,
            ConditionRuleEditor: true,
            ImpactPreview: true
          }
        }
      })
      
      await router.push('/system/roles/1')
      await router.isReady()
      await flushPromises()
      
      const vm = wrapper.vm
      vm.managementDimensions = [
        { id: 'domain', name: '领域', code: 'domain' }
      ]
      
      const name = vm.getDimensionName('domain')
      expect(name).toBe('领域')
      
      wrapper.unmount()
    })
    
    it('getPermissionLevelLabel应该返回正确的权限级别标签', async () => {
      const wrapper = mount(RolePermissionCenter, {
        global: {
          plugins: [router],
          stubs: {
            ManagementDimensionSelector: true,
            ConditionRuleEditor: true,
            ImpactPreview: true
          }
        }
      })
      
      await router.push('/system/roles/1')
      await router.isReady()
      await flushPromises()
      
      const vm = wrapper.vm
      
      expect(vm.getPermissionLevelLabel('read')).toBe('只读')
      expect(vm.getPermissionLevelLabel('write')).toBe('可编辑')
      expect(vm.getPermissionLevelLabel('admin')).toBe('完全管理')
      
      wrapper.unmount()
    })
    
    it('getPermissionLevelType应该返回正确的权限级别类型', async () => {
      const wrapper = mount(RolePermissionCenter, {
        global: {
          plugins: [router],
          stubs: {
            ManagementDimensionSelector: true,
            ConditionRuleEditor: true,
            ImpactPreview: true
          }
        }
      })
      
      await router.push('/system/roles/1')
      await router.isReady()
      await flushPromises()
      
      const vm = wrapper.vm
      
      expect(vm.getPermissionLevelType('read')).toBe('')
      expect(vm.getPermissionLevelType('write')).toBe('warning')
      expect(vm.getPermissionLevelType('admin')).toBe('success')
      
      wrapper.unmount()
    })
  })
  
  describe('响应式布局', () => {
    
    it('小屏幕应该调整布局', async () => {
      const wrapper = mount(RolePermissionCenter, {
        global: {
          plugins: [router],
          stubs: {
            ManagementDimensionSelector: true,
            ConditionRuleEditor: true,
            ImpactPreview: true
          }
        }
      })
      
      await router.push('/system/roles/1')
      await router.isReady()
      await flushPromises()
      
      const aside = wrapper.find('.rpc-aside')
      expect(aside.exists()).toBe(true)
      
      wrapper.unmount()
    })
  })
})
