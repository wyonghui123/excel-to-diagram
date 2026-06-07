/**
 * ImpactPreview 组件测试
 * 测试应用层：src/components/common/ImpactPreview/ImpactPreview.vue
 *
 * 注意：@element-plus/icons-vue 已在 src/test/setup.js 中全局 mock（Proxy 兜底），
 * 本 spec 无需再写自己的 vi.mock。
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref, computed } from 'vue'

import ImpactPreview from '../ImpactPreview.vue'

const mockImpactData = {
  domainCount: 2,
  subDomainCount: 6,
  serviceModuleCount: 15,
  businessObjectCount: 45,
  items: [
    { type: 'domain', code: 'SUPPLY_CHAIN', name: '供应链', impactType: 'direct', permissionLevel: 'write' },
    { type: 'subDomain', code: 'PROCUREMENT', name: '采购', impactType: 'inherit', permissionLevel: 'write' },
    { type: 'serviceModule', code: 'PO_MODULE', name: '采购订单', impactType: 'inherit', permissionLevel: 'read' },
    { type: 'businessObject', code: 'PO001', name: '采购订单对象', impactType: 'propagate', permissionLevel: 'admin' },
    { type: 'businessObject', code: 'PO002', name: '采购申请对象', impactType: 'direct', permissionLevel: 'read' }
  ]
}

describe('ImpactPreview - 影响范围预览组件', () => {
  
  describe('组件渲染', () => {
    
    it('应该正确渲染组件标题', () => {
      const wrapper = mount(ImpactPreview, {
        props: { impactData: mockImpactData, loading: false }
      })
      
      expect(wrapper.find('.impact-preview__title').text()).toBe('影响范围预览')
    })
    
    it('加载状态应该显示loading', () => {
      const wrapper = mount(ImpactPreview, {
        props: { impactData: {}, loading: true }
      })
      
      expect(wrapper.find('.impact-preview__loading').exists()).toBe(true)
      expect(wrapper.find('.impact-preview__loading').text()).toContain('加载中')
    })
    
    it('非加载状态不应该显示loading', () => {
      const wrapper = mount(ImpactPreview, {
        props: { impactData: mockImpactData, loading: false }
      })
      
      expect(wrapper.find('.impact-preview__loading').exists()).toBe(false)
    })
  })
  
  describe('统计摘要', () => {
    
    it('应该正确渲染统计卡片', () => {
      const wrapper = mount(ImpactPreview, {
        props: { impactData: mockImpactData, loading: false }
      })
      
      const cards = wrapper.findAll('.summary-card')
      expect(cards.length).toBe(4)
    })
    
    it('应该正确显示统计数据', () => {
      const wrapper = mount(ImpactPreview, {
        props: { impactData: mockImpactData, loading: false }
      })
      
      const values = wrapper.findAll('.summary-card__value')
      expect(values[0].text()).toBe('2')
      expect(values[1].text()).toBe('6')
      expect(values[2].text()).toBe('15')
      expect(values[3].text()).toBe('45')
    })
    
    it('应该正确显示统计标签', () => {
      const wrapper = mount(ImpactPreview, {
        props: { impactData: mockImpactData, loading: false }
      })
      
      const labels = wrapper.findAll('.summary-card__label')
      expect(labels[0].text()).toBe('领域')
      expect(labels[1].text()).toBe('子领域')
      expect(labels[2].text()).toBe('服务模块')
      expect(labels[3].text()).toBe('业务对象')
    })
    
    it('空数据应该显示0', () => {
      const wrapper = mount(ImpactPreview, {
        props: { impactData: {}, loading: false }
      })
      
      const values = wrapper.findAll('.summary-card__value')
      values.forEach(v => {
        expect(v.text()).toBe('0')
      })
    })
  })
  
  describe('详细清单表格', () => {
    
    it('应该正确渲染表格', () => {
      const wrapper = mount(ImpactPreview, {
        props: { impactData: mockImpactData, loading: false }
      })
      
      expect(wrapper.find('.el-table').exists()).toBe(true)
    })
    
    it('应该正确显示表格数据', () => {
      const wrapper = mount(ImpactPreview, {
        props: { impactData: mockImpactData, loading: false }
      })
      
      const rows = wrapper.findAll('.el-table__body-wrapper .el-table__row')
      expect(rows.length).toBeGreaterThan(0)
    })
    
    it('应该显示项目总数', () => {
      const wrapper = mount(ImpactPreview, {
        props: { impactData: mockImpactData, loading: false }
      })
      
      expect(wrapper.find('.detail-header__count').text()).toContain('5')
    })
  })
  
  describe('影响方式标记', () => {
    
    it('直接匹配应该显示绿色标签', () => {
      const wrapper = mount(ImpactPreview, {
        props: { impactData: mockImpactData, loading: false }
      })
      
      const filteredData = wrapper.vm.filteredTableData
      const directItems = filteredData.filter(item => item.impactType === 'direct')
      expect(directItems.length).toBeGreaterThan(0)
    })
    
    it('向下继承应该显示蓝色标签', () => {
      const wrapper = mount(ImpactPreview, {
        props: { impactData: mockImpactData, loading: false }
      })
      
      const filteredData = wrapper.vm.filteredTableData
      const inheritItems = filteredData.filter(item => item.impactType === 'inherit')
      expect(inheritItems.length).toBeGreaterThan(0)
    })
    
    it('向上传播应该显示橙色标签', () => {
      const wrapper = mount(ImpactPreview, {
        props: { impactData: mockImpactData, loading: false }
      })
      
      const filteredData = wrapper.vm.filteredTableData
      const propagateItems = filteredData.filter(item => item.impactType === 'propagate')
      expect(propagateItems.length).toBeGreaterThan(0)
    })
  })
  
  describe('过滤功能', () => {
    
    it('应该有过滤按钮', () => {
      const wrapper = mount(ImpactPreview, {
        props: { impactData: mockImpactData, loading: false }
      })
      
      const filterBtn = wrapper.find('.detail-header__actions .el-button')
      expect(filterBtn.exists()).toBe(true)
    })
    
    it('过滤变更应该触发filter-change事件', async () => {
      const wrapper = mount(ImpactPreview, {
        props: { impactData: mockImpactData, loading: false }
      })
      
      await wrapper.vm.handleFilterCommand('direct')
      
      expect(wrapper.emitted('filter-change')).toBeTruthy()
      expect(wrapper.emitted('filter-change')[0]).toEqual([{ type: 'direct' }])
    })
  })
  
  describe('导出功能', () => {
    
    it('应该有导出按钮', () => {
      const wrapper = mount(ImpactPreview, {
        props: { impactData: mockImpactData, loading: false }
      })
      
      const exportBtn = wrapper.findAll('.detail-header__actions .el-button')
      const exportButton = exportBtn.find(btn => btn.text().includes('导出'))
      expect(exportButton).toBeTruthy()
    })
    
    it('导出应该触发export事件', async () => {
      const wrapper = mount(ImpactPreview, {
        props: { impactData: mockImpactData, loading: false }
      })
      
      vi.stubGlobal('URL', {
        createObjectURL: vi.fn(() => 'blob:test'),
        revokeObjectURL: vi.fn()
      })
      
      await wrapper.vm.handleExport()
      
      expect(wrapper.emitted('export')).toBeTruthy()
      expect(wrapper.emitted('export')[0][0]).toHaveProperty('fileName')
      expect(wrapper.emitted('export')[0][0]).toHaveProperty('count')
    })
  })
  
  describe('折叠功能', () => {
    
    it('默认应该展开详细清单', () => {
      const wrapper = mount(ImpactPreview, {
        props: { impactData: mockImpactData, loading: false }
      })
      
      expect(wrapper.vm.detailExpanded).toBe(true)
    })
    
    it('点击头部应该切换展开状态', async () => {
      const wrapper = mount(ImpactPreview, {
        props: { impactData: mockImpactData, loading: false }
      })
      
      await wrapper.find('.detail-header').trigger('click')
      expect(wrapper.vm.detailExpanded).toBe(false)
      
      await wrapper.find('.detail-header').trigger('click')
      expect(wrapper.vm.detailExpanded).toBe(true)
    })
  })
  
  describe('分页功能', () => {
    
    it('应该有分页组件', () => {
      const wrapper = mount(ImpactPreview, {
        props: { impactData: mockImpactData, loading: false }
      })
      
      expect(wrapper.find('.el-pagination').exists()).toBe(true)
    })
    
    it('应该正确显示总数', () => {
      const wrapper = mount(ImpactPreview, {
        props: { impactData: mockImpactData, loading: false }
      })
      
      const pagination = wrapper.find('.el-pagination')
      expect(pagination.text()).toContain('5')
    })
  })
  
  describe('Props 验证', () => {
    
    it('应该接受impactData prop', () => {
      const wrapper = mount(ImpactPreview, {
        props: { impactData: mockImpactData }
      })
      
      expect(wrapper.props('impactData')).toEqual(mockImpactData)
    })
    
    it('应该接受loading prop', () => {
      const wrapper = mount(ImpactPreview, {
        props: { impactData: {}, loading: true }
      })
      
      expect(wrapper.props('loading')).toBe(true)
    })
    
    it('loading默认值应该是false', () => {
      const wrapper = mount(ImpactPreview, {
        props: { impactData: {} }
      })
      
      expect(wrapper.props('loading')).toBe(false)
    })
  })
})

describe('ImpactPreview - 边界情况', () => {
  
  it('空items应该正常显示', () => {
    const wrapper = mount(ImpactPreview, {
      props: { 
        impactData: { 
          domainCount: 0,
          items: [] 
        }, 
        loading: false 
      }
    })
    
    expect(wrapper.find('.detail-header__count').text()).toContain('0')
  })
  
  it('缺少可选字段应该使用默认值', () => {
    const wrapper = mount(ImpactPreview, {
      props: { 
        impactData: { 
          items: [
            { code: 'TEST', name: '测试' }
          ]
        }, 
        loading: false 
      }
    })
    
    expect(wrapper.find('.impact-preview').exists()).toBe(true)
  })
  
  it('大数据量应该正常分页', () => {
    const largeData = {
      domainCount: 1,
      items: Array.from({ length: 100 }, (_, i) => ({
        type: 'businessObject',
        code: `BO${i}`,
        name: `业务对象${i}`,
        impactType: 'direct',
        permissionLevel: 'read'
      }))
    }
    
    const wrapper = mount(ImpactPreview, {
      props: { impactData: largeData, loading: false }
    })
    
    expect(wrapper.find('.detail-header__count').text()).toContain('100')
  })
})
