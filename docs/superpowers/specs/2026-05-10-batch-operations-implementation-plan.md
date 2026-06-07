# 元数据驱动的批量操作功能 - 实施计划

**基于设计文档**: `2026-05-10-batch-operations-design.md`  
**创建日期**: 2026-05-10  
**预计工期**: 2天（阶段1）+ 1天（阶段2）

---

## 📋 实施概览

本实施计划基于已批准的设计文档，分两个阶段完成元数据驱动的批量操作功能。

### 阶段划分

- **阶段1**：用户管理页面实现（优先级：高）
- **阶段2**：推广到其他元数据页面（优先级：中）

---

## 🎯 阶段1：用户管理页面实现

### 任务1：提取 ImportDialog 为公共组件

**预计时间**: 4小时  
**优先级**: 高  
**依赖**: 无

#### 子任务

- [ ] **1.1 创建公共组件目录结构**
  ```bash
  src/components/common/ImportDialog/
  ├── ImportDialog.vue
  ├── index.js
  └── README.md
  ```

- [ ] **1.2 复制并重构 ImportDialog 组件**
  - 从 `src/views/ArchDataManageApp/components/ImportDialog.vue` 复制
  - 修改 props 参数：
    - `objectType`: String（已支持）
    - `context`: Object（通用化）
  - 移除硬编码的对象类型列表
  - 添加单对象类型模板下载支持

- [ ] **1.3 修改模板下载逻辑**
  ```javascript
  // 修改前
  async function downloadTemplate() {
    await downloadFullTemplate()  // 下载所有架构数据模板
  }
  
  // 修改后
  async function downloadTemplate() {
    await downloadTemplate(objectType)  // 下载指定对象类型模板
  }
  ```

- [ ] **1.4 更新 API 调用**
  - 确保 `importData` 和 `importDataAsync` 支持 `objectType` 参数
  - 验证 `context` 参数传递正确

- [ ] **1.5 编写组件文档**
  - 使用示例
  - Props 说明
  - Events 说明

#### 验收标准

- [ ] ImportDialog 组件可在任意页面使用
- [ ] 支持 `objectType` 参数
- [ ] 模板下载功能正常
- [ ] 导入功能正常

---

### 任务2：创建 ExportDialog 公共组件

**预计时间**: 4小时  
**优先级**: 高  
**依赖**: 任务1

#### 子任务

- [ ] **2.1 创建 ExportDialog 组件结构**
  ```bash
  src/components/common/ExportDialog/
  ├── ExportDialog.vue
  ├── index.js
  └── README.md
  ```

- [ ] **2.2 实现导出对话框UI**
  - 字段选择器（多选）
  - 导出选项配置
  - 执行导出按钮
  - 下载文件功能

- [ ] **2.3 实现导出逻辑**
  ```javascript
  async function handleExport() {
    const result = await api.exportData({
      object_type: props.objectType,
      fields: selectedFields.value,
      options: exportOptions.value
    })
    
    if (result.success) {
      window.location.href = result.data.file_url
    }
  }
  ```

- [ ] **2.4 添加导出选项**
  - 包含/排除字段
  - 导出筛选后的数据
  - 导出格式选择（预留）

- [ ] **2.5 编写组件文档**

#### 验收标准

- [ ] ExportDialog 组件可正常使用
- [ ] 支持字段选择
- [ ] 导出功能正常
- [ ] 文件下载正常

---

### 任务3：在 userMeta.js 中配置 batch_actions

**预计时间**: 1小时  
**优先级**: 高  
**依赖**: 无

#### 子任务

- [ ] **3.1 添加 batch_actions 配置**
  ```javascript
  // src/views/SystemManagement/meta/userMeta.js
  export const userMeta = {
    // ... 现有配置 ...
    
    list: {
      // ... 现有配置 ...
      
      batch_actions: [
        {
          key: 'export',
          label: '导出',
          icon: 'download',
          variant: 'secondary',
          position: 'toolbar',
          action: 'batch_export'
        },
        {
          key: 'import',
          label: '导入',
          icon: 'upload',
          variant: 'secondary',
          position: 'toolbar',
          action: 'batch_import'
        },
        {
          key: 'delete',
          label: '删除选中',
          icon: 'delete',
          variant: 'danger',
          position: 'toolbar',
          action: 'batch_delete',
          confirmMessage: '确定要删除选中的 {count} 条记录吗？',
          confirmTitle: '确认批量删除'
        }
      ]
    }
  }
  ```

