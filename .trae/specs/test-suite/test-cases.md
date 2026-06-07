# 核心模块测试用例规范

> **目标**: 基于当前完成情况，为核心模块完备测试用例
>
> **范围**: useMetaList, useImportExportApi, ExportDialog, ImportDialog, TableHeaderFilter, UserManagement
>
> **测试覆盖率目标**: 90%+

---

## 一、测试用例管理

### 1.1 测试文件位置

```
tests/
├── unit/
│   ├── composables/
│   │   ├── useMetaList.spec.js
│   │   ├── useImportExportApi.spec.js
│   │   └── useAssociation.spec.js
│   └── utils/
│       ├── filterBuilder.spec.js
│       └── queryParams.spec.js
│
├── component/
│   ├── ExportDialog.spec.js
│   ├── ImportDialog.spec.js
│   ├── TableHeaderFilter.spec.js
│   └── AssociationPanel.spec.js
│
├── integration/
│   ├── UserManagement.spec.js
│   ├── RoleManagement.spec.js
│   └── AssociationOperations.spec.js
│
└── e2e/
    ├── list-operations.spec.js
    ├── import-export.spec.js
    └── association-workflow.spec.js
```

### 1.2 测试工具

- **单元测试**: Vitest + Vue Test Utils
- **组件测试**: Vitest + @vue/test-utils
- **E2E测试**: Playwright
- **API Mock**: MSW (Mock Service Worker)

---

## 二、useMetaList 测试用例

### 2.1 模块概述

**文件**: `src/composables/useMetaList.js`

**核心能力**:
- 列表加载与分页
- 过滤条件构建
- 排序参数处理
- 列定义转换
- 批量选择管理
- 工具栏操作处理

### 2.2 测试用例

#### TC-ML-001: 列表加载

```javascript
describe('useMetaList - 列表加载', () => {
  test('TC-ML-001-01: 初始加载应获取第一页数据', async () => {
    // Arrange
    const mockData = { items: [...], total: 100 }
    vi.spyOn(boService, 'query').mockResolvedValue({
      success: true,
      data: { items: mockData.items, total: 100 }
    })
    
    // Act
    const { loadList } = useMetaList('user')
    await loadList()
    
    // Assert
    expect(boService.query).toHaveBeenCalledWith(
      'user',
      expect.objectContaining({ page: 1, page_size: 20 })
    )
  })

  test('TC-ML-001-02: 加载成功应更新items和total', async () => {
    // Arrange
    const mockData = { items: genUsers(20), total: 100 }
    
    // Act
    const { loadList, items, pagination } = useMetaList('user')
    await loadList()
    
    // Assert
    expect(items.value).toHaveLength(20)
    expect(pagination.total).toBe(100)
  })

  test('TC-ML-001-03: 加载失败应设置错误信息', async () => {
    // Arrange
    vi.spyOn(boService, 'query').mockRejectedValue(new Error('Network error'))
    
    // Act
    const { loadList, error } = useMetaList('user')
    await loadList()
    
    // Assert
    expect(error.value).toBe('Network error')
  })

  test('TC-ML-001-04: 加载中应设置loading状态', async () => {
    // Arrange
    let resolveFn
    const promise = new Promise(resolve => { resolveFn = resolve })
    vi.spyOn(boService, 'query').mockReturnValue(promise)
    
    // Act
    const { loadList, loading } = useMetaList('user')
    const loadPromise = loadList()
    expect(loading.value).toBe(true)
    
    resolveFn({ success: true, data: { items: [], total: 0 } })
    await loadPromise
    
    // Assert
    expect(loading.value).toBe(false)
  })
})
```

#### TC-ML-002: 分页功能

