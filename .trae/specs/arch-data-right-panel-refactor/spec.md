# 架构数据管理右侧面板重构 Spec

## Why

当前架构数据管理的右侧面板使用简单的 Tab 切换（层级数据/业务关系），但缺少维度细分、操作栏与当前 Tab 联动、以及与左侧树选择的联动。用户需要更细粒度的数据查看和操作能力，参考 AA 图的维度导航模式。

## What Changes

- **维度 Tab 切换**：层级数据下增加子 Tab（领域/子领域/服务模块/业务对象）
- **操作栏联动**：操作栏内容根据当前 Tab 动态切换
- **左侧树联动**：点击左侧树节点自动切换到对应维度 Tab 并过滤数据
- **CRUD 功能保留**：新建、删除、搜索、导入导出等功能完整保留
- **Landing Page 重构**：作为后续待办，添加产品版本快捷入口

## Impact

- Affected specs: unified-sidebar-tree-interaction, architecture-data-management
- Affected code:
  - `src/views/ArchDataManageApp/index.vue` - 右侧面板重构
  - `src/views/ArchDataManageApp/components/DynamicView.vue` - 增强操作栏联动
  - `src/views/ArchDataManageApp/stores/archDataStore.js` - 增加维度 Tab 状态
  - `src/components/ArchWorkspace.vue` - Landing Page 重构（后续待办）

---

## ADDED Requirements

### Requirement: 维度 Tab 切换

系统 SHALL 在右侧面板提供维度 Tab 切换，层级数据下包含：领域、子领域、服务模块、业务对象四个子 Tab。

#### Scenario: 层级数据子 Tab
- **WHEN** 用户选择"层级数据"主 Tab
- **THEN** 显示子 Tab：[领域] [子领域] [服务模块] [业务对象]
- **AND** 默认选中"业务对象"子 Tab

#### Scenario: 业务关系 Tab
- **WHEN** 用户选择"业务关系"主 Tab
- **THEN** 显示关系列表，操作栏显示关系相关操作

### Requirement: 操作栏联动

系统 SHALL 根据当前 Tab 动态切换操作栏内容。

#### Scenario: 领域 Tab 操作栏
- **WHEN** 用户在"领域"子 Tab
- **THEN** 操作栏显示：[新建领域] [删除选中] [搜索...]

#### Scenario: 业务对象 Tab 操作栏
- **WHEN** 用户在"业务对象"子 Tab
- **THEN** 操作栏显示：[新建业务对象] [删除选中] [搜索...]

#### Scenario: 业务关系 Tab 操作栏
- **WHEN** 用户在"业务关系"主 Tab
- **THEN** 操作栏显示：[新建关系] [删除选中] [搜索...]

### Requirement: 左侧树与右侧 Tab 联动

系统 SHALL 支持左侧树节点点击自动切换右侧 Tab 并过滤数据。

#### Scenario: 点击领域节点
- **WHEN** 用户在左侧树点击"供应链云"领域节点
- **THEN** 自动切换到"领域"子 Tab
- **AND** 表格显示该领域及其下级数据

#### Scenario: 点击子领域节点
- **WHEN** 用户在左侧树点击"采购供应"子领域节点
- **THEN** 自动切换到"子领域"子 Tab
- **AND** 表格显示该子领域及其下级数据

#### Scenario: 点击服务模块节点
- **WHEN** 用户在左侧树点击"库存管理"服务模块节点
- **THEN** 自动切换到"服务模块"子 Tab
- **AND** 表格显示该服务模块及其下级数据

#### Scenario: 点击业务对象节点
- **WHEN** 用户在左侧树点击某个业务对象节点
- **THEN** 自动切换到"业务对象"子 Tab
- **AND** 表格高亮显示该业务对象

### Requirement: CRUD 功能完整保留

系统 SHALL 保留所有现有的 CRUD 功能，包括新建、删除、编辑、搜索、导入导出等。

#### Scenario: 新建操作
- **WHEN** 用户点击"新建"按钮
- **THEN** 弹出新建表单，表单字段根据当前 Tab 类型动态生成
- **AND** 支持层级归属联动选择

#### Scenario: 删除操作
- **WHEN** 用户选中一条或多条记录并点击"删除"
- **THEN** 弹出确认对话框
- **AND** 删除前检查引用完整性

#### Scenario: 搜索过滤
- **WHEN** 用户在搜索框输入关键字
- **THEN** 表格实时过滤显示匹配结果
- **AND** 支持按当前 Tab 类型搜索

#### Scenario: 导入导出
- **WHEN** 用户点击"导入"或"导出"
- **THEN** 执行对应操作
- **AND** 导入时校验数据格式

---

## MODIFIED Requirements

### Requirement: index.vue 右侧面板结构

原右侧面板只有主 Tab 切换，修改为支持子 Tab 和操作栏联动。

**当前代码结构（index.vue L43-L66）：**
```vue
<main class="adm-content">
  <div class="adm-tabs">
    <button :class="['adm-tab', { 'adm-tab-active': activeTab === 'hierarchy' }]">层级数据</button>
    <button :class="['adm-tab', { 'adm-tab-active': activeTab === 'relationship' }]">业务关系</button>
  </div>
  <DynamicView :object-type="currentObjectType" ... />
</main>
```

