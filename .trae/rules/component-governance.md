# 组件治理规范 (Component Governance)

## [CLIPBOARD] 文档信息
- **版本**: v1.0.0
- **创建日期**: 2026-05-08
- **适用范围**: `src/components/common/` 目录下的所有公共组件
- **维护者**: 架构团队 + 前端开发团队

---

## [TARGET] 核心原则

### 1. 单一职责原则 (Single Responsibility)
每个组件应该有明确、单一的职责范围。避免创建功能重叠的组件。

**[OK] 正确示例:**
- `FilterBar` - 统一的过滤栏组件（支持搜索、选择、日期范围、多选）
- `MetaTable` - 元数据驱动的表格组件
- `AppModal` - 通用的模态框组件

**[X] 错误示例:**
- `SmartFilterBar` - 与 FilterBar 功能重叠 [X] 已删除
- `DynamicFilters` - 与 FilterBar 功能重叠 [X] 已弃用

### 2. 组件分层架构

```
src/components/
├── common/                    # 公共组件库（标准化）
│   ├── FilterBar/            # [OK] 推荐使用
│   │   ├── FilterBar.vue
│   │   └── index.js
│   ├── AppButton/            # 基础UI组件
│   ├── AppInput/
│   ├── AppSelect/
│   ├── AppModal/
│   ├── MetaTable/            # 业务组件
│   ├── MetaForm/
│   └── DynamicFilters.vue    # [WARNING] 已弃用（v2.0.0 移除）
├── business/                  # 特定业务组件
└── features/                  # 功能模块组件
```

### 3. 命名规范

#### 组件命名
- **格式**: PascalCase + 语义化后缀
- **示例**: `FilterBar`, `AppButton`, `MetaTable`, `AuditLog`

#### 目录结构
- **推荐**: 每个组件独立目录，包含 `.vue` 文件和 `index.js`
- **示例**:
  ```
  FilterBar/
  ├── FilterBar.vue      # 主组件
  ├── index.js           # 导出文件
  └── README.md          # 使用文档（可选）
  ```

#### Props 命名
- 使用 camelCase
- 语义化命名：`fields`, `modelValue`, `showReset`

---

## [PACKAGE] 组件分类与职责

### A. 基础 UI 组件 (Foundation Components)
提供原子级别的UI构建块。

| 组件名 | 职责 | 状态 |
|--------|------|------|
| AppButton | 按钮控件 | [OK] 稳定 |
| AppInput | 输入框控件 | [OK] 稳定 |
| AppSelect | 选择器控件 | [OK] 稳定 |
| AppCard | 卡片容器 | [OK] 稳定 |
| AppModal | 模态对话框 | [OK] 稳定 |
| AppTabs | 标签页切换（支持多页面管理） | [OK] 稳定 |
| AppSideNav | 侧边导航 | [OK] 稳定 |
| Pagination | 分页控件 | [OK] 稳定 |
| Drawer | 抽屉面板 | [OK] 稳定 |
| AppIcon | 图标组件 | [OK] 稳定 |
| AppAlert | 提示信息 | [OK] 稳定 |
| AppCollapse | 折叠面板 | [OK] 稳定 |

### A+. 顶部导航系统 (Navigation System Components) **[NEW]**
全局导航和布局容器，参考 SAP Fiori / Salesforce / D365 设计模式。

