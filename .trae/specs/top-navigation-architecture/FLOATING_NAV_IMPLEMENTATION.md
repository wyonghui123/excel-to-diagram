# 浮动导航（FloatingNav）实现文档

## 概述

浮动导航是一种现代化的导航解决方案，完全替代传统的固定侧边栏，提供极致的空间利用率和流畅的用户体验。

## 核心特性

### 1. 拖拽移动
- 支持在屏幕任意位置拖拽浮动图标
- 拖拽时带有视觉反馈（放大、阴影加深）
- 释放后自动调整位置

### 2. 边缘自动吸附
- 靠近屏幕边缘时自动吸附
- 吸附时缩小为微型图标（56x56px）
- 贴近左/右/上/下边缘自动定位

### 3. 智能菜单展开
- 点击图标展开完整菜单
- 支持嵌套菜单组
- 菜单方向智能调整（左右、上下）
- 支持搜索过滤

### 4. 键盘快捷键
- `Esc` 键关闭菜单
- 流畅的动画过渡

## 技术实现

### 组件结构

```
FloatingNav/
├── FloatingNav.vue          # 主组件
└── index.js                  # 导出文件
```

### Props 接口

```typescript
interface FloatingNavProps {
  items: Array<{
    key: string
    label: string
    icon?: string
    badge?: string | number
    children?: Array<{
      key: string
      label: string
      icon?: string
      badge?: string | number
    }>
  }>
  modelValue: string | number          // 当前选中的菜单项
  searchable?: boolean                  // 是否显示搜索框，默认 true
  showFooter?: boolean                  // 是否显示底部快捷键提示，默认 true
  initialPosition?: { x: number, y: number }  // 初始位置，默认 { x: 20, y: 200 }
  dockThreshold?: number                // 吸附阈值，默认 60px
  dockSize?: number                    // 吸附后图标大小，默认 56px
}
```

### Events

```typescript
// 菜单选择事件
@select (item: MenuItem) => void

// 菜单开关事件
@toggle (isOpen: boolean) => void

// 位置变化事件
@move (position: { x: number, y: number }) => void

// v-model 更新
@update:modelValue (key: string) => void
```

## 使用示例

### 1. 独立使用

```vue
<template>
  <FloatingNav
    :items="menuItems"
    v-model="activeMenu"
    :searchable="true"
    @select="handleSelect"
    @toggle="handleToggle"
  />
</template>

<script setup>
import { ref } from 'vue'
import { FloatingNav } from '@/components/common'

const activeMenu = ref('home')

const menuItems = [
  { key: 'home', label: '首页', icon: 'Home' },
  { key: 'diagram', label: '架构图', icon: 'Document' },
  { key: 'data', label: '数据管理', icon: 'DataAnalysis' },
  { key: 'system', label: '系统管理', icon: 'Setting', children: [
    { key: 'config', label: '业务配置', icon: 'Setting' },
    { key: 'permission', label: '用户权限', icon: 'User' }
  ]}
]

function handleSelect(item) {
  console.log('Selected:', item)
}

function handleToggle(isOpen) {
  console.log('Menu is', isOpen ? 'open' : 'closed')
}
</script>
```

### 2. 在 AppLayout 中使用

```vue
<template>
  <AppLayout
    :show-sidebar="true"
    navigation-mode="floating"
    :sidebar-items="menuItems"
    :sidebar-active="activeMenu"
    @sidebar-select="handleSelect"
  />
</template>

<script setup>
import { ref } from 'vue'
import { AppLayout } from '@/components/common'

const activeMenu = ref('home')

const menuItems = [
  { key: 'home', label: '首页', icon: 'Home', to: '/' },
  { key: 'diagram', label: '架构图', icon: 'Document', to: '/diagram' },
  { key: 'data', label: '数据管理', icon: 'DataAnalysis', to: '/data' }
]
</script>
```

### 3. 切换模式

```vue
<template>
  <div>
    <el-button @click="toggleMode">
      {{ navigationMode === 'floating' ? '切换到固定侧边栏' : '切换到浮动导航' }}
    </el-button>

    <AppLayout
      :navigation-mode="navigationMode"
      :show-sidebar="true"
      :sidebar-items="menuItems"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { AppLayout } from '@/components/common'

const navigationMode = ref('floating')

function toggleMode() {
  navigationMode.value = navigationMode.value === 'floating' ? 'fixed' : 'floating'
}
</script>
```

