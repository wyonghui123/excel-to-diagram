# UI设计常见问题（FAQ）

> 本文档收集了UI设计中的常见问题和标准答案，供智能体在遇到UI相关问题时快速查阅。

---

## Q1: Tab导航应该用什么样式？

### 问题
用户反馈"tab样式看起来很奇怪"或"tab样式有问题"

### 答案
**Tab导航必须使用底部指示线样式，不使用填充背景。**

```vue
<!-- ✅ 正确：底部指示线 -->
<nav class="tabs">
  <button class="tab tab--active">标签1</button>
  <button class="tab">标签2</button>
</nav>

<style scoped>
.tabs {
  display: flex;
  border-bottom: 1px solid var(--color-border);
}

.tab {
  padding: var(--spacing-md) 0;
  color: var(--color-text-secondary);
  border: none;
  border-bottom: 2px solid transparent;
}

.tab--active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
}
</style>
```

```vue
<!-- ❌ 错误：使用 AppButton 作为 Tab -->
<AppButton variant="primary">标签</AppButton>

<!-- ❌ 错误：填充背景 -->
.tab--active {
  background: var(--color-primary);
  color: white;
}
```

### 规范依据
yonDesign规范：Tab使用底部指示线表示激活状态。

---

## Q2: 侧边导航应该用什么样式？

### 问题
用户反馈"左侧导航样式有问题"或"导航看起来像按钮"

### 答案
**侧边导航必须使用左侧指示线样式，不使用背景填充。**

```vue
<!-- ✅ 正确：左侧指示线 -->
<aside class="sidebar">
  <button class="nav-item nav-item--active">菜单1</button>
  <button class="nav-item">菜单2</button>
</aside>

<style scoped>
.sidebar {
  width: 200px;
  border-right: 1px solid var(--color-border);
}

.nav-item {
  display: flex;
  align-items: center;
  border-left: 2px solid transparent;
  color: var(--color-text-secondary);
}

.nav-item--active {
  border-left-color: var(--color-primary);
  color: var(--color-primary);
}
</style>
```

### 规范依据
yonDesign规范：侧边导航使用左侧指示线表示激活状态。

---

## Q3: 表格文本颜色应该用什么？

### 问题
用户反馈"文字看起来像有删除线"或"文本对比度不够"

### 答案
**表格内容使用 `--color-text-primary`，表头使用 `--color-text-secondary`。**

```scss
// ✅ 正确
.data-table td {
  color: var(--color-text-primary);  // #333333
}

.data-table th {
  color: var(--color-text-secondary);  // #666666
  font-weight: var(--font-weight-medium);
}
```

```scss
// ❌ 错误：使用 tertiary 颜色
.data-table td {
  color: var(--color-text-tertiary);  // #999999 - 对比度不足
}
```

### 颜色变量说明

| 变量 | 色值 | 用途 |
|------|------|------|
| `--color-text-primary` | #333333 | 主要文本、表格内容 |
| `--color-text-secondary` | #666666 | 次要文本、表头 |
| `--color-text-tertiary` | #999999 | 占位符、禁用状态 |
| `--color-text-disabled` | #cccccc | 禁用文本 |

---

## Q4: 滚动条应该怎么处理？

### 问题
用户反馈"滚动条样式不统一"或"滚动条看起来很奇怪"

### 答案
**使用浏览器默认滚动条，禁止全局自定义。**

```scss
// ✅ 正确：使用浏览器默认
.content {
  overflow-y: auto;
}
```

```scss
// ❌ 错误：自定义滚动条
::-webkit-scrollbar {
  width: 8px;
}

::-webkit-scrollbar-thumb {
  background: var(--color-primary);
  border-radius: 4px;
}
```

### 规范依据
yonDesign规范：使用浏览器原生滚动条，保持一致的跨平台体验。

---

## Q5: 消息通知应该怎么实现？

### 问题
用户看到弹出alert，或消息通知不统一

### 答案
**必须使用 `useMessage()` composable，禁止使用 `alert()`。**

```javascript
// ✅ 正确
import { useMessage } from '@/composables/useMessage'
const message = useMessage()

message.success('操作成功')
message.error('保存失败')
message.warning('警告信息')
message.info('提示信息')
```

