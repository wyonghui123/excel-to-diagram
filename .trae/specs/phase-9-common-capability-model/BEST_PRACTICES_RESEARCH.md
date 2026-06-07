# Phase 9 行业最佳实践研究报告

> **研究日期**: 2026-05-11
> **参考产品**: SAP CAP, Salesforce Lightning, Microsoft Dynamics 365, SAP Fiori

---

## 一、研究背景

Phase 9 的目标是完备通用能力模型（Association操作、详情页面、导航等），并基于此适配用户组、角色等对象。为确保方案设计符合行业最佳实践，我们研究了以下头部产品：

| 产品 | 重点研究领域 |
|------|-------------|
| **SAP Cloud Application Programming Model (CAP)** | Association/Composition 模式、OData $expand、层级树视图 |
| **Salesforce Lightning Platform** | Dynamic Related Lists、GraphQL 关联查询、Related List Metadata |
| **Microsoft Dynamics 365 Dataverse** | Associate/Disassociate 操作、多对多关系处理 |
| **SAP Fiori** | Dynamic Page 布局、FlexibleColumnLayout、响应式设计 |

---

## 二、项目现有能力分析

### 2.1 后端现有能力

| 模块 | 文件 | 状态 | 复用价值 |
|------|------|------|---------|
| **AssociationEngine** | `meta/core/association_engine.py` | ✅ 完备 | ⭐⭐⭐ 核心引擎 |
| **ConstraintEngine** | `meta/core/constraint_engine.py` | ✅ 完备 | ⭐⭐⭐ 核心引擎 |
| **DeepInsertEngine** | `meta/core/deep_insert_engine.py` | ✅ 完备 | ⭐⭐⭐ 核心引擎 |
| **BOFramework** | `meta/core/bo_framework.py` | ✅ 完备 | ⭐⭐⭐ 核心框架 |
| **9个拦截器** | `meta/core/interceptors/` | ✅ 完备 | ⭐⭐⭐ 通用能力 |
| **bo_api.py** | `meta/api/bo_api.py` | ✅ v2 API | ⭐⭐⭐ 核心API |
| **export_import_api.py** | `meta/api/` | ✅ 完备 | ⭐⭐ 通用功能 |

### 2.2 前端现有能力

| 模块 | 文件 | 状态 | 复用价值 |
|------|------|------|---------|
| **useMetaList.js** | `src/composables/` | ✅ 完备 | ⭐⭐⭐ 核心Composable |
| **boService.js** | `src/services/` | ✅ 完备 | ⭐⭐⭐ 核心服务 |
| **metaService.js** | `src/services/` | ✅ 完备 | ⭐⭐⭐ 核心服务 |
| **Element Plus** | `main.js` | ✅ 已集成 | ⭐⭐⭐ 基础组件 |
| **FilterBar** | `src/components/common/` | ✅ 完备 | ⭐⭐ 业务组件 |
| **AssociationSelector** | `src/components/bo/` | ✅ 可扩展 | ⭐⭐ 业务组件 |
| **ExportDialog/ImportDialog** | `src/components/common/` | ✅ 完备 | ⭐⭐ 业务组件 |
| **AuditLog** | `src/components/common/` | ✅ 完备 | ⭐⭐ 业务组件 |

### 2.3 现有UserManagement.vue分析

```
┌─────────────────────────────────────────────────────────────┐
│              UserManagement.vue 现有能力分析                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ✅ 已实现:                                                 │
│  ─────────────────                                          │
│  • 元数据驱动的列表 (useMetaList)                          │
│  • 详情抽屉 (el-drawer)                                   │
│  • AssociationSelector 组件 (角色关联)                      │
│  • 表单对话框 (新建/编辑)                                  │
│  • 导出导入对话框                                          │
│  • 批量选择和操作                                          │
│  • 表头过滤                                                │
│  • 分页和排序                                              │
│  • 跨页选择保留                                            │
│                                                             │
│  ⏳ 可复用到其他对象:                                       │
│  ─────────────────                                          │
│  • useMetaList 整个Composable                             │
│  • boService + metaService                                 │
│  • ExportDialog + ImportDialog                             │
│  • AssociationSelector 组件                                 │
│                                                             │
│  📋 待实现 (Phase 9):                                      │
│  ─────────────────                                          │
│  • 通用详情页组件 (DetailPage.vue)                        │
│  • AssociationPanel 关联信息面板                           │
│  • useDetail Composable                                    │
│  • useAssociation Composable                               │
│  • 分配对话框 (AssignmentDialog)                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.4 现有可复用模块清单

#### 前端Composable层

| 模块 | 行数 | 功能 | 可复用度 |
|------|------|------|---------|
| `useMetaList.js` | ~1500 | 列表CRUD、过滤、排序、分页、批量操作 | ⭐⭐⭐ 高 |
| `useBOApi.js` | ~500 | BO API封装、响应式状态管理 | ⭐⭐⭐ 高 |
| `useImportExportApi.js` | ~300 | 导入导出API封装 | ⭐⭐⭐ 高 |
| `useMessage.js` | ~100 | 全局消息提示 | ⭐⭐ 中 |

#### 前端服务层

| 模块 | 行数 | 功能 | 可复用度 |
|------|------|------|---------|
| `boService.js` | ~300 | CRUD、Association、Deep Insert | ⭐⭐⭐ 高 |
| `metaService.js` | ~260 | UI Config、Schema、View Config | ⭐⭐⭐ 高 |
| `enumService.js` | ~200 | 枚举加载、缓存、预加载 | ⭐⭐ 中 |

#### 前端组件

| 组件 | 类型 | 功能 | 可复用度 |
|------|------|------|---------|
| **FilterBar** | 业务组件 | 统一过滤栏 | ⭐⭐⭐ 高 |
| **MetaTable** | 业务组件 | 元数据驱动表格 | ⭐⭐⭐ 高 |
| **AssociationSelector** | BO组件 | 关联选择器 | ⭐⭐⭐ 高 |
| **AssociationCell** | BO组件 | 关联列渲染 | ⭐⭐ 中 |
| **ExportDialog** | 业务组件 | 导出对话框 | ⭐⭐⭐ 高 |
| **ImportDialog** | 业务组件 | 导入对话框 | ⭐⭐⭐ 高 |
| **AuditLog** | 业务组件 | 审计日志展示 | ⭐⭐ 中 |
| **AppButton/Input/Select** | 基础组件 | 适配Element Plus | ⭐⭐⭐ 高 |

#### 后端模块

| 模块 | 功能 | 可复用度 |
|------|------|---------|
| **AssociationEngine** | 通用关联操作 | ⭐⭐⭐ 高 |
| **ConstraintEngine** | 约束验证 | ⭐⭐⭐ 高 |
| **BOFramework** | 业务对象框架 | ⭐⭐⭐ 高 |
| **9个拦截器** | 通用能力 | ⭐⭐⭐ 高 |

---

## 三、需要新建的标准模块

### 3.1 前端新增模块

```
┌─────────────────────────────────────────────────────────────┐
│              Phase 9 需要新建的标准模块                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  新建 Composable:                                           │
│  ─────────────────                                          │
│  📦 src/composables/useDetail.js                           │
│     - loadDetail: 加载详情                                 │
│     - updateDetail: 更新详情                               │
│     - deleteDetail: 删除详情                               │
│     - loadAssociations: 加载关联信息                         │
│     - 状态: activeTab, loading, detail                    │
│                                                             │
│  📦 src/composables/useAssociation.js                      │
│     - assign: 分配关联                                    │
│     - unassign: 取消关联                                  │
│     - batchAssign: 批量分配                                │
│     - batchUnassign: 批量取消                              │
│     - queryAssociations: 查询关联列表                       │
│                                                             │
│  新建组件:                                                  │
│  ─────────────────                                          │
│  📦 src/components/common/DetailPage/                     │
│     ├── DetailPage.vue        # 通用详情页                 │
│     └── index.js             # 导出                        │
│                                                             │
│  📦 src/components/common/AssociationPanel/                │
│     ├── AssociationPanel.vue  # 关联信息面板               │
│     └── index.js             # 导出                        │
│                                                             │
│  📦 src/components/common/MemberList/                     │
│     ├── MemberList.vue       # 成员列表组件                │
│     └── index.js             # 导出                        │
│                                                             │
│  📦 src/components/common/AssignmentDialog/                │
│     ├── AssignmentDialog.vue  # 分配对话框                 │
│     └── index.js             # 导出                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 后端新增/扩展

