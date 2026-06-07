# YonDesign Element Plus 标准组件库

> **状态**: 维护中
> **废弃通知**: `yon-ep` 组件库（YButton, YInput, YSelect 等）已于 2026-06-03 废弃
> **替代方案**: 直接使用 Element Plus 原生组件 + 全局样式

## 概述

基于 Element Plus 的标准组件封装，统一应用 YonDesign 圆润风格和主题色，确保全项目视觉一致性。

## 设计规范

| 组件类型 | 圆角 | 说明 |
|---------|------|------|
| 按钮/输入框/选择器 | 6px | 基础交互组件 |
| 标签/分页/下拉项 | 4px | 小型组件 |
| 卡片/弹窗/抽屉/结果页 | 8px | 容器型组件 |
| 圆形按钮 | 9999px | 使用 `rounded` prop |

## 主题色

- **主色**: `#ea580c` (YonDesign Orange)
- **成功色**: `#22c55e` (Green)
- **警告色**: `#f59e0b` (Amber)
- **危险色**: `#ea580c` (使用主色保持一致)

## 使用方式

### 方式1：全局样式自动应用（推荐）

在 `main.js` 中已自动导入全局样式，所有 Element Plus 组件自动应用圆润效果：

```javascript
// main.js
import './styles/yon-ep.scss'  // 已自动导入
```

### 方式2：直接使用 Element Plus 组件

```vue
<template>
  <!-- 使用 el-button（全局样式已覆盖圆角和主题色） -->
  <el-button type="primary">提交</el-button>
  <el-button type="success">圆角按钮</el-button>

  <!-- 使用 el-input -->
  <el-input v-model="value" placeholder="请输入" />

  <!-- 使用 el-select -->
  <el-select v-model="value" placeholder="请选择">
    <el-option label="选项1" value="1" />
    <el-option label="选项2" value="2" />
  </el-select>

  <!-- 使用 el-dialog -->
  <el-dialog v-model="visible" title="标题">
    <p>内容</p>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary">确定</el-button>
    </template>
  </el-dialog>

  <!-- 使用 el-table -->
  <el-table :data="tableData">
    <el-table-column prop="name" label="名称" />
  </el-table>

  <!-- 使用 el-tag -->
  <el-tag type="success">成功</el-tag>
  <el-tag type="warning">警告</el-tag>

  <!-- 使用 el-pagination -->
  <el-pagination :total="100" v-model:current-page="page" />
</template>
```

## 组件使用规范

根据 `project_rules.md` 中的规范，组件分为三类：

### 必须使用封装组件（仅限以下 11 个）

| 组件类型 | 封装组件 | 禁止使用 | 原因 |
|---------|---------|---------|------|
| 按钮 | AppButton | el-button | 封装 Hover/Active 状态和 CSS 变量 |
| 弹窗 | AppModal | el-dialog | 统一样式，自定义动画 |
| 警告提示 | AppAlert | el-alert | 统一颜色和圆角 |
| 卡片 | AppCard | el-card | 统一圆角和阴影 |
| 标签页 | AppTabs | el-tabs | 统一指示线样式 |
| 选择器 | AppSelect | el-select | 统一圆角和样式 |
| 输入框 | AppInput | el-input | 统一圆角和样式 |
| 折叠面板 | AppCollapse | el-collapse | 统一样式 |
| 侧边导航 | AppSideNav | el-menu | 统一指示线样式 |
| 图标 | AppIcon | el-icon | 统一颜色 |
| 页头 | AppHeader | - | 自定义组件 |

### 可以直接使用 el-* 组件（全局样式已覆盖）

以下组件可以通过全局样式自动应用 YonDesign 风格，无需额外封装：

| 类别 | 组件 |
|------|------|
| 表单组件 | el-input, el-select, el-option, el-checkbox, el-radio, el-switch, el-slider, el-date-picker, el-time-picker, el-cascader, el-transfer, el-input-number, el-rate, el-color-picker, el-upload, el-autocomplete |
| 数据展示 | el-table, el-tag, el-badge, el-progress, el-skeleton, el-timeline, el-tree, el-avatar, el-calendar, el-image, el-descriptions, el-result |
| 导航组件 | el-pagination, el-dropdown, el-steps, el-breadcrumb, el-affix, el-backtop |
| 反馈组件 | el-message, el-notification, el-tooltip, el-popover, el-popconfirm, el-loading, el-alert |

### 特殊组件（使用框架原生方式）

