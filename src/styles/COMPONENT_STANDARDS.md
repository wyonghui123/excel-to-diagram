# 组件使用规范

> **重要：所有开发者在使用组件前必须查阅此文件！**
>
> **最后更新**: 2026-05-11
> **参考页面**: http://localhost:3004/component-comparison

---

## 概述

本项目使用 **Element Plus** 作为 UI 组件库，并通过以下方式统一样式：

1. **封装组件**：对核心交互组件进行封装（App* 系列）
2. **全局样式覆盖**：通过 `src/styles/yon-ep.scss` 覆盖 Element Plus 默认样式
3. **设计系统**：遵循 YonDesign 规范（橙色主色调、圆润圆角）

---

## 组件分类

基于 ComponentComparison.vue 页面的测试，我们有 **49 个 Element Plus 组件**，分为三类：

| 类别 | 数量 | 说明 |
|------|------|------|
| **必须使用封装组件** | 11个 | 需要特殊样式或功能封装 |
| **可以直接使用 el-* 组件** | 36个 | 全局样式已覆盖 |
| **特殊组件** | 2个 | 使用框架原生方式 |

---

## 1. 必须使用封装组件（11个）

### 1.1 组件列表

| 组件类型 | 封装组件 | 禁止使用 | 原因 |
|---------|---------|---------|------|
| **按钮** | AppButton | el-button | 封装 Hover/Active 状态，使用 CSS 变量 |
| **弹窗** | AppModal | el-dialog | 统一样式，自定义动画，统一使用 AppButton |
| **警告提示** | AppAlert | el-alert | 统一颜色和圆角 |
| **卡片** | AppCard | el-card | 统一圆角和阴影 |
| **标签页** | AppTabs | el-tabs | 统一指示线样式（底部/左侧） |
| **选择器** | AppSelect | el-select | 统一圆角和样式 |
| **输入框** | AppInput | el-input | 统一圆角和样式 |
| **折叠面板** | AppCollapse | el-collapse | 统一样式 |
| **侧边导航** | AppSideNav | el-menu | 统一指示线样式 |
| **图标** | AppIcon | el-icon | 统一颜色 |
| **页头** | AppHeader | - | 自定义组件 |

### 1.2 AppButton 使用指南

#### 基本用法

```vue
<template>
  <AppButton variant="primary" @click="handleClick">
    新建用户
  </AppButton>
</template>

<script setup>
import AppButton from '@/components/common/AppButton/AppButton.vue'

const handleClick = () => {
  console.log('按钮点击')
}
</script>
```

#### variant 属性值

| 值 | 说明 | 使用场景 |
|----|------|----------|
| `primary` | 主要按钮 | 主要操作，如"新建"、"保存" |
| `secondary` | 次要按钮 | 次要操作，如"取消"、"返回" |
| `text` | 文字按钮 | 低优先级操作，如"详情"、"编辑" |
| `danger` | 危险按钮 | 危险操作，如"删除"、"移除" |
| `success` | 成功按钮 | 成功操作，如"启用"、"通过" |
| `warning` | 警告按钮 | 警告操作，如"停用"、"拒绝" |

#### size 属性值

| 值 | 说明 | 使用场景 |
|----|------|----------|
| `xs` | 超小 | 紧凑表格中的操作 |
| `sm` | 小 | 表格操作列、下拉菜单内 |
| `md` | 中等（默认） | 表单操作、工具栏 |
| `lg` | 大 | 主要页面操作 |
| `xl` | 超大 | 空状态、操作引导 |

#### 其他属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `disabled` | Boolean | 是否禁用 |
| `loading` | Boolean | 是否加载中 |
| `icon` | Object/Function | 图标组件 |
| `block` | Boolean | 是否 block 按钮 |

### 1.3 AppModal 使用指南

#### 基本用法

```vue
<template>
  <AppModal
    v-model="visible"
    title="确认删除"
    @confirm="handleConfirm"
    @cancel="handleCancel"
  >
    <p>确定要删除此用户吗？此操作无法撤销。</p>
  </AppModal>
</template>

<script setup>
import { ref } from 'vue'
import AppModal from '@/components/common/AppModal/AppModal.vue'

const visible = ref(false)

const handleConfirm = () => {
  console.log('确认删除')
  visible.value = false
}

const handleCancel = () => {
  console.log('取消')
  visible.value = false
}
</script>
```

#### Props

