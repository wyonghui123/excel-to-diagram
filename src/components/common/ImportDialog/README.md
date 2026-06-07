# ImportDialog 组件

通用的数据导入对话框组件，支持Excel文件导入、预览、验证和异步导入。

## 功能特性

- ✅ 拖拽上传Excel文件
- ✅ 文件预览和验证
- ✅ 冲突处理策略选择
- ✅ 异步导入任务
- ✅ 实时进度显示
- ✅ 错误详情展示
- ✅ 模板下载

## 使用方法

### 基本用法

```vue
<template>
  <div>
    <button @click="showImport = true">导入数据</button>
    
    <ImportDialog
      v-model:visible="showImport"
      object-type="user"
      @success="handleImportSuccess"
      @close="showImport = false"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import ImportDialog from '@/components/common/ImportDialog'

const showImport = ref(false)

function handleImportSuccess() {
  console.log('导入成功')
  // 刷新列表等操作
}
</script>
```

### 带上下文参数

```vue
<ImportDialog
  v-model:visible="showImport"
  object-type="business_object"
  :context="{ version_id: 1, product_id: 2 }"
  @success="handleImportSuccess"
  @close="showImport = false"
/>
```

## Props

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| visible | Boolean | 否 | false | 控制对话框显示/隐藏 |
| objectType | String | 是 | - | 对象类型（如 'user', 'role' 等） |
| context | Object | 否 | {} | 上下文参数（如 version_id, product_id 等） |

## Events

| 事件名 | 参数 | 说明 |
|--------|------|------|
| close | - | 关闭对话框时触发 |
| success | - | 导入成功时触发 |

## 导入流程

1. **Step 1**: 上传Excel文件
   - 支持拖拽上传
   - 支持点击选择文件
   - 自动验证文件格式

2. **Step 2**: 预览数据
   - 显示Sheet信息
   - 显示验证错误
   - 选择冲突处理策略

3. **Step 3**: 执行导入
   - 显示导入进度
   - 显示导入结果
   - 显示错误详情

## API依赖

组件依赖以下API端点：

- `POST /api/v1/import` - 预览导入数据
- `POST /api/v1/import/async` - 异步导入数据
- `GET /api/v1/import/status/:taskId` - 查询导入状态
- `GET /api/v1/import/template/:objectType` - 下载导入模板
- `GET /api/v1/import-export/config/:objectType` - 获取导入导出配置

## 示例

### 用户管理页面导入

```vue
<template>
  <div class="user-management">
    <button @click="showImport = true">导入用户</button>
    
    <ImportDialog
      v-model:visible="showImport"
      object-type="user"
      @success="loadUsers"
      @close="showImport = false"
    />
  </div>
</template>
```

### 架构数据导入

```vue
<template>
  <div class="arch-data-management">
    <button @click="showImport = true">导入架构数据</button>
    
    <ImportDialog
      v-model:visible="showImport"
      object-type="business_object"
      :context="{ version_id: currentVersion.id, product_id: currentProduct.id }"
      @success="loadArchData"
      @close="showImport = false"
    />
  </div>
</template>
```

## 注意事项

1. 确保后端API已实现相关端点
2. 导入大文件时可能需要较长时间，请耐心等待
3. 导入失败时可以查看错误详情，定位问题
4. 建议先下载模板，按模板格式准备数据