| 模块 | 扩展内容 | 优先级 |
|------|---------|--------|
| **bo_api.py** | 添加 assign/unassign 端点 | P0 |
| **bo_api.py** | 完善 GET /bo/{entity}/{id} 返回关联信息 | P0 |
| **YAML元数据** | role.yaml 添加 detail 配置 | P0 |
| **YAML元数据** | user_group.yaml 添加 detail 配置 | P0 |
| **YAML元数据** | user.yaml 完善 detail 配置 | P1 |

### 3.3 可复用架构设计

```
┌─────────────────────────────────────────────────────────────┐
│              可复用架构设计                                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  前端分层架构:                                              │
│  ─────────────────                                          │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ 页面层 (Page)                                       │  │
│  │ ├── UserManagement.vue    (已有)                   │  │
│  │ ├── RoleManagement.vue    (基于UserManagement改造)  │  │
│  │ └── UserGroupManagement.vue (基于UserManagement改造) │  │
│  └─────────────────────────────────────────────────────┘  │
│                           ↓                                │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Composable层 (可复用)                                 │  │
│  │ ├── useMetaList.js       (已有，完全复用)            │  │
│  │ ├── useDetail.js         (新建)                     │  │
│  │ └── useAssociation.js   (新建)                     │  │
│  └─────────────────────────────────────────────────────┘  │
│                           ↓                                │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ 通用组件层 (Component Library)                       │  │
│  │ ├── DetailPage.vue        (新建-通用详情页)          │  │
│  │ ├── AssociationPanel.vue  (新建-关联面板)           │  │
│  │ ├── MemberList.vue       (新建-成员列表)            │  │
│  │ ├── AssignmentDialog.vue  (新建-分配对话框)          │  │
│  │ ├── AssociationSelector.vue (已有-可扩展)            │  │
│  │ └── ExportDialog/ImportDialog (已有)               │  │
│  └─────────────────────────────────────────────────────┘  │
│                           ↓                                │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ 服务层 (Services)                                    │  │
│  │ ├── boService.js       (已有，完全复用)             │  │
│  │ └── metaService.js     (已有，完全复用)             │  │
│  └─────────────────────────────────────────────────────┘  │
│                           ↓                                │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ API层 (Backend)                                      │  │
│  │ └── bo_api.py         (扩展assign/unassign端点)      │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 四、行业最佳实践

### 2.1 SAP CAP: Association vs Composition

```
┌─────────────────────────────────────────────────────────────┐
│              SAP CAP 关联关系类型                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Association (关联)                                          │
│  ├── 描述实体之间的关系，但不拥有子记录                      │
│  ├── 类似 reference 类型                                    │
│  └── 删除父记录不影响子记录                                 │
│                                                             │
│  Composition (组合)                                          │
│  ├── 父记录"拥有"子记录                                    │
│  ├── 级联删除：删除父记录时自动删除子记录                    │
│  └── 类似 composition 类型                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**CDS 定义示例**:
```cds
entity Order : cuid, {
    customer  : Association to Customer;
    items     : Composition of many OrderItems on items.order = $self;
}
```

### 2.2 Microsoft Dataverse: Associate/Disassociate

**分配操作**:
```http
PATCH /api/data/v9.2/contacts({contactId})
{
  "parentcustomerid_account@odata.bind": "accounts({accountId})"
}
```
**响应**: `204 No Content`

**取消分配**:
```http
PATCH /api/data/v9.2/contacts({contactId})
{
  "parentcustomerid_account@odata.bind": null
}
```

### 2.3 SAP CAP: OData $expand 深度读取

```
请求: GET /Orders?$expand=customer,items

响应:
{
  "value": [
    {
      "ID": 1,
      "customer": {           ← 展开的关联对象
        "ID": 101,
        "name": "Acme Corp"
      },
      "items": [             ← 展开的组合对象
        { "product": "A", "quantity": 10 },
        { "product": "B", "quantity": 5 }
      ]
    }
  ]
}
```

### 2.4 Salesforce: Dynamic Related Lists

