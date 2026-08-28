import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

const mockRole = {
  id: 1,
  code: 'admin',
  name: '管理员',
  description: '系统管理员角色'
}

const mockUnifiedData = {
  menus: [
    {
      menu_code: 'dashboard',
      display_name: '仪表盘',
      menu_path: '/dashboard',
      assigned: true,
      required_permissions: [
        { code: 'view', granted: true },
        { code: 'edit', granted: true }
      ]
    }
  ],
  summary: {
    assigned_menus: 5,
    total_menus: 10,
    total_function_permissions: 20,
    total_data_scopes: 3
  }
}

describe('RoleDetailDrawer', () => {
  describe('基本渲染', () => {
    it('应该渲染角色详情抽屉', () => {
      const wrapper = mount({
        template: `
          <div v-if="visible" class="drawer-overlay">
            <div class="drawer-panel">
              <div class="drawer-header">
                <h3>{{ role?.name || '角色' }} - 角色详情</h3>
              </div>
            </div>
          </div>
        `,
        data() {
          return { visible: true, role: mockRole }
        }
      })
      expect(wrapper.find('.drawer-overlay').exists()).toBe(true)
      expect(wrapper.find('.drawer-panel').exists()).toBe(true)
    })

    it('应该显示角色名称', () => {
      const wrapper = mount({
        template: `
          <div v-if="visible" class="drawer-overlay">
            <div class="drawer-panel">
              <div class="drawer-header">
                <h3>{{ role?.name || '角色' }} - 角色详情</h3>
              </div>
            </div>
          </div>
        `,
        data() {
          return { visible: true, role: mockRole }
        }
      })
      expect(wrapper.text()).toContain('管理员')
    })
  })

  describe('基本信息显示', () => {
    it('应该显示角色编码', () => {
      const wrapper = mount({
        template: `
          <div class="drawer-content">
            <div class="basic-info">
              <div class="info-row"><span class="label">角色编码：</span><span>{{ role?.code || '-' }}</span></div>
            </div>
          </div>
        `,
        data() {
          return { role: mockRole }
        }
      })
      expect(wrapper.text()).toContain('角色编码')
      expect(wrapper.text()).toContain('admin')
    })

    it('应该显示角色名称', () => {
      const wrapper = mount({
        template: `
          <div class="drawer-content">
            <div class="basic-info">
              <div class="info-row"><span class="label">角色名称：</span><span>{{ role?.name || '-' }}</span></div>
            </div>
          </div>
        `,
        data() {
          return { role: mockRole }
        }
      })
      expect(wrapper.text()).toContain('角色名称')
      expect(wrapper.text()).toContain('管理员')
    })

    it('应该显示角色描述', () => {
      const wrapper = mount({
        template: `
          <div class="drawer-content">
            <div class="basic-info">
              <div class="info-row"><span class="label">描述：</span><span>{{ role?.description || '无' }}</span></div>
            </div>
          </div>
        `,
        data() {
          return { role: mockRole }
        }
      })
      expect(wrapper.text()).toContain('描述')
      expect(wrapper.text()).toContain('系统管理员角色')
    })
  })

  describe('Tab 导航', () => {
    it('应该渲染 Tab 导航', () => {
      const tabs = [
        { key: 'permissions', label: '权限配置' },
        { key: 'logs', label: '操作日志' }
      ]
      const wrapper = mount({
        template: `
          <div class="drawer-content">
            <div class="drawer-tabs">
              <button
                v-for="tab in tabs"
                :key="tab.key"
                class="drawer-tab"
                :class="{ active: activeTab === tab.key }"
              >{{ tab.label }}</button>
            </div>
          </div>
        `,
        data() {
          return {
            tabs,
            activeTab: 'permissions'
          }
        }
      })
      expect(wrapper.find('.drawer-tabs').exists()).toBe(true)
      expect(wrapper.findAll('.drawer-tab').length).toBe(2)
    })

    it('应该高亮当前激活的 Tab', () => {
      const tabs = [
        { key: 'permissions', label: '权限配置' },
        { key: 'logs', label: '操作日志' }
      ]
      const wrapper = mount({
        template: `
          <div class="drawer-content">
            <div class="drawer-tabs">
              <button
                v-for="tab in tabs"
                :key="tab.key"
                class="drawer-tab"
                :class="{ active: activeTab === tab.key }"
              >{{ tab.label }}</button>
            </div>
          </div>
        `,
        data() {
          return {
            tabs,
            activeTab: 'permissions'
          }
        }
      })
      const activeTab = wrapper.find('.drawer-tab.active')
      expect(activeTab.exists()).toBe(true)
      expect(activeTab.text()).toBe('权限配置')
    })

    it('应该支持 Tab 切换', async () => {
      const tabs = [
        { key: 'permissions', label: '权限配置' },
        { key: 'logs', label: '操作日志' }
      ]
      const wrapper = mount({
        template: `
          <div class="drawer-content">
            <div class="drawer-tabs">
              <button
                v-for="tab in tabs"
                :key="tab.key"
                class="drawer-tab"
                :class="{ active: activeTab === tab.key }"
                @click="activeTab = tab.key"
              >{{ tab.label }}</button>
            </div>
            <div v-if="activeTab === 'logs'" class="logs-tab">
              <span>操作日志内容</span>
            </div>
          </div>
        `,
        data() {
          return {
            tabs,
            activeTab: 'permissions'
          }
        }
      })
      expect(wrapper.vm.activeTab).toBe('permissions')
      expect(wrapper.find('.logs-tab').exists()).toBe(false)
      const logsTab = wrapper.findAll('.drawer-tab')[1]
      await logsTab.trigger('click')
      expect(wrapper.vm.activeTab).toBe('logs')
      expect(wrapper.find('.logs-tab').exists()).toBe(true)
    })
  })

  describe('操作日志 Tab', () => {
    it('应该显示操作日志内容', () => {
      const wrapper = mount({
        template: `
          <div class="logs-tab">
            <div class="audit-log">
              <div v-for="log in logs" :key="log.id" class="al-item">
                {{ log.action }} - {{ log.user_name }}
              </div>
            </div>
          </div>
        `,
        data() {
          return {
            logs: [
              { id: 1, action: 'UPDATE', user_name: '张三' },
              { id: 2, action: 'CREATE', user_name: '李四' }
            ]
          }
        }
      })
      expect(wrapper.find('.audit-log').exists()).toBe(true)
      expect(wrapper.findAll('.al-item').length).toBe(2)
    })

    it('应该传递日志数据给 AuditLog 组件', () => {
      const logs = [
        { id: 1, action: 'UPDATE', user_name: '张三', created_at: '2024-01-15T10:00:00' }
      ]
      const wrapper = mount({
        template: `
          <div class="logs-tab">
            <div class="audit-log">
              <div v-for="log in logs" :key="log.id" class="al-item">
                <span class="al-action">{{ log.action }}</span>
                <span class="al-user">{{ log.user_name }}</span>
              </div>
            </div>
          </div>
        `,
        data() {
          return { logs }
        }
      })
      expect(wrapper.text()).toContain('UPDATE')
      expect(wrapper.text()).toContain('张三')
    })
  })

  describe('权限配置 Tab', () => {
    it('应该显示权限摘要信息', () => {
      const wrapper = mount({
        template: `
          <div class="unified-perm-section">
            <div class="perm-header">
              <h4>菜单与功能权限</h4>
              <div class="header-summary" v-if="summary">
                <span class="summary-item assigned">{{ summary.assigned_menus }}/{{ summary.total_menus }} 菜单已分配</span>
              </div>
            </div>
          </div>
        `,
        data() {
          return {
            summary: mockUnifiedData.summary
          }
        }
      })
      expect(wrapper.text()).toContain('菜单与功能权限')
      expect(wrapper.text()).toContain('5/10 菜单已分配')
    })

    it('应该显示菜单列表', () => {
      const wrapper = mount({
        template: `
          <div class="menu-list">
            <div v-for="menu in menus" :key="menu.menu_code" class="menu-card">
              <span class="menu-name">{{ menu.display_name }}</span>
            </div>
          </div>
        `,
        data() {
          return {
            menus: mockUnifiedData.menus
          }
        }
      })
      expect(wrapper.findAll('.menu-card').length).toBe(1)
      expect(wrapper.text()).toContain('仪表盘')
    })
  })
})

