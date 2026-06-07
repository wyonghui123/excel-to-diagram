/**
 * EnumFieldDisplay 组件测试
 * 
 * 测试目标：验证枚举字段显示组件的功能
 */

import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import EnumFieldDisplay from '@/components/EnumFieldDisplay.vue'

describe('EnumFieldDisplay', () => {
  it('应该显示枚举值名称', () => {
    const field = {
      id: 'relation_code',
      ui: {
        display_field: 'name'
      }
    }
    
    const record = {
      relation_code: 'GENERATES',
      relation_code_name: '生成'
    }
    
    const wrapper = mount(EnumFieldDisplay, {
      props: {
        field,
        record
      }
    })
    
    expect(wrapper.text()).toBe('生成')
  })
  
  it('应该支持自定义 display_field', () => {
    const field = {
      id: 'status',
      ui: {
        display_field: 'name_en'
      }
    }
    
    const record = {
      status: 'ACTIVE',
      status_name_en: 'Active'
    }
    
    const wrapper = mount(EnumFieldDisplay, {
      props: {
        field,
        record,
        displayField: 'name_en'
      }
    })
    
    expect(wrapper.text()).toBe('Active')
  })
  
  it('应该在枚举值缺失时降级显示原始值', () => {
    const field = {
      id: 'relation_code',
      ui: {
        display_field: 'name'
      }
    }
    
    const record = {
      relation_code: 'GENERATES'
      // 没有 relation_code_name
    }
    
    const wrapper = mount(EnumFieldDisplay, {
      props: {
        field,
        record
      }
    })
    
    expect(wrapper.text()).toBe('GENERATES')
  })
  
  it('应该支持空值', () => {
    const field = {
      id: 'status',
      ui: {
        display_field: 'name'
      }
    }
    
    const record = {
      status: null
    }
    
    const wrapper = mount(EnumFieldDisplay, {
      props: {
        field,
        record
      }
    })
    
    expect(wrapper.text()).toBe('')
  })
  
  it('应该使用默认 display_field 为 name', () => {
    const field = {
      id: 'relation_code',
      ui: {}
    }
    
    const record = {
      relation_code: 'GENERATES',
      relation_code_name: '生成'
    }
    
    const wrapper = mount(EnumFieldDisplay, {
      props: {
        field,
        record
      }
    })
    
    expect(wrapper.text()).toBe('生成')
  })
})