**核心特性**:
1. **组件可见性**: 根据用户角色/档案显示不同列表
2. **列表过滤**: 动态过滤关联列表
3. **字段选择**: 动态选择显示字段
4. **排序配置**: 动态配置排序规则
5. **操作按钮**: 动态配置操作按钮

---

## 三、详情页面布局最佳实践

### 3.1 SAP Fiori: Dynamic Page

```
┌─────────────────────────────────────────────────────────────┐
│              SAP Fiori Dynamic Page                         │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Header (页面头部)                                     │  │
│  │ - 标题、面包屑                                       │  │
│  │ - 关键字段信息                                       │  │
│  │ - 操作按钮                                           │  │
│  └─────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Content Area (内容区)                                │  │
│  │ - 表单/表格/图表                                     │  │
│  └─────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Footer Toolbar (底部工具栏)                          │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 SAP Fiori: FlexibleColumnLayout

```
桌面端:
┌──────────┬──────────────┬───────────────┐
│ Begin    │ Middle      │ End           │
│ (Master) │ (Detail)    │ (Detail-Detail)│
│ 列表页   │ 详情页      │ 嵌套详情页    │
└──────────┴──────────────┴───────────────┘

平板端:
┌──────────────┬───────────────┐
│ Begin        │ Middle        │
│ (Master)     │ (Detail)      │
└──────────────┴───────────────┘

手机端:
┌────────────────────────┐
│ Single Column          │
│ (Stacked Navigation)   │
└────────────────────────┘
```

### 3.3 Salesforce: Lightning Record Pages

- **Dynamic Forms**: 字段级自定义，动态显示/隐藏
- **Related Lists**: 关联列表，支持过滤和排序
- **Tab-based Layout**: 分Tab展示不同类型信息

---

## 四、API 设计对比

### 4.1 Association 操作模式

| 平台 | 分配操作 | 取消分配 | 查询 | 深度读取 |
|------|---------|---------|------|---------|
| **SAP CAP** | PATCH + bind | PATCH + null | GET + $filter | $expand |
| **Salesforce** | assign() | unassign() | query() | $expand |
| **Dataverse** | PATCH + @odata.bind | PATCH + null | GET | $expand |
| **我们方案** | POST /assign | POST /unassign | GET /list | GET ?$expand |

### 4.2 推荐 API 设计

```
┌─────────────────────────────────────────────────────────────┐
│                    推荐 API 设计                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Association 操作:                                          │
│  ─────────────────                                          │
│  POST /api/v2/bo/{entity}/{id}/$associations/{assoc}/assign      │
│  POST /api/v2/bo/{entity}/{id}/$associations/{assoc}/unassign    │
│  POST /api/v2/bo/{entity}/{id}/$associations/{assoc}/batch_assign│
│  POST /api/v2/bo/{entity}/{id}/$associations/{assoc}/batch_unassign│
│  GET  /api/v2/bo/{entity}/{id}/$associations/{assoc}             │
│  GET  /api/v2/bo/{entity}/{id}/$associations/{assoc}/count       │
│                                                             │
│  详情页:                                                    │
│  ─────────────────                                          │
│  GET  /api/v2/bo/{entity}/{id}                             │
│  GET  /api/v2/bo/{entity}/{id}?associations=users,groups&depth=2 │
│                                                             │
│  响应格式:                                                   │
│  ─────────────────                                          │
│  成功: 204 No Content (分配/取消操作)                       │
│  成功: 200 OK + data (查询操作)                             │
│  错误: 400/401/403/404 + error message                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 五、详情页布局对比

| 平台 | 布局模式 | 导航方式 | 响应式 |
|------|---------|---------|-------|
| **SAP Fiori** | Dynamic Page | FlexibleColumnLayout | ✅ |
| **Salesforce** | Record Page + Tabs | Related Lists | ✅ |
| **Dataverse** | Form-based | Lookup Navigation | ✅ |
| **我们方案** | Tab-based + Panels | Inline + Breadcrumb | ✅ |

---

## 六、推荐采用的设计

```
┌─────────────────────────────────────────────────────────────┐
│              Phase 9 推荐设计方案                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  API 设计:                                                  │
│  ─────────────────                                          │
│  • 分配: POST /assign     (返回 204)                       │
│  • 取消: POST /unassign   (返回 204)                       │
│  • 查询: GET /list        (支持分页)                       │
│  • 深度: GET ?$expand     (限制深度≤2)                     │
│                                                             │
│  详情页布局:                                               │
│  ─────────────────                                          │
│  • Header: 标题 + 操作按钮                                 │
│  • Tabs: 基本信息 | 关联信息 | 操作日志                     │
│  • 关联信息: 可折叠面板，支持过滤和排序                     │
│                                                             │
│  导航模式:                                                 │
│  ─────────────────                                          │
│  • 行内导航: 点击关联列打开侧边详情                         │
│  • 面板导航: 点击Tab进入关联列表                            │
│  • 面包屑: 记录导航路径                                    │
│                                                             │
│  响应式设计:                                               │
│  ─────────────────                                          │
│  • 桌面端: 左侧边栏(可选) + 主内容区                        │
│  • 平板端: 单栏，详情覆盖                                  │
│  • 手机端: 全屏单页                                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 七、关键参考链接

### SAP
- [CAP Documentation](https://cap.cloud.sap/docs/)
- [CAP May 2025 Release](https://cap.cloud.sap/docs/releases/archive/2025/may25)
- [Fiori Page Layouts](https://experience.sap.com/fiori-design-web/floorplan-overview/)
- [FlexibleColumnLayout](https://github.com/SAP-docs/sapui5/blob/main/docs/06_SAP_Fiori_Elements/enabling-the-flexible-column-layout-e762257.md)

### Salesforce
- [LWC GraphQL Relationships](https://developer.salesforce.com/docs/platform/ja-jp/lwc/guide/reference-graphql-relationships.html)
- [Dynamic Related Lists](https://trailhead.salesforce.com/es/content/learn/projects/upgrade-to-dynamic-related-lists/get-started-with-dynamic-related-lists)
- [getRelatedListInfo](https://developer.salesforce.com/docs/platform/ja-jp/lwc/guide/reference-wire-adapters-get-related-list-info.html)

### Microsoft
- [Dataverse Associate/Disassociate](https://learn.microsoft.com/zh-tw/power-apps/developer/data-platform/webapi/associate-disassociate-entities-using-web-api)
- [Dataverse Entity Reference](https://learn.microsoft.com/zh-cn/dynamics365/developer/reference/about-entity-reference)

---

## 八、YAML 配置规范（单一事实原则）

### 8.1 单一事实原则（Single Source of Truth）

遵循以下原则设计 YAML 配置：

```
┌─────────────────────────────────────────────────────────────┐
│              YAML 单一事实原则                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  原则1: 字段定义一次，到处引用                               │
│  ─────────────────────────────────                          │
│  • fields 定义字段元数据                                    │
│  • ui_view_config.detail.tabs 通过 field ID 引用           │
│  • 不要在 detail.tabs 中重复定义字段属性                    │
│                                                             │
│  原则2: UI 配置集中在 ui_view_config                        │
│  ─────────────────────────────────                          │
│  • 列表配置: ui_view_config.list                           │
│  • 表单配置: ui_view_config.form                           │
│  • 详情配置: ui_view_config.detail                         │
│  • 字段级UI: 在 fields[].ui 中定义                         │
│                                                             │
│  原则3: 关联配置在 associations 中定义                       │
│  ─────────────────────────────────                          │
│  • 关联类型 (type)                                          │
│  • 关联字段 (source_key, target_key)                       │
│  • 关联操作 (actions: assign/unassign/list)               │
│  • UI展示 (display: label, target_display_field)           │
│                                                             │
│  原则4: 语义定义在 semantics 中                              │
│  ─────────────────────────────────                          │
│  • business_key: 是否为业务键                               │
│  • display_name: 是否为显示名称                             │
│  • filterable: 是否可过滤                                   │
│  • sortable: 是否可排序                                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 8.2 detail 配置规范