- [ ] **3.2 添加导出选项配置**
  ```javascript
  exportOptions: {
    includeFields: ['username', 'display_name', 'email', 'status', 'created_at'],
    excludeFields: ['password', 'salt'],
    sheetName: '用户列表'
  }
  ```

- [ ] **3.3 添加导入选项配置**
  ```javascript
  importOptions: {
    templateName: '用户导入模板.xlsx',
    requiredFields: ['username', 'display_name', 'email'],
    uniqueFields: ['username', 'email']
  }
  ```

#### 验收标准

- [ ] batch_actions 配置正确
- [ ] 导出选项配置正确
- [ ] 导入选项配置正确

---

### 任务4：在 useMetaList.js 中实现批量操作逻辑

**预计时间**: 4小时  
**优先级**: 高  
**依赖**: 任务1, 任务2, 任务3

#### 子任务

- [ ] **4.1 添加批量操作相关状态**
  ```javascript
  // src/composables/useMetaList.js
  
  const batchActions = ref([])
  const selectedRows = ref([])
  const showExportDialog = ref(false)
  const showImportDialog = ref(false)
  const exportLoading = ref(false)
  const importLoading = ref(false)
  ```

- [ ] **4.2 实现 handleBatchDelete 函数**
  ```javascript
  async function handleBatchDelete() {
    if (!selectedRows.value.length) return
    
    const action = batchActions.value.find(a => a.key === 'delete')
    if (!action) return
    
    const message = action.confirmMessage.replace('{count}', selectedRows.value.length)
    
    await ElMessageBox.confirm(message, action.confirmTitle || '确认操作', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    
    try {
      const ids = selectedRows.value.map(row => row.id)
      const result = await boService.batchDelete(objectType, ids)
      
      if (result.success) {
        ElMessage.success(`成功删除 ${result.data.count} 条记录`)
        selectedRows.value = []
        await loadList()
      } else {
        ElMessage.error(result.message || '删除失败')
      }
    } catch (error) {
      ElMessage.error(error.message || '删除失败')
    }
  }
  ```

- [ ] **4.3 实现 handleExport 函数**
  ```javascript
  async function handleExport(options = {}) {
    showExportDialog.value = true
  }
  ```

- [ ] **4.4 实现 handleImport 函数**
  ```javascript
  async function handleImport() {
    showImportDialog.value = true
  }
  ```

- [ ] **4.5 实现 handleSelectionChange 函数**
  ```javascript
  function handleSelectionChange(selection) {
    selectedRows.value = selection
  }
  ```

- [ ] **4.6 添加计算属性**
  ```javascript
  const canBatchDelete = computed(() => selectedRows.value.length > 0)
  ```

- [ ] **4.7 更新元数据加载逻辑**
  ```javascript
  async function loadMeta() {
    // ... 现有逻辑 ...
    
    // 加载批量操作配置
    if (listConfig.batch_actions || listConfig.batchActions) {
      batchActions.value = _transformActions(listConfig.batch_actions || listConfig.batchActions)
    }
  }
  ```

#### 验收标准

- [ ] 批量删除功能正常
- [ ] 导出功能正常
- [ ] 导入功能正常
- [ ] 行选择功能正常

---

### 任务5：添加批量删除API端点

**预计时间**: 2小时  
**优先级**: 高  
**依赖**: 无

#### 子任务

- [ ] **5.1 在 user_api.py 中添加批量删除端点**
  ```python
  # meta/api/user_api.py
  
  @user_bp.route('/batch-delete', methods=['POST'])
  @login_required
  def batch_delete_users():
      """批量删除用户"""
      data = request.get_json()
      ids = data.get('ids', [])
      
      if not ids:
          return jsonify({
              'success': False,
              'message': '请选择要删除的记录'
          }), 400
      
      try:
          result = bo_framework.batch_delete('user', ids)
          
          return jsonify({
              'success': True,
              'data': {'count': result.get('deleted_count', 0)},
              'message': f'成功删除 {result.get("deleted_count", 0)} 条记录'
          })
      except Exception as e:
          return jsonify({
              'success': False,
              'message': str(e)
          }), 500
  ```