```javascript
describe('useMetaList - 分页功能', () => {
  test('TC-ML-002-01: 跳转到指定页应更新page参数', async () => {
    // Arrange
    const { goToPage } = useMetaList('user')
    
    // Act
    await goToPage(3)
    
    // Assert
    expect(boService.query).toHaveBeenCalledWith(
      'user',
      expect.objectContaining({ page: 3 })
    )
  })

  test('TC-ML-002-02: 改变pageSize应重新加载', async () => {
    // Arrange
    const { setPageSize } = useMetaList('user')
    
    // Act
    await setPageSize(50)
    
    // Assert
    expect(boService.query).toHaveBeenCalledWith(
      'user',
      expect.objectContaining({ page_size: 50, page: 1 })
    )
  })

  test('TC-ML-002-03: 翻页后应重置到第一页', async () => {
    // Arrange
    const { setPageSize, pagination } = useMetaList('user')
    await goToPage(5)
    
    // Act
    await setPageSize(100)
    
    // Assert
    expect(pagination.current).toBe(1)
  })

  test('TC-ML-002-04: 总数计算应正确', async () => {
    // Arrange
    vi.spyOn(boService, 'query').mockResolvedValue({
      success: true,
      data: { items: genUsers(20), total: 150 }
    })
    
    // Act
    const { loadList, pagination } = useMetaList('user')
    await loadList()
    
    // Assert
    expect(pagination.total).toBe(150)
    expect(pagination.totalPages).toBe(8) // 150/20 = 7.5 → 8
  })
})
```

#### TC-ML-003: 过滤功能

```javascript
describe('useMetaList - 过滤功能', () => {
  test('TC-ML-003-01: 关键词搜索应添加search参数', async () => {
    // Arrange
    const { setKeyword } = useMetaList('user')
    
    // Act
    await setKeyword('test')
    
    // Assert
    expect(boService.query).toHaveBeenCalledWith(
      'user',
      expect.objectContaining({ search: 'test' })
    )
  })

  test('TC-ML-003-02: 清空关键词应移除search参数', async () => {
    // Arrange
    const { setKeyword } = useMetaList('user')
    await setKeyword('test')
    
    // Act
    await setKeyword('')
    
    // Assert
    expect(boService.query).toHaveBeenLastCalledWith(
      'user',
      expect.not.objectContaining({ search: expect.anything() })
    )
  })

  test('TC-ML-003-03: 表头过滤应构建正确的过滤参数', async () => {
    // Arrange
    const { setHeaderFilter } = useMetaList('user')
    
    // Act
    await setHeaderFilter('status', 'active')
    
    // Assert
    expect(boService.query).toHaveBeenCalledWith(
      'user',
      expect.objectContaining({ status: 'active' })
    )
  })

  test('TC-ML-003-04: 日期范围过滤应生成start和end参数', async () => {
    // Arrange
    const { setHeaderFilter } = useMetaList('user')
    const startDate = '2026-05-01 00:00:00'
    const endDate = '2026-05-09 23:59:59'
    
    // Act
    await setHeaderFilter('created_at', [startDate, endDate])
    
    // Assert
    expect(boService.query).toHaveBeenCalledWith(
      'user',
      expect.objectContaining({
        created_at_start: startDate,
        created_at_end: endDate
      })
    )
  })

  test('TC-ML-003-05: 重置过滤应清除所有过滤条件', async () => {
    // Arrange
    const { setKeyword, setHeaderFilter, resetFilters } = useMetaList('user')
    await setKeyword('test')
    await setHeaderFilter('status', 'active')
    
    // Act
    await resetFilters()
    
    // Assert
    expect(boService.query).toHaveBeenLastCalledWith(
      'user',
      expect.not.objectContaining({
        search: expect.anything(),
        status: expect.anything()
      })
    )
  })

  test('TC-ML-003-06: 多字段过滤应使用AND关系', async () => {
    // Arrange
    const { setKeyword, setHeaderFilter } = useMetaList('user')
    
    // Act
    await setKeyword('test')
    await setHeaderFilter('status', 'active')
    
    // Assert
    expect(boService.query).toHaveBeenCalledWith(
      'user',
      expect.objectContaining({
        search: 'test',
        status: 'active'
      })
    )
  })
})
```

#### TC-ML-004: 排序功能

