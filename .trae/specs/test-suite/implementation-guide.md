# 测试用例实现指南

> **目标**: 为核心模块提供可执行的测试代码
>
> **框架**: Vitest + Vue Test Utils + MSW

---

## 一、环境配置

### 1.1 安装依赖

```bash
npm install -D vitest @vue/test-utils happy-dom msw
```

### 1.2 Vitest 配置

```javascript
// vitest.config.js
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: {
    globals: true,
    environment: 'happy-dom',
    setupFiles: ['./tests/setup.js'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: [
        'node_modules/**',
        'tests/**',
        '**/*.spec.js'
      ]
    }
  }
})
```

### 1.3 测试设置文件

```javascript
// tests/setup.js
import { afterAll, afterEach, beforeAll } from 'vitest'
import { server } from './mocks/server'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
afterEach(() => server.resetHandlers())
```

---

## 二、useMetaList 测试实现

### 2.1 测试文件

```javascript
// tests/unit/composables/useMetaList.spec.js
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { flushPromises } from '@vue/test-utils'

// Mock boService
vi.mock('@/services/boService', () => ({
  default: {
    query: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    batchDelete: vi.fn()
  }
}))

import useMetaList from '@/composables/useMetaList'
import boService from '@/services/boService'

describe('useMetaList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('列表加载', () => {
    it('应该正确初始化状态', () => {
      const { items, loading, pagination, error } = useMetaList('user')
      
      expect(items.value).toEqual([])
      expect(loading.value).toBe(false)
      expect(pagination.current).toBe(1)
      expect(pagination.pageSize).toBe(20)
      expect(error.value).toBeNull()
    })

    it('加载数据应该更新items和total', async () => {
      const mockData = {
        items: [
          { id: 1, username: 'user1' },
          { id: 2, username: 'user2' }
        ],
        total: 100
      }
      
      boService.query.mockResolvedValue({
        success: true,
        data: mockData
      })
      
      const { loadList, items, pagination } = useMetaList('user')
      await loadList()
      
      expect(items.value).toEqual(mockData.items)
      expect(pagination.total).toBe(100)
    })

    it('加载失败应该设置错误信息', async () => {
      boService.query.mockRejectedValue(new Error('Network error'))
      
      const { loadList, error } = useMetaList('user')
      await loadList()
      
      expect(error.value).toBe('Network error')
    })
  })

  describe('分页功能', () => {
    it('跳页应该更新page参数', async () => {
      boService.query.mockResolvedValue({
        success: true,
        data: { items: [], total: 0 }
      })
      
      const { goToPage } = useMetaList('user')
      await goToPage(3)
      
      expect(boService.query).toHaveBeenCalledWith(
        'user',
        expect.objectContaining({ page: 3 })
      )
    })

    it('改变pageSize应该重置到第一页', async () => {
      boService.query.mockResolvedValue({
        success: true,
        data: { items: [], total: 0 }
      })
      
      const { setPageSize, pagination } = useMetaList('user')
      await setPageSize(50)
      
      expect(pagination.current).toBe(1)
      expect(pagination.pageSize).toBe(50)
    })
  })

  describe('过滤功能', () => {
    it('关键词搜索应该添加search参数', async () => {
      boService.query.mockResolvedValue({
        success: true,
        data: { items: [], total: 0 }
      })
      
      const { setKeyword } = useMetaList('user')
      await setKeyword('test')
      
      expect(boService.query).toHaveBeenCalledWith(
        'user',
        expect.objectContaining({ search: 'test' })
      )
    })

    it('清空关键词应该移除search参数', async () => {
      boService.query.mockResolvedValue({
        success: true,
        data: { items: [], total: 0 }
      })
      
      const { setKeyword } = useMetaList('user')
      await setKeyword('test')
      await setKeyword('')
      
      expect(boService.query).toHaveBeenLastCalledWith(
        'user',
        expect.not.objectContaining({ search: expect.anything() })
      )
    })
  })

  describe('批量选择', () => {
    it('切换选择应该更新selectedIds', () => {
      const { toggleSelection, selectedIds } = useMetaList('user')
      const user = { id: 1, username: 'test' }
      
      toggleSelection(user)
      expect(selectedIds.value.has(1)).toBe(true)
      
      toggleSelection(user)
      expect(selectedIds.value.has(1)).toBe(false)
    })

    it('全选当前页应该选中所有记录', async () => {
      const mockItems = [
        { id: 1, username: 'user1' },
        { id: 2, username: 'user2' }
      ]
      
      boService.query.mockResolvedValue({
        success: true,
        data: { items: mockItems, total: 2 }
      })
      
      const { loadList, selectAllCurrentPage, selectedIds } = useMetaList('user')
      await loadList()
      selectAllCurrentPage()
      
      expect(selectedIds.value.size).toBe(2)
    })
  })
})
```

---

## 三、useImportExportApi 测试实现

### 3.1 测试文件