**修改为：**
```vue
<main class="adm-content">
  <!-- 主 Tab -->
  <div class="adm-tabs">
    <button :class="['adm-tab', { 'adm-tab-active': activeTab === 'hierarchy' }]">层级数据</button>
    <button :class="['adm-tab', { 'adm-tab-active': activeTab === 'relationship' }]">业务关系</button>
  </div>
  
  <!-- 子 Tab（仅层级数据显示） -->
  <div class="adm-sub-tabs" v-if="activeTab === 'hierarchy'">
    <button v-for="dim in dimensionTabs" :key="dim.key"
      :class="['adm-sub-tab', { 'adm-sub-tab-active': activeDimension === dim.key }]"
      @click="switchDimension(dim.key)">
      {{ dim.label }}
    </button>
  </div>
  
  <!-- 操作栏 -->
  <div class="adm-toolbar">
    <button class="adm-toolbar-btn primary" @click="handleCreate">
      新建{{ currentTypeLabel }}
    </button>
    <button class="adm-toolbar-btn danger" @click="handleBatchDelete" :disabled="selectedRows.length === 0">
      删除选中 ({{ selectedRows.length }})
    </button>
    <div class="adm-toolbar-search">
      <input v-model="searchKeyword" placeholder="搜索..." @keyup.enter="handleSearch" />
    </div>
  </div>
  
  <DynamicView 
    :object-type="currentObjectType"
    :filter-params="currentFilterParams"
    @selection-change="handleSelectionChange"
    ref="dynamicViewRef"
  />
</main>
```

### Requirement: archDataStore 状态扩展

**当前状态（archDataStore.js L5-L21）：**
```javascript
state: () => ({
  treeData: [],
  tableData: [],
  detailData: null,
  currentObjectType: 'business_object',
  selectedNode: null,
  loading: false,
  // ...
})
```

**新增状态：**
```javascript
// 维度 Tab 相关
activeDimension: 'business_object',  // 当前维度 Tab: domain/sub_domain/service_module/business_object
selectedRows: [],                    // 表格选中行 ID 列表
```

---

## 技术设计

### 维度 Tab 配置

```javascript
const dimensionTabs = [
  { key: 'domain', label: '领域', type: 'domain' },
  { key: 'sub_domain', label: '子领域', type: 'sub_domain' },
  { key: 'service_module', label: '服务模块', type: 'service_module' },
  { key: 'business_object', label: '业务对象', type: 'business_object' }
]
```

### 操作栏配置

```javascript
const toolbarConfig = {
  domain: { createLabel: '新建领域', type: 'domain' },
  sub_domain: { createLabel: '新建子领域', type: 'sub_domain' },
  service_module: { createLabel: '新建服务模块', type: 'service_module' },
  business_object: { createLabel: '新建业务对象', type: 'business_object' },
  relationship: { createLabel: '新建关系', type: 'relationship' }
}
```

### 左侧树节点类型与维度 Tab 映射

```javascript
const nodeTypeToDimension = {
  'domain': 'domain',
  'sub_domain': 'sub_domain',
  'service_module': 'service_module',
  'business_object': 'business_object'
}
```

### 布局设计

```
┌─────────────────────────────────────────────────────────────────────┐
│  ← 返回  架构数据管理  [🔍全局搜索...]  [导入] [导出] [刷新]         │
├──────────────────┬────────────────────────────────────────────────┤
│                  │  [层级数据]  [业务关系]                         │
│  产品: [ERP ▼]  ├────────────────────────────────────────────────┤
│  版本: [v2.0▼] │  [领域] [子领域] [服务模块] [业务对象]            │
│                  ├────────────────────────────────────────────────┤
│ ▼ 对象范围       │  [新建业务对象] [删除选中(0)]  [🔍搜索...]      │
│   ├─领域A ✓    ├────────────────────────────────────────────────┤
│   │ ├─子领域A1 │                                                │
│   │ │ └─服务A1 │  ┌──────────────────────────────────────────┐  │
│   │ │    └─BO1 │  │                                          │  │
│   │ └─子领域A2 │  │  数据表格（支持排序、筛选、分页）          │  │
│   │            │  │                                          │  │
│   ├─领域B      │  │                                          │  │
│   │            │  │                                          │  │
│ ▶ 关系范围     │  │                                          │  │
│                │  └──────────────────────────────────────────┘  │
│   ├─中心范围   │                                                │
│   ├─跨领域     │  上一页  1 2 3 ...  下一页    每页 [20▼] 条    │
│   └─同领域跨子域│                                                │
│                │                                                │
│  [展开][收起] │                                                │
│  [全选][清空] │                                                │
└────────────────┴────────────────────────────────────────────────┘
```

---

## 后续待办

### Landing Page 重构

- 添加产品版本快捷入口卡片
- 添加"添加入口"功能
- 添加独立的产品管理、版本管理入口
- 保留 AA 图生成入口
