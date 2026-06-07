# [ROBOT] AI 智能体组件开发遵循指南

> **版本**: v1.0.0
> **创建日期**: 2026-05-19
> **适用对象**: 所有 AI 编程助手、智能体、开发者
> **重要程度**: [CRITICAL] **必须遵守**

---

## [PIN] 核心原则

### [OK] **强制规则（MUST）**

1. **必须使用标准组件库**
   - 禁止重复造轮子
   - 优先使用 `src/components/common/` 下的已有组件
   - 新建组件前必须检查是否已存在类似功能

2. **必须遵循 YonDesign UI 规范**
   - 圆角：按钮/输入框 `6px`，标签 `4px`，卡片 `8px`
   - 主色：`#ea580c` (YonDesign Orange)
   - 间距：使用 CSS Variables (`--spacing-*`)
   - 字体：Element Plus 默认字体栈

3. **必须使用 Vue 3 Composition API**
   - 使用 `<script setup>` 语法
   - 使用 `ref()` / `reactive()` / `computed()`
   - 禁止使用 Options API

4. **必须基于 Element Plus 构建**
   - 不允许直接操作 DOM
   - 优先使用 EP 组件封装
   - 保持 API 兼容性

### [WARNING] **推荐规则（SHOULD）**

5. 组件命名：PascalCase + 语义化后缀
6. Props 命名：camelCase，语义化
7. 每个 Props 必须有默认值和类型定义
8. 提供完整的事件（Emits）定义
9. 支持无障碍性（ARIA 属性）
10. 编写单元测试

---

## [DOC] 必读文档清单

在开始任何前端开发工作之前，**必须**阅读以下文档：

### [CRITICAL] **必读（Required）**

