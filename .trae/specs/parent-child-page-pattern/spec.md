# Spec: 标准化父子页面模式 (Parent-Child Page Pattern)

## 1. Background & Objectives

### 1.1 Background

当前项目中存在多种父子关系数据的管理页面，但缺乏统一的标准化模式：

- **产品-版本** (`ProductVersionApp`): 使用自定义的左侧产品列表 + 右侧版本表格布局，未复用 `MetaListPage`/`ObjectPage`
- **枚举类型-枚举值** (`EnumTypeDetail`): 使用 `ObjectPage` + `MetaListPage` slot 内嵌子列表，但子列表的 `initial-filters` 和面包屑需要手动配置
- **领域-子领域-服务模块-业务对象** (`DomainManagement`): 使用 `MasterDetailLayout` + 树形导航 + `MetaListPage`，代码在4个文件中大量重复
- **角色-权限** (`RoleDetailDrawer`): 完全自定义详情页，不使用 `DetailPage`

这些页面各自实现了相似的父子关系逻辑（过滤、面包屑、返回导航、子对象创建），导致：
1. 代码重复（`HIERARCHY_MAP` 在多个文件中重复定义）
2. 用户体验不一致（有的用 Drawer，有的用路由跳转，有的用内嵌表格）
3. 新增父子关系页面成本高（需要从头写页面组件）
4. YAML Schema 中的 `parent_object` 和 `relations` 配置未被前端自动消费

### 1.2 Business Objectives

- **标准化**: 建立统一的父子页面模式，所有父子关系页面遵循相同的设计规范
- **可配置化**: 通过 YAML Schema 配置驱动父子页面渲染，减少硬编码
- **低代码**: 新增父子关系页面时，只需配置 YAML，无需编写页面组件
- **一致性**: 确保所有父子页面的交互模式、视觉风格、路由行为一致

### 1.3 User / Stakeholder Objectives

- **终端用户**: 在不同父子关系页面间获得一致的浏览和操作体验
- **前端开发者**: 新增父子页面时，复用标准化组件而非从头开发
- **架构师**: 通过 YAML 配置即可定义新的父子关系页面，无需修改前端代码

---

## 2. Requirement Type Overview

| Type | Applicable | Evidence |
|------|-----------|----------|
| Business | Yes | 减少页面开发成本，提升用户体验一致性 |
| User/Stakeholder | Yes | 终端用户、前端开发者、架构师 |
| Solution | Yes | 新增 `useParentChild` composable + `ChildListSection` 组件 |
| Functional | Yes | FR-001 ~ FR-012 |
| Nonfunctional | Yes | NFR-001 ~ NFR-004 |
| External Interface | Yes | YAML Schema 扩展、路由约定 |
| Transition | Yes | 现有页面逐步迁移到新模式 |

---

## 3. Functional Requirements

### FR-001: YAML 驱动的父子关系声明

- **Description**: YAML Schema 支持声明 `parent_object` 和 `child_objects` 配置，前端自动识别父子关系
- **Acceptance Criteria**:
  - `version.yaml` 中 `parent_object: product` 被前端自动消费
  - 支持 `child_objects` 列表声明多个子对象类型
  - 前端通过 `metaService` 获取父子关系配置
- **Priority**: Must
- **Type**: Solution

### FR-002: 标准化的子列表内嵌展示 (ObjectPage Section)

- **Description**: 父对象详情页 (`ObjectPage`) 支持通过 `display: 'always'` 的 section 自动渲染子列表
- **Acceptance Criteria**:
  - `ObjectPage` 的 `alwaysVisibleSections` 支持 `type: 'child_list'` 自动渲染 `MetaListPage`
  - 子列表自动注入 `initial-filters`（如 `{ product_id: parentId }`）
  - 子