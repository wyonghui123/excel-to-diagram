# 页面布局规范实施总结

> **实施日期**: 2024-05-13  
> **状态**: ✅ 已完成

---

## 一、本次实施内容

### 1.1 创建了页面布局规范文档

**文件**: `docs/architecture/04-page-layout-standards.md`

**核心内容**:
- 参考 SAP Fiori、Salesforce Lightning、Dynamics 365、Workday 四大头部企业规范
- 设计统一的页面层级结构（三层级模型）
- 定义 Header 区域左-中-右三段式布局标准
- 统一面包屑、返回按钮、操作按钮的位置和样式
- Tab 导航规范
- 响应式设计策略

### 1.2 改造了 ObjectPage 组件

**文件**: `src/components/common/ObjectPage/ObjectPage.vue`

**改造内容**:

#### ✅ 问题1修复：input 被拉长
- 优化 `.op-field` 容器样式
- 限制表单控件宽度为 100%
- 防止内容溢出

#### ✅ 问题2修复：返回按钮位置统一
- **改造前**: 返回按钮在 Header 右侧（与其他页面不一致）
- **改造后**: 返回按钮移动到 Header 左侧（符合 Salesforce/Workday 规范）
- 新增 `.object-page__header-left` 区域，包含返回按钮和面包屑

#### ✅ 问题3修复：折叠区域样式和功能
- 改进折叠卡片样式（左侧虚线 + 淡灰背景）
- 修复展开逻辑（使用响应式 Set 触发更新）
- 优化展开/收起按钮样式

#### 🆕 新增功能：Header 三段式布局

**新布局结构**:
```
┌────────────────────────────────────────────────────────────────────────┐
│ [← 返回] [面包屑] │       页面标题 + 状态        │    [操作按钮]     │
│    (左侧区域)      │        (中央区域)             │    (右侧区域)      │
└────────────────────────────────────────────────────────────────────────┘
```

**实现细节**:

1. **左侧区域** (`object-page__header-left`)
   - 返回按钮（条件显示）
   - 面包屑导航
   - 布局：flex，gap: 16px，padding-left: 24px

2. **中央区域** (`object-page__header-center`)
   - 页面标题（大字体，居中显示）
   - 状态徽章
   - 副标题
   - 布局：flex: 1（占据剩余空间），居中对齐

3. **右侧区域** (`object-page__header-right`)
   - 操作按钮插槽
   - 布局：flex，gap: 8px，padding-right: 24px

---

## 二、参考的四大企业规范对比

### 2.1 返回按钮位置

| 企业 | 位置 | 说明 |
|------|------|------|
| SAP Fiori | 无独立按钮 | 仅使用面包屑导航 |
| Salesforce | Header 左 | 返回按钮在左侧，紧跟面包屑 |
| Microsoft Dynamics | 无独立按钮 | 使用 Command Bar |
| **Workday** | **Header 左** | **独立箭头按钮 + 面包屑共存** |
| **我们的规范** | **Header 左** | **参考 Workday/Salesforce** |

### 2.2 Header 布局模式

| 区域 | 我们的规范 | 说明 |
|------|-----------|------|
| **左侧** | 返回按钮 + 面包屑 | 导航功能区 |
| **中央** | 页面标题 + 状态 | 信息展示区 |
| **右侧** | 操作按钮 | 交互功能区 |

### 2.3 面包屑规范

| 规范项 | 值 | 说明 |
|--------|-----|------|
| 分隔符 | `›` | 替代原来的 `/` |
| 层级限制 | 最多 4 级 | 建议 3 级以内 |
| 可点击性 | 前 N-1 级 | 最后一级不可点击 |
| 字体大小 | 13px | 比页面标题小 |
| 颜色 | `var(--color-text-tertiary)` | 淡化处理 |

---

## 三、组件 Props 变更

### 3.1 ObjectPage Props