```javascript
describe('useMetaList - 排序功能', () => {
  test('TC-ML-004-01: 点击升序应设置ordering参数', async () => {
    // Arrange
    const { setSort } = useMetaList('user')
    
    // Act
    await setSort('username', 'ascending')
    
    // Assert
    expect(boService.query).toHaveBeenCalledWith(
      'user',
      expect.objectContaining({ ordering: 'username' })
    )
  })

  test('TC-ML-004-02: 点击降序应设置-前缀', async () => {
    // Arrange
    const { setSort } = useMetaList('user')
    
    // Act
    await setSort('username', 'descending')
    
    // Assert
    expect(boService.query).toHaveBeenCalledWith(
      'user',
      expect.objectContaining({ ordering: '-username' })
    )
  })

  test('TC-ML-004-03: 再次点击同一列应切换排序方向', async () => {
    // Arrange
    const { setSort, sortInfo } = useMetaList('user')
    await setSort('username', 'ascending')
    
    // Act
    await setSort('username', 'descending')
    
    // Assert
    expect(sortInfo.value.order).toBe('descending')
  })

  test('TC-ML-004-04: 切换排序列应清除之前的排序', async () => {
    // Arrange
    const { setSort } = useMetaList('user')
    await setSort('username', 'ascending')
    
    // Act
    await setSort('email', 'ascending')
    
    // Assert
    expect(boService.query).toHaveBeenLastCalledWith(
      'user',
      expect.objectContaining({ ordering: 'email' })
    )
    expect(sortInfo.value.prop).toBe('email')
  })
})
```

#### TC-ML-005: 批量选择

```javascript
describe('useMetaList - 批量选择', () => {
  test('TC-ML-005-01: 选择单条记录应添加到selectedIds', () => {
    // Arrange
    const { toggleSelection, selectedIds } = useMetaList('user')
    const user = { id: 1, username: 'test' }
    
    // Act
    toggleSelection(user)
    
    // Assert
    expect(selectedIds.value.has(1)).toBe(true)
  })

  test('TC-ML-005-02: 取消选择应从selectedIds移除', () => {
    // Arrange
    const { toggleSelection, selectedIds } = useMetaList('user')
    const user = { id: 1, username: 'test' }
    toggleSelection(user)
    
    // Act
    toggleSelection(user)
    
    // Assert
    expect(selectedIds.value.has(1)).toBe(false)
  })

  test('TC-ML-005-03: 全选当前页应选中所有记录', async () => {
    // Arrange
    vi.spyOn(boService, 'query').mockResolvedValue({
      success: true,
      data: { items: genUsers(20), total: 100 }
    })
    
    const { loadList, selectAllCurrentPage, selectedIds } = useMetaList('user')
    await loadList()
    
    // Act
    selectAllCurrentPage()
    
    // Assert
    expect(selectedIds.value.size).toBe(20)
  })

  test('TC-ML-005-04: 翻页应保留之前的选择', async () => {
    // Arrange
    const { loadList, goToPage, toggleSelection, selectedIds } = useMetaList('user')
    await loadList()
    await toggleSelection({ id: 1, username: 'test1' })
    await toggleSelection({ id: 5, username: 'test5' })
    
    // Act
    await goToPage(2)
    await loadList()
    
    // Assert
    expect(selectedIds.value.has(1)).toBe(true)
    expect(selectedIds.value.has(5)).toBe(true)
  })

  test('TC-ML-005-05: 清除选择应清空所有selectedIds', () => {
    // Arrange
    const { toggleSelection, clearAllSelection, selectedIds } = useMetaList('user')
    toggleSelection({ id: 1 })
    toggleSelection({ id: 2 })
    toggleSelection({ id: 3 })
    
    // Act
    clearAllSelection()
    
    // Assert
    expect(selectedIds.value.size).toBe(0)
  })

  test('TC-ML-005-06: 已选择数量应正确计算', () => {
    // Arrange
    const { toggleSelection, totalSelectedCount } = useMetaList('user')
    toggleSelection({ id: 1 })
    toggleSelection({ id: 2 })
    
    // Assert
    expect(totalSelectedCount.value).toBe(2)
  })
})
```

