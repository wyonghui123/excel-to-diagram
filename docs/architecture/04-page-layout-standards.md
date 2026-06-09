## 目录

1. [一、规范目标](#一-规范目标)
2. [二、页面层级结构](#二-页面层级结构)
3. [三、Header 区域规范（核心）](#三-header-区域规范（核心）)
4. [四、面包屑导航规范](#四-面包屑导航规范)
5. [五、返回按钮规范](#五-返回按钮规范)
6. [六、Tab 导航规范](#六-tab-导航规范)
7. [七、页面 Layout 组件设计](#七-页面-layout-组件设计)
8. [八、响应式设计规范](#八-响应式设计规范)
9. [九、现有组件改造计划](#九-现有组件改造计划)
10. [十、实施检查清单](#十-实施检查清单)
11. [附录](#附录)

---
# 页面布局与导航规范 v1.0

> **版本**: v1.0  
> **创建日期**: 2024-05-13  
> **参考标准**: SAP Fiori, Salesforce Lightning, Microsoft Dynamics 365, Workday  
> **状态**: 草稿

---

## 一、规范目标

1. **统一页面布局**：所有页面遵循一致的层级结构和布局规范
2. **规范化导航**：返回按钮、面包屑、操作按钮的位置统一
3. **组件复用**：提供通用 Page Layout 组件，减少重复代码
4. **响应式支持**：支持桌面、平板、手机等多种设备

---

## 二、页面层级结构

### 2.1 三层级模型

```
┌─────────────────────────────────────────────────────────────────┐
│ Level 1: 全局导航 (Global Navigation)                           │
├─────────────────────────────────────────────────────────────────┤
│ 位置: 页面最顶部或最左侧                                         │
│ 内容: 应用切换、模块入口、用户信息、搜索                          │
├─────────────────────────────────────────────────────────────────┤
│ Level 2: 页面框架 (Page Layout)                                 │
├─────────────────────────────────────────────────────────────────┤
│ 位置: Header 区域                                                │
│ 内容: 面包屑 + 返回按钮 | 页面标题 + 状态 | 操作按钮              │
├─────────────────────────────────────────────────────────────────┤
│ Level 3: 内容区域 (Content Area)                                │
├─────────────────────────────────────────────────────────────────┤
│ 位置: Page Layout 内部                                           │
│ 内容: Tab 导航、表单、列表、详情等                               │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 页面类型分类

| 页面类型 | 说明 | 复杂度 | 示例 |
|----------|------|--------|------|
| **ListPage** | 列表页 | 低 | 用户列表、产品列表 |
| **DetailPage** | 详情页 | 中 | 用户详情、产品详情 |
| **EditPage** | 编辑页 | 中 | 编辑用户、编辑产品 |
| **CreatePage** | 创建页 | 低 | 新建用户、新建产品 |
| **Dashboard** | 仪表盘 | 中 | 数据看板、统计图表 |
| **Workspace** | 工作台 | 高 | 复杂的多 Tab 页面 |

---

## 三、Header 区域规范（核心）

### 3.1 标准布局

**Header 采用左-中-右三段式布局**：

```
┌────────────────────────────────────────────────────────────────────────┐
│ 左侧区域 (Left)          │ 中央区域 (Center)      │ 右侧区域 (Right)  │
├──────────────────────────┼───────────────────────┼───────────────────┤
│ • 返回按钮               │ • 页面标题            │ • 操作按钮        │
│ • 面包屑导航             │ • 状态指示器          │ • 更多操作        │
│ (Breadcrumb + Back)     │ • 关键字段预览        │ (Action Buttons)  │
└────────────────────────────────────────────────────────────────────────┘
```

### 3.2 各区域规范

#### 3.2.1 左侧区域（Left - Navigation）

| 元素 | 必需性 | 说明 | 样式 |
|------|--------|------|------|
| **返回按钮** | 条件必需 | 仅在有上级页面时显示 | 箭头 + "返回"文字 |
| **面包屑** | 条件必需 | 仅在二级及以上页面显示 | "模块 > 子模块 > 当前页" |

**布局规范**：
```css
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;  /* 返回按钮与面包屑间距 */
  flex: 0 0 auto;  /* 不参与 flex 拉伸 */
}
```

#### 3.2.2 中央区域（Center - Title）

| 元素 | 必需性 | 说明 |
|------|--------|------|
| **页面标题** | 必需 | 页面名称，支持多级标题 |
| **状态指示** | 条件必需 | 如"草稿"、"已发布"等状态标签 |
| **关键字段** | 可选 | 如记录ID、关联对象等 |

**布局规范**：
```css
.header-center {
  flex: 1;  /* 占据剩余空间 */
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: flex-start;
  min-width: 0;  /* 防止溢出 */
}
```

#### 3.2.3 右侧区域（Right - Actions）

| 元素 | 必需性 | 说明 | 按钮数量 |
|------|--------|------|----------|
| **主操作按钮** | 可选 | 主要操作如"保存"、"提交" | 1个 |
| **次要操作按钮** | 可选 | 次要操作如"导出"、"刷新" | 0-3个 |
| **更多操作** | 可选 | 更多操作收起在 dropdown | 3+个时使用 |

**布局规范**：
```css
.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;  /* 不参与 flex 拉伸 */
}
```

### 3.3 头部高度规范

| 页面类型 | 高度 | 适用场景 |
|----------|------|----------|
| **Compact** | 48px | 简单页面、列表页 |
| **Standard** | 64px | 标准详情页（推荐） |
| **Relaxed** | 80px | 复杂页面、Workspace |

### 3.4 Header 区域参考对比

| 元素 | SAP Fiori | Salesforce | Dynamics 365 | Workday | **我们的规范** |
|------|-----------|------------|--------------|---------|----------------|
| 返回按钮 | 无（纯面包屑） | Header 左 | Command Bar | Header 左 | **Header 左** |
| 面包屑位置 | Header 左 | Header 左 | 无 | Header 左 | **Header 左** |
| 页面标题 | Header 中 | Header 中 | Header 中 | Header 中 | **Header 中** |
| 操作按钮 | Header 右 | Header 右 | Command Bar | Header 右 | **Header 右** |

---

## 四、面包屑导航规范

### 4.1 标准格式

```
模块名称 > 子模块名称 > 页面名称
```

### 4.2 规范要点

| 规范项 | 说明 |
|--------|------|
| **分隔符** | 使用 `>` 符号，前后留空格 |
| **层级限制** | 最多 4 级，建议 3 级以内 |
| **可点击性** | 前 N-1 级可点击，最后一级不可点击 |
| **省略策略** | 超过 4 级时，保留首尾，中间用 `...` 省略 |
| **当前位置高亮** | 最后一级使用 `font-weight: 600`，颜色加深 |

### 4.3 示例

```html
<!-- 标准场景 -->
<nav class="breadcrumb">
  <a href="#">系统管理</a>
  <span class="breadcrumb-sep">›</span>
  <a href="#">用户管理</a>
  <span class="breadcrumb-sep">›</span>
  <span class="breadcrumb-current">张三</span>
</nav>

<!-- 简化场景（少于 3 级时，可省略面包屑） -->
<nav class="breadcrumb">
  <a href="#">系统管理</a>
  <span class="breadcrumb-sep">›</span>
  <span class="breadcrumb-current">用户管理</span>
</nav>

<!-- 深层级场景（超过 4 级） -->
<nav class="breadcrumb">
  <a href="#">首页</a>
  <span class="breadcrumb-sep">›</span>
  <span class="breadcrumb-ellipsis">...</span>
  <span class="breadcrumb-sep">›</span>
  <a href="#">销售管理</a>
  <span class="breadcrumb-sep">›</span>
  <span class="breadcrumb-current">客户详情</span>
</nav>
```

---

## 五、返回按钮规范

### 5.1 显示条件

| 条件 | 是否显示 | 说明 |
|------|----------|------|
| 从列表页进入详情页 | 显示 | 返回列表 |
| 从详情页进入编辑页 | 显示 | 返回详情 |
| 直接访问页面 | 不显示 | 如直接访问 URL |
| 首页/工作台 | 不显示 | 无上级页面 |

### 5.2 按钮样式

```css
.back-button {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  font-size: 14px;
  color: var(--color-text-secondary);
  background: transparent;
  border: 1px solid var(--color-border-secondary);
  border-radius: var(--radius-base);
  cursor: pointer;
  transition: all 0.2s ease;
}

.back-button:hover {
  color: var(--color-primary);
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}
```

### 5.3 图标规范

| 图标 | Unicode | 方向 | 说明 |
|------|---------|------|------|
| `←` | U+2190 | 向左 | 标准返回箭头 |
| `‹` | U+2039 | 向左 | 可选，比 ← 更细 |
| `← Back` | 组合 | 向左 | 推荐：箭头 + 文字 |

---

## 六、Tab 导航规范

### 6.1 Tab 位置

**标准位置**：Header 下方，内容区域上方

```
┌─────────────────────────────────────────────────────────────────┐
│ Header: 返回 | 面包屑 | 标题 | 操作按钮                         │
├─────────────────────────────────────────────────────────────────┤
│ Tab 导航栏 (Anchor Bar)                                        │
│ [基本信息] [详细信息] [关联信息] [操作日志]                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ 内容区域                                                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 Tab 样式规范

```css
.anchor-bar {
  display: flex;
  gap: 4px;
  padding: 0 24px;
  background: var(--color-bg-container);
  border-bottom: 1px solid var(--color-border-secondary);
  position: sticky;
  top: 0;
  z-index: var(--z-index-sticky);
}

.anchor-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 12px 20px;
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-secondary);
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition: all 0.2s ease;
}

.anchor-tab:hover {
  color: var(--color-text-primary);
  background: var(--color-bg-tertiary);
}

.anchor-tab--active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
}
```

### 6.3 Tab 数量规范

| 数量 | 建议 | 说明 |
|------|------|------|
| 1-5 个 | 推荐 | 最佳用户体验 |
| 6-7 个 | 可接受 | 可考虑折叠 |
| 8+ 个 | 不推荐 | 考虑分组或搜索 |

---

## 七、页面 Layout 组件设计

### 7.1 组件结构

```
AppPage (顶层布局)
├── AppHeader (Header 区域)
│   ├── BreadcrumbNav (面包屑导航)
│   ├── BackButton (返回按钮)
│   ├── PageTitle (页面标题)
│   ├── StatusBadge (状态指示)
│   └── ActionButtons (操作按钮)
├── AnchorBar (Tab 导航)
└── ContentArea (内容区域)
    ├── <slot name="content" />
    └── <slot name="footer" />
```

### 7.2 Props 设计

```typescript
interface AppPageProps {
  // 标题配置
  title: string
  subtitle?: string
  
  // 面包屑配置
  breadcrumbs?: Array<{ label: string; to?: string }>
  
  // 返回按钮
  showBackButton?: boolean
  backButtonText?: string
  
  // 状态配置
  status?: string
  statusType?: 'default' | 'success' | 'warning' | 'error'
  
  // Tab 导航
  tabs?: Array<{ key: string; label: string; icon?: string }>
  activeTab?: string
  
  // 布局配置
  headerHeight?: 'compact' | 'standard' | 'relaxed'
  showAnchorBar?: boolean
  
  // 其他
  loading?: boolean
}
```

### 7.3 Events

```typescript
interface AppPageEvents {
  'back': () => void           // 返回按钮点击
  'tab-change': (key: string) => void  // Tab 切换
  'breadcrumb-click': (crumb: BreadcrumbItem) => void  // 面包屑点击
}
```

---

## 八、响应式设计规范

### 8.1 断点定义

| 断点 | 宽度 | 设备 | Header 布局变化 |
|------|------|------|----------------|
| **Desktop** | ≥1200px | 桌面 | 完整三段式布局 |
| **Tablet** | 768-1199px | 平板 | 面包屑可能换行 |
| **Mobile** | <768px | 手机 | 简化为单行或抽屉式 |

### 8.2 响应式策略

```css
/* Desktop: 完整布局 */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
}

/* Tablet: 面包屑可能换行 */
@media (max-width: 1199px) {
  .page-header {
    flex-wrap: wrap;
  }
  
  .header-left {
    flex-basis: 100%;
    margin-bottom: 12px;
  }
}

/* Mobile: 简化布局 */
@media (max-width: 767px) {
  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
  
  .breadcrumb {
    display: none;  /* 移动端可能隐藏面包屑 */
  }
  
  .header-right {
    width: 100%;
    justify-content: flex-end;
  }
}
```

---

## 九、现有组件改造计划

### 9.1 需要改造的组件

| 组件 | 当前问题 | 改造方案 |
|------|----------|----------|
| **ObjectPage** | 返回按钮在右上角 | 移动到 Header 左侧 |
| **MasterDetailLayout** | 无统一 Header | 集成 AppHeader 功能 |
| **EnumTypeDetail** | 使用旧布局 | 迁移到 AppPage 组件 |

### 9.2 改造优先级

| 优先级 | 组件 | 说明 |
|--------|------|------|
| **P0** | ObjectPage | 核心详情页组件，影响所有详情页 |
| **P1** | AppPage | 新建统一布局组件 |
| **P2** | 详情页改造 | EnumTypeDetail, RolePermissionDetail 等 |

---

## 十、实施检查清单

### 10.1 代码层面

- [ ] 创建 AppPage.vue 通用布局组件
- [ ] ObjectPage 返回按钮移至 Header 左侧
- [ ] 面包屑导航统一使用 BreadcrumbNav 组件
- [ ] 操作按钮统一放置在 Header 右侧
- [ ] Tab 导航使用 AnchorBar 组件
- [ ] 所有详情页迁移到 AppPage 布局

### 10.2 规范层面

- [ ] 更新 YON_EP_GUIDE.md，添加页面布局规范
- [ ] 更新 DESIGN_CHECKLIST.md，添加 Header 规范检查项
- [ ] 创建 PageLayoutStorybook.stories.tsx 用于组件文档
- [ ] 编写页面布局规范的最佳实践指南

### 10.3 视觉层面

- [ ] 统一所有页面的 Header 高度
- [ ] 统一返回按钮样式
- [ ] 统一面包屑样式
- [ ] 统一操作按钮排列顺序
- [ ] 创建响应式布局的视觉测试用例

---

## 附录

### A. 相关文档

- [SAP Fiori Design Guidelines](https://experience.sap.com/fiori-design/)
- [Salesforce Lightning Design System](https://www.lightningdesignsystem.com/)
- [Microsoft Fluent UI](https://developer.microsoft.com/en-us/fluentui/)
- [Ant Design Pro Components](https://pro.ant.design/components/page-container)

### B. 设计资源

- 图标库：Heroicons / Lucide Icons
- 设计系统：Tailwind CSS / Ant Design
- 布局组件：ProLayout, PageContainer

### C. 版本历史

| 版本 | 日期 | 修改内容 | 作者 |
|------|------|----------|------|
| 1.0 | 2024-05-13 | 初始版本 | AI Assistant |

---

**备注**：本规范为初稿，需要在实际应用中不断完善和迭代。建议每季度进行一次规范评审，根据用户反馈和业务需求进行优化。
