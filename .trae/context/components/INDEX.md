# Components Context 注册表 (INDEX)

> **最后更新**: 2026-06-13
> **总数**: 110+ Vue components(本批次 Context 覆盖 55 个关键组件)
> **覆盖策略**: 按 TBD-5 全量覆盖,分批进行
> **覆盖率**: ~50%(55/110+)
> **规范**: 每个 Context doc 遵循 [.trae/context/_TEMPLATE.md](../_TEMPLATE.md) 7 节 Schema

## 注册表

### P0 - 应用主框架(5)

| ID | Component | 职责 | YonDesign | 测试 | Context |
|----|-----------|------|-----------|------|---------|
| CMP-001 | AADiagramApp | 主应用框架(架构图) | - | ⚠️ 0% | [OK] |
| CMP-002 | ConfigApp | 主应用框架(配置) | - | ⚠️ 0% | [OK] |
| CMP-003 | AppShell | 应用 Shell(顶栏+侧栏) | [OK] | ⚠️ 0% | [OK] |
| CMP-004 | AppLayout | 应用 Layout | [OK] | ⚠️ 0% | [OK] |
| CMP-005 | AppRootLayout | 根布局 | [OK] | ⚠️ 0% | [OK] |

### P0 - 元数据核心(5)

| ID | Component | 职责 | YonDesign | 测试 | Context |
|----|-----------|------|-----------|------|---------|
| CMP-006 | MetaTable | 元数据表格 | - | ⚠️ 0% | [OK] |
| CMP-007 | MetaForm | 元数据表单 | - | ⚠️ 0% | [OK] |
| CMP-008 | MetaDialog | 元数据对话框 | - | ⚠️ 0% | [OK] |
| CMP-009 | MetaListPage | 元数据列表页 | - | ⚠️ 0% | [OK] |
| CMP-010 | MetaListV2 | 元数据列表 v2 | - | ⚠️ 0% | [OK] |

### P0 - 图与视图(4)

| ID | Component | 职责 | YonDesign | 测试 | Context |
|----|-----------|------|-----------|------|---------|
| CMP-011 | MermaidComponent | Mermaid 图渲染 | - | ⚠️ 0% | [OK] |
| CMP-012 | ArchWorkspaceNew | 架构工作区 | - | ⚠️ 0% | [OK] |
| CMP-013 | LoginPage | 登录页 | - | ⚠️ 0% | [OK] |
| CMP-014 | ValidationPanel | 校验面板 | - | ⚠️ 0% | [OK] |

### P0 - ObjectPage 系列(8)

| ID | Component | 职责 | YonDesign | 测试 | Context |
|----|-----------|------|-----------|------|---------|
| CMP-015 | ObjectPage | 对象详情页 | - | ⚠️ 0% | [OK] |
| CMP-016 | ObjectPageShell | ObjectPage Shell | - | ⚠️ 0% | [OK] |
| CMP-017 | ObjectPageHeader | 头部 | - | ⚠️ 0% | [OK] |
| CMP-018 | ObjectPageContent | 内容区 | - | ⚠️ 0% | [OK] |
| CMP-019 | ObjectPageField | 字段 | - | ⚠️ 0% | [OK] |
| CMP-020 | FieldGroupSection | 字段分组 | - | ⚠️ 0% | [OK] |
| CMP-021 | AssociationSection | 关联项 | - | ⚠️ 0% | [OK] |
| CMP-022 | HistorySection | 历史 | - | ⚠️ 0% | [OK] |

### P1 - DetailPage + 子组件(3)

| ID | Component | 职责 | YonDesign | 测试 | Context |
|----|-----------|------|-----------|------|---------|
| CMP-023 | DetailPage | 详情页标准 | - | ⚠️ 0% | [OK] |
| CMP-024 | DetailSection | 详情分区 | - | ⚠️ 0% | [OK] |
| CMP-025 | DetailPageAssociationSection | 详情关联 | - | ⚠️ 0% | [OK] |

### P1 - MetaListPage 子组件(4)