| 属性 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `modelValue` | Boolean | 控制显示/隐藏 | - |
| `title` | String | 弹窗标题 | - |
| `width` | String | 弹窗宽度 | '600px' |
| `showClose` | Boolean | 显示关闭按钮 | true |
| `showDefaultFooter` | Boolean | 显示默认底部按钮 | true |
| `confirmText` | String | 确认按钮文字 | '确定' |
| `cancelText` | String | 取消按钮文字 | '取消' |
| `confirmLoading` | Boolean | 确认按钮加载状态 | false |

#### Slots

| 名称 | 说明 |
|------|------|
| `default` | 弹窗内容 |
| `header` | 自定义头部 |
| `footer` | 自定义底部（会覆盖 showDefaultFooter） |

### 1.4 其他封装组件

请参考以下文件：

- `src/components/common/AppAlert/AppAlert.vue` - 警告提示
- `src/components/common/AppCard/AppCard.vue` - 卡片
- `src/components/common/AppTabs/AppTabs.vue` - 标签页
- `src/components/common/AppSelect/AppSelect.vue` - 选择器
- `src/components/common/AppInput/AppInput.vue` - 输入框
- `src/components/common/AppCollapse/AppCollapse.vue` - 折叠面板
- `src/components/common/AppSideNav/AppSideNav.vue` - 侧边导航
- `src/components/common/AppIcon/AppIcon.vue` - 图标
- `src/components/common/AppHeader.vue` - 页头

---

## 2. 可以直接使用 el-* 组件（36个）

以下组件**可以直接使用**，无需封装，因为全局样式（`src/styles/yon-ep.scss`）已覆盖圆润和颜色：

### 2.1 布局类组件

| 组件 | 说明 |
|------|------|
| Space | 间距组件 |

### 2.2 表单类组件

| 组件 | 说明 |
|------|------|
| Input | 输入框（建议使用 AppInput） |
| Select | 选择器（建议使用 AppSelect） |
| InputNumber | 数字输入框 |
| DatePicker | 日期选择器 |
| TimePicker | 时间选择器 |
| Cascader | 级联选择器 |
| Switch | 开关 |
| Slider | 滑块 |
| Radio | 单选框 |
| Checkbox | 多选框 |
| Rate | 评分 |
| ColorPicker | 颜色选择器 |

### 2.3 数据展示类组件

| 组件 | 说明 |
|------|------|
| Table | 表格 |
| Tag | 标签 |
| Progress | 进度条 |
| Avatar | 头像 |
| Badge | 徽标 |
| Timeline | 时间线 |
| Descriptions | 描述列表 |
| Calendar | 日历 |
| Image | 图片 |
| Statistic | 统计数值 |
| Result | 结果 |

### 2.4 导航类组件

| 组件 | 说明 |
|------|------|
| Menu | 导航菜单（建议使用 AppSideNav） |
| Tabs | 标签页（建议使用 AppTabs） |
| Steps | 步骤条 |
| Dropdown | 下拉菜单 |
| Backtop | 回到顶部 |

### 2.5 反馈类组件

| 组件 | 说明 |
|------|------|
| Alert | 警告提示（建议使用 AppAlert） |
| Tooltip | 文字提示 |
| Popover | 弹出框 |
| Drawer | 抽屉 |
| Skeleton | 骨架屏 |
| Empty | 空状态 |

### 2.6 其他组件

| 组件 | 说明 |
|------|------|
| Tree | 树形控件 |
| Transfer | 穿梭框 |
| Pagination | 分页 |
| Segment | 段落 |
| Watermark | 水印 |
| InfiniteScroll | 无限滚动 |

### 2.7 使用示例

```vue
<template>
  <div>
    <!-- ✅ 可以直接使用 -->
    <el-input v-model="form.name" placeholder="请输入姓名" />
    <el-select v-model="form.gender" placeholder="请选择性别">
      <el-option label="男" value="male" />
      <el-option label="女" value="female" />
    </el-select>
    <el-table :data="tableData" border>
      <el-table-column prop="name" label="姓名" />
      <el-table-column prop="age" label="年龄" />
    </el-table>
    <el-pagination
      v-model:current-page="currentPage"
      :page-size="20"
      :total="100"
      layout="prev, pager, next"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'

const form = ref({
  name: '',
  gender: ''
})

const tableData = ref([
  { name: '张三', age: 25 },
  { name: '李四', age: 30 }
])

const currentPage = ref(1)
</script>
```

---

## 3. 特殊组件（2个）

### 3.1 Link 按钮

Link 按钮使用 `el-link`，但遵循 **Material Design** 规范：

```vue
<template>
  <!-- ✅ 正确：使用 el-link，全局样式已覆盖 -->
  <el-button size="small" link>详情</el-button>
  <el-button size="small" link>编辑</el-button>
  <el-button size="small" link>删除</el-button>
</template>
```