#### TC-ML-006: 工具栏操作

```javascript
describe('useMetaList - 工具栏操作', () => {
  test('TC-ML-006-01: 新建操作应触发事件', async () => {
    // Arrange
    const { handleToolbarAction, emit } = useMetaList('user')
    
    // Act
    await handleToolbarAction({ key: 'create', label: '新建' })
    
    // Assert
    expect(emit).toHaveBeenCalledWith('action', expect.objectContaining({
      action: expect.objectContaining({ key: 'create' })
    }))
  })

  test('TC-ML-006-02: 导出操作应打开导出对话框', async () => {
    // Arrange
    const { handleToolbarAction, showExportDialog } = useMetaList('user')
    
    // Act
    await handleToolbarAction({ key: 'export', label: '导出' })
    
    // Assert
    expect(showExportDialog.value).toBe(true)
  })

  test('TC-ML-006-03: 导入操作应打开导入对话框', async () => {
    // Arrange
    const { handleToolbarAction, showImportDialog } = useMetaList('user')
    
    // Act
    await handleToolbarAction({ key: 'import', label: '导入' })
    
    // Assert
    expect(showImportDialog.value).toBe(true)
  })

  test('TC-ML-006-04: 刷新操作应重新加载列表', async () => {
    // Arrange
    const { handleToolbarAction } = useMetaList('user')
    
    // Act
    await handleToolbarAction({ key: 'refresh', label: '刷新' })
    
    // Assert
    expect(boService.query).toHaveBeenCalled()
  })
})
```

---

## 三、useImportExportApi 测试用例

### 3.1 模块概述

**文件**: `src/composables/useImportExportApi.js`

**核心能力**:
- 导出数据
- 下载模板
- 导入预览
- 执行导入
- 认证token管理

### 3.2 测试用例

#### TC-IE-001: 导出功能

```javascript
describe('useImportExportApi - 导出功能', () => {
  beforeEach(() => {
    localStorage.setItem('auth_token', 'test-token')
  })

  afterEach(() => {
    localStorage.removeItem('auth_token')
  })

  test('TC-IE-001-01: 导出应包含Authorization头', async () => {
    // Arrange
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        success: true,
        data: { download_url: '/api/v1/export/download/test.xlsx' }
      })
    })
    
    // Act
    const { exportData } = useImportExportApi()
    await exportData('user', { scope: 'single' })
    
    // Assert
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/export'),
      expect.objectContaining({
        headers: expect.objectContaining({
          'Authorization': 'Bearer test-token'
        })
      })
    )
  })

  test('TC-IE-001-02: 导出单对象应发送正确参数', async () => {
    // Arrange
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        success: true,
        data: { download_url: '/api/v1/export/download/test.xlsx' }
      })
    })
    
    // Act
    const { exportData } = useImportExportApi()
    await exportData('user', {
      scope: 'single',
      filters: { status: 'active' },
      options: { exclude_sensitive: true }
    })
    
    // Assert
    expect(fetch).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          object_type: 'user',
          scope: 'single',
          filters: { status: 'active' },
          options: { exclude_sensitive: true }
        })
      })
    )
  })

  test('TC-IE-001-03: 导出失败应返回错误', async () => {
    // Arrange
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: () => Promise.resolve({
        success: false,
        message: 'Export failed'
      })
    })
    
    // Act
    const { exportData } = useImportExportApi()
    const result = await exportData('user', { scope: 'single' })
    
    // Assert
    expect(result.success).toBe(false)
    expect(result.message).toBe('Export failed')
  })
})
```

#### TC-IE-002: 模板下载

```javascript
describe('useImportExportApi - 模板下载', () => {
  test('TC-IE-002-01: 下载模板应使用正确的URL', async () => {
    // Arrange
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      blob: () => Promise.resolve(new Blob(['template']))
    })
    
    // Act
    const { downloadTemplate } = useImportExportApi()
    await downloadTemplate('user')
    
    // Assert
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/import/template/user'),
      expect.anything()
    )
  })

  test('TC-IE-002-02: 下载模板应包含认证token', async () => {
    // Arrange
    localStorage.setItem('auth_token', 'test-token')
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      blob: () => Promise.resolve(new Blob(['template']))
    })
    
    // Act
    const { downloadTemplate } = useImportExportApi()
    await downloadTemplate('user')
    
    // Assert
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('token=test-token'),
      expect.anything()
    )
  })
})
```

