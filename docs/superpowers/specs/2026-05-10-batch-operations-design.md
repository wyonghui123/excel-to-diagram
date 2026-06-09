## 目录

1. [一、概述](#一-概述)
2. [二、需求分析](#二-需求分析)
3. [三、架构设计](#三-架构设计)
4. [四、详细设计](#四-详细设计)
5. [五、数据流设计](#五-数据流设计)
6. [六、错误处理设计](#六-错误处理设计)
7. [七、测试策略](#七-测试策略)
8. [八、性能优化](#八-性能优化)
9. [九、实施计划](#九-实施计划)
10. [十、风险与缓解](#十-风险与缓解)
11. [十一、验收标准](#十一-验收标准)
12. [十二、参考资料](#十二-参考资料)
13. [十三、变更历史](#十三-变更历史)

---
# 元数据驱动的批量操作功能设计文档

**版本**: v1.0  
**日期**: 2026-05-10  
**状态**: 设计中  
**作者**: AI Assistant

---

## 一、概述

### 1.1 背景

当前用户管理页面缺少批量操作功能（导出、导入、批量删除），影响了用户体验和工作效率。根据对SAP Fiori Elements、Mia-Platform、Salesforce等头部产品的研究，批量操作应该是元数据模型的默认能力。

### 1.2 目标

- 为用户管理页面添加批量导出、导入、删除功能
- 作为元数据模型的默认能力，便于后续推广到其他页面
- 复用架构数据管理的成熟实现，减少重复开发

### 1.3 范围

**阶段1（当前）**：用户管理页面实现  
**阶段2（后续）**：推广到角色、用户组等其他元数据页面

---

## 二、需求分析

### 2.1 功能需求

#### 2.1.1 批量删除

- **前置条件**：用户选择一条或多条记录
- **交互流程**：
  1. 点击"删除选中"按钮
  2. 显示确认对话框："确定删除选中的 X 条记录吗？"
  3. 确认后执行删除
  4. 显示删除结果
- **安全措施**：
  - 简单确认对话框
  - BOFramework自动处理验证和审计日志
  - 参考架构数据管理的批量删除实现

#### 2.1.2 导出功能

- **前置条件**：无（可导出全部或筛选后的数据）
- **交互流程**：
  1. 点击"导出"按钮
  2. 显示导出对话框（可选导出字段、导出选项）
  3. 执行导出
  4. 自动下载Excel文件
- **导出格式**：Excel (.xlsx)
- **导出选项**：
  - 包含/排除特定字段
  - 排除敏感字段（如password、salt）
  - 支持筛选条件导出

#### 2.1.3 导入功能

- **前置条件**：准备Excel文件
- **交互流程**：
  1. 点击"导入"按钮
  2. 显示导入对话框
  3. 上传Excel文件（支持拖拽）
  4. 预览数据（显示Sheet信息、验证错误）
  5. 选择冲突处理策略
  6. 执行导入（显示进度）
  7. 显示导入结果（成功/失败统计）
- **导入格式**：Excel (.xlsx)
- **导入选项**：
  - 数据预览
  - 冲突处理（更新/跳过）
  - 错误报告下载
  - 模板下载

### 2.2 非功能需求

- **性能**：批量删除支持1000+条记录
- **可用性**：导入导出失败时提供明确的错误信息
- **一致性**：与架构数据管理的交互模式保持一致
- **可扩展性**：作为元数据模型的默认能力

---

## 三、架构设计

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                      前端层                              │
├─────────────────────────────────────────────────────────┤
│  userMeta.js          │  useMetaList.js                 │
│  - batch_actions配置  │  - handleBatchDelete()          │
│  - exportOptions      │  - handleExport()               │
│  - importOptions      │  - handleImport()               │
├─────────────────────────────────────────────────────────┤
│  公共组件                                               │
│  - ImportDialog.vue (提取)                             │
│  - ExportDialog.vue (新建)                             │
│  - BatchActions.vue (新建)                             │
└─────────────────────────────────────────────────────────┘
                          ↓ API调用
┌─────────────────────────────────────────────────────────┐
│                      API层                              │
├─────────────────────────────────────────────────────────┤
│  /api/v1/users/batch-delete  (新增)                    │
│  /api/v1/export              (复用)                    │
│  /api/v1/import              (复用)                    │
└─────────────────────────────────────────────────────────┘
                          ↓ 服务调用
┌─────────────────────────────────────────────────────────┐
│                     服务层                              │
├─────────────────────────────────────────────────────────┤
│  ImportExportService (复用)                            │
│  - export_to_excel()                                   │
│  - import_from_excel()                                 │
├─────────────────────────────────────────────────────────┤
│  ManageService (复用)                                  │
│  - batch_delete()                                      │
├─────────────────────────────────────────────────────────┤
│  BOFramework (复用)                                    │
│  - 自动验证                                            │
│  - 自动审计日志                                        │
└─────────────────────────────────────────────────────────┘
```

### 3.2 核心原则

1. **元数据驱动**：所有批量操作基于元数据模型定义
2. **复用优先**：复用架构数据管理的成熟组件和服务
3. **统一交互**：与架构数据管理保持一致的UI/UX
4. **默认能力**：作为元数据模型的标准能力

---

## 四、详细设计

### 4.1 前端设计

#### 4.1.1 元数据配置 (userMeta.js)

```javascript
export const userMeta = {
  entity: 'user',
  label: '用户',
  apiBase: '/api/v1/users',
  
  list: {
    // ... 现有配置 ...
    
    // 批量操作配置
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
    ],
    
    // 导出选项配置
    exportOptions: {
      includeFields: ['username', 'display_name', 'email', 'status', 'created_at'],
      excludeFields: ['password', 'salt'],
      sheetName: '用户列表'
    },
    
    // 导入选项配置
    importOptions: {
      templateName: '用户导入模板.xlsx',
      requiredFields: ['username', 'display_name', 'email'],
      uniqueFields: ['username', 'email']
    }
  }
}
```

#### 4.1.2 useMetaList.js 增强

```javascript
// 新增状态
const batchActions = ref([])
const selectedRows = ref([])
const showExportDialog = ref(false)
const showImportDialog = ref(false)

// 批量删除处理
async function handleBatchDelete() {
  if (!selectedRows.value.length) return
  
  const action = batchActions.value.find(a => a.key === 'delete')
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

// 导出处理
async function handleExport(options = {}) {
  showExportDialog.value = true
}

// 导入处理
async function handleImport() {
  showImportDialog.value = true
}

// 行选择处理
function handleSelectionChange(selection) {
  selectedRows.value = selection
}
```

#### 4.1.3 ImportDialog 组件复用

**提取为公共组件**：`src/components/common/ImportDialog.vue`

**关键修改点**：
1. 参数化 `objectType`（已支持）
2. 通用化 `context` 参数
3. 添加单对象类型模板下载支持

**使用方式**：
```vue
<ImportDialog
  v-model:visible="showImportDialog"
  object-type="user"
  :context="{}"
  @success="handleImportSuccess"
  @close="showImportDialog = false"
/>
```

#### 4.1.4 ExportDialog 组件设计

**新建公共组件**：`src/components/common/ExportDialog.vue`

**功能**：
- 选择导出字段
- 配置导出选项
- 执行导出
- 下载文件

**使用方式**：
```vue
<ExportDialog
  v-model:visible="showExportDialog"
  object-type="user"
  :fields="exportableFields"
  @export="handleExportExecute"
  @close="showExportDialog = false"
/>
```

### 4.2 后端设计

#### 4.2.1 批量删除API

**端点**：`POST /api/v1/users/batch-delete`

**请求体**：
```json
{
  "ids": [1, 2, 3]
}
```

**响应**：
```json
{
  "success": true,
  "data": {
    "count": 3
  },
  "message": "成功删除 3 条记录"
}
```

**实现**：
```python
@user_bp.route('/batch-delete', methods=['POST'])
@login_required
def batch_delete_users():
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

#### 4.2.2 导出API（复用现有）

**端点**：`POST /api/v1/export`

**请求体**：
```json
{
  "object_type": "user",
  "filters": {},
  "fields": ["username", "display_name", "email"],
  "options": {}
}
```

**响应**：
```json
{
  "success": true,
  "data": {
    "file_path": "/exports/user_20260510_212100.xlsx",
    "file_url": "/api/v1/download/exports/user_20260510_212100.xlsx"
  }
}
```

**实现**：复用 `ImportExportService.export_to_excel()`

#### 4.2.3 导入API（复用现有）

**端点**：`POST /api/v1/import`

**FormData**：
- `file`: Excel文件
- `object_type`: "user"
- `mode`: "preview" | "import"
- `conflict_strategy`: "upsert" | "skip"
- `context`: {}

**响应**：
```json
{
  "success": true,
  "data": {
    "task_id": "abc123",
    "status": "processing"
  }
}
```

**实现**：复用 `ImportExportService.import_from_excel()`

---

## 五、数据流设计

### 5.1 批量删除流程

```
用户选择多行
    ↓
点击"删除选中"按钮
    ↓
显示确认对话框
    ↓
用户确认
    ↓
调用 API: POST /api/v1/users/batch-delete
    ↓
BOFramework 执行批量删除
    ├─ 验证权限
    ├─ 检查约束
    ├─ 执行删除
    └─ 记录审计日志
    ↓
返回结果
    ↓
刷新列表
    ↓
显示成功消息
```

### 5.2 导出流程

```
用户点击"导出"按钮
    ↓
显示导出对话框
    ↓
配置导出选项
    ↓
调用 API: POST /api/v1/export
    ↓
ImportExportService.export_to_excel()
    ├─ 查询数据
    ├─ 生成Excel文件
    └─ 保存到 exports/ 目录
    ↓
返回文件路径
    ↓
浏览器下载文件
```

### 5.3 导入流程

```
用户点击"导入"按钮
    ↓
显示导入对话框
    ↓
上传Excel文件
    ↓
Step 1: 预览
    ├─ 解析Excel
    ├─ 验证数据
    └─ 显示预览结果
    ↓
Step 2: 确认导入
    ├─ 选择冲突处理策略
    └─ 点击"开始导入"
    ↓
Step 3: 执行导入
    ├─ 后台异步任务
    ├─ 实时进度更新
    └─ 显示导入结果
    ↓
刷新列表
    ↓
显示成功消息
```

---

## 六、错误处理设计

### 6.1 批量删除错误处理

**前端**：
```javascript
try {
  const result = await boService.batchDelete('user', ids)
  
  if (result.success) {
    message.success(`成功删除 ${result.data.count} 条记录`)
  } else {
    message.error(result.message || '删除失败')
  }
} catch (error) {
  message.error('网络错误，请重试')
}
```

**后端**：
```python
def batch_delete(object_type: str, ids: List[int]) -> ActionResult:
    errors = []
    deleted_count = 0
    
    for obj_id in ids:
        try:
            # 检查约束
            if object_type == 'user':
                user = self.read(object_type, obj_id)
                if user.data.get('is_admin'):
                    errors.append(f'不能删除管理员用户')
                    continue
            
            # 执行删除
            result = self.delete(object_type, obj_id)
            if result.success:
                deleted_count += 1
            else:
                errors.append(f'删除ID {obj_id} 失败: {result.message}')
        except Exception as e:
            errors.append(f'删除ID {obj_id} 异常: {str(e)}')
    
    return ActionResult(
        success=deleted_count > 0,
        data={'deleted_count': deleted_count},
        errors=errors,
        message=f'成功删除 {deleted_count} 条，失败 {len(errors)} 条'
    )
```

### 6.2 导入错误处理

**已在 ImportDialog 中实现**：
- 文件格式验证
- 数据预览验证
- 导入错误详情展示
- 按行号定位错误
- 错误报告下载

---

## 七、测试策略

### 7.1 单元测试

**前端测试**：
```javascript
// src/composables/__tests__/useMetaList.batch.spec.js
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

### 7.2 集成测试

**后端测试**：
```python
# meta/tests/test_user_batch_operations.py
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

### 7.3 E2E测试

**场景1：批量删除**
1. 登录系统
2. 进入用户管理页面
3. 选择多条记录
4. 点击"删除选中"按钮
5. 确认删除
6. 验证删除成功

**场景2：导出导入**
1. 导出用户列表
2. 修改Excel文件
3. 导入修改后的文件
4. 验证数据更新成功

---

## 八、性能优化

### 8.1 批量删除优化

```python
# 使用事务批量删除
def batch_delete_optimized(object_type: str, ids: List[int]) -> ActionResult:
    with self.data_source.transaction():
        # 批量查询约束
        constraints = self._check_batch_constraints(object_type, ids)
        if constraints['errors']:
            return ActionResult(success=False, errors=constraints['errors'])
        
        # 批量删除
        deleted_count = self.data_source.batch_delete(
            table_name=self._get_table_name(object_type),
            ids=ids
        )
        
        # 批量记录审计日志
        self._batch_audit_log(object_type, ids, 'DELETE')
    
    return ActionResult(success=True, data={'deleted_count': deleted_count})
```

### 8.2 导出优化

```python
# 分批查询大量数据
def export_large_dataset(object_type: str, filters: Dict) -> str:
    batch_size = 1000
    offset = 0
    
    wb = Workbook()
    ws = wb.active
    
    while True:
        data = self.query_service.search(SearchRequest(
            object_type=object_type,
            conditions=filters,
            page=offset // batch_size + 1,
            page_size=batch_size
        ))
        
        if not data.data:
            break
        
        for record in data.data:
            ws.append(self._record_to_row(record))
        
        offset += batch_size
    
    return self._save_workbook(wb, object_type)
```

---

## 九、实施计划

### 9.1 阶段1：用户管理页面实现（预计2天）

**任务清单**：
1. 提取 ImportDialog 为公共组件（4小时）
2. 创建 ExportDialog 公共组件（4小时）
3. 在 userMeta.js 中配置 batch_actions（1小时）
4. 在 useMetaList.js 中实现批量操作逻辑（4小时）
5. 添加批量删除API端点（2小时）
6. 编写单元测试（3小时）
7. 编写集成测试（2小时）
8. E2E测试验证（2小时）

### 9.2 阶段2：推广到其他页面（预计1天）

**任务清单**：
1. 在 roleMeta.js 中添加 batch_actions（1小时）
2. 在 userGroupMeta.js 中添加 batch_actions（1小时）
3. 测试所有页面的批量操作功能（4小时）
4. 优化和修复问题（2小时）

---

## 十、风险与缓解

### 10.1 技术风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| ImportDialog组件耦合度高 | 中 | 参数化设计，支持通用context |
| 批量删除性能问题 | 高 | 使用事务和批量操作优化 |
| 导入数据量大导致超时 | 中 | 异步任务处理，进度轮询 |

### 10.2 业务风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 误删除重要数据 | 高 | 确认对话框 + 审计日志 |
| 导入数据错误 | 中 | 预览验证 + 错误报告 |
| 权限控制缺失 | 高 | 复用BOFramework权限验证 |

---

## 十一、验收标准

### 11.1 功能验收

- [ ] 用户管理页面显示批量操作按钮
- [ ] 批量删除功能正常工作
- [ ] 导出功能生成正确的Excel文件
- [ ] 导入功能支持预览和错误处理
- [ ] 所有操作都有审计日志记录

### 11.2 性能验收

- [ ] 批量删除1000条记录 < 5秒
- [ ] 导出10000条记录 < 10秒
- [ ] 导入1000条记录 < 15秒

### 11.3 测试验收

- [ ] 单元测试覆盖率 > 80%
- [ ] 集成测试全部通过
- [ ] E2E测试全部通过

---

## 十二、参考资料

### 12.1 业界最佳实践

- [SAP Fiori Elements - Using the Export Button](https://github.com/SAP-docs/sapui5/blob/main/docs/06_SAP_Fiori_Elements/using-the-export-button-4bab6f2.md)
- [SAP Fiori Elements - Adding Actions to Tables](https://github.com/SAP-docs/sapui5/blob/main/docs/06_SAP_Fiori_Elements/adding-actions-to-tables-b623e0b.md)
- [Mia-Platform CRUD Service](https://github.com/mia-platform/crud-service/blob/main/docs/10_Overview_and_Usage.md)
- [Salesforce Metadata API](https://resources.docs.salesforce.com/latest/latest/en-us/sfdc/pdf/api_meta.pdf)

### 12.2 内部参考

- 架构数据管理导入导出实现：`src/views/ArchDataManageApp/components/ImportDialog.vue`
- ImportExportService：`meta/services/import_export_service.py`
- BOFramework：`meta/core/bo_framework.py`

---

## 十三、变更历史

| 日期 | 版本 | 变更内容 | 作者 |
|------|------|----------|------|
| 2026-05-10 | v1.0 | 初始设计文档 | AI Assistant |
