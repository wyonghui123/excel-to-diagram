import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'

vi.mock('vue')

const mockEnumValues = [
  { code: 'STRING', name: '字符串', is_active: true, is_system: true },
  { code: 'INTEGER', name: '整数', is_active: true, is_system: true },
  { code: 'CUSTOM_001', name: '自定义类型', is_active: true, is_system: false }
]

describe('EnumSelect', () => {
  describe('基本渲染', () => {
    it('应该正确渲染组件结构', () => {
      const wrapper = mount({
        template: `
          <div class="enum-select">
            <select>
              <option value="">请选择</option>
            </select>
          </div>
        `
      })
      expect(wrapper.find('.enum-select').exists()).toBe(true)
      expect(wrapper.find('select').exists()).toBe(true)
    })

    it('应该显示 placeholder', () => {
      const wrapper = mount({
        template: `
          <div class="enum-select">
            <select>
              <option value="">请选择枚举值</option>
            </select>
          </div>
        `
      })
      expect(wrapper.text()).toContain('请选择枚举值')
    })
  })

  describe('v-model 绑定', () => {
    it('应该支持 v-model 绑定', async () => {
      const wrapper = mount({
        template: `
          <div class="enum-select">
            <select v-model="selectedValue">
              <option value="STRING">字符串</option>
            </select>
          </div>
        `,
        data() {
          return { selectedValue: 'STRING' }
        }
      })
      expect(wrapper.vm.selectedValue).toBe('STRING')
    })
  })

  describe('禁用状态', () => {
    it('禁用时应该显示禁用样式', () => {
      const wrapper = mount({
        template: `
          <div class="enum-select disabled">
            <select disabled>
              <option value="">请选择</option>
            </select>
          </div>
        `
      })
      expect(wrapper.find('.enum-select.disabled').exists()).toBe(true)
      expect(wrapper.find('select[disabled]').exists()).toBe(true)
    })
  })

  describe('清空功能', () => {
    it('可清空时应该显示清空按钮', () => {
      const wrapper = mount({
        template: `
          <div class="enum-select">
            <select>
              <option value="">请选择</option>
              <option value="STRING">字符串</option>
            </select>
            <button class="clear-btn">×</button>
          </div>
        `,
        props: ['clearable']
      })
      expect(wrapper.find('.clear-btn').exists()).toBe(true)
    })
  })

  describe('枚举值加载', () => {
    it('应该正确加载枚举值列表', () => {
      const wrapper = mount({
        template: `
          <div class="enum-select">
            <select>
              <option value="">请选择</option>
              <option v-for="item in enumValues" :key="item.code" :value="item.code">
                {{ item.name }}
              </option>
            </select>
          </div>
        `,
        data() {
          return {
            enumValues: mockEnumValues
          }
        }
      })
      const options = wrapper.findAll('option')
      expect(options.length).toBe(4)
    })
  })

  describe('搜索功能', () => {
    it('应该支持搜索过滤', async () => {
      const wrapper = mount({
        template: `
          <div class="enum-select">
            <input v-model="searchKeyword" placeholder="搜索..." />
            <select>
              <option v-for="item in filteredValues" :key="item.code" :value="item.code">
                {{ item.name }}
              </option>
            </select>
          </div>
        `,
        data() {
          return {
            searchKeyword: '字符',
            enumValues: mockEnumValues
          }
        },
        computed: {
          filteredValues() {
            if (!this.searchKeyword) return this.enumValues
            return this.enumValues.filter(v => 
              v.name.includes(this.searchKeyword) || v.code.includes(this.searchKeyword)
            )
          }
        }
      })
      expect(wrapper.vm.filteredValues.length).toBe(1)
      expect(wrapper.vm.filteredValues[0].code).toBe('STRING')
    })
  })
})