> **文档**: [API 文档](file:///d:/filework/excel-to-diagram/docs/architecture/14-top-navigation-components-api.md)
>
> **使用示例**: [完整示例](file:///d:/filework/excel-to-diagram/docs/architecture/15-component-library-examples.md)

| 组件名 | 职责 | 文件路径 | 状态 |
|--------|------|---------|------|
| **AppShell** | **全局应用容器（Header+Tabs+Sidebar+Content）** | `AppShell/AppShell.vue` | [OK] **已完成** |
| **AppTabs** | **多页面 Tab 管理（最多8-10个，溢出菜单）** | `AppTabs/AppTabs.vue` | [OK] **已完成** |
| **BreadcrumbNav** | **面包屑导航（支持省略号、路由跳转）** | `BreadcrumbNav/BreadcrumbNav.vue` | [OK] **已完成** |
| **UserMenu** | **用户下拉菜单（头像+角色+操作项）** | `UserMenu/UserMenu.vue` | [OK] **已完成** |
| **GlobalSearch** | **全局搜索（Ctrl+K快捷键、建议列表）** | `GlobalSearch/GlobalSearch.vue` | [OK] **已完成** |
| **PageHeader** | **页面标题栏（返回按钮+标题+操作区）** | `AppHeader.vue` | [OK] **已完成** |

### B. 复合业务组件 (Composite Business Components)
基于基础组件构建的业务级组件。

| 组件名 | 职责 | 状态 |
|--------|------|------|
| **FilterBar** | **统一过滤栏（支持多种字段类型）** | [OK] **推荐** |
| MetaTable | 元数据驱动表格 | [OK] 稳定 |
| MetaForm | 元数据驱动表单 | [OK] 稳定 |
| MetaDialog | 元数据驱动对话框 | [OK] 稳定 |
| EnumSelect | 枚举选择器 | [OK] 稳定 |
| AuditLog | 审计日志展示 | [OK] 稳定 |
| MasterDetailLayout | 主从布局 | [OK] 稳定 |
| AppHeader | 应用头部 | [OK] 稳定 |
| ConfirmDialog | 确认对话框 | [OK] 稳定 |
| EmptyState | 空状态展示 | [OK] 稳定 |

### C. 已弃用组件 (Deprecated Components)
标记为弃用，将在未来版本移除。

| 组件名 | 弃用原因 | 替代方案 | 计划移除版本 |
|--------|----------|----------|--------------|
| DynamicFilters | 与 FilterBar 功能重叠 | FilterBar | v2.0.0 |
| SmartFilterBar | 与 FilterBar 功能重叠 | FilterBar | v1.9.0 [OK] 已删除 |

---

## [TOOL] FilterBar 组件详细规范

### 为什么选择 FilterBar 作为标准？

1. **功能完整性**: 支持所有常见的过滤场景
2. **可扩展性**: 易于添加新的字段类型
3. **一致性**: 统一的交互模式和视觉样式
4. **性能优化**: 内置防抖和懒加载机制

### 支持的字段类型

```javascript
const filterFields = [
  {
    key: 'name',
    label: '名称',
    type: 'search',        // 搜索输入框
    placeholder: '请输入名称'
  },
  {
    key: 'status',
    label: '状态',
    type: 'select',        // 单选下拉框
    options: [
      { value: 'active', label: '启用' },
      { value: 'inactive', label: '禁用' }
    ]
  },
  {
    key: 'dateRange',
    label: '创建日期',
    type: 'date-range',   // 日期范围选择
    placeholder: ['开始日期', '结束日期']
  },
  {
    key: 'categories',
    label: '分类',
    type: 'multi-select',  // 多选下拉框（带全选/清空）
    options: [
      { value: 'cat1', label: '分类1' },
      { value: 'cat2', label: '分类2' }
    ]
  }
]
```

### 使用示例

```vue
<template>
  <FilterBar
    :fields="filterableFields"
    v-model="filters"
    :show-reset="true"
    @search="handleSearch"
    @reset="handleReset"
  />
</template>

<script setup>
import { ref } from 'vue'
import { FilterBar } from '@/components/common/FilterBar'

const filters = ref({})

const filterableFields = [
  {
    key: 'keyword',
    label: '关键词',
    type: 'search',
    placeholder: '请输入关键词'
  },
  {
    key: 'status',
    label: '状态',
    type: 'select',
    options: [
      { value: 'all', label: '全部' },
      { value: 'active', label: '启用' },
      { value: 'inactive', label: '禁用' }
    ]
  }
]

function handleSearch(params) {
  console.log('搜索参数:', params)
}

function handleReset() {
  console.log('已重置')
}
</script>
```

---

## [FORBID] 组件治理规则

### 规则 1: 禁止创建重复功能组件

在创建新组件之前，必须检查现有组件是否已经满足需求。

**检查清单:**
- [ ] 查看 `src/components/common/` 目录
- [ ] 阅读 [Component Patterns](../context/developer/component-patterns.md)
- [ ] 确认没有功能重叠的现有组件
- [ ] 如果现有组件可以扩展，优先扩展现有组件而非创建新组件

### 规则 2: 新组件必须通过评审

新组件的创建需要经过以下流程：

1. **需求分析**: 明确组件的职责边界
2. **设计评审**: 确认与现有组件无冲突
3. **实现开发**: 遵循代码规范
4. **测试验证**: 包含单元测试和集成测试
5. **文档编写**: 提供 README 和 API 文档
6. **集成导出**: 在 `index.js` 中正确导出

### 规则 3: 弃用流程

当组件需要弃用时：

1. **标记弃用**: 添加 `@deprecated` 注释
2. **控制台警告**: 运行时输出弃用警告
3. **迁移指南**: 提供替代方案和迁移路径
4. **更新文档**: 在本文档中记录弃用信息
5. **计划移除**: 设定移除版本号
6. **最终删除**: 到达计划版本时删除代码

---

## [CHART] 组件使用统计与监控

### 当前组件使用情况

#### 推荐使用的组件（2026-05-08）

| 组件名 | 使用页面数 | 覆盖率 | 趋势 |
|--------|------------|--------|------|
| FilterBar | 8+ 页面 | 85% | [TREND_UP] 增长中 |
| MetaTable | 12+ 页面 | 95% | [TREND_UP] 稳定 |
| AppModal | 15+ 页面 | 98% | [TREND_UP] 稳定 |
| AuditLog | 3 页面 | 新增 | 🆕 刚上线 |

#### 已弃用组件迁移进度

| 组件名 | 原使用数 | 已迁移数 | 迁移率 | 状态 |
|--------|----------|----------|--------|------|
| SmartFilterBar | 2 | 2 | 100% | [OK] 已完成并删除 |
| DynamicFilters | 1 | 1 | 100% | [OK] 已迁移，待删除 |

---

## [REFRESH] 迁移指南

### 从 DynamicFilters 迁移到 FilterBar

**步骤 1: 更新导入**
```javascript
// [X] 旧代码
import DynamicFilters from '@/components/common/DynamicFilters.vue'

// [OK] 新代码
import { FilterBar } from '@/components/common/FilterBar'
```

**步骤 2: 转换字段配置**
```javascript
// [X] DynamicFilters 格式
const fields = [
  {
    id: 'name',
    name: 'name',
    label: '名称',
    type: 'text',
    placeholder: '请输入名称'
  }
]

// [OK] FilterBar 格式
const fields = [
  {
    key: 'name',
    label: '名称',
    type: 'search',
    placeholder: '请输入名称'
  }
]
```

**步骤 3: 更新模板**
```vue
<!-- [X] 旧模板 -->
<DynamicFilters
  :fields="fields"
  v-model="filterValues"
  @change="handleFilterChange"
/>

<!-- [OK] 新模板 -->
<FilterBar
  :fields="fields"
  v-model="filters"
  :show-reset="true"
  @search="handleSearch"
  @reset="handleReset"
/>
```

---

## [DESIGN] 设计一致性要求

### 间距规范
参考 [UI Design Standards](../context/developer/ui-design-standards.md)：
- 组件间距: `--spacing-xs` (4px), `--spacing-sm` (8px), `--spacing-md` (16px), `--spacing-lg` (24px)
- 内容区 padding: 24px
- 卡片内边距: 20px

### 字体规范
- 标题: `--font-size-lg` (18px)
- 正文: `--font-size-base` (14px)
- 辅助文字: `--font-size-sm` (12px)
- 小字: `--font-size-xs` (11px)

### 颜色规范
- 主色: `--color-primary` (#1890ff)
- 成功色: `--color-success` (#52c41a)
- 警告色: `--color-warning` #faad14)
- 错误色: `--color-error` (#ff4d4f)

---

## [NOTE] 开发工作流

### 创建新组件 Checklist

- [ ] 确认现有组件无法满足需求
- [ ] 编写组件设计文档
- [ ] 实现组件代码（遵循 Vue 3 Composition API）
- [ ] 编写单元测试（覆盖率 > 80%）
- [ ] 添加 TypeScript 类型定义（如果使用 TS）
- [ ] 编写 README 文档
- [ ] 在 `index.js` 中导出
- [ ] 提交 Code Review
- [ ] 合并到主分支

### 修改现有组件 Checklist

- [ ] 分析影响范围（哪些页面使用了该组件）
- [ ] 确保向后兼容（或提供迁移路径）
- [ ] 更新单元测试
- [ ] 更新文档
- [ ] 通知相关开发者
- [ ] 提交 Code Review

---

## [CRYSTAL] 未来规划

### 短期计划 (Q2 2026)
- [x] [OK] 完成 FilterBar 多选功能增强
- [x] [OK] 迁移 ArchDataManageApp 到 FilterBar
- [x] [OK] 删除 SmartFilterBar 组件
- [x] [OK] 标记 DynamicFilters 为弃用
- [ ] 完善 FilterBar 文档和示例
- [ ] 添加 FilterBar 性能监控

### 中期计划 (Q3 2026)
- [ ] 删除 DynamicFilters 组件（v2.0.0）
- [ ] 实现 FilterBar 高级功能（过滤变体保存/加载）
- [ ] 建立 Component Registry（组件注册中心）
- [ ] 引入 Storybook 进行组件可视化测试
- [ ] 建立组件版本管理机制

### 长期计划 (Q4 2026+)
- [ ] 建立组件市场（内部 npm 包）
- [ ] 实现组件自动生成工具
- [ ] 建立组件质量评分系统
- [ ] 跨项目组件共享机制
- [ ] AI 辅助组件推荐系统

---

## [DOC] 相关文档

- [Component Patterns](../context/developer/component-patterns.md) - 组件设计模式
- [UI Design Standards](../context/developer/ui-design-standards.md) - UI 设计规范
- [Coding Standards](../context/developer/coding-standards.md) - 编码规范
- [Engineering Guidelines](./engineering-guidelines.md) - 工程指南

---

# 元数据配置治理规范 (Metadata Configuration Governance)

## [CLIPBOARD] 文档信息
- **版本**: v1.0.0
- **创建日期**: 2026-05-08
- **适用范围**: 所有元数据配置文件（YAML）和相关 API
- **维护者**: 架构团队

---

## [TARGET] 核心原则

### 1. 配置契约明确化

所有元数据配置必须遵循明确的配置契约（Configuration Contract）。

**[OK] 正确做法:**
- 配置前查阅配置契约文档
- 配置时遵循字段类型和约束
- 配置后运行验证工具检查

**[X] 错误做法:**
- 闭着眼睛写配置
- 不验证配置是否有效
- 不查阅文档凭猜测配置

### 2. API 规范统一化

所有 API 必须遵循统一的规范：

| 规范 | 说明 |
|------|------|
| 路径约定 | 使用复数形式 `/enum-types` |
| 响应格式 | `{success, data, message}` |
| 嵌套结构 | 列表数据使用 `data.data` |
| 错误格式 | `{success: false, message, code}` |

**相关文档:**
- [枚举 API 规范](../../docs/api/enum-api.md)
- [跨表过滤配置契约](../../docs/metadata/cross-table-filters.md)

### 3. 验证机制完善化

配置从定义到消费全程可验证。

```javascript
// 使用 ConfigValidator 验证配置
import { ConfigValidator } from '@/utils/configValidator'

const result = ConfigValidator.validateAndLog(
  metaObj.analytical_model?.cross_table_filters,
  'cross_table_filters'
)

// 输出验证日志
// [ConfigValidator] cross_table_filters validation passed
```

### 4. 代码复用最大化

通用逻辑必须封装为可复用服务。

**[OK] 统一枚举加载:**
```javascript
// [X] 错误：重复实现枚举加载
const options = await fetch(`/api/v1/enums/${enumType}`)

// [OK] 正确：使用统一服务
import { EnumService } from '@/services/enumService'
const options = await EnumService.loadOptions(enumType)
```

---

## [PACKAGE] 配置类型与契约文档

### 元模型配置

| 配置类型 | 契约文档 | 说明 |
|----------|----------|------|
| `fields[].semantics` | 元模型设计规范 | 字段语义定义 |
| `ui_view_config` | UI 视图配置规范 | 视图配置 |
| `analytical_model` | 分析模型规范 | 聚合计算 |
| `cross_table_filters` | [跨表过滤配置契约](../../docs/metadata/cross-table-filters.md) | 跨表关联过滤 |

### API 配置

| API 类型 | 规范文档 | 说明 |
|----------|----------|------|
| 枚举相关 API | [枚举 API 规范](../../docs/api/enum-api.md) | enum-types, enum-values |
| 查询相关 API | 查询 API 规范 | query, aggregate |

---

## [TOOL] 配置验证工具

### ConfigValidator

配置验证工具提供运行时验证：

```javascript
import { ConfigValidator } from '@/utils/configValidator'

// 验证跨表过滤配置
ConfigValidator.validateCrossTableFilters(config)
```

**验证规则:**
- 必需字段检查
- 选项来源互斥验证
- 枚举类型存在性检查
- API 端点有效性检查

### EnumService

统一枚举加载服务：

```javascript
import { EnumService } from '@/services/enumService'

// 加载枚举选项
const options = await EnumService.loadOptions('annotation_category')

// 预加载多个枚举
await EnumService.preload(['enum1', 'enum2', 'enum3'])

// 清除缓存
EnumService.clearCache()
```

**特性:**
- 自动缓存
- 错误处理
- 数据规范化
- 预加载支持

---

## [CLIPBOARD] 开发工作流

### 创建新配置 Checklist

- [ ] 查阅配置契约文档
- [ ] 确认配置字段类型和约束
- [ ] 实现配置代码
- [ ] 运行 ConfigValidator 验证
- [ ] 编写单元测试
- [ ] 更新配置契约文档（如需）

### 使用枚举 Checklist

- [ ] 使用 EnumService 加载枚举（不重复实现）
- [ ] 处理加载错误
- [ ] 验证枚举类型 ID 存在
- [ ] 测试枚举选项显示

### 调用 API Checklist

- [ ] 查阅 API 规范文档
- [ ] 使用正确的 API 路径
- [ ] 处理响应格式（注意嵌套结构）
- [ ] 错误处理

---

## [ALERT] 常见问题与解决方案

### 问题 1：枚举选项为空

**可能原因:**
- 枚举类型 ID 不存在
- API 路径错误
- 响应格式解析错误

**解决方案:**
1. 检查枚举类型 ID 是否存在
2. 查阅 [枚举 API 规范](../../docs/api/enum-api.md)
3. 使用 EnumService（自动处理解析）

### 问题 2：配置不生效

**可能原因:**
- 配置字段名称错误
- 缺少必需字段
- 类型不匹配

**解决方案:**
1. 运行 ConfigValidator 验证
2. 查阅配置契约文档
3. 检查控制台验证日志

### 问题 3：API 调用失败

**可能原因:**
- 路径错误
- 认证问题
- 响应格式错误

**解决方案:**
1. 查阅 API 规范文档
2. 检查认证 Token
3. 使用正确的响应解析

---

## [DOC] 相关文档

- [Component Patterns](../context/developer/component-patterns.md) - 组件设计模式
- [UI Design Standards](../context/developer/ui-design-standards.md) - UI 设计规范
- [Coding Standards](../context/developer/coding-standards.md) - 编码规范
- [Engineering Guidelines](./engineering-guidelines.md) - 工程指南
- [枚举 API 规范](../../docs/api/enum-api.md) - 枚举 API 规范
- [跨表过滤配置契约](../../docs/metadata/cross-table-filters.md) - 跨表过滤配置文档
- [元模型驱动过滤规范](../specs/meta-model-driven-filters/spec.md) - 过滤系统规范

---

**最后更新**: 2026-05-08
**下次审查**: 2026-06-08