#### TC-IE-003: 导入预览

```javascript
describe('useImportExportApi - 导入预览', () => {
  test('TC-IE-003-01: 预览应返回文件内容', async () => {
    // Arrange
    const mockFile = new File(['name,email\ntest,test@example.com'], 'test.csv', {
      type: 'text/csv'
    })
    
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        success: true,
        data: {
          sheet_count: 1,
          preview: [
            { name: 'test', email: 'test@example.com' }
          ]
        }
      })
    })
    
    // Act
    const { previewImport } = useImportExportApi()
    const result = await previewImport('user', mockFile)
    
    // Assert
    expect(result.success).toBe(true)
    expect(result.data.preview).toHaveLength(1)
  })

  test('TC-IE-003-02: 预览应返回校验错误', async () => {
    // Arrange
    const mockFile = new File(['name,email\n,invalid'], 'test.csv', {
      type: 'text/csv'
    })
    
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        success: true,
        data: {
          errors: [
            { row: 1, field: 'name', message: '必填字段不能为空' }
          ]
        }
      })
    })
    
    // Act
    const { previewImport } = useImportExportApi()
    const result = await previewImport('user', mockFile)
    
    // Assert
    expect(result.data.errors).toHaveLength(1)
    expect(result.data.errors[0].message).toBe('必填字段不能为空')
  })
})
```

---

## 四、ExportDialog 组件测试

### 4.1 组件概述

**文件**: `src/components/common/ExportDialog/ExportDialog.vue`

**核心能力**:
- 导出选项配置
- 导出进度显示
- 导出结果处理

### 4.2 测试用例

#### TC-ED-001: 对话框显示

```javascript
describe('ExportDialog - 对话框显示', () => {
  test('TC-ED-001-01: visible为true时应显示对话框', () => {
    // Arrange & Act
    const wrapper = mount(ExportDialog, {
      props: {
        visible: true,
        objectType: 'user'
      }
    })
    
    // Assert
    expect(wrapper.findComponent({ name: 'ElDialog' }).props('modelValue')).toBe(true)
  })

  test('TC-ED-001-02: visible为false时应隐藏对话框', () => {
    // Arrange & Act
    const wrapper = mount(ExportDialog, {
      props: {
        visible: false,
        objectType: 'user'
      }
    })
    
    // Assert
    expect(wrapper.findComponent({ name: 'ElDialog' }).props('modelValue')).toBe(false)
  })

  test('TC-ED-001-03: 对话框标题应包含对象名称', () => {
    // Arrange & Act
    const wrapper = mount(ExportDialog, {
      props: {
        visible: true,
        objectType: 'user'
      }
    })
    
    // Assert
    expect(wrapper.find('.el-dialog__title').text()).toContain('用户')
  })
})
```

#### TC-ED-002: 导出选项

```javascript
describe('ExportDialog - 导出选项', () => {
  test('TC-ED-002-01: 默认应选中"导出筛选后的数据"', () => {
    // Arrange & Act
    const wrapper = mount(ExportDialog, {
      props: {
        visible: true,
        objectType: 'user',
        filters: { status: 'active' }
      }
    })
    
    // Assert
    expect(wrapper.find('input[value="includeFilters"]').element.checked).toBe(true)
  })

  test('TC-ED-002-02: 切换选项应更新options', async () => {
    // Arrange
    const wrapper = mount(ExportDialog, {
      props: {
        visible: true,
        objectType: 'user'
      }
    })
    
    // Act
    await wrapper.find('input[value="excludeSensitive"]').setChecked()
    
    // Assert
    expect(wrapper.vm.options.excludeSensitive).toBe(true)
  })
})
```

#### TC-ED-003: 导出执行