#### 状态规范

| 状态 | 文字颜色 | 背景颜色 | 说明 |
|------|----------|----------|------|
| 默认 | `#ea580c` | transparent | - |
| Hover | `#ea580c` | `rgba(234, 88, 12, 0.06)` | 6% 透明度 |
| Focus | `#ea580c` | `rgba(234, 88, 12, 0.12)` | 12% 透明度 |
| Active | `#ea580c` | `rgba(234, 88, 12, 0.16)` | 16% 透明度 |

#### 设计原则

- 文字颜色**始终保持不变**
- 通过背景透明度变化表达交互状态
- 不使用边框，只使用背景色

### 3.2 Message / Notification

使用框架原生的消息提示，全局样式已覆盖：

```vue
<script setup>
import { ElMessage, ElNotification } from 'element-plus'

// ✅ 消息提示
ElMessage.success('操作成功')

// ✅ 通知
ElNotification({
  title: '提示',
  message: '这是一条通知',
  type: 'success'
})
</script>
```

---

## 4. 全局样式覆盖范围

以下样式通过 `src/styles/yon-ep.scss` 全局覆盖：

### 4.1 圆角

| 变量 | 默认值 | 圆润值 | 应用场景 |
|------|--------|--------|----------|
| `--el-border-radius-base` | 4px | **6px** | 按钮、输入框、选择器 |
| `--el-border-radius-small` | 2px | **4px** | 标签、分页、下拉项 |
| `--el-border-radius-round` | 20px | **8px** | 圆形按钮 |

### 4.2 主题色

| 用途 | 色值 | 变量 |
|------|------|------|
| Primary | `#ea580c` | `--el-color-primary` |
| Primary Light-3 | `#fb923c` | `--el-color-primary-light-3` |
| Primary Light-5 | `#fdba74` | `--el-color-primary-light-5` |
| Primary Dark-2 | `#c2410c` | `--el-color-primary-dark-2` |

### 4.3 按钮样式

- 所有按钮统一使用 `border-radius: 6px`
- Primary 按钮 Hover 时保持白色文字
- Link 按钮使用 Material Design 规范

---

## 5. 验证和测试

### 5.1 验证页面

访问 http://localhost:3004/component-comparison 查看所有组件的对比效果。

### 5.2 组件测试清单

在修改样式后，请验证：

- [ ] 按钮的 Hover 状态（文字应保持白色）
- [ ] Link 按钮的交互效果（背景透明度变化）
- [ ] 弹窗的样式和动画
- [ ] 表单的圆角和颜色
- [ ] 整体风格一致性

### 5.3 常见问题

**Q: 为什么有些组件可以直接使用 el-*？**
A: 因为全局样式（`src/styles/yon-ep.scss`）已经覆盖了这些组件的圆角和颜色。

**Q: 为什么按钮和弹窗需要封装？**
A: 因为它们有复杂的交互状态（Hover/Active/Focus），需要封装以确保样式一致性。

**Q: 如何选择使用 App* 还是 el-*？**
A: 优先使用 App* 组件；如果 App* 不满足需求，再考虑使用 el-*。

---

## 6. 规范执行

### 6.1 违规检测

使用以下命令检测违规：

```bash
# 检测是否使用了禁止的组件
grep -rn "el-button\|el-dialog\|el-alert" src/ --include="*.vue" | grep -v "AppButton\|AppModal\|AppAlert"

# 检测硬编码颜色
grep -rn "#ea580c\|#f97316\|#c2410c" src/ --include="*.vue" | grep -v "var(--"

# 检测 Emoji
grep -rP '[\x{1F600}-\x{1F64F}]' src/ --include="*.md" --include="*.js" --include="*.vue"
```

### 6.2 纠正流程

1. **发现问题**：组件使用不符合规范
2. **检查规范**：查阅本文件和 `YON_DESIGN_CONSTANTS.md`
3. **修正代码**：替换为正确的组件
4. **验证效果**：在组件对比页面验证
5. **记录问题**：如果是新情况，更新本文档

---

## 7. 参考文档

- `src/styles/YON_DESIGN_CONSTANTS.md` - 设计规范速查表
- `src/styles/YON_EP_GUIDE.md` - Element Plus 封装规范
- `src/styles/DESIGN_CHECKLIST.md` - 设计决策检查清单
- `src/views/ComponentComparison.vue` - 组件对比测试页面

---

**【最后提醒】遵循本规范，确保 UI 风格一致性和可维护性！**