```javascript
// tests/unit/composables/useImportExportApi.spec.js
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Mock fetch
global.fetch = vi.fn()

describe('useImportExportApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.setItem('auth_token', 'test-token-123')
  })

  afterEach(() => {
    localStorage.removeItem('auth_token')
  })

  describe('导出功能', () => {
    it('应该包含Authorization头', async () => {
      fetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { download_url: '/test.xlsx' }
        })
      })
      
      const { exportData } = useImportExportApi()
      await exportData('user', { scope: 'single' })
      
      expect(fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            'Authorization': 'Bearer test-token-123'
          })
        })
      )
    })

    it('成功应该返回download_url', async () => {
      fetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { download_url: '/api/v1/export/download/test.xlsx' }
        })
      })
      
      const { exportData } = useImportExportApi()
      const result = await exportData('user', { scope: 'single' })
      
      expect(result.success).toBe(true)
      expect(result.data.download_url).toBe('/api/v1/export/download/test.xlsx')
    })

    it('失败应该返回错误信息', async () => {
      fetch.mockResolvedValue({
        ok: false,
        status: 500,
        json: () => Promise.resolve({
          success: false,
          message: 'Export failed'
        })
      })
      
      const { exportData } = useImportExportApi()
      const result = await exportData('user', { scope: 'single' })
      
      expect(result.success).toBe(false)
      expect(result.message).toBe('Export failed')
    })
  })

  describe('模板下载', () => {
    it('应该使用正确的URL', async () => {
      fetch.mockResolvedValue({
        ok: true,
        blob: () => Promise.resolve(new Blob(['template']))
      })
      
      const { downloadTemplate } = useImportExportApi()
      await downloadTemplate('user')
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/import/template/user'),
        expect.any(Object)
      )
    })
  })
})
```

---

## 四、组件测试实现

### 4.1 ExportDialog 测试

```javascript
// tests/component/ExportDialog.spec.js
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ExportDialog from '@/components/common/ExportDialog/ExportDialog.vue'

// Mock useImportExportApi
vi.mock('@/composables/useImportExportApi', () => ({
  useImportExportApi: () => ({
    exportData: vi.fn().mockResolvedValue({
      success: true,
      data: { download_url: '/test.xlsx' }
    })
  })
}))

describe('ExportDialog', () => {
  it('显示对话框当visible为true', () => {
    const wrapper = mount(ExportDialog, {
      props: {
        visible: true,
        objectType: 'user'
      }
    })
    
    expect(wrapper.find('.el-dialog').isVisible()).toBe(true)
  })

  it('隐藏对话框当visible为false', () => {
    const wrapper = mount(ExportDialog, {
      props: {
        visible: false,
        objectType: 'user'
      }
    })
    
    expect(wrapper.find('.el-dialog').isVisible()).toBe(false)
  })

  it('关闭对话框应该触发update:visible事件', async () => {
    const wrapper = mount(ExportDialog, {
      props: {
        visible: true,
        objectType: 'user'
      }
    })
    
    await wrapper.find('.el-dialog__headerbtn').trigger('click')
    
    expect(wrapper.emitted('update:visible')[0]).toEqual([false])
  })

  it('点击开始导出应该调用API', async () => {
    const { useImportExportApi } = vi.mocked('@/composables/useImportExportApi')
    const exportData = vi.fn().mockResolvedValue({
      success: true,
      data: { download_url: '/test.xlsx' }
    })
    useImportExportApi.mockReturnValue({ exportData })
    
    const wrapper = mount(ExportDialog, {
      props: {
        visible: true,
        objectType: 'user'
      }
    })
    
    await wrapper.find('button:contains("开始导出")').trigger('click')
    
    expect(exportData).toHaveBeenCalled()
  })
})
```

### 4.2 TableHeaderFilter 测试

```javascript
// tests/component/TableHeaderFilter.spec.js
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TableHeaderFilter from '@/components/common/TableHeaderFilter/TableHeaderFilter.vue'

describe('TableHeaderFilter', () => {
  describe('过滤控件渲染', () => {
    it('search类型应该渲染文本输入框', () => {
      const wrapper = mount(TableHeaderFilter, {
        props: {
          filterType: 'search',
          visible: true
        }
      })
      
      expect(wrapper.find('input').exists()).toBe(true)
    })

    it('select类型应该渲染下拉选择框', () => {
      const wrapper = mount(TableHeaderFilter, {
        props: {
          filterType: 'select',
          options: [
            { label: '活跃', value: 'active' },
            { label: '禁用', value: 'disabled' }
          ],
          visible: true
        }
      })
      
      expect(wrapper.find('select').exists()).toBe(true)
      expect(wrapper.findAll('option')).toHaveLength(2)
    })

    it('date-range类型应该渲染日期选择器', () => {
      const wrapper = mount(TableHeaderFilter, {
        props: {
          filterType: 'date-range',
          visible: true
        }
      })
      
      expect(wrapper.find('.el-date-editor').exists()).toBe(true)
    })
  })

  describe('过滤值管理', () => {
    it('输入值应该触发update事件', async () => {
      const wrapper = mount(TableHeaderFilter, {
        props: {
          filterType: 'search',
          visible: true
        }
      })
      
      await wrapper.find('input').setValue('test')
      
      expect(wrapper.emitted('update:modelValue')[0]).toEqual(['test'])
    })

    it('清空应该触发reset事件', async () => {
      const wrapper = mount(TableHeaderFilter, {
        props: {
          filterType: 'search',
          modelValue: 'test',
          visible: true
        }
      })
      
      await wrapper.find('input').clear()
      
      expect(wrapper.emitted('reset')).toBeTruthy()
    })
  })
})
```

