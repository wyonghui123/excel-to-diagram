# 样式使用指南

> **文档版本**: v1.0
> **创建日期**: 2026-04-09
> **维护者**: 开发团队

---

## 1. 快速开始

### 1.1 样式入口

在 Vue 组件中使用时，只需导入 `index.scss`：

```javascript
// 在 main.js 或 App.vue 中
import './styles/index.scss'
```

### 1.2 立即使用变量

```scss
.my-component {
  color: var(--color-text-primary);
  background: var(--color-bg-secondary);
  padding: var(--spacing-md);
  border-radius: var(--radius-lg);
}
```

---

## 2. 设计令牌使用

### 2.1 颜色

**正确示例** ✅

```scss
// 使用语义化变量
.button {
  background: var(--color-primary);
  color: var(--color-text-inverse);
}

.alert {
  background: var(--color-error-bg);
  border-color: var(--color-error);
}
```

**错误示例** ❌

```scss
// 不要使用硬编码颜色
.button {
  background: #1890ff;  // 错误
  color: #ffffff;      // 错误
}

// 不要使用不语义化的变量名
.alert {
  background: var(--color-success);  // 语义错误
}
```

### 2.2 间距

使用4px基准的间距系统：

```scss
.card {
  padding: var(--spacing-md);      // 16px
  margin-bottom: var(--spacing-lg); // 24px
}

.form-group {
  margin-bottom: var(--spacing-form-item); // 24px
}
```

**间距值参考**：

| 变量 | 值 | 用途 |
|------|-----|------|
| `--spacing-xs` | 4px | 紧凑间距 |
| `--spacing-sm` | 8px | 小间距 |
| `--spacing-md` | 16px | 默认间距 |
| `--spacing-lg` | 24px | 大间距 |
| `--spacing-xl` | 32px | 特大间距 |

### 2.3 字体

```scss
.title {
  font-size: var(--font-size-xxl);     // 20px
  font-weight: var(--font-weight-bold); // 700
  line-height: var(--line-height-tight); // 1.25
}

.body {
  font-size: var(--font-size-md);     // 14px
  line-height: var(--line-height-normal); // 1.5
}

.caption {
  font-size: var(--font-size-xs);     // 12px
  color: var(--color-text-tertiary);
}
```

### 2.4 阴影

```scss
.card {
  box-shadow: var(--shadow-sm);  // 默认卡片
}

.card-hover:hover {
  box-shadow: var(--shadow-md); // 悬停效果
}

.modal {
  box-shadow: var(--shadow-lg);  // 模态框
}
```

### 2.5 圆角

```scss
.button {
  border-radius: var(--radius-button);  // 4px
}

.card {
  border-radius: var(--radius-card);    // 8px
}

.badge {
  border-radius: var(--radius-badge);   // 9999px
}
```

---

## 3. 组件样式使用

### 3.1 按钮

**HTML**

```html
<button class="btn btn-primary btn-md">主要操作</button>
<button class="btn btn-secondary btn-md">次要操作</button>
<button class="btn btn-text btn-sm">文字按钮</button>
<button class="btn btn-danger btn-md">删除</button>
```

**尺寸变体**：

| 类名 | 高度 | 用途 |
|------|------|------|
| `.btn-sm` | 24px | 紧凑场景 |
| `.btn-md` | 32px | 默认 |
| `.btn-lg` | 40px | 强调操作 |

### 3.2 输入框

**HTML**

```html
<input type="text" class="input input-md" placeholder="请输入">
<input type="text" class="input input-md input-error" value="错误示例">
```

### 3.3 卡片

**HTML**

```html
<div class="card">
  <div class="card-header">卡片标题</div>
  <div class="card-body">卡片内容</div>
  <div class="card-footer">卡片底部</div>
</div>

<!-- 可交互卡片 -->
<div class="card card-interactive">
  <div class="card-body">悬停时阴影会变化</div>
</div>
```

### 3.4 辅助类

**文本对齐**

```html
<p class="text-left">左对齐</p>
<p class="text-center">居中</p>
<p class="text-right">右对齐</p>
```

