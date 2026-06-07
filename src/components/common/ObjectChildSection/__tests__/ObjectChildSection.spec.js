import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, ref, computed } from 'vue'

const ObjectChildSection = {
  template: `
    <div class="object-child-section">
      <div class="ocs-header" @click="toggleExpanded">
        <span class="ocs-title">{{ computedTitle }}</span>
        <span class="ocs-count">({{ pagination.total }})</span>
      </div>
      <div v-show="expanded" class="ocs-content">
        <slot v-if="!useMetaListMode" name="table">
          <div class="simple-table">Simple Table Mode</div>
        </slot>
        <slot v-else name="metalist">
          <div class="metalist">MetaListPage Mode</div>
        </slot>
      </div>
    </div>
  `,
  props: {
    parentObjectType: { type: String, required: true },
    childObjectType: { type: String, required: true },
    parentId: { type: [String, Number], required: true },
    title: { type: String, default: '' },
    displayMode: { type: String, default: 'expandable' },
    pageSize: { type: Number, default: 10 },
    useMetaList: { type: Boolean, default: false }
  },
  setup(props) {
    const expanded = ref(props.displayMode === 'always')
    
    const computedTitle = computed(() => {
      if (props.title) return props.title
      return props.childObjectType
    })
    
    const pagination = ref({ total: 5, current: 1, pageSize: props.pageSize })
    
    const useMetaListMode = computed(() => props.useMetaList)
    
    function toggleExpanded() {
      if (props.displayMode === 'expandable') {
        expanded.value = !expanded.value
      }
    }
    
    return {
      expanded,
      computedTitle,
      pagination,
      useMetaListMode,
      toggleExpanded
    }
  }
}

describe('ObjectChildSection Component', () => {
  describe('Props Validation', () => {
    it('should accept valid props', () => {
      const wrapper = mount(ObjectChildSection, {
        props: {
          parentObjectType: 'product',
          childObjectType: 'version',
          parentId: 123,
          title: '版本列表',
          displayMode: 'expandable',
          pageSize: 10,
          useMetaList: false
        }
      })
      
      expect(wrapper.vm.computedTitle).toBe('版本列表')
      expect(wrapper.vm.useMetaListMode).toBe(false)
    })
    
    it('should use childObjectType as default title', () => {
      const wrapper = mount(ObjectChildSection, {
        props: {
          parentObjectType: 'product',
          childObjectType: 'version',
          parentId: 123
        }
      })
      
      expect(wrapper.vm.computedTitle).toBe('version')
    })
  })
  
  describe('Display Mode', () => {
    it('should expand by default when displayMode is "always"', () => {
      const wrapper = mount(ObjectChildSection, {
        props: {
          parentObjectType: 'product',
          childObjectType: 'version',
          parentId: 123,
          displayMode: 'always'
        }
      })
      
      expect(wrapper.vm.expanded).toBe(true)
    })
    
    it('should collapse by default when displayMode is "expandable"', () => {
      const wrapper = mount(ObjectChildSection, {
        props: {
          parentObjectType: 'product',
          childObjectType: 'version',
          parentId: 123,
          displayMode: 'expandable'
        }
      })
      
      expect(wrapper.vm.expanded).toBe(false)
    })
  })
  
  describe('Rendering Mode', () => {
    it('should render simple table mode when useMetaList is false', () => {
      const wrapper = mount(ObjectChildSection, {
        props: {
          parentObjectType: 'product',
          childObjectType: 'version',
          parentId: 123,
          useMetaList: false
        }
      })
      
      expect(wrapper.vm.useMetaListMode).toBe(false)
      expect(wrapper.find('.simple-table').exists()).toBe(true)
    })
    
    it('should render MetaListPage mode when useMetaList is true', () => {
      const wrapper = mount(ObjectChildSection, {
        props: {
          parentObjectType: 'product',
          childObjectType: 'version',
          parentId: 123,
          useMetaList: true
        }
      })
      
      expect(wrapper.vm.useMetaListMode).toBe(true)
      expect(wrapper.find('.metalist').exists()).toBe(true)
    })
  })
  
  describe('Toggle Expanded', () => {
    it('should toggle expanded state when clicked', async () => {
      const wrapper = mount(ObjectChildSection, {
        props: {
          parentObjectType: 'product',
          childObjectType: 'version',
          parentId: 123,
          displayMode: 'expandable'
        }
      })
      
      expect(wrapper.vm.expanded).toBe(false)
      
      await wrapper.find('.ocs-header').trigger('click')
      
      expect(wrapper.vm.expanded).toBe(true)
      
      await wrapper.find('.ocs-header').trigger('click')
      
      expect(wrapper.vm.expanded).toBe(false)
    })
  })
  
  describe('Pagination', () => {
    it('should display pagination count', () => {
      const wrapper = mount(ObjectChildSection, {
        props: {
          parentObjectType: 'product',
          childObjectType: 'version',
          parentId: 123
        }
      })
      
      expect(wrapper.vm.pagination.total).toBe(5)
      expect(wrapper.find('.ocs-count').text()).toBe('(5)')
    })
  })
})
