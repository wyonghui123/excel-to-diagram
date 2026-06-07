# 侧边栏优化方案

## 问题
左侧菜单占用空间较大，影响主要内容区域的显示。

## 解决方案

### 方案 1：侧边栏折叠（推荐）
折叠后只显示图标，展开时显示完整菜单。

**特点：**
- 默认展开，用户可手动折叠
- 折叠后只占 64px 宽度（原来是 240px）
- 点击菜单项可自动展开
- 适合多层级菜单

### 方案 2：减小默认宽度
将默认宽度从 240px 减小到 160px。

### 方案 3：顶部导航
完全移除侧边栏，使用顶部导航。

## 使用方法

### 基础用法（自动折叠）

```vue
<template>
  <AppLayout
    :show-sidebar="true"
    :sidebar-items="menuItems"
    :sidebar-active="activeKey"
    :sidebar-collapsed="isCollapsed"
    @sidebar-select="handleSelect"
    @sidebar-collapse="handleCollapse"
  >
    <!-- 内容 -->
  </AppLayout>
</template>

<script setup>
import { ref } from 'vue'
import { AppLayout } from '@/components/common'

const isCollapsed = ref(false)
const activeKey = ref('home')

const menuItems = [
  { key: 'home', label: '首页', icon: 'Home', to: '/' },
  { key: 'data', label: '数据管理', icon: 'Data', to: '/data' },
  { key: 'settings', label: '设置', icon: 'Setting', to: '/settings' }
]

function handleSelect(key) {
  activeKey.value = key
  console.log('Selected:', key)
}

function handleCollapse(collapsed) {
  isCollapsed.value = collapsed
  console.log('Collapsed:', collapsed)
}
</script>
```

### 默认折叠

```vue
<template>
  <AppLayout
    :sidebar-collapsed="true"
    :sidebar-items="menuItems"
  >
    <!-- 内容 -->
  </AppLayout>
</template>
```

### 控制折叠的按钮

```vue
<template>
  <div>
    <el-button @click="toggleSidebar">
      {{ isCollapsed ? '展开' : '折叠' }}侧边栏
    </el-button>
    
    <AppLayout :sidebar-collapsed="isCollapsed">
      <!-- 内容 -->
    </AppLayout>
  </div>
</template>

<script setup>
import { ref } from 'vue'
const isCollapsed = ref(true)
const toggleSidebar = () => isCollapsed.value = !isCollapsed.value
</script>
```

## AppSideNav Props

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `items` | Array | [] | 菜单项列表 |
| `modelValue` | String/Number | - | 当前选中的菜单 key |
| `collapsible` | Boolean | false | 是否可折叠 |
| `collapsed` | Boolean | false | 是否折叠状态 |
| `width` | Number | 200 | 展开时的宽度 |

## AppLayout Props

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `sidebarItems` | Array | [] | 菜单项列表 |
| `sidebarActive` | String/Number | '' | 当前选中的菜单 key |
| `sidebarCollapsed` | Boolean | false | 是否折叠状态 |
| `sidebarWidth` | Number/String | 240 | 展开时的宽度 |

## AppLayout Events

| 事件 | 参数 | 说明 |
|------|------|------|
| `sidebar-select` | (key) | 菜单选中时触发 |
| `sidebar-collapse` | (collapsed) | 折叠状态变化时触发 |

## 菜单项格式

```javascript
{
  key: 'home',        // 唯一标识
  label: '首页',      // 显示文本
  icon: 'Home',       // 图标名称
  to: '/home',        // 跳转路径（可选）
  badge: '5',         // 徽章数字（可选）
  disabled: false,    // 是否禁用（可选）
  children: []        // 子菜单（可选）
}
```

## 效果对比

### 展开状态
```
┌────────────┬─────────────────────┐
│ 🏠 首页     │                     │
│ 📊 数据管理  │    主内容区域        │
│ ⚙️ 设置     │                     │
│            │                     │
│   [<<]     │                     │
└────────────┴─────────────────────┘
宽度: 240px
```

### 折叠状态
```
┌────┬─────────────────────┐
│ 🏠 │                     │
│ 📊 │    主内容区域        │
│ ⚙️ │                     │
│    │                     │
│ [>>]│                     │
└────┴─────────────────────┘
宽度: 64px
```

## 最佳实践

1. **重要菜单放顶部**：将最常用的功能放在顶部导航
2. **使用图标**：确保所有菜单项都有图标，便于折叠后识别
3. **自动同步**：折叠状态可以保存到 localStorage
4. **响应式设计**：小屏幕下自动折叠

## 示例代码

### 保存折叠状态

```javascript
const isCollapsed = ref(
  localStorage.getItem('sidebar-collapsed') === 'true'
)

function handleCollapse(collapsed) {
  localStorage.setItem('sidebar-collapsed', collapsed)
}
```

### 响应式折叠

```javascript
import { ref, onMounted, onUnmounted } from 'vue'

const isCollapsed = ref(false)

function checkWidth() {
  isCollapsed.value = window.innerWidth < 768
}

onMounted(() => {
  window.addEventListener('resize', checkWidth)
  checkWidth()
})

onUnmounted(() => {
  window.removeEventListener('resize', checkWidth)
})
```