**间距**

```html
<div class="mt-md mb-lg">上下间距</div>
<div class="p-md">内边距</div>
```

---

## 4. 响应式开发

### 4.1 使用 Mixin

```scss
.my-component {
  padding: var(--spacing-sm);

  @include respond-to('md') {
    padding: var(--spacing-md);
  }

  @include respond-to('lg') {
    padding: var(--spacing-lg);
  }
}
```

### 4.2 响应式工具类

```html
<!-- 移动端隐藏 -->
<div class="hide-sm">在大屏幕上显示</div>

<!-- 桌面端隐藏 -->
<div class="show-xs-only">只在手机上显示</div>
```

---

## 5. 深色模式

项目已支持深色模式，使用语义化变量即可自动适配：

```scss
// ✅ 正确 - 自动适配深色模式
.text {
  color: var(--color-text-primary);
  background: var(--color-bg-secondary);
}

// ❌ 错误 - 硬编码颜色不会适配深色模式
.text {
  color: #333333;  // 深色模式下不可见
  background: #f5f7fa;
}
```

---

## 6. SCSS 混合宏

### 6.1 已有的 Mixin

```scss
// 响应式断点
@include respond-to('sm') { ... }
@include respond-to('md') { ... }

// 文本省略
@include text-ellipsis;
@include text-ellipsis-multi(2);

// 布局
@include flex-center;     // 居中
@include flex-between;   // 两端对齐
```

### 6.2 自定义 Mixin

在 `mixins.scss` 中添加项目特定的 mixin：

```scss
// 示例：添加新的 mixin
@mixin card-base {
  background: var(--color-bg-container);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-sm);
  padding: var(--spacing-md);
}
```

---

## 7. 常见问题

### 7.1 如何添加新颜色？

1. 在 `tokens.scss` 中添加变量
2. 确保语义化命名
3. 添加深色模式对应的值

```scss
// tokens.scss
--color-my-brand: #custom-color;

// 深色模式
@media (prefers-color-scheme: dark) {
  :root {
    --color-my-brand: #custom-dark-color;
  }
}
```

### 7.2 如何处理组件样式冲突？