```yaml
# detail 配置 - 单一事实原则
ui_view_config:
  detail:
    # 布局模式: tabs | sections | grid
    layout: tabs
    
    # 标题
    title: "{record.name} 详情"  # 支持模板语法
    
    # Tab 配置
    tabs:
      - id: basic                    # Tab ID
        label: 基本信息               # Tab 标签
        type: fields                 # Tab 类型: fields | association | history
      
      - id: members
        label: 成员列表
        type: association            # 关联Tab
        association: members         # 引用 associations 中的定义
        widget: member_list          # widget: member_list | association_list
      
      - id: roles
        label: 角色
        type: association
        association: roles
        widget: association_list
        actions:                     # 允许的操作
          - assign
          - unassign
      
      - id: history
        label: 变更历史
        type: history                # history 是特殊类型
    
    # 如果 layout: sections
    sections:
      - id: basic_info
        title: 基本信息
        type: fields
        fields:                     # 引用 fields 中的定义
          - username
          - display_name
          - email
          - status
      
      - id: association_section
        title: 关联信息
        type: association
        association: groups
    
    # 如果 layout: grid (简化场景)
    fields:
      - username
      - display_name
      - email
      - status
    associations:
      - members
      - roles
```

### 8.3 关联配置规范

```yaml
# associations 配置 - 单一事实原则
associations:
  - name: members                          # 关联名称 (唯一标识)
    target_type: user                      # 目标对象类型
    type: many_to_many                     # 关联类型
    through: user_group_members            # 中间表
    source_key: group_id                    # 源外键
    target_key: user_id                    # 目标外键
    
    # 元数据字段 (中间表的额外字段)
    metadata_fields:
      - id: is_manager
        type: boolean
        default: false
    
    # 展示配置
    display:
      label: 成员                           # 显示名称
      target_display_field: display_name    # 目标显示字段
      target_code_field: username           # 目标编码字段
    
    # 操作配置
    actions:
      assign:
        label: 添加成员
      unassign:
        label: 移除成员
      list:
        label: 成员列表
        readonly: true
    
    # UI 配置 (引用 ui_view_config.detail)
    ui:
      widget: member_list                   # member_list | association_list | tags
      sortable: true
      filterable: true
      max_display: 10                      # 最大显示数量
```

### 8.4 现有 YAML 分析

```
┌─────────────────────────────────────────────────────────────┐
│              现有 YAML 配置分析                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  user.yaml                                                 │
│  ─────────────────────────────────                          │
│  ✅ associations 定义在顶层                                  │
│  ✅ ui_view_config.detail 定义详情布局                       │
│  ✅ detail.tabs 通过 field ID 引用字段                      │
│  ✅ detail.tabs 通过 association 名称引用关联                │
│                                                             │
│  role.yaml                                                 │
│  ─────────────────────────────────                          │
│  ✅ associations 定义在顶层                                  │
│  ✅ ui_view_config.detail 定义详情布局                       │
│  ✅ associations 包含 actions 配置                          │
│                                                             │
│  user_group.yaml                                           │
│  ─────────────────────────────────                          │
│  ✅ associations 定义在顶层                                  │
│  ✅ metadata_fields 定义中间表字段                          │
│  ✅ display 配置显示字段                                    │
│  ❌ 缺少 ui_view_config.detail                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 九、UI 设计规范（YON_EP_GUIDE.md）

### 9.1 设计规范要点

| 组件类型 | 圆角 | 说明 |
|---------|------|------|
| 按钮/输入框/选择器 | **6px** | 基础交互组件 |
| 标签/分页/下拉项 | **4px** | 小型组件 |
| 卡片/弹窗/抽屉/结果页 | **8px** | 容器型组件 |
| 圆形按钮 | **9999px** | 使用 `rounded` prop |

### 9.2 主题色

| 用途 | 色值 |
|------|------|
| **主色** | `#ea580c` (YonDesign Orange) |
| 成功色 | `#22c55e` (Green) |
| 警告色 | `#f59e0b` (Amber) |
| 危险色 | `#ea580c` (与主色保持一致) |

### 9.3 DetailPage 组件规范