| ID | Component | 职责 | YonDesign | 测试 | Context |
|----|-----------|------|-----------|------|---------|
| CMP-026 | InlineEditCell | 内联编辑单元 | - | ⚠️ 0% | [OK] |
| CMP-027 | InlineEditToolbar | 编辑工具栏 | - | ⚠️ 0% | [OK] |
| CMP-028 | AssociationNavigationMenu | 关联导航 | - | ⚠️ 0% | [OK] |
| CMP-029 | NavigationSourceInfo | 来源信息 | - | ⚠️ 0% | [OK] |

### P0 - RelationScopeTree 系列(4) + FilterBar(1)

| ID | Component | 职责 | YonDesign | 测试 | Context |
|----|-----------|------|-----------|------|---------|
| CMP-030 | RelationScopeTree | 关系域树 | - | ⚠️ 0% | [OK] |
| CMP-031 | RelationScopeSection | 关系分区 | - | ⚠️ 0% | [OK] |
| CMP-032 | ObjectScopeSection | 对象分区 | - | ⚠️ 0% | [OK] |
| CMP-033 | RelationFilterSection | 关系过滤 | - | ⚠️ 0% | [OK] |
| CMP-034 | FilterBar | 筛选条 | - | ⚠️ 0% | [OK] |

### P1 - YonDesign 基础组件(11)

| ID | Component | 职责 | YonDesign | 测试 | Context |
|----|-----------|------|-----------|------|---------|
| CMP-035 | AppButton | 按钮 | [OK] | ⚠️ 0% | [OK] |
| CMP-036 | AppInput | 输入框 | [OK] | ⚠️ 0% | [OK] |
| CMP-037 | AppSelect | 选择器 | [OK] | ⚠️ 0% | [OK] |
| CMP-038 | AppModal | 模态框 | [OK] | ⚠️ 0% | [OK] |
| CMP-039 | AppCard | 卡片 | [OK] | ⚠️ 0% | [OK] |
| CMP-040 | AppAlert | 警告 | [OK] | ⚠️ 0% | [OK] |
| CMP-041 | AppIcon | 图标 | [OK] | ⚠️ 0% | [OK] |
| CMP-042 | AppCollapse | 折叠面板 | [OK] | ⚠️ 0% | [OK] |
| CMP-043 | AppDatePicker | 日期选择 | [OK] | ⚠️ 0% | [OK] |
| CMP-044 | AppHeader | 顶栏 | [OK] | ⚠️ 0% | [OK] |
| CMP-045 | AppSideNav | 侧栏导航 | [OK] | ⚠️ 0% | [OK] |

### P1 - 常见领域组件(5)

| ID | Component | 职责 | YonDesign | 测试 | Context |
|----|-----------|------|-----------|------|---------|
| CMP-046 | ValueHelpField | 值帮助字段 | - | ⚠️ 0% | [OK] |
| CMP-047 | EnumSelect | 枚举选择器 | - | ⚠️ 0% | [OK] |
| CMP-048 | EnumSearchHelp | 枚举搜索帮助 | - | ⚠️ 0% | [OK] |
| CMP-049 | EmptyState | 空状态 | [OK] | ⚠️ 0% | [OK] |
| CMP-050 | ErrorBoundary | 错误边界 | [OK] | ⚠️ 0% | [OK] |

### P1 - Dialog + Picker 系列(7)

| ID | Component | 职责 | YonDesign | 测试 | Context |
|----|-----------|------|-----------|------|---------|
| CMP-051 | SearchHelpDialog | 搜索帮助对话框 | - | ⚠️ 0% | [OK] |
| CMP-052 | ImportDialog | 导入对话框 | - | ⚠️ 0% | [OK] |
| CMP-053 | ExportDialog | 导出对话框 | - | ⚠️ 0% | [OK] |
| CMP-054 | AssignmentDialog | 分配对话框 | - | ⚠️ 0% | [OK] |
| CMP-055 | ConditionRuleEditor | 条件规则编辑器 | - | ⚠️ 0% | [OK] |
| CMP-056 | ValueHelpSelector | 值帮助选择器 | - | ⚠️ 0% | [OK] |
| CMP-057 | TableHeaderFilter | 表头筛选 | - | ⚠️ 0% | [OK] |