- [ ] **5.2 在 boService.js 中添加批量删除方法**
  ```javascript
  // src/services/boService.js
  
  async batchDelete(objectType, ids) {
    const response = await fetch(`/api/v1/${objectType}s/batch-delete`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${getToken()}`
      },
      body: JSON.stringify({ ids })
    })
    
    return response.json()
  }
  ```

- [ ] **5.3 测试API端点**
  - 使用 Postman 或 curl 测试
  - 验证权限控制
  - 验证审计日志记录

#### 验收标准

- [ ] API端点可正常访问
- [ ] 批量删除功能正常
- [ ] 权限验证正常
- [ ] 审计日志记录正常

---

### 任务6：编写单元测试

**预计时间**: 3小时  
**优先级**: 中  
**依赖**: 任务4

#### 子任务

- [ ] **6.1 创建测试文件**
  ```bash
  src/composables/__tests__/useMetaList.batch.spec.js
  ```

- [ ] **6.2 编写批量删除测试**
  ```javascript
  describe('useMetaList - 批量操作', () => {
    it('应该正确处理批量删除', async () => {
      const { handleBatchDelete, selectedRows } = useMetaList('user')
      
      selectedRows.value = [
        { id: 1, username: 'user1' },
        { id: 2, username: 'user2' }
      ]
      
      await handleBatchDelete()
      
      expect(mockBoService.batchDelete).toHaveBeenCalledWith('user', [1, 2])
    })
    
    it('应该在未选择记录时禁用删除按钮', () => {
      const { selectedRows, canBatchDelete } = useMetaList('user')
      
      selectedRows.value = []
      expect(canBatchDelete.value).toBe(false)
      
      selectedRows.value = [{ id: 1 }]
      expect(canBatchDelete.value).toBe(true)
    })
  })
  ```

- [ ] **6.3 编写导出测试**
  ```javascript
  it('应该正确处理导出', async () => {
    const { handleExport, showExportDialog } = useMetaList('user')
    
    await handleExport()
    
    expect(showExportDialog.value).toBe(true)
  })
  ```

- [ ] **6.4 编写导入测试**
  ```javascript
  it('应该正确处理导入', async () => {
    const { handleImport, showImportDialog } = useMetaList('user')
    
    await handleImport()
    
    expect(showImportDialog.value).toBe(true)
  })
  ```

- [ ] **6.5 运行测试**
  ```bash
  npm run test:unit
  ```

#### 验收标准

- [ ] 单元测试覆盖率 > 80%
- [ ] 所有测试通过

---

### 任务7：编写集成测试

**预计时间**: 2小时  
**优先级**: 中  
**依赖**: 任务5

#### 子任务

- [ ] **7.1 创建测试文件**
  ```bash
  meta/tests/test_user_batch_operations.py
  ```

- [ ] **7.2 编写批量删除测试**
  ```python
  def test_batch_delete_users(client, auth_headers):
      """测试批量删除用户"""
      # 创建测试用户
      users = [
          {'username': 'test1', 'display_name': 'Test 1', 'email': 'test1@example.com'},
          {'username': 'test2', 'display_name': 'Test 2', 'email': 'test2@example.com'}
      ]
      created_ids = []
      for user in users:
          resp = client.post('/api/v1/users', json=user, headers=auth_headers)
          created_ids.append(resp.json['data']['id'])
      
      # 批量删除
      resp = client.post('/api/v1/users/batch-delete', 
                         json={'ids': created_ids},
                         headers=auth_headers)
      
      assert resp.status_code == 200
      assert resp.json['success'] is True
      assert resp.json['data']['count'] == 2
  ```

- [ ] **7.3 编写导出测试**
  ```python
  def test_export_users(client, auth_headers):
      """测试导出用户"""
      resp = client.post('/api/v1/export',
                         json={'object_type': 'user'},
                         headers=auth_headers)
      
      assert resp.status_code == 200
      assert resp.json['success'] is True
      assert 'file_url' in resp.json['data']
  ```

- [ ] **7.4 编写导入测试**
  ```python
  def test_import_users(client, auth_headers, tmp_path):
      """测试导入用户"""
      # 准备测试文件
      # ...
      
      # 导入
      # ...
      
      assert resp.status_code == 200
  ```

- [ ] **7.5 运行测试**
  ```bash
  pytest meta/tests/test_user_batch_operations.py
  ```

#### 验收标准

- [ ] 所有集成测试通过
- [ ] 测试覆盖主要场景

---

### 任务8：E2E测试验证

**预计时间**: 2小时  
**优先级**: 高  
**依赖**: 任务1-7

#### 子任务

- [ ] **8.1 准备测试环境**
  - 启动前后端服务
  - 准备测试数据

- [ ] **8.2 测试批量删除场景**
  1. 登录系统
  2. 进入用户管理页面
  3. 选择多条记录
  4. 点击"删除选中"按钮
  5. 确认删除
  6. 验证删除成功

- [ ] **8.3 测试导出场景**
  1. 进入用户管理页面
  2. 点击"导出"按钮
  3. 配置导出选项
  4. 执行导出
  5. 验证文件下载

- [ ] **8.4 测试导入场景**
  1. 进入用户管理页面
  2. 点击"导入"按钮
  3. 上传Excel文件
  4. 预览数据
  5. 执行导入
  6. 验证导入成功

- [ ] **8.5 记录测试结果**

#### 验收标准

- [ ] 批量删除功能正常
- [ ] 导出功能正常
- [ ] 导入功能正常
- [ ] 无明显bug

---

## 🎯 阶段2：推广到其他元数据页面

### 任务9：在 roleMeta.js 中添加 batch_actions

**预计时间**: 1小时  
**优先级**: 中  
**依赖**: 阶段1完成

#### 子任务

- [ ] **9.1 添加 batch_actions 配置**
  ```javascript
  // src/views/SystemManagement/meta/roleMeta.js
  
  batch_actions: [
    {
      key: 'export',
      label: '导出',
      icon: 'download',
      variant: 'secondary',
      position: 'toolbar',
      action: 'batch_export'
    },
    {
      key: 'import',
      label: '导入',
      icon: 'upload',
      variant: 'secondary',
      position: 'toolbar',
      action: 'batch_import'
    },
    {
      key: 'delete',
      label: '删除选中',
      icon: 'delete',
      variant: 'danger',
      position: 'toolbar',
      action: 'batch_delete',
      confirmMessage: '确定要删除选中的 {count} 条记录吗？',
      confirmTitle: '确认批量删除'
    }
  ]
  ```

- [ ] **9.2 添加导出选项配置**
- [ ] **9.3 添加导入选项配置**

#### 验收标准

- [ ] 角色管理页面显示批量操作按钮
- [ ] 批量操作功能正常

---

### 任务10：在 userGroupMeta.js 中添加 batch_actions

**预计时间**: 1小时  
**优先级**: 中  
**依赖**: 阶段1完成

#### 子任务

- [ ] **10.1 添加 batch_actions 配置**
- [ ] **10.2 添加导出选项配置**
- [ ] **10.3 添加导入选项配置**

#### 验收标准

- [ ] 用户组管理页面显示批量操作按钮
- [ ] 批量操作功能正常

---

### 任务11：测试所有页面的批量操作功能

**预计时间**: 4小时  
**优先级**: 高  
**依赖**: 任务9, 任务10

#### 子任务

- [ ] **11.1 测试用户管理页面**
- [ ] **11.2 测试角色管理页面**
- [ ] **11.3 测试用户组管理页面**
- [ ] **11.4 记录测试结果**

#### 验收标准

- [ ] 所有页面批量操作功能正常
- [ ] 无明显bug

---

### 任务12：优化和修复问题

**预计时间**: 2小时  
**优先级**: 中  
**依赖**: 任务11

#### 子任务

- [ ] **12.1 分析测试结果**
- [ ] **12.2 修复发现的问题**
- [ ] **12.3 优化性能**
- [ ] **12.4 更新文档**

#### 验收标准

- [ ] 所有问题已修复
- [ ] 性能满足要求
- [ ] 文档已更新

---

## 📊 进度跟踪

### 阶段1进度

| 任务 | 预计时间 | 实际时间 | 状态 | 完成度 |
|------|---------|---------|------|--------|
| 任务1 | 4h | - | ⏳ 待开始 | 0% |
| 任务2 | 4h | - | ⏳ 待开始 | 0% |
| 任务3 | 1h | - | ⏳ 待开始 | 0% |
| 任务4 | 4h | - | ⏳ 待开始 | 0% |
| 任务5 | 2h | - | ⏳ 待开始 | 0% |
| 任务6 | 3h | - | ⏳ 待开始 | 0% |
| 任务7 | 2h | - | ⏳ 待开始 | 0% |
| 任务8 | 2h | - | ⏳ 待开始 | 0% |
| **总计** | **22h** | **-** | **⏳** | **0%** |

### 阶段2进度

| 任务 | 预计时间 | 实际时间 | 状态 | 完成度 |
|------|---------|---------|------|--------|
| 任务9 | 1h | - | ⏳ 待开始 | 0% |
| 任务10 | 1h | - | ⏳ 待开始 | 0% |
| 任务11 | 4h | - | ⏳ 待开始 | 0% |
| 任务12 | 2h | - | ⏳ 待开始 | 0% |
| **总计** | **8h** | **-** | **⏳** | **0%** |

---

## 🚀 开始实施

现在可以按照本实施计划开始开发。建议按顺序执行任务，每完成一个任务后更新进度跟踪表。

**下一步行动**：
1. 开始任务1：提取 ImportDialog 为公共组件
2. 创建组件目录结构
3. 复制并重构组件代码