```vue
<!-- DetailPage.vue 设计规范 -->

<!-- 1. 容器圆角: 8px -->
<template>
  <el-drawer 
    class="detail-page"
    :size="width"
  >
    <!-- 头部 -->
    <template #header>
      <div class="detail-page__header">
        <h3>{{ title }}</h3>
        <div class="detail-page__actions">
          <!-- 操作按钮使用 6px 圆角 -->
          <el-button @click="$emit('close')">关闭</el-button>
          <el-button type="primary">编辑</el-button>
        </div>
      </div>
    </template>
    
    <!-- 内容区 -->
    <div class="detail-page__content">
      <!-- Tab 导航 -->
      <el-tabs v-model="activeTab" class="detail-page__tabs">
        <!-- Tab 使用 6px 圆角 -->
        <el-tab-pane label="基本信息" name="basic" />
        <el-tab-pane label="关联信息" name="associations" />
        <el-tab-pane label="变更历史" name="history" />
      </el-tabs>
      
      <!-- Tab 内容 -->
      <div class="detail-page__body">
        <!-- 基本信息 - Grid 布局 -->
        <div class="detail-grid">
          <div class="detail-item">
            <span class="detail-label">字段名</span>
            <span class="detail-value">字段值</span>
          </div>
        </div>
        
        <!-- 关联信息 -->
        <AssociationPanel 
          v-if="activeTab === 'associations'"
          :associations="associations"
        />
        
        <!-- 变更历史 -->
        <AuditLog 
          v-if="activeTab === 'history'"
          :logs="logs"
        />
      </div>
    </div>
  </el-drawer>
</template>

<style scoped>
/* 圆角规范 */
.detail-page {
  /* 容器: 8px */
  --el-drawer-padding-primary: 16px;
}

/* Tab 样式 */
.detail-page__tabs :deep(.el-tabs__item) {
  /* Tab 标签: 6px 圆角 */
  border-radius: 6px 6px 0 0;
}

/* Grid 布局 */
.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-label {
  font-size: 12px;
  color: #999;        /* 灰色标签 */
}

.detail-value {
  font-size: 14px;
  color: #333;        /* 深色值 */
}

/* 按钮: 6px 圆角 */
.el-button {
  border-radius: 6px;
}

/* 标签: 4px 圆角 */
.el-tag {
  border-radius: 4px;
}
</style>
```

### 9.4 AssociationPanel 组件规范

```vue
<!-- AssociationPanel.vue 设计规范 -->

<template>
  <div class="association-panel">
    <!-- 关联列表 -->
    <div v-for="assoc in associations" :key="assoc.name" class="assoc-section">
      <div class="assoc-header">
        <span class="assoc-title">{{ assoc.display.label }}</span>
        <span class="assoc-count">({{ assoc.items.length }})</span>
        
        <!-- 操作按钮 -->
        <div class="assoc-actions" v-if="!readonly">
          <el-button 
            size="small" 
            type="primary"
            @click="openAssignDialog(assoc)"
          >
            添加
          </el-button>
        </div>
      </div>
      
      <!-- 成员列表 -->
      <div class="assoc-list">
        <el-tag
          v-for="item in assoc.items"
          :key="item.id"
          closable
          @close="handleUnassign(assoc, item)"
        >
          {{ item[assoc.display.target_display_field] }}
        </el-tag>
        
        <!-- 空状态 -->
        <span v-if="assoc.items.length === 0" class="assoc-empty">
          暂无数据
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 标签: 4px 圆角 */
.assoc-list .el-tag {
  border-radius: 4px;
  margin: 4px;
}

/* 按钮: 6px 圆角 */
.assoc-actions .el-button {
  border-radius: 6px;
}
</style>
```

### 9.5 复用层级设计

```
┌─────────────────────────────────────────────────────────────┐
│              复用层级设计                                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Level 1: 基础组件 (Element Plus + YON_EP_GUIDE)          │
│  ─────────────────────────────────                          │
│  • el-button     → 6px 圆角                                │
│  • el-drawer     → 8px 圆角                                │
│  • el-tabs       → 6px 圆角                                │
│  • el-tag        → 4px 圆角                                │
│  • el-table      → 6px 圆角                                │
│  • el-pagination → 4px 圆角                                │
│                                                             │
│  Level 2: 业务组件 (复用 UI 组件)                           │
│  ─────────────────────────────────                          │
│  • AuditLog.vue        → 直接复用                          │
│  • FilterBar.vue       → 直接复用                          │
│  • MetaTable.vue       → 直接复用                          │
│  • AssociationSelector.vue → 扩展复用                      │
│                                                             │
│  Level 3: 详情页组件 (新建)                                 │
│  ─────────────────────────────────                          │
│  • DetailPage.vue      → 基于 YAML 配置生成详情页           │
│  • AssociationPanel.vue → 关联信息面板                     │
│  • MemberList.vue      → 成员列表                          │
│                                                             │
│  Level 4: Composable (新建)                                 │
│  ─────────────────────────────────                          │
│  • useDetail.js        → 详情加载/更新逻辑                 │
│  • useAssociation.js  → 关联操作逻辑                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 十、现有详情页组件分析

### 10.1 已有的详情页组件

| 组件 | 位置 | 功能 | 可复用度 |
|------|------|------|---------|
| **RoleDetailDrawer.vue** | `src/views/SystemManagement/` | Tab导航、基本信息、权限配置、操作日志 | ⭐⭐⭐ |
| **DynamicDetail.vue** | `src/views/ArchDataManageApp/components/` | Facet模式、关联关系、变更历史 | ⭐⭐⭐ |
| **DetailPanel.vue** | `src/views/ArchDataManageApp/components/` | 层级路径、关联关系、变更历史 | ⭐⭐⭐ |
| **RelationFacet.vue** | `src/views/ArchDataManageApp/components/` | 关联关系双栏展示 | ⭐⭐ |
| **AuditLog.vue** | `src/components/common/AuditLog/` | 操作日志时间线展示 | ⭐⭐⭐ |

### 10.2 详情页模式分析

```
┌─────────────────────────────────────────────────────────────┐
│              现有详情页模式分析                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  RoleDetailDrawer.vue                                       │
│  ─────────────────────────────────                          │
│  ├── Header: 标题 + 关闭按钮                                 │
│  ├── Tabs: [权限配置] [操作日志]                            │
│  ├── 基本信息: name, code, description                      │
│  ├── 权限配置:                                              │
│  │   ├── 菜单权限树 (可折叠)                               │
│  │   ├── 功能权限矩阵                                      │
│  │   └── 数据范围配置                                      │
│  └── 操作日志: AuditLog 组件                               │
│                                                             │
│  DynamicDetail.vue                                          │
│  ─────────────────────────────────                          │
│  ├── Header: 返回按钮 + 标题 + 操作按钮                       │
│  ├── Tabs: [基本信息] [变更历史]                            │
│  ├── 基本信息: Facet 模式展示                               │
│  │   ├── relation_list 类型 (RelationFacet)               │
│  │   └── 普通字段类型 (detail-grid)                        │
│  ├── 关联关系: sourceRelations / targetRelations           │
│  └── 变更历史: 时间线展示                                   │
│                                                             │
│  DetailPanel.vue                                            │
│  ─────────────────────────────────                          │
│  ├── Header: 返回按钮 + 标题 + 操作按钮                       │
│  ├── 基本信息: detail-grid 模式                            │
│  ├── 层级路径: hierarchy-path                              │
│  ├── 关联关系: 双栏展示 (source/target)                   │
│  └── 变更历史: 时间线展示                                   │
│                                                             │
│  通用组件:                                                  │
│  ─────────────────────────────────                          │
│  ├── AuditLog.vue: 操作日志时间线                          │
│  ├── RelationFacet.vue: 关联关系展示                        │
│  └── 使用模式:                                              │
│      • Tab 导航                                            │
│      • Section 分组                                        │
│      • Grid 布局 (2列)                                     │
│      • 时间线展示                                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 10.3 可复用组件清单