```typescript
// 新增 Props（保持向后兼容）
{
  title: string,           // 页面标题（必需）
  subtitle?: string,      // 副标题
  status?: string,        // 状态文本
  statusType?: 'default' | 'success' | 'warning' | 'error',
  breadcrumbs?: Array<{ label: string; to?: string }>,  // 面包屑
  showBackButton?: boolean,  // 是否显示返回按钮
  tabs?: Array<{ key: string; label: string }>,  // Tab 导航
  activeTab?: string,     // 当前激活的 Tab
  // ... 其他原有 props
}
```

### 3.2 Events

```typescript
// 新增 Events
{
  'back': () => void,     // 返回按钮点击
  'navigate': (crumb) => void,  // 面包屑点击
  'tab-change': (key: string) => void,  // Tab 切换
}
```

---

## 四、后续改造计划

### 4.1 优先级 P0（立即执行）

- [ ] 创建 AppPage.vue 通用页面布局组件
- [ ] 改造其他详情页（RolePermissionDetail.vue）
- [ ] 更新 YON_EP_GUIDE.md，添加页面布局规范

### 4.2 优先级 P1（短期执行）

- [ ] 创建 BreadcrumbNav 组件
- [ ] 创建 BackButton 组件
- [ ] 创建 ActionButtons 组件
- [ ] 更新 DESIGN_CHECKLIST.md

### 4.3 优先级 P2（中期执行）

- [ ] 响应式布局测试
- [ ] 创建 PageLayoutStorybook.stories.tsx
- [ ] 编写最佳实践指南

---

## 五、验收标准

### 5.1 功能验收

- [ ] 所有详情页的返回按钮位于 Header 左侧
- [ ] 面包屑导航正确显示，层级关系清晰
- [ ] 操作按钮统一放置在 Header 右侧
- [ ] Tab 导航在 Header 下方，内容区域上方
- [ ] 页面标题居中显示在 Header 中央

### 5.2 样式验收

- [ ] Header 高度统一为 64px
- [ ] 返回按钮样式：透明背景 + 1px 边框 + 圆角
- [ ] 面包屑分隔符使用 `›`
- [ ] 标题字号 20px，副标题 13px
- [ ] 操作按钮间距 8px

### 5.3 响应式验收

- [ ] Desktop (≥1200px): 完整三段式布局
- [ ] Tablet (768-1199px): 标题可能换行
- [ ] Mobile (<768px): 简化为单列布局

---

## 六、相关文件清单

### 6.1 新增文件

| 文件路径 | 说明 |
|----------|------|
| `docs/architecture/04-page-layout-standards.md` | 页面布局规范文档 |
| `docs/architecture/05-page-layout-implementation-summary.md` | 本总结文档 |

### 6.2 修改文件

| 文件路径 | 修改内容 |
|----------|----------|
| `src/components/common/ObjectPage/ObjectPage.vue` | Header 三段式布局、返回按钮位置、折叠功能修复 |

### 6.3 待修改文件

| 文件路径 | 说明 |
|----------|------|
| `src/views/SystemManagement/EnumTypeDetail.vue` | 需要适配新的 Header 布局 |
| `src/views/SystemManagement/RolePermissionDetail.vue` | 需要适配新的 Header 布局 |
| `src/styles/YON_EP_GUIDE.md` | 添加页面布局规范章节 |
| `src/styles/DESIGN_CHECKLIST.md` | 添加 Header 规范检查项 |

---

## 七、总结

本次实施解决了以下核心问题：

1. **返回按钮位置不统一**: 统一将返回按钮放置在 Header 左侧，参考 Workday/Salesforce 规范
2. **缺少顶层 UI 框架规范**: 创建了完整的页面布局规范文档，包含四大头部企业的最佳实践
3. **页面布局混乱**: 定义了左-中-右三段式 Header 布局，统一所有详情页的页面结构

**规范的核心价值**:
- 🎯 统一用户体验：所有页面遵循一致的布局规范
- 🔄 提高开发效率：通用组件和模式减少重复代码
- 📚 便于维护：清晰的文档和标准易于团队理解
- 🚀 可扩展性：规范设计考虑了未来可能的扩展需求

---

**下一步行动**: 建议立即在团队内部分享本规范，并开始 P0 优先级的改造工作。