---

## 五、集成测试实现

### 5.1 UserManagement 集成测试

```javascript
// tests/integration/UserManagement.spec.js
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import UserManagement from '@/views/SystemManagement/UserManagement.vue'

// Mock路由
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/user-permission', component: UserManagement }
  ]
})

// Mock服务
vi.mock('@/services/boService', () => ({
  default: {
    query: vi.fn().mockResolvedValue({
      success: true,
      data: { items: [], total: 0 }
    })
  }
}))

describe('UserManagement 集成测试', () => {
  let wrapper

  beforeEach(async () => {
    vi.clearAllMocks()
    wrapper = mount(UserManagement, {
      global: {
        plugins: [router]
      }
    })
    await flushPromises()
  })

  describe('列表功能', () => {
    it('应该显示表格', () => {
      expect(wrapper.find('.el-table').exists()).toBe(true)
    })

    it('应该显示分页组件', () => {
      expect(wrapper.find('.el-pagination').exists()).toBe(true)
    })

    it('应该显示工具栏', () => {
      expect(wrapper.find('.toolbar').exists()).toBe(true)
    })
  })

  describe('搜索功能', () => {
    it('输入关键词点击搜索应该过滤数据', async () => {
      await wrapper.find('input[placeholder*="搜索"]').setValue('test')
      await wrapper.find('button:contains("搜索")').trigger('click')
      
      expect(wrapper.vm.keyword).toBe('test')
    })
  })

  describe('批量选择', () => {
    it('选中记录应该更新选中计数', async () => {
      await wrapper.find('.el-table__body tr').trigger('click')
      
      expect(wrapper.vm.selectedIds.size).toBeGreaterThan(0)
    })
  })
})
```

---

## 六、MSW Mock 配置

### 6.1 Server 配置

```javascript
// tests/mocks/server.js
import { setupServer } from 'msw/node'
import { handlers } from './handlers'

export const server = setupServer(...handlers)
```

### 6.2 Handlers 配置

```javascript
// tests/mocks/handlers.js
import { rest } from 'msw'

export const handlers = [
  // 列表查询
  rest.get('/api/v2/bo/:entity', (req, res, ctx) => {
    const { entity } = req.params
    const page = parseInt(req.url.searchParams.get('page')) || 1
    const pageSize = parseInt(req.url.searchParams.get('page_size')) || 20
    
    const mockData = Array.from({ length: pageSize }, (_, i) => ({
      id: (page - 1) * pageSize + i + 1,
      username: `user_${(page - 1) * pageSize + i + 1}`,
      email: `user_${(page - 1) * pageSize + i + 1}@example.com`,
      status: 'active'
    }))
    
    return res(
      ctx.json({
        success: true,
        data: {
          items: mockData,
          total: 100,
          page,
          page_size: pageSize
        }
      })
    )
  }),

  // 导出
  rest.post('/api/v1/export', (req, res, ctx) => {
    return res(
      ctx.json({
        success: true,
        data: {
          download_url: `/api/v1/export/download/${Date.now()}.xlsx`,
          total_rows: 100
        }
      })
    )
  }),

  // 导入预览
  rest.post('/api/v1/import/preview', (req, res, ctx) => {
    return res(
      ctx.json({
        success: true,
        data: {
          sheet_count: 1,
          preview: [
            { name: 'Test User', email: 'test@example.com' }
          ],
          errors: []
        }
      })
    )
  }),

  // 导入执行
  rest.post('/api/v1/import', (req, res, ctx) => {
    return res(
      ctx.json({
        success: true,
        data: {
          imported: 10,
          skipped: 0,
          errors: []
        }
      })
    )
  })
]
```

### 6.3 错误处理 Handlers

```javascript
// tests/mocks/errorHandlers.js
import { rest } from 'msw'

export const errorHandlers = [
  // 401 未授权
  rest.get('/api/v2/bo/:entity', (req, res, ctx) => {
    return res(
      ctx.status(401),
      ctx.json({
        success: false,
        message: 'Unauthorized'
      })
    )
  }),

  // 500 服务器错误
  rest.post('/api/v1/export', (req, res, ctx) => {
    return res(
      ctx.status(500),
      ctx.json({
        success: false,
        message: 'Internal server error'
      })
    )
  })
]
```

---

## 七、运行测试

### 7.1 运行所有测试

```bash
npm test
```

### 7.2 运行单元测试

```bash
npm run test:unit
```

### 7.3 运行组件测试

```bash
npm run test:component
```

### 7.4 运行集成测试

```bash
npm run test:integration
```

### 7.5 生成覆盖率报告

```bash
npm run test:coverage
```

### 7.6 监视模式

```bash
npm run test:watch
```