| 组件 | 行数 | 功能 | 复用价值 | 复用建议 |
|------|------|------|---------|---------|
| **AuditLog.vue** | ~300 | 操作日志时间线展示 | ⭐⭐⭐ | 直接复用 |
| **RelationFacet.vue** | ~150 | 关联关系双栏展示 | ⭐⭐ | 可扩展为 AssociationPanel |
| **DetailPanel.vue** | ~500 | 基本信息 + 层级路径 | ⭐⭐ | 可提取通用布局 |
| **DynamicDetail.vue** | ~400 | Facet 模式详情页 | ⭐⭐⭐ | 可提取为 DetailPage 基类 |

### 10.4 UserManagement.vue 详情抽屉分析

```vue
<!-- UserManagement.vue 详情抽屉 -->
<el-drawer v-model="showDetailDrawer" title="用户详情" size="600px">
  <!-- Tab 导航 -->
  <el-tabs v-model="activeDetailTab">
    <el-tab-pane label="基本信息" name="basic" />
    <el-tab-pane label="关联信息" name="associations" />
    <el-tab-pane label="操作日志" name="logs" />
  </el-tabs>
  
  <!-- 基本信息 -->
  <div v-if="activeDetailTab === 'basic'">
    <!-- 用户字段展示 -->
  </div>
  
  <!-- 关联信息 -->
  <div v-if="activeDetailTab === 'associations'">
    <!-- AssociationSelector 组件 -->
  </div>
  
  <!-- 操作日志 -->
  <div v-if="activeDetailTab === 'logs'">
    <AuditLog :logs="userLogs" />
  </div>
</el-drawer>
```

### 10.5 复用策略建议

```
┌─────────────────────────────────────────────────────────────┐
│              详情页复用策略                                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  复用层次:                                                  │
│  ─────────────────────────────────                          │
│                                                             │
│  Level 1: 直接复用 (无需修改)                               │
│  ├── AuditLog.vue                                          │
│  └── FilterBar.vue                                         │
│                                                             │
│  Level 2: 配置化复用 (通过YAML配置)                         │
│  ├── DetailPage.vue    ← 新建，统一布局                    │
│  ├── AssociationPanel.vue ← 新建，关联信息面板              │
│  └── MetaTable.vue                                         │
│                                                             │
│  Level 3: 模式复用 (继承/组合)                              │
│  ├── useDetail.js      ← 新建，详情逻辑Composable          │
│  ├── useAssociation.js ← 新建，关联操作Composable          │
│  └── DynamicDetail.vue  ← 可作为 DetailPage 基类参考       │
│                                                             │
│  具体实现:                                                  │
│  ─────────────────────────────────                          │
│                                                             │
│  1. 新建通用 DetailPage.vue                                 │
│     ├── 基于 DynamicDetail.vue + DetailPanel.vue 合并优化   │
│     ├── 支持 YAML 配置                                     │
│     └── 支持 Tab + Section + Grid 布局                     │
│                                                             │
│  2. 新建通用 AssociationPanel.vue                            │
│     ├── 基于 RelationFacet.vue + UserManagement 关联部分    │
│     ├── 支持关联列表展示                                    │
│     └── 支持分配/取消分配操作                               │
│                                                             │
│  3. 新建 useDetail.js                                      │
│     ├── loadDetail(): 加载详情                             │
│     ├── updateDetail(): 更新详情                           │
│     ├── deleteDetail(): 删除详情                           │
│     └── loadAuditLogs(): 加载审计日志                      │
│                                                             │
│  4. 新建 useAssociation.js                                  │
│     ├── assign(): 分配关联                                │
│     ├── unassign(): 取消关联                              │
│     ├── queryAssociations(): 查询关联                      │
│     └── loadAssociationMembers(): 加载成员列表             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 十一、后续行动

1. **Phase 9.1**: 实现 Association 操作 UI 通用化 ✅ 已完成
2. **Phase 9.2**: 实现 useDetail Composable 和详情页面 ✅ 已完成
3. **Phase 9.3**: 实现 Partial Edit in Place 模式
4. **Phase 9.4**: 实现 Role 对象适配
5. **Phase 9.5**: 实现 UserGroup 对象适配
6. **Phase 9.6**: 实现导航与 Retrieve 能力
7. **Phase 9.7**: 集成测试与优化

---

## 十二、详情页编辑模式设计（已确认采纳）

### 12.1 编辑模式选择

基于 SAP Fiori / Salesforce / Dynamics 365 的最佳实践研究，确认采纳 **Partial Edit in Place** 模式：

```
┌─────────────────────────────────────────────────────────────┐
│              Partial Edit in Place 模式                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  交互流程:                                                  │
│  ─────────────────────────────────                          │
│  1. 用户查看详情页（只读模式）                               │
│  2. 用户点击 section 头部的 "编辑" 按钮                      │
│  3. 该 section 切换为编辑模式                                │
│     - 字段变为可编辑状态                                    │
│     - "编辑" 按钮变为 "保存" 和 "取消" 按钮                  │
│  4. 用户编辑字段                                            │
│  5. 用户点击 "保存" 或 "取消"                                │
│     - 保存：提交修改，刷新数据                              │
│     - 取消：放弃修改，恢复原数据                            │
│                                                             │
│  适用场景:                                                  │
│  ─────────────────────────────────                          │
│  • 基本信息 section：支持就地编辑                           │
│  • 关联信息 section：保持 Dialog 模式（需要选择目标对象）    │
│  • 变更历史 section：只读，不可编辑                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 12.2 各 section 编辑模式