## 交互行为

### 拖拽行为
1. **鼠标按下**：记录起始位置和按下时间
2. **鼠标移动**：
   - 更新浮动图标位置
   - 实时检测是否靠近屏幕边缘
   - 如果靠近边缘，自动吸附
3. **鼠标释放**：
   - 如果是点击（拖拽距离 < 5px 或 时间 < 150ms）：
     - 菜单关闭时：展开菜单
     - 菜单打开时：关闭菜单
   - 如果是拖拽且靠近边缘：自动吸附为小图标
   - 如果是拖拽且不在边缘：保持当前位置

### 菜单展开行为
1. **位置检测**：
   - 检测屏幕右侧空间是否足够（>= 340px）
   - 如果不够，菜单向左展开
   - 检测屏幕下方空间是否足够（>= 520px）
   - 如果不够，菜单向上展开
2. **搜索功能**：
   - 支持模糊搜索
   - 搜索时自动过滤菜单项
   - 包含子菜单的父项也会被过滤

### 边缘吸附行为
- **吸附阈值**：60px
- **吸附方向**：左、右、上、下
- **吸附后大小**：56x56px（微型图标）
- **视觉反馈**：
  - 背景变为主题色
  - 图标颜色变为白色
  - 圆角调整为 14px

## 样式定制

### CSS 变量

```css
:root {
  /* 浮动导航样式 */
  --floating-nav-bg: var(--color-bg-primary);
  --floating-nav-border-radius: 12px;
  --floating-nav-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  --floating-nav-shadow-hover: 0 6px 30px rgba(0, 0, 0, 0.2);
  --floating-nav-shadow-dragging: 0 12px 40px rgba(0, 0, 0, 0.25);

  /* 菜单面板样式 */
  --floating-nav-panel-width: 280px;
  --floating-nav-panel-max-height: 500px;
  --floating-nav-panel-radius: 12px;

  /* 过渡动画 */
  --floating-nav-transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
```

### 深色模式支持

```css
.dark {
  --floating-nav-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
  --floating-nav-shadow-hover: 0 6px 30px rgba(0, 0, 0, 0.5);
}
```

## 与固定侧边栏对比

| 特性 | 固定侧边栏 | 浮动导航 |
|------|----------|---------|
| 空间占用 | 240px (展开) / 64px (折叠) | 0px（完全隐藏）|
| 交互方式 | 始终可见，点击切换 | 需要点击展开 |
| 位置灵活性 | 固定在左侧 | 可拖拽到任意位置 |
| 边缘吸附 | 不支持 | 支持自动吸附 |
| 适用场景 | 需要频繁切换菜单 | 专注内容的工作区 |
| 学习成本 | 低 | 中等 |

## 最佳实践

### 推荐使用浮动导航的场景

1. **内容密集型应用**：如文档编辑、图表设计、数据分析
2. **AI 助手类应用**：需要最大化对话和内容区域
3. **专业工具软件**：用户熟悉界面后，主要使用键盘快捷键
4. **移动端适配**：在小屏幕设备上提供更好的体验

### 推荐使用固定侧边栏的场景

1. **导航密集型应用**：如电商后台、企业管理系统
2. **新手用户**：需要清晰的导航指引
3. **高频切换场景**：需要快速在多个模块间切换

## 性能优化

1. **虚拟滚动**：对于大量菜单项（> 100项），考虑使用虚拟滚动
2. **懒加载**：子菜单内容可以按需加载
3. **动画优化**：使用 `transform` 和 `opacity` 属性确保 GPU 加速

## 未来优化方向

1. **多点触控支持**：支持平板设备的触控手势
2. **快捷键绑定**：为常用菜单项绑定数字快捷键
3. **记忆位置**：使用 localStorage 记忆用户拖拽的位置
4. **智能推荐**：基于用户行为智能推荐菜单位置
5. **手势支持**：支持滑动手势展开/关闭菜单

## 相关文档

- [顶部导航架构设计](./spec.md)
- [企业导航设计研究](./ENTERPRISE_NAVIGATION_RESEARCH.md)
- [侧边栏优化指南](./SIDEBAR_OPTIMIZATION.md)