### P2 - BO 组件(2)

| ID | Component | 职责 | YonDesign | 测试 | Context |
|----|-----------|------|-----------|------|---------|
| CMP-058 | ActionExecutor | 动作执行器 | - | ⚠️ 0% | [OK] |
| CMP-059 | StateTransitionButton(s) | 状态流转按钮 | - | ⚠️ 0% | [OK] |
| CMP-060 | AssociationCell | 关联单元格 | - | ⚠️ 0% | [OK] |
| CMP-061 | AssociationSelector | 关联选择器 | - | ⚠️ 0% | [OK] |

### P2 - 业务组件(8)

| ID | Component | 职责 | YonDesign | 测试 | Context |
|----|-----------|------|-----------|------|---------|
| CMP-062 | FeishuDataImport | 飞书数据导入 | - | ⚠️ 0% | [OK] |
| CMP-063 | ServiceModuleConfig | 服务模块配置 | - | ⚠️ 0% | [OK] |
| CMP-064 | MultiObjectManagementPage | 多对象管理 | - | ⚠️ 0% | [OK] |
| CMP-065 | CenterDomainSelect | 中心域选择 | - | ⚠️ 0% | [OK] |
| CMP-066 | StatsOverview | 统计概览 | - | ⚠️ 0% | [OK] |
| CMP-067 | FeishuBotPanel | 飞书机器人 | - | ⚠️ 0% | [OK] |
| CMP-068 | DataPreview | 数据预览 | - | ⚠️ 0% | [OK] |
| CMP-069 | FileUploader | 文件上传 | - | ⚠️ 0% | [OK] |

### P2 - Utility 组件(7)

| ID | Component | 职责 | YonDesign | 测试 | Context |
|----|-----------|------|-----------|------|---------|
| CMP-070 | GlobalSearch | 全局搜索 | [OK] | ⚠️ 0% | [OK] |
| CMP-071 | GlobalToolbar | 全局工具栏 | [OK] | ⚠️ 0% | [OK] |
| CMP-072 | UserMenu | 用户菜单 | [OK] | ⚠️ 0% | [OK] |
| CMP-073 | BreadcrumbNav | 面包屑 | [OK] | ⚠️ 0% | [OK] |
| CMP-074 | AppTabs | Tabs | [OK] | ⚠️ 0% | [OK] |
| CMP-075 | NotificationContainer | 通知容器 | - | ⚠️ 0% | [OK] |
| CMP-076 | Drawer | 抽屉 | [OK] | ⚠️ 0% | [OK] |
| CMP-077 | ConfirmDialog | 确认对话框 | [OK] | ⚠️ 0% | [OK] |

---

## 覆盖率统计

- **已 Context 化**: 77 个(本批次完成)
- **未 Context 化**: ~33 个(子组件/特殊场景)
- **覆盖率**: ~70%

## 待补充(后续批次)

> 剩余 ~33 个 Vue components:
> - SubNavTabs, SubNavTabs, MasterDetailLayout, CollapsiblePanel
> - FkLinkField, FilterVariantSelector, EmptyState(已加)
> - CenterScopeSelector, ScopeSelector, TreeNode
> - RelationCategoryTree, RelationCategoryNode
> - FrequentProductsSection
> - Pagination, AppTabs(已加), AppDatePicker(已加), AppInput(已加), TableHeaderFilter(已加)
> - AccountSettingsDialog, ChangePasswordDialog
> - ObjectChildSection, ObjectPageWithChildren
> - DateTimePicker, ImpactPreview, ManagementDimensionSelector
> - MasterDetailLayout
> - NotificationContainer(已加), SubNavTabs

## 维护规则

- 新增 component 时,在此 INDEX 追加一行
- 标注是否 YonDesign 体系组件
- 标注当前测试覆盖现状

## 相关链接

- [.trae/context/_TEMPLATE.md](../_TEMPLATE.md) — 通用模板
- [.trae/skills/test-gen/SKILL.md](../../skills/test-gen/SKILL.md) — Vue 测试生成 Skill
- [.trae/skills/CHANGELOG.md](../../skills/CHANGELOG.md) — 变更日志