```javascript
describe('ExportDialog - 导出执行', () => {
  test('TC-ED-003-01: 点击"开始导出"应调用导出API', async () => {
    // Arrange
    const exportData = vi.fn().mockResolvedValue({
      success: true,
      data: { download_url: '/api/v1/export/download/test.xlsx' }
    })
    
    const wrapper = mount(ExportDialog, {
      props: {
        visible: true,
        objectType: 'user'
      },
      global: {
        mocks: {
          useImportExportApi: () => ({ exportData })
        }
      }
    })
    
    // Act
    await wrapper.find('button:contains("开始导出")').trigger('click')
    
    // Assert
    expect(exportData).toHaveBeenCalledWith('user', expect.any(Object))
  })

  test('TC-ED-003-02: 导出中应显示进度条', async () => {
    // Arrange
    let resolveFn
    const exportData = vi.fn().mockReturnValue(
      new Promise(resolve => { resolveFn = resolve })
    )
    
    const wrapper = mount(ExportDialog, {
      props: {
        visible: true,
        objectType: 'user'
      },
      global: {
        mocks: {
          useImportExportApi: () => ({ exportData })
        }
      }
    })
    
    // Act
    await wrapper.find('button:contains("开始导出")').trigger('click')
    
    // Assert
    expect(wrapper.findComponent({ name: 'ElProgress' }).exists()).toBe(true)
    
    resolveFn({ success: true, data: {} })
  })

  test('TC-ED-003-03: 导出成功应触发success事件', async () => {
    // Arrange
    const wrapper = mount(ExportDialog, {
      props: {
        visible: true,
        objectType: 'user'
      },
      global: {
        mocks: {
          useImportExportApi: () => ({
            exportData: vi.fn().mockResolvedValue({
              success: true,
              data: { download_url: '/api/v1/export/download/test.xlsx' }
            })
          })
        }
      }
    })
    
    // Act
    await wrapper.find('button:contains("开始导出")').trigger('click')
    await flushPromises()
    
    // Assert
    expect(wrapper.emitted('success')).toBeTruthy()
  })
})
```

---

## 五、TableHeaderFilter 组件测试

### 5.1 组件概述

**文件**: `src/components/common/TableHeaderFilter/TableHeaderFilter.vue`

**核心能力**:
- 过滤类型推断
- 过滤控件渲染
- 过滤值管理
- 事件传播控制

### 5.2 测试用例

#### TC-TH-001: 过滤控件渲染

```javascript
describe('TableHeaderFilter - 过滤控件渲染', () => {
  test('TC-TH-001-01: filterType为search时应渲染文本输入框', () => {
    // Arrange & Act
    const wrapper = mount(TableHeaderFilter, {
      props: {
        filterType: 'search',
        visible: true
      }
    })
    
    // Assert
    expect(wrapper.findComponent({ name: 'ElInput' }).exists()).toBe(true)
  })

  test('TC-TH-001-02: filterType为select时应渲染下拉框', () => {
    // Arrange & Act
    const wrapper = mount(TableHeaderFilter, {
      props: {
        filterType: 'select',
        options: [{ label: '活跃', value: 'active' }],
        visible: true
      }
    })
    
    // Assert
    expect(wrapper.findComponent({ name: 'ElSelect' }).exists()).toBe(true)
  })

  test('TC-TH-001-03: filterType为date-range时应渲染日期选择器', () => {
    // Arrange & Act
    const wrapper = mount(TableHeaderFilter, {
      props: {
        filterType: 'date-range',
        visible: true
      }
    })
    
    // Assert
    expect(wrapper.findComponent({ name: 'ElDatePicker' }).exists()).toBe(true)
  })
})
```

#### TC-TH-002: 过滤值管理