| 组件名称 | 使用方式 | 原因 |
|---------|---------|------|
| Link | el-link (全局样式) | 使用 Link 按钮规范（Material Design） |
| Message/Notification | ElMessage | 框架原生，使用全局样式 |

### Link 按钮详细规范（操作列按钮）

> **重要**：Link 按钮用于表格操作列（详情/编辑/删除等），必须使用 **Material Design** 风格！

#### 设计原则

遵循 **Google Material Design 3 Text Button** 规范：
- **Hover/Focus/Active 状态只改变背景透明度**
- **文字颜色始终保持不变**，确保可读性和对比度稳定
- 通过背景深浅（6% < 12% < 16%）表达交互状态层次
- 参考实现：[MetaTable.vue](../components/common/MetaTable.vue) 中的 `.mt-link-btn` 类（第 1011-1076 行）

#### 视觉规范

| 状态 | 文字颜色 | 背景颜色 | 背景透明度 | 边框 | 示意图 |
|------|----------|----------|-----------|------|--------|
| 默认 | `#ea580c` (orange-600) | 透明 | 0% | 无 | `[详情]` (橙色文字) |
| Hover | `#ea580c` (orange-600) | 橙色 | **6%** | 无 | `[详情]` (橙色文字 + 极淡橙背景) |
| Focus | `#ea580c` (orange-600) | 橙色 | **12%** | 无 | `[详情]` (橙色文字 + 淡橙背景) |
| Active | `#ea580c` (orange-600) | 橙色 | **16%** | 无 | `[详情]` (橙色文字 + 中橙背景) |

#### 核心优势

- **可读性稳定**：文字颜色始终不变，对比度保持一致
- **符合 Material Design 最佳实践**：业界标准交互模式
- **渐进式状态反馈**：用户可以清晰区分不同交互状态
- **性能优秀**：只改变背景透明度，无需重绘文字
- **实现简单**：代码量少，维护成本低

#### 使用示例

```vue
<template>
  <!-- 操作列 Link 按钮 -->
  <el-table-column label="操作" width="200">
    <template #default="{ row }">
      <el-button
        v-for="action in getRowActions(row)"
        :key="action.key"
        size="small"
        link
        @click="handleAction(action, row)"
      >
        {{ action.label }}
      </el-button>
    </template>
  </el-table-column>
</template>
```

#### 样式实现位置

全局样式已定义在 [yon-ep.scss](./yon-ep.scss) 第 105-148 行，自动应用于所有 `.el-button.is-link` 元素。

**关键代码片段**：
```scss
&.is-link {
  color: var(--yonyou-orange-600, #ea580c) !important;  // 固定文字色

  &:hover,
  &:focus {
    background: rgba(234, 88, 12, 0.06) !important;  // 6% opacity
    color: var(--yonyou-orange-600, #ea580c) !important;  // 不变
  }

  &:focus-visible {
    background: rgba(234, 88, 12, 0.12) !important;  // 12% opacity
  }

  &:active {
    background: rgba(234, 88, 12, 0.16) !important;  // 16% opacity
  }
}
```

## 自动导入配置

在 `vite.config.js` 中配置组件自动导入：

```javascript
// vite.config.js
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver, VueUseComponentsResolver } from 'element-plus/auto-resolver'

export default defineConfig({
  plugins: [
    Components({
      resolvers: [
        // Element Plus 组件
        ElementPlusResolver({
          importStyle: false, // 关闭自动导入样式
        }),
      ],
      include: [/\.vue$/, /\.vue\?vue/],
    }),
  ],
})
```

## 更新规范

当 `ComponentComparison` 页面确认了新的标准样式后：

1. 更新 `src/styles/yon-ep.scss` 全局样式
2. 所有引用 Element Plus 组件的页面自动生效

## 注意事项

1. 全局样式会覆盖 Element Plus 默认样式，确保在 `element-plus` 样式之后导入
2. 必须使用封装组件的场景，请使用 `@/components/common` 中的 App* 组件
3. 其他场景直接使用 Element Plus 原生组件即可，全局样式会自动覆盖

## 废弃组件清单

以下组件已于 2026-06-03 废弃：

| 废弃组件 | 替代方案 |
|---------|---------|
| YButton | el-button + 全局样式 或 AppButton |
| YInput | el-input + 全局样式 或 AppInput |
| YSelect | el-select + 全局样式 或 AppSelect |
| YDialog | el-dialog + 全局样式 或 AppModal |
| YDrawer | el-drawer + 全局样式 |
| YTable | el-table + 全局样式 |
| YTag | el-tag + 全局样式 |
| YPagination | el-pagination + 全局样式 |