| Section 类型 | 编辑模式 | 说明 |
|-------------|---------|------|
| **基本信息** | Partial Edit in Place | section 级别就地编辑 |
| **关联信息** | Dialog | 分配/取消分配通过 Dialog 完成 |
| **变更历史** | 只读 | 不可编辑 |

### 12.3 UI 设计

```
┌─────────────────────────────────────────────────────────────┐
│  用户详情                                          [关闭]   │
├─────────────────────────────────────────────────────────────┤
│  [基本信息] [角色] [所属用户组] [变更历史]                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  基本信息                              [编辑]               │
│  ─────────────────────────────────────────────────────────  │
│  用户名:      admin                                         │
│  显示名称:    系统管理员                                    │
│  邮箱:        admin@example.com                            │
│  状态:        [启用]                                        │
│                                                             │
│  点击 [编辑] 后:                                            │
│  ─────────────────────────────────────────────────────────  │
│  基本信息                            [保存] [取消]          │
│  ─────────────────────────────────────────────────────────  │
│  用户名:      [admin        ]                               │
│  显示名称:    [系统管理员    ]                               │
│  邮箱:        [admin@example.com]                          │
│  状态:        [启用 ▼]                                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 12.4 实现要点

1. **DetailSection.vue** 组件扩展
   - 添加 `editable` prop 控制是否可编辑
   - 添加 `editing` prop 控制编辑状态
   - 添加 `@edit`, `@save`, `@cancel` 事件
   - 字段渲染支持编辑模式

2. **DetailPage.vue** 组件扩展
   - 管理 section 编辑状态
   - 处理保存/取消逻辑
   - 数据验证和提交

3. **useDetail.js** Composable 扩展
   - 添加 `updateSection` 方法
   - 支持部分字段更新

---

## 十三、元模型驱动的字段权限控制

### 13.1 字段权限配置层级

```
┌─────────────────────────────────────────────────────────────┐
│              字段权限配置层级（单一事实原则）                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Level 1: 全局字段 UI 配置 (fields[].ui)                     │
│  ─────────────────────────────────                          │
│  • visible: true/false     # 字段是否可见                   │
│  • editable: true/false    # 字段是否可编辑                 │
│  • readonly: true/false    # 字段是否只读（优先级更高）       │
│  • hidden_in_detail: true  # 在详情页隐藏                   │
│  • hidden_in_form: true    # 在表单隐藏                     │
│  • hidden_in_list: true    # 在列表隐藏                     │
│                                                             │
│  Level 2: detail 级别字段配置覆盖                             │
│  ─────────────────────────────────                          │
│  ui_view_config:                                            │
│    detail:                                                  │
│      tabs:                                                  │
│        - id: basic                                          │
│          fields:                                            │
│            - id: username                                   │
│              editable: false    # 覆盖全局配置              │
│            - id: email                                     │
│              visible: true                                  │
│              editable: true                                 │
│                                                             │
│  Level 3: 运行时权限检查                                      │
│  ─────────────────────────────────                          │
│  • 基于用户角色/权限动态控制                                  │
│  • 基于数据状态动态控制                                      │
│  • 基于业务规则动态控制                                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 13.2 字段权限配置规范

```yaml
# 字段级 UI 配置
fields:
  - id: username
    name: 用户名
    type: string
    ui:
      # 全局 UI 配置
      visible: true           # 默认可见
      editable: true          # 默认可编辑
      readonly: false         # 默认非只读
      hidden_in_detail: false # 在详情页不隐藏
      hidden_in_form: false   # 在表单不隐藏
      hidden_in_list: false   # 在列表不隐藏
      
  - id: created_at
    name: 创建时间
    type: datetime
    ui:
      visible: true
      editable: false         # 创建时间不可编辑
      readonly: true          # 只读
      
  - id: password_hash
    name: 密码哈希
    type: string
    ui:
      visible: false          # 敏感字段，不可见
      editable: false
      hidden_in_detail: true  # 在详情页隐藏
      hidden_in_form: true    # 在表单隐藏
      hidden_in_list: true    # 在列表隐藏

# detail 级别字段配置覆盖
ui_view_config:
  detail:
    tabs:
      - id: basic
        label: 基本信息
        type: fields
        fields:
          - id: username
            editable: false     # 用户名不可修改
            readonly: true
          - id: display_name
            editable: true
          - id: email
            editable: true
          - id: status
            editable: true
          - id: created_at
            visible: true
            editable: false
```

### 13.3 权限计算优先级

```
权限计算优先级（从高到低）:

1. detail.tabs[].fields[].readonly     # 最高优先级
2. detail.tabs[].fields[].editable
3. detail.tabs[].fields[].visible
4. fields[].ui.readonly
5. fields[].ui.editable
6. fields[].ui.visible                 # 最低优先级

计算逻辑:
- readonly = true → 字段不可编辑（无论 editable 值）
- editable = false → 字段不可编辑
- visible = false → 字段不显示
- hidden_in_detail = true → 字段在详情页不显示
```

### 13.4 组件实现

```javascript
// DetailSection.vue 中计算字段权限
function getFieldPermission(fieldId) {
  // 1. 获取全局字段配置
  const globalField = props.schema?.fields?.find(f => f.id === fieldId)
  
  // 2. 获取 detail 级别字段配置
  const detailField = props.detailFields?.find(f => f.id === fieldId)
  
  // 3. 计算最终权限
  return {
    visible: detailField?.visible ?? globalField?.ui?.visible ?? true,
    editable: detailField?.editable ?? globalField?.ui?.editable ?? true,
    readonly: detailField?.readonly ?? globalField?.ui?.readonly ?? false,
    hiddenInDetail: globalField?.ui?.hidden_in_detail ?? false
  }
}

function isFieldEditable(field) {
  const permission = getFieldPermission(field.id)
  
  // 权限检查优先级
  if (props.readonly) return false
  if (permission.hiddenInDetail) return false
  if (permission.readonly) return false
  if (!permission.editable) return false
  if (!permission.visible) return false
  
  // 系统字段不可编辑
  const systemFields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']
  if (systemFields.includes(field.id)) return false
  
  return true
}
```