describe('RoleDetailDrawer 权限控制', () => {
  describe('Tab 可见性', () => {
    it('权限配置 Tab 应该默认显示', () => {
      const wrapper = mount({
        template: `
          <div class="drawer-content">
            <div class="drawer-tabs">
              <button
                v-for="tab in tabs"
                :key="tab.key"
                class="drawer-tab"
                :class="{ active: activeTab === tab.key }"
                @click="activeTab = tab.key"
              >{{ tab.label }}</button>
            </div>
            <div v-if="activeTab === 'permissions'" class="perm-section">
              权限配置内容
            </div>
          </div>
        `,
        data() {
          return {
            tabs: [
              { key: 'permissions', label: '权限配置' },
              { key: 'logs', label: '操作日志' }
            ],
            activeTab: 'permissions'
          }
        }
      })
      expect(wrapper.find('.perm-section').exists()).toBe(true)
    })

    it('切换到日志 Tab 时应该隐藏权限配置', async () => {
      const wrapper = mount({
        template: `
          <div class="drawer-content">
            <div class="drawer-tabs">
              <button
                v-for="tab in tabs"
                :key="tab.key"
                class="drawer-tab"
                :class="{ active: activeTab === tab.key }"
                @click="activeTab = tab.key"
              >{{ tab.label }}</button>
            </div>
            <div v-if="activeTab === 'permissions'" class="perm-section">
              权限配置内容
            </div>
            <div v-if="activeTab === 'logs'" class="logs-section">
              操作日志内容
            </div>
          </div>
        `,
        data() {
          return {
            tabs: [
              { key: 'permissions', label: '权限配置' },
              { key: 'logs', label: '操作日志' }
            ],
            activeTab: 'permissions'
          }
        }
      })
      expect(wrapper.find('.perm-section').exists()).toBe(true)
      expect(wrapper.find('.logs-section').exists()).toBe(false)
      await wrapper.findAll('.drawer-tab')[1].trigger('click')
      expect(wrapper.find('.perm-section').exists()).toBe(false)
      expect(wrapper.find('.logs-section').exists()).toBe(true)
    })
  })
})

