## 目录

1. [业务场景分析](#业务场景分析)
2. [行业内的页面组件模式](#行业内的页面组件模式)
3. [组件抽象建议](#组件抽象建议)
4. [现有实现分析与改进建议](#现有实现分析与改进建议)
5. [实施路线图](#实施路线图)
6. [行业头部方案研究](#行业头部方案研究)
7. [复杂对象表单方案](#复杂对象表单方案)
8. [总结](#总结)

---
# 页面组件模式研究

> **重要：分析业务场景与行业内的页面组件模式**
>
> **最后更新**: 2026-05-11
> **研究范围**: 父子关系 + 关联关系

---

## 业务场景分析

### 场景 1: 产品与版本管理（父子关系）

```
┌─────────────────────────────────────────────────────────────┐
│ 产品管理                                                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  产品A                                                       │
│    ├── 版本 1.0                                             │
│    ├── 版本 2.0                                             │
│    └── 版本 3.0 (当前)                                       │
│                                                             │
│  产品B                                                       │
│    ├── 版本 1.0                                             │
│    └── 版本 2.0                                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**当前实现**：
- `ProductTree.vue` - 产品树形列表
- `VersionTable.vue` - 版本表格
- `ProductFormDialog.vue` - 产品表单
- `VersionFormDialog.vue` - 版本表单

---

### 场景 2: 用户、用户组、角色（关联关系）

```
┌─────────────────────────────────────────────────────────────┐
│ 用户权限管理                                                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  用户 ─────┬───── 用户组                                    │
│            │                                                │
│            └───── 角色                                       │
│                                                             │
│  用户组 ───┬───── 用户                                       │
│            │                                                │
│            └───── 角色                                       │
│                                                             │
│  角色 ─────┬───── 权限                                       │
│            │                                                │
│            └───── 用户组                                     │
│                     └───── 用户                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**当前实现**：
- `UserManagement.vue` - 用户管理
- `UserGroupManagement.vue` - 用户组管理
- `RoleManagement.vue` - 角色管理
- `GroupRoleDialog.vue` - 用户组-角色关联
- `RoleDetailDrawer.vue` - 角色详情（权限配置）

---

## 行业内的页面组件模式

### 1. 父子关系模式

#### 1.1 Tree-Master-Detail（树形-主表-详情）

```
┌────────────────┬────────────────────────────────────────┐
│                │                                        │
│   树形导航      │           主表区域                      │
│                │                                        │
│  ├─ 节点1      │  ┌──────┬──────┬──────┬──────┐      │
│  ├─ 节点2  ←──┼──│ Col1 │ Col2 │ Col3 │ Col4 │      │
│  └─ 节点3      │  ├──────┼──────┼──────┼──────┤      │
│                │  │      │      │      │      │      │
│                │  │ Data │ Data │ Data │ Data │      │
│                │  └──────┴──────┴──────┴──────┘      │
│                │                                        │
│                ├────────────────────────────────────────┤
│                │                                        │
│                │           详情区域                      │
│                │                                        │
│                │  ┌─────────────────────────────────┐   │
│                │  │                                 │   │
│                │  │   选中项的详细信息              │   │
│                │  │                                 │   │
│                │  └─────────────────────────────────┘   │
│                │                                        │
└────────────────┴────────────────────────────────────────┘
```

**适用场景**：
- 产品-版本管理
- 分类-子分类
- 组织-部门

**行业产品**：
- Jira - Issue Type Scheme
- Confluence - Space Structure
- Jenkins - Folder/Job

#### 1.2 Tree-Grid（树形-网格）

```
┌─────────────────────────────────────────────────────────────┐
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │ 树形 + 表格 组合视图                                 │ │
│  ├──────────────────────────────────────────────────────┤ │
│  │ ├─ 产品A                                            │ │
│  │ │  ├── Version 1.0                                  │ │
│  │ │  └── Version 2.0                                  │ │
│  │ └─ 产品B                                            │ │
│  │    ├── Version 1.0                                  │ │
│  │    └── Version 2.0                                  │ │
│  │                                                       │ │
│  │  特点：在同一视图中展示父子关系                      │ │
│  │  优点：直观、层次清晰                               │ │
│  │  缺点：不适合大数据量                               │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
└─────────────────────────────────────────────────────────────┘
```

**适用场景**：
- 简单的父子关系展示
- 层级不深的结构

#### 1.3 Tree-Select-Detail（树形-选择-详情）

```
┌─────────────────────────────────────────────────────────────┐
│                                                            │
│   树形选择         选中项详情                               │
│                                                            │
│  ┌──────────┐   ┌────────────────────────────────────┐  │
│  │ 树形列表  │   │                                    │  │
│  │          │   │  ┌────────────────────────────┐    │  │
│  │ 产品A    │   │  │  基本信息                 │    │  │
│  │  版本1.0 │ ←──│  名称: 产品A - 版本1.0     │    │  │
│  │  版本2.0 │   │  状态: 活跃               │    │  │
│  │ 产品B    │   │  创建时间: 2024-01-01     │    │  │
│  │  版本1.0 │   │  └────────────────────────────┘    │  │
│  │          │   │                                    │  │
│  └──────────┘   │  ┌────────────────────────────┐    │  │
│                 │  │  版本列表                 │    │  │
│                 │  │  [表格展示子版本]          │    │  │
│                 │  └────────────────────────────┘    │  │
│                 └────────────────────────────────────┘  │
│                                                            │
└─────────────────────────────────────────────────────────────┘
```

**适用场景**：
- 需要展示选中项的详细信息
- 父子关系有明显区分

---

### 2. 关联关系模式

#### 2.1 Master-Detail-Tabs（主表-详情-标签页）

```
┌─────────────────────────────────────────────────────────────┐
│                                                            │
│  主表区域（列表）                                          │
│  ┌──────────────────────────────────────────────────────┐ │
│  │ 用户列表 / 用户组列表 / 角色列表                      │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
│  详情抽屉/面板                                            │
│  ┌────────────────────────────────────────────────────┐  │
│  │  基本信息  │  关联用户  │  关联角色  │  权限配置  │  │
│  ├────────────────────────────────────────────────────┤  │
│  │                                                    │  │
│  │  Tab 内容区域                                       │  │
│  │                                                    │  │
│  │  - 关联用户：用户列表 + 添加/移除                    │  │
│  │  - 关联角色：角色列表 + 添加/移除                    │  │
│  │  - 权限配置：权限树/矩阵                           │  │
│  │                                                    │  │
│  └────────────────────────────────────────────────────┘  │
│                                                            │
└─────────────────────────────────────────────────────────────┘
```

**适用场景**：
- 用户-用户组-角色关联管理
- 需要展示多维度关联

**行业产品**：
- Keycloak - Role/Group Management
- Azure AD - Enterprise Applications
- AWS IAM - Users/Groups/Roles

#### 2.2 Transfer（穿梭框）

```
┌─────────────────────────────────────────────────────────────┐
│                                                            │
│  用户组: 测试组                                            │
│                                                            │
│  ┌───────────────────┐       ┌───────────────────┐        │
│  │ 可选角色           │       │ 已选角色           │        │
│  ├───────────────────┤       ├───────────────────┤        │
│  │ ☐ 管理员          │  ───→ │ ☑ 开发者          │        │
│  │ ☑ 开发者          │  ←─── │ ☑ 测试人员        │        │
│  │ ☐ 测试人员        │       │                   │        │
│  │ ☐ 访客            │       │                   │        │
│  └───────────────────┘       └───────────────────┘        │
│                                                            │
│  [确定]  [取消]                                            │
│                                                            │
└─────────────────────────────────────────────────────────────┘
```

**适用场景**：
- 用户组-角色关联
- 用户-权限关联
- 多对多关系管理

**Element Plus 组件**：`el-transfer`

#### 2.3 Multi-Select-Table（多选表格）

```
┌─────────────────────────────────────────────────────────────┐
│                                                            │
│  关联用户组                                                │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │ ☐ │ 名称      │ 描述              │ 成员数          │ │
│  ├───┼───────────┼───────────────────┼──────────────────┤ │
│  │ ☑ │ 研发组    │ 研发相关人员      │ 15              │ │
│  │ ☐ │ 测试组    │ 测试相关人员      │ 8               │ │
│  │ ☑ │ 产品组    │ 产品相关人员      │ 5               │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
│  已选择: 2 项                          [移除选中] [清空]   │
│                                                            │
└─────────────────────────────────────────────────────────────┘
```

**适用场景**：
- 用户-用户组关联
- 角色-用户组关联
- 需要展示关联实体详情

#### 2.4 Association-Panel（关联面板）

```
┌─────────────────────────────────────────────────────────────┐
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │ 关联用户                                              │ │
│  ├──────────────────────────────────────────────────────┤ │
│  │                                                      │ │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐      │ │
│  │  │ 用户1  │ │ 用户2  │ │ 用户3  │ │ + 添加  │      │ │
│  │  └────────┘ └────────┘ └────────┘ └────────┘      │ │
│  │                                                      │ │
│  │  [移除] 操作在 hover 时显示                         │ │
│  │                                                      │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │ 关联角色                                              │ │
│  ├──────────────────────────────────────────────────────┤ │
│  │                                                      │ │
│  │  ┌────────┐ ┌────────┐ ┌────────┐                  │ │
│  │  │ 管理员  │ │ 开发者  │ │ 测试   │                  │ │
│  │  └────────┘ └────────┘ └────────┘                  │ │
│  │                                                      │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
└─────────────────────────────────────────────────────────────┘
```

**适用场景**：
- 用户组详情页
- 角色详情页
- 需要直观展示关联关系

---

## 组件抽象建议

### 1. 父子关系组件

#### 1.1 MetaTreePage（树形列表页）

**定位**：通用树形列表页面组件

```vue
<!-- 使用示例 -->
<MetaTreePage
  object-type="product_version"
  :tree-config="{
    parentField: 'parent_id',
    labelField: 'name',
    iconField: 'type'
  }"
  :list-config="{
    columns: ['name', 'version', 'status', 'created_at'],
    actions: ['edit', 'delete']
  }"
/>
```

**Props**：

| 属性 | 类型 | 说明 |
|------|------|------|
| `objectType` | String | 业务对象类型 |
| `treeConfig` | Object | 树形配置 |
| `listConfig` | Object | 表格配置 |
| `parentField` | String | 父级字段 |
| `rootFilter` | Object | 根节点筛选条件 |

#### 1.2 TreeDetailPanel（树形-详情面板）

**定位**：树形导航 + 详情展示

```vue
<!-- 使用示例 -->
<TreeDetailPanel
  :tree-data="products"
  :detail-component="VersionDetail"
  :tree-props="{
    label: 'name',
    children: 'versions'
  }"
/>
```

**Props**：

| 属性 | 类型 | 说明 |
|------|------|------|
| `treeData` | Array | 树形数据 |
| `detailComponent` | Component | 详情组件 |
| `treeProps` | Object | Element Plus Tree Props |

---

### 2. 关联关系组件

#### 2.1 AssociationManager（关联管理器）

**定位**：通用的关联关系管理组件

```vue
<!-- 使用示例：用户组-角色关联 -->
<AssociationManager
  type="many-to-many"
  :source="{ objectType: 'user_group', id: groupId }"
  :target="{ objectType: 'role' }"
  :display-mode="'transfer'"
  :columns="['name', 'code', 'description']"
  @change="handleAssociationChange"
/>
```

**Props**：

| 属性 | 类型 | 说明 |
|------|------|------|
| `type` | String | 关联类型（many-to-many） |
| `source` | Object | 源对象配置 |
| `target` | Object | 目标对象配置 |
| `displayMode` | String | 显示模式（transfer/table/panel） |
| `columns` | Array | 列表列配置 |

**displayMode 选项**：

| 值 | 说明 | 适用场景 |
|----|------|----------|
| `transfer` | 穿梭框 | 大量选项、快速选择 |
| `table` | 多选表格 | 需要展示详情、批量操作 |
| `panel` | 卡片面板 | 直观展示、适合少量关联 |

#### 2.2 RolePermissionPanel（角色权限面板）

**定位**：角色权限配置专用面板

```vue
<!-- 使用示例 -->
<RolePermissionPanel
  :role="currentRole"
  :menu-tree="menuTree"
  :permission-tree="permissionTree"
  @save="handleSavePermissions"
/>
```

**Props**：

| 属性 | 类型 | 说明 |
|------|------|------|
| `role` | Object | 当前角色 |
| `menuTree` | Array | 菜单树 |
| `permissionTree` | Array | 权限树 |

---

## 现有实现分析与改进建议

### 当前实现问题

#### 1. 产品-版本管理

**现有实现**：
- `ProductTree.vue` - 手写树形列表
- `VersionTable.vue` - 手写版本表格
- 无统一的父子关系组件

**问题**：
- 代码重复
- 难以复用
- 维护成本高

**改进建议**：
```vue
<!-- 改进后：使用通用父子关系组件 -->
<MetaTreePage
  object-type="product_version"
  :tree-config="{
    parentField: 'parent_id',
    rootFilter: { type: 'product' }
  }"
  :list-config="{
    columns: ['name', 'version', 'status', 'created_at'],
    rowActions: ['edit', 'delete']
  }"
/>
```

#### 2. 用户-用户组-角色关联

**现有实现**：
- `GroupRoleDialog.vue` - 硬编码的角色穿梭框
- `RoleDetailDrawer.vue` - 硬编码的权限配置
- 无统一的关联管理组件

**问题**：
- 关联逻辑分散
- 无法通用化
- 扩展性差

**改进建议**：
```vue
<!-- 改进后：使用通用关联管理组件 -->
<AssociationManager
  type="many-to-many"
  :source="{ objectType: 'user_group', id: currentGroupId }"
  :target="{ objectType: 'role' }"
  display-mode="transfer"
/>

<!-- 或使用卡片面板模式 -->
<AssociationManager
  type="many-to-many"
  :source="{ objectType: 'role', id: currentRoleId }"
  :target="{ objectType: 'user_group' }"
  display-mode="panel"
/>
```

---

## 实施路线图

### Phase 1: 抽象通用组件（短期）

1. **MetaTreePage** - 树形列表页组件
   - 支持父子关系展示
   - 支持选择和详情展示
   - YAML 驱动

2. **AssociationManager** - 关联管理器
   - 支持多种显示模式
   - 支持 CRUD 操作
   - YAML 驱动

### Phase 2: 业务场景适配（中期）

1. **产品-版本管理** - 迁移到 MetaTreePage
2. **用户组-角色关联** - 迁移到 AssociationManager
3. **用户-用户组关联** - 迁移到 AssociationManager

### Phase 3: 组件完善（长期）

1. **RolePermissionPanel** - 角色权限专用面板
2. **HierarchyTree** - 层级数据专用树形组件
3. **PermissionMatrix** - 权限矩阵组件

---

## 行业头部方案研究

### SAP Fiori：Object Page Floorplan（对象页蓝图）

SAP Fiori 的 Object Page 是目前 SAP 旗舰级的对象展示方案，专门解决复杂对象（20+ 属性）的展示问题。

#### 三级容器体系

```
Section（段）
  └── SubSection（子段）
        └── Content（实际内容：表单/表格/图表）
```

**设计理念**：一个 Section = 一个业务语义域。

#### 两种导航方式对比

| 导航方式 | 适用场景 | 说明 |
|---------|---------|------|
| Anchor Bar（锚点栏） | 相关内容流式阅读 | 水平锚点，点击滚动到对应 Section |
| Tab Bar（标签页） | 内容相互独立 | Tab 切换，各自有复杂内容（如内嵌表格） |

#### FieldGroup：字段分组（核心手段）

通过 `@UI.FieldGroup` 注解将紧密相关的字段打包为视觉容器：

```yaml
FieldGroups:
  - group: "Address"
    fields: [Street, HouseNumber, PostalCode, City, Country, Region]
  - group: "Financial"
    fields: [Currency, Price, TaxCode, DiscountRate, NetValue]
```

#### Dynamic Field Control（动态字段控制）

字段的显示/隐藏/只读取决于数据状态：

| 类型 | 实现方式 | 示例 |
|------|---------|------|
| 静态隐藏 | `@UI.hidden: true` | 始终不可见 |
| 动态隐藏 | `@UI.hidden: #(IsActiveEntity)` | 新建时可见，保存后隐藏 |
| 动态只读 | `field ( readonly:update ) Price` | 编辑时才只读 |

#### Progressive Disclosure（渐进式披露）

SubSection 支持 `isPartOfPreview` 属性，核心字段默认展示，次要字段通过 "Show All / Show Less" 按钮折叠/展开。

#### Nested Tabs（嵌套标签页）

Section 内部通过 Collection facet 实现二级 Sub-Tab，支持 Expand 按钮展示下拉子标签列表。

#### Connected Fields（关联字段）

语义连接的字段合并到一个标签下（如：运单号 / 预计到达）。

#### Extension Points（扩展点）

SAP 提供两种扩展机制：
- **Custom Section**：预留插槽，完全由开发者编写自定义 UI5 组件
- **Custom Field Renderer**：某个字段用自定义组件渲染（如把"审批进度"渲染成时间轴）

---

### Salesforce Lightning：Dynamic Forms

Salesforce 的方案偏向**低代码用户自助配置**。

#### 核心设计

将传统"Details"单体大块拆分为独立的 **Field Section 组件**，每个 Section 是一个可视容器。

#### 条件可见性规则（Visibility Rules）

| 条件类型 | 示例 |
|---------|------|
| 字段值 | `Active = Yes` 时显示 SLA 字段 |
| 用户画像 | 只有"管理员"可见敏感字段 |
| 记录类型 | 不同记录类型显示不同字段集 |
| 设备类型 | 手机隐藏复杂字段 |
| 多条件组合 | `(角色=销售 AND 金额>100万) OR (角色=管理者)` |

#### Custom Components Slot

标准区域与 Custom LWC Component 可以混排在同一页面的不同位置。

---

### 方案对比总结

| 维度 | SAP Fiori | Salesforce | YonDesign 采纳 |
|------|----------|-----------|----------------|
| 分组方式 | Section > SubSection > FieldGroup 三级 | Field Section 一级分组 + Tab | 采纳 SAP 三级体系 |
| 导航方式 | Anchor Bar / Tab Bar | Tab + Accordion | 两者可选，Tab 适用独立主题 |
| 字段隐藏 | @UI.hidden 注解（静态+动态） | Visibility Rules（多条件） | 采纳两者优点 |
| 渐进披露 | isPartOfPreview（Show All） | Accordion 折叠 | 采纳 SAP 模式 |
| Display/Edit 切换 | SmartForm 自动切换 | 不支持原生 | 采纳 SAP 模式 |
| Connected Fields | 支持（合并标签） | 不支持原生 | 采纳 |
| 响应式 | L4/M4/S4 栅格 | 设备类型可见性 | 采纳 SAP 栅格 |
| 扩展定制 | Custom Section + Custom Renderer | Custom LWC Slot | 采纳 Slot 插槽模式 |
| 单一事实源 | CDS View 注解 | Object Manager | 采纳 Schema 层 |

---

## 复杂对象表单方案

### 设计目标

处理 **20+ 属性对象**，确保：
- 信息架构清晰，不造成认知负担
- 支持不同复杂度的定制需求（从纯 YAML 到完全自定义）
- Schema 层作为单一事实来源，避免字段定义重复

### 方案一：MetaDetailPage 复合表单

```
┌─────────────────────────────────────────────────────────────┐
│  MetaDetailPage（对象详情页）                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [基本信息]  [技术参数]  [商务条款]  [合规审查]  [附件]    │  ← Tab/Anchor Bar
│                                                             │
│  ┌─ FieldGroup: 标识信息 ───────────────────────────────┐  │
│  │  名称    │ 编码    │ 类型    │ 状态                  │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─ FieldGroup: 组织信息 ───────────────────────────────┐  │
│  │  部门    │ 负责人  │ 创建时间 │ 生效日期             │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─ 扩展属性（渐进式披露）─────────────────────┐            │
│  │  描述 │ 备注 │ 标签 │ 版本 │ 审批人 │ 来源  │            │
│  └──────────────────────────────────────────────┘            │
│                      [Show All / Show Less]                   │
│                                                             │
│  ┌─ Section: 合规审查 ─ (仅当 riskLevel='high' 时显示) ─┐  │
│  │  审查员 │ 审查日期 │ 审查结果 │ 整改期限              │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### YAML 配置示例

```yaml
detailPage:
  objectType: "product"
  navigation: "tabs"
  
  tabs:
    - key: "basic"
      label: "基本信息"
      fieldGroups:
        - title: "标识信息"
          layout: "grid-4"
          fields: [name, code, type, status]
        - title: "组织信息"
          layout: "grid-4"
          fields: [department, manager, createdAt, effectiveDate]
        - title: "扩展属性"
          collapsed: true
          collapseLabel: "更多信息"
          layout: "grid-4"
          fields: [description, tags, version, approver, source, priority]
          
    - key: "compliance"
      label: "合规审查"
      visibleWhen:
        field: "riskLevel"
        operator: "equals"
        value: "high"
      fieldGroups:
        - title: "审查信息"
          layout: "grid-4"
          fields: [reviewer, reviewDate, reviewResult, rectifyDeadline]
```

---

### 方案二：Custom Slot 机制（复杂定制场景）

YAML 声明式配置能解决 80% 的标准场景，但以下场景需要定制：

| 场景 | 举例 | 为何 YAML 不够 |
|------|------|---------------|
| 交互式计算 | 报价单实时计算总价 | 跨字段联动计算 |
| 可视化嵌入 | 供应商质量趋势图 | 需嵌入 ECharts |
| 外部数据联动 | 天眼查企业信息 | 需调用外部 API |
| 复杂拖拽 | 审批流节点排序 | 需自定义拖拽 |
| 跨字段校验 | 生效日期 > 创建日期 | 校验依赖链 |
| 条件链联动 | 选海外供应商 → 海关信息 → 关税计算 | 链式条件联动 |

#### Slot 机制设计

```yaml
detailPage:
  objectType: "product"
  navigation: "tabs"
  
  tabs:
    # 标准 YAML 驱动区域（80% 场景）
    - key: "basic"
      label: "基本信息"
      type: "standard"              # 默认值，可省略
      fieldGroups:
        - title: "标识信息"
          layout: "grid-4"
          fields: [name, code, type]

    # 自定义组件槽位（复杂定制）
    - key: "pricing"
      label: "价格计算"
      type: "custom"
      component: "ProductPricingCalculator"
      props:
        currencyField: "currency"
        basePriceField: "basePrice"

    # 混合模式：标准字段 + 自定义渲染器
    - key: "compliance"
      label: "合规审查"
      type: "standard"
      fieldGroups:
        - title: "审查信息"
          layout: "grid-4"
          fields:
            - key: "reviewStatus"
            - key: "approvalProgress"
              renderer: "ApprovalTimeline"     # 自定义渲染器
              rendererProps:
                nodeField: "approvalNodes"
            - key: "riskLevel"
              visibleWhen:
                field: "reviewStatus"
                operator: "equals"
                value: "completed"

    # 完整自定义 Tab
    - key: "analytics"
      label: "数据分析"
      type: "custom"
      component: "SupplierAnalyticsDashboard"
      props:
        supplierId: "{id}"           # 模板变量，运行时替换
```

#### 两种区域共存机制

```
┌──────────────────────────────────────────────────────────┐
│           DetailPage 的两种区域共存机制                     │
├──────────────────────────────────────────────────────────┤
│                                                          │
│   Standard 区域（YAML 驱动）     Custom 区域（定制）        │
│  ┌─────────────────────┐   ┌─────────────────────────┐  │
│  │ fields + fieldGroups│   │ <slot name="pricing">   │  │
│  │ 自动渲染            │   │   <PricingCalculator /> │  │
│  │ 自动校验            │   │ </slot>                 │  │
│  │ 自动布局            │   │                         │  │
│  └─────────────────────┘   │ 开发者完全控制           │  │
│           │                │ 但接收统一数据 context   │  │
│           └────────┬───────┘                         │  │
│                    ▼                                  │  │
│         统一的数据 Context（formData, objectId, mode）  │  │
│         共享同一个数据源，保持数据一致性                 │  │
└──────────────────────────────────────────────────────────┘
```

---

### 方案三：单一事实来源（Single Source of Truth）

#### 问题本质

字段属性（type、label、validations）如果在列表页、详情页、表单页各自重复定义，将导致：
- 修改字段类型时需同步多处
- 校验规则不一致
- 枚举值不统一

#### 三层字段定义体系

```
┌────────────────────────────────────────────────────────────────┐
│                    单一事实来源：Schema 层                       │
│                   object-definitions/product.yaml               │
├────────────────────────────────────────────────────────────────┤
│  product:                                                      │
│    label: "产品"                                                │
│    fields:                         ← 每个字段只在这里定义一次   │
│      name:                                                      │
│        label: "产品名称"                                        │
│        type: "text"                                             │
│        dbType: "varchar(100)"                                   │
│        required: true                                           │
│        validations:                                             │
│          - rule: "maxLength"                                    │
│            value: 100                                           │
│      status:                                                    │
│        label: "状态"                                            │
│        type: "select"                                           │
│        options:                                                 │
│          - { value: "active", label: "活跃" }                   │
│          - { value: "inactive", label: "停用" }                 │
│        defaultValue: "active"                                   │
│      riskLevel:                                                 │
│        label: "风险等级"                                        │
│        type: "select"                                           │
│        visibleWhen: "{status} == 'active'" ← 条件可见性在Schema│
└────────────────────────────────────────────────────────────────┘
                              │
                              │ 引用（不是重新定义）
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│               页面配置层（只描述"展示行为"）                      │
│                 page-definitions/product-list.yaml                │
├─────────────────────────────────────────────────────────────────┤
│  listPage:                                                      │
│    objectType: "product"            ← 关联到 Schema              │
│    columns:                         ← 只指定顺序和看覆盖展示属性  │
│      - field: "name"               ← 引用 Schema 中的 name      │
│        width: 200                   ← 列表特有的宽度             │
│        sortable: true               ← 列表特有的排序             │
│      - field: "status"                                          │
│        renderAs: "tag"              ← 列表中渲染为标签          │
└─────────────────────────────────────────────────────────────────┘
```

#### 运行时合并规则

```
优先级（低 → 高）：
  1. Schema 默认值       （type, required, validations, options）
  2. 页面配置覆盖值       （width, sortable, renderAs, label override）
  3. 运行时计算值         （visibleWhen, readonlyWhen）

禁止覆盖（来自 Schema，页面不能改）：
  - type        → 字段类型
  - validations → 校验规则
  - dbType      → 数据库类型
  - unique      → 唯一性

允许覆盖（页面可以定制）：
  - label       → 标签文本
  - width       → 列宽
  - sortable    → 是否可排序
  - renderAs    → 渲染方式
  - visibleWhen → 可见条件
  - readonlyWhen→ 只读条件
```

---

## 总结

### 核心设计原则

1. **语义分组优先**（SAP FieldGroup）：不平铺 20 个字段，按业务语义归类分组
2. **三级容器体系**（SAP Section/SubSection）：Section > FieldGroup > Field
3. **渐进式披露**（SAP isPartOfPreview）：核心默认展示，次要折叠
4. **条件可见性**（Salesforce Visibility Rules）：字段取决于数据和角色
5. **Tab vs Anchor 选择**：独立主题用 Tab，连续阅读用 Anchor
6. **Connected Fields**（SAP）：关联字段合并标签，减少视觉噪音
7. **Slot 插槽**：80% YAML 驱动 + 20% 自定义组件混排
8. **Schema 单一事实源**：字段定义一次，页面仅声明展示行为

### 建议的组件体系

```
┌─────────────────────────────────────────────────────────────┐
│                   页面组件层（Page Layer）                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  MetaListPage      → 通用列表页（YAML 驱动）               │
│  MetaTreePage       → 树形列表页（YAML 驱动）【NEW】        │
│  MetaDetailPage     → 复合详情页（YAML/Slot 双模式）【NEW】 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   业务组件层（Business Layer）                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  AssociationManager   → 关联管理器【NEW】                    │
│  RolePermissionPanel → 角色权限面板【NEW】                   │
│  FieldGroup           → 字段分组容器【NEW】                   │
│  MetaTable           → 业务表格                             │
│  MetaForm            → 业务表单                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

### Element Plus 相关组件

- `el-tree` - 树形控件
- `el-table` - 表格
- `el-transfer` - 穿梭框
- `el-drawer` - 抽屉
- `el-tabs` - 标签页

### 行业参考

- [SAP Fiori Object Page](https://experience.sap.com/fiori-design-web/object-page/) - SAP 旗舰对象展示方案
- [Salesforce Dynamic Forms](https://help.salesforce.com/s/articleView?id=platform.dynamic_forms.htm) - 低代码动态表单
- [Ant Design Pro](https://pro.ant.design/) - 企业级中台前端
- [Progressive Disclosure Pattern](https://www.nngroup.com/articles/progressive-disclosure/) - Nielsen Norman Group

---

**【下一步】**
1. 实现 MetaDetailPage 组件（YAML + Slot 双模式）
2. 实现 FieldGroup 分组容器组件
3. 实现 Schema 层与页面配置层的合并引擎
4. 在 component-comparison 页面增加交互式演示