---

## 十四、现有实现复用与统一

### 14.1 后端已有能力

项目中已实现完善的元模型驱动能力：

| 模块 | 文件 | 功能 |
|------|------|------|
| **FieldPermissionChecker** | `meta/core/field_permission_checker.py` | 字段级权限校验 |
| **ViewConfigService** | `meta/services/view_config_service.py` | 视图配置服务 |

### 14.2 FieldPermissionChecker 能力

```python
class FieldPermissionChecker:
    """字段级权限校验器"""
    
    def filter_readable_fields(object_type, record) -> Dict
        # 过滤不可读字段，返回仅包含可读字段的记录
    
    def filter_writable_fields(object_type, data) -> Dict
        # 过滤不可写字段，返回仅包含可写字段的数据
    
    def get_hidden_fields(object_type) -> List[str]
        # 获取对当前用户隐藏的字段列表
    
    def get_readonly_fields(object_type) -> List[str]
        # 获取对当前用户只读的字段列表
```

### 14.3 ViewConfigService 智能推导

```python
class ViewConfigService:
    """视图配置服务 - 已实现单一事实原则"""
    
    def build_list_view_from_fields(object_type) -> UIListViewConfig
        # 从字段定义自动构建列表视图配置
    
    def build_detail_view_from_fields(object_type) -> UIDetailViewConfig
        # 从字段定义自动构建详情视图配置
    
    def build_form_view_from_fields(object_type) -> UIFormViewConfig
        # 从字段定义自动构建表单视图配置
    
    def _enrich_columns_with_field_meta(object_type, config)
        # 用字段元数据丰富视图配置
    
    def _auto_generate_filters(list_config, field_map)
        # 自动生成过滤器：默认所有字段都可过滤
    
    def _auto_generate_search_fields(list_config, field_map)
        # 自动生成搜索字段：默认所有字符串类型字段都可搜索
    
    def _apply_default_sort(list_config, field_map)
        # 应用默认排序：updated_at 降序
```

### 14.4 单一事实原则实现

后端已实现的智能推导：

```
┌─────────────────────────────────────────────────────────────┐
│              后端已实现的单一事实原则                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 默认所有字段都可排序                                     │
│     除非显式声明 sortable: false                            │
│                                                             │
│  2. 默认所有字段都可过滤                                     │
│     除非显式声明 filterable: false                          │
│                                                             │
│  3. 默认所有字符串类型字段都可搜索                           │
│     无需在 YAML 中重复声明 searchFields                     │
│                                                             │
│  4. 默认排序使用 updated_at 降序                            │
│     无需在每个 YAML 中重复配置 defaultSort                  │
│                                                             │
│  5. 从字段定义自动构建视图配置                               │
│     当没有显式配置时，根据字段的 UI 注解自动生成              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 14.5 字段权限智能推导

基于 SAP Fiori 最佳实践，实现字段权限智能推导：

```python
# 字段权限智能推导规则
FIELD_PERMISSION_RULES = {
    # 系统字段：始终只读
    'system_fields': {
        'fields': ['id', 'created_at', 'updated_at', 'created_by', 'updated_by'],
        'readonly': True,
        'editable': False
    },
    
    # 时间戳字段：只读
    'timestamp_fields': {
        'types': ['datetime', 'timestamp'],
        'readonly': True,
        'editable': False
    },
    
    # 敏感字段：隐藏
    'sensitive_fields': {
        'fields': ['password_hash', 'password', 'secret', 'token'],
        'visible': False,
        'hidden_in_detail': True,
        'hidden_in_form': True,
        'hidden_in_list': True
    },
    
    # 业务键字段：创建后不可修改
    'business_key_fields': {
        'semantics': ['business_key'],
        'editable_on_create': True,
        'editable_on_update': False,
        'readonly_after_create': True
    },
    
    # 计算字段：只读
    'computed_fields': {
        'semantics': ['computed', 'calculated'],
        'readonly': True,
        'editable': False
    }
}
```

### 14.6 YAML 简化配置

基于智能推导，YAML 配置可以大幅简化：

```yaml
# 简化前：需要完整配置
ui_view_config:
  detail:
    tabs:
      - id: basic
        fields:
          - id: username
            editable: false
            readonly: true
          - id: display_name
            editable: true
          - id: email
            editable: true
          - id: created_at
            editable: false
            readonly: true

# 简化后：智能推导
# 无需配置 detail.tabs，系统自动从 fields 推导
# 只需配置例外情况

fields:
  - id: username
    semantics:
      business_key: true    # 自动推导：创建后不可修改
  
  - id: password_hash
    ui:
      visible: false        # 自动推导：隐藏
      
  - id: created_at
    type: datetime          # 自动推导：只读

# detail 配置可选，仅在需要覆盖时配置
ui_view_config:
  detail:
    tabs:
      - id: basic
        fields:
          - id: status      # 仅配置需要覆盖的字段
            editable: true  # 覆盖默认值
```

### 14.7 前端复用策略

```
┌─────────────────────────────────────────────────────────────┐
│              前端复用后端智能推导                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 后端 API 返回已计算的字段权限                            │
│     GET /api/v2/meta/{objectType}/ui-config                │
│     返回: fields[].ui.{visible, editable, readonly}        │
│                                                             │
│  2. 前端组件直接使用后端返回的权限                           │
│     无需前端重复计算                                        │
│                                                             │
│  3. 前端仅需处理运行时动态权限                               │
│     - 基于数据状态的权限                                    │
│     - 基于用户交互的权限                                    │
│                                                             │
│  4. detail 级别配置仅用于覆盖                                │
│     覆盖后端计算的默认权限                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 11.1 复用检查清单

在实现新功能前，请检查以下复用清单：

- [ ] `AuditLog.vue` 能否满足审计日志需求？ → 直接复用
- [ ] `DetailPanel.vue` 的布局模式能否复用？ → 作为 DetailPage 参考
- [ ] `DynamicDetail.vue` 的 Facet 模式能否复用？ → 作为 DetailPage 参考
- [ ] `UserManagement.vue` 的详情抽屉能否配置化？ → 新建 DetailPage.vue
- [ ] `UserManagement.vue` 的关联信息能否通用化？ → 新建 AssociationPanel.vue