使用 Vue 的 [scoped CSS](https://vue-loader.vuejs.org/guide/scoped-css.html) 或 CSS Modules：

```vue
<style scoped>
.my-component {
  /* 样式只作用于当前组件 */
}
</style>
```

### 7.3 如何覆盖第三方组件样式？

使用 `:deep()` 选择器（Vue 3）：

```scss
:deep(.third-party-component) {
  --color-primary: var(--color-primary);
}
```

---

## 8. UI组件使用

### 8.1 按钮组件 (AppButton)

```vue
<template>
  <!-- 基础用法 -->
  <AppButton @click="handleClick">默认按钮</AppButton>

  <!-- 按钮类型 -->
  <AppButton variant="primary">主要按钮</AppButton>
  <AppButton variant="secondary">次要按钮</AppButton>
  <AppButton variant="text">文字按钮</AppButton>
  <AppButton variant="danger">危险按钮</AppButton>

  <!-- 按钮尺寸 -->
  <AppButton size="sm">小按钮</AppButton>
  <AppButton size="md">中按钮</AppButton>
  <AppButton size="lg">大按钮</AppButton>

  <!-- 加载状态 -->
  <AppButton :loading="loading">加载中</AppButton>

  <!-- 禁用状态 -->
  <AppButton disabled>禁用按钮</AppButton>

  <!-- 块级按钮 -->
  <AppButton block>块级按钮</AppButton>

  <!-- 带图标 -->
  <AppButton :icon="PlusIcon">
    添加
  </AppButton>
</template>

<script setup>
import { AppButton } from '@/components/common'
import { PlusIcon } from '@heroicons/vue/24/outline' // 或其他图标库

const loading = ref(false)
const handleClick = () => {
  console.log('clicked')
}
</script>
```

### 8.2 输入框组件 (AppInput)

```vue
<template>
  <!-- 基础用法 -->
  <AppInput v-model="value" placeholder="请输入" />

  <!-- 带标签 -->
  <AppInput
    v-model="value"
    label="用户名"
    placeholder="请输入用户名"
  />

  <!-- 错误状态 -->
  <AppInput
    v-model="value"
    :error="errorMessage"
    placeholder="请输入"
  />

  <!-- 可清空 -->
  <AppInput
    v-model="value"
    clearable
    placeholder="可清空"
  />

  <!-- 带图标 -->
  <AppInput
    v-model="value"
    :prefix-icon="SearchIcon"
    placeholder="搜索..."
  />

  <!-- 尺寸 -->
  <AppInput v-model="value" size="sm" placeholder="小尺寸" />
  <AppInput v-model="value" size="md" placeholder="中尺寸" />
  <AppInput v-model="value" size="lg" placeholder="大尺寸" />
</template>

<script setup>
import { ref } from 'vue'
import { AppInput } from '@/components/common'
import { SearchIcon } from '@heroicons/vue/24/outline'

const value = ref('')
const errorMessage = ref('请输入正确的格式')
</script>
```

### 8.3 卡片组件 (AppCard)

```vue
<template>
  <!-- 基础用法 -->
  <AppCard title="卡片标题">
    卡片内容
  </AppCard>

  <!-- 带副标题 -->
  <AppCard
    title="卡片标题"
    subtitle="副标题描述"
  >
    卡片内容
  </AppCard>

  <!-- 带底部 -->
  <AppCard title="卡片标题">
    卡片内容
    <template #footer>
      <AppButton size="sm">操作</AppButton>
    </template>
  </AppCard>

  <!-- 可点击 -->
  <AppCard
    title="可点击卡片"
    clickable
    @click="handleCardClick"
  >
    点击此卡片会触发事件
  </AppCard>

  <!-- 阴影级别 -->
  <AppCard title="无阴影" shadow="none">内容</AppCard>
  <AppCard title="小阴影" shadow="sm">内容</AppCard>
  <AppCard title="中阴影" shadow="md">内容</AppCard>
  <AppCard title="大阴影" shadow="lg">内容</AppCard>
</template>

<script setup>
import { AppCard, AppButton } from '@/components/common'

const handleCardClick = () => {
  console.log('card clicked')
}
</script>
```

### 8.4 选择框组件 (AppSelect)

```vue
<template>
  <!-- 基础用法 -->
  <AppSelect
    v-model="selected"
    :options="options"
    placeholder="请选择"
  />

  <!-- 可搜索 -->
  <AppSelect
    v-model="selected"
    :options="options"
    searchable
    placeholder="搜索并选择"
  />

  <!-- 多选 -->
  <AppSelect
    v-model="selectedMultiple"
    :options="options"
    multiple
    placeholder="可多选"
  />
</template>

<script setup>
import { ref } from 'vue'
import { AppSelect } from '@/components/common'

const selected = ref('')
const selectedMultiple = ref([])

const options = [
  { label: '选项1', value: '1' },
  { label: '选项2', value: '2' },
  { label: '选项3', value: '3', disabled: true }
]
</script>
```

### 8.5 模态框组件 (AppModal)

```vue
<template>
  <!-- 基础用法 -->
  <AppButton @click="showModal = true">打开模态框</AppButton>

  <AppModal
    v-model="showModal"
    title="模态框标题"
  >
    模态框内容
  </AppModal>

  <!-- 带默认底部按钮 -->
  <AppModal
    v-model="showModal"
    title="确认操作"
    show-default-footer
    @confirm="handleConfirm"
    @cancel="handleCancel"
  >
    确定要执行此操作吗？
  </AppModal>

  <!-- 自定义底部 -->
  <AppModal v-model="showModal" title="自定义底部">
    内容
    <template #footer>
      <AppButton variant="secondary" @click="showModal = false">
        取消
      </AppButton>
      <AppButton variant="primary" :loading="loading" @click="handleSubmit">
        提交
      </AppButton>
    </template>
  </AppModal>
</template>

<script setup>
import { ref } from 'vue'
import { AppModal, AppButton } from '@/components/common'

const showModal = ref(false)
const loading = ref(false)

const handleConfirm = () => {
  console.log('confirmed')
  showModal.value = false
}

const handleCancel = () => {
  console.log('cancelled')
}

const handleSubmit = async () => {
  loading.value = true
  // 执行提交操作
  await submitData()
  loading.value = false
  showModal.value = false
}
</script>
```

---

## 9. 最佳实践

### 9.1 组件导入

推荐使用统一导入方式：

```javascript
// ✅ 推荐
import { AppButton, AppInput, AppCard } from '@/components/common'

// ❌ 不推荐
import AppButton from '@/components/common/AppButton/AppButton.vue'
```

### 9.2 样式覆盖

当需要覆盖组件默认样式时：

```vue
<template>
  <AppButton class="my-custom-button">按钮</AppButton>
</template>

<style scoped>
.my-custom-button {
  /* 自定义样式 */
  background: var(--color-success);
}
</style>
```

### 9.3 表单验证

结合AppInput的错误状态实现表单验证：

```vue
<template>
  <form @submit.prevent="handleSubmit">
    <AppInput
      v-model="form.email"
      label="邮箱"
      :error="errors.email"
      @blur="validateEmail"
    />
    <AppButton type="submit" :loading="submitting">
      提交
    </AppButton>
  </form>
</template>
```

---

## 10. 相关文件

| 文件 | 说明 |
|------|------|
| [tokens.scss](./tokens.scss) | 设计令牌完整定义 |
| [variables.scss](./variables.scss) | CSS 变量 |
| [mixins.scss](./mixins.scss) | SCSS 混合宏 |
| [utilities.scss](./utilities.scss) | 实用工具类 |
| [COMPONENT_STANDARDS.md](./COMPONENT_STANDARDS.md) | 组件规范 |
| [MIGRATION_GUIDE.md](./MIGRATION_GUIDE.md) | 迁移指南 |

---

## 11. Element Plus 主题定制

### 11.1 核心问题

Element Plus 使用 CSS 变量进行主题定制，但存在以下复杂性：

1. **unplugin-vue-components 自动导入**：按需导入组件时会重新注入默认 CSS 变量
2. **样式层叠顺序**：多个样式表定义相同变量，后者覆盖前者
3. **硬编码颜色**：部分组件可能直接使用 `#409eff`（Element Plus 默认蓝色）

### 11.2 解决方案

使用更高特异性的选择器 + `!important` 强制覆盖：

```css
/* element-plus-overrides.css */
:root:root,
html:root,
html :root {
  --el-color-primary: #ea580c !important;
  --el-color-primary-light-9: #fff7ed !important;
  /* ... 其他变量 */
}
```

### 11.3 禁止事项

```scss
// ❌ 禁止硬编码 Element Plus 默认颜色
.icon:hover {
  color: #409eff;  // 错误！
}

// ✅ 正确：使用 CSS 变量
.icon:hover {
  color: var(--el-color-primary, #ea580c);
}
```

### 11.4 表格排序规范

```scss
// 表头悬停不变色
.el-table th.el-table__cell:hover {
  background-color: #fafafa !important;
}

// 排序图标悬停不变色
.el-table .caret-wrapper:hover {
  background: transparent !important;
}

// 仅在激活状态显示主色
.el-table th.ascending .sort-caret.ascending {
  border-bottom-color: var(--el-color-primary) !important;
}
```

### 11.5 调试方法

```javascript
// 检查 CSS 变量实际值
const style = getComputedStyle(document.documentElement);
console.log(style.getPropertyValue('--el-color-primary'));
// 预期: #ea580c（不是 #409eff）
```

---

## 12. 更新记录

| 日期 | 版本 | 变更内容 |
|------|------|----------|
| 2026-05-10 | v1.2 | 新增 Element Plus 主题定制章节，包含 CSS 变量覆盖、禁止事项、表格排序规范、调试方法 |
| 2026-04-09 | v1.1 | 添加UI组件使用示例 |
| 2026-04-09 | v1.0 | 初始版本 |