```javascript
describe('TableHeaderFilter - 过滤值管理', () => {
  test('TC-TH-002-01: 输入搜索值应触发update事件', async () => {
    // Arrange
    const wrapper = mount(TableHeaderFilter, {
      props: {
        filterType: 'search',
        visible: true
      }
    })
    
    // Act
    await wrapper.find('input').setValue('test')
    
    // Assert
    expect(wrapper.emitted('update:modelValue')[0]).toEqual(['test'])
  })

  test('TC-TH-002-02: 清空值应触发update事件', async () => {
    // Arrange
    const wrapper = mount(TableHeaderFilter, {
      props: {
        filterType: 'search',
        modelValue: 'test',
        visible: true
      }
    })
    
    // Act
    await wrapper.find('input').clear()
    
    // Assert
    expect(wrapper.emitted('update:modelValue')[0]).toEqual([''])
  })
})
```

---

## 六、集成测试用例

### 6.1 UserManagement 集成测试

#### TC-UM-001: 完整用户搜索流程

```javascript
describe('UserManagement - 完整用户搜索流程', () => {
  test('TC-UM-001-01: 搜索 → 分页 → 排序完整流程', async () => {
    // Arrange
    const wrapper = mount(UserManagement)
    const boService = wrapper.vm.boService
    
    // 1. 搜索用户
    await wrapper.find('input[placeholder="搜索关键词"]').setValue('test')
    await wrapper.find('button:contains("搜索")').trigger('click')
    
    expect(boService.query).toHaveBeenCalledWith(
      'user',
      expect.objectContaining({ search: 'test' })
    )
    
    // 2. 翻页
    await wrapper.find('.el-pagination button:contains("2")').trigger('click')
    
    expect(boService.query).toHaveBeenCalledWith(
      'user',
      expect.objectContaining({ page: 2 })
    )
    
    // 3. 排序
    await wrapper.find('.el-table__header-wrapper th:contains("用户名")').trigger('click')
    
    expect(boService.query).toHaveBeenCalledWith(
      'user',
      expect.objectContaining({ ordering: 'username' })
    )
  })
})
```

#### TC-UM-002: 批量选择与删除

```javascript
describe('UserManagement - 批量选择与删除', () => {
  test('TC-UM-002-01: 批量选择应更新选中计数', async () => {
    // Arrange
    const wrapper = mount(UserManagement)
    await flushPromises()
    
    // Act - 选择前3条
    await wrapper.findAll('.el-table__body tr').slice(0, 3)
      .forEach(row => row.trigger('click'))
    
    // Assert
    expect(wrapper.find('.selected-count').text()).toContain('已选择 3 项')
  })

  test('TC-UM-002-02: 批量删除应显示确认对话框', async () => {
    // Arrange
    const wrapper = mount(UserManagement)
    await flushPromises()
    
    // 选择用户
    await wrapper.find('.el-table__body tr:first-child').trigger('click')
    
    // Act
    await wrapper.find('button:contains("批量删除")').trigger('click')
    
    // Assert
    expect(wrapper.findComponent({ name: 'ElMessageBox' }).exists()).toBe(true)
  })
})
```

---

## 七、API Mock 配置

### 7.1 MSW 配置

```javascript
// tests/mocks/handlers.js
import { rest } from 'msw'

export const handlers = [
  // 列表查询
  rest.get('/api/v2/bo/:entity', (req, res, ctx) => {
    const { entity } = req.params
    const page = parseInt(req.url.searchParams.get('page')) || 1
    const pageSize = parseInt(req.url.searchParams.get('page_size')) || 20
    
    return res(
      ctx.json({
        success: true,
        data: {
          items: generateMockData(entity, pageSize),
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
          preview: [{ name: 'test', email: 'test@example.com' }],
          errors: []
        }
      })
    )
  })
]
```

---

## 八、测试覆盖率目标

### 8.1 覆盖率指标

| 模块 | 目标覆盖率 |
|------|----------|
| useMetaList | 90%+ |
| useImportExportApi | 85%+ |
| ExportDialog | 80%+ |
| ImportDialog | 80%+ |
| TableHeaderFilter | 75%+ |

### 8.2 测试类型分布

| 类型 | 数量 | 占比 |
|------|------|------|
| 单元测试 | 150+ | 60% |
| 组件测试 | 60+ | 25% |
| 集成测试 | 30+ | 15% |