| 文档 | 路径 | 说明 |
|------|------|------|
| **本指南** | `.trae/rules/AI_AGENT_COMPONENT_GUIDE.md` | 你正在阅读的文档 |
| **组件治理规范** | [component-governance.md](file:///d:/filework/excel-to-diagram/.trae/rules/component-governance.md) | 组件分类、命名、职责 |
| **YonDesign 规范** | [YON_EP_GUIDE.md](file:///d:/filework/excel-to-diagram/src/styles/YON_EP_GUIDE.md) | UI 设计规范（圆角、颜色、间距） |
| **顶部导航 API** | [14-top-navigation-components-api.md](file:///d:/filework/excel-to-diagram/docs/architecture/14-top-navigation-components-api.md) | 新组件的完整 API 文档 |
| **使用示例** | [15-component-library-examples.md](file:///d:/filework/excel-to-diagram/docs/architecture/15-component-library-examples.md) | 所有组件的使用示例 |

### [MEDIUM] **推荐阅读（Recommended）**

| 文档 | 路径 | 说明 |
|------|------|------|
| 架构原则 | [01-principles.md](file:///d:/filework/excel-to-diagram/docs/architecture/01-principles.md) | 六大核心设计原则 |
| 顶部导航架构 | [13-top-navigation-architecture.md](file:///d:/filework/excel-to-diagram/docs/architecture/13-top-navigation-architecture.md) | SAP Fiori / Salesforce Pattern 分析 |
| 页面布局标准 | [04-page-layout-standards.md](file:///d:/filework/excel-to-diagram/docs/architecture/04-page-layout-standards.md) | 布局规范 |
| 编码规范 | [coding-standards.md](file:///d:/filework/excel-to-diagram/.trae/context/developer/coding-standards.md) | 代码风格 |

---

## [PUZZLE] 标准组件库速查表

### A. 顶部导航系统（优先使用）

> **何时使用**: 需要全局布局、多页面管理、用户交互时

```
┌─ 需求场景 ─────────────────────────────┬─ 推荐组件 ───────────────────────────┐
│ 全局应用容器                            │ AppShell                              │
│ 多页面 Tab 管理                        │ AppTabs                               │
│ 面包屑导航                            │ BreadcrumbNav                         │
│ 用户信息下拉菜单                      │ UserMenu                              │
│ 全局搜索框                            │ GlobalSearch                          │
│ 子页面标题栏（返回+标题）              │ PageHeader (AppHeader)                │
└────────────────────────────────────────┴──────────────────────────────────────┘
```

#### 快速导入

```javascript
import {
  AppShell,          // 全局容器
  AppTabs,           // 多页面Tab
  BreadcrumbNav,     // 面包屑
  UserMenu,          // 用户菜单
  GlobalSearch,      // 全局搜索
  PageHeader         // 页面标题栏（别名 AppHeader）
} from '@/components/common'
```

#### 最小化示例

```vue
<template>
  <AppShell :show-tabs="true">
    <template #header-center>
      <BreadcrumbNav :items="breadcrumbs" />
      <GlobalSearch @search="handleSearch" />
    </template>

    <template #header-right>
      <UserMenu :user="user" @command="handleUserAction" />
    </template>

    <template #tabs>
      <AppTabs v-model="activeTab" :tabs="openTabs" @tab-close="closeTab" />
    </template>

    <router-view />
  </AppShell>
</template>
```

---

### B. 基础 UI 组件

> **何时使用**: 表单、按钮、展示类基础元素

```
┌─ 需求场景 ─────────────────────────────┬─ 推荐组件 ───────────────────────────┐
│ 按钮                                    │ AppButton                             │
│ 输入框                                  │ AppInput                              │
│ 下拉选择                                │ AppSelect                             │
│ 卡片容器                                │ AppCard                               │
│ 模态对话框                              │ AppModal                              │
│ 图标                                    │ AppIcon                               │
│ 提示信息                                │ AppAlert                              │
│ 折叠面板                                │ AppCollapse                           │
└────────────────────────────────────────┴──────────────────────────────────────┘
```

#### 快速导入

```javascript
import {
  AppButton,
  AppInput,
  AppSelect,
  AppCard,
  AppModal,
  AppIcon,
  AppAlert,
  AppCollapse
} from '@/components/common'
```

---

### C. 业务页面组件

> **何时需要**: CRUD 页面、详情页、列表页

```
┌─ 需求场景 ─────────────────────────────┬─ 推荐组件 ───────────────────────────┐
│ 元数据驱动的列表页                      │ MetaListPage                          │
│ 对象详情页（字段组+Tab）               │ ObjectPage                            │
│ 主从布局（左列右详情）                  │ MasterDetailLayout                    │
│ 页面外壳容器                            │ PageShell                             │
│ 子导航 Tab                              │ SubNavTabs                            │
│ 子对象区域                              │ ObjectChildSection                    │
│ 详情页容器                              │ DetailPage                            │
│ 详情区域                                │ DetailSection                         │
└────────────────────────────────────────┴──────────────────────────────────────┘
```

#### 快速导入

```javascript
import {
  MetaListPage,
  ObjectPage,
  ObjectPageWithChildren,
  MasterDetailLayout,
  PageShell,
  SubNavTabs,
  ObjectChildSection,
  DetailPage,
  DetailSection
} from '@/components/common'
```

---

### D. 数据管理组件

> **何时需要**: 过滤、分页、表格、侧滑面板

```
┌─ 需求场景 ─────────────────────────────┬─ 推荐组件 ───────────────────────────┐
│ 过滤器栏（搜索+选择+日期范围）          │ FilterBar                             │
│ 分页控件                                │ Pagination                            │
│ 元数据表格                              │ MetaTable                             │
│ 元数据表单                              │ MetaForm                              │
│ 可折叠面板                              │ CollapsiblePanel                      │
│ 侧滑抽屉                                │ Drawer                                │
│ 外键链接字段                            │ FkLinkField                           │
│ 浮动导航                                │ FloatingNav                           │
└────────────────────────────────────────┴──────────────────────────────────────┘
```

#### 快速导入

```javascript
import {
  FilterBar,
  Pagination,
  MetaTable,
  MetaForm,
  CollapsiblePanel,
  Drawer,
  FkLinkField,
  FloatingNav
} from '@/components/common'
```

---

### E. 对话框与交互组件

> **何时需要**: 确认操作、导入导出、空状态展示

```
┌─ 需求场景 ─────────────────────────────┬─ 推荐组件 ───────────────────────────┐
│ 确认对话框（删除等危险操作）            │ ConfirmDialog                         │
│ 空状态展示                              │ EmptyState                            │
│ 导入对话框                              │ ImportDialog                          │
│ 导出对话框                              │ ExportDialog                          │
│ 分配对话框                              │ AssignmentDialog                      │
│ 搜索帮助对话框                          │ SearchHelpDialog                      │
│ 值帮助字段                              │ ValueHelpField                        │
│ 枚举选择/搜索                          │ EnumSelect / EnumSearchHelp           │
└────────────────────────────────────────┴──────────────────────────────────────┘
```

#### 快速导入

```javascript
import {
  ConfirmDialog,
  EmptyState,
  ImportDialog,
  ExportDialog,
  AssignmentDialog,
  SearchHelpDialog,
  ValueHelpField,
  EnumSelect,
  EnumSearchHelp
} from '@/components/common'
```

---

## [DESIGN] UI 规范速查卡

### 尺寸规范

| 类型 | 小 (sm) | 中 (md) | 大 (lg) |
|------|---------|---------|----------|
| **按钮高度** | 28px | 32px | 40px |
| **输入框高度** | 28px | 32px | 40px |
| **字体大小** | 12px | 14px | 16px |
| **图标大小** | 14px | 16px | 20px |

### 圆角规范

| 元素 | 圆角值 | CSS 变量 |
|------|--------|----------|
| 按钮 / 输入框 / 选择器 | **6px** | `--el-border-radius-base` |
| 标签 / 徽章 / 分页项 | **4px** | `--el-border-radius-small` |
| 卡片 / 弹窗 / 抽屉 | **8px** | 自定义 |
| 头像 / 圆形按钮 | **9999px** | `border-radius: 50%` |

### 间距系统

```scss
--spacing-xs: 4px;    // 极小间距
--spacing-sm: 8px;    // 小间距
--spacing-md: 16px;   // 中间距（常用）
--spacing-lg: 24px;   // 大间距
--spacing-xl: 32px;   // 特大间距
```

### 颜色系统

```scss
// 主色系（YonDesign Orange）
--yonyou-orange-100: #ffedd5;  // 最浅
--yonyou-orange-200: #fed7aa;
--yonyou-orange-300: #fdba74;
--yonyou-orange-400: #fb923c;
--yonyou-orange-500: #f97316;
--yonyou-orange-600: #ea580c;  // * 主色
--yonyou-orange-700: #c2410c;
--yonyou-orange-800: #9a3412;

// 功能色
--color-success: #22c55e;   // 成功
--color-warning: #f59e0b;   // 警告
--color-danger: #ef4444;    // 危险
--color-info: #3b82f6;      // 信息
```

---

## [NOTE] 组件开发模板

### 标准组件结构

```vue
<template>
  <div class="component-name">
    <!-- 组件内容 -->
  </div>
</template>

<script setup>
/**
 * ComponentName - 组件说明
 * @version 1.0.0
 * @author AI Agent
 */

// ====== Imports ======
import { ref, computed, onMounted } from 'vue'

// ====== Props ======
const props = defineProps({
  /**
   * 参数说明
   * @type {String}
   * @default ''
   */
  propExample: {
    type: String,
    default: ''
  },

  /**
   * 是否显示
   * @type {Boolean}
   * @default true
   */
  visible: {
    type: Boolean,
    default: true
  }
})

// ====== Emits ======
const emit = defineEmits([
  'update:modelValue',  // v-model 支持
  'change',             // 值变化
  'click'               // 点击事件
])

// ====== State ======
const state = ref(null)

// ====== Computed ======
const computedValue = computed(() => {
  return props.propExample
})

// ====== Methods ======
function handleClick() {
  emit('click', state.value)
}

// ====== Lifecycle ======
onMounted(() => {
  console.log('Component mounted')
})
</script>

<style scoped>
.component-name {
  /* 使用 CSS Variables */
  padding: var(--spacing-md);
  border-radius: var(--el-border-radius-base);  /* 6px */
}

/* Element Plus 深度选择器覆盖 */
.component-name :deep(.el-input__wrapper) {
  border-radius: var(--el-border-radius-base);
}

/* 响应式 */
@media (max-width: 768px) {
  .component-name {
    padding: var(--spacing-sm);
  }
}
</style>
```

### index.js 导出模板

```javascript
// src/components/common/ComponentName/index.js
import ComponentName from './ComponentName.vue'

export { ComponentName }
export default ComponentName
```

---

## [FORBID] 禁止事项（Anti-Patterns）

### [X] **禁止的做法**

1. **禁止硬编码样式值**
   ```vue
   <!-- [X] 错误 -->
   <div style="padding: 16px; border-radius: 6px;">

   <!-- [OK] 正确 -->
   <div class="my-component">
   ```
   ```scss
   .my-component {
     padding: var(--spacing-md);
     border-radius: var(--el-border-radius-base);
   }
   ```

2. **禁止重复创建已有功能的组件**
   ```javascript
   // [X] 错误：FilterBar 已存在，不要创建 MyFilterBar
   import MyFilterBar from './MyFilterBar'

   // [OK] 正确：复用现有组件
   import { FilterBar } from '@/components/common'
   ```

3. **禁止在组件内写业务逻辑**
   ```vue
   <script setup>
   // [X] 错误：组件不应包含 API 调用
   const data = await fetch('/api/data')

   // [OK] 正确：通过 Props 和 Emits 传递数据
   const props = defineProps({ data: Array })
   const emit = defineEmits(['fetch-data'])
   </script>
   ```

4. **禁止忽略无障碍性**
   ```vue
   <!-- [X] 错误 -->
   <button @click="handleClick">点击</button>

   <!-- [OK] 正确 -->
   <button
     @click="handleClick"
     :aria-label="'执行操作'"
     :disabled="loading"
   >
     点击
   </button>
   ```

5. **禁止使用 Options API**
   ```vue
   <script>
   // [X] 错误：Options API
   export default {
     data() { return {} },
     methods: {}
   }
   </script>

   <script setup>
   // [OK] 正确：Composition API
   import { ref } from 'vue'
   const count = ref(0)
   </script>
   ```

---

## [OK] 开发检查清单

在提交代码之前，请逐项确认：

### 代码质量

- [ ] 使用 `<script setup>` 语法
- [ ] 所有 Props 有类型定义和默认值
- [ ] 所有 Events 在 `defineEmits` 中声明
- [ ] 使用 CSS Variables（不硬编码颜色/间距）
- [ ] 圆角符合 YonDesign 规范（6px/4px/8px）
- [ ] 响应式适配（移动端）

### 文档完整性

- [ ] 组件内有 JSDoc 注释
- [ ] Props 说明清晰
- [ ] Events 说明清晰
- [ ] 提供 Slots 说明（如有）
- [ ] 更新 component-governance.md（如新建组件）

### 测试要求

- [ ] 单元测试覆盖率 > 80%
- [ ] 关键路径有集成测试
- [ ] 无障碍性测试通过

### 性能优化

- [ ] 大列表使用虚拟滚动
- [ ] 图片懒加载
- [ ] 避免不必要的重渲染
- [ ] 合理使用 `v-once` / `v-memo`

---

## [BUG] 常见问题排查

### Q1: 组件样式不生效？

**解决方案**:
1. 检查是否使用了 `scoped`
2. 如需覆盖子组件样式，使用 `:deep()` 选择器
3. 确保使用了 CSS Variables

```scss
/* [OK] 正确 */
.my-component :deep(.el-button) {
  border-radius: var(--el-border-radius-base);
}
```

### Q2: 找不到组件？

**解决方案**:
1. 检查 `src/components/common/index.js` 是否导出
2. 检查组件目录是否有 `index.js`
3. 确认导入路径正确

```javascript
// [OK] 正确导入方式
import { AppButton } from '@/components/common'

// 或单独导入
import AppButton from '@/components/common/AppButton/AppButton.vue'
```

### Q3: Element Plus 样式被覆盖？

**解决方案**:
1. 不要全局修改 Element Plus 变量
2. 在组件级别使用 `:deep()` 定向覆盖
3. 或创建自定义主题文件

---

## [PHONE] 联系与反馈

- **文档问题**: 提交 Issue 到 docs 仓库
- **组件 Bug**: 提交 Issue 并附上复现步骤
- **新组件建议**: 先查阅现有组件，避免重复
- **规范疑问**: 查看 [YON_EP_GUIDE.md](file:///d:/filework/excel-to-diagram/src/styles/YON_EP_GUIDE.md)

---

## [REFRESH] 版本历史

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.0.0 | 2026-05-19 | 初始版本，包含完整的组件库规范和遵循指南 |

---

**最后更新**: 2026-05-19
**维护者**: 架构团队 + AI 协作团队
**下次审查**: 2026-06-19