```javascript
// ❌ 错误
alert('操作成功')  // 禁止使用
```

### 规范依据
yonDesign规范 + 项目规则：所有操作反馈使用统一消息服务。

---

## Q6: 是否有可复用的UI组件？

### 问题
需要实现Tab、导航、日志等功能，不知道有没有现成组件

### 答案
**已有以下可复用组件，必须优先使用：**

| 组件 | 路径 | 用途 |
|------|------|------|
| `AppTabs` | `src/components/common/AppTabs/` | Tab导航 |
| `AppSideNav` | `src/components/common/AppSideNav/` | 侧边导航 |
| `AuditLog` | `src/components/common/AuditLog/` | 变更日志 |
| `AppButton` | `src/components/common/AppButton/` | 按钮 |
| `MetaTable` | `src/components/common/MetaTable.vue` | 数据表格 |

### 使用示例

```vue
<script setup>
import { AppTabs, AppSideNav, AuditLog } from '@/components/common'

// Tab导航
<AppTabs v-model="activeTab" :tabs="[
  { key: 'tab1', label: '标签1' },
  { key: 'tab2', label: '标签2' }
]" />

// 侧边导航
<AppSideNav v-model="currentMenu" :items="[
  { key: 'menu1', label: '菜单1', icon: 'home' }
]" />

// 日志展示
<AuditLog :logs="logs" :loading="loading" />
</script>
```

---

## Q7: 设计令牌（CSS变量）有哪些？

### 问题
不确定应该使用哪个CSS变量

### 答案
**必须使用设计令牌，禁止硬编码颜色值。**

### 颜色

```scss
--color-primary: #ea580c;           // 主色
--color-primary-hover: #f97316;     // 悬停
--color-primary-active: #c2410c;    // 激活

--color-text-primary: #333333;      // 主要文本
--color-text-secondary: #666666;     // 次要文本
--color-text-tertiary: #999999;      // 辅助文本

--color-bg-primary: #ffffff;
--color-bg-secondary: #f5f7fa;
--color-bg-tertiary: #f0f0f0;

--color-border: #e8e8e8;
--color-border-light: #f0f0f0;
```

### 间距

```scss
--spacing-xs: 4px;
--spacing-sm: 8px;
--spacing-md: 16px;
--spacing-lg: 24px;
--spacing-xl: 32px;
```

### 字体

```scss
--font-size-xs: 12px;
--font-size-sm: 13px;
--font-size-md: 14px;
--font-size-lg: 16px;

--font-weight-normal: 400;
--font-weight-medium: 500;
--font-weight-semibold: 600;
```

### 圆角

```scss
--radius-sm: 4px;
--radius-md: 8px;
--radius-lg: 12px;
```

---

## Q8: 如何确保代码符合UI规范？

### 问题
不确定自己的代码是否符合UI规范

### 答案
**在开发前、开发中、开发后进行以下检查：**

### 开发前
- [ ] 读取 `.trae/context/developer/ui-design-standards.md`
- [ ] 检查是否有现有组件可复用
- [ ] 确认需要实现的UI组件类型

### 开发中
- [ ] 使用设计令牌而非硬编码
- [ ] 遵循Tab/导航样式规范
- [ ] 使用 `useMessage()` 而非 `alert()`

### 开发后
- [ ] 自检清单：
  - [ ] Tab使用底部指示线？
  - [ ] 侧边导航使用左侧指示线？
  - [ ] 文本颜色使用正确？
  - [ ] 没有全局自定义滚动条？
  - [ ] 组件复用最大化？

### Code Review时
使用 [review-checklist.md](../.trae/context/reviewer/review-checklist.md) 中的 **Stage 2: UI规范审查** 检查项。

---

## 相关文档

| 文档 | 说明 |
|------|------|
| [UI_COMPONENT_GUIDELINES.md](./UI_COMPONENT_GUIDELINES.md) | 详细UI组件规范 |
| [YONYOU_DESIGN.md](../src/styles/YONYOU_DESIGN.md) | yonDesign设计系统 |
| [.trae/context/developer/ui-design-standards.md](../.trae/context/developer/ui-design-standards.md) | 开发者UI规范速查 |

---

**最后更新**: 2026-05-07