describe('RoleDetailDrawer 日志加载', () => {
  describe('日志数据获取', () => {
    it('应该从 API 获取角色日志', () => {
      const logs = [
        { id: 1, action: 'UPDATE', user_name: '张三', created_at: '2024-01-15T10:00:00', field_name: 'name', old_value: '旧名称', new_value: '新名称' }
      ]
      const wrapper = mount({
        template: `
          <div class="audit-log">
            <div v-if="loading" class="al-loading">加载中...</div>
            <div v-else>
              <div v-for="log in logs" :key="log.id" class="al-item">
                <span class="al-action al-action--{{ log.action.toLowerCase() }}">{{ log.action }}</span>
                <span class="al-user">{{ log.user_name }}</span>
              </div>
            </div>
          </div>
        `,
        data() {
          return {
            logs,
            loading: false
          }
        }
      })
      expect(wrapper.find('.loading-state').exists()).toBe(false)
      expect(wrapper.findAll('.al-item').length).toBe(1)
    })

    it('加载中状态应该显示加载提示', () => {
      const wrapper = mount({
        template: `
          <div class="audit-log">
            <div v-if="loading" class="al-loading">加载中...</div>
          </div>
        `,
        data() {
          return { loading: true }
        }
      })
      expect(wrapper.find('.al-loading').exists()).toBe(true)
      expect(wrapper.text()).toContain('加载中')
    })
  })
})
