# UI 样式规范

> 最后更新: 2026-06-07 | 状态: 活跃
> 拆分自 project_rules.md（原第 6-152 行）

## [!!!] YonDesign 设计规范 [!!!]

**修改样式前必读**：`src/styles/YON_DESIGN_CONSTANTS.md`

- [FORBIDDEN] **禁止使用任何 Emoji 符号！**
- 主色调必须使用 YonDesign Orange (#ea580c 橙色系)
- 所有颜色必须使用 CSS 变量（--yonyou-*），禁止硬编码
- 修改样式前必须查阅设计决策清单 (`src/styles/DESIGN_CHECKLIST.md`)
- 违反此原则会导致设计系统不一致和编码错误！

## Vue 组件规范

**创建或修改任何 Vue 组件之前，必须：**

- **必读1**：`src/styles/YON_DESIGN_CONSTANTS.md` - 了解设计规范（颜色、按钮状态、圆角等）
- **必读2**：`src/styles/YON_EP_GUIDE.md` - 了解 Element Plus 封装规范

## 组件使用规范

### 必须使用封装组件（11个）

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

### 可以直接使用 el-* 组件（36个）

全局样式已覆盖圆润和颜色：Alert, Badge, Input, Select, Tag, Progress, Avatar, Tooltip, Switch, Slider, Radio, Checkbox, InputNumber, DatePicker, TimePicker, Cascader, Transfer, Rate, ColorPicker, Popover, Drawer, Message, MessageBox, Notification, Pagination, Table, Steps, Tree, Dropdown, Skeleton, Empty, Result, Timeline, Descriptions, Calendar, Image, Backtop, InfiniteScroll, Space, Statistic, Segment, Watermark

### 特殊组件（2个）

| 组件名称 | 使用方式 | 原因 |
|---------|---------|------|
| Link | el-link (全局样式) | 使用 Link 按钮规范（Material Design） |
| Message/Notification | ElMessage | 框架原生，使用全局样式 |

## 组件使用示例

```vue
<!-- [OK] 正确：使用封装组件 -->
<AppButton variant="primary">新建用户</AppButton>
<AppModal v-model="visible" title="确认删除">
  <p>确定要删除吗？</p>
</AppModal>

<!-- [X] 错误：使用原生组件 -->
<el-button type="primary">新建用户</el-button>
<el-dialog v-model="visible">确认删除</el-dialog>

<!-- [OK] 正确：可以直接使用 el-* 组件（全局样式已覆盖） -->
<el-input v-model="form.name" placeholder="请输入" />
<el-select v-model="form.type" placeholder="请选择">
  <el-option label="选项1" value="1" />
</el-select>
<el-table :data="tableData">
  <el-table-column prop="name" label="名称" />
</el-table>
```

## UI 规范要点

- Tab导航：使用底部指示线
- 侧边导航：使用左侧指示线
- 文本颜色：正确使用 design tokens
- 滚动条：使用浏览器默认
- 详细规范：`docs/UI_COMPONENT_GUIDELINES.md`

## CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-06-07 | AI Assistant | 从 project_rules.md 拆分 